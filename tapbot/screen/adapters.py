"""Adapters for legacy camera, fixture, and mock graph sources."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from threading import RLock

from tapbot.camera.image_source import ImageCameraSource
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.camera.source import CameraSource
from tapbot.screen.source import (
    ScreenFrame,
    ScreenSource,
    ScreenSourceMetadata,
    captured_now,
)


class LegacyCameraScreenSource(ScreenSource):
    """Optional bridge for an already-canonical legacy ``CameraSource``."""

    def __init__(self, camera: CameraSource, *, already_canonical: bool) -> None:
        if not already_canonical:
            raise ValueError(
                "A physical camera is not a canonical ScreenSource; use the legacy "
                "phone detection pipeline explicitly"
            )
        self.camera = camera
        self.source_id = camera.id
        self._latest: ScreenFrame | None = None
        self._sequence = 0
        self._lock = RLock()

    def latest_frame(self) -> ScreenFrame:
        with self._lock:
            latest = self._latest
        return latest if latest is not None else self.screenshot()

    def screenshot(self) -> ScreenFrame:
        if not self.camera.is_opened():
            self.camera.open()
        image = self.camera.read_frame()
        height, width = image.shape[:2]
        with self._lock:
            self._sequence += 1
            frame_id = str(self._sequence)
        frame = ScreenFrame(
            image=image,
            frame_id=frame_id,
            source_id=self.source_id,
            captured_at=captured_now(),
            width=width,
            height=height,
            metadata={
                **self.camera.get_metadata(),
                "already_canonical": True,
                "legacy_camera_adapter": True,
            },
        )
        with self._lock:
            self._latest = frame
        return frame

    @property
    def width(self) -> int:
        return self._current_dimension("width")

    @property
    def height(self) -> int:
        return self._current_dimension("height")

    @property
    def rotation(self) -> int:
        return 0

    def get_metadata(self) -> ScreenSourceMetadata:
        return {
            **self.camera.get_metadata(),
            "source_id": self.source_id,
            "already_canonical": True,
            "legacy_camera_adapter": True,
        }

    def _current_dimension(self, key: str) -> int:
        with self._lock:
            latest = self._latest
        if latest is not None:
            return int(getattr(latest, key))
        value = self.camera.get_metadata().get(key, 0)
        return int(value) if isinstance(value, int | float) else 0


class MockGraphScreenSource(LegacyCameraScreenSource):
    """Canonical screen adapter for a stateful mock graph."""

    camera: MockGraphCameraSource

    def __init__(self, camera: MockGraphCameraSource) -> None:
        super().__init__(camera, already_canonical=True)

    def screenshot(self) -> ScreenFrame:
        frame = super().screenshot()
        state = self.camera.current_state
        digest = sha256(frame.image.tobytes()).hexdigest()[:12]
        enriched = ScreenFrame(
            image=frame.image,
            frame_id=f"{state}:{digest}",
            source_id=frame.source_id,
            captured_at=frame.captured_at,
            width=frame.width,
            height=frame.height,
            metadata={
                **frame.metadata,
                "current_state": state,
                "hotspot_count": len(self.camera.available_hotspots),
            },
        )
        with self._lock:
            self._latest = enriched
        return enriched


class ImageFixtureScreenSource(LegacyCameraScreenSource):
    """A repeatable canonical screenshot loaded from an image fixture."""

    def __init__(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        name: str | None = None,
    ) -> None:
        camera = ImageCameraSource(path, source_id=source_id, name=name)
        super().__init__(camera, already_canonical=True)
