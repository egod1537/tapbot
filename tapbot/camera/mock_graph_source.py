"""Camera source backed by a validated mock screen graph."""

from __future__ import annotations

from pathlib import Path

from tapbot.camera.mock_graph import (
    MockEventRecorder,
    MockHotspot,
    MockScreenGraph,
    MockTap,
    MockTransition,
)
from tapbot.camera.scenario_registry import MockScenarioRegistry
from tapbot.camera.source import (
    BGRFrame,
    CameraMetadata,
    CameraNotOpenError,
    CameraSource,
    base_metadata,
)


class MockGraphCameraSource(CameraSource):
    """Return the image belonging to the graph's current screen state."""

    source_type = "mock_graph"

    def __init__(
        self,
        graph_id: str = "reservation-flow",
        *,
        name: str | None = None,
        fps: float = 5.0,
        already_canonical: bool = True,
        graph_path: str | Path | None = None,
        graph: MockScreenGraph | None = None,
        event_recorder: MockEventRecorder | None = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("Mock graph fps must be positive")
        if graph is not None and graph_path is not None:
            raise ValueError("Provide graph or graph_path, not both")
        self.graph_id = graph_id
        self.source = graph_id
        self.id = f"mock:{graph_id}"
        self.name = name or f"Mock Graph: {graph_id}"
        self.fps = fps
        self.already_canonical = already_canonical
        self.graph_path = (
            Path(graph_path)
            if graph_path
            else MockScenarioRegistry.default().get(graph_id).graph_path
        )
        self._graph = graph
        self._event_recorder = event_recorder
        if self._graph is not None:
            self._graph.set_event_recorder(event_recorder)
        self._opened = False

    def open(self) -> None:
        if self._opened:
            return
        if self._graph is None:
            self._graph = MockScreenGraph.load(
                self.graph_path,
                event_recorder=self._event_recorder,
            )
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_opened(self) -> bool:
        return self._opened

    def is_available(self) -> bool:
        return self._graph is not None or self.graph_path.is_file()

    def read_frame(self) -> BGRFrame:
        return self._require_graph().read_frame()

    def get_metadata(self) -> CameraMetadata:
        if self._graph is None:
            width = height = 0
            current_state: str | None = None
        else:
            frame = self._graph.read_frame()
            height, width = frame.shape[:2]
            current_state = self._graph.current_state
        metadata = base_metadata(
            name=self.name,
            source_type=self.source_type,
            width=width,
            height=height,
            fps=self.fps,
        )
        metadata.update(
            graph_id=self.graph_id,
            graph_path=str(self.graph_path),
            current_state=current_state,
            already_canonical=self.already_canonical,
        )
        return metadata

    @property
    def current_state(self) -> str:
        return self._require_graph().current_state

    @property
    def available_hotspots(self) -> tuple[MockHotspot, ...]:
        return self._require_graph().available_hotspots

    @property
    def last_tap(self) -> MockTap | None:
        return self._require_graph().last_tap

    @property
    def last_transition(self) -> MockTransition | None:
        return self._require_graph().last_transition

    def reset(self) -> MockTransition:
        return self._require_graph().reset()

    def transition(self, next_state: str) -> MockTransition:
        return self._require_graph().transition(next_state)

    def tap(self, x: float, y: float) -> MockTransition | None:
        return self._require_graph().tap(x, y)

    def status(self) -> dict[str, object]:
        return self._require_graph().status()

    def set_event_recorder(self, recorder: MockEventRecorder | None) -> None:
        self._event_recorder = recorder
        if self._graph is not None:
            self._graph.set_event_recorder(recorder)

    def _require_graph(self) -> MockScreenGraph:
        if not self._opened or self._graph is None:
            raise CameraNotOpenError(
                f"Camera source is not open: {self.id}; call open() first"
            )
        return self._graph
