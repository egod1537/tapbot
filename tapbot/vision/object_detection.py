"""Object detection abstractions and the pretrained YOLO phone adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
import math
import os
from threading import Lock
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


DEFAULT_YOLO_PHONE_MODEL = "yolo11n.pt"
DEFAULT_PHONE_LABELS = ("cell phone", "mobile phone", "phone")


class ObjectDetectionError(RuntimeError):
    """Raised when an object detector cannot load or run."""


@dataclass(frozen=True, slots=True)
class ObjectBoundingBox:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("object bounding box values must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("object bounding box dimensions must be positive")

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class ObjectDetection:
    label: str
    confidence: float
    bbox: ObjectBoundingBox
    class_id: int
    source: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("object confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict(),
            "class_id": self.class_id,
            "source": self.source,
        }


class ObjectDetector(Protocol):
    @property
    def name(self) -> str: ...

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[ObjectDetection]: ...


@dataclass(frozen=True, slots=True)
class YoloPhoneDetectorConfig:
    model: str = DEFAULT_YOLO_PHONE_MODEL
    device: str | None = None
    confidence_threshold: float = 0.5
    max_detections: int = 5
    phone_class_labels: tuple[str, ...] = DEFAULT_PHONE_LABELS
    image_size: int | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("YOLO model name/path must not be empty")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("YOLO confidence must be between 0 and 1")
        if self.max_detections < 1:
            raise ValueError("YOLO max_detections must be positive")
        if not self.phone_class_labels:
            raise ValueError("At least one phone class label is required")
        if self.image_size is not None and self.image_size < 32:
            raise ValueError("YOLO image_size must be at least 32")

    @classmethod
    def from_environment(cls) -> "YoloPhoneDetectorConfig":
        image_size_value = os.getenv("TAPBOT_PHONE_IMAGE_SIZE")
        labels = tuple(
            label.strip().lower()
            for label in os.getenv(
                "TAPBOT_PHONE_CLASS_LABELS",
                ",".join(DEFAULT_PHONE_LABELS),
            ).split(",")
            if label.strip()
        )
        return cls(
            model=os.getenv("TAPBOT_PHONE_MODEL", DEFAULT_YOLO_PHONE_MODEL),
            device=os.getenv("TAPBOT_PHONE_DEVICE") or None,
            confidence_threshold=float(
                os.getenv("TAPBOT_PHONE_CONFIDENCE", "0.5")
            ),
            max_detections=int(os.getenv("TAPBOT_PHONE_MAX_DETECTIONS", "5")),
            phone_class_labels=labels,
            image_size=(int(image_size_value) if image_size_value else None),
        )


class YoloPhoneDetector:
    """Lazy Ultralytics COCO detector restricted to phone classes."""

    def __init__(self, config: YoloPhoneDetectorConfig | None = None) -> None:
        self.config = config or YoloPhoneDetectorConfig.from_environment()
        self._model: object | None = None
        self._phone_class_ids: tuple[int, ...] = ()
        self._lock = Lock()

    @property
    def name(self) -> str:
        return f"ultralytics:{self.config.model}"

    def detect(
        self,
        frame: NDArray[np.uint8],
    ) -> tuple[ObjectDetection, ...]:
        with self._lock:
            model = self._load_model()
            arguments: dict[str, object] = {
                "source": frame,
                "classes": list(self._phone_class_ids),
                "conf": self.config.confidence_threshold,
                "max_det": self.config.max_detections,
                "verbose": False,
                "device": self.config.device,
            }
            if self.config.image_size is not None:
                arguments["imgsz"] = self.config.image_size
            try:
                results = model.predict(**arguments)
            except Exception as error:
                raise ObjectDetectionError(
                    f"YOLO phone inference failed: {error}"
                ) from error

        if not results:
            return ()
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return ()
        coordinates = boxes.xyxy.detach().cpu().tolist()
        confidences = boxes.conf.detach().cpu().tolist()
        class_ids = boxes.cls.detach().cpu().tolist()
        names = result.names
        allowed_labels = {
            label.strip().lower() for label in self.config.phone_class_labels
        }
        detections: list[ObjectDetection] = []
        for xyxy, confidence, class_id in zip(
            coordinates,
            confidences,
            class_ids,
        ):
            numeric_class_id = int(class_id)
            label = (
                str(names.get(numeric_class_id, numeric_class_id))
                if isinstance(names, dict)
                else str(names[numeric_class_id])
            )
            if label.strip().lower() not in allowed_labels:
                continue
            x1, y1, x2, y2 = (float(value) for value in xyxy)
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append(
                ObjectDetection(
                    label=label,
                    confidence=float(confidence),
                    bbox=ObjectBoundingBox(x1, y1, x2 - x1, y2 - y1),
                    class_id=numeric_class_id,
                    source=self.name,
                )
            )
        detections.sort(
            key=lambda detection: (
                detection.confidence,
                detection.bbox.area,
            ),
            reverse=True,
        )
        return tuple(detections[: self.config.max_detections])

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise ObjectDetectionError(
                "Ultralytics is not installed. Run `npm run setup` once."
            ) from error
        try:
            model = YOLO(self.config.model)
        except Exception as error:
            raise ObjectDetectionError(
                f"Could not load YOLO model {self.config.model!r}: {error}"
            ) from error
        names = getattr(model, "names", {})
        items = names.items() if isinstance(names, dict) else enumerate(names)
        allowed_labels = {
            label.strip().lower() for label in self.config.phone_class_labels
        }
        class_ids = tuple(
            int(class_id)
            for class_id, label in items
            if str(label).strip().lower() in allowed_labels
        )
        if not class_ids:
            raise ObjectDetectionError(
                f"Model {self.config.model!r} has no configured phone class"
            )
        self._model = model
        self._phone_class_ids = class_ids
        return model


def phone_detector_backend() -> str:
    backend = os.getenv("TAPBOT_PHONE_DETECTOR_BACKEND", "yolo").strip().lower()
    if backend not in {"yolo", "contour"}:
        raise ValueError("TAPBOT_PHONE_DETECTOR_BACKEND must be yolo or contour")
    return backend


def bbox_fallback_enabled() -> bool:
    value = os.getenv("TAPBOT_PHONE_BBOX_FALLBACK", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("TAPBOT_PHONE_BBOX_FALLBACK must be true or false")


@lru_cache(maxsize=1)
def default_phone_object_detector() -> ObjectDetector | None:
    if phone_detector_backend() == "contour":
        return None
    return YoloPhoneDetector()
