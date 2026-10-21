package app.reelvault.core

/** Turns whatever Instagram (or any app) shares into a capture: original text kept, URL extracted when possible. */
data class ParsedShare(val sharedText: String, val url: String?, val normalizedUrl: String?)

object ShareParser {
    fun parse(text: String?, subject: String? = null): ParsedShare? {
        val combined = listOfNotNull(subject?.takeIf { it.isNotBlank() }, text?.takeIf { it.isNotBlank() }).joinToString("\n")
        if (combined.isBlank()) return null
        val url = UrlNormalizer.extractUrl(combined)?.takeIf { UrlNormalizer.isSafeUrl(it) }
        return ParsedShare(
            sharedText = combined.take(8000),
            url = url,
            normalizedUrl = url?.let { UrlNormalizer.normalize(it) },
        )
    }
}
