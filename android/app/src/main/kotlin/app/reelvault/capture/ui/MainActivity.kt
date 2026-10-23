package app.reelvault.capture.ui

import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.reelvault.capture.data.Capture
import app.reelvault.capture.data.SyncState
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.text.DateFormat
import java.util.Date

private val Amber = Color(0xFFF2A93B)
private val Green = Color(0xFF3FCF7A)
private val Red = Color(0xFFEF5350)
private val Blue = Color(0xFF4CC2FF)

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme(colorScheme = darkColorScheme(primary = Amber, secondary = Blue)) { App(vm) } }
    }
    override fun onResume() { super.onResume(); vm.refresh() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App(vm: MainViewModel) {
    var tab by remember { mutableIntStateOf(0) }
    val snackbar = remember { SnackbarHostState() }
    val message by vm.message.collectAsStateWithLifecycle()
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); vm.clearMessage() } }
    Scaffold(
        topBar = { TopAppBar(title = { Text(listOf("Inbox", "Sync", "Settings")[tab]) }) },
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, icon = { Icon(Icons.Default.List, null) }, label = { Text("Inbox") })
                NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, icon = { Icon(Icons.Default.Refresh, null) }, label = { Text("Sync") })
                NavigationBarItem(selected = tab == 2, onClick = { tab = 2 }, icon = { Icon(Icons.Default.Settings, null) }, label = { Text("Settings") })
            }
        },
    ) { padding -> Column(Modifier.padding(padding).fillMaxSize()) { when (tab) { 0 -> InboxScreen(vm); 1 -> SyncScreen(vm); else -> SettingsScreen(vm) } } }
}

@Composable
private fun StatusDot(color: Color) { Box(Modifier.size(10.dp).background(color, CircleShape)) }

private fun stateColor(c: Capture) = when (c.syncState) { SyncState.SYNCED -> Green; SyncState.FAILED -> if (c.permanent) Red else Amber; SyncState.SYNCING -> Blue; else -> Amber }
private fun stateLabel(c: Capture): String = when (c.syncState) {
    SyncState.SYNCED -> if (c.serverResult == "duplicate") "synced (already on PC)" else "synced"
    SyncState.SYNCING -> "syncing"
    SyncState.FAILED -> if (c.permanent) "failed: needs attention" else "waiting for PC (retrying)"
    else -> if (c.attempts > 0) "pending (retry ${c.attempts})" else "pending"
}

@Composable
fun InboxScreen(vm: MainViewModel) {
    val items by vm.captures.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    var link by remember { mutableStateOf("") }
    val df = remember { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT) }
    Column(Modifier.fillMaxSize()) {
        Card(Modifier.fillMaxWidth().padding(12.dp)) {
            Column(Modifier.padding(12.dp)) {
                Text("Quick save a link", style = MaterialTheme.typography.titleSmall)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = link, onValueChange = { link = it }, placeholder = { Text("Paste an Instagram or YouTube link") }, singleLine = true, modifier = Modifier.weight(1f))
                    TextButton(onClick = { val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager; link = cm.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString() ?: "" }) { Text("Paste") }
                    Button(onClick = { vm.saveLink(link); link = "" }, enabled = link.isNotBlank()) { Text("Save") }
                }
                Text("Fastest path: in Instagram tap Share, then \"Save to ReelVault\" in the share sheet (long-press it there to pin it near the top).", style = MaterialTheme.typography.bodySmall)
            }
        }
        if (items.isEmpty()) {
            Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                Text("No captures yet", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(8.dp))
                Text("Shared reels are saved here instantly and sent to your PC whenever it is reachable on your WiFi.", style = MaterialTheme.typography.bodyMedium)
            }
        } else {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(items, key = { it.captureId }) { c -> CaptureRow(c, df.format(Date(c.createdAt))) { vm.delete(c.captureId) } }
            }
        }
    }
}

@Composable
private fun CaptureRow(c: Capture, time: String, onDelete: () -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(48.dp).background(Color(0xFF222A35), RoundedCornerShape(10.dp)), contentAlignment = Alignment.Center) {
                Text(when (c.source) { "Instagram" -> "IG"; "YouTube Shorts" -> "YTS"; "YouTube" -> "YT"; "text" -> "Aa"; else -> "URL" }, fontWeight = FontWeight.Bold, color = Amber)
            }
            Column(Modifier.weight(1f)) {
                Text(c.normalizedUrl?.removePrefix("https://") ?: c.sharedText.lineSequence().firstOrNull().orEmpty(), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, maxLines = 2)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusDot(stateColor(c)); Text(stateLabel(c), style = MaterialTheme.typography.bodySmall); Text("· $time", style = MaterialTheme.typography.bodySmall)
                }
                if (c.syncState != SyncState.SYNCED && !c.lastError.isNullOrBlank()) Text(c.lastError, style = MaterialTheme.typography.bodySmall, maxLines = 2, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            TextButton(onClick = onDelete) { Text("Remove") }
        }
    }
}

@Composable
fun SyncScreen(vm: MainViewModel) {
    val counts by vm.counts.collectAsStateWithLifecycle()
    val last by vm.lastSync.collectAsStateWithLifecycle()
    val lastOk by vm.lastSuccess.collectAsStateWithLifecycle()
    val running by vm.syncRunning.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val df = remember { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card { Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Connection", style = MaterialTheme.typography.titleSmall)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusDot(if (!settings.paired) Red else if (running) Blue else if (lastOk > 0) Green else Amber)
                Text(if (!settings.paired) "Not paired. Open Settings and scan the PC's QR." else if (running) "Syncing now..." else "PC ${settings.host}:${settings.port}")
            }
            Text(if (lastOk > 0) "Last successful sync: ${df.format(Date(lastOk))}" else "No successful sync yet", style = MaterialTheme.typography.bodySmall)
            if (last.isNotBlank()) Text(last, style = MaterialTheme.typography.bodySmall)
        } }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { Stat("Synced", counts.synced, Green); Stat("Pending", counts.pending + counts.syncing, Amber); Stat("Failed", counts.failed, Red) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { vm.syncNow() }, enabled = settings.paired && !running) { Text("Sync now") }
            OutlinedButton(onClick = { vm.retryFailed() }, enabled = counts.failed > 0) { Text("Retry failed") }
            if (running) CircularProgressIndicator(Modifier.size(24.dp))
        }
        HorizontalDivider()
        Text("How it works", style = MaterialTheme.typography.titleSmall)
        Text("Captures are stored on this phone first. They are sent to the PC over your WiFi whenever it is reachable; an offline PC cannot receive them until it is back. Transient failures retry with increasing delays and are never dropped. \"Needs attention\" means the token or address is wrong: fix it in Settings, then Retry failed. Downloads or AI analysis failing later on the PC do not affect a synced capture.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Stat(label: String, value: Int, color: Color) {
    Card { Column(Modifier.padding(horizontal = 18.dp, vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.headlineSmall, color = color); Text(label, style = MaterialTheme.typography.bodySmall)
    } }
}

@Composable
fun SettingsScreen(vm: MainViewModel) {
    val s by vm.settings.collectAsStateWithLifecycle()
    val conn by vm.connection.collectAsStateWithLifecycle()
    val testing by vm.testing.collectAsStateWithLifecycle()
    var showToken by remember { mutableStateOf(false) }
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result -> vm.applyScannedQr(result.contents) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("PC connection", style = MaterialTheme.typography.titleMedium)
        Text("On the PC: ReelVault > Settings > Pair your phone. Scan the QR; the app fills in host, port and token and tests the connection. Manual entry works too.", style = MaterialTheme.typography.bodySmall)
        Button(onClick = { scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setBeepEnabled(false).setOrientationLocked(true).setPrompt("Scan the ReelVault pairing QR")) }) { Text("Scan pairing QR") }
        conn.ok?.let { ok ->
            Card { Column(Modifier.padding(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) { StatusDot(if (ok) Green else Red); Text(conn.message, style = MaterialTheme.typography.bodyMedium) }
                if (conn.hint.isNotBlank()) Text(conn.hint, style = MaterialTheme.typography.bodySmall)
            } }
        }
        OutlinedTextField(value = s.host, onValueChange = { v -> vm.updateSettings { copy(host = v) } }, label = { Text("PC host (LAN IP)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = s.port, onValueChange = { v -> vm.updateSettings { copy(port = v.filter { it.isDigit() }.take(5)) } }, label = { Text("Port") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.width(160.dp))
        OutlinedTextField(value = s.token, onValueChange = { v -> vm.updateSettings { copy(token = v) } }, label = { Text("Pairing token") }, singleLine = true,
            visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton(onClick = { showToken = !showToken }) { Text(if (showToken) "Hide" else "Show") } }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = { vm.saveSettings() }) { Text("Save") }
            OutlinedButton(onClick = { vm.testConnection() }, enabled = !testing) { Text("Test connection") }
            if (testing) CircularProgressIndicator(Modifier.size(22.dp))
        }
        HorizontalDivider()
        Text("Behaviour", style = MaterialTheme.typography.titleMedium)
        ToggleRow("Auto-sync in the background", s.autoSync) { v -> vm.updateSettings { copy(autoSync = v) }; vm.saveSettings(false) }
        ToggleRow("Show a brief toast after saving", s.showToast) { v -> vm.updateSettings { copy(showToast = v) }; vm.saveSettings(false) }
        ToggleRow("Sync on WiFi without internet", s.syncWithoutInternet) { v -> vm.updateSettings { copy(syncWithoutInternet = v) }; vm.saveSettings(false) }
        OutlinedTextField(value = s.deviceName, onValueChange = { v -> vm.updateSettings { copy(deviceName = v) } }, label = { Text("Device name (shown on the PC)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Text("Sync uses plain HTTP on your private WiFi; the token is stored encrypted on this phone and never leaves your network.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { Text(label, Modifier.weight(1f)); Switch(checked = checked, onCheckedChange = onChange) }
}
