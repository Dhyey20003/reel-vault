package app.reelvault.capture.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import app.reelvault.capture.ReelVaultApp
import app.reelvault.capture.data.Capture
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

data class Counts(val synced: Int = 0, val pending: Int = 0, val failed: Int = 0)

data class SettingsState(
    val host: String = "", val port: String = "8765", val token: String = "", val autoSync: Boolean = true,
    val showToast: Boolean = true, val deviceName: String = "", val paired: Boolean = false,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val rv = app as ReelVaultApp
    private val repo = rv.repository
    private val prefs = rv.prefs

    val captures: StateFlow<List<Capture>> = repo.observeAll().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val counts: StateFlow<Counts> = combine(
        repo.observeCount(SyncState.SYNCED), repo.observeCount(SyncState.PENDING), repo.observeCount(SyncState.FAILED),
    ) { s, p, f -> Counts(s, p, f) }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), Counts())

    private val _settings = MutableStateFlow(loadSettings())
    val settings: StateFlow<SettingsState> = _settings.asStateFlow()

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _lastSync = MutableStateFlow(prefs.lastSyncSummary)
    val lastSync: StateFlow<String> = _lastSync.asStateFlow()

    val syncRunning: StateFlow<Boolean> = WorkManager.getInstance(app).getWorkInfosForUniqueWorkFlow(SyncScheduler.ONE_TIME)
        .map { infos -> infos.any { it.state == WorkInfo.State.RUNNING } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    private fun loadSettings() = SettingsState(
        host = prefs.host, port = prefs.port.toString(), token = prefs.token, autoSync = prefs.autoSync,
        showToast = prefs.showToast, deviceName = prefs.deviceName, paired = prefs.isPaired,
    )

    fun refreshLastSync() { _lastSync.value = prefs.lastSyncSummary }
    fun clearMessage() { _message.value = null }

    fun syncNow() {
        viewModelScope.launch {
            repo.makeAllDue()
            SyncScheduler.syncNow(getApplication())
            _message.value = "Sync requested"
        }
    }

    fun retryFailed() {
        viewModelScope.launch {
            val n = repo.retryFailed()
            if (n > 0) SyncScheduler.syncNow(getApplication())
            _message.value = if (n > 0) "$n capture(s) queued again" else "Nothing to retry"
        }
    }

    fun delete(id: String) { viewModelScope.launch { repo.delete(id) } }

    fun updateSettings(transform: SettingsState.() -> SettingsState) { _settings.value = _settings.value.transform() }

    fun saveSettings(): Boolean {
        val s = _settings.value
        val port = s.port.trim().toIntOrNull()
        if (!PairingUri.isValidHost(s.host.trim())) { _message.value = "Enter the PC's LAN IP (shown in ReelVault Settings on the PC)"; return false }
        if (port == null || port !in 1..65535) { _message.value = "Port must be 1 to 65535"; return false }
        if (!SyncClient.isPrivateHost(s.host.trim())) { _message.value = "Only private LAN addresses are allowed (e.g. 192.168.x.x)"; return false }
        prefs.host = s.host.trim(); prefs.port = port; prefs.token = s.token.trim()
        prefs.autoSync = s.autoSync; prefs.showToast = s.showToast
        if (s.deviceName.isNotBlank()) prefs.deviceName = s.deviceName
        if (s.autoSync) SyncScheduler.ensurePeriodic(getApplication()) else SyncScheduler.cancelPeriodic(getApplication())
        _settings.value = loadSettings()
        _message.value = "Settings saved"
        return true
    }

    fun applyScannedQr(contents: String?) {
        val p = contents?.let { PairingUri.parse(it) }
        if (p == null) { _message.value = "That QR code is not a ReelVault pairing code"; return }
        _settings.value = _settings.value.copy(host = p.host, port = p.port.toString(), token = p.token)
        saveSettings()
        _message.value = "Paired with ${p.host}:${p.port}"
    }

    fun testConnection() {
        val s = _settings.value
        val port = s.port.trim().toIntOrNull() ?: run { _message.value = "Invalid port"; return }
        if (s.token.isBlank()) { _message.value = "Enter or scan the pairing token first"; return }
        viewModelScope.launch {
            _message.value = "Testing..."
            val result = withContext(Dispatchers.IO) { SyncClient(Pairing(s.host.trim(), port, s.token.trim())).ping() }
            _message.value = when (result) {
                is SyncClient.Outcome.Ok -> "Connected to the PC"
                is SyncClient.Outcome.Unreachable -> "Cannot reach ${s.host}:${s.port} (${result.message}). Same WiFi? LAN access enabled on the PC?"
                is SyncClient.Outcome.Rejected -> result.message
            }
        }
    }
}
