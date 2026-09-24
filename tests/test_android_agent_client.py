from email.message import Message
import json
from urllib.error import URLError

import pytest

from tapbot.android.client import (
    AndroidAgentClient,
    AndroidAgentTransportError,
)


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
