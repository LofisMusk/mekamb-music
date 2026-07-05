package pl.mekamb.music.desktop.updater

import pl.mekamb.music.desktop.api.GhAsset

/** Maps the running platform to the matching release asset naming convention. */
object PlatformAssets {

    const val OS_MACOS_ARM64 = "macos-arm64"
    const val OS_WINDOWS_X64 = "windows-x64"
    const val OS_LINUX_X86_64 = "linux-x86_64"

    fun currentOsKey(): String {
        val osName = System.getProperty("os.name").lowercase()
        return when {
            osName.contains("mac") || osName.contains("darwin") -> OS_MACOS_ARM64
            osName.contains("win") -> OS_WINDOWS_X64
            else -> OS_LINUX_X86_64
        }
    }

    fun pickAsset(
        assets: List<GhAsset>,
        osKey: String = currentOsKey(),
        appImageEnv: Boolean = System.getenv("APPIMAGE") != null,
    ): GhAsset? = when (osKey) {
        OS_MACOS_ARM64 -> assets.find { it.name.endsWith("-macos-arm64.dmg") }
        OS_WINDOWS_X64 -> assets.find { it.name.endsWith("-windows-x64.msi") }
        OS_LINUX_X86_64 -> {
            val appImage = assets.find { it.name.endsWith("-linux-x86_64.AppImage") }
            val deb = assets.find { it.name.endsWith("-linux-amd64.deb") }
            if (appImageEnv) appImage ?: deb else deb ?: appImage
        }
        else -> null
    }
}
