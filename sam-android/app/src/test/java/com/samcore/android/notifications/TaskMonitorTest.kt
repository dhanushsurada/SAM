package com.samcore.android.notifications

import com.samcore.android.data.transport.TaskEvent
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TaskStatus
import com.samcore.android.data.transport.TransportResult
import com.samcore.android.fakes.FakeSamTransport
import com.samcore.android.fakes.FakeTaskKeepAlive
import com.samcore.android.fakes.FakeTaskNotifier
import com.samcore.android.fakes.StreamScript
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
import org.junit.Assert.assertThrows
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
 * timing. The reconnect tests at the end drive a virtual clock by hand and assert
 * the wait schedule exactly. Like everything in this file they have been
 * type-checked but NEVER executed by JUnit (see the build report).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TaskMonitorTest {

    // reconnectBackoffMillis defaults to EMPTY here — no reconnecting — so every
    // test written before reconnecting existed keeps testing the single-attempt
    // behavior it was written for (an empty list is that mode, not a special
    // case). The reconnect tests at the end opt in explicitly; one of them
    // builds the monitor without this helper to exercise the production default.
    private fun taskMonitor(
        transport: FakeSamTransport,
        notifier: FakeTaskNotifier,
        keepAlive: TaskKeepAlive = FakeTaskKeepAlive(),
        scope: CoroutineScope = CoroutineScope(UnconfinedTestDispatcher()),
        maxWatchMillis: Long = TaskMonitor.DEFAULT_MAX_WATCH_MILLIS,
        reconnectBackoffMillis: List<Long> = emptyList(),
    ): TaskMonitor = TaskMonitor(transport, notifier, keepAlive, scope, maxWatchMillis, reconnectBackoffMillis)

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

    // --- reconnecting (virtual time) -----------------------------------------------
    //
    // A stream that ends is not a task that ended: when the status lookup says
    // "still running" (or cannot say), the monitor waits and opens a new stream
    // that resumes after the last event it showed. Everything here runs on a clock
    // the test moves by hand, so the schedule is asserted exactly (999 ms: nothing
    // yet; 1000 ms: reconnected) instead of by sleeping. FakeSamTransport's
    // streamScripts script one connection each; taskEventsRequests records the
    // (taskId, afterSeq) of every connection actually made.

    private class VirtualClock {
        val scheduler = TestCoroutineScheduler()
        val scope = CoroutineScope(UnconfinedTestDispatcher(scheduler))

        /** Moves time forward and runs everything that falls due, including work scheduled for exactly the new instant. */
        fun advance(millis: Long) {
            scheduler.advanceTimeBy(millis)
            scheduler.runCurrent()
        }
    }

    private fun event(seq: Long?, phase: String, taskId: String = "t-1") =
        TaskEvent(type = "execution.step", taskId = taskId, phase = phase, message = "$phase step", seq = seq)

    private fun request(taskId: String, afterSeq: Long?) = taskId to afterSeq

    @Test
    fun `a dropped stream on a running task is reconnected after the delay, resuming from the last event shown`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(
                events = listOf(event(1, "received"), event(2, "executing")),
                failure = java.io.IOException("connection dropped"),
            )
            streamScripts += StreamScript(events = listOf(event(3, "verifying"), event(4, "completed")))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(1_000))

        monitor.watch(snapshot(TaskStatus.QUEUED))

        // The first connection has dropped, the lookup says the task is still
        // running, and the monitor is now waiting out its delay.
        assertEquals(listOf(request("t-1", null)), transport.taskEventsRequests)
        assertEquals(listOf<Long?>(1, 2), monitor.events.value.map { it.seq })
        assertTrue(monitor.isWatching.value) // the foreground service must not stop while we wait
        assertTrue(notifier.notifiedSnapshots.isEmpty())

        clock.advance(999)
        assertEquals(1, transport.taskEventsRequests.size) // one millisecond short

        clock.advance(1)
        assertEquals(listOf(request("t-1", null), request("t-1", 2)), transport.taskEventsRequests)
        assertEquals(listOf<Long?>(1, 2, 3, 4), monitor.events.value.map { it.seq })
        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.single().status)
        assertEquals(2, transport.getTaskCalls) // one lookup per stream that ended, none extra at the end
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `events the server replays on reconnect are not shown twice`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(
                events = listOf(event(1, "received"), event(2, "executing")),
                failure = java.io.IOException("connection dropped"),
            )
            // A server that ignores the resume point and replays everything, the
            // boundary event included.
            streamScripts += StreamScript(events = listOf(event(1, "received"), event(2, "executing"), event(3, "completed")))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier(), scope = clock.scope, reconnectBackoffMillis = listOf(100))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(100)

        assertEquals(listOf<Long?>(1, 2, 3), monitor.events.value.map { it.seq })
        assertEquals(listOf(request("t-1", null), request("t-1", 2)), transport.taskEventsRequests) // it did ask to resume
    }

    @Test
    fun `when the status lookup fails too, the watch reconnects from the beginning and announces once the task is known to be finished`() {
        // The network is down for the first attempt: the stream fails before
        // delivering anything AND the lookup fails. Nothing has been shown, so the
        // retry starts from the beginning (no resume point).
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(failure = java.io.IOException("network down"))
            streamScripts += StreamScript(events = listOf(event(1, "executing"), event(2, "completed")))
            getTaskResults.add(TransportResult.Failure("unreachable"))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(500))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        assertTrue(monitor.isWatching.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())

        clock.advance(500)

        assertEquals(listOf(request("t-1", null), request("t-1", null)), transport.taskEventsRequests)
        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.single().status)
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `events that arrived without a seq are never replayed, so the watch ends instead of reconnecting`() {
        // Nothing to resume from: reconnecting from the start would show these
        // events a second time, and de-duplicating needs a seq.
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(
                events = listOf(event(null, "received"), event(null, "executing")),
                failure = java.io.IOException("connection dropped"),
            )
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(100))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(10_000)

        assertEquals(1, transport.taskEventsRequests.size)
        assertEquals(2, monitor.events.value.size)
        assertFalse(monitor.isWatching.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
    }

    @Test
    fun `a task that finished while the stream was down is announced at once, without reconnecting`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(events = listOf(event(1, "received")), failure = java.io.IOException("connection dropped"))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(1_000))

        monitor.watch(snapshot(TaskStatus.QUEUED))

        assertEquals(1, notifier.notifiedSnapshots.size)
        assertFalse(monitor.isWatching.value)
        clock.advance(60_000)
        assertEquals(1, transport.taskEventsRequests.size) // not even one reconnect
        assertEquals(1, notifier.notifiedSnapshots.size) // and no second announcement
    }

    @Test
    fun `reconnecting gives up after the configured attempts and the watch ends silently`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            taskEventsError = java.io.IOException("unreachable") // every connection fails at once, delivering nothing
            repeat(4) { getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING))) }
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(100, 200, 400))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        assertEquals(1, transport.taskEventsRequests.size)

        clock.advance(99)
        assertEquals(1, transport.taskEventsRequests.size)
        clock.advance(1) // t = 100: first reconnect, after the first wait
        assertEquals(2, transport.taskEventsRequests.size)

        clock.advance(199)
        assertEquals(2, transport.taskEventsRequests.size)
        clock.advance(1) // t = 300: second reconnect, after the second wait
        assertEquals(3, transport.taskEventsRequests.size)

        clock.advance(399)
        assertEquals(3, transport.taskEventsRequests.size)
        clock.advance(1) // t = 700: third and last reconnect, after the third wait
        assertEquals(4, transport.taskEventsRequests.size)

        assertEquals(4, transport.getTaskCalls) // one lookup per connection
        assertFalse(monitor.isWatching.value)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
        assertEquals(TaskStatus.EXECUTING, monitor.snapshot.value?.status)

        clock.advance(60_000)
        assertEquals(4, transport.taskEventsRequests.size) // budget spent: no fifth connection
    }

    @Test
    fun `a reconnect that delivers something new restores the whole budget`() {
        // Budget of two, waits of 100 ms then 5 s. Each of the first three
        // connections delivers one new event and then drops. Progress resets the
        // schedule every time, so every wait is the short one and the budget is
        // never spent; without the reset the third drop would use the 5 s wait and
        // the fourth would exhaust the budget.
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            for (seq in 1L..3L) {
                streamScripts += StreamScript(events = listOf(event(seq, "executing")), failure = java.io.IOException("dropped"))
            }
            streamScripts += StreamScript(events = listOf(event(4, "completed")))
            repeat(3) { getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING))) }
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(100, 5_000))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(300)

        assertEquals(listOf<Long?>(null, 1, 2, 3), transport.taskEventsRequests.map { it.second })
        assertEquals(listOf<Long?>(1, 2, 3, 4), monitor.events.value.map { it.seq })
        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.single().status)
    }

    @Test
    fun `the cap still bounds reconnecting, and the final lookup still runs`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            taskEventsError = java.io.IOException("unreachable")
            repeat(3) { getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING))) }
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED))) // what the final lookup finds
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(
            transport,
            notifier,
            scope = clock.scope,
            maxWatchMillis = 1_000,
            reconnectBackoffMillis = listOf(400, 400, 400, 400, 400),
        )

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(1_001)

        assertEquals(3, transport.taskEventsRequests.size) // t = 0, 400, 800 — the wait due to end at 1200 was cut off by the cap
        assertEquals(4, transport.getTaskCalls) // one per connection, plus the final lookup
        assertEquals(1, notifier.notifiedSnapshots.size)
        assertEquals(TaskStatus.COMPLETED, notifier.notifiedSnapshots.single().status)
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `watching a new task while the old one waits to reconnect cancels that reconnect`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(events = listOf(event(1, "executing")), failure = java.io.IOException("connection dropped"))
            taskEventsNeverCompleteForIds += "t-2"
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING, taskId = "t-1")))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(1_000))

        monitor.watch(snapshot(TaskStatus.EXECUTING, taskId = "t-1")) // drops, is told "still running", now waits
        monitor.watch(snapshot(TaskStatus.QUEUED, taskId = "t-2"))
        clock.advance(60_000)

        assertEquals(1, transport.taskEventsRequests.count { it.first == "t-1" }) // never reconnected
        assertEquals(1, transport.getTaskCalls) // only t-1's single lookup: the superseded watch ran no more
        assertEquals("t-2", monitor.snapshot.value?.taskId)
        assertTrue(monitor.events.value.isEmpty())
        assertTrue(monitor.isWatching.value) // t-2 is being watched
        assertTrue(notifier.notifiedSnapshots.isEmpty())
    }

    @Test
    fun `stopWatching while waiting to reconnect cancels the reconnect`() {
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(events = listOf(event(1, "executing")), failure = java.io.IOException("connection dropped"))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = taskMonitor(transport, notifier, scope = clock.scope, reconnectBackoffMillis = listOf(1_000))

        monitor.watch(snapshot(TaskStatus.QUEUED))
        assertTrue(monitor.isWatching.value) // waiting to reconnect
        monitor.stopWatching()
        assertFalse(monitor.isWatching.value)
        clock.advance(60_000)

        assertEquals(1, transport.taskEventsRequests.size)
        assertEquals(1, transport.getTaskCalls)
        assertTrue(notifier.notifiedSnapshots.isEmpty())
    }

    @Test
    fun `with no backoff delays the monitor never reconnects`() {
        // The empty list is the "reconnecting off" setting that every older test in
        // this file relies on; this one states it outright.
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(events = listOf(event(1, "executing")), failure = java.io.IOException("connection dropped"))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
        }
        val monitor = taskMonitor(transport, FakeTaskNotifier(), scope = clock.scope, reconnectBackoffMillis = emptyList())

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(600_000)

        assertEquals(1, transport.taskEventsRequests.size)
        assertFalse(monitor.isWatching.value)
    }

    @Test
    fun `negative reconnect delays are rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            taskMonitor(FakeSamTransport(), FakeTaskNotifier(), reconnectBackoffMillis = listOf(100, -1))
        }
    }

    @Test
    fun `the production default reconnects, starting with a one second wait`() {
        // Built without the helper, so no backoff argument is passed: this is the
        // behavior the app actually gets from AppContainer.
        val clock = VirtualClock()
        val transport = FakeSamTransport().apply {
            streamScripts += StreamScript(events = listOf(event(1, "executing")), failure = java.io.IOException("connection dropped"))
            streamScripts += StreamScript(events = listOf(event(2, "completed")))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.EXECUTING)))
            getTaskResults.add(TransportResult.Success(snapshot(TaskStatus.COMPLETED)))
        }
        val notifier = FakeTaskNotifier()
        val monitor = TaskMonitor(transport, notifier, FakeTaskKeepAlive(), clock.scope)

        monitor.watch(snapshot(TaskStatus.QUEUED))
        clock.advance(999)
        assertEquals(1, transport.taskEventsRequests.size)
        clock.advance(1)

        assertEquals(2, transport.taskEventsRequests.size)
        assertEquals(1, notifier.notifiedSnapshots.size)
    }
}
