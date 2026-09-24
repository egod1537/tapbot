from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pytest

from tapbot.vision.calibration import (
    Calibration,
    CalibrationError,
    CalibrationStore,
    CoordinateOutOfBoundsError,
    Point2D,
    RobotWorkArea,
)


def make_calibration(profile_name: str = "phone-a") -> Calibration:
    return Calibration(
        profile_name=profile_name,
        camera_corners=(
            Point2D(100, 100),
            Point2D(500, 120),
            Point2D(540, 900),
            Point2D(80, 880),
        ),
        robot_points=(
            Point2D(10, 20),
            Point2D(210, 20),
            Point2D(210, 420),
            Point2D(10, 420),
        ),
        phone_width=1000,
        phone_height=2000,
        created_at=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        camera_resolution=(640, 960),
        robot_work_area=RobotWorkArea(0, 300, 0, 500),
    )


def assert_point(point: Point2D, x: float, y: float) -> None:
    assert point.x == pytest.approx(x, abs=1e-5)
    assert point.y == pytest.approx(y, abs=1e-5)


def test_screen_center_maps_to_expected_robot_center() -> None:
    calibration = make_calibration()

    assert_point(calibration.screen_to_robot(500, 1000), 110, 220)


def test_robot_to_screen_is_inverse_mapping() -> None:
    calibration = make_calibration()

    screen = calibration.robot_to_screen(110, 220)

    assert_point(screen, 500, 1000)


def test_camera_perspective_maps_phone_center_to_robot_center() -> None:
    calibration = make_calibration()
    camera_center = calibration.screen_to_camera(500, 1000)

    robot = calibration.camera_to_robot(camera_center.x, camera_center.y)

    assert_point(robot, 110, 220)


def test_rectifies_camera_frame_to_phone_dimensions() -> None:
    calibration = make_calibration()
    frame = np.zeros((960, 640, 3), dtype=np.uint8)

    rectified = calibration.rectify_frame(frame)

    assert rectified.shape == (2000, 1000, 3)


@pytest.mark.parametrize("x,y", [(-1, 100), (1001, 100), (100, 2001)])
def test_rejects_screen_coordinates_outside_phone(x: float, y: float) -> None:
    with pytest.raises(CoordinateOutOfBoundsError):
        make_calibration().screen_to_robot(x, y)


def test_rejects_robot_coordinates_outside_work_area() -> None:
    with pytest.raises(CoordinateOutOfBoundsError, match="work area"):
        make_calibration().robot_to_screen(301, 100)


def test_rejects_non_finite_coordinates() -> None:
    with pytest.raises(CalibrationError, match="finite"):
        make_calibration().screen_to_robot(float("nan"), 100)


def test_rejects_degenerate_calibration_points() -> None:
    with pytest.raises(CalibrationError, match="non-degenerate"):
        Calibration(
            profile_name="invalid",
            camera_corners=(
                Point2D(0, 0),
                Point2D(1, 1),
                Point2D(2, 2),
                Point2D(3, 3),
            ),
            robot_points=(
                Point2D(0, 0),
                Point2D(100, 0),
                Point2D(100, 100),
                Point2D(0, 100),
            ),
            phone_width=100,
            phone_height=100,
            robot_work_area=RobotWorkArea(0, 200, 0, 200),
        )


def test_store_round_trip_preserves_transform(tmp_path: Path) -> None:
    path = tmp_path / "calibrations.json"
    store = CalibrationStore(path)
    original = make_calibration()
    expected = original.screen_to_robot(250, 750)

    store.save(original)
    loaded = store.load()

    assert loaded.to_dict() == original.to_dict()
    assert_point(loaded.screen_to_robot(250, 750), expected.x, expected.y)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["active_profile"] == "phone-a"


def test_store_supports_multiple_profiles(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path / "calibrations.json")

    store.save(make_calibration("phone-a"))
    store.save(make_calibration("phone-b"))

    assert store.list_profiles() == ["phone-a", "phone-b"]
    assert store.load().profile_name == "phone-b"
    assert store.load("phone-a").profile_name == "phone-a"
