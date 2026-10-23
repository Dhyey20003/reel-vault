package app.reelvault.capture.data

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import app.reelvault.core.Pairing
import java.util.UUID

/**
 * Settings. The pairing token lives in EncryptedSharedPreferences (Android Keystore backed) and is
 * excluded from backups. It is never logged or shown in full by the UI.
 */
class Prefs(context: Context) {
    private val plain: SharedPreferences = context.getSharedPreferences("reelvault_prefs", Context.MODE_PRIVATE)
    private val secure: SharedPreferences = run {
        val key = MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            context, "reelvault_secure", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var host: String
        get() = plain.getString("host", "") ?: ""
        set(v) = plain.edit().putString("host", v.trim()).apply()

    var port: Int
        get() = plain.getInt("port", 8765)
        set(v) = plain.edit().putInt("port", v).apply()

    var token: String
        get() = secure.getString("token", "") ?: ""
        set(v) = secure.edit().putString("token", v.trim()).apply()

    var autoSync: Boolean
        get() = plain.getBoolean("auto_sync", true)
        set(v) = plain.edit().putBoolean("auto_sync", v).apply()

    var showToast: Boolean
        get() = plain.getBoolean("show_toast", true)
        set(v) = plain.edit().putBoolean("show_toast", v).apply()

    var lastSyncSummary: String
        get() = plain.getString("last_sync", "") ?: ""
        set(v) = plain.edit().putString("last_sync", v).apply()

    var lastSuccessAt: Long
        get() = plain.getLong("last_success_at", 0L)
        set(v) = plain.edit().putLong("last_success_at", v).apply()

    /** Sync even when Android reports the network has no internet (home WiFi without uplink, hotspots). */
    var syncWithoutInternet: Boolean
        get() = plain.getBoolean("sync_without_internet", false)
        set(v) = plain.edit().putBoolean("sync_without_internet", v).apply()

    val deviceId: String
        get() = plain.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            plain.edit().putString("device_id", it).apply()
        }

    var deviceName: String
        get() = plain.getString("device_name", null) ?: "${Build.MANUFACTURER} ${Build.MODEL}".trim()
        set(v) = plain.edit().putString("device_name", v.trim()).apply()

    val isPaired: Boolean get() = host.isNotBlank() && token.isNotBlank()

    fun pairing(): Pairing? = if (isPaired) Pairing(host, port, token) else null

    fun applyPairing(p: Pairing) { host = p.host; port = p.port; token = p.token }
}
