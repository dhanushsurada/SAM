package com.samcore.android.ui.connection

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.ui.simpleViewModelFactory

@Composable
fun ConnectionStateScreen(
    transport: SamTransport,
    onOpenTaskStatus: () -> Unit,
    onUnpaired: () -> Unit,
    viewModel: ConnectionViewModel = viewModel(factory = simpleViewModelFactory { ConnectionViewModel(transport) }),
) {
    val connectionState by viewModel.connectionState.collectAsState()
    val isChecking by viewModel.isChecking.collectAsState()
    val lastCheckError by viewModel.lastCheckError.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        StatusRow(connectionState)
        Spacer(modifier = Modifier.height(8.dp))
        when (val state = connectionState) {
            is ConnectionState.Connected -> {
                Text(
                    text = state.device.deviceName,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                Text(
                    text = state.baseUrl,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            else -> Unit
        }
        if (lastCheckError != null) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = lastCheckError.orEmpty(),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Spacer(modifier = Modifier.height(32.dp))
        Button(
            onClick = { viewModel.checkConnection() },
            enabled = !isChecking,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (isChecking) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), color = MaterialTheme.colorScheme.onPrimary)
            } else {
                Text("Check connection")
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
        OutlinedButton(
            onClick = onOpenTaskStatus,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Send SAM a task")
        }
        Spacer(modifier = Modifier.height(24.dp))
        TextButton(
            onClick = { viewModel.unpair(onDone = onUnpaired) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Unpair this device", color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun StatusRow(state: ConnectionState) {
    val (label, color) = when (state) {
        is ConnectionState.Connected -> "Connected" to MaterialTheme.colorScheme.primary
        is ConnectionState.Connecting -> "Connecting…" to MaterialTheme.colorScheme.onSurfaceVariant
        is ConnectionState.Disconnected -> "Disconnected" to MaterialTheme.colorScheme.onSurfaceVariant
        is ConnectionState.Error -> "Connection error" to MaterialTheme.colorScheme.error
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            modifier = Modifier.size(10.dp),
            shape = CircleShape,
            color = color,
        ) {}
        Spacer(modifier = Modifier.width(8.dp))
        Text(text = label, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onBackground)
    }
}
