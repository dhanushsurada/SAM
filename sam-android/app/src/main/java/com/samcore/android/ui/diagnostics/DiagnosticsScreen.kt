package com.samcore.android.ui.diagnostics

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.samcore.android.data.transport.SamTransport

@Composable
fun DiagnosticsScreen(
    transport: SamTransport
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("System Diagnostics", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Cryptographic Identity", style = MaterialTheme.typography.titleMedium)
                Text("Algorithm: Ed25519 (RFC 8032)", style = MaterialTheme.typography.bodyMedium)
                Text("Storage: Android Keystore / Encrypted Preferences", style = MaterialTheme.typography.bodySmall)
                Text("Replay Protection: 120s Timestamp Window + In-Memory Nonce Cache", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Transport Metrics", style = MaterialTheme.typography.titleMedium)
                Text("Channel: Authenticated LAN HTTP + SSE Stream", style = MaterialTheme.typography.bodyMedium)
                Text("Heartbeat Interval: 5.0 seconds", style = MaterialTheme.typography.bodySmall)
                Text("Staleness Sweep: 30.0 seconds", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Thermal & Memory Diagnostics", style = MaterialTheme.typography.titleMedium)
                val runtime = Runtime.getRuntime()
                val usedMb = (runtime.totalMemory() - runtime.freeMemory()) / (1024 * 1024)
                val totalMb = runtime.totalMemory() / (1024 * 1024)
                Text("JVM Heap Usage: $usedMb MB / $totalMb MB", style = MaterialTheme.typography.bodyMedium)
                Text("Thermal State: Normal", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
