"""No-retry HTTP client for the TapBot Android Agent primitive API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from tapbot.device.gesture import PointerGesture


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


@dataclass(frozen=True, slots=True)
class AndroidUiBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
        }


@dataclass(frozen=True, slots=True)
class AndroidUiNode:
    node_id: str
    parent_id: str | None
    depth: int
    class_name: str | None
    text: str | None
    content_description: str | None
    view_id_resource_name: str | None
    package_name: str | None
    bounds: AndroidUiBounds
    clickable: bool
    enabled: bool
    focusable: bool
    focused: bool
    selected: bool
    checked: bool
    checkable: bool
    scrollable: bool
    editable: bool
    visible_to_user: bool
    password: bool
    child_count: int
    children: tuple["AndroidUiNode", ...] = ()

    def to_dict(self, *, include_children: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "class_name": self.class_name,
            "text": self.text,
            "content_description": self.content_description,
            "view_id_resource_name": self.view_id_resource_name,
            "package_name": self.package_name,
            "bounds": self.bounds.to_dict(),
            "clickable": self.clickable,
            "enabled": self.enabled,
            "focusable": self.focusable,
            "focused": self.focused,
            "selected": self.selected,
            "checked": self.checked,
            "checkable": self.checkable,
            "scrollable": self.scrollable,
            "editable": self.editable,
            "visible_to_user": self.visible_to_user,
            "password": self.password,
            "child_count": self.child_count,
        }
        if include_children:
            result["children"] = [child.to_dict() for child in self.children]
        return result


@dataclass(frozen=True, slots=True)
class AndroidUiTree:
    request_id: str
    captured_at: str
    package_name: str | None
    window_title: str | None
    rotation: int
    screen_width: int
    screen_height: int
    root: AndroidUiNode
    nodes: tuple[AndroidUiNode, ...]
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "request_id": self.request_id,
            "captured_at": self.captured_at,
            "package_name": self.package_name,
            "window_title": self.window_title,
            "rotation": self.rotation,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "node_count": len(self.nodes),
            "truncated": self.truncated,
            "root": self.root.to_dict(),
            "nodes": [node.to_dict(include_children=False) for node in self.nodes],
        }


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

    def ui_tree(self) -> AndroidUiTree:
        payload = self._json_request("GET", "/api/ui-tree")
        try:
            root = _ui_node(payload.get("root"))
            raw_nodes = payload.get("nodes")
            if isinstance(raw_nodes, list):
                nodes = tuple(_ui_node(item) for item in raw_nodes)
            else:
                nodes = tuple(_flatten_ui_nodes(root))
            screen_width = _required_int(payload, "screen_width", minimum=1)
            screen_height = _required_int(payload, "screen_height", minimum=1)
            rotation = _required_int(payload, "rotation", minimum=0)
            if rotation not in (0, 90, 180, 270):
                raise ValueError("rotation must be 0, 90, 180, or 270")
            return AndroidUiTree(
                request_id=_required_string(payload, "request_id"),
                captured_at=_required_string(payload, "captured_at"),
                package_name=_optional_string(payload.get("package_name")),
                window_title=_optional_string(payload.get("window_title")),
                rotation=rotation,
                screen_width=screen_width,
                screen_height=screen_height,
                root=root,
                nodes=nodes,
                truncated=_required_bool(payload, "truncated"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AndroidAgentApiError(
                f"Android Agent returned an invalid UI tree: {error}",
                code="invalid_ui_tree",
                request_id=(
                    str(payload["request_id"])
                    if payload.get("request_id") is not None
                    else None
                ),
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

    def gesture(self, gesture: PointerGesture) -> AndroidActionResult:
        return self._action(
            "/api/gesture",
            {"points": [point.to_dict() for point in gesture.points]},
            duration_ms=gesture.duration_ms,
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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string field has a non-string value")
    return value


def _required_int(
    payload: dict[str, Any],
    key: str,
    *,
    minimum: int | None = None,
) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return value


def _required_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _ui_node(value: object) -> AndroidUiNode:
    if not isinstance(value, dict):
        raise ValueError("UI node must be an object")
    raw_bounds = value.get("bounds")
    if not isinstance(raw_bounds, dict):
        raise ValueError("UI node bounds must be an object")
    children = value.get("children", [])
    if not isinstance(children, list):
        raise ValueError("UI node children must be an array")
    node_id = value.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("UI node_id must be a non-empty string")
    password = _node_bool(value, "password")
    return AndroidUiNode(
        node_id=node_id,
        parent_id=_optional_string(value.get("parent_id")),
        depth=_node_int(value, "depth", minimum=0),
        class_name=_optional_string(value.get("class_name")),
        text=None if password else _optional_string(value.get("text")),
        content_description=_optional_string(value.get("content_description")),
        view_id_resource_name=_optional_string(value.get("view_id_resource_name")),
        package_name=_optional_string(value.get("package_name")),
        bounds=AndroidUiBounds(
            _node_int(raw_bounds, "left"),
            _node_int(raw_bounds, "top"),
            _node_int(raw_bounds, "right"),
            _node_int(raw_bounds, "bottom"),
        ),
        clickable=_node_bool(value, "clickable"),
        enabled=_node_bool(value, "enabled"),
        focusable=_node_bool(value, "focusable"),
        focused=_node_bool(value, "focused"),
        selected=_node_bool(value, "selected"),
        checked=_node_bool(value, "checked"),
        checkable=_node_bool(value, "checkable"),
        scrollable=_node_bool(value, "scrollable"),
        editable=_node_bool(value, "editable"),
        visible_to_user=_node_bool(value, "visible_to_user"),
        password=password,
        child_count=_node_int(value, "child_count", minimum=0),
        children=tuple(_ui_node(child) for child in children),
    )


def _node_int(
    payload: dict[str, Any],
    key: str,
    *,
    minimum: int | None = None,
) -> int:
    return _required_int(payload, key, minimum=minimum)


def _node_bool(payload: dict[str, Any], key: str) -> bool:
    return _required_bool(payload, key)


def _flatten_ui_nodes(root: AndroidUiNode) -> Iterator[AndroidUiNode]:
    yield root
    for child in root.children:
        yield from _flatten_ui_nodes(child)
