"""Primitive UI control abstraction for macro execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tapbot.device.gesture import PointerGesture


class ControllerCapabilityError(RuntimeError):
    """Raised when a backend cannot implement a requested primitive."""


@dataclass(frozen=True, slots=True)
class ControllerResult:
    command: str
    state: str
    action_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "state": self.state,
            "action_id": self.action_id,
            "metadata": dict(self.metadata),
        }


class DeviceController(ABC):
    """The only input surface exposed to the PC macro engine."""

    def execute_gesture(self, gesture: PointerGesture) -> ControllerResult:
        raise ControllerCapabilityError(
            f"{type(self).__name__} does not support pointer gestures"
        )

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        return self._compatibility_result(
            self.execute_gesture(
                PointerGesture.from_tap(x, y, duration_ms=duration_ms)
            ),
            "tap",
        )

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        duration_ms: int = 450,
    ) -> ControllerResult:
        return self._compatibility_result(
            self.execute_gesture(
                PointerGesture.from_swipe(
                    x1,
                    y1,
                    x2,
                    y2,
                    duration_ms=duration_ms,
                )
            ),
            "swipe",
        )

    @staticmethod
    def _compatibility_result(
        result: ControllerResult,
        command: str,
    ) -> ControllerResult:
        return ControllerResult(
            command=command,
            state=result.state,
            action_id=result.action_id,
            metadata=result.metadata,
        )

    @abstractmethod
    def back(self) -> ControllerResult:
        pass

    @abstractmethod
    def home(self) -> ControllerResult:
        pass
