"""Unified camera-frame to canonical UI-detection pipeline."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from tapbot.vision.calibration import Point2D
from tapbot.vision.detector import Detection, Detector
from tapbot.vision.screen import (
    PhoneScreenDetection,
    PhoneScreenDetector,
    PhoneScreenResult,
    ScreenBoundingBox,
)


ScreenEventRecorder = Callable[[str, Mapping[str, object]], None]


@dataclass(frozen=True, slots=True)
class ScreenPipelineTimings:
    phone_detection_ms: float
    canonical_transform_ms: float
    ui_detection_ms: float
    total_ms: float
    object_detection_ms: float = 0.0
    screen_refinement_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "phone_detection_ms": self.phone_detection_ms,
            "canonical_transform_ms": self.canonical_transform_ms,
            "ui_detection_ms": self.ui_detection_ms,
            "total_ms": self.total_ms,
            "object_detection_ms": self.object_detection_ms,
            "screen_refinement_ms": self.screen_refinement_ms,
        }


@dataclass(frozen=True, slots=True)
class ScreenPipelineResult:
    frame_id: int
    phone_detection: PhoneScreenDetection
    canonical_image: NDArray[np.uint8] | None
    canonical_width: int | None
    canonical_height: int | None
    detections: tuple[Detection, ...]
    timings: ScreenPipelineTimings
    already_canonical: bool
    failure_stage: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure_stage is None


class ScreenPipeline:
    """Run phone localization, rectification, and UI detection once per frame."""

    def __init__(
        self,
        phone_detector: PhoneScreenDetector,
        ui_detectors: Sequence[Detector],
        *,
        already_canonical: bool = False,
        event_recorder: ScreenEventRecorder | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self.phone_detector = phone_detector
        self.ui_detectors = tuple(ui_detectors)
        self.already_canonical = already_canonical
        self._event_recorder = event_recorder
        self._clock = clock

    def detect_phone(self, frame: NDArray[np.uint8]) -> PhoneScreenDetection:
        if not self.already_canonical:
            return self.phone_detector.detect(frame)
        self.phone_detector._validate_frame(frame)
        height, width = frame.shape[:2]
        corners = (
            Point2D(0, 0),
            Point2D(width - 1, 0),
            Point2D(width - 1, height - 1),
            Point2D(0, height - 1),
        )
        return PhoneScreenDetection(
            found=True,
            confidence=1.0,
            corners=corners,
            bbox=ScreenBoundingBox(0, 0, width, height),
            center=Point2D((width - 1) / 2, (height - 1) / 2),
            source="already_canonical",
            debug_metadata={
                "phone_detection_skipped": True,
                "reason": "camera source supplies canonical screen frames",
            },
        )

    def rectify(
        self,
        frame: NDArray[np.uint8],
        detection: PhoneScreenDetection,
    ) -> PhoneScreenResult:
        if self.already_canonical:
            height, width = frame.shape[:2]
            return PhoneScreenResult(
                detection=detection,
                canonical_image=frame.copy(),
                canonical_width=width,
                canonical_height=height,
                homography=np.eye(3, dtype=np.float64),
            )
        return self.phone_detector.rectify_detection(frame, detection)

    def detect_ui(self, canonical: NDArray[np.uint8]) -> tuple[Detection, ...]:
        detections = [
            detection
            for detector in self.ui_detectors
            for detection in detector.detect(canonical)
        ]
        detections.sort(
            key=lambda item: (
                item.bbox.y,
                item.bbox.x,
                item.detector_type,
                item.label,
            )
        )
        return tuple(detections)

    def run(
        self,
        frame: NDArray[np.uint8],
        *,
        frame_id: int,
    ) -> ScreenPipelineResult:
        total_started = self._clock()
        self._emit(
            "screen.frame",
            {
                "frame_id": frame_id,
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
                "already_canonical": self.already_canonical,
                "status": "success",
            },
        )
        self._emit(
            "screen.phone_detect.start",
            {
                "frame_id": frame_id,
                "skipped": self.already_canonical,
                "status": "pending",
            },
        )

        phone_started = self._clock()
        try:
            phone_detection = self.detect_phone(frame)
        except Exception as error:
            return self._failure(
                frame_id,
                "phone_detection",
                str(error),
                total_started,
                phone_detection=self._missing_detection("phone_detection_error"),
                phone_detection_ms=self._elapsed_ms(phone_started),
            )
        phone_detection_ms = (
            0.0 if self.already_canonical else self._elapsed_ms(phone_started)
        )
        self._emit(
            "screen.phone_detect.result",
            {
                "frame_id": frame_id,
                "found": phone_detection.found,
                "confidence": phone_detection.confidence,
                "source": phone_detection.source,
                "skipped": self.already_canonical,
                "status": "success" if phone_detection.found else "warning",
                "latency_ms": phone_detection_ms,
                "object_detection_ms": self._debug_timing(
                    phone_detection,
                    "object_detection_ms",
                ),
                "screen_refinement_ms": self._debug_timing(
                    phone_detection,
                    "screen_refinement_ms",
                ),
            },
        )
        if not phone_detection.found:
            return self._failure(
                frame_id,
                "phone_detection",
                phone_detection.failure_reason or "no_phone_candidate",
                total_started,
                phone_detection=phone_detection,
                phone_detection_ms=phone_detection_ms,
            )

        transform_started = self._clock()
        try:
            canonical = self.rectify(frame, phone_detection)
        except Exception as error:
            return self._failure(
                frame_id,
                "canonical_transform",
                str(error),
                total_started,
                phone_detection=phone_detection,
                phone_detection_ms=phone_detection_ms,
                canonical_transform_ms=self._elapsed_ms(transform_started),
            )
        canonical_transform_ms = (
            0.0 if self.already_canonical else self._elapsed_ms(transform_started)
        )
        if canonical.canonical_image is None:
            return self._failure(
                frame_id,
                "canonical_transform",
                "canonical image was not created",
                total_started,
                phone_detection=phone_detection,
                phone_detection_ms=phone_detection_ms,
                canonical_transform_ms=canonical_transform_ms,
            )
        self._emit(
            "screen.canonical.ready",
            {
                "frame_id": frame_id,
                "width": canonical.canonical_width,
                "height": canonical.canonical_height,
                "skipped": self.already_canonical,
                "status": "success",
                "latency_ms": canonical_transform_ms,
            },
        )

        ui_started = self._clock()
        try:
            detections = self.detect_ui(canonical.canonical_image)
        except Exception as error:
            return self._failure(
                frame_id,
                "ui_detection",
                str(error),
                total_started,
                phone_detection=phone_detection,
                canonical=canonical,
                phone_detection_ms=phone_detection_ms,
                canonical_transform_ms=canonical_transform_ms,
                ui_detection_ms=self._elapsed_ms(ui_started),
            )
        ui_detection_ms = self._elapsed_ms(ui_started)
        total_ms = self._elapsed_ms(total_started)
        self._emit(
            "screen.ui_detect.result",
            {
                "frame_id": frame_id,
                "detection_count": len(detections),
                "status": "success",
                "latency_ms": ui_detection_ms,
            },
        )
        return ScreenPipelineResult(
            frame_id=frame_id,
            phone_detection=phone_detection,
            canonical_image=canonical.canonical_image,
            canonical_width=canonical.canonical_width,
            canonical_height=canonical.canonical_height,
            detections=detections,
            timings=ScreenPipelineTimings(
                phone_detection_ms,
                canonical_transform_ms,
                ui_detection_ms,
                total_ms,
                self._debug_timing(phone_detection, "object_detection_ms"),
                self._debug_timing(phone_detection, "screen_refinement_ms"),
            ),
            already_canonical=self.already_canonical,
        )

    def _failure(
        self,
        frame_id: int,
        stage: str,
        error: str,
        total_started: float,
        *,
        phone_detection: PhoneScreenDetection,
        canonical: PhoneScreenResult | None = None,
        phone_detection_ms: float = 0.0,
        canonical_transform_ms: float = 0.0,
        ui_detection_ms: float = 0.0,
    ) -> ScreenPipelineResult:
        total_ms = self._elapsed_ms(total_started)
        self._emit(
            "screen.pipeline.error",
            {
                "frame_id": frame_id,
                "stage": stage,
                "error": error,
                "status": "error",
                "latency_ms": total_ms,
            },
        )
        return ScreenPipelineResult(
            frame_id=frame_id,
            phone_detection=phone_detection,
            canonical_image=(None if canonical is None else canonical.canonical_image),
            canonical_width=(None if canonical is None else canonical.canonical_width),
            canonical_height=(None if canonical is None else canonical.canonical_height),
            detections=(),
            timings=ScreenPipelineTimings(
                phone_detection_ms,
                canonical_transform_ms,
                ui_detection_ms,
                total_ms,
                self._debug_timing(phone_detection, "object_detection_ms"),
                self._debug_timing(phone_detection, "screen_refinement_ms"),
            ),
            already_canonical=self.already_canonical,
            failure_stage=stage,
            error=error,
        )

    @staticmethod
    def _missing_detection(reason: str) -> PhoneScreenDetection:
        return PhoneScreenDetection(
            found=False,
            confidence=0.0,
            failure_reason=reason,
            debug_metadata={"candidate_count": 0},
        )

    def _elapsed_ms(self, started: float) -> float:
        return max(0.0, (self._clock() - started) * 1000)

    @staticmethod
    def _debug_timing(detection: PhoneScreenDetection, name: str) -> float:
        value = detection.debug_metadata.get(name, 0.0)
        return float(value) if isinstance(value, int | float) else 0.0

    def _emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        if self._event_recorder is not None:
            self._event_recorder(event_type, payload)
