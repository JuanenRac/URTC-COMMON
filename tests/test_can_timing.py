# =============================================================================
# URTC-COMMON - tests/test_can_timing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The bit rate of the bus of the tool heads (one specification) and the timing the firmware computes from it: exact, with the sample point not below the floor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from urtc_common import can_timing as ct
from urtc_common import protocol as p

SPEC = json.loads((Path(__file__).resolve().parent.parent / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
CONSTANTS = {item["name"]: item["value"] for item in SPEC["constants"]}


def test_the_heads_default_to_one_megabit_and_five_hundred_kilobit_is_the_legacy_option():
    assert p.BITRATE == CONSTANTS["BITRATE"] == 1_000_000
    assert p.BITRATE_LEGACY == CONSTANTS["BITRATE_LEGACY"] == 500_000
    assert (ct.BITRATE_DEFAULT, ct.BITRATE_LEGACY) == (1_000_000, 500_000)
    assert SPEC["slcan"]["bitrate_default_code"] == "8"
    assert dict((code, name) for name, code in SPEC["slcan"]["bitrate_codes"])["8"] == "1 Mbit/s"


def test_the_sample_point_and_the_jump_width_come_from_the_specification():
    assert (p.CAN_SAMPLE_POINT_PERMILLE, p.CAN_SAMPLE_POINT_MIN_PERMILLE, p.CAN_SJW_TQ) == (875, 750, 2)
    assert ct.SAMPLE_POINT_MIN_PERMILLE <= ct.SAMPLE_POINT_PERMILLE


def test_the_master_clock_gives_the_two_known_timings():
    assert ct.compute(32_000_000, 1_000_000) == ct.Timing(prescaler=2, bs1=13, bs2=2, sjw=2)
    assert ct.compute(32_000_000, 500_000) == ct.Timing(prescaler=4, bs1=13, bs2=2, sjw=2)


@pytest.mark.parametrize("row", ct.table(), ids=lambda row: f"{row['pclk_hz']}-{row['bitrate']}")
def test_every_clock_and_rate_of_the_table_has_an_exact_timing_with_a_sample_point_of_at_least_75_percent(row):
    timing = row["timing"]
    assert timing is not None, f"no exact timing for {row['bitrate']} from {row['pclk_hz']} Hz"
    assert row["actual"] == row["bitrate"] and row["error_ppm"] == 0
    assert row["sample_permille"] >= p.CAN_SAMPLE_POINT_MIN_PERMILLE
    assert 1 <= timing.prescaler <= 1024 and 1 <= timing.bs1 <= 16 and 1 <= timing.bs2 <= 8 and 1 <= timing.sjw <= min(4, timing.bs2)
    assert row["tolerance_ppm"] > 0


def test_the_table_has_one_row_per_clock_and_rate():
    rows = ct.table()
    assert len(rows) == len(ct.PERIPHERAL_CLOCKS_HZ) * 2
    assert {row["bitrate"] for row in rows} == {ct.BITRATE_DEFAULT, ct.BITRATE_LEGACY}


def test_a_clock_that_cannot_give_the_rate_exactly_has_no_timing_and_is_said_so_in_the_table():
    assert ct.compute(33_000_000, 1_000_000) is None or ct.compute(33_000_000, 1_000_000).rate(33_000_000) == 1_000_000
    assert ct.compute(31_999_999, 1_000_000) is None
    row = ct.table({"odd": 31_999_999}, (1_000_000,))[0]
    assert row["timing"] is None and row["pclk_hz"] == 31_999_999


@pytest.mark.parametrize("args", [(0, 1_000_000), (32_000_000, 0), (-1, 1_000_000), (32_000_000, 1_000_000, 499), (32_000_000, 1_000_000, 901)])
def test_bad_arguments_give_no_timing(args):
    assert ct.compute(*args) is None


def test_the_jump_width_is_held_between_one_and_the_second_segment():
    assert ct.compute(32_000_000, 1_000_000, 875, 9).sjw == 2
    assert ct.compute(32_000_000, 1_000_000, 875, 0).sjw == 1
    assert ct.compute(32_000_000, 1_000_000, 875, 1).sjw == 1


def test_the_sample_point_follows_the_wanted_one_as_closely_as_the_quanta_allow():
    for wanted in (750, 800, 875):
        timing = ct.compute(32_000_000, 1_000_000, wanted)
        assert timing is not None and abs(timing.sample_permille - wanted) <= 63 and timing.sample_permille >= 750


def test_the_tolerance_of_the_clock_is_the_same_at_both_rates_because_the_quanta_are_the_same():
    one = ct.compute(32_000_000, 1_000_000)
    half = ct.compute(32_000_000, 500_000)
    assert one.total_tq == half.total_tq == 16
    assert one.tolerance_ppm == half.tolerance_ppm == 4854        # 0.49 percent: a bus of two heads needs clocks better than half of it, so a crystal (not the internal RC) at either rate


def test_a_bus_of_mixed_speeds_is_warned_about_and_one_speed_is_not():
    assert ct.mixed_rate_warning([1_000_000, 1_000_000]) is None
    assert ct.mixed_rate_warning([]) is None
    assert ct.mixed_rate_warning([0, 1_000_000]) is None
    warning = ct.mixed_rate_warning([500_000, 1_000_000, 500_000])
    assert warning is not None and "500 kbit/s" in warning and "1000 kbit/s" in warning


def test_the_bus_limits_say_the_trunk_is_shorter_at_one_megabit():
    one, half = ct.BUS_LIMITS[1_000_000], ct.BUS_LIMITS[500_000]
    assert one["max_trunk_m"] < half["max_trunk_m"] and one["max_stub_m"] <= half["max_stub_m"] and one["terminations"] == half["terminations"] == 2


def test_the_discovery_window_of_the_multinode_scan_is_shorter_at_the_higher_rate():
    from urtc_common import multinode as mn
    assert mn.discover_window_ms(bitrate=1_000_000) <= mn.discover_window_ms(bitrate=500_000)


# ---- a board on a bus at another speed (the virtual adapter) ---------------------------------------------------------------------------------------
def _query(adapter, code: str) -> bytes:
    from urtc_common.slcan import encode_line
    adapter.feed(b"C\rS" + code.encode() + b"\rO\r")
    return adapter.feed(encode_line(p.CAN_ID_QUERY_VERSION).encode() + b"\r")


def test_a_board_on_a_one_megabit_bus_answers_an_adapter_at_one_megabit_and_is_deaf_to_one_at_another_speed():
    from urtc_common.slcan import LineReader
    from urtc_common.virtual_board import SlcanAdapter, VirtualBoard
    adapter = SlcanAdapter(VirtualBoard(), bus_bitrate_code=p.SLCAN_BITRATE_DEFAULT_CODE)
    right = LineReader().frames(_query(adapter, p.SLCAN_BITRATE_DEFAULT_CODE))
    assert [frame.id for frame in right][:1] == [p.CAN_ID_VERSION_RESPONSE]
    wrong = _query(adapter, "6")                         # the adapter set to the legacy 500 kbit/s on a 1 Mbit/s bus
    assert wrong == b"z\r" and LineReader().frames(wrong) == []
    assert adapter.board.received.count((p.CAN_ID_QUERY_VERSION, b"")) == 1       # the board heard only the frame sent at its own speed


def test_a_board_on_a_legacy_bus_is_found_only_at_the_legacy_speed():
    from urtc_common.slcan import LineReader
    from urtc_common.virtual_board import SlcanAdapter, VirtualBoard
    adapter = SlcanAdapter(VirtualBoard(), bus_bitrate_code="6")
    assert LineReader().frames(_query(adapter, p.SLCAN_BITRATE_DEFAULT_CODE)) == []
    assert LineReader().frames(_query(adapter, "6")) != []


def test_without_a_bus_speed_the_adapter_behaves_as_before():
    from urtc_common.slcan import LineReader
    from urtc_common.virtual_board import SlcanAdapter, VirtualBoard
    adapter = SlcanAdapter(VirtualBoard())
    assert LineReader().frames(_query(adapter, "3")) != []
