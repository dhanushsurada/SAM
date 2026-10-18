package com.samcore.android.ui.pairing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TransportResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class PairingUiState(
    val baseUrl: String = "",
    val pairingCode: String = "",
    val isPairing: Boolean = false,
    val errorMessage: String? = null,
)

class PairingViewModel(private val transport: SamTransport) : ViewModel() {

    private val _uiState = MutableStateFlow(PairingUiState())
    val uiState: StateFlow<PairingUiState> = _uiState

    fun onBaseUrlChange(value: String) {
        _uiState.value = _uiState.value.copy(baseUrl = value, errorMessage = null)
    }

    fun onPairingCodeChange(value: String) {
        _uiState.value = _uiState.value.copy(pairingCode = value, errorMessage = null)
    }

    fun pair(onSuccess: () -> Unit) {
        val state = _uiState.value
        if (state.baseUrl.isBlank() || state.pairingCode.isBlank()) {
            _uiState.value = state.copy(errorMessage = "Enter both the SAM Core address and the pairing code.")
            return
        }
        _uiState.value = state.copy(isPairing = true, errorMessage = null)
        viewModelScope.launch {
            when (val result = transport.pair(state.baseUrl, state.pairingCode)) {
                is TransportResult.Success -> {
                    _uiState.value = _uiState.value.copy(isPairing = false)
                    onSuccess()
                }
                is TransportResult.Failure -> {
                    _uiState.value = _uiState.value.copy(isPairing = false, errorMessage = result.message)
                }
            }
        }
    }
}
