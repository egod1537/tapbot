package com.tapbot.agent

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.tapbot.agent.accessibility.TapBotAccessibilityService
import com.tapbot.agent.api.ApiTokenStore
import com.tapbot.agent.state.AgentState
import com.tapbot.agent.state.AgentStateStore
import com.tapbot.agent.state.RemoteControlSettings
import com.tapbot.agent.streaming.ScreenStreamService
import com.tapbot.agent.system.DeviceInfoProvider
import com.tapbot.agent.system.DisplayInfoProvider

@SuppressLint("SetTextI18n")
class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var statusText: TextView
    private lateinit var endpointText: TextView
    private lateinit var tokenText: TextView
    private lateinit var remoteControlButton: Button
    private lateinit var remoteControlSettings: RemoteControlSettings
    private lateinit var projectionManager: MediaProjectionManager
    private val stateListener: (AgentState) -> Unit = { state ->
        runOnUiThread { render(state) }
    }
    private val periodicRefresh = object : Runnable {
        override fun run() {
            refreshPlatformState()
            handler.postDelayed(this, 1_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        remoteControlSettings = RemoteControlSettings(this)
        setContentView(buildContent())
        tokenText.text = ApiTokenStore(this).getOrCreate()
        requestNotificationPermission()
        startAgentService()
    }

    override fun onStart() {
        super.onStart()
        AgentStateStore.addListener(stateListener)
        handler.post(periodicRefresh)
    }

    override fun onStop() {
        handler.removeCallbacks(periodicRefresh)
        AgentStateStore.removeListener(stateListener)
        super.onStop()
    }

    @Deprecated("MediaProjection permission uses the platform activity result contract")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_CAPTURE) return
        if (resultCode != RESULT_OK || data == null) {
            AgentStateStore.update { it.copy(lastError = "Screen capture permission denied") }
            return
        }
        val intent = Intent(this, ScreenStreamService::class.java)
            .setAction(ScreenStreamService.ACTION_START_CAPTURE)
            .putExtra(ScreenStreamService.EXTRA_RESULT_CODE, resultCode)
            .putExtra(ScreenStreamService.EXTRA_RESULT_DATA, data)
        startForegroundService(intent)
    }

    private fun buildContent(): ScrollView {
        val spacing = dp(16)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(spacing, spacing, spacing, spacing)
            setBackgroundColor(Color.rgb(24, 27, 31))
        }
        container.addView(TextView(this).apply {
            text = "TAPBOT ANDROID AGENT"
            textSize = 24f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, dp(12))
        }, matchWidth())

        statusText = selectableText(16f)
        endpointText = selectableText(15f)
        tokenText = selectableText(13f)
        container.addView(statusText, matchWidth())
        container.addView(sectionTitle("Endpoint"), matchWidth())
        container.addView(endpointText, matchWidth())
        container.addView(sectionTitle("Bearer token"), matchWidth())
        container.addView(tokenText, matchWidth())

        remoteControlButton = button("Enable Remote Control") {
            val enabled = !AgentStateStore.snapshot().remoteControlEnabled
            remoteControlSettings.setEnabled(enabled)
            AgentStateStore.update { it.copy(remoteControlEnabled = enabled) }
        }
        container.addView(remoteControlButton, matchWidth())
        container.addView(button("Copy token") {
            val clipboard = getSystemService(ClipboardManager::class.java)
            clipboard.setPrimaryClip(ClipData.newPlainText("TapBot API token", tokenText.text))
        }, matchWidth())
        container.addView(button("Rotate token") {
            tokenText.text = ApiTokenStore(this).rotate()
        }, matchWidth())
        container.addView(button("Enable Accessibility") {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }, matchWidth())
        container.addView(button("Grant Screen Capture") {
            startAgentService()
            startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_CAPTURE)
        }, matchWidth())
        container.addView(button("Start Agent Server") { startAgentService() }, matchWidth())
        container.addView(button("Stop Agent") {
            startService(
                Intent(this, ScreenStreamService::class.java)
                    .setAction(ScreenStreamService.ACTION_STOP),
            )
        }, matchWidth())

        container.addView(sectionTitle("Scope"), matchWidth())
        container.addView(selectableText(14f).apply {
            text = "Screen capture/stream + tap/swipe/back/home only.\n" +
                "Vision, VLM, macros, and app-specific decisions stay on the PC."
        }, matchWidth())
        return ScrollView(this).apply { addView(container) }
    }

    private fun render(state: AgentState) {
        statusText.text = buildString {
            appendLine("Remote Control  ${if (state.remoteControlEnabled) "ENABLED" else "DISABLED"}")
            appendLine("Accessibility   ${if (state.accessibilityEnabled) "ENABLED" else "DISABLED"}")
            appendLine("Screen Capture  ${if (state.captureReady) "READY" else "NOT READY"}")
            appendLine("Server          ${if (state.serverRunning) "RUNNING" else "STOPPED"}")
            appendLine("Stream          ${if (state.streamRunning) "RUNNING" else "STOPPED"}")
            appendLine("Clients         ${state.connectedClients}")
            appendLine("Frame           ${state.frameId ?: "—"}")
            appendLine(
                "Logical Screen  ${state.display.logicalWidth} × ${state.display.logicalHeight}",
            )
            append("Last Error      ${state.lastError ?: "—"}")
        }
        remoteControlButton.text = if (state.remoteControlEnabled) {
            "Disable Remote Control"
        } else {
            "Enable Remote Control"
        }
        val addresses = DeviceInfoProvider.current().localIpv4Addresses
        endpointText.text = if (addresses.isEmpty()) {
            "Connect Wi-Fi to obtain a LAN address. Port ${state.serverPort}."
        } else {
            addresses.joinToString("\n\n") {
                "Viewer  http://$it:${state.serverPort}/viewer\n" +
                    "API     http://$it:${state.serverPort}/api/v1"
            }
        }
    }

    private fun refreshPlatformState() {
        val display = DisplayInfoProvider(this).current()
        val accessibility = TapBotAccessibilityService.isEnabled(this)
        AgentStateStore.update {
            it.copy(accessibilityEnabled = accessibility, display = display)
        }
    }

    private fun startAgentService() {
        startForegroundService(
            Intent(this, ScreenStreamService::class.java)
                .setAction(ScreenStreamService.ACTION_START),
        )
    }

    private fun requestNotificationPermission() {
        if (
            Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
    }

    private fun button(label: String, onClick: () -> Unit): Button = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { onClick() }
    }

    private fun sectionTitle(label: String): TextView = TextView(this).apply {
        text = label
        textSize = 12f
        setTextColor(Color.rgb(150, 165, 180))
        setPadding(0, dp(16), 0, dp(4))
    }

    private fun selectableText(size: Float): TextView = TextView(this).apply {
        textSize = size
        setTextColor(Color.rgb(225, 230, 235))
        setTextIsSelectable(true)
        setPadding(dp(8), dp(8), dp(8), dp(8))
    }

    private fun matchWidth(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val REQUEST_CAPTURE = 1001
        private const val REQUEST_NOTIFICATIONS = 1002
    }
}
