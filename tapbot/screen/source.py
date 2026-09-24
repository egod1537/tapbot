"""Source-neutral canonical screen frame contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeAlias

import numpy as np
from numpy.typing import NDArray


BGRScreen: TypeAlias = NDArray[np.uint8]
ScreenSourceMetadata: TypeAlias = dict[str, Any]


class ScreenSourceError(RuntimeError):
    """Base error for canonical screen sources."""


class ScreenReadError(ScreenSourceError):
    """Raised when a source cannot return a valid screen frame."""


@dataclass(frozen=True, slots=True)
class ScreenFrame:
    """One canonical BGR screen image and its coordinate metadata."""

    image: BGRScreen
    frame_id: str
    source_id: str
    captured_at: str
    width: int
    height: int
    rotation: int = 0
    metadata: ScreenSourceMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_screen_image(self.image, source_id=self.source_id)
        image_height, image_width = self.image.shape[:2]
        if self.width != image_width or self.height != image_height:
            raise ValueError("ScreenFrame dimensions must match the decoded image")
        if not self.frame_id:
            raise ValueError("frame_id must not be empty")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")


class ScreenSource(ABC):
    """A producer of already-canonical screen frames.

    Unlike ``CameraSource``, this contract never implies a physical camera or
    a phone localization step. Every returned image is ready for UI vision.
    """

    source_id: str

    @abstractmethod
    def latest_frame(self) -> ScreenFrame:
        """Return the latest cached frame, fetching one if no cache exists."""

    @abstractmethod
    def screenshot(self) -> ScreenFrame:
        """Capture/fetch a new frame and update the latest-frame cache."""

    @property
    @abstractmethod
    def width(self) -> int:
        """Current canonical frame width, or zero before discovery."""

    @property
    @abstractmethod
    def height(self) -> int:
        """Current canonical frame height, or zero before discovery."""

    @property
    @abstractmethod
    def rotation(self) -> int:
        """Current display rotation in degrees."""

    @abstractmethod
    def get_metadata(self) -> ScreenSourceMetadata:
        """Return source and live-stream metadata."""

    @property
    def metadata(self) -> ScreenSourceMetadata:
        """Property form of metadata from the public ScreenSource contract."""

        return self.get_metadata()


def validate_screen_image(image: object, *, source_id: str) -> BGRScreen:
    if (
        not isinstance(image, np.ndarray)
        or image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or image.size == 0
    ):
        raise ScreenReadError(
            f"Screen source {source_id!r} returned an invalid BGR uint8 image"
        )
    return image


def captured_now() -> str:
    return datetime.now(timezone.utc).isoformat()
