# =============================================================================
# URTC-COMMON - tests/test_safety_policy.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The clear-error command and the communication watchdog: the specification, the reference decisions and the vectors the firmware replays."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_safety_vectors  # noqa: E402
from urtc_common import protocol as p  # noqa: E402
from urtc_common import quick_state  # noqa: E402
from urtc_common import safety_policy as sp  # noqa: E402

SPEC = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "conformance" / "safety_policy_vectors.json").read_text(encoding="utf-8"))
ENUMS = {entry["name"]: {v["name"]: v["value"] for v in entry["values"]} for entry in SPEC["enums"]}


def message(identifier: str) -> dict:
    return next(m for m in SPEC["messages"] if m["id"] == identifier)


# ---------------------------------------------------------------------------------------------------------------------
# the specification
# ---------------------------------------------------------------------------------------------------------------------
def test_the_three_new_features_are_switches_that_start_off_in_the_mask():
    features = ENUMS["firmware_feature"]
    assert features["CLEAR_ERROR"] == 16 and features["COMMS_WATCHDOG"] == 32 and features["MAGNET_RELEASE"] == 64
    assert len(set(features.values())) == len(features)          # no two features share a bit
    assert all(value & (value - 1) == 0 for value in features.values())   # each is one bit
    ranges = [f["range"] for lay in message("0x1AE")["layouts"] + message("0x1AF")["layouts"] for f in lay["fields"] if "range" in f]
    assert ranges and all(r == [0, 127] for r in ranges), "the mask fields must reach the seventh bit"
    assert max(features.values()) * 2 - 1 == 127


def test_the_clear_error_command_needs_its_magic_and_passes_the_error_gate():
    m = message("0x1B2")
    assert m["direction"] == "host_to_board" and m["gates"]["blocked_by_critical_error"] is False and m["gates"]["needs_magic"] == "clear_error"
    assert m["layouts"][0]["dlc"] == {"exact": 4} and m["firmware_accepts_dlc"] == {"exact": 4}
    assert p.MAGIC_CLEAR_ERROR == b"CLER"
    identifier, data = p.encode_clear_error(magic=p.MAGIC_CLEAR_ERROR)
    assert identifier == 0x1B2 and data == b"CLER"
    assert next(x for x in SPEC["magic_payloads"] if x["name"] == "clear_error")["id"] == "0x1B2"


def test_the_quick_state_answer_carries_the_reason_and_the_last_clear_result():
    lay = message("0x111")["layouts"][0]
    assert lay["dlc"] == {"min": 4, "max": 8}
    by_name = {f["name"]: f for f in lay["fields"]}
    assert by_name["error_reason"]["offset"] == 6 and by_name["clear_result"]["offset"] == 7
    assert by_name["error_reason"]["optional"] and by_name["clear_result"]["optional"]
    full = quick_state.decode(bytes([10, 1, 0, 0, 0, 8, p.ERROR_REASON_STEPPER_SILENCE, p.CLEAR_ERROR_REFUSED_HOT]))
    assert full["error_reason_name"] == "STEPPER_SILENCE" and full["clear_result_name"] == "REFUSED_HOT" and full["system_error"] is True
    old = quick_state.decode(bytes([10, 1, 0, 0, 0, 8]))
    assert old["error_reason"] is None and old["clear_result"] is None, "an older firmware does not report a reason: not zero"
    none = quick_state.decode(bytes([0, 0, 0, 0, 0, 0, 0, 0]))
    assert none["error_reason_name"] is None and none["clear_result_name"] is None


def test_every_error_reason_and_result_has_a_name_a_value_and_no_gaps():
    for enum in ("error_reason", "clear_error_result"):
        values = sorted(ENUMS[enum].values())
        assert values == list(range(len(values))), f"{enum} has a gap"
    assert ENUMS["error_reason"]["TOOL_ID"] == p.ERROR_REASON_TOOL_ID


def test_the_limits_are_in_the_specification_and_make_sense():
    assert p.CLEAR_ERROR_MAX_TEMP_C == 50
    assert p.STEPPER_SILENCE_MIN_MS == 1000 and p.STEPPER_SILENCE_PERCENT == 50
    assert p.MAGNET_SILENCE_MS == 5000
    assert p.MAGNET_SILENCE_MS > p.WATCHDOG_MS, "the coil waits longer than the 250 ms watchdogs of the other actuators"


def test_the_notes_of_the_stepper_and_the_electromagnet_name_the_switches():
    assert any("COMMS_WATCHDOG" in note for note in message("0x120")["notes"])
    assert "MAGNET_RELEASE" in message("0x1B0")["notes"][0] and "held" in message("0x1B0")["notes"][0]


# ---------------------------------------------------------------------------------------------------------------------
# the decisions
# ---------------------------------------------------------------------------------------------------------------------
def test_clear_error_is_refused_while_the_switch_is_off_whatever_else_is_true():
    for reason in range(9):
        for temperature in (0, 49, 50, sp.TEMPERATURE_UNKNOWN):
            for off in (True, False):
                assert sp.clear_error_decision(False, True, reason, temperature, off) == p.CLEAR_ERROR_REFUSED_SWITCH_OFF


def test_clear_error_checks_run_in_the_documented_order():
    ok = (True, True, p.ERROR_REASON_COMMS_WATCHDOG, 20, True)
    assert sp.clear_error_decision(*ok) == p.CLEAR_ERROR_CLEARED
    assert sp.clear_error_decision(True, False, 0, 20, True) == p.CLEAR_ERROR_REFUSED_NO_ERROR
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_TOOL_ID, 20, True) == p.CLEAR_ERROR_REFUSED_NOT_CLEARABLE
    # a hot board with an actuator on is reported hot first; an unreadable temperature counts as hot
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_THERMAL, 200, False) == p.CLEAR_ERROR_REFUSED_HOT
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_SENSOR, sp.TEMPERATURE_UNKNOWN, True) == p.CLEAR_ERROR_REFUSED_HOT
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_COMMS_WATCHDOG, 20, False) == p.CLEAR_ERROR_REFUSED_ACTUATOR_ON
    # the tool-identity error is never lifted, however cool and quiet the board is
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_TOOL_ID, 0, True) == p.CLEAR_ERROR_REFUSED_NOT_CLEARABLE


def test_the_temperature_limit_is_exclusive():
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_THERMAL, 49, True) == p.CLEAR_ERROR_CLEARED
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_THERMAL, 50, True) == p.CLEAR_ERROR_REFUSED_HOT


def test_the_silence_limit_of_a_move_never_falls_below_the_floor_and_never_overflows():
    assert sp.stepper_silence_limit_ms(0, 0) == p.STEPPER_SILENCE_MIN_MS
    assert sp.stepper_silence_limit_ms(100, 500) == p.STEPPER_SILENCE_MIN_MS
    assert sp.stepper_silence_limit_ms(4000, 500) == 4000       # 8 s of movement, half of it
    assert sp.stepper_silence_limit_ms(4000, 0) == 4000         # speed zero means the default speed
    assert sp.stepper_silence_limit_ms(0xFFFFFFFF, 1) == 0xFFFFFFFF
    assert sp.stepper_silence_limit_ms(0xFFFFFFFF, 0xFFFF) == 32768500


def test_the_silence_limit_grows_with_the_steps_and_shrinks_with_the_speed():
    rng = random.Random(20260101)
    for _ in range(2000):
        steps = rng.randrange(0, 2**32)
        speed = rng.randrange(0, 2**16)
        limit = sp.stepper_silence_limit_ms(steps, speed)
        assert p.STEPPER_SILENCE_MIN_MS <= limit <= 0xFFFFFFFF
        assert sp.stepper_silence_limit_ms(min(steps + 1000, 0xFFFFFFFF), speed) >= limit
        if speed >= 1:
            assert sp.stepper_silence_limit_ms(steps, speed + 1) <= limit


def test_the_watchdog_only_cuts_a_move_that_runs_with_the_switch_on_and_after_the_limit():
    assert sp.stepper_must_stop(True, True, 1001, 1000) is True
    assert sp.stepper_must_stop(True, True, 1000, 1000) is False
    assert sp.stepper_must_stop(False, True, 10**9, 1000) is False
    assert sp.stepper_must_stop(True, False, 10**9, 1000) is False


def test_the_electromagnet_holds_unless_both_switches_are_on_and_the_silence_is_long():
    for watchdog in (False, True):
        for release in (False, True):
            for energised in (False, True):
                expected = watchdog and release and energised
                assert sp.magnet_must_release(watchdog, release, energised, 5001) is expected
                assert sp.magnet_must_release(watchdog, release, energised, 5000) is False
    assert sp.magnet_must_release(True, False, True, 0xFFFFFFFF) is False, "the default policy is to hold"


# ---------------------------------------------------------------------------------------------------------------------
# the vectors
# ---------------------------------------------------------------------------------------------------------------------
def test_the_vectors_are_what_the_reference_produces_and_the_files_are_current():
    assert make_safety_vectors.build() == VECTORS
    assert (ROOT / "generated" / "safety_policy_vectors.h").read_text(encoding="utf-8").replace("\r\n", "\n") == make_safety_vectors.c_header(VECTORS)


def test_the_vectors_cover_every_outcome_and_both_sides_of_every_limit():
    results = {c["result"] for c in VECTORS["clear"]}
    assert results == set(range(1, 7)), "every outcome of the clear-error command is exercised"
    assert {c["stop"] for c in VECTORS["stepper_stop"]} == {True, False}
    assert {c["release"] for c in VECTORS["magnet"]} == {True, False}
    temperatures = {c["temperature_c"] for c in VECTORS["clear"]}
    assert {49, 50, 51, sp.TEMPERATURE_UNKNOWN} <= temperatures
    silences = {c["silence_ms"] for c in VECTORS["magnet"]}
    assert {4999, 5000, 5001} <= silences
    constants = VECTORS["constants"]
    assert constants["clear_error_max_temp_c"] == p.CLEAR_ERROR_MAX_TEMP_C and constants["magnet_silence_ms"] == p.MAGNET_SILENCE_MS
