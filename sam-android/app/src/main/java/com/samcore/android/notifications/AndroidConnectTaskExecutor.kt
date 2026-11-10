package com.samcore.android.notifications

import android.content.Context
import com.samcore.android.ai.SamMobileInferenceEngine
import com.samcore.android.automation.AndroidAppLauncher
import com.samcore.android.automation.SamAccessibilityService
import com.samcore.android.automation.SamFileManager
import com.samcore.android.automation.SamNotificationListener
import com.samcore.android.data.transport.ConnectDeviceTask
import com.samcore.android.data.transport.SamTransport
import com.samcore.android.data.transport.TransportResult
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Executes cross-device and local tasks routed to this Android client.
 * Supports:
 * - Notifications (posting & reading permitted notifications)
 * - App Launching and URL opening
 * - Accessibility-based UI interaction (clicks, text input, navigation)
 * - Scoped Storage file receiving and checking
 * - On-device local AI inference
 */
class AndroidConnectTaskExecutor(
    context: Context,
    private val transport: SamTransport,
    private val appLauncher: AndroidAppLauncher = AndroidAppLauncher(context.applicationContext),
    private val fileManager: SamFileManager = SamFileManager(context.applicationContext),
    private val mobileInference: SamMobileInferenceEngine = SamMobileInferenceEngine(context.applicationContext)
) {
    private val appContext = context.applicationContext

    suspend fun execute(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val acknowledged = transport.acknowledgeConnectTask(task.taskId)
        if (acknowledged is TransportResult.Failure) return acknowledged

        return when (task.action) {
            ACTION_SHOW_NOTIFICATION -> executeShowNotification(task)
            ACTION_APP_LAUNCH -> executeAppLaunch(task)
            ACTION_VIEW_URL -> executeViewUrl(task)
            ACTION_SHARE -> executeShare(task)
            ACTION_GET_NOTIFICATIONS -> executeGetNotifications(task)
            ACTION_ACCESSIBILITY_CLICK -> executeAccessibilityClick(task)
            ACTION_ACCESSIBILITY_TYPE -> executeAccessibilityType(task)
            ACTION_ACCESSIBILITY_ACTION -> executeAccessibilityAction(task)
            ACTION_RECEIVE_FILE -> executeReceiveFile(task)
            ACTION_LOCAL_INFER -> executeLocalInfer(task)
            else -> transport.failConnectTask(task.taskId, "Action '${task.action}' is not supported by this Android client.")
        }
    }

    private suspend fun executeShowNotification(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val title = task.payload["title"]?.let { (it as? JsonPrimitive)?.content }?.takeIf { it.isNotBlank() } ?: "SAM notification"
        val message = task.payload["message"]?.let { (it as? JsonPrimitive)?.content }?.takeIf { it.isNotBlank() }
            ?: return transport.failConnectTask(task.taskId, "Notification task payload requires a non-empty 'message'.")

        transport.reportConnectTaskProgress(task.taskId, "Posting a notification", 50)
        if (!SamNotifications.notifyRouted(appContext, task.taskId, title, message)) {
            return transport.failConnectTask(task.taskId, "Notification permission is unavailable.")
        }
        transport.reportConnectTaskAction(task.taskId, "Submitted private notification")
        transport.reportConnectTaskVerification(task.taskId, true, "Notification accepted by Android system.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("submitted", true) })
    }

    private suspend fun executeAppLaunch(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val appName = task.payload["app"]?.let { (it as? JsonPrimitive)?.content }
            ?: return transport.failConnectTask(task.taskId, "Missing 'app' parameter in app_launch payload.")

        transport.reportConnectTaskProgress(task.taskId, "Launching application $appName", 50)
        val launched = appLauncher.launchAppByNameOrPackage(appName)
        if (!launched) {
            return transport.failConnectTask(task.taskId, "Could not locate or launch application '$appName'.")
        }
        transport.reportConnectTaskAction(task.taskId, "Launched $appName via intent")
        transport.reportConnectTaskVerification(task.taskId, true, "Application $appName started in foreground.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("launched", true); put("app", appName) })
    }

    private suspend fun executeViewUrl(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val url = task.payload["url"]?.let { (it as? JsonPrimitive)?.content }
            ?: return transport.failConnectTask(task.taskId, "Missing 'url' parameter.")

        transport.reportConnectTaskProgress(task.taskId, "Opening URL", 50)
        val opened = appLauncher.openUrl(url)
        if (!opened) return transport.failConnectTask(task.taskId, "Failed to launch browser for $url.")
        transport.reportConnectTaskVerification(task.taskId, true, "Browser launched with URL.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("opened", true); put("url", url) })
    }

    private suspend fun executeShare(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val content = task.payload["content"]?.let { (it as? JsonPrimitive)?.content }
            ?: return transport.failConnectTask(task.taskId, "Missing 'content' parameter.")
        val title = task.payload["title"]?.let { (it as? JsonPrimitive)?.content } ?: "Share via SAM"

        transport.reportConnectTaskProgress(task.taskId, "Opening share sheet", 50)
        val shared = appLauncher.shareContent(content, title)
        if (!shared) return transport.failConnectTask(task.taskId, "Share sheet failed to open.")
        transport.reportConnectTaskVerification(task.taskId, true, "Share sheet presented.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("shared", true) })
    }

    private suspend fun executeGetNotifications(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val listener = SamNotificationListener.instance
        if (listener == null) {
            return transport.failConnectTask(
                task.taskId,
                "Notification Listener Service is not enabled. Please enable it in Android Settings > Notification Access."
            )
        }
        transport.reportConnectTaskProgress(task.taskId, "Reading permitted notifications", 50)
        val notifications = listener.getActiveNotificationsList()
        val notifArray = buildJsonArray {
            for (n in notifications) {
                add(buildJsonObject {
                    put("package", n.packageName)
                    put("title", n.title)
                    put("text", n.text)
                    put("timestamp", n.postTime)
                })
            }
        }
        transport.reportConnectTaskVerification(task.taskId, true, "Collected ${notifications.size} notifications.")
        return transport.completeConnectTask(task.taskId, buildJsonObject {
            put("count", notifications.size)
            put("notifications", notifArray)
        })
    }

    private suspend fun executeAccessibilityClick(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val service = SamAccessibilityService.instance
            ?: return transport.failConnectTask(task.taskId, "Accessibility Service is not enabled.")

        val text = task.payload["text"]?.let { (it as? JsonPrimitive)?.content }
        val x = task.payload["x"]?.let { (it as? JsonPrimitive)?.content }?.toFloatOrNull()
        val y = task.payload["y"]?.let { (it as? JsonPrimitive)?.content }?.toFloatOrNull()

        transport.reportConnectTaskProgress(task.taskId, "Performing UI click", 50)
        val clicked = if (text != null) {
            service.clickNodeWithText(text)
        } else if (x != null && y != null) {
            service.clickCoordinates(x, y)
        } else false

        if (!clicked) return transport.failConnectTask(task.taskId, "Accessibility click failed to find target.")
        transport.reportConnectTaskVerification(task.taskId, true, "Click dispatched.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("clicked", true) })
    }

    private suspend fun executeAccessibilityType(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val service = SamAccessibilityService.instance
            ?: return transport.failConnectTask(task.taskId, "Accessibility Service is not enabled.")
        val text = task.payload["text"]?.let { (it as? JsonPrimitive)?.content }
            ?: return transport.failConnectTask(task.taskId, "Missing text to type.")

        transport.reportConnectTaskProgress(task.taskId, "Entering text", 50)
        val typed = service.inputText(text)
        if (!typed) return transport.failConnectTask(task.taskId, "No focused text field found to type into.")
        transport.reportConnectTaskVerification(task.taskId, true, "Text typed successfully.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("typed", true) })
    }

    private suspend fun executeAccessibilityAction(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val service = SamAccessibilityService.instance
            ?: return transport.failConnectTask(task.taskId, "Accessibility Service is not enabled.")
        val actionName = task.payload["action"]?.let { (it as? JsonPrimitive)?.content } ?: "back"
        val globalCode = when (actionName.lowercase()) {
            "home" -> android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME
            "recents" -> android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_RECENTS
            else -> android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK
        }
        val done = service.performGlobal(globalCode)
        if (!done) return transport.failConnectTask(task.taskId, "Global action $actionName failed.")
        transport.reportConnectTaskVerification(task.taskId, true, "Global action $actionName executed.")
        return transport.completeConnectTask(task.taskId, buildJsonObject { put("action", actionName); put("success", true) })
    }

    private suspend fun executeReceiveFile(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val filename = task.payload["filename"]?.let { (it as? JsonPrimitive)?.content } ?: "received_file"
        val base64Data = task.payload["data"]?.let { (it as? JsonPrimitive)?.content } ?: ""
        val expectedSha256 = task.payload["sha256"]?.let { (it as? JsonPrimitive)?.content }
        val bytes = android.util.Base64.decode(base64Data, android.util.Base64.DEFAULT)

        transport.reportConnectTaskProgress(task.taskId, "Writing file to scoped storage", 50)
        val result = fileManager.saveReceivedFile(filename, bytes, expectedSha256)
        if (!result.success) {
            return transport.failConnectTask(task.taskId, result.error ?: "File saving failed.")
        }
        transport.reportConnectTaskVerification(task.taskId, true, "File stored at ${result.filePath}")
        return transport.completeConnectTask(task.taskId, buildJsonObject {
            put("saved", true)
            put("path", result.filePath ?: "")
            put("size_bytes", result.fileSize)
            put("sha256", result.sha256 ?: "")
        })
    }

    private suspend fun executeLocalInfer(task: ConnectDeviceTask): TransportResult<ConnectDeviceTask> {
        val prompt = task.payload["prompt"]?.let { (it as? JsonPrimitive)?.content }
            ?: return transport.failConnectTask(task.taskId, "Missing 'prompt' parameter.")
        transport.reportConnectTaskProgress(task.taskId, "Running on-device local AI inference", 30)
        val (response, metrics) = mobileInference.infer(prompt)
        transport.reportConnectTaskVerification(task.taskId, true, "Local inference completed in ${metrics.durationMs}ms.")
        return transport.completeConnectTask(task.taskId, buildJsonObject {
            put("response", response)
            put("tokens", metrics.tokensGenerated)
            put("duration_ms", metrics.durationMs)
            put("tokens_per_sec", metrics.tokensPerSecond.toDouble())
        })
    }

    companion object {
        const val ACTION_SHOW_NOTIFICATION = "show_notification"
        const val ACTION_APP_LAUNCH = "app_launch"
        const val ACTION_VIEW_URL = "view_url"
        const val ACTION_SHARE = "share_content"
        const val ACTION_GET_NOTIFICATIONS = "get_notifications"
        const val ACTION_ACCESSIBILITY_CLICK = "accessibility_click"
        const val ACTION_ACCESSIBILITY_TYPE = "accessibility_type"
        const val ACTION_ACCESSIBILITY_ACTION = "accessibility_action"
        const val ACTION_RECEIVE_FILE = "receive_file"
        const val ACTION_LOCAL_INFER = "local_infer"
    }
}
