"""Vision-derived state classification and declarative state-machine policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from tapbot.macro.actions import MacroAction, RequestHumanAction, ScreenshotAction
from tapbot.screen.source import ScreenFrame
from tapbot.vision.detector import Detection


@dataclass(frozen=True, slots=True)
class StateClassification:
    state: str
    confidence: float
    evidence: tuple[str, ...] = ()


class StateClassifier(Protocol):
    def classify(
        self,
        frame: ScreenFrame,
        detections: Sequence[Detection],
    ) -> StateClassification: ...


@dataclass(frozen=True, slots=True)
class DetectionStateRule:
    state: str
    required_labels: frozenset[str]
    minimum_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.state or not self.required_labels:
            raise ValueError("State rules require a state and at least one label")
        if not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")


class DetectionStateClassifier:
    """Classify screens from trusted detector labels, without issuing actions."""

    def __init__(
        self,
        rules: Sequence[DetectionStateRule],
        *,
        unknown_state: str = "unknown",
    ) -> None:
        if not unknown_state:
            raise ValueError("unknown_state must not be empty")
        self.rules = tuple(rules)
        self.unknown_state = unknown_state

    def classify(
        self,
        frame: ScreenFrame,
        detections: Sequence[Detection],
    ) -> StateClassification:
        del frame
        label_confidence: dict[str, float] = {}
        for detection in detections:
            label_confidence[detection.label] = max(
                label_confidence.get(detection.label, 0.0),
                detection.confidence,
            )
        candidates: list[tuple[float, int, int, DetectionStateRule]] = []
        for index, rule in enumerate(self.rules):
            confidences = [
                label_confidence.get(label, 0.0) for label in rule.required_labels
            ]
            if all(value >= rule.minimum_confidence for value in confidences):
                candidates.append(
                    (min(confidences), len(rule.required_labels), -index, rule)
                )
        if not candidates:
            return StateClassification(self.unknown_state, 0.0)
        confidence, _, _, selected = max(candidates, key=lambda item: item[:3])
        return StateClassification(
            selected.state,
            confidence,
            tuple(sorted(selected.required_labels)),
        )


class MacroStateMachine:
    """Map classified state names to constrained primitive-level intentions."""

    def __init__(
        self,
        actions: Mapping[str, MacroAction],
        *,
        terminal_states: Sequence[str] = (),
    ) -> None:
        self._actions = dict(actions)
        self._terminal_states = frozenset(terminal_states)

    def decide(self, classification: StateClassification) -> MacroAction:
        if classification.state in self._terminal_states:
            return ScreenshotAction()
        return self._actions.get(
            classification.state,
            RequestHumanAction(
                f"No macro transition is configured for state {classification.state!r}"
            ),
        )
