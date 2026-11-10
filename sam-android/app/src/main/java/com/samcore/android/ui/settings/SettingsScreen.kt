package com.samcore.android.ui.settings

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun SettingsScreen() {
    var deviceName by remember { mutableStateOf("Android Device") }
    var autoSyncEnabled by remember { mutableStateOf(true) }
    var highRiskApproval by remember { mutableStateOf(true) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("SAM Android Settings", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))

        OutlinedTextField(
            value = deviceName,
            onValueChange = { deviceName = it },
            label = { Text("Device Display Name") },
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Selective Context Sync", style = MaterialTheme.typography.titleMedium)
                Text("Sync user preferences without syncing sensitive keys or files", style = MaterialTheme.typography.bodySmall)
            }
            Switch(checked = autoSyncEnabled, onCheckedChange = { autoSyncEnabled = it })
        }

        Spacer(modifier = Modifier.height(16.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("High-Risk Approval Gating", style = MaterialTheme.typography.titleMedium)
                Text("Prompt before executing deletions or privileged actions", style = MaterialTheme.typography.bodySmall)
            }
            Switch(checked = highRiskApproval, onCheckedChange = { highRiskApproval = it })
        }
    }
}
