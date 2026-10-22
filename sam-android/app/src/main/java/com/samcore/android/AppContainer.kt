package com.samcore.android

import android.content.Context
import com.samcore.android.data.local.DevicePrefsStore
import com.samcore.android.data.local.AndroidCapabilityReporter
import com.samcore.android.data.local.AndroidEncryptedIdentityStore
import com.samcore.android.data.transport.HttpSseSamTransport
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.notifications.AndroidTaskKeepAlive
import com.samcore.android.notifications.AndroidTaskNotifier
import com.samcore.android.notifications.TaskMonitor
import com.samcore.android.notifications.AndroidConnectTaskExecutor

/**
 * Deliberately not Hilt/Dagger for this first slice — one transport
 * singleton and a handful of small ViewModels don't need a DI framework yet,
 * and adding one is exactly the kind of unbounded change ways-of-working asks
 * to avoid unless there's a real reason. Swap this for Hilt later if the
 * dependency graph actually grows past what this can comfortably express.
 */
class AppContainer(context: Context) {
    private val devicePrefsStore = DevicePrefsStore(context.applicationContext)
    private val identityStore = AndroidEncryptedIdentityStore(context.applicationContext)
    private val capabilities = AndroidCapabilityReporter(context.applicationContext)
    val samTransport: SamTransport = HttpSseSamTransport(
        devicePrefsStore,
        identityStore = identityStore,
        capabilitiesProvider = capabilities::snapshot,
    )

    // Application-scoped (not tied to any ViewModel) so a watched task keeps
    // being observed — and can still trigger a completion notification —
    // across screen navigation. AndroidTaskKeepAlive additionally asks for a
    // foreground service while a watch is live (TaskWatchForegroundService
    // reads taskMonitor.isWatching from this container to know when to stop).
    // See TaskMonitor's own doc comment for what this does and doesn't survive.
    val taskMonitor = TaskMonitor(
        samTransport,
        AndroidTaskNotifier(context),
        AndroidTaskKeepAlive(context),
    )
    val connectTaskExecutor = AndroidConnectTaskExecutor(context, samTransport)
}
