"""Hardware-independent actions understood by TapBot."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MoveAction:
    """Move the robot to an absolute X/Y coordinate."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class TapAction:
    """Tap once at an absolute X/Y coordinate."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class WaitAction:
    """Wait for ``duration_ms`` milliseconds."""

    duration_ms: int


@dataclass(frozen=True, slots=True)
class HomeAction:
    """Return the robot to its home position."""


@dataclass(frozen=True, slots=True)
class PenUpAction:
    """Raise the tapping pen."""


@dataclass(frozen=True, slots=True)
class PenDownAction:
    """Lower the tapping pen."""


@dataclass(frozen=True, slots=True)
class EmergencyStopAction:
    """Stop robot operation immediately."""


Action = (
    MoveAction
    | TapAction
    | WaitAction
    | HomeAction
    | PenUpAction
    | PenDownAction
    | EmergencyStopAction
)
