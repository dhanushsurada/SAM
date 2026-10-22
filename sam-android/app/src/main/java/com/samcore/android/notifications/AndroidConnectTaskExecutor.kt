package com.samcore.android.notifications

import android.content.Context
import com.samcore.android.data.transport.ConnectDeviceTask
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TransportResult
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** User-triggered executor for the single Android Connect action implemented by this client. */
class AndroidConnectTaskExecutor(context: Context, private val transport: SamTransport) {
    private val appContext = context.applicationContext

    suspend fun execute(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val acknowledged = transport.acknowledgeConnectTask(task.taskId)
        if (acknowledged is TransportResult.Failure) return acknowledged

        if (task.action != ACTION_SHOW_NOTIFICATION) {
            return transport.failConnectTask(task.taskId, "This Android client does not support action '${task.action}'.")
        }
        if (task.requiredCapability != CAPABILITY_NOTIFICATIONS) {
            return transport.failConnectTask(task.taskId, "This action must be routed with the '$CAPABILITY_NOTIFICATIONS' capability.")
        }
        val title = task.payload["title"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
            ?.takeIf { it.isNotBlank() } ?: "SAM notification"
        val message = task.payload["message"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
            ?.takeIf { it.isNotBlank() }
            ?: return transport.failConnectTask(task.taskId, "Notification task payload requires a non-empty 'message'.")

        when (val progress = transport.reportConnectTaskProgress(task.taskId, "Posting a notification", 50)) {
            is TransportResult.Failure -> return progress
            is TransportResult.Success -> Unit
        }
        if (!SamNotifications.notifyRouted(appContext, task.taskId, title, message)) {
            return transport.failConnectTask(
                task.taskId,
                "Notification permission is unavailable. Enable SAM notifications in Android Settings and retry."
            )
        }
        when (val action = transport.reportConnectTaskAction(task.taskId, "Submitted a private notification to Android")) {
            is TransportResult.Failure -> return action
            is TransportResult.Success -> Unit
        }
        when (val verified = transport.reportConnectTaskVerification(
            task.taskId, true, "Notification request accepted; visibility depends on Android notification settings."
        )) {
            is TransportResult.Failure -> return verified
            is TransportResult.Success -> Unit
        }
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("submitted", true) })
    }

    companion object {
        const val ACTION_SHOW_NOTIFICATION = "show_notification"
        const val CAPABILITY_NOTIFICATIONS = "notifications"
    }
}
