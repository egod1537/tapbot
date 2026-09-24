import numpy as np
import pytest

from tapbot.vision.object_detection import (
    ObjectDetectionError,
    YoloPhoneDetector,
    YoloPhoneDetectorConfig,
)


class FakeValues:
    def __init__(self, values: object) -> None:
        self.values = values

    def detach(self) -> "FakeValues":
        return self

    def cpu(self) -> "FakeValues":
        return self

    def tolist(self) -> object:
        return self.values


class FakeBoxes:
    xyxy = FakeValues(
        [
            [10, 20, 110, 220],
            [300, 40, 500, 440],
            [0, 0, 50, 50],
        ]
    )
    conf = FakeValues([0.8, 0.8, 0.99])
    cls = FakeValues([67, 67, 0])


class FakeResult:
    boxes = FakeBoxes()
    names = {0: "person", 67: "cell phone"}


class FakeModel:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.arguments: dict[str, object] | None = None

    def predict(self, **arguments: object) -> list[FakeResult]:
        self.arguments = arguments
        if self.error is not None:
            raise self.error
        return [FakeResult()]


def configured_detector(model: FakeModel) -> YoloPhoneDetector:
    detector = YoloPhoneDetector(
        YoloPhoneDetectorConfig(
            model="test-phone.pt",
            confidence_threshold=0.5,
            max_detections=2,
            image_size=640,
        )
    )
    detector._model = model
    detector._phone_class_ids = (67,)
    return detector


def test_yolo_adapter_filters_phone_class_and_sorts_equal_confidence_by_area() -> None:
    model = FakeModel()
    detector = configured_detector(model)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    detections = detector.detect(frame)

    assert [detection.label for detection in detections] == [
        "cell phone",
        "cell phone",
    ]
    assert detections[0].bbox.area > detections[1].bbox.area
    assert detections[0].class_id == 67
    assert detections[0].source == "ultralytics:test-phone.pt"
    assert model.arguments is not None
    assert model.arguments["source"] is frame
    assert model.arguments["classes"] == [67]
    assert model.arguments["conf"] == 0.5
    assert model.arguments["max_det"] == 2
    assert model.arguments["imgsz"] == 640


def test_yolo_adapter_reports_inference_failure() -> None:
    detector = configured_detector(FakeModel(error=RuntimeError("GPU failed")))

    with pytest.raises(ObjectDetectionError, match="GPU failed"):
        detector.detect(np.zeros((20, 20, 3), dtype=np.uint8))
