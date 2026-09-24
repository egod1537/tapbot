"""Pure G-code generation with no serial or hardware dependency."""

from dataclasses import dataclass
import math
from numbers import Real


@dataclass(frozen=True, slots=True)
class GCodeConfig:
    """Commands that may vary between GRBL/servo kits."""

    pen_down_command: str = "M3"
    pen_up_command: str = "M5"
    home_command: str = "$H"
    move_command: str = "G0"


class GCodeGenerator:
    """Generate individual GRBL-compatible G-code commands."""

    def __init__(self, config: GCodeConfig | None = None) -> None:
        self.config = config or GCodeConfig()

    def absolute_mode(self) -> str:
        """Select absolute coordinate positioning."""

        return "G90"

    def move_to(
        self,
        x: float,
        y: float,
        *,
        feed_rate: float | None = None,
    ) -> str:
        """Generate an X/Y movement command."""

        self._validate_non_negative_number("x", x)
        self._validate_non_negative_number("y", y)
        command = (
            f"{self.config.move_command} "
            f"X{self._format_number(x)} Y{self._format_number(y)}"
        )
        if feed_rate is not None:
            self._validate_non_negative_number("feed_rate", feed_rate)
            if feed_rate == 0:
                raise ValueError("feed_rate must be positive")
            command += f" F{self._format_number(feed_rate)}"
        return command

    def absolute_move_to(self, x: float, y: float) -> tuple[str, str]:
        """Generate a self-contained absolute X/Y movement sequence."""

        return self.absolute_mode(), self.move_to(x, y)

    def pen_down(self) -> str:
        return self.config.pen_down_command

    def pen_up(self) -> str:
        return self.config.pen_up_command

    def dwell(self, duration_ms: int) -> str:
        """Generate a GRBL dwell command, with P expressed in seconds."""

        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise ValueError("duration_ms must be an integer")
        if duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        seconds = duration_ms / 1000
        return f"G4 P{self._format_number(seconds)}"

    def home(self) -> str:
        return self.config.home_command

    @staticmethod
    def _validate_non_negative_number(name: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a real number")
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
        if value < 0:
            raise ValueError(f"{name} must not be negative")

    @staticmethod
    def _format_number(value: Real) -> str:
        return format(float(value), ".15g")
