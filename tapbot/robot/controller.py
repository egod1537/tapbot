"""Abstract robot controller API."""

from abc import ABC, abstractmethod


class RobotController(ABC):
    """Hardware-agnostic interface used by all TapBot callers."""

    @abstractmethod
    def home(self) -> None:
        """Return the robot to its home position."""

    @abstractmethod
    def move_to(self, x: float, y: float) -> None:
        """Move to an absolute X/Y coordinate."""

    @abstractmethod
    def tap(self, x: float, y: float) -> None:
        """Tap once at an absolute X/Y coordinate."""

    @abstractmethod
    def pen_down(self) -> None:
        """Lower the tapping pen."""

    @abstractmethod
    def pen_up(self) -> None:
        """Raise the tapping pen."""

    @abstractmethod
    def emergency_stop(self) -> None:
        """Stop all robot operation immediately."""
