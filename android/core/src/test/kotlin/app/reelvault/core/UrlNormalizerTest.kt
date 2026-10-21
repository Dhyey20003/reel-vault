package app.reelvault.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class UrlNormalizerTest {
    @Test
    fun instagramVariantsCollapse() {
        val expected = "https://instagram.com/reel/C1a2B3c4D5e"
        assertEquals(expected, UrlNormalizer.normalize("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc123"))
        assertEquals(expected, UrlNormalizer.normalize("https://instagram.com/reels/C1a2B3c4D5e"))
        assertEquals(expected, UrlNormalizer.normalize("http://www.instagram.com/reel/C1a2B3c4D5e/?utm_source=ig_web_copy_link"))
        assertEquals(expected, UrlNormalizer.normalize("https://www.instagram.com/someuser/reel/C1a2B3c4D5e/"))
        assertEquals("https://instagram.com/p/C1a2B3c4D5e", UrlNormalizer.normalize("https://www.instagram.com/p/C1a2B3c4D5e/"))
    }

    @Test
    fun youtubeAndGeneric() {
        assertEquals("https://youtube.com/watch?v=dQw4w9WgXcQ", UrlNormalizer.normalize("https://youtu.be/dQw4w9WgXcQ?si=xyz"))
        assertEquals("https://youtube.com/shorts/abcDEF123", UrlNormalizer.normalize("https://www.youtube.com/shorts/abcDEF123"))
        assertEquals("https://example.com/path?a=1&b=2", UrlNormalizer.normalize("https://Example.com/path/?b=2&a=1&utm_medium=x"))
    }

    @Test
    fun extractFromInstagramShareText() {
        val text = "Check out this reel by @someone https://www.instagram.com/reel/XyZ/?igsh=1 on Instagram."
        assertEquals("https://www.instagram.com/reel/XyZ/?igsh=1", UrlNormalizer.extractUrl(text))
        assertNull(UrlNormalizer.extractUrl("no link"))
        assertNull(UrlNormalizer.extractUrl(null))
    }

    @Test
    fun safety() {
        assertTrue(UrlNormalizer.isSafeUrl("https://instagram.com/reel/abc"))
        assertFalse(UrlNormalizer.isSafeUrl("javascript:alert(1)"))
        assertFalse(UrlNormalizer.isSafeUrl("file:///sdcard/x"))
        assertFalse(UrlNormalizer.isSafeUrl("https://" + "a".repeat(3000)))
    }
}
