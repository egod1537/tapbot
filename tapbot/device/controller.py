"""Primitive UI control abstraction for macro execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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

    @abstractmethod
    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        pass

    @abstractmethod
    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        duration_ms: int = 450,
    ) -> ControllerResult:
        pass

    @abstractmethod
    def back(self) -> ControllerResult:
        pass

    @abstractmethod
    def home(self) -> ControllerResult:
        pass
