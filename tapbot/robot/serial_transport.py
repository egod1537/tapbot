"""USB serial implementation of the GRBL transport."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

import serial

from tapbot.robot.transport import (
    Transport,
    TransportConnectionError,
    TransportError,
    TransportTimeoutError,
)


class SerialConnection(Protocol):
    is_open: bool

    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def readline(self) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SerialTransportConfig:
    port: str
    baud_rate: int = 115200
    read_timeout_s: float = 0.25
    write_timeout_s: float = 1.0

    def __post_init__(self) -> None:
        if not self.port.strip():
            raise ValueError("serial port must not be empty")
        if self.baud_rate <= 0:
            raise ValueError("baud_rate must be positive")
        if self.read_timeout_s <= 0 or self.write_timeout_s <= 0:
            raise ValueError("serial timeouts must be positive")


class SerialTransport(Transport):
    """pyserial-backed USB transport."""

    def __init__(
        self,
        config: SerialTransportConfig,
        *,
        serial_factory: Callable[..., SerialConnection] = serial.Serial,
    ) -> None:
        self.config = config
        self._serial_factory = serial_factory
        self._serial: SerialConnection | None = None
        self._write_lock = Lock()

    def connect(self) -> None:
        if self.is_connected:
            return
        try:
            self._serial = self._serial_factory(
                port=self.config.port,
                baudrate=self.config.baud_rate,
                timeout=self.config.read_timeout_s,
                write_timeout=self.config.write_timeout_s,
            )
        except (serial.SerialException, OSError) as error:
            self._serial = None
            raise TransportConnectionError(
                f"Could not open serial port {self.config.port!r}: {error}"
            ) from error
        if not self.is_connected:
            self.close()
            raise TransportConnectionError(
                f"Serial port did not open: {self.config.port!r}"
            )

    def send_line(self, command: str) -> None:
        if "\r" in command or "\n" in command:
            raise TransportError("send_line accepts exactly one command without a newline")
        try:
            payload = command.encode("ascii") + b"\n"
        except UnicodeEncodeError as error:
            raise TransportError("GRBL commands must contain ASCII characters only") from error
        self._write(payload)

    def send_realtime(self, data: bytes) -> None:
        if not data:
            raise TransportError("Realtime data must not be empty")
        self._write(data)

    def read_line(self) -> str:
        connection = self._require_connection()
        try:
            raw = connection.readline()
        except (serial.SerialException, OSError) as error:
            raise TransportError(f"Serial read failed: {error}") from error
        if not raw:
            raise TransportTimeoutError(
                f"Timed out reading from serial port {self.config.port!r}"
            )
        try:
            return raw.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise TransportError("GRBL returned non-ASCII serial data") from error

    def close(self) -> None:
        connection, self._serial = self._serial, None
        if connection is not None:
            try:
                connection.close()
            except (serial.SerialException, OSError) as error:
                raise TransportError(f"Could not close serial port: {error}") from error

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and bool(self._serial.is_open)

    def _write(self, payload: bytes) -> None:
        connection = self._require_connection()
        with self._write_lock:
            try:
                written = connection.write(payload)
                connection.flush()
            except (serial.SerialException, OSError) as error:
                raise TransportError(f"Serial write failed: {error}") from error
        if written != len(payload):
            raise TransportError(
                f"Incomplete serial write: wrote {written} of {len(payload)} bytes"
            )

    def _require_connection(self) -> SerialConnection:
        if not self.is_connected or self._serial is None:
            raise TransportConnectionError("Serial transport is not connected")
        return self._serial
