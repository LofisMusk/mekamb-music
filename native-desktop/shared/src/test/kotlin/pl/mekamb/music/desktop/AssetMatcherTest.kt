package pl.mekamb.music.desktop

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import pl.mekamb.music.desktop.api.GhAsset
import pl.mekamb.music.desktop.updater.PlatformAssets

class AssetMatcherTest {

    private fun asset(name: String) = GhAsset(name = name, browserDownloadUrl = "https://example.com/$name", size = 1)

    private val dmg = asset("MekambMusic-1.2.0-macos-arm64.dmg")
    private val msi = asset("MekambMusic-1.2.0-windows-x64.msi")
    private val appImage = asset("MekambMusic-1.2.0-linux-x86_64.AppImage")
    private val deb = asset("MekambMusic-1.2.0-linux-amd64.deb")
    private val checksums = asset("SHA256SUMS.txt")
    private val allAssets = listOf(checksums, deb, appImage, msi, dmg)

    @Test
    fun `mac picks dmg`() {
        assertEquals(dmg, PlatformAssets.pickAsset(allAssets, osKey = "macos-arm64", appImageEnv = false))
    }

    @Test
    fun `windows picks msi`() {
        assertEquals(msi, PlatformAssets.pickAsset(allAssets, osKey = "windows-x64", appImageEnv = false))
    }

    @Test
    fun `linux without appimage env prefers deb`() {
        assertEquals(deb, PlatformAssets.pickAsset(allAssets, osKey = "linux-x86_64", appImageEnv = false))
    }

    @Test
    fun `linux with appimage env prefers appimage`() {
        assertEquals(appImage, PlatformAssets.pickAsset(allAssets, osKey = "linux-x86_64", appImageEnv = true))
    }

    @Test
    fun `linux falls back to the other asset when preferred missing`() {
        val withoutDeb = allAssets - deb
        val withoutAppImage = allAssets - appImage
        assertEquals(appImage, PlatformAssets.pickAsset(withoutDeb, osKey = "linux-x86_64", appImageEnv = false))
        assertEquals(deb, PlatformAssets.pickAsset(withoutAppImage, osKey = "linux-x86_64", appImageEnv = true))
    }

    @Test
    fun `returns null when no matching asset exists`() {
        assertNull(PlatformAssets.pickAsset(listOf(checksums), osKey = "macos-arm64", appImageEnv = false))
        assertNull(PlatformAssets.pickAsset(listOf(dmg), osKey = "windows-x64", appImageEnv = false))
        assertNull(PlatformAssets.pickAsset(listOf(dmg, msi), osKey = "linux-x86_64", appImageEnv = true))
        assertNull(PlatformAssets.pickAsset(emptyList(), osKey = "linux-x86_64", appImageEnv = false))
    }

    @Test
    fun `unknown os key returns null`() {
        assertNull(PlatformAssets.pickAsset(allAssets, osKey = "solaris-sparc", appImageEnv = false))
    }

    @Test
    fun `current os key is one of the known keys`() {
        val key = PlatformAssets.currentOsKey()
        assertEquals(true, key in setOf("macos-arm64", "windows-x64", "linux-x86_64"))
    }
}
