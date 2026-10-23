package app.reelvault.core

import java.net.URI
import java.net.URLDecoder

/** Parsed form of the QR code shown by the PC: reelvault://pair?host=...&port=...&token=... */
data class Pairing(val host: String, val port: Int, val token: String) {
    val baseUrl: String get() = "http://$host:$port"
}

object PairingUri {
    fun parse(text: String): Pairing? {
        val t = text.trim()
        if (!t.startsWith("reelvault://pair", ignoreCase = true)) return null
        val uri = runCatching { URI(t) }.getOrNull() ?: return null
        val q = (uri.rawQuery ?: "").split('&').mapNotNull { part ->
            val i = part.indexOf('=')
            if (i < 0) null else URLDecoder.decode(part.substring(0, i), "UTF-8") to URLDecoder.decode(part.substring(i + 1), "UTF-8")
        }.toMap()
        val host = q["host"]?.trim().orEmpty()
        val port = q["port"]?.trim()?.toIntOrNull() ?: return null
        val token = q["token"]?.trim().orEmpty()
        if (host.isEmpty() || token.isEmpty() || port !in 1..65535) return null
        return Pairing(host, port, token)
    }

    fun isValidHost(host: String): Boolean =
        host.isNotBlank() && host.length <= 253 && Regex("""^[A-Za-z0-9.\-]+$""").matches(host)
}
