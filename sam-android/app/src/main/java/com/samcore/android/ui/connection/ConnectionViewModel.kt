package com.samcore.android.ui.connection

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TransportResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ConnectionViewModel(private val transport: SamTransport) : ViewModel() {

    // SamTransport.connectionState is a plain Flow by contract (any future
    // implementation can back it however it wants) — stateIn() is the
    // correct way to get a Compose-friendly StateFlow out of that without
    // assuming anything about how the implementation produces it.
    val connectionState: StateFlow<ConnectionState> = transport.connectionState.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = ConnectionState.Connecting,
    )

    private val _isChecking = MutableStateFlow(false)
    val isChecking: StateFlow<Boolean> = _isChecking

    private val _lastCheckError = MutableStateFlow<String?>(null)
    val lastCheckError: StateFlow<String?> = _lastCheckError

    fun checkConnection() {
        _isChecking.value = true
        _lastCheckError.value = null
        viewModelScope.launch {
            when (val result = transport.checkConnection()) {
                is TransportResult.Success -> _lastCheckError.value = null
                is TransportResult.Failure -> _lastCheckError.value = result.message
            }
            _isChecking.value = false
        }
    }

    fun unpair(onDone: () -> Unit) {
        viewModelScope.launch {
            transport.unpair()
            onDone()
        }
    }
}
