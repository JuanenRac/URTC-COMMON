# =============================================================================
# URTC-COMMON - tests/test_transports.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The transports, run against fakes: no serial port, no kernel interface and no adapter is needed."""
from __future__ import annotations

import errno
import socket
import struct
import threading
import time
import types

import pytest

from urtc_common import protocol, transports
from urtc_common.framing import CanFrame


# =============================================================================
# fakes
# =============================================================================
class FakeSerialException(Exception):
    pass


class FakeSerial:
    """The part of pyserial's Serial that SLCAN uses."""

    instances: list["FakeSerial"] = []

    def __init__(self, port, baudrate=9600, timeout=None):
        self.port, self.baudrate, self.timeout = port, baudrate, timeout
        self.rx = bytearray()
        self.written: list[bytes] = []
        self.resets = 0
        self.closed = False
        self.fail_write = False
        self.fail_read = False
        self.write_delay = 0.0
        self.active_writers = 0
        self.max_active_writers = 0
        self.lock = threading.Lock()
        FakeSerial.instances.append(self)

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, size=1):
        if self.fail_read:
            raise FakeSerialException("device removed")
        out = bytes(self.rx[:size])
        del self.rx[:size]
        if not out:
            time.sleep(0.001)
        return out

    def write(self, data):
        if self.fail_write:
            raise FakeSerialException("device removed")
        with self.lock:
            self.active_writers += 1
            self.max_active_writers = max(self.max_active_writers, self.active_writers)
        if self.write_delay:
            time.sleep(self.write_delay)
        self.written.append(bytes(data))
        with self.lock:
            self.active_writers -= 1
        return len(data)

    def reset_input_buffer(self):
        self.resets += 1
        self.rx.clear()

    def close(self):
        self.closed = True


FAKE_SERIAL_MODULE = types.SimpleNamespace(Serial=FakeSerial, SerialException=FakeSerialException)


@pytest.fixture
def slcan_port(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    FakeSerial.instances.clear()
    port = transports.SLCAN("COM-FAKE", serial_module=FAKE_SERIAL_MODULE, settle_seconds=0)
    return port


# =============================================================================
# SLCAN
# =============================================================================
def test_slcan_open_closes_sets_the_bitrate_and_opens(slcan_port):
    slcan_port.open_channel()
    assert slcan_port.ser.written == [b"C\r", b"S6\r", b"O\r"]
    assert slcan_port.listen_only is False
    assert slcan_port.ser.timeout == 0.02 and slcan_port.ser.baudrate == 115200


def test_slcan_listen_only_opens_with_l_and_refuses_to_transmit(slcan_port):
    slcan_port.open_channel("4", listen_only=True)
    assert slcan_port.ser.written[-2:] == [b"S4\r", b"L\r"]
    with pytest.raises(transports.SLCANError, match="listen-only"):
        slcan_port.send_frame(0x100, b"")
    assert len(slcan_port.ser.written) == 3


def test_slcan_send_writes_one_exact_line(slcan_port):
    slcan_port.send_frame(0x7F1, bytes(range(1, 9)))
    slcan_port.send_frame(0x100)
    assert slcan_port.ser.written == [b"t7F180102030405060708\r", b"t1000\r"]


@pytest.mark.parametrize("can_id,data", [(0x800, b""), (-1, b""), (0x100, bytes(9))])
def test_slcan_refuses_an_impossible_frame_without_writing(slcan_port, can_id, data):
    with pytest.raises(transports.SLCANError):
        slcan_port.send_frame(can_id, data)
    assert slcan_port.ser.written == []


def test_a_failed_serial_write_is_a_typed_error(slcan_port):
    slcan_port.ser.fail_write = True
    with pytest.raises(transports.SLCANError, match="serial write failed"):
        slcan_port.send_frame(0x100, b"")
    # closing never raises
    slcan_port.close()
    assert slcan_port.ser.closed


def test_a_failed_serial_read_is_a_typed_error(slcan_port):
    slcan_port.ser.fail_read = True
    with pytest.raises(transports.SLCANError, match="serial read failed"):
        slcan_port.read_frame(0.05)


def test_slcan_reads_a_frame_split_over_several_os_reads(slcan_port):
    slcan_port.ser.rx += b"t7F98"
    assert slcan_port.read_frame(0.01) is None
    slcan_port.ser.rx += b"000303CC01000003\r"
    assert slcan_port.read_frame(0.05) == (0x7F9, bytes.fromhex("000303CC01000003"))


def test_slcan_skips_status_characters_and_extended_frames_inside_one_wait(slcan_port):
    slcan_port.ser.rx += b"z\rZ\r\x07\rT0000011180102030405060708\rzt1101AA\r"
    assert slcan_port.read_frame(0.05) == (0x110, b"\xaa")


def test_slcan_drops_non_ascii_lines_instead_of_guessing(slcan_port):
    slcan_port.ser.rx += b"\xffjunk\rt1000\r"
    assert slcan_port.read_frame(0.05) == (0x100, b"")


def test_slcan_returns_none_when_nothing_arrives(slcan_port):
    assert slcan_port.read_frame(0.01) is None


def test_open_clears_a_stale_half_line(slcan_port):
    slcan_port.ser.rx += b"t7F98"
    assert slcan_port.read_frame(0.005) is None  # the half line is now in the application-level buffer
    slcan_port.open_channel()
    slcan_port.ser.rx += b"t1000\r"
    assert slcan_port.read_frame(0.05) == (0x100, b"")


def test_slcan_writes_never_interleave_between_threads(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    port = transports.SLCAN("COM-FAKE", serial_module=FAKE_SERIAL_MODULE, settle_seconds=0)
    port.ser.write_delay = 0.002
    threads = [threading.Thread(target=lambda: [port.send_frame(0x100 + i, b"\x01") for _ in range(5)]) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert port.ser.max_active_writers == 1
    assert len(port.ser.written) == 20


def test_slcan_without_pyserial_says_how_to_install_it(monkeypatch):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "serial":
            raise ImportError("no pyserial")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(transports.SLCANError, match="pip install pyserial"):
        transports.SLCAN("COM-FAKE")


# =============================================================================
# SocketCAN
# =============================================================================
class FakeSock:
    def __init__(self, bind_error=None):
        self.bind_error = bind_error
        self.closed = False
        self.sent: list[bytes] = []
        self.send_errors: list[OSError] = []
        self.incoming: list = []
        self.timeouts: list[float] = []

    def bind(self, address):
        if self.bind_error:
            raise self.bind_error
        self.address = address

    def settimeout(self, value):
        self.timeouts.append(value)

    def send(self, frame):
        if self.send_errors:
            raise self.send_errors.pop(0)
        self.sent.append(frame)

    def recv(self, size):
        if not self.incoming:
            raise socket.timeout()
        item = self.incoming.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


def fake_socket_module(sock):
    return types.SimpleNamespace(AF_CAN=29, SOCK_RAW=3, CAN_RAW=1, socket=lambda *args: sock, timeout=socket.timeout)


def raw_frame(can_id, data, flags=0, dlc=None):
    return struct.pack("=IB3x8s", can_id | flags, len(data) if dlc is None else dlc, data + bytes(8 - len(data)))


@pytest.fixture
def can0(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    sock = FakeSock()
    transport = transports.SocketCAN("can0", socket_module=fake_socket_module(sock))
    return transport, sock


def test_socketcan_binds_the_interface_and_sets_a_short_timeout(can0):
    transport, sock = can0
    assert sock.address == ("can0",) and sock.timeouts == [0.05]


def test_a_failed_bind_closes_the_socket_and_is_a_typed_error():
    sock = FakeSock(bind_error=OSError(errno.ENODEV, "no such device"))
    with pytest.raises(transports.SocketCANError, match="couldn't open 'can9'"):
        transports.SocketCAN("can9", socket_module=fake_socket_module(sock))
    assert sock.closed


def test_a_system_without_af_can_gives_a_typed_error():
    with pytest.raises(transports.SocketCANError):
        transports.SocketCAN("can0", socket_module=types.SimpleNamespace())


def test_socketcan_sends_the_native_frame_padded_to_eight_bytes(can0):
    transport, sock = can0
    transport.send_frame(0x7F0, bytes.fromhex("B0071D5A"))
    assert sock.sent == [struct.pack("=IB3x8s", 0x7F0, 4, bytes.fromhex("B0071D5A") + bytes(4))]
    transport.send_frame(0x100, memoryview(b"\x01\x02"))
    assert sock.sent[-1] == struct.pack("=IB3x8s", 0x100, 2, b"\x01\x02" + bytes(6))


@pytest.mark.parametrize("can_id,data", [(0x800, b""), (-5, b""), (0x100, bytes(9))])
def test_socketcan_refuses_an_impossible_frame(can0, can_id, data):
    transport, sock = can0
    with pytest.raises(transports.SocketCANError):
        transport.send_frame(can_id, data)
    assert sock.sent == []


def test_a_full_kernel_queue_is_retried_and_then_succeeds(can0):
    transport, sock = can0
    sock.send_errors = [OSError(errno.ENOBUFS, "full"), OSError(errno.ENOBUFS, "full")]
    transport.send_frame(0x100, b"")
    assert len(sock.sent) == 1


def test_a_queue_that_stays_full_gives_up_after_five_tries(can0):
    transport, sock = can0
    sock.send_errors = [OSError(errno.ENOBUFS, "full") for _ in range(10)]
    with pytest.raises(transports.SocketCANError, match="ENOBUFS"):
        transport.send_frame(0x100, b"")
    assert len(sock.send_errors) == 5


def test_any_other_send_error_fails_at_once(can0):
    transport, sock = can0
    sock.send_errors = [OSError(errno.ENETDOWN, "down"), OSError(errno.ENETDOWN, "down")]
    with pytest.raises(transports.SocketCANError, match="send failed"):
        transport.send_frame(0x100, b"")
    assert len(sock.send_errors) == 1


def test_socketcan_listen_only_is_soft_and_refuses_to_transmit(can0):
    transport, sock = can0
    logged = []
    transport.log = logged.append
    transport.open_channel(listen_only=True)
    assert logged and "cannot be opened listen-only" in logged[0]
    with pytest.raises(transports.SocketCANError, match="listen-only"):
        transport.send_frame(0x100, b"")


def test_socketcan_read_returns_the_identifier_and_the_declared_bytes(can0):
    transport, sock = can0
    sock.incoming = [raw_frame(0x111, bytes.fromhex("0A0001"))]
    assert transport.read_frame(0.05) == (0x111, bytes.fromhex("0A0001"))


@pytest.mark.parametrize("flags", [0x80000000, 0x40000000, 0x20000000])
def test_socketcan_discards_extended_remote_and_error_frames_before_masking(can0, flags):
    transport, sock = can0
    sock.incoming = [raw_frame(0x111, b"\x01", flags=flags)]
    assert transport.read_frame(0.05) is None


def test_socketcan_clamps_a_dlc_above_eight(can0):
    transport, sock = can0
    sock.incoming = [raw_frame(0x111, bytes(range(8)), dlc=15)]
    assert transport.read_frame(0.05) == (0x111, bytes(range(8)))


def test_socketcan_quiet_bus_and_truncated_reads_give_none(can0):
    transport, sock = can0
    assert transport.read_frame(0.05) is None
    sock.incoming = [b"\x00\x01"]
    assert transport.read_frame(0.05) is None


def test_socketcan_only_changes_the_timeout_when_it_differs(can0):
    transport, sock = can0
    for _ in range(3):
        transport.read_frame(0.2)
    transport.read_frame(0.05)
    assert sock.timeouts == [0.05, 0.2, 0.05]


def test_a_dead_socket_is_logged_not_hidden(can0):
    transport, sock = can0
    logged = []
    transport.log = logged.append
    sock.incoming = [OSError(errno.ENETDOWN, "down")]
    assert transport.read_frame(0.05) is None
    assert logged and "read error on 'can0'" in logged[0]


def test_socketcan_close_is_safe_twice(can0):
    transport, sock = can0
    transport.close()
    transport.close()
    assert sock.closed


def test_sysfs_readers(tmp_path, monkeypatch):
    monkeypatch.setattr(transports.SocketCAN, "SYSFS_NET", str(tmp_path))
    (tmp_path / "can0" / "statistics").mkdir(parents=True)
    (tmp_path / "can0" / "carrier").write_text("1\n")
    for name, value in (("rx_packets", 5), ("tx_packets", 6), ("rx_errors", 0), ("tx_errors", 1), ("rx_dropped", 0), ("tx_dropped", 0), ("collisions", 0)):
        (tmp_path / "can0" / "statistics" / name).write_text(f"{value}\n")
    assert transports.SocketCAN.check_carrier("can0") is True
    (tmp_path / "can0" / "carrier").write_text("0\n")
    assert transports.SocketCAN.check_carrier("can0") is False
    assert transports.SocketCAN.check_carrier("nothing") is None
    assert transports.SocketCAN.read_interface_stats("can0")["tx_errors"] == 1
    assert transports.SocketCAN.read_interface_stats("nothing") is None
    (tmp_path / "can0" / "statistics" / "rx_errors").write_text("x")
    assert transports.SocketCAN.read_interface_stats("can0") is None


def test_a_down_interface_logs_a_warning_when_opened(tmp_path, monkeypatch):
    monkeypatch.setattr(transports.SocketCAN, "SYSFS_NET", str(tmp_path))
    (tmp_path / "can0").mkdir()
    (tmp_path / "can0" / "carrier").write_text("0\n")
    logged = []
    transports.SocketCAN("can0", log=logged.append, socket_module=fake_socket_module(FakeSock()))
    assert logged and "no carrier" in logged[0]


def test_list_socketcan_interfaces(tmp_path):
    for name, kind in (("can0", "280"), ("eth0", "1"), ("vcan0", "280")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "type").write_text(kind + "\n")
    (tmp_path / "lo").mkdir()
    assert transports.list_socketcan_interfaces(str(tmp_path)) == ["can0", "vcan0"]
    assert transports.list_socketcan_interfaces(str(tmp_path / "missing")) == []


# =============================================================================
# python-can
# =============================================================================
class FakeMessage:
    def __init__(self, arbitration_id=0, data=b"", is_extended_id=False, is_remote_frame=False, is_error_frame=False):
        self.arbitration_id, self.data = arbitration_id, data
        self.is_extended_id, self.is_remote_frame, self.is_error_frame = is_extended_id, is_remote_frame, is_error_frame


class FakeBus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent = []
        self.incoming = []
        self.down = False

    def send(self, message):
        self.sent.append(message)

    def recv(self, timeout):
        return self.incoming.pop(0) if self.incoming else None

    def shutdown(self):
        self.down = True


def fake_can_module(bus_error=None):
    holder = {}

    def make_bus(**kwargs):
        if bus_error:
            raise bus_error
        holder["bus"] = FakeBus(**kwargs)
        return holder["bus"]

    return types.SimpleNamespace(Bus=make_bus, Message=FakeMessage), holder


def test_python_can_opens_the_spec_and_sends_standard_frames():
    module, holder = fake_can_module()
    port = transports.PythonCAN("pcan:PCAN_USBBUS1", can_module=module)
    port.open_channel()
    assert holder["bus"].kwargs == {"interface": "pcan", "channel": "PCAN_USBBUS1", "bitrate": 500000}
    port.send_frame(0x100, b"\x01")
    message = holder["bus"].sent[0]
    assert message.arbitration_id == 0x100 and message.data == b"\x01" and message.is_extended_id is False
    transports.PythonCAN("kvaser:0", can_module=module).open_channel()
    assert holder["bus"].kwargs["channel"] == 0


@pytest.mark.parametrize("spec", ["", "pcan", "pcan:", ":0"])
def test_python_can_refuses_a_malformed_spec(spec):
    module, _ = fake_can_module()
    with pytest.raises(transports.PythonCANError, match="expected <interface>:<channel>"):
        transports.PythonCAN(spec, can_module=module).open_channel()


def test_python_can_wraps_open_and_send_failures():
    module, _ = fake_can_module(bus_error=RuntimeError("no adapter"))
    with pytest.raises(transports.PythonCANError, match="cannot open"):
        transports.PythonCAN("pcan:1", can_module=module).open_channel()
    module, holder = fake_can_module()
    port = transports.PythonCAN("pcan:1", can_module=module)
    port.open_channel()
    holder["bus"].send = lambda message: (_ for _ in ()).throw(RuntimeError("bus off"))
    with pytest.raises(transports.PythonCANError, match="send failed"):
        port.send_frame(0x100, b"")


def test_python_can_must_be_open_and_rejects_out_of_range_frames():
    module, _ = fake_can_module()
    port = transports.PythonCAN("pcan:1", can_module=module)
    with pytest.raises(transports.PythonCANError, match="not open"):
        port.send_frame(0x100, b"")
    with pytest.raises(transports.PythonCANError, match="not open"):
        port.read_frame()
    port.open_channel()
    with pytest.raises(transports.PythonCANError):
        port.send_frame(0x800, b"")
    port.close()
    port.close()


def test_python_can_listen_only_does_not_transmit():
    module, _ = fake_can_module()
    port = transports.PythonCAN("pcan:1", can_module=module)
    port.open_channel(listen_only=True)
    with pytest.raises(transports.PythonCANError, match="listen-only"):
        port.send_frame(0x100, b"")


def test_python_can_read_filters_extended_remote_and_error_frames():
    module, holder = fake_can_module()
    port = transports.PythonCAN("pcan:1", can_module=module)
    port.open_channel()
    bus = holder["bus"]
    bus.incoming = [FakeMessage(0x111, b"\x01"), FakeMessage(0x111, b"\x01", is_extended_id=True), FakeMessage(0x111, b"", is_remote_frame=True),
                    FakeMessage(0x111, b"", is_error_frame=True)]
    assert port.read_frame() == (0x111, b"\x01")
    assert port.read_frame() is None and port.read_frame() is None and port.read_frame() is None
    assert port.read_frame() is None  # quiet


def test_python_can_missing_package_says_how_to_install_it(monkeypatch):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "can":
            raise ImportError("no python-can")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(transports.PythonCANError, match="pip install python-can"):
        transports.PythonCAN("pcan:1").open_channel()


# =============================================================================
# the simulated board
# =============================================================================
def drain(board):
    out = []
    while True:
        frame = board.read_frame()
        if frame is None:
            return out
        out.append(frame)


def mock(**kwargs):
    return transports.MockCAN(delay=0, **kwargs)


def test_mock_answers_a_version_query_like_a_bootloader_without_a_patch():
    board = mock(installed_version=(0, 3))
    board.send_frame(protocol.CAN_ID_QUERY_VERSION, b"\x00")
    assert drain(board) == [(0x7F9, bytes.fromhex("010303CC01000003")), (0x7FA, bytes([1, 0, 1]))]


def test_mock_sends_the_patch_frame_when_the_board_knows_its_patch():
    board = mock(installed_version=(0, 3), installed_patch=5, accepts_patch=True)
    board.send_frame(protocol.CAN_ID_QUERY_VERSION, b"\x00")
    assert drain(board)[-1] == (0x7E9, bytes([1, 5, 1]))
    board = mock(installed_patch=protocol.PATCH_UNKNOWN)
    board.send_frame(protocol.CAN_ID_QUERY_VERSION, b"\x00")
    assert drain(board)[-1] == (0x7E9, bytes([1, 0xFF, 0]))


def test_mock_update_acknowledges_full_pages_and_the_partial_last_page_at_the_end():
    board = mock(page_size=16)
    board.send_frame(protocol.CAN_ID_START_UPDATE, struct.pack(">II", 40, protocol.HARDWARE_ID_MAIN))
    assert drain(board) == [(0x7F5, b"\x02"), (0x7F5, b"\x03")]
    for _ in range(5):
        board.send_frame(protocol.CAN_ID_DATA, bytes(8))
    assert drain(board) == [(0x7F3, struct.pack(">I", 0)), (0x7F3, struct.pack(">I", 1))]
    board.send_frame(protocol.CAN_ID_END_UPDATE, bytes.fromhex("DEADBEEF00000003"))
    assert drain(board) == [(0x7F3, struct.pack(">I", 2)), (0x7F5, b"\x06"), (0x7F5, b"\x04")]
    assert board.end_update_payload == bytes.fromhex("DEADBEEF00000003")


def test_mock_can_fail_verification_with_a_reason():
    board = mock(simulate_failure=protocol.VERIFY_FAIL_REASON_ROLLBACK)
    board.send_frame(protocol.CAN_ID_START_UPDATE, struct.pack(">II", 8, protocol.HARDWARE_ID_MAIN))
    drain(board)
    board.send_frame(protocol.CAN_ID_DATA, bytes(8))
    board.send_frame(protocol.CAN_ID_END_UPDATE, bytes(8))
    assert drain(board)[-1] == (0x7F5, bytes([0x05, 0x05]))


def test_mock_reads_back_in_pages_and_the_last_frame_is_as_short_as_the_size_requires():
    image = bytes(range(35))
    board = mock(installed_image=image, page_size=16)
    board.send_frame(protocol.CAN_ID_READBACK, b"")
    first = drain(board)
    assert first[0] == (0x7FE, struct.pack(">I", 35))
    assert b"".join(d for _, d in first[1:]) == image[:16]
    board.send_frame(protocol.CAN_ID_READBACK_PAGE_ACK, struct.pack(">I", 0))
    board.send_frame(protocol.CAN_ID_READBACK_PAGE_ACK, struct.pack(">I", 1))
    rest = drain(board)
    assert b"".join(d for _, d in rest) == image[16:]
    assert len(rest[-1][1]) == 3


def test_mock_readback_with_nothing_installed_reports_size_zero():
    board = mock()
    board.send_frame(protocol.CAN_ID_READBACK, b"")
    assert drain(board) == [(0x7FE, struct.pack(">I", 0))]


def test_mock_slave_version_answers_in_two_frames_with_the_optional_extension():
    board = mock(slave_version={"version": (0, 2), "bootloader": 1, "patch_extension": True, "patch": 4})
    board.send_frame(protocol.CAN_ID_SLAVE_VERSION_RESP_1, b"")
    first, second = drain(board)
    assert first[0] == 0x217 and len(first[1]) == 8 and second == (0x218, bytes([2, 1, 4, 0, 0]))
    board = mock(slave_version={"version": (0, 2)})
    board.send_frame(protocol.CAN_ID_SLAVE_VERSION_RESP_1, b"")
    assert drain(board)[1] == (0x218, bytes([2, 0]))
    silent = mock()
    silent.send_frame(protocol.CAN_ID_SLAVE_VERSION_RESP_1, b"")
    assert drain(silent) == []


def test_mock_keeps_the_slave_end_of_update_and_records_what_was_sent():
    board = mock()
    board.send_frame(protocol.CAN_ID_SLAVE_END_UPDATE, bytes.fromhex("1234567800000002"))
    assert board.slave_end_update_payload == bytes.fromhex("1234567800000002")
    assert board.sent == [(0x214, bytes.fromhex("1234567800000002"))]


def test_mock_hmac_chunks_get_no_answer_and_impossible_frames_are_refused():
    board = mock()
    board.send_frame(protocol.CAN_ID_HMAC_CHUNK, bytes(8))
    assert drain(board) == []
    with pytest.raises(transports.SLCANError):
        board.send_frame(0x800, b"")


def test_mock_has_the_interface_of_the_real_transports():
    board = mock()
    board.open_channel("6", listen_only=False)
    board.close_channel()
    board.close()
    assert board.read_frame(0.01) is None


# =============================================================================
# bitrate detection
# =============================================================================
class Trial:
    def __init__(self, hears):
        self.hears, self.closed = hears, False

    def read_frame(self, timeout=0.05):
        return (0x100, b"") if self.hears else None

    def close(self):
        self.closed = True


def test_bitrate_detection_listens_only_and_reports_the_label():
    tried, trials = [], []

    def open_trial(code):
        trials.append(Trial(code == "6"))
        return trials[-1]

    label = transports.detect_bitrate_listen_only(open_trial, protocol.SLCAN_BITRATES, listen_seconds=0.01, on_try=tried.append)
    assert label == "500 kbit/s"
    assert tried == ["10 kbit/s", "20 kbit/s", "50 kbit/s", "100 kbit/s", "125 kbit/s", "250 kbit/s", "500 kbit/s"]
    assert all(t.closed for t in trials)


def test_bitrate_detection_gives_none_for_a_silent_bus_and_survives_a_failing_open():
    def open_trial(code):
        if code == "0":
            raise transports.SLCANError("busy")
        return Trial(False)

    assert transports.detect_bitrate_listen_only(open_trial, protocol.SLCAN_BITRATES, listen_seconds=0.01) is None


def test_as_frames_wraps_pairs():
    assert transports.as_frames([(0x100, b"")]) == [CanFrame(0x100)]


def test_a_tool_can_say_the_warnings_in_its_own_language(tmp_path, monkeypatch):
    monkeypatch.setattr(transports.SocketCAN, "SYSFS_NET", str(tmp_path))
    (tmp_path / "can0").mkdir()
    (tmp_path / "can0" / "carrier").write_text("0\n")
    said = []
    transports.SocketCAN("can0", log=said.append, socket_module=fake_socket_module(FakeSock()),
                         translate=lambda key, **params: f"[{key}] {params['interface']}")
    assert said == ["[WARN_NO_CARRIER] can0"]
