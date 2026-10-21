package app.reelvault.core

import java.net.URI

/**
 * URL extraction and normalization. Mirrors reelvault/urlnorm.py on the PC so both sides
 * compute the same dedup key. The original shared text/URL is always preserved separately.
 */
object UrlNormalizer {
    private val urlRegex = Regex("""https?://[^\s<>"']+""", RegexOption.IGNORE_CASE)
    private val trackingParams = setOf(
        "igsh", "igshid", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "si", "feature", "ref", "ref_src", "s", "t",
    )
    private val instagramHosts = setOf("instagram.com", "m.instagram.com", "instagr.am")
    private val instagramPath = Regex("""^/(?:[A-Za-z0-9_.]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)/?""")

    /** First http(s) URL inside arbitrary shared text, or null. */
    fun extractUrl(text: String?): String? {
        if (text.isNullOrBlank()) return null
        val m = urlRegex.find(text) ?: return null
        return m.value.trimEnd('.', ',', ';', ':', ')', '!', '?')
    }

    fun isSafeUrl(url: String): Boolean {
        if (url.length > 2048) return false
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        val scheme = uri.scheme?.lowercase() ?: return false
        return (scheme == "http" || scheme == "https") && !uri.host.isNullOrBlank()
    }

    fun normalize(raw: String): String {
        val url = raw.trim()
        val uri = runCatching { URI(url) }.getOrNull() ?: return url
        var host = (uri.host ?: "").lowercase()
        if (host.startsWith("www.")) host = host.removePrefix("www.")
        var path = uri.rawPath.ifEmpty { "/" }
        val query = parseQuery(uri.rawQuery).filter { it.first.lowercase() !in trackingParams }
        if (host in instagramHosts) {
            instagramPath.find(path)?.let { m ->
                val kind = if (m.groupValues[1] == "reels") "reel" else m.groupValues[1]
                return "https://instagram.com/$kind/${m.groupValues[2]}"
            }
        }
        if (host == "youtube.com" || host == "m.youtube.com") {
            val q = query.toMap()
            if (path == "/watch" && q["v"] != null) return "https://youtube.com/watch?v=${q["v"]}"
            Regex("""^/shorts/([A-Za-z0-9_-]+)""").find(path)?.let { return "https://youtube.com/shorts/${it.groupValues[1]}" }
        }
        if (host == "youtu.be") return "https://youtube.com/watch?v=${path.trim('/')}"
        if (path != "/" && path.endsWith("/")) path = path.trimEnd('/')
        val scheme = if (uri.scheme.lowercase() == "http") "https" else uri.scheme.lowercase()
        val port = if (uri.port != -1 && uri.port != 80 && uri.port != 443) ":${uri.port}" else ""
        val qs = query.sortedWith(compareBy({ it.first }, { it.second })).joinToString("&") { (k, v) -> encode(k) + "=" + encode(v) }
        return "$scheme://$host$port$path" + if (qs.isNotEmpty()) "?$qs" else ""
    }

    private fun parseQuery(raw: String?): List<Pair<String, String>> {
        if (raw.isNullOrEmpty()) return emptyList()
        return raw.split('&').filter { it.isNotEmpty() }.map { part ->
            val idx = part.indexOf('=')
            if (idx < 0) decode(part) to "" else decode(part.substring(0, idx)) to decode(part.substring(idx + 1))
        }
    }

    private fun decode(s: String) = runCatching { java.net.URLDecoder.decode(s, "UTF-8") }.getOrDefault(s)
    private fun encode(s: String) = java.net.URLEncoder.encode(s, "UTF-8")
}
