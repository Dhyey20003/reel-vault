package app.reelvault.core

import org.json.JSONArray
import org.json.JSONObject

/** Wire format shared with the PC sync API (reelvault/api/sync.py). */
data class CaptureDto(val captureId: String, val sharedText: String, val url: String?, val capturedAtIso: String)

data class CaptureResult(val captureId: String, val result: String, val ideaId: String?, val error: String?) {
    val accepted: Boolean get() = result == "created" || result == "duplicate"
}

object SyncProtocol {
    const val TOKEN_HEADER = "X-ReelVault-Token"
    const val CAPTURES_PATH = "/api/sync/captures"
    const val PING_PATH = "/api/sync/ping"

    fun batchJson(deviceId: String, deviceName: String, captures: List<CaptureDto>): String {
        val arr = JSONArray()
        for (c in captures) {
            arr.put(JSONObject().apply {
                put("capture_id", c.captureId)
                put("shared_text", c.sharedText)
                if (c.url != null) put("url", c.url) else put("url", JSONObject.NULL)
                put("captured_at", c.capturedAtIso)
            })
        }
        return JSONObject().apply {
            put("device_id", deviceId)
            put("device_name", deviceName)
            put("captures", arr)
        }.toString()
    }

    fun parseResults(body: String): List<CaptureResult> {
        val root = JSONObject(body)
        val arr = root.optJSONArray("results") ?: return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            CaptureResult(
                captureId = o.optString("capture_id"),
                result = o.optString("result"),
                ideaId = o.optString("idea_id").takeIf { it.isNotEmpty() && !o.isNull("idea_id") },
                error = o.optString("error").takeIf { it.isNotEmpty() },
            )
        }
    }
}
