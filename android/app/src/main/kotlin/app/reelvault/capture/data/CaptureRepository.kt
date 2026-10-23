package app.reelvault.capture.data

import app.reelvault.core.Backoff
import app.reelvault.core.CaptureResult
import app.reelvault.core.ShareParser
import java.util.UUID

/** Local capture queue logic (persist first, dedup by normalized URL, retry bookkeeping). */
class CaptureRepository(private val dao: CaptureDao) {

    sealed class SaveOutcome {
        data class Saved(val capture: Capture) : SaveOutcome()
        data class AlreadyQueued(val capture: Capture) : SaveOutcome()
        object Nothing : SaveOutcome()
    }

    /**
     * Persists a shared text/URL. If the same normalized URL is already in the queue, no new row is
     * created: a synced row is left alone (the PC also dedups), a failed row is reset to pending.
     */
    suspend fun save(text: String?, subject: String?, now: Long = System.currentTimeMillis()): SaveOutcome {
        val parsed = ShareParser.parse(text, subject) ?: return SaveOutcome.Nothing
        parsed.normalizedUrl?.let { norm ->
            dao.findByNormalized(norm)?.let { existing ->
                if (existing.syncState == SyncState.FAILED) {
                    dao.update(existing.copy(syncState = SyncState.PENDING, attempts = 0, nextAttemptAt = 0L, lastError = null, permanent = false))
                }
                return SaveOutcome.AlreadyQueued(existing)
            }
        }
        val capture = Capture(
            captureId = UUID.randomUUID().toString(),
            sharedText = parsed.sharedText,
            url = parsed.url,
            normalizedUrl = parsed.normalizedUrl,
            createdAt = now,
        )
        dao.insert(capture)
        return SaveOutcome.Saved(capture)
    }

    suspend fun due(now: Long = System.currentTimeMillis()): List<Capture> = dao.due(now)

    suspend fun markSyncing(batch: List<Capture>) { for (c in batch) dao.update(c.copy(syncState = SyncState.SYNCING)) }

    /** Applies per-item acknowledgements. Items missing from the response stay pending and are re-sent. */
    suspend fun applyResults(batch: List<Capture>, results: List<CaptureResult>, now: Long = System.currentTimeMillis()) {
        val byId = results.associateBy { it.captureId }
        for (c in batch) {
            val r = byId[c.captureId]
            val cur = dao.byId(c.captureId) ?: continue
            when {
                r == null -> dao.update(cur.copy(syncState = SyncState.PENDING, lastError = "no acknowledgement for this item; will resend"))
                r.accepted -> dao.update(cur.copy(syncState = SyncState.SYNCED, syncedAt = now, serverResult = r.result, ideaId = r.ideaId, lastError = null, permanent = false))
                else -> dao.update(cur.copy(syncState = SyncState.FAILED, serverResult = r.result, lastError = r.error ?: "rejected by PC", permanent = true))
            }
        }
    }

    /**
     * Records a transport failure for every capture in the batch with exponential backoff.
     * Transient failures are never abandoned: after MAX attempts the row shows as failed but is
     * still retried every 30 minutes. Permanent failures (bad token/host) wait for a settings fix.
     */
    suspend fun markBatchFailed(batch: List<Capture>, error: String, permanent: Boolean, now: Long = System.currentTimeMillis()) {
        for (c in batch) {
            val cur = dao.byId(c.captureId) ?: continue
            val attempts = cur.attempts + 1
            val exhausted = attempts >= Backoff.MAX_ATTEMPTS_BEFORE_FAILED
            dao.update(
                cur.copy(
                    attempts = attempts,
                    lastError = error,
                    permanent = permanent,
                    syncState = if (permanent || exhausted) SyncState.FAILED else SyncState.PENDING,
                    nextAttemptAt = if (permanent) cur.nextAttemptAt else if (exhausted) now + Backoff.MAX_MS else Backoff.nextAttemptAt(now, attempts - 1),
                ),
            )
        }
    }

    suspend fun retryFailed(): Int = dao.retryFailed()
    suspend fun makeAllDue(): Int = dao.makeAllDue()
    suspend fun resetInFlight(): Int = dao.resetInFlight()
    suspend fun delete(id: String) = dao.delete(id)
    fun observeAll() = dao.observeAll()
    fun observeCount(state: String) = dao.observeCount(state)
}
