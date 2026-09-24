"""Reserved Wi-Fi transport boundary for a future protocol decision."""

from dataclasses import dataclass

from tapbot.robot.transport import Transport


@dataclass(frozen=True, slots=True)
class WiFiTransportConfig:
    host: str
    port: int
    timeout_s: float = 1.0


class WiFiTransport(Transport):
    """Interface placeholder; Wi-Fi framing is intentionally not selected yet."""

    def __init__(self, config: WiFiTransportConfig) -> None:
        self.config = config

    def connect(self) -> None:
        raise NotImplementedError("Wi-Fi GRBL transport is not implemented")

    def send_line(self, command: str) -> None:
        raise NotImplementedError("Wi-Fi GRBL transport is not implemented")

    def read_line(self) -> str:
        raise NotImplementedError("Wi-Fi GRBL transport is not implemented")

    def send_realtime(self, data: bytes) -> None:
        raise NotImplementedError("Wi-Fi GRBL transport is not implemented")

    def close(self) -> None:
        return None

    @property
    def is_connected(self) -> bool:
        return False
