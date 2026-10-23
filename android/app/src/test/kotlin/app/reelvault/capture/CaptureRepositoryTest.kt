package app.reelvault.capture

import app.reelvault.capture.data.Capture
import app.reelvault.capture.data.CaptureDao
import app.reelvault.capture.data.CaptureRepository
import app.reelvault.capture.data.SyncState
import app.reelvault.core.Backoff
import app.reelvault.core.CaptureResult
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** In-memory DAO so the queue logic can be unit-tested on the JVM without Room. */
class FakeDao : CaptureDao {
    val rows = MutableStateFlow<Map<String, Capture>>(emptyMap())
    override suspend fun insert(capture: Capture): Long { if (rows.value.containsKey(capture.captureId)) return -1; rows.value = rows.value + (capture.captureId to capture); return 1 }
    override suspend fun update(capture: Capture) { rows.value = rows.value + (capture.captureId to capture) }
    override fun observeAll(): Flow<List<Capture>> = rows.map { it.values.sortedByDescending { c -> c.createdAt } }
    override suspend fun findByNormalized(normalized: String) = rows.value.values.firstOrNull { it.normalizedUrl == normalized }
    override suspend fun byId(id: String) = rows.value[id]
    override suspend fun due(now: Long, limit: Int) = rows.value.values.filter { ((it.syncState == SyncState.PENDING || it.syncState == SyncState.SYNCING) && it.nextAttemptAt <= now) || (it.syncState == SyncState.FAILED && !it.permanent && it.nextAttemptAt <= now) }.sortedBy { it.createdAt }.take(limit)
    override fun observeCount(state: String): Flow<Int> = rows.map { m -> m.values.count { it.syncState == state } }
    override suspend fun retryFailed(): Int { val f = rows.value.values.filter { it.syncState == SyncState.FAILED }; f.forEach { update(it.copy(syncState = SyncState.PENDING, attempts = 0, nextAttemptAt = 0, lastError = null, permanent = false)) }; return f.size }
    override suspend fun makeAllDue(): Int { val p = rows.value.values.filter { it.syncState != SyncState.SYNCED }; p.forEach { update(it.copy(nextAttemptAt = 0)) }; return p.size }
    override suspend fun resetInFlight(): Int { val p = rows.value.values.filter { it.syncState == SyncState.SYNCING }; p.forEach { update(it.copy(syncState = SyncState.PENDING)) }; return p.size }
    override suspend fun delete(id: String) { rows.value = rows.value - id }
}

class CaptureRepositoryTest {
    private val dao = FakeDao()
    private val repo = CaptureRepository(dao)
    private val reel = "https://www.instagram.com/reel/AbC123/?igsh=xyz"

    @Test fun persistsAndExtractsUrl() = runTest {
        val out = repo.save("Look at this $reel", null, now = 1000)
        assertTrue(out is CaptureRepository.SaveOutcome.Saved)
        val c = (out as CaptureRepository.SaveOutcome.Saved).capture
        assertEquals(reel, c.url)
        assertEquals("https://instagram.com/reel/AbC123", c.normalizedUrl)
        assertEquals(SyncState.PENDING, c.syncState)
        assertEquals(1, repo.due(now = 1000).size)
    }

    @Test fun duplicateShareDoesNotCreateSecondRow() = runTest {
        repo.save(reel, null)
        val again = repo.save("https://instagram.com/reels/AbC123", null)
        assertTrue(again is CaptureRepository.SaveOutcome.AlreadyQueued)
        assertEquals(1, dao.rows.value.size)
    }

    @Test fun duplicateOfFailedRowResetsItToPending() = runTest {
        val c = (repo.save(reel, null) as CaptureRepository.SaveOutcome.Saved).capture
        dao.update(c.copy(syncState = SyncState.FAILED, attempts = 8, lastError = "x"))
        repo.save(reel, null)
        val row = dao.byId(c.captureId)!!
        assertEquals(SyncState.PENDING, row.syncState); assertEquals(0, row.attempts); assertNull(row.lastError)
    }

    @Test fun textWithoutLinkIsStillKept() = runTest {
        val out = repo.save("some idea text", "Subject")
        assertTrue(out is CaptureRepository.SaveOutcome.Saved)
        assertNull((out as CaptureRepository.SaveOutcome.Saved).capture.url)
        assertTrue(repo.save("   ", null) is CaptureRepository.SaveOutcome.Nothing)
    }

    @Test fun serverResultsUpdateState() = runTest {
        val a = (repo.save(reel, null) as CaptureRepository.SaveOutcome.Saved).capture
        val b = (repo.save("no link", null) as CaptureRepository.SaveOutcome.Saved).capture
        repo.applyResults(listOf(a, b), listOf(
            CaptureResult(a.captureId, "duplicate", "idea1", null),
            CaptureResult(b.captureId, "invalid", null, "no http(s) URL"),
        ))
        assertEquals(SyncState.SYNCED, dao.byId(a.captureId)!!.syncState)
        assertEquals("idea1", dao.byId(a.captureId)!!.ideaId)
        assertEquals(SyncState.FAILED, dao.byId(b.captureId)!!.syncState)
        assertEquals("no http(s) URL", dao.byId(b.captureId)!!.lastError)
    }

    @Test fun transportFailureBacksOffThenGivesUp() = runTest {
        val c = (repo.save(reel, null) as CaptureRepository.SaveOutcome.Saved).capture
        repo.markBatchFailed(listOf(c), "unreachable", permanent = false, now = 10_000)
        var row = dao.byId(c.captureId)!!
        assertEquals(SyncState.PENDING, row.syncState); assertEquals(1, row.attempts)
        assertEquals(10_000 + Backoff.delayMs(0), row.nextAttemptAt)
        assertTrue(repo.due(now = 10_000).isEmpty())
        assertEquals(1, repo.due(now = 10_000 + Backoff.delayMs(0)).size)
        repeat(Backoff.MAX_ATTEMPTS_BEFORE_FAILED) { repo.markBatchFailed(listOf(dao.byId(c.captureId)!!), "unreachable", permanent = false, now = 20_000) }
        row = dao.byId(c.captureId)!!
        assertEquals(SyncState.FAILED, row.syncState)
        assertEquals(false, row.permanent)
        // never abandoned: still due again after the long backoff, without any user action
        assertTrue(repo.due(now = 20_000).isEmpty())
        assertEquals(1, repo.due(now = 20_000 + Backoff.MAX_MS).size)
        assertEquals(1, repo.retryFailed())
        assertEquals(SyncState.PENDING, dao.byId(c.captureId)!!.syncState)
    }

    @Test fun partialAcknowledgementKeepsUnansweredItemsPending() = runTest {
        val a = (repo.save("https://instagram.com/reel/P1", null) as CaptureRepository.SaveOutcome.Saved).capture
        val b = (repo.save("https://instagram.com/reel/P2", null) as CaptureRepository.SaveOutcome.Saved).capture
        repo.markSyncing(listOf(a, b))
        assertEquals(SyncState.SYNCING, dao.byId(a.captureId)!!.syncState)
        repo.applyResults(listOf(a, b), listOf(CaptureResult(a.captureId, "created", "i1", null)))
        assertEquals(SyncState.SYNCED, dao.byId(a.captureId)!!.syncState)
        assertEquals(SyncState.PENDING, dao.byId(b.captureId)!!.syncState)
        assertEquals(1, repo.due().size)
    }

    @Test fun crashMidRequestLeavesRowsResendable() = runTest {
        val a = (repo.save("https://instagram.com/reel/C1", null) as CaptureRepository.SaveOutcome.Saved).capture
        repo.markSyncing(listOf(a))
        assertEquals(1, repo.due().size)  // 'syncing' rows are due again after a restart
        assertEquals(1, repo.resetInFlight())
        assertEquals(SyncState.PENDING, dao.byId(a.captureId)!!.syncState)
    }

    @Test fun permanentRejectionFailsImmediatelyAndIsNotAutoRetried() = runTest {
        val c = (repo.save(reel, null) as CaptureRepository.SaveOutcome.Saved).capture
        repo.markBatchFailed(listOf(c), "token rejected", permanent = true)
        val row = dao.byId(c.captureId)!!
        assertEquals(SyncState.FAILED, row.syncState); assertTrue(row.permanent)
        assertTrue(repo.due(now = System.currentTimeMillis() + Backoff.MAX_MS * 10).isEmpty())
        assertEquals(1, repo.retryFailed())  // after fixing settings
        assertEquals(1, repo.due().size)
    }
}
