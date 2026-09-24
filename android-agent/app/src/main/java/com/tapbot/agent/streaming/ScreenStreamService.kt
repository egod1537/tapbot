package com.tapbot.agent.streaming

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import com.tapbot.agent.MainActivity
import com.tapbot.agent.api.ApiTokenStore
import com.tapbot.agent.api.ControlServer
import com.tapbot.agent.capture.ScreenCaptureManager
import com.tapbot.agent.state.AgentStateStore
import com.tapbot.agent.state.RemoteControlSettings
import com.tapbot.agent.system.DisplayInfoProvider

class ScreenStreamService : Service() {
    private lateinit var captureManager: ScreenCaptureManager
    private var controlServer: ControlServer? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, notification("Agent server starting"))
        captureManager = ScreenCaptureManager(applicationContext)
        AgentStateStore.update {
            it.copy(
                remoteControlEnabled = RemoteControlSettings(applicationContext).isEnabled(),
                display = DisplayInfoProvider(applicationContext).current(),
            )
        }
        startControlServer()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> {
                if (controlServer == null) startControlServer()
            }
            ACTION_START_CAPTURE -> intent?.let(::startCapture)
            ACTION_STOP -> stopSelf()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        controlServer?.close()
        controlServer = null
        captureManager.close()
        AgentStateStore.update {
            it.copy(
                serverRunning = false,
                captureReady = false,
                streamRunning = false,
                connectedClients = 0,
            )
        }
        Log.i(TAG, "Agent foreground service stopped")
        super.onDestroy()
    }

    private fun startControlServer() {
        if (controlServer != null) return
        val server = ControlServer(
            port = DEFAULT_PORT,
            apiToken = ApiTokenStore(applicationContext).getOrCreate(),
            captureProvider = captureManager,
        )
        runCatching(server::startServer)
            .onSuccess {
                controlServer = server
                notifyState("Agent server running on port $DEFAULT_PORT")
                Log.i(TAG, "Agent foreground service started")
            }
            .onFailure { notifyState("Agent server failed: ${it.message}") }
    }

    private fun startCapture(intent: Intent) {
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
        val resultData = projectionData(intent)
        if (resultData == null) {
            AgentStateStore.update { it.copy(lastError = "MediaProjection result data missing") }
            return
        }
        runCatching { captureManager.start(resultCode, resultData) }
            .onSuccess { notifyState("Screen capture and server running") }
            .onFailure { error ->
                AgentStateStore.update {
                    it.copy(lastError = "Capture start failed: ${error.message}")
                }
                Log.e(TAG, "Capture start failed", error)
            }
    }

    @Suppress("DEPRECATION")
    private fun projectionData(intent: Intent): Intent? = if (Build.VERSION.SDK_INT >= 33) {
        intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
    } else {
        intent.getParcelableExtra(EXTRA_RESULT_DATA)
    }

    private fun createNotificationChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                NOTIFICATION_CHANNEL,
                "TapBot Agent",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Keeps authenticated screen capture and remote control active"
            },
        )
    }

    private fun notification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, ScreenStreamService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return Notification.Builder(this, NOTIFICATION_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("TapBot Android Agent")
            .setContentText(text)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Stop", stopIntent).build())
            .build()
    }

    private fun notifyState(text: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, notification(text))
    }

    companion object {
        private const val TAG = "TapBotStreamService"
        private const val NOTIFICATION_CHANNEL = "tapbot_agent"
        private const val NOTIFICATION_ID = 4101
        const val DEFAULT_PORT = 8765
        const val ACTION_START = "com.tapbot.agent.START"
        const val ACTION_START_CAPTURE = "com.tapbot.agent.START_CAPTURE"
        const val ACTION_STOP = "com.tapbot.agent.STOP"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
    }
}
