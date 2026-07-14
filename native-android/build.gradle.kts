plugins {
    id("com.android.application") version "9.2.1" apply false
    // Compose compiler is now a standalone Kotlin plugin (Kotlin 2.0+). AGP 9.x compiles Kotlin
    // through its built-in Kotlin support (no org.jetbrains.kotlin.android plugin needed), and that
    // built-in compiler is Kotlin 2.3.21 for AGP 9.2.x — so the Compose compiler plugin version is
    // pinned to match it exactly (the two must always be the same Kotlin version).
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.21" apply false
}
