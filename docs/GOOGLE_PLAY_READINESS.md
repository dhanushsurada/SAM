# Google Play Store Release Readiness & Compliance Guide

## 1. SDK & Target API Compliance
- **compileSdk**: 35 (Android 15)
- **targetSdk**: 35 (Android 15) — exceeds Google Play's minimum target API requirement (API 34+).
- **minSdk**: 26 (Android 8.0 Oreo) — ensures 96%+ device compatibility while supporting notification channels, adaptive icons, and Keystore crypto.

---

## 2. Policy Disclosures & Service Justifications

### A. AccessibilityService (`SamAccessibilityService`)
- **Google Play Policy**: Apps requesting `BIND_ACCESSIBILITY_SERVICE` must have declared, user-facing accessibility utility or assistive automation.
- **Compliance Implementation**:
  - The service is declared in `AndroidManifest.xml` with `android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"`.
  - Configured via `@xml/accessibility_service_config` with `@string/accessibility_service_description`.
  - **Prominent In-App Disclosure**: Displayed in `PermissionsScreen.kt` before user is redirected to Android Accessibility settings.
  - **Purpose**: Strictly executes user-directed on-device automation (e.g. "Click the Submit button", "Type hello into search").
  - **Restrictions**: Does NOT collect keystrokes in password fields, does NOT run without explicit user activation, and cannot be used for remote surveillance.

### B. Foreground Services (`TaskWatchForegroundService`)
- **Google Play Policy**: Android 14+ requires explicit `foregroundServiceType` declarations with valid user benefits.
- **Type Declared**: `dataSync` (`android:foregroundServiceType="dataSync"`).
- **Justification**: Syncs and watches active cross-device tasks over local Wi-Fi while the user is away from the screen.
- **Handling**:
  - Posts persistent user-visible notification via `SamNotifications`.
  - Implements `Service.onTimeout()` for Android 15's 6-hour daily background execution cap.
  - Automatically terminates when task completes or connection is closed.

### C. Notification Listener (`SamNotificationListener`)
- **Policy**: `BIND_NOTIFICATION_LISTENER_SERVICE` is gated behind special access.
- **Use Case**: Enables user to ask SAM "Summarize my phone notifications".
- **Safety**: Only reads notifications from permitted packages upon explicit command; does not store or exfiltrate private messages.

---

## 3. Google Play Data Safety Declaration

| Data Category | Data Collected? | Data Shared? | Purpose | Retention |
|:---|:---|:---|:---|:---|
| **Location** | No | No | N/A | None |
| **Personal Info** | Optional display name only | No | Assistant personalization | Local only (`EncryptedSharedPreferences`) |
| **Messages / Notifications** | Only on user request | No | In-memory summarization | Discarded after summary |
| **Files & Documents** | User-selected files | No | Local Wi-Fi transfer to desktop | Saved to scoped storage |
| **Audio / Voice** | User speech input | No | Transcribed on-device / local Core | None stored |
| **Device / ID** | Generated Ed25519 Public Key | No | Device pairing identity | Revocable on device |

- **Encrypted in Transit**: Yes, all LAN/relay traffic is encrypted and Ed25519-signed.
- **Account Creation Required**: No.
- **Free to Use**: Yes, no mandatory cloud subscription or paywall.

---

## 4. Release Build & Signing Instructions

### A. Generate Android Keystore (Do not commit to Git)
```bash
keytool -genkey -v -keystore sam-release-key.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias sam-release
```

### B. Build Signed Android App Bundle (AAB)
```bash
cd sam-android
./gradlew bundleRelease
```
The output `.aab` file will be generated at:
`sam-android/app/build/outputs/bundle/release/app-release.aab`
