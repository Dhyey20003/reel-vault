package app.reelvault.core

/** Retry delay policy for failed syncs: 30s, 1m, 2m, 4m ... capped at 30 minutes. */
object Backoff {
    const val BASE_MS = 30_000L
    const val MAX_MS = 30L * 60 * 1000
    const val MAX_ATTEMPTS_BEFORE_FAILED = 8

    fun delayMs(attempt: Int): Long {
        val a = attempt.coerceAtLeast(0).coerceAtMost(20)
        val d = BASE_MS shl a
        return if (d <= 0 || d > MAX_MS) MAX_MS else d
    }

    fun nextAttemptAt(nowMs: Long, attempt: Int): Long = nowMs + delayMs(attempt)
}
