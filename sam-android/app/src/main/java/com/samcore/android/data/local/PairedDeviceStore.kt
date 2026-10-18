package com.samcore.android.data.local

import com.samcore.android.data.transport.DeviceInfo
import kotlinx.coroutines.flow.Flow

/**
 * Extracted from DevicePrefsStore so HttpSseSamTransport depends on this
 * interface rather than the concrete DataStore-backed class — the seam that
 * lets HttpSseSamTransportTest use an in-memory fake instead of needing a
 * real Android Context. DevicePrefsStore (the real, DataStore-backed
 * implementation) is unchanged in behavior; this is a pure extraction.
 */
interface PairedDeviceStore {
    val pairedDevice: Flow<PairedDevice?>
    suspend fun save(baseUrl: String, device: DeviceInfo)
    suspend fun clear()
}

data class PairedDevice(val baseUrl: String, val device: DeviceInfo)
