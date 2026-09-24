package com.tapbot.agent.capture

data class ScreenFrame(
    val bytes: ByteArray,
    val mimeType: String,
    val width: Int,
    val height: Int,
    val rotation: Int,
    val capturedAtMs: Long,
    val frameId: Long,
    val captureLatencyMs: Double,
    val encodeLatencyMs: Double,
)

data class ScreenCaptureStatus(
    val running: Boolean,
    val codec: String,
    val transport: String,
    val width: Int,
    val height: Int,
    val rotation: Int,
    val targetFps: Int,
    val estimatedFps: Double,
    val estimatedBitrate: Long,
    val lastCaptureLatencyMs: Double?,
    val lastEncodeLatencyMs: Double?,
    val lastFrameAgeMs: Long?,
    val lastFrameId: Long?,
    val screenInteractive: Boolean,
    val deviceLocked: Boolean,
)

class CaptureNotReadyException(message: String) : IllegalStateException(message)

interface ScreenCaptureProvider {
    /** Returns the latest complete frame using logical display coordinates. */
    @Throws(CaptureNotReadyException::class)
    fun capture(): ScreenFrame

    fun status(): ScreenCaptureStatus
}

internal data class CaptureMetric(
    val capturedAtMs: Long,
    val byteCount: Int,
    val captureLatencyMs: Double,
    val encodeLatencyMs: Double,
)

internal class CaptureMetrics(private val windowMs: Long = 2_000) {
    private val samples = ArrayDeque<CaptureMetric>()

    @Synchronized
    fun record(metric: CaptureMetric) {
        samples.addLast(metric)
        prune(metric.capturedAtMs)
    }

    @Synchronized
    fun snapshot(nowMs: Long = System.currentTimeMillis()): MetricsSnapshot {
        prune(nowMs)
        if (samples.isEmpty()) return MetricsSnapshot(0.0, 0, null, null)
        val first = samples.first()
        val last = samples.last()
        val elapsedMs = (last.capturedAtMs - first.capturedAtMs).coerceAtLeast(1)
        val fps = if (samples.size == 1) 0.0 else (samples.size - 1) * 1_000.0 / elapsedMs
        val bytes = samples.sumOf { it.byteCount.toLong() }
        val coveredMs = if (samples.size == 1) windowMs else elapsedMs
        val bitrate = bytes * 8_000L / coveredMs.coerceAtLeast(1)
        return MetricsSnapshot(
            fps,
            bitrate,
            last.captureLatencyMs,
            last.encodeLatencyMs,
        )
    }

    @Synchronized
    fun clear() = samples.clear()

    private fun prune(nowMs: Long) {
        while (samples.isNotEmpty() && nowMs - samples.first().capturedAtMs > windowMs) {
            samples.removeFirst()
        }
    }
}

internal data class MetricsSnapshot(
    val fps: Double,
    val bitrate: Long,
    val lastCaptureLatencyMs: Double?,
    val lastEncodeLatencyMs: Double?,
)
