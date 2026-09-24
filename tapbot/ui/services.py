"""Threaded services used by the web UI."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import itertools
import logging
from queue import PriorityQueue
from threading import Event, Lock, Thread
from time import perf_counter

import cv2
import numpy as np
from numpy.typing import NDArray

from tapbot.camera.source import CameraError, CameraSource
from tapbot.core.actions import Action, EmergencyStopAction
from tapbot.core.executor import ActionExecutor
from tapbot.robot.controller import RobotController


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LogEntry:
    id: int
    timestamp: str
    level: str
    message: str
    event_type: str
    category: str
    status: str
    trace_id: str | None
    latency_ms: float | None
    payload: dict[str, object]


class EventLog:
    """Small thread-safe in-memory log for the operator UI."""

    def __init__(self, capacity: int = 500) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._ids = itertools.count(1)
        self._lock = Lock()

    def add(
        self,
        message: str,
        *,
        level: str = "info",
        event_type: str = "system.log",
        category: str = "system",
        status: str | None = None,
        trace_id: str | None = None,
        latency_ms: float | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> LogEntry:
        with self._lock:
            entry = LogEntry(
                id=next(self._ids),
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=level,
                message=message,
                event_type=event_type,
                category=category,
                status=(
                    status
                    if status is not None
                    else (level if level in {"warning", "error"} else "info")
                ),
                trace_id=trace_id,
                latency_ms=latency_ms,
                payload=dict(payload or {}),
            )
            self._entries.append(entry)
        getattr(logger, level if level in {"debug", "info", "warning", "error"} else "info")(
            "%s", message
        )
        return entry

    def entries(self, *, after_id: int = 0) -> list[LogEntry]:
        with self._lock:
            return [entry for entry in self._entries if entry.id > after_id]


@dataclass(order=True, slots=True)
class _QueuedAction:
    priority: int
    sequence: int
    action: Action = field(compare=False)
    trace_id: str | None = field(compare=False, default=None)
    submitted_at: float = field(compare=False, default_factory=perf_counter)
    completed: Event = field(compare=False, default_factory=Event)
    error: BaseException | None = field(compare=False, default=None)
    shutdown: bool = field(compare=False, default=False)


class RobotCommandDispatcher:
    """Execute robot actions sequentially, prioritizing emergency stops."""

    _EMERGENCY_PRIORITY = 0
    _NORMAL_PRIORITY = 10
    _SHUTDOWN_PRIORITY = 100

    def __init__(
        self,
        controller: RobotController,
        event_log: EventLog,
    ) -> None:
        self.controller = controller
        self._executor = ActionExecutor(controller)
        self._event_log = event_log
        self._queue: PriorityQueue[_QueuedAction] = PriorityQueue()
        self._sequence = itertools.count()
        self._thread: Thread | None = None
        self._lifecycle_lock = Lock()
        self._activity_lock = Lock()
        self._active_commands = 0

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run,
                name="tapbot-robot-dispatcher",
                daemon=True,
            )
            self._thread.start()

    def submit(
        self,
        action: Action,
        *,
        timeout: float = 10.0,
        trace_id: str | None = None,
    ) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            raise RuntimeError("Robot command dispatcher is not running")

        if isinstance(action, EmergencyStopAction):
            # Never put STOP behind a currently running or queued motion. GRBL
            # controllers use this direct call to send realtime bytes.
            started_at = perf_counter()
            self._begin_command()
            try:
                self._executor.execute(action)
                self._event_log.add(
                    f"{type(self.controller).__name__} executed immediately: {action}",
                    event_type="robot.response",
                    category="robot",
                    status="success",
                    trace_id=trace_id,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    payload={"action": repr(action), "immediate": True},
                )
            finally:
                self._end_command()
            return

        priority = self._NORMAL_PRIORITY
        command = _QueuedAction(
            priority,
            next(self._sequence),
            action,
            trace_id=trace_id,
        )
        self._queue.put(command)
        if not command.completed.wait(timeout):
            raise TimeoutError(f"Robot action timed out: {action}")
        if command.error is not None:
            raise command.error

    def shutdown(self, *, timeout: float = 2.0) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return
            sentinel = _QueuedAction(
                self._SHUTDOWN_PRIORITY,
                next(self._sequence),
                EmergencyStopAction(),
                shutdown=True,
            )
            self._queue.put(sentinel)
            thread.join(timeout)
            self._thread = None

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def is_busy(self) -> bool:
        with self._activity_lock:
            return self._active_commands > 0 or self._queue.qsize() > 0

    def _begin_command(self) -> None:
        with self._activity_lock:
            self._active_commands += 1

    def _end_command(self) -> None:
        with self._activity_lock:
            self._active_commands -= 1

    def _run(self) -> None:
        while True:
            command = self._queue.get()
            try:
                if command.shutdown:
                    return
                self._begin_command()
                self._executor.execute(command.action)
                self._event_log.add(
                    f"{type(self.controller).__name__} executed: {command.action}",
                    event_type="robot.response",
                    category="robot",
                    status="success",
                    trace_id=command.trace_id,
                    latency_ms=(perf_counter() - command.submitted_at) * 1000,
                    payload={"action": repr(command.action)},
                )
            except BaseException as error:
                command.error = error
                self._event_log.add(
                    f"Robot execution error for {command.action}: {error}",
                    level="error",
                    event_type="robot.error",
                    category="robot",
                    status="error",
                    trace_id=command.trace_id,
                    latency_ms=(perf_counter() - command.submitted_at) * 1000,
                    payload={"action": repr(command.action), "error": str(error)},
                )
            finally:
                if not command.shutdown:
                    self._end_command()
                command.completed.set()
                self._queue.task_done()


@dataclass(frozen=True, slots=True)
class CameraFrameSnapshot:
    frame_id: int
    captured_at: str
    width: int
    height: int
    jpeg: bytes
    source_id: str | None = None
    source_metadata: dict[str, object] = field(default_factory=dict)


class CameraFrameWorker:
    """Capture and JPEG-encode frames away from FastAPI's event loop."""

    def __init__(
        self,
        camera: CameraSource,
        event_log: EventLog,
        *,
        fps: float = 20.0,
        encoder: Callable[[str, NDArray[np.uint8]], tuple[bool, NDArray[np.uint8]]] = cv2.imencode,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.camera = camera
        self._event_log = event_log
        self._frame_interval = 1 / fps
        self._encoder = encoder
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._frame: NDArray[np.uint8] | None = None
        self._snapshot: CameraFrameSnapshot | None = None
        self._frame_ids = itertools.count(1)
        self._frozen_frames: dict[int, NDArray[np.uint8]] = {}
        self._error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="tapbot-camera-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self.camera.close()
        self._thread = None

    def latest_frame(self) -> CameraFrameSnapshot | None:
        with self._lock:
            return self._snapshot

    def latest_bgr_frame(self) -> NDArray[np.uint8] | None:
        """Return a copy of the latest original BGR frame, if available."""

        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def freeze_latest_frame(self) -> CameraFrameSnapshot | None:
        """Pin the latest BGR frame for a later calibration preview."""

        with self._lock:
            if self._snapshot is None or self._frame is None:
                return None
            self._frozen_frames[self._snapshot.frame_id] = self._frame.copy()
            while len(self._frozen_frames) > 8:
                oldest_frame_id = next(iter(self._frozen_frames))
                del self._frozen_frames[oldest_frame_id]
            return self._snapshot

    def frozen_bgr_frame(self, frame_id: int) -> NDArray[np.uint8] | None:
        with self._lock:
            frame = self._frozen_frames.get(frame_id)
            return None if frame is None else frame.copy()

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def clear(self) -> None:
        """Discard frames and errors when the active source changes."""

        with self._lock:
            self._frame = None
            self._snapshot = None
            self._frozen_frames.clear()
            self._error = None

    def _run(self) -> None:
        try:
            self.camera.open()
            source_id = getattr(
                self.camera,
                "id",
                getattr(self.camera, "source", type(self.camera).__name__),
            )
            self._event_log.add(f"Camera opened: {source_id!r}")
            while not self._stop.is_set():
                iteration_started = perf_counter()
                try:
                    read_with_metadata = getattr(
                        self.camera,
                        "read_frame_with_metadata",
                        None,
                    )
                    if callable(read_with_metadata):
                        frame, frame_source_id, source_metadata = read_with_metadata()
                    else:
                        frame = self.camera.read_frame()
                        frame_source_id = str(
                            getattr(
                                self.camera,
                                "id",
                                getattr(
                                    self.camera,
                                    "source",
                                    type(self.camera).__name__,
                                ),
                            )
                        )
                        metadata_getter = getattr(self.camera, "get_metadata", None)
                        source_metadata = (
                            dict(metadata_getter())
                            if callable(metadata_getter)
                            else {}
                        )
                    success, encoded = self._encoder(".jpg", frame)
                    if not success:
                        raise CameraError("Failed to encode camera frame as JPEG")
                    height, width = frame.shape[:2]
                    snapshot = CameraFrameSnapshot(
                        frame_id=next(self._frame_ids),
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        width=width,
                        height=height,
                        jpeg=encoded.tobytes(),
                        source_id=frame_source_id,
                        source_metadata=dict(source_metadata),
                    )
                    with self._lock:
                        self._frame = frame.copy()
                        self._snapshot = snapshot
                        self._error = None
                    self._event_log.add(
                        f"Camera frame {snapshot.frame_id} captured",
                        level="debug",
                        event_type="camera.frame",
                        category="camera",
                        status="success",
                        trace_id=f"frame-{snapshot.frame_id}",
                        payload={
                            "frame_id": snapshot.frame_id,
                            "captured_at": snapshot.captured_at,
                            "width": width,
                            "height": height,
                            "source_id": frame_source_id,
                            "already_canonical": bool(
                                source_metadata.get("already_canonical", False)
                            ),
                        },
                    )
                except CameraError as error:
                    with self._lock:
                        self._error = str(error)
                    self._event_log.add(
                        f"Camera error: {error}",
                        level="error",
                        event_type="camera.error",
                        category="camera",
                        status="error",
                        payload={"error": str(error)},
                    )
                elapsed = perf_counter() - iteration_started
                self._stop.wait(max(0.0, self._frame_interval - elapsed))
        except CameraError as error:
            with self._lock:
                self._error = str(error)
            self._event_log.add(f"Camera open error: {error}", level="error")
        except Exception as error:
            with self._lock:
                self._error = str(error)
            self._event_log.add(f"Unexpected camera error: {error}", level="error")
        finally:
            self.camera.close()
