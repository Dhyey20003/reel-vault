package app.reelvault.capture.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import app.reelvault.capture.ReelVaultApp
import java.util.concurrent.TimeUnit

object SyncScheduler {
    const val ONE_TIME = "reelvault-sync"
    const val PERIODIC = "reelvault-sync-periodic"

    private fun constraints(context: Context): Constraints {
        val prefs = (context.applicationContext as ReelVaultApp).prefs
        // A home WiFi without internet still reaches the PC; let the user opt out of the "connected" gate.
        return if (prefs.syncWithoutInternet) Constraints.NONE else Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
    }

    /** Runs a sync as soon as possible; replaces any sync waiting in backoff (in-flight rows are re-sent safely). */
    fun syncNow(context: Context) {
        val req = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(constraints(context))
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(ONE_TIME, ExistingWorkPolicy.REPLACE, req)
    }

    /** Every 15 minutes (the WorkManager minimum) pick up anything still pending or transiently failed. */
    fun ensurePeriodic(context: Context) {
        val req = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(constraints(context))
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, req)
    }

    fun cancelPeriodic(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(PERIODIC)
    }
}
