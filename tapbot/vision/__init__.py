"""Camera and image-processing services."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapbot.vision.camera import (
        CameraError,
        CameraNotOpenError,
        CameraOpenError,
        CameraReadError,
        CameraService,
        FrameInfo,
        FrameSaveError,
    )
    from tapbot.vision.calibration import (
        Calibration,
        CalibrationError,
        CalibrationNotFoundError,
        CalibrationStore,
        CoordinateOutOfBoundsError,
        CoordinateTransformError,
        Point2D,
        RobotWorkArea,
    )
    from tapbot.vision.detector import (
        BoundingBox,
        ColorButtonConfig,
        ColorButtonDetector,
        Detection,
        Detector,
        VisionPipeline,
        VisionResult,
        draw_debug_overlay,
        save_debug_overlay,
    )
    from tapbot.vision.screen import PhoneScreenDetector

__all__ = [
    "CameraError",
    "CameraNotOpenError",
    "CameraOpenError",
    "CameraReadError",
    "CameraService",
    "FrameInfo",
    "FrameSaveError",
    "Calibration",
    "CalibrationError",
    "CalibrationNotFoundError",
    "CalibrationStore",
    "CoordinateOutOfBoundsError",
    "CoordinateTransformError",
    "Point2D",
    "RobotWorkArea",
    "BoundingBox",
    "ColorButtonConfig",
    "ColorButtonDetector",
    "Detection",
    "Detector",
    "PhoneScreenDetector",
    "VisionPipeline",
    "VisionResult",
    "draw_debug_overlay",
    "save_debug_overlay",
]


def __getattr__(name: str) -> Any:
    """Load camera exports lazily so ``python -m`` remains warning-free."""

    camera_exports = {
        "CameraError",
        "CameraNotOpenError",
        "CameraOpenError",
        "CameraReadError",
        "CameraService",
        "FrameInfo",
        "FrameSaveError",
    }
    if name in camera_exports:
        from tapbot.vision import camera

        return getattr(camera, name)
    calibration_exports = {
        "Calibration",
        "CalibrationError",
        "CalibrationNotFoundError",
        "CalibrationStore",
        "CoordinateOutOfBoundsError",
        "CoordinateTransformError",
        "Point2D",
        "RobotWorkArea",
    }
    if name in calibration_exports:
        from tapbot.vision import calibration

        return getattr(calibration, name)
    if name == "PhoneScreenDetector":
        from tapbot.vision import screen

        return getattr(screen, name)
    if name in __all__:
        from tapbot.vision import detector

        return getattr(detector, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
