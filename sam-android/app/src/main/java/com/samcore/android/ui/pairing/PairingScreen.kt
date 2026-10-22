package com.samcore.android.ui.pairing

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.ui.simpleViewModelFactory

@Composable
fun PairingScreen(
    transport: SamTransport,
    onPaired: () -> Unit,
    viewModel: PairingViewModel = viewModel(factory = simpleViewModelFactory { PairingViewModel(transport) }),
) {
    val uiState by viewModel.uiState.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "Pair with SAM Core",
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Both devices need to be on the same trusted Wi-Fi network. Enter the desktop address and one-time pairing token from SAM Connect.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(24.dp))
        OutlinedTextField(
            value = uiState.baseUrl,
            onValueChange = viewModel::onBaseUrlChange,
            label = { Text("SAM Core address (e.g. http://192.168.1.42:8420)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(modifier = Modifier.height(12.dp))
        OutlinedTextField(
            value = uiState.pairingCode,
            onValueChange = viewModel::onPairingCodeChange,
            label = { Text("One-time pairing token") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        if (uiState.errorMessage != null) {
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = uiState.errorMessage.orEmpty(),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Connect signs device requests for authentication, but local HTTP does not encrypt task content. Pair only on a network you trust; never expose this endpoint to the public internet.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
        )
        Spacer(modifier = Modifier.height(24.dp))
        Button(
            onClick = { viewModel.pair(onSuccess = onPaired) },
            enabled = !uiState.isPairing,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (uiState.isPairing) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), color = MaterialTheme.colorScheme.onPrimary)
            } else {
                Text("Pair")
            }
        }
    }
}
