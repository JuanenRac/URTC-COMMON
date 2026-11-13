# =============================================================================
# URTC-COMMON - tests/test_health_info.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The identity frame 0x1BB in both protocol versions: a head of version 2 declares the bit rate of its bus, one of version 1 declares nothing and is read as before."""
from __future__ import annotations

import random

import pytest

from urtc_common import bus_health as bh
from urtc_common import can_timing as ct
from urtc_common import health_info as hi
from urtc_common import protocol as p
from urtc_common.virtual_board import SlcanAdapter, VirtualBoard


def test_the_protocol_is_at_version_two_and_the_codes_are_those_of_the_specification():
    assert p.PROTOCOL_VERSION == 2 == hi.FIRST_DECLARING_VERSION
    assert hi.CAN_ID_HEALTH_INFO == p.CAN_ID_HEALTH_INFO
    assert (hi.CODE_UNKNOWN, hi.CODE_OF_RATE[p.BITRATE], hi.CODE_OF_RATE[p.BITRATE_LEGACY]) == (p.BUS_RATE_UNKNOWN, p.BUS_RATE_MBIT_1, p.BUS_RATE_KBIT_500)
    assert (hi.CODE_OF_RATE[250_000], hi.CODE_OF_RATE[125_000]) == (p.BUS_RATE_KBIT_250, p.BUS_RATE_KBIT_125)
    assert sorted(hi.RATE_OF_CODE) == [code for code in sorted(p.ENUM_NAMES["bus_rate_code"]) if code != p.BUS_RATE_UNKNOWN]


def test_the_example_of_the_specification_is_read_back():
    can_id, data = p.encode_health_info(2, 8, 4, 4, 0, p.BUS_RATE_MBIT_1, 3600)
    assert can_id == 0x1BB and data.hex().upper() == "0208040400010E10"
    info = hi.parse(data)
    assert info is not None
    assert (info.protocol_version, info.reset_cause, info.fw_minor, info.fw_patch, info.fw_build, info.uptime_s, info.rate_code, info.rate_bps) == (2, 8, 4, 4, 0, 3600, 1, 1_000_000)
    assert hi.encode(2, 8, 4, 4, 0, 3600, 1_000_000) == data


@pytest.mark.parametrize("rate", [1_000_000, 500_000, 250_000, 125_000])
def test_every_known_rate_goes_through_a_frame_of_version_two(rate):
    info = hi.parse(hi.encode(2, 0, 1, 2, 3, 99, rate))
    assert info is not None and info.rate_bps == rate and info.uptime_s == 99


@pytest.mark.parametrize("rate", [None, 0, 800_000, 33_333])
def test_a_rate_that_is_not_one_of_the_four_is_declared_as_unknown(rate):
    info = hi.parse(hi.encode(2, 0, 1, 2, 3, 99, rate))
    assert info is not None and info.rate_code == hi.CODE_UNKNOWN and info.rate_bps is None


def test_a_frame_of_version_one_declares_nothing_and_keeps_its_24_bit_uptime():
    frame = bytes([1, 8, 4, 4, 0, 0x01, 0x0E, 0x10])          # in version 1 the byte 5 is the top byte of the uptime: 0x010E10 s, NOT a rate of 1 Mbit/s
    info = hi.parse(frame)
    assert info is not None and info.rate_code is None and info.rate_bps is None and info.uptime_s == 0x010E10
    assert hi.encode(1, 8, 4, 4, 0, 0x010E10, 1_000_000) == frame             # a head of version 1 cannot declare: the rate argument is ignored


def test_the_uptime_of_version_two_stops_at_65535_and_never_wraps():
    assert hi.parse(hi.encode(2, 0, 0, 0, 0, 70_000, 1_000_000)).uptime_s == hi.UPTIME_V2_MAX
    assert hi.parse(hi.encode(2, 0, 0, 0, 0, -5, 1_000_000)).uptime_s == 0
    assert hi.parse(hi.encode(1, 0, 0, 0, 0, 2**30, None)).uptime_s == 0xFFFFFF


@pytest.mark.parametrize("length", [0, 1, 7, 9, 64])
def test_a_payload_that_is_not_eight_bytes_is_not_an_identity_frame(length):
    assert hi.parse(bytes(length)) is None


def test_a_version_older_than_one_or_newer_than_two_is_read_by_its_byte_zero_only():
    assert hi.parse(bytes([0, 0, 0, 0, 0, 2, 0, 0])).rate_code is None            # version 0 never existed: read like version 1
    assert hi.parse(bytes([3, 0, 0, 0, 0, 2, 0, 0])).rate_bps == 500_000         # a later version keeps the byte (the host is told to read it as a rate from 2 on)
    assert hi.parse(bytes([2, 0, 0, 0, 0, 77, 0, 0])).rate_bps is None            # a code this reader does not know is not a rate


def test_an_old_reader_sees_only_a_wrong_uptime_in_the_new_frame():
    data = hi.encode(2, 8, 4, 4, 0, 3600, 1_000_000)
    old_uptime = int.from_bytes(data[5:8], "big")                                  # what a reader of version 1 computes
    assert old_uptime == p.BUS_RATE_MBIT_1 * 65536 + 3600 and data[:5] == bytes([2, 8, 4, 4, 0])


def test_random_frames_never_break_the_reader_and_a_version_two_frame_round_trips():
    rng = random.Random(1101)
    for _ in range(500):
        raw = bytes(rng.randrange(256) for _ in range(8))
        info = hi.parse(raw)
        assert info is not None and 0 <= info.uptime_s <= 0xFFFFFF
        assert (info.rate_code is None) == (raw[0] < 2)
        if raw[0] >= 2:
            assert info.uptime_s <= 0xFFFF and info.rate_code == raw[5]
    for _ in range(200):
        rate, up = rng.choice(list(hi.CODE_OF_RATE)), rng.randrange(0, 70_000)
        info = hi.parse(hi.encode(2, rng.randrange(256), rng.randrange(256), rng.randrange(256), rng.randrange(256), up, rate))
        assert info.rate_bps == rate and info.uptime_s == min(up, 65535)


def test_the_rates_of_a_set_of_frames_skip_the_heads_that_declare_nothing():
    frames = [hi.encode(2, 0, 0, 0, 0, 1, 1_000_000), hi.encode(1, 0, 0, 0, 0, 1, None), b"\x02", hi.encode(2, 0, 0, 0, 0, 1, None), hi.encode(2, 0, 0, 0, 0, 1, 500_000)]
    assert hi.declared_rates(frames) == [1_000_000, 500_000]
    assert hi.rates_by_head({"A": frames[0], 7: frames[1], "C": frames[4], "D": b""}) == {"A": 1_000_000, "7": None, "C": 500_000, "D": None}


def test_the_rate_text_is_numbers_and_units_only():
    assert [hi.rate_text(r) for r in (1_000_000, 500_000, 250_000, 125_000, None, 0)] == ["1 Mbit/s", "500 kbit/s", "250 kbit/s", "125 kbit/s", "", ""]


# ---- the bus judgement and the timing warning use the declaration ---------------------------------------------------------------------------------
QUIET = {"tec": 0, "rec": 0, "bus_off_count": 0}


def test_two_different_declared_rates_are_a_mixed_bus_for_certain_and_come_first():
    assert bh.warnings([QUIET], declared_rates=[1_000_000, 500_000]) == [bh.RATES_DECLARED_DIFFER]
    noisy = {"tec": 120, "rec": 0, "bus_off_count": 0}
    result = bh.warnings([noisy], True, ["HEAD-OLD"], bh.Thresholds(legacy_heads=("HEAD-OLD",)), [1_000_000, 500_000])
    assert result == list(bh.CODES) and result[0] == bh.RATES_DECLARED_DIFFER


@pytest.mark.parametrize("declared", [[], [None], [1_000_000], [1_000_000, 1_000_000], [None, 500_000], [0, 1_000_000, None]])
def test_equal_or_missing_declarations_add_nothing_to_the_symptom_judgement(declared):
    assert bh.warnings([QUIET], declared_rates=declared) == []
    assert bh.warnings([{"tec": 120}], declared_rates=declared) == [bh.BUS_ERRORS]


def test_the_timing_warning_prefers_what_the_heads_declare_and_falls_back_on_what_the_tool_knows():
    mixed = [hi.encode(2, 0, 0, 0, 0, 1, 1_000_000), hi.encode(2, 0, 0, 0, 0, 1, 500_000)]
    assert ct.declared_rate_warning(mixed) == "mixed_bitrates: 500 kbit/s, 1000 kbit/s"
    assert ct.declared_rate_warning([hi.encode(2, 0, 0, 0, 0, 1, 1_000_000)] * 3) is None
    assert ct.declared_rate_warning([hi.encode(1, 0, 0, 0, 0, 1, None)], [500_000, 1_000_000]) == ct.mixed_rate_warning([500_000, 1_000_000])
    assert ct.declared_rate_warning([], [1_000_000]) is None
    assert ct.declared_rate_warning(mixed, [250_000, 125_000]) == "mixed_bitrates: 500 kbit/s, 1000 kbit/s"          # the declaration wins over the fallback


def test_the_tap_keeps_the_identity_frames_apart_from_the_health_frames():
    class Transport:
        def __init__(self, frames):
            self.frames = list(frames)

        def read_frame(self, timeout: float = 0.05):
            return self.frames.pop(0) if self.frames else None

    info = hi.encode(2, 0, 1, 2, 3, 5, 1_000_000)
    health = bytes([0, 0, 0, 16, 7, 65, 12, 228])
    transport = Transport([(bh.CAN_ID_HEALTH_INFO, info), (bh.CAN_ID_HEALTH_PROFILE, health), (0x111, b"\x01"), (bh.CAN_ID_HEALTH_INFO, info)])
    tap = bh.HealthTap(transport, keep=1)
    for _ in range(4):
        transport.read_frame()
    assert tap.take_info() == [info] and tap.take_info() == [] and tap.take() == [health]
    assert bh.CAN_ID_HEALTH_INFO == hi.CAN_ID_HEALTH_INFO


def test_a_virtual_adapter_at_another_rate_still_hears_nobody_so_no_declaration_can_contradict_the_bus():
    adapter = SlcanAdapter(VirtualBoard(), bus_bitrate_code="9")
    assert adapter.bus_bitrate_code == "9"
    assert ct.declared_rate_warning([]) is None            # nothing heard, nothing declared: the symptoms (search at every speed) are the only evidence
