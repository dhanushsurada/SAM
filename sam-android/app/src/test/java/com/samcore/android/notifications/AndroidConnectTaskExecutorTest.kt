package com.samcore.android.notifications

import com.samcore.android.ai.InferenceMetrics
import com.samcore.android.ai.SamMobileInferenceEngine
import com.samcore.android.automation.AndroidAppLauncher
import com.samcore.android.automation.FileResult
import com.samcore.android.automation.SamFileManager
import com.samcore.android.data.transport.ConnectDeviceTask
import com.samcore.android.data.transport.TransportResult
import com.samcore.android.fakes.FakeSamTransport
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.*
import org.junit.Test
import java.util.Base64

class AndroidConnectTaskExecutorTest {

    private class MockAppLauncher : AndroidAppLauncher(null) {
        var launchAppResult = true
        var openUrlResult = true
        var shareContentResult = true
        var lastLaunchedApp: String? = null
        var lastOpenedUrl: String? = null
        var lastSharedContent: String? = null

        override fun launchAppByNameOrPackage(appNameOrPkg: String): Boolean {
            lastLaunchedApp = appNameOrPkg
            return launchAppResult
        }

        override fun openUrl(url: String): Boolean {
            lastOpenedUrl = url
            return openUrlResult
        }

        override fun shareContent(text: String, title: String): Boolean {
            lastSharedContent = text
            return shareContentResult
        }
    }

    private class MockFileManager : SamFileManager(null) {
        var saveResult = FileResult(success = true, filePath = "/mock/downloads/test.txt", fileSize = 12L, sha256 = "mock-sha")
        var lastSavedFilename: String? = null
        var lastSavedBytes: ByteArray? = null

        override fun saveReceivedFile(filename: String, bytes: ByteArray, expectedSha256: String?): FileResult {
            lastSavedFilename = filename
            lastSavedBytes = bytes
            return saveResult
        }
    }

    private class MockMobileInference : SamMobileInferenceEngine(null) {
        var inferenceResult = Pair("SAM response text", InferenceMetrics(tokensGenerated = 15, durationMs = 120L, tokensPerSecond = 125.0f, ramUsedMb = 350L))
        var lastPrompt: String? = null

        override suspend fun infer(prompt: String): Pair<String, InferenceMetrics> {
            lastPrompt = prompt
            return inferenceResult
        }
    }

    private fun createTask(action: String, payload: kotlinx.serialization.json.JsonObject = buildJsonObject {}): ConnectDeviceTask {
        return ConnectDeviceTask(
            taskId = "task-${System.currentTimeMillis()}-${(1..1000).random()}",
            origin = "desktop",
            targetDeviceId = "android-target",
            action = action,
            payload = payload,
            status = "dispatched",
            createdAt = "2026-11-15T08:00:00Z",
            updatedAt = "2026-11-15T08:00:00Z"
        )
    }

    @Test
    fun execute_transportAcknowledgeFailure_abortsImmediately() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Failure("Network timeout on ACK")
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH, buildJsonObject { put("app", "Camera") })
        val result = executor.execute(task)

        assertTrue(result is TransportResult.Failure)
        assertEquals("Network timeout on ACK", (result as TransportResult.Failure).error)
        assertEquals(listOf(task.taskId), transport.acknowledgedTasks)
        assertTrue(transport.completedTasks.isEmpty())
        assertTrue(transport.failedTasks.isEmpty())
    }

    @Test
    fun execute_unknownAction_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask("unsupported_xyz"))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask("unsupported_xyz")
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertEquals(task.taskId, transport.failedTasks[0].first)
        assertTrue(transport.failedTasks[0].second.contains("is not supported by this Android client"))
    }

    @Test
    fun execute_showNotification_missingMessage_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_SHOW_NOTIFICATION))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_SHOW_NOTIFICATION, buildJsonObject { put("title", "Hello") })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("requires a non-empty 'message'"))
    }

    @Test
    fun execute_showNotification_noContextPermission_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_SHOW_NOTIFICATION))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_SHOW_NOTIFICATION, buildJsonObject {
            put("title", "Hello")
            put("message", "Task done")
        })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Notification permission is unavailable"))
    }

    @Test
    fun execute_appLaunch_missingApp_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH, buildJsonObject {})
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Missing 'app' parameter"))
    }

    @Test
    fun execute_appLaunch_appNotFound_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH))
        val launcher = MockAppLauncher().apply { launchAppResult = false }
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, appLauncher = launcher)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH, buildJsonObject { put("app", "NonExistentApp") })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Could not locate or launch application"))
        assertEquals("NonExistentApp", launcher.lastLaunchedApp)
    }

    @Test
    fun execute_appLaunch_success_reportsCompletion() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH))
        val launcher = MockAppLauncher().apply { launchAppResult = true }
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, appLauncher = launcher)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_APP_LAUNCH, buildJsonObject { put("app", "YouTube") })
        val result = executor.execute(task)

        assertTrue(result is TransportResult.Success)
        assertEquals("YouTube", launcher.lastLaunchedApp)
        assertEquals(1, transport.completedTasks.size)
        assertEquals(task.taskId, transport.completedTasks[0].first)
        val payload = transport.completedTasks[0].second
        assertNotNull(payload)
        assertEquals(JsonPrimitive(true), payload!!["launched"])
        assertEquals(JsonPrimitive("YouTube"), payload["app"])
    }

    @Test
    fun execute_viewUrl_missingUrl_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_VIEW_URL))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_VIEW_URL, buildJsonObject {})
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Missing 'url' parameter"))
    }

    @Test
    fun execute_viewUrl_success_reportsCompletion() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_VIEW_URL))
        val launcher = MockAppLauncher().apply { openUrlResult = true }
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, appLauncher = launcher)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_VIEW_URL, buildJsonObject { put("url", "https://sam.dev") })
        executor.execute(task)

        assertEquals("https://sam.dev", launcher.lastOpenedUrl)
        assertEquals(1, transport.completedTasks.size)
        val payload = transport.completedTasks[0].second
        assertEquals(JsonPrimitive(true), payload!!["opened"])
        assertEquals(JsonPrimitive("https://sam.dev"), payload["url"])
    }

    @Test
    fun execute_share_missingContent_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_SHARE))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_SHARE, buildJsonObject {})
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Missing 'content' parameter"))
    }

    @Test
    fun execute_share_success_reportsCompletion() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_SHARE))
        val launcher = MockAppLauncher().apply { shareContentResult = true }
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, appLauncher = launcher)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_SHARE, buildJsonObject {
            put("content", "Shared report text")
            put("title", "Project Summary")
        })
        executor.execute(task)

        assertEquals("Shared report text", launcher.lastSharedContent)
        assertEquals(1, transport.completedTasks.size)
    }

    @Test
    fun execute_getNotifications_listenerDisabled_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_GET_NOTIFICATIONS))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_GET_NOTIFICATIONS)
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Notification Listener Service is not enabled"))
    }

    @Test
    fun execute_accessibilityClick_serviceDisabled_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_CLICK))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_CLICK, buildJsonObject { put("text", "Submit") })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Accessibility Service is not enabled"))
    }

    @Test
    fun execute_accessibilityType_serviceDisabled_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_TYPE))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_TYPE, buildJsonObject { put("text", "Hello") })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Accessibility Service is not enabled"))
    }

    @Test
    fun execute_accessibilityAction_serviceDisabled_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_ACTION))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_ACCESSIBILITY_ACTION, buildJsonObject { put("action", "home") })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Accessibility Service is not enabled"))
    }

    @Test
    fun execute_receiveFile_success_writesAndVerifiesSha256() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_RECEIVE_FILE))
        val fileManager = MockFileManager()
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, fileManager = fileManager)

        val content = "File content for test"
        val base64Content = Base64.getEncoder().encodeToString(content.toByteArray(Charsets.UTF_8))

        val task = createTask(AndroidConnectTaskExecutor.ACTION_RECEIVE_FILE, buildJsonObject {
            put("filename", "notes.txt")
            put("data", base64Content)
            put("sha256", "mock-sha")
        })
        val result = executor.execute(task)

        assertTrue(result is TransportResult.Success)
        assertEquals("notes.txt", fileManager.lastSavedFilename)
        assertEquals(content, String(fileManager.lastSavedBytes!!, Charsets.UTF_8))
        assertEquals(1, transport.completedTasks.size)
        val payload = transport.completedTasks[0].second
        assertEquals(JsonPrimitive(true), payload!!["saved"])
        assertEquals(JsonPrimitive("/mock/downloads/test.txt"), payload["path"])
        assertEquals(JsonPrimitive("mock-sha"), payload["sha256"])
    }

    @Test
    fun execute_receiveFile_checksumMismatch_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_RECEIVE_FILE))
        val fileManager = MockFileManager().apply {
            saveResult = FileResult(success = false, error = "Checksum mismatch: expected a, got b")
        }
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, fileManager = fileManager)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_RECEIVE_FILE, buildJsonObject {
            put("filename", "corrupt.bin")
            put("data", "AAAA")
            put("sha256", "bad-hash")
        })
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Checksum mismatch"))
    }

    @Test
    fun execute_localInfer_missingPrompt_reportsFailure() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_LOCAL_INFER))
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_LOCAL_INFER, buildJsonObject {})
        executor.execute(task)

        assertEquals(1, transport.failedTasks.size)
        assertTrue(transport.failedTasks[0].second.contains("Missing 'prompt' parameter"))
    }

    @Test
    fun execute_localInfer_success_reportsMetrics() = runBlocking {
        val transport = FakeSamTransport()
        transport.connectTaskUpdateResult = TransportResult.Success(createTask(AndroidConnectTaskExecutor.ACTION_LOCAL_INFER))
        val inference = MockMobileInference()
        val executor = AndroidConnectTaskExecutor(context = null, transport = transport, mobileInference = inference)

        val task = createTask(AndroidConnectTaskExecutor.ACTION_LOCAL_INFER, buildJsonObject {
            put("prompt", "Summarize mobile status")
        })
        val result = executor.execute(task)

        assertTrue(result is TransportResult.Success)
        assertEquals("Summarize mobile status", inference.lastPrompt)
        assertEquals(1, transport.completedTasks.size)
        val payload = transport.completedTasks[0].second
        assertEquals(JsonPrimitive("SAM response text"), payload!!["response"])
        assertEquals(JsonPrimitive(15), payload["tokens"])
        assertEquals(JsonPrimitive(120L), payload["duration_ms"])
    }
}
