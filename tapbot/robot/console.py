"""Safety policy and capability description for the developer G-code console."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re

from tapbot.robot.grbl import GrblRobotConfig, GrblRobotController


class GcodeConsoleError(ValueError):
    """Raised when a raw command is not permitted by the console policy."""


@dataclass(frozen=True, slots=True)
class GcodePreset:
    command: str
    label: str
    description: str
    category: str
    dangerous: bool = False


_MOTION_TOKEN = re.compile(
    r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
    flags=re.IGNORECASE,
)


def is_motion_console_command(command: str) -> bool:
    """Return whether a validated console command performs G0/G1 motion."""

    compact = re.sub(r"\s+", "", command.upper())
    tokens = _MOTION_TOKEN.findall(compact)
    return bool(
        tokens
        and tokens[0][0] == "G"
        and tokens[0][1] in {"0", "00", "1", "01"}
    )


def console_capabilities(
    controller: object,
    *,
    mode: str,
    connected: bool,
) -> dict[str, object]:
    if not isinstance(controller, GrblRobotController):
        return {
            "available": False,
            "mode": mode,
            "connected": connected,
            "firmware": None,
            "max_command_length": 120,
            "presets": [],
            "reason": "Raw console requires a GRBL controller",
        }

    config = controller.config
    presets = [
        GcodePreset("?", "Status", "Read current GRBL machine status", "diagnostic"),
        GcodePreset("$$", "Settings", "Read firmware settings", "diagnostic"),
        GcodePreset("$G", "Parser state", "Read active parser modes", "diagnostic"),
        GcodePreset("$#", "Offsets", "Read coordinate offsets", "diagnostic"),
        GcodePreset("$I", "Build info", "Read firmware build information", "diagnostic"),
        GcodePreset("$H", "Home", "Run the firmware homing cycle", "motion", True),
        GcodePreset(
            config.servo_up_command,
            "Pen up",
            "Send the configured pen-up command",
            "configured",
            True,
        ),
        GcodePreset(
            config.servo_down_command,
            "Pen down",
            "Send the configured pen-down command",
            "configured",
            True,
        ),
    ]
    unique_presets = {preset.command: preset for preset in presets}
    return {
        "available": True,
        "mode": mode,
        "connected": connected,
        "firmware": "GRBL",
        "max_command_length": 120,
        "presets": [asdict(preset) for preset in unique_presets.values()],
        "reason": None,
    }


def validate_console_command(command: str, config: GrblRobotConfig) -> str:
    value = command.strip()
    if not value:
        raise GcodeConsoleError("Command must not be empty")
    if len(value) > 120:
        raise GcodeConsoleError("Command exceeds the 120 character limit")
    if "\n" in value or "\r" in value:
        raise GcodeConsoleError("Only one command line may be sent at a time")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as error:
        raise GcodeConsoleError("Command must contain ASCII characters only") from error

    normalized = value.upper()
    if ";" in normalized or "(" in normalized or ")" in normalized:
        raise GcodeConsoleError("Inline comments are not permitted in raw commands")

    fixed_commands = {
        "?",
        "$$",
        "$G",
        "$#",
        "$I",
        "$N",
        "$H",
        "G90",
        config.servo_up_command.strip().upper(),
        config.servo_down_command.strip().upper(),
    }
    if normalized in fixed_commands:
        return normalized

    compact = re.sub(r"\s+", "", normalized)
    tokens = _MOTION_TOKEN.findall(compact)
    if not tokens or "".join(f"{letter}{number}" for letter, number in tokens) != compact:
        raise GcodeConsoleError("Command is not supported by the raw console policy")

    first_letter, first_value = tokens[0]
    if first_letter != "G" or first_value not in {"0", "00", "1", "01"}:
        raise GcodeConsoleError("Only absolute G0/G1 motion is supported")

    values: dict[str, float] = {}
    for letter, raw_value in tokens[1:]:
        if letter not in {"X", "Y", "F"}:
            raise GcodeConsoleError(f"Unsupported motion word: {letter}")
        if letter in values:
            raise GcodeConsoleError(f"Duplicate motion word: {letter}")
        numeric = float(raw_value)
        if not math.isfinite(numeric):
            raise GcodeConsoleError(f"{letter} must be finite")
        values[letter] = numeric

    if "X" not in values or "Y" not in values:
        raise GcodeConsoleError("Raw G0/G1 requires both X and Y coordinates")
    if not 0 <= values["X"] <= config.workspace_width_mm:
        raise GcodeConsoleError(
            f"X must be between 0 and {config.workspace_width_mm}"
        )
    if not 0 <= values["Y"] <= config.workspace_height_mm:
        raise GcodeConsoleError(
            f"Y must be between 0 and {config.workspace_height_mm}"
        )
    if "F" in values and values["F"] <= 0:
        raise GcodeConsoleError("Feed rate must be positive")
    return normalized
