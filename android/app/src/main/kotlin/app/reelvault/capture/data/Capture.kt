package app.reelvault.capture.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/** Sync states of a queued capture. */
object SyncState {
    const val PENDING = "pending"   // waiting to be sent (or waiting for its retry time)
    const val SYNCING = "syncing"   // in a request right now
    const val SYNCED = "synced"     // acknowledged by the PC for this capture_id (created or duplicate)
    const val FAILED = "failed"     // transient: still retried on a slow schedule; permanent: needs a settings fix
}

@Entity(
    tableName = "captures",
    indices = [Index("normalized_url"), Index("sync_state"), Index("created_at")],
)
data class Capture(
    @PrimaryKey @ColumnInfo(name = "capture_id") val captureId: String,
    @ColumnInfo(name = "shared_text") val sharedText: String,
    @ColumnInfo(name = "url") val url: String?,
    @ColumnInfo(name = "normalized_url") val normalizedUrl: String?,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    @ColumnInfo(name = "sync_state") val syncState: String = SyncState.PENDING,
    @ColumnInfo(name = "attempts") val attempts: Int = 0,
    @ColumnInfo(name = "next_attempt_at") val nextAttemptAt: Long = 0L,
    @ColumnInfo(name = "last_error") val lastError: String? = null,
    @ColumnInfo(name = "synced_at") val syncedAt: Long? = null,
    @ColumnInfo(name = "server_result") val serverResult: String? = null,
    @ColumnInfo(name = "idea_id") val ideaId: String? = null,
    /** v2: a permanent failure (token rejected, bad host) is not retried automatically. */
    @ColumnInfo(name = "permanent", defaultValue = "0") val permanent: Boolean = false,
) {
    val source: String get() = when {
        normalizedUrl == null -> "text"
        normalizedUrl.contains("instagram.com") -> "Instagram"
        normalizedUrl.contains("youtube.com/shorts") -> "YouTube Shorts"
        normalizedUrl.contains("youtube.com") -> "YouTube"
        else -> "Link"
    }
}
