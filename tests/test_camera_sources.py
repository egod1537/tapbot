from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import time

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

from tapbot.camera.descriptors import CameraSourceDescriptor
from tapbot.camera.image_source import ImageCameraSource
from tapbot.camera.manager import CameraManager, CameraSourceNotFoundError
from tapbot.camera.mock_graph_source import MockGraphCameraSource
import tapbot.camera.opencv_source as opencv_source_module
from tapbot.camera.opencv_source import OpenCVCameraSource, create_opencv_capture
from tapbot.camera.source import (
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraSource,
    base_metadata,
)
from tapbot.camera.video_source import VideoCameraSource
from tapbot.ui.app import create_app


class FakeCapture:
    def __init__(
        self,
        frames: list[tuple[bool, np.ndarray | None]],
        *,
        opened: bool = True,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
    ) -> None:
        self.frames = frames
        self.opened = opened
        self.width = width
        self.height = height
        self.fps = fps
        self.released = False
        self.requested_properties: list[tuple[int, float]] = []

    def isOpened(self) -> bool:  # noqa: N802
        return self.opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self.frames.pop(0)

    def release(self) -> None:
        self.opened = False
        self.released = True

    def get(self, property_id: int) -> float:
        return {
            cv2.CAP_PROP_FRAME_WIDTH: self.width,
            cv2.CAP_PROP_FRAME_HEIGHT: self.height,
            cv2.CAP_PROP_FPS: self.fps,
        }.get(property_id, 0.0)

    def set(self, property_id: int, value: float) -> bool:
        self.requested_properties.append((property_id, value))
        return True


class FakeCameraSource(CameraSource):
    source_type = "mock_graph"

    def __init__(self, source_id: str, value: int) -> None:
        self.id = source_id
        self.name = f"Fake {source_id}"
        self.source = source_id
        self.value = value
        self.opened = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        if self.opened:
            return
        self.opened = True
        self.open_calls += 1

    def close(self) -> None:
        if not self.opened:
            return
        self.opened = False
        self.close_calls += 1

    def is_opened(self) -> bool:
        return self.opened

    def read_frame(self) -> np.ndarray:
        if not self.opened:
            raise CameraNotOpenError("fake source is closed")
        return np.full((8, 12, 3), self.value, dtype=np.uint8)

    def get_metadata(self) -> CameraMetadata:
        return base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=12,
            height=8,
            fps=20.0,
        )


def descriptor(
    source_id: str, source_type: str = "mock_graph"
) -> CameraSourceDescriptor:
    return CameraSourceDescriptor(
        id=source_id,
        name=f"Source {source_id}",
        type=source_type,  # type: ignore[arg-type]
        available=True,
        metadata={
            "width": 12,
            "height": 8,
            "fps": 20.0,
            "type": source_type,
            "name": f"Source {source_id}",
        },
    )


def test_manager_lists_physical_and_mock_sources_together() -> None:
    probed_indexes: list[int] = []
    probes: list[FakeCapture] = []

    def capture_factory(index: int) -> FakeCapture:
        probed_indexes.append(index)
        capture = FakeCapture([], opened=index in {0, 2})
        probes.append(capture)
        return capture

    manager = CameraManager.with_defaults(
        "mock:reservation-flow",
        discovery_max_index=2,
        capture_factory=capture_factory,
    )

    sources = manager.list_sources()

    assert [(source.id, source.type) for source in sources] == [
        ("opencv:0", "physical"),
        ("opencv:2", "physical"),
        ("mock:reservation-flow", "mock_graph"),
    ]
    assert [source.name for source in sources[:2]] == ["Camera 0", "Camera 2"]
    assert probed_indexes == [0, 1, 2]
    assert all(probe.released for probe in probes)
    assert manager.active_source_id == "mock:reservation-flow"


def test_source_api_refresh_rediscovers_new_physical_camera() -> None:
    available_indexes: set[int] = set()

    def capture_factory(index: int) -> FakeCapture:
        return FakeCapture([], opened=index in available_indexes)

    manager = CameraManager.with_defaults(
        "mock:reservation-flow",
        discovery_max_index=1,
        capture_factory=capture_factory,
    )
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        initial = client.get("/api/camera/sources")
        available_indexes.add(1)
        cached = client.get("/api/camera/sources")
        refreshed = client.get("/api/camera/sources?refresh=true")

    assert [source["id"] for source in initial.json()["sources"]] == [
        "mock:reservation-flow"
    ]
    assert [source["id"] for source in cached.json()["sources"]] == [
        "mock:reservation-flow"
    ]
    assert [source["id"] for source in refreshed.json()["sources"]] == [
        "opencv:1",
        "mock:reservation-flow",
    ]


def test_manager_switches_sources_without_changing_consumer_api() -> None:
    first = FakeCameraSource("mock:first", 10)
    second = FakeCameraSource("mock:second", 200)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(first.id), lambda: first)
    manager.register(descriptor(second.id), lambda: second)
    manager.select(first.id)

    first_frame = manager.read_frame()
    manager.select(second.id)
    second_frame = manager.read_frame()

    assert first_frame[0, 0].tolist() == [10, 10, 10]
    assert second_frame[0, 0].tolist() == [200, 200, 200]
    assert first.close_calls == 1
    assert second.open_calls == 1
    assert manager.get_metadata()["type"] == "mock_graph"


def test_manager_status_reconnect_and_close_current() -> None:
    source = FakeCameraSource("mock:status", 50)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(source.id), lambda: source)
    manager.select(source.id)

    assert manager.current_source() is source
    assert manager.status()["state"] == "connected"

    manager.reconnect()

    assert source.close_calls == 1
    assert source.open_calls == 2
    assert manager.status()["connected"] is True

    manager.close_current()

    assert manager.status()["state"] == "disconnected"


def test_manager_keeps_failed_selection_and_error_status() -> None:
    class FailingCameraSource(FakeCameraSource):
        def open(self) -> None:
            raise CameraOpenError("camera is busy")

    working = FakeCameraSource("mock:working", 10)
    failing = FailingCameraSource("mock:failing", 0)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(working.id), lambda: working)
    manager.register(descriptor(failing.id), lambda: failing)
    manager.select(working.id)

    with pytest.raises(CameraOpenError, match="busy"):
        manager.select(failing.id)

    status = manager.status()
    assert working.close_calls == 1
    assert status["source_id"] == "mock:failing"
    assert status["state"] == "error"
    assert status["connected"] is False
    assert status["error"] == "camera is busy"


def test_source_switch_waits_for_in_flight_frame_read() -> None:
    read_started = Event()
    release_read = Event()

    class BlockingCameraSource(FakeCameraSource):
        def read_frame(self) -> np.ndarray:
            read_started.set()
            assert release_read.wait(1)
            return super().read_frame()

    first = BlockingCameraSource("mock:blocking", 10)
    second = FakeCameraSource("mock:next", 20)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(first.id), lambda: first)
    manager.register(descriptor(second.id), lambda: second)
    manager.select(first.id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        read_future = pool.submit(manager.read_frame)
        assert read_started.wait(1)
        select_future = pool.submit(manager.select, second.id)
        time.sleep(0.02)
        assert not select_future.done()
        release_read.set()
        assert read_future.result().mean() == 10
        assert select_future.result() is second

    assert first.close_calls == 1
    assert second.is_opened()


def test_manager_reports_unknown_source_explicitly() -> None:
    manager = CameraManager(discovery_max_index=None)

    with pytest.raises(CameraSourceNotFoundError, match="not registered"):
        manager.select("mock:missing")


def test_opencv_source_returns_bgr_and_metadata() -> None:
    frame = np.full((4, 6, 3), (5, 10, 200), dtype=np.uint8)
    capture = FakeCapture([(True, frame)], width=6, height=4, fps=24)
    source = OpenCVCameraSource(
        2,
        capture_factory=lambda _: capture,
        clock=lambda: 100.0,
    )

    source.open()
    result = source.read_frame()

    assert result is frame
    assert source.id == "opencv:2"
    assert source.get_metadata() == {
        "width": 6,
        "height": 4,
        "fps": 24.0,
        "type": "physical",
        "name": "OpenCV Camera 2",
    }


def test_windows_physical_camera_uses_directshow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    black = np.zeros((4, 6, 3), dtype=np.uint8)
    frame = np.full((4, 6, 3), 100, dtype=np.uint8)
    msmf_capture = FakeCapture([(True, black), (True, black), (True, black)])
    directshow_capture = FakeCapture([(True, frame)])
    captures = [msmf_capture, directshow_capture]
    monkeypatch.setattr(opencv_source_module.sys, "platform", "win32")
    monkeypatch.setattr(
        opencv_source_module.cv2,
        "VideoCapture",
        lambda *args: calls.append(args) or captures.pop(0),
    )

    result = create_opencv_capture(0)

    assert result.isOpened()  # type: ignore[attr-defined]
    assert result.read() == (True, frame)  # type: ignore[attr-defined]
    assert calls == [(0, cv2.CAP_MSMF), (0, cv2.CAP_DSHOW)]
    expected_mode = [
        (cv2.CAP_PROP_FRAME_WIDTH, 1280.0),
        (cv2.CAP_PROP_FRAME_HEIGHT, 720.0),
        (cv2.CAP_PROP_FPS, 30.0),
    ]
    assert msmf_capture.requested_properties == expected_mode
    assert directshow_capture.requested_properties == expected_mode


def test_windows_camera_rejects_opened_capture_without_usable_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures: list[FakeCapture] = []

    def black_capture(*_args: object) -> FakeCapture:
        black = np.zeros((4, 6, 3), dtype=np.uint8)
        capture = FakeCapture([(True, black.copy()) for _ in range(3)])
        captures.append(capture)
        return capture

    monkeypatch.setattr(opencv_source_module.sys, "platform", "win32")
    monkeypatch.setattr(opencv_source_module.cv2, "VideoCapture", black_capture)

    result = create_opencv_capture(0)

    assert not result.isOpened()  # type: ignore[attr-defined]
    assert all(capture.released for capture in captures)


def test_non_device_source_keeps_opencv_auto_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    capture = FakeCapture([])
    monkeypatch.setattr(opencv_source_module.sys, "platform", "win32")
    monkeypatch.setattr(
        opencv_source_module.cv2,
        "VideoCapture",
        lambda *args: calls.append(args) or capture,
    )

    result = create_opencv_capture("demo.mp4")

    assert result is capture
    assert calls == [("demo.mp4",)]


def test_video_source_read_failure_is_explicit() -> None:
    source = VideoCameraSource(
        "demo.mp4",
        source_id="video:demo",
        capture_factory=lambda _: FakeCapture([(False, None)]),
    )
    source.open()

    with pytest.raises(CameraReadError, match="video:demo"):
        source.read_frame()


def test_image_source_repeats_independent_bgr_frames(tmp_path: Path) -> None:
    image = np.full((5, 7, 3), (11, 22, 33), dtype=np.uint8)
    path = tmp_path / "test.png"
    assert cv2.imwrite(str(path), image)
    source = ImageCameraSource(path, source_id="image:test")

    source.open()
    first = source.read_frame()
    first[0, 0] = 0
    second = source.read_frame()

    assert source.is_available()
    assert second[0, 0].tolist() == [11, 22, 33]
    assert source.get_metadata()["width"] == 7
    assert source.get_metadata()["height"] == 5


def test_mock_graph_source_produces_valid_bgr_screen() -> None:
    source = MockGraphCameraSource(fps=10)
    source.open()

    frame = source.read_frame()

    assert frame.shape == (720, 1280, 3)
    assert frame.dtype == np.uint8
    assert source.get_metadata()["fps"] == 10
    assert source.current_state == "home"


def test_camera_source_api_lists_and_switches_manager_sources() -> None:
    first = FakeCameraSource("mock:first", 10)
    second = FakeCameraSource("mock:second", 200)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(first.id), lambda: first)
    manager.register(descriptor(second.id), lambda: second)
    manager.select(first.id)
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        listing = client.get("/api/camera/sources")
        switched = client.post(
            "/api/camera/select", json={"source_id": "mock:second"}
        )
        status = client.get("/api/camera/status")
        reconnected = client.post("/api/camera/reconnect")
        frame_response = None
        for _ in range(50):
            frame_response = client.get("/api/camera/frame")
            if frame_response.status_code == 200:
                break
            time.sleep(0.01)

    assert listing.status_code == 200
    assert listing.json()["active_id"] == "mock:first"
    assert [item["id"] for item in listing.json()["sources"]] == [
        "mock:first",
        "mock:second",
    ]
    assert switched.status_code == 200
    assert switched.json()["active_id"] == "mock:second"
    assert status.status_code == 200
    assert status.json()["source_id"] == "mock:second"
    assert status.json()["state"] == "connected"
    assert reconnected.status_code == 200
    assert reconnected.json()["source_id"] == "mock:second"
    assert frame_response is not None
    assert frame_response.status_code == 200
    decoded = cv2.imdecode(
        np.frombuffer(frame_response.content, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert int(decoded.mean()) == pytest.approx(200, abs=2)


def test_camera_api_resets_active_mock_graph() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        tapped = client.post("/api/robot/tap", json={"x": 640, "y": 540})
        before_reset = client.get("/api/camera/status")
        reset = client.post("/api/camera/reset-graph")
        after_reset = client.get("/api/camera/status")
        entries = client.get("/api/logs").json()["entries"]

    assert tapped.status_code == 200
    assert before_reset.json()["mock_graph"]["current_state"] == "reservation"
    assert reset.status_code == 200
    assert reset.json()["mock_graph"]["current_state"] == "home"
    assert after_reset.json()["mock_graph"]["current_state"] == "home"
    assert any(
        entry["event_type"] == "camera.graph.reset" for entry in entries
    )


def test_camera_api_rejects_graph_reset_for_non_mock_source() -> None:
    source = FakeCameraSource("image:still", 10)
    source.source_type = "image"
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(source.id, "image"), lambda: source)
    manager.select(source.id)
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        reset = client.post("/api/camera/reset-graph")
        graph_status = client.get("/api/mock-graph/status")

    assert reset.status_code == 409
    assert reset.json()["detail"] == "The active camera source is not a mock graph"
    assert graph_status.status_code == 409
    assert graph_status.json()["detail"] == (
        "The active camera source is not a mock graph"
    )


def test_camera_api_preserves_failed_source_status() -> None:
    class FailingCameraSource(FakeCameraSource):
        def open(self) -> None:
            raise CameraOpenError("device is unavailable")

    working = FakeCameraSource("mock:working", 10)
    failing = FailingCameraSource("mock:failing", 0)
    manager = CameraManager(discovery_max_index=None)
    manager.register(descriptor(working.id), lambda: working)
    manager.register(descriptor(failing.id), lambda: failing)
    manager.select(working.id)
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        selected = client.post(
            "/api/camera/select", json={"source_id": failing.id}
        )
        status = client.get("/api/camera/status")

    assert selected.status_code == 422
    assert status.status_code == 200
    assert status.json()["source_id"] == failing.id
    assert status.json()["state"] == "error"
    assert status.json()["connected"] is False
    assert "unavailable" in status.json()["error"]
