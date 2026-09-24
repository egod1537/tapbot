"""Common camera source contract and errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray


CameraSourceType: TypeAlias = Literal["physical", "image", "video", "mock_graph"]
BGRFrame: TypeAlias = NDArray[np.uint8]
CameraMetadata: TypeAlias = dict[str, object]


class CameraError(RuntimeError):
    """Base class for camera source failures."""


class CameraOpenError(CameraError):
    """Raised when a source cannot be opened."""


class CameraNotOpenError(CameraError):
    """Raised when a source operation requires an open source."""


class CameraReadError(CameraError):
    """Raised when an open source cannot produce a valid BGR frame."""


@dataclass(frozen=True, slots=True)
class FrameInfo:
    """Metadata for the most recently captured BGR frame."""

    timestamp: float
    width: int
    height: int


class CameraSource(ABC):
    """Hardware-independent producer of uint8 BGR frames."""

    id: str
    name: str
    source_type: CameraSourceType

    @abstractmethod
    def open(self) -> None:
        """Acquire resources required to read frames."""

    @abstractmethod
    def close(self) -> None:
        """Release resources. Repeated calls must be safe."""

    @abstractmethod
    def is_opened(self) -> bool:
        """Return whether this source is ready to read."""

    @abstractmethod
    def read_frame(self) -> BGRFrame:
        """Return one BGR uint8 frame or raise ``CameraReadError``."""

    @abstractmethod
    def get_metadata(self) -> CameraMetadata:
        """Return width, height, fps, type, and name metadata."""

    def is_available(self) -> bool:
        """Return whether the source can currently be opened."""

        return True

    def __enter__(self) -> CameraSource:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def validate_bgr_frame(frame: object, *, source_id: str) -> BGRFrame:
    """Validate the common frame contract and return a typed array."""

    if (
        not isinstance(frame, np.ndarray)
        or frame.dtype != np.uint8
        or frame.ndim != 3
        or frame.shape[2] != 3
    ):
        raise CameraReadError(
            f"Camera source {source_id!r} returned an invalid BGR uint8 frame"
        )
    return frame


def base_metadata(
    *,
    name: str,
    source_type: CameraSourceType,
    width: int,
    height: int,
    fps: float,
) -> CameraMetadata:
    """Build metadata with the fields guaranteed by every source."""

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "type": source_type,
        "name": name,
    }
