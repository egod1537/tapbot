"""Hardware-free replay of saved screenshots through the decision layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import PathLike

import cv2

from tapbot.model.pipeline import DecisionEngine, DecisionResult
from tapbot.vision.detector import Detection


class ReplayRunner:
    """Re-run model decisions from disk without executing any Action."""

    def __init__(self, engine: DecisionEngine) -> None:
        self.engine = engine

    def run(
        self,
        screenshot: str | PathLike[str],
        context: Mapping[str, object] | None = None,
        detections: Sequence[Detection] = (),
    ) -> DecisionResult:
        image = cv2.imread(str(screenshot), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Could not read replay screenshot: {screenshot}")
        replay_context = dict(context or {})
        replay_context["replay_screenshot"] = str(screenshot)
        return self.engine.decide(image, replay_context, detections)
