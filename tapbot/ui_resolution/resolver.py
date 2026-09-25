"""Accessibility-first target resolution with deterministic Vision fallback."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tapbot.android.client import AndroidUiTree
from tapbot.model.resolver import ResolvedTarget, TargetResolver
from tapbot.ui_resolution.accessibility import AccessibilityUiResolver
from tapbot.ui_resolution.models import UiSelector
from tapbot.vision.detector import Detection


class HybridTargetResolver:
    def __init__(
        self,
        vision_resolver: TargetResolver,
        selectors: Mapping[str, Sequence[UiSelector]] | None = None,
        *,
        accessibility_resolver: AccessibilityUiResolver | None = None,
    ) -> None:
        self.vision_resolver = vision_resolver
        self.selectors = {
            target: tuple(target_selectors)
            for target, target_selectors in (selectors or {}).items()
        }
        self.accessibility_resolver = (
            accessibility_resolver or AccessibilityUiResolver()
        )

    def resolve(
        self,
        target_name: str,
        detections: Sequence[Detection],
        *,
        screen_width: int,
        screen_height: int,
        ui_tree: AndroidUiTree | None = None,
    ) -> ResolvedTarget | None:
        if (
            ui_tree is not None
            and ui_tree.screen_width == screen_width
            and ui_tree.screen_height == screen_height
        ):
            for selector in self.selectors.get(
                target_name,
                _literal_target_selectors(target_name),
            ):
                result = self.accessibility_resolver.resolve(ui_tree, selector)
                if result.status == "resolved" and result.element is not None:
                    element = result.element
                    return ResolvedTarget(
                        name=target_name,
                        center=element.bbox.center,
                        source=element.source,
                        bbox=element.bbox,
                        metadata={
                            "text": element.text,
                            "content_description": element.content_description,
                            "view_id": element.view_id,
                            **element.metadata,
                        },
                    )
                if result.status == "ambiguous":
                    break
        return self.vision_resolver.resolve(
            target_name,
            detections,
            screen_width=screen_width,
            screen_height=screen_height,
        )


def _literal_target_selectors(target_name: str) -> tuple[UiSelector, ...]:
    return (
        UiSelector(view_id=target_name, clickable=True),
        UiSelector(content_description=target_name, clickable=True),
        UiSelector(text=target_name, clickable=True),
        UiSelector(text_contains=target_name, clickable=True),
    )
