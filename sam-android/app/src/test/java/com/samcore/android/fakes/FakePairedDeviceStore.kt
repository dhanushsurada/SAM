package com.samcore.android.fakes

import com.samcore.android.data.local.PairedDevice
import com.samcore.android.data.local.PairedDeviceStore
import com.samcore.android.data.transport.DeviceInfo
import kotlinx.coroutines.flow.MutableStateFlow

/** In-memory PairedDeviceStore for tests — no Android Context needed. */
class FakePairedDeviceStore(initial: PairedDevice? = null) : PairedDeviceStore {
    private val state = MutableStateFlow(initial)
    override val pairedDevice = state

    override suspend fun save(baseUrl: String, device: DeviceInfo) {
        state.value = PairedDevice(baseUrl, device)
    }

    override suspend fun clear() {
        state.value = null
    }
}
