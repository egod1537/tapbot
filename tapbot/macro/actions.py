"""Constrained actions emitted by a PC-side macro state machine."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class TapTargetAction:
    target: str
    duration_ms: int = 70

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("tap target must not be empty")
        _duration(self.duration_ms)


@dataclass(frozen=True, slots=True)
class SwipeAction:
    x1: float
    y1: float
    x2: float
    y2: float
    duration_ms: int = 450

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) for value in (self.x1, self.y1, self.x2, self.y2)):
            raise ValueError("swipe coordinates must be finite")
        _duration(self.duration_ms)


@dataclass(frozen=True, slots=True)
class BackAction:
    pass


@dataclass(frozen=True, slots=True)
class HomeAction:
    pass


@dataclass(frozen=True, slots=True)
class WaitAction:
    duration_ms: int

    def __post_init__(self) -> None:
        _duration(self.duration_ms, allow_zero=True)


@dataclass(frozen=True, slots=True)
class ScreenshotAction:
    pass


@dataclass(frozen=True, slots=True)
class RequestHumanAction:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("request-human reason must not be empty")


MacroAction = (
    TapTargetAction
    | SwipeAction
    | BackAction
    | HomeAction
    | WaitAction
    | ScreenshotAction
    | RequestHumanAction
)


def action_to_dict(action: MacroAction) -> dict[str, object]:
    match action:
        case TapTargetAction(target=target, duration_ms=duration_ms):
            return {"type": "tap_target", "target": target, "duration_ms": duration_ms}
        case SwipeAction(x1=x1, y1=y1, x2=x2, y2=y2, duration_ms=duration_ms):
            return {
                "type": "swipe",
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "duration_ms": duration_ms,
            }
        case BackAction():
            return {"type": "back"}
        case HomeAction():
            return {"type": "home"}
        case WaitAction(duration_ms=duration_ms):
            return {"type": "wait", "duration_ms": duration_ms}
        case ScreenshotAction():
            return {"type": "screenshot"}
        case RequestHumanAction(reason=reason):
            return {"type": "request_human", "reason": reason}


def _duration(value: int, *, allow_zero: bool = False) -> None:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"duration_ms must be an integer >= {minimum}")
