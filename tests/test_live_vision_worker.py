from __future__ import annotations

from threading import Event, Lock
import time

import numpy as np

from tapbot.ui.services import (
    CameraFrameSnapshot,
    CameraFrameWorker,
    EventLog,
    ScreenPipelineWorker,
)


def wait_until(predicate: object, *, timeout: float = 1.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(predicate) and predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


class SnapshotFeed:
    def __init__(self) -> None:
        self._lock = Lock()
        self._value: tuple[CameraFrameSnapshot, np.ndarray] | None = None

    def set(self, frame_id: int, source_id: str = "camera:a") -> None:
        snapshot = CameraFrameSnapshot(
            frame_id=frame_id,
            captured_at="2026-09-24T00:00:00+00:00",
            width=8,
            height=6,
            jpeg=b"jpeg",
            source_id=source_id,
            source_metadata={},
        )
        frame = np.full((6, 8, 3), frame_id, dtype=np.uint8)
        with self._lock:
            self._value = snapshot, frame

    def latest_frame_with_bgr(
        self,
    ) -> tuple[CameraFrameSnapshot, np.ndarray] | None:
        with self._lock:
            if self._value is None:
                return None
            snapshot, frame = self._value
            return snapshot, frame.copy()


class CountingCamera:
    id = "camera:counting"

    def __init__(self) -> None:
        self.opened = False
        self.count = 0

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_opened(self) -> bool:
        return self.opened

    def read_frame(self) -> np.ndarray:
        self.count += 1
        return np.full((8, 12, 3), self.count % 255, dtype=np.uint8)

    def get_metadata(self) -> dict[str, object]:
        return {"already_canonical": False}


def test_worker_drops_intermediate_frames_and_never_reprocesses_duplicate() -> None:
    feed = SnapshotFeed()
    feed.set(1)
    first_started = Event()
    release_first = Event()
    processed: list[int] = []

    def process(snapshot: CameraFrameSnapshot, _: np.ndarray) -> dict[str, object]:
        processed.append(snapshot.frame_id)
        if snapshot.frame_id == 1:
            first_started.set()
            assert release_first.wait(1)
        return {"frame_id": snapshot.frame_id, "failure_stage": None, "error": None}

    worker = ScreenPipelineWorker(
        feed,  # type: ignore[arg-type]
        process,
        EventLog(),
        target_fps=100,
    )
    worker.start()
    try:
        assert first_started.wait(1)
        feed.set(2)
        feed.set(3)
        feed.set(4)
        release_first.set()
        wait_until(lambda: len(processed) >= 2)
        assert processed[:2] == [1, 4]
        duplicate_count = len(processed)
        time.sleep(0.05)
        assert len(processed) == duplicate_count
        assert worker.status()["dropped_frames"] == 2
    finally:
        release_first.set()
        worker.stop()


def test_invalidation_rejects_in_flight_old_source_result() -> None:
    feed = SnapshotFeed()
    feed.set(1, "camera:old")
    old_started = Event()
    release_old = Event()

    def process(snapshot: CameraFrameSnapshot, _: np.ndarray) -> dict[str, object]:
        if snapshot.source_id == "camera:old":
            old_started.set()
            assert release_old.wait(1)
        return {"frame_id": snapshot.frame_id, "failure_stage": None, "error": None}

    worker = ScreenPipelineWorker(
        feed,  # type: ignore[arg-type]
        process,
        EventLog(),
        target_fps=100,
    )
    worker.start()
    try:
        assert old_started.wait(1)
        worker.invalidate()
        feed.set(2, "camera:new")
        release_old.set()
        wait_until(
            lambda: worker.latest_result() is not None
            and worker.latest_result().source_id == "camera:new"  # type: ignore[union-attr]
        )
        result = worker.latest_result()
        assert result is not None
        assert result.frame_id == 2
        assert result.source_id == "camera:new"
    finally:
        release_old.set()
        worker.stop()


def test_worker_can_be_disabled_and_reenabled_without_backlog() -> None:
    feed = SnapshotFeed()
    feed.set(1)
    processed: list[int] = []

    def process(snapshot: CameraFrameSnapshot, _: np.ndarray) -> dict[str, object]:
        processed.append(snapshot.frame_id)
        return {"frame_id": snapshot.frame_id, "failure_stage": None, "error": None}

    worker = ScreenPipelineWorker(
        feed,  # type: ignore[arg-type]
        process,
        EventLog(),
        enabled=False,
        target_fps=100,
    )
    worker.start()
    try:
        time.sleep(0.04)
        assert processed == []
        worker.enable()
        wait_until(lambda: processed == [1])
        worker.disable()
        feed.set(2)
        time.sleep(0.04)
        assert processed == [1]
        worker.enable()
        wait_until(lambda: processed == [1, 2])
    finally:
        worker.stop()


def test_slow_vision_does_not_pause_camera_capture() -> None:
    event_log = EventLog()
    camera_worker = CameraFrameWorker(CountingCamera(), event_log, fps=60)
    inference_started = Event()
    release_inference = Event()

    def process(snapshot: CameraFrameSnapshot, _: np.ndarray) -> dict[str, object]:
        inference_started.set()
        assert release_inference.wait(1)
        return {"frame_id": snapshot.frame_id, "failure_stage": None, "error": None}

    vision_worker = ScreenPipelineWorker(
        camera_worker,
        process,
        event_log,
        target_fps=30,
    )
    camera_worker.start()
    vision_worker.start()
    try:
        assert inference_started.wait(1)
        first = camera_worker.latest_frame()
        assert first is not None
        wait_until(
            lambda: camera_worker.latest_frame() is not None
            and camera_worker.latest_frame().frame_id >= first.frame_id + 3  # type: ignore[union-attr]
        )
        latest = camera_worker.latest_frame()
        assert latest is not None
        assert latest.frame_id > first.frame_id
    finally:
        release_inference.set()
        vision_worker.stop()
        camera_worker.stop()
