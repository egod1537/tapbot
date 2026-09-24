from pathlib import Path

import cv2
import numpy as np

from tapbot.camera.manager import CameraManager
from tapbot.core.actions import TapAction
from tapbot.core.executor import ActionExecutor
from tapbot.robot.mock import MockRobotController
from tapbot.simulation import SimulationBridge


def test_mock_robot_taps_drive_complete_camera_graph_loop() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    robot = MockRobotController()
    executor = ActionExecutor(robot)
    events: list[tuple[str, dict[str, object]]] = []
    bridge = SimulationBridge(
        robot,
        manager,
        event_recorder=lambda event_type, payload: events.append(
            (event_type, dict(payload))
        ),
    )

    with bridge:
        home_frame = manager.read_frame()
        executor.execute(TapAction(640, 540))
        reservation_frame = manager.read_frame()
        assert manager.status()["mock_graph"]["current_state"] == "reservation"

        executor.execute(TapAction(640, 540))
        verify_photo_frame = manager.read_frame()
        assert manager.status()["mock_graph"]["current_state"] == "verify-photo"

    assert not np.array_equal(home_frame, reservation_frame)
    assert not np.array_equal(reservation_frame, verify_photo_frame)
    assert [event_type for event_type, _ in events] == [
        "action.tap",
        "mock.hit",
        "mock.transition",
        "action.tap",
        "mock.hit",
        "mock.transition",
    ]
    assert events[2][1]["from_state"] == "home"
    assert events[2][1]["to_state"] == "reservation"
    assert events[5][1]["from_state"] == "reservation"
    assert events[5][1]["to_state"] == "verify-photo"


def test_bridge_records_miss_without_changing_the_frame() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    robot = MockRobotController()
    events: list[str] = []

    with SimulationBridge(
        robot,
        manager,
        event_recorder=lambda event_type, _: events.append(event_type),
    ):
        before = manager.read_frame()
        robot.tap(0, 0)
        after = manager.read_frame()

    assert np.array_equal(before, after)
    assert manager.status()["mock_graph"]["current_state"] == "home"
    assert events == ["action.tap", "mock.miss"]


def test_bridge_ignores_non_mock_camera_source(tmp_path: Path) -> None:
    image_path = tmp_path / "still.png"
    assert cv2.imwrite(
        str(image_path), np.full((12, 16, 3), 80, dtype=np.uint8)
    )
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    image_id = manager.register_image(image_path)
    manager.select(image_id)
    robot = MockRobotController()
    events: list[tuple[str, dict[str, object]]] = []

    with SimulationBridge(
        robot,
        manager,
        event_recorder=lambda event_type, payload: events.append(
            (event_type, dict(payload))
        ),
    ):
        robot.tap(640, 540)

    assert [event_type for event_type, _ in events] == ["action.tap"]
    assert events[0][1]["processed"] is False


def test_bridge_accepts_robot_to_screen_coordinate_mapper() -> None:
    class FixedMapper:
        def robot_to_screen(self, x: float, y: float) -> tuple[float, float]:
            assert (x, y) == (10, 20)
            return 640, 540

    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    robot = MockRobotController()

    with SimulationBridge(robot, manager, coordinate_mapper=FixedMapper()):
        robot.tap(10, 20)

    assert manager.status()["mock_graph"]["current_state"] == "reservation"
