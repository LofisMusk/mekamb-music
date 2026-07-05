package pl.mekamb.music.desktop

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import pl.mekamb.music.desktop.updater.SemVer

class SemVerTest {

    @Test
    fun `parses plain version`() {
        assertEquals(SemVer(1, 2, 3), SemVer.parse("1.2.3"))
    }

    @Test
    fun `parses v-prefixed version`() {
        assertEquals(SemVer(1, 2, 3), SemVer.parse("v1.2.3"))
        assertEquals(SemVer(0, 10, 0), SemVer.parse("V0.10.0"))
    }

    @Test
    fun `parses pre-release version`() {
        assertEquals(SemVer(1, 2, 3, "beta.1"), SemVer.parse("1.2.3-beta.1"))
        assertEquals(SemVer(2, 0, 0, "rc"), SemVer.parse("v2.0.0-rc"))
    }

    @Test
    fun `returns null on garbage`() {
        assertNull(SemVer.parse(""))
        assertNull(SemVer.parse("garbage"))
        assertNull(SemVer.parse("1.2"))
        assertNull(SemVer.parse("1.2.3.4"))
        assertNull(SemVer.parse("android-7"))
        assertNull(SemVer.parse("ios-1.0-8f34735"))
        assertNull(SemVer.parse("v1.2.x"))
        assertNull(SemVer.parse("99999999999999999999.0.0"))
    }

    @Test
    fun `orders by major minor patch`() {
        assertTrue(SemVer.parse("1.0.0")!! < SemVer.parse("2.0.0")!!)
        assertTrue(SemVer.parse("1.1.0")!! < SemVer.parse("1.2.0")!!)
        assertTrue(SemVer.parse("1.1.1")!! < SemVer.parse("1.1.2")!!)
        assertTrue(SemVer.parse("1.10.0")!! > SemVer.parse("1.9.9")!!)
    }

    @Test
    fun `pre-release sorts below its release`() {
        assertTrue(SemVer.parse("1.0.0-rc")!! < SemVer.parse("1.0.0")!!)
        assertTrue(SemVer.parse("1.0.0")!! > SemVer.parse("1.0.0-beta.9")!!)
        // ...but above any lower release
        assertTrue(SemVer.parse("1.0.1-alpha")!! > SemVer.parse("1.0.0")!!)
    }

    @Test
    fun `numeric pre-release identifiers compare numerically`() {
        assertTrue(SemVer.parse("1.0.0-beta.2")!! < SemVer.parse("1.0.0-beta.10")!!)
        assertTrue(SemVer.parse("1.0.0-alpha.1")!! < SemVer.parse("1.0.0-alpha.1.1")!!)
        // numeric identifiers sort below alphanumeric ones
        assertTrue(SemVer.parse("1.0.0-1")!! < SemVer.parse("1.0.0-alpha")!!)
        assertTrue(SemVer.parse("1.0.0-alpha")!! < SemVer.parse("1.0.0-beta")!!)
    }

    @Test
    fun `equal versions compare equal`() {
        assertEquals(0, SemVer.parse("v1.2.3")!!.compareTo(SemVer.parse("1.2.3")!!))
        assertEquals(0, SemVer.parse("1.2.3-rc.1")!!.compareTo(SemVer.parse("v1.2.3-rc.1")!!))
    }
}
