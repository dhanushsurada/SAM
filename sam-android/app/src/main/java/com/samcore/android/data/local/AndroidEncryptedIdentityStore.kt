package com.samcore.android.data.local

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.samcore.android.data.transport.ConnectIdentityCrypto
import com.samcore.android.data.transport.DeviceIdentity
import com.samcore.android.data.transport.DeviceIdentityStore
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores only the encrypted Ed25519 private key in app preferences. The AES
 * wrapping key lives in Android Keystore. Public key and device UUID are not
 * secret, but are kept beside the ciphertext to preserve a stable identity.
 */
class AndroidEncryptedIdentityStore(context: Context) : DeviceIdentityStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        "sam_connect_identity", Context.MODE_PRIVATE
    )

    @Synchronized
    override fun loadOrCreate(): DeviceIdentity {
        val id = preferences.getString(KEY_DEVICE_ID, null)
        val public = preferences.getString(KEY_PUBLIC_KEY, null)
        val encrypted = preferences.getString(KEY_PRIVATE_KEY, null)
        val iv = preferences.getString(KEY_IV, null)
        if (id != null || public != null || encrypted != null || iv != null) {
            if (id == null || public == null || encrypted == null || iv == null) {
                error("Stored SAM device identity is incomplete; preserve app data and re-pair from the desktop.")
            }
            val privateBytes = decrypt(Base64.getDecoder().decode(encrypted), Base64.getDecoder().decode(iv))
            return DeviceIdentity(
                id,
                java.security.KeyPair(
                    ConnectIdentityCrypto.publicKeyFromX509(Base64.getDecoder().decode(public)),
                    ConnectIdentityCrypto.privateKeyFromPkcs8(privateBytes),
                ),
            )
        }

        val identity = ConnectIdentityCrypto.generate()
        val encryptedPrivate = encrypt(identity.keyPair.private.encoded)
        val saved = preferences.edit()
            .putString(KEY_DEVICE_ID, identity.deviceId)
            .putString(KEY_PUBLIC_KEY, Base64.getEncoder().encodeToString(identity.keyPair.public.encoded))
            .putString(KEY_PRIVATE_KEY, Base64.getEncoder().encodeToString(encryptedPrivate.first))
            .putString(KEY_IV, Base64.getEncoder().encodeToString(encryptedPrivate.second))
            .commit()
        check(saved) { "Could not safely save the SAM device identity." }
        return identity
    }

    private fun wrappingKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(clear: ByteArray): Pair<ByteArray, ByteArray> {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey())
        return cipher.doFinal(clear) to cipher.iv
    }

    private fun decrypt(encrypted: ByteArray, iv: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, wrappingKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(encrypted)
    }

    private companion object {
        const val KEY_ALIAS = "sam_connect_identity_wrapper"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_PUBLIC_KEY = "public_key"
        const val KEY_PRIVATE_KEY = "encrypted_private_key"
        const val KEY_IV = "private_key_iv"
    }
}
