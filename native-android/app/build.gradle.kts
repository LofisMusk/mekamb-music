plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

kotlin {
    jvmToolchain(21)
}

android {
    namespace = "pl.mekamb.music"

    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "pl.mekamb.music"
        minSdk = 26
        targetSdk = 36
        versionCode = 5
        versionName = "2.0.0"
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    // Jetpack Compose, pinned via the BOM so individual artifact versions stay mutually
    // compatible. 2026.06.00 is the latest stable BOM at the time this was written.
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.runtime:runtime")
    implementation("androidx.compose.material3:material3")
    // Shuffle/repeat/logout/cloud-download/etc. live outside the small default icon set.
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Compose glue: Activity entry point, single-Activity navigation, and viewModel()/collectAsState.
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.navigation:navigation-compose:2.9.8")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")

    // Compose needs a coroutine dispatcher for LaunchedEffect/rememberCoroutineScope; the app's
    // networking otherwise stays plain HttpURLConnection wrapped in withContext(Dispatchers.IO).
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")

    // Coil for artwork loading/caching in Compose instead of the old hand-rolled LruCache+disk
    // cache in MainActivity.kt. coil-network-okhttp supplies the HTTP engine Coil needs.
    implementation("io.coil-kt.coil3:coil-compose:3.5.0")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.5.0")
}
