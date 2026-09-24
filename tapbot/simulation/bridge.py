"""Connect mock robot tap events to the active mock screen camera."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Protocol

from tapbot.camera.manager import CameraManager
from tapbot.camera.mock_graph import MockEventRecorder
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.camera.source import CameraError
from tapbot.robot.mock import MockRobotController, Unsubscribe


class CoordinateMapper(Protocol):
    """Map robot coordinates into mock-screen coordinates."""

    def robot_to_screen(self, x: float, y: float) -> tuple[float, float]: ...


@dataclass(frozen=True, slots=True)
class IdentityCoordinateMapper:
    """Use robot coordinates as screen coordinates in simulation mode."""

    def robot_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x, y


class SimulationBridge:
    """Forward mock robot taps only to an active mock-graph camera source."""

    def __init__(
        self,
        robot: MockRobotController,
        camera_manager: CameraManager,
        *,
        coordinate_mapper: CoordinateMapper | None = None,
        event_recorder: MockEventRecorder | None = None,
    ) -> None:
        self._robot = robot
        self._camera_manager = camera_manager
        self._coordinate_mapper = coordinate_mapper or IdentityCoordinateMapper()
        self._event_recorder = event_recorder
        self._unsubscribe: Unsubscribe | None = None
        self._lock = RLock()

    def start(self) -> None:
        """Attach the bridge. Calling this method repeatedly is safe."""

        with self._lock:
            if self._unsubscribe is not None:
                return
            self._camera_manager.set_event_recorder(self._record_event)
            self._unsubscribe = self._robot.add_tap_listener(self._on_robot_tap)

    def close(self) -> None:
        """Detach the robot listener and graph event sink."""

        with self._lock:
            unsubscribe = self._unsubscribe
            self._unsubscribe = None
        if unsubscribe is not None:
            unsubscribe()
        self._camera_manager.set_event_recorder(None)

    def __enter__(self) -> SimulationBridge:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _on_robot_tap(self, robot_x: float, robot_y: float) -> None:
        try:
            source = self._camera_manager.current_source()
        except CameraError:
            source = None

        active_mock_graph = isinstance(source, MockGraphCameraSource)
        screen_point = (
            self._coordinate_mapper.robot_to_screen(robot_x, robot_y)
            if active_mock_graph
            else (None, None)
        )
        screen_x, screen_y = screen_point
        self._record_event(
            "action.tap",
            {
                "robot_x": robot_x,
                "robot_y": robot_y,
                "screen_x": screen_x,
                "screen_y": screen_y,
                "source_id": None if source is None else source.id,
                "processed": active_mock_graph,
            },
        )
        if active_mock_graph:
            # CameraManager serializes this with frame reads and source switches.
            assert screen_x is not None and screen_y is not None
            self._camera_manager.tap(screen_x, screen_y)

    def _record_event(
        self, event_type: str, payload: Mapping[str, object]
    ) -> None:
        recorder = self._event_recorder
        if recorder is not None:
            recorder(event_type, payload)
