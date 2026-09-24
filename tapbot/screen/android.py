"""Android Agent-backed canonical screen source."""

from __future__ import annotations

from threading import RLock
from urllib.parse import urlparse

import cv2
import numpy as np

from tapbot.android.client import AndroidAgentClient, AndroidScreenshot
from tapbot.screen.source import (
    ScreenFrame,
    ScreenReadError,
    ScreenSource,
    ScreenSourceMetadata,
)


class AndroidRemoteScreenSource(ScreenSource):
    """Fetch canonical Android screenshots without phone detection/homography."""

    def __init__(
        self,
        client: AndroidAgentClient,
        *,
        source_id: str | None = None,
    ) -> None:
        self.client = client
        host = urlparse(client.base_url).netloc or "agent"
        self.source_id = source_id or f"android:{host}"
        self._latest: ScreenFrame | None = None
        self._status: dict[str, object] = {}
        self._lock = RLock()

    def refresh_status(self) -> dict[str, object]:
        status = self.client.status()
        device = status.get("device")
        if not isinstance(device, dict):
            raise ScreenReadError("Android Agent status is missing device geometry")
        snapshot = dict(status)
        stream_status = getattr(self.client, "stream_status", None)
        if callable(stream_status):
            try:
                snapshot["stream"] = stream_status()
            except Exception as error:
                snapshot["stream_error"] = str(error)
        with self._lock:
            self._status = snapshot
        return snapshot

    def latest_frame(self) -> ScreenFrame:
        with self._lock:
            latest = self._latest
        return latest if latest is not None else self.screenshot()

    def screenshot(self) -> ScreenFrame:
        remote = self.client.screenshot()
        image = self._decode(remote)
        frame = ScreenFrame(
            image=image,
            frame_id=str(remote.frame_id),
            source_id=self.source_id,
            captured_at=remote.captured_at,
            width=remote.width,
            height=remote.height,
            rotation=remote.rotation,
            metadata={
                "already_canonical": True,
                "transport": "android_agent_http",
                "mime_type": remote.mime_type,
            },
        )
        with self._lock:
            self._latest = frame
        return frame

    @property
    def width(self) -> int:
        return self._dimension("width")

    @property
    def height(self) -> int:
        return self._dimension("height")

    @property
    def rotation(self) -> int:
        with self._lock:
            if self._latest is not None:
                return self._latest.rotation
            device = self._status.get("device")
            value = device.get("rotation", 0) if isinstance(device, dict) else 0
        return int(value) if isinstance(value, int | float) else 0

    def get_metadata(self) -> ScreenSourceMetadata:
        with self._lock:
            status = dict(self._status)
        if not status:
            try:
                status = self.refresh_status()
            except Exception as error:
                status = {"status_error": str(error)}
        return {
            "source_id": self.source_id,
            "type": "android_remote",
            "already_canonical": True,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "agent": status,
        }

    def _dimension(self, name: str) -> int:
        with self._lock:
            if self._latest is not None:
                return int(getattr(self._latest, name))
            device = self._status.get("device")
            value = device.get(name, 0) if isinstance(device, dict) else 0
        return int(value) if isinstance(value, int | float) else 0

    def _decode(self, remote: AndroidScreenshot) -> np.ndarray:
        encoded = np.frombuffer(remote.content, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ScreenReadError("Android screenshot could not be decoded")
        height, width = image.shape[:2]
        if (width, height) != (remote.width, remote.height):
            raise ScreenReadError(
                "Android screenshot dimensions do not match response metadata: "
                f"decoded={width}x{height}, metadata={remote.width}x{remote.height}"
            )
        return image
