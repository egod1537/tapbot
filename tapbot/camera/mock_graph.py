"""Validated image-state graph engine for mock camera flows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from threading import RLock
from typing import TypeAlias

import cv2

from tapbot.camera.source import BGRFrame, validate_bgr_frame


MockEventRecorder: TypeAlias = Callable[[str, Mapping[str, object]], None]
ImageLoader: TypeAlias = Callable[[str, int], object]
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]*$")
TARGET_LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class MockGraphError(RuntimeError):
    """Base class for mock screen graph errors."""


class MockGraphValidationError(MockGraphError):
    """Raised when a graph document or referenced image is invalid."""


class MockGraphStateError(MockGraphError):
    """Raised when a transition targets an unknown state."""


@dataclass(frozen=True, slots=True)
class MockGraphMetadata:
    schema_version: int
    id: str
    name: str
    description: str
    screen_width: int
    screen_height: int


@dataclass(frozen=True, slots=True)
class MockHotspot:
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    next_state: str

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "next_state": self.next_state,
        }


@dataclass(frozen=True, slots=True)
class MockScreenState:
    id: str
    image: Path
    hotspots: tuple[MockHotspot, ...]


@dataclass(frozen=True, slots=True)
class MockTap:
    x: float
    y: float
    state: str
    hit: bool
    hotspot_id: str | None
    timestamp: str

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "state": self.state,
            "hit": self.hit,
            "hotspot_id": self.hotspot_id,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class MockTransition:
    from_state: str
    to_state: str
    trigger: str
    hotspot_id: str | None
    label: str | None
    timestamp: str

    def to_dict(self) -> dict[str, object]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "hotspot_id": self.hotspot_id,
            "label": self.label,
            "timestamp": self.timestamp,
        }


class MockScreenGraph:
    """Navigate image states through coordinate-based hotspots."""

    def __init__(
        self,
        metadata: MockGraphMetadata,
        initial_state: str,
        states: Mapping[str, MockScreenState],
        frames: Mapping[str, BGRFrame],
        *,
        event_recorder: MockEventRecorder | None = None,
    ) -> None:
        if initial_state not in states:
            raise MockGraphValidationError(
                f"initial_state references unknown state: {initial_state}"
            )
        if set(states) != set(frames):
            raise MockGraphValidationError("Every state must have one decoded image")
        self.metadata = metadata
        self.initial_state = initial_state
        self.states = dict(states)
        self._frames = {state_id: frame.copy() for state_id, frame in frames.items()}
        self._current_state = initial_state
        self._last_tap: MockTap | None = None
        self._last_transition: MockTransition | None = None
        self._event_recorder = event_recorder
        self._lock = RLock()

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        event_recorder: MockEventRecorder | None = None,
        image_loader: ImageLoader = cv2.imread,
    ) -> MockScreenGraph:
        graph_path = Path(path)
        try:
            document = json.loads(graph_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise MockGraphValidationError(
                f"Could not read mock graph: {graph_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise MockGraphValidationError(
                f"Mock graph is not valid JSON: {graph_path}"
            ) from error

        metadata, initial_state, states = _parse_document(
            document, graph_path.parent
        )
        frames: dict[str, BGRFrame] = {}
        for state_id, state in states.items():
            raw_frame = image_loader(str(state.image), cv2.IMREAD_COLOR)
            if raw_frame is None:
                raise MockGraphValidationError(
                    f"State {state_id!r} image could not be decoded: {state.image}"
                )
            try:
                frame = validate_bgr_frame(
                    raw_frame, source_id=f"mock-state:{state_id}"
                )
            except Exception as error:
                raise MockGraphValidationError(
                    f"State {state_id!r} image is not a BGR image: {state.image}"
                ) from error
            height, width = frame.shape[:2]
            if width != metadata.screen_width or height != metadata.screen_height:
                raise MockGraphValidationError(
                    f"State {state_id!r} image must be "
                    f"{metadata.screen_width}x{metadata.screen_height}, got "
                    f"{width}x{height}: {state.image}"
                )
            frames[state_id] = frame
        return cls(
            metadata,
            initial_state,
            states,
            frames,
            event_recorder=event_recorder,
        )

    @property
    def current_state(self) -> str:
        with self._lock:
            return self._current_state

    @property
    def current_state_model(self) -> MockScreenState:
        with self._lock:
            return self.states[self._current_state]

    @property
    def available_hotspots(self) -> tuple[MockHotspot, ...]:
        with self._lock:
            return self.states[self._current_state].hotspots

    @property
    def last_tap(self) -> MockTap | None:
        with self._lock:
            return self._last_tap

    @property
    def last_transition(self) -> MockTransition | None:
        with self._lock:
            return self._last_transition

    def read_frame(self) -> BGRFrame:
        with self._lock:
            return self._frames[self._current_state].copy()

    def reset(self) -> MockTransition:
        with self._lock:
            self._last_tap = None
            transition = self._apply_transition_locked(
                self.initial_state,
                trigger="reset",
                hotspot=None,
            )
        self._record_transition(transition)
        return transition

    def transition(self, next_state: str) -> MockTransition:
        with self._lock:
            transition = self._apply_transition_locked(
                next_state,
                trigger="manual",
                hotspot=None,
            )
        self._record_transition(transition)
        return transition

    def tap(self, x: float, y: float) -> MockTransition | None:
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Mock tap coordinates must be finite")
        with self._lock:
            state_id = self._current_state
            hotspot = next(
                (
                    candidate
                    for candidate in self.states[state_id].hotspots
                    if candidate.contains(x, y)
                ),
                None,
            )
            tap = MockTap(
                x=x,
                y=y,
                state=state_id,
                hit=hotspot is not None,
                hotspot_id=None if hotspot is None else hotspot.id,
                timestamp=_timestamp(),
            )
            self._last_tap = tap
            transition = (
                None
                if hotspot is None
                else self._apply_transition_locked(
                    hotspot.next_state,
                    trigger="tap",
                    hotspot=hotspot,
                )
            )
        if hotspot is None:
            self._record_event("mock.miss", tap.to_dict())
            return None
        self._record_event(
            "mock.hit",
            {**tap.to_dict(), "label": hotspot.label, "next_state": hotspot.next_state},
        )
        assert transition is not None
        self._record_transition(transition)
        return transition

    def set_event_recorder(self, recorder: MockEventRecorder | None) -> None:
        with self._lock:
            self._event_recorder = recorder

    def status(self) -> dict[str, object]:
        with self._lock:
            states: list[dict[str, object]] = []
            edges: list[dict[str, object]] = []
            for state_id, state in self.states.items():
                frame_height, frame_width = self._frames[state_id].shape[:2]
                states.append(
                    {
                        "id": state_id,
                        "image": state.image.name,
                        "width": frame_width,
                        "height": frame_height,
                        "hotspots": [
                            hotspot.to_dict() for hotspot in state.hotspots
                        ],
                    }
                )
                edges.extend(
                    {
                        "id": f"{state_id}:{hotspot.id}",
                        "from_state": state_id,
                        "to_state": hotspot.next_state,
                        "hotspot_id": hotspot.id,
                        "label": hotspot.label,
                    }
                    for hotspot in state.hotspots
                )
            return {
                "schema_version": self.metadata.schema_version,
                "id": self.metadata.id,
                "name": self.metadata.name,
                "description": self.metadata.description,
                "screen_width": self.metadata.screen_width,
                "screen_height": self.metadata.screen_height,
                "initial_state": self.initial_state,
                "current_state": self._current_state,
                "previous_state": (
                    None
                    if self._last_transition is None
                    else self._last_transition.from_state
                ),
                "available_hotspots": [
                    hotspot.to_dict()
                    for hotspot in self.states[self._current_state].hotspots
                ],
                "last_tap": (
                    None if self._last_tap is None else self._last_tap.to_dict()
                ),
                "last_transition": (
                    None
                    if self._last_transition is None
                    else self._last_transition.to_dict()
                ),
                "states": states,
                "edges": edges,
            }

    def _apply_transition_locked(
        self,
        next_state: str,
        *,
        trigger: str,
        hotspot: MockHotspot | None,
    ) -> MockTransition:
        if next_state not in self.states:
            raise MockGraphStateError(f"Unknown mock screen state: {next_state}")
        transition = MockTransition(
            from_state=self._current_state,
            to_state=next_state,
            trigger=trigger,
            hotspot_id=None if hotspot is None else hotspot.id,
            label=None if hotspot is None else hotspot.label,
            timestamp=_timestamp(),
        )
        self._current_state = next_state
        self._last_transition = transition
        return transition

    def _record_transition(self, transition: MockTransition) -> None:
        self._record_event("mock.transition", transition.to_dict())

    def _record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        recorder = self._event_recorder
        if recorder is not None:
            recorder(event_type, payload)


def _parse_document(
    document: object, base_path: Path
) -> tuple[MockGraphMetadata, str, dict[str, MockScreenState]]:
    root = _require_mapping(document, "graph")
    schema_version = root.get("schema_version")
    if schema_version != 1:
        raise MockGraphValidationError("schema_version must be 1")
    metadata = MockGraphMetadata(
        schema_version=1,
        id=_require_stable_id(root.get("id"), "id"),
        name=_require_string(root.get("name"), "name"),
        description=_require_string(root.get("description"), "description"),
        screen_width=_require_dimension(root.get("screen_width"), "screen_width"),
        screen_height=_require_dimension(
            root.get("screen_height"), "screen_height"
        ),
    )
    initial_state = _require_stable_id(
        root.get("initial_state"), "initial_state"
    )
    state_documents = _require_mapping(root.get("states"), "states")
    if not state_documents:
        raise MockGraphValidationError("states must not be empty")

    states: dict[str, MockScreenState] = {}
    for state_id, raw_state in state_documents.items():
        _require_stable_id(state_id, f"states.{state_id}.key")
        state = _require_mapping(raw_state, f"states.{state_id}")
        declared_id = state.get("id", state_id)
        if declared_id != state_id:
            raise MockGraphValidationError(
                f"states.{state_id}.id must match its states key"
            )
        image_name = _require_string(state.get("image"), f"states.{state_id}.image")
        relative_image_path = Path(image_name)
        if relative_image_path.is_absolute():
            raise MockGraphValidationError(
                f"states.{state_id}.image must be relative to the scenario directory"
            )
        scenario_path = base_path.resolve()
        image_path = (scenario_path / relative_image_path).resolve()
        try:
            image_path.relative_to(scenario_path)
        except ValueError as error:
            raise MockGraphValidationError(
                f"states.{state_id}.image must stay inside the scenario directory"
            ) from error
        if not image_path.is_file():
            raise MockGraphValidationError(
                f"State {state_id!r} image does not exist: {image_path}"
            )
        raw_hotspots = state.get("hotspots", [])
        if not isinstance(raw_hotspots, list):
            raise MockGraphValidationError(
                f"states.{state_id}.hotspots must be an array"
            )
        hotspots = tuple(
            _parse_hotspot(raw_hotspot, f"states.{state_id}.hotspots[{index}]")
            for index, raw_hotspot in enumerate(raw_hotspots)
        )
        hotspot_ids = [hotspot.id for hotspot in hotspots]
        if len(hotspot_ids) != len(set(hotspot_ids)):
            raise MockGraphValidationError(
                f"states.{state_id}.hotspot IDs must be unique"
            )
        states[state_id] = MockScreenState(
            id=state_id,
            image=image_path,
            hotspots=hotspots,
        )

    if initial_state not in states:
        raise MockGraphValidationError(
            f"initial_state references unknown state: {initial_state}"
        )
    for state in states.values():
        for hotspot in state.hotspots:
            if hotspot.next_state not in states:
                raise MockGraphValidationError(
                    f"Hotspot {state.id}.{hotspot.id} references unknown state: "
                    f"{hotspot.next_state}"
                )
            if (
                hotspot.x < 0
                or hotspot.y < 0
                or hotspot.x + hotspot.width > metadata.screen_width
                or hotspot.y + hotspot.height > metadata.screen_height
            ):
                raise MockGraphValidationError(
                    f"Hotspot {state.id}.{hotspot.id} must fit within "
                    f"{metadata.screen_width}x{metadata.screen_height}"
                )
    return metadata, initial_state, states


def _parse_hotspot(document: object, path: str) -> MockHotspot:
    hotspot = _require_mapping(document, path)
    width = _require_number(hotspot.get("width"), f"{path}.width")
    height = _require_number(hotspot.get("height"), f"{path}.height")
    if width <= 0 or height <= 0:
        raise MockGraphValidationError(f"{path} width and height must be positive")
    return MockHotspot(
        id=_require_stable_id(hotspot.get("id"), f"{path}.id"),
        label=_require_target_label(hotspot.get("label"), f"{path}.label"),
        x=_require_number(hotspot.get("x"), f"{path}.x"),
        y=_require_number(hotspot.get("y"), f"{path}.y"),
        width=width,
        height=height,
        next_state=_require_stable_id(
            hotspot.get("next_state"), f"{path}.next_state"
        ),
    )


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise MockGraphValidationError(f"{path} must be an object")
    return value


def _require_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise MockGraphValidationError(f"{path} must be a non-empty string")
    return value


def _require_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MockGraphValidationError(f"{path} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise MockGraphValidationError(f"{path} must be a finite number")
    return number


def _require_dimension(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MockGraphValidationError(f"{path} must be a positive integer")
    return value


def _require_stable_id(value: object, path: str) -> str:
    text = _require_string(value, path)
    if STABLE_ID_PATTERN.fullmatch(text) is None:
        raise MockGraphValidationError(
            f"{path} must match {STABLE_ID_PATTERN.pattern}"
        )
    return text


def _require_target_label(value: object, path: str) -> str:
    text = _require_string(value, path)
    if TARGET_LABEL_PATTERN.fullmatch(text) is None:
        raise MockGraphValidationError(
            f"{path} must match {TARGET_LABEL_PATTERN.pattern}"
        )
    return text


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
