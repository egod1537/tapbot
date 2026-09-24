import cv2
import numpy as np

from tapbot.vision.detector import ColorButtonConfig, ColorButtonDetector
from tapbot.vision.object_detection import (
    ObjectBoundingBox,
    ObjectDetection,
)
from tapbot.vision.pipeline import ScreenPipeline
from tapbot.vision.screen import PhoneScreenDetector, PhoneScreenDetectorConfig


class StubObjectDetector:
    name = "ultralytics:test-phone.pt"

    def __init__(self, *detections: ObjectDetection) -> None:
        self.detections = detections

    def detect(self, _frame: np.ndarray) -> tuple[ObjectDetection, ...]:
        return self.detections


def phone_object() -> ObjectDetection:
    return ObjectDetection(
        label="cell phone",
        confidence=0.92,
        bbox=ObjectBoundingBox(190, 10, 340, 570),
        class_id=67,
        source="ultralytics:test-phone.pt",
    )


def physical_like_frame() -> np.ndarray:
    canonical = np.full((400, 200, 3), 220, dtype=np.uint8)
    canonical[280:330, 45:155] = (0, 255, 0)
    camera_corners = np.float32([[250, 40], [470, 65], [500, 540], [220, 525]])
    canonical_corners = np.float32([[0, 0], [199, 0], [199, 399], [0, 399]])
    matrix = cv2.getPerspectiveTransform(canonical_corners, camera_corners)
    return cv2.warpPerspective(canonical, matrix, (720, 600))


def ui_detector() -> ColorButtonDetector:
    return ColorButtonDetector(
        ColorButtonConfig(min_area=100, morphology_kernel_size=1)
    )


def test_physical_like_pipeline_runs_every_stage() -> None:
    events: list[str] = []
    pipeline = ScreenPipeline(
        PhoneScreenDetector(
            config=PhoneScreenDetectorConfig(
                canonical_width=200,
                canonical_height=400,
            ),
            object_detector=StubObjectDetector(phone_object()),
        ),
        [ui_detector()],
        event_recorder=lambda event_type, _payload: events.append(event_type),
    )

    result = pipeline.run(physical_like_frame(), frame_id=123)

    assert result.succeeded
    assert result.frame_id == 123
    assert result.phone_detection.found
    assert result.phone_detection.source == "yolo+contour"
    assert result.canonical_image is not None
    assert result.canonical_image.shape == (400, 200, 3)
    assert result.detections[0].label == "green_button"
    assert result.timings.phone_detection_ms >= 0
    assert result.timings.canonical_transform_ms >= 0
    assert result.timings.ui_detection_ms >= 0
    assert result.timings.total_ms >= 0
    assert events == [
        "screen.frame",
        "screen.phone_detect.start",
        "screen.phone_detect.result",
        "screen.canonical.ready",
        "screen.ui_detect.result",
    ]


def test_already_canonical_pipeline_skips_phone_and_transform() -> None:
    canonical = np.full((120, 200, 3), 30, dtype=np.uint8)
    canonical[40:80, 60:150] = (0, 255, 0)
    pipeline = ScreenPipeline(
        PhoneScreenDetector(object_detector=StubObjectDetector()),
        [ui_detector()],
        already_canonical=True,
    )

    result = pipeline.run(canonical, frame_id=8)

    assert result.succeeded
    assert result.already_canonical
    assert result.phone_detection.source == "already_canonical"
    assert result.phone_detection.debug_metadata["phone_detection_skipped"] is True
    assert result.canonical_image is not None
    assert np.array_equal(result.canonical_image, canonical)
    assert result.timings.phone_detection_ms == 0
    assert result.timings.canonical_transform_ms == 0
    assert len(result.detections) == 1


def test_no_phone_stops_before_canonical_and_ui_detection() -> None:
    events: list[str] = []
    pipeline = ScreenPipeline(
        PhoneScreenDetector(object_detector=StubObjectDetector()),
        [ui_detector()],
        event_recorder=lambda event_type, _payload: events.append(event_type),
    )

    result = pipeline.run(
        np.full((300, 400, 3), 30, dtype=np.uint8),
        frame_id=9,
    )

    assert not result.succeeded
    assert result.failure_stage == "phone_detection"
    assert result.error == "no_phone_candidate"
    assert result.canonical_image is None
    assert result.detections == ()
    assert "screen.canonical.ready" not in events
    assert "screen.ui_detect.result" not in events
    assert events[-1] == "screen.pipeline.error"
