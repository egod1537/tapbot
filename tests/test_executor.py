import logging

import pytest

from tapbot.core.actions import (
    EmergencyStopAction,
    HomeAction,
    MoveAction,
    TapAction,
    WaitAction,
)
from tapbot.core.executor import ActionExecutor, InvalidActionError
from tapbot.robot.mock import MockRobotController


def test_executes_tap_without_hardware() -> None:
    robot = MockRobotController()

    ActionExecutor(robot).execute(TapAction(100, 200))

    assert robot.commands == [("tap", 100.0, 200.0)]


def test_records_move_and_tap_in_execution_order() -> None:
    robot = MockRobotController()
    executor = ActionExecutor(robot)

    executor.execute_all([MoveAction(10, 20), TapAction(100, 200)])

    assert robot.commands == [
        ("move_to", 10.0, 20.0),
        ("tap", 100.0, 200.0),
    ]


def test_dispatches_home_and_emergency_stop() -> None:
    robot = MockRobotController()
    executor = ActionExecutor(robot)

    executor.execute_all([HomeAction(), EmergencyStopAction()])

    assert robot.commands == [("home",), ("emergency_stop",)]


def test_wait_uses_milliseconds_and_does_not_touch_robot() -> None:
    waits: list[float] = []
    robot = MockRobotController()

    ActionExecutor(robot, sleep=waits.append).execute(WaitAction(250))

    assert waits == [0.25]
    assert robot.commands == []


@pytest.mark.parametrize(
    "action",
    [
        MoveAction(-1, 2),
        MoveAction(float("nan"), 2),
        TapAction(1, float("inf")),
        WaitAction(-1),
    ],
)
def test_invalid_action_is_rejected_before_controller_call(action: object) -> None:
    robot = MockRobotController()

    with pytest.raises(InvalidActionError):
        ActionExecutor(robot).execute(action)  # type: ignore[arg-type]

    assert robot.commands == []


def test_execution_emits_log_record(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="tapbot.core.executor"):
        ActionExecutor(MockRobotController()).execute(HomeAction())

    assert "Executing action: HomeAction()" in caplog.text
