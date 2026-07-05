plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.compose.multiplatform)
}

kotlin {
    jvmToolchain(21)
}

val appVersion: String = (project.findProperty("appVersion") as String?) ?: "1.0.0-dev"

val generateBuildInfo by tasks.registering {
    val outputDir = layout.buildDirectory.dir("generated/buildinfo/kotlin")
    inputs.property("appVersion", appVersion)
    outputs.dir(outputDir)
    doLast {
        val target = outputDir.get().file("pl/mekamb/music/desktop/BuildInfo.kt").asFile
        target.parentFile.mkdirs()
        target.writeText(
            """
            package pl.mekamb.music.desktop

            object BuildInfo {
                const val APP_VERSION: String = "$appVersion"
                const val GITHUB_REPO: String = "LofisMusk/mekamb-music"
                const val APP_NAME: String = "Mekamb Music"
            }
            """.trimIndent() + "\n"
        )
    }
}

kotlin.sourceSets["main"].kotlin.srcDir(layout.buildDirectory.dir("generated/buildinfo/kotlin"))

tasks.named("compileKotlin") {
    dependsOn(generateBuildInfo)
}

dependencies {
    api(compose.desktop.currentOs)
    api(compose.material3)
    api(compose.materialIconsExtended)
    api(libs.kotlinx.coroutines.core)
    api(libs.kotlinx.coroutines.swing)
    api(libs.kotlinx.serialization.json)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.cio)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.ktor3)
    implementation(libs.javacv) {
        exclude(group = "org.bytedeco")
    }
    implementation(libs.javacpp)
    implementation(libs.ffmpeg)

    testImplementation(libs.kotlin.test)
    // ffmpeg natives for the build host so :shared tests can exercise the audio engine.
    // Packaged apps get their natives from the per-OS runtimeOnly deps in each platform module.
    val hostClassifier = run {
        val osName = System.getProperty("os.name").lowercase()
        val arch = System.getProperty("os.arch").lowercase()
        when {
            osName.contains("mac") && arch.contains("aarch64") -> "macosx-arm64"
            osName.contains("mac") -> "macosx-x86_64"
            osName.contains("win") -> "windows-x86_64"
            else -> "linux-x86_64"
        }
    }
    testRuntimeOnly("org.bytedeco:javacpp:${libs.versions.javacpp.get()}:$hostClassifier")
    testRuntimeOnly("org.bytedeco:ffmpeg:${libs.versions.ffmpeg.get()}:$hostClassifier")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
