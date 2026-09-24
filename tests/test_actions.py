from dataclasses import FrozenInstanceError

import pytest

from tapbot.core.actions import (
    EmergencyStopAction,
    HomeAction,
    MoveAction,
    TapAction,
    WaitAction,
)


def test_action_models_hold_hardware_independent_values() -> None:
    assert MoveAction(10, 20) == MoveAction(x=10, y=20)
    assert TapAction(100, 200).y == 200
    assert WaitAction(250).duration_ms == 250
    assert HomeAction() == HomeAction()
    assert EmergencyStopAction() == EmergencyStopAction()


def test_actions_are_immutable() -> None:
    action = MoveAction(1, 2)

    with pytest.raises(FrozenInstanceError):
        action.x = 3  # type: ignore[misc]
