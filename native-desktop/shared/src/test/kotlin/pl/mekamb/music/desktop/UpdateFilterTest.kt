package pl.mekamb.music.desktop

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import pl.mekamb.music.desktop.api.GhRelease
import pl.mekamb.music.desktop.updater.selectNewerRelease

class UpdateFilterTest {

    private fun release(tag: String, draft: Boolean = false) =
        GhRelease(tagName = tag, draft = draft)

    @Test
    fun `picks the max semver release newer than current`() {
        val releases = listOf(
            release("v1.1.0"),
            release("v1.3.0"),
            release("v1.2.5"),
        )
        assertEquals("v1.3.0", selectNewerRelease(releases, "1.0.0")?.tagName)
    }

    @Test
    fun `drafts are excluded`() {
        val releases = listOf(
            release("v9.9.9", draft = true),
            release("v1.1.0"),
        )
        assertEquals("v1.1.0", selectNewerRelease(releases, "1.0.0")?.tagName)
        assertNull(selectNewerRelease(listOf(release("v2.0.0", draft = true)), "1.0.0"))
    }

    @Test
    fun `mobile tags are ignored`() {
        val releases = listOf(
            release("android-7"),
            release("ios-1.0-8f34735"),
            release("android-99.0.0"),
            release("v1.1.0"),
        )
        assertEquals("v1.1.0", selectNewerRelease(releases, "1.0.0")?.tagName)
        assertNull(selectNewerRelease(listOf(release("android-7"), release("ios-1.0-8f34735")), "1.0.0"))
    }

    @Test
    fun `equal version returns null`() {
        assertNull(selectNewerRelease(listOf(release("v1.2.3")), "1.2.3"))
    }

    @Test
    fun `older versions return null`() {
        val releases = listOf(release("v1.0.0"), release("v1.2.2"))
        assertNull(selectNewerRelease(releases, "1.2.3"))
    }

    @Test
    fun `pre-release tag is offered above older release but not above its own release`() {
        assertEquals(
            "v1.3.0-beta.1",
            selectNewerRelease(listOf(release("v1.3.0-beta.1")), "1.2.0")?.tagName,
        )
        assertNull(selectNewerRelease(listOf(release("v1.3.0-beta.1")), "1.3.0"))
        // full release wins over its own pre-release
        assertEquals(
            "v1.3.0",
            selectNewerRelease(listOf(release("v1.3.0-rc.2"), release("v1.3.0")), "1.2.0")?.tagName,
        )
    }

    @Test
    fun `unparseable current version returns null`() {
        assertNull(selectNewerRelease(listOf(release("v9.9.9")), "not-a-version"))
        assertNull(selectNewerRelease(listOf(release("v9.9.9")), "1.0"))
        assertNull(selectNewerRelease(listOf(release("v9.9.9")), ""))
    }

    @Test
    fun `empty release list returns null`() {
        assertNull(selectNewerRelease(emptyList(), "1.0.0"))
    }
}
