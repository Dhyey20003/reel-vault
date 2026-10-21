package app.reelvault.capture.sync

import app.reelvault.core.CaptureDto
import app.reelvault.core.CaptureResult
import app.reelvault.core.Pairing
import app.reelvault.core.SyncProtocol
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL

/** Minimal HTTP client for the PC's token-gated sync API. No third-party networking library. */
class SyncClient(private val pairing: Pairing, private val connectTimeoutMs: Int = 5000, private val readTimeoutMs: Int = 20000) {

    sealed class Outcome<out T> {
        data class Ok<T>(val value: T) : Outcome<T>()
        /** Transport problem: PC off, wrong WiFi, timeout. Retry later. */
        data class Unreachable(val message: String) : Outcome<Nothing>()
        /** The PC answered but rejected us (bad token = 401, bad request = 4xx). Do not retry blindly. */
        data class Rejected(val code: Int, val message: String) : Outcome<Nothing>()
    }

    fun ping(): Outcome<String> = request("GET", SyncProtocol.PING_PATH, null).let { o ->
        when (o) {
            is Outcome.Ok -> Outcome.Ok(o.value)
            is Outcome.Unreachable -> o
            is Outcome.Rejected -> o
        }
    }

    fun sendCaptures(deviceId: String, deviceName: String, captures: List<CaptureDto>): Outcome<List<CaptureResult>> {
        val body = SyncProtocol.batchJson(deviceId, deviceName, captures)
        return when (val o = request("POST", SyncProtocol.CAPTURES_PATH, body)) {
            is Outcome.Ok -> try { Outcome.Ok(SyncProtocol.parseResults(o.value)) } catch (e: Exception) { Outcome.Rejected(200, "unexpected reply from PC") }
            is Outcome.Unreachable -> o
            is Outcome.Rejected -> o
        }
    }

    private fun request(method: String, path: String, body: String?): Outcome<String> {
        if (!isPrivateHost(pairing.host)) return Outcome.Rejected(0, "Host must be a private LAN address (e.g. 192.168.x.x)")
        val conn = try {
            (URL(pairing.baseUrl + path).openConnection() as HttpURLConnection)
        } catch (e: Exception) {
            return Outcome.Rejected(0, "Invalid host or port")
        }
        try {
            conn.requestMethod = method
            conn.connectTimeout = connectTimeoutMs
            conn.readTimeout = readTimeoutMs
            conn.useCaches = false
            conn.setRequestProperty(SyncProtocol.TOKEN_HEADER, pairing.token)
            conn.setRequestProperty("Accept", "application/json")
            conn.setRequestProperty("User-Agent", "ReelVault-Android/1.0")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            return if (code in 200..299) Outcome.Ok(text) else Outcome.Rejected(code, describe(code, text))
        } catch (e: IOException) {
            return Outcome.Unreachable(e.message ?: e.javaClass.simpleName)
        } finally {
            conn.disconnect()
        }
    }

    private fun describe(code: Int, text: String): String = when (code) {
        401 -> "Pairing token rejected by the PC (401). Re-pair in Settings."
        403 -> "The PC refused this network (403)."
        404 -> "Not a ReelVault server (404). Check host and port."
        else -> "PC replied $code: ${text.take(120)}"
    }

    companion object {
        /** Only private/loopback IPs and local-only hostnames are allowed; nothing on the public internet. */
        fun isPrivateHost(host: String): Boolean {
            val h = host.trim().lowercase()
            if (h.isEmpty()) return false
            if (h == "localhost" || h.endsWith(".local") || h.endsWith(".lan") || h.endsWith(".home")) return true
            return try {
                val addr = InetAddress.getByName(h)
                addr.isSiteLocalAddress || addr.isLoopbackAddress || addr.isLinkLocalAddress || isCgnat(addr.address)
            } catch (e: Exception) {
                false
            }
        }

        private fun isCgnat(b: ByteArray): Boolean = b.size == 4 && (b[0].toInt() and 0xff) == 100 && ((b[1].toInt() and 0xff) in 64..127)
    }
}
