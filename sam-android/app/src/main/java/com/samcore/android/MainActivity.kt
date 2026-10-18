package com.samcore.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.samcore.android.ui.navigation.SamNavGraph
import com.samcore.android.ui.theme.SamTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val transport = (application as SamApplication).container.samTransport
        val taskMonitor = (application as SamApplication).container.taskMonitor

        setContent {
            SamTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    SamNavGraph(transport = transport, taskMonitor = taskMonitor)
                }
            }
        }
    }
}
