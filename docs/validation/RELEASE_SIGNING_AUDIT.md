# SAM Android Release Signing & Security Audit

**Document ID:** `VAL-REL-SIGN-001`  
**Date:** 2026-11-10  
**Target:** `sam-android/app/build.gradle.kts` & `.github/workflows/release.yml`  
**Security Status:** `PASS (Debug Key Fallback Removed & CI Secret Isolation Implemented)`

---

## 1. Problem Statement & Audit Finding

In earlier configuration drafts, the release build type in `sam-android/app/build.gradle.kts` contained the following hazardous fallback:
```kotlin
buildTypes {
    release {
        isMinifyEnabled = false
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        signingConfig = signingConfigs.getByName("debug") // HAZARDOUS
    }
}
```

### Security Risk of Debug-Signed Release Builds:
1. **Public Key Exposure:** The standard Android debug keystore uses public, well-known keys (`androiddebugkey`, password `android`). Any third party could forge updates to the application.
2. **Google Play Rejection:** Google Play Console unconditionally rejects APKs and AABs signed with standard debug certificates.
3. **Silent Compromise:** Developers or CI systems might assume an artifact is production-ready when it is actually signed with test keys.

---

## 2. Hardened Release Signing Configuration

The release configuration in `sam-android/app/build.gradle.kts` has been permanently remediated:

```kotlin
signingConfigs {
    val keystorePath = System.getenv("SAM_ANDROID_KEYSTORE_PATH")
    if (!keystorePath.isNullOrBlank() && file(keystorePath).exists()) {
        create("release") {
            storeFile = file(keystorePath)
            storePassword = System.getenv("SAM_ANDROID_KEYSTORE_PASSWORD")
            keyAlias = System.getenv("SAM_ANDROID_KEY_ALIAS")
            keyPassword = System.getenv("SAM_ANDROID_KEY_PASSWORD")
        }
    }
}

buildTypes {
    release {
        isMinifyEnabled = false
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        val keystorePath = System.getenv("SAM_ANDROID_KEYSTORE_PATH")
        if (!keystorePath.isNullOrBlank() && file(keystorePath).exists()) {
            signingConfig = signingConfigs.getByName("release")
        } else {
            // Strictly unsigned: NEVER fall back to debug signing for release
            signingConfig = null
        }
    }
    debug {
        // Debug builds use standard Android SDK debug keystore
    }
}
```

### Guarantees Enforced:
1. **Zero Silent Debug Signing:** If release credentials are not provided in the environment, Gradle produces an **unsigned** release artifact (`app-release-unsigned.apk`). It never silently signs a release build with the debug certificate.
2. **Local Isolation:** Local developers executing `./gradlew assembleDebug` continue using the standard debug keystore without needing production secrets.

---

## 3. GitHub Actions CI/CD Integration (`.github/workflows/release.yml`)

The automated release workflow integrates secure release signing credentials via protected GitHub Actions Secrets:

### Required Secrets:
- `SAM_ANDROID_KEYSTORE_BASE64`: Base64-encoded binary content of the production `.jks` or `.keystore` file.
- `SAM_ANDROID_KEYSTORE_PASSWORD`: Keystore master password.
- `SAM_ANDROID_KEY_ALIAS`: Key alias name (e.g. `sam-release`).
- `SAM_ANDROID_KEY_PASSWORD`: Private key password.

### Workflow Safeguards:
1. **Atomic Validation:** If partial secrets are configured (e.g. keystore base64 provided but alias omitted), the workflow halts immediately with an explicit error.
2. **Ephemeral Disk Ingestion:** The decoded keystore is written to `$RUNNER_TEMP/release.keystore` and wiped when the ephemeral GitHub runner terminates.
3. **No Credential Logging:** Secrets are declared under private job-scoped environment variables.

---

## 4. Production Keystore Generation & Signature Verification

### Generating a Production Signing Key:
```bash
keytool -genkeypair -v \
  -keystore sam-release.jks \
  -alias sam-release \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000 \
  -dname "CN=SAM Core, OU=Production, O=SAM, C=US"
```

### Verifying APK Signature Integrity:
```bash
# Verify signing scheme (v1, v2, v3, v4) and certificate details
$ANDROID_HOME/build-tools/35.0.0/apksigner verify \
  --verbose \
  --print-certs \
  dist/SAM_0.1.0_android.apk
```

Expected verification output for release builds:
```text
Verifies
Verified using v1 scheme (JAR signing): true
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): true
Signer #1 certificate DN: CN=SAM Core, OU=Production, O=SAM, C=US
Signer #1 key algorithm: RSA 4096 bits
```
