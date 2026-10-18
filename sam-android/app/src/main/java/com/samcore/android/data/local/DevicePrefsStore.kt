package com.samcore.android.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.samcore.android.data.transport.DeviceInfo
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "sam_device_prefs")

/**
 * Persists the paired device locally so the app doesn't re-run onboarding on
 * every launch. Deliberately NOT where any long-lived trust/pairing token
 * lives long-term — that's connect/core/device_registry.py's job on the SAM
 * Core side; this is just "what did we last pair with," mirroring the split
 * device_registry.py itself documents (device/account metadata kept apart
 * from other local state).
 *
 * Implements PairedDeviceStore (data/local/PairedDeviceStore.kt) so callers
 * — specifically HttpSseSamTransport — can be tested against an in-memory
 * fake instead of this real DataStore-backed class.
 */
class DevicePrefsStore(private val context: Context) : PairedDeviceStore {

    private object Keys {
        val BASE_URL = stringPreferencesKey("base_url")
        val DEVICE_ID = stringPreferencesKey("device_id")
        val DEVICE_NAME = stringPreferencesKey("device_name")
    }

    override val pairedDevice: Flow<PairedDevice?> = context.dataStore.data.map { prefs ->
        val baseUrl = prefs[Keys.BASE_URL] ?: return@map null
        val deviceId = prefs[Keys.DEVICE_ID] ?: return@map null
        val deviceName = prefs[Keys.DEVICE_NAME] ?: return@map null
        PairedDevice(baseUrl, DeviceInfo(deviceId = deviceId, deviceName = deviceName))
    }

    override suspend fun save(baseUrl: String, device: DeviceInfo) {
        context.dataStore.edit { prefs ->
            prefs[Keys.BASE_URL] = baseUrl
            prefs[Keys.DEVICE_ID] = device.deviceId
            prefs[Keys.DEVICE_NAME] = device.deviceName
        }
    }

    override suspend fun clear() {
        context.dataStore.edit { it.clear() }
    }
}
