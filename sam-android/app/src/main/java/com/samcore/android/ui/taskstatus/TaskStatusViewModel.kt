package com.samcore.android.ui.taskstatus

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TaskEvent
import com.samcore.android.data.transport.TaskRequest
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TransportResult
import com.samcore.android.notifications.TaskMonitor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class TaskStatusUiState(
    val instruction: String = "",
    val isSending: Boolean = false,
    val snapshot: TaskSnapshot? = null,
    val events: List<TaskEvent> = emptyList(),
    val errorMessage: String? = null,
)

/**
 * Sending/cancelling a task still goes straight through SamTransport — only
 * *observing* a task in flight is delegated to TaskMonitor now, so the same
 * live status keeps updating (and can still notify on completion) even if
 * the user backs out of this screen before the task finishes.
 */
class TaskStatusViewModel(
    private val transport: SamTransport,
    private val taskMonitor: TaskMonitor,
) : ViewModel() {

    private val _instruction = MutableStateFlow("")
    private val _isSending = MutableStateFlow(false)
    private val _errorMessage = MutableStateFlow<String?>(null)

    val uiState: StateFlow<TaskStatusUiState> = combine(
        _instruction,
        _isSending,
        taskMonitor.snapshot,
        taskMonitor.events,
        _errorMessage,
    ) { instruction, isSending, snapshot, events, errorMessage ->
        TaskStatusUiState(instruction, isSending, snapshot, events, errorMessage)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TaskStatusUiState(),
    )

    fun onInstructionChange(value: String) {
        _instruction.value = value
        _errorMessage.value = null
    }

    fun sendTask() {
        val instruction = _instruction.value
        if (instruction.isBlank()) {
            _errorMessage.value = "Type something for SAM to do first."
            return
        }
        _isSending.value = true
        _errorMessage.value = null
        viewModelScope.launch {
            when (val result = transport.sendTask(TaskRequest(instruction = instruction))) {
                is TransportResult.Success -> {
                    _isSending.value = false
                    taskMonitor.watch(result.value)
                }
                is TransportResult.Failure -> {
                    _isSending.value = false
                    _errorMessage.value = result.message
                }
            }
        }
    }

    fun cancelTask() {
        val taskId = taskMonitor.snapshot.value?.taskId ?: return
        viewModelScope.launch { transport.cancelTask(taskId) }
    }
}
