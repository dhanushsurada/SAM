package com.samcore.android.data.transport

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Shapes in this file are a v0 working assumption, not a frozen contract.
 *
 * Field names follow docs/iqoo/PROTOCOL.md (task state machine, SSE event
 * shape) and connect/core/device_registry.py (device_id/device_name/channel)
 * in the main SAM repo — the closest tested precedent found during
 * reconnaissance, not a resolved PDR §16 "shared contract." Everything here
 * sits behind the SamTransport interface (SamTransport.kt) specifically so
 * that when Agent 3 defines the real cross-device contract, only this file +
 * HttpSseSamTransport.kt need to change — no ViewModel or screen in this app
 * references these types directly except through that interface.
 */

@Serializable
data class DeviceInfo(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
    val channel: String = "android", // mirrors device_registry.py's channel column (today: "telegram")
)

sealed class ConnectionState {
    data object Disconnected : ConnectionState()
    data object Connecting : ConnectionState()
    data class Connected(val baseUrl: String, val device: DeviceInfo) : ConnectionState()
    data class Error(val message: String) : ConnectionState()
}

@Serializable
enum class TaskStatus {
    @SerialName("queued") QUEUED,
    @SerialName("received") RECEIVED,
    @SerialName("understanding") UNDERSTANDING,
    @SerialName("perceiving") PERCEIVING, // non-text input only — see PROTOCOL.md
    @SerialName("planning") PLANNING,
    @SerialName("executing") EXECUTING,
    @SerialName("verifying") VERIFYING,
    @SerialName("completed") COMPLETED,
    @SerialName("failed") FAILED,
    @SerialName("cancelled") CANCELLED,
}

@Serializable
data class TaskRequest(
    val instruction: String,
    @SerialName("input_type") val inputType: String = "text", // text | voice | image | image+text | image+voice
    val attachments: List<String> = emptyList(),
)

@Serializable
data class TaskSnapshot(
    @SerialName("task_id") val taskId: String,
    val instruction: String,
    @SerialName("input_type") val inputType: String,
    val status: TaskStatus,
    @SerialName("result_text") val resultText: String? = null,
    val error: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class TaskEvent(
    val type: String,
    @SerialName("task_id") val taskId: String,
    val phase: String,
    val message: String,
    val timestamp: String? = null,
)

/** Thin wrapper so callers don't need to know this is HTTP+SSE underneath. */
sealed class TransportResult<out T> {
    data class Success<T>(val value: T) : TransportResult<T>()
    data class Failure(val message: String, val cause: Throwable? = null) : TransportResult<Nothing>()
}
