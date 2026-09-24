"""PC-side Android debug proxy, canonical vision, and macro state service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

import cv2

from tapbot.android.client import AndroidAgentClient
from tapbot.device.android import AndroidRemoteController
from tapbot.macro import (
    DetectionStateClassifier,
    DetectionStateRule,
    MacroEngine,
    MacroStateMachine,
    StateClassifier,
    TapTargetAction,
)
from tapbot.model.resolver import TargetResolver
from tapbot.screen.android import AndroidRemoteScreenSource
from tapbot.screen.geometry import ScreenGeometry
from tapbot.screen.source import ScreenFrame
from tapbot.ui.services import EventLog
from tapbot.vision.canonical import CanonicalVisionPipeline, CanonicalVisionResult
from tapbot.vision.detector import Detector


@dataclass(frozen=True, slots=True)
class EncodedAndroidFrame:
    content: bytes
    frame_id: str
    width: int
    height: int
    rotation: int
    captured_at: str


class AndroidDebugService:
    """Keep Android auth, screen state, and macro execution on the PC backend."""

    def __init__(
        self,
        client: AndroidAgentClient,
        detectors: tuple[Detector, ...],
        event_log: EventLog,
        *,
        classifier: StateClassifier | None = None,
        state_machine: MacroStateMachine | None = None,
        capture_dir: str | Path = "tapbot-captures/android",
    ) -> None:
        self.client = client
        self.source = AndroidRemoteScreenSource(client)
        self.controller = AndroidRemoteController(client)
        self.vision = CanonicalVisionPipeline(detectors)
        self.classifier = classifier or _default_classifier()
        self.state_machine = state_machine or _default_state_machine()
        self.target_resolver = TargetResolver(minimum_detection_confidence=0.5)
        self.event_log = event_log
        self.capture_dir = Path(capture_dir)
        self._lock = RLock()
        self._macro_id = _macro_id()
        self._macro_status = "IDLE"
        self._macro = self._new_macro_engine()
        self._previous_state: str | None = None
        self._current_state = "unknown"
        self._state_confidence = 0.0
        self._latest_vision: CanonicalVisionResult | None = None
        self._latest_frame_jpeg: bytes | None = None
        self._last_action: dict[str, object] | None = None
        self._last_action_result: dict[str, object] | None = None
        self._blocked_reason: str | None = None
        self._last_error: str | None = None

    def status(self) -> dict[str, object]:
        try:
            agent = self.source.refresh_status()
        except Exception as error:
            with self._lock:
                self._last_error = str(error)
            return {
                "configured": True,
                "connected": False,
                "error": str(error),
                "agent": None,
                "stream": None,
                "macro_status": self.macro_status,
            }
        stream = agent.get("stream")
        with self._lock:
            self._last_error = None
        return {
            "configured": True,
            "connected": True,
            "error": None,
            "agent": agent,
            "stream": stream if isinstance(stream, dict) else None,
            "macro_status": self.macro_status,
        }

    @property
    def macro_status(self) -> str:
        with self._lock:
            return self._macro_status

    def screenshot(self) -> EncodedAndroidFrame:
        frame = self.source.screenshot()
        encoded = _encode_jpeg(frame)
        with self._lock:
            self._latest_frame_jpeg = encoded
            self._last_error = None
        return _encoded(frame, encoded)

    def save_screenshot(self) -> dict[str, object]:
        frame = self.source.screenshot()
        destination = self.capture_dir / "snapshots" / (
            f"{_file_timestamp()}-{_safe_id(frame.frame_id)}.png"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), frame.image):
            raise OSError(f"Could not save Android screenshot: {destination}")
        self.event_log.add(
            f"Android screenshot saved: {destination.name}",
            event_type="android.screenshot.saved",
            category="android",
            status="success",
            payload={"frame_id": frame.frame_id, "path": str(destination)},
        )
        return {
            "ok": True,
            "frame": _frame_metadata(frame),
            "path": str(destination),
        }

    def run_vision(self) -> dict[str, object]:
        frame = self.source.screenshot()
        result = self.vision.run(frame)
        classification = self.classifier.classify(frame, result.detections)
        encoded = _encode_jpeg(frame)
        with self._lock:
            if classification.state != self._current_state:
                self._previous_state = self._current_state
            self._current_state = classification.state
            self._state_confidence = classification.confidence
            self._latest_vision = result
            self._latest_frame_jpeg = encoded
            self._blocked_reason = None
            self._last_error = None
        self.event_log.add(
            f"Android vision detected {len(result.detections)} objects",
            event_type="android.vision.result",
            category="vision",
            status="success",
            latency_ms=result.ui_detection_ms,
            payload={
                "frame_id": frame.frame_id,
                "state": classification.state,
                "detections": len(result.detections),
            },
        )
        return self.debug_state()

    def latest_vision_frame(self) -> EncodedAndroidFrame | None:
        with self._lock:
            result = self._latest_vision
            content = self._latest_frame_jpeg
        if result is None or content is None:
            return None
        return _encoded(result.frame, content)

    def manual_tap(
        self,
        x: float,
        y: float,
        *,
        duration_ms: int = 70,
    ) -> dict[str, object]:
        frame = self.source.latest_frame()
        status = self.source.refresh_status()
        device = status.get("device")
        device = device if isinstance(device, dict) else {}
        geometry = ScreenGeometry(
            frame.width,
            frame.height,
            _positive_int(device.get("width"), frame.width),
            _positive_int(device.get("height"), frame.height),
            _rotation(device.get("rotation"), frame.rotation),
        )
        device_x, device_y = geometry.screen_to_device(x, y)
        result = self.controller.tap(device_x, device_y, duration_ms=duration_ms)
        payload = {
            "ok": True,
            "screen": {"x": x, "y": y},
            "device": {"x": device_x, "y": device_y},
            "result": result.to_dict(),
        }
        self._remember_action(
            {"type": "manual_tap", "x": device_x, "y": device_y},
            result.to_dict(),
        )
        self.event_log.add(
            f"Manual Android tap: ({device_x:.1f}, {device_y:.1f})",
            event_type="android.tap.manual",
            category="android",
            status="success",
            payload=payload,
        )
        return payload

    def back(self) -> dict[str, object]:
        result = self.controller.back()
        self._remember_action({"type": "back"}, result.to_dict())
        self._record_primitive("back", result.to_dict())
        return {"ok": True, "result": result.to_dict()}

    def home(self) -> dict[str, object]:
        result = self.controller.home()
        self._remember_action({"type": "home"}, result.to_dict())
        self._record_primitive("home", result.to_dict())
        return {"ok": True, "result": result.to_dict()}

    def start_macro(self) -> dict[str, object]:
        with self._lock:
            self._macro_status = "RUNNING"
        self._record_macro("started")
        return self.debug_state()

    def pause_macro(self) -> dict[str, object]:
        with self._lock:
            self._macro_status = "PAUSED"
        self._record_macro("paused")
        return self.debug_state()

    def stop_macro(self) -> dict[str, object]:
        with self._lock:
            self._macro_status = "STOPPED"
            macro_id = self._macro_id
            macro = self._macro
        trace_path = self.capture_dir / "macros" / macro_id / "trace.json"
        macro.finish(trace_path)
        self._record_macro("stopped", {"trace_path": str(trace_path)})
        return self.debug_state()

    def reset_macro(self) -> dict[str, object]:
        with self._lock:
            self._macro_id = _macro_id()
            self._macro_status = "IDLE"
            self._macro = self._new_macro_engine()
            self._previous_state = None
            self._current_state = "unknown"
            self._state_confidence = 0.0
            self._last_action = None
            self._last_action_result = None
            self._blocked_reason = None
            self._last_error = None
        self._record_macro("reset")
        return self.debug_state()

    def step_macro(self) -> dict[str, object]:
        with self._lock:
            macro = self._macro
            before = self._macro_status
            self._macro_status = "STEPPING"
        try:
            result = macro.step(execute=True)
        except Exception as error:
            with self._lock:
                self._macro_status = before
                self._last_error = str(error)
                self._blocked_reason = str(error)
            self._record_macro("step failed", {"error": str(error)}, level="error")
            raise
        trace = result.trace
        encoded = _encode_jpeg(result.frame)
        with self._lock:
            if result.classification.state != self._current_state:
                self._previous_state = self._current_state
            self._current_state = result.classification.state
            self._state_confidence = result.classification.confidence
            self._latest_vision = result.vision
            self._latest_frame_jpeg = encoded
            self._last_action = trace.decision
            self._last_action_result = trace.api_result
            self._blocked_reason = trace.error
            self._last_error = trace.error if trace.status == "execution_failed" else None
            self._macro_status = before
        self._record_macro(
            "step",
            {
                "step": trace.step,
                "state": trace.state,
                "status": trace.status,
                "action": trace.action,
            },
            level="error" if trace.status == "execution_failed" else "info",
        )
        return self.debug_state()

    def debug_state(self) -> dict[str, object]:
        with self._lock:
            vision = self._latest_vision
            trace_steps = tuple(self._macro.trace.steps)
            last_step = trace_steps[-1] if trace_steps else None
            return {
                "state": {
                    "current": self._current_state,
                    "previous": self._previous_state,
                    "confidence": self._state_confidence,
                },
                "macro": {
                    "id": self._macro_id,
                    "status": self._macro_status,
                    "step_index": len(trace_steps),
                },
                "frame": (
                    None if vision is None else _frame_metadata(vision.frame)
                ),
                "detections": (
                    []
                    if vision is None
                    else [
                        {"id": f"{item.detector_type}:{index}", **item.to_dict()}
                        for index, item in enumerate(vision.detections)
                    ]
                ),
                "vision_latency_ms": (
                    None if vision is None else vision.ui_detection_ms
                ),
                "decision": {
                    "classifier": {
                        "state": self._current_state,
                        "confidence": self._state_confidence,
                    },
                    "vlm": None,
                    "target": None if last_step is None else last_step.target,
                    "final_action": self._last_action,
                    "blocked_reason": self._blocked_reason,
                },
                "last_action": self._last_action,
                "last_action_result": self._last_action_result,
                "error": self._last_error,
            }

    def stream(self):
        return self.client.iter_stream()

    def _new_macro_engine(self) -> MacroEngine:
        return MacroEngine(
            self.source,
            self.vision,
            self.classifier,
            self.state_machine,
            self.target_resolver,
            self.controller,
            artifact_dir=self.capture_dir / "macros" / self._macro_id / "frames",
        )

    def _remember_action(
        self,
        action: dict[str, object],
        result: dict[str, object],
    ) -> None:
        with self._lock:
            self._last_action = action
            self._last_action_result = result
            self._blocked_reason = None
            self._last_error = None

    def _record_primitive(self, command: str, payload: dict[str, object]) -> None:
        self.event_log.add(
            f"Android primitive: {command}",
            event_type=f"android.{command}",
            category="android",
            status="success",
            payload=payload,
        )

    def _record_macro(
        self,
        action: str,
        payload: dict[str, object] | None = None,
        *,
        level: str = "info",
    ) -> None:
        self.event_log.add(
            f"Android macro {action}",
            level=level,
            event_type=f"macro.{action.replace(' ', '_')}",
            category="macro",
            status="error" if level == "error" else "success",
            trace_id=self._macro_id,
            payload=payload,
        )


def _default_classifier() -> DetectionStateClassifier:
    return DetectionStateClassifier(
        (
            DetectionStateRule("home", frozenset({"reservation_button"})),
            DetectionStateRule("reservation", frozenset({"verify_photo_button"})),
            DetectionStateRule("verify_photo", frozenset({"home_button"})),
            DetectionStateRule("confirmation", frozenset({"confirm_button"})),
        )
    )


def _default_state_machine() -> MacroStateMachine:
    return MacroStateMachine(
        {
            "home": TapTargetAction("reservation_button"),
            "reservation": TapTargetAction("verify_photo_button"),
            "confirmation": TapTargetAction("confirm_button"),
        },
        terminal_states=("verify_photo",),
    )


def _encode_jpeg(frame: ScreenFrame) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise OSError("Could not encode Android screen frame")
    return encoded.tobytes()


def _encoded(frame: ScreenFrame, content: bytes) -> EncodedAndroidFrame:
    return EncodedAndroidFrame(
        content,
        frame.frame_id,
        frame.width,
        frame.height,
        frame.rotation,
        frame.captured_at,
    )


def _frame_metadata(frame: ScreenFrame) -> dict[str, object]:
    return {
        "frame_id": frame.frame_id,
        "source_id": frame.source_id,
        "captured_at": frame.captured_at,
        "width": frame.width,
        "height": frame.height,
        "rotation": frame.rotation,
        "already_canonical": True,
    }


def _macro_id() -> str:
    return f"macro-{uuid4().hex[:12]}"


def _file_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _safe_id(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in value
    )[:80]


def _positive_int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback


def _rotation(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and value in (0, 90, 180, 270) else fallback
