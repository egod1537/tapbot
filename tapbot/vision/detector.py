"""Deterministic OpenCV detectors and debug visualization."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from tapbot.vision.calibration import Point2D
from tapbot.vision.screen import (
    PhoneScreenDetection,
    PhoneScreenDetector,
    PhoneScreenNotFoundError,
)


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError("Bounding box origin must not be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Bounding box dimensions must be positive")

    @property
    def center(self) -> Point2D:
        return Point2D(self.x + self.width / 2, self.y + self.height / 2)

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class Detection:
    label: str
    bbox: BoundingBox
    confidence: float
    detector_type: str

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("Detection label must not be empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Detection confidence must be between 0 and 1")
        if not self.detector_type:
            raise ValueError("detector_type must not be empty")

    @property
    def center(self) -> Point2D:
        return self.bbox.center

    def to_dict(self) -> dict[str, object]:
        center = self.center
        return {
            "label": self.label,
            "bbox": self.bbox.to_dict(),
            "center": {"x": center.x, "y": center.y},
            "confidence": self.confidence,
            "detector_type": self.detector_type,
        }


class Detector(Protocol):
    """Interface implemented by all rectified-screen detectors."""

    def detect(self, image: NDArray[np.uint8]) -> list[Detection]: ...


@dataclass(frozen=True, slots=True)
class ColorButtonConfig:
    """HSV range and contour constraints for a solid-color button."""

    label: str = "green_button"
    lower_hsv: tuple[int, int, int] = (35, 80, 80)
    upper_hsv: tuple[int, int, int] = (85, 255, 255)
    min_area: float = 100
    morphology_kernel_size: int = 3

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("label must not be empty")
        for name, values in (("lower_hsv", self.lower_hsv), ("upper_hsv", self.upper_hsv)):
            if len(values) != 3 or any(value < 0 or value > 255 for value in values):
                raise ValueError(f"{name} must contain three values from 0 to 255")
        if any(low > high for low, high in zip(self.lower_hsv, self.upper_hsv)):
            raise ValueError("lower_hsv must not exceed upper_hsv")
        if self.min_area <= 0:
            raise ValueError("min_area must be positive")
        if self.morphology_kernel_size < 1 or self.morphology_kernel_size % 2 == 0:
            raise ValueError("morphology_kernel_size must be a positive odd number")


class ColorButtonDetector:
    """Detect solid-color button candidates in a rectified BGR screen."""

    detector_type = "opencv_color_contour"

    def __init__(self, config: ColorButtonConfig | None = None) -> None:
        self.config = config or ColorButtonConfig()

    def detect(self, image: NDArray[np.uint8]) -> list[Detection]:
        self._validate_image(image)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.array(self.config.lower_hsv, dtype=np.uint8),
            np.array(self.config.upper_hsv, dtype=np.uint8),
        )
        kernel_size = self.config.morphology_kernel_size
        if kernel_size > 1:
            kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.config.min_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            bbox = BoundingBox(x, y, width, height)
            rectangular_fill = min(1.0, area / (width * height))
            detections.append(
                Detection(
                    label=self.config.label,
                    bbox=bbox,
                    confidence=rectangular_fill,
                    detector_type=self.detector_type,
                )
            )

        detections.sort(key=lambda item: (item.bbox.y, item.bbox.x, item.label))
        return detections

    @staticmethod
    def _validate_image(image: object) -> None:
        if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Detector input must be a BGR image")
        if image.dtype != np.uint8 or image.size == 0:
            raise ValueError("Detector input must be a non-empty uint8 image")


@dataclass(frozen=True, slots=True)
class VisionResult:
    rectified_image: NDArray[np.uint8]
    detections: tuple[Detection, ...]
    phone_screen: PhoneScreenDetection | None = None


class VisionPipeline:
    """Rectify a camera frame and run one or more deterministic detectors."""

    def __init__(
        self,
        screen_detector: PhoneScreenDetector,
        detectors: Sequence[Detector],
    ) -> None:
        self.screen_detector = screen_detector
        self.detectors = tuple(detectors)

    def process(self, camera_frame: NDArray[np.uint8]) -> VisionResult:
        screen_result = self.screen_detector.process(camera_frame)
        rectified = screen_result.canonical_image
        if rectified is None:
            raise PhoneScreenNotFoundError(
                screen_result.detection.failure_reason or "no_phone_candidate"
            )
        detections = [
            detection
            for detector in self.detectors
            for detection in detector.detect(rectified)
        ]
        detections.sort(
            key=lambda item: (
                item.bbox.y,
                item.bbox.x,
                item.detector_type,
                item.label,
            )
        )
        return VisionResult(rectified, tuple(detections), screen_result.detection)


def draw_debug_overlay(
    image: NDArray[np.uint8],
    detections: Sequence[Detection],
    *,
    copy: bool = True,
) -> NDArray[np.uint8]:
    """Draw bounding boxes, labels, confidence, and centers on a BGR image."""

    ColorButtonDetector._validate_image(image)
    output = image.copy() if copy else image
    for detection in detections:
        bbox = detection.bbox
        center = detection.center
        end = (bbox.x + bbox.width - 1, bbox.y + bbox.height - 1)
        cv2.rectangle(output, (bbox.x, bbox.y), end, (0, 255, 255), 2)
        cv2.circle(output, (round(center.x), round(center.y)), 4, (0, 0, 255), -1)
        text = f"{detection.label} {detection.confidence:.2f}"
        text_y = max(14, bbox.y - 5)
        cv2.putText(
            output,
            text,
            (bbox.x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return output


def save_debug_overlay(
    path: str | PathLike[str],
    image: NDArray[np.uint8],
    detections: Sequence[Detection],
) -> Path:
    """Render and save a debug overlay, raising if OpenCV cannot write it."""

    destination = Path(path)
    overlay = draw_debug_overlay(image, detections)
    try:
        written = cv2.imwrite(str(destination), overlay)
    except (cv2.error, OSError) as error:
        raise OSError(f"Could not save debug overlay to {destination}") from error
    if not written:
        raise OSError(f"Could not save debug overlay to {destination}")
    return destination
