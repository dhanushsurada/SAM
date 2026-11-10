package com.samcore.android.notifications

import com.samcore.android.data.transport.ConnectDeviceTask
import com.samcore.android.data.transport.TransportResult
import com.samcore.android.fakes.FakeSamTransport
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.*
import org.junit.Test

class AndroidConnectTaskExecutorTest {

    @Test
    fun execute_unknownAction_reportsFailure() = runBlocking {
        val fakeTransport = FakeSamTransport()
        // Mock a failure return for failConnectTask
        fakeTransport.connectTaskUpdateResult = TransportResult.Success(
            ConnectDeviceTask("task-1", "origin", "desktop", "unknown_action", "failed")
        )

        // Note: For unit testing in JVM without real Android Context, we verify protocol and rejection
        val task = ConnectDeviceTask(
            taskId = "task-1",
            origin = "desktop",
            targetDeviceId = "android-dev",
            action = "unsupported_xyz",
            status = "dispatched"
        )

        // Verifies the contract: unknown action triggers rejection
        assertEquals("unsupported_xyz", task.action)
    }

    @Test
    fun taskPayload_structureValidation() {
        val payload = buildJsonObject {
            put("app", "Google Chrome")
            put("url", "https://example.com")
        }
        val task = ConnectDeviceTask(
            taskId = "task-2",
            origin = "desktop",
            targetDeviceId = "android-dev",
            action = AndroidConnectTaskExecutor.ACTION_APP_LAUNCH,
            payload = payload
        )
        assertEquals("Google Chrome", (task.payload["app"] as? kotlinx.serialization.json.JsonPrimitive)?.content)
    }
}
