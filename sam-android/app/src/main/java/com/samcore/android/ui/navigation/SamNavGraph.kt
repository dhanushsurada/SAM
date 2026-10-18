package com.samcore.android.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.samcore.android.data.transport.ConnectionState
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.notifications.TaskMonitor
import com.samcore.android.ui.connection.ConnectionStateScreen
import com.samcore.android.ui.onboarding.OnboardingScreen
import com.samcore.android.ui.pairing.PairingScreen
import com.samcore.android.ui.taskstatus.TaskStatusScreen

private object Routes {
    const val LOADING = "loading"
    const val ONBOARDING = "onboarding"
    const val PAIRING = "pairing"
    const val CONNECTION = "connection"
    const val TASK_STATUS = "task_status"
}

/**
 * First-slice navigation: loading -> {onboarding|connection} -> pairing ->
 * connection -> task_status. See recon report §5 — notifications, background
 * service and voice entry are deliberately not part of this graph yet.
 */
@Composable
fun SamNavGraph(transport: SamTransport, taskMonitor: TaskMonitor) {
    val navController = rememberNavController()
    val connectionState by transport.connectionState.collectAsState(initial = ConnectionState.Connecting)

    LaunchedEffect(Unit) {
        transport.restore()
    }

    // Resolves the *initial* route once restore() lands on a real answer.
    // Guarded to the loading screen only, so it never fights with in-app
    // navigation that happens later (e.g. PairingScreen's own onPaired call).
    LaunchedEffect(connectionState) {
        if (navController.currentDestination?.route != Routes.LOADING) return@LaunchedEffect
        when (connectionState) {
            is ConnectionState.Connected -> navigateAndClear(navController, Routes.CONNECTION)
            is ConnectionState.Disconnected, is ConnectionState.Error -> navigateAndClear(navController, Routes.ONBOARDING)
            is ConnectionState.Connecting -> Unit // still resolving
        }
    }

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
                onPaired = { navigateAndClear(navController, Routes.CONNECTION) },
            )
        }
        composable(Routes.CONNECTION) {
            ConnectionStateScreen(
                transport = transport,
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

private fun navigateAndClear(navController: NavHostController, route: String) {
    navController.navigate(route) {
        // Verified pattern (Android's own Navigation Compose docs, "pop up
        // to start destination" idiom) — popUpTo(0) is NOT valid here: these
        // are string routes, not the old Int-destination-ID system, and 0
        // wouldn't correspond to any real destination in this graph.
        popUpTo(navController.graph.findStartDestination().id) {
            inclusive = true
        }
    }
}
