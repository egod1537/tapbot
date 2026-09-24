from datetime import datetime, timezone
import logging
from pathlib import Path

import numpy as np
import pytest

from tapbot.core.actions import TapAction, WaitAction
from tapbot.core.executor import ActionExecutor
from tapbot.model.client import MockModelClient
from tapbot.model.decision import (
    DECISION_JSON_SCHEMA,
    DecisionAction,
    DecisionOutputError,
    DecisionParser,
)
from tapbot.model.pipeline import (
    DecisionCoordinator,
    DecisionEngine,
    DecisionPolicy,
)
from tapbot.model.replay import ReplayRunner
from tapbot.model.resolver import TargetResolver
from tapbot.robot.mock import MockRobotController
from tapbot.vision.calibration import Calibration, Point2D, RobotWorkArea
from tapbot.vision.detector import BoundingBox, Detection


def make_calibration(width: int = 200, height: int = 100) -> Calibration:
    return Calibration(
        profile_name="model-test",
        camera_corners=(
            Point2D(0, 0),
            Point2D(width, 0),
            Point2D(width, height),
            Point2D(0, height),
        ),
        robot_points=(
            Point2D(10, 20),
            Point2D(210, 20),
            Point2D(210, 120),
            Point2D(10, 120),
        ),
        phone_width=width,
        phone_height=height,
        created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        camera_resolution=(width, height),
        robot_work_area=RobotWorkArea(0, 300, 0, 200),
    )


def tap_decision(
    *,
    target: str = "confirm_button",
    confidence: float = 0.95,
) -> dict[str, object]:
    return {
        "state": "confirmation_visible",
        "action": "tap_target",
        "target": target,
        "confidence": confidence,
        "reason": "The deterministic detector found the confirmation button.",
    }


def target_detection() -> Detection:
    return Detection(
        label="confirm_button",
        bbox=BoundingBox(80, 40, 40, 20),
        confidence=0.9,
        detector_type="opencv_color_contour",
    )


def make_engine(response: object, **policy: object) -> DecisionEngine:
    return DecisionEngine(
        MockModelClient(response),  # type: ignore[arg-type]
        TargetResolver(minimum_detection_confidence=0.5),
        make_calibration(),
        policy=DecisionPolicy(**policy),  # type: ignore[arg-type]
    )


def test_decision_schema_allows_only_high_level_actions() -> None:
    action_values = DECISION_JSON_SCHEMA["properties"]["action"]["enum"]

    assert action_values == ["noop", "tap_target", "wait", "request_human"]
    assert DECISION_JSON_SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize(
    "extra_field",
    [
        {"gcode": "G0 X100 Y200"},
        {"shell_command": "rm -rf /"},
        {"robot_x": 100, "robot_y": 200},
    ],
)
def test_parser_rejects_forbidden_executable_or_coordinate_fields(
    extra_field: dict[str, object],
) -> None:
    raw = tap_decision() | extra_field

    with pytest.raises(DecisionOutputError, match="forbidden fields"):
        DecisionParser().parse(raw)


def test_mock_model_target_resolves_to_tap_action_and_executes() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    robot = MockRobotController()
    engine = make_engine(tap_decision())
    coordinator = DecisionCoordinator(engine, ActionExecutor(robot))

    result = coordinator.run(image, {}, [target_detection()], execute=True)

    assert result.decision is not None
    assert result.decision.action is DecisionAction.TAP_TARGET
    assert result.action == TapAction(110, 70)
    assert result.resolved_target is not None
    assert result.resolved_target.source == "detection"
    assert result.executed is True
    assert robot.commands == [("tap", 110.0, 70.0)]


def test_invalid_model_schema_never_moves_robot() -> None:
    invalid = tap_decision() | {"gcode": "G1 X999 Y999"}
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    robot = MockRobotController()
    coordinator = DecisionCoordinator(
        make_engine(invalid),
        ActionExecutor(robot),
    )

    result = coordinator.run(image, detections=[target_detection()], execute=True)

    assert result.status == "invalid_model_output"
    assert result.action is None
    assert result.executed is False
    assert robot.commands == []


def test_confidence_gate_blocks_action_creation() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    result = make_engine(tap_decision(confidence=0.79)).decide(
        image,
        detections=[target_detection()],
    )

    assert result.status == "confidence_below_threshold"
    assert result.action is None
    assert result.execution_allowed is False


def test_rectified_image_size_mismatch_blocks_model_call() -> None:
    engine = make_engine(tap_decision())

    result = engine.decide(np.zeros((50, 100, 3), dtype=np.uint8))

    assert result.status == "screen_size_mismatch"
    assert result.action is None
    model = engine.model_client
    assert isinstance(model, MockModelClient)
    assert model.calls == []


def test_missing_target_blocks_action_creation() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    result = make_engine(tap_decision(target="missing_button")).decide(
        image,
        detections=[target_detection()],
    )

    assert result.status == "target_not_found"
    assert result.action is None


def test_predefined_roi_can_resolve_trusted_target() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    engine = DecisionEngine(
        MockModelClient(tap_decision(target="fixed_confirm_roi")),
        TargetResolver({"fixed_confirm_roi": BoundingBox(80, 40, 40, 20)}),
        make_calibration(),
    )

    result = engine.decide(image)

    assert result.action == TapAction(110, 70)
    assert result.resolved_target is not None
    assert result.resolved_target.source == "predefined_roi"


def test_wait_duration_comes_from_policy_not_model() -> None:
    decision = {
        "state": "loading",
        "action": "wait",
        "target": None,
        "confidence": 0.99,
        "reason": "The screen is loading.",
    }
    image = np.zeros((100, 200, 3), dtype=np.uint8)

    result = make_engine(decision, wait_duration_ms=250).decide(image)

    assert result.action == WaitAction(250)


def test_noop_and_human_request_never_create_actions() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    for action, expected_status in (
        ("noop", "noop"),
        ("request_human", "human_required"),
    ):
        decision = {
            "state": "uncertain",
            "action": action,
            "target": None,
            "confidence": 0.99,
            "reason": "No automatic action is safe.",
        }

        result = make_engine(decision).decide(image)

        assert result.status == expected_status
        assert result.action is None


def test_decision_logs_image_response_parser_and_execution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    robot = MockRobotController()
    coordinator = DecisionCoordinator(
        make_engine(tap_decision()),
        ActionExecutor(robot),
    )

    with caplog.at_level(logging.INFO):
        result = coordinator.run(
            image,
            {"scenario": "checkout"},
            [target_detection()],
            execute=True,
        )

    assert result.image_id in caplog.text
    assert "Model response" in caplog.text
    assert "Decision parser result" in caplog.text
    assert "executed=true" in caplog.text


def test_replay_runs_saved_screenshot_without_hardware() -> None:
    fixture = (
        Path(__file__).parents[1]
        / "vision"
        / "fixtures"
        / "green_button.ppm"
    )
    detection = Detection(
        label="confirm_button",
        bbox=BoundingBox(5, 3, 10, 6),
        confidence=0.9,
        detector_type="opencv_color_contour",
    )
    engine = DecisionEngine(
        MockModelClient(tap_decision()),
        TargetResolver(),
        make_calibration(20, 12),
    )

    result = ReplayRunner(engine).run(
        fixture,
        {"test_case": "saved-green-button"},
        [detection],
    )

    assert result.action == TapAction(110, 70)
    assert result.executed is False
    model = engine.model_client
    assert isinstance(model, MockModelClient)
    assert model.calls[0][1]["replay_screenshot"] == str(fixture)
