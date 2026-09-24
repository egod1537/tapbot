"""FastAPI application for manual TapBot operation."""

from __future__ import annotations

import asyncio
import argparse
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from itertools import count
import json
import math
from pathlib import Path
from threading import Lock
from time import perf_counter
from collections.abc import Mapping, Sequence
from typing import Annotated, AsyncIterator

import cv2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
import uvicorn

from tapbot.camera.manager import CameraManager, CameraSourceNotFoundError
from tapbot.camera.mock_graph import MockGraphStateError
from tapbot.camera.source import CameraError, CameraSource
from tapbot.core.actions import (
    Action,
    EmergencyStopAction,
    HomeAction,
    MoveAction,
    PenDownAction,
    PenUpAction,
    TapAction,
)
from tapbot.model.client import MockModelClient, ModelClient, TracingModelClient
from tapbot.model.decision import Decision
from tapbot.model.pipeline import DecisionEngine, DecisionPolicy, DecisionResult
from tapbot.model.resolver import TargetResolver
from tapbot.robot.controller import RobotController
from tapbot.robot.console import (
    GcodeConsoleError,
    console_capabilities,
    is_motion_console_command,
    validate_console_command,
)
from tapbot.robot.grbl import GrblRobotConfig, GrblRobotController, GrblSession
from tapbot.robot.mock import MockRobotController
from tapbot.robot.serial_transport import SerialTransport, SerialTransportConfig
from tapbot.robot.transport import MockTransport
from tapbot.simulation import SimulationBridge
from tapbot.ui.services import (
    CameraFrameWorker,
    CameraFrameSnapshot,
    EventLog,
    RobotCommandDispatcher,
)
from tapbot.vision.calibration import (
    Calibration,
    CalibrationError,
    CalibrationNotFoundError,
    CalibrationStore,
    Point2D,
    RobotWorkArea,
)
from tapbot.vision.detector import (
    ColorButtonDetector,
    Detector,
    VisionPipeline,
    VisionResult,
    draw_debug_overlay,
)
from tapbot.vision.screen import PhoneScreenDetector


@dataclass(frozen=True, slots=True)
class WorkspaceBounds:
    min_x: float = 0
    max_x: float = 1000
    min_y: float = 0
    max_y: float = 1000


@dataclass(frozen=True, slots=True)
class CoordinateRequest:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class CameraSourceSelectionRequest:
    source_id: str


@dataclass(frozen=True, slots=True)
class MockGraphTransitionRequest:
    state_id: str


@dataclass(frozen=True, slots=True)
class RawGcodeRequest:
    command: str


@dataclass(frozen=True, slots=True)
class CalibrationRequest:
    profile_name: str
    camera_corners: list[CoordinateRequest]
    robot_points: list[CoordinateRequest]
    phone_width: float
    phone_height: float
    camera_width: int | None = None
    camera_height: int | None = None
    frame_id: int | None = None


@dataclass(frozen=True, slots=True)
class VisionRunRequest:
    frame_id: int
    detector_types: list[str] | None = None
    confidence_threshold: float = 0.0


@dataclass(frozen=True, slots=True)
class ModelRunRequest:
    frame_id: int | None = None
    context: dict[str, object] | None = None


STATIC_DIR = Path(__file__).with_name("static")


def create_app(
    *,
    robot: RobotController | None = None,
    camera: CameraSource | None = None,
    camera_manager: CameraManager | None = None,
    bounds: WorkspaceBounds | None = None,
    camera_fps: float = 5.0,
    calibration_store: CalibrationStore | None = None,
    vision_detectors: Sequence[Detector] | None = None,
    model_client: ModelClient | None = None,
    decision_policy: DecisionPolicy | None = None,
) -> FastAPI:
    robot = robot or MockRobotController()
    if camera is not None and camera_manager is not None:
        raise ValueError("Provide either camera or camera_manager, not both")
    if camera_manager is None and camera is None:
        camera_manager = CameraManager.with_defaults()
    if camera_manager is not None:
        camera = camera_manager
    assert camera is not None
    bounds = bounds or WorkspaceBounds()
    event_log = EventLog()

    def record_simulation_event(
        event_type: str, payload: Mapping[str, object]
    ) -> None:
        messages = {
            "action.tap": "Mock tap action received",
            "mock.hit": f"Mock hotspot hit: {payload.get('hotspot_id')}",
            "mock.miss": "Mock hotspot missed",
            "mock.transition": (
                f"Mock screen transition: {payload.get('from_state')} "
                f"→ {payload.get('to_state')}"
            ),
        }
        event_log.add(
            messages.get(event_type, f"Simulation event: {event_type}"),
            event_type=event_type,
            category="robot" if event_type == "action.tap" else "camera",
            status="warning" if event_type == "mock.miss" else "success",
            payload=payload,
        )

    simulation_bridge = (
        SimulationBridge(
            robot,
            camera_manager,
            event_recorder=record_simulation_event,
        )
        if isinstance(robot, MockRobotController) and camera_manager is not None
        else None
    )
    dispatcher = RobotCommandDispatcher(robot, event_log)
    camera_worker = CameraFrameWorker(camera, event_log, fps=camera_fps)
    calibration_store = calibration_store or CalibrationStore("tapbot-calibrations.json")
    vision_detectors = tuple(vision_detectors or (ColorButtonDetector(),))
    model_client = model_client or MockModelClient(
        {
            "state": "debug_idle",
            "action": "noop",
            "target": None,
            "confidence": 1.0,
            "reason": "Default debug model does not propose robot actions.",
        }
    )
    traced_model_client = TracingModelClient(model_client)
    decision_policy = decision_policy or DecisionPolicy()
    calibration_lock = Lock()
    gcode_console_lock = Lock()
    vision_frame_lock = Lock()
    vision_result_lock = Lock()
    model_debug_lock = Lock()
    model_result_lock = Lock()
    saved_vision_frames: dict[int, CameraFrameSnapshot] = {}
    vision_result_images: dict[int, bytes] = {}
    vision_result_ids = count(1)
    model_input_images: dict[int, bytes] = {}
    model_result_ids = count(1)
    operation_trace_ids = count(1)
    try:
        active_calibration: Calibration | None = calibration_store.load()
        event_log.add(
            f"Loaded calibration profile: {active_calibration.profile_name}"
        )
    except CalibrationNotFoundError:
        active_calibration = None
    except CalibrationError as error:
        active_calibration = None
        event_log.add(f"Calibration load error: {error}", level="error")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        connect_robot = getattr(robot, "connect", None)
        if callable(connect_robot):
            try:
                await asyncio.to_thread(connect_robot)
                event_log.add(f"Robot connected: {type(robot).__name__}")
            except Exception as error:
                event_log.add(f"Robot connection error: {error}", level="error")
        if simulation_bridge is not None:
            simulation_bridge.start()
        dispatcher.start()
        camera_worker.start()
        event_log.add("TapBot UI services started")
        try:
            yield
        finally:
            if simulation_bridge is not None:
                simulation_bridge.close()
            camera_worker.stop()
            dispatcher.shutdown()
            close_robot = getattr(robot, "close", None)
            if callable(close_robot):
                try:
                    await asyncio.to_thread(close_robot)
                except Exception as error:
                    event_log.add(f"Robot close error: {error}", level="error")
            event_log.add("TapBot UI services stopped")

    application = FastAPI(title="TapBot Control UI", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Frame-Id",
            "X-Frame-Timestamp",
            "X-Frame-Width",
            "X-Frame-Height",
            "X-Frame-Frozen",
            "X-Preview-Width",
            "X-Preview-Height",
            "X-Center-Robot-X",
            "X-Center-Robot-Y",
        ],
    )
    application.state.robot = robot
    application.state.camera = camera
    application.state.camera_manager = camera_manager
    application.state.bounds = bounds
    application.state.event_log = event_log
    application.state.dispatcher = dispatcher
    application.state.camera_worker = camera_worker
    application.state.calibration_store = calibration_store
    application.state.vision_detectors = vision_detectors
    application.state.model_client = model_client
    application.state.decision_policy = decision_policy
    application.state.simulation_bridge = simulation_bridge
    robot_state_lock = Lock()
    robot_state: dict[str, object] = {
        "x": 0.0,
        "y": 0.0,
        "homed": False,
        "pen": "unknown",
        "last_command": None,
    }

    def robot_mode() -> str:
        if isinstance(robot, MockRobotController):
            return "MOCK"
        if (
            isinstance(robot, GrblRobotController)
            and robot.session is not None
            and isinstance(robot.session.transport, MockTransport)
        ):
            return "MOCK"
        config = getattr(robot, "config", None)
        if getattr(config, "dry_run", False):
            return "DRY-RUN"
        return "REAL"

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        event_log.add(f"Request validation error: {error}", level="error")
        return JSONResponse(status_code=422, content={"detail": error.errors()})

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/status")
    async def status() -> dict[str, object]:
        snapshot = camera_worker.latest_frame()
        source_id = getattr(
            camera, "id", getattr(camera, "source", type(camera).__name__)
        )
        return {
            "robot": type(robot).__name__,
            "robot_connected": getattr(robot, "is_connected", True),
            "robot_mode": robot_mode(),
            "robot_busy": dispatcher.is_busy,
            "camera_opened": camera.is_opened(),
            "camera_error": camera_worker.error,
            "camera_frame_id": None if snapshot is None else snapshot.frame_id,
            "camera_source_id": str(source_id),
            "camera_source_type": getattr(camera, "source_type", "physical"),
            "robot_queue_depth": dispatcher.pending_count,
            "workspace": asdict(bounds),
            "calibration_profile": (
                None if active_calibration is None else active_calibration.profile_name
            ),
            "model_provider": traced_model_client.provider,
            "model_name": traced_model_client.model_name,
            "model_connected": traced_model_client.connected,
            "model_latency_ms": traced_model_client.last_latency_ms,
            "vision_detectors": [
                type(detector).__name__ for detector in vision_detectors
            ],
        }

    @application.get("/api/logs")
    async def logs(
        after_id: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        return {"entries": [asdict(entry) for entry in event_log.entries(after_id=after_id)]}

    @application.get("/api/events/stream")
    async def event_stream(
        request: Request,
        after_id: Annotated[int, Query(ge=0)] = 0,
        once: bool = False,
    ) -> StreamingResponse:
        try:
            header_id = int(request.headers.get("last-event-id", "0"))
        except ValueError:
            header_id = 0
        initial_cursor = max(after_id, header_id)

        async def stream_events() -> AsyncIterator[str]:
            cursor = initial_cursor
            heartbeat_at = asyncio.get_running_loop().time()
            while True:
                entries = event_log.entries(after_id=cursor)
                for entry in entries:
                    cursor = entry.id
                    data = json.dumps(
                        asdict(entry),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield f"id: {entry.id}\ndata: {data}\n\n"
                if once:
                    return
                if await request.is_disconnected():
                    return
                now = asyncio.get_running_loop().time()
                if now - heartbeat_at >= 15:
                    yield ": keep-alive\n\n"
                    heartbeat_at = now
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/api/gcode/capabilities")
    async def gcode_capabilities() -> dict[str, object]:
        return console_capabilities(
            robot,
            mode=robot_mode(),
            connected=bool(getattr(robot, "is_connected", True)),
        )

    @application.post("/api/gcode/command")
    async def raw_gcode(payload: RawGcodeRequest) -> dict[str, object]:
        trace_id = f"gcode-{next(operation_trace_ids)}"
        if not isinstance(robot, GrblRobotController):
            event_log.add(
                "Raw G-code rejected: GRBL controller is not active",
                level="error",
                event_type="robot.error",
                category="robot",
                status="error",
                trace_id=trace_id,
                payload={
                    "command": payload.command,
                    "error": "Raw G-code console requires a GRBL controller",
                },
            )
            raise HTTPException(
                status_code=409,
                detail="Raw G-code console requires a GRBL controller",
            )
        try:
            command = validate_console_command(payload.command, robot.config)
        except GcodeConsoleError as error:
            event_log.add(
                f"Raw G-code rejected: {error}",
                level="warning",
                event_type="robot.error",
                category="robot",
                status="error",
                trace_id=trace_id,
                payload={"command": payload.command, "error": str(error)},
            )
            raise HTTPException(status_code=422, detail=str(error)) from error

        def execute_command() -> tuple[str, ...]:
            with gcode_console_lock:
                if command == "?":
                    return (robot.query_raw_status(),)
                if is_motion_console_command(command):
                    robot.execute_raw("G90")
                return (*robot.execute_raw(command), "ok")

        event_log.add(
            f"G-code command: {command}",
            level="warning",
            event_type="robot.command",
            category="robot",
            status="pending",
            trace_id=trace_id,
            payload={"command": command, "raw": True},
        )
        started_at = perf_counter()
        try:
            response_lines = await asyncio.to_thread(execute_command)
        except Exception as error:
            event_log.add(
                f"G-code failed: {error}",
                level="error",
                event_type="robot.error",
                category="robot",
                status="error",
                trace_id=trace_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                payload={"command": command, "error": str(error)},
            )
            raise HTTPException(status_code=500, detail=str(error)) from error
        event_log.add(
            f"G-code response: {response_lines[-1] if response_lines else 'ok'}",
            event_type="robot.response",
            category="robot",
            status="success",
            trace_id=trace_id,
            latency_ms=(perf_counter() - started_at) * 1000,
            payload={"command": command, "response": list(response_lines)},
        )
        return {
            "ok": True,
            "command": command,
            "response": list(response_lines),
            "mode": robot_mode(),
        }

    @application.get("/api/robot/status")
    async def robot_status() -> dict[str, object]:
        with robot_state_lock:
            state = dict(robot_state)
        return {
            "connected": bool(getattr(robot, "is_connected", True)),
            "busy": dispatcher.is_busy,
            "homed": state["homed"],
            "mode": robot_mode(),
            "position": {"x": state["x"], "y": state["y"]},
            "pen": state["pen"],
            "last_command": state["last_command"],
            "workspace": asdict(bounds),
            "queue_depth": dispatcher.pending_count,
        }

    @application.get("/api/camera/sources")
    async def camera_sources(refresh: bool = False) -> dict[str, object]:
        if camera_manager is not None:
            descriptors = await asyncio.to_thread(
                camera_manager.list_sources, refresh=refresh
            )
            return {
                "active_id": camera_manager.active_source_id,
                "sources": [descriptor.to_dict() for descriptor in descriptors],
            }

        source_id = str(
            getattr(camera, "id", getattr(camera, "source", type(camera).__name__))
        )
        metadata_getter = getattr(camera, "get_metadata", None)
        metadata = (
            metadata_getter()
            if callable(metadata_getter)
            else {
                "width": 0,
                "height": 0,
                "fps": camera_fps,
                "type": "physical",
                "name": type(camera).__name__,
            }
        )
        return {
            "active_id": source_id,
            "sources": [
                {
                    "id": source_id,
                    "name": str(metadata.get("name", type(camera).__name__)),
                    "type": str(metadata.get("type", "physical")),
                    "available": camera.is_opened(),
                    "metadata": metadata,
                }
            ],
        }

    @application.get("/api/camera/status")
    async def camera_status() -> dict[str, object]:
        snapshot = camera_worker.latest_frame()
        if camera_manager is not None:
            result = camera_manager.status()
        else:
            source_id = str(
                getattr(camera, "id", getattr(camera, "source", type(camera).__name__))
            )
            opened = camera.is_opened()
            result = {
                "source_id": source_id,
                "name": getattr(camera, "name", type(camera).__name__),
                "type": getattr(camera, "source_type", "physical"),
                "opened": opened,
                "connected": opened,
                "state": "connected" if opened else "disconnected",
                "error": None,
                "metadata": None,
                "discovery_completed": False,
                "mock_graph": None,
            }
        if camera_worker.error is not None:
            result["state"] = "error"
            result["connected"] = False
            result["error"] = camera_worker.error
        result["frame_id"] = None if snapshot is None else snapshot.frame_id
        return result

    @application.post("/api/camera/source", include_in_schema=False)
    @application.post("/api/camera/select")
    async def select_camera_source(
        payload: CameraSourceSelectionRequest,
    ) -> dict[str, object]:
        if camera_manager is None:
            raise HTTPException(
                status_code=409,
                detail="The injected camera source cannot be switched",
            )

        await asyncio.to_thread(camera_worker.stop)
        camera_worker.clear()
        try:
            camera_manager.select(payload.source_id)
        except CameraSourceNotFoundError as error:
            camera_worker.start()
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CameraError as error:
            camera_worker.start()
            raise HTTPException(status_code=422, detail=str(error)) from error

        camera_worker.start()
        event_log.add(
            f"Camera source selected: {payload.source_id}",
            event_type="camera.source",
            category="camera",
            status="success",
            payload={"source_id": payload.source_id},
        )
        return {
            "active_id": camera_manager.active_source_id,
            "metadata": camera_manager.get_metadata(),
        }

    @application.post("/api/camera/reconnect")
    async def reconnect_camera() -> dict[str, object]:
        if camera_manager is None:
            raise HTTPException(
                status_code=409,
                detail="The injected camera source cannot be reconnected",
            )

        await asyncio.to_thread(camera_worker.stop)
        camera_worker.clear()
        try:
            await asyncio.to_thread(camera_manager.reconnect)
        except CameraError as error:
            camera_worker.start()
            raise HTTPException(status_code=503, detail=str(error)) from error

        camera_worker.start()
        event_log.add(
            f"Camera source reconnected: {camera_manager.active_source_id}",
            event_type="camera.reconnect",
            category="camera",
            status="success",
            payload={"source_id": camera_manager.active_source_id},
        )
        return camera_manager.status()

    @application.post("/api/camera/reset-graph")
    async def reset_camera_graph() -> dict[str, object]:
        if camera_manager is None:
            raise HTTPException(
                status_code=409,
                detail="The injected camera source is not a mock graph",
            )

        transition = await asyncio.to_thread(camera_manager.reset_mock_graph)
        if transition is None:
            raise HTTPException(
                status_code=409,
                detail="The active camera source is not a mock graph",
            )
        camera_worker.clear()
        event_log.add(
            f"Mock camera graph reset: {transition.to_state}",
            event_type="camera.graph.reset",
            category="camera",
            status="success",
            payload=transition.to_dict(),
        )
        return camera_manager.status()

    def mock_graph_status_snapshot() -> dict[str, object]:
        if camera_manager is None:
            raise HTTPException(
                status_code=409,
                detail="The injected camera source is not a mock graph",
            )
        status = camera_manager.mock_graph_status()
        if status is None:
            raise HTTPException(
                status_code=409,
                detail="The active camera source is not a mock graph",
            )
        return status

    @application.get("/api/mock-graph/status")
    async def mock_graph_status() -> dict[str, object]:
        return await asyncio.to_thread(mock_graph_status_snapshot)

    @application.post("/api/mock-graph/reset")
    async def reset_mock_graph() -> dict[str, object]:
        mock_graph_status_snapshot()
        assert camera_manager is not None
        transition = await asyncio.to_thread(camera_manager.reset_mock_graph)
        assert transition is not None
        camera_worker.clear()
        return {
            "transition": transition.to_dict(),
            "status": await asyncio.to_thread(mock_graph_status_snapshot),
        }

    @application.post("/api/mock-graph/tap")
    async def tap_mock_graph(payload: CoordinateRequest) -> dict[str, object]:
        mock_graph_status_snapshot()
        assert camera_manager is not None
        transition = await asyncio.to_thread(
            camera_manager.tap, payload.x, payload.y
        )
        camera_worker.clear()
        status = await asyncio.to_thread(mock_graph_status_snapshot)
        return {
            "hit": transition is not None,
            "tap": status["last_tap"],
            "transition": (
                None if transition is None else transition.to_dict()
            ),
            "status": status,
        }

    @application.post("/api/mock-graph/transition")
    async def transition_mock_graph(
        payload: MockGraphTransitionRequest,
    ) -> dict[str, object]:
        mock_graph_status_snapshot()
        assert camera_manager is not None
        try:
            transition = await asyncio.to_thread(
                camera_manager.transition_mock_graph, payload.state_id
            )
        except MockGraphStateError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        assert transition is not None
        camera_worker.clear()
        return {
            "transition": transition.to_dict(),
            "status": await asyncio.to_thread(mock_graph_status_snapshot),
        }

    @application.get("/api/camera/frame")
    async def camera_frame() -> Response:
        snapshot = camera_worker.latest_frame()
        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail=camera_worker.error or "Camera frame is not available yet",
            )
        return camera_snapshot_response(snapshot)

    def camera_snapshot_response(snapshot: CameraFrameSnapshot) -> Response:
        return Response(
            content=snapshot.jpeg,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Id": str(snapshot.frame_id),
                "X-Frame-Timestamp": snapshot.captured_at,
                "X-Frame-Width": str(snapshot.width),
                "X-Frame-Height": str(snapshot.height),
            },
        )

    @application.post("/api/camera/freeze")
    async def freeze_camera_frame() -> Response:
        snapshot = camera_worker.freeze_latest_frame()
        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail=camera_worker.error or "Camera frame is not available yet",
            )
        response = camera_snapshot_response(snapshot)
        response.headers["X-Frame-Frozen"] = "true"
        return response

    def current_calibration() -> Calibration:
        with calibration_lock:
            calibration = active_calibration
        if calibration is None:
            raise HTTPException(status_code=409, detail="Calibration is not configured")
        return calibration

    def calibration_response(calibration: Calibration) -> dict[str, object]:
        return {"configured": True, "calibration": calibration.to_dict()}

    def calibration_from_payload(payload: CalibrationRequest) -> Calibration:
        if len(payload.camera_corners) != 4 or len(payload.robot_points) != 4:
            raise HTTPException(
                status_code=422,
                detail="Exactly four camera corners and robot points are required",
            )
        if (payload.camera_width is None) != (payload.camera_height is None):
            raise HTTPException(
                status_code=422,
                detail="camera_width and camera_height must be supplied together",
            )
        camera_resolution = (
            None
            if payload.camera_width is None or payload.camera_height is None
            else (payload.camera_width, payload.camera_height)
        )
        try:
            return Calibration(
                profile_name=payload.profile_name,
                camera_corners=tuple(
                    Point2D(point.x, point.y) for point in payload.camera_corners
                ),  # type: ignore[arg-type]
                robot_points=tuple(
                    Point2D(point.x, point.y) for point in payload.robot_points
                ),  # type: ignore[arg-type]
                phone_width=payload.phone_width,
                phone_height=payload.phone_height,
                camera_resolution=camera_resolution,
                robot_work_area=RobotWorkArea(
                    bounds.min_x, bounds.max_x, bounds.min_y, bounds.max_y
                ),
            )
        except CalibrationError as error:
            event_log.add(f"Calibration error: {error}", level="error")
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/calibration/profiles")
    async def calibration_profiles() -> dict[str, object]:
        try:
            profiles = calibration_store.list_profiles()
        except CalibrationError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "profiles": profiles,
            "active_profile": (
                None if active_calibration is None else active_calibration.profile_name
            ),
        }

    @application.get("/api/calibration")
    async def get_calibration(
        profile: str | None = None,
    ) -> dict[str, object]:
        if profile is None:
            with calibration_lock:
                calibration = active_calibration
            if calibration is None:
                return {"configured": False, "calibration": None}
            return calibration_response(calibration)
        try:
            return calibration_response(calibration_store.load(profile))
        except CalibrationError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.post("/api/calibration")
    async def save_calibration(payload: CalibrationRequest) -> dict[str, object]:
        nonlocal active_calibration
        calibration = calibration_from_payload(payload)
        try:
            calibration_store.save(calibration)
        except OSError as error:
            event_log.add(f"Calibration save error: {error}", level="error")
            raise HTTPException(status_code=500, detail="Could not save calibration") from error
        with calibration_lock:
            active_calibration = calibration
        event_log.add(f"Calibration saved: {calibration.profile_name}")
        return calibration_response(calibration)

    @application.post("/api/calibration/preview")
    async def preview_calibration(payload: CalibrationRequest) -> Response:
        calibration = calibration_from_payload(payload)
        frame = (
            camera_worker.latest_bgr_frame()
            if payload.frame_id is None
            else camera_worker.frozen_bgr_frame(payload.frame_id)
        )
        if frame is None:
            raise HTTPException(
                status_code=409 if payload.frame_id is not None else 503,
                detail=(
                    f"Frozen camera frame is unavailable: {payload.frame_id}"
                    if payload.frame_id is not None
                    else camera_worker.error or "Camera frame is not available yet"
                ),
            )
        try:
            rectified = await asyncio.to_thread(calibration.rectify_frame, frame)
            center = calibration.screen_to_robot(
                calibration.phone_width / 2,
                calibration.phone_height / 2,
            )
            success, encoded = await asyncio.to_thread(
                cv2.imencode, ".jpg", rectified
            )
            if not success:
                raise CalibrationError("Could not encode calibration preview")
        except (CalibrationError, cv2.error) as error:
            event_log.add(f"Calibration preview error: {error}", level="error")
            raise HTTPException(status_code=422, detail=str(error)) from error
        return Response(
            content=encoded.tobytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Preview-Width": str(rectified.shape[1]),
                "X-Preview-Height": str(rectified.shape[0]),
                "X-Center-Robot-X": str(center.x),
                "X-Center-Robot-Y": str(center.y),
            },
        )

    @application.post("/api/calibration/activate")
    async def activate_calibration(profile: str) -> dict[str, object]:
        nonlocal active_calibration
        try:
            calibration = calibration_store.load(profile)
            calibration_store.save(calibration)
        except CalibrationError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(
                status_code=500, detail="Could not activate calibration"
            ) from error
        with calibration_lock:
            active_calibration = calibration
        event_log.add(f"Calibration activated: {calibration.profile_name}")
        return calibration_response(calibration)

    def transform_response(operation: str, transform: object) -> dict[str, float]:
        try:
            point = transform()
        except CalibrationError as error:
            event_log.add(f"Calibration transform error: {error}", level="error")
            raise HTTPException(status_code=422, detail=str(error)) from error
        event_log.add(f"Calibration transform {operation}: ({point.x}, {point.y})")
        return {"x": point.x, "y": point.y}

    @application.post("/api/calibration/screen-to-robot")
    async def screen_to_robot(payload: CoordinateRequest) -> dict[str, object]:
        calibration = current_calibration()
        robot_point = transform_response(
            "screen-to-robot",
            lambda: calibration.screen_to_robot(payload.x, payload.y),
        )
        return {"robot": robot_point}

    @application.post("/api/calibration/robot-to-screen")
    async def robot_to_screen(payload: CoordinateRequest) -> dict[str, object]:
        calibration = current_calibration()
        screen_point = transform_response(
            "robot-to-screen",
            lambda: calibration.robot_to_screen(payload.x, payload.y),
        )
        return {"screen": screen_point}

    @application.post("/api/calibration/camera-to-robot")
    async def camera_to_robot(payload: CoordinateRequest) -> dict[str, object]:
        calibration = current_calibration()
        try:
            screen = calibration.camera_to_screen(payload.x, payload.y)
            robot_point = calibration.screen_to_robot(screen.x, screen.y)
        except CalibrationError as error:
            event_log.add(f"Calibration transform error: {error}", level="error")
            raise HTTPException(status_code=422, detail=str(error)) from error
        event_log.add(
            "Camera test point "
            f"({payload.x}, {payload.y}) -> screen ({screen.x}, {screen.y}) "
            f"-> robot ({robot_point.x}, {robot_point.y})"
        )
        return {
            "screen": {"x": screen.x, "y": screen.y},
            "robot": {"x": robot_point.x, "y": robot_point.y},
        }

    def detector_descriptor(detector: Detector) -> dict[str, str]:
        return {
            "type": str(
                getattr(detector, "detector_type", type(detector).__name__)
            ),
            "name": type(detector).__name__,
        }

    def vision_frame_metadata(snapshot: CameraFrameSnapshot) -> dict[str, object]:
        return {
            "frame_id": snapshot.frame_id,
            "captured_at": snapshot.captured_at,
            "width": snapshot.width,
            "height": snapshot.height,
        }

    def remember_vision_frame(snapshot: CameraFrameSnapshot) -> None:
        with vision_frame_lock:
            saved_vision_frames[snapshot.frame_id] = snapshot
            while len(saved_vision_frames) > 8:
                oldest_frame_id = next(iter(saved_vision_frames))
                del saved_vision_frames[oldest_frame_id]

    @application.get("/api/vision/capabilities")
    async def vision_capabilities() -> dict[str, object]:
        return {
            "detectors": [
                detector_descriptor(detector) for detector in vision_detectors
            ],
            "max_saved_frames": 8,
        }

    @application.get("/api/vision/frames")
    async def vision_frames() -> dict[str, object]:
        with vision_frame_lock:
            frames = list(saved_vision_frames.values())
        return {
            "frames": [
                vision_frame_metadata(snapshot)
                for snapshot in reversed(frames)
            ]
        }

    @application.post("/api/vision/frames")
    async def save_vision_frame() -> dict[str, object]:
        snapshot = camera_worker.freeze_latest_frame()
        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail=camera_worker.error or "Camera frame is not available yet",
            )
        remember_vision_frame(snapshot)
        event_log.add(f"Vision frame saved: {snapshot.frame_id}")
        return {"frame": vision_frame_metadata(snapshot)}

    @application.get("/api/vision/frames/{frame_id}/raw")
    async def vision_raw_frame(frame_id: int) -> Response:
        with vision_frame_lock:
            snapshot = saved_vision_frames.get(frame_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Saved vision frame not found")
        return Response(
            content=snapshot.jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @application.post("/api/vision/run")
    async def run_vision(payload: VisionRunRequest) -> dict[str, object]:
        if (
            not math.isfinite(payload.confidence_threshold)
            or not 0 <= payload.confidence_threshold <= 1
        ):
            raise HTTPException(
                status_code=422,
                detail="confidence_threshold must be between 0 and 1",
            )
        with vision_frame_lock:
            snapshot = saved_vision_frames.get(payload.frame_id)
        frame = camera_worker.frozen_bgr_frame(payload.frame_id)
        if snapshot is None or frame is None:
            raise HTTPException(status_code=404, detail="Saved vision frame not found")
        trace_id = f"frame-{payload.frame_id}"
        started_at = perf_counter()

        descriptors = [
            (detector, detector_descriptor(detector)) for detector in vision_detectors
        ]
        available_types = {descriptor["type"] for _, descriptor in descriptors}
        selected_types = (
            available_types
            if payload.detector_types is None
            else set(payload.detector_types)
        )
        unknown_types = selected_types - available_types
        if unknown_types:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown detector types: {', '.join(sorted(unknown_types))}",
            )
        selected_detectors = [
            detector
            for detector, descriptor in descriptors
            if descriptor["type"] in selected_types
        ]
        calibration = current_calibration()
        pipeline = VisionPipeline(
            PhoneScreenDetector(calibration),
            selected_detectors,
        )

        try:
            result = await asyncio.to_thread(pipeline.process, frame)
            detections = tuple(
                detection
                for detection in result.detections
                if detection.confidence >= payload.confidence_threshold
            )
            success, encoded = await asyncio.to_thread(
                cv2.imencode, ".jpg", result.rectified_image
            )
            if not success:
                raise ValueError("Could not encode rectified vision frame")
        except (CalibrationError, ValueError, cv2.error) as error:
            event_log.add(
                f"Vision replay error: {error}",
                level="error",
                event_type="vision.error",
                category="vision",
                status="error",
                trace_id=trace_id,
                latency_ms=(perf_counter() - started_at) * 1000,
                payload={"frame_id": payload.frame_id, "error": str(error)},
            )
            raise HTTPException(status_code=422, detail=str(error)) from error

        result_id = next(vision_result_ids)
        with vision_result_lock:
            vision_result_images[result_id] = encoded.tobytes()
            while len(vision_result_images) > 12:
                oldest_result_id = next(iter(vision_result_images))
                del vision_result_images[oldest_result_id]

        detector_names = {
            descriptor["type"]: descriptor["name"] for _, descriptor in descriptors
        }
        detection_values = []
        for index, detection in enumerate(detections, start=1):
            value = detection.to_dict()
            value.update(
                {
                    "id": f"result-{result_id}-detection-{index}",
                    "detector_name": detector_names.get(
                        detection.detector_type, detection.detector_type
                    ),
                }
            )
            detection_values.append(value)

        height, width = result.rectified_image.shape[:2]
        event_log.add(
            f"Vision detected {len(detection_values)} objects",
            event_type="vision.detected",
            category="vision",
            status="success",
            trace_id=trace_id,
            latency_ms=(perf_counter() - started_at) * 1000,
            payload={
                "frame_id": payload.frame_id,
                "result_id": result_id,
                "detector_types": sorted(selected_types),
                "confidence_threshold": payload.confidence_threshold,
                "detections": detection_values,
            },
        )
        return {
            "result_id": result_id,
            "frame": vision_frame_metadata(snapshot),
            "rectified": {"width": width, "height": height},
            "detector_types": sorted(selected_types),
            "confidence_threshold": payload.confidence_threshold,
            "detections": detection_values,
        }

    @application.get("/api/vision/results/{result_id}/rectified")
    async def vision_rectified_result(result_id: int) -> Response:
        with vision_result_lock:
            jpeg = vision_result_images.get(result_id)
        if jpeg is None:
            raise HTTPException(status_code=404, detail="Vision result not found")
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    def model_status_response() -> dict[str, object]:
        return {
            "provider": traced_model_client.provider,
            "model_name": traced_model_client.model_name,
            "connected": traced_model_client.connected,
            "last_latency_ms": traced_model_client.last_latency_ms,
            "confidence_threshold": decision_policy.confidence_threshold,
            "execution_default": False,
        }

    def raw_model_response_value() -> object:
        raw = traced_model_client.last_raw_response
        if isinstance(raw, Decision):
            return raw.to_dict()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        if raw is None or isinstance(raw, (str, dict)):
            return raw
        return repr(raw)

    def model_gate_response(result: DecisionResult) -> dict[str, object]:
        decision = result.decision
        schema_passed: bool | None = (
            False
            if result.status == "invalid_model_output"
            else (True if decision is not None else None)
        )
        confidence_passed = (
            None
            if decision is None
            else decision.confidence >= decision_policy.confidence_threshold
        )
        target_passed: bool | None = None
        if decision is not None and decision.action.value == "tap_target":
            target_passed = result.resolved_target is not None
        return {
            "schema_valid": {
                "passed": schema_passed,
                "reason": (
                    result.error
                    if schema_passed is False
                    else (
                        "Structured decision schema accepted"
                        if schema_passed
                        else "Schema was not evaluated"
                    )
                ),
            },
            "confidence_threshold": {
                "passed": confidence_passed,
                "reason": (
                    "No parsed confidence"
                    if confidence_passed is None
                    else (
                        f"Confidence meets {decision_policy.confidence_threshold:.2f} threshold"
                        if confidence_passed
                        else f"Confidence is below {decision_policy.confidence_threshold:.2f} threshold"
                    )
                ),
            },
            "target_resolved": {
                "passed": target_passed,
                "reason": (
                    "Target resolution is not required"
                    if target_passed is None
                    else (
                        "Target resolved to a trusted screen coordinate"
                        if target_passed
                        else "Target was not found in trusted detections or ROIs"
                    )
                ),
            },
            "action_created": {
                "passed": result.action is not None,
                "reason": (
                    f"Created {type(result.action).__name__}"
                    if result.action is not None
                    else f"No action created: {result.status}"
                ),
            },
        }

    @application.get("/api/model/status")
    async def model_status() -> dict[str, object]:
        return model_status_response()

    @application.post("/api/model/run")
    async def run_model(payload: ModelRunRequest) -> dict[str, object]:
        if payload.frame_id is None:
            snapshot = camera_worker.freeze_latest_frame()
            if snapshot is None:
                raise HTTPException(
                    status_code=503,
                    detail=camera_worker.error or "Camera frame is not available yet",
                )
            remember_vision_frame(snapshot)
        else:
            with vision_frame_lock:
                snapshot = saved_vision_frames.get(payload.frame_id)
            if snapshot is None:
                raise HTTPException(status_code=404, detail="Saved model frame not found")

        trace_id = f"frame-{snapshot.frame_id}"
        frame = camera_worker.frozen_bgr_frame(snapshot.frame_id)
        if frame is None:
            raise HTTPException(status_code=404, detail="Saved model frame not found")
        calibration = current_calibration()
        pipeline = VisionPipeline(
            PhoneScreenDetector(calibration),
            vision_detectors,
        )
        vision_started_at = perf_counter()
        try:
            vision_result = await asyncio.to_thread(pipeline.process, frame)
            success, encoded = await asyncio.to_thread(
                cv2.imencode, ".jpg", vision_result.rectified_image
            )
            if not success:
                raise ValueError("Could not encode model input frame")
        except (CalibrationError, ValueError, cv2.error) as error:
            event_log.add(
                f"Model input error: {error}",
                level="error",
                event_type="model.error",
                category="model",
                status="error",
                trace_id=trace_id,
                payload={"frame_id": snapshot.frame_id, "error": str(error)},
            )
            raise HTTPException(status_code=422, detail=str(error)) from error

        event_log.add(
            f"Vision detected {len(vision_result.detections)} objects for model input",
            event_type="vision.detected",
            category="vision",
            status="success",
            trace_id=trace_id,
            latency_ms=(perf_counter() - vision_started_at) * 1000,
            payload={
                "frame_id": snapshot.frame_id,
                "source": "model_debug",
                "detections": [
                    detection.to_dict() for detection in vision_result.detections
                ],
            },
        )

        height, width = vision_result.rectified_image.shape[:2]
        model_context = dict(payload.context or {})
        model_context.update(
            {
                "debug_replay": True,
                "source_frame_id": snapshot.frame_id,
                "captured_at": snapshot.captured_at,
                "screen_size": {"width": width, "height": height},
                "detections": [
                    detection.to_dict() for detection in vision_result.detections
                ],
            }
        )
        engine = DecisionEngine(
            traced_model_client,
            TargetResolver(minimum_detection_confidence=0.5),
            calibration,
            policy=decision_policy,
        )
        event_log.add(
            f"Model request: {traced_model_client.model_name}",
            event_type="model.request",
            category="model",
            status="pending",
            trace_id=trace_id,
            payload={
                "frame_id": snapshot.frame_id,
                "provider": traced_model_client.provider,
                "model_name": traced_model_client.model_name,
                "context": model_context,
            },
        )

        def decide_without_execution() -> tuple[
            DecisionResult, object, dict[str, object]
        ]:
            with model_debug_lock:
                decision_result = engine.decide(
                    vision_result.rectified_image,
                    model_context,
                    vision_result.detections,
                )
                return (
                    decision_result,
                    raw_model_response_value(),
                    model_status_response(),
                )

        result, raw_response, run_model_status = await asyncio.to_thread(
            decide_without_execution
        )
        model_result_id = next(model_result_ids)
        with model_result_lock:
            model_input_images[model_result_id] = encoded.tobytes()
            while len(model_input_images) > 12:
                oldest_result_id = next(iter(model_input_images))
                del model_input_images[oldest_result_id]

        resolved_target = None
        if result.resolved_target is not None:
            resolved_target = {
                "name": result.resolved_target.name,
                "center": {
                    "x": result.resolved_target.center.x,
                    "y": result.resolved_target.center.y,
                },
                "source": result.resolved_target.source,
            }
        resolved_action = None
        if result.action is not None:
            resolved_action = {
                "type": type(result.action).__name__,
                "parameters": asdict(result.action),
            }
        execution_reason = (
            "Action passed all gates, but Model Debug never executes robot actions"
            if result.execution_allowed
            else result.error or f"Blocked by decision status: {result.status}"
        )
        event_log.add(
            f"Model decision: {result.status}",
            level=("error" if result.status == "invalid_model_output" else "info"),
            event_type="model.decision",
            category="model",
            status=(
                "error"
                if result.status == "invalid_model_output"
                else ("success" if result.execution_allowed else "blocked")
            ),
            trace_id=trace_id,
            latency_ms=traced_model_client.last_latency_ms,
            payload={
                "frame_id": snapshot.frame_id,
                "run_id": model_result_id,
                "decision": (
                    None if result.decision is None else result.decision.to_dict()
                ),
                "raw_response": raw_response,
                "status": result.status,
                "error": result.error,
            },
        )
        if result.action is not None:
            event_log.add(
                f"Action created: {type(result.action).__name__}",
                event_type="action.created",
                category="model",
                status="success",
                trace_id=trace_id,
                payload={
                    "action": type(result.action).__name__,
                    "parameters": asdict(result.action),
                    "execution_requested": False,
                    "execution_allowed": result.execution_allowed,
                },
            )
        return {
            "run_id": model_result_id,
            "model": run_model_status,
            "frame": vision_frame_metadata(snapshot),
            "input": {
                "image_id": result.image_id,
                "width": width,
                "height": height,
            },
            "context": model_context,
            "raw_response": raw_response,
            "decision": (
                None if result.decision is None else result.decision.to_dict()
            ),
            "resolved_target": resolved_target,
            "resolved_action": resolved_action,
            "gates": model_gate_response(result),
            "execution": {
                "allowed": result.execution_allowed,
                "requested": False,
                "executed": False,
                "reason": execution_reason,
            },
            "status": result.status,
            "error": result.error,
        }

    @application.get("/api/model/runs/{run_id}/input")
    async def model_input_image(run_id: int) -> Response:
        with model_result_lock:
            jpeg = model_input_images.get(run_id)
        if jpeg is None:
            raise HTTPException(status_code=404, detail="Model input image not found")
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    async def latest_vision_result() -> VisionResult:
        frame = camera_worker.latest_bgr_frame()
        if frame is None:
            raise HTTPException(
                status_code=503,
                detail=camera_worker.error or "Camera frame is not available yet",
            )
        calibration = current_calibration()
        pipeline = VisionPipeline(
            PhoneScreenDetector(calibration),
            vision_detectors,
        )
        try:
            return await asyncio.to_thread(pipeline.process, frame)
        except (CalibrationError, ValueError) as error:
            event_log.add(f"Vision processing error: {error}", level="error")
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/vision/detections")
    async def vision_detections() -> dict[str, object]:
        result = await latest_vision_result()
        height, width = result.rectified_image.shape[:2]
        return {
            "screen": {"width": width, "height": height},
            "detections": [detection.to_dict() for detection in result.detections],
        }

    @application.get("/api/vision/debug")
    async def vision_debug() -> Response:
        result = await latest_vision_result()

        def render_overlay() -> bytes:
            overlay = draw_debug_overlay(
                result.rectified_image,
                result.detections,
            )
            success, encoded = cv2.imencode(".jpg", overlay)
            if not success:
                raise ValueError("Could not encode vision debug overlay")
            return encoded.tobytes()

        try:
            jpeg = await asyncio.to_thread(render_overlay)
        except (cv2.error, ValueError) as error:
            event_log.add(f"Vision overlay error: {error}", level="error")
            raise HTTPException(status_code=500, detail=str(error)) from error
        return Response(content=jpeg, media_type="image/jpeg")

    def validate_coordinates(payload: CoordinateRequest) -> None:
        if not math.isfinite(payload.x) or not math.isfinite(payload.y):
            event_log.add("Coordinate validation error: coordinates must be finite", level="error")
            raise HTTPException(status_code=422, detail="Coordinates must be finite")
        if not bounds.min_x <= payload.x <= bounds.max_x:
            event_log.add(f"Coordinate validation error: X={payload.x}", level="error")
            raise HTTPException(
                status_code=422,
                detail=f"X must be between {bounds.min_x} and {bounds.max_x}",
            )
        if not bounds.min_y <= payload.y <= bounds.max_y:
            event_log.add(f"Coordinate validation error: Y={payload.y}", level="error")
            raise HTTPException(
                status_code=422,
                detail=f"Y must be between {bounds.min_y} and {bounds.max_y}",
            )

    async def dispatch(action: Action, user_message: str) -> dict[str, object]:
        trace_id = f"manual-{next(operation_trace_ids)}"
        event_log.add(
            f"User command: {user_message}",
            event_type="action.request",
            category="robot",
            status="info",
            trace_id=trace_id,
            payload={"command": user_message},
        )
        event_log.add(
            f"Action created: {action}",
            event_type="action.created",
            category="robot",
            status="success",
            trace_id=trace_id,
            payload={
                "action": type(action).__name__,
                "parameters": asdict(action),
            },
        )
        event_log.add(
            f"Robot command: {type(action).__name__}",
            event_type="robot.command",
            category="robot",
            status="pending",
            trace_id=trace_id,
            payload={
                "action": type(action).__name__,
                "parameters": asdict(action),
            },
        )
        try:
            await asyncio.to_thread(dispatcher.submit, action, trace_id=trace_id)
        except Exception as error:
            event_log.add(
                f"Command failed: {error}",
                level="error",
                event_type="robot.error",
                category="robot",
                status="error",
                trace_id=trace_id,
                payload={"action": type(action).__name__, "error": str(error)},
            )
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {"ok": True, "action": type(action).__name__}

    @application.post("/api/robot/move")
    async def move(payload: CoordinateRequest) -> dict[str, object]:
        validate_coordinates(payload)
        result = await dispatch(
            MoveAction(payload.x, payload.y), f"move({payload.x}, {payload.y})"
        )
        with robot_state_lock:
            robot_state.update(x=payload.x, y=payload.y, last_command="move")
        return result

    @application.post("/api/robot/tap")
    async def tap(payload: CoordinateRequest) -> dict[str, object]:
        validate_coordinates(payload)
        result = await dispatch(
            TapAction(payload.x, payload.y), f"tap({payload.x}, {payload.y})"
        )
        with robot_state_lock:
            robot_state.update(
                x=payload.x, y=payload.y, pen="up", last_command="tap"
            )
        return result

    @application.post("/api/robot/home")
    async def home() -> dict[str, object]:
        result = await dispatch(HomeAction(), "home")
        with robot_state_lock:
            robot_state.update(x=0.0, y=0.0, homed=True, last_command="home")
        return result

    @application.post("/api/robot/pen/up")
    async def pen_up() -> dict[str, object]:
        result = await dispatch(PenUpAction(), "pen up")
        with robot_state_lock:
            robot_state.update(pen="up", last_command="pen up")
        return result

    @application.post("/api/robot/pen/down")
    async def pen_down() -> dict[str, object]:
        result = await dispatch(PenDownAction(), "pen down")
        with robot_state_lock:
            robot_state.update(pen="down", last_command="pen down")
        return result

    @application.post("/api/robot/stop")
    async def stop() -> dict[str, object]:
        result = await dispatch(EmergencyStopAction(), "EMERGENCY STOP")
        with robot_state_lock:
            robot_state.update(homed=False, pen="unknown", last_command="emergency stop")
        return result

    return application


app = create_app()


def _parse_camera_source(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TapBot control UI")
    parser.add_argument(
        "--camera-source",
        "--camera",
        type=_parse_camera_source,
        default="mock:reservation-flow",
        help=(
            "source ID (opencv:0 or mock:reservation-flow), device index, "
            "image path, video path, or stream URL "
            "(default: mock:reservation-flow)"
        ),
    )
    parser.add_argument(
        "--camera-max-index",
        type=int,
        default=4,
        help="highest OpenCV device index included in discovery (default: 4)",
    )
    parser.add_argument("--camera-fps", type=float, default=5.0)
    parser.add_argument("--robot", choices=("mock", "grbl"), default="mock")
    parser.add_argument("--serial-port")
    parser.add_argument("--baud-rate", type=int, default=115200)
    parser.add_argument("--feed-rate", type=float, default=1000)
    parser.add_argument(
        "--workspace-width",
        type=float,
        help="robot workspace width (default: mock 1280, GRBL 300)",
    )
    parser.add_argument(
        "--workspace-height",
        type=float,
        help="robot workspace height (default: mock 720, GRBL 300)",
    )
    parser.add_argument("--tap-dwell-ms", type=int, default=150)
    parser.add_argument("--servo-down-command", default="M3")
    parser.add_argument("--servo-up-command", default="M5")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--calibration-file",
        default="tapbot-calibrations.json",
        help="versioned JSON calibration profile store",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    workspace_width = (
        args.workspace_width
        if args.workspace_width is not None
        else (1280.0 if args.robot == "mock" else 300.0)
    )
    workspace_height = (
        args.workspace_height
        if args.workspace_height is not None
        else (720.0 if args.robot == "mock" else 300.0)
    )

    robot_controller: RobotController
    if args.robot == "grbl":
        if not args.dry_run and not args.serial_port:
            parser.error("--serial-port is required for GRBL unless --dry-run is used")
        robot_config = GrblRobotConfig(
            feed_rate_mm_per_min=args.feed_rate,
            workspace_width_mm=workspace_width,
            workspace_height_mm=workspace_height,
            tap_dwell_ms=args.tap_dwell_ms,
            servo_down_command=args.servo_down_command,
            servo_up_command=args.servo_up_command,
            dry_run=args.dry_run,
        )
        session = None
        if not args.dry_run:
            session = GrblSession(
                SerialTransport(
                    SerialTransportConfig(
                        port=args.serial_port,
                        baud_rate=args.baud_rate,
                    )
                )
            )
        robot_controller = GrblRobotController(session, robot_config)
    else:
        robot_controller = MockRobotController()

    application = create_app(
        robot=robot_controller,
        camera_manager=CameraManager.with_defaults(
            args.camera_source,
            discovery_max_index=args.camera_max_index,
        ),
        camera_fps=args.camera_fps,
        calibration_store=CalibrationStore(args.calibration_file),
        bounds=WorkspaceBounds(
            max_x=workspace_width,
            max_y=workspace_height,
        ),
    )
    uvicorn.run(application, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
