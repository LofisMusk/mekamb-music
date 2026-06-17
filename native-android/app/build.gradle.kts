plugins {
    id("com.android.application")
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
        versionCode = 1
        versionName = "0.1.0"
    }
}
