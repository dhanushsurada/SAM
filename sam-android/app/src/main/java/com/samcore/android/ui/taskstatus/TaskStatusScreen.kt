package com.samcore.android.ui.taskstatus

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.notifications.TaskMonitor
import com.samcore.android.ui.simpleViewModelFactory

@Composable
fun TaskStatusScreen(
    transport: SamTransport,
    taskMonitor: TaskMonitor,
    onBack: () -> Unit,
    viewModel: TaskStatusViewModel = viewModel(
        factory = simpleViewModelFactory { TaskStatusViewModel(transport, taskMonitor) },
    ),
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    // Requested here — the point notifications actually become relevant —
    // not at app launch. Denying it doesn't block sending the task; it just
    // means no completion notification later. See SamNotifications' doc
    // comment for why every notify() call re-checks this anyway.
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
        onResult = {}, // nothing to do either way — sendTask() already proceeded
    )
    val requestNotificationPermissionIfNeeded = remember(context) {
        {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                    PackageManager.PERMISSION_GRANTED
                if (!granted) {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Row {
            TextButton(onClick = onBack) { Text("Back") }
        }
        Text(
            text = "Send SAM a task",
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Spacer(modifier = Modifier.height(16.dp))
        OutlinedTextField(
            value = uiState.instruction,
            onValueChange = viewModel::onInstructionChange,
            label = { Text("What should SAM do?") },
            modifier = Modifier.fillMaxWidth(),
        )
        if (uiState.errorMessage != null) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(uiState.errorMessage.orEmpty(), color = MaterialTheme.colorScheme.error)
        }
        Spacer(modifier = Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = {
                    requestNotificationPermissionIfNeeded()
                    viewModel.sendTask()
                },
                enabled = !uiState.isSending,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (uiState.isSending) "Sending…" else "Send")
            }
            if (uiState.snapshot != null) {
                Spacer(modifier = Modifier.width(8.dp))
                TextButton(onClick = { viewModel.cancelTask() }) {
                    Text("Cancel task", color = MaterialTheme.colorScheme.error)
                }
            }
        }

        uiState.snapshot?.let { snapshot ->
            Spacer(modifier = Modifier.height(20.dp))
            Text(
                text = "Status: ${snapshot.status.name.lowercase()}",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            snapshot.resultText?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onBackground)
            }
            snapshot.error?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
            }
        }

        if (uiState.events.isNotEmpty()) {
            Spacer(modifier = Modifier.height(20.dp))
            HorizontalDivider()
            Spacer(modifier = Modifier.height(12.dp))
            Text("Live events", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onBackground)
            Spacer(modifier = Modifier.height(8.dp))
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(uiState.events) { event ->
                    Text(
                        text = "[${event.phase}] ${event.message}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 4.dp),
                    )
                }
            }
        }
    }
}
