package com.samcore.android.ui.voice

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp

@Composable
fun VoiceScreen(
    onNavigateBack: () -> Unit = {}
) {
    var isListening by remember { mutableStateOf(false) }
    var transcription by remember { mutableStateOf("Press the mic button to speak with SAM...") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Text("Voice Assistant", style = MaterialTheme.typography.headlineMedium)

        // Waveform / Listening indicator
        Box(
            modifier = Modifier
                .size(160.dp)
                .clip(CircleShape)
                .background(
                    if (isListening) MaterialTheme.colorScheme.primaryContainer
                    else MaterialTheme.colorScheme.surfaceVariant
                ),
            contentAlignment = Alignment.Center
        ) {
            Text(
                if (isListening) "Listening..." else "Tap to Speak",
                style = MaterialTheme.typography.titleMedium,
                color = if (isListening) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        // Live transcription card
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = MaterialTheme.shapes.medium,
            modifier = Modifier.fillMaxWidth().heightIn(min = 100.dp)
        ) {
            Text(
                text = transcription,
                modifier = Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodyLarge
            )
        }

        // Push to talk control
        Button(
            onClick = {
                isListening = !isListening
                transcription = if (isListening) "Listening to user speech..." else "Processed voice input."
            },
            modifier = Modifier.fillMaxWidth().height(56.dp)
        ) {
            Text(if (isListening) "Stop Listening" else "Start Voice Interaction")
        }
    }
}
