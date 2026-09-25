from email.message import Message
import json
from urllib.error import URLError

import pytest

from tapbot.android.client import (
    AndroidAgentClient,
    AndroidAgentTransportError,
)
from tapbot.device.gesture import PointerGesture, PointerPoint


class FakeResponse:
    def __init__(self, content: bytes, headers: Message | None = None) -> None:
        self.content = content
        self.headers = headers or Message()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.content


def test_tap_uses_exact_primitive_endpoint_and_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[object, float]] = []

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse(
            json.dumps(
                {
                    "ok": True,
                    "request_id": "request-1",
                    "action_id": "action-1",
                    "command": "tap",
                    "state": "completed",
                    "error": None,
                }
            ).encode()
        )

    monkeypatch.setattr("tapbot.android.client.urlopen", fake_urlopen)
    client = AndroidAgentClient("http://phone:8765/api", "secret")

    result = client.tap(520, 1170, duration_ms=70)

    assert result.action_id == "action-1"
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == "http://phone:8765/api/tap"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"x": 520, "y": 1170, "duration_ms": 70}
    assert request.get_header("Authorization") == "Bearer secret"
    assert timeout == 5.0


def test_transport_failure_is_not_retried_and_marks_tap_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def failing_urlopen(*_: object, **__: object) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise URLError("offline")

    monkeypatch.setattr("tapbot.android.client.urlopen", failing_urlopen)
    client = AndroidAgentClient("http://phone:8765", "secret")

    with pytest.raises(AndroidAgentTransportError) as captured:
        client.tap(1, 2)

    assert calls == 1
    assert captured.value.outcome_unknown is True


def test_gesture_posts_complete_trajectory_with_duration_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[object, float]] = []

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse(
            json.dumps(
                {
                    "ok": True,
                    "request_id": "request-g",
                    "action_id": "action-g",
                    "command": "gesture",
                    "state": "completed",
                }
            ).encode()
        )

    monkeypatch.setattr("tapbot.android.client.urlopen", fake_urlopen)
    gesture = PointerGesture.from_points(
        (
            PointerPoint(500, 1800, 0),
            PointerPoint(510, 1300, 100),
            PointerPoint(500, 600, 260),
        ),
        started_at_ms=123,
    )

    result = AndroidAgentClient(
        "http://phone:8765",
        "secret",
        timeout=1,
    ).gesture(gesture)

    request, timeout = requests[0]
    assert request.full_url == "http://phone:8765/api/gesture"
    assert json.loads(request.data) == {
        "points": [
            {"x": 500, "y": 1800, "t_ms": 0},
            {"x": 510, "y": 1300, "t_ms": 100},
            {"x": 500, "y": 600, "t_ms": 260},
        ]
    }
    assert timeout == 3.26
    assert result.command == "gesture"


def test_screenshot_parses_coordinate_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    headers = Message()
    headers["Content-Type"] = "image/jpeg"
    headers["X-Frame-Id"] = "42"
    headers["X-Screen-Width"] = "1080"
    headers["X-Screen-Height"] = "2400"
    headers["X-Rotation"] = "0"
    headers["X-Captured-At"] = "2026-09-24T00:00:00Z"

    monkeypatch.setattr(
        "tapbot.android.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"jpeg", headers),
    )

    frame = AndroidAgentClient("http://phone:8765", "secret").screenshot()

    assert frame.content == b"jpeg"
    assert (frame.width, frame.height, frame.rotation) == (1080, 2400, 0)
    assert frame.frame_id == 42


def test_stream_status_uses_canonical_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        requests.append(request)
        return FakeResponse(
            json.dumps(
                {
                    "ok": True,
                    "request_id": "stream-1",
                    "running": True,
                    "width": 1080,
                    "height": 2400,
                    "fps": 20.0,
                    "error": None,
                }
            ).encode()
        )

    monkeypatch.setattr("tapbot.android.client.urlopen", fake_urlopen)

    status = AndroidAgentClient("http://phone:8765", "secret").stream_status()

    assert status["fps"] == 20.0
    assert requests[0].full_url == "http://phone:8765/api/stream/status"


def test_ui_tree_parses_nested_and_flat_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    child = _ui_node_payload(
        "n0.0",
        parent_id="n0",
        depth=1,
        text="사진 인증",
        view_id="com.example:id/verifyButton",
        clickable=True,
        bounds={"left": 220, "top": 1680, "right": 860, "bottom": 1820},
    )
    root = _ui_node_payload("n0", children=[child])
    payload = {
        "ok": True,
        "request_id": "tree-1",
        "captured_at": "2026-09-25T00:00:00Z",
        "package_name": "com.example",
        "window_title": None,
        "rotation": 0,
        "screen_width": 1080,
        "screen_height": 2400,
        "truncated": False,
        "root": root,
        "nodes": [root | {"children": []}, child],
    }
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        requests.append(request)
        return FakeResponse(json.dumps(payload, ensure_ascii=False).encode())

    monkeypatch.setattr("tapbot.android.client.urlopen", fake_urlopen)

    tree = AndroidAgentClient("http://phone:8765", "secret").ui_tree()

    assert requests[0].full_url == "http://phone:8765/api/ui-tree"
    assert tree.root.children[0].text == "사진 인증"
    assert tree.nodes[1].view_id_resource_name == "com.example:id/verifyButton"
    assert tree.nodes[1].bounds.center == (540.0, 1750.0)


def _ui_node_payload(
    node_id: str,
    *,
    parent_id: str | None = None,
    depth: int = 0,
    text: str | None = None,
    view_id: str | None = None,
    clickable: bool = False,
    bounds: dict[str, int] | None = None,
    children: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "parent_id": parent_id,
        "depth": depth,
        "class_name": "android.widget.Button" if clickable else "android.view.View",
        "text": text,
        "content_description": None,
        "view_id_resource_name": view_id,
        "package_name": "com.example",
        "bounds": bounds or {"left": 0, "top": 0, "right": 1080, "bottom": 2400},
        "clickable": clickable,
        "enabled": True,
        "focusable": False,
        "focused": False,
        "selected": False,
        "checked": False,
        "checkable": False,
        "scrollable": False,
        "editable": False,
        "visible_to_user": True,
        "password": False,
        "child_count": len(children or []),
        "children": children or [],
    }
