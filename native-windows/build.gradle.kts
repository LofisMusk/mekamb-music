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
val packageVersionString: String = appVersion.substringBefore("-").ifBlank { "1.0.0" }

dependencies {
    implementation(project(":shared"))
    runtimeOnly("org.bytedeco:javacpp:${libs.versions.javacpp.get()}:windows-x86_64")
    runtimeOnly("org.bytedeco:ffmpeg:${libs.versions.ffmpeg.get()}:windows-x86_64")
}

compose.desktop {
    application {
        mainClass = "pl.mekamb.music.desktop.windows.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Msi)
            packageName = "MekambMusic"
            packageVersion = packageVersionString
            description = "Mekamb Music desktop client"
            vendor = "Mekamb"
            modules("jdk.unsupported", "java.naming")

            windows {
                // Stable identity for in-place MSI upgrades — never change this value.
                upgradeUuid = "6f3e2a1d-9c4b-4e8f-b1a7-2d5c8e9f0a3b"
                menu = true
                shortcut = true
                iconFile.set(project.file("icons/app.ico"))
            }
        }
    }
}
