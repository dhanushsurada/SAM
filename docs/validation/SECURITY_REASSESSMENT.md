# SAM Security Reassessment & Cryptographic Threat Audit

**Document ID:** `VAL-SEC-REASSESS-001`  
**Date:** 2026-11-10  
**Scope:** Device Identity, Replay Prevention, Transport Integrity, Android Attack Surface, Approval Gates  
**Status:** `PASS` (Zero Critical / Zero High Vulnerabilities)

---

## 1. Vulnerability Findings by Severity

| ID | Category | Severity | Description & Attack Vector | Mitigation in SAM Codebase | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Cryptographic Material | **HIGH** | Extraction of device private keys from Android storage or backups | Private keys generated on-device with BouncyCastle, stored in EncryptedSharedPreferences; `android:allowBackup="false"` prevents ADB backup extraction. | **RESOLVED** |
| **SEC-02** | Replay Attacks | **MEDIUM** | Attacker capturing valid LAN HTTP task packet and replaying it | Dual protection: 120-second sliding timestamp window (`TIMESTAMP_WINDOW_SECONDS = 120`) + in-memory `NonceCache` rejecting identical `(device_id, nonce)` pairs. | **RESOLVED** |
| **SEC-03** | Command Injection | **CRITICAL** | Injecting shell commands via math router or terminal tool | Math calculator strictly validates character set: `0123456789. +-/*%()^`. Unsanitized strings divert to LLM; shell tools gated by user confirmation. | **RESOLVED** |
| **SEC-04** | Path Traversal | **HIGH** | Arbitrary file upload (`../../etc/shadow` or `.bashrc`) | `SamFileManager.kt` regex-sanitizes filenames with `[^a-zA-Z0-9._-]` and restricts writes strictly to app-specific Scoped Storage. | **RESOLVED** |
| **SEC-05** | Credential Exfiltration | **HIGH** | Leaking desktop API keys or user passwords across device sync | `ScopedContextManager` explicitly marks `MemoryScope.SENSITIVE` as `sync_permitted = False`. Excluded from sync packages. | **RESOLVED** |
| **SEC-06** | Relay Tampering (MitM) | **HIGH** | Malicious relay intercepting and altering task instructions | Blind relay model: Messages are signed with originating device's Ed25519 private key. Relay cannot alter payload without invalidating signature. | **RESOLVED** |
| **SEC-07** | Android Permission Abuse| **MEDIUM** | AccessibilityService reading sensitive password fields | `SamAccessibilityService` never inspects `isPassword` nodes, collects zero credentials, and requires explicit user consent dialogs. | **RESOLVED** |
| **SEC-08** | Insecure Release Signing | **HIGH** | Debug keystore used as fallback for production release APK | Removed debug fallback. Release build requires all 4 `SAM_ANDROID_*` credentials or remains strictly unsigned. | **RESOLVED** |

---

## 2. In-Depth Cryptographic Analysis

### A. Mutual Ed25519 Authentication (`connect/core/crypto.py` & `ConnectIdentityCrypto.kt`)
- **Key Generation:** Android generates an Ed25519 keypair locally using BouncyCastle `KeyPairGenerator.getInstance("Ed25519")`. The private key is PKCS8-encoded and never transmitted across the network.
- **Pairing Entropy:** QR code payload includes a 128-bit cryptographically random token (`PAIRING_TOKEN_TTL_MINUTES = 15`). Token redemption transmits only the SubjectPublicKeyInfo PEM.

### B. Canonical Request Signature Scheme (`connect/transports/lan_http.py`)
Every authenticated LAN HTTP request carries:
```text
X-SAM-Device-Id:  <uuid>
X-SAM-Timestamp:  <epoch_seconds>
X-SAM-Nonce:      <base64_urlsafe_24_bytes>
X-SAM-Signature:  <base64_ed25519_signature>
```
Signed over canonical string:
```text
{METHOD}\n{PATH}\n{TIMESTAMP}\n{NONCE}\n{SHA256_HEX(BODY)}
```
Tested against tampered body bytes, tampered paths, and expired timestamps in `tests/test_connect_offline.py` (100% rejection).

---

## 3. Destructive Action Approval Gating (`connect/core/security_policy.py`)

Actions are classified into three risk tiers:
1. **LOW:** Read-only operations (`calculate`, `screenshot`, `read_document`, `get_notifications`). Auto-approved.
2. **MEDIUM:** Non-destructive state alterations (`app_launch`, `create_document`, benign `terminal`). Single prompt or auto-approved based on configuration.
3. **HIGH:** Potentially irreversible or destructive operations (`delete_file`, `format_drive`, `sudo`, `rm -rf`, `send_payment`, `change_security_settings`). Mandatory user confirmation prompt before dispatch.

---

## 4. Android Exported Component Analysis (`AndroidManifest.xml`)

- `MainActivity`: Exported for launcher intent (`ACTION_MAIN` / `CATEGORY_LAUNCHER`).
- `TaskWatchForegroundService`: `android:exported="false"` (strictly internal).
- `SamAccessibilityService`: Exported with mandatory `android.permission.BIND_ACCESSIBILITY_SERVICE` (system-only bindable).
- `SamNotificationListener`: Exported with mandatory `android.permission.BIND_NOTIFICATION_LISTENER_SERVICE` (system-only bindable).

**Result:** No unauthenticated external application can invoke internal SAM services.
