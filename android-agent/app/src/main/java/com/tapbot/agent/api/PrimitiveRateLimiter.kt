package com.tapbot.agent.api

data class RateLimitDecision(
    val allowed: Boolean,
    val retryAfterMs: Long = 0,
)

class SlidingWindowRateLimiter(
    private val limit: Int,
    private val windowMs: Long = 1_000,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val acceptedAt = ArrayDeque<Long>()

    init {
        require(limit > 0) { "limit must be positive" }
        require(windowMs > 0) { "windowMs must be positive" }
    }

    @Synchronized
    fun tryAcquire(): RateLimitDecision {
        val now = clock()
        while (acceptedAt.isNotEmpty() && now - acceptedAt.first() >= windowMs) {
            acceptedAt.removeFirst()
        }
        if (acceptedAt.size >= limit) {
            return RateLimitDecision(
                allowed = false,
                retryAfterMs = (windowMs - (now - acceptedAt.first())).coerceAtLeast(1),
            )
        }
        acceptedAt.addLast(now)
        return RateLimitDecision(allowed = true)
    }
}
