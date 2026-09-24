"""Explicit mapping between screenshot pixels and device input coordinates."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ScreenInsets:
    top: float = 0
    bottom: float = 0
    left: float = 0
    right: float = 0

    def __post_init__(self) -> None:
        values = (self.top, self.bottom, self.left, self.right)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Screen insets must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ScreenGeometry:
    """Coordinate mapping boundary kept even when the mapping is currently 1:1.

    Android Agent screenshots use the same logical orientation as gesture
    coordinates. Rotation is therefore metadata, not an extra transform here.
    Insets are retained for future content-area mapping but screenshots map to
    the full logical display by default.
    """

    frame_width: int
    frame_height: int
    device_width: int
    device_height: int
    rotation: int = 0
    insets: ScreenInsets = ScreenInsets()

    def __post_init__(self) -> None:
        if min(
            self.frame_width,
            self.frame_height,
            self.device_width,
            self.device_height,
        ) <= 0:
            raise ValueError("Frame and device dimensions must be positive")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")
        if self.insets.left + self.insets.right >= self.device_width:
            raise ValueError("Horizontal insets consume the whole device width")
        if self.insets.top + self.insets.bottom >= self.device_height:
            raise ValueError("Vertical insets consume the whole device height")

    def screen_to_device(self, x: float, y: float) -> tuple[float, float]:
        """Scale a full-screen frame point to Android logical display pixels."""

        self._validate_point(x, y)
        device_x = self._scale(x, self.frame_width, self.device_width)
        device_y = self._scale(y, self.frame_height, self.device_height)
        return device_x, device_y

    @staticmethod
    def _scale(value: float, source_size: int, target_size: int) -> float:
        if source_size == 1:
            return 0.0
        return value * (target_size - 1) / (source_size - 1)

    def _validate_point(self, x: float, y: float) -> None:
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Screen coordinates must be finite")
        if not 0 <= x <= self.frame_width - 1:
            raise ValueError(f"x must be within 0..{self.frame_width - 1}")
        if not 0 <= y <= self.frame_height - 1:
            raise ValueError(f"y must be within 0..{self.frame_height - 1}")
