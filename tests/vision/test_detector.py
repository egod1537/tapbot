from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from tapbot.vision.calibration import Calibration, Point2D, RobotWorkArea
from tapbot.vision.detector import (
    BoundingBox,
    ColorButtonConfig,
    ColorButtonDetector,
    VisionPipeline,
    draw_debug_overlay,
    save_debug_overlay,
)
from tapbot.vision.screen import PhoneScreenDetector


FIXTURE = Path(__file__).parent / "fixtures" / "green_button.ppm"


def identity_calibration(width: int, height: int) -> Calibration:
    return Calibration(
        profile_name="vision-test",
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


def fixture_detector() -> ColorButtonDetector:
    return ColorButtonDetector(
        ColorButtonConfig(min_area=10, morphology_kernel_size=1)
    )


def test_saved_image_detection_is_reproducible() -> None:
    image = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
    assert image is not None
    detector = fixture_detector()

    first = detector.detect(image)
    second = detector.detect(image.copy())

    assert first == second
    assert len(first) == 1
    assert first[0].label == "green_button"
    assert first[0].bbox == BoundingBox(x=5, y=3, width=10, height=6)
    assert first[0].center == Point2D(10, 6)
    assert first[0].detector_type == "opencv_color_contour"
    assert 0.7 < first[0].confidence <= 1


def test_detector_ignores_shapes_below_minimum_area() -> None:
    image = np.zeros((30, 30, 3), dtype=np.uint8)
    image[5:8, 5:8] = (0, 255, 0)

    detections = ColorButtonDetector(
        ColorButtonConfig(min_area=20, morphology_kernel_size=1)
    ).detect(image)

    assert detections == []


def test_debug_overlay_draws_bbox_label_and_center(tmp_path: Path) -> None:
    image = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
    detections = fixture_detector().detect(image)

    overlay = draw_debug_overlay(image, detections)
    output_path = save_debug_overlay(tmp_path / "overlay.png", image, detections)

    assert not np.array_equal(overlay, image)
    assert output_path.exists()
    assert cv2.imread(str(output_path)) is not None


def test_pipeline_rectifies_before_detection() -> None:
    rectified = np.zeros((100, 200, 3), dtype=np.uint8)
    rectified[40:70, 70:130] = (0, 255, 0)
    camera_corners = np.float32([[30, 20], [250, 10], [270, 150], [20, 160]])
    screen_corners = np.float32([[0, 0], [200, 0], [200, 100], [0, 100]])
    screen_to_camera = cv2.getPerspectiveTransform(screen_corners, camera_corners)
    camera_frame = cv2.warpPerspective(rectified, screen_to_camera, (300, 180))
    calibration = Calibration(
        profile_name="perspective-test",
        camera_corners=tuple(Point2D(*point) for point in camera_corners),  # type: ignore[arg-type]
        robot_points=(
            Point2D(10, 20),
            Point2D(210, 20),
            Point2D(210, 120),
            Point2D(10, 120),
        ),
        phone_width=200,
        phone_height=100,
        camera_resolution=(300, 180),
        robot_work_area=RobotWorkArea(0, 300, 0, 200),
    )
    pipeline = VisionPipeline(
        PhoneScreenDetector(calibration),
        [ColorButtonDetector(ColorButtonConfig(min_area=100))],
    )

    result = pipeline.process(camera_frame)

    assert result.rectified_image.shape == (100, 200, 3)
    assert len(result.detections) == 1
    center = result.detections[0].center
    assert center.x == pytest.approx(100, abs=2)
    assert center.y == pytest.approx(55, abs=2)
    robot = calibration.screen_to_robot(center.x, center.y)
    assert robot.x == pytest.approx(110, abs=2)
    assert robot.y == pytest.approx(75, abs=2)


def test_phone_screen_detector_rejects_non_bgr_input() -> None:
    detector = PhoneScreenDetector(identity_calibration(20, 12))

    with pytest.raises(ValueError, match="BGR"):
        detector.extract(np.zeros((12, 20), dtype=np.uint8))


def test_phone_screen_detector_rejects_resolution_mismatch() -> None:
    detector = PhoneScreenDetector(identity_calibration(20, 12))

    with pytest.raises(ValueError, match="does not match calibration"):
        detector.extract(np.zeros((24, 40, 3), dtype=np.uint8))
