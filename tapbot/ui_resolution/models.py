"""Shared models for structured UI sources and resolution results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from tapbot.android.client import AndroidUiTree
from tapbot.vision.detector import BoundingBox


@dataclass(frozen=True, slots=True)
class UiSelector:
    text: str | None = None
    text_contains: str | None = None
    content_description: str | None = None
    view_id: str | None = None
    class_name: str | None = None
    clickable: bool | None = None
    enabled: bool | None = True
    visible_to_user: bool | None = True

    def __post_init__(self) -> None:
        if not any(
            value is not None
            for value in (
                self.text,
                self.text_contains,
                self.content_description,
                self.view_id,
                self.class_name,
            )
        ):
            raise ValueError("UiSelector requires at least one identifying field")


@dataclass(frozen=True, slots=True)
class ResolvedUiElement:
    label: str
    source: str
    confidence: float
    bbox: BoundingBox
    text: str | None
    content_description: str | None
    view_id: str | None
    class_name: str | None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StructuredStateClassification:
    state: str
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UiResolutionResult:
    status: Literal["resolved", "not_found", "ambiguous"]
    element: ResolvedUiElement | None = None
    candidates: tuple[ResolvedUiElement, ...] = ()
    reason: str | None = None


class AmbiguousUiElementError(LookupError):
    def __init__(self, result: UiResolutionResult) -> None:
        super().__init__(result.reason or "UI selector matched multiple elements")
        self.result = result


class UiTreeProvider(Protocol):
    def snapshot(self, *, max_age_ms: float = 0) -> AndroidUiTree: ...
