package com.samcore.android.data.local

import android.content.Context
import androidx.core.app.NotificationManagerCompat
import com.samcore.android.automation.SamAccessibilityService
import com.samcore.android.data.transport.DeviceCapability

/** Reports capabilities this Android client actively supports and their permission state. */
class AndroidCapabilityReporter(context: Context) {
    private val appContext = context.applicationContext

    fun snapshot(): Map<String, DeviceCapability> {
        val hasNotif = NotificationManagerCompat.from(appContext).areNotificationsEnabled()
        val notifPermission = if (hasNotif) "granted" else "denied"
        val hasAccessibility = SamAccessibilityService.isServiceEnabled

        return mapOf(
            "notifications" to DeviceCapability(
                available = hasNotif,
                permission = notifPermission,
            ),
            "app-launch" to DeviceCapability(
                available = true,
                permission = "granted",
            ),
            "device-control" to DeviceCapability(
                available = hasAccessibility,
                permission = if (hasAccessibility) "granted" else "not_requested",
            ),
            "model-inference" to DeviceCapability(
                available = true,
                permission = "granted",
            ),
            "file-transfer" to DeviceCapability(
                available = true,
                permission = "granted",
            ),
            "voice" to DeviceCapability(available = false, permission = "not_requested"),
            "camera" to DeviceCapability(available = false, permission = "not_requested"),
        )
    }
}
