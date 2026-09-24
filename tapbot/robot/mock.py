"""In-memory robot controller for development and tests."""

import logging
from typing import TypeAlias

from tapbot.robot.controller import RobotController


logger = logging.getLogger(__name__)
RecordedCommand: TypeAlias = tuple[str, *tuple[float, ...]]


class MockRobotController(RobotController):
    """Record controller calls without talking to physical hardware."""

    def __init__(self, *, log: logging.Logger | None = None) -> None:
        self.commands: list[RecordedCommand] = []
        self._log = log or logger

    def _record(self, name: str, *values: float) -> None:
        command: RecordedCommand = (name, *values)
        self.commands.append(command)
        self._log.info("Mock robot command: %s", command)

    def home(self) -> None:
        self._record("home")

    def move_to(self, x: float, y: float) -> None:
        self._record("move_to", x, y)

    def tap(self, x: float, y: float) -> None:
        self._record("tap", x, y)

    def pen_down(self) -> None:
        self._record("pen_down")

    def pen_up(self) -> None:
        self._record("pen_up")

    def emergency_stop(self) -> None:
        self._record("emergency_stop")

    def clear(self) -> None:
        """Discard all previously recorded commands."""

        self.commands.clear()
