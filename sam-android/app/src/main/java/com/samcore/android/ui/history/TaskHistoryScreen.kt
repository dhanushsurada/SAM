package com.samcore.android.ui.history

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class HistoryItem(
    val taskId: String,
    val goal: String,
    val origin: String,
    val status: String,
    val timeFormatted: String
)

@Composable
fun TaskHistoryScreen() {
    val sampleHistory = remember {
        listOf(
            HistoryItem("task_01", "Transfer PDF document from Desktop", "desktop", "completed", "10 mins ago"),
            HistoryItem("task_02", "Check phone notifications and build briefing", "phone", "completed", "1 hour ago"),
            HistoryItem("task_03", "Launch Google Chrome on Desktop", "phone", "completed", "2 hours ago")
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Task History", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            "Audit trail of executed local and cross-device tasks.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(16.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(sampleHistory) { item ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(item.taskId, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                            Text(item.timeFormatted, style = MaterialTheme.typography.labelSmall)
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(item.goal, style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Origin: ${item.origin.uppercase()} | Status: ${item.status.uppercase()}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}
