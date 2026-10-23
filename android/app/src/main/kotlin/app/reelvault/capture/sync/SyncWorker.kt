package app.reelvault.capture.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import app.reelvault.capture.ReelVaultApp
import app.reelvault.capture.data.Capture
import app.reelvault.core.CaptureDto
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Sends due captures to the PC in chunks. Idempotent: the PC answers the same capture_id
 * consistently, so a lost response or a retry never creates a duplicate idea. Rows are only
 * marked synced on a per-item acknowledgement from the PC.
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as ReelVaultApp
        val prefs = app.prefs
        val repo = app.repository
        val pairing = prefs.pairing() ?: run {
            prefs.lastSyncSummary = "Not paired: open Settings and scan the PC's QR code."
            return Result.success()
        }
        repo.resetInFlight()
        val all = repo.due()
        if (all.isEmpty()) return Result.success()
        val client = SyncClient(pairing)
        var retry = false
        for (batch in all.chunked(CHUNK)) {
            if (isStopped) return Result.retry()
            repo.markSyncing(batch)
            when (val outcome = client.sendCaptures(prefs.deviceId, prefs.deviceName, batch.map { it.toDto() })) {
                is SyncClient.Outcome.Ok -> {
                    repo.applyResults(batch, outcome.value)
                    val created = outcome.value.count { it.result == "created" }
                    val dup = outcome.value.count { it.result == "duplicate" }
                    val bad = outcome.value.count { !it.accepted }
                    prefs.lastSuccessAt = System.currentTimeMillis()
                    prefs.lastSyncSummary = "Synced ${now()}: $created new, $dup already on PC${if (bad > 0) ", $bad rejected" else ""}"
                    Log.i(TAG, "synced ${outcome.value.size} captures")
                }
                is SyncClient.Outcome.Unreachable -> {
                    repo.markBatchFailed(batch, "PC unreachable: ${outcome.message}", permanent = false)
                    prefs.lastSyncSummary = "PC unreachable at ${now()} (${outcome.message}). Captures are kept and retried."
                    return Result.retry()
                }
                is SyncClient.Outcome.Rejected -> {
                    val permanent = outcome.code in setOf(0, 401, 403, 404)
                    repo.markBatchFailed(batch, outcome.message, permanent = permanent)
                    prefs.lastSyncSummary = "Sync rejected at ${now()}: ${outcome.message}"
                    if (permanent) return Result.failure()
                    retry = true
                }
            }
        }
        return if (retry || repo.due().isNotEmpty()) Result.retry() else Result.success()
    }

    private fun now(): String = DateTimeFormatter.ISO_INSTANT.format(Instant.now()).replace("T", " ").take(16)

    companion object {
        private const val TAG = "ReelVaultSync"
        const val CHUNK = 100
        fun Capture.toDto() = CaptureDto(captureId, sharedText, url, DateTimeFormatter.ISO_INSTANT.format(Instant.ofEpochMilli(createdAt)))
    }
}
