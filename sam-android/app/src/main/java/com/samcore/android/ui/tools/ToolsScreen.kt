package com.samcore.android.ui.tools

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.samcore.android.automation.SamAccessibilityService
import com.samcore.android.automation.SamNotificationListener

data class ToolCapabilityState(
    val name: String,
    val description: String,
    val isEnabled: Boolean,
    val category: String
)

@Composable
fun ToolsScreen() {
    val tools = remember {
        listOf(
            ToolCapabilityState("App Launcher", "Direct application launching and deep linking", true, "Intent Automation"),
            ToolCapabilityState("UI Accessibility", "Touch, click, type and gesture navigation", SamAccessibilityService.isServiceEnabled, "Accessibility"),
            ToolCapabilityState("Notification Reader", "Permitted notification inspection & summary", SamNotificationListener.isListeningEnabled, "Notification Access"),
            ToolCapabilityState("Scoped Storage", "Secure file reception and SHA-256 verification", true, "File System"),
            ToolCapabilityState("Mobile Inference", "On-device LiteRT and GGUF neural reasoning", true, "Intelligence")
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Skills & Capabilities", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            "Registered on-device capabilities reported to SAM Unified Task Coordinator.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(16.dp))

        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(tools) { tool ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(tool.name, style = MaterialTheme.typography.titleMedium)
                            Text(tool.description, style = MaterialTheme.typography.bodySmall)
                            Text(tool.category, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                        }
                        Badge(
                            containerColor = if (tool.isEnabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        ) {
                            Text(if (tool.isEnabled) "ACTIVE" else "DISABLED", modifier = Modifier.padding(4.dp))
                        }
                    }
                }
            }
        }
    }
}
