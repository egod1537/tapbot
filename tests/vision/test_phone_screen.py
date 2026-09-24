from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from tapbot.vision.calibration import Calibration, Point2D, RobotWorkArea
from tapbot.vision.detector import ColorButtonConfig, ColorButtonDetector, VisionPipeline
from tapbot.vision.screen import (
    InvalidQuadrilateralError,
    PhoneScreenDetector,
    PhoneScreenDetectorConfig,
    order_corners,
)


FIXTURE = Path(__file__).parent / "fixtures" / "green_button.ppm"


def phone_frame(*, multiple: bool = False) -> np.ndarray:
    frame = np.full((600, 900, 3), 30, dtype=np.uint8)
    if multiple:
        small = np.array([[50, 100], [190, 100], [190, 350], [50, 350]])
        cv2.fillConvexPoly(frame, small, (220, 220, 220))
        cv2.polylines(frame, [small], True, (5, 5, 5), 8)
    phone = np.array([[400, 40], [700, 60], [730, 560], [370, 550]])
    cv2.fillConvexPoly(frame, phone, (225, 225, 225))
    cv2.polylines(frame, [phone], True, (5, 5, 5), 8)
    return frame


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


def test_contour_detection_creates_configured_canonical_view() -> None:
    detector = PhoneScreenDetector(
        config=PhoneScreenDetectorConfig(
            canonical_width=300,
            canonical_height=600,
        )
    )

    result = detector.process(phone_frame())

    assert result.detection.found is True
    assert result.detection.source == "contour"
    assert result.detection.confidence > 0.6
    assert result.canonical_image is not None
    assert result.canonical_image.shape == (600, 300, 3)
    assert result.homography is not None
    assert result.homography.shape == (3, 3)


def test_no_detection_returns_explicit_failure() -> None:
    result = PhoneScreenDetector().process(
        np.full((300, 400, 3), 40, dtype=np.uint8)
    )

    assert result.detection.found is False
    assert result.detection.failure_reason == "no_phone_candidate"
    assert result.canonical_image is None


def test_multi_candidate_selection_prefers_larger_phone_like_rectangle() -> None:
    detection = PhoneScreenDetector().detect(phone_frame(multiple=True))

    assert detection.found is True
    assert detection.bbox is not None
    assert detection.bbox.x > 300
    assert detection.bbox.height > 450
    assert detection.debug_metadata["candidate_count"] >= 2


def test_fixture_regression_uses_calibration_fallback() -> None:
    frame = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
    assert frame is not None
    height, width = frame.shape[:2]
    calibration = Calibration(
        profile_name="fixture-fallback",
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
    detector = PhoneScreenDetector(
        calibration,
        config=PhoneScreenDetectorConfig(min_area_ratio=0.7),
    )

    result = detector.process(frame)

    assert result.detection.source == "calibration"
    assert result.canonical_image is not None
    assert result.canonical_image.shape == frame.shape


def test_downstream_detector_receives_automatic_canonical_view() -> None:
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
            )
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
    assert result.phone_screen.source == "contour"
    assert len(result.detections) == 1
    assert result.detections[0].label == "green_button"
