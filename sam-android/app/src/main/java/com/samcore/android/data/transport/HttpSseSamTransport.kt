package com.samcore.android.data.transport

import com.samcore.android.data.local.PairedDeviceStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
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
import java.util.concurrent.TimeUnit

/**
 * v0 SamTransport implementation. Task/event/health calls are shaped after
 * docs/iqoo/PROTOCOL.md in the main repo — real, tested endpoints, just built
 * for a different (now-excluded) track. The pair() endpoint below is NOT
 * grounded the same way: no existing HTTP pairing endpoint was found during
 * reconnaissance (today's real pairing is a Telegram bot command flow, see
 * interfaces/telegram/pair_new_device.py — not an HTTP call at all). The
 * shape here — POST a code, get a device_id back — is a placeholder guess for
 * Agent 3 to replace, not a contract to build further app logic on top of.
 *
 * Everything below implements SamTransport (SamTransport.kt) — no other file
 * in the app touches OkHttp directly. Depends on PairedDeviceStore (an
 * interface), not the concrete DataStore-backed DevicePrefsStore, so this
 * class can be unit-tested (HttpSseSamTransportTest) against MockWebServer +
 * an in-memory fake store without needing a real Android Context.
 */
class HttpSseSamTransport(
    private val prefsStore: PairedDeviceStore,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS) // regular calls only — see sseClient below
        .build(),
    sseReadTimeoutSeconds: Long = SSE_READ_TIMEOUT_SECONDS,
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
    // server sends no heartbeats, idle streams will be cut at this timeout
    // and the watch will end without a completion notification.
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

    // --- Pairing (PLACEHOLDER SHAPE — see class doc) -----------------------

    override suspend fun pair(baseUrl: String, pairingCode: String): TransportResult<DeviceInfo> =
        withContext(Dispatchers.IO) {
            val normalizedBase = baseUrl.trimEnd('/')
            val body = json.encodeToString(mapOf("pairing_code" to pairingCode))
                .toRequestBody(jsonMedia)
            val request = Request.Builder()
                .url("$normalizedBase/api/connect/pair") // PLACEHOLDER path — confirm with Agent 3
                .post(body)
                .build()
            try {
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        return@withContext TransportResult.Failure(
                            "Pairing failed: HTTP ${response.code}"
                        )
                    }
                    val text = response.body?.string().orEmpty()
                    val device = json.decodeFromString(DeviceInfo.serializer(), text)
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

    // --- Health (grounded — GET /api/iqoo/health in PROTOCOL.md) -----------

    override suspend fun checkConnection(): TransportResult<Unit> = withContext(Dispatchers.IO) {
        val base = currentBaseUrl ?: return@withContext TransportResult.Failure("Not paired")
        val request = Request.Builder().url("$base/api/iqoo/health").get().build()
        try {
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    TransportResult.Success(Unit)
                } else {
                    TransportResult.Failure("Health check failed: HTTP ${response.code}")
                }
            }
        } catch (e: IOException) {
            _connectionState.value = ConnectionState.Error("Unreachable: ${e.message}")
            TransportResult.Failure("Unreachable: ${e.message}", e)
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
    }

    // --- Task events (grounded — GET /api/iqoo/tasks/{id}/events, SSE) -----

    override fun taskEvents(taskId: String): Flow<TaskEvent> = callbackFlow {
        val base = currentBaseUrl
        if (base == null) {
            close(IllegalStateException("Not paired"))
            return@callbackFlow
        }
        val request = Request.Builder().url("$base/api/iqoo/tasks/$taskId/events").build()

        // PROTOCOL.md: "Heartbeat comment lines (`: heartbeat\n\n`) are sent
        // during idle gaps" — SSE comment lines (no "event:"/"data:" prefix)
        // are handled by okhttp-sse internally and never reach onEvent, so no
        // special-casing is needed here for them.
        val listener = object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                try {
                    trySend(json.decodeFromString(TaskEvent.serializer(), data))
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
}
