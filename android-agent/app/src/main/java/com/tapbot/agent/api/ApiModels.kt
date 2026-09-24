package com.tapbot.agent.api

import com.tapbot.agent.state.AgentState
import com.tapbot.agent.capture.ScreenCaptureStatus
import com.tapbot.agent.capture.ScreenFrame
import com.tapbot.agent.system.DeviceInfo
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

object ApiModels {
    fun status(requestId: String, state: AgentState, device: DeviceInfo): JSONObject =
        successObject(requestId).apply {
        put("remote_control_enabled", state.remoteControlEnabled)
        put("accessibility_enabled", state.accessibilityEnabled)
        put("capture_ready", state.captureReady)
        put("stream_running", state.streamRunning)
        put("server_running", state.serverRunning)
        put("server_port", state.serverPort)
        put("connected_clients", state.connectedClients)
        put("frame_id", state.frameId ?: JSONObject.NULL)
        put("captured_at_ms", state.capturedAtMs ?: JSONObject.NULL)
        put("last_error", state.lastError ?: JSONObject.NULL)
        put("coordinate_mapping", "screenshot_px_equals_logical_screen_px")
        put("agent_version", AGENT_VERSION)
        put("display", JSONObject().apply {
            put("physical_width", state.display.physicalWidth)
            put("physical_height", state.display.physicalHeight)
            put("logical_width", state.display.logicalWidth)
            put("logical_height", state.display.logicalHeight)
            put("density", state.display.density.toDouble())
            put("density_dpi", state.display.densityDpi)
            put("rotation", state.display.rotation)
            put("insets", JSONObject().apply {
                put("top", state.display.insets.top)
                put("bottom", state.display.insets.bottom)
                put("left", state.display.insets.left)
                put("right", state.display.insets.right)
            })
        })
        put("device", JSONObject().apply {
            put("width", state.display.logicalWidth)
            put("height", state.display.logicalHeight)
            put("rotation", state.display.rotation)
            put("density", state.display.density.toDouble())
            put("manufacturer", device.manufacturer)
            put("model", device.model)
            put("android_version", device.androidVersion)
            put("sdk_int", device.sdkInt)
            put("local_ipv4_addresses", JSONArray(device.localIpv4Addresses))
        })
    }

    fun success(requestId: String, fields: JSONObject = JSONObject()): String =
        successObject(requestId).apply {
            fields.keys().forEach { key -> put(key, fields.get(key)) }
        }.toString()

    fun screenshot(requestId: String, frame: ScreenFrame): JSONObject =
        successObject(requestId).apply {
        put("frame_id", frame.frameId)
        put("mime_type", frame.mimeType)
        put("width", frame.width)
        put("height", frame.height)
        put("rotation", frame.rotation)
        put("captured_at_ms", frame.capturedAtMs)
        put("captured_at", Instant.ofEpochMilli(frame.capturedAtMs).toString())
        put("capture_latency_ms", frame.captureLatencyMs)
        put("encode_latency_ms", frame.encodeLatencyMs)
        put("coordinate_system", "logical_display_pixels")
    }

    fun stream(
        requestId: String,
        status: ScreenCaptureStatus,
        clients: Int,
    ): JSONObject = successObject(requestId).apply {
        put("running", status.running)
        put("codec", status.codec)
        put("transport", status.transport)
        put("width", status.width)
        put("height", status.height)
        put("rotation", status.rotation)
        put("fps", status.estimatedFps)
        put("target_fps", status.targetFps)
        put("bitrate", status.estimatedBitrate)
        put("clients", clients)
        put("last_frame_id", status.lastFrameId ?: JSONObject.NULL)
        put("capture_latency_ms", status.lastCaptureLatencyMs ?: JSONObject.NULL)
        put("encode_latency_ms", status.lastEncodeLatencyMs ?: JSONObject.NULL)
        put("frame_age_ms", status.lastFrameAgeMs ?: JSONObject.NULL)
        put("screen_interactive", status.screenInteractive)
        put("device_locked", status.deviceLocked)
        put("coordinate_system", "logical_display_pixels")
    }

    fun error(
        requestId: String,
        code: String,
        message: String,
        fields: JSONObject = JSONObject(),
    ): String = JSONObject()
        .put("ok", false)
        .put("request_id", requestId)
        .put("error", JSONObject().put("code", code).put("message", message))
        .apply { fields.keys().forEach { key -> put(key, fields.get(key)) } }
        .toString()

    private fun successObject(requestId: String): JSONObject = JSONObject()
        .put("ok", true)
        .put("request_id", requestId)
        .put("error", JSONObject.NULL)

    private const val AGENT_VERSION = "0.1.0"
}
