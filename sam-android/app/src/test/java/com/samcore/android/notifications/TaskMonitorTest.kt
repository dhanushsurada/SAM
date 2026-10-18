package com.samcore.android.notifications

import com.samcore.android.data.transport.TaskEvent
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TaskStatus
import com.samcore.android.data.transport.TransportResult
import com.samcore.android.fakes.FakeSamTransport
import com.samcore.android.fakes.FakeTaskKeepAlive
import com.samcore.android.fakes.FakeTaskNotifier
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UnconfinedTestDispatcher so TaskMonitor's internally-launched coroutine
 * (it owns its own scope on purpose — see TaskMonitor's doc comment) runs
 * essentially synchronously with watch(), since none of these fakes have a
 * real suspension point. Not run by an actual test task in this environment
 * — see the build report.
 *
 * "Navigating away doesn't stop monitoring" (the property this whole class
 * exists for) isn't something a standalone unit test can demonstrate in
 * isolation — there's no ViewModel or navigation here to detach from. That
 * property rests on TaskMonitor's scope being constructed once in
 * AppContainer, independent of any ViewModel, plus the fact that nothing in
 * TaskStatusViewModel holds a job that clearing it would cancel — an
 * architectural fact to verify by reading AppContainer.kt and
 * TaskStatusViewModel.kt together, not a thing this file asserts.
 *
 * The keep-alive / isWatching / cap tests below were added with the foreground
 * service. The two cap tests use a TestCoroutineScheduler passed explicitly to
 * the monitor's dispatcher so time is virtual — they advance that scheduler by
 * hand rather than waiting. The "stale work" tests came out of running the real
 * TaskMonitor on real threads, which showed a lookup result from a just-replaced
 * watch could still overwrite the new watch's snapshot; they force that window
 * deterministically (gates / a hook in the keep-alive call) instead of relying on
 * timing. Like everything in this file they have been type-checked but NEVER
 * executed by JUnit (see the build report).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TaskMonitorTest {

    private fun taskMonitor(
        transport: FakeSamTransport,
        notifier: FakeTaskNotifier,
        keepAlive: TaskKeepAlive = FakeTaskKeepAlive(),
        scope: CoroutineScope = CoroutineScope(UnconfinedTestDispatcher()),
        maxWatchMillis: Long = TaskMonitor.DEFAULT_MAX_WATCH_MILLIS,
    ): TaskMonitor = TaskMonitor(transport, notifier, keepAlive, scope, maxWatchMillis)

    private fun snapshot(status: TaskStatus, taskId: String = "t-1") = TaskSnapshot(
        taskId = taskId,
        instruction = "open chrome",
        inputType = "text",
        status = status,
    )

    @Test
    fun `watch collects emitted events`() = runTest {
        val transport = FakeSamTransport().apply {
            taskEventsToEmit = listOf(
                TaskEvent(type = "progress", taskId = "t-1", phase = "planning", message = "Planning the steps"),
                TaskEvent(type = "progress", taskId = "t-1", phase = "executing", message = "Opening Chrome"),
            )
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.QUEUED))

        assertEquals(2, monitor.events.value.size)
        assertEquals("executing", monitor.events.value.last().phase)
    }

    @Test
    fun `stream completion triggers an authoritative status lookup`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertEquals("t-1", transport.lastGetTaskId)
        assertEquals(TaskStatus.COMPLETED, monitor.snapshot.value?.status)
    }

    @Test
    fun `notifier fires when the authoritative status is terminal`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()

        taskMonitor(transport, notifier).watch(snapshot(TaskStatus.EXECUTING))

        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.first().status)
    }

    @Test
    fun `notifier does NOT fire when the authoritative status is still running`() = runTest {
        // Simulates a dropped SSE connection on a task that hasn't actually
        // finished — the exact case the terminal check exists to prevent.
        val transport = FakeSamTransport().apply {
            taskEventsError = java.io.IOException("connection dropped")
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val notifier = FakeTaskNotifier()

        taskMonitor(transport, notifier).watch(snapshot(TaskStatus.EXECUTING))

        assertTrue(notifier.notifiedSnapshots.isEmpty())
    }

    @Test
    fun `notifier does not fire when the follow-up getTask call itself fails`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Failure("unreachable"))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)
        val initial = snapshot(TaskStatus.EXECUTING)

        monitor.watch(initial)

        assertTrue(notifier.notifiedSnapshots.isEmpty())
        // Last-known snapshot is left alone rather than cleared — the UI
        // should keep showing what it last knew, not blank out on a failed refresh.
        assertEquals(initial, monitor.snapshot.value)
    }

    @Test
    fun `watching a new task cancels the previous still-running watch`() = runTest {
        val transport = FakeSamTransport().apply {
            taskEventsNeverCompletesForId = "t-1" // t-1's stream hangs open; t-2's completes normally
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED, taskId = "t-2")))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING, taskId = "t-1")) // never completes on its own
        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2"))

        // If the first watch weren't actually cancelled, getTask would never
        // be called at all (t-1's stream never completes on its own) —
        // getting here with t-2 confirms the second watch() pre-empted the
        // first rather than queuing behind it.
        assertEquals("t-2", transport.lastGetTaskId)
        assertEquals("t-2", monitor.snapshot.value?.taskId)
    }

    // --- keep-alive request + isWatching (the flag the foreground service obeys) ---

    @Test
    fun `isWatching is false before any watch and no keep-alive has been requested`() {
        val keepAlive = FakeTaskKeepAlive()
        val monitor = taskMonitor(FakeSamTransport(), FakeTaskNotifier(), keepAlive)

        assertFalse(monitor.isWatching.value)
        assertEquals(0, keepAlive.startCount)
    }

    @Test
    fun `each watch requests the keep-alive once`() = runTest {
        val keepAlive = FakeTaskKeepAlive()
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED, taskId = "t-1")))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED, taskId = "t-2")))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier(), keepAlive)

        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-1"))
        assertEquals(1, keepAlive.startCount)

        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2"))
        assertEquals(2, keepAlive.startCount)
    }

    @Test
    fun `isWatching is true while the stream is still open`() = runTest {
        val transport = FakeSamTransport().apply { taskEventsNeverCompletesForId = "t-1" }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertTrue(monitor.isWatching.value)
    }

    @Test
    fun `isWatching goes false once the task is terminal`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `isWatching goes false when the stream drops on a task that is still running`() = runTest {
        // The zombie-service case: the watch ends but the task is NOT terminal,
        // so nothing would ever flip a "terminal reached" flag. The service
        // must still be released.
        val transport = FakeSamTransport().apply {
            taskEventsError = java.io.IOException("connection dropped")
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertFalse(monitor.isWatching.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
    }

    @Test
    fun `isWatching goes false even when the follow-up lookup fails`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Failure("unreachable"))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `replacing a watch keeps isWatching true`() = runTest {
        // Both streams stay open, so only the supersede logic can end the
        // first. Its cancellation completes straight away (Unconfined) — if
        // that completion cleared the flag, the service would stop while the
        // second task was still being watched.
        val transport = FakeSamTransport().apply {
            taskEventsNeverCompleteForIds += setOf("t-1", "t-2")
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier())

        monitor.watch(snapshot(TaskStatus.EXECUTING, taskId = "t-1"))
        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2"))

        assertTrue(monitor.isWatching.value)
        assertEquals("t-2", monitor.snapshot.value?.taskId)
        assertNull(transport.lastGetTaskId) // the superseded watch must not run a lookup
    }

    @Test
    fun `stopWatching clears isWatching and announces nothing`() = runTest {
        val transport = FakeSamTransport().apply { taskEventsNeverCompletesForId = "t-1" }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)
        monitor.watch(snapshot(TaskStatus.EXECUTING))

        monitor.stopWatching()

        assertFalse(monitor.isWatching.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
        assertNull(transport.lastGetTaskId)
    }

    @Test
    fun `a keep-alive that throws does not stop the watch`() = runTest {
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val keepAlive = FakeTaskKeepAlive(failWith = IllegalStateException("background start not allowed"))
        val monitor = taskMonitor(transport, notifier, keepAlive)

        monitor.watch(snapshot(TaskStatus.EXECUTING))

        assertEquals(1, keepAlive.startCount)
        assertEquals(1, notifier.notifiedSnapshots.size) // watching and notifying still worked
        assertFalse(monitor.isWatching.value)
    }

    // --- stale work from a watch that has been superseded or stopped ----------------
    //
    // Cancellation is cooperative, so a watch can still deliver a lookup result or
    // an event a moment after it was replaced. These tests force exactly that and
    // check it cannot touch the newer watch's state. The gate-based ones hold the
    // old watch inside its lookup (FakeSamTransport.getTaskGate, which answers
    // even if the caller was cancelled meanwhile). getTaskResults being empty at the
    // end proves the stale answer really was fetched, i.e. the test is not
    // passing only because the lookup never ran.

    @Test
    fun `a lookup that is slow but still current is applied and announced`() = runTest {
        // Control for the next two tests: same gate, no supersede.
        val gate = CompletableDeferred<Unit>()
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
            getTaskGate = gate
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)

        monitor.watch(snapshot(TaskStatus.EXECUTING))
        assertTrue(monitor.isWatching.value)
        gate.complete(Unit)

        assertEquals(TaskStatus.COMPLETED, monitor.snapshot.value?.status)
        assertEquals(1, notifier.notifiedSnapshots.size)
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `a lookup result that arrives after the watch was superseded is dropped`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val transport = FakeSamTransport().apply {
            taskEventsNeverCompleteForIds += "t-2"
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED, taskId = "t-1")))
            getTaskGate = gate
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)

        monitor.watch(snapshot(TaskStatus.EXECUTING, taskId = "t-1")) // its stream ends at once, then it waits inside the lookup
        assertTrue(transport.getTaskReachedGate.isCompleted)
        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2")) // supersedes it mid-lookup
        gate.complete(Unit) // the stale answer arrives anyway

        assertTrue(transport.getTaskResults.isEmpty())
        assertEquals("t-2", monitor.snapshot.value?.taskId) // not overwritten by t-1's COMPLETED snapshot
        assertTrue(notifier.notifiedSnapshots.isEmpty())
        assertTrue(monitor.isWatching.value) // t-2 is still being watched
    }

    @Test
    fun `a lookup result that arrives after stopWatching is dropped`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val transport = FakeSamTransport().apply {
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
            getTaskGate = gate
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier)
        val initial = snapshot(TaskStatus.EXECUTING)

        monitor.watch(initial)
        assertTrue(transport.getTaskReachedGate.isCompleted)
        monitor.stopWatching()
        gate.complete(Unit)

        assertTrue(transport.getTaskResults.isEmpty())
        assertEquals(initial, monitor.snapshot.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `an event delivered to a superseded watch is not appended to the new watch's list`() = runTest {
        // watch() has already reset the event list when it calls keepAlive.start(),
        // yet the old watch is not cancelled until a few lines later. Make the old
        // stream deliver an event right in that gap.
        val oldStream = MutableSharedFlow<TaskEvent>(extraBufferCapacity = 1)
        val transport = FakeSamTransport().apply {
            taskEventsOverride = { id -> if (id == "t-1") oldStream else flow<TaskEvent> { awaitCancellation() } }
        }
        val keepAlive = FakeTaskKeepAlive()
        val monitor = taskMonitor(transport, FakeTaskNotifier(), keepAlive)
        keepAlive.onStart = { call ->
            if (call == 2) {
                oldStream.tryEmit(TaskEvent(type = "progress", taskId = "t-1", phase = "executing", message = "late"))
            }
        }

        monitor.watch(snapshot(TaskStatus.EXECUTING, taskId = "t-1"))
        assertEquals(1, oldStream.subscriptionCount.value) // the old watch really is collecting
        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2"))

        assertTrue(monitor.events.value.isEmpty())
    }

    // --- the cap (virtual time) ---------------------------------------------------

    @Test
    fun `a stream that never ends is abandoned at the cap and a still-running task stays silent`() {
        val scheduler = TestCoroutineScheduler()
        val transport = FakeSamTransport().apply {
            taskEventsNeverCompletesForId = "t-1"
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(
            transport,
            notifier,
            scope = CoroutineScope(UnconfinedTestDispatcher(scheduler)),
            maxWatchMillis = 1_000,
        )

        monitor.watch(snapshot(TaskStatus.EXECUTING))
        assertTrue(monitor.isWatching.value)

        scheduler.advanceTimeBy(999)
        scheduler.runCurrent()
        assertTrue(monitor.isWatching.value) // one millisecond short of the cap

        scheduler.advanceTimeBy(2)
        scheduler.runCurrent()
        assertFalse(monitor.isWatching.value)
        assertEquals("t-1", transport.lastGetTaskId) // the authoritative lookup still ran
        assertTrue(notifier.notifiedSnapshots.isEmpty()) // task is still EXECUTING: silent
    }

    @Test
    fun `at the cap a task that turned out to be finished is still announced`() {
        val scheduler = TestCoroutineScheduler()
        val transport = FakeSamTransport().apply {
            taskEventsNeverCompletesForId = "t-1" // e.g. the terminal event was lost on a flaky link
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(
            transport,
            notifier,
            scope = CoroutineScope(UnconfinedTestDispatcher(scheduler)),
            maxWatchMillis = 1_000,
        )

        monitor.watch(snapshot(TaskStatus.EXECUTING))
        scheduler.advanceTimeBy(1_001)
        scheduler.runCurrent()

        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.first().status)
        assertFalse(monitor.isWatching.value)
    }
}
