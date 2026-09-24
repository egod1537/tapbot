package com.tapbot.agent.api

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
}
