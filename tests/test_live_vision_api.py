import time

from fastapi.testclient import TestClient
import numpy as np

from tapbot.ui.app import create_app


class AlreadyCanonicalCamera:
    id = "mock:canonical-test"
    source = id

    def __init__(self) -> None:
        self.opened = False
        self.counter = 0

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_opened(self) -> bool:
        return self.opened

    def read_frame(self) -> np.ndarray:
        self.counter += 1
        frame = np.zeros((60, 40, 3), dtype=np.uint8)
        frame[15:35, 10:30] = (0, 255, 0)
        return frame

    def get_metadata(self) -> dict[str, object]:
        return {
            "already_canonical": True,
            "type": "mock_graph",
            "name": "Canonical Test",
        }


class FailIfCalledObjectDetector:
    def detect(self, _: np.ndarray) -> object:
        raise AssertionError("already-canonical sources must skip object detection")


def wait_for_live_result(client: TestClient) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get("/api/vision/live/result")
        if response.status_code == 200:
            return response.json()
        assert response.status_code == 404
        time.sleep(0.01)
    raise AssertionError("live vision result was not produced")


def test_live_vision_api_processes_already_canonical_source_and_controls_worker() -> None:
    app = create_app(
        camera=AlreadyCanonicalCamera(),
        camera_fps=60,
        phone_object_detector=FailIfCalledObjectDetector(),  # type: ignore[arg-type]
        live_detection_enabled=True,
        live_detection_target_fps=30,
    )

    with TestClient(app) as client:
        result_wrapper = wait_for_live_result(client)
        result = result_wrapper["result"]
        assert isinstance(result, dict)
        assert result_wrapper["source_id"] == "mock:canonical-test"
        assert result_wrapper["frame_id"] == result["frame_id"]
        assert result["already_canonical"] is True
        assert result["phone_detection"]["source"] == "already_canonical"
        assert result["canonical"]["transform_skipped"] is True
        assert result["canonical"]["width"] == 40
        assert result["canonical"]["height"] == 60

        canonical = client.get("/api/vision/live/canonical")
        assert canonical.status_code == 200
        assert canonical.headers["content-type"] == "image/jpeg"

        status = client.get("/api/vision/live/status").json()
        assert status["enabled"] is True
        assert status["target_fps"] == 30
        assert status["last_result_frame_id"] == result_wrapper["frame_id"]

        stopped = client.post("/api/vision/live/stop").json()
        assert stopped["enabled"] is False
        started = client.post("/api/vision/live/start").json()
        assert started["enabled"] is True
