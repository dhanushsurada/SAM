package com.samcore.android.ui.modelmanager

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.samcore.android.ai.MobileModelInfo
import com.samcore.android.ai.SamMobileInferenceEngine
import kotlinx.coroutines.launch

@Composable
fun ModelManagerScreen(
    inferenceEngine: SamMobileInferenceEngine
) {
    val tier = remember { inferenceEngine.hardwareTier }
    var installedModels by remember { mutableStateOf(inferenceEngine.listInstalledModels()) }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Mobile Model Manager", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))

        // Hardware profile card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Device Hardware Profile: ${tier.name} TIER", style = MaterialTheme.typography.titleMedium)
                Text("Recommended model: ${tier.recommendedModelSize}", style = MaterialTheme.typography.bodyMedium)
                Text("Inference backend: LiteRT / GGUF Mobile", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Text("Installed Local Models (${installedModels.size})", style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.height(8.dp))

        if (installedModels.isEmpty()) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    "No local models installed yet.\nImport or download a GGUF / LiteRT model for offline AI.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(installedModels) { model ->
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(model.displayName, style = MaterialTheme.typography.titleMedium)
                                Text("${model.format} | ${model.quantization} | ${model.sizeBytes / (1024 * 1024)} MB", style = MaterialTheme.typography.bodySmall)
                            }
                            Button(
                                onClick = {
                                    scope.launch {
                                        if (model.isLoaded) inferenceEngine.unloadModel()
                                        else inferenceEngine.loadModel(model.modelId)
                                        installedModels = inferenceEngine.listInstalledModels()
                                    }
                                }
                            ) {
                                Text(if (model.isLoaded) "Unload" else "Load")
                            }
                        }
                    }
                }
            }
        }

        Button(
            onClick = {
                // Refresh list
                installedModels = inferenceEngine.listInstalledModels()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Refresh Installed Models")
        }
    }
}
