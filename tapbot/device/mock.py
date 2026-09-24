"""Mock graph primitive controller for hardware-free macro tests."""

from __future__ import annotations

from uuid import uuid4

from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.device.controller import (
    ControllerCapabilityError,
    ControllerResult,
    DeviceController,
)


class MockGraphController(DeviceController):
    def __init__(self, source: MockGraphCameraSource) -> None:
        self.source = source

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        transition = self.source.tap(x, y)
        return ControllerResult(
            command="tap",
            state="completed",
            action_id=str(uuid4()),
            metadata={
                "backend": "mock_graph",
                "hit": transition is not None,
                "transition": None if transition is None else transition.to_dict(),
                "duration_ms": duration_ms,
            },
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
        raise ControllerCapabilityError("Mock graph does not model swipe gestures")

    def back(self) -> ControllerResult:
        raise ControllerCapabilityError("Mock graph does not model Android back")

    def home(self) -> ControllerResult:
        self.source.reset()
        return ControllerResult(
            command="home",
            state="completed",
            action_id=str(uuid4()),
            metadata={"backend": "mock_graph", "reset": True},
        )
