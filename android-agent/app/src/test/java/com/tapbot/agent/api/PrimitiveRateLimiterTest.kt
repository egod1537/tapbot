package com.tapbot.agent.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrimitiveRateLimiterTest {
    @Test
    fun rejectsCommandsBeyondLimitAndReportsRetryDelay() {
        var now = 1_000L
        val limiter = SlidingWindowRateLimiter(limit = 2, windowMs = 1_000) { now }

        assertTrue(limiter.tryAcquire().allowed)
        assertTrue(limiter.tryAcquire().allowed)
        val rejected = limiter.tryAcquire()
        assertFalse(rejected.allowed)
        assertEquals(1_000, rejected.retryAfterMs)

        now = 2_000
        assertTrue(limiter.tryAcquire().allowed)
    }
}
