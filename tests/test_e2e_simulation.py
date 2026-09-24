from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from tapbot.camera.mock_graph import MockHotspot
from tapbot.model.client import MockModelClient
from tapbot.simulation import (
    SimulationFailure,
    SimulationFinishedError,
    SimulationOutcome,
    SimulationRunner,
    SimulationTrace,
)
from tapbot.simulation.cli import main as simulation_main
from tapbot.vision.detector import VisionResult


def decision(
    *,
    action: str = "tap_target",
    target: str | None = "reservation_button",
    confidence: float = 1.0,
) -> dict[str, object]:
    return {
        "state": "fixture-state",
        "action": action,
        "target": target,
        "confidence": confidence,
        "reason": "E2E failure-path fixture",
    }


def test_auto_mode_runs_complete_hardware_free_pipeline(tmp_path: Path) -> None:
    trace_path = tmp_path / "reservation-trace.json"

    with SimulationRunner.for_scenario(
        "reservation-flow", "verify-photo", max_steps=5
    ) as runner:
        trace = runner.run_auto()
        trace.save(trace_path)

    assert trace.outcome is SimulationOutcome.SUCCEEDED
    assert [step.state for step in trace.steps] == ["home", "reservation"]
    assert [step.next_state for step in trace.steps] == [
        "reservation",
        "verify-photo",
    ]
    assert all(step.frame_id.startswith("sha256:") for step in trace.steps)
    assert trace.steps[0].detections[0]["label"] == "reservation_button"
    assert trace.steps[0].model_decision == {
        "state": "home",
        "action": "tap_target",
        "target": "reservation_button",
        "confidence": 1.0,
        "reason": "Deterministic mock model selected the first visible target.",
    }
    assert trace.steps[0].action == {"type": "tap", "x": 640.0, "y": 540.0}
    assert trace.steps[0].tap_coordinate == {"x": 640.0, "y": 540.0}
    assert [event["type"] for event in trace.steps[0].events] == [
        "action.tap",
        "mock.hit",
        "mock.transition",
    ]
    assert SimulationTrace.load(trace_path).to_dict() == trace.to_dict()


def test_step_mode_executes_exactly_one_iteration_at_a_time() -> None:
    with SimulationRunner.for_scenario(
        "reservation-flow", "verify-photo", max_steps=5
    ) as runner:
        first = runner.step()
        assert first.next_state == "reservation"
        assert runner.trace.outcome is SimulationOutcome.RUNNING

        second = runner.step()
        assert second.next_state == "verify-photo"
        assert runner.trace.outcome is SimulationOutcome.SUCCEEDED

        try:
            runner.step()
        except SimulationFinishedError:
            pass
        else:  # pragma: no cover - documents the terminal-state contract
            raise AssertionError("terminal simulation accepted another step")


def test_max_steps_failure_identifies_last_state_and_action() -> None:
    with SimulationRunner.for_scenario(
        "reservation-flow", "verify-photo", max_steps=1
    ) as runner:
        trace = runner.run_auto()

    assert trace.outcome is SimulationOutcome.FAILED
    assert trace.failure_reason is SimulationFailure.MAX_STEPS_EXCEEDED
    assert trace.steps[-1].state == "home"
    assert trace.steps[-1].next_state == "reservation"
    assert trace.steps[-1].action is not None


def test_same_state_repetition_is_a_distinct_failure() -> None:
    model = MockModelClient(
        decision(action="wait", target=None),
    )
    with SimulationRunner.for_scenario(
        "reservation-flow",
        "verify-photo",
        max_steps=5,
        same_state_limit=2,
        model_client=model,
    ) as runner:
        trace = runner.run_auto()

    assert trace.failure_reason is SimulationFailure.SAME_STATE_REPEATED
    assert len(trace.steps) == 2
    assert all(step.state == step.next_state == "home" for step in trace.steps)


def test_unresolved_target_and_low_confidence_are_distinct_failures() -> None:
    cases = (
        (
            MockModelClient(decision(target="not_visible")),
            SimulationFailure.UNRESOLVED_TARGET,
        ),
        (
            MockModelClient(decision(confidence=0.2)),
            SimulationFailure.LOW_CONFIDENCE,
        ),
    )
    for model, expected in cases:
        with SimulationRunner.for_scenario(
            "reservation-flow",
            "verify-photo",
            model_client=model,
        ) as runner:
            trace = runner.run_auto()
        assert trace.failure_reason is expected
        assert len(trace.steps) == 1


def test_tap_miss_is_recorded_with_action_location() -> None:
    class MissMapper:
        def robot_to_screen(self, x: float, y: float) -> tuple[float, float]:
            return 0, 0

    with SimulationRunner.for_scenario(
        "reservation-flow",
        "verify-photo",
        coordinate_mapper=MissMapper(),
    ) as runner:
        trace = runner.run_auto()

    assert trace.failure_reason is SimulationFailure.TAP_MISS
    step = trace.steps[0]
    assert step.tap_coordinate == {"x": 640.0, "y": 540.0}
    assert step.next_state == "home"
    assert any(event["type"] == "mock.miss" for event in step.events)


def test_saved_trace_can_be_replayed_and_divergence_is_reported(
    tmp_path: Path,
) -> None:
    with SimulationRunner.for_scenario(
        "reservation-flow", "verify-photo"
    ) as runner:
        expected = runner.run_auto()

    replay = SimulationRunner.replay(expected)
    assert replay.matched is True
    assert replay.actual.outcome is SimulationOutcome.SUCCEEDED

    changed_step = replace(expected.steps[0], next_state="unexpected")
    changed = SimulationTrace(
        config=expected.config,
        started_at=expected.started_at,
        completed_at=expected.completed_at,
        outcome=expected.outcome,
        steps=[changed_step, *expected.steps[1:]],
    )
    mismatch = SimulationRunner.replay(changed)
    assert mismatch.matched is False
    assert mismatch.mismatch_step == 1

    trace_path = tmp_path / "trace.json"
    replay_path = tmp_path / "replay.json"
    expected.save(trace_path)
    assert simulation_main(
        ["--replay", str(trace_path), "--trace", str(replay_path)]
    ) == 0
    assert replay_path.is_file()


def test_failure_trace_replay_uses_recorded_decision_and_tap_mapping() -> None:
    class MissMapper:
        def robot_to_screen(self, x: float, y: float) -> tuple[float, float]:
            return 0, 0

    with SimulationRunner.for_scenario(
        "reservation-flow",
        "verify-photo",
        model_client=MockModelClient(decision(target="reservation_button")),
        coordinate_mapper=MissMapper(),
    ) as runner:
        expected = runner.run_auto()

    replay = SimulationRunner.replay(expected)

    assert expected.failure_reason is SimulationFailure.TAP_MISS
    assert replay.matched is True
    assert replay.actual.failure_reason is SimulationFailure.TAP_MISS


def test_custom_vision_result_can_trigger_unresolved_target() -> None:
    class NoDetectionVision:
        def process(
            self,
            frame: NDArray[np.uint8],
            hotspots: Sequence[MockHotspot],
        ) -> VisionResult:
            return VisionResult(frame.copy(), ())

    with SimulationRunner.for_scenario(
        "reservation-flow",
        "verify-photo",
        vision=NoDetectionVision(),
    ) as runner:
        trace = runner.run_auto()

    assert trace.failure_reason is SimulationFailure.UNRESOLVED_TARGET
