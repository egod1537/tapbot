"""Strict JSON schema and parser for local-model decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import math
from typing import Any


class DecisionOutputError(ValueError):
    """Raised when model output does not satisfy the decision schema."""


class DecisionAction(StrEnum):
    NOOP = "noop"
    TAP_TARGET = "tap_target"
    WAIT = "wait"
    REQUEST_HUMAN = "request_human"


DECISION_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "TapBotDecision",
    "type": "object",
    "additionalProperties": False,
    "required": ["state", "action", "target", "confidence", "reason"],
    "properties": {
        "state": {"type": "string", "minLength": 1, "maxLength": 100},
        "action": {
            "type": "string",
            "enum": [action.value for action in DecisionAction],
        },
        "target": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 100},
                {"type": "null"},
            ]
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 1000},
    },
}


@dataclass(frozen=True, slots=True)
class Decision:
    state: str
    action: DecisionAction
    target: str | None
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "action": self.action.value,
            "target": self.target,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class DecisionParser:
    """Parse model JSON without accepting extra executable fields."""

    _FIELDS = frozenset(DECISION_JSON_SCHEMA["required"])

    def parse(self, raw: str | bytes | dict[str, object] | Decision) -> Decision:
        if isinstance(raw, Decision):
            value = raw.to_dict()
        elif isinstance(raw, bytes):
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DecisionOutputError("Model output is not valid UTF-8 JSON") from error
        elif isinstance(raw, str):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise DecisionOutputError("Model output is not valid JSON") from error
        elif isinstance(raw, dict):
            value = raw
        else:
            raise DecisionOutputError("Model output must be a JSON object")

        if not isinstance(value, dict):
            raise DecisionOutputError("Model output must be a JSON object")
        fields = set(value)
        missing = self._FIELDS - fields
        extra = fields - self._FIELDS
        if missing:
            raise DecisionOutputError(
                f"Model output is missing fields: {', '.join(sorted(missing))}"
            )
        if extra:
            raise DecisionOutputError(
                f"Model output contains forbidden fields: {', '.join(sorted(extra))}"
            )

        state = value["state"]
        action_value = value["action"]
        target = value["target"]
        confidence = value["confidence"]
        reason = value["reason"]
        if not isinstance(state, str) or not 1 <= len(state) <= 100:
            raise DecisionOutputError("state must be a string from 1 to 100 characters")
        if not isinstance(action_value, str):
            raise DecisionOutputError("action must be a string")
        try:
            action = DecisionAction(action_value)
        except ValueError as error:
            raise DecisionOutputError(f"Unsupported decision action: {action_value!r}") from error
        if target is not None and (
            not isinstance(target, str) or not 1 <= len(target) <= 100
        ):
            raise DecisionOutputError(
                "target must be null or a string from 1 to 100 characters"
            )
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise DecisionOutputError("confidence must be a number")
        confidence_value = float(confidence)
        if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
            raise DecisionOutputError("confidence must be finite and between 0 and 1")
        if not isinstance(reason, str) or len(reason) > 1000:
            raise DecisionOutputError("reason must be a string up to 1000 characters")
        if action is DecisionAction.TAP_TARGET and target is None:
            raise DecisionOutputError("tap_target requires a target")
        if action is not DecisionAction.TAP_TARGET and target is not None:
            raise DecisionOutputError(
                f"{action.value} must not include a target"
            )

        return Decision(
            state=state,
            action=action,
            target=target,
            confidence=confidence_value,
            reason=reason,
        )
