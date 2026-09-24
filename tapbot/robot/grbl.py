"""GRBL protocol session and RobotController implementation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import math
from numbers import Real
from threading import Event, Lock
import time

from tapbot.robot.controller import RobotController
from tapbot.robot.gcode import GCodeConfig, GCodeGenerator
from tapbot.robot.transport import Transport, TransportTimeoutError


logger = logging.getLogger(__name__)


class GrblError(RuntimeError):
    """Base class for GRBL session and controller errors."""


class GrblConnectionError(GrblError):
    """Raised when GRBL initialization or state checking fails."""


class GrblResponseTimeoutError(GrblError):
    """Raised when GRBL does not acknowledge a command in time."""


class GrblCommandError(GrblError):
    """Raised for an explicit ``error:`` response."""

    def __init__(self, command: str, response: str) -> None:
        self.command = command
        self.response = response
        super().__init__(f"GRBL rejected {command!r}: {response}")


class GrblAlarmError(GrblError):
    """Raised when GRBL reports an alarm while handling a command."""


class GrblEmergencyStopError(GrblError):
    """Raised when a normal command is interrupted by emergency stop."""


class RobotCoordinateError(ValueError):
    """Raised before transmission when a point is outside the work area."""


@dataclass(frozen=True, slots=True)
class GrblStatus:
    state: str
    fields: dict[str, str]
    raw: str

    @classmethod
    def parse(cls, line: str) -> GrblStatus:
        if not line.startswith("<") or not line.endswith(">"):
            raise GrblConnectionError(f"Invalid GRBL status response: {line!r}")
        parts = line[1:-1].split("|")
        if not parts or not parts[0]:
            raise GrblConnectionError(f"Invalid GRBL status response: {line!r}")
        fields: dict[str, str] = {}
        for part in parts[1:]:
            key, separator, value = part.partition(":")
            if separator:
                fields[key] = value
        return cls(parts[0], fields, line)


@dataclass(frozen=True, slots=True)
class GrblSessionConfig:
    command_timeout_s: float = 5.0
    status_timeout_s: float = 3.0
    wakeup_delay_s: float = 2.0

    def __post_init__(self) -> None:
        if self.command_timeout_s <= 0 or self.status_timeout_s <= 0:
            raise ValueError("GRBL timeouts must be positive")
        if self.wakeup_delay_s < 0:
            raise ValueError("wakeup_delay_s must not be negative")


class GrblSession:
    """Track GRBL send-response acknowledgements and realtime controls."""

    def __init__(
        self,
        transport: Transport,
        config: GrblSessionConfig | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.transport = transport
        self.config = config or GrblSessionConfig()
        self._monotonic = monotonic
        self._sleep = sleep
        self._command_lock = Lock()
        self._emergency_stop = Event()
        self._ready = False
        self.last_status: GrblStatus | None = None

    def connect(self) -> GrblStatus:
        self.transport.connect()
        self._emergency_stop.clear()
        self._ready = False
        # GRBL realtime bytes never receive a CR/LF suffix.
        self.transport.send_realtime(b"\r\n\r\n")
        if self.config.wakeup_delay_s:
            self._sleep(self.config.wakeup_delay_s)
        try:
            status = self.query_status(timeout_s=self.config.status_timeout_s)
        except Exception as error:
            self.transport.close()
            raise GrblConnectionError(
                f"Connected transport but could not read initial GRBL status: {error}"
            ) from error
        self.last_status = status
        self._ready = True
        logger.info("GRBL connected with initial status: %s", status.raw)
        return status

    def execute(self, command: str, *, timeout_s: float | None = None) -> tuple[str, ...]:
        if not command or "\n" in command or "\r" in command:
            raise ValueError("GRBL command must be one non-empty line")
        if not self._ready or not self.transport.is_connected:
            raise GrblConnectionError("GRBL session is not ready")
        timeout = timeout_s or self.config.command_timeout_s
        messages: list[str] = []
        with self._command_lock:
            if self._emergency_stop.is_set():
                raise GrblEmergencyStopError("GRBL session was emergency-stopped")
            self.transport.send_line(command)
            deadline = self._monotonic() + timeout
            while True:
                if self._emergency_stop.is_set():
                    raise GrblEmergencyStopError(
                        f"GRBL command interrupted by emergency stop: {command!r}"
                    )
                line = self._read_before(deadline, f"acknowledging {command!r}")
                if self._emergency_stop.is_set():
                    raise GrblEmergencyStopError(
                        f"GRBL command interrupted by emergency stop: {command!r}"
                    )
                if line == "ok":
                    logger.info("GRBL acknowledged: %s", command)
                    return tuple(messages)
                if line.startswith("error:"):
                    raise GrblCommandError(command, line)
                if line.startswith("ALARM:"):
                    raise GrblAlarmError(
                        f"GRBL alarm while executing {command!r}: {line}"
                    )
                if line.startswith("<") and line.endswith(">"):
                    self.last_status = GrblStatus.parse(line)
                messages.append(line)

    def query_status(self, *, timeout_s: float | None = None) -> GrblStatus:
        if not self.transport.is_connected:
            raise GrblConnectionError("GRBL transport is not connected")
        with self._command_lock:
            self.transport.send_realtime(b"?")
            deadline = self._monotonic() + (timeout_s or self.config.status_timeout_s)
            while True:
                line = self._read_before(deadline, "waiting for status")
                if line.startswith("<") and line.endswith(">"):
                    status = GrblStatus.parse(line)
                    self.last_status = status
                    return status
                if line.startswith("error:"):
                    raise GrblConnectionError(f"GRBL status query failed: {line}")

    def emergency_stop(self) -> None:
        """Bypass the line queue with feed hold followed by GRBL soft reset."""

        if not self.transport.is_connected:
            raise GrblConnectionError("GRBL transport is not connected")
        self._emergency_stop.set()
        self._ready = False
        hold_error: Exception | None = None
        try:
            self.transport.send_realtime(b"!")
        except Exception as error:
            hold_error = error
        # Always attempt the reset even if the feed-hold write reported an
        # error. The transport remains the authority on whether it succeeded.
        self.transport.send_realtime(b"\x18")
        if hold_error is not None:
            raise GrblError(
                f"Soft reset was attempted after feed hold failed: {hold_error}"
            ) from hold_error
        logger.critical("GRBL emergency stop sent: feed hold + soft reset")

    def close(self) -> None:
        self._ready = False
        self.transport.close()

    @property
    def is_ready(self) -> bool:
        return self._ready and self.transport.is_connected

    def _read_before(self, deadline: float, operation: str) -> str:
        while True:
            if self._monotonic() >= deadline:
                raise GrblResponseTimeoutError(f"Timed out {operation}")
            try:
                line = self.transport.read_line()
            except TransportTimeoutError:
                continue
            if line:
                return line


@dataclass(frozen=True, slots=True)
class GrblRobotConfig:
    feed_rate_mm_per_min: float = 1000
    workspace_width_mm: float = 300
    workspace_height_mm: float = 300
    tap_dwell_ms: int = 150
    servo_down_command: str = "M3"
    servo_up_command: str = "M5"
    movement_command: str = "G1"
    negative_coordinate_policy: str = "reject"
    dry_run: bool = False

    def __post_init__(self) -> None:
        numeric = (
            self.feed_rate_mm_per_min,
            self.workspace_width_mm,
            self.workspace_height_mm,
        )
        if not all(math.isfinite(value) and value > 0 for value in numeric):
            raise ValueError("feed rate and workspace dimensions must be positive and finite")
        if isinstance(self.tap_dwell_ms, bool) or not isinstance(self.tap_dwell_ms, int):
            raise ValueError("tap_dwell_ms must be an integer")
        if self.tap_dwell_ms < 0:
            raise ValueError("tap_dwell_ms must not be negative")
        if self.negative_coordinate_policy != "reject":
            raise ValueError("Only the safe negative-coordinate policy 'reject' is supported")
        for name, command in (
            ("servo_down_command", self.servo_down_command),
            ("servo_up_command", self.servo_up_command),
            ("movement_command", self.movement_command),
        ):
            if not command or "\n" in command or "\r" in command:
                raise ValueError(f"{name} must be one non-empty line")


class GrblRobotController(RobotController):
    """RobotController backed by an acknowledged GRBL session."""

    def __init__(
        self,
        session: GrblSession | None,
        config: GrblRobotConfig | None = None,
    ) -> None:
        self.config = config or GrblRobotConfig()
        if session is None and not self.config.dry_run:
            raise ValueError("A GRBL session is required unless dry_run is enabled")
        self.session = session
        self.generated_commands: list[str] = []
        self._dry_connected = False
        self._generator = GCodeGenerator(
            GCodeConfig(
                pen_down_command=self.config.servo_down_command,
                pen_up_command=self.config.servo_up_command,
                move_command=self.config.movement_command,
            )
        )

    def connect(self) -> GrblStatus | None:
        if self.config.dry_run:
            self._dry_connected = True
            logger.info("GRBL dry-run connected; no transport opened")
            return None
        assert self.session is not None
        return self.session.connect()

    def close(self) -> None:
        self._dry_connected = False
        if self.session is not None:
            self.session.close()

    @property
    def is_connected(self) -> bool:
        return (self.config.dry_run and self._dry_connected) or (
            self.session is not None and self.session.is_ready
        )

    def home(self) -> None:
        self._send(self._generator.home())
        self._send(self._generator.absolute_mode())

    def move_to(self, x: float, y: float) -> None:
        self._validate_coordinates(x, y)
        self._send(self._generator.absolute_mode())
        self._send(
            self._generator.move_to(
                x,
                y,
                feed_rate=self.config.feed_rate_mm_per_min,
            )
        )

    def tap(self, x: float, y: float) -> None:
        self.move_to(x, y)
        self.pen_down()
        try:
            self._send(self._generator.dwell(self.config.tap_dwell_ms))
        finally:
            self.pen_up()

    def pen_down(self) -> None:
        self._send(self._generator.pen_down())

    def pen_up(self) -> None:
        self._send(self._generator.pen_up())

    def emergency_stop(self) -> None:
        if self.config.dry_run:
            self.generated_commands.extend(["!", "<CTRL-X>"])
            logger.warning("GRBL dry-run emergency stop: !, Ctrl-X")
            return
        assert self.session is not None
        self.session.emergency_stop()

    def execute_raw(self, command: str) -> tuple[str, ...]:
        """Execute a command already approved by the console safety policy."""

        self.generated_commands.append(command)
        if self.config.dry_run:
            logger.info("GRBL dry-run raw command: %s", command)
            return ("dry-run: command validated; transport write skipped",)
        assert self.session is not None
        return self.session.execute(command)

    def query_raw_status(self) -> str:
        """Read status through GRBL's realtime query path."""

        if self.config.dry_run:
            return "<DryRun|MPos:0.000,0.000,0.000>"
        assert self.session is not None
        return self.session.query_status().raw

    def _send(self, command: str) -> None:
        self.generated_commands.append(command)
        if self.config.dry_run:
            logger.info("GRBL dry-run command: %s", command)
            return
        assert self.session is not None
        self.session.execute(command)

    def _validate_coordinates(self, x: float, y: float) -> None:
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, Real)
            or not isinstance(y, Real)
        ):
            raise RobotCoordinateError("Robot coordinates must be real numbers")
        if not math.isfinite(x) or not math.isfinite(y):
            raise RobotCoordinateError("Robot coordinates must be finite")
        if x < 0 or y < 0:
            raise RobotCoordinateError(
                "Negative robot coordinates are rejected by policy"
            )
        if x > self.config.workspace_width_mm:
            raise RobotCoordinateError(
                f"X={x} exceeds workspace width {self.config.workspace_width_mm}"
            )
        if y > self.config.workspace_height_mm:
            raise RobotCoordinateError(
                f"Y={y} exceeds workspace height {self.config.workspace_height_mm}"
            )
