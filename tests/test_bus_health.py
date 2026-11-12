# =============================================================================
# URTC-COMMON - tests/test_bus_health.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A bus that mixes speeds is recognised by its symptoms, with no change of the protocol; the thresholds come from the configuration file."""
from __future__ import annotations

import pytest

from urtc_common import bus_health as bh
from urtc_common import protocol as p
from urtc_common.slcan import LineReader, encode_line
from urtc_common.virtual_board import SlcanAdapter, VirtualBoard

QUIET = {"tec": 0, "rec": 0, "bus_off_count": 0}


def test_a_quiet_bus_has_nothing_to_say():
    assert bh.warnings([QUIET, QUIET]) == []
    assert bh.warnings([]) == []


@pytest.mark.parametrize("profile", [{"tec": 96, "rec": 0, "bus_off_count": 0}, {"tec": 0, "rec": 96, "bus_off_count": 0}, {"tec": 0, "rec": 0, "bus_off_count": 1}])
def test_the_error_counters_or_a_bus_off_at_the_threshold_warn_of_bus_errors(profile):
    assert bh.warnings([QUIET, profile]) == [bh.BUS_ERRORS]


@pytest.mark.parametrize("profile", [{"tec": 95, "rec": 95, "bus_off_count": 0}, {}, {"tec": None}])
def test_below_the_thresholds_or_without_the_fields_there_is_no_warning(profile):
    assert bh.warnings([profile]) == []


def test_a_search_that_found_nobody_at_any_speed_says_so():
    assert bh.warnings([], found_nobody_at_any_speed=True) == [bh.NO_HEAD_AT_ANY_SPEED]


def test_a_known_legacy_head_is_reported_and_with_errors_the_bus_is_suspected_of_mixing_speeds():
    limits = bh.Thresholds(legacy_heads=("HEAD-OLD",))
    assert bh.warnings([QUIET], heads_on_bus=["HEAD-OLD", "HEAD-NEW"], thresholds=limits) == [bh.LEGACY_HEAD_KNOWN]
    noisy = {"tec": 120, "rec": 0, "bus_off_count": 0}
    assert bh.warnings([noisy], heads_on_bus=["HEAD-OLD"], thresholds=limits) == [bh.MIXED_BUS_SUSPECTED, bh.BUS_ERRORS, bh.LEGACY_HEAD_KNOWN]
    assert bh.warnings([noisy], heads_on_bus=["HEAD-NEW"], thresholds=limits) == [bh.BUS_ERRORS]
    assert bh.warnings([noisy], heads_on_bus=["HEAD-OLD"]) == [bh.BUS_ERRORS]          # a head is legacy only when the configuration says so


def test_the_codes_are_listed_from_the_most_to_the_least_serious_and_each_once():
    limits = bh.Thresholds(legacy_heads=("1",))
    result = bh.warnings([{"tec": 200, "bus_off_count": 3}], True, [1], limits)
    assert result == [bh.MIXED_BUS_SUSPECTED, bh.NO_HEAD_AT_ANY_SPEED, bh.BUS_ERRORS, bh.LEGACY_HEAD_KNOWN]
    assert sorted(result) == sorted(bh.CODES) and result == [code for code in bh.CODES if code in result]


def test_the_thresholds_come_from_the_configuration_and_a_bad_value_keeps_its_default():
    assert bh.thresholds_from_config(None) == bh.Thresholds()
    assert bh.thresholds_from_config("oops") == bh.Thresholds()
    given = {"tec_warn": 50, "rec_warn": 60, "bus_off_warn": 2, "legacy_heads": ["A", 7, True, None]}
    assert bh.thresholds_from_config(given) == bh.Thresholds(50, 60, 2, ("A", "7"))
    bad = {"tec_warn": 0, "rec_warn": 256, "bus_off_warn": True, "legacy_heads": "A"}
    assert bh.thresholds_from_config(bad) == bh.Thresholds()
    assert bh.thresholds_from_config({"tec_warn": 1.5, "rec_warn": "9"}) == bh.Thresholds()


def test_a_lower_threshold_warns_earlier():
    profile = {"tec": 40, "rec": 0, "bus_off_count": 0}
    assert bh.warnings([profile]) == []
    assert bh.warnings([profile], thresholds=bh.thresholds_from_config({"tec_warn": 40})) == [bh.BUS_ERRORS]


def test_the_names_that_are_legacy_are_matched_as_text():
    limits = bh.thresholds_from_config({"legacy_heads": [12345, "abc"]})
    assert bh.is_legacy_head(12345, limits) and bh.is_legacy_head("12345", limits) and bh.is_legacy_head("abc", limits)
    assert not bh.is_legacy_head(None, limits) and not bh.is_legacy_head("other", limits)


# ---- with the virtual bus: a head at another speed is never heard ----------------------------------------------------------------------------------
def _heard(adapter: SlcanAdapter, code: str) -> bool:
    adapter.feed(b"C\rS" + code.encode() + b"\rO\r")
    reply = adapter.feed(encode_line(p.CAN_ID_QUERY_VERSION).encode() + b"\r")
    return bool(LineReader().frames(reply))


def _search_every_speed(adapter: SlcanAdapter) -> bool:
    """True when nobody answered at any of the speeds of the adapter table (the search of the tools)."""
    return not any(_heard(adapter, code) for _label, code in p.SLCAN_BITRATES)


def test_a_head_on_the_bus_of_the_adapters_speed_is_found_and_the_search_has_nothing_to_warn_about():
    adapter = SlcanAdapter(VirtualBoard(), bus_bitrate_code=p.SLCAN_BITRATE_DEFAULT_CODE)
    found_nobody = _search_every_speed(adapter)
    assert found_nobody is False and bh.warnings([QUIET], found_nobody) == []


def test_a_head_at_a_speed_the_table_does_not_have_leaves_the_search_empty_and_the_tool_warns():
    adapter = SlcanAdapter(VirtualBoard(), bus_bitrate_code="9")                 # a code that no adapter setting reaches
    found_nobody = _search_every_speed(adapter)
    assert found_nobody is True
    assert bh.warnings([], found_nobody) == [bh.NO_HEAD_AT_ANY_SPEED]


def test_a_bus_with_a_head_of_the_legacy_speed_that_is_heard_and_noisy_is_suspected_of_mixing_speeds():
    limits = bh.thresholds_from_config({"legacy_heads": ["HEAD-OLD"], "tec_warn": 64})
    heard = {"tec": 70, "rec": 3, "bus_off_count": 0}                              # a head that is heard shows the errors the other one causes
    assert bh.warnings([heard], False, ["HEAD-OLD", "HEAD-NEW"], limits)[0] == bh.MIXED_BUS_SUSPECTED
