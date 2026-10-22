package com.samcore.android.data.transport

import java.security.KeyPair

data class DeviceIdentity(val deviceId: String, val keyPair: KeyPair)

/** The device owns its Ed25519 private key; it is never sent to SAM Core. */
interface DeviceIdentityStore {
    fun loadOrCreate(): DeviceIdentity
}

/** Used by transport unit tests. Production injects AndroidEncryptedIdentityStore. */
class EphemeralDeviceIdentityStore : DeviceIdentityStore {
    @Volatile private var identity: DeviceIdentity? = null
    override fun loadOrCreate(): DeviceIdentity = identity ?: synchronized(this) {
        identity ?: ConnectIdentityCrypto.generate().also { identity = it }
    }
}
