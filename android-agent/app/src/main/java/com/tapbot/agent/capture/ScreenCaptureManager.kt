package com.tapbot.agent.capture

import android.annotation.SuppressLint
import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import android.os.PowerManager
import android.util.Log
import com.tapbot.agent.state.DisplayState
import com.tapbot.agent.state.AgentStateStore
import com.tapbot.agent.system.DisplayInfoProvider
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

class ScreenCaptureManager(
    private val context: Context,
    private val targetFps: Int = 20,
    private val jpegQuality: Int = 80,
) : ScreenCaptureProvider, AutoCloseable {
    private val projectionManager =
        context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    private val displayManager =
        context.getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
    private val latestFrame = AtomicReference<ScreenFrame?>(null)
    private val activeDisplay = AtomicReference<DisplayState?>(null)
    private val frameIds = AtomicLong(0)
    private val lastEncodedAtNs = AtomicLong(0)
    private val metrics = CaptureMetrics()
    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var captureThread: HandlerThread? = null
    private var captureHandler: Handler? = null

    private val displayListener = object : DisplayManager.DisplayListener {
        override fun onDisplayAdded(displayId: Int) = Unit
        override fun onDisplayRemoved(displayId: Int) = Unit

        override fun onDisplayChanged(displayId: Int) {
            reconfigureForDisplayChange()
        }
    }

    private val projectionCallback = object : MediaProjection.Callback() {
        override fun onStop() {
            Log.w(TAG, "MediaProjection revoked")
            stopInternal(stopProjection = false, error = "MediaProjection permission revoked")
        }
    }

    @SuppressLint("WrongConstant")
    @Synchronized
    fun start(resultCode: Int, resultData: Intent) {
        require(resultCode == Activity.RESULT_OK) { "Screen capture permission was not granted" }
        stopInternal(stopProjection = true)

        val display = DisplayInfoProvider(context).current()
        require(display.logicalWidth > 0 && display.logicalHeight > 0) {
            "Logical display size is unavailable"
        }
        val thread = HandlerThread("tapbot-screen-capture").apply { start() }
        val handler = Handler(thread.looper)
        captureThread = thread
        captureHandler = handler

        try {
            val mediaProjection = projectionManager.getMediaProjection(resultCode, resultData)
                ?: error("Could not create MediaProjection")
            mediaProjection.registerCallback(projectionCallback, handler)
            projection = mediaProjection

            val reader = createImageReader(display, handler)
            imageReader = reader
            activeDisplay.set(display)
            virtualDisplay = mediaProjection.createVirtualDisplay(
                "TapBotScreen",
                display.logicalWidth,
                display.logicalHeight,
                display.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface,
                null,
                handler,
            )
            displayManager.registerDisplayListener(displayListener, handler)
            AgentStateStore.update {
                it.copy(
                    captureReady = true,
                    streamRunning = true,
                    display = display,
                    lastError = null,
                )
            }
            Log.i(TAG, "Screen capture started: ${display.logicalWidth}x${display.logicalHeight}")
        } catch (error: Exception) {
            stopInternal(stopProjection = true, error = error.message ?: "Capture start failed")
            throw error
        }
    }

    override fun capture(): ScreenFrame = latestFrame.get()
        ?: throw CaptureNotReadyException("No captured frame is available")

    override fun status(): ScreenCaptureStatus {
        val display = activeDisplay.get() ?: DisplayInfoProvider(context).current()
        val frame = latestFrame.get()
        val metric = metrics.snapshot()
        val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        val keyguardManager = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        return ScreenCaptureStatus(
            running = AgentStateStore.snapshot().captureReady,
            codec = "mjpeg",
            transport = "http-multipart",
            width = frame?.width ?: display.logicalWidth,
            height = frame?.height ?: display.logicalHeight,
            rotation = frame?.rotation ?: display.rotation,
            targetFps = targetFps,
            estimatedFps = metric.fps,
            estimatedBitrate = metric.bitrate,
            lastCaptureLatencyMs = metric.lastCaptureLatencyMs,
            lastEncodeLatencyMs = metric.lastEncodeLatencyMs,
            lastFrameAgeMs = frame?.let {
                (System.currentTimeMillis() - it.capturedAtMs).coerceAtLeast(0)
            },
            lastFrameId = frame?.frameId,
            screenInteractive = powerManager.isInteractive,
            deviceLocked = keyguardManager.isDeviceLocked,
        )
    }

    @Synchronized
    fun stop() {
        stopInternal(stopProjection = true)
    }

    override fun close() = stop()

    private fun onImageAvailable(reader: ImageReader) {
        val image = reader.acquireLatestImage() ?: return
        try {
            val now = System.nanoTime()
            val minimumIntervalNs = 1_000_000_000L / targetFps.coerceAtLeast(1)
            val previous = lastEncodedAtNs.get()
            if (now - previous < minimumIntervalNs || !lastEncodedAtNs.compareAndSet(previous, now)) {
                return
            }
            val encodeStarted = System.nanoTime()
            val capturedAt = System.currentTimeMillis()
            val captureLatencyMs = if (image.timestamp > 0) {
                ((encodeStarted - image.timestamp).coerceAtLeast(0)) / 1_000_000.0
            } else {
                0.0
            }
            val jpeg = imageToJpeg(image)
            val encodeLatencyMs = (System.nanoTime() - encodeStarted) / 1_000_000.0
            val display = activeDisplay.get() ?: DisplayInfoProvider(context).current()
            val frame = ScreenFrame(
                bytes = jpeg,
                mimeType = "image/jpeg",
                capturedAtMs = capturedAt,
                width = image.width,
                height = image.height,
                rotation = display.rotation,
                frameId = frameIds.incrementAndGet(),
                captureLatencyMs = captureLatencyMs,
                encodeLatencyMs = encodeLatencyMs,
            )
            latestFrame.set(frame)
            metrics.record(
                CaptureMetric(capturedAt, jpeg.size, captureLatencyMs, encodeLatencyMs),
            )
            AgentStateStore.update {
                it.copy(frameId = frame.frameId, capturedAtMs = capturedAt, lastError = null)
            }
        } catch (error: Exception) {
            AgentStateStore.update {
                it.copy(lastError = "Screen encoder failed: ${error.message}")
            }
            Log.e(TAG, "Screen encoder failed", error)
        } finally {
            image.close()
        }
    }

    private fun imageToJpeg(image: Image): ByteArray {
        val plane = image.planes.firstOrNull() ?: error("Capture image has no planes")
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val paddedWidth = image.width + (rowStride - pixelStride * image.width) / pixelStride
        val padded = Bitmap.createBitmap(paddedWidth, image.height, Bitmap.Config.ARGB_8888)
        return try {
            padded.copyPixelsFromBuffer(plane.buffer)
            val cropped = if (paddedWidth == image.width) {
                padded
            } else {
                Bitmap.createBitmap(padded, 0, 0, image.width, image.height)
            }
            try {
                ByteArrayOutputStream().use { output ->
                    check(cropped.compress(Bitmap.CompressFormat.JPEG, jpegQuality, output)) {
                        "JPEG compression failed"
                    }
                    output.toByteArray()
                }
            } finally {
                if (cropped !== padded) cropped.recycle()
            }
        } finally {
            padded.recycle()
        }
    }

    @SuppressLint("WrongConstant")
    private fun createImageReader(display: DisplayState, handler: Handler): ImageReader =
        ImageReader.newInstance(
            display.logicalWidth,
            display.logicalHeight,
            PixelFormat.RGBA_8888,
            2,
        ).also { it.setOnImageAvailableListener(::onImageAvailable, handler) }

    @Synchronized
    private fun reconfigureForDisplayChange() {
        val handler = captureHandler ?: return
        val current = activeDisplay.get() ?: return
        val updated = DisplayInfoProvider(context).current()
        if (
            current.logicalWidth == updated.logicalWidth &&
            current.logicalHeight == updated.logicalHeight &&
            current.rotation == updated.rotation
        ) {
            return
        }

        try {
            val replacement = createImageReader(updated, handler)
            virtualDisplay?.resize(
                updated.logicalWidth,
                updated.logicalHeight,
                updated.densityDpi,
            )
            virtualDisplay?.surface = replacement.surface
            imageReader?.setOnImageAvailableListener(null, null)
            imageReader?.close()
            imageReader = replacement
            activeDisplay.set(updated)
            latestFrame.set(null)
            metrics.clear()
            AgentStateStore.update {
                it.copy(
                    display = updated,
                    frameId = null,
                    capturedAtMs = null,
                    lastError = null,
                )
            }
            Log.i(
                TAG,
                "Capture geometry changed to ${updated.logicalWidth}x${updated.logicalHeight} rotation=${updated.rotation}",
            )
        } catch (error: Exception) {
            AgentStateStore.update {
                it.copy(lastError = "Display reconfiguration failed: ${error.message}")
            }
            Log.e(TAG, "Display reconfiguration failed", error)
        }
    }

    @Synchronized
    private fun stopInternal(stopProjection: Boolean, error: String? = null) {
        displayManager.unregisterDisplayListener(displayListener)
        imageReader?.setOnImageAvailableListener(null, null)
        virtualDisplay?.release()
        imageReader?.close()
        projection?.unregisterCallback(projectionCallback)
        if (stopProjection) projection?.stop()
        captureThread?.quitSafely()

        virtualDisplay = null
        imageReader = null
        projection = null
        captureHandler = null
        captureThread = null
        latestFrame.set(null)
        activeDisplay.set(null)
        lastEncodedAtNs.set(0)
        metrics.clear()
        AgentStateStore.update {
            it.copy(
                captureReady = false,
                streamRunning = false,
                frameId = null,
                capturedAtMs = null,
                lastError = error ?: it.lastError,
            )
        }
        Log.i(TAG, "Screen capture stopped")
    }

    companion object {
        private const val TAG = "TapBotCapture"
    }
}
