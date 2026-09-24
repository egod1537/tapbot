"""One-step PC macro orchestration over interchangeable sources/controllers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time

import cv2

from tapbot.device.controller import ControllerResult, DeviceController
from tapbot.macro.actions import (
    BackAction,
    HomeAction,
    MacroAction,
    RequestHumanAction,
    ScreenshotAction,
    SwipeAction,
    TapTargetAction,
    WaitAction,
    action_to_dict,
)
from tapbot.macro.state import MacroStateMachine, StateClassification, StateClassifier
from tapbot.macro.trace import MacroStepTrace, MacroTrace
from tapbot.model.resolver import ResolvedTarget, TargetResolver
from tapbot.screen.geometry import ScreenGeometry, ScreenInsets
from tapbot.screen.source import ScreenFrame, ScreenSource
from tapbot.vision.canonical import CanonicalVisionPipeline, CanonicalVisionResult


GeometryFactory = Callable[[ScreenFrame, dict[str, object]], ScreenGeometry]


@dataclass(frozen=True, slots=True)
class MacroStepResult:
    frame: ScreenFrame
    vision: CanonicalVisionResult
    classification: StateClassification
    decision: MacroAction
    resolved_target: ResolvedTarget | None
    controller_result: ControllerResult | None
    trace: MacroStepTrace


class MacroEngine:
    """Run screenshot -> vision -> state -> action without camera rectification.

    The state classifier and any future VLM can only choose constrained
    ``MacroAction`` values. Target names are resolved against detector output
    here, and only this execution boundary invokes a ``DeviceController``.
    """

    def __init__(
        self,
        source: ScreenSource,
        vision: CanonicalVisionPipeline,
        classifier: StateClassifier,
        state_machine: MacroStateMachine,
        target_resolver: TargetResolver,
        controller: DeviceController,
        *,
        geometry_factory: GeometryFactory | None = None,
        artifact_dir: str | Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source = source
        self.vision = vision
        self.classifier = classifier
        self.state_machine = state_machine
        self.target_resolver = target_resolver
        self.controller = controller
        self.geometry_factory = geometry_factory or _default_geometry
        self.artifact_dir = None if artifact_dir is None else Path(artifact_dir)
        self.sleep = sleep
        self.trace = MacroTrace()

    def step(self, *, execute: bool = True) -> MacroStepResult:
        frame = self.source.screenshot()
        vision = self.vision.run(frame)
        classification = self.classifier.classify(frame, vision.detections)
        decision = self.state_machine.decide(classification)
        resolved: ResolvedTarget | None = None
        controller_result: ControllerResult | None = None
        api_result: dict[str, object] | None = None
        status = "planned"
        error: str | None = None
        target_trace: dict[str, object] | None = None

        if isinstance(decision, TapTargetAction):
            resolved = self.target_resolver.resolve(
                decision.target,
                vision.detections,
                screen_width=frame.width,
                screen_height=frame.height,
            )
            if resolved is None:
                status = "target_not_found"
                error = f"Target {decision.target!r} was not resolved"
            else:
                geometry = self.geometry_factory(frame, self.source.get_metadata())
                device_x, device_y = geometry.screen_to_device(
                    resolved.center.x,
                    resolved.center.y,
                )
                target_trace = {
                    "name": resolved.name,
                    "source": resolved.source,
                    "screen": {"x": resolved.center.x, "y": resolved.center.y},
                    "device": {"x": device_x, "y": device_y},
                }
                if execute:
                    try:
                        controller_result = self.controller.tap(
                            device_x,
                            device_y,
                            duration_ms=decision.duration_ms,
                        )
                        status = "executed"
                    except Exception as caught:
                        status = "execution_failed"
                        error = str(caught)
                        api_result = _error_result(caught)
        elif isinstance(decision, RequestHumanAction):
            status = "human_required"
            error = decision.reason
        elif execute:
            try:
                controller_result = self._execute_non_target(decision, frame)
                status = "executed"
            except Exception as caught:
                status = "execution_failed"
                error = str(caught)
                api_result = _error_result(caught)

        step_number = len(self.trace.steps) + 1
        screenshot_path = self._save_screenshot(frame, step_number)
        step_trace = MacroStepTrace(
            step=step_number,
            captured_at=frame.captured_at,
            source_id=frame.source_id,
            frame_id=frame.frame_id,
            screenshot_path=screenshot_path,
            state=classification.state,
            state_confidence=classification.confidence,
            detections=tuple(item.to_dict() for item in vision.detections),
            decision=action_to_dict(decision),
            action=(
                action_to_dict(decision)
                if status in {"planned", "executed", "execution_failed"}
                else None
            ),
            target=target_trace,
            api_result=(
                controller_result.to_dict()
                if controller_result is not None
                else api_result
            ),
            status=status,
            error=error,
        )
        self.trace.append(step_trace)
        return MacroStepResult(
            frame,
            vision,
            classification,
            decision,
            resolved,
            controller_result,
            step_trace,
        )

    def finish(self, path: str | Path | None = None) -> MacroTrace:
        self.trace.finish()
        if path is not None:
            self.trace.save(path)
        return self.trace

    def _execute_non_target(
        self,
        action: MacroAction,
        frame: ScreenFrame,
    ) -> ControllerResult | None:
        geometry = self.geometry_factory(frame, self.source.get_metadata())
        match action:
            case SwipeAction(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                duration_ms=duration_ms,
            ):
                device_start = geometry.screen_to_device(x1, y1)
                device_end = geometry.screen_to_device(x2, y2)
                return self.controller.swipe(
                    *device_start,
                    *device_end,
                    duration_ms=duration_ms,
                )
            case BackAction():
                return self.controller.back()
            case HomeAction():
                return self.controller.home()
            case WaitAction(duration_ms=duration_ms):
                self.sleep(duration_ms / 1000)
                return None
            case ScreenshotAction():
                return None
            case _:  # RequestHuman and TapTarget are handled before this method.
                raise TypeError(f"Unsupported macro action: {type(action).__name__}")

    def _save_screenshot(self, frame: ScreenFrame, step: int) -> str | None:
        if self.artifact_dir is None:
            return None
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        destination = self.artifact_dir / f"step-{step:04d}-{_safe_id(frame.frame_id)}.png"
        if not cv2.imwrite(str(destination), frame.image):
            raise OSError(f"Could not save macro screenshot: {destination}")
        return str(destination)


def _default_geometry(
    frame: ScreenFrame,
    metadata: dict[str, object],
) -> ScreenGeometry:
    agent = metadata.get("agent")
    device = agent.get("device") if isinstance(agent, dict) else None
    device = device if isinstance(device, dict) else {}
    width = _positive_int(device.get("width"), frame.width)
    height = _positive_int(device.get("height"), frame.height)
    rotation = _rotation(device.get("rotation"), frame.rotation)
    display = agent.get("display") if isinstance(agent, dict) else None
    display = display if isinstance(display, dict) else {}
    raw_insets = display.get("insets", device.get("insets"))
    raw_insets = raw_insets if isinstance(raw_insets, dict) else {}
    insets = ScreenInsets(
        top=_non_negative_number(raw_insets.get("top")),
        bottom=_non_negative_number(raw_insets.get("bottom")),
        left=_non_negative_number(raw_insets.get("left")),
        right=_non_negative_number(raw_insets.get("right")),
    )
    return ScreenGeometry(
        frame.width,
        frame.height,
        width,
        height,
        rotation,
        insets,
    )


def _positive_int(value: object, fallback: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return fallback


def _rotation(value: object, fallback: int) -> int:
    if isinstance(value, int) and value in (0, 90, 180, 270):
        return value
    return fallback


def _non_negative_number(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return 0.0


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)[:80]


def _error_result(error: Exception) -> dict[str, object]:
    result: dict[str, object] = {
        "ok": False,
        "error_type": type(error).__name__,
        "message": str(error),
    }
    for name in ("code", "request_id", "action_id", "outcome_unknown", "status"):
        value = getattr(error, name, None)
        if value is not None:
            result[name] = value
    return result
