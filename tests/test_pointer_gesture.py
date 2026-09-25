import math

import pytest

from tapbot.device.gesture import (
    MAX_POINTER_POINTS,
    PointerGesture,
    PointerPoint,
)


def test_pointer_gesture_factories_preserve_timing_and_geometry() -> None:
    tap = PointerGesture.from_tap(10, 20, duration_ms=70, started_at_ms=123)
    swipe = PointerGesture.from_swipe(
        1,
        2,
        30,
        40,
        duration_ms=450,
        started_at_ms=456,
    )

    assert tap.points == (PointerPoint(10, 20, 0), PointerPoint(10, 20, 70))
    assert (tap.started_at_ms, tap.duration_ms) == (123, 70)
    assert swipe.points[-1] == PointerPoint(30, 40, 450)
    assert (swipe.started_at_ms, swipe.duration_ms) == (456, 450)


@pytest.mark.parametrize(
    "points,duration,error",
    [
        ((PointerPoint(0, 0, 10), PointerPoint(1, 1, 9)), -1, "monotonic"),
        ((PointerPoint(0, 0, 0), PointerPoint(1, 1, 0)), 0, "positive"),
    ],
)
def test_pointer_gesture_rejects_invalid_timing(
    points: tuple[PointerPoint, ...],
    duration: int,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        PointerGesture(points, 0, duration)


def test_pointer_gesture_rejects_non_finite_coordinates() -> None:
    with pytest.raises(ValueError, match="finite"):
        PointerPoint(math.inf, 1, 0)


def test_pointer_gesture_rejects_too_many_points() -> None:
    points = tuple(PointerPoint(1, 1, index) for index in range(MAX_POINTER_POINTS + 1))
    with pytest.raises(ValueError, match="must not exceed"):
        PointerGesture(points, 0, MAX_POINTER_POINTS)
