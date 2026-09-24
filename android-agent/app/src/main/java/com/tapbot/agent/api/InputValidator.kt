package com.tapbot.agent.api

data class ValidationError(val code: String, val message: String)

object InputValidator {
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
}
