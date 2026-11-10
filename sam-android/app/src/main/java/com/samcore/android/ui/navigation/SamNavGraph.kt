package com.samcore.android.ui.navigation

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.samcore.android.ai.SamMobileInferenceEngine
import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.notifications.AndroidConnectTaskExecutor
import com.samcore.android.notifications.TaskMonitor
import com.samcore.android.ui.automation.AutomationScreen
import com.samcore.android.ui.chat.ChatScreen
import com.samcore.android.ui.connection.ConnectionStateScreen
import com.samcore.android.ui.diagnostics.DiagnosticsScreen
import com.samcore.android.ui.history.TaskHistoryScreen
import com.samcore.android.ui.memory.MemoryScreen
import com.samcore.android.ui.modelmanager.ModelManagerScreen
import com.samcore.android.ui.onboarding.OnboardingScreen
import com.samcore.android.ui.pairing.PairingScreen
import com.samcore.android.ui.permissions.PermissionsScreen
import com.samcore.android.ui.settings.SettingsScreen
import com.samcore.android.ui.taskstatus.TaskStatusScreen
import com.samcore.android.ui.tools.ToolsScreen
import com.samcore.android.ui.voice.VoiceScreen

object Routes {
    const val LOADING = "loading"
    const val ONBOARDING = "onboarding"
    const val PAIRING = "pairing"
    const val CHAT = "chat"
    const val VOICE = "voice"
    const val CONNECTION = "connection"
    const val MODEL_MANAGER = "model_manager"
    const val MEMORY = "memory"
    const val TOOLS = "tools"
    const val TASK_HISTORY = "task_history"
    const val AUTOMATION = "automation"
    const val PERMISSIONS = "permissions"
    const val DIAGNOSTICS = "diagnostics"
    const val SETTINGS = "settings"
    const val TASK_STATUS = "task_status"
}

data class BottomNavItem(
    val route: String,
    val label: String
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SamNavGraph(
    transport: SamTransport,
    taskMonitor: TaskMonitor,
    connectTaskExecutor: AndroidConnectTaskExecutor,
    mobileInference: SamMobileInferenceEngine = SamMobileInferenceEngine(androidx.compose.ui.platform.LocalContext.current)
) {
    val navController = rememberNavController()
    val connectionState by transport.connectionState.collectAsState(initial = ConnectionState.Connecting)
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    LaunchedEffect(Unit) {
        transport.restore()
    }

    LaunchedEffect(connectionState) {
        if (navController.currentDestination?.route != Routes.LOADING) return@LaunchedEffect
        when (connectionState) {
            is ConnectionState.Connected -> navigateAndClear(navController, Routes.CHAT)
            is ConnectionState.Disconnected, is ConnectionState.Error -> navigateAndClear(navController, Routes.ONBOARDING)
            is ConnectionState.Connecting -> Unit
        }
    }

    val bottomNavItems = listOf(
        BottomNavItem(Routes.CHAT, "Chat"),
        BottomNavItem(Routes.VOICE, "Voice"),
        BottomNavItem(Routes.MODEL_MANAGER, "Models"),
        BottomNavItem(Routes.TOOLS, "Tools"),
        BottomNavItem(Routes.CONNECTION, "Bridge"),
        BottomNavItem(Routes.SETTINGS, "Settings")
    )

    val showBottomBar = currentRoute in bottomNavItems.map { it.route }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    bottomNavItems.forEach { item ->
                        NavigationBarItem(
                            selected = currentRoute == item.route,
                            onClick = {
                                if (currentRoute != item.route) {
                                    navController.navigate(item.route) {
                                        popUpTo(navController.graph.findStartDestination().id) {
                                            saveState = true
                                        }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            icon = {},
                            label = { Text(item.label) }
                        )
                    }
                }
            }
        }
    ) { paddingValues ->
        Box(modifier = Modifier.padding(paddingValues)) {
            NavHost(navController = navController, startDestination = Routes.LOADING) {
                composable(Routes.LOADING) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                    }
                }
                composable(Routes.ONBOARDING) {
                    OnboardingScreen(onGetStarted = { navController.navigate(Routes.PAIRING) })
                }
                composable(Routes.PAIRING) {
                    PairingScreen(
                        transport = transport,
                        onPaired = { navigateAndClear(navController, Routes.CHAT) },
                    )
                }
                composable(Routes.CHAT) {
                    ChatScreen(
                        transport = transport,
                        mobileInference = mobileInference,
                        onNavigateToVoice = { navController.navigate(Routes.VOICE) }
                    )
                }
                composable(Routes.VOICE) {
                    VoiceScreen(onNavigateBack = { navController.popBackStack() })
                }
                composable(Routes.MODEL_MANAGER) {
                    ModelManagerScreen(inferenceEngine = mobileInference)
                }
                composable(Routes.TOOLS) {
                    ToolsScreen()
                }
                composable(Routes.MEMORY) {
                    MemoryScreen()
                }
                composable(Routes.TASK_HISTORY) {
                    TaskHistoryScreen()
                }
                composable(Routes.AUTOMATION) {
                    AutomationScreen()
                }
                composable(Routes.PERMISSIONS) {
                    PermissionsScreen()
                }
                composable(Routes.DIAGNOSTICS) {
                    DiagnosticsScreen(transport = transport)
                }
                composable(Routes.SETTINGS) {
                    SettingsScreen()
                }
                composable(Routes.CONNECTION) {
                    ConnectionStateScreen(
                        transport = transport,
                        connectTaskExecutor = connectTaskExecutor,
                        onOpenTaskStatus = { navController.navigate(Routes.TASK_STATUS) },
                        onUnpaired = { navigateAndClear(navController, Routes.ONBOARDING) },
                    )
                }
                composable(Routes.TASK_STATUS) {
                    TaskStatusScreen(
                        transport = transport,
                        taskMonitor = taskMonitor,
                        onBack = { navController.popBackStack() },
                    )
                }
            }
        }
    }
}

private fun navigateAndClear(navController: NavHostController, route: String) {
    navController.navigate(route) {
        popUpTo(navController.graph.findStartDestination().id) {
            inclusive = true
        }
    }
}
