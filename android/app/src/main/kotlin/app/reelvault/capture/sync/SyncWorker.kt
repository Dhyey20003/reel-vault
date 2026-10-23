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

/** Sends due captures to the PC. Idempotent: the PC answers the same capture_id consistently. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as ReelVaultApp
        val prefs = app.prefs
        val repo = app.repository
        val pairing = prefs.pairing() ?: run {
            prefs.lastSyncSummary = "Not paired: open Settings and enter the PC host, port and token."
            return Result.success()
        }
        val batch = repo.due()
        if (batch.isEmpty()) {
            return Result.success()
        }
        val client = SyncClient(pairing)
        val dtos = batch.map { it.toDto() }
        return when (val outcome = client.sendCaptures(prefs.deviceId, prefs.deviceName, dtos)) {
            is SyncClient.Outcome.Ok -> {
                repo.applyResults(outcome.value)
                val created = outcome.value.count { it.result == "created" }
                val dup = outcome.value.count { it.result == "duplicate" }
                val bad = outcome.value.count { !it.accepted }
                prefs.lastSyncSummary = "Synced ${now()}: $created new, $dup already on PC${if (bad > 0) ", $bad rejected" else ""}"
                Log.i(TAG, "synced ${outcome.value.size} captures")
                if (repo.due().isNotEmpty()) Result.retry() else Result.success()
            }
            is SyncClient.Outcome.Unreachable -> {
                repo.markBatchFailed(batch, "PC unreachable: ${outcome.message}", permanent = false)
                prefs.lastSyncSummary = "PC unreachable at ${now()} (${outcome.message}); will retry."
                Result.retry()
            }
            is SyncClient.Outcome.Rejected -> {
                val permanent = outcome.code == 401 || outcome.code == 0 || outcome.code == 404 || outcome.code == 403
                repo.markBatchFailed(batch, outcome.message, permanent = permanent)
                prefs.lastSyncSummary = "Sync rejected at ${now()}: ${outcome.message}"
                if (permanent) Result.failure() else Result.retry()
            }
        }
    }

    private fun now(): String = DateTimeFormatter.ISO_INSTANT.format(Instant.now()).replace("T", " ").take(16)

    companion object {
        private const val TAG = "ReelVaultSync"
        fun Capture.toDto() = CaptureDto(captureId, sharedText, url, DateTimeFormatter.ISO_INSTANT.format(Instant.ofEpochMilli(createdAt)))
    }
}
