import pytest

from tapbot.android.client import AndroidUiBounds, AndroidUiNode, AndroidUiTree
from tapbot.model.resolver import TargetResolver
from tapbot.ui_resolution import (
    AccessibilityUiResolver,
    AmbiguousUiElementError,
    AndroidAccessibilityUiTreeProvider,
    HybridTargetResolver,
    UiSelector,
)
from tapbot.vision.detector import BoundingBox, Detection


def node(
    node_id: str,
    *,
    parent_id: str | None = None,
    depth: int = 0,
    text: str | None = None,
    content_description: str | None = None,
    view_id: str | None = None,
    clickable: bool = False,
    enabled: bool = True,
    visible: bool = True,
    bounds: AndroidUiBounds = AndroidUiBounds(10, 10, 110, 60),
) -> AndroidUiNode:
    return AndroidUiNode(
        node_id=node_id,
        parent_id=parent_id,
        depth=depth,
        class_name="android.widget.Button" if clickable else "android.widget.TextView",
        text=text,
        content_description=content_description,
        view_id_resource_name=view_id,
        package_name="com.example",
        bounds=bounds,
        clickable=clickable,
        enabled=enabled,
        focusable=False,
        focused=False,
        selected=False,
        checked=False,
        checkable=False,
        scrollable=False,
        editable=False,
        visible_to_user=visible,
        password=False,
        child_count=0,
    )


def tree(*nodes: AndroidUiNode, request_id: str = "tree-1") -> AndroidUiTree:
    root = nodes[0]
    return AndroidUiTree(
        request_id=request_id,
        captured_at="2026-09-25T00:00:00Z",
        package_name="com.example",
        window_title=None,
        rotation=0,
        screen_width=1080,
        screen_height=2400,
        root=root,
        nodes=nodes,
        truncated=False,
    )


def test_exact_text_and_view_id_resolution() -> None:
    root = node("n0", bounds=AndroidUiBounds(0, 0, 1080, 2400))
    button = node(
        "n0.0",
        parent_id="n0",
        depth=1,
        text="사진 인증",
        view_id="com.example:id/verifyButton",
        clickable=True,
    )
    snapshot = tree(root, button)
    resolver = AccessibilityUiResolver()

    by_text = resolver.find(snapshot, text="사진 인증", clickable=True)
    by_id = resolver.find(
        snapshot,
        view_id="com.example:id/verifyButton",
        clickable=True,
    )

    assert by_text is not None and by_text.source == "accessibility_tree"
    assert by_id is not None and by_id.metadata["node_id"] == "n0.0"


def test_nearest_clickable_parent_supplies_action_bounds() -> None:
    parent = node(
        "n0",
        clickable=True,
        bounds=AndroidUiBounds(200, 1600, 880, 1840),
    )
    label = node(
        "n0.0",
        parent_id="n0",
        depth=1,
        text="사진 인증",
        bounds=AndroidUiBounds(300, 1680, 760, 1780),
    )

    result = AccessibilityUiResolver().find(
        tree(parent, label),
        text="사진 인증",
        clickable=True,
    )

    assert result is not None
    assert result.bbox == BoundingBox(200, 1600, 680, 240)
    assert result.metadata["clickable_ancestor"] is True


def test_duplicate_candidates_are_ambiguous_and_hidden_disabled_are_filtered() -> None:
    root = node("n0", bounds=AndroidUiBounds(0, 0, 1080, 2400))
    first = node("n0.0", parent_id="n0", text="확인", clickable=True)
    second = node(
        "n0.1",
        parent_id="n0",
        text="확인",
        clickable=True,
        bounds=AndroidUiBounds(200, 10, 300, 60),
    )
    hidden = node(
        "n0.2",
        parent_id="n0",
        text="숨김",
        clickable=True,
        visible=False,
    )
    disabled = node(
        "n0.3",
        parent_id="n0",
        text="비활성",
        clickable=True,
        enabled=False,
    )
    resolver = AccessibilityUiResolver()
    snapshot = tree(root, first, second, hidden, disabled)

    ambiguous = resolver.resolve(snapshot, UiSelector(text="확인", clickable=True))
    assert ambiguous.status == "ambiguous"
    with pytest.raises(AmbiguousUiElementError):
        resolver.find(snapshot, text="확인", clickable=True)
    assert resolver.find(snapshot, text="숨김", clickable=True) is None
    assert resolver.find(snapshot, text="비활성", clickable=True) is None


def test_hybrid_resolver_prefers_accessibility_then_falls_back_to_vision() -> None:
    root = node("n0", bounds=AndroidUiBounds(0, 0, 1080, 2400))
    button = node(
        "n0.0",
        parent_id="n0",
        text="사진 인증",
        clickable=True,
        bounds=AndroidUiBounds(220, 1680, 860, 1820),
    )
    detection = Detection(
        "verify_photo_button",
        BoundingBox(10, 10, 100, 50),
        0.9,
        "test",
    )
    hybrid = HybridTargetResolver(
        TargetResolver(minimum_detection_confidence=0.5),
        {
            "verify_photo_button": (
                UiSelector(text="사진 인증", clickable=True),
            )
        },
    )

    accessibility = hybrid.resolve(
        "verify_photo_button",
        [detection],
        screen_width=1080,
        screen_height=2400,
        ui_tree=tree(root, button),
    )
    fallback = hybrid.resolve(
        "verify_photo_button",
        [detection],
        screen_width=1080,
        screen_height=2400,
        ui_tree=tree(root),
    )

    assert accessibility is not None
    assert accessibility.source == "accessibility_tree"
    assert accessibility.center.x == 540
    assert accessibility.center.y == 1750
    assert fallback is not None and fallback.source == "detection"


def test_provider_refreshes_stale_tree_and_isolates_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = node("n0", bounds=AndroidUiBounds(0, 0, 1080, 2400))

    class Client:
        def __init__(self, prefix: str) -> None:
            self.prefix = prefix
            self.calls = 0

        def ui_tree(self) -> AndroidUiTree:
            self.calls += 1
            return tree(root, request_id=f"{self.prefix}-{self.calls}")

    times = iter((0.0, 0.1, 0.2, 1.0, 1.1, 1.2, 1.3))
    monkeypatch.setattr(
        "tapbot.ui_resolution.accessibility.monotonic",
        lambda: next(times),
    )
    client_a = Client("a")
    client_b = Client("b")
    provider_a = AndroidAccessibilityUiTreeProvider(client_a)  # type: ignore[arg-type]
    provider_b = AndroidAccessibilityUiTreeProvider(client_b)  # type: ignore[arg-type]

    assert provider_a.snapshot(max_age_ms=500).request_id == "a-1"
    assert provider_a.snapshot(max_age_ms=500).request_id == "a-1"
    assert provider_a.snapshot(max_age_ms=500).request_id == "a-2"
    assert provider_b.snapshot().request_id == "b-1"
    assert client_a.calls == 2
    assert client_b.calls == 1
