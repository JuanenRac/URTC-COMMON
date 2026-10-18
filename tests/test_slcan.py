# =============================================================================
# URTC-COMMON - tests/test_slcan.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The SLCAN codec: strict hexadecimal, standard frames only, one frame per line."""
from __future__ import annotations

import pytest

from urtc_common import framing, slcan


@pytest.mark.parametrize(
    "can_id,data,line",
    [(0x7F8, b"\x00", "t7F8100"), (0x000, b"", "t0000"), (0x7FF, bytes(range(1, 9)), "t7FF80102030405060708"), (0x1A4, b"\x0a", "t1A410A")],
)
def test_encode_line_is_upper_case_and_exact(can_id, data, line):
    assert slcan.encode_line(can_id, data) == line


@pytest.mark.parametrize("can_id,data", [(0x800, b""), (0xFFF, b"\x00"), (-1, b""), (0x100, bytes(9))])
def test_encode_line_refuses_what_a_classic_frame_cannot_carry(can_id, data):
    with pytest.raises(framing.FrameError):
        slcan.encode_line(can_id, data)


@pytest.mark.parametrize(
    "line",
    [
        "", "z", "t", "t11", "t1G10", "t+1F0", "t0x10", "t1_20", "t 100", "t10002",
        "t11140102", "t1239010203040506070809", "t123F000000000000000000000000000000",
        "T0000011180102030405060708", "T000001110", "r1110", "R000001110",
        "t-100", "t1.00", "t1000\x00",
    ],
)
def test_lines_that_hold_no_valid_standard_frame(line):
    assert slcan.decode_line(line) is None, line


def test_white_space_around_a_line_is_stripped_like_the_terminator():
    assert slcan.decode_line("t1000 ") == framing.CanFrame(0x100, b"")
    assert slcan.decode_line("  t1000\n") == framing.CanFrame(0x100, b"")


def test_hex_digits_are_accepted_in_either_case():
    assert slcan.decode_line("t1a6101") == framing.CanFrame(0x1A6, b"\x01")
    assert slcan.decode_line("t1A6101") == framing.CanFrame(0x1A6, b"\x01")
    assert slcan.decode_line("t7ff8ffffffffffffffff").data == b"\xff" * 8


def test_an_adapter_timestamp_after_the_payload_makes_the_line_unusable():
    # The protocol never enables timestamps; a line longer than its DLC implies is dropped, not trimmed.
    assert slcan.decode_line("t11101234") is None


def test_a_status_character_glued_to_a_frame_is_skipped():
    assert slcan.decode_line("zt1000") == framing.CanFrame(0x100, b"")
    assert slcan.decode_line("\x07t1000") == framing.CanFrame(0x100, b"")
    assert slcan.decode_line("zT1000") is None


def test_the_reader_joins_a_line_split_over_several_reads():
    reader = slcan.LineReader()
    assert reader.frames(b"t7F98") == []
    assert reader.frames(b"000303CC") == []
    assert reader.frames(b"01000003\r") == [framing.CanFrame(0x7F9, bytes.fromhex("000303CC01000003"))]
    assert reader.buffer == b""


def test_the_reader_yields_every_frame_of_a_burst_and_skips_noise():
    reader = slcan.LineReader()
    chunk = b"z\rt1000\r\xff\xfe\rT0000011180102030405060708\rt1101AA\rr1110\r"
    assert reader.frames(chunk) == [framing.CanFrame(0x100, b""), framing.CanFrame(0x110, b"\xaa")]


def test_a_buffer_without_a_terminator_is_discarded_past_the_limit():
    reader = slcan.LineReader()
    assert reader.frames(b"A" * (slcan.RX_BUFFER_LIMIT + 1)) == []
    assert reader.buffer == b""
    assert reader.frames(b"t1000\r") == [framing.CanFrame(0x100, b"")]
    small = slcan.LineReader(limit=10)
    small.feed(b"t1")
    assert small.buffer == b"t1"


def test_a_burst_with_complete_lines_is_not_thrown_away_for_being_long():
    reader = slcan.LineReader()
    burst = b"t1000\r" * 1000
    assert len(reader.frames(burst)) == 1000


def test_clear_drops_the_unfinished_line():
    reader = slcan.LineReader()
    reader.feed(b"t7F98")
    reader.clear()
    assert reader.frames(b"t1000\r") == [framing.CanFrame(0x100, b"")]


def test_the_frame_object_validates_and_describes_itself():
    frame = framing.CanFrame.from_hex("0x1a6", "01")
    assert frame.id == 0x1A6 and frame.dlc == 1 and frame.id_hex() == "0x1A6" and frame.data_hex() == "01" and frame.name() == "SET_MLX_VARIANT"
    assert framing.CanFrame(0x7FF).name() is not None and framing.CanFrame(0x3FF).name() is None
    with pytest.raises(framing.FrameError):
        framing.CanFrame(0x800)
    with pytest.raises(framing.FrameError):
        framing.CanFrame(0x100, bytes(9))
    with pytest.raises(framing.FrameError):
        framing.CanFrame(True)  # a boolean is not an identifier


def test_magic_frames_are_recognised_only_with_identifier_and_payload_together():
    assert framing.is_magic(0x7F0, bytes.fromhex("B0071D5A")) == "enter_bootloader"
    assert framing.is_magic(0x7F0, bytes.fromhex("B0071D5B")) is None
    assert framing.is_magic(0x7F1, bytes.fromhex("B0071D5A")) is None
    assert framing.is_magic(0x131, b"RSP0") == "solder_feeder_reset"
