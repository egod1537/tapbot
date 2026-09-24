from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import time
import json

import cv2
from fastapi.testclient import TestClient
import numpy as np

from tapbot.core.actions import EmergencyStopAction, MoveAction
from tapbot.model.client import MockModelClient
from tapbot.robot.mock import MockRobotController
from tapbot.robot.grbl import (
    GrblRobotConfig,
    GrblRobotController,
    GrblSession,
    GrblSessionConfig,
)
from tapbot.robot.transport import MockTransport
from tapbot.ui.app import WorkspaceBounds, create_app
from tapbot.ui.services import EventLog, RobotCommandDispatcher
from tapbot.vision.calibration import CalibrationStore


class FakeCamera:
    source = "fake-camera"

    def __init__(self) -> None:
        self.opened = False
        self.frame = np.full((8, 12, 3), 120, dtype=np.uint8)

    def open(self) -> None:
        self.opened = True

    def read_frame(self) -> np.ndarray:
        return self.frame

    def close(self) -> None:
        self.opened = False

    def is_opened(self) -> bool:
        return self.opened


def make_client() -> tuple[TestClient, MockRobotController]:
    robot = MockRobotController()
    app = create_app(robot=robot, camera=FakeCamera(), camera_fps=20)
    return TestClient(app), robot


def wait_for_camera(client: TestClient) -> object:
    for _ in range(50):
        response = client.get(
            "/api/camera/frame", headers={"Origin": "http://localhost:5173"}
        )
        if response.status_code == 200:
            return response
        time.sleep(0.01)
    raise AssertionError("camera frame was not produced")


def test_ui_page_contains_camera_controls_and_log() -> None:
    client, _ = make_client()
    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Camera Preview" in response.text
    assert "Robot Control" in response.text
    assert "data-command=\"tap\"" in response.text
    assert "Log" in response.text
    assert "Select 4 corners" in response.text
    assert "Save calibration" in response.text
    assert "vision-debug" in response.text


def test_manual_robot_commands_reach_mock_in_order() -> None:
    client, robot = make_client()
    with client:
        assert client.post("/api/robot/move", json={"x": 10, "y": 20}).status_code == 200
        response = client.post("/api/robot/tap", json={"x": 100, "y": 200})
        assert response.status_code == 200
        assert response.json() == {"ok": True, "action": "TapAction"}
        assert client.post("/api/robot/home").status_code == 200
        assert client.post("/api/robot/stop").status_code == 200

    assert robot.commands == [
        ("move_to", 10.0, 20.0),
        ("tap", 100.0, 200.0),
        ("home",),
        ("emergency_stop",),
    ]


def test_robot_status_and_pen_commands() -> None:
    client, robot = make_client()
    with client:
        initial = client.get("/api/robot/status")
        assert client.post("/api/robot/pen/down").status_code == 200
        assert client.post("/api/robot/pen/up").status_code == 200
        assert client.post("/api/robot/move", json={"x": 25, "y": 50}).status_code == 200
        moved = client.get("/api/robot/status")
        assert client.post("/api/robot/home").status_code == 200
        homed = client.get("/api/robot/status")

    assert initial.json() == {
        "connected": True,
        "busy": False,
        "homed": False,
        "mode": "MOCK",
        "position": {"x": 0.0, "y": 0.0},
        "pen": "unknown",
        "last_command": None,
        "workspace": {
            "min_x": 0,
            "max_x": 1000,
            "min_y": 0,
            "max_y": 1000,
        },
        "queue_depth": 0,
    }
    assert moved.json()["position"] == {"x": 25.0, "y": 50.0}
    assert homed.json()["homed"] is True
    assert homed.json()["position"] == {"x": 0.0, "y": 0.0}
    assert robot.commands == [
        ("pen_down",),
        ("pen_up",),
        ("move_to", 25.0, 50.0),
        ("home",),
    ]


def test_backend_rejects_coordinates_outside_workspace() -> None:
    robot = MockRobotController()
    app = create_app(
        robot=robot,
        camera=FakeCamera(),
        bounds=WorkspaceBounds(max_x=300, max_y=400),
    )
    with TestClient(app) as client:
        response = client.post("/api/robot/tap", json={"x": 301, "y": 200})

    assert response.status_code == 422
    assert "X must be between" in response.json()["detail"]
    assert robot.commands == []


def test_status_and_camera_frame_endpoints() -> None:
    client, _ = make_client()
    with client:
        status = client.get("/api/status")
        frame_response = wait_for_camera(client)

    assert status.status_code == 200
    assert status.json()["robot"] == "MockRobotController"
    assert status.json()["robot_mode"] == "MOCK"
    assert status.json()["robot_connected"] is True
    assert status.json()["model_provider"] == "mock"
    assert status.json()["model_connected"] is True
    assert status.json()["calibration_profile"] is None
    assert frame_response.headers["content-type"] == "image/jpeg"
    assert int(frame_response.headers["x-frame-id"]) >= 1
    assert frame_response.headers["x-frame-width"] == "12"
    assert frame_response.headers["x-frame-height"] == "8"
    assert frame_response.headers["cache-control"] == "no-store"
    assert "X-Frame-Id" in frame_response.headers["access-control-expose-headers"]
    decoded = cv2.imdecode(np.frombuffer(frame_response.content, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (8, 12, 3)


def test_ui_log_contains_user_action_and_execution_result() -> None:
    client, _ = make_client()
    with client:
        client.post("/api/robot/tap", json={"x": 100, "y": 200})
        entries = client.get("/api/logs").json()["entries"]

    messages = [entry["message"] for entry in entries]
    assert any("User command: tap(100.0, 200.0)" in message for message in messages)
    assert any("Action created: TapAction" in message for message in messages)
    assert any("MockRobotController executed: TapAction" in message for message in messages)


def test_sse_event_stream_correlates_robot_command_and_response() -> None:
    client, _ = make_client()
    with client:
        wait_for_camera(client)
        existing = client.get("/api/logs").json()["entries"]
        after_id = existing[-1]["id"] if existing else 0
        assert client.post("/api/robot/tap", json={"x": 100, "y": 200}).status_code == 200
        stream = client.get(
            f"/api/events/stream?after_id={after_id}&once=true",
            headers={"Accept": "text/event-stream"},
        )

    events = [
        json.loads(line.removeprefix("data: "))
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    event_types = [event["event_type"] for event in events]
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert event_types == [
        "action.request",
        "action.created",
        "robot.command",
        "robot.response",
    ]
    trace_ids = {event["trace_id"] for event in events}
    assert len(trace_ids) == 1
    assert next(iter(trace_ids)).startswith("manual-")
    assert events[-1]["status"] == "success"
    assert events[-1]["latency_ms"] >= 0
    assert events[-1]["payload"]["action"].startswith("TapAction")


class BlockingRobot(MockRobotController):
    def __init__(self) -> None:
        super().__init__()
        self.first_move_started = Event()
        self.release_first_move = Event()

    def move_to(self, x: float, y: float) -> None:
        if not self.first_move_started.is_set():
            self.first_move_started.set()
            self.release_first_move.wait(2)
        super().move_to(x, y)


def test_emergency_stop_jumps_ahead_of_queued_normal_commands() -> None:
    robot = BlockingRobot()
    dispatcher = RobotCommandDispatcher(robot, EventLog())
    dispatcher.start()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(dispatcher.submit, MoveAction(1, 1))
            assert robot.first_move_started.wait(1)
            second = pool.submit(dispatcher.submit, MoveAction(2, 2))
            stop = pool.submit(dispatcher.submit, EmergencyStopAction())
            for _ in range(100):
                if dispatcher.pending_count == 1:
                    break
                time.sleep(0.005)
            assert dispatcher.pending_count == 1
            stop.result(1)
            assert robot.commands == [("emergency_stop",)]
            robot.release_first_move.set()
            first.result(2)
            second.result(2)
    finally:
        dispatcher.shutdown()

    assert robot.commands == [
        ("emergency_stop",),
        ("move_to", 1.0, 1.0),
        ("move_to", 2.0, 2.0),
    ]


def calibration_payload() -> dict[str, object]:
    return {
        "profile_name": "test-phone",
        "camera_corners": [
            {"x": 0, "y": 0},
            {"x": 12, "y": 0},
            {"x": 12, "y": 8},
            {"x": 0, "y": 8},
        ],
        "robot_points": [
            {"x": 10, "y": 20},
            {"x": 210, "y": 20},
            {"x": 210, "y": 420},
            {"x": 10, "y": 420},
        ],
        "phone_width": 1000,
        "phone_height": 2000,
        "camera_width": 12,
        "camera_height": 8,
    }


def test_calibration_api_saves_and_transforms_camera_click(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path / "calibrations.json")
    app = create_app(camera=FakeCamera(), calibration_store=store)

    with TestClient(app) as client:
        saved = client.post("/api/calibration", json=calibration_payload())
        screen_center = client.post(
            "/api/calibration/screen-to-robot", json={"x": 500, "y": 1000}
        )
        camera_center = client.post(
            "/api/calibration/camera-to-robot", json={"x": 6, "y": 4}
        )

    assert saved.status_code == 200
    assert saved.json()["calibration"]["profile_name"] == "test-phone"
    assert screen_center.json()["robot"] == {"x": 110.0, "y": 220.0}
    assert camera_center.json()["screen"]["x"] == 500.0
    assert camera_center.json()["screen"]["y"] == 1000.0
    assert camera_center.json()["robot"] == {"x": 110.0, "y": 220.0}


def test_calibration_preview_validates_without_saving(tmp_path: Path) -> None:
    app = create_app(
        camera=FakeCamera(),
        camera_fps=20,
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )
    with TestClient(app) as client:
        wait_for_camera(client)
        frozen = client.post("/api/camera/freeze")
        payload = calibration_payload() | {
            "frame_id": int(frozen.headers["x-frame-id"])
        }
        preview = client.post("/api/calibration/preview", json=payload)
        profiles = client.get("/api/calibration/profiles")

    assert preview.status_code == 200
    assert frozen.headers["x-frame-frozen"] == "true"
    assert preview.headers["content-type"] == "image/jpeg"
    assert preview.headers["x-preview-width"] == "1000"
    assert preview.headers["x-preview-height"] == "2000"
    assert float(preview.headers["x-center-robot-x"]) == 110.0
    assert float(preview.headers["x-center-robot-y"]) == 220.0
    image = cv2.imdecode(np.frombuffer(preview.content, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (2000, 1000, 3)
    assert profiles.json() == {"profiles": [], "active_profile": None}


def test_existing_calibration_profile_can_be_activated(tmp_path: Path) -> None:
    app = create_app(
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )
    first = calibration_payload()
    second = calibration_payload() | {"profile_name": "second-phone"}
    with TestClient(app) as client:
        assert client.post("/api/calibration", json=first).status_code == 200
        assert client.post("/api/calibration", json=second).status_code == 200
        activated = client.post(
            "/api/calibration/activate", params={"profile": "test-phone"}
        )
        profiles = client.get("/api/calibration/profiles")

    assert activated.status_code == 200
    assert activated.json()["calibration"]["profile_name"] == "test-phone"
    assert profiles.json()["active_profile"] == "test-phone"


def test_calibration_api_rejects_out_of_bounds_point(tmp_path: Path) -> None:
    app = create_app(
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )
    with TestClient(app) as client:
        assert client.post("/api/calibration", json=calibration_payload()).status_code == 200
        response = client.post(
            "/api/calibration/screen-to-robot", json={"x": 1001, "y": 1000}
        )

    assert response.status_code == 422
    assert "outside the phone screen" in response.json()["detail"]


def test_saved_calibration_is_loaded_after_app_restart(tmp_path: Path) -> None:
    store = CalibrationStore(tmp_path / "calibrations.json")
    first_app = create_app(camera=FakeCamera(), calibration_store=store)
    with TestClient(first_app) as client:
        client.post("/api/calibration", json=calibration_payload())

    second_app = create_app(camera=FakeCamera(), calibration_store=store)
    with TestClient(second_app) as client:
        loaded = client.get("/api/calibration")
        transformed = client.post(
            "/api/calibration/screen-to-robot", json={"x": 500, "y": 1000}
        )

    assert loaded.json()["configured"] is True
    assert loaded.json()["calibration"]["profile_name"] == "test-phone"
    assert transformed.json()["robot"] == {"x": 110.0, "y": 220.0}


class GreenButtonCamera(FakeCamera):
    def __init__(self) -> None:
        super().__init__()
        self.frame = np.zeros((80, 120, 3), dtype=np.uint8)
        self.frame[30:50, 40:80] = (0, 255, 0)


def test_vision_detections_and_debug_overlay_are_available_in_ui(
    tmp_path: Path,
) -> None:
    app = create_app(
        camera=GreenButtonCamera(),
        camera_fps=20,
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )
    payload = {
        "profile_name": "vision-ui-test",
        "camera_corners": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "robot_points": [
            {"x": 10, "y": 20},
            {"x": 210, "y": 20},
            {"x": 210, "y": 120},
            {"x": 10, "y": 120},
        ],
        "phone_width": 120,
        "phone_height": 80,
        "camera_width": 120,
        "camera_height": 80,
    }

    with TestClient(app) as client:
        wait_for_camera(client)
        assert client.post("/api/calibration", json=payload).status_code == 200
        detections = client.get("/api/vision/detections")
        debug = client.get("/api/vision/debug")

    assert detections.status_code == 200
    values = detections.json()["detections"]
    assert len(values) == 1
    assert values[0]["label"] == "green_button"
    assert values[0]["center"] == {"x": 60.0, "y": 40.0}
    assert debug.status_code == 200
    assert debug.headers["content-type"] == "image/jpeg"
    overlay = cv2.imdecode(np.frombuffer(debug.content, np.uint8), cv2.IMREAD_COLOR)
    assert overlay.shape == (80, 120, 3)


def test_vision_saved_frame_can_be_filtered_and_replayed(tmp_path: Path) -> None:
    app = create_app(
        camera=GreenButtonCamera(),
        camera_fps=20,
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )
    calibration = {
        "profile_name": "vision-replay-test",
        "camera_corners": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "robot_points": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "phone_width": 120,
        "phone_height": 80,
        "camera_width": 120,
        "camera_height": 80,
    }

    with TestClient(app) as client:
        wait_for_camera(client)
        assert client.post("/api/calibration", json=calibration).status_code == 200
        capabilities = client.get("/api/vision/capabilities")
        saved = client.post("/api/vision/frames")
        frame_id = saved.json()["frame"]["frame_id"]
        result = client.post(
            "/api/vision/run",
            json={
                "frame_id": frame_id,
                "detector_types": ["opencv_color_contour"],
                "confidence_threshold": 0.5,
            },
        )
        filtered = client.post(
            "/api/vision/run",
            json={"frame_id": frame_id, "confidence_threshold": 1.0},
        )
        frames = client.get("/api/vision/frames")
        raw = client.get(f"/api/vision/frames/{frame_id}/raw")
        rectified = client.get(
            f"/api/vision/results/{result.json()['result_id']}/rectified"
        )
        unknown = client.post(
            "/api/vision/run",
            json={"frame_id": frame_id, "detector_types": ["not-installed"]},
        )

    assert capabilities.json()["detectors"] == [
        {"type": "opencv_color_contour", "name": "ColorButtonDetector"}
    ]
    assert saved.status_code == 200
    assert saved.json()["frame"]["width"] == 120
    assert frames.json()["frames"][0]["frame_id"] == frame_id
    assert result.status_code == 200
    assert result.json()["rectified"] == {"width": 120, "height": 80}
    assert result.json()["detections"][0]["detector_name"] == "ColorButtonDetector"
    assert filtered.json()["detections"] == []
    assert raw.headers["content-type"] == "image/jpeg"
    assert rectified.headers["content-type"] == "image/jpeg"
    assert unknown.status_code == 422
    assert "Unknown detector types" in unknown.json()["detail"]


def test_model_debug_traces_decision_gates_without_executing_robot(
    tmp_path: Path,
) -> None:
    robot = MockRobotController()
    model = MockModelClient(
        {
            "state": "confirmation_visible",
            "action": "tap_target",
            "target": "green_button",
            "confidence": 0.94,
            "reason": "The confirmation button is visible.",
        },
        provider="local-test",
        model_name="tapbot-vlm-test",
    )
    app = create_app(
        robot=robot,
        camera=GreenButtonCamera(),
        camera_fps=20,
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
        model_client=model,
    )
    calibration = {
        "profile_name": "model-debug-test",
        "camera_corners": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "robot_points": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "phone_width": 120,
        "phone_height": 80,
        "camera_width": 120,
        "camera_height": 80,
    }

    with TestClient(app) as client:
        wait_for_camera(client)
        assert client.post("/api/calibration", json=calibration).status_code == 200
        before = client.get("/api/model/status")
        response = client.post(
            "/api/model/run",
            json={"context": {"workflow": "reservation"}},
        )
        input_image = client.get(
            f"/api/model/runs/{response.json()['run_id']}/input"
        )
        after = client.get("/api/model/status")
        timeline = client.get("/api/logs").json()["entries"]

    value = response.json()
    assert before.json()["provider"] == "local-test"
    assert before.json()["model_name"] == "tapbot-vlm-test"
    assert before.json()["last_latency_ms"] is None
    assert response.status_code == 200
    assert value["decision"]["target"] == "green_button"
    assert value["raw_response"]["confidence"] == 0.94
    assert value["context"]["workflow"] == "reservation"
    assert value["context"]["detections"][0]["label"] == "green_button"
    assert value["resolved_target"] == {
        "name": "green_button",
        "center": {"x": 60.0, "y": 40.0},
        "source": "detection",
    }
    assert value["resolved_action"] == {
        "type": "TapAction",
        "parameters": {"x": 60.0, "y": 40.0},
    }
    assert all(gate["passed"] for gate in value["gates"].values())
    assert value["execution"] == {
        "allowed": True,
        "requested": False,
        "executed": False,
        "reason": "Action passed all gates, but Model Debug never executes robot actions",
    }
    assert robot.commands == []
    assert input_image.headers["content-type"] == "image/jpeg"
    assert after.json()["last_latency_ms"] >= 0
    trace_id = f"frame-{value['frame']['frame_id']}"
    trace_events = [
        event["event_type"] for event in timeline if event["trace_id"] == trace_id
    ]
    assert "camera.frame" in trace_events
    assert "vision.detected" in trace_events
    assert trace_events[-3:] == ["model.request", "model.decision", "action.created"]


def test_model_debug_preserves_invalid_raw_response_and_blocks_action(
    tmp_path: Path,
) -> None:
    robot = MockRobotController()
    invalid_response = {
        "state": "unsafe",
        "action": "tap_target",
        "target": "green_button",
        "confidence": 0.99,
        "reason": "Contains a forbidden executable field.",
        "gcode": "G1 X999 Y999",
    }
    app = create_app(
        robot=robot,
        camera=GreenButtonCamera(),
        camera_fps=20,
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
        model_client=MockModelClient(invalid_response),
    )
    calibration = {
        "profile_name": "invalid-model-debug-test",
        "camera_corners": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "robot_points": [
            {"x": 0, "y": 0},
            {"x": 120, "y": 0},
            {"x": 120, "y": 80},
            {"x": 0, "y": 80},
        ],
        "phone_width": 120,
        "phone_height": 80,
        "camera_width": 120,
        "camera_height": 80,
    }

    with TestClient(app) as client:
        wait_for_camera(client)
        assert client.post("/api/calibration", json=calibration).status_code == 200
        response = client.post("/api/model/run", json={})

    value = response.json()
    assert response.status_code == 200
    assert value["status"] == "invalid_model_output"
    assert value["raw_response"] == invalid_response
    assert value["decision"] is None
    assert value["gates"]["schema_valid"]["passed"] is False
    assert value["gates"]["action_created"]["passed"] is False
    assert value["execution"]["allowed"] is False
    assert value["execution"]["executed"] is False
    assert "forbidden fields" in value["error"]
    assert robot.commands == []


def test_ui_can_use_dry_run_grbl_controller(tmp_path: Path) -> None:
    robot = GrblRobotController(
        None,
        GrblRobotConfig(
            feed_rate_mm_per_min=500,
            tap_dwell_ms=100,
            dry_run=True,
        ),
    )
    app = create_app(
        robot=robot,
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )

    with TestClient(app) as client:
        status = client.get("/api/status")
        tapped = client.post("/api/robot/tap", json={"x": 100, "y": 200})
        stopped = client.post("/api/robot/stop")

    assert status.json()["robot"] == "GrblRobotController"
    assert status.json()["robot_connected"] is True
    assert tapped.status_code == 200
    assert stopped.status_code == 200
    assert robot.generated_commands == [
        "G90",
        "G1 X100 Y200 F500",
        "M3",
        "G4 P0.1",
        "M5",
        "!",
        "<CTRL-X>",
    ]


def test_gcode_console_uses_mock_transport_and_backend_capabilities(
    tmp_path: Path,
) -> None:
    transport = MockTransport(
        ["<Idle|MPos:0,0,0>", "$0=10", "$1=25", "ok"],
    )
    robot = GrblRobotController(
        GrblSession(
            transport,
            GrblSessionConfig(wakeup_delay_s=0, command_timeout_s=0.1),
        )
    )
    app = create_app(
        robot=robot,
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )

    with TestClient(app) as client:
        capabilities = client.get("/api/gcode/capabilities")
        response = client.post("/api/gcode/command", json={"command": "$$"})

    assert capabilities.status_code == 200
    assert capabilities.json()["available"] is True
    assert capabilities.json()["mode"] == "MOCK"
    assert {item["command"] for item in capabilities.json()["presets"]} >= {
        "?",
        "$$",
        "$H",
    }
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "command": "$$",
        "response": ["$0=10", "$1=25", "ok"],
        "mode": "MOCK",
    }
    assert transport.sent_lines == ["$$"]


def test_gcode_console_rejects_unsupported_and_out_of_bounds_commands(
    tmp_path: Path,
) -> None:
    robot = GrblRobotController(
        None,
        GrblRobotConfig(
            workspace_width_mm=300,
            workspace_height_mm=200,
            dry_run=True,
        ),
    )
    app = create_app(
        robot=robot,
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )

    with TestClient(app) as client:
        valid = client.post(
            "/api/gcode/command", json={"command": "G1 X10 Y20 F500"}
        )
        outside = client.post(
            "/api/gcode/command", json={"command": "G1 X301 Y20"}
        )
        forbidden = client.post(
            "/api/gcode/command", json={"command": "$RST=*"}
        )

    assert valid.status_code == 200
    assert valid.json()["response"][-1] == "ok"
    assert outside.status_code == 422
    assert "X must be between" in outside.json()["detail"]
    assert forbidden.status_code == 422
    assert robot.generated_commands == ["G90", "G1 X10 Y20 F500"]


def test_grbl_device_error_is_returned_and_recorded_in_backend_log(
    tmp_path: Path,
) -> None:
    transport = MockTransport(["<Idle|MPos:0,0,0>", "error:2"])
    session = GrblSession(
        transport,
        GrblSessionConfig(wakeup_delay_s=0, command_timeout_s=0.1),
    )
    robot = GrblRobotController(session)
    app = create_app(
        robot=robot,
        camera=FakeCamera(),
        calibration_store=CalibrationStore(tmp_path / "calibrations.json"),
    )

    with TestClient(app) as client:
        response = client.post("/api/robot/move", json={"x": 10, "y": 20})
        logs = client.get("/api/logs").json()["entries"]

    assert response.status_code == 500
    assert "GRBL rejected" in response.json()["detail"]
    assert any(
        "Robot execution error" in entry["message"] and "error:2" in entry["message"]
        for entry in logs
    )
