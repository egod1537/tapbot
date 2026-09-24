package com.tapbot.agent.system

import android.content.Context
import android.graphics.Insets
import android.os.Build
import android.util.DisplayMetrics
import android.view.Surface
import android.view.WindowInsets
import android.view.WindowManager
import com.tapbot.agent.state.DisplayState
import com.tapbot.agent.state.InsetsState

class DisplayInfoProvider(private val context: Context) {
    @Suppress("DEPRECATION")
    fun current(): DisplayState {
        val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val logicalMetrics = context.resources.displayMetrics
        val realMetrics = DisplayMetrics()
        windowManager.defaultDisplay.getRealMetrics(realMetrics)

        val rotation = when (windowManager.defaultDisplay.rotation) {
            Surface.ROTATION_90 -> 90
            Surface.ROTATION_180 -> 180
            Surface.ROTATION_270 -> 270
            else -> 0
        }

        var logicalWidth = logicalMetrics.widthPixels
        var logicalHeight = logicalMetrics.heightPixels
        var insets = InsetsState()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val metrics = windowManager.currentWindowMetrics
            logicalWidth = metrics.bounds.width()
            logicalHeight = metrics.bounds.height()
            val platformInsets: Insets = metrics.windowInsets.getInsetsIgnoringVisibility(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
            )
            insets = InsetsState(
                top = platformInsets.top,
                bottom = platformInsets.bottom,
                left = platformInsets.left,
                right = platformInsets.right,
            )
        }

        return DisplayState(
            physicalWidth = realMetrics.widthPixels,
            physicalHeight = realMetrics.heightPixels,
            logicalWidth = logicalWidth,
            logicalHeight = logicalHeight,
            density = logicalMetrics.density,
            densityDpi = logicalMetrics.densityDpi,
            rotation = rotation,
            insets = insets,
        )
    }
}
