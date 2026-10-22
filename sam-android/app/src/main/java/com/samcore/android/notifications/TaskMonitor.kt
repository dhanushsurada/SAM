package com.samcore.android.notifications

import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TaskEvent
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TaskStatus
import com.samcore.android.data.transport.TransportResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Watches one task's event stream on an application-scoped coroutine — not
 * viewModelScope — specifically so it keeps running (and can still post a
 * completion notification) if the user navigates off the task-status screen
 * while a task is in flight. TaskStatusViewModel reads its state instead of
 * calling SamTransport.taskEvents() directly.
 *
 * KEEP-ALIVE. Each watch() asks [keepAlive] for a foreground service so Android
 * is much less likely to freeze/kill the process while the user is in another
 * app. [isWatching] is the single source of truth the service obeys: it stays
 * true for exactly as long as a watch is live — including while it waits to
 * reconnect — and goes false however the watch ends (terminal task, giving up
 * on reconnecting, cap expiry, cancellation), at which point the service stops
 * itself. See TaskKeepAlive for why there is no stop() call from here.
 *
 * RECONNECT. A stream that ends is not the same as a task that ended, so when
 * it does, the watch asks for the authoritative status (getTask) and:
 *  - terminal            -> announces it (once) and ends, exactly as before;
 *  - still running, or the lookup itself failed (usually: the network is down)
 *                        -> waits, then opens a new stream that resumes AFTER
 *                           the last event already shown (TaskEvent.seq ->
 *                           SamTransport.taskEvents(afterSeq)).
 * Bounded, so a dead link can never pin the foreground service:
 *  1. [reconnectBackoffMillis] lists the wait before each consecutive
 *     reconnect that follows a connection that produced no new event; its
 *     size is the budget. When it is spent the watch ends silently — the same
 *     outcome as before reconnecting existed. An empty list disables
 *     reconnecting entirely. A connection that delivers at least one new event
 *     counts as progress and restores the full budget (and the shortest wait).
 *     A connection that stays open with only heartbeats counts as no progress.
 *  2. [maxWatchMillis] still caps the whole watch, waits and lookups included.
 * Replays are harmless: an event whose seq is not above the last one shown is
 * skipped, so a server that ignores the resume point just costs bandwidth. If
 * events arrived WITHOUT a seq there is nothing safe to resume from (replaying
 * from the start would show them twice), so the watch does not reconnect.
 * Defaults are provisional and unmeasured; they assume the repo's server
 * (events numbered 1, 2, 3 … per task, `Last-Event-ID` honored) which
 * docs/iqoo/PROTOCOL.md does not describe — Agent 3's contract must.
 *
 * WHAT THIS DOES NOT DO — stated plainly, per PDR §18:
 *  - It does not survive the process being killed. A foreground service lowers
 *    the odds; nothing is persisted, and a killed process loses the watch with
 *    no recovery on relaunch.
 *  - It cannot tell a permanent failure from a transient one:
 *    TransportResult.Failure carries no status, so a task the server no longer
 *    knows (404), a revoked pairing or an unpaired app burn the whole budget
 *    (31 s of waiting with the defaults) before the watch gives up.
 *  - It does not wait for connectivity (no ConnectivityManager callback) — it
 *    just retries on a fixed schedule — and the UI is not told that it is
 *    reconnecting; the screen simply stops updating until events resume.
 *  - It does not detect gaps in seq (an event dropped inside the transport
 *    would be skipped over, not re-requested).
 *  - One live task at a time: watching a new one supersedes the previous.
 *
 * STALE WORK. Cancellation is cooperative: a watch that has just been
 * superseded (or stopped) can still be a few instructions away from writing a
 * lookup result or an event into the shared state, or from announcing. Every
 * such write is therefore made under [lock] and only if the watch's generation
 * is still the current one, so once watch()/stopWatching() has returned the old
 * watch can no longer change [snapshot] or [events]. One deliberate exception:
 * an announcement that was already decided at the instant a newer watch or a
 * stop arrived is still delivered — it is true information about a task that
 * really finished, delivered at most once, and the call into the notifier is
 * kept outside the lock so a slow system call can never block the caller of
 * watch() (usually the main thread). A superseded watch also stops reconnecting
 * (it is cancelled while waiting, and re-checks before connecting again).
 *
 * BOUNDS. A watch can never outlive [maxWatchMillis] (plus the one final
 * lookup, and whatever blocking call was in flight when the cap fired). That is
 * the backstop for a stream that stays open but never delivers a terminal event;
 * the transport's own SSE read timeout is the (faster) detector for a dead
 * connection. The default is provisional: the repo's server hard-fails a task
 * after 600 s of execution (interfaces/api/gateway.py,
 * DEFAULT_TASK_TIMEOUT_SECONDS) but that clock excludes time spent queued, so
 * the cap is set well above it. Revisit once Agent 3's contract defines task
 * timeouts and queueing.
 *
 * Takes TaskNotifier and TaskKeepAlive (interfaces) rather than a raw Context
 * so this class has no Android framework dependency at all and is fully
 * unit-testable (TaskMonitorTest). scope is an optional constructor param for
 * the same reason: tests inject a test dispatcher instead of Dispatchers.Default.
 */
class TaskMonitor(
    private val transport: SamTransport,
    private val notifier: TaskNotifier,
    private val keepAlive: TaskKeepAlive,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
    private val maxWatchMillis: Long = DEFAULT_MAX_WATCH_MILLIS,
    private val reconnectBackoffMillis: List<Long> = DEFAULT_RECONNECT_BACKOFF_MILLIS,
) {
    init {
        require(maxWatchMillis > 0) { "maxWatchMillis must be positive" }
        require(reconnectBackoffMillis.all { it >= 0 }) { "reconnect delays must not be negative" }
    }

    // Guards watchJob, watchGeneration, and — crucially — every "is this watch
    // still current? / then write shared state" pair: clearing isWatching,
    // appending an event, applying a lookup result and deciding to announce.
    // Without it, a superseded watch finishing on a background thread could
    // clear the flag between a newer watch() setting it and the service reading
    // it (the service would stop while the new watch was still running), or
    // overwrite the new watch's snapshot/events with the old task's.
    private val lock = Any()
    private var watchJob: Job? = null
    private var watchGeneration = 0L

    private val _events = MutableStateFlow<List<TaskEvent>>(emptyList())
    val events: StateFlow<List<TaskEvent>> = _events

    private val _snapshot = MutableStateFlow<TaskSnapshot?>(null)
    val snapshot: StateFlow<TaskSnapshot?> = _snapshot

    private val _isWatching = MutableStateFlow(false)

    /** True from watch() until that watch ends for any reason. Superseding a watch with a new one keeps it true. */
    val isWatching: StateFlow<Boolean> = _isWatching

    fun watch(initialSnapshot: TaskSnapshot) {
        val taskId = initialSnapshot.taskId
        synchronized(lock) {
            // Bump the generation BEFORE cancelling the old job: a cancelled
            // job's completion handler can run synchronously inside cancel(),
            // and it must already see that it has been superseded.
            val generation = ++watchGeneration
            _snapshot.value = initialSnapshot
            _events.value = emptyList()
            _isWatching.value = true
            requestKeepAlive()
            watchJob?.cancel()
            val job = scope.launch { watchUntilDone(taskId, generation) }
            // invokeOnCompletion rather than try/finally inside the coroutine:
            // a job cancelled before it ever starts never enters its body, so a
            // finally there would not run — this handler runs in every case.
            job.invokeOnCompletion { onWatchEnded(generation) }
            watchJob = job
        }
    }

    fun stopWatching() {
        synchronized(lock) {
            // Invalidate the running watch's completion handler, clear the
            // flag now (don't wait for a cancelled blocking call to unwind),
            // then cancel.
            watchGeneration++
            _isWatching.value = false
            watchJob?.cancel()
        }
    }

    private fun requestKeepAlive() {
        try {
            keepAlive.start()
        } catch (e: Exception) {
            // The contract says it must not throw; this is defense in depth.
            // Keep-alive is an optimization — watching and notifying must work
            // without it.
        }
    }

    private fun onWatchEnded(generation: Long) {
        synchronized(lock) {
            if (generation == watchGeneration) {
                _isWatching.value = false
            }
        }
    }

    private fun isCurrent(generation: Long): Boolean = synchronized(lock) { generation == watchGeneration }

    /** What a status lookup found, as far as the watch loop cares. */
    private enum class Lookup {
        /** Terminal status: applied to [snapshot] and announced. The watch is over. */
        TERMINAL,

        /** Applied to [snapshot]; the task has not finished. */
        RUNNING,

        /** The lookup itself failed. [snapshot] is left alone. */
        FAILED,

        /** This watch is no longer the current one; nothing was applied or announced. */
        SUPERSEDED,
    }

    private suspend fun watchUntilDone(taskId: String, generation: Long) {
        // withTimeoutOrNull swallows only its OWN timeout (returns null). If
        // the surrounding job is cancelled — superseded or stopWatching() —
        // the CancellationException still propagates and nothing below runs,
        // so a cancelled watch normally announces nothing; the generation
        // checks cover the cases where cancellation arrives too late for that
        // to be enough.
        val ranToEnd = withTimeoutOrNull(maxWatchMillis) {
            streamUntilDone(taskId, generation)
            true
        }
        if (ranToEnd == null) {
            // The cap expired mid-stream or mid-wait. One last authoritative
            // look (as before reconnecting existed): the terminal event may
            // have been lost on a flaky link, and a still-running task correctly
            // stays silent instead of falsely announcing completion.
            refreshAndMaybeNotify(taskId, generation)
        }
    }

    /**
     * One connection after another until the task is terminal, this watch is
     * superseded, the reconnect budget is spent, or the stream cannot safely be
     * resumed. Returns normally in all of those cases; the cap cancels it from
     * outside.
     */
    private suspend fun streamUntilDone(taskId: String, generation: Long) {
        var lastSeq: Long? = null // cursor: highest seq appended so far
        var appendedAny = false
        var reconnectsSinceProgress = 0

        while (true) {
            var progressed = false
            transport.taskEvents(taskId, afterSeq = lastSeq)
                .catch { /* handled uniformly below, same as normal stream completion */ }
                .collect { event ->
                    val seq = event.seq
                    val shown = lastSeq
                    // A replay overlap (a server that ignores the resume point, or
                    // one that re-sends the boundary event): already shown.
                    if (seq != null && shown != null && seq <= shown) return@collect
                    if (appendEventIfCurrent(generation, event)) {
                        progressed = true
                        appendedAny = true
                        if (seq != null) lastSeq = seq
                    }
                }

            // The stream ended — the server closed it after a terminal event
            // (PROTOCOL.md's documented behavior), .catch absorbed a failure, or
            // it was cut. Ask for the authoritative current status rather than
            // guessing which "phase" string in the events meant done: a dropped
            // connection on a still-running task must not falsely announce
            // completion. TaskMonitorTest asserts this directly.
            if (progressed) reconnectsSinceProgress = 0
            when (refreshAndMaybeNotify(taskId, generation)) {
                Lookup.TERMINAL, Lookup.SUPERSEDED -> return
                Lookup.RUNNING, Lookup.FAILED -> Unit
            }

            // Still running (or we could not find out). Reconnect if we may.
            if (reconnectsSinceProgress >= reconnectBackoffMillis.size) return // budget spent: end silently
            if (appendedAny && lastSeq == null) return // events without seq: replaying would show them twice
            delay(reconnectBackoffMillis[reconnectsSinceProgress])
            reconnectsSinceProgress++
            if (!isCurrent(generation)) return // superseded while waiting; don't open a stream for a dead watch
        }
    }

    /**
     * The event list is read-modify-write, so it must be atomic with respect
     * to watch(), which resets it: otherwise an event from a watch that was
     * superseded a moment ago could be appended to the NEW watch's list.
     * Returns whether the event was appended (false = this watch is stale).
     */
    private fun appendEventIfCurrent(generation: Long, event: TaskEvent): Boolean =
        synchronized(lock) {
            if (generation == watchGeneration) {
                _events.value = _events.value + event
                true
            } else {
                false
            }
        }

    private suspend fun refreshAndMaybeNotify(taskId: String, generation: Long): Lookup {
        val result = transport.getTask(taskId)
        if (result !is TransportResult.Success) {
            // Failure case deliberately left alone here: the UI still shows the
            // last-known snapshot/events either way, same as before this change.
            return if (isCurrent(generation)) Lookup.FAILED else Lookup.SUPERSEDED
        }
        val latest = result.value

        // Decide under the lock; call out after releasing it. A lookup result
        // that arrives after this watch was superseded or stopped is dropped
        // entirely — it must neither overwrite the newer watch's snapshot nor
        // announce.
        val outcome = synchronized(lock) {
            if (generation != watchGeneration) {
                Lookup.SUPERSEDED
            } else {
                _snapshot.value = latest
                // The terminal check lives here — not inside the notifier — so
                // it's directly testable with a fake that just records whether
                // it was called, per TaskMonitorTest. SamNotifications keeps its
                // own defensive check too (defense in depth for any other
                // caller), but this is the gate that actually matters for
                // TaskMonitor's contract: a dropped connection on a still-running
                // task must not falsely announce completion.
                if (latest.status in TERMINAL_STATUSES) Lookup.TERMINAL else Lookup.RUNNING
            }
        }
        if (outcome == Lookup.TERMINAL) {
            notifier.notifyFinished(latest)
        }
        return outcome
    }

    companion object {
        /** Provisional — see the class doc's BOUNDS section. */
        const val DEFAULT_MAX_WATCH_MILLIS = 30 * 60 * 1000L

        /**
         * Provisional and unmeasured: the wait before each consecutive reconnect
         * that follows a connection that delivered nothing new (1 s, 2 s, 4 s,
         * 8 s, 16 s — five reconnects, 31 s of waiting). Sized for a Wi-Fi roam
         * or a SAM Core restart (seconds to tens of seconds); a longer outage
         * ends the watch silently, as it did before reconnecting existed.
         */
        val DEFAULT_RECONNECT_BACKOFF_MILLIS: List<Long> = listOf(1_000L, 2_000L, 4_000L, 8_000L, 16_000L)

        private val TERMINAL_STATUSES = setOf(TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    }
}
