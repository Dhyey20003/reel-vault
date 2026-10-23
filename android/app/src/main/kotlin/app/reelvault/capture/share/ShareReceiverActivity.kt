package app.reelvault.capture.share

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import app.reelvault.capture.R
import app.reelvault.capture.ReelVaultApp
import app.reelvault.capture.data.CaptureRepository
import app.reelvault.capture.sync.SyncScheduler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The invisible share target. Instagram's Share sheet -> "Save to ReelVault" lands here.
 *
 * Contract (see docs/ANDROID.md):
 *  1. Read ACTION_SEND text/plain (EXTRA_TEXT and, if present, EXTRA_SUBJECT).
 *  2. Persist to the Room queue BEFORE any network activity.
 *  3. Enqueue a background sync (WorkManager) and finish immediately. No window is drawn:
 *     the theme is translucent with no animation, the activity is excluded from recents and
 *     has an empty task affinity, so the user stays in Instagram.
 *  No AI, no downloads, no metadata lookups happen here.
 */
class ShareReceiverActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val intent = intent
        if (intent?.action != Intent.ACTION_SEND) {
            finish(); return
        }
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)
        val subject = intent.getStringExtra(Intent.EXTRA_SUBJECT)
        val app = applicationContext as ReelVaultApp
        val repo = app.repository
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        scope.launch {
            val showToast = runCatching { app.prefs.showToast }.getOrDefault(true)
            val outcome = try {
                repo.save(text, subject)
            } catch (e: Exception) {
                Log.e(TAG, "could not persist share", e)
                null
            }
            // Only after the row is on disk do we touch WorkManager (which also persists its request).
            if (outcome is CaptureRepository.SaveOutcome.Saved || outcome is CaptureRepository.SaveOutcome.AlreadyQueued) {
                SyncScheduler.syncNow(app)
                Shortcuts.reportUsed(app)
            }
            withContext(Dispatchers.Main) {
                if (showToast) {
                    val msg = when (outcome) {
                        is CaptureRepository.SaveOutcome.Saved -> R.string.toast_saved
                        is CaptureRepository.SaveOutcome.AlreadyQueued -> R.string.toast_saved_again
                        else -> R.string.toast_nothing
                    }
                    Toast.makeText(app, msg, Toast.LENGTH_SHORT).show()
                }
                finish()
                @Suppress("DEPRECATION")
                overridePendingTransition(0, 0)
            }
        }
    }

    companion object { private const val TAG = "ReelVaultShare" }
}
