package com.samcore.android.data.local

import android.content.Context
import androidx.core.app.NotificationManagerCompat
import com.samcore.android.data.transport.DeviceCapability

/** Reports only capabilities this client currently implements. */
class AndroidCapabilityReporter(context: Context) {
    private val appContext = context.applicationContext

    fun snapshot(): Map<String, DeviceCapability> {
        val notificationPermission = if (
            NotificationManagerCompat.from(appContext).areNotificationsEnabled()
        ) "granted" else "denied"
        return mapOf(
            "notifications" to DeviceCapability(
                available = notificationPermission == "granted",
                permission = notificationPermission,
            ),
            "voice" to DeviceCapability(available = false, permission = "not_requested"),
            "camera" to DeviceCapability(available = false, permission = "not_requested"),
            "app-launch" to DeviceCapability(available = false, permission = "not_requested"),
            "device-control" to DeviceCapability(available = false, permission = "not_requested"),
        )
    }
}
