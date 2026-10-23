package app.reelvault.capture

import android.app.Application
import app.reelvault.capture.data.AppDatabase
import app.reelvault.capture.data.CaptureRepository
import app.reelvault.capture.data.Prefs
import app.reelvault.capture.sync.SyncScheduler

class ReelVaultApp : Application() {
    val database: AppDatabase by lazy { AppDatabase.get(this) }
    val prefs: Prefs by lazy { Prefs(this) }
    val repository: CaptureRepository by lazy { CaptureRepository(database.captureDao()) }

    override fun onCreate() {
        super.onCreate()
        if (prefs.autoSync) SyncScheduler.ensurePeriodic(this)
        app.reelvault.capture.share.Shortcuts.publish(this)
    }
}
