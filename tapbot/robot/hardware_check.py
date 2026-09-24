"""Interactive, staged GRBL hardware validation CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from tapbot.robot.grbl import (
    GrblRobotConfig,
    GrblRobotController,
    GrblSession,
    GrblSessionConfig,
)
from tapbot.robot.serial_transport import SerialTransport, SerialTransportConfig


Confirmation = Callable[[str], bool]


def run_hardware_check(
    controller: GrblRobotController,
    *,
    step_mm: float = 5,
    tap_x: float = 5,
    tap_y: float = 5,
    confirm: Confirmation,
) -> bool:
    """Run the documented validation order, stopping on any declined step."""

    steps: list[tuple[str, Callable[[], None]]] = [
        ("Home the machine with the work area clear", controller.home),
        (f"Move X axis to X={step_mm} mm", lambda: controller.move_to(step_mm, 0)),
        (
            f"Move Y axis to Y={step_mm} mm",
            lambda: controller.move_to(step_mm, step_mm),
        ),
        ("Raise the pen/servo", controller.pen_up),
        ("Lower the pen/servo; verify minimum safe pressure", controller.pen_down),
        ("Raise the pen/servo again", controller.pen_up),
        (
            "Run a tap sequence with NO phone under the tool",
            lambda: controller.tap(tap_x, tap_y),
        ),
        (
            "Only after fixing the phone in the jig, perform one minimum-pressure tap",
            lambda: controller.tap(tap_x, tap_y),
        ),
    ]
    try:
        status = controller.connect()
        print(
            "Connected in dry-run mode"
            if status is None
            else f"Connected. Initial GRBL status: {status.raw}"
        )
        for description, operation in steps:
            if not confirm(description):
                print(f"Stopped before step: {description}")
                return False
            operation()
            print(f"Completed: {description}")
        return True
    finally:
        controller.close()


def _interactive_confirmation(description: str) -> bool:
    response = input(f"\n{description}\nType RUN to continue, or anything else to stop: ")
    return response.strip().upper() == "RUN"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a staged and interactive TapBot GRBL hardware check"
    )
    parser.add_argument("--serial-port", help="USB serial device, e.g. /dev/cu.usbserial-XXXX")
    parser.add_argument("--baud-rate", type=int, default=115200)
    parser.add_argument("--feed-rate", type=float, default=500)
    parser.add_argument("--workspace-width", type=float, default=300)
    parser.add_argument("--workspace-height", type=float, default=300)
    parser.add_argument("--tap-dwell-ms", type=int, default=150)
    parser.add_argument("--servo-down-command", default="M3")
    parser.add_argument("--servo-up-command", default="M5")
    parser.add_argument("--step-mm", type=float, default=5)
    parser.add_argument("--tap-x", type=float, default=5)
    parser.add_argument("--tap-y", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.serial_port:
        parser.error("--serial-port is required unless --dry-run is used")

    config = GrblRobotConfig(
        feed_rate_mm_per_min=args.feed_rate,
        workspace_width_mm=args.workspace_width,
        workspace_height_mm=args.workspace_height,
        tap_dwell_ms=args.tap_dwell_ms,
        servo_down_command=args.servo_down_command,
        servo_up_command=args.servo_up_command,
        dry_run=args.dry_run,
    )
    session = None
    if not args.dry_run:
        transport = SerialTransport(
            SerialTransportConfig(
                port=args.serial_port,
                baud_rate=args.baud_rate,
            )
        )
        session = GrblSession(transport, GrblSessionConfig())
    controller = GrblRobotController(session, config)
    try:
        completed = run_hardware_check(
            controller,
            step_mm=args.step_mm,
            tap_x=args.tap_x,
            tap_y=args.tap_y,
            confirm=(lambda _: True) if args.dry_run else _interactive_confirmation,
        )
    except Exception as error:
        print(f"Hardware check failed: {error}")
        return 1

    if args.dry_run:
        print("\nGenerated commands:")
        for command in controller.generated_commands:
            print(command)
    return 0 if completed else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
