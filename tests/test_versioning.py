# =============================================================================
# URTC-COMMON - tests/test_versioning.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The version query, the patch number, the quick state and the order of versions."""
from __future__ import annotations

import pytest

from urtc_common import protocol, quick_state, versioning

APP = (0x7F9, bytes.fromhex("000303CC01000003"))


def test_an_application_without_the_patch_frame_has_an_unknown_patch():
    answer = versioning.parse_version_answer([APP])
    assert answer["responder"] == "application" and answer["hardware_id"] == "0x0303CC01"
    assert (answer["major"], answer["minor"], answer["patch"]) == (0, 3, None)
    assert answer["patch_aware"] is False and answer["accepts_patch_in_end_update"] is False


def test_the_patch_frame_gives_the_patch_and_the_flag():
    answer = versioning.parse_version_answer([APP, (0x7E9, bytes([0, 5, 0]))])
    assert answer["patch"] == 5 and answer["patch_aware"] is True and answer["accepts_patch_in_end_update"] is False
    answer = versioning.parse_version_answer([(0x7F9, bytes.fromhex("010303CC01000004")), (0x7FA, bytes([0, 3, 9])), (0x7E9, bytes([1, 7, 1]))])
    assert answer["responder"] == "bootloader" and answer["accepts_patch_in_end_update"] is True and answer["bootloader"] == (0, 3, 9)


def test_patch_ff_means_unknown_but_the_board_knows_the_extension():
    answer = versioning.parse_version_answer([APP, (0x7E9, bytes([0, 0xFF, 0]))])
    assert answer["patch"] is None and answer["patch_aware"] is True


def test_a_short_or_late_frame_is_not_a_patch_frame_and_extra_bytes_are_ignored():
    assert versioning.parse_version_answer([APP, (0x7E9, bytes([0, 5]))])["patch_aware"] is False
    assert versioning.parse_version_answer([APP, (0x7E9, bytes([0, 9, 0, 0x7F]))])["patch"] == 9


def test_no_answer_without_a_whole_version_frame():
    assert versioning.parse_version_answer([]) is None
    assert versioning.parse_version_answer([(0x7F9, bytes(7))]) is None
    assert versioning.parse_version_answer([(0x7E9, bytes([0, 5, 0]))]) is None


def test_the_application_never_reports_a_bootloader_version():
    answer = versioning.parse_version_answer([APP, (0x7FA, bytes([0, 3, 9]))])
    assert "bootloader" not in answer


def test_only_the_first_answer_of_each_kind_counts():
    answer = versioning.parse_version_answer([APP, (0x7F9, bytes.fromhex("000303CC01000009"))])
    assert answer["minor"] == 3


@pytest.mark.parametrize(
    "minor,patch,accepts,expected",
    [(3, 5, True, 0x8503), (3, 5, False, 3), (3, None, True, 3), (3, 0, True, 0x8003), (3, 127, True, 0xFF03), (3, 128, True, 3), (255, 1, True, 0x81FF), (3, -1, True, 3)],
)
def test_the_patch_rides_in_the_minor_field_only_towards_a_bootloader_that_announced_it(minor, patch, accepts, expected):
    assert versioning.end_update_minor_field(minor, patch, accepts) == expected


def test_a_minor_field_is_split_back_into_minor_and_patch():
    for minor in (0, 3, 255):
        for patch in (None, 0, 5, 127):
            field = versioning.end_update_minor_field(minor, patch, True)
            assert protocol.minor_field_minor(field) == minor and protocol.minor_field_patch(field) == patch


@pytest.mark.parametrize(
    "installed,candidate,expected",
    [((0, 3, 5), (0, 3, 5), 0), ((0, 3, 5), (0, 3, 6), 1), ((0, 3, 5), (0, 3, 4), -1), ((0, 3, None), (0, 3, 4), 0), ((0, 3, 5), (0, 3, None), 0),
     ((0, 3, 9), (0, 4, 0), 1), ((0, 4, 0), (0, 3, 9), -1), ((1, 0, 0), (0, 9, 9), -1), ((0, 9, 9), (1, 0, 0), 1)],
)
def test_the_order_decides_on_major_and_minor_and_the_patch_only_when_both_have_one(installed, candidate, expected):
    assert versioning.compare(installed, candidate) == expected


def test_quick_state_legacy_lengths():
    four = quick_state.decode(bytes.fromhex("0A000100"))
    assert four["tool_id"] == 10 and four["can_error"] is True and four["thermal_fault"] is None and four["reset_cause"] is None and four["watchdog_reset"] is False
    five = quick_state.decode(bytes.fromhex("0A01000002"))
    assert five["system_error"] is True and five["thermal_fault"] == 2 and five["thermal_fault_name"] == "HEATING_NO_RISE" and five["reset_cause"] is None
    six = quick_state.decode(bytes.fromhex("000000000001"))
    assert six["thermal_fault"] == 0 and six["thermal_fault_name"] is None and six["watchdog_reset"] is True and six["reset_causes"] == ["IWDG"]
    assert quick_state.decode(bytes.fromhex("000000")) is None


def test_quick_state_names_every_reset_cause_bit_and_an_unknown_fault_code():
    state = quick_state.decode(bytes.fromhex("19000001" + "09" + "0C"))
    assert state["reset_causes"] == ["SOFTWARE", "POWER_ON"] and state["thermal_fault"] == 9 and state["thermal_fault_name"] == "CODE_9"
    assert state["booting"] is True and state["tool_id"] == 25


# ---- the application of the expansion slave: 0x221 and its companion 0x222 -------------------------------------------------------
SLAVE_VECTORS = __import__("json").loads((__import__("pathlib").Path(__file__).resolve().parents[1] / "conformance" / "slave_version_vectors.json").read_text(encoding="utf-8"))


def test_the_request_asks_for_the_version_register_of_the_slave():
    can_id, data = versioning.slave_app_version_request()
    assert (can_id, data.hex()) == (SLAVE_VECTORS["request"]["id"], SLAVE_VECTORS["request"]["data"])


@pytest.mark.parametrize("case", SLAVE_VECTORS["cases"], ids=lambda case: case["name"])
def test_the_slave_version_is_read_as_the_vectors_say(case):
    info = versioning.parse_slave_app_version([(can_id, bytes.fromhex(data)) for can_id, data in case["frames"]])
    assert info == case["expected"]
    assert versioning.slave_app_version_text(info) == case["text"]
