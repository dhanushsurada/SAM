package com.samcore.android.ui.memory

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class MemoryItem(val key: String, val value: String, val scope: String)

@Composable
fun MemoryScreen() {
    val sampleMemories = remember {
        listOf(
            MemoryItem("user_name", "Dhanush", "personal"),
            MemoryItem("theme_preference", "dark", "personal"),
            MemoryItem("active_desktop_host", "192.168.1.100", "device_local"),
            MemoryItem("task_sync_policy", "selective", "task")
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("SAM Memory & Context", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            "Scoped context separation ensures private data stays local while preferences sync cleanly across paired devices.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(16.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(sampleMemories) { mem ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(mem.key, style = MaterialTheme.typography.titleMedium)
                            SuggestionChip(
                                onClick = {},
                                label = { Text(mem.scope.uppercase()) }
                            )
                        }
                        Text(mem.value, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
        }
    }
}
