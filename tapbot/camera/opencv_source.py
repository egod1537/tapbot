"""Physical OpenCV camera source."""

from __future__ import annotations

from collections.abc import Callable
import sys
import time
from typing import Protocol, TypeAlias

import cv2
import numpy as np

from tapbot.camera.source import (
    BGRFrame,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraSource,
    FrameInfo,
    base_metadata,
    validate_bgr_frame,
)


OpenCVInput: TypeAlias = int | str
WINDOWS_CAMERA_BACKENDS = (cv2.CAP_MSMF, cv2.CAP_DSHOW)
CAMERA_PROBE_READS = 3


class _CaptureHandle(Protocol):
    def isOpened(self) -> bool: ...  # noqa: N802

    def read(self) -> tuple[bool, object | None]: ...

    def release(self) -> None: ...

    def get(self, property_id: int) -> float: ...


class _BufferedCapture:
    """Return the discovery frame once before delegating to OpenCV."""

    def __init__(self, capture: _CaptureHandle, frame: object) -> None:
        self._capture = capture
        self._frame: object | None = frame

    def isOpened(self) -> bool:  # noqa: N802
        return self._capture.isOpened()

    def read(self) -> tuple[bool, object | None]:
        if self._frame is not None:
            frame, self._frame = self._frame, None
            return True, frame
        return self._capture.read()

    def release(self) -> None:
        self._frame = None
        self._capture.release()

    def get(self, property_id: int) -> float:
        return self._capture.get(property_id)


class _UnavailableCapture:
    def isOpened(self) -> bool:  # noqa: N802
        return False

    def read(self) -> tuple[bool, None]:
        return False, None

    def release(self) -> None:
        pass

    def get(self, property_id: int) -> float:
        return 0.0


def create_opencv_capture(source: OpenCVInput) -> object:
    """Create a capture with a reliable native backend for the host platform.

    Windows laptops often expose separate HD and IR interfaces. A backend can
    report the IR interface as opened while producing a practically black
    frame, or report an already-occupied HD interface as opened but unreadable.
    Probe MSMF and DirectShow with real frame reads, keep the first usable BGR
    frame, and hide unusable interfaces from web discovery. File and network
    sources keep OpenCV's automatic backend selection.
    """

    if sys.platform == "win32" and isinstance(source, int):
        for backend in WINDOWS_CAMERA_BACKENDS:
            capture = cv2.VideoCapture(source, backend)
            if not capture.isOpened():
                capture.release()
                continue
            for _ in range(CAMERA_PROBE_READS):
                success, frame = capture.read()
                if success and _is_usable_camera_frame(frame):
                    return _BufferedCapture(capture, frame)
            capture.release()
        return _UnavailableCapture()
    return cv2.VideoCapture(source)


def _is_usable_camera_frame(frame: object) -> bool:
    if (
        not isinstance(frame, np.ndarray)
        or frame.dtype != np.uint8
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
    ):
        return False
    # A covered camera still contains sensor noise. The inactive IR interface
    # observed on Windows is effectively all-zero with only isolated artifacts.
    return not (float(frame.mean()) < 0.5 and float(frame.std()) < 2.0)


class OpenCVCameraSource(CameraSource):
    """Read BGR frames from a physical device index via OpenCV."""

    source_type = "physical"

    def __init__(
        self,
        device_index: int = 0,
        *,
        name: str | None = None,
        capture_factory: Callable[[int], object] = create_opencv_capture,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.device_index = device_index
        self.source = device_index
        self.id = f"opencv:{device_index}"
        self.name = name or f"OpenCV Camera {device_index}"
        self._capture_factory = capture_factory
        self._clock = clock
        self._capture: object | None = None
        self._last_frame_info: FrameInfo | None = None

    def open(self) -> None:
        if self.is_opened():
            return
        capture = self._capture_factory(self.device_index)
        if not bool(capture.isOpened()):  # type: ignore[attr-defined]
            capture.release()  # type: ignore[attr-defined]
            raise CameraOpenError(f"Could not open camera source: {self.id}")
        self._capture = capture

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()  # type: ignore[attr-defined]

    def is_opened(self) -> bool:
        return self._capture is not None and bool(
            self._capture.isOpened()  # type: ignore[attr-defined]
        )

    def read_frame(self) -> BGRFrame:
        capture = self._require_capture()
        success, raw_frame = capture.read()  # type: ignore[attr-defined]
        if not success or raw_frame is None:
            raise CameraReadError(f"Failed to read from camera source: {self.id}")
        frame = validate_bgr_frame(raw_frame, source_id=self.id)
        height, width = frame.shape[:2]
        self._last_frame_info = FrameInfo(self._clock(), width, height)
        return frame

    def get_metadata(self) -> CameraMetadata:
        if self._last_frame_info is not None:
            width = self._last_frame_info.width
            height = self._last_frame_info.height
        elif self.is_opened():
            capture = self._require_capture()
            width = int(
                capture.get(cv2.CAP_PROP_FRAME_WIDTH)  # type: ignore[attr-defined]
            )
            height = int(
                capture.get(cv2.CAP_PROP_FRAME_HEIGHT)  # type: ignore[attr-defined]
            )
        else:
            width = height = 0
        fps = (
            float(
                self._require_capture().get(  # type: ignore[attr-defined]
                    cv2.CAP_PROP_FPS
                )
            )
            if self.is_opened()
            else 0.0
        )
        return base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=width,
            height=height,
            fps=max(fps, 0.0),
        )

    def is_available(self) -> bool:
        if self.is_opened():
            return True
        capture = self._capture_factory(self.device_index)
        try:
            return bool(capture.isOpened())  # type: ignore[attr-defined]
        finally:
            capture.release()  # type: ignore[attr-defined]

    @property
    def last_frame_info(self) -> FrameInfo | None:
        return self._last_frame_info

    def _require_capture(self) -> object:
        if not self.is_opened():
            raise CameraNotOpenError(
                f"Camera source is not open: {self.id}; call open() first"
            )
        assert self._capture is not None
        return self._capture
