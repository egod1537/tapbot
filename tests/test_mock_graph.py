import json
from pathlib import Path
import time

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

from tapbot.camera.manager import CameraManager
from tapbot.camera.mock_graph import (
    MockGraphStateError,
    MockGraphValidationError,
    MockScreenGraph,
)
from tapbot.ui.app import create_app


def write_graph(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    for name, value in {
        "home": 25,
        "reservation": 125,
        "verify-photo": 225,
    }.items():
        image = np.full((12, 16, 3), value, dtype=np.uint8)
        assert cv2.imwrite(str(tmp_path / f"{name}.png"), image)

    document: dict[str, object] = {
        "schema_version": 1,
        "id": "test-flow",
        "name": "Test flow",
        "description": "Synthetic graph used by the unit test suite.",
        "screen_width": 16,
        "screen_height": 12,
        "initial_state": "home",
        "states": {
            "home": {
                "image": "home.png",
                "hotspots": [
                    {
                        "id": "open",
                        "label": "reservation_button",
                        "x": 2,
                        "y": 3,
                        "width": 5,
                        "height": 4,
                        "next_state": "reservation",
                    }
                ],
            },
            "reservation": {
                "image": "reservation.png",
                "hotspots": [
                    {
                        "id": "verify-photo",
                        "label": "verify_photo_button",
                        "x": 8,
                        "y": 3,
                        "width": 5,
                        "height": 4,
                        "next_state": "verify-photo",
                    }
                ],
            },
            "verify-photo": {
                "image": "verify-photo.png",
                "hotspots": [],
            },
        },
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, document


def test_graph_tap_transition_miss_and_reset(tmp_path: Path) -> None:
    path, _ = write_graph(tmp_path)
    events: list[tuple[str, dict[str, object]]] = []
    graph = MockScreenGraph.load(
        path,
        event_recorder=lambda event_type, payload: events.append(
            (event_type, dict(payload))
        ),
    )

    assert graph.initial_state == "home"
    assert graph.current_state == "home"
    assert graph.read_frame()[0, 0].tolist() == [25, 25, 25]
    assert [hotspot.id for hotspot in graph.available_hotspots] == ["open"]

    assert graph.tap(15, 11) is None
    assert graph.current_state == "home"
    assert graph.last_tap is not None
    assert graph.last_tap.hit is False
    assert graph.last_transition is None
    assert events[-1][0] == "mock.miss"

    transition = graph.tap(3, 4)

    assert transition is not None
    assert transition.from_state == "home"
    assert transition.to_state == "reservation"
    assert graph.current_state == "reservation"
    assert graph.read_frame()[0, 0].tolist() == [125, 125, 125]
    assert graph.last_tap is not None
    assert graph.last_tap.hotspot_id == "open"
    assert [event_type for event_type, _ in events[-2:]] == [
        "mock.hit",
        "mock.transition",
    ]
    assert events[-1][1]["label"] == "reservation_button"

    graph.transition("verify-photo")
    reset = graph.reset()

    assert reset.to_state == "home"
    assert reset.trigger == "reset"
    assert graph.current_state == "home"
    assert graph.last_tap is None
    assert events[-1][1]["trigger"] == "reset"


def test_transition_rejects_unknown_runtime_state(tmp_path: Path) -> None:
    path, _ = write_graph(tmp_path)
    graph = MockScreenGraph.load(path)

    with pytest.raises(MockGraphStateError, match="Unknown"):
        graph.transition("missing")

    assert graph.current_state == "home"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda document: document.update(initial_state="missing"),
            "initial_state references unknown",
        ),
        (
            lambda document: document["states"]["home"]["hotspots"][0].update(
                next_state="missing"
            ),
            "references unknown state",
        ),
        (
            lambda document: document["states"]["home"].update(image="missing.png"),
            "image does not exist",
        ),
        (
            lambda document: document["states"]["home"]["hotspots"][0].update(
                width=0
            ),
            "must be positive",
        ),
        (
            lambda document: document["states"]["home"]["hotspots"][0].update(
                x=15
            ),
            "must fit within",
        ),
        (
            lambda document: document.update(screen_width=17),
            "image must be 17x12",
        ),
        (
            lambda document: document["states"]["home"]["hotspots"][0].update(
                label="Not a target"
            ),
            "must match",
        ),
    ],
)
def test_loader_rejects_invalid_graph_references(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    path, document = write_graph(tmp_path)
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MockGraphValidationError, match=message):
        MockScreenGraph.load(path)


def test_robot_tap_advances_builtin_graph_and_records_event() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        initial_frame = None
        for _ in range(50):
            response = client.get("/api/camera/frame")
            if response.status_code == 200:
                initial_frame = response.content
                break
            time.sleep(0.01)
        tap_response = client.post("/api/robot/tap", json={"x": 640, "y": 540})
        status = client.get("/api/camera/status")
        changed_frame = None
        for _ in range(50):
            response = client.get("/api/camera/frame")
            if response.status_code == 200 and response.content != initial_frame:
                changed_frame = response.content
                break
            time.sleep(0.01)
        events = client.get("/api/logs").json()["entries"]

    assert initial_frame is not None
    assert changed_frame is not None
    assert tap_response.status_code == 200
    assert tap_response.json() == {"ok": True, "action": "TapAction"}
    assert status.json()["mock_graph"]["current_state"] == "reservation"
    simulation_entries = [
        event
        for event in events
        if event["event_type"]
        in {"action.tap", "mock.hit", "mock.miss", "mock.transition"}
    ]
    assert [event["event_type"] for event in simulation_entries] == [
        "action.tap",
        "mock.hit",
        "mock.transition",
    ]
    assert [event["category"] for event in simulation_entries] == [
        "robot",
        "camera",
        "camera",
    ]


def test_mock_graph_debug_api_supports_status_miss_transition_and_reset() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        initial = client.get("/api/mock-graph/status")
        home_frame = manager.read_frame()
        missed = client.post("/api/mock-graph/tap", json={"x": 0, "y": 0})
        transitioned = client.post(
            "/api/mock-graph/transition", json={"state_id": "reservation"}
        )
        reservation_frame = manager.read_frame()
        tapped = client.post(
            "/api/mock-graph/tap", json={"x": 640, "y": 540}
        )
        verify_photo_frame = manager.read_frame()
        reset = client.post("/api/mock-graph/reset")
        reset_frame = manager.read_frame()

    assert initial.status_code == 200
    assert initial.json()["current_state"] == "home"
    assert initial.json()["previous_state"] is None
    assert [state["id"] for state in initial.json()["states"]] == [
        "home",
        "reservation",
        "verify-photo",
    ]
    assert initial.json()["states"][0]["image"] == "home.png"
    assert len(initial.json()["edges"]) == 4

    assert missed.status_code == 200
    assert missed.json()["hit"] is False
    assert missed.json()["tap"]["hit"] is False
    assert missed.json()["status"]["current_state"] == "home"

    assert transitioned.status_code == 200
    assert transitioned.json()["transition"]["trigger"] == "manual"
    assert transitioned.json()["status"]["previous_state"] == "home"
    assert transitioned.json()["status"]["current_state"] == "reservation"
    assert not np.array_equal(home_frame, reservation_frame)

    assert tapped.status_code == 200
    assert tapped.json()["hit"] is True
    assert tapped.json()["transition"]["to_state"] == "verify-photo"
    assert tapped.json()["status"]["current_state"] == "verify-photo"
    assert not np.array_equal(reservation_frame, verify_photo_frame)

    assert reset.status_code == 200
    assert reset.json()["transition"]["trigger"] == "reset"
    assert reset.json()["status"]["current_state"] == "home"
    assert reset.json()["status"]["previous_state"] == "verify-photo"
    assert np.array_equal(home_frame, reset_frame)


def test_mock_graph_debug_api_rejects_invalid_manual_state() -> None:
    manager = CameraManager.with_defaults(
        "mock:reservation-flow", discovery_max_index=None
    )
    app = create_app(camera_manager=manager, camera_fps=30)

    with TestClient(app) as client:
        response = client.post(
            "/api/mock-graph/transition", json={"state_id": "missing"}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown mock screen state: missing"
