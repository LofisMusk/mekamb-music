import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.compose.multiplatform)
}

kotlin {
    jvmToolchain(21)
}

val appVersion: String = (project.findProperty("appVersion") as String?) ?: "1.0.0-dev"
// jpackage on macOS requires a plain x.y.z version with major >= 1.
val packageVersionString: String = appVersion.substringBefore("-").ifBlank { "1.0.0" }.also {
    require(!it.startsWith("0.")) { "macOS package version must have major >= 1, got $it" }
}

dependencies {
    implementation(project(":shared"))
    runtimeOnly("org.bytedeco:javacpp:${libs.versions.javacpp.get()}:macosx-arm64")
    runtimeOnly("org.bytedeco:ffmpeg:${libs.versions.ffmpeg.get()}:macosx-arm64")
}

compose.desktop {
    application {
        mainClass = "pl.mekamb.music.desktop.mac.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Dmg)
            packageName = "MekambMusic"
            packageVersion = packageVersionString
            description = "Mekamb Music desktop client"
            vendor = "Mekamb"
            modules("jdk.unsupported", "java.naming")

            macOS {
                bundleID = "pl.mekamb.music.desktop"
                iconFile.set(project.file("icons/app.icns"))
            }
        }
    }
}
