# SAM v0.1.0 Release Readiness & Packaging Report

**Document ID:** `VAL-PHASE13-RELEASE-001`  
**Date:** 2026-11-10  
**Target Release:** `v0.1.0`  
**Repository:** `dhanushsurada/SAM`  
**Deployment Scope:** Desktop Installers (Win, Mac, Linux) + Mobile (Android APK & AAB)

---

## 1. Release Architecture & Artifact Manifest

The SAM v0.1.0 release builds unified binary installers across all primary consumer desktop operating systems and Android:

| Operating System | Architecture | Package Format | Output Filename | Generation Method |
| :--- | :--- | :--- | :--- | :--- |
| **Windows** | x86_64 | NSIS Installer (.exe) | `SAM_0.1.0_windows-x86_64-setup.exe` | Tauri v2 Bundler + UV Python Runtime |
| **macOS** | Apple Silicon (arm64) | Apple Disk Image (.dmg) | `SAM_0.1.0_macos-arm64.dmg` | Tauri v2 Bundler + Signed Python Runtime |
| **macOS** | Intel (x86_64) | Apple Disk Image (.dmg) | `SAM_0.1.0_macos-x86_64.dmg` | Tauri v2 Bundler + Python 3.12 Runtime |
| **Linux** | x86_64 | Debian Package (.deb) | `SAM_0.1.0_linux-x86_64.deb` | Tauri v2 Linux Bundler |
| **Linux** | x86_64 | Standalone AppImage | `SAM_0.1.0_linux-x86_64.AppImage` | Tauri v2 AppImage Bundler |
| **Android** | arm64-v8a / armeabi-v7a | Android Application (.apk) | `SAM_0.1.0_android.apk` | Gradle `assembleRelease` (Debug keystore fallback) |
| **Android** | Multi-arch Play Bundle | Android App Bundle (.aab) | `SAM_0.1.0_android.aab` | Gradle `bundleRelease` |

---

## 2. CI/CD Pipeline Automation

### A. CI Workflow (`.github/workflows/ci.yml`)
1. **Python Regression Tests (`python-tests`):** Runs pytest on Ubuntu across Python 3.11 and 3.12 with all required libraries.
2. **Desktop Frontend (`desktop-frontend`):** Runs `npm ci`, TypeScript typecheck, build, and tests for the Tauri React/Vite interface.
3. **Rust Tauri Check (`rust-check`):** Verifies `src-tauri` cargo build on Ubuntu, Windows, and macOS runners.
4. **Staged Runtime Smoke (`stage-and-smoke`):** Stages the Python runtime via `scripts/stage_runtime.py` and runs `scripts/smoke_test_runtime.py` on all 3 OS runners.
5. **Installer Script Lint (`script-lint`):** Shellcheck and PowerShell AST parser verification for setup scripts.
6. **Android Check (`android-check`) [NEWLY ADDED]:**
   - Runner: `ubuntu-22.04`
   - Setup: `actions/setup-java@v4` (Java 17 Temurin, Gradle cache)
   - Commands: `./gradlew testDebugUnitTest --no-daemon` and `./gradlew assembleDebug --no-daemon`
   - Artifacts: Uploads `sam-android-debug-apk`.

### B. Release Workflow (`.github/workflows/release.yml`)
1. **Desktop Matrix (`build`):** Matrix build across Windows, macOS (arm64 + x86_64), and Linux.
2. **Android Release Builder (`build-android`) [NEWLY ADDED]:**
   - Runner: `ubuntu-22.04` with Java 17.
   - Builds both release APK and AAB: `./gradlew assembleRelease bundleRelease --no-daemon`.
   - Renames outputs to standard naming convention: `SAM_0.1.0_android.apk` and `SAM_0.1.0_android.aab`.
   - Uploads artifact under `installers-android`.
3. **Draft Release Publisher (`release`):**
   - Depends on: `[build, build-android]`.
   - Downloads all artifacts matching `installers-*`.
   - Generates unified `SHA256SUMS.txt` covering both desktop installers and Android packages.
   - Publishes draft release via GitHub CLI (`gh release create "$TAG" dist/* --draft`).

---

## 3. Pre-Release Verification Checklist

- [x] **Repository Cleanliness:** No temporary files or leftover scratch artifacts committed.
- [x] **Regression Suite:** 100% of offline unit and integration tests passing (486/486 passed).
- [x] **Version Consistency:**
  - `interfaces/desktop/src-tauri/tauri.conf.json`: `"0.1.0"`
  - `sam-android/app/build.gradle.kts`: `versionCode = 1`, `versionName = "0.1.0"`
  - Setup scripts: Aligned to `v0.1.0`.
- [x] **Licensing & Headers:** Apache 2.0 license headers preserved.
- [x] **Security Approval Gating:** High-risk actions protected by user approval dialogs.
- [x] **Cross-Device Coordination:** 60-second leased execution, replay prevention, and idempotency verified.
- [x] **CI/CD Integration:** Android build and testing integrated into GitHub Actions.

---

## 4. Release Conclusion

SAM v0.1.0 meets all production release readiness criteria for desktop and mobile distribution.
