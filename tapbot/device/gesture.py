"""Backend-neutral single-pointer gesture value objects."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time


MAX_POINTER_POINTS = 256
MAX_GESTURE_DURATION_MS = 10_000


class PointerGestureBoundsError(ValueError):
    """Raised when a screen-space gesture point is outside its source frame."""


@dataclass(frozen=True, slots=True)
class PointerPoint:
    x: float
    y: float
    t_ms: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("Pointer coordinates must be finite")
        if isinstance(self.t_ms, bool) or not isinstance(self.t_ms, int):
            raise TypeError("Pointer point t_ms must be an integer")
        if self.t_ms < 0:
            raise ValueError("Pointer point t_ms must be non-negative")

    def to_dict(self) -> dict[str, float | int]:
        return {"x": self.x, "y": self.y, "t_ms": self.t_ms}


@dataclass(frozen=True, slots=True)
class PointerGesture:
    """A completed single-pointer path.

    The first point means DOWN and the final point means UP. Intermediate
    points preserve the recorded geometry. ``t_ms`` is relative to the start
    of the recording; ``started_at_ms`` is metadata only.
    """

    points: tuple[PointerPoint, ...]
    started_at_ms: int
    duration_ms: int

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("Pointer gesture requires at least two points")
        if len(self.points) > MAX_POINTER_POINTS:
            raise ValueError(
                f"Pointer gesture must not exceed {MAX_POINTER_POINTS} points"
            )
        if isinstance(self.started_at_ms, bool) or not isinstance(
            self.started_at_ms, int
        ):
            raise TypeError("started_at_ms must be an integer")
        if self.started_at_ms < 0:
            raise ValueError("started_at_ms must be non-negative")
        previous = self.points[0].t_ms
        for point in self.points[1:]:
            if point.t_ms < previous:
                raise ValueError("Pointer point t_ms values must be monotonic")
            previous = point.t_ms
        computed_duration = self.points[-1].t_ms - self.points[0].t_ms
        if self.duration_ms != computed_duration:
            raise ValueError("duration_ms must equal last.t_ms - first.t_ms")
        if self.duration_ms <= 0:
            raise ValueError("Pointer gesture duration_ms must be positive")
        if self.duration_ms > MAX_GESTURE_DURATION_MS:
            raise ValueError(
                f"Pointer gesture duration_ms must not exceed {MAX_GESTURE_DURATION_MS}"
            )

    @classmethod
    def from_points(
        cls,
        points: tuple[PointerPoint, ...],
        *,
        started_at_ms: int | None = None,
    ) -> "PointerGesture":
        if len(points) < 2:
            raise ValueError("Pointer gesture requires at least two points")
        return cls(
            points=points,
            started_at_ms=(
                int(time.time() * 1_000)
                if started_at_ms is None
                else started_at_ms
            ),
            duration_ms=points[-1].t_ms - points[0].t_ms,
        )

    @classmethod
    def from_tap(
        cls,
        x: float,
        y: float,
        *,
        duration_ms: int = 70,
        started_at_ms: int | None = None,
    ) -> "PointerGesture":
        return cls.from_points(
            (PointerPoint(x, y, 0), PointerPoint(x, y, duration_ms)),
            started_at_ms=started_at_ms,
        )

    @classmethod
    def from_swipe(
        cls,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        duration_ms: int = 450,
        started_at_ms: int | None = None,
    ) -> "PointerGesture":
        return cls.from_points(
            (PointerPoint(x1, y1, 0), PointerPoint(x2, y2, duration_ms)),
            started_at_ms=started_at_ms,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "points": [point.to_dict() for point in self.points],
            "started_at_ms": self.started_at_ms,
            "duration_ms": self.duration_ms,
        }
