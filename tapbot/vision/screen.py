"""Phone-screen detection and perspective canonicalization."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import cv2
import numpy as np
from numpy.typing import NDArray

from tapbot.vision.calibration import (
    Calibration,
    CalibrationError,
    Point2D,
    PointTuple,
    perspective_matrix,
    warp_perspective,
)


class PhoneScreenDetectionError(ValueError):
    """Base class for screen detection and canonicalization failures."""


class InvalidQuadrilateralError(PhoneScreenDetectionError):
    """Raised when four points cannot describe a safe screen polygon."""


class PhoneScreenNotFoundError(PhoneScreenDetectionError):
    """Raised when neither an automatic nor calibrated screen is available."""


@dataclass(frozen=True, slots=True)
class PhoneScreenDetectorConfig:
    """Device-independent contour and canonical-view settings."""

    min_area_ratio: float = 0.08
    max_area_ratio: float = 0.98
    min_long_short_ratio: float = 1.1
    max_long_short_ratio: float = 3.5
    approximation_epsilon_ratio: float = 0.025
    canny_low: int = 50
    canny_high: int = 150
    blur_kernel_size: int = 5
    canonical_width: int | None = None
    canonical_height: int | None = None

    def __post_init__(self) -> None:
        if not 0 < self.min_area_ratio < self.max_area_ratio <= 1:
            raise ValueError("area ratios must satisfy 0 < min < max <= 1")
        if not 1 <= self.min_long_short_ratio < self.max_long_short_ratio:
            raise ValueError("screen aspect-ratio bounds are invalid")
        if not 0 < self.approximation_epsilon_ratio < 0.2:
            raise ValueError("approximation_epsilon_ratio must be between 0 and 0.2")
        if not 0 <= self.canny_low < self.canny_high <= 255:
            raise ValueError("Canny thresholds must satisfy 0 <= low < high <= 255")
        if self.blur_kernel_size < 1 or self.blur_kernel_size % 2 == 0:
            raise ValueError("blur_kernel_size must be a positive odd number")
        for name, value in (
            ("canonical_width", self.canonical_width),
            ("canonical_height", self.canonical_height),
        ):
            if value is not None and (isinstance(value, bool) or value < 2):
                raise ValueError(f"{name} must be at least 2")


@dataclass(frozen=True, slots=True)
class ScreenBoundingBox:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class PhoneScreenDetection:
    found: bool
    confidence: float
    corners: PointTuple | None = None
    bbox: ScreenBoundingBox | None = None
    center: Point2D | None = None
    source: str | None = None
    failure_reason: str | None = None
    debug_metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.found and (
            self.corners is None or self.bbox is None or self.center is None
        ):
            raise ValueError("found screen detections require geometry")

    def geometry_dict(self) -> dict[str, object]:
        if not self.found or self.corners is None:
            return {
                "found": False,
                "confidence": self.confidence,
                "corners": None,
                "bbox": None,
                "center": None,
                "source": self.source,
                "failure_reason": self.failure_reason,
                "debug_metadata": self.debug_metadata,
            }
        tl, tr, br, bl = self.corners
        assert self.bbox is not None and self.center is not None
        return {
            "found": True,
            "confidence": self.confidence,
            "corners": {
                "tl": {"x": tl.x, "y": tl.y},
                "tr": {"x": tr.x, "y": tr.y},
                "br": {"x": br.x, "y": br.y},
                "bl": {"x": bl.x, "y": bl.y},
            },
            "bbox": self.bbox.to_dict(),
            "center": {"x": self.center.x, "y": self.center.y},
            "source": self.source,
            "failure_reason": None,
            "debug_metadata": self.debug_metadata,
        }

    def overlay_metadata(self) -> dict[str, object] | None:
        if not self.found or self.corners is None or self.center is None:
            return None
        labels = ("TL", "TR", "BR", "BL")
        return {
            "polygon": [
                {"x": point.x, "y": point.y} for point in self.corners
            ],
            "corners": [
                {"label": label, "x": point.x, "y": point.y}
                for label, point in zip(labels, self.corners)
            ],
            "center": {"x": self.center.x, "y": self.center.y},
            "label": f"phone_screen {self.confidence:.2f}",
        }


@dataclass(frozen=True, slots=True)
class PhoneScreenResult:
    detection: PhoneScreenDetection
    canonical_image: NDArray[np.uint8] | None
    canonical_width: int | None
    canonical_height: int | None
    homography: NDArray[np.float64] | None = field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class _Candidate:
    corners: PointTuple
    bbox: ScreenBoundingBox
    center: Point2D
    confidence: float
    metrics: dict[str, float | bool]


def order_corners(points: object) -> PointTuple:
    """Normalize four camera points to TL, TR, BR, BL order."""

    try:
        array = np.asarray(points, dtype=np.float64).reshape(4, 2)
    except (TypeError, ValueError) as error:
        raise InvalidQuadrilateralError("quadrilateral requires exactly four points") from error
    if not np.isfinite(array).all():
        raise InvalidQuadrilateralError("quadrilateral points must be finite")
    if len(np.unique(array, axis=0)) != 4:
        raise InvalidQuadrilateralError("quadrilateral points must be unique")

    center = array.mean(axis=0)
    angles = np.arctan2(array[:, 1] - center[1], array[:, 0] - center[0])
    ordered = array[np.argsort(angles)]
    ordered = np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)
    contour = ordered.astype(np.float32)
    if not cv2.isContourConvex(contour):
        raise InvalidQuadrilateralError("quadrilateral must be convex")
    area = abs(float(cv2.contourArea(contour)))
    if not math.isfinite(area) or area <= 1e-6:
        raise InvalidQuadrilateralError("quadrilateral must have positive area")
    return tuple(Point2D(float(x), float(y)) for x, y in ordered)  # type: ignore[return-value]


class PhoneScreenDetector:
    """Detect a phone screen and create its front-facing canonical view."""

    def __init__(
        self,
        calibration: Calibration | None = None,
        *,
        config: PhoneScreenDetectorConfig | None = None,
    ) -> None:
        self.calibration = calibration
        self.config = config or PhoneScreenDetectorConfig()

    def detect(self, frame: NDArray[np.uint8]) -> PhoneScreenDetection:
        self._validate_frame(frame)
        candidates = self._contour_candidates(frame)
        if candidates:
            best = max(candidates, key=lambda candidate: candidate.confidence)
            return PhoneScreenDetection(
                found=True,
                confidence=best.confidence,
                corners=best.corners,
                bbox=best.bbox,
                center=best.center,
                source="contour",
                debug_metadata={
                    "candidate_count": len(candidates),
                    "selected_metrics": best.metrics,
                    "edge_thresholds": {
                        "low": self.config.canny_low,
                        "high": self.config.canny_high,
                    },
                },
            )
        if self.calibration is not None:
            return self._calibration_detection(frame)
        return PhoneScreenDetection(
            found=False,
            confidence=0.0,
            failure_reason="no_phone_candidate",
            debug_metadata={"candidate_count": 0},
        )

    def process(self, frame: NDArray[np.uint8]) -> PhoneScreenResult:
        detection = self.detect(frame)
        return self.rectify_detection(frame, detection)

    def rectify_detection(
        self,
        frame: NDArray[np.uint8],
        detection: PhoneScreenDetection,
    ) -> PhoneScreenResult:
        """Create a canonical view from an already computed detection."""

        self._validate_frame(frame)
        if not detection.found or detection.corners is None:
            return PhoneScreenResult(detection, None, None, None)
        width, height = self._canonical_size(detection.corners, detection.source)
        use_native_calibration = (
            detection.source == "calibration"
            and self.calibration is not None
            and self.config.canonical_width is None
            and self.config.canonical_height is None
        )
        if use_native_calibration:
            assert self.calibration is not None
            canonical = self.calibration.rectify_frame(frame)
            destination = self.calibration.screen_corners
            matrix = perspective_matrix(
                detection.corners,
                destination,
                name="camera-to-canonical",
            )
        else:
            destination: PointTuple = (
                Point2D(0, 0),
                Point2D(width - 1, 0),
                Point2D(width - 1, height - 1),
                Point2D(0, height - 1),
            )
            matrix = perspective_matrix(
                detection.corners,
                destination,
                name="camera-to-canonical",
            )
            canonical = warp_perspective(frame, matrix, width, height)
        return PhoneScreenResult(detection, canonical, width, height, matrix)

    def detect_corners(self, frame: NDArray[np.uint8]) -> PointTuple:
        if self.calibration is not None:
            self._validate_frame(frame)
            self._validate_calibration_resolution(frame)
            return self.calibration.camera_corners
        detection = self.detect(frame)
        if not detection.found or detection.corners is None:
            raise PhoneScreenNotFoundError(
                detection.failure_reason or "no_phone_candidate"
            )
        return detection.corners

    def extract(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        if self.calibration is not None:
            self._validate_frame(frame)
            self._validate_calibration_resolution(frame)
            return self.calibration.rectify_frame(frame)
        result = self.process(frame)
        if result.canonical_image is None:
            raise PhoneScreenNotFoundError(
                result.detection.failure_reason or "no_phone_candidate"
            )
        return result.canonical_image

    def rectify(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        return self.extract(frame)

    def _contour_candidates(self, frame: NDArray[np.uint8]) -> list[_Candidate]:
        height, width = frame.shape[:2]
        frame_area = float(width * height)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.config.blur_kernel_size > 1:
            gray = cv2.GaussianBlur(
                gray,
                (self.config.blur_kernel_size, self.config.blur_kernel_size),
                0,
            )
        edges = cv2.Canny(gray, self.config.canny_low, self.config.canny_high)
        kernel = np.ones((3, 3), dtype=np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(
            edges,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        candidates: list[_Candidate] = []
        for contour in contours:
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0:
                continue
            approximation = cv2.approxPolyDP(
                contour,
                self.config.approximation_epsilon_ratio * perimeter,
                True,
            )
            if len(approximation) != 4 or not cv2.isContourConvex(approximation):
                continue
            try:
                corners = order_corners(approximation.reshape(4, 2))
            except InvalidQuadrilateralError:
                continue
            points = np.array(
                [[point.x, point.y] for point in corners],
                dtype=np.float32,
            )
            area = abs(float(cv2.contourArea(points)))
            area_ratio = area / frame_area
            if not self.config.min_area_ratio <= area_ratio <= self.config.max_area_ratio:
                continue

            top = self._distance(corners[0], corners[1])
            right = self._distance(corners[1], corners[2])
            bottom = self._distance(corners[2], corners[3])
            left = self._distance(corners[3], corners[0])
            screen_width = (top + bottom) / 2
            screen_height = (left + right) / 2
            short = min(screen_width, screen_height)
            long = max(screen_width, screen_height)
            if short <= 1e-6:
                continue
            long_short_ratio = long / short
            if not (
                self.config.min_long_short_ratio
                <= long_short_ratio
                <= self.config.max_long_short_ratio
            ):
                continue

            rectangle = cv2.minAreaRect(points)
            rectangle_area = float(rectangle[1][0] * rectangle[1][1])
            rectangularity = min(1.0, area / rectangle_area) if rectangle_area > 0 else 0.0
            x, y, bbox_width, bbox_height = cv2.boundingRect(points)
            margin = min(x, y, width - (x + bbox_width), height - (y + bbox_height))
            border_clearance = max(0.0, min(1.0, margin / (min(width, height) * 0.03)))
            area_score = min(1.0, area_ratio / 0.5)
            preferred_ratio = math.sqrt(
                self.config.min_long_short_ratio * self.config.max_long_short_ratio
            )
            ratio_span = math.log(
                self.config.max_long_short_ratio / self.config.min_long_short_ratio
            )
            aspect_score = max(
                0.0,
                1.0
                - abs(math.log(long_short_ratio / preferred_ratio))
                / max(ratio_span / 2, 1e-6),
            )
            confidence = max(
                0.0,
                min(
                    1.0,
                    0.40 * area_score
                    + 0.30 * rectangularity
                    + 0.20 * aspect_score
                    + 0.10 * border_clearance,
                ),
            )
            center = Point2D(
                sum(point.x for point in corners) / 4,
                sum(point.y for point in corners) / 4,
            )
            candidates.append(
                _Candidate(
                    corners,
                    ScreenBoundingBox(x, y, bbox_width, bbox_height),
                    center,
                    confidence,
                    {
                        "area_ratio": area_ratio,
                        "long_short_ratio": long_short_ratio,
                        "rectangularity": rectangularity,
                        "border_clearance": border_clearance,
                        "touches_frame_boundary": margin <= 0,
                    },
                )
            )
        return candidates

    def _calibration_detection(
        self,
        frame: NDArray[np.uint8],
    ) -> PhoneScreenDetection:
        assert self.calibration is not None
        self._validate_calibration_resolution(frame)
        corners = order_corners(
            [[point.x, point.y] for point in self.calibration.camera_corners]
        )
        points = np.array(
            [[point.x, point.y] for point in corners],
            dtype=np.float32,
        )
        x, y, width, height = cv2.boundingRect(points)
        center = Point2D(
            sum(point.x for point in corners) / 4,
            sum(point.y for point in corners) / 4,
        )
        return PhoneScreenDetection(
            found=True,
            confidence=1.0,
            corners=corners,
            bbox=ScreenBoundingBox(x, y, width, height),
            center=center,
            source="calibration",
            debug_metadata={
                "candidate_count": 0,
                "calibration_profile": self.calibration.profile_name,
            },
        )

    def _canonical_size(
        self,
        corners: PointTuple,
        source: str | None,
    ) -> tuple[int, int]:
        configured_width = self.config.canonical_width
        configured_height = self.config.canonical_height
        if configured_width is not None and configured_height is not None:
            return configured_width, configured_height
        if source == "calibration" and self.calibration is not None:
            natural_width = int(round(self.calibration.phone_width))
            natural_height = int(round(self.calibration.phone_height))
        else:
            natural_width = int(
                round(
                    (self._distance(corners[0], corners[1]) + self._distance(corners[3], corners[2]))
                    / 2
                )
            )
            natural_height = int(
                round(
                    (self._distance(corners[0], corners[3]) + self._distance(corners[1], corners[2]))
                    / 2
                )
            )
        if natural_width < 2 or natural_height < 2:
            raise CalibrationError("canonical size invalid")
        if configured_width is not None:
            return configured_width, max(
                2,
                int(round(configured_width * natural_height / natural_width)),
            )
        if configured_height is not None:
            return max(
                2,
                int(round(configured_height * natural_width / natural_height)),
            ), configured_height
        return natural_width, natural_height

    @staticmethod
    def _distance(first: Point2D, second: Point2D) -> float:
        return math.hypot(second.x - first.x, second.y - first.y)

    @staticmethod
    def _validate_frame(frame: object) -> None:
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.ndim != 3
            or frame.shape[2] != 3
            or frame.size == 0
        ):
            raise ValueError("Phone screen detection requires a non-empty uint8 BGR image")

    def _validate_calibration_resolution(self, frame: NDArray[np.uint8]) -> None:
        assert self.calibration is not None
        if self.calibration.camera_resolution is None:
            return
        expected_width, expected_height = self.calibration.camera_resolution
        actual_height, actual_width = frame.shape[:2]
        if (actual_width, actual_height) != (expected_width, expected_height):
            raise ValueError(
                "Camera frame resolution "
                f"{actual_width}x{actual_height} does not match calibration "
                f"{expected_width}x{expected_height}"
            )


def draw_phone_screen_overlay(
    frame: NDArray[np.uint8],
    detection: PhoneScreenDetection,
    *,
    copy: bool = True,
) -> NDArray[np.uint8]:
    """Draw the selected polygon, corner labels, center, and confidence."""

    PhoneScreenDetector._validate_frame(frame)
    output = frame.copy() if copy else frame
    if not detection.found or detection.corners is None or detection.center is None:
        return output
    points = np.array(
        [[round(point.x), round(point.y)] for point in detection.corners],
        dtype=np.int32,
    )
    cv2.polylines(output, [points], True, (0, 220, 255), 3, cv2.LINE_AA)
    for label, point in zip(("TL", "TR", "BR", "BL"), detection.corners):
        location = (round(point.x), round(point.y))
        cv2.circle(output, location, 6, (0, 80, 255), -1, cv2.LINE_AA)
        cv2.putText(
            output,
            label,
            (location[0] + 8, max(18, location[1] - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 220, 255),
            2,
            cv2.LINE_AA,
        )
    center = (round(detection.center.x), round(detection.center.y))
    cv2.drawMarker(output, center, (255, 80, 80), cv2.MARKER_CROSS, 18, 2)
    cv2.putText(
        output,
        f"phone screen {detection.confidence:.2f}",
        (int(points[0][0]), max(22, int(points[0][1]) - 28)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 220, 255),
        2,
        cv2.LINE_AA,
    )
    return output
