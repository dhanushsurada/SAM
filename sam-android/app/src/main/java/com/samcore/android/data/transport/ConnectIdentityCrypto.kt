package com.samcore.android.data.transport

import org.bouncycastle.jce.provider.BouncyCastleProvider
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.SecureRandom
import java.util.Base64
import java.util.UUID

object ConnectIdentityCrypto {
    private val provider = BouncyCastleProvider()
    fun provider() = provider

    fun generate(): DeviceIdentity {
        val generator = KeyPairGenerator.getInstance("Ed25519", provider)
        return DeviceIdentity(UUID.randomUUID().toString(), generator.generateKeyPair())
    }

    fun publicKeyPem(pair: KeyPair): String {
        val encoded = Base64.getMimeEncoder(64, "\n".toByteArray()).encodeToString(pair.public.encoded)
        return "-----BEGIN PUBLIC KEY-----\n$encoded\n-----END PUBLIC KEY-----\n"
    }

    fun privateKeyFromPkcs8(encoded: ByteArray): java.security.PrivateKey {
        return java.security.KeyFactory.getInstance("Ed25519", provider).generatePrivate(
            java.security.spec.PKCS8EncodedKeySpec(encoded)
        )
    }

    fun publicKeyFromX509(encoded: ByteArray): java.security.PublicKey {
        return java.security.KeyFactory.getInstance("Ed25519", provider).generatePublic(
            java.security.spec.X509EncodedKeySpec(encoded)
        )
    }

    fun randomNonce(): String {
        val bytes = ByteArray(24)
        SecureRandom().nextBytes(bytes)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }
}
