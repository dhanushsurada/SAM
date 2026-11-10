package com.samcore.android.automation

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log

/**
 * Intercepts and formats permitted notifications for the assistant.
 * Policy compliance:
 * - Only active when explicitly enabled by user in Android Notification Access settings.
 * - Processes notification text only on explicit user query (e.g. "Summarize my notifications").
 * - Does not silently exfiltrate or store notifications in the background.
 */
class SamNotificationListener : NotificationListenerService() {

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
        Log.i(TAG, "Notification listener connected")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        instance = null
        Log.i(TAG, "Notification listener disconnected")
    }

    fun getActiveNotificationsList(limit: Int = 20): List<NotificationItem> {
        val active = activeNotifications ?: return emptyList()
        val result = mutableListOf<NotificationItem>()

        for (sbn in active.take(limit)) {
            val extras = sbn.notification.extras ?: continue
            val title = extras.getCharSequence("android.title")?.toString() ?: ""
            val text = extras.getCharSequence("android.text")?.toString() ?: ""
            val packageName = sbn.packageName ?: ""

            // Exclude SAM's own notifications to avoid recursion
            if (packageName == applicationContext.packageName) continue

            if (title.isNotBlank() || text.isNotBlank()) {
                result.add(
                    NotificationItem(
                        packageName = packageName,
                        title = title,
                        text = text,
                        postTime = sbn.postTime
                    )
                )
            }
        }
        return result
    }

    companion object {
        private const val TAG = "SamNotifListener"
        var instance: SamNotificationListener? = null
            private set

        val isListeningEnabled: Boolean
            get() = instance != null
    }
}

data class NotificationItem(
    val packageName: String,
    val title: String,
    val text: String,
    val postTime: Long
)
