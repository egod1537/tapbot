package com.tapbot.agent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ComponentName
import android.content.Context
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import com.tapbot.agent.state.AgentStateStore
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.locks.ReentrantLock
import java.util.UUID

enum class ActionOutcome {
    COMPLETED,
    DISPATCHED,
    CANCELLED,
    REJECTED,
    TIMEOUT,
    BUSY,
}

data class ActionExecutionResult(
    val actionId: String,
    val outcome: ActionOutcome,
)

class TapBotAccessibilityService : AccessibilityService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val gestureLock = ReentrantLock()

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        AgentStateStore.update { it.copy(accessibilityEnabled = true, lastError = null) }
        Log.i(TAG, "Accessibility input service connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() {
        AgentStateStore.update { it.copy(lastError = "Accessibility service interrupted") }
        Log.w(TAG, "Accessibility input service interrupted")
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        clearInstance()
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        clearInstance()
        super.onDestroy()
    }

    fun tap(
        x: Float,
        y: Float,
        durationMs: Long = DEFAULT_TAP_DURATION_MS,
    ): ActionExecutionResult {
        val path = Path().apply { moveTo(x, y) }
        return dispatch(
            GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
                .build(),
            "tap",
        )
    }

    fun swipe(
        x1: Float,
        y1: Float,
        x2: Float,
        y2: Float,
        durationMs: Long,
    ): ActionExecutionResult {
        val path = Path().apply {
            moveTo(x1, y1)
            lineTo(x2, y2)
        }
        return dispatch(
            GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
                .build(),
            "swipe",
        )
    }

    fun back(): ActionExecutionResult = globalAction { performGlobalAction(GLOBAL_ACTION_BACK) }

    fun home(): ActionExecutionResult = globalAction { performGlobalAction(GLOBAL_ACTION_HOME) }

    fun recents(): ActionExecutionResult = globalAction {
        performGlobalAction(GLOBAL_ACTION_RECENTS)
    }

    private fun dispatch(
        gesture: GestureDescription,
        command: String,
    ): ActionExecutionResult {
        val actionId = UUID.randomUUID().toString()
        if (!gestureLock.tryLock()) {
            return ActionExecutionResult(actionId, ActionOutcome.BUSY)
        }
        try {
            val outcome = AtomicReference<ActionOutcome?>(null)
            val callbackCompleted = CountDownLatch(1)
            val dispatchResult = onMainThread {
                dispatchGesture(
                    gesture,
                    object : GestureResultCallback() {
                        override fun onCompleted(gestureDescription: GestureDescription?) {
                            outcome.set(ActionOutcome.COMPLETED)
                            callbackCompleted.countDown()
                            Log.d(TAG, "$command gesture completed")
                        }

                        override fun onCancelled(gestureDescription: GestureDescription?) {
                            outcome.set(ActionOutcome.CANCELLED)
                            callbackCompleted.countDown()
                            AgentStateStore.update {
                                it.copy(lastError = "$command gesture was cancelled")
                            }
                            Log.w(TAG, "$command gesture cancelled")
                        }
                    },
                    mainHandler,
                )
            }
            if (!dispatchResult.completed) {
                return ActionExecutionResult(actionId, ActionOutcome.TIMEOUT)
            }
            if (!dispatchResult.value) {
                return ActionExecutionResult(actionId, ActionOutcome.REJECTED)
            }
            val callbackArrived = callbackCompleted.await(
                gestureDurationMs(gesture) + GESTURE_CALLBACK_GRACE_MS,
                TimeUnit.MILLISECONDS,
            )
            return ActionExecutionResult(
                actionId,
                if (callbackArrived) outcome.get() ?: ActionOutcome.REJECTED else ActionOutcome.TIMEOUT,
            )
        } finally {
            gestureLock.unlock()
        }
    }

    private fun globalAction(action: () -> Boolean): ActionExecutionResult {
        val actionId = UUID.randomUUID().toString()
        val result = onMainThread(action)
        return ActionExecutionResult(
            actionId,
            when {
                !result.completed -> ActionOutcome.TIMEOUT
                result.value -> ActionOutcome.DISPATCHED
                else -> ActionOutcome.REJECTED
            },
        )
    }

    private fun gestureDurationMs(gesture: GestureDescription): Long =
        (0 until gesture.strokeCount)
            .maxOfOrNull { gesture.getStroke(it).duration }
            ?: DEFAULT_TAP_DURATION_MS

    private fun onMainThread(action: () -> Boolean): MainThreadResult {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            return MainThreadResult(completed = true, value = action())
        }
        val result = AtomicBoolean(false)
        val completed = CountDownLatch(1)
        val runnable = Runnable {
            runCatching(action)
                .onSuccess(result::set)
                .onFailure { error ->
                    AgentStateStore.update { it.copy(lastError = error.message) }
                    Log.e(TAG, "Input action failed", error)
                }
            completed.countDown()
        }
        mainHandler.post(runnable)
        val finished = completed.await(MAIN_THREAD_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        if (!finished) mainHandler.removeCallbacks(runnable)
        return MainThreadResult(completed = finished, value = finished && result.get())
    }

    private data class MainThreadResult(val completed: Boolean, val value: Boolean)

    private fun clearInstance() {
        if (instance === this) instance = null
        AgentStateStore.update { it.copy(accessibilityEnabled = false) }
        Log.i(TAG, "Accessibility input service disconnected")
    }

    companion object {
        private const val TAG = "TapBotAccessibility"
        private const val GESTURE_CALLBACK_GRACE_MS = 2_000L
        private const val MAIN_THREAD_TIMEOUT_MS = 2_000L
        const val DEFAULT_TAP_DURATION_MS = 75L

        @Volatile
        private var instance: TapBotAccessibilityService? = null

        fun current(): TapBotAccessibilityService? = instance

        fun isEnabled(context: Context): Boolean {
            val expected = ComponentName(context, TapBotAccessibilityService::class.java)
                .flattenToString()
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ).orEmpty()
            return enabled.split(':').any { it.equals(expected, ignoreCase = true) }
        }
    }
}
