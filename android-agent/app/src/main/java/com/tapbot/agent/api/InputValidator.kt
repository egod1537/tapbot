package com.tapbot.agent.api

import com.tapbot.agent.accessibility.GesturePoint
import kotlin.math.hypot

data class ValidationError(val code: String, val message: String)

object InputValidator {
    const val MAX_GESTURE_POINTS = 256
    const val MAX_GESTURE_DURATION_MS = 10_000L
    const val MAX_GESTURE_PATH_LENGTH = 100_000.0

    fun point(x: Float, y: Float, width: Int, height: Int): ValidationError? {
        if (!x.isFinite() || !y.isFinite()) {
            return ValidationError("invalid_coordinate", "Coordinates must be finite numbers")
        }
        if (width <= 0 || height <= 0) {
            return ValidationError("display_unavailable", "Logical display size is unavailable")
        }
        if (x < 0f || x >= width || y < 0f || y >= height) {
            return ValidationError(
                "coordinate_out_of_bounds",
                "Coordinate ($x, $y) is outside ${width}x$height",
            )
        }
        return null
    }

    fun duration(durationMs: Long, minimumMs: Long = 1): ValidationError? = when {
        durationMs < minimumMs -> ValidationError(
            "invalid_duration",
            "duration_ms must be at least $minimumMs",
        )
        durationMs > 60_000 -> ValidationError(
            "invalid_duration",
            "duration_ms must not exceed 60000",
        )
        else -> null
    }

    fun gesture(
        points: List<GesturePoint>,
        width: Int,
        height: Int,
    ): ValidationError? {
        if (points.size < 2) {
            return ValidationError("invalid_gesture", "Gesture requires at least two points")
        }
        if (points.size > MAX_GESTURE_POINTS) {
            return ValidationError(
                "gesture_too_large",
                "Gesture must not exceed $MAX_GESTURE_POINTS points",
            )
        }
        if (width <= 0 || height <= 0) {
            return ValidationError("display_unavailable", "Logical display size is unavailable")
        }
        var previous = points.first()
        if (previous.tMs < 0) {
            return ValidationError("invalid_gesture", "Gesture timestamps must be non-negative")
        }
        point(previous.x, previous.y, width, height)?.let {
            val code = if (it.code == "coordinate_out_of_bounds") {
                "point_out_of_bounds"
            } else {
                "invalid_gesture"
            }
            return ValidationError(code, "Gesture point 0: ${it.message}")
        }
        var pathLength = 0.0
        points.drop(1).forEachIndexed { offset, current ->
            val index = offset + 1
            if (current.tMs < previous.tMs) {
                return ValidationError(
                    "invalid_gesture",
                    "Gesture timestamps must be monotonic at point $index",
                )
            }
            point(current.x, current.y, width, height)?.let {
                val code = if (it.code == "coordinate_out_of_bounds") {
                    "point_out_of_bounds"
                } else {
                    "invalid_gesture"
                }
                return ValidationError(code, "Gesture point $index: ${it.message}")
            }
            pathLength += hypot(
                (current.x - previous.x).toDouble(),
                (current.y - previous.y).toDouble(),
            )
            if (pathLength > MAX_GESTURE_PATH_LENGTH) {
                return ValidationError(
                    "gesture_too_large",
                    "Gesture path length must not exceed $MAX_GESTURE_PATH_LENGTH pixels",
                )
            }
            previous = current
        }
        val duration = points.last().tMs - points.first().tMs
        if (duration <= 0) {
            return ValidationError("invalid_gesture", "Gesture duration must be positive")
        }
        if (duration > MAX_GESTURE_DURATION_MS) {
            return ValidationError(
                "gesture_too_large",
                "Gesture duration must not exceed $MAX_GESTURE_DURATION_MS ms",
            )
        }
        return null
    }
}
