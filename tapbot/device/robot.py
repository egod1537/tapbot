"""Adapter that lets the macro engine target a robot tapping backend."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from tapbot.device.controller import (
    ControllerCapabilityError,
    ControllerResult,
    DeviceController,
)
from tapbot.device.gesture import PointerGesture
from tapbot.robot.controller import RobotController


class ScreenToRobotMapper(Protocol):
    def screen_to_robot(self, x: float, y: float) -> object: ...


class RobotTapController(DeviceController):
    """Convert canonical screen taps to robot coordinates at the adapter edge."""

    def __init__(self, robot: RobotController, mapper: ScreenToRobotMapper) -> None:
        self.robot = robot
        self.mapper = mapper

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> ControllerResult:
        robot_x, robot_y = self._map(x, y)
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

    def execute_gesture(self, gesture: PointerGesture) -> ControllerResult:
        mapped_points = [self._map(point.x, point.y) for point in gesture.points]
        first_x, first_y = mapped_points[0]
        self.robot.move_to(first_x, first_y)
        self.robot.pen_down()
        try:
            for robot_x, robot_y in mapped_points[1:]:
                self.robot.move_to(robot_x, robot_y)
        finally:
            self.robot.pen_up()
        return ControllerResult(
            command="gesture",
            state="completed",
            action_id=str(uuid4()),
            metadata={
                "backend": "robot_tap",
                "gesture": gesture.to_dict(),
                "robot_points": [
                    {"x": robot_x, "y": robot_y}
                    for robot_x, robot_y in mapped_points
                ],
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
        return super().swipe(x1, y1, x2, y2, duration_ms=duration_ms)

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

    def _map(self, x: float, y: float) -> tuple[float, float]:
        mapped = self.mapper.screen_to_robot(x, y)
        if isinstance(mapped, tuple) and len(mapped) == 2:
            return float(mapped[0]), float(mapped[1])
        try:
            return float(getattr(mapped, "x")), float(getattr(mapped, "y"))
        except (AttributeError, TypeError, ValueError) as error:
            raise TypeError(
                "screen_to_robot must return (x, y) or an object with x/y"
            ) from error
