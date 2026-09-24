"""Resolve model target names to trusted screen coordinates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from tapbot.vision.calibration import Point2D
from tapbot.vision.detector import BoundingBox, Detection


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    name: str
    center: Point2D
    source: str
    detection: Detection | None = None


class TargetResolver:
    """Resolve only known Detection labels or predefined trusted ROIs."""

    def __init__(
        self,
        predefined_rois: Mapping[str, BoundingBox] | None = None,
        *,
        minimum_detection_confidence: float = 0,
    ) -> None:
        if (
            not math.isfinite(minimum_detection_confidence)
            or not 0 <= minimum_detection_confidence <= 1
        ):
            raise ValueError("minimum_detection_confidence must be between 0 and 1")
        self._predefined_rois = dict(predefined_rois or {})
        self.minimum_detection_confidence = minimum_detection_confidence

    def resolve(
        self,
        target_name: str,
        detections: Sequence[Detection],
        *,
        screen_width: int,
        screen_height: int,
    ) -> ResolvedTarget | None:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")
        candidates = [
            detection
            for detection in detections
            if detection.label == target_name
            and detection.confidence >= self.minimum_detection_confidence
            and self._bbox_is_inside(
                detection.bbox,
                screen_width=screen_width,
                screen_height=screen_height,
            )
        ]
        if candidates:
            selected = min(
                candidates,
                key=lambda detection: (
                    -detection.confidence,
                    detection.bbox.y,
                    detection.bbox.x,
                ),
            )
            return ResolvedTarget(
                name=target_name,
                center=selected.center,
                source="detection",
                detection=selected,
            )

        roi = self._predefined_rois.get(target_name)
        if roi is not None and self._bbox_is_inside(
            roi,
            screen_width=screen_width,
            screen_height=screen_height,
        ):
            return ResolvedTarget(
                name=target_name,
                center=roi.center,
                source="predefined_roi",
            )
        return None

    @staticmethod
    def _bbox_is_inside(
        bbox: BoundingBox,
        *,
        screen_width: int,
        screen_height: int,
    ) -> bool:
        return (
            bbox.x + bbox.width <= screen_width
            and bbox.y + bbox.height <= screen_height
        )
