"""Camera, phone-screen, and robot coordinate calibration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from os import PathLike
from pathlib import Path
from typing import Any, TypeAlias

import cv2
import numpy as np
from numpy.typing import NDArray


class CalibrationError(ValueError):
    """Base class for invalid calibration data or transformations."""


class CalibrationNotFoundError(CalibrationError):
    """Raised when a requested calibration profile does not exist."""


class CoordinateOutOfBoundsError(CalibrationError):
    """Raised when an input or transformed point is outside its safe area."""


class CoordinateTransformError(CalibrationError):
    """Raised when a homography cannot produce a finite point."""


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise CalibrationError("Point coordinates must be finite")

    def as_list(self) -> list[float]:
        return [self.x, self.y]

    @classmethod
    def from_value(cls, value: object) -> Point2D:
        if isinstance(value, dict):
            try:
                return cls(float(value["x"]), float(value["y"]))
            except (KeyError, TypeError, ValueError) as error:
                raise CalibrationError("Point must contain numeric x and y") from error
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return cls(float(value[0]), float(value[1]))
            except (TypeError, ValueError) as error:
                raise CalibrationError("Point coordinates must be numeric") from error
        raise CalibrationError("Point must be [x, y] or an object with x and y")


@dataclass(frozen=True, slots=True)
class RobotWorkArea:
    min_x: float = 0
    max_x: float = 1000
    min_y: float = 0
    max_y: float = 1000

    def __post_init__(self) -> None:
        values = (self.min_x, self.max_x, self.min_y, self.max_y)
        if not all(math.isfinite(value) for value in values):
            raise CalibrationError("Robot work area values must be finite")
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise CalibrationError("Robot work area minimums must be less than maximums")

    def contains(self, point: Point2D) -> bool:
        return (
            self.min_x <= point.x <= self.max_x
            and self.min_y <= point.y <= self.max_y
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": self.min_x,
            "max_x": self.max_x,
            "min_y": self.min_y,
            "max_y": self.max_y,
        }


PointTuple: TypeAlias = tuple[Point2D, Point2D, Point2D, Point2D]


@dataclass(frozen=True, slots=True)
class Calibration:
    """A four-corner mapping among camera, screen, and robot coordinates.

    Corner order is always top-left, top-right, bottom-right, bottom-left.
    """

    profile_name: str
    camera_corners: PointTuple
    robot_points: PointTuple
    phone_width: float
    phone_height: float
    robot_work_area: RobotWorkArea
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    camera_resolution: tuple[int, int] | None = None
    _camera_to_screen_matrix: NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )
    _screen_to_camera_matrix: NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )
    _screen_to_robot_matrix: NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )
    _robot_to_screen_matrix: NDArray[np.float64] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.profile_name.strip():
            raise CalibrationError("profile_name must not be empty")
        if not math.isfinite(self.phone_width) or self.phone_width <= 0:
            raise CalibrationError("phone_width must be a positive finite number")
        if not math.isfinite(self.phone_height) or self.phone_height <= 0:
            raise CalibrationError("phone_height must be a positive finite number")
        if len(self.camera_corners) != 4 or len(self.robot_points) != 4:
            raise CalibrationError("Exactly four camera and robot points are required")
        if self.created_at.tzinfo is None:
            raise CalibrationError("created_at must include timezone information")
        if self.camera_resolution is not None:
            width, height = self.camera_resolution
            if isinstance(width, bool) or isinstance(height, bool) or width <= 0 or height <= 0:
                raise CalibrationError("camera_resolution must contain positive integers")
            if not isinstance(width, int) or not isinstance(height, int):
                raise CalibrationError("camera_resolution must contain integers")
            for point in self.camera_corners:
                if not 0 <= point.x <= width or not 0 <= point.y <= height:
                    raise CalibrationError(
                        "Camera corner is outside the recorded camera resolution"
                    )
        for point in self.robot_points:
            if not self.robot_work_area.contains(point):
                raise CalibrationError("Robot reference point is outside the work area")

        camera = self._points_array(self.camera_corners)
        screen = self._points_array(self.screen_corners)
        robot = self._points_array(self.robot_points)
        self._validate_quadrilateral("camera_corners", camera)
        self._validate_quadrilateral("robot_points", robot)

        camera_to_screen = cv2.getPerspectiveTransform(camera, screen)
        screen_to_robot = cv2.getPerspectiveTransform(screen, robot)
        self._validate_matrix("camera-to-screen", camera_to_screen)
        self._validate_matrix("screen-to-robot", screen_to_robot)
        object.__setattr__(self, "_camera_to_screen_matrix", camera_to_screen)
        object.__setattr__(
            self,
            "_screen_to_camera_matrix",
            self._invert_matrix("camera-to-screen", camera_to_screen),
        )
        object.__setattr__(self, "_screen_to_robot_matrix", screen_to_robot)
        object.__setattr__(
            self,
            "_robot_to_screen_matrix",
            self._invert_matrix("screen-to-robot", screen_to_robot),
        )

    @property
    def screen_corners(self) -> PointTuple:
        return (
            Point2D(0, 0),
            Point2D(self.phone_width, 0),
            Point2D(self.phone_width, self.phone_height),
            Point2D(0, self.phone_height),
        )

    def screen_to_robot(self, x: float, y: float) -> Point2D:
        screen = Point2D(x, y)
        self._require_screen_bounds(screen)
        robot = self._transform(screen, self._screen_to_robot_matrix)
        if not self.robot_work_area.contains(robot):
            raise CoordinateOutOfBoundsError(
                f"Transformed robot point ({robot.x}, {robot.y}) is outside the work area"
            )
        return robot

    def robot_to_screen(self, x: float, y: float) -> Point2D:
        robot = Point2D(x, y)
        if not self.robot_work_area.contains(robot):
            raise CoordinateOutOfBoundsError(
                f"Robot point ({x}, {y}) is outside the work area"
            )
        screen = self._transform(robot, self._robot_to_screen_matrix)
        self._require_screen_bounds(screen, transformed=True)
        return screen

    def camera_to_screen(self, x: float, y: float) -> Point2D:
        camera = Point2D(x, y)
        if self.camera_resolution is not None:
            width, height = self.camera_resolution
            if not 0 <= x <= width or not 0 <= y <= height:
                raise CoordinateOutOfBoundsError(
                    f"Camera point ({x}, {y}) is outside the camera resolution"
                )
        screen = self._transform(camera, self._camera_to_screen_matrix)
        self._require_screen_bounds(screen, transformed=True)
        return screen

    def screen_to_camera(self, x: float, y: float) -> Point2D:
        screen = Point2D(x, y)
        self._require_screen_bounds(screen)
        camera = self._transform(screen, self._screen_to_camera_matrix)
        if self.camera_resolution is not None:
            width, height = self.camera_resolution
            if not 0 <= camera.x <= width or not 0 <= camera.y <= height:
                raise CoordinateOutOfBoundsError(
                    "Transformed camera point is outside the camera resolution"
                )
        return camera

    def camera_to_robot(self, x: float, y: float) -> Point2D:
        screen = self.camera_to_screen(x, y)
        return self.screen_to_robot(screen.x, screen.y)

    def rectify_frame(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Warp a camera BGR frame into the phone's front-facing plane."""

        if not isinstance(frame, np.ndarray) or frame.ndim < 2:
            raise CalibrationError("frame must be a valid image array")
        size = (int(round(self.phone_width)), int(round(self.phone_height)))
        if size[0] <= 0 or size[1] <= 0:
            raise CalibrationError("phone dimensions are too small to rectify")
        return cv2.warpPerspective(frame, self._camera_to_screen_matrix, size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "camera_corners": [point.as_list() for point in self.camera_corners],
            "robot_points": [point.as_list() for point in self.robot_points],
            "phone_logical_size": {
                "width": self.phone_width,
                "height": self.phone_height,
            },
            "created_at": self.created_at.isoformat(),
            "camera_resolution": (
                None
                if self.camera_resolution is None
                else list(self.camera_resolution)
            ),
            "robot_work_area": self.robot_work_area.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> Calibration:
        if not isinstance(value, dict):
            raise CalibrationError("Calibration profile must be a JSON object")
        try:
            logical_size = value["phone_logical_size"]
            work_area = value["robot_work_area"]
            if not isinstance(logical_size, dict) or not isinstance(work_area, dict):
                raise TypeError
            camera_resolution_value = value.get("camera_resolution")
            camera_resolution = (
                None
                if camera_resolution_value is None
                else (
                    int(camera_resolution_value[0]),
                    int(camera_resolution_value[1]),
                )
            )
            camera_points = tuple(
                Point2D.from_value(point) for point in value["camera_corners"]
            )
            robot_points = tuple(
                Point2D.from_value(point) for point in value["robot_points"]
            )
            if len(camera_points) != 4 or len(robot_points) != 4:
                raise CalibrationError("Exactly four camera and robot points are required")
            return cls(
                profile_name=str(value["profile_name"]),
                camera_corners=camera_points,  # type: ignore[arg-type]
                robot_points=robot_points,  # type: ignore[arg-type]
                phone_width=float(logical_size["width"]),
                phone_height=float(logical_size["height"]),
                created_at=datetime.fromisoformat(str(value["created_at"])),
                camera_resolution=camera_resolution,
                robot_work_area=RobotWorkArea(
                    min_x=float(work_area["min_x"]),
                    max_x=float(work_area["max_x"]),
                    min_y=float(work_area["min_y"]),
                    max_y=float(work_area["max_y"]),
                ),
            )
        except CalibrationError:
            raise
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise CalibrationError("Invalid calibration profile structure") from error

    def _require_screen_bounds(
        self, point: Point2D, *, transformed: bool = False
    ) -> None:
        if not 0 <= point.x <= self.phone_width or not 0 <= point.y <= self.phone_height:
            prefix = "Transformed screen" if transformed else "Screen"
            raise CoordinateOutOfBoundsError(
                f"{prefix} point ({point.x}, {point.y}) is outside the phone screen"
            )

    @staticmethod
    def _points_array(points: PointTuple) -> NDArray[np.float32]:
        return np.array([[point.x, point.y] for point in points], dtype=np.float32)

    @staticmethod
    def _validate_quadrilateral(name: str, points: NDArray[np.float32]) -> None:
        area = abs(float(cv2.contourArea(points)))
        if not math.isfinite(area) or area <= 1e-6:
            raise CalibrationError(f"{name} must form a non-degenerate quadrilateral")

    @staticmethod
    def _validate_matrix(name: str, matrix: NDArray[np.float64]) -> None:
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
            raise CalibrationError(f"Could not calculate {name} homography")
        determinant = float(np.linalg.det(matrix))
        if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
            raise CalibrationError(f"{name} homography is singular")

    @staticmethod
    def _invert_matrix(
        name: str, matrix: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        try:
            inverse = np.linalg.inv(matrix)
        except np.linalg.LinAlgError as error:
            raise CalibrationError(f"{name} homography is not invertible") from error
        Calibration._validate_matrix(f"inverse {name}", inverse)
        return inverse

    @staticmethod
    def _transform(
        point: Point2D, matrix: NDArray[np.float64]
    ) -> Point2D:
        source = np.array([[[point.x, point.y]]], dtype=np.float64)
        try:
            transformed = cv2.perspectiveTransform(source, matrix)[0, 0]
        except cv2.error as error:
            raise CoordinateTransformError("Perspective transform failed") from error
        x, y = float(transformed[0]), float(transformed[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise CoordinateTransformError("Perspective transform produced NaN or infinity")
        return Point2D(x, y)


class CalibrationStore:
    """Versioned JSON storage that can hold multiple device profiles."""

    FORMAT_VERSION = 1

    def __init__(self, path: str | PathLike[str]) -> None:
        self.path = Path(path)

    def save(self, calibration: Calibration, *, make_active: bool = True) -> None:
        document = self._read_document(allow_missing=True)
        profiles = document.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            raise CalibrationError("Calibration profiles must be a JSON object")
        profiles[calibration.profile_name] = calibration.to_dict()
        if make_active:
            document["active_profile"] = calibration.profile_name

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def load(self, profile_name: str | None = None) -> Calibration:
        document = self._read_document(allow_missing=False)
        selected = profile_name or document.get("active_profile")
        if not isinstance(selected, str) or not selected:
            raise CalibrationNotFoundError("No active calibration profile")
        profiles = document.get("profiles")
        if not isinstance(profiles, dict) or selected not in profiles:
            raise CalibrationNotFoundError(
                f"Calibration profile does not exist: {selected}"
            )
        return Calibration.from_dict(profiles[selected])

    def list_profiles(self) -> list[str]:
        document = self._read_document(allow_missing=True)
        profiles = document.get("profiles", {})
        if not isinstance(profiles, dict):
            raise CalibrationError("Calibration profiles must be a JSON object")
        return sorted(str(name) for name in profiles)

    def _read_document(self, *, allow_missing: bool) -> dict[str, Any]:
        if not self.path.exists():
            if allow_missing:
                return {"version": self.FORMAT_VERSION, "profiles": {}}
            raise CalibrationNotFoundError(f"Calibration file does not exist: {self.path}")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CalibrationError(f"Could not read calibration file: {self.path}") from error
        if not isinstance(value, dict):
            raise CalibrationError("Calibration file root must be a JSON object")
        if value.get("version") != self.FORMAT_VERSION:
            raise CalibrationError(
                f"Unsupported calibration format version: {value.get('version')!r}"
            )
        return value
