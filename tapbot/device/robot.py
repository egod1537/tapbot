"""Adapter that lets the macro engine target a robot tapping backend."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from tapbot.device.controller import (
    ControllerCapabilityError,
    ControllerResult,
    DeviceController,
)
from tapbot.robot.controller import RobotController


class ScreenToRobotMapper(Protocol):
    def screen_to_robot(self, x: float, y: float) -> object: ...


class RobotTapController(DeviceController):
    """Convert canonical screen taps to robot coordinates at the adapter edge."""

    def __init__(self, robot: RobotController, mapper: ScreenToRobotMapper) -> None:
        self.robot = robot
        self.mapper = mapper

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        mapped = self.mapper.screen_to_robot(x, y)
        if isinstance(mapped, tuple) and len(mapped) == 2:
            robot_x, robot_y = float(mapped[0]), float(mapped[1])
        else:
            try:
                robot_x = float(getattr(mapped, "x"))
                robot_y = float(getattr(mapped, "y"))
            except (AttributeError, TypeError, ValueError) as error:
                raise TypeError(
                    "screen_to_robot must return (x, y) or an object with x/y"
                ) from error
        self.robot.tap(robot_x, robot_y)
        return ControllerResult(
            command="tap",
            state="completed",
            action_id=str(uuid4()),
            metadata={
                "backend": "robot_tap",
                "screen": {"x": x, "y": y},
                "robot": {"x": robot_x, "y": robot_y},
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
        raise ControllerCapabilityError("Robot tap backend does not support swipe")

    def back(self) -> ControllerResult:
        raise ControllerCapabilityError("Robot tap backend does not support back")

    def home(self) -> ControllerResult:
        self.robot.home()
        return ControllerResult(
            command="home",
            state="completed",
            action_id=str(uuid4()),
            metadata={"backend": "robot_tap"},
        )
