"""In-memory robot controller for development and tests."""

import logging
from collections.abc import Callable
from threading import RLock
from typing import TypeAlias

from tapbot.robot.controller import RobotController


logger = logging.getLogger(__name__)
RecordedCommand: TypeAlias = tuple[str, *tuple[float, ...]]
TapListener: TypeAlias = Callable[[float, float], None]
Unsubscribe: TypeAlias = Callable[[], None]


class MockRobotController(RobotController):
    """Record controller calls without talking to physical hardware."""

    def __init__(self, *, log: logging.Logger | None = None) -> None:
        self.commands: list[RecordedCommand] = []
        self._log = log or logger
        self._tap_listeners: list[TapListener] = []
        self._lock = RLock()

    def _record(self, name: str, *values: float) -> None:
        command: RecordedCommand = (name, *values)
        with self._lock:
            self.commands.append(command)
        self._log.info("Mock robot command: %s", command)

    def home(self) -> None:
        self._record("home")

    def move_to(self, x: float, y: float) -> None:
        self._record("move_to", x, y)

    def tap(self, x: float, y: float) -> None:
        self._record("tap", x, y)
        with self._lock:
            listeners = tuple(self._tap_listeners)
        for listener in listeners:
            listener(x, y)

    def add_tap_listener(self, listener: TapListener) -> Unsubscribe:
        """Subscribe to successful mock taps without coupling to a simulator."""

        with self._lock:
            if listener not in self._tap_listeners:
                self._tap_listeners.append(listener)

        def unsubscribe() -> None:
            self.remove_tap_listener(listener)

        return unsubscribe

    def remove_tap_listener(self, listener: TapListener) -> None:
        with self._lock:
            try:
                self._tap_listeners.remove(listener)
            except ValueError:
                pass

    def pen_down(self) -> None:
        self._record("pen_down")

    def pen_up(self) -> None:
        self._record("pen_up")

    def emergency_stop(self) -> None:
        self._record("emergency_stop")

    def clear(self) -> None:
        """Discard all previously recorded commands."""

        with self._lock:
            self.commands.clear()
