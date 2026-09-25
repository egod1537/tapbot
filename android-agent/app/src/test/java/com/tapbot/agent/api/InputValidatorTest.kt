package com.tapbot.agent.api

import com.tapbot.agent.accessibility.GesturePoint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class InputValidatorTest {
    @Test
    fun acceptsCoordinatesInsideLogicalDisplay() {
        assertNull(InputValidator.point(0f, 0f, 1080, 2400))
        assertNull(InputValidator.point(1079f, 2399f, 1080, 2400))
    }

    @Test
    fun rejectsCoordinatesAtOrBeyondExclusiveBounds() {
        assertEquals(
            "coordinate_out_of_bounds",
            InputValidator.point(1080f, 100f, 1080, 2400)?.code,
        )
        assertEquals(
            "coordinate_out_of_bounds",
            InputValidator.point(-1f, 100f, 1080, 2400)?.code,
        )
    }

    @Test
    fun rejectsInvalidDurations() {
        assertEquals("invalid_duration", InputValidator.duration(0)?.code)
        assertEquals("invalid_duration", InputValidator.duration(60_001)?.code)
        assertNull(InputValidator.duration(75))
    }

    @Test
    fun acceptsValidPointerTrajectory() {
        assertNull(
            InputValidator.gesture(
                listOf(
                    GesturePoint(500f, 1800f, 0),
                    GesturePoint(510f, 1300f, 100),
                    GesturePoint(500f, 600f, 260),
                ),
                1080,
                2400,
            ),
        )
    }

    @Test
    fun rejectsMalformedGestureTimingAndBounds() {
        assertEquals(
            "invalid_gesture",
            InputValidator.gesture(
                listOf(GesturePoint(1f, 1f, 10), GesturePoint(2f, 2f, 9)),
                1080,
                2400,
            )?.code,
        )
        assertEquals(
            "point_out_of_bounds",
            InputValidator.gesture(
                listOf(GesturePoint(1f, 1f, 0), GesturePoint(1080f, 2f, 10)),
                1080,
                2400,
            )?.code,
        )
    }

    @Test
    fun rejectsOversizedGestures() {
        val tooMany = (0..InputValidator.MAX_GESTURE_POINTS).map {
            GesturePoint(1f, 1f, it.toLong())
        }
        assertEquals(
            "gesture_too_large",
            InputValidator.gesture(tooMany, 1080, 2400)?.code,
        )
        assertEquals(
            "gesture_too_large",
            InputValidator.gesture(
                listOf(
                    GesturePoint(1f, 1f, 0),
                    GesturePoint(2f, 2f, InputValidator.MAX_GESTURE_DURATION_MS + 1),
                ),
                1080,
                2400,
            )?.code,
        )
    }
}
