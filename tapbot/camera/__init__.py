"""Camera source abstractions and source management."""

from tapbot.camera.descriptors import CameraSourceDescriptor
from tapbot.camera.image_source import ImageCameraSource
from tapbot.camera.manager import CameraManager, CameraSourceNotFoundError
from tapbot.camera.mock_graph import (
    MockGraphError,
    MockGraphMetadata,
    MockGraphStateError,
    MockGraphValidationError,
    MockHotspot,
    MockScreenGraph,
    MockScreenState,
    MockTap,
    MockTransition,
)
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.camera.opencv_source import OpenCVCameraSource, create_opencv_capture
from tapbot.camera.source import (
    BGRFrame,
    CameraError,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraSource,
    CameraSourceType,
)
from tapbot.camera.video_source import VideoCameraSource
from tapbot.camera.scenario_registry import (
    MockScenarioDescriptor,
    MockScenarioNotFoundError,
    MockScenarioRegistry,
    MockScenarioRegistryError,
)

__all__ = [
    "BGRFrame",
    "CameraError",
    "CameraManager",
    "CameraMetadata",
    "CameraNotOpenError",
    "CameraOpenError",
    "CameraReadError",
    "CameraSource",
    "CameraSourceDescriptor",
    "CameraSourceNotFoundError",
    "CameraSourceType",
    "ImageCameraSource",
    "MockGraphError",
    "MockGraphMetadata",
    "MockGraphCameraSource",
    "MockGraphStateError",
    "MockGraphValidationError",
    "MockHotspot",
    "MockScreenGraph",
    "MockScreenState",
    "MockTap",
    "MockTransition",
    "MockScenarioDescriptor",
    "MockScenarioNotFoundError",
    "MockScenarioRegistry",
    "MockScenarioRegistryError",
    "OpenCVCameraSource",
    "create_opencv_capture",
    "VideoCameraSource",
]
