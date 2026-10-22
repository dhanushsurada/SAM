package com.samcore.android.data.transport

import kotlinx.coroutines.flow.Flow

/**
 * The single boundary between SAM Android's UI/ViewModel layer and however it
 * actually talks to SAM Core. Nothing above this interface should import
 * OkHttp, know the base URL, or know the wire format.
 *
 * Why this exists (see the recon report, §5 "Key architectural move"): PDR
 * §16's shared contracts aren't frozen yet, and Agent 3 owns the real
 * protocol. Building the UI against this interface now — with
 * HttpSseSamTransport as a clearly-labeled v0 guess underneath — means a
 * later contract change is a new implementation of this interface, not a
 * rewrite of four screens and their ViewModels.
 */
interface SamTransport {

    /** Hydrate [connectionState] from any persisted pairing before the UI
     *  decides whether to show onboarding or the home screen. Must always
     *  resolve connectionState to either Connected or Disconnected — never
     *  leave it at Connecting. Call once, at app start. */
    suspend fun restore()

    /** Attempt to pair with a SAM Core instance at [baseUrl] using a pairing code
     *  shown on the desktop app (mirrors the existing Telegram bridge's
     *  token → trusted-device flow in connect/core/device_registry.py, adapted
     *  for a directly-entered code instead of a chat command). */
    suspend fun pair(baseUrl: String, pairingCode: String): TransportResult<DeviceInfo>

    /** One-shot reachability/health check against the currently paired device. */
    suspend fun checkConnection(): TransportResult<Unit>

    /** Observed connection state — Disconnected until pair() succeeds, then
     *  reflects ongoing reachability. Collected by the connection-state screen. */
    val connectionState: Flow<ConnectionState>

    suspend fun sendTask(request: TaskRequest): TransportResult<TaskSnapshot>

    suspend fun getTask(taskId: String): TransportResult<TaskSnapshot>

    /** Server-sent execution events for one task. Terminates when the stream
     *  closes (a terminal-phase event, per PROTOCOL.md) or is cancelled by the
     *  collector.
     *
     *  [afterSeq] resumes a dropped stream: when non-null, the stream starts
     *  with the events whose [TaskEvent.seq] is greater than it instead of the
     *  task's full history; null means "from the beginning". The HTTP
     *  implementation sends it as the SSE Last-Event-ID header, which the
     *  repo's server (interfaces/api/server.py) honors — PROTOCOL.md does not
     *  document that, so treat it as provisional. A transport that cannot
     *  resume may ignore it (the collector de-duplicates by seq regardless). */
    fun taskEvents(taskId: String, afterSeq: Long? = null): Flow<TaskEvent>

    suspend fun cancelTask(taskId: String): TransportResult<Unit>

    /** Forget the paired device and return to Disconnected. */
    suspend fun unpair()
}
