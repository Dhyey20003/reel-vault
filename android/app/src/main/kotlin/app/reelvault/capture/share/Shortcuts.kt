package app.reelvault.capture.share

import android.content.Context
import android.content.Intent
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import app.reelvault.capture.R

/**
 * Publishes a long-lived "Save to ReelVault" sharing shortcut so Android can show it in the
 * share sheet's direct-share row (one tap instead of scrolling to the app list). Android decides
 * the ranking; sharing often from Instagram tends to move it up. Users can also long-press the
 * ReelVault entry in the share sheet and choose Pin.
 */
object Shortcuts {
    const val ID = "save_to_reelvault"
    const val CATEGORY = "app.reelvault.capture.SHARE_TARGET"

    fun publish(context: Context) {
        try {
            val intent = Intent(context, ShareReceiverActivity::class.java).setAction(Intent.ACTION_SEND)
            val shortcut = ShortcutInfoCompat.Builder(context, ID)
                .setShortLabel(context.getString(R.string.share_target_label))
                .setLongLabel(context.getString(R.string.share_target_label))
                .setIcon(IconCompat.createWithResource(context, R.mipmap.ic_launcher))
                .setIntent(intent)
                .setLongLived(true)
                .setCategories(setOf(CATEGORY))
                .build()
            ShortcutManagerCompat.pushDynamicShortcut(context, shortcut)
        } catch (e: Exception) {
            // Shortcuts are an optimisation only; sharing via the app list keeps working.
        }
    }

    fun reportUsed(context: Context) {
        try { ShortcutManagerCompat.reportShortcutUsed(context, ID) } catch (e: Exception) { /* ignore */ }
    }
}
