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
 * true for exactly as long as a watch is live and goes false however the watch
 * ends (terminal task, stream failure, cap expiry, cancellation), at which
 * point the service stops itself. See TaskKeepAlive for why there is no
 * stop() call from here.
 *
 * WHAT THIS DOES NOT DO — stated plainly, per PDR §18:
 *  - It does not survive the process being killed. A foreground service lowers
 *    the odds; nothing is persisted, and a killed process loses the watch with
 *    no recovery on relaunch.
 *  - It does not reconnect. If the stream ends while the task is still running
 *    (network blip, server restart, read timeout), the watch makes one
 *    authoritative status lookup, notifies only if that shows a terminal
 *    status, and then ends — the user is not told the task finished later. The
 *    server supports replay-from-seq via Last-Event-ID (interfaces/api/
 *    server.py), so a bounded reconnect loop is the natural next step; it is
 *    deliberately not part of this change.
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
 * watch() (usually the main thread).
 *
 * BOUNDS. A watch can never outlive [maxWatchMillis]. That is the backstop
 * for a stream that stays open but never delivers a terminal event; the
 * transport's own SSE read timeout is the (faster) detector for a dead
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
) {
    init {
        require(maxWatchMillis > 0) { "maxWatchMillis must be positive" }
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

    private suspend fun watchUntilDone(taskId: String, generation: Long) {
        // withTimeoutOrNull swallows only its OWN timeout (returns null). If
        // the surrounding job is cancelled — superseded or stopWatching() —
        // the CancellationException still propagates and the lookup below is
        // skipped, so a cancelled watch normally announces nothing; the
        // generation checks below cover the cases where cancellation arrives
        // too late for that to be enough.
        withTimeoutOrNull(maxWatchMillis) {
            transport.taskEvents(taskId)
                .catch { /* handled uniformly below, same as normal stream completion */ }
                .collect { event -> appendEventIfCurrent(generation, event) }
        }

        // Reached once the stream ends — the server closed it after a terminal
        // event (PROTOCOL.md's documented behavior), .catch above absorbed a
        // failure, or the cap expired. Either way, ask for the authoritative
        // current status rather than guessing which "phase" string in the
        // events meant done — a dropped connection or a cap expiry on a
        // still-running task correctly stays silent instead of falsely
        // announcing completion. TaskMonitorTest asserts this directly.
        refreshAndMaybeNotify(taskId, generation)
    }

    /**
     * The event list is read-modify-write, so it must be atomic with respect
     * to watch(), which resets it: otherwise an event from a watch that was
     * superseded a moment ago could be appended to the NEW watch's list.
     */
    private fun appendEventIfCurrent(generation: Long, event: TaskEvent) {
        synchronized(lock) {
            if (generation == watchGeneration) {
                _events.value = _events.value + event
            }
        }
    }

    private suspend fun refreshAndMaybeNotify(taskId: String, generation: Long) {
        val result = transport.getTask(taskId)
        if (result !is TransportResult.Success) {
            // Failure case deliberately left alone here: the UI still shows the
            // last-known snapshot/events either way, same as before this change.
            return
        }
        val latest = result.value

        // Decide under the lock; call out after releasing it. A lookup result
        // that arrives after this watch was superseded or stopped is dropped
        // entirely — it must neither overwrite the newer watch's snapshot nor
        // announce.
        val announce = synchronized(lock) {
            if (generation != watchGeneration) {
                false
            } else {
                _snapshot.value = latest
                // The terminal check lives here — not inside the notifier — so
                // it's directly testable with a fake that just records whether
                // it was called, per TaskMonitorTest. SamNotifications keeps its
                // own defensive check too (defense in depth for any other
                // caller), but this is the gate that actually matters for
                // TaskMonitor's contract: a dropped connection on a still-running
                // task must not falsely announce completion.
                latest.status in TERMINAL_STATUSES
            }
        }
        if (announce) {
            notifier.notifyFinished(latest)
        }
    }

    companion object {
        /** Provisional — see the class doc's BOUNDS section. */
        const val DEFAULT_MAX_WATCH_MILLIS = 30 * 60 * 1000L

        private val TERMINAL_STATUSES = setOf(TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    }
}
