"""UI vision pipeline for sources that already provide canonical screens."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter

from tapbot.screen.source import ScreenFrame
from tapbot.vision.detector import Detection, Detector


@dataclass(frozen=True, slots=True)
class CanonicalVisionResult:
    frame: ScreenFrame
    detections: tuple[Detection, ...]
    ui_detection_ms: float


class CanonicalVisionPipeline:
    """Run UI detectors directly; no phone bbox, corners, or homography exist."""

    def __init__(self, detectors: Sequence[Detector]) -> None:
        self.detectors = tuple(detectors)

    def run(self, frame: ScreenFrame) -> CanonicalVisionResult:
        started = perf_counter()
        detections = [
            detection
            for detector in self.detectors
            for detection in detector.detect(frame.image)
        ]
        detections.sort(
            key=lambda item: (
                item.bbox.y,
                item.bbox.x,
                item.detector_type,
                item.label,
            )
        )
        return CanonicalVisionResult(
            frame=frame,
            detections=tuple(detections),
            ui_detection_ms=max(0.0, (perf_counter() - started) * 1000),
        )
