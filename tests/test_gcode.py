import pytest

from tapbot.robot.gcode import GCodeConfig, GCodeGenerator


def test_generates_absolute_xy_move() -> None:
    generator = GCodeGenerator()

    assert generator.absolute_move_to(100, 200) == ("G90", "G0 X100 Y200")


def test_generates_configured_feed_rate() -> None:
    assert GCodeGenerator().move_to(10, 20, feed_rate=500) == "G0 X10 Y20 F500"


def test_generates_default_pen_commands() -> None:
    generator = GCodeGenerator()

    assert generator.pen_down() == "M3"
    assert generator.pen_up() == "M5"


def test_servo_commands_are_configurable() -> None:
    generator = GCodeGenerator(
        GCodeConfig(pen_down_command="M3 S90", pen_up_command="M3 S0")
    )

    assert generator.pen_down() == "M3 S90"
    assert generator.pen_up() == "M3 S0"


def test_generates_dwell_in_seconds() -> None:
    assert GCodeGenerator().dwell(250) == "G4 P0.25"


def test_generates_home() -> None:
    assert GCodeGenerator().home() == "$H"


@pytest.mark.parametrize("duration_ms", [-1, 1.5, True])
def test_rejects_invalid_dwell(duration_ms: object) -> None:
    with pytest.raises(ValueError):
        GCodeGenerator().dwell(duration_ms)  # type: ignore[arg-type]


@pytest.mark.parametrize("x, y", [(-1, 0), (0, -1), (float("inf"), 0)])
def test_rejects_invalid_move(x: float, y: float) -> None:
    with pytest.raises(ValueError):
        GCodeGenerator().move_to(x, y)
