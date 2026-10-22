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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.notifications.AndroidConnectTaskExecutor
import com.samcore.android.ui.simpleViewModelFactory
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.JsonPrimitive

@Composable
fun ConnectionStateScreen(
    transport: SamTransport,
    connectTaskExecutor: AndroidConnectTaskExecutor,
    onOpenTaskStatus: () -> Unit,
    onUnpaired: () -> Unit,
    viewModel: ConnectionViewModel = viewModel(factory = simpleViewModelFactory {
        ConnectionViewModel(transport, connectTaskExecutor)
    }),
) {
    val connectionState by viewModel.connectionState.collectAsState()
    val isChecking by viewModel.isChecking.collectAsState()
    val lastCheckError by viewModel.lastCheckError.collectAsState()
    val connectTasks by viewModel.connectTasks.collectAsState()
    val executingTaskId by viewModel.executingTaskId.collectAsState()

    LaunchedEffect(connectionState) {
        if (connectionState is ConnectionState.Connected) viewModel.checkConnection()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
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
        if (connectTasks.isNotEmpty()) {
            Spacer(modifier = Modifier.height(18.dp))
            Text("Tasks routed to this phone", style = MaterialTheme.typography.titleSmall)
            connectTasks.forEach { task ->
                Column(modifier = Modifier.padding(top = 8.dp)) {
                    Text(
                        text = "${task.action} · ${task.status}${task.lastMessage?.let { " · $it" } ?: ""}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    val taskTitle = (task.payload["title"] as? JsonPrimitive)?.contentOrNull
                    val taskMessage = (task.payload["message"] as? JsonPrimitive)?.contentOrNull
                    if (!taskTitle.isNullOrBlank() || !taskMessage.isNullOrBlank()) {
                        Text(
                            text = listOfNotNull(taskTitle?.takeIf { it.isNotBlank() }, taskMessage?.takeIf { it.isNotBlank() })
                                .joinToString(" — "),
                            modifier = Modifier.padding(top = 3.dp),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    if (task.status == "dispatched" || task.status == "queued_offline") {
                        if (task.action == AndroidConnectTaskExecutor.ACTION_SHOW_NOTIFICATION) {
                            OutlinedButton(
                                onClick = { viewModel.executeConnectTask(task) },
                                enabled = executingTaskId == null,
                                modifier = Modifier.padding(top = 4.dp),
                            ) {
                                Text(if (executingTaskId == task.taskId) "Running…" else "Show notification")
                            }
                        } else {
                            Text(
                                "This phone does not support this action.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
            Text(
                text = "Tasks run only after you choose an action. Notification content is private on the lock screen.",
                modifier = Modifier.padding(top = 6.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
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
        Text(
            text = "Unpairing removes this phone's saved connection. To revoke its SAM trust record, use the desktop device controls.",
            modifier = Modifier.padding(top = 8.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
        )
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
