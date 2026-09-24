"""Video-file camera source."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2

from tapbot.camera.source import (
    BGRFrame,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraSource,
    base_metadata,
    validate_bgr_frame,
)


class VideoCameraSource(CameraSource):
    """Read sequential BGR frames from a video file or stream URL."""

    source_type = "video"

    def __init__(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        name: str | None = None,
        capture_factory: Callable[[str], object] = cv2.VideoCapture,
    ) -> None:
        self.path = str(path)
        self.source = self.path
        stem = Path(self.path).stem or "stream"
        self.id = source_id or f"video:{stem}"
        self.name = name or Path(self.path).name or self.path
        self._capture_factory = capture_factory
        self._capture: object | None = None

    def open(self) -> None:
        if self.is_opened():
            return
        capture = self._capture_factory(self.path)
        if not bool(capture.isOpened()):  # type: ignore[attr-defined]
            capture.release()  # type: ignore[attr-defined]
            raise CameraOpenError(f"Could not open video source: {self.path}")
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
            raise CameraReadError(f"Failed to read from video source: {self.id}")
        return validate_bgr_frame(raw_frame, source_id=self.id)

    def get_metadata(self) -> CameraMetadata:
        if self.is_opened():
            capture = self._require_capture()
            width = int(
                capture.get(cv2.CAP_PROP_FRAME_WIDTH)  # type: ignore[attr-defined]
            )
            height = int(
                capture.get(cv2.CAP_PROP_FRAME_HEIGHT)  # type: ignore[attr-defined]
            )
            fps = float(capture.get(cv2.CAP_PROP_FPS))  # type: ignore[attr-defined]
        else:
            width = height = 0
            fps = 0.0
        metadata = base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=width,
            height=height,
            fps=max(fps, 0.0),
        )
        metadata["path"] = self.path
        return metadata

    def is_available(self) -> bool:
        if self.is_opened():
            return True
        if "://" not in self.path and not Path(self.path).is_file():
            return False
        capture = self._capture_factory(self.path)
        try:
            return bool(capture.isOpened())  # type: ignore[attr-defined]
        finally:
            capture.release()  # type: ignore[attr-defined]

    def _require_capture(self) -> object:
        if not self.is_opened():
            raise CameraNotOpenError(
                f"Camera source is not open: {self.id}; call open() first"
            )
        assert self._capture is not None
        return self._capture
