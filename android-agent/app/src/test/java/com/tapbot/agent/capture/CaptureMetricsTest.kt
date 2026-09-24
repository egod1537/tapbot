package com.tapbot.agent.capture

import org.junit.Assert.assertEquals
import org.junit.Test

class CaptureMetricsTest {
    @Test
    fun calculatesFpsBitrateAndLastEncodeLatency() {
        val metrics = CaptureMetrics(windowMs = 2_000)
        metrics.record(CaptureMetric(1_000, 100_000, 2.0, 4.0))
        metrics.record(CaptureMetric(1_050, 100_000, 2.5, 5.0))
        metrics.record(CaptureMetric(1_100, 100_000, 3.0, 6.0))

        val result = metrics.snapshot(nowMs = 1_100)

        assertEquals(20.0, result.fps, 0.01)
        assertEquals(24_000_000, result.bitrate)
        assertEquals(3.0, result.lastCaptureLatencyMs ?: 0.0, 0.01)
        assertEquals(6.0, result.lastEncodeLatencyMs ?: 0.0, 0.01)
    }

    @Test
    fun expiresOldSamplesInsteadOfReportingStaleFps() {
        val metrics = CaptureMetrics(windowMs = 2_000)
        metrics.record(CaptureMetric(1_000, 10, 1.0, 1.0))

        val result = metrics.snapshot(nowMs = 3_001)

        assertEquals(0.0, result.fps, 0.0)
        assertEquals(0, result.bitrate)
        assertEquals(null, result.lastCaptureLatencyMs)
        assertEquals(null, result.lastEncodeLatencyMs)
    }
}
