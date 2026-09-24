"""Canonical screen sources used by PC-side vision and macro execution."""

from tapbot.screen.adapters import (
    ImageFixtureScreenSource,
    LegacyCameraScreenSource,
    MockGraphScreenSource,
)
from tapbot.screen.android import AndroidRemoteScreenSource
from tapbot.screen.geometry import ScreenGeometry, ScreenInsets
from tapbot.screen.source import (
    ScreenFrame,
    ScreenReadError,
    ScreenSource,
    ScreenSourceError,
    ScreenSourceMetadata,
)

__all__ = [
    "AndroidRemoteScreenSource",
    "ImageFixtureScreenSource",
    "LegacyCameraScreenSource",
    "MockGraphScreenSource",
    "ScreenFrame",
    "ScreenGeometry",
    "ScreenInsets",
    "ScreenReadError",
    "ScreenSource",
    "ScreenSourceError",
    "ScreenSourceMetadata",
]
