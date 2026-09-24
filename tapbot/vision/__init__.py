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
        perspective_matrix,
        warp_perspective,
        warp_quadrilateral,
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
    from tapbot.vision.screen import (
        InvalidQuadrilateralError,
        PhoneScreenDetection,
        PhoneScreenDetectionError,
        PhoneScreenDetector,
        PhoneScreenDetectorConfig,
        PhoneScreenNotFoundError,
        PhoneScreenResult,
        ScreenBoundingBox,
        draw_phone_screen_overlay,
        order_corners,
    )
    from tapbot.vision.pipeline import (
        ScreenPipeline,
        ScreenPipelineResult,
        ScreenPipelineTimings,
    )

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
    "perspective_matrix",
    "warp_perspective",
    "warp_quadrilateral",
    "BoundingBox",
    "ColorButtonConfig",
    "ColorButtonDetector",
    "Detection",
    "Detector",
    "PhoneScreenDetector",
    "PhoneScreenDetectorConfig",
    "PhoneScreenDetection",
    "PhoneScreenResult",
    "PhoneScreenDetectionError",
    "PhoneScreenNotFoundError",
    "InvalidQuadrilateralError",
    "ScreenBoundingBox",
    "order_corners",
    "draw_phone_screen_overlay",
    "ScreenPipeline",
    "ScreenPipelineResult",
    "ScreenPipelineTimings",
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
        "perspective_matrix",
        "warp_perspective",
        "warp_quadrilateral",
    }
    if name in calibration_exports:
        from tapbot.vision import calibration

        return getattr(calibration, name)
    screen_exports = {
        "PhoneScreenDetector",
        "PhoneScreenDetectorConfig",
        "PhoneScreenDetection",
        "PhoneScreenResult",
        "PhoneScreenDetectionError",
        "PhoneScreenNotFoundError",
        "InvalidQuadrilateralError",
        "ScreenBoundingBox",
        "order_corners",
        "draw_phone_screen_overlay",
    }
    if name in screen_exports:
        from tapbot.vision import screen

        return getattr(screen, name)
    pipeline_exports = {
        "ScreenPipeline",
        "ScreenPipelineResult",
        "ScreenPipelineTimings",
    }
    if name in pipeline_exports:
        from tapbot.vision import pipeline

        return getattr(pipeline, name)
    if name in __all__:
        from tapbot.vision import detector

        return getattr(detector, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
