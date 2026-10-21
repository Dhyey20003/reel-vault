package app.reelvault.capture

import android.content.Intent
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.reelvault.capture.share.ShareReceiverActivity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Verifies the hero behaviour on a device/emulator: sharing a Reel link persists a capture
 * and the share activity finishes on its own without showing UI.
 */
@RunWith(AndroidJUnit4::class)
class ShareReceiverTest {
    @Test fun sharedLinkIsPersistedAndActivityFinishes() {
        val app = ApplicationProvider.getApplicationContext<ReelVaultApp>()
        val url = "https://www.instagram.com/reel/TeSt123/?igsh=abc"
        val intent = Intent(app, ShareReceiverActivity::class.java).apply {
            action = Intent.ACTION_SEND; type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "Reel by someone $url")
        }
        val scenario = ActivityScenario.launch<ShareReceiverActivity>(intent)
        val deadline = System.currentTimeMillis() + 5000
        while (scenario.state != Lifecycle.State.DESTROYED && System.currentTimeMillis() < deadline) Thread.sleep(50)
        assertEquals(Lifecycle.State.DESTROYED, scenario.state)
        val rows = runBlocking { app.repository.observeAll().first() }
        assertTrue(rows.any { it.normalizedUrl == "https://instagram.com/reel/TeSt123" })
    }
}
