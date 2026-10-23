# =============================================================================
# URTC-COMMON - tests/test_links.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The two companion links (the rack serial frame and the vision sensor frame): big-endian, version 2, same vectors everywhere."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from urtc_common import rack_sim as rk
from urtc_common import sensor_frame as sf
from sources import text

ROOT = Path(__file__).resolve().parents[1]
SENSOR = json.loads((ROOT / "conformance" / "sensor_vectors.json").read_text(encoding="utf-8"))
CANBUS = "URTC/docs/CANBUS.TXT"


# ---- the sensor link against its vectors ----------------------------------------------------------------------------------
@pytest.mark.parametrize("v", SENSOR["frames"], ids=lambda v: v["name"])
def test_sensor_frames_encode_to_the_vector_bytes_and_parse_back(v):
    payload = bytes.fromhex(v["payload"])
    frame = sf.encode_frame(v["sensor_id"], v["seq"], v["timestamp_ms"], payload)
    assert frame.hex().upper() == v["frame"]
    assert sf.parse_frame(frame) == ("ok", {"sensor_id": v["sensor_id"], "seq": v["seq"], "timestamp_ms": v["timestamp_ms"], "payload": payload})


@pytest.mark.parametrize("v", SENSOR["parse"], ids=lambda v: v["name"])
def test_sensor_parse_statuses(v):
    assert sf.parse_frame(bytes.fromhex(v["hex"]))[0] == v["status"]


@pytest.mark.parametrize("v", SENSOR["thermal"], ids=lambda v: v["name"])
def test_sensor_thermal_readings(v):
    assert sf.validate_thermal(bytes.fromhex(v["payload"])) == (v["status"], v["centidegrees"])


def test_the_sensor_vectors_state_the_limits_the_module_uses():
    assert SENSOR["limits"] == {"version": sf.VERSION, "min_centidegrees_c": sf.MIN_TEMP_CENTIDEGREES_C, "max_centidegrees_c": sf.MAX_TEMP_CENTIDEGREES_C}


# ---- byte order, written down once ------------------------------------------------------------------------------------------
def test_the_timestamp_of_the_sensor_frame_is_big_endian():
    frame = sf.encode_frame(1, 0, 0x01020304)
    assert frame[4:8] == bytes([1, 2, 3, 4])


def test_a_thermal_reading_is_a_big_endian_signed_number():
    assert sf.encode_thermal_payload(2000) == bytes([0x07, 0xD0])
    assert sf.encode_thermal_payload(-1) == bytes([0xFF, 0xFF])
    assert sf.validate_thermal(bytes([0x07, 0xD0])) == ("ok", 2000)
    assert sf.validate_thermal(bytes([0xD0, 0x07]))[0] == "temp_out_of_range"  # the old order reads as 53255 / -12281


def test_the_temperature_of_the_rack_command_is_big_endian_on_both_links():
    assert rk.encode_set_preheat(1, 0, 200)[5:8] == bytes([0, 0, 200])
    assert rk.encode_set_preheat(1, 0, 350)[5:8] == bytes([0, 1, 94])
    assert rk.encode_set_preheat_can(1, 0, 350)[:3] == bytes([0, 1, 94])
    assert rk.validate_set_preheat(bytes([19, 1, 94])) == ("ok", 19, 350)


def test_a_frame_of_the_old_layout_is_refused_by_its_version():
    old = bytearray(rk.encode_set_preheat(1, 0, 200))
    old[1] = 1
    assert rk.parse_frame(bytes(old))[0] == "unsupported_version"
    old_sensor = bytearray(sf.encode_frame(1, 0, 5))
    old_sensor[1] = 1
    assert sf.parse_frame(bytes(old_sensor))[0] == "unsupported_version"


def test_both_links_are_at_version_two():
    assert (rk.VERSION, sf.VERSION) == (2, 2)


def test_the_crc_is_the_one_of_the_check_text():
    assert sf.crc8(b"123456789") == rk.crc8(b"123456789") == 0xF4


# ---- the prose ----------------------------------------------------------------------------------------------------------------------
def test_the_contracts_document_names_the_versions_of_the_companion_links():
    document = (ROOT / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    assert f"rack serial frame version {rk.VERSION}" in document
    assert f"sensor frame version {sf.VERSION}" in document


def test_the_bus_prose_names_the_versions_of_the_companion_links(sibling):
    prose = text(sibling(CANBUS))
    assert re.search(rf"rack serial\s+frame version {rk.VERSION}\b", prose), "CANBUS.TXT does not say which version of the rack serial frame is big-endian"
    assert re.search(rf"sensor frame version {sf.VERSION}\b", prose), "CANBUS.TXT does not say which version of the sensor frame is big-endian"
