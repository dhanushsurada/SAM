package com.samcore.android.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.samcore.android.ai.SamMobileInferenceEngine
import com.samcore.android.data.transport.SamTransport
import kotlinx.coroutines.launch

data class ChatMessage(
    val id: String,
    val sender: String, // "user" | "sam"
    val text: String,
    val executingDevice: String = "desktop", // "desktop" | "phone"
    val timestamp: Long = System.currentTimeMillis()
)

@Composable
fun ChatScreen(
    transport: SamTransport,
    mobileInference: SamMobileInferenceEngine,
    onNavigateToVoice: () -> Unit = {}
) {
    var messages by remember {
        mutableStateOf(
            listOf(
                ChatMessage("1", "sam", "Hello! I am SAM. Ask me to control your desktop, interact with phone apps, or analyze documents.", "desktop")
            )
        )
    }
    var inputText by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // Active Device Status Bar
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("Unified SAM Assistant", style = MaterialTheme.typography.titleMedium)
                    Text("Auto-routing: Desktop + Android", style = MaterialTheme.typography.bodySmall)
                }
                SuggestionChip(
                    onClick = {},
                    label = { Text("Active") },
                    colors = SuggestionChipDefaults.suggestionChipColors(
                        labelColor = MaterialTheme.colorScheme.primary
                    )
                )
            }
        }

        // Chat message history
        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(messages) { msg ->
                val isUser = msg.sender == "user"
                Box(
                    modifier = Modifier.fillMaxWidth(),
                    contentAlignment = if (isUser) Alignment.CenterEnd else Alignment.CenterStart
                ) {
                    Surface(
                        color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.secondaryContainer,
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.widthIn(max = 300.dp)
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            if (!isUser) {
                                Text(
                                    text = "Executed on ${msg.executingDevice.uppercase()}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.primary
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                            }
                            Text(
                                text = msg.text,
                                color = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSecondaryContainer,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                }
            }
        }

        // Input row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                placeholder = { Text("Ask SAM anything...") },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(24.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Button(
                onClick = {
                    if (inputText.isNotBlank()) {
                        val userPrompt = inputText
                        messages = messages + ChatMessage(System.currentTimeMillis().toString(), "user", userPrompt)
                        inputText = ""

                        scope.launch {
                            val (reply, _) = mobileInference.infer(userPrompt)
                            messages = messages + ChatMessage(
                                (System.currentTimeMillis() + 1).toString(),
                                "sam",
                                reply,
                                "phone"
                            )
                        }
                    }
                },
                shape = RoundedCornerShape(24.dp)
            ) {
                Text("Send")
            }
        }
    }
}
