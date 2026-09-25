"""Structured UI recognition providers and resolvers."""

from tapbot.ui_resolution.accessibility import (
    AccessibilityUiResolver,
    AccessibilityStateClassifier,
    AccessibilityStateRule,
    AndroidAccessibilityUiTreeProvider,
    MockUiTreeProvider,
)
from tapbot.ui_resolution.models import (
    AmbiguousUiElementError,
    ResolvedUiElement,
    StructuredStateClassification,
    UiResolutionResult,
    UiSelector,
    UiTreeProvider,
)
from tapbot.ui_resolution.resolver import HybridTargetResolver

__all__ = [
    "AccessibilityUiResolver",
    "AccessibilityStateClassifier",
    "AccessibilityStateRule",
    "AmbiguousUiElementError",
    "AndroidAccessibilityUiTreeProvider",
    "HybridTargetResolver",
    "MockUiTreeProvider",
    "ResolvedUiElement",
    "StructuredStateClassification",
    "UiResolutionResult",
    "UiSelector",
    "UiTreeProvider",
]
