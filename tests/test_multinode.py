# =============================================================================
# URTC-COMMON - tests/test_multinode.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The multinode extension: identifiers that clash with nothing, frames that reproduce the vectors, helpers and bus load."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from urtc_common import multinode as mn
from urtc_common import protocol as p

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "conformance" / "multinode_vectors.json"


@pytest.fixture(scope="module")
def mv():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def test_the_extension_is_marked_as_a_design(spec):
    assert spec["multinode"]["status"] == "designed_not_implemented_in_firmware"
    assert all("implemented_by" not in f for f in spec["multinode"]["frames"])


def test_no_identifier_of_the_extension_clashes_with_the_single_head_protocol(spec):
    used = {int(m["id"], 16) for m in spec["messages"]}
    seen = set()
    for frame in spec["multinode"]["frames"]:
        base = int(frame["id"], 16)
        block = set(range(base, base + frame["span"]))
        assert not block & used, frame["name"]
        assert not block & seen, frame["name"]
        assert block <= set(range(0x400, 0x4A0))
        seen |= block
    # The extension must also stay below the bootloader identifiers and above every application identifier.
    assert max(seen) < min(i for i in used if i >= 0x7E9) and min(seen) > max(i for i in used if i < 0x400)


def test_a_ranged_frame_covers_exactly_the_node_addresses(spec):
    for frame in spec["multinode"]["frames"]:
        assert frame["span"] in (1, p.MN_NODE_MAX)
    assert p.MN_NODE_MAX == 1 << p.MN_ADDRESS_BITS and p.MN_ADDRESS_MASK == p.MN_NODE_MAX - 1


def test_vectors_are_current():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_multinode_vectors.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _encoder(name):
    return getattr(p, f"encode_mn_{name.lower()}")


def _decoder(name):
    return getattr(p, f"decode_mn_{name.lower()}")


def _values(entry):
    fields = dict(entry["fields"])
    for key, value in fields.items():
        if isinstance(value, str):
            fields[key] = bytes.fromhex(value)
    return fields


def test_encoders_reproduce_every_vector(mv):
    assert len(mv["encode"]) >= 16
    for entry in mv["encode"]:
        args = ([entry["node"]] if "node" in entry else [])
        can_id, data = _encoder(entry["frame"])(*args, **_values(entry))
        assert (f"0x{can_id:03X}", data.hex().upper()) == (entry["id"], entry["data"]), entry["name"]


def test_decoders_reproduce_every_vector(mv):
    for entry in mv["decode"]:
        got = _decoder(entry["frame"])(bytes.fromhex(entry["data"]))
        expected = {k: (v.upper() if isinstance(v, str) else v) for k, v in entry["fields"].items()}
        got = {k: (v.hex().upper() if isinstance(v, (bytes, bytearray)) else v) for k, v in got.items()}
        assert got == expected, entry["name"]


def test_a_node_outside_the_address_space_is_refused(mv):
    assert mv["rejected"]
    for entry in mv["rejected"]:
        encoder = _encoder(entry["frame"])
        with pytest.raises(ValueError):
            if entry["frame"] == "NODE_INFO":
                encoder(entry["node"], tool=0, state=0, instance=0, mn_version=1, serial=1)
            elif entry["frame"] == "NODE_STATUS":
                encoder(entry["node"], state=0, error=0, uptime_s=0)
            else:
                encoder(entry["node"], func=0x100, **{("args" if entry["frame"] == "NODE_CMD" else "data"): b""})


def test_values_out_of_range_are_refused():
    with pytest.raises(ValueError):
        p.encode_mn_select(action=2, node=0, seq=0)
    with pytest.raises(ValueError):
        p.encode_mn_select(action=1, node=32, seq=0)
    with pytest.raises(ValueError):
        p.encode_mn_discover(mn_version=1, slot_ms=0)


def test_a_too_short_payload_is_reported_not_guessed():
    assert p.decode_mn_node_info(b"\x00\x00") is None
    assert p.decode_mn_node_cmd(b"\x01") is None


def test_split_and_build_identifiers_agree():
    for node in range(p.MN_NODE_MAX):
        can_id = p.mn_node_id(p.MN_ID_NODE_STATUS_BASE, node)
        assert p.mn_split_id(can_id) == ("NODE_STATUS", node)
    assert p.mn_split_id(p.MN_ID_DISCOVER) == ("DISCOVER", None)
    assert p.mn_split_id(p.CAN_ID_GLOBAL_STATUS) is None
    assert p.mn_split_id(0x4A0) is None and p.mn_split_id(0x403) is None
    with pytest.raises(ValueError):
        p.mn_node_id(p.MN_ID_DISCOVER, 1)
    with pytest.raises(ValueError):
        p.mn_node_id(p.MN_ID_NODE_INFO_BASE, 32)
    with pytest.raises(ValueError):
        p.mn_node_id(p.MN_ID_NODE_INFO_BASE, True)


def test_lower_node_address_wins_arbitration():
    assert p.mn_node_id(p.MN_ID_NODE_INFO_BASE, 3) < p.mn_node_id(p.MN_ID_NODE_INFO_BASE, 4)
    assert p.MN_ID_SAFE_STOP < p.MN_ID_NODE_INFO_BASE < p.MN_ID_NODE_STATUS_BASE < p.MN_ID_NODE_CMD_BASE < p.MN_ID_NODE_RESP_BASE


def test_address_from_jumpers():
    assert mn.address_from_jumpers([0, 0, 0, 0, 0]) == 0
    assert mn.address_from_jumpers([1, 0, 0, 0, 0]) == 1
    assert mn.address_from_jumpers([1, 1, 1, 1, 1]) == 31
    assert mn.address_from_jumpers([0, 0, 0, 0, 1]) == 16
    with pytest.raises(ValueError):
        mn.address_from_jumpers([1, 1, 1, 1])


def test_frame_bits_match_the_known_lengths_of_a_classic_frame():
    assert mn.frame_bits(0) == 47 and mn.frame_bits(8) == 111
    assert mn.frame_bits(8, worst_case=True) == 111 + (34 + 64 - 1) // 4
    with pytest.raises(ValueError):
        mn.frame_bits(9)


def test_bus_load_of_a_full_bus_of_status_frames():
    worst = mn.bus_load(mn.status_traffic(32), 500000, worst_case=True)
    assert 0.005 < worst < 0.007
    assert mn.bus_load(mn.status_traffic(32), 10000, worst_case=True) > 0.25
    assert mn.bus_load([], 500000) == 0.0
    with pytest.raises(ValueError):
        mn.status_traffic(33)


def test_discovery_answers_are_spread_out():
    assert mn.discover_answer_delay_ms(0) == 0 and mn.discover_answer_delay_ms(31) == 62
    assert mn.discover_window_ms() > 62
    assert mn.discover_window_ms(bitrate=10000) > mn.discover_window_ms(bitrate=500000)
    # at 10 kbit/s 32 frames of 135 bits queue for 432 ms, far longer than the slots
    assert mn.discover_window_ms(bitrate=10000) > 432
    assert mn.discover_window_ms(bitrate=500000) < 70


def _info(serial=1, state=0):
    return {"tool": 0, "state": state, "instance": 0, "serial": serial}


def test_node_table_tracks_liveness_and_selection():
    table = mn.NodeTable()
    table.on_info(4, _info(state=p.MN_STATE_SELECTED), 0)
    table.on_info(5, _info(serial=2), 0)
    assert table.alive(1000) == [4, 5] and table.selected(1000) == 4
    table.on_status(5, {"state": 0, "error": 0, "uptime_s": 9}, 3000)
    assert table.gone(5000) == [4] and table.alive(5000) == [5]
    assert table.selected(5000) is None
    assert table.on_status(9, {"state": 0, "error": 0, "uptime_s": 0}, 0) is None


def test_two_boards_on_one_address_are_a_conflict_and_not_commanded():
    table = mn.NodeTable()
    table.on_info(7, _info(serial=1), 0)
    assert table.may_command(7, 10)
    table.on_info(7, _info(serial=2), 5)
    assert table.nodes[7].conflict and not table.may_command(7, 10)


def test_a_faulted_or_bootloader_node_is_not_commanded():
    table = mn.NodeTable()
    table.on_info(1, _info(state=p.MN_STATE_FAULT), 0)
    table.on_info(2, _info(serial=2, state=p.MN_STATE_BOOTLOADER), 0)
    table.on_info(3, _info(serial=3), 0)
    assert [table.may_command(n, 1) for n in (1, 2, 3, 4)] == [False, False, True, False]
    assert not table.may_command(3, p.MN_NODE_TIMEOUT_MS + 1)


def test_two_selected_nodes_are_reported_as_no_selection():
    table = mn.NodeTable()
    table.on_info(1, _info(state=p.MN_STATE_SELECTED), 0)
    table.on_info(2, _info(serial=2, state=p.MN_STATE_SELECTED), 0)
    assert table.selected(1) is None
