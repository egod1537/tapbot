from pathlib import Path

import cv2
import numpy as np
import pytest

from tapbot.android.client import AndroidScreenshot
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.screen import (
    AndroidRemoteScreenSource,
    LegacyCameraScreenSource,
    MockGraphScreenSource,
    ScreenGeometry,
)


class StubAndroidClient:
    base_url = "http://phone.local:8765"

    def __init__(self, encoded: bytes) -> None:
        self.encoded = encoded

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "device": {"width": 4, "height": 3, "rotation": 0, "density": 3.0},
            "stream_running": True,
        }

    def screenshot(self) -> AndroidScreenshot:
        return AndroidScreenshot(
            self.encoded,
            "image/png",
            42,
            4,
            3,
            0,
            "2026-09-25T00:00:00Z",
        )


def test_android_source_decodes_canonical_screenshot_and_status() -> None:
    image = np.full((3, 4, 3), (10, 20, 30), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    source = AndroidRemoteScreenSource(StubAndroidClient(encoded.tobytes()))  # type: ignore[arg-type]

    status = source.refresh_status()
    frame = source.screenshot()

    assert status["stream_running"] is True
    assert frame.frame_id == "42"
    assert frame.source_id == "android:phone.local:8765"
    assert frame.metadata["already_canonical"] is True
    assert (source.width, source.height, source.rotation) == (4, 3, 0)
    assert source.metadata["already_canonical"] is True
    assert np.array_equal(frame.image, image)
    assert source.latest_frame() is frame


def test_noncanonical_camera_cannot_sneak_into_default_screen_path() -> None:
    source = MockGraphCameraSource("reservation-flow")
    with pytest.raises(ValueError, match="not a canonical ScreenSource"):
        LegacyCameraScreenSource(source, already_canonical=False)


def test_mock_graph_source_is_canonical_and_tracks_state() -> None:
    camera = MockGraphCameraSource("reservation-flow")
    camera.open()
    source = MockGraphScreenSource(camera)

    home = source.screenshot()
    camera.tap(640, 540)
    reservation = source.screenshot()

    assert home.metadata["current_state"] == "home"
    assert reservation.metadata["current_state"] == "reservation"
    assert home.frame_id != reservation.frame_id
    assert source.get_metadata()["already_canonical"] is True


def test_screen_geometry_is_identity_at_matching_resolution_and_scales() -> None:
    identity = ScreenGeometry(1080, 2400, 1080, 2400)
    assert identity.screen_to_device(520, 1170) == (520, 1170)

    scaled = ScreenGeometry(540, 1200, 1080, 2400)
    x, y = scaled.screen_to_device(539, 1199)
    assert (x, y) == (1079, 2399)
    with pytest.raises(ValueError, match="x must be within"):
        scaled.screen_to_device(540, 0)
