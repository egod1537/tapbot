"""OpenCV-backed camera capture service and development preview CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import logging
from os import PathLike, fspath
from pathlib import Path
import time
from typing import Protocol, TypeAlias

import cv2

from tapbot.camera.opencv_source import create_opencv_capture
from tapbot.camera.source import (
    BGRFrame,
    CameraError,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraReadError,
    CameraSource as CameraSourceBase,
    CameraSourceType,
    FrameInfo,
    base_metadata,
    validate_bgr_frame,
)


logger = logging.getLogger(__name__)

LegacyCameraInput: TypeAlias = int | str | PathLike[str]


class FrameSaveError(CameraError):
    """Raised when OpenCV cannot write a captured frame."""


class CaptureDevice(Protocol):
    """Small subset of ``cv2.VideoCapture`` used by CameraService."""

    def isOpened(self) -> bool: ...  # noqa: N802 - mirrors OpenCV

    def read(self) -> tuple[bool, BGRFrame | None]: ...

    def release(self) -> None: ...

    def get(self, property_id: int) -> float: ...


class CameraService(CameraSourceBase):
    """Own an OpenCV capture source behind a small, testable API.

    ``read_frame`` returns the untouched BGR array supplied by OpenCV. Metadata
    for that frame is available through ``last_frame_info``.
    """

    def __init__(
        self,
        source: LegacyCameraInput = 0,
        *,
        capture_factory: Callable[[int | str], CaptureDevice] = create_opencv_capture,
        image_writer: Callable[[str, BGRFrame], bool] = cv2.imwrite,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.source = source
        self.id = (
            f"opencv:{source}"
            if isinstance(source, int)
            else f"video:{Path(fspath(source)).stem or 'stream'}"
        )
        self.name = (
            f"OpenCV Camera {source}"
            if isinstance(source, int)
            else Path(fspath(source)).name or fspath(source)
        )
        self.source_type: CameraSourceType = (
            "physical" if isinstance(source, int) else "video"
        )
        self._capture_factory = capture_factory
        self._image_writer = image_writer
        self._clock = clock
        self._capture: CaptureDevice | None = None
        self._last_frame: BGRFrame | None = None
        self._last_frame_info: FrameInfo | None = None

    def open(self) -> None:
        """Open the configured source, or raise ``CameraOpenError``."""

        if self.is_opened():
            return

        normalized_source = (
            fspath(self.source) if isinstance(self.source, PathLike) else self.source
        )
        capture = self._capture_factory(normalized_source)
        if not capture.isOpened():
            capture.release()
            raise CameraOpenError(f"Could not open camera source: {self.source!r}")

        self._capture = capture
        logger.info("Opened camera source: %r", self.source)

    def read_frame(self) -> BGRFrame:
        """Read and return one original BGR frame.

        Failure is explicit: an unopened source raises ``CameraNotOpenError``
        and a failed device read raises ``CameraReadError``.
        """

        capture = self._require_open_capture()
        success, frame = capture.read()
        if not success or frame is None:
            raise CameraReadError(
                f"Failed to read a frame from camera source: {self.source!r}"
            )
        frame = validate_bgr_frame(frame, source_id=self.id)

        height, width = frame.shape[:2]
        self._last_frame = frame
        self._last_frame_info = FrameInfo(
            timestamp=self._clock(), width=width, height=height
        )
        return frame

    def save_frame(self, path: str | PathLike[str]) -> Path:
        """Save the latest BGR frame, capturing one first if necessary."""

        frame = self._last_frame if self._last_frame is not None else self.read_frame()
        destination = Path(path)
        try:
            written = self._image_writer(str(destination), frame)
        except (cv2.error, OSError) as error:
            raise FrameSaveError(f"Could not save frame to {destination}") from error
        if not written:
            raise FrameSaveError(f"Could not save frame to {destination}")

        logger.info("Saved camera frame: %s", destination)
        return destination

    def close(self) -> None:
        """Release the capture resource; repeated calls are safe."""

        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
            logger.info("Closed camera source: %r", self.source)

    def is_opened(self) -> bool:
        """Return whether the current capture resource is open."""

        return self._capture is not None and self._capture.isOpened()

    def get_resolution(self) -> tuple[int, int]:
        """Return current ``(width, height)`` in pixels."""

        capture = self._require_open_capture()
        if self._last_frame_info is not None:
            return self._last_frame_info.width, self._last_frame_info.height
        return (
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    def get_metadata(self) -> CameraMetadata:
        """Return the metadata shared by all camera source implementations."""

        if self.is_opened():
            width, height = self.get_resolution()
            fps = max(float(self._require_open_capture().get(cv2.CAP_PROP_FPS)), 0.0)
        else:
            width = height = 0
            fps = 0.0
        return base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=width,
            height=height,
            fps=fps,
        )

    def is_available(self) -> bool:
        if self.is_opened():
            return True
        normalized_source = (
            fspath(self.source) if isinstance(self.source, PathLike) else self.source
        )
        capture = self._capture_factory(normalized_source)
        try:
            return capture.isOpened()
        finally:
            capture.release()

    @property
    def last_frame_info(self) -> FrameInfo | None:
        """Metadata for the latest successful read, if one has occurred."""

        return self._last_frame_info

    @property
    def last_frame_timestamp(self) -> float | None:
        """Timestamp for the latest successful read, if one has occurred."""

        return (
            None if self._last_frame_info is None else self._last_frame_info.timestamp
        )

    def __enter__(self) -> CameraService:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _require_open_capture(self) -> CaptureDevice:
        if not self.is_opened():
            raise CameraNotOpenError(
                f"Camera source is not open: {self.source!r}; call open() first"
            )
        assert self._capture is not None
        return self._capture


def run_preview(
    camera: CameraService,
    *,
    screenshot_path: str | PathLike[str] = "tapbot-screenshot.jpg",
    window_name: str = "TapBot Camera Preview",
) -> None:
    """Show live video until Q/Escape; press S to save the current frame."""

    try:
        camera.open()
        while True:
            frame = camera.read_frame()
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                destination = camera.save_frame(screenshot_path)
                print(f"Saved screenshot: {destination}")
    finally:
        camera.close()
        cv2.destroyAllWindows()


def _parse_source(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the development camera preview CLI."""

    parser = argparse.ArgumentParser(description="Preview a TapBot camera source")
    parser.add_argument(
        "--source",
        type=_parse_source,
        default=0,
        help="device index, video file, or RTSP URL (default: 0)",
    )
    parser.add_argument(
        "--screenshot",
        default="tapbot-screenshot.jpg",
        help="path written when S is pressed",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    try:
        run_preview(CameraService(args.source), screenshot_path=args.screenshot)
    except CameraError as error:
        logger.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
