"""Still-image camera source."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2

from tapbot.camera.source import (
    BGRFrame,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraSource,
    base_metadata,
    validate_bgr_frame,
)


class ImageCameraSource(CameraSource):
    """Expose a still image as a repeatable BGR camera frame."""

    source_type = "image"

    def __init__(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        name: str | None = None,
        image_reader: Callable[[str, int], object] = cv2.imread,
    ) -> None:
        self.path = Path(path)
        self.source = str(self.path)
        self.id = source_id or f"image:{self.path.stem}"
        self.name = name or self.path.name
        self._image_reader = image_reader
        self._frame: BGRFrame | None = None

    def open(self) -> None:
        if self.is_opened():
            return
        raw_frame = self._image_reader(str(self.path), cv2.IMREAD_COLOR)
        if raw_frame is None:
            raise CameraOpenError(f"Could not open image source: {self.path}")
        try:
            self._frame = validate_bgr_frame(raw_frame, source_id=self.id)
        except Exception as error:
            raise CameraOpenError(
                f"Could not open image source: {self.path}"
            ) from error

    def close(self) -> None:
        self._frame = None

    def is_opened(self) -> bool:
        return self._frame is not None

    def read_frame(self) -> BGRFrame:
        if self._frame is None:
            raise CameraNotOpenError(
                f"Camera source is not open: {self.id}; call open() first"
            )
        return self._frame.copy()

    def get_metadata(self) -> CameraMetadata:
        height, width = (self._frame.shape[:2] if self._frame is not None else (0, 0))
        metadata = base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=width,
            height=height,
            fps=0.0,
        )
        metadata["path"] = str(self.path)
        return metadata

    def is_available(self) -> bool:
        return self.path.is_file()
