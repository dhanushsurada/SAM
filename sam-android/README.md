# SAM for Android — Mobile Companion Client

**Native Android Client for SAM Core (Kotlin · Jetpack Compose · Android 8.0+ / API 26+)**

> Local pairing · Asymmetric Ed25519 authentication · Scoped Storage file sync · Mobile AI inference · Cross-device task execution

---

## Architecture & Implementation Overview

SAM for Android provides the mobile bridge for the SAM ecosystem, enabling your phone to act as an authenticated remote execution node and companion to SAM Desktop.

### 1. Cryptographic Identity & Pairing
- **Ed25519 Device Keypair:** Generated locally using `bcprov-jdk18on`. The private key is encrypted with a hardware-backed non-exportable AES key in the **Android Keystore**.
- **Canonical Request Signing:** Every HTTP request to SAM Core includes an authenticated signature computed over:
  ```text
  METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(body)
  ```
- **One-Time Pairing:** Redeems token at `/api/connect/pairing/redeem` (scanned from Desktop QR or manual code) and transitions to trusted state.
- **Auto-Revocation Protection:** Application backup is strictly disabled (`android:allowBackup="false"`).

### 2. 10 Routed Task Actions (`AndroidConnectTaskExecutor`)
When SAM Desktop dispatches tasks to Android via the Connect protocol, `AndroidConnectTaskExecutor` handles execution across 10 distinct actions:

| Action | Handler | Mechanism |
|---|---|---|
| `show_notification` | `SamNotifications` | Displays private notification on device via `NotificationManagerCompat` |
| `app_launch` | `AndroidAppLauncher` | Launches application by common name or Android package |
| `view_url` | `AndroidAppLauncher` | Opens web URL in default mobile browser (`Intent.ACTION_VIEW`) |
| `share_content` | `AndroidAppLauncher` | Opens system share sheet for cross-device text/link sharing |
| `get_notifications` | `SamNotificationListener` | Queries active notifications for desktop summarization |
| `accessibility_click` | `SamAccessibilityService` | Performs UI clicks by text or coordinate targeting |
| `accessibility_type` | `SamAccessibilityService` | Types text into focused UI input fields |
| `accessibility_action` | `SamAccessibilityService` | Performs global navigation (Home, Back, Recents) |
| `receive_file` | `SamFileManager` | Writes incoming file to scoped storage with SHA-256 integrity validation |
| `local_infer` | `SamMobileInferenceEngine` | Runs on-device mobile AI inference with latency & token metrics |

### 3. Background Keep-Alive & Bounded Reconnect
- **Foreground Service (`TaskWatchForegroundService`):** Android 14+ compatible `dataSync` service displaying a low-priority ongoing notification during task execution to prevent process termination.
- **Bounded Exponential Backoff (`TaskMonitor`):** When SSE connection drops, automatically retries on an exponential backoff schedule (`1s, 2s, 4s, 8s, 16s`).
- **Event Sequence De-duplication:** Automatically de-duplicates incoming events using `seq` cursors and `Last-Event-ID`.

---

## Testing & CI Verification

The Android module includes **78 automated JVM unit tests** executed in GitHub Actions CI:

```bash
# Run unit test suite
./gradlew testDebugUnitTest --no-daemon

# Build debug APK
./gradlew assembleDebug --no-daemon

# Build production release APK and AAB
./gradlew assembleRelease bundleRelease --no-daemon
```

### Unit Test Breakdown:
- **`AndroidConnectTaskExecutorTest` (19 tests):** Exercises all 10 action dispatches, missing parameter validation, disabled-service failure reporting, transport acknowledgement failures, and SHA-256 disk validation.
- **`SamFileManagerTest` (4 tests):** Exercises un-mocked SHA-256 calculation, disk file writes in isolated temporary folders, corruption rejection, and readback.
- **`HttpSseSamTransportTest` (21 tests):** Tests token redemption, canonical request signing, heartbeat updates, SSE streaming, and error handling against `MockWebServer`.
- **`TaskMonitorTest` (34 tests):** Tests event collecting, terminal-only notification gates, watch cancellations, keep-alive requests, and millisecond-accurate reconnect schedules.

---

## Physical Hardware Execution Status

While code implementation and JVM unit tests pass with 100% success in CI, execution on physical hardware requires connected devices to validate:
- Live OS permission grants (`POST_NOTIFICATIONS`, `BIND_ACCESSIBILITY_SERVICE`, `BIND_NOTIFICATION_LISTENER_SERVICE`).
- OEM-specific battery optimization policies (e.g., vivo FuntouchOS, Samsung OneUI, Xiaomi HyperOS).
- Seamless radio handover between same-network Wi-Fi and cellular via Remote Relay.

---

## Opening in Android Studio

1. Open the `sam-android` directory in **Android Studio Ladybug (2024.2+)** or newer.
2. Ensure **JDK 17** is configured in Project Structure.
3. Sync Gradle and run `./gradlew test`.
4. Deploy to a connected physical device or emulator running API 26 or higher.
