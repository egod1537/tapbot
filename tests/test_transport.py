import pytest

from tapbot.robot.serial_transport import SerialTransport, SerialTransportConfig
from tapbot.robot.transport import MockTransport, TransportError, TransportTimeoutError
from tapbot.robot.wifi_transport import WiFiTransport, WiFiTransportConfig


class FakeSerial:
    def __init__(self, *, lines: list[bytes] | None = None, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.lines = list(lines or [])
        self.writes: list[bytes] = []
        self.flush_calls = 0
        self.close_calls = 0
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        self.flush_calls += 1

    def readline(self) -> bytes:
        return self.lines.pop(0) if self.lines else b""

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False


def test_serial_transport_writes_lines_and_realtime_bytes() -> None:
    created: list[FakeSerial] = []

    def factory(**kwargs: object) -> FakeSerial:
        connection = FakeSerial(lines=[b"ok\r\n"], **kwargs)
        created.append(connection)
        return connection

    transport = SerialTransport(
        SerialTransportConfig("/dev/cu.test", baud_rate=115200),
        serial_factory=factory,
    )

    transport.connect()
    transport.send_line("G90")
    transport.send_realtime(b"?")

    assert transport.read_line() == "ok"
    assert created[0].writes == [b"G90\n", b"?"]
    assert created[0].kwargs["port"] == "/dev/cu.test"
    assert created[0].kwargs["baudrate"] == 115200
    transport.close()
    transport.close()
    assert created[0].close_calls == 1


def test_serial_transport_timeout_and_multiline_rejection() -> None:
    connection = FakeSerial()
    transport = SerialTransport(
        SerialTransportConfig("COM99"),
        serial_factory=lambda **_: connection,
    )
    transport.connect()

    with pytest.raises(TransportTimeoutError):
        transport.read_line()
    with pytest.raises(TransportError, match="one command"):
        transport.send_line("G90\nG0 X1")


def test_mock_transport_records_and_queues() -> None:
    transport = MockTransport(["ok"])
    transport.connect()

    transport.send_line("G90")
    transport.send_realtime(b"?")

    assert transport.read_line() == "ok"
    assert transport.sent_lines == ["G90"]
    assert transport.realtime_writes == [b"?"]


def test_wifi_transport_is_an_explicit_unimplemented_boundary() -> None:
    transport = WiFiTransport(WiFiTransportConfig("192.0.2.1", 23))

    with pytest.raises(NotImplementedError):
        transport.connect()
    assert not transport.is_connected
