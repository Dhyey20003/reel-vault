package app.reelvault.core

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ProtocolTest {
    @Test
    fun pairingUriParses() {
        val p = PairingUri.parse("reelvault://pair?host=192.168.1.20&port=8765&token=abc%2Fdef")!!
        assertEquals("192.168.1.20", p.host); assertEquals(8765, p.port); assertEquals("abc/def", p.token)
        assertEquals("http://192.168.1.20:8765", p.baseUrl)
        assertNull(PairingUri.parse("https://example.com"))
        assertNull(PairingUri.parse("reelvault://pair?host=&port=1&token=x"))
        assertNull(PairingUri.parse("reelvault://pair?host=h&port=99999&token=x"))
    }

    @Test
    fun backoffGrowsAndCaps() {
        assertEquals(30_000L, Backoff.delayMs(0))
        assertEquals(60_000L, Backoff.delayMs(1))
        assertEquals(240_000L, Backoff.delayMs(3))
        assertEquals(Backoff.MAX_MS, Backoff.delayMs(10))
        assertEquals(Backoff.MAX_MS, Backoff.delayMs(40))
    }

    @Test
    fun batchJsonMatchesPcSchema() {
        val json = SyncProtocol.batchJson("dev1", "Pixel", listOf(CaptureDto("c1", "hello https://x.y/z", "https://x.y/z", "2026-01-01T00:00:00Z")))
        val o = JSONObject(json)
        assertEquals("dev1", o.getString("device_id"))
        val c = o.getJSONArray("captures").getJSONObject(0)
        assertEquals("c1", c.getString("capture_id"))
        assertEquals("https://x.y/z", c.getString("url"))
        assertEquals("2026-01-01T00:00:00Z", c.getString("captured_at"))
    }

    @Test
    fun resultsParse() {
        val r = SyncProtocol.parseResults("""{"ok":true,"results":[{"capture_id":"a","result":"created","idea_id":"i1"},{"capture_id":"b","result":"invalid","error":"no url"}]}""")
        assertEquals(2, r.size)
        assertTrue(r[0].accepted); assertEquals("i1", r[0].ideaId)
        assertEquals("invalid", r[1].result); assertEquals("no url", r[1].error); assertNull(r[1].ideaId)
    }

    @Test
    fun shareParserKeepsOriginalText() {
        val p = ShareParser.parse("Look https://www.instagram.com/reel/AbC/?igsh=1", "Reel")!!
        assertEquals("https://www.instagram.com/reel/AbC/?igsh=1", p.url)
        assertEquals("https://instagram.com/reel/AbC", p.normalizedUrl)
        assertTrue(p.sharedText.startsWith("Reel\nLook"))
        val noUrl = ShareParser.parse("just text")!!
        assertNull(noUrl.url); assertEquals("just text", noUrl.sharedText)
        assertNull(ShareParser.parse("  ", null))
    }
}
