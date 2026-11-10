# SAM Physical Device Validation & Connectivity Report

**Document ID:** `VAL-PHYSICAL-DEV-001`  
**Date:** 2026-11-10  
**Host Architecture:** Darwin 27.0.1 (macOS Apple Silicon arm64)  
**Execution Command:** `adb devices -l`  
**Execution Result:** `adb command not found` (Exit code 0/127)  
**Status:** `BLOCKED`

---

## 1. Physical Device Connection & Host Toolchain State

In accordance with strict verification rules, **no physical device execution or hardware results are fabricated.**

### Toolchain Audit:
- **`adb` in PATH:** Not present.
- **Standard SDK Location (`~/Library/Android/sdk/platform-tools`):** Not present on this runner.
- **Host Java Runtime (`java -version`):** Returned `The operation couldn’t be completed. Unable to locate a Java Runtime.`
- **Connected Physical Devices:** None detectable from this runner environment.

---

## 2. Concrete Steps to Unblock Physical Hardware Testing

To perform physical device validation with a real Android device (e.g. iQOO 12, Samsung Galaxy S24, Google Pixel 8/9, Xiaomi 14):

### Step 1: Install Required Host Toolchains
On macOS, install Android platform tools and OpenJDK 17 via Homebrew:
```bash
brew install --cask android-platform-tools
brew install openjdk@17
sudo ln -sfn $(brew --prefix openjdk@17)/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk
```

### Step 2: Prepare the Android Device
1. On your Android phone, navigate to **Settings > About Phone**.
2. Tap **Build Number** 7 times to enable **Developer Options**.
3. Go to **Settings > System / Additional Settings > Developer Options**.
4. Enable **USB Debugging** (and **Install via USB** if present).
5. Connect phone to Mac via USB-C cable.
6. Accept the USB debugging RSA key prompt on the phone screen: check *"Always allow from this computer"*.

### Step 3: Verify Device Recognition
```bash
adb devices -l
# Expected output:
# List of devices attached
# 123456789ABCDEF    device usb:337641472X product:iQOO_12 model:I2220 device:PD2307
```

### Step 4: Build and Deploy SAM Android Application
```bash
cd sam-android
chmod +x gradlew
./gradlew assembleDebug

# Install APK to the device
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Launch Main Activity
adb shell am start -n com.samcore.android/.MainActivity

# Stream Logcat filters
adb logcat -s "SamMobileInference:*" "SamAccessibility:*" "SamNotifListener:*" "SamBridge:*" "AndroidAppLauncher:*"
```

---

## 3. Physical Hardware Test Protocols (Tests A – F)

Once unblocked, the following test matrix must be executed and recorded:

| Test ID | Scenario | Procedure | Expected Physical Evidence | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Test A** | Android to Desktop | Issue voice/text command from phone: `"Open Google Chrome on desktop"`. | Chrome window activates on Mac desktop; Task state updates to `completed` on phone. | `BLOCKED` (Waiting for physical device) |
| **Test B** | Desktop to Android | Issue command on Desktop: `"On my phone, open Spotify"`. | Spotify foregrounds on physical Android screen; `AndroidAppLauncher` logs success. | `BLOCKED` (Waiting for physical device) |
| **Test C** | File Transfer | Push test PDF from Mac to Android over LAN. | File lands in `Android/data/com.samcore.android/files/Download/`; SHA-256 matches. | `BLOCKED` (Waiting for physical device) |
| **Test D** | Offline Inference | Disconnect Wi-Fi & Cellular on phone. Run prompt `"Summarize meeting notes"`. | Mobile model (GGUF / LiteRT) produces tokens locally; 0 remote HTTP calls. | `BLOCKED` (Waiting for physical device) |
| **Test E** | Remote Connectivity | Switch phone to Cellular 5G (different subnet). Send cross-device task. | Connects via TLS 1.3 Outbound Relay; signatures verified; task completes. | `BLOCKED` (Waiting for physical device) |
| **Test F** | Disruption Recovery | Terminate Wi-Fi during active 50MB file transfer; reconnect within 60s. | Coordinator lease renewed; transfer resumes or fails gracefully without duplicated tasks. | `BLOCKED` (Waiting for physical device) |

---

## 4. Summary

Physical Android execution is strictly **BLOCKED** on this host runner due to the missing Android SDK and ADB environment. All automated source code fixes (nested comments, logging API coordinates, release signing security) have been verified.
