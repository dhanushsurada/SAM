package com.samcore.android.data.transport

import com.samcore.android.fakes.FakePairedDeviceStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.Signature
import java.util.Base64

/**
 * Everything here runs against MockWebServer, not a real network — this is
 * exactly the kind of test the build report's "zero tests executed" line was
 * about, and per the build report accompanying this change, these have NOT
 * been run by an actual JVM/Gradle test task in this environment either (no
 * dependency resolution possible here — see that report). Written and
 * manually traced through, not executed.
 */
class HttpSseSamTransportTest {

    private lateinit var server: MockWebServer
    private lateinit var store: FakePairedDeviceStore
    private lateinit var transport: HttpSseSamTransport
    private lateinit var identity: DeviceIdentity

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        store = FakePairedDeviceStore()
        identity = ConnectIdentityCrypto.generate().copy(deviceId = "dev-1")
        transport = HttpSseSamTransport(store, identityStore = object : DeviceIdentityStore {
            override fun loadOrCreate() = identity
        })
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun baseUrl(): String = server.url("/").toString().trimEnd('/')

    // --- restore() / persistence --------------------------------------

    @Test
    fun `restore with nothing saved resolves to Disconnected`() = runTest {
        transport.restore()
        assertEquals(ConnectionState.Disconnected, transport.connectionState.first())
    }

    @Test
    fun `restore with a saved device resolves to Connected`() = runTest {
        val device = DeviceInfo(deviceId = "abc123", deviceName = "Dhanush's Pixel")
        store.save("http://192.168.1.50:8420", device)

        transport.restore()

        val state = transport.connectionState.first()
        assertTrue(state is ConnectionState.Connected)
        state as ConnectionState.Connected
        assertEquals("http://192.168.1.50:8420", state.baseUrl)
        assertEquals(device, state.device)
    }

    // --- pair() ---------------------------------------------------------

    @Test
    fun `pair success persists the device and updates connectionState`() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200)
                .setBody("""{"device_id":"dev-1","status":"trusted"}"""),
        )

        val result = transport.pair(baseUrl(), "123456")

        assertTrue(result is TransportResult.Success)
        val device = (result as TransportResult.Success).value
        assertEquals("dev-1", device.deviceId)

        val persisted = store.pairedDevice.first()
        assertEquals(device, persisted?.device)

        val state = transport.connectionState.first()
        assertTrue(state is ConnectionState.Connected)
        val request = server.takeRequest()
        assertEquals("/api/connect/pairing/redeem", request.path)
        assertEquals("POST", request.method)
        assertEquals("dev-1", kotlinx.serialization.json.Json.parseToJsonElement(request.body.readUtf8())
            .let { (it as kotlinx.serialization.json.JsonObject)["device_id"].toString().trim('"') })
    }

    @Test
    fun `pair with an HTTP error does not persist anything`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401).setBody("bad code"))

        val result = transport.pair(baseUrl(), "wrong-code")

        assertTrue(result is TransportResult.Failure)
        assertNull(store.pairedDevice.first())
    }

    @Test
    fun `pair with an unparseable response body fails cleanly instead of crashing`() = runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody("not json"))

        val result = transport.pair(baseUrl(), "123456")

        assertTrue(result is TransportResult.Failure)
        assertNull(store.pairedDevice.first())
    }

    // --- checkConnection() ------------------------------------------------

    @Test
    fun `checkConnection before pairing fails without making a network call`() = runTest {
        val result = transport.checkConnection()
        assertTrue(result is TransportResult.Failure)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `checkConnection success and failure`() = runTest {
        pairSuccessfully()

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"updated":true}"""))
        server.enqueue(MockResponse().setResponseCode(200))
        assertTrue(transport.checkConnection() is TransportResult.Success)

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"updated":true}"""))
        server.enqueue(MockResponse().setResponseCode(503))
        assertTrue(transport.checkConnection() is TransportResult.Failure)
    }

    @Test
    fun `connect heartbeat and capability requests use the documented signature`() = runTest {
        pairSuccessfully()
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"updated":true}"""))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"device_id":"dev-1","connection_state":"online","pending_tasks":[]}"""))
        assertTrue(transport.checkConnection() is TransportResult.Success)

        server.takeRequest() // pairing redemption is intentionally unsigned
        val capabilityRequest = server.takeRequest()
        val heartbeatRequest = server.takeRequest()
        assertSignatureValid(capabilityRequest)
        assertSignatureValid(heartbeatRequest)
        assertEquals("PUT", capabilityRequest.method)
        assertEquals("POST", heartbeatRequest.method)
    }

    @Test
    fun `acknowledging a routed task signs the canonical request`() = runTest {
        pairSuccessfully()
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"task_id":"task-1","origin":"desktop","target_device_id":"dev-1","action":"notify","payload":{},"status":"started","created_at":"2026-10-22T00:00:00","updated_at":"2026-10-22T00:00:01"}"""
        ))

        val result = transport.acknowledgeConnectTask("task-1")

        assertTrue(result is TransportResult.Success)
        val pairRequest = server.takeRequest()
        assertNull(pairRequest.getHeader("X-SAM-Signature"))
        val ackRequest = server.takeRequest()
        assertEquals("/api/connect/tasks/task-1/ack", ackRequest.path)
        assertSignatureValid(ackRequest)
    }

    // --- sendTask() / getTask() / cancelTask() -----------------------------

    @Test
    fun `sendTask happy path returns the created snapshot`() = runTest {
        pairSuccessfully()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"task_id":"t-1","instruction":"open chrome","input_type":"text","status":"queued"}""",
            ),
        )

        val result = transport.sendTask(TaskRequest(instruction = "open chrome"))

        assertTrue(result is TransportResult.Success)
        assertEquals(TaskStatus.QUEUED, (result as TransportResult.Success).value.status)
    }

    @Test
    fun `sendTask HTTP error is reported as Failure`() = runTest {
        pairSuccessfully()
        server.enqueue(MockResponse().setResponseCode(500))

        assertTrue(transport.sendTask(TaskRequest(instruction = "open chrome")) is TransportResult.Failure)
    }

    @Test
    fun `getTask returns the current snapshot`() = runTest {
        pairSuccessfully()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"task_id":"t-1","instruction":"open chrome","input_type":"text","status":"completed","result_text":"Done"}""",
            ),
        )

        val result = transport.getTask("t-1")

        assertTrue(result is TransportResult.Success)
        assertEquals(TaskStatus.COMPLETED, (result as TransportResult.Success).value.status)
        assertEquals("Done", result.value.resultText)
    }

    @Test
    fun `cancelTask happy path and HTTP error`() = runTest {
        pairSuccessfully()

        server.enqueue(MockResponse().setResponseCode(200))
        assertTrue(transport.cancelTask("t-1") is TransportResult.Success)

        server.enqueue(MockResponse().setResponseCode(404))
        assertTrue(transport.cancelTask("t-1") is TransportResult.Failure)
    }

    // --- taskEvents() (SSE) ---------------------------------------------------

    @Test
    fun `taskEvents emits parsed events and completes when the server ends the stream`() = runTest {
        pairSuccessfully()
        // Framing per interfaces/api/server.py's _format_sse(): "id: <seq>" then
        // "data: <json>", with ": heartbeat" comment lines during idle gaps —
        // those must be ignored, not surfaced as events. "seq" is an extra field
        // the app's TaskEvent model doesn't declare (ignoreUnknownKeys covers it).
        val body = "id: 1\n" +
            """data: {"type":"execution.step","task_id":"t-1","seq":1,"phase":"planning","message":"Planning","timestamp":"2026-01-01T00:00:00"}""" + "\n\n" +
            ": heartbeat\n\n" +
            "id: 2\n" +
            """data: {"type":"execution.step","task_id":"t-1","seq":2,"phase":"completed","message":"Done","timestamp":"2026-01-01T00:00:01"}""" + "\n\n"
        server.enqueue(
            MockResponse().setResponseCode(200)
                .setHeader("Content-Type", "text/event-stream")
                .setBody(body),
        )

        val events = transport.taskEvents("t-1").toList()

        assertEquals(listOf("planning", "completed"), events.map { it.phase })
        assertEquals("Done", events.last().message)
    }

    @Test
    fun `the SSE client has a finite read timeout`() {
        // An infinite (0) read timeout would let a half-open connection hold the
        // foreground service open until TaskMonitor's cap. This pins the setting;
        // it does not (cannot, here) exercise a real stalled connection.
        val millis = transport.sseClient.readTimeoutMillis
        assertTrue("SSE read timeout must be finite", millis > 0)
        assertEquals(HttpSseSamTransport.SSE_READ_TIMEOUT_SECONDS * 1_000, millis.toLong())
    }

    // --- taskEvents(): resuming a dropped stream ------------------------------
    //
    // The wire shapes below follow what the repo's own route returned when run
    // offline on 2026-10-18 (FastAPI TestClient against interfaces/api/server.py):
    // "id: <seq>\ndata: {json}\n\n"; Last-Event-ID: 2 on a three-event task replied
    // with event 3 only. Ids and timestamps are shortened. This file's tests still
    // have not been executed by JUnit here; the server side of that exchange was.

    @Test
    fun `taskEvents sends no Last-Event-ID header on a first connection`() = runTest {
        pairSuccessfully()
        server.takeRequest() // the pairing call made by pairSuccessfully()
        server.enqueue(sseResponse(sseEvent(seq = 1, phase = "completed")))

        transport.taskEvents("t-1").toList()

        val recorded = server.takeRequest()
        assertEquals("/api/iqoo/tasks/t-1/events", recorded.path)
        assertNull(recorded.getHeader("Last-Event-ID"))
    }

    @Test
    fun `taskEvents resumes with the Last-Event-ID header when given afterSeq`() = runTest {
        pairSuccessfully()
        server.takeRequest() // the pairing call
        server.enqueue(sseResponse(sseEvent(seq = 3, phase = "completed"))) // what the server sends after Last-Event-ID: 2

        val events = transport.taskEvents("t-1", afterSeq = 2).toList()

        assertEquals("2", server.takeRequest().getHeader("Last-Event-ID"))
        assertEquals(listOf<Long?>(3), events.map { it.seq })
    }

    @Test
    fun `taskEvents takes seq from the SSE id line and leaves it null when an event has none`() = runTest {
        pairSuccessfully()
        // The first event has no id: line, so nothing could have been carried over
        // from an earlier one; the second has id: 7. Both JSON bodies say "seq":99
        // on purpose — the id: line is the source, the body is not read for it.
        val body = """data: {"type": "execution.step", "task_id": "t-1", "seq": 99, "phase": "planning", "message": "Planning"}""" + "\n\n" +
            "id: 7\n" +
            """data: {"type": "execution.step", "task_id": "t-1", "seq": 99, "phase": "completed", "message": "Done"}""" + "\n\n"
        server.enqueue(sseResponse(body))

        val events = transport.taskEvents("t-1").toList()

        assertEquals(listOf<Long?>(null, 7), events.map { it.seq })
    }

    // --- getTask(): a response the app cannot decode ------------------------------

    @Test
    fun `getTask with a body that is not valid JSON fails cleanly instead of throwing`() = runTest {
        pairSuccessfully()
        server.enqueue(MockResponse().setResponseCode(200).setBody("not json"))

        val result = transport.getTask("t-1")

        assertTrue(result is TransportResult.Failure)
        assertTrue((result as TransportResult.Failure).message.contains("Unexpected response"))
    }

    @Test
    fun `getTask with a status the app does not list fails cleanly instead of throwing`() = runTest {
        pairSuccessfully()
        // "testing" is accepted by the repo's task store (interfaces/api/task_store.py,
        // ALL_STATUSES) but is not a TaskStatus value.
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"task_id":"t-1","instruction":"open chrome","input_type":"text","status":"testing"}""",
            ),
        )

        assertTrue(transport.getTask("t-1") is TransportResult.Failure)
    }

    // --- unpair() -----------------------------------------------------------

    @Test
    fun `unpair clears the store and resets connectionState to Disconnected`() = runTest {
        pairSuccessfully()

        transport.unpair()

        assertNull(store.pairedDevice.first())
        assertEquals(ConnectionState.Disconnected, transport.connectionState.first())
        // And the transport must actually forget the base URL, not just the
        // store — otherwise a stale call could still hit the old server.
        val result = transport.checkConnection()
        assertTrue(result is TransportResult.Failure)
        assertFalse((result as TransportResult.Failure).message.contains("HTTP"))
    }

    private fun sseResponse(body: String) = MockResponse().setResponseCode(200)
        .setHeader("Content-Type", "text/event-stream")
        .setBody(body)

    /** One event framed the way interfaces/api/server.py's _format_sse() frames it. */
    private fun sseEvent(seq: Int, phase: String) =
        "id: $seq\n" +
            """data: {"type": "execution.step", "task_id": "t-1", "seq": $seq, "phase": "$phase", "message": "$phase step", "timestamp": "2026-10-18T07:37:47.433928"}""" +
            "\n\n"

    private suspend fun pairSuccessfully() {
        server.enqueue(
            MockResponse().setResponseCode(200)
                .setBody("""{"device_id":"dev-1","status":"trusted"}"""),
        )
        val result = transport.pair(baseUrl(), "123456")
        check(result is TransportResult.Success) { "test setup: pairing was expected to succeed" }
    }

    private fun assertSignatureValid(request: okhttp3.mockwebserver.RecordedRequest) {
        val timestamp = request.getHeader("X-SAM-Timestamp")!!
        val nonce = request.getHeader("X-SAM-Nonce")!!
        val signature = Base64.getDecoder().decode(request.getHeader("X-SAM-Signature")!!)
        val bodyHash = MessageDigest.getInstance("SHA-256").digest(request.body.readByteArray())
            .joinToString("") { "%02x".format(it) }
        val canonical = "${request.method}\n${request.requestUrl!!.encodedPath}\n$timestamp\n$nonce\n$bodyHash"
        val verifier = Signature.getInstance("Ed25519", ConnectIdentityCrypto.provider())
        verifier.initVerify(identity.keyPair.public)
        verifier.update(canonical.toByteArray(StandardCharsets.UTF_8))
        assertTrue(verifier.verify(signature))
        assertEquals("dev-1", request.getHeader("X-SAM-Device-Id"))
    }
}
