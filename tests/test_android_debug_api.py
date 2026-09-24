from pathlib import Path

import cv2
from fastapi.testclient import TestClient
import numpy as np

from tapbot.android.client import AndroidActionResult, AndroidScreenshot
from tapbot.ui.app import create_app
from tapbot.vision.detector import ColorButtonConfig, ColorButtonDetector


class FakeCamera:
    source = "legacy-test-camera"

    def __init__(self) -> None:
        self.opened = False
        self.frame = np.zeros((8, 12, 3), dtype=np.uint8)

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_opened(self) -> bool:
        return self.opened

    def read_frame(self) -> np.ndarray:
        return self.frame.copy()


class FakeAndroidClient:
    base_url = "http://android.test:8765"

    def __init__(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        image[30:70, 80:140] = (0, 255, 0)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        self.image = encoded.tobytes()
        self.frame_id = 0
        self.taps: list[tuple[float, float, int]] = []
        self.commands: list[str] = []

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "accessibility_enabled": True,
            "capture_ready": True,
            "stream_running": True,
            "remote_control_enabled": True,
            "agent_version": "0.1.0",
            "device": {
                "width": 200,
                "height": 100,
                "rotation": 0,
                "density": 3.0,
            },
        }

    def stream_status(self) -> dict[str, object]:
        return {
            "ok": True,
            "running": True,
            "codec": "mjpeg",
            "transport": "http-multipart",
            "width": 200,
            "height": 100,
            "rotation": 0,
            "fps": 20.0,
            "target_fps": 20,
            "bitrate": 1000,
            "clients": 1,
            "capture_latency_ms": 4.0,
            "encode_latency_ms": 2.0,
            "frame_age_ms": 10,
        }

    def screenshot(self) -> AndroidScreenshot:
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
        return AndroidActionResult("req-tap", "action-tap", "tap", "completed")

    def back(self) -> AndroidActionResult:
        self.commands.append("back")
        return AndroidActionResult("req-back", "action-back", "back", "dispatched")

    def home(self) -> AndroidActionResult:
        self.commands.append("home")
        return AndroidActionResult("req-home", "action-home", "home", "dispatched")

    def iter_stream(self):
        yield b"--tapbotframe\r\nContent-Type: image/jpeg\r\n\r\nfake\r\n"


def make_android_client(
    tmp_path: Path,
) -> tuple[TestClient, FakeAndroidClient]:
    android = FakeAndroidClient()
    detector = ColorButtonDetector(
        ColorButtonConfig(
            label="reservation_button",
            min_area=100,
            morphology_kernel_size=1,
        )
    )
    app = create_app(
        camera=FakeCamera(),
        android_client=android,  # type: ignore[arg-type]
        android_capture_dir=tmp_path,
        vision_detectors=(detector,),
    )
    return TestClient(app), android


def test_android_proxy_status_screenshot_and_stream(tmp_path: Path) -> None:
    client, _ = make_android_client(tmp_path)

    with client:
        status = client.get("/api/android/status")
        screenshot = client.get("/api/android/screenshot")
        stream = client.get("/api/android/stream")

    assert status.json()["connected"] is True
    assert status.json()["stream"]["fps"] == 20.0
    assert screenshot.status_code == 200
    assert screenshot.headers["x-screen-width"] == "200"
    assert cv2.imdecode(np.frombuffer(screenshot.content, np.uint8), cv2.IMREAD_COLOR).shape == (
        100,
        200,
        3,
    )
    assert b"tapbotframe" in stream.content


def test_android_vision_macro_step_and_manual_controls(tmp_path: Path) -> None:
    client, android = make_android_client(tmp_path)

    with client:
        vision = client.post("/api/android/vision/run")
        step = client.post("/api/android/macro/step")
        manual = client.post(
            "/api/android/tap",
            json={"x": 10, "y": 20, "duration_ms": 80},
        )
        assert client.post("/api/android/back").status_code == 200
        assert client.post("/api/android/home").status_code == 200
        saved = client.post("/api/android/screenshot/save")

    assert vision.json()["state"]["current"] == "home"
    assert vision.json()["detections"][0]["label"] == "reservation_button"
    assert step.json()["macro"]["step_index"] == 1
    assert step.json()["last_action"]["type"] == "tap_target"
    assert manual.json()["device"] == {"x": 10.0, "y": 20.0}
    assert len(android.taps) == 2
    assert android.commands == ["back", "home"]
    assert Path(saved.json()["path"]).is_file()


def test_android_routes_report_unconfigured_without_touching_legacy_camera() -> None:
    app = create_app(camera=FakeCamera())

    with TestClient(app) as client:
        status = client.get("/api/android/status")
        screenshot = client.get("/api/android/screenshot")

    assert status.json()["configured"] is False
    assert screenshot.status_code == 503
