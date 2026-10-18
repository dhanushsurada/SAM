package com.samcore.android.fakes

import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.DeviceInfo
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TaskEvent
import com.samcore.android.data.transport.TaskRequest
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TransportResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext

/**
 * Controllable SamTransport for tests. Every method is scriptable via a
 * public var/queue set up before the call under test — nothing here talks to
 * a network or an Android framework class.
 */
class FakeSamTransport : SamTransport {

    var restoreCalled = false
    var pairResult: TransportResult<DeviceInfo> = TransportResult.Failure("not configured")
    var checkConnectionResult: TransportResult<Unit> = TransportResult.Success(Unit)
    var sendTaskResult: TransportResult<TaskSnapshot> = TransportResult.Failure("not configured")
    val getTaskResults = ArrayDeque<TransportResult<TaskSnapshot>>() // consumed in order, one per getTask() call
    var cancelTaskResult: TransportResult<Unit> = TransportResult.Success(Unit)
    var unpairCalled = false

    /** Events emitted by taskEvents(), then the flow completes normally — set
     *  taskEventsError instead to have it throw partway (or immediately), or
     *  taskEventsNeverCompletesForId to a specific task id to simulate a
     *  still-open stream for just that task (for testing that watching a new
     *  task actually cancels an old, still-running watch — other task ids
     *  are unaffected and complete normally). */
    var taskEventsToEmit: List<TaskEvent> = emptyList()
    var taskEventsError: Throwable? = null
    var taskEventsNeverCompletesForId: String? = null

    /** Same as [taskEventsNeverCompletesForId] but for any number of task ids at once
     *  (needed to test a second watch superseding a first while BOTH streams stay open). */
    val taskEventsNeverCompleteForIds = mutableSetOf<String>()

    /** When set, replaces taskEvents() entirely — lets a test hand TaskMonitor a
     *  stream it controls (e.g. a SharedFlow it can emit into at an exact moment). */
    var taskEventsOverride: ((taskId: String) -> Flow<TaskEvent>)? = null

    /** When set, getTask() stops here until the gate is completed — and waits
     *  NON-cancellably, so the answer still comes back even if the watch that
     *  asked was cancelled meanwhile. That models the narrow real-world window
     *  in which a lookup has already returned by the time its coroutine would
     *  have noticed the cancellation. [getTaskReachedGate] completes as soon as
     *  a call is waiting, so a test can tell "the lookup is in flight" from
     *  "it never got there". */
    var getTaskGate: CompletableDeferred<Unit>? = null
    val getTaskReachedGate = CompletableDeferred<Unit>()

    var lastRequestedTaskEventsId: String? = null
    var lastGetTaskId: String? = null

    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Connecting)
    override val connectionState: Flow<ConnectionState> = _connectionState

    fun setConnectionState(state: ConnectionState) {
        _connectionState.value = state
    }

    override suspend fun restore() {
        restoreCalled = true
    }

    override suspend fun pair(baseUrl: String, pairingCode: String): TransportResult<DeviceInfo> = pairResult

    override suspend fun checkConnection(): TransportResult<Unit> = checkConnectionResult

    override suspend fun sendTask(request: TaskRequest): TransportResult<TaskSnapshot> = sendTaskResult

    override suspend fun getTask(taskId: String): TransportResult<TaskSnapshot> {
        lastGetTaskId = taskId
        getTaskGate?.let { gate ->
            getTaskReachedGate.complete(Unit)
            withContext(NonCancellable) { gate.await() }
        }
        return if (getTaskResults.isNotEmpty()) getTaskResults.removeFirst() else TransportResult.Failure("no more results queued")
    }

    override fun taskEvents(taskId: String): Flow<TaskEvent> {
        lastRequestedTaskEventsId = taskId
        taskEventsOverride?.let { return it(taskId) }
        return flow {
            for (event in taskEventsToEmit) {
                emit(event)
            }
            taskEventsError?.let { throw it }
            if (taskId == taskEventsNeverCompletesForId || taskId in taskEventsNeverCompleteForIds) {
                awaitCancellation()
            }
        }
    }

    override suspend fun cancelTask(taskId: String): TransportResult<Unit> = cancelTaskResult

    override suspend fun unpair() {
        unpairCalled = true
        _connectionState.value = ConnectionState.Disconnected
    }
}
