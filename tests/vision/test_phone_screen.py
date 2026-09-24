from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from tapbot.vision.calibration import Calibration, Point2D, RobotWorkArea
from tapbot.vision.detector import ColorButtonConfig, ColorButtonDetector, VisionPipeline
from tapbot.vision.object_detection import (
    ObjectBoundingBox,
    ObjectDetection,
    ObjectDetectionError,
)
from tapbot.vision.screen import (
    InvalidQuadrilateralError,
    PhoneScreenDetector,
    PhoneScreenDetectorConfig,
    order_corners,
)


FIXTURE = Path(__file__).parent / "fixtures" / "green_button.ppm"


class StubObjectDetector:
    name = "ultralytics:test-phone.pt"

    def __init__(self, *detections: ObjectDetection) -> None:
        self.detections = detections

    def detect(self, _frame: np.ndarray) -> tuple[ObjectDetection, ...]:
        return self.detections


class FailingObjectDetector:
    name = "ultralytics:broken.pt"

    def detect(self, _frame: np.ndarray) -> tuple[ObjectDetection, ...]:
        raise ObjectDetectionError("model unavailable")


def phone_object(
    x: float,
    y: float,
    width: float,
    height: float,
    confidence: float = 0.9,
) -> ObjectDetection:
    return ObjectDetection(
        label="cell phone",
        confidence=confidence,
        bbox=ObjectBoundingBox(x, y, width, height),
        class_id=67,
        source="ultralytics:test-phone.pt",
    )


def phone_frame(*, multiple: bool = False) -> np.ndarray:
    frame = np.full((600, 900, 3), 30, dtype=np.uint8)
    if multiple:
        small = np.array([[50, 100], [230, 100], [230, 400], [50, 400]])
        cv2.fillConvexPoly(frame, small, (220, 220, 220))
        cv2.polylines(frame, [small], True, (5, 5, 5), 8)
    phone = np.array([[400, 40], [700, 60], [730, 560], [370, 550]])
    cv2.fillConvexPoly(frame, phone, (225, 225, 225))
    cv2.polylines(frame, [phone], True, (5, 5, 5), 8)
    return frame


def identity_calibration(width: int, height: int, name: str) -> Calibration:
    return Calibration(
        profile_name=name,
        camera_corners=(
            Point2D(0, 0),
            Point2D(width - 1, 0),
            Point2D(width - 1, height - 1),
            Point2D(0, height - 1),
        ),
        robot_points=(
            Point2D(0, 0),
            Point2D(width, 0),
            Point2D(width, height),
            Point2D(0, height),
        ),
        phone_width=width,
        phone_height=height,
        created_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        camera_resolution=(width, height),
        robot_work_area=RobotWorkArea(0, 100, 0, 100),
    )


def test_corner_ordering_normalizes_shuffled_points() -> None:
    ordered = order_corners([[620, 1020], [100, 80], [90, 1005], [620, 95]])

    assert [(point.x, point.y) for point in ordered] == [
        (100, 80),
        (620, 95),
        (620, 1020),
        (90, 1005),
    ]


@pytest.mark.parametrize(
    "points",
    [
        [[0, 0], [1, 1], [2, 2], [3, 3]],
        [[0, 0], [10, 0], [10, 0], [0, 10]],
        [[0, 0], [20, 0], [10, 2], [0, 20]],
    ],
)
def test_corner_ordering_rejects_malformed_quadrilateral(
    points: list[list[int]],
) -> None:
    with pytest.raises(InvalidQuadrilateralError):
        order_corners(points)


def test_contour_only_detection_is_preserved() -> None:
    detector = PhoneScreenDetector(
        config=PhoneScreenDetectorConfig(
            canonical_width=300,
            canonical_height=600,
        )
    )

    result = detector.process(phone_frame())

    assert result.detection.found is True
    assert result.detection.source == "contour"
    assert result.canonical_image is not None
    assert result.canonical_image.shape == (600, 300, 3)


def test_yolo_bbox_refines_roi_and_restores_full_frame_corners() -> None:
    detector = PhoneScreenDetector(
        config=PhoneScreenDetectorConfig(
            canonical_width=300,
            canonical_height=600,
        ),
        object_detector=StubObjectDetector(phone_object(340, 10, 430, 580, 0.93)),
    )

    result = detector.process(phone_frame())

    assert result.detection.source == "yolo+contour"
    assert result.detection.phone_bbox is not None
    assert result.detection.phone_bbox_confidence == pytest.approx(0.93)
    assert result.detection.corners is not None
    assert min(point.x for point in result.detection.corners) > 340
    assert max(point.x for point in result.detection.corners) > 700
    assert result.detection.debug_metadata["refinement_candidate_count"] >= 1
    assert result.canonical_image is not None
    assert result.canonical_image.shape == (600, 300, 3)


def test_multi_phone_best_candidate_uses_confidence_then_area() -> None:
    detector = PhoneScreenDetector(
        object_detector=StubObjectDetector(
            phone_object(30, 80, 230, 350, 0.7),
            phone_object(340, 10, 430, 580, 0.9),
        )
    )

    detection = detector.detect(phone_frame(multiple=True))

    assert detection.source == "yolo+contour"
    assert detection.phone_bbox_confidence == pytest.approx(0.9)
    assert detection.bbox is not None
    assert detection.bbox.x > 300
    assert detection.debug_metadata["phone_candidate_count"] == 2


def test_no_phone_and_no_contour_returns_explicit_failure() -> None:
    result = PhoneScreenDetector(
        object_detector=StubObjectDetector(),
    ).process(np.full((300, 400, 3), 40, dtype=np.uint8))

    assert result.detection.found is False
    assert result.detection.failure_reason == "no_phone_candidate"
    assert result.canonical_image is None


def test_yolo_failure_falls_back_to_contour() -> None:
    detection = PhoneScreenDetector(
        object_detector=FailingObjectDetector(),
    ).detect(phone_frame())

    assert detection.found is True
    assert detection.source == "contour"
    assert detection.debug_metadata["object_detection_error"] == "model unavailable"


def test_bbox_only_fallback_is_disabled_by_default() -> None:
    detection = PhoneScreenDetector(
        object_detector=StubObjectDetector(phone_object(100, 50, 200, 240)),
    ).detect(np.full((400, 500, 3), 40, dtype=np.uint8))

    assert detection.found is False
    assert detection.failure_reason == "screen_quad_not_found"
    assert detection.phone_bbox is not None
    assert detection.source is None


def test_bbox_only_fallback_can_be_enabled_explicitly() -> None:
    detection = PhoneScreenDetector(
        config=PhoneScreenDetectorConfig(bbox_fallback=True),
        object_detector=StubObjectDetector(phone_object(100, 50, 200, 240)),
    ).detect(np.full((400, 500, 3), 40, dtype=np.uint8))

    assert detection.found is True
    assert detection.source == "yolo+bbox-fallback"


def test_calibration_fallback_after_roi_refinement_failure() -> None:
    frame = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
    assert frame is not None
    height, width = frame.shape[:2]
    calibration = identity_calibration(width, height, "fixture-fallback")
    detector = PhoneScreenDetector(
        calibration,
        config=PhoneScreenDetectorConfig(min_area_ratio=0.7),
        object_detector=StubObjectDetector(phone_object(0, 0, width, height)),
    )

    result = detector.process(frame)

    assert result.detection.source == "calibration"
    assert result.detection.debug_metadata["fallback_reason"] == (
        "screen_quad_not_found"
    )
    assert result.canonical_image is not None
    assert result.canonical_image.shape == frame.shape


def test_downstream_detector_receives_yolo_refined_canonical_view() -> None:
    canonical = np.full((400, 200, 3), 220, dtype=np.uint8)
    canonical[280:330, 45:155] = (0, 255, 0)
    camera_corners = np.float32([[250, 40], [470, 65], [500, 540], [220, 525]])
    canonical_corners = np.float32([[0, 0], [199, 0], [199, 399], [0, 399]])
    canonical_to_camera = cv2.getPerspectiveTransform(
        canonical_corners,
        camera_corners,
    )
    camera_frame = cv2.warpPerspective(canonical, canonical_to_camera, (720, 600))
    pipeline = VisionPipeline(
        PhoneScreenDetector(
            config=PhoneScreenDetectorConfig(
                canonical_width=200,
                canonical_height=400,
            ),
            object_detector=StubObjectDetector(phone_object(190, 10, 340, 570)),
        ),
        [
            ColorButtonDetector(
                ColorButtonConfig(min_area=100, morphology_kernel_size=1)
            )
        ],
    )

    result = pipeline.process(camera_frame)

    assert result.rectified_image.shape == (400, 200, 3)
    assert result.phone_screen is not None
    assert result.phone_screen.source == "yolo+contour"
    assert len(result.detections) == 1
    assert result.detections[0].label == "green_button"
