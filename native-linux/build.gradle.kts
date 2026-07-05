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
    runtimeOnly("org.bytedeco:javacpp:${libs.versions.javacpp.get()}:linux-x86_64")
    runtimeOnly("org.bytedeco:ffmpeg:${libs.versions.ffmpeg.get()}:linux-x86_64")
}

compose.desktop {
    application {
        mainClass = "pl.mekamb.music.desktop.linux.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Deb)
            packageName = "mekamb-music"
            packageVersion = packageVersionString
            description = "Mekamb Music desktop client"
            vendor = "Mekamb"
            modules("jdk.unsupported", "java.naming")

            linux {
                iconFile.set(project.file("icons/app.png"))
                menuGroup = "Audio"
                shortcut = true
            }
        }
    }
}
