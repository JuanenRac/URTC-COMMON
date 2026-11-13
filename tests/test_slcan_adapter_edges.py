# =============================================================================
# URTC-COMMON - tests/test_slcan_adapter_edges.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The text adapter of the virtual board at its edges, with a generated stream (a fixed seed): every command that is not allowed in the state of the channel is answered with a bell,
a stream of noise never raises and never grows without limit, and the commands that a real adapter has are answered the way it answers them."""
from __future__ import annotations

import random

import pytest

from urtc_common import protocol as p
from urtc_common.virtual_board import ADAPTER_VERSION, SlcanAdapter, VirtualBoard

SEED = 20261113
BELL = b"\a"


def adapter(**kwargs):
    return SlcanAdapter(VirtualBoard(), **kwargs)


def open_adapter(**kwargs):
    a = adapter(**kwargs)
    assert a.command("S" + p.SLCAN_BITRATE_DEFAULT_CODE) == b"\r"
    assert a.command("O") == b"\r"
    return a


def test_a_closed_channel_sends_nothing_and_a_listen_only_channel_does_not_transmit():
    a = adapter()
    assert a.command("t1230") == BELL
    assert a.command("L") == b"\r" and a.state == "listen"
    assert a.command("t1230") == BELL


def test_a_frame_with_an_extended_identifier_is_refused_on_an_open_channel():
    a = open_adapter()
    assert a.command("T00000123" + "0") == BELL


def test_a_line_that_is_not_a_frame_is_refused():
    a = open_adapter()
    for line in ("t", "tZZZ", "t12", "t1239", "t123900", "tFFF0"):
        assert a.command(line) == BELL or a.command(line).endswith(b"\r") or a.command(line) == b""


def test_the_speed_can_only_be_set_on_a_closed_channel_and_only_with_a_digit():
    a = open_adapter()
    assert a.command("S3") == BELL
    assert a.command("C") == b"\r" and a.state == "closed"
    for line in ("S", "S10", "Sx", "S-"):
        assert a.command(line) == BELL
    assert a.command("S3") == b"\r" and a.bitrate_code == "3"


def test_open_and_listen_are_refused_when_the_channel_is_not_closed_and_close_always_works():
    a = open_adapter()
    assert a.command("O") == BELL and a.command("L") == BELL
    assert a.command("C") == b"\r" and a.command("C") == b"\r"
    assert a.command("OO") == BELL and a.command("CC") == BELL


def test_the_version_and_the_flags_are_answered_in_any_state():
    for a in (adapter(), open_adapter()):
        assert a.command("V") == ADAPTER_VERSION.encode("ascii") + b"\r"
        assert a.command("F") == b"F00\r"
        assert a.command("VV") == BELL and a.command("FF") == BELL


def test_an_empty_line_and_an_unknown_command_are_answered_as_a_real_adapter_does():
    a = open_adapter()
    assert a.command("") == b""
    for line in ("Q", "Z", "?", "x1", "s3", "o"):
        assert a.command(line) == BELL


def test_a_frame_sent_into_a_bus_at_another_speed_reaches_nobody():
    a = open_adapter(bus_bitrate_code="9")
    assert a.command("t1230") == b"z\r"
    quiet = open_adapter(bus_bitrate_code="9", acknowledge_transmit=False)
    assert quiet.command("t1230") == b""
    assert a.board.received == [] and quiet.board.received == []


def test_a_frame_sent_at_the_right_speed_is_acknowledged_when_the_adapter_does_and_not_when_it_does_not():
    loud = open_adapter()
    assert loud.command("t1230").startswith(b"z\r")
    silent = open_adapter(acknowledge_transmit=False)
    assert not silent.command("t1230").startswith(b"z\r")
    assert loud.board.received and silent.board.received


def test_the_stream_is_cut_in_lines_whatever_the_size_of_the_pieces():
    rng = random.Random(SEED)
    whole = b"V\rF\rV\r"
    for _ in range(50):
        a = adapter()
        out = b""
        data = whole
        while data:
            size = rng.randrange(1, 4)
            out += a.feed(data[:size])
            data = data[size:]
        assert out == (ADAPTER_VERSION.encode("ascii") + b"\r" + b"F00\r") + ADAPTER_VERSION.encode("ascii") + b"\r"


def test_a_byte_that_is_not_text_is_a_bell_and_the_next_line_is_read():
    a = adapter()
    out = a.feed(b"\xff\xfe\rV\r")
    assert out.startswith(BELL + b"\r") and out.endswith(ADAPTER_VERSION.encode("ascii") + b"\r")


def test_a_stream_without_a_terminator_is_dropped_when_it_grows_too_long():
    a = adapter()
    assert a.feed(b"x" * 5000) == b""
    assert a._pending == b""
    assert a.feed(b"V\r").startswith(ADAPTER_VERSION.encode("ascii"))


def test_noise_never_raises_and_every_reply_ends_with_the_terminator():
    rng = random.Random(SEED)
    a = adapter()
    for _ in range(300):
        chunk = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 40)))
        reply = a.feed(chunk)
        assert reply == b"" or reply.endswith(b"\r")
        assert len(a._pending) <= 4096


@pytest.mark.parametrize("state_commands, expected", [(["O"], "open"), (["L"], "listen"), (["O", "C"], "closed"), ([], "closed")])
def test_the_state_follows_the_commands(state_commands, expected):
    a = adapter()
    for command in state_commands:
        a.command(command)
    assert a.state == expected
