package app.reelvault.capture

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.reelvault.capture.data.AppDatabase
import app.reelvault.capture.data.Capture
import app.reelvault.capture.data.CaptureRepository
import app.reelvault.capture.data.SyncState
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CaptureDaoTest {
    private lateinit var db: AppDatabase

    @Before fun setUp() {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), AppDatabase::class.java).build()
    }

    @After fun tearDown() { db.close() }

    @Test fun insertDedupAndRetryQueries() = runTest {
        val dao = db.captureDao()
        val repo = CaptureRepository(dao)
        val saved = repo.save("https://www.instagram.com/reel/XyZ/?igsh=1", null, now = 5)
        assertTrue(saved is CaptureRepository.SaveOutcome.Saved)
        assertTrue(repo.save("https://instagram.com/reel/XyZ", null) is CaptureRepository.SaveOutcome.AlreadyQueued)
        assertEquals(1, dao.due(now = 10).size)
        val c = dao.due(now = 10).first()
        dao.update(c.copy(syncState = SyncState.FAILED))
        assertEquals(0, dao.due(now = 10).size)
        assertEquals(1, dao.retryFailed())
        assertEquals(1, dao.due(now = 10).size)
        // primary key conflict is ignored, never crashes
        assertEquals(-1L, dao.insert(Capture(c.captureId, "x", null, null, 1)))
    }
}
