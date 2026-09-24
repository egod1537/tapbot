"""No-retry HTTP client for the TapBot Android Agent primitive API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class AndroidActionResult:
    request_id: str
    action_id: str
    command: str
    state: str


@dataclass(frozen=True, slots=True)
class AndroidScreenshot:
    content: bytes
    mime_type: str
    frame_id: int
    width: int
    height: int
    rotation: int
    captured_at: str


class AndroidAgentApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        request_id: str | None,
        status: int | None = None,
        action_id: str | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.status = status
        self.action_id = action_id
        self.outcome_unknown = outcome_unknown


class AndroidAgentTransportError(RuntimeError):
    """The request outcome is unknown; callers must not blindly retry input."""

    def __init__(self, message: str, *, outcome_unknown: bool) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class AndroidAgentClient:
    """Thin primitive client. It intentionally performs no automatic retries."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 5.0,
    ) -> None:
        normalized = base_url.rstrip("/")
        for suffix in ("/api/v1", "/api"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not token:
            raise ValueError("token must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = normalized
        self.token = token
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        payload = self._json_request("GET", "/api/status")
        return payload

    def stream_status(self) -> dict[str, Any]:
        """Return live-stream geometry and performance metadata."""

        return self._json_request("GET", "/api/stream/status")

    def iter_stream(self, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        """Proxy Android's authenticated MJPEG stream without buffering it."""

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        request = Request(
            f"{self.base_url}/api/stream",
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=max(self.timeout, 30.0)) as response:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except HTTPError as error:
            content = error.read()
            self._raise_api_error(content, error.code)
        except (URLError, TimeoutError, OSError) as error:
            raise AndroidAgentTransportError(
                "Android Agent stream disconnected.",
                outcome_unknown=False,
            ) from error

    def screenshot(self) -> AndroidScreenshot:
        content, headers = self._request("GET", "/api/screenshot")
        try:
            return AndroidScreenshot(
                content=content,
                mime_type=headers.get("Content-Type", "application/octet-stream")
                .split(";", 1)[0],
                frame_id=int(headers["X-Frame-Id"]),
                width=int(headers["X-Screen-Width"]),
                height=int(headers["X-Screen-Height"]),
                rotation=int(headers["X-Rotation"]),
                captured_at=headers["X-Captured-At"],
            )
        except (KeyError, ValueError) as error:
            raise AndroidAgentApiError(
                "Screenshot response is missing valid frame metadata",
                code="invalid_screenshot_metadata",
                request_id=headers.get("X-Request-Id"),
            ) from error

    def tap(self, x: float, y: float, *, duration_ms: int = 70) -> AndroidActionResult:
        return self._action(
            "/api/tap",
            {"x": x, "y": y, "duration_ms": duration_ms},
            duration_ms=duration_ms,
        )

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        duration_ms: int = 450,
    ) -> AndroidActionResult:
        return self._action(
            "/api/swipe",
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "duration_ms": duration_ms,
            },
            duration_ms=duration_ms,
        )

    def back(self) -> AndroidActionResult:
        return self._action("/api/back", None)

    def home(self) -> AndroidActionResult:
        return self._action("/api/home", None)

    def _action(
        self,
        path: str,
        payload: dict[str, object] | None,
        *,
        duration_ms: int = 0,
    ) -> AndroidActionResult:
        timeout = max(self.timeout, duration_ms / 1_000 + 3.0)
        result = self._json_request("POST", path, payload, timeout=timeout)
        return AndroidActionResult(
            request_id=_required_string(result, "request_id"),
            action_id=_required_string(result, "action_id"),
            command=_required_string(result, "command"),
            state=_required_string(result, "state"),
        )

    def _json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        content, _ = self._request(method, path, payload, timeout=timeout)
        try:
            value = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AndroidAgentApiError(
                "Android Agent returned invalid JSON",
                code="invalid_json_response",
                request_id=None,
            ) from error
        if not isinstance(value, dict):
            raise AndroidAgentApiError(
                "Android Agent returned a non-object JSON response",
                code="invalid_json_response",
                request_id=None,
            )
        if value.get("ok") is not True:
            error = value.get("error")
            error = error if isinstance(error, dict) else {}
            raise AndroidAgentApiError(
                str(error.get("message", "Android Agent reported a failed request")),
                code=str(error.get("code", "api_error")),
                request_id=(
                    str(value["request_id"])
                    if value.get("request_id") is not None
                    else None
                ),
                action_id=(
                    str(value["action_id"])
                    if value.get("action_id") is not None
                    else None
                ),
                outcome_unknown=bool(value.get("outcome_unknown", False)),
            )
        return value

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[bytes, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json, image/jpeg",
            "Authorization": f"Bearer {self.token}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                return response.read(), response.headers
        except HTTPError as error:
            content = error.read()
            self._raise_api_error(content, error.code)
            raise AssertionError("_raise_api_error must raise")
        except (URLError, TimeoutError, OSError) as error:
            non_idempotent = method == "POST" and path in {
                "/api/tap",
                "/api/swipe",
                "/api/back",
                "/api/home",
            }
            raise AndroidAgentTransportError(
                "Android Agent request failed. Do not automatically retry input commands.",
                outcome_unknown=non_idempotent,
            ) from error

    @staticmethod
    def _raise_api_error(content: bytes, status: int) -> None:
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        raise AndroidAgentApiError(
            str(error.get("message", f"Android Agent request failed ({status})")),
            code=str(error.get("code", "http_error")),
            request_id=(
                str(payload["request_id"])
                if isinstance(payload, dict) and payload.get("request_id") is not None
                else None
            ),
            status=status,
            action_id=(
                str(payload["action_id"])
                if isinstance(payload, dict) and payload.get("action_id") is not None
                else None
            ),
            outcome_unknown=bool(
                isinstance(payload, dict) and payload.get("outcome_unknown", False)
            ),
        )


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AndroidAgentApiError(
            f"Android Agent response is missing {key}",
            code="invalid_response",
            request_id=(
                str(payload["request_id"])
                if payload.get("request_id") is not None
                else None
            ),
        )
    return value
