from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pytest

from tapbot.robot.grbl import (
    GrblAlarmError,
    GrblCommandError,
    GrblEmergencyStopError,
    GrblResponseTimeoutError,
    GrblRobotConfig,
    GrblRobotController,
    GrblSession,
    GrblSessionConfig,
    RobotCoordinateError,
)
from tapbot.robot.hardware_check import run_hardware_check
from tapbot.robot.transport import MockTransport, Transport, TransportTimeoutError


def make_session(
    responses: list[str | BaseException],
) -> tuple[GrblSession, MockTransport]:
    transport = MockTransport(responses)
    session = GrblSession(
        transport,
        GrblSessionConfig(
            command_timeout_s=0.03,
            status_timeout_s=0.03,
            wakeup_delay_s=0,
        ),
    )
    return session, transport


def test_connect_checks_initial_status() -> None:
    session, transport = make_session(
        ["Grbl 1.1h ['$' for help]", "<Idle|MPos:0.000,0.000,0.000|FS:0,0>"]
    )

    status = session.connect()

    assert status.state == "Idle"
    assert status.fields["MPos"] == "0.000,0.000,0.000"
    assert transport.realtime_writes == [b"\r\n\r\n", b"?"]
    assert session.is_ready


def test_command_waits_for_ok_and_keeps_feedback_messages() -> None:
    session, transport = make_session(["<Idle|MPos:0,0,0>", "[MSG:ready]", "ok"])
    session.connect()

    messages = session.execute("G90")

    assert messages == ("[MSG:ready]",)
    assert transport.sent_lines == ["G90"]


@pytest.mark.parametrize(
    "response,error_type",
    [("error:2", GrblCommandError), ("ALARM:1", GrblAlarmError)],
)
def test_error_and_alarm_responses_are_not_ignored(
    response: str,
    error_type: type[Exception],
) -> None:
    session, _ = make_session(["<Idle|MPos:0,0,0>", response])
    session.connect()

    with pytest.raises(error_type):
        session.execute("G1 X10")


def test_command_timeout_is_explicit() -> None:
    session, _ = make_session(["<Idle|MPos:0,0,0>"])
    session.connect()

    with pytest.raises(GrblResponseTimeoutError, match="Timed out"):
        session.execute("G90")


class BlockingTransport(Transport):
    def __init__(self) -> None:
        self.connected = False
        self.sent_lines: list[str] = []
        self.realtime_writes: list[bytes] = []
        self.command_read_started = Event()
        self.release_command_read = Event()
        self.initial_status_pending = True

    def connect(self) -> None:
        self.connected = True

    def send_line(self, command: str) -> None:
        self.sent_lines.append(command)

    def read_line(self) -> str:
        if self.initial_status_pending:
            self.initial_status_pending = False
            return "<Idle|MPos:0,0,0>"
        self.command_read_started.set()
        self.release_command_read.wait(2)
        return "ok"

    def send_realtime(self, data: bytes) -> None:
        self.realtime_writes.append(data)
        if data == b"!":
            self.release_command_read.set()

    def close(self) -> None:
        self.connected = False

    @property
    def is_connected(self) -> bool:
        return self.connected


def test_emergency_stop_bypasses_blocked_command_and_uses_realtime_bytes() -> None:
    transport = BlockingTransport()
    session = GrblSession(
        transport,
        GrblSessionConfig(wakeup_delay_s=0),
    )
    session.connect()

    with ThreadPoolExecutor(max_workers=1) as pool:
        command = pool.submit(session.execute, "G1 X100 F500")
        assert transport.command_read_started.wait(1)
        before = time.monotonic()
        session.emergency_stop()
        elapsed = time.monotonic() - before
        with pytest.raises(GrblEmergencyStopError):
            command.result(1)

    assert elapsed < 0.1
    assert transport.realtime_writes[-2:] == [b"!", b"\x18"]
    assert not session.is_ready


def test_dry_run_generates_configured_gcode_without_transport() -> None:
    controller = GrblRobotController(
        None,
        GrblRobotConfig(
            feed_rate_mm_per_min=500,
            workspace_width_mm=200,
            workspace_height_mm=300,
            tap_dwell_ms=150,
            servo_down_command="M3 S90",
            servo_up_command="M3 S0",
            dry_run=True,
        ),
    )
    controller.connect()

    controller.home()
    controller.tap(100, 200)

    assert controller.generated_commands == [
        "$H",
        "G90",
        "G90",
        "G1 X100 Y200 F500",
        "M3 S90",
        "G4 P0.15",
        "M3 S0",
    ]


@pytest.mark.parametrize(
    "x,y",
    [(-1, 0), (0, -1), (201, 0), (0, 301), (float("nan"), 0)],
)
def test_workspace_violation_is_blocked_before_command_generation(
    x: float,
    y: float,
) -> None:
    controller = GrblRobotController(
        None,
        GrblRobotConfig(
            workspace_width_mm=200,
            workspace_height_mm=300,
            dry_run=True,
        ),
    )

    with pytest.raises(RobotCoordinateError):
        controller.move_to(x, y)

    assert controller.generated_commands == []


def test_controller_sends_each_command_and_propagates_device_error() -> None:
    session, transport = make_session(
        ["<Idle|MPos:0,0,0>", "ok", "error:15"]
    )
    controller = GrblRobotController(session)
    controller.connect()

    with pytest.raises(GrblCommandError):
        controller.move_to(10, 20)

    assert transport.sent_lines == ["G90", "G1 X10 Y20 F1000"]


def test_hardware_check_follows_safe_order_in_dry_run() -> None:
    controller = GrblRobotController(
        None,
        GrblRobotConfig(feed_rate_mm_per_min=500, dry_run=True),
    )

    completed = run_hardware_check(
        controller,
        confirm=lambda _description: True,
    )

    assert completed is True
    assert controller.generated_commands[:6] == [
        "$H",
        "G90",
        "G90",
        "G1 X5 Y0 F500",
        "G90",
        "G1 X5 Y5 F500",
    ]
    assert controller.generated_commands.count("M3") == 3
    assert controller.generated_commands.count("M5") == 4
