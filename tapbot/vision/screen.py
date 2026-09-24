"""Phone-screen extraction and perspective rectification."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from tapbot.vision.calibration import Calibration, PointTuple


class PhoneScreenDetector:
    """Extract a phone screen using the four corners in a calibration profile.

    Automatic contour discovery can be added later without changing the
    rectified-image contract consumed by downstream detectors.
    """

    def __init__(self, calibration: Calibration) -> None:
        self.calibration = calibration

    def detect_corners(self, frame: NDArray[np.uint8]) -> PointTuple:
        """Return calibrated camera corners after validating the input frame."""

        self._validate_frame(frame)
        return self.calibration.camera_corners

    def extract(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Return a front-facing BGR image of the calibrated phone screen."""

        self._validate_frame(frame)
        return self.calibration.rectify_frame(frame)

    def rectify(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Alias for ``extract`` emphasizing perspective rectification."""

        return self.extract(frame)

    def _validate_frame(self, frame: object) -> None:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Phone screen extraction requires a BGR image")
        if frame.size == 0:
            raise ValueError("Phone screen extraction requires a non-empty image")
        if self.calibration.camera_resolution is not None:
            expected_width, expected_height = self.calibration.camera_resolution
            actual_height, actual_width = frame.shape[:2]
            if (actual_width, actual_height) != (expected_width, expected_height):
                raise ValueError(
                    "Camera frame resolution "
                    f"{actual_width}x{actual_height} does not match calibration "
                    f"{expected_width}x{expected_height}"
                )
