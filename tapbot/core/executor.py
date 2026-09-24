"""Action validation and dispatch to a robot controller."""

from collections.abc import Callable, Iterable
import logging
import math
from numbers import Real
import time

from tapbot.core.actions import (
    Action,
    EmergencyStopAction,
    HomeAction,
    MoveAction,
    PenDownAction,
    PenUpAction,
    TapAction,
    WaitAction,
)
from tapbot.robot.controller import RobotController


logger = logging.getLogger(__name__)


class InvalidActionError(ValueError):
    """Raised when an action contains values that cannot be executed safely."""


class ActionExecutor:
    """Validate hardware-independent actions and dispatch them to a robot."""

    def __init__(
        self,
        controller: RobotController,
        *,
        sleep: Callable[[float], None] = time.sleep,
        log: logging.Logger | None = None,
    ) -> None:
        self._controller = controller
        self._sleep = sleep
        self._log = log or logger

    def execute(self, action: Action) -> None:
        """Validate and execute a single action."""

        self._validate(action)
        self._log.info("Executing action: %s", action)

        match action:
            case MoveAction(x=x, y=y):
                self._controller.move_to(float(x), float(y))
            case TapAction(x=x, y=y):
                self._controller.tap(float(x), float(y))
            case WaitAction(duration_ms=duration_ms):
                self._sleep(duration_ms / 1000)
            case HomeAction():
                self._controller.home()
            case PenUpAction():
                self._controller.pen_up()
            case PenDownAction():
                self._controller.pen_down()
            case EmergencyStopAction():
                self._controller.emergency_stop()
            case _:  # pragma: no cover - protected by _validate
                raise InvalidActionError(f"Unsupported action: {type(action).__name__}")

    def execute_all(self, actions: Iterable[Action]) -> None:
        """Execute actions sequentially in the supplied order."""

        for action in actions:
            self.execute(action)

    @staticmethod
    def _validate(action: object) -> None:
        if isinstance(action, (MoveAction, TapAction)):
            ActionExecutor._validate_coordinate("x", action.x)
            ActionExecutor._validate_coordinate("y", action.y)
            return

        if isinstance(action, WaitAction):
            if isinstance(action.duration_ms, bool) or not isinstance(
                action.duration_ms, int
            ):
                raise InvalidActionError("duration_ms must be an integer")
            if action.duration_ms < 0:
                raise InvalidActionError("duration_ms must not be negative")
            return

        if not isinstance(
            action, (HomeAction, PenUpAction, PenDownAction, EmergencyStopAction)
        ):
            raise InvalidActionError(f"Unsupported action: {type(action).__name__}")

    @staticmethod
    def _validate_coordinate(name: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise InvalidActionError(f"{name} must be a real number")
        if not math.isfinite(float(value)):
            raise InvalidActionError(f"{name} must be finite")
        if value < 0:
            raise InvalidActionError(f"{name} must not be negative")
