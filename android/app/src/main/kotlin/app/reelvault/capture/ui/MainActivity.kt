package app.reelvault.capture.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
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
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.reelvault.capture.data.Capture
import app.reelvault.capture.data.SyncState
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.text.DateFormat
import java.util.Date

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) { App(vm) }
        }
    }

    override fun onResume() {
        super.onResume()
        vm.refreshLastSync()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App(vm: MainViewModel) {
    var tab by remember { mutableIntStateOf(0) }
    val snackbar = remember { SnackbarHostState() }
    val message by vm.message.collectAsStateWithLifecycle()
    LaunchedEffect(message) {
        message?.let { snackbar.showSnackbar(it); vm.clearMessage() }
    }
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
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            when (tab) {
                0 -> InboxScreen(vm)
                1 -> SyncScreen(vm)
                else -> SettingsScreen(vm)
            }
        }
    }
}

@Composable
fun InboxScreen(vm: MainViewModel) {
    val items by vm.captures.collectAsStateWithLifecycle()
    if (items.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
            Text("No captures yet", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Text("In Instagram, tap Share on a Reel and choose \"Save to ReelVault\". It is saved here instantly and synced to your PC when it is reachable.", style = MaterialTheme.typography.bodyMedium)
        }
        return
    }
    val df = remember { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(items, key = { it.captureId }) { c -> CaptureRow(c, df.format(Date(c.createdAt))) { vm.delete(c.captureId) } }
    }
}

@Composable
private fun CaptureRow(c: Capture, time: String, onDelete: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(c.normalizedUrl ?: c.sharedText.lineSequence().firstOrNull().orEmpty(), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, maxLines = 2)
            if (c.url == null) Text("No link found in the shared text; kept as text", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AssistChip(onClick = {}, label = { Text(stateLabel(c)) })
                Text(time, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onDelete) { Text("Remove") }
            }
            c.lastError?.takeIf { c.syncState != SyncState.SYNCED }?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
        }
    }
}

private fun stateLabel(c: Capture): String = when (c.syncState) {
    SyncState.SYNCED -> if (c.serverResult == "duplicate") "synced (already on PC)" else "synced"
    SyncState.FAILED -> "failed"
    else -> if (c.attempts > 0) "pending (retry ${c.attempts})" else "pending"
}

@Composable
fun SyncScreen(vm: MainViewModel) {
    val counts by vm.counts.collectAsStateWithLifecycle()
    val last by vm.lastSync.collectAsStateWithLifecycle()
    val running by vm.syncRunning.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Stat("Synced", counts.synced); Stat("Pending", counts.pending); Stat("Failed", counts.failed)
        }
        HorizontalDivider()
        Text(if (!settings.paired) "Not paired yet. Open Settings." else if (running) "Sync running..." else last.ifBlank { "No sync yet." }, style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { vm.syncNow() }, enabled = settings.paired) { Text("Sync now") }
            OutlinedButton(onClick = { vm.retryFailed() }, enabled = counts.failed > 0) { Text("Retry failed") }
        }
        Text("Captures are stored on the phone first and sent to the PC over your WiFi whenever it is reachable. Failed items retry with increasing delays; after repeated failures they wait for a manual retry.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Stat(label: String, value: Int) {
    Card { Column(Modifier.padding(horizontal = 18.dp, vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.headlineSmall); Text(label, style = MaterialTheme.typography.bodySmall)
    } }
}

@Composable
fun SettingsScreen(vm: MainViewModel) {
    val s by vm.settings.collectAsStateWithLifecycle()
    var showToken by remember { androidx.compose.runtime.mutableStateOf(false) }
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result -> vm.applyScannedQr(result.contents) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("PC connection", style = MaterialTheme.typography.titleMedium)
        Text("On the PC open ReelVault > Settings > Pair your phone. Scan the QR code, or type the host, port and token shown there.", style = MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick = {
            scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setBeepEnabled(false).setOrientationLocked(true).setPrompt("Scan the ReelVault pairing QR"))
        }) { Text("Scan pairing QR") }
        OutlinedTextField(value = s.host, onValueChange = { v -> vm.updateSettings { copy(host = v) } }, label = { Text("PC host (LAN IP)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = s.port, onValueChange = { v -> vm.updateSettings { copy(port = v.filter { it.isDigit() }.take(5)) } }, label = { Text("Port") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.width(160.dp))
        OutlinedTextField(value = s.token, onValueChange = { v -> vm.updateSettings { copy(token = v) } }, label = { Text("Pairing token") }, singleLine = true,
            visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = { TextButton(onClick = { showToken = !showToken }) { Text(if (showToken) "Hide" else "Show") } }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { vm.saveSettings() }) { Text("Save") }
            OutlinedButton(onClick = { vm.testConnection() }) { Text("Test connection") }
        }
        HorizontalDivider()
        Text("Behaviour", style = MaterialTheme.typography.titleMedium)
        ToggleRow("Auto-sync in the background", s.autoSync) { v -> vm.updateSettings { copy(autoSync = v) }; vm.saveSettings() }
        ToggleRow("Show a brief toast after saving", s.showToast) { v -> vm.updateSettings { copy(showToast = v) }; vm.saveSettings() }
        OutlinedTextField(value = s.deviceName, onValueChange = { v -> vm.updateSettings { copy(deviceName = v) } }, label = { Text("Device name (shown on the PC)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Text("Sync uses plain HTTP on your private WiFi; the token is stored encrypted on this phone and never leaves your network.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f)); Switch(checked = checked, onCheckedChange = onChange)
    }
}
