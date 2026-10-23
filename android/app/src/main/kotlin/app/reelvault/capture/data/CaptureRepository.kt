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
                    dao.update(existing.copy(syncState = SyncState.PENDING, attempts = 0, nextAttemptAt = 0L, lastError = null))
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

    suspend fun applyResults(results: List<CaptureResult>, now: Long = System.currentTimeMillis()) {
        for (r in results) {
            val c = dao.byId(r.captureId) ?: continue
            if (r.accepted) {
                dao.update(c.copy(syncState = SyncState.SYNCED, syncedAt = now, serverResult = r.result, ideaId = r.ideaId, lastError = null))
            } else {
                dao.update(c.copy(syncState = SyncState.FAILED, serverResult = r.result, lastError = r.error ?: "rejected by PC"))
            }
        }
    }

    /** Records a transport failure for every capture in the batch, with exponential backoff. */
    suspend fun markBatchFailed(batch: List<Capture>, error: String, permanent: Boolean, now: Long = System.currentTimeMillis()) {
        for (c in batch) {
            val attempts = c.attempts + 1
            val giveUp = permanent || attempts >= Backoff.MAX_ATTEMPTS_BEFORE_FAILED
            dao.update(
                c.copy(
                    attempts = attempts,
                    lastError = error,
                    syncState = if (giveUp) SyncState.FAILED else SyncState.PENDING,
                    nextAttemptAt = if (giveUp) c.nextAttemptAt else Backoff.nextAttemptAt(now, attempts - 1),
                ),
            )
        }
    }

    suspend fun retryFailed(): Int = dao.retryFailed()
    suspend fun makeAllDue(): Int = dao.makeAllDue()
    suspend fun delete(id: String) = dao.delete(id)
    fun observeAll() = dao.observeAll()
    fun observeCount(state: String) = dao.observeCount(state)
}
