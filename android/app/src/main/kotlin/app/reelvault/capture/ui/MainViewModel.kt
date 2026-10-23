package app.reelvault.capture.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import app.reelvault.capture.ReelVaultApp
import app.reelvault.capture.data.Capture
import app.reelvault.capture.data.CaptureRepository
import app.reelvault.capture.data.SyncState
import app.reelvault.capture.sync.SyncClient
import app.reelvault.capture.sync.SyncScheduler
import app.reelvault.core.Pairing
import app.reelvault.core.PairingUri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class Counts(val synced: Int = 0, val pending: Int = 0, val syncing: Int = 0, val failed: Int = 0)

data class SettingsState(
    val host: String = "", val port: String = "8765", val token: String = "", val autoSync: Boolean = true,
    val showToast: Boolean = true, val deviceName: String = "", val paired: Boolean = false, val syncWithoutInternet: Boolean = false,
)

/** Result of a connection test, with an actionable explanation. */
data class ConnectionState(val ok: Boolean? = null, val message: String = "", val hint: String = "")

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val rv = app as ReelVaultApp
    private val repo = rv.repository
    private val prefs = rv.prefs

    val captures: StateFlow<List<Capture>> = repo.observeAll().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val counts: StateFlow<Counts> = combine(
        repo.observeCount(SyncState.SYNCED), repo.observeCount(SyncState.PENDING), repo.observeCount(SyncState.SYNCING), repo.observeCount(SyncState.FAILED),
    ) { s, p, g, f -> Counts(s, p, g, f) }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), Counts())

    private val _settings = MutableStateFlow(loadSettings())
    val settings: StateFlow<SettingsState> = _settings.asStateFlow()
    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()
    private val _lastSync = MutableStateFlow(prefs.lastSyncSummary)
    val lastSync: StateFlow<String> = _lastSync.asStateFlow()
    private val _lastSuccess = MutableStateFlow(prefs.lastSuccessAt)
    val lastSuccess: StateFlow<Long> = _lastSuccess.asStateFlow()
    private val _connection = MutableStateFlow(ConnectionState())
    val connection: StateFlow<ConnectionState> = _connection.asStateFlow()
    private val _testing = MutableStateFlow(false)
    val testing: StateFlow<Boolean> = _testing.asStateFlow()

    val syncRunning: StateFlow<Boolean> = WorkManager.getInstance(app).getWorkInfosForUniqueWorkFlow(SyncScheduler.ONE_TIME)
        .map { infos -> infos.any { it.state == WorkInfo.State.RUNNING } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    private fun loadSettings() = SettingsState(
        host = prefs.host, port = prefs.port.toString(), token = prefs.token, autoSync = prefs.autoSync, showToast = prefs.showToast,
        deviceName = prefs.deviceName, paired = prefs.isPaired, syncWithoutInternet = prefs.syncWithoutInternet,
    )

    fun refresh() { _lastSync.value = prefs.lastSyncSummary; _lastSuccess.value = prefs.lastSuccessAt }
    fun clearMessage() { _message.value = null }

    fun syncNow() { viewModelScope.launch { repo.makeAllDue(); SyncScheduler.syncNow(getApplication()); _message.value = "Sync requested" } }

    fun retryFailed() {
        viewModelScope.launch {
            val n = repo.retryFailed()
            if (n > 0) SyncScheduler.syncNow(getApplication())
            _message.value = if (n > 0) "$n capture(s) queued again" else "Nothing to retry"
        }
    }

    /** Paste-link fallback: same path as the share target. */
    fun saveLink(text: String) {
        viewModelScope.launch {
            when (val out = repo.save(text, null)) {
                is CaptureRepository.SaveOutcome.Saved -> { SyncScheduler.syncNow(getApplication()); _message.value = "Saved; syncing when the PC is reachable" }
                is CaptureRepository.SaveOutcome.AlreadyQueued -> { SyncScheduler.syncNow(getApplication()); _message.value = "Already saved; will sync again" }
                else -> _message.value = "Paste a link or some text first"
            }
        }
    }

    fun delete(id: String) { viewModelScope.launch { repo.delete(id) } }
    fun updateSettings(transform: SettingsState.() -> SettingsState) { _settings.value = _settings.value.transform() }

    fun saveSettings(retryAfterTokenChange: Boolean = true): Boolean {
        val s = _settings.value
        val port = s.port.trim().toIntOrNull()
        if (!PairingUri.isValidHost(s.host.trim())) { _message.value = "Enter the PC's LAN IP (shown under Settings > Pair your phone on the PC)"; return false }
        if (port == null || port !in 1..65535) { _message.value = "Port must be 1 to 65535"; return false }
        if (!SyncClient.isPrivateHost(s.host.trim())) { _message.value = "Only private LAN addresses are allowed (e.g. 192.168.x.x)"; return false }
        val changed = prefs.host != s.host.trim() || prefs.port != port || prefs.token != s.token.trim()
        prefs.host = s.host.trim(); prefs.port = port; prefs.token = s.token.trim()
        prefs.autoSync = s.autoSync; prefs.showToast = s.showToast; prefs.syncWithoutInternet = s.syncWithoutInternet
        if (s.deviceName.isNotBlank()) prefs.deviceName = s.deviceName
        if (s.autoSync) SyncScheduler.ensurePeriodic(getApplication()) else SyncScheduler.cancelPeriodic(getApplication())
        _settings.value = loadSettings()
        if (changed && retryAfterTokenChange) viewModelScope.launch { repo.retryFailed(); SyncScheduler.syncNow(getApplication()) }
        _message.value = "Settings saved"
        return true
    }

    /** QR flow: parse, fill the fields, validate the connection, then save. Manual entry stays available. */
    fun applyScannedQr(contents: String?) {
        if (contents == null) return  // scan cancelled
        val p = PairingUri.parse(contents)
        if (p == null) { _connection.value = ConnectionState(false, "That QR code is not a ReelVault pairing code.", "On the PC open Settings > Pair your phone and scan the QR shown there."); return }
        _settings.value = _settings.value.copy(host = p.host, port = p.port.toString(), token = p.token)
        if (!SyncClient.isPrivateHost(p.host)) { _connection.value = ConnectionState(false, "The PC advertised ${p.host}, which is not a private LAN address.", "On the PC choose your WiFi address under Settings > Advertised host, then scan again."); return }
        viewModelScope.launch {
            val r = test(p)
            _connection.value = r
            if (r.ok == true) { saveSettings(); _message.value = "Paired with ${p.host}:${p.port}" }
            else { saveSettings(retryAfterTokenChange = false); _message.value = "Details filled in; connection not confirmed yet" }
        }
    }

    fun testConnection() {
        val s = _settings.value
        val port = s.port.trim().toIntOrNull() ?: run { _connection.value = ConnectionState(false, "Invalid port", ""); return }
        if (s.token.isBlank()) { _connection.value = ConnectionState(false, "Enter or scan the pairing token first.", ""); return }
        viewModelScope.launch { _connection.value = test(Pairing(s.host.trim(), port, s.token.trim())) }
    }

    private suspend fun test(p: Pairing): ConnectionState {
        _testing.value = true
        val result = withContext(Dispatchers.IO) { SyncClient(p).ping() }
        _testing.value = false
        return when (result) {
            is SyncClient.Outcome.Ok -> ConnectionState(true, "Connected to the PC at ${p.host}:${p.port}.", "")
            is SyncClient.Outcome.Unreachable -> ConnectionState(false, "Cannot reach ${p.host}:${p.port} (${result.message}).",
                "Check: phone and PC on the same WiFi; LAN access enabled in ReelVault Settings and the app restarted; firewall allowed on private networks; the PC's address did not change (rescan the QR).")
            is SyncClient.Outcome.Rejected -> ConnectionState(false, result.message, when (result.code) {
                401 -> "The PC's token changed or was typed wrong. Rescan the QR or copy the token again."
                403 -> "The PC only accepts private networks; make sure the phone is on home WiFi, not mobile data or a VPN."
                404 -> "Something answered at that address but it is not ReelVault. Check host and port."
                else -> ""
            })
        }
    }
}
