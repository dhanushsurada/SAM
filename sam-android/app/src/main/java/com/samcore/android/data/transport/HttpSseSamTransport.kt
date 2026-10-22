package com.samcore.android.data.transport

import com.samcore.android.data.local.PairedDeviceStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.Signature
import java.util.Base64
import java.util.concurrent.TimeUnit

/**
 * SAM Connect pairing and authenticated device operations use the contract in
 * docs/architecture/CROSS_DEVICE_PROTOCOL.md. Phone-submitted work remains on
 * the existing /api/iqoo/* gateway; those routes are a separate Core-owned
 * flow. All HTTP details stay behind SamTransport for testability.
 */
class HttpSseSamTransport(
    private val prefsStore: PairedDeviceStore,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS) // regular calls only — see sseClient below
        .build(),
    sseReadTimeoutSeconds: Long = SSE_READ_TIMEOUT_SECONDS,
    private val identityStore: DeviceIdentityStore = EphemeralDeviceIdentityStore(),
    private val capabilitiesProvider: () -> Map<String, DeviceCapability> = { emptyMap() },
) : SamTransport {

    // The event stream needs its own, longer read timeout than regular calls:
    // a real task can sit in one phase for minutes with no new *event*, so the
    // 15s used for request/response calls would kill healthy streams. History:
    // the first version of this fix disabled the timeout entirely (0 =
    // infinite); that was reasonable while nothing consumed the stream except
    // a screen, but it is wrong now that a foreground service keeps the app
    // alive while the stream is open — a half-open connection (SAM Core's
    // laptop closes its lid, Wi-Fi roams) would otherwise look like "SAM is
    // working" until TaskMonitor's overall cap.
    //
    // The bound is justified by what the repo's server actually does, not by
    // PROTOCOL.md (which only says heartbeats are sent "during idle gaps"
    // with no interval): interfaces/api/server.py's event_stream() waits at
    // most 1.0s for a new event and otherwise yields ": heartbeat" — so while
    // the connection is healthy, bytes arrive roughly every second. 60s is
    // ~60x that. PROVISIONAL: this is an assumption about the pre-existing
    // (hackathon-track) server; Agent 3's contract must state a heartbeat
    // interval, and this value must stay comfortably above it. If a future
    // server sends no heartbeats, idle streams will be cut at this timeout;
    // TaskMonitor then reconnects (bounded — see its RECONNECT section), so a
    // silent server would look like a flapping connection and the watch would
    // end without a completion notification once that budget is spent.
    //
    // Regular request/response calls keep the timeout in [client]; only the
    // event stream uses this one. internal (not private) only so a test can
    // pin the setting — see HttpSseSamTransportTest.
    internal val sseClient: OkHttpClient = client.newBuilder()
        .readTimeout(sseReadTimeoutSeconds, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true }
    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    // Starts Connecting (meaning "not yet determined"), not Disconnected —
    // restore() always resolves this one way or the other. The NavGraph start
    // destination watches for exactly that transition instead of guessing.
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Connecting)
    override val connectionState: Flow<ConnectionState> = _connectionState

    private var currentBaseUrl: String? = null

    override suspend fun restore() {
        val paired = try {
            prefsStore.pairedDevice.first()
        } catch (e: Exception) {
            null
        }
        if (paired != null) {
            currentBaseUrl = paired.baseUrl
            _connectionState.value = ConnectionState.Connected(paired.baseUrl, paired.device)
        } else {
            _connectionState.value = ConnectionState.Disconnected
        }
    }

    // --- Pairing: POST /api/connect/pairing/redeem -------------------------

    override suspend fun pair(baseUrl: String, pairingCode: String): TransportResult<DeviceInfo> =
        withContext(Dispatchers.IO) {
            val normalizedBase = baseUrl.trimEnd('/')
            try {
                val identity = identityStore.loadOrCreate()
                val payload = PairingRedeemRequest(
                    token = pairingCode.trim(),
                    deviceId = identity.deviceId,
                    deviceName = android.os.Build.MODEL?.takeIf { it.isNotBlank() } ?: "Android device",
                    publicKey = ConnectIdentityCrypto.publicKeyPem(identity.keyPair),
                    capabilities = reportedCapabilities(),
                )
                val body = json.encodeToString(payload).toByteArray(StandardCharsets.UTF_8)
                val request = Request.Builder()
                    .url("$normalizedBase/api/connect/pairing/redeem")
                    .post(body.toRequestBody(jsonMedia))
                    .build()
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        return@withContext TransportResult.Failure(
                            "Pairing failed: ${httpFailure(response)}"
                        )
                    }
                    val text = response.body?.string().orEmpty()
                    val redeemed = json.decodeFromString(PairingRedeemResponse.serializer(), text)
                    if (redeemed.deviceId != identity.deviceId || redeemed.status != "trusted") {
                        return@withContext TransportResult.Failure("SAM returned an unexpected pairing identity or status.")
                    }
                    val device = DeviceInfo(identity.deviceId, payload.deviceName)
                    currentBaseUrl = normalizedBase
                    prefsStore.save(normalizedBase, device)
                    _connectionState.value = ConnectionState.Connected(normalizedBase, device)
                    TransportResult.Success(device)
                }
            } catch (e: IOException) {
                TransportResult.Failure("Could not reach $normalizedBase — check same-WiFi network and address.", e)
            } catch (e: Exception) {
                TransportResult.Failure("Unexpected pairing error: ${e.message}", e)
            }
        }

    override suspend fun unpair() {
        currentBaseUrl = null
        prefsStore.clear()
        _connectionState.value = ConnectionState.Disconnected
    }

    // --- Connect authentication and reachability -------------------------

    override suspend fun checkConnection(): TransportResult<Unit> = when (val result = refreshConnectTasks()) {
        is TransportResult.Success -> TransportResult.Success(Unit)
        is TransportResult.Failure -> result
    }

    override suspend fun refreshConnectTasks(): TransportResult<List<ConnectDeviceTask>> =
        withContext(Dispatchers.IO) {
            val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
            val paired = prefsStore.pairedDevice.first()
                ?: return@withContext TransportResult.Failure("Not paired")
            try {
                val capabilitiesBody = json.encodeToString(
                    CapabilitiesUpdateRequest(reportedCapabilities())
                ).toByteArray(StandardCharsets.UTF_8)
                val capabilitiesRequest = signedRequest(
                    base, "/api/connect/devices/${paired.device.deviceId}/capabilities", "PUT", capabilitiesBody
                )
                client.newCall(capabilitiesRequest).execute().use { response ->
                    if (!response.isSuccessful) {
                        if (response.code == 401) {
                            _connectionState.value = ConnectionState.Error("Device trust expired or revoked: ${httpFailure(response)}")
                        }
                        return@withContext TransportResult.Failure(
                            "Capability update failed: ${httpFailure(response)}"
                        )
                    }
                }
                val request = signedRequest(base, "/api/connect/devices/${paired.device.deviceId}/heartbeat", "POST")
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        val detail = httpFailure(response)
                        if (response.code == 401) _connectionState.value = ConnectionState.Error("Device trust expired or revoked: $detail")
                        return@withContext TransportResult.Failure("SAM Connect check failed: $detail")
                    }
                    val heartbeat = json.decodeFromString(
                        ConnectHeartbeat.serializer(), response.body?.string().orEmpty()
                    )
                    if (heartbeat.deviceId != paired.device.deviceId) {
                        return@withContext TransportResult.Failure("SAM returned a heartbeat for a different device.")
                    }
                    TransportResult.Success(heartbeat.pendingTasks)
                }
            } catch (e: IOException) {
                _connectionState.value = ConnectionState.Error("Unreachable: ${e.message}")
                TransportResult.Failure("Unreachable: ${e.message}", e)
            } catch (e: SerializationException) {
                TransportResult.Failure("Unexpected Connect response: ${e.message}", e)
            } catch (e: Exception) {
                TransportResult.Failure("Connect request failed: ${e.message}", e)
            }
        }

    override suspend fun acknowledgeConnectTask(taskId: String) = postConnectTask(taskId, "ack", null)

    override suspend fun reportConnectTaskProgress(taskId: String, message: String, pct: Int?) =
        postConnectTask(taskId, "progress", json.encodeToString(ConnectTaskProgress(message, pct)))

    override suspend fun reportConnectTaskAction(taskId: String, description: String) =
        postConnectTask(taskId, "action", json.encodeToString(ConnectTaskAction(description)))

    override suspend fun reportConnectTaskVerification(taskId: String, verified: Boolean, detail: String) =
        postConnectTask(taskId, "verification", json.encodeToString(ConnectTaskVerification(verified, detail)))

    override suspend fun completeConnectTask(taskId: String, result: kotlinx.serialization.json.JsonObject?) =
        postConnectTask(taskId, "complete", json.encodeToString(ConnectTaskComplete(result)))

    override suspend fun failConnectTask(taskId: String, error: String) =
        postConnectTask(taskId, "fail", json.encodeToString(ConnectTaskFailure(error)))

    private suspend fun postConnectTask(taskId: String, action: String, jsonBody: String?): TransportResult<ConnectDeviceTask> =
        withContext(Dispatchers.IO) {
            val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
            val payload = jsonBody?.toByteArray(StandardCharsets.UTF_8) ?: byteArrayOf()
            try {
                val request = signedRequest(base, "/api/connect/tasks/$taskId/$action", "POST", payload)
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        return@withContext TransportResult.Failure("Connect task update failed: ${httpFailure(response)}")
                    }
                    TransportResult.Success(json.decodeFromString(
                        ConnectDeviceTask.serializer(), response.body?.string().orEmpty()
                    ))
                }
            } catch (e: IOException) {
                TransportResult.Failure("Could not reach SAM Core: ${e.message}", e)
            } catch (e: Exception) {
                TransportResult.Failure("Unexpected Connect task response: ${e.message}", e)
            }
        }

    // --- Tasks (grounded — POST/GET /api/iqoo/tasks in PROTOCOL.md) --------

    override suspend fun sendTask(request: TaskRequest): TransportResult<TaskSnapshot> =
        withContext(Dispatchers.IO) {
            val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
            val body = json.encodeToString(request).toRequestBody(jsonMedia)
            val httpRequest = Request.Builder().url("$base/api/iqoo/tasks").post(body).build()
            executeForSnapshot(httpRequest)
        }

    override suspend fun getTask(taskId: String): TransportResult<TaskSnapshot> =
        withContext(Dispatchers.IO) {
            val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
            val httpRequest = Request.Builder().url("$base/api/iqoo/tasks/$taskId").get().build()
            executeForSnapshot(httpRequest)
        }

    override suspend fun cancelTask(taskId: String): TransportResult<Unit> =
        withContext(Dispatchers.IO) {
            val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
            val httpRequest = Request.Builder()
                .url("$base/api/iqoo/tasks/$taskId/cancel")
                .post("".toRequestBody())
                .build()
            try {
                client.newCall(httpRequest).execute().use { response ->
                    if (response.isSuccessful) TransportResult.Success(Unit)
                    else TransportResult.Failure("Cancel failed: HTTP ${response.code}")
                }
            } catch (e: IOException) {
                TransportResult.Failure("Could not reach SAM Core: ${e.message}", e)
            }
        }

    private fun executeForSnapshot(request: Request): TransportResult<TaskSnapshot> = try {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                TransportResult.Failure("HTTP ${response.code}")
            } else {
                val text = response.body?.string().orEmpty()
                TransportResult.Success(json.decodeFromString(TaskSnapshot.serializer(), text))
            }
        }
    } catch (e: IOException) {
        TransportResult.Failure("Could not reach SAM Core: ${e.message}", e)
    } catch (e: SerializationException) {
        // A body that is not valid JSON, lacks a required field, or carries a
        // status this app's TaskStatus does not list (the repo's task store also
        // accepts "testing", which TaskStatus lacks — interfaces/api/task_store.py
        // ALL_STATUSES) used to escape from here as an uncaught exception. Callers
        // treat this function as returning a TransportResult, and TaskMonitor now
        // calls getTask repeatedly from a background scope where an escaped
        // exception ends the whole process. Reported as a failed lookup instead.
        TransportResult.Failure("Unexpected response from SAM Core: ${e.message}", e)
    }

    // --- Task events (grounded — GET /api/iqoo/tasks/{id}/events, SSE) -----

    override fun taskEvents(taskId: String, afterSeq: Long?): Flow<TaskEvent> = callbackFlow {
        val base = currentBaseUrl
        if (base == null) {
            close(IllegalStateException("Not paired"))
            return@callbackFlow
        }
        val request = Request.Builder()
            .url("$base/api/iqoo/tasks/$taskId/events")
            .apply {
                // Resume point. interfaces/api/server.py reads this header (digits
                // only — anything else means "from the start") and replays just
                // the events with a higher seq; not described in PROTOCOL.md, so
                // provisional. Omitted on a first connection: no header = full history.
                if (afterSeq != null) header("Last-Event-ID", afterSeq.toString())
            }
            .build()

        // PROTOCOL.md: "Heartbeat comment lines (`: heartbeat\n\n`) are sent
        // during idle gaps" — SSE comment lines (no "event:"/"data:" prefix)
        // are handled by okhttp-sse internally and never reach onEvent, so no
        // special-casing is needed here for them.
        val listener = object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                try {
                    // seq comes from the SSE "id:" line (the protocol-level resume
                    // cursor), not from the JSON body — see TaskEvent.seq.
                    val parsed = json.decodeFromString(TaskEvent.serializer(), data)
                    trySend(parsed.copy(seq = id?.toLongOrNull()))
                } catch (e: Exception) {
                    // Malformed event payload — drop it rather than crash the
                    // stream; the task-status screen falls back to polling
                    // getTask() regardless, so one bad event isn't fatal.
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                close(t ?: IOException("SSE stream failed"))
            }

            override fun onClosed(eventSource: EventSource) {
                close()
            }
        }

        val eventSource = EventSources.createFactory(sseClient).newEventSource(request, listener)
        awaitClose { eventSource.cancel() }
    }

    companion object {
        /** See the comment on [sseClient] — provisional, derived from the repo's server, not from PROTOCOL.md. */
        const val SSE_READ_TIMEOUT_SECONDS = 60L
    }

    private fun signedRequest(base: String, path: String, method: String, body: ByteArray = byteArrayOf()): Request {
        val identity = identityStore.loadOrCreate()
        val timestamp = (System.currentTimeMillis() / 1000L).toString()
        val nonce = ConnectIdentityCrypto.randomNonce()
        val bodyHash = MessageDigest.getInstance("SHA-256").digest(body)
            .joinToString("") { "%02x".format(it) }
        val canonical = "${method.uppercase()}\n$path\n$timestamp\n$nonce\n$bodyHash"
        val signer = Signature.getInstance("Ed25519", ConnectIdentityCrypto.provider())
        signer.initSign(identity.keyPair.private)
        signer.update(canonical.toByteArray(StandardCharsets.UTF_8))
        val signature = Base64.getEncoder().encodeToString(signer.sign())
        val builder = Request.Builder()
            .url(base + path)
            .header("X-SAM-Device-Id", identity.deviceId)
            .header("X-SAM-Timestamp", timestamp)
            .header("X-SAM-Nonce", nonce)
            .header("X-SAM-Signature", signature)
        val requestBody = body.toRequestBody(jsonMedia)
        when (method.uppercase()) {
            "GET" -> builder.get()
            "PUT" -> builder.put(requestBody)
            "POST" -> builder.post(requestBody)
            else -> error("Unsupported signed Connect method: $method")
        }
        return builder.build()
    }

    private fun reportedCapabilities(): Map<String, DeviceCapability> = capabilitiesProvider()

    private fun httpFailure(response: okhttp3.Response): String {
        val body = response.body?.string().orEmpty()
        val detail = try {
            json.parseToJsonElement(body).let { element ->
                (element as? kotlinx.serialization.json.JsonObject)?.get("detail")?.toString()?.trim('"')
            }
        } catch (_: Exception) { null }
        return detail?.takeIf { it.isNotBlank() } ?: "HTTP ${response.code}"
    }
}
