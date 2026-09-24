"""Physical-device discovery and active camera source management."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from tapbot.camera.descriptors import CameraSourceDescriptor
from tapbot.camera.image_source import ImageCameraSource
from tapbot.camera.mock_graph import MockEventRecorder, MockTransition
from tapbot.camera.mock_graph_source import MockGraphCameraSource
from tapbot.camera.opencv_source import OpenCVCameraSource, create_opencv_capture
from tapbot.camera.scenario_registry import MockScenarioRegistry
from tapbot.camera.source import (
    BGRFrame,
    CameraError,
    CameraMetadata,
    CameraNotOpenError,
    CameraOpenError,
    CameraSource,
    CameraSourceType,
    base_metadata,
)
from tapbot.camera.video_source import VideoCameraSource


CameraSourceFactory = Callable[[], CameraSource]
PhysicalCaptureFactory = Callable[[int], object]


class CameraSourceNotFoundError(CameraError):
    """Raised when a source ID is not registered."""


@dataclass(frozen=True, slots=True)
class _Registration:
    descriptor: CameraSourceDescriptor
    factory: CameraSourceFactory


class CameraManager(CameraSource):
    """Discover sources and safely delegate to one active implementation.

    The manager is itself a ``CameraSource``. The frame worker and vision code
    therefore keep one stable dependency while physical, file, and generated
    sources are selected at runtime. All active-source operations share one
    lock so a read cannot overlap close/open during a hot-swap.
    """

    def __init__(
        self,
        *,
        discovery_max_index: int | None = 4,
        capture_factory: PhysicalCaptureFactory = create_opencv_capture,
        scenario_registry: MockScenarioRegistry | None = None,
    ) -> None:
        if discovery_max_index is not None and discovery_max_index < 0:
            raise ValueError("discovery_max_index must be non-negative")
        self._discovery_max_index = discovery_max_index
        self._capture_factory = capture_factory
        self._scenario_registry = scenario_registry or MockScenarioRegistry.default()
        self._registrations: dict[str, _Registration] = {}
        self._discovered_physical_ids: set[str] = set()
        self._discovery_completed = False
        self._active: CameraSource | None = None
        self._last_error: str | None = None
        self._event_recorder: MockEventRecorder | None = None
        self._lock = RLock()

    @classmethod
    def with_defaults(
        cls,
        initial_source: int | str = "mock:reservation-flow",
        *,
        discovery_max_index: int | None = 4,
        capture_factory: PhysicalCaptureFactory = create_opencv_capture,
        scenario_registry: MockScenarioRegistry | None = None,
    ) -> CameraManager:
        """Create a manager with the built-in mock registry.

        Physical discovery is lazy and runs on the first ``list_sources`` call.
        An explicitly requested physical ID is registered immediately so CLI
        startup can fail clearly if that configured device cannot be opened.
        """

        manager = cls(
            discovery_max_index=discovery_max_index,
            capture_factory=capture_factory,
            scenario_registry=scenario_registry,
        )
        manager.register_fixture_scenarios()
        source_id = manager._register_configured_source(initial_source)
        manager.select(source_id)
        return manager

    def register(
        self,
        descriptor: CameraSourceDescriptor,
        factory: CameraSourceFactory,
        *,
        replace: bool = False,
    ) -> None:
        if not descriptor.id:
            raise ValueError("Camera source ID must not be empty")
        with self._lock:
            if descriptor.id in self._registrations and not replace:
                raise ValueError(
                    f"Camera source is already registered: {descriptor.id}"
                )
            if self._active is not None and self._active.id == descriptor.id:
                raise ValueError(f"Cannot replace the active source: {descriptor.id}")
            self._registrations[descriptor.id] = _Registration(descriptor, factory)

    def discover_physical_sources(
        self, *, force: bool = False
    ) -> list[CameraSourceDescriptor]:
        """Probe OpenCV indexes ``0..N`` and register successful devices."""

        with self._lock:
            if self._discovery_completed and not force:
                return self._physical_descriptors()
            if self._discovery_max_index is None:
                self._discovery_completed = True
                return self._physical_descriptors()

            available_ids: set[str] = set()
            for device_index in range(self._discovery_max_index + 1):
                source_id = f"opencv:{device_index}"
                probe = OpenCVCameraSource(
                    device_index,
                    name=f"Camera {device_index}",
                    capture_factory=self._capture_factory,
                )
                try:
                    available = probe.is_available()
                except Exception:
                    available = False
                if not available:
                    continue
                available_ids.add(source_id)
                if source_id not in self._registrations:
                    self.register_opencv(device_index, name=f"Camera {device_index}")

            if force:
                disappeared = self._discovered_physical_ids - available_ids
                for source_id in disappeared:
                    registration = self._registrations.get(source_id)
                    if registration is None:
                        continue
                    if self._active is not None and self._active.id == source_id:
                        self._registrations[source_id] = _Registration(
                            CameraSourceDescriptor(
                                id=registration.descriptor.id,
                                name=registration.descriptor.name,
                                type="physical",
                                available=False,
                                metadata=dict(registration.descriptor.metadata),
                            ),
                            registration.factory,
                        )
                    else:
                        del self._registrations[source_id]

            self._discovered_physical_ids = available_ids
            self._discovery_completed = True
            return self._physical_descriptors()

    def register_opencv(self, device_index: int, *, name: str | None = None) -> str:
        source_id = f"opencv:{device_index}"
        source_name = name or f"Camera {device_index}"
        self.register(
            CameraSourceDescriptor(
                id=source_id,
                name=source_name,
                type="physical",
                available=True,
                metadata=base_metadata(
                    name=source_name,
                    source_type="physical",
                    width=0,
                    height=0,
                    fps=0.0,
                ),
            ),
            lambda: OpenCVCameraSource(
                device_index,
                name=source_name,
                capture_factory=self._capture_factory,
            ),
        )
        return source_id

    def register_image(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        name: str | None = None,
    ) -> str:
        image_path = Path(path)
        resolved_id = source_id or f"image:{image_path.stem}"
        source_name = name or image_path.name
        self.register(
            CameraSourceDescriptor(
                id=resolved_id,
                name=source_name,
                type="image",
                available=image_path.is_file(),
                metadata={
                    **base_metadata(
                        name=source_name,
                        source_type="image",
                        width=0,
                        height=0,
                        fps=0.0,
                    ),
                    "path": str(image_path),
                },
            ),
            lambda: ImageCameraSource(
                image_path, source_id=resolved_id, name=source_name
            ),
        )
        return resolved_id

    def register_video(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        name: str | None = None,
    ) -> str:
        raw_path = str(path)
        stem = Path(raw_path).stem or "stream"
        resolved_id = source_id or f"video:{stem}"
        source_name = name or Path(raw_path).name or raw_path
        self.register(
            CameraSourceDescriptor(
                id=resolved_id,
                name=source_name,
                type="video",
                available="://" in raw_path or Path(raw_path).is_file(),
                metadata={
                    **base_metadata(
                        name=source_name,
                        source_type="video",
                        width=0,
                        height=0,
                        fps=0.0,
                    ),
                    "path": raw_path,
                },
            ),
            lambda: VideoCameraSource(
                raw_path, source_id=resolved_id, name=source_name
            ),
        )
        return resolved_id

    def register_mock_graph(
        self,
        graph_id: str,
        *,
        name: str | None = None,
        fps: float = 5.0,
        already_canonical: bool = True,
        graph_path: str | Path | None = None,
    ) -> str:
        scenario = (
            self._scenario_registry.get(graph_id) if graph_path is None else None
        )
        resolved_graph_path = (
            scenario.graph_path if scenario is not None else Path(graph_path)
        )
        source_id = f"mock:{graph_id}"
        source_name = name or (
            scenario.name if scenario is not None else f"Mock Graph: {graph_id}"
        )
        self.register(
            CameraSourceDescriptor(
                id=source_id,
                name=source_name,
                type="mock_graph",
                available=resolved_graph_path.is_file(),
                metadata={
                    **base_metadata(
                        name=source_name,
                        source_type="mock_graph",
                        width=(
                            scenario.screen_width if scenario is not None else 0
                        ),
                        height=(
                            scenario.screen_height if scenario is not None else 0
                        ),
                        fps=fps,
                    ),
                    "graph_id": graph_id,
                    "already_canonical": already_canonical,
                    "description": (
                        scenario.description if scenario is not None else ""
                    ),
                },
            ),
            lambda: MockGraphCameraSource(
                graph_id,
                name=source_name,
                fps=fps,
                already_canonical=already_canonical,
                graph_path=resolved_graph_path,
                event_recorder=self._record_mock_event,
            ),
        )
        return source_id

    def register_fixture_scenarios(self) -> list[str]:
        """Register every scenario declared in fixtures/registry.json."""

        registered: list[str] = []
        for scenario in self._scenario_registry.list_scenarios():
            source_id = f"mock:{scenario.id}"
            if source_id in self._registrations:
                continue
            registered.append(self.register_mock_graph(scenario.id))
        return registered

    def list_sources(self, *, refresh: bool = False) -> list[CameraSourceDescriptor]:
        """Return discovered physical and registered mock/file sources."""

        self.discover_physical_sources(force=refresh)
        with self._lock:
            registrations = tuple(self._registrations.values())
            active = self._active

        descriptors: list[CameraSourceDescriptor] = []
        for registration in registrations:
            descriptor = registration.descriptor
            source = (
                active
                if active is not None and active.id == descriptor.id
                else registration.factory()
            )
            if refresh:
                try:
                    available = source.is_available()
                    metadata = source.get_metadata()
                except CameraError:
                    available = False
                    metadata = dict(descriptor.metadata)
            else:
                available = (
                    source.is_opened() if source is active else descriptor.available
                )
                metadata = (
                    source.get_metadata()
                    if source is active
                    else dict(descriptor.metadata)
                )
            descriptors.append(
                CameraSourceDescriptor(
                    id=descriptor.id,
                    name=descriptor.name,
                    type=descriptor.type,
                    available=available,
                    metadata=metadata,
                )
            )
        return sorted(descriptors, key=_descriptor_sort_key)

    def select(self, source_id: str) -> CameraSource:
        """Atomically close the previous source and open the selected source."""

        with self._lock:
            registration = self._registrations.get(source_id)
            if registration is None:
                self._last_error = f"Camera source is not registered: {source_id}"
                raise CameraSourceNotFoundError(self._last_error)

            if self._active is not None and self._active.id == source_id:
                if not self._active.is_opened():
                    self._open_active()
                return self._active

            if self._active is not None:
                self._active.close()

            self._active = registration.factory()
            self._last_error = None
            self._open_active()
            return self._active

    def current_source(self) -> CameraSource:
        """Return the selected source, even when its last open failed."""

        with self._lock:
            if self._active is None:
                raise CameraSourceNotFoundError("No active camera source is selected")
            return self._active

    def reconnect(self) -> CameraSource:
        """Close and reopen the selected source while holding the switch lock."""

        with self._lock:
            source = self.current_source()
            source.close()
            self._last_error = None
            self._open_active()
            return source

    def close_current(self) -> None:
        """Close the selected source without removing its selection."""

        with self._lock:
            if self._active is not None:
                self._active.close()

    def status(self) -> dict[str, object]:
        """Return an explicit connected/disconnected/error state snapshot."""

        with self._lock:
            if self._active is None:
                return {
                    "source_id": None,
                    "name": None,
                    "type": None,
                    "opened": False,
                    "connected": False,
                    "state": "error" if self._last_error else "disconnected",
                    "error": self._last_error,
                    "metadata": None,
                    "discovery_completed": self._discovery_completed,
                }
            opened = self._active.is_opened()
            try:
                metadata: CameraMetadata | None = self._active.get_metadata()
            except CameraError:
                metadata = None
            state = "error" if self._last_error else (
                "connected" if opened else "disconnected"
            )
            return {
                "source_id": self._active.id,
                "name": self._active.name,
                "type": self._active.source_type,
                "opened": opened,
                "connected": opened and self._last_error is None,
                "state": state,
                "error": self._last_error,
                "metadata": metadata,
                "discovery_completed": self._discovery_completed,
                "mock_graph": (
                    self._active.status()
                    if isinstance(self._active, MockGraphCameraSource)
                    and self._active.is_opened()
                    else None
                ),
            }

    def set_event_recorder(self, recorder: MockEventRecorder | None) -> None:
        """Attach an implementation-neutral event sink for source events."""

        with self._lock:
            self._event_recorder = recorder
            if isinstance(self._active, MockGraphCameraSource):
                self._active.set_event_recorder(self._record_mock_event)

    def tap(self, x: float, y: float) -> MockTransition | None:
        """Forward a tap when the active source is a mock screen graph."""

        with self._lock:
            if not isinstance(self._active, MockGraphCameraSource):
                return None
            return self._active.tap(x, y)

    def reset_mock_graph(self) -> MockTransition | None:
        with self._lock:
            if not isinstance(self._active, MockGraphCameraSource):
                return None
            return self._active.reset()

    def transition_mock_graph(self, next_state: str) -> MockTransition | None:
        with self._lock:
            if not isinstance(self._active, MockGraphCameraSource):
                return None
            return self._active.transition(next_state)

    def mock_graph_status(self) -> dict[str, object] | None:
        with self._lock:
            if not isinstance(self._active, MockGraphCameraSource):
                return None
            return {
                "source_id": self._active.id,
                "name": self._active.name,
                "metadata": self._active.get_metadata(),
                **self._active.status(),
            }

    @property
    def active_source(self) -> CameraSource:
        """Compatibility alias for ``current_source``."""

        return self.current_source()

    @property
    def active_source_id(self) -> str:
        return self.current_source().id

    @property
    def id(self) -> str:
        return self.current_source().id

    @property
    def source(self) -> str:
        """Compatibility label used by the existing capture worker."""

        return self.id

    @property
    def name(self) -> str:
        return self.current_source().name

    @property
    def source_type(self) -> CameraSourceType:
        return self.current_source().source_type

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def open(self) -> None:
        with self._lock:
            if not self.current_source().is_opened():
                self._open_active()

    def close(self) -> None:
        self.close_current()

    def is_opened(self) -> bool:
        with self._lock:
            return self._active is not None and self._active.is_opened()

    def read_frame(self) -> BGRFrame:
        with self._lock:
            if self._active is None:
                error = "No active camera source is selected"
                self._last_error = error
                raise CameraNotOpenError(error)
            try:
                frame = self._active.read_frame()
            except CameraError as error:
                self._last_error = str(error)
                raise
            self._last_error = None
            return frame

    def read_frame_with_metadata(
        self,
    ) -> tuple[BGRFrame, str, CameraMetadata]:
        """Atomically capture a frame and the source metadata that produced it."""

        with self._lock:
            frame = self.read_frame()
            source = self.current_source()
            return frame, source.id, source.get_metadata()

    def get_metadata(self) -> CameraMetadata:
        with self._lock:
            return self.current_source().get_metadata()

    def is_available(self) -> bool:
        with self._lock:
            return self._active is not None and self._active.is_available()

    def _open_active(self) -> None:
        assert self._active is not None
        try:
            self._active.open()
        except CameraError as error:
            self._last_error = str(error)
            raise
        except Exception as error:
            wrapped = CameraOpenError(
                f"Could not open camera source: {self._active.id}"
            )
            self._last_error = str(wrapped)
            raise wrapped from error
        self._last_error = None

    def _register_configured_source(self, source: int | str) -> str:
        if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
            device_index = int(source)
            source_id = f"opencv:{device_index}"
            if source_id not in self._registrations:
                self.register_opencv(device_index)
            return source_id

        source_id = str(source)
        if source_id in self._registrations:
            return source_id
        if source_id.startswith("opencv:"):
            try:
                device_index = int(source_id.removeprefix("opencv:"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid OpenCV camera source ID: {source_id}"
                ) from error
            return self.register_opencv(device_index)
        if source_id.startswith("mock:"):
            return self.register_mock_graph(source_id.removeprefix("mock:"))

        suffix = Path(source_id).suffix.lower()
        if suffix in {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
            return self.register_image(source_id)
        return self.register_video(source_id)

    def _physical_descriptors(self) -> list[CameraSourceDescriptor]:
        return [
            registration.descriptor
            for registration in self._registrations.values()
            if registration.descriptor.type == "physical"
        ]

    def _record_mock_event(
        self, event_type: str, payload: Mapping[str, object]
    ) -> None:
        recorder = self._event_recorder
        if recorder is not None:
            recorder(event_type, payload)


def _descriptor_sort_key(descriptor: CameraSourceDescriptor) -> tuple[int, str]:
    type_order = {"physical": 0, "image": 1, "video": 2, "mock_graph": 3}
    return type_order[descriptor.type], descriptor.id
