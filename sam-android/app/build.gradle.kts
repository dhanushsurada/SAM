plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "com.samcore.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.samcore.android"
        minSdk = 26 // Android 8.0 — required for adaptive icons + notification channels used below
        targetSdk = 35
        versionCode = 3
        versionName = "2.0.1"
    }

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
                // Secure production enforcement: NEVER fallback to debug signing for release.
                // Builds without keystore environment variables produce unsigned artifacts.
                signingConfig = null
            }
        }
        debug {
            // Debug builds use standard Android SDK debug keystore
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(libs.core.ktx)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.activity.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)
    implementation(libs.compose.material3)
    implementation(libs.navigation.compose)
    implementation(libs.okhttp)
    implementation(libs.okhttp.sse) // verified real coordinate: com.squareup.okhttp3:okhttp-sse, same version line as okhttp
    implementation(libs.datastore.preferences)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.bouncycastle.provider)

    // Test-only — see app/src/test/. Verified coordinates, not run here (no
    // JVM/dependency access in this environment — see the build report).
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
}
