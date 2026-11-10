package com.samcore.android.ui.permissions

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class PermissionItem(
    val title: String,
    val purpose: String,
    val policyRequirement: String,
    val status: String
)

@Composable
fun PermissionsScreen() {
    val items = remember {
        listOf(
            PermissionItem(
                "Notifications",
                "Delivers task progress and alerts to status bar.",
                "POST_NOTIFICATIONS (Android 13+)",
                "Granted"
            ),
            PermissionItem(
                "Accessibility Service",
                "Assists user with navigating buttons, typing, and actions on request.",
                "Explicit user toggle in Accessibility settings",
                "Optional"
            ),
            PermissionItem(
                "Notification Listener",
                "Reads incoming notifications to generate daily briefings on command.",
                "Notification Access setting (Google Play compliant)",
                "Optional"
            ),
            PermissionItem(
                "Foreground Service",
                "Maintains reliable task handoff connection over local Wi-Fi.",
                "FOREGROUND_SERVICE_DATA_SYNC (Android 14+)",
                "Active"
            ),
            PermissionItem(
                "Scoped Storage",
                "Saves and transfers requested documents in app private storage.",
                "No broad storage access requested (Compliant)",
                "Active"
            )
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Permissions & Privacy", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            "SAM follows least-privilege principles. No sensitive data is silently collected.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(16.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(items) { item ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(item.title, style = MaterialTheme.typography.titleMedium)
                            SuggestionChip(
                                onClick = {},
                                label = { Text(item.status) }
                            )
                        }
                        Text(item.purpose, style = MaterialTheme.typography.bodyMedium)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(item.policyRequirement, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
}
