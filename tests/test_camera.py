from pathlib import Path

import numpy as np
import pytest

import tapbot.vision.camera as camera_module
from tapbot.vision.camera import (
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraService,
    FrameSaveError,
    run_preview,
)


class FakeCapture:
    def __init__(
        self,
        frames: list[tuple[bool, np.ndarray | None]],
        *,
        opened: bool = True,
        resolution: tuple[int, int] = (640, 480),
    ) -> None:
        self.frames = frames
        self.opened = opened
        self.resolution = resolution
        self.release_calls = 0

    def isOpened(self) -> bool:  # noqa: N802
        return self.opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self.frames.pop(0)

    def release(self) -> None:
        self.opened = False
        self.release_calls += 1

    def get(self, property_id: int) -> float:
        # CameraService asks for width followed by height.
        return float(self.resolution[0] if property_id == 3 else self.resolution[1])


def make_service(
    capture: FakeCapture,
    *,
    writer=lambda _path, _frame: True,
    clock=lambda: 1234.5,
) -> CameraService:
    return CameraService(
        capture_factory=lambda _source: capture,
        image_writer=writer,
        clock=clock,
    )


def test_open_read_and_frame_metadata() -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    capture = FakeCapture([(True, frame)])
    camera = make_service(capture)

    camera.open()
    result = camera.read_frame()

    assert result is frame
    assert camera.is_opened()
    assert camera.get_resolution() == (640, 480)
    assert camera.last_frame_timestamp == 1234.5
    assert camera.last_frame_info is not None
    assert camera.last_frame_info.width == 640
    assert camera.last_frame_info.height == 480


def test_default_source_is_device_zero() -> None:
    sources: list[int | str] = []
    capture = FakeCapture([])
    camera = CameraService(capture_factory=lambda source: sources.append(source) or capture)

    camera.open()

    assert sources == [0]


def test_string_source_supports_future_file_or_rtsp_input() -> None:
    sources: list[int | str] = []
    capture = FakeCapture([])
    camera = CameraService(
        "rtsp://camera/stream",
        capture_factory=lambda source: sources.append(source) or capture,
    )

    camera.open()

    assert sources == ["rtsp://camera/stream"]


def test_open_failure_is_explicit_and_releases_capture() -> None:
    capture = FakeCapture([], opened=False)
    camera = make_service(capture)

    with pytest.raises(CameraOpenError, match="Could not open"):
        camera.open()

    assert capture.release_calls == 1
    assert not camera.is_opened()


def test_read_before_open_is_distinct_from_device_read_failure() -> None:
    camera = make_service(FakeCapture([]))

    with pytest.raises(CameraNotOpenError, match="call open"):
        camera.read_frame()


def test_device_read_failure_is_explicit() -> None:
    camera = make_service(FakeCapture([(False, None)]))
    camera.open()

    with pytest.raises(CameraReadError, match="Failed to read"):
        camera.read_frame()


def test_save_frame_captures_and_writes_bgr_data(tmp_path: Path) -> None:
    frame = np.full((2, 3, 3), 127, dtype=np.uint8)
    writes: list[tuple[str, np.ndarray]] = []
    camera = make_service(
        FakeCapture([(True, frame)]),
        writer=lambda path, image: writes.append((path, image)) or True,
    )
    camera.open()
    destination = tmp_path / "screenshot.png"

    result = camera.save_frame(destination)

    assert result == destination
    assert writes == [(str(destination), frame)]


def test_save_failure_is_explicit(tmp_path: Path) -> None:
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    camera = make_service(FakeCapture([(True, frame)]), writer=lambda *_: False)
    camera.open()

    with pytest.raises(FrameSaveError, match="Could not save"):
        camera.save_frame(tmp_path / "missing.png")


def test_close_is_idempotent() -> None:
    capture = FakeCapture([])
    camera = make_service(capture)
    camera.open()

    camera.close()
    camera.close()

    assert capture.release_calls == 1
    assert not camera.is_opened()


def test_context_manager_always_releases_capture() -> None:
    capture = FakeCapture([])
    camera = make_service(capture)

    with pytest.raises(RuntimeError):
        with camera:
            raise RuntimeError("test failure")

    assert capture.release_calls == 1


def test_resolution_is_available_before_first_frame() -> None:
    camera = make_service(FakeCapture([], resolution=(1920, 1080)))
    camera.open()

    assert camera.get_resolution() == (1920, 1080)


def test_preview_releases_camera_and_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    capture = FakeCapture([(True, frame)])
    camera = make_service(capture)
    shown: list[tuple[str, np.ndarray]] = []
    windows_closed: list[bool] = []
    monkeypatch.setattr(
        camera_module.cv2,
        "imshow",
        lambda name, image: shown.append((name, image)),
    )
    monkeypatch.setattr(camera_module.cv2, "waitKey", lambda _delay: ord("q"))
    monkeypatch.setattr(
        camera_module.cv2,
        "destroyAllWindows",
        lambda: windows_closed.append(True),
    )

    run_preview(camera)

    assert shown == [("TapBot Camera Preview", frame)]
    assert capture.release_calls == 1
    assert windows_closed == [True]
