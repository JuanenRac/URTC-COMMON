# =============================================================================
# URTC-COMMON - tests/test_virtual_board.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The virtual board: checked against the shared vectors, then reached through the real SLCAN transport over TCP."""
from __future__ import annotations

import socket
import sys
import time
import types

import pytest

from urtc_common import protocol, quick_state, transports, versioning
from urtc_common.slcan import LineReader, encode_line
from urtc_common.virtual_board import APPLICATION, BOOTLOADER, SlcanAdapter, VirtualBoard, VirtualBoardServer, main


def _id(text: str) -> int:
    return int(text, 16)


def _board_for(expect: dict) -> VirtualBoard:
    flags = protocol.PATCH_FLAG_ACCEPTS_IN_END_UPDATE if expect["accepts_patch_in_end_update"] else 0
    patch = protocol.PATCH_UNKNOWN if expect["patch_aware"] and expect["patch"] is None else expect["patch"]
    return VirtualBoard(hardware_id=_id(expect["hardware_id"]), version=(expect["major"], expect["minor"]), patch=patch, accepts_patch=bool(flags))


# =============================================================================
# the board against the vectors
# =============================================================================
def test_the_application_reproduces_every_version_vector_it_can_represent(vectors):
    checked = 0
    for entry in vectors["version_query"]:
        expect = entry["expect"]
        if expect is None or expect["responder"] != "application" or not (expect["patch_aware"] or expect["patch"] is None):
            continue
        answer = _board_for(expect).handle(protocol.CAN_ID_QUERY_VERSION)
        expected_frames = [(_id(i), bytes.fromhex(d)) for i, d in entry["frames"] if len(bytes.fromhex(d)) >= 3]
        if entry["name"].startswith("patch frame longer") or entry["name"].startswith("patch frame shorter"):
            continue  # frames the board itself never builds
        assert answer == expected_frames, entry["name"]
        parsed = versioning.parse_version_answer(answer)
        assert all(parsed[key] == value for key, value in expect.items()), entry["name"]
        checked += 1
    assert checked >= 3


def test_a_board_that_predates_the_patch_frame_sends_only_the_version(vectors):
    board = VirtualBoard(version=(0, 3), patch=None)
    answer = board.handle(protocol.CAN_ID_QUERY_VERSION)
    assert [can_id for can_id, _ in answer] == [protocol.CAN_ID_VERSION_RESPONSE]
    assert versioning.parse_version_answer(answer)["patch_aware"] is False


def test_the_quick_state_reproduces_every_vector_byte_for_byte(vectors):
    checked = 0
    for entry in vectors["quick_state"]:
        expect = entry["expect"]
        if expect is None:
            continue
        board = VirtualBoard(tool_id=expect["tool_id"], system_error=expect["system_error"], can_error=expect["can_error"],
                             booting=expect["booting"], thermal_fault=expect["thermal_fault"], reset_cause=expect["reset_cause"])
        ((can_id, data),) = board.handle(protocol.CAN_ID_QUERY_ACTIVE_TOOL)
        assert can_id == protocol.CAN_ID_ACTIVE_TOOL_RESP
        assert data.hex().upper() == entry["data"].upper(), entry["name"]
        decoded = quick_state.decode(data)
        assert all(decoded[key] == value for key, value in expect.items()), entry["name"]
        checked += 1
    assert checked == 4


def test_only_the_exact_magic_payload_enters_the_bootloader(vectors):
    magics = {entry["name"]: (_id(entry["id"]), bytes.fromhex(entry["data"])) for entry in vectors["magic_payloads"]}
    can_id, data = magics["enter_bootloader"]
    for wrong in (b"", data[:-1], data + b"\x00", bytes(4), bytes.fromhex("D09E12AD")):
        board = VirtualBoard()
        board.handle(can_id, wrong)
        assert board.mode == APPLICATION, wrong
    for name, (other_id, other_data) in magics.items():
        if name != "enter_bootloader":
            board = VirtualBoard()
            board.handle(other_id, other_data)
            assert board.mode == APPLICATION, name
    board = VirtualBoard()
    board.handle(can_id, data)
    assert board.mode == BOOTLOADER


def test_the_bootloader_answers_the_version_query_as_a_bootloader_and_runs_an_update():
    board = VirtualBoard(version=(0, 2), bootloader=True)
    parsed = versioning.parse_version_answer(board.handle(protocol.CAN_ID_QUERY_VERSION))
    assert parsed["responder"] == "bootloader" and parsed["major"] == 0 and parsed["minor"] == 2
    answer = board.handle(protocol.CAN_ID_START_UPDATE, (4).to_bytes(4, "big"))
    assert [data for _, data in answer] == [bytes([protocol.STATUS_ERASING]), bytes([protocol.STATUS_RECEIVING])]
    board.reboot()
    assert board.mode == APPLICATION


def test_other_identifiers_are_silent_in_the_application():
    board = VirtualBoard()
    assert board.handle(protocol.CAN_ID_GLOBAL_STATUS, b"\x01") == []
    assert board.received == [(protocol.CAN_ID_GLOBAL_STATUS, b"\x01")]


# =============================================================================
# the adapter
# =============================================================================
def _adapter() -> SlcanAdapter:
    return SlcanAdapter(VirtualBoard())


def test_the_adapter_is_closed_until_opened_and_refuses_frames():
    adapter = _adapter()
    assert adapter.feed(b"t7F80\r") == b"\a\r"
    assert adapter.feed(b"S6\rO\r") == b"\r\r"
    assert adapter.state == "open" and adapter.bitrate_code == "6"


def test_a_query_is_acknowledged_and_answered_in_the_same_stream():
    adapter = _adapter()
    adapter.feed(b"S6\rO\r")
    reply = adapter.feed(encode_line(protocol.CAN_ID_QUERY_VERSION).encode() + b"\r")
    assert reply.startswith(b"z\r")
    frames = LineReader().frames(reply)
    assert [frame.id for frame in frames] == [protocol.CAN_ID_VERSION_RESPONSE, protocol.CAN_ID_VERSION_PATCH_RESPONSE]


def test_the_acknowledgement_can_be_turned_off():
    adapter = SlcanAdapter(VirtualBoard(), acknowledge_transmit=False)
    adapter.feed(b"O\r")
    assert not adapter.feed(b"t1000\r")


def test_listen_only_never_transmits():
    adapter = _adapter()
    adapter.feed(b"S6\rL\r")
    assert adapter.state == "listen"
    assert adapter.feed(b"t7F80\r") == b"\a\r"
    assert adapter.board.received == []


@pytest.mark.parametrize("line", [b"x\r", b"S9x\r", b"T0000010011\r", b"t7F8\r", b"tZZZ0\r", b"O1\r"])
def test_what_the_adapter_does_not_understand_gets_a_bell(line):
    adapter = _adapter()
    adapter.feed(b"O\r")
    assert adapter.feed(line) == b"\a\r"


def test_version_status_and_close():
    adapter = _adapter()
    assert adapter.feed(b"V\r") == b"V0101\r"
    assert adapter.feed(b"F\r") == b"F00\r"
    adapter.feed(b"O\r")
    assert adapter.feed(b"C\r") == b"\r" and adapter.state == "closed"


def test_a_line_split_over_several_chunks_is_put_together():
    adapter = _adapter()
    adapter.feed(b"O\r")
    assert adapter.feed(b"t7F") == b""
    assert adapter.feed(b"80\r").startswith(b"z\r")


# =============================================================================
# through the real transport over TCP
# =============================================================================
class SocketSerial:
    """Just enough of pyserial's socket:// handler: a socket with a short read timeout."""

    def __init__(self, url, baudrate=115200, timeout=None):
        host, _, port = url[len("socket://"):].partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout=2)
        self.sock.settimeout(timeout)
        self.timeout = timeout

    @property
    def in_waiting(self):
        return 0

    def read(self, size=1):
        try:
            return self.sock.recv(size)
        except (socket.timeout, TimeoutError):
            return b""

    def write(self, data):
        self.sock.sendall(data)
        return len(data)

    def reset_input_buffer(self):
        self.sock.settimeout(0)
        try:
            while self.sock.recv(4096):
                pass
        except OSError:
            pass
        self.sock.settimeout(self.timeout)

    def close(self):
        self.sock.close()


SERIAL_MODULE = types.SimpleNamespace(SerialException=OSError, serial_for_url=SocketSerial)


def _collect(port, wanted: int, timeout: float = 2.0):
    frames = []
    deadline = time.monotonic() + timeout
    while len(frames) < wanted and time.monotonic() < deadline:
        frame = port.read_frame(0.05)
        if frame is not None:
            frames.append(frame)
    return frames


def test_a_serial_url_is_recognised():
    assert transports.is_serial_url("socket://127.0.0.1:7777")
    assert not transports.is_serial_url("COM3") and not transports.is_serial_url("/dev/ttyACM0")


def test_the_slcan_transport_queries_the_version_of_the_virtual_board_over_tcp():
    with VirtualBoardServer(VirtualBoard(version=(0, 5), patch=2)) as server:
        port = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        try:
            port.open_channel()
            port.send_frame(protocol.CAN_ID_QUERY_VERSION)
            parsed = versioning.parse_version_answer(_collect(port, 2))
        finally:
            port.close()
    assert parsed["responder"] == "application" and (parsed["major"], parsed["minor"], parsed["patch"]) == (0, 5, 2)


def test_the_slcan_transport_runs_a_bootloader_session_over_tcp():
    board = VirtualBoard(version=(0, 2))
    with VirtualBoardServer(board) as server:
        port = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        try:
            port.open_channel()
            port.send_frame(protocol.CAN_ID_ENTER_BOOTLOADER, bytes.fromhex(protocol.MAGIC_PAYLOADS["enter_bootloader"]["data"]))
            port.send_frame(protocol.CAN_ID_QUERY_VERSION)
            parsed = versioning.parse_version_answer(_collect(port, 3))
            assert parsed["responder"] == "bootloader"
            port.send_frame(protocol.CAN_ID_START_UPDATE, (16).to_bytes(4, "big"))
            statuses = [data for can_id, data in _collect(port, 2) if can_id == protocol.CAN_ID_STATUS]
        finally:
            port.close()
    assert statuses == [bytes([protocol.STATUS_ERASING]), bytes([protocol.STATUS_RECEIVING])]
    assert board.mode == BOOTLOADER


def test_two_clients_share_one_board_like_two_programs_on_one_bus():
    with VirtualBoardServer(VirtualBoard()) as server:
        first = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        second = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        try:
            first.open_channel()
            second.open_channel()
            first.send_frame(protocol.CAN_ID_QUERY_ACTIVE_TOOL)
            assert _collect(first, 1)[0][0] == protocol.CAN_ID_ACTIVE_TOOL_RESP
        finally:
            first.close()
            second.close()


def test_the_server_listens_on_loopback_by_default():
    with VirtualBoardServer() as server:
        assert server.host == "127.0.0.1" and server.url == f"socket://127.0.0.1:{server.port}"


def test_the_transport_refuses_a_module_that_cannot_open_urls():
    module = types.SimpleNamespace(Serial=lambda *a, **k: None, SerialException=OSError)
    with pytest.raises(transports.SLCANError, match="by URL"):
        transports.SLCAN("socket://127.0.0.1:1", serial_module=module, settle_seconds=0)


def test_a_failed_url_is_a_typed_error():
    def refuse(url, **kwargs):
        raise OSError("connection refused")

    module = types.SimpleNamespace(serial_for_url=refuse, SerialException=OSError)
    with pytest.raises(transports.SLCANError, match="connection refused"):
        transports.SLCAN("socket://127.0.0.1:1", serial_module=module, settle_seconds=0)


def test_the_real_pyserial_url_handler_reaches_the_board():
    serial = pytest.importorskip("serial")
    with VirtualBoardServer(VirtualBoard(version=(0, 7), patch=1)) as server:
        port = transports.SLCAN(server.url, serial_module=serial, settle_seconds=0)
        try:
            port.open_channel()
            port.send_frame(protocol.CAN_ID_QUERY_VERSION)
            parsed = versioning.parse_version_answer(_collect(port, 2))
        finally:
            port.close()
    assert (parsed["major"], parsed["minor"], parsed["patch"]) == (0, 7, 1)


# =============================================================================
# the bridge to a program that speaks SLCAN text (the firmware's own virtual board)
# =============================================================================
ECHO_PROGRAM = (
    "import sys\n"
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line.startswith('t'):\n"
    "        print('t7F90' if line.startswith('t7F8') else 'X', flush=True)\n"
    "    elif line[:1] in 'SOC':\n"
    "        print('', flush=True)\n"
)


def test_the_exec_bridge_passes_frames_to_a_program_and_back():
    with VirtualBoardServer(command=[sys.executable, "-c", ECHO_PROGRAM]) as server:
        port = transports.SLCAN(server.url, serial_module=SERIAL_MODULE, settle_seconds=0)
        try:
            port.open_channel()
            port.send_frame(protocol.CAN_ID_QUERY_VERSION)
            port.send_frame(protocol.CAN_ID_GLOBAL_STATUS, b"\x01")  # the program answers X: a reset notice, not a frame
            frames = _collect(port, 1, timeout=15.0)
        finally:
            port.close()
    assert frames == [(protocol.CAN_ID_VERSION_RESPONSE, b"")]


def test_main_reports_a_bad_version(capsys):
    assert main(["--firmware-version", "x", "--port", "0"]) == 2
    assert "VIRTUAL_BOARD=FAIL" in capsys.readouterr().err


def test_the_command_line_subcommand_reports_a_bad_option(capsys):
    from urtc_common import cli

    assert cli.main(["virtual-board", "--firmware-version", "x", "--port", "0"]) == 2
    assert "VIRTUAL_BOARD=FAIL" in capsys.readouterr().err
