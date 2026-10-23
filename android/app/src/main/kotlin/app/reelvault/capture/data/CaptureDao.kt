package app.reelvault.capture.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface CaptureDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(capture: Capture): Long

    @Update
    suspend fun update(capture: Capture)

    @Query("SELECT * FROM captures ORDER BY created_at DESC")
    fun observeAll(): Flow<List<Capture>>

    @Query("SELECT * FROM captures WHERE normalized_url = :normalized LIMIT 1")
    suspend fun findByNormalized(normalized: String): Capture?

    @Query("SELECT * FROM captures WHERE capture_id = :id")
    suspend fun byId(id: String): Capture?

    /** Pending rows whose retry time has come, plus transient failures (never abandoned), plus rows stuck in 'syncing' after a crash. */
    @Query("SELECT * FROM captures WHERE ((sync_state = 'pending' OR sync_state = 'syncing') AND next_attempt_at <= :now) OR (sync_state = 'failed' AND permanent = 0 AND next_attempt_at <= :now) ORDER BY created_at LIMIT :limit")
    suspend fun due(now: Long, limit: Int = 100): List<Capture>

    @Query("SELECT COUNT(*) FROM captures WHERE sync_state = :state")
    fun observeCount(state: String): Flow<Int>

    @Query("UPDATE captures SET sync_state = 'pending', attempts = 0, next_attempt_at = 0, last_error = NULL, permanent = 0 WHERE sync_state = 'failed'")
    suspend fun retryFailed(): Int

    @Query("UPDATE captures SET next_attempt_at = 0 WHERE sync_state <> 'synced'")
    suspend fun makeAllDue(): Int

    @Query("UPDATE captures SET sync_state = 'pending' WHERE sync_state = 'syncing'")
    suspend fun resetInFlight(): Int

    @Query("DELETE FROM captures WHERE capture_id = :id")
    suspend fun delete(id: String)
}
