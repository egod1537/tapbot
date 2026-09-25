from pathlib import Path

import cv2
import numpy as np

from tapbot.android.client import AndroidActionResult, AndroidScreenshot
from tapbot.camera.mock_graph import MockHotspot
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.device import AndroidRemoteController, MockGraphController
from tapbot.device.gesture import PointerGesture
from tapbot.macro import (
    DetectionStateClassifier,
    DetectionStateRule,
    MacroEngine,
    MacroStateMachine,
    MacroTrace,
    TapTargetAction,
)
from tapbot.model.resolver import TargetResolver
from tapbot.screen import AndroidRemoteScreenSource, MockGraphScreenSource
from tapbot.vision import CanonicalVisionPipeline
from tapbot.vision.detector import (
    BoundingBox,
    ColorButtonConfig,
    ColorButtonDetector,
    Detection,
)


class HotspotDetector:
    detector_type = "mock_hotspot"

    def __init__(self, source: MockGraphCameraSource) -> None:
        self.source = source

    def detect(self, _image: object) -> list[Detection]:
        return [self._detection(hotspot) for hotspot in self.source.available_hotspots]

    def _detection(self, hotspot: MockHotspot) -> Detection:
        return Detection(
            hotspot.label,
            BoundingBox(
                round(hotspot.x),
                round(hotspot.y),
                round(hotspot.width),
                round(hotspot.height),
            ),
            1.0,
            self.detector_type,
        )


def build_engine(tmp_path: Path) -> tuple[MacroEngine, MockGraphCameraSource]:
    graph = MockGraphCameraSource("reservation-flow")
    graph.open()
    source = MockGraphScreenSource(graph)
    classifier = DetectionStateClassifier(
        [
            DetectionStateRule("home", frozenset({"reservation_button"})),
            DetectionStateRule("reservation", frozenset({"verify_photo_button"})),
            DetectionStateRule("verify_photo", frozenset({"home_button"})),
        ]
    )
    state_machine = MacroStateMachine(
        {
            "home": TapTargetAction("reservation_button"),
            "reservation": TapTargetAction("verify_photo_button"),
        },
        terminal_states=["verify_photo"],
    )
    engine = MacroEngine(
        source,
        CanonicalVisionPipeline([HotspotDetector(graph)]),
        classifier,
        state_machine,
        TargetResolver(minimum_detection_confidence=0.5),
        MockGraphController(graph),
        artifact_dir=tmp_path / "frames",
    )
    return engine, graph


def test_same_macro_engine_drives_mock_source_and_records_replay_trace(
    tmp_path: Path,
) -> None:
    engine, graph = build_engine(tmp_path)

    first = engine.step()
    second = engine.step()
    trace_path = tmp_path / "trace.json"
    trace = engine.finish(trace_path)
    replay = MacroTrace.load(trace_path)

    assert first.classification.state == "home"
    assert first.trace.target == {
        "name": "reservation_button",
        "source": "detection",
        "screen": {"x": 640.0, "y": 540.0},
        "device": {"x": 640.0, "y": 540.0},
    }
    assert first.controller_result is not None
    assert first.controller_result.metadata["backend"] == "mock_graph"
    assert second.classification.state == "reservation"
    assert graph.current_state == "verify-photo"
    assert len(trace.steps) == 2
    assert replay.to_dict() == trace.to_dict()
    assert all(Path(step.screenshot_path or "").is_file() for step in trace.steps)


def test_unresolved_target_never_calls_controller(tmp_path: Path) -> None:
    engine, graph = build_engine(tmp_path)
    engine.state_machine = MacroStateMachine(
        {"home": TapTargetAction("missing_button")}
    )

    result = engine.step()

    assert result.trace.status == "target_not_found"
    assert result.controller_result is None
    assert graph.current_state == "home"


def test_canonical_vision_has_no_phone_detection_or_homography(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)

    result = engine.step(execute=False)

    assert result.vision.frame.metadata["already_canonical"] is True
    assert result.vision.detections[0].label == "reservation_button"
    assert not hasattr(result.vision, "phone_detection")
    assert not hasattr(result.vision, "homography")


class MacroAndroidClient:
    base_url = "http://android.test:8765"

    def __init__(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[30:70, 80:140] = (0, 255, 0)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        self.encoded = encoded.tobytes()
        self.taps: list[tuple[float, float, int]] = []

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "device": {"width": 200, "height": 100, "rotation": 0},
        }

    def screenshot(self) -> AndroidScreenshot:
        return AndroidScreenshot(
            self.encoded,
            "image/png",
            7,
            200,
            100,
            0,
            "2026-09-25T00:00:00Z",
        )

    def tap(self, x: float, y: float, *, duration_ms: int) -> AndroidActionResult:
        self.taps.append((x, y, duration_ms))
        return AndroidActionResult("req-7", "action-7", "tap", "completed")

    def gesture(self, gesture: PointerGesture) -> AndroidActionResult:
        first = gesture.points[0]
        self.taps.append((first.x, first.y, gesture.duration_ms))
        return AndroidActionResult("req-7", "action-7", "gesture", "completed")

    def swipe(self, *args: object, **kwargs: object) -> AndroidActionResult:
        raise AssertionError("swipe should not be called")

    def back(self) -> AndroidActionResult:
        raise AssertionError("back should not be called")

    def home(self) -> AndroidActionResult:
        raise AssertionError("home should not be called")


def test_android_screenshot_runs_vision_and_calls_remote_tap() -> None:
    client = MacroAndroidClient()
    source = AndroidRemoteScreenSource(client)  # type: ignore[arg-type]
    controller = AndroidRemoteController(client)  # type: ignore[arg-type]
    engine = MacroEngine(
        source,
        CanonicalVisionPipeline(
            [
                ColorButtonDetector(
                    ColorButtonConfig(
                        label="confirm_button",
                        min_area=100,
                        morphology_kernel_size=1,
                    )
                )
            ]
        ),
        DetectionStateClassifier(
            [DetectionStateRule("confirmation", frozenset({"confirm_button"}))]
        ),
        MacroStateMachine(
            {"confirmation": TapTargetAction("confirm_button")}
        ),
        TargetResolver(minimum_detection_confidence=0.5),
        controller,
    )

    result = engine.step()

    assert result.trace.status == "executed"
    assert result.trace.frame_id == "7"
    assert result.trace.api_result is not None
    assert result.trace.api_result["metadata"]["backend"] == "android_remote"
    assert len(client.taps) == 1
    tap_x, tap_y, duration = client.taps[0]
    assert 108 <= tap_x <= 111
    assert 48 <= tap_y <= 51
    assert duration == 70
