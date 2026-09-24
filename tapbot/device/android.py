"""Device controller backed by Android Agent REST primitives."""

from __future__ import annotations

from tapbot.android.client import AndroidActionResult, AndroidAgentClient
from tapbot.device.controller import ControllerResult, DeviceController


class AndroidRemoteController(DeviceController):
    def __init__(self, client: AndroidAgentClient) -> None:
        self.client = client

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        return self._result(self.client.tap(x, y, duration_ms=duration_ms))

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        duration_ms: int = 450,
    ) -> ControllerResult:
        return self._result(
            self.client.swipe(x1, y1, x2, y2, duration_ms=duration_ms)
        )

    def back(self) -> ControllerResult:
        return self._result(self.client.back())

    def home(self) -> ControllerResult:
        return self._result(self.client.home())

    @staticmethod
    def _result(result: AndroidActionResult) -> ControllerResult:
        return ControllerResult(
            command=result.command,
            state=result.state,
            action_id=result.action_id,
            metadata={"request_id": result.request_id, "backend": "android_remote"},
        )
