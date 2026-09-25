"""Serializable replay evidence for PC macro iterations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class MacroStepTrace:
    step: int
    captured_at: str
    source_id: str
    frame_id: str
    screenshot_path: str | None
    state: str
    state_confidence: float
    detections: tuple[dict[str, object], ...]
    decision: dict[str, object]
    action: dict[str, object] | None
    target: dict[str, object] | None
    api_result: dict[str, Any] | None
    status: str
    error: str | None = None
    ui_tree: dict[str, object] | None = None


@dataclass(slots=True)
class MacroTrace:
    device_id: str | None = None
    started_at: str = field(default_factory=lambda: _now())
    completed_at: str | None = None
    steps: list[MacroStepTrace] = field(default_factory=list)

    def append(self, step: MacroStepTrace) -> None:
        self.steps.append(step)

    def finish(self) -> None:
        self.completed_at = _now()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "device_id": self.device_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": [asdict(step) for step in self.steps],
        }

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "MacroTrace":
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("Unsupported macro trace schema")
        raw_steps = document.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("Macro trace steps must be an array")
        steps: list[MacroStepTrace] = []
        for item in raw_steps:
            if not isinstance(item, dict):
                raise ValueError("Macro trace step must be an object")
            values = dict(item)
            detections = values.get("detections", ())
            values["detections"] = tuple(detections)
            steps.append(MacroStepTrace(**values))
        return cls(
            device_id=(
                None
                if document.get("device_id") is None
                else str(document["device_id"])
            ),
            started_at=str(document.get("started_at", "")),
            completed_at=(
                None
                if document.get("completed_at") is None
                else str(document["completed_at"])
            ),
            steps=steps,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
