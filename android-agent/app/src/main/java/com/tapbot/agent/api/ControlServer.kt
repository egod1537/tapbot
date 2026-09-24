package com.tapbot.agent.api

import android.util.Log
import com.tapbot.agent.accessibility.ActionExecutionResult
import com.tapbot.agent.accessibility.ActionOutcome
import com.tapbot.agent.accessibility.TapBotAccessibilityService
import com.tapbot.agent.capture.CaptureNotReadyException
import com.tapbot.agent.capture.ScreenCaptureProvider
import com.tapbot.agent.capture.ScreenFrame
import com.tapbot.agent.state.AgentStateStore
import com.tapbot.agent.system.DeviceInfoProvider
import fi.iki.elonen.NanoHTTPD
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Instant
import java.util.Base64
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

class ControlServer(
    port: Int,
    private val apiToken: String,
    private val captureProvider: ScreenCaptureProvider,
) : NanoHTTPD(port), AutoCloseable {
    private val running = AtomicBoolean(false)
    private val viewerSessions = ConcurrentHashMap<String, Long>()
    private val requestIds = ThreadLocal<String>()
    private val tapRateLimiter = SlidingWindowRateLimiter(limit = 10)
    private val swipeRateLimiter = SlidingWindowRateLimiter(limit = 4)
    private val globalActionRateLimiter = SlidingWindowRateLimiter(limit = 6)

    fun startServer() {
        try {
            start(SOCKET_READ_TIMEOUT, false)
            running.set(true)
            AgentStateStore.update {
                it.copy(serverRunning = true, serverPort = listeningPort, lastError = null)
            }
            Log.i(TAG, "Control server started on port $listeningPort")
        } catch (error: Exception) {
            running.set(false)
            AgentStateStore.update {
                it.copy(serverRunning = false, lastError = "Server bind failed: ${error.message}")
            }
            Log.e(TAG, "Control server bind failed", error)
            throw error
        }
    }

    override fun serve(session: IHTTPSession): Response {
        requestIds.set(UUID.randomUUID().toString())
        try {
            if (session.method == Method.OPTIONS) return cors(emptyResponse())
            if (session.method == Method.GET && session.uri == "/viewer") {
                return secure(viewer())
            }
            if (!isAuthorized(session)) {
                return cors(jsonError(Response.Status.UNAUTHORIZED, "unauthorized", "Valid Bearer token required"))
            }

            return try {
                cors(route(session))
            } catch (error: JSONException) {
                cors(jsonError(Response.Status.BAD_REQUEST, "invalid_json", error.message ?: "Invalid JSON body"))
            } catch (error: Exception) {
                AgentStateStore.update { it.copy(lastError = "API request failed: ${error.message}") }
                Log.e(TAG, "API request failed: ${session.method} ${session.uri}", error)
                cors(jsonError(Response.Status.INTERNAL_ERROR, "internal_error", error.message ?: "Request failed"))
            }
        } finally {
            requestIds.remove()
        }
    }

    private fun route(session: IHTTPSession): Response = when {
        session.method == Method.GET && session.uri in STATUS_PATHS ->
            json(
                Response.Status.OK,
                ApiModels.status(
                    requestId(),
                    AgentStateStore.snapshot(),
                    DeviceInfoProvider.current(),
                ).toString(),
            )

        session.method == Method.POST && session.uri == "/api/viewer/session" -> viewerSession()
        session.method == Method.GET && session.uri in SCREENSHOT_PATHS -> screenshot()
        session.method == Method.GET && session.uri in SCREENSHOT_METADATA_PATHS -> screenshotMetadata()
        session.method == Method.GET && session.uri in STREAM_PATHS -> stream()
        session.method == Method.GET && session.uri in STREAM_STATUS_PATHS -> streamStatus()
        session.method == Method.POST && session.uri in TAP_PATHS -> tap(readJson(session))
        session.method == Method.POST && session.uri in SWIPE_PATHS -> swipe(readJson(session))
        session.method == Method.POST && session.uri in BACK_PATHS -> globalAction("back")
        session.method == Method.POST && session.uri in HOME_PATHS -> globalAction("home")
        session.method == Method.POST && session.uri in RECENTS_PATHS -> globalAction("recents")
        session.method == Method.GET && session.uri in UI_TREE_PATHS ->
            jsonError(
                Response.Status.NOT_IMPLEMENTED,
                "ui_tree_unavailable",
                "UI tree export is optional and is not enabled in this build",
            )
        session.uri.startsWith("/api/") ->
            jsonError(Response.Status.METHOD_NOT_ALLOWED, "method_not_allowed", "Unknown route or method")
        else -> jsonError(Response.Status.NOT_FOUND, "not_found", "Route not found")
    }

    private fun screenshot(): Response {
        val frame = try {
            captureProvider.capture()
        } catch (error: CaptureNotReadyException) {
            return jsonError(Response.Status.SERVICE_UNAVAILABLE, "capture_not_ready", error.message ?: "No frame")
        }
        return newFixedLengthResponse(
            Response.Status.OK,
            frame.mimeType,
            ByteArrayInputStream(frame.bytes),
            frame.bytes.size.toLong(),
        ).apply { addFrameHeaders(frame, requestId()) }
    }

    private fun screenshotMetadata(): Response {
        val frame = try {
            captureProvider.capture()
        } catch (error: CaptureNotReadyException) {
            return jsonError(Response.Status.SERVICE_UNAVAILABLE, "capture_not_ready", error.message ?: "No frame")
        }
        return json(
            Response.Status.OK,
            ApiModels.screenshot(requestId(), frame).toString(),
        )
    }

    private fun stream(): Response {
        if (!AgentStateStore.snapshot().captureReady) {
            return jsonError(Response.Status.SERVICE_UNAVAILABLE, "capture_not_ready", "Screen capture permission is required")
        }
        val input = LatestFrameInputStream(captureProvider) { running.get() }
        Log.i(TAG, "MJPEG client connected")
        return newChunkedResponse(
            Response.Status.OK,
            "multipart/x-mixed-replace; boundary=$MJPEG_BOUNDARY",
            input,
        ).apply {
            addHeader("Cache-Control", "no-store, no-cache, must-revalidate")
            addHeader("Pragma", "no-cache")
        }
    }

    private fun streamStatus(): Response {
        val state = AgentStateStore.snapshot()
        return json(
            Response.Status.OK,
            ApiModels.stream(
                requestId(),
                captureProvider.status(),
                state.connectedClients,
            ).toString(),
        )
    }

    private fun viewerSession(): Response {
        val sessionId = ByteArray(24)
            .also(SecureRandom()::nextBytes)
            .let { Base64.getUrlEncoder().withoutPadding().encodeToString(it) }
        viewerSessions.entries.removeIf { it.value < System.currentTimeMillis() }
        viewerSessions[sessionId] = System.currentTimeMillis() + VIEWER_SESSION_TTL_MS
        return json(Response.Status.OK, ApiModels.success(requestId())).apply {
            addHeader(
                "Set-Cookie",
                "$VIEWER_COOKIE=$sessionId; Path=/api; HttpOnly; SameSite=Strict; Max-Age=${VIEWER_SESSION_TTL_MS / 1_000}",
            )
        }
    }

    private fun tap(payload: JSONObject): Response {
        remoteControlDisabled()?.let { return it }
        val display = AgentStateStore.snapshot().display
        val x = payload.getDouble("x").toFloat()
        val y = payload.getDouble("y").toFloat()
        val duration = payload.optLong("duration_ms", TapBotAccessibilityService.DEFAULT_TAP_DURATION_MS)
        InputValidator.point(x, y, display.logicalWidth, display.logicalHeight)?.let {
            return jsonError(Response.Status.BAD_REQUEST, it.code, it.message)
        }
        InputValidator.duration(duration)?.let {
            return jsonError(Response.Status.BAD_REQUEST, it.code, it.message)
        }
        val service = accessibilityService() ?: return accessibilityDisabled()
        enforceRateLimit(tapRateLimiter, "tap")?.let { return it }
        Log.i(TAG, "Input command: tap request_id=${requestId()} x=$x y=$y duration_ms=$duration")
        return actionResponse("tap", service.tap(x, y, duration))
    }

    private fun swipe(payload: JSONObject): Response {
        remoteControlDisabled()?.let { return it }
        val display = AgentStateStore.snapshot().display
        val x1 = payload.getDouble("x1").toFloat()
        val y1 = payload.getDouble("y1").toFloat()
        val x2 = payload.getDouble("x2").toFloat()
        val y2 = payload.getDouble("y2").toFloat()
        val duration = payload.optLong("duration_ms", 450)
        InputValidator.point(x1, y1, display.logicalWidth, display.logicalHeight)?.let {
            return jsonError(Response.Status.BAD_REQUEST, it.code, "Swipe start: ${it.message}")
        }
        InputValidator.point(x2, y2, display.logicalWidth, display.logicalHeight)?.let {
            return jsonError(Response.Status.BAD_REQUEST, it.code, "Swipe end: ${it.message}")
        }
        InputValidator.duration(duration, minimumMs = 50)?.let {
            return jsonError(Response.Status.BAD_REQUEST, it.code, it.message)
        }
        val service = accessibilityService() ?: return accessibilityDisabled()
        enforceRateLimit(swipeRateLimiter, "swipe")?.let { return it }
        Log.i(TAG, "Input command: swipe request_id=${requestId()} duration_ms=$duration")
        return actionResponse("swipe", service.swipe(x1, y1, x2, y2, duration))
    }

    private fun globalAction(name: String): Response {
        remoteControlDisabled()?.let { return it }
        val service = accessibilityService() ?: return accessibilityDisabled()
        enforceRateLimit(globalActionRateLimiter, name)?.let { return it }
        val result = when (name) {
            "back" -> service.back()
            "home" -> service.home()
            "recents" -> service.recents()
            else -> error("Unknown global action: $name")
        }
        Log.i(TAG, "Input command: $name request_id=${requestId()}")
        return actionResponse(name, result)
    }

    private fun accessibilityService(): TapBotAccessibilityService? =
        TapBotAccessibilityService.current()

    private fun accessibilityDisabled(): Response = jsonError(
        Response.Status.SERVICE_UNAVAILABLE,
        "accessibility_disabled",
        "Enable the TapBot accessibility service before sending input",
    )

    private fun remoteControlDisabled(): Response? =
        if (AgentStateStore.snapshot().remoteControlEnabled) {
            null
        } else {
            jsonError(
                Response.Status.FORBIDDEN,
                "remote_control_disabled",
                "Enable Remote Control in the Android app before sending input",
            )
        }

    private fun enforceRateLimit(
        limiter: SlidingWindowRateLimiter,
        command: String,
    ): Response? {
        val decision = limiter.tryAcquire()
        if (decision.allowed) return null
        return jsonError(
            Response.Status.TOO_MANY_REQUESTS,
            "rate_limited",
            "$command rate limit exceeded; retry after ${decision.retryAfterMs}ms",
        ).apply {
            addHeader("Retry-After", ((decision.retryAfterMs + 999) / 1_000).toString())
        }
    }

    private fun actionResponse(
        command: String,
        result: ActionExecutionResult,
    ): Response {
        val fields = JSONObject()
            .put("action_id", result.actionId)
            .put("command", command)
            .put("state", result.outcome.name.lowercase())
            .put("retry_policy", "do_not_retry_automatically")
        return when (result.outcome) {
            ActionOutcome.COMPLETED -> json(
                Response.Status.OK,
                ApiModels.success(requestId(), fields),
            )
            ActionOutcome.DISPATCHED -> json(
                Response.Status.ACCEPTED,
                ApiModels.success(requestId(), fields),
            )
            ActionOutcome.CANCELLED -> actionError(
                Response.Status.CONFLICT,
                "gesture_cancelled",
                "Android cancelled the $command gesture; it may have partially executed",
                fields,
            )
            ActionOutcome.REJECTED -> actionError(
                Response.Status.CONFLICT,
                "gesture_dispatch_failed",
                "Android rejected the $command command",
                fields,
            )
            ActionOutcome.TIMEOUT -> actionError(
                Response.Status.REQUEST_TIMEOUT,
                "gesture_result_timeout",
                "$command callback timed out; execution outcome is unknown",
                fields.put("outcome_unknown", true),
            )
            ActionOutcome.BUSY -> actionError(
                Response.Status.CONFLICT,
                "gesture_busy",
                "Another gesture is still executing",
                fields,
            )
        }
    }

    private fun actionError(
        status: Response.IStatus,
        code: String,
        message: String,
        fields: JSONObject,
    ): Response = json(
        status,
        ApiModels.error(requestId(), code, message, fields),
    )

    private fun readJson(session: IHTTPSession): JSONObject {
        val files = HashMap<String, String>()
        session.parseBody(files)
        val body = files["postData"].orEmpty()
        if (body.isBlank()) throw JSONException("JSON request body is required")
        return JSONObject(body)
    }

    private fun isAuthorized(session: IHTTPSession): Boolean {
        val supplied = session.headers["authorization"]
            ?.removePrefix("Bearer ")
            ?.takeIf { it.length != session.headers["authorization"]?.length }
        if (
            supplied != null && MessageDigest.isEqual(
                apiToken.toByteArray(StandardCharsets.UTF_8),
                supplied.toByteArray(StandardCharsets.UTF_8),
            )
        ) {
            return true
        }
        if (session.method != Method.GET) return false
        val viewerSession = session.headers["cookie"]
            ?.split(';')
            ?.map { it.trim() }
            ?.firstOrNull { it.startsWith("$VIEWER_COOKIE=") }
            ?.substringAfter('=')
            ?: return false
        val expiresAt = viewerSessions[viewerSession] ?: return false
        if (expiresAt < System.currentTimeMillis()) {
            viewerSessions.remove(viewerSession)
            return false
        }
        return session.uri in VIEWER_SESSION_PATHS
    }

    private fun jsonError(status: Response.IStatus, code: String, message: String): Response =
        json(status, ApiModels.error(requestId(), code, message))

    private fun json(status: Response.IStatus, body: String): Response =
        newFixedLengthResponse(status, "application/json; charset=utf-8", body).apply {
            addHeader("X-Request-Id", requestId())
        }

    private fun requestId(): String = requestIds.get() ?: "request-id-unavailable"

    private fun emptyResponse(): Response = newFixedLengthResponse(Response.Status.NO_CONTENT, MIME_PLAINTEXT, "")

    private fun cors(response: Response): Response = response.apply {
        addHeader("X-Request-Id", requestId())
        addHeader("Access-Control-Allow-Origin", "*")
        addHeader("Access-Control-Allow-Headers", "Authorization, Content-Type")
        addHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        addHeader("Access-Control-Expose-Headers", "X-Request-Id, X-Frame-Id, X-Screen-Width, X-Screen-Height, X-Rotation, X-Captured-At")
        addHeader("X-Content-Type-Options", "nosniff")
    }

    private fun secure(response: Response): Response = response.apply {
        addHeader("Cache-Control", "no-store")
        addHeader("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
        addHeader("X-Content-Type-Options", "nosniff")
        addHeader("X-Frame-Options", "DENY")
    }

    private fun viewer(): Response = newFixedLengthResponse(
        Response.Status.OK,
        "text/html; charset=utf-8",
        VIEWER_HTML,
    )

    override fun close() {
        running.set(false)
        stop()
        AgentStateStore.update { it.copy(serverRunning = false, connectedClients = 0) }
        Log.i(TAG, "Control server stopped")
    }

    private class LatestFrameInputStream(
        private val captureProvider: ScreenCaptureProvider,
        private val keepRunning: () -> Boolean,
    ) : InputStream() {
        private var closed = false
        private var current = ByteArray(0)
        private var offset = 0
        private var lastFrameId = -1L

        init {
            AgentStateStore.update { it.copy(connectedClients = it.connectedClients + 1) }
        }

        override fun read(): Int {
            val one = ByteArray(1)
            return if (read(one, 0, 1) < 0) -1 else one[0].toInt() and 0xff
        }

        override fun read(buffer: ByteArray, targetOffset: Int, length: Int): Int {
            if (closed || !keepRunning()) return -1
            while (offset >= current.size) {
                val frame = runCatching(captureProvider::capture).getOrNull()
                if (frame != null && frame.frameId != lastFrameId) {
                    current = encodePart(frame)
                    offset = 0
                    lastFrameId = frame.frameId
                    break
                }
                if (closed || !keepRunning()) return -1
                Thread.sleep(20)
            }
            val count = minOf(length, current.size - offset)
            current.copyInto(buffer, targetOffset, offset, offset + count)
            offset += count
            return count
        }

        override fun close() {
            if (closed) return
            closed = true
            AgentStateStore.update {
                it.copy(connectedClients = (it.connectedClients - 1).coerceAtLeast(0))
            }
            Log.i(TAG, "MJPEG client disconnected")
        }

        private fun encodePart(frame: ScreenFrame): ByteArray = ByteArrayOutputStream().use { output ->
            output.write("--$MJPEG_BOUNDARY\r\n".toByteArray())
            output.write("Content-Type: ${frame.mimeType}\r\n".toByteArray())
            output.write("Content-Length: ${frame.bytes.size}\r\n".toByteArray())
            output.write("X-Frame-Id: ${frame.frameId}\r\n".toByteArray())
            output.write("X-Screen-Width: ${frame.width}\r\n".toByteArray())
            output.write("X-Screen-Height: ${frame.height}\r\n".toByteArray())
            output.write("X-Rotation: ${frame.rotation}\r\n".toByteArray())
            output.write("X-Captured-At-Ms: ${frame.capturedAtMs}\r\n\r\n".toByteArray())
            output.write(frame.bytes)
            output.write("\r\n".toByteArray())
            output.toByteArray()
        }
    }

    companion object {
        private const val TAG = "TapBotControlServer"
        private const val MJPEG_BOUNDARY = "tapbotframe"
        private const val VIEWER_COOKIE = "tapbot_viewer"
        private const val VIEWER_SESSION_TTL_MS = 8 * 60 * 60 * 1_000L
        private val STATUS_PATHS = setOf("/api/status", "/api/v1/status")
        private val TAP_PATHS = setOf("/api/tap", "/api/v1/tap", "/api/v1/input/tap")
        private val SWIPE_PATHS = setOf(
            "/api/swipe",
            "/api/v1/swipe",
            "/api/v1/input/swipe",
        )
        private val BACK_PATHS = setOf("/api/back", "/api/v1/back", "/api/v1/input/back")
        private val HOME_PATHS = setOf("/api/home", "/api/v1/home", "/api/v1/input/home")
        private val RECENTS_PATHS = setOf(
            "/api/recents",
            "/api/v1/recents",
            "/api/v1/input/recents",
        )
        private val UI_TREE_PATHS = setOf("/api/ui-tree", "/api/v1/ui-tree")
        private val SCREENSHOT_PATHS = setOf(
            "/api/screenshot",
            "/api/v1/screenshot",
            "/api/v1/screen",
        )
        private val SCREENSHOT_METADATA_PATHS = setOf(
            "/api/screenshot/metadata",
            "/api/v1/screenshot/metadata",
        )
        private val STREAM_PATHS = setOf(
            "/api/stream",
            "/api/v1/stream",
            "/api/v1/screen/stream",
        )
        private val STREAM_STATUS_PATHS = setOf(
            "/api/stream/status",
            "/api/v1/stream/status",
        )
        private val VIEWER_SESSION_PATHS =
            SCREENSHOT_PATHS + SCREENSHOT_METADATA_PATHS + STREAM_PATHS + STREAM_STATUS_PATHS

        private fun Response.addFrameHeaders(frame: ScreenFrame, requestId: String) {
            addHeader("Cache-Control", "no-store")
            addHeader("X-Request-Id", requestId)
            addHeader("X-Frame-Id", frame.frameId.toString())
            addHeader("X-Screen-Width", frame.width.toString())
            addHeader("X-Screen-Height", frame.height.toString())
            addHeader("X-Rotation", frame.rotation.toString())
            addHeader("X-Captured-At", Instant.ofEpochMilli(frame.capturedAtMs).toString())
            addHeader("X-Captured-At-Ms", frame.capturedAtMs.toString())
            addHeader("X-Frame-Width", frame.width.toString())
            addHeader("X-Frame-Height", frame.height.toString())
        }

        private val VIEWER_HTML = """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width,initial-scale=1">
              <title>TapBot Screen</title>
              <style>
                body{margin:0;background:#11151a;color:#e8edf2;font:14px system-ui;display:grid;place-items:center;min-height:100vh}
                main{width:min(94vw,1100px);display:grid;gap:12px}.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
                input{flex:1;min-width:260px;padding:10px;background:#20262d;border:1px solid #46515d;color:white}
                button{padding:10px 16px;background:#2d72d2;border:0;color:white;cursor:pointer}#status{color:#9fb1c3}
                img{display:block;max-width:100%;max-height:82vh;margin:auto;background:#000;border:1px solid #303944}
              </style>
            </head>
            <body><main><div class="bar"><strong>TapBot Live Screen</strong><span id="status">Disconnected</span></div>
              <div class="bar"><input id="token" type="password" placeholder="Bearer token from Android app" autocomplete="off"><button id="connect">Connect</button></div>
              <img id="screen" alt="Android live screen">
            </main><script>
              const status=document.getElementById('status'),screen=document.getElementById('screen'),token=document.getElementById('token');
              let statusTimer;
              async function updateStatus(){try{const r=await fetch('/api/stream/status');if(!r.ok)throw 0;const s=await r.json();status.textContent=s.codec.toUpperCase()+' · '+s.width+'×'+s.height+' · '+s.fps.toFixed(1)+' FPS · '+(s.capture_latency_ms??0).toFixed(1)+' ms capture · '+(s.encode_latency_ms??0).toFixed(1)+' ms encode · '+(s.frame_age_ms??0)+' ms age · '+s.clients+' client(s)'}catch{status.textContent='Reconnecting…'}}
              async function connect(){status.textContent='Authenticating…';const r=await fetch('/api/viewer/session',{method:'POST',headers:{Authorization:'Bearer '+token.value}});if(!r.ok){status.textContent='Authentication failed';return}token.value='';screen.src='/api/stream?now='+Date.now();clearInterval(statusTimer);statusTimer=setInterval(updateStatus,1000);updateStatus()}
              document.getElementById('connect').onclick=connect;screen.onerror=()=>{status.textContent='Stream disconnected';setTimeout(()=>{screen.src='/api/stream?retry='+Date.now()},1000)};
            </script></body></html>
        """.trimIndent()
    }
}
