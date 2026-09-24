"""Deterministic, hardware-free execution of a complete TapBot pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from tapbot.camera.manager import CameraManager
from tapbot.camera.mock_graph import MockHotspot
from tapbot.camera.mock_graph_source import MockGraphCameraSource
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
from tapbot.core.executor import ActionExecutor
from tapbot.model.client import MockModelClient, ModelClient
from tapbot.model.pipeline import (
    DecisionCoordinator,
    DecisionEngine,
    DecisionPolicy,
    DecisionResult,
)
from tapbot.model.resolver import TargetResolver
from tapbot.robot.mock import MockRobotController
from tapbot.simulation.bridge import CoordinateMapper, SimulationBridge
from tapbot.vision.calibration import Calibration, Point2D, RobotWorkArea
from tapbot.vision.detector import BoundingBox, Detection, VisionResult


TRACE_SCHEMA_VERSION = 1


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulationOutcome(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SimulationFailure(StrEnum):
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    SAME_STATE_REPEATED = "same_state_repeated"
    UNRESOLVED_TARGET = "unresolved_target"
    LOW_CONFIDENCE = "low_confidence"
    TAP_MISS = "tap_miss"
    PIPELINE_ERROR = "pipeline_error"


class SimulationFinishedError(RuntimeError):
    """Raised when a caller tries to step a terminal simulation."""


class SimulationTraceError(ValueError):
    """Raised when a saved trace is malformed or incompatible."""


class SimulationVision(Protocol):
    """Vision boundary used by the simulation runner."""

    def process(
        self,
        frame: NDArray[np.uint8],
        hotspots: Sequence[MockHotspot],
    ) -> VisionResult: ...


class MockGraphVision:
    """Expose graph hotspots as deterministic mock-vision detections."""

    detector_type = "mock_graph_fixture"

    def process(
        self,
        frame: NDArray[np.uint8],
        hotspots: Sequence[MockHotspot],
    ) -> VisionResult:
        detections = tuple(
            Detection(
                label=hotspot.label,
                bbox=BoundingBox(
                    x=round(hotspot.x),
                    y=round(hotspot.y),
                    width=round(hotspot.width),
                    height=round(hotspot.height),
                ),
                confidence=1.0,
                detector_type=self.detector_type,
            )
            for hotspot in hotspots
        )
        return VisionResult(frame.copy(), detections)


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    scenario_id: str
    target_state: str
    max_steps: int = 10
    same_state_limit: int = 2
    confidence_threshold: float = 0.8

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must not be empty")
        if not self.target_state:
            raise ValueError("target_state must not be empty")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.same_state_limit <= 0:
            raise ValueError("same_state_limit must be positive")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "target_state": self.target_state,
            "max_steps": self.max_steps,
            "same_state_limit": self.same_state_limit,
            "confidence_threshold": self.confidence_threshold,
        }

    @classmethod
    def from_dict(cls, value: object) -> SimulationConfig:
        if not isinstance(value, dict):
            raise SimulationTraceError("trace config must be an object")
        try:
            return cls(
                scenario_id=str(value["scenario_id"]),
                target_state=str(value["target_state"]),
                max_steps=int(value["max_steps"]),
                same_state_limit=int(value["same_state_limit"]),
                confidence_threshold=float(value["confidence_threshold"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SimulationTraceError("trace config is invalid") from error


@dataclass(frozen=True, slots=True)
class SimulationStepTrace:
    step: int
    timestamp: str
    frame_id: str
    state: str
    detections: tuple[dict[str, object], ...]
    model_decision: dict[str, object] | None
    action: dict[str, object] | None
    tap_coordinate: dict[str, float] | None
    next_state: str
    decision_status: str
    executed: bool
    events: tuple[dict[str, object], ...]
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "state": self.state,
            "detections": list(self.detections),
            "model_decision": self.model_decision,
            "action": self.action,
            "tap_coordinate": self.tap_coordinate,
            "next_state": self.next_state,
            "decision_status": self.decision_status,
            "executed": self.executed,
            "events": list(self.events),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: object) -> SimulationStepTrace:
        if not isinstance(value, dict):
            raise SimulationTraceError("trace step must be an object")
        try:
            detections = value["detections"]
            events = value["events"]
            if not isinstance(detections, list) or not all(
                isinstance(item, dict) for item in detections
            ):
                raise TypeError
            if not isinstance(events, list) or not all(
                isinstance(item, dict) for item in events
            ):
                raise TypeError
            model_decision = value.get("model_decision")
            action = value.get("action")
            tap_coordinate = value.get("tap_coordinate")
            if model_decision is not None and not isinstance(model_decision, dict):
                raise TypeError
            if action is not None and not isinstance(action, dict):
                raise TypeError
            if tap_coordinate is not None and not isinstance(tap_coordinate, dict):
                raise TypeError
            error = value.get("error")
            return cls(
                step=int(value["step"]),
                timestamp=str(value["timestamp"]),
                frame_id=str(value["frame_id"]),
                state=str(value["state"]),
                detections=tuple(dict(item) for item in detections),
                model_decision=(
                    None if model_decision is None else dict(model_decision)
                ),
                action=None if action is None else dict(action),
                tap_coordinate=(
                    None
                    if tap_coordinate is None
                    else {
                        str(key): float(number)
                        for key, number in tap_coordinate.items()
                    }
                ),
                next_state=str(value["next_state"]),
                decision_status=str(value["decision_status"]),
                executed=bool(value["executed"]),
                events=tuple(dict(item) for item in events),
                error=None if error is None else str(error),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SimulationTraceError("trace step is invalid") from error

    def replay_signature(self) -> dict[str, object]:
        """Return deterministic fields, excluding wall-clock event timestamps."""

        return {
            "frame_id": self.frame_id,
            "state": self.state,
            "detections": self.detections,
            "model_decision": self.model_decision,
            "action": self.action,
            "tap_coordinate": self.tap_coordinate,
            "next_state": self.next_state,
            "decision_status": self.decision_status,
            "executed": self.executed,
        }


@dataclass(slots=True)
class SimulationTrace:
    config: SimulationConfig
    started_at: str = field(default_factory=_timestamp)
    completed_at: str | None = None
    outcome: SimulationOutcome = SimulationOutcome.RUNNING
    failure_reason: SimulationFailure | None = None
    failure_detail: str | None = None
    steps: list[SimulationStepTrace] = field(default_factory=list)

    def succeed(self) -> None:
        self.outcome = SimulationOutcome.SUCCEEDED
        self.completed_at = _timestamp()

    def fail(self, reason: SimulationFailure, detail: str) -> None:
        self.outcome = SimulationOutcome.FAILED
        self.failure_reason = reason
        self.failure_detail = detail
        self.completed_at = _timestamp()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "config": self.config.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outcome": self.outcome.value,
            "failure_reason": (
                None if self.failure_reason is None else self.failure_reason.value
            ),
            "failure_detail": self.failure_detail,
            "steps": [step.to_dict() for step in self.steps],
        }

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    @classmethod
    def load(cls, path: str | Path) -> SimulationTrace:
        source = Path(path)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise SimulationTraceError(f"Could not read trace: {source}") from error
        except json.JSONDecodeError as error:
            raise SimulationTraceError(f"Trace is not valid JSON: {source}") from error
        if not isinstance(document, dict):
            raise SimulationTraceError("trace root must be an object")
        if document.get("schema_version") != TRACE_SCHEMA_VERSION:
            raise SimulationTraceError(
                f"Unsupported trace schema_version: {document.get('schema_version')!r}"
            )
        raw_steps = document.get("steps")
        if not isinstance(raw_steps, list):
            raise SimulationTraceError("trace steps must be an array")
        try:
            outcome = SimulationOutcome(str(document["outcome"]))
            raw_failure = document.get("failure_reason")
            failure = (
                None if raw_failure is None else SimulationFailure(str(raw_failure))
            )
            trace = cls(
                config=SimulationConfig.from_dict(document.get("config")),
                started_at=str(document["started_at"]),
                completed_at=(
                    None
                    if document.get("completed_at") is None
                    else str(document["completed_at"])
                ),
                outcome=outcome,
                failure_reason=failure,
                failure_detail=(
                    None
                    if document.get("failure_detail") is None
                    else str(document["failure_detail"])
                ),
                steps=[SimulationStepTrace.from_dict(item) for item in raw_steps],
            )
        except (KeyError, ValueError) as error:
            raise SimulationTraceError("trace metadata is invalid") from error
        return trace


@dataclass(frozen=True, slots=True)
class SimulationReplayResult:
    matched: bool
    expected: SimulationTrace
    actual: SimulationTrace
    mismatch_step: int | None = None
    detail: str | None = None


class SimulationRunner:
    """Run Camera → Vision → Model → Action → Robot → Graph iterations."""

    def __init__(
        self,
        config: SimulationConfig,
        camera_manager: CameraManager,
        robot: MockRobotController,
        coordinator: DecisionCoordinator,
        *,
        vision: SimulationVision | None = None,
        coordinate_mapper: CoordinateMapper | None = None,
    ) -> None:
        source = camera_manager.current_source()
        if not isinstance(source, MockGraphCameraSource):
            raise ValueError("Simulation requires an active mock_graph camera source")
        source_states = source.status()["states"]
        state_ids = {
            str(state["id"])
            for state in source_states
            if isinstance(state, dict) and "id" in state
        }
        if config.target_state not in state_ids:
            raise ValueError(
                f"target_state is not present in scenario: {config.target_state}"
            )
        self.config = config
        self.camera_manager = camera_manager
        self.robot = robot
        self.coordinator = coordinator
        self.vision = vision or MockGraphVision()
        self.trace = SimulationTrace(config)
        self._source = source
        self._step_events: list[dict[str, object]] = []
        self._same_state_count = 0
        self._closed = False
        self._bridge = SimulationBridge(
            robot,
            camera_manager,
            coordinate_mapper=coordinate_mapper,
            event_recorder=self._record_event,
        )
        self._bridge.start()

    @classmethod
    def for_scenario(
        cls,
        scenario_id: str,
        target_state: str,
        *,
        max_steps: int = 10,
        same_state_limit: int = 2,
        confidence_threshold: float = 0.8,
        model_client: ModelClient | None = None,
        vision: SimulationVision | None = None,
        coordinate_mapper: CoordinateMapper | None = None,
    ) -> SimulationRunner:
        config = SimulationConfig(
            scenario_id=scenario_id,
            target_state=target_state,
            max_steps=max_steps,
            same_state_limit=same_state_limit,
            confidence_threshold=confidence_threshold,
        )
        manager = CameraManager.with_defaults(
            f"mock:{scenario_id}", discovery_max_index=None
        )
        source = manager.current_source()
        assert isinstance(source, MockGraphCameraSource)
        status = source.status()
        width = int(status["screen_width"])
        height = int(status["screen_height"])
        calibration = _identity_calibration(width, height)
        client = model_client or MockModelClient(_default_model_response)
        engine = DecisionEngine(
            client,
            TargetResolver(minimum_detection_confidence=0),
            calibration,
            policy=DecisionPolicy(
                confidence_threshold=confidence_threshold,
                wait_duration_ms=0,
            ),
        )
        robot = MockRobotController()
        coordinator = DecisionCoordinator(
            engine,
            ActionExecutor(robot, sleep=lambda _: None),
        )
        return cls(
            config,
            manager,
            robot,
            coordinator,
            vision=vision,
            coordinate_mapper=coordinate_mapper,
        )

    @property
    def current_state(self) -> str:
        return self._source.current_state

    def step(self) -> SimulationStepTrace:
        """Execute exactly one complete pipeline iteration."""

        if self.trace.outcome is not SimulationOutcome.RUNNING:
            raise SimulationFinishedError(
                f"Simulation already finished: {self.trace.outcome.value}"
            )
        if self.current_state == self.config.target_state:
            self.trace.succeed()
            raise SimulationFinishedError("Simulation is already at the target state")
        if len(self.trace.steps) >= self.config.max_steps:
            self._fail_max_steps()
            raise SimulationFinishedError("Simulation reached max_steps")

        state = self.current_state
        frame = self.camera_manager.read_frame()
        vision_result = self.vision.process(frame, self._source.available_hotspots)
        self._step_events = []
        result = self.coordinator.run(
            vision_result.rectified_image,
            {
                "simulation": True,
                "scenario_id": self.config.scenario_id,
                "current_state": state,
                "step": len(self.trace.steps) + 1,
            },
            vision_result.detections,
            execute=True,
        )
        next_state = self.current_state
        step = SimulationStepTrace(
            step=len(self.trace.steps) + 1,
            timestamp=_timestamp(),
            frame_id=result.image_id,
            state=state,
            detections=tuple(
                detection.to_dict() for detection in vision_result.detections
            ),
            model_decision=(
                None if result.decision is None else result.decision.to_dict()
            ),
            action=_action_to_dict(result.action),
            tap_coordinate=_tap_coordinate(result.action),
            next_state=next_state,
            decision_status=result.status,
            executed=result.executed,
            events=tuple(dict(event) for event in self._step_events),
            error=result.error,
        )
        self.trace.steps.append(step)
        self._update_outcome(step, result)
        return step

    def run_auto(self) -> SimulationTrace:
        """Run until target state or the first deterministic failure."""

        if self.current_state == self.config.target_state:
            self.trace.succeed()
            return self.trace
        while self.trace.outcome is SimulationOutcome.RUNNING:
            self.step()
        return self.trace

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bridge.close()
        self.camera_manager.close_current()

    def __enter__(self) -> SimulationRunner:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @classmethod
    def replay(cls, expected: SimulationTrace) -> SimulationReplayResult:
        """Re-run a trace from its fixture and report the first divergence."""

        def recorded_response(
            _image: NDArray[np.uint8], context: Mapping[str, object]
        ) -> dict[str, object]:
            step_number = int(context["step"])
            if step_number > len(expected.steps):
                return _default_model_response(_image, context)
            decision = expected.steps[step_number - 1].model_decision
            if decision is None:
                return _default_model_response(_image, context)
            return dict(decision)

        mapper = _ReplayCoordinateMapper.from_trace(expected)
        with cls.for_scenario(
            expected.config.scenario_id,
            expected.config.target_state,
            max_steps=expected.config.max_steps,
            same_state_limit=expected.config.same_state_limit,
            confidence_threshold=expected.config.confidence_threshold,
            model_client=MockModelClient(recorded_response),
            coordinate_mapper=mapper,
        ) as runner:
            if expected.outcome is SimulationOutcome.RUNNING:
                for _ in expected.steps:
                    if runner.trace.outcome is not SimulationOutcome.RUNNING:
                        break
                    runner.step()
                actual = runner.trace
            else:
                actual = runner.run_auto()

        for index, expected_step in enumerate(expected.steps):
            if index >= len(actual.steps):
                return SimulationReplayResult(
                    False,
                    expected,
                    actual,
                    mismatch_step=index + 1,
                    detail="Replay ended before the recorded trace",
                )
            if (
                expected_step.replay_signature()
                != actual.steps[index].replay_signature()
            ):
                return SimulationReplayResult(
                    False,
                    expected,
                    actual,
                    mismatch_step=index + 1,
                    detail="Replay step differs from the recorded trace",
                )
        if len(expected.steps) != len(actual.steps):
            return SimulationReplayResult(
                False,
                expected,
                actual,
                mismatch_step=min(len(expected.steps), len(actual.steps)) + 1,
                detail="Replay produced a different number of steps",
            )
        if (
            expected.outcome != actual.outcome
            or expected.failure_reason != actual.failure_reason
        ):
            return SimulationReplayResult(
                False,
                expected,
                actual,
                detail="Replay outcome differs from the recorded trace",
            )
        return SimulationReplayResult(True, expected, actual)

    def _update_outcome(
        self, step: SimulationStepTrace, result: DecisionResult
    ) -> None:
        if step.next_state == self.config.target_state:
            self.trace.succeed()
            return
        if result.status == "confidence_below_threshold":
            self.trace.fail(
                SimulationFailure.LOW_CONFIDENCE,
                f"Step {step.step}: model confidence was below the threshold",
            )
            return
        if result.status == "target_not_found":
            self.trace.fail(
                SimulationFailure.UNRESOLVED_TARGET,
                f"Step {step.step}: model target could not be resolved",
            )
            return
        if any(event.get("type") == "mock.miss" for event in step.events):
            self.trace.fail(
                SimulationFailure.TAP_MISS,
                f"Step {step.step}: tap did not hit a graph hotspot",
            )
            return
        if result.status not in {"executed", "action_created"}:
            self.trace.fail(
                SimulationFailure.PIPELINE_ERROR,
                f"Step {step.step}: pipeline stopped with {result.status}",
            )
            return
        if step.state == step.next_state:
            self._same_state_count += 1
        else:
            self._same_state_count = 0
        if self._same_state_count >= self.config.same_state_limit:
            self.trace.fail(
                SimulationFailure.SAME_STATE_REPEATED,
                f"Step {step.step}: state {step.state!r} did not change for "
                f"{self._same_state_count} consecutive iterations",
            )
            return
        if len(self.trace.steps) >= self.config.max_steps:
            self._fail_max_steps()

    def _fail_max_steps(self) -> None:
        self.trace.fail(
            SimulationFailure.MAX_STEPS_EXCEEDED,
            f"Target state {self.config.target_state!r} was not reached within "
            f"{self.config.max_steps} steps",
        )

    def _record_event(
        self, event_type: str, payload: Mapping[str, object]
    ) -> None:
        self._step_events.append({"type": event_type, "payload": dict(payload)})


def _default_model_response(
    _image: NDArray[np.uint8], context: Mapping[str, object]
) -> dict[str, object]:
    detections = context.get("detections")
    target: str | None = None
    if isinstance(detections, list) and detections:
        first = detections[0]
        if isinstance(first, dict) and isinstance(first.get("label"), str):
            target = first["label"]
    return {
        "state": str(context.get("current_state", "unknown")),
        "action": "tap_target",
        "target": target or "unresolved_target",
        "confidence": 1.0,
        "reason": "Deterministic mock model selected the first visible target.",
    }


class _ReplayCoordinateMapper:
    def __init__(self, points: Sequence[tuple[float, float]]) -> None:
        self._points = tuple(points)
        self._index = 0

    @classmethod
    def from_trace(cls, trace: SimulationTrace) -> _ReplayCoordinateMapper:
        points: list[tuple[float, float]] = []
        for step in trace.steps:
            for event in step.events:
                if event.get("type") != "action.tap":
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                screen_x = payload.get("screen_x")
                screen_y = payload.get("screen_y")
                if isinstance(screen_x, (int, float)) and isinstance(
                    screen_y, (int, float)
                ):
                    points.append((float(screen_x), float(screen_y)))
        return cls(points)

    def robot_to_screen(self, x: float, y: float) -> tuple[float, float]:
        if self._index >= len(self._points):
            return x, y
        point = self._points[self._index]
        self._index += 1
        return point


def _identity_calibration(width: int, height: int) -> Calibration:
    corners = (
        Point2D(0, 0),
        Point2D(width, 0),
        Point2D(width, height),
        Point2D(0, height),
    )
    return Calibration(
        profile_name="simulation-identity",
        camera_corners=corners,
        robot_points=corners,
        phone_width=width,
        phone_height=height,
        robot_work_area=RobotWorkArea(0, width, 0, height),
        camera_resolution=(width, height),
    )


def _action_to_dict(action: Action | None) -> dict[str, object] | None:
    match action:
        case TapAction(x=x, y=y):
            return {"type": "tap", "x": float(x), "y": float(y)}
        case MoveAction(x=x, y=y):
            return {"type": "move", "x": float(x), "y": float(y)}
        case WaitAction(duration_ms=duration_ms):
            return {"type": "wait", "duration_ms": duration_ms}
        case HomeAction():
            return {"type": "home"}
        case PenUpAction():
            return {"type": "pen_up"}
        case PenDownAction():
            return {"type": "pen_down"}
        case EmergencyStopAction():
            return {"type": "emergency_stop"}
        case None:
            return None


def _tap_coordinate(action: Action | None) -> dict[str, float] | None:
    if not isinstance(action, TapAction):
        return None
    return {"x": float(action.x), "y": float(action.y)}
