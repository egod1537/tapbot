import json
from pathlib import Path

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

from tapbot.android.client import (
    AndroidActionResult,
    AndroidScreenshot,
    AndroidUiBounds,
    AndroidUiNode,
    AndroidUiTree,
)
from tapbot.android.registry import AndroidDeviceConfig, AndroidDeviceRegistry
from tapbot.ui.app import create_app
from tapbot.ui.services import EventLog
from tapbot.device.gesture import PointerGesture
from tapbot.vision.detector import ColorButtonConfig, ColorButtonDetector


class FakeCamera:
    source = "registry-test-camera"

    def __init__(self) -> None:
        self.opened = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_opened(self) -> bool:
        return self.opened

    def read_frame(self) -> np.ndarray:
        return np.zeros((8, 12, 3), dtype=np.uint8)


class DeviceClient:
    def __init__(self, device_id: str, color: tuple[int, int, int]) -> None:
        self.base_url = f"http://{device_id}.test:8765"
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[30:70, 80:140] = color
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        self.image = encoded.tobytes()
        self.frame_id = 0
        self.taps: list[tuple[float, float, int]] = []
        self.commands: list[str] = []
        self.offline = False

    def status(self) -> dict[str, object]:
        if self.offline:
            raise OSError("device offline")
        return {
            "accessibility_enabled": True,
            "capture_ready": True,
            "stream_running": True,
            "remote_control_enabled": True,
            "agent_version": "test",
            "device": {"width": 200, "height": 100, "rotation": 0, "density": 3},
        }

    def stream_status(self) -> dict[str, object]:
        if self.offline:
            raise OSError("stream offline")
        return {"running": True, "width": 200, "height": 100, "fps": 20.0}

    def screenshot(self) -> AndroidScreenshot:
        if self.offline:
            raise OSError("device offline")
        self.frame_id += 1
        return AndroidScreenshot(
            self.image,
            "image/png",
            self.frame_id,
            200,
            100,
            0,
            "2026-09-25T00:00:00Z",
        )

    def tap(self, x: float, y: float, *, duration_ms: int) -> AndroidActionResult:
        self.taps.append((x, y, duration_ms))
        return AndroidActionResult("request", "action", "tap", "completed")

    def gesture(self, gesture: PointerGesture) -> AndroidActionResult:
        first = gesture.points[0]
        self.taps.append((first.x, first.y, gesture.duration_ms))
        return AndroidActionResult("request", "action", "gesture", "completed")

    def back(self) -> AndroidActionResult:
        self.commands.append("back")
        return AndroidActionResult("request", "action", "back", "completed")

    def home(self) -> AndroidActionResult:
        self.commands.append("home")
        return AndroidActionResult("request", "action", "home", "completed")

    def iter_stream(self):
        yield b"--tapbotframe\r\nContent-Type: image/jpeg\r\n\r\nfake\r\n"

    def ui_tree(self) -> AndroidUiTree:
        device_id = self.base_url.removeprefix("http://").split(".", 1)[0]
        root = AndroidUiNode(
            node_id="n0",
            parent_id=None,
            depth=0,
            class_name="android.widget.FrameLayout",
            text=device_id,
            content_description=None,
            view_id_resource_name=None,
            package_name=f"com.example.{device_id}",
            bounds=AndroidUiBounds(0, 0, 200, 100),
            clickable=False,
            enabled=True,
            focusable=False,
            focused=False,
            selected=False,
            checked=False,
            checkable=False,
            scrollable=False,
            editable=False,
            visible_to_user=True,
            password=False,
            child_count=0,
        )
        return AndroidUiTree(
            request_id=f"tree-{device_id}",
            captured_at="2026-09-25T00:00:00Z",
            package_name=root.package_name,
            window_title=None,
            rotation=0,
            screen_width=200,
            screen_height=100,
            root=root,
            nodes=(root,),
            truncated=False,
        )


def build_registry(tmp_path: Path):
    detector = ColorButtonDetector(
        ColorButtonConfig(
            label="reservation_button",
            min_area=100,
            morphology_kernel_size=1,
        )
    )
    registry = AndroidDeviceRegistry(
        (detector,),
        EventLog(),
        capture_dir=tmp_path,
        default_device_id="device-a",
    )
    device_a = DeviceClient("device-a", (0, 255, 0))
    device_b = DeviceClient("device-b", (255, 0, 0))
    registry.register(
        AndroidDeviceConfig("device-a", "Device A", device_a.base_url, "secret"),
        client=device_a,  # type: ignore[arg-type]
    )
    registry.register(
        AndroidDeviceConfig("device-b", "Device B", device_b.base_url, "secret"),
        client=device_b,  # type: ignore[arg-type]
    )
    return registry, device_a, device_b


def test_registry_builds_independent_stacks_and_rejects_duplicates(tmp_path: Path) -> None:
    registry, _, _ = build_registry(tmp_path)
    first, second = registry.list()

    assert first.client is not second.client
    assert first.source is not second.source
    assert first.controller is not second.controller
    assert first.debug_service is not second.debug_service
    assert first.ui_tree_provider is not second.ui_tree_provider
    assert first.debug_service.capture_dir == tmp_path / "device-a"
    assert second.debug_service.capture_dir == tmp_path / "device-b"
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(first.config)


def test_device_routes_isolate_actions_frames_macros_and_failures(tmp_path: Path) -> None:
    registry, device_a, device_b = build_registry(tmp_path)
    app = create_app(camera=FakeCamera(), android_registry=registry)

    with TestClient(app) as client:
        devices = client.get("/api/android/devices")
        assert client.post(
            "/api/android/device-a/tap",
            json={"x": 10, "y": 20, "duration_ms": 80},
        ).status_code == 200
        assert client.post("/api/android/device-a/vision/run").status_code == 200
        assert client.post("/api/android/device-a/macro/step").status_code == 200
        b_state = client.get("/api/android/device-b/debug/state").json()
        assert client.post("/api/android/device-b/macro/step").status_code == 200
        stopped_a = client.post("/api/android/device-a/macro/stop").json()
        stopped_b = client.post("/api/android/device-b/macro/stop").json()
        saved_a = client.post("/api/android/device-a/screenshot/save").json()
        saved_b = client.post("/api/android/device-b/screenshot/save").json()
        tree_a = client.get("/api/android/device-a/ui-tree").json()
        tree_b = client.get("/api/android/device-b/ui-tree").json()
        device_a.offline = True
        offline_a = client.get("/api/android/device-a/status").json()
        online_b = client.get("/api/android/device-b/status").json()
        missing = client.get("/api/android/missing/status")

    assert {item["id"] for item in devices.json()["devices"]} == {
        "device-a",
        "device-b",
    }
    assert len(device_a.taps) == 2
    assert device_b.taps == []
    assert b_state["device_id"] == "device-b"
    assert b_state["macro"]["step_index"] == 0
    assert stopped_a["macro"]["id"] != stopped_b["macro"]["id"]
    trace_a = tmp_path / "device-a" / "macros" / stopped_a["macro"]["id"] / "trace.json"
    trace_b = tmp_path / "device-b" / "macros" / stopped_b["macro"]["id"] / "trace.json"
    assert json.loads(trace_a.read_text(encoding="utf-8"))["device_id"] == "device-a"
    assert json.loads(trace_b.read_text(encoding="utf-8"))["device_id"] == "device-b"
    assert Path(saved_a["path"]).parent.parent == tmp_path / "device-a"
    assert Path(saved_b["path"]).parent.parent == tmp_path / "device-b"
    assert tree_a["device_id"] == "device-a"
    assert tree_a["package_name"] == "com.example.device-a"
    assert tree_b["device_id"] == "device-b"
    assert tree_b["package_name"] == "com.example.device-b"
    assert offline_a["connected"] is False
    assert online_b["connected"] is True
    assert missing.status_code == 404


def test_refresh_all_keeps_partial_failure_and_config_filters_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, device_a, _ = build_registry(tmp_path)
    device_a.offline = True
    summaries = registry.refresh_all()
    by_id = {item["id"]: item for item in summaries}
    assert by_id["device-a"]["connected"] is False
    assert by_id["device-b"]["connected"] is True

    config = tmp_path / "devices.json"
    config.write_text(
        json.dumps(
            {
                "devices": [
                    {
                        "id": "enabled",
                        "name": "Enabled",
                        "base_url": "http://enabled",
                        "token": "file-token",
                        "enabled": True,
                    },
                    {
                        "id": "disabled",
                        "name": "Disabled",
                        "base_url": "http://disabled",
                        "token": "unused",
                        "enabled": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TAPBOT_ANDROID_DEVICE_ENABLED_TOKEN", "env-token")
    created: list[tuple[str, str]] = []

    def factory(url: str, token: str):
        created.append((url, token))
        return DeviceClient("enabled", (0, 255, 0))

    loaded = AndroidDeviceRegistry.from_config_file(
        config,
        (),
        EventLog(),
        capture_dir=tmp_path,
        client_factory=factory,  # type: ignore[arg-type]
    )
    assert [context.config.id for context in loaded.list()] == ["enabled"]
    assert created == [("http://enabled", "env-token")]


def test_duplicate_ids_in_config_are_rejected_even_when_disabled(tmp_path: Path) -> None:
    config = tmp_path / "duplicates.json"
    device = {
        "id": "duplicate",
        "name": "Duplicate",
        "base_url": "http://duplicate",
        "token": "secret",
        "enabled": False,
    }
    config.write_text(json.dumps({"devices": [device, device]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        AndroidDeviceRegistry.from_config_file(config, (), EventLog())
