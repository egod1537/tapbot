"""Android Accessibility UI tree providers and deterministic selectors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from threading import RLock
from time import monotonic

from tapbot.android.client import AndroidAgentClient, AndroidUiNode, AndroidUiTree
from tapbot.ui_resolution.models import (
    AmbiguousUiElementError,
    ResolvedUiElement,
    StructuredStateClassification,
    UiResolutionResult,
    UiSelector,
)
from tapbot.vision.detector import BoundingBox


class AndroidAccessibilityUiTreeProvider:
    """Fetch and briefly cache one device's UI tree independently."""

    def __init__(self, client: AndroidAgentClient) -> None:
        self.client = client
        self._latest: AndroidUiTree | None = None
        self._fetched_at = 0.0
        self._lock = RLock()

    def snapshot(self, *, max_age_ms: float = 0) -> AndroidUiTree:
        if max_age_ms < 0:
            raise ValueError("max_age_ms must not be negative")
        now = monotonic()
        with self._lock:
            if (
                self._latest is not None
                and max_age_ms > 0
                and (now - self._fetched_at) * 1_000 <= max_age_ms
            ):
                return self._latest
            snapshot = self.client.ui_tree()
            self._latest = snapshot
            self._fetched_at = monotonic()
            return snapshot

    @property
    def latest(self) -> AndroidUiTree | None:
        with self._lock:
            return self._latest

    def invalidate(self) -> None:
        with self._lock:
            self._latest = None
            self._fetched_at = 0.0


class MockUiTreeProvider:
    def __init__(self, snapshots: Iterable[AndroidUiTree]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self, *, max_age_ms: float = 0) -> AndroidUiTree:
        del max_age_ms
        self.calls += 1
        if not self._snapshots:
            raise RuntimeError("No mock UI tree snapshot is available")
        if len(self._snapshots) == 1:
            return self._snapshots[0]
        return self._snapshots.pop(0)

    def invalidate(self) -> None:
        return None


class AccessibilityUiResolver:
    def resolve(
        self,
        tree: AndroidUiTree,
        selector: UiSelector,
        *,
        nearest_clickable_ancestor: bool = True,
        expected_region: BoundingBox | None = None,
    ) -> UiResolutionResult:
        by_id = {node.node_id: node for node in tree.nodes}
        resolved: dict[str, ResolvedUiElement] = {}
        for node in tree.nodes:
            if not self._matches(node, selector):
                continue
            target = self._click_target(
                node,
                selector,
                by_id,
                nearest_clickable_ancestor=nearest_clickable_ancestor,
            )
            if target is None or not self._usable_bounds(target, tree):
                continue
            resolved[target.node_id] = self._element(node, target, selector)

        candidates = tuple(resolved.values())
        if expected_region is not None and len(candidates) > 1:
            regional = tuple(
                candidate
                for candidate in candidates
                if _center_inside(candidate.bbox, expected_region)
            )
            if regional:
                candidates = regional
        if not candidates:
            return UiResolutionResult(
                "not_found",
                reason="No usable accessibility node matched the selector",
            )
        if len(candidates) > 1:
            return UiResolutionResult(
                "ambiguous",
                candidates=candidates,
                reason=f"UI selector matched {len(candidates)} usable elements",
            )
        return UiResolutionResult(
            "resolved",
            element=candidates[0],
            candidates=candidates,
        )

    def find(
        self,
        tree: AndroidUiTree,
        selector: UiSelector | None = None,
        *,
        text: str | None = None,
        text_contains: str | None = None,
        content_description: str | None = None,
        view_id: str | None = None,
        class_name: str | None = None,
        clickable: bool | None = None,
        enabled: bool | None = True,
        visible: bool | None = True,
        nearest_clickable_ancestor: bool = True,
    ) -> ResolvedUiElement | None:
        query = selector or UiSelector(
            text=text,
            text_contains=text_contains,
            content_description=content_description,
            view_id=view_id,
            class_name=class_name,
            clickable=clickable,
            enabled=enabled,
            visible_to_user=visible,
        )
        result = self.resolve(
            tree,
            query,
            nearest_clickable_ancestor=nearest_clickable_ancestor,
        )
        if result.status == "ambiguous":
            raise AmbiguousUiElementError(result)
        return result.element

    @staticmethod
    def _matches(node: AndroidUiNode, selector: UiSelector) -> bool:
        return (
            (selector.text is None or node.text == selector.text)
            and (
                selector.text_contains is None
                or selector.text_contains in (node.text or "")
            )
            and (
                selector.content_description is None
                or node.content_description == selector.content_description
            )
            and (
                selector.view_id is None
                or node.view_id_resource_name == selector.view_id
            )
            and (
                selector.class_name is None
                or node.class_name == selector.class_name
            )
            and (selector.enabled is None or node.enabled is selector.enabled)
            and (
                selector.visible_to_user is None
                or node.visible_to_user is selector.visible_to_user
            )
        )

    @staticmethod
    def _click_target(
        node: AndroidUiNode,
        selector: UiSelector,
        by_id: dict[str, AndroidUiNode],
        *,
        nearest_clickable_ancestor: bool,
    ) -> AndroidUiNode | None:
        if selector.clickable is False:
            return node if not node.clickable else None
        if selector.clickable is not True or node.clickable:
            return node
        if not nearest_clickable_ancestor:
            return None
        parent_id = node.parent_id
        while parent_id is not None:
            parent = by_id.get(parent_id)
            if parent is None:
                return None
            if parent.clickable and parent.enabled and parent.visible_to_user:
                return parent
            parent_id = parent.parent_id
        return None

    @staticmethod
    def _usable_bounds(node: AndroidUiNode, tree: AndroidUiTree) -> bool:
        bounds = node.bounds
        return (
            bounds.area > 0
            and bounds.left >= 0
            and bounds.top >= 0
            and bounds.right <= tree.screen_width
            and bounds.bottom <= tree.screen_height
        )

    @staticmethod
    def _element(
        matched: AndroidUiNode,
        target: AndroidUiNode,
        selector: UiSelector,
    ) -> ResolvedUiElement:
        bounds = target.bounds
        exact = any(
            value is not None
            for value in (
                selector.view_id,
                selector.content_description,
                selector.text,
            )
        )
        label = (
            matched.text
            or matched.content_description
            or matched.view_id_resource_name
            or matched.class_name
            or matched.node_id
        )
        return ResolvedUiElement(
            label=label,
            source="accessibility_tree",
            confidence=1.0 if exact else 0.9 if selector.text_contains else 0.75,
            bbox=BoundingBox(
                bounds.left,
                bounds.top,
                bounds.width,
                bounds.height,
            ),
            text=matched.text,
            content_description=matched.content_description,
            view_id=matched.view_id_resource_name,
            class_name=matched.class_name,
            metadata={
                "node_id": target.node_id,
                "matched_node_id": matched.node_id,
                "parent_id": target.parent_id,
                "depth": target.depth,
                "clickable_ancestor": target.node_id != matched.node_id,
            },
        )


@dataclass(frozen=True, slots=True)
class AccessibilityStateRule:
    state: str
    selectors: tuple[UiSelector, ...]
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.state or not self.selectors:
            raise ValueError("Accessibility state rules require state and selectors")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


class AccessibilityStateClassifier:
    def __init__(
        self,
        rules: Iterable[AccessibilityStateRule],
        *,
        resolver: AccessibilityUiResolver | None = None,
    ) -> None:
        self.rules = tuple(rules)
        self.resolver = resolver or AccessibilityUiResolver()

    def classify(self, tree: AndroidUiTree) -> StructuredStateClassification | None:
        candidates: list[tuple[int, int, AccessibilityStateRule]] = []
        for index, rule in enumerate(self.rules):
            if all(
                self.resolver.resolve(tree, selector).status == "resolved"
                for selector in rule.selectors
            ):
                candidates.append((len(rule.selectors), -index, rule))
        if not candidates:
            return None
        _, _, selected = max(candidates, key=lambda item: item[:2])
        return StructuredStateClassification(
            selected.state,
            selected.confidence,
            tuple(
                _selector_evidence(selector) for selector in selected.selectors
            ),
        )


def _center_inside(candidate: BoundingBox, region: BoundingBox) -> bool:
    center = candidate.center
    return (
        region.x <= center.x <= region.x + region.width
        and region.y <= center.y <= region.y + region.height
    )


def _selector_evidence(selector: UiSelector) -> str:
    for name in ("view_id", "content_description", "text", "text_contains", "class_name"):
        value = getattr(selector, name)
        if value is not None:
            return f"accessibility:{name}={value}"
    return "accessibility"
