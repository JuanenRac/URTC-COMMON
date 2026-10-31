# =============================================================================
# URTC-COMMON - tests/test_rack_frames.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The two CAN frames of the tool rack (0x260 the order, 0x261 the reply) in the specification, in the generated modules and in the simulator.

The rack frames are a section of their own in the specification, apart from the messages of the tool head, so these tests make sure that no
identifier of any group is also an identifier of another (the pairs are all checked, and an identifier that is added later is checked too),
that the reply is the same three bytes as the serial reply of the rack, and that the simulator, the generated code and the vectors agree.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from urtc_common import bus_scenario as bs
from urtc_common import protocol as pr
from urtc_common import rack_sim as rk

ROOT = Path(__file__).resolve().parents[1]
RACK_VECTORS = json.loads((ROOT / "conformance" / "rack_vectors.json").read_text(encoding="utf-8"))


def groups(spec: dict) -> dict[str, set[int]]:
    """Every group of identifiers the specification defines, as sets of numbers (a multinode range expanded to its identifiers)."""
    out: dict[str, set[int]] = {"messages": {int(m["id"], 16) for m in spec["messages"]}, "rack": {int(f["id"], 16) for f in spec["rack"]["frames"]}}
    for frame in spec["multinode"]["frames"]:
        base = int(frame["id"], 16)
        out["multinode " + frame["name"]] = set(range(base, base + frame["span"]))
    return out


def test_the_rack_section_is_valid_and_sits_in_the_reserved_block(spec):
    rack = spec["rack"]
    first, last = int(rack["range"]["first"], 16), int(rack["range"]["last"], 16)
    assert (first, last) == (0x260, 0x26F)
    ids = [int(f["id"], 16) for f in rack["frames"]]
    assert ids == [0x260, 0x261] and all(first <= i <= last for i in ids)
    names = [f["name"] for f in rack["frames"]]
    assert names == ["SET_PREHEAT", "REPLY"] and len(set(names)) == len(names)
    assert [f["direction"] for f in rack["frames"]] == ["host_to_rack", "rack_to_host"]


def test_no_identifier_belongs_to_two_groups_all_pairs(spec):
    table = groups(spec)
    assert len(table) == 2 + len(spec["multinode"]["frames"])
    for (name_a, a), (name_b, b) in itertools.combinations(table.items(), 2):
        assert a.isdisjoint(b), (name_a, name_b, sorted(a & b))
    # no identifier of a tool head message is inside the block reserved for the rack, and the multinode range stays above it
    first, last = int(spec["rack"]["range"]["first"], 16), int(spec["rack"]["range"]["last"], 16)
    assert not any(first <= i <= last for i in table["messages"])
    assert max(table["rack"]) <= last < min(min(ids) for name, ids in table.items() if name.startswith("multinode"))
    # the magic payloads and the registers that travel on CAN name identifiers that exist as messages, never one of the rack
    for magic in spec["magic_payloads"]:
        for can_id in [magic["id"], *magic.get("also_on", [])]:
            assert int(can_id, 16) in table["messages"] and int(can_id, 16) not in table["rack"]
    assert {0x1A2, 0x1A3} <= table["messages"] and not {0x1A2, 0x1A3} & table["rack"]       # the free-tool pair
    assert {0x7E9, 0x7F0, 0x7F8, 0x7FD} <= table["messages"] and not table["rack"] & set(range(0x7E0, 0x800))   # the bootloader


def test_the_reply_identifier_is_the_neighbour_of_the_order_and_free_in_every_group(spec):
    table = groups(spec)
    assert 0x261 == 0x260 + 1 == pr.RACK_ID_REPLY == rk.CAN_ID_REPLY == bs.CAN_ID_REPLY
    assert 0x261 not in table["messages"] and all(0x261 not in ids for name, ids in table.items() if name != "rack")
    assert 0x262 not in set().union(*table.values())           # the next one stays free for whatever the rack may need later


def test_a_collision_would_be_seen(spec):
    broken = json.loads(json.dumps(spec))
    broken["rack"]["frames"][1]["id"] = "0x255"                  # an identifier of the thermal group
    table = groups(broken)
    assert not table["messages"].isdisjoint(table["rack"])


def test_the_generated_python_matches_the_specification(spec):
    rack = spec["rack"]
    assert pr.RACK_ID_SET_PREHEAT == 0x260 and pr.RACK_ID_REPLY == 0x261 and (pr.RACK_ID_FIRST, pr.RACK_ID_LAST) == (0x260, 0x26F)
    assert pr.RACK_REPLY_LENGTH == 3 and pr.RACK_TOOL_NONE == 0xFF and pr.RACK_CMD_SET_PREHEAT == 1
    assert pr.RACK_REPLY_REASONS == {r["value"]: r["name"].lower() for r in rack["reply_reasons"]}
    assert pr.RACK_REPLY_ACKNOWLEDGEMENTS == (0, 1)
    assert pr.RACK_NAMES == {0x260: "SET_PREHEAT", 0x261: "REPLY"}
    assert pr.RACK_DIRECTIONS == {0x260: "host_to_rack", 0x261: "rack_to_host"}
    assert [r["value"] for r in rack["reply_reasons"]] == list(range(len(rack["reply_reasons"])))


def test_the_reasons_are_the_reasons_of_the_simulator_and_of_the_scenarios(spec):
    names = tuple(r["name"].lower() for r in spec["rack"]["reply_reasons"])
    assert names == rk.REPLY_CODES == bs.REPLY_CODES
    assert tuple(r["name"].lower() for r in spec["rack"]["reply_reasons"] if r["kind"] == "acknowledgement") == rk.REPLY_ACKNOWLEDGEMENTS
    assert rk.REPLY_PAYLOAD_LEN == pr.RACK_REPLY_LENGTH and rk.REPLY_TOOL_NONE == pr.RACK_TOOL_NONE and rk.CMD_SET_PREHEAT == pr.RACK_CMD_SET_PREHEAT


def test_the_examples_of_the_specification_are_what_the_simulator_builds(spec):
    order = spec["rack"]["frames"][0]["layout"]["examples"][0]
    assert rk.encode_set_preheat_can(order["fields"]["sequence"], order["fields"]["tool"], order["fields"]["target_c"]).hex().upper() == order["data"]
    assert pr.encode_rack_set_preheat(**order["fields"]) == (0x260, bytes.fromhex(order["data"]))
    for example in spec["rack"]["frames"][1]["layout"]["examples"]:
        fields = example["fields"]
        assert pr.encode_rack_reply(**fields) == (0x261, bytes.fromhex(example["data"]))
        assert pr.decode_rack_reply(bytes.fromhex(example["data"]), strict=True) == fields
        reason = rk.REPLY_CODES[fields["reason"]]
        assert rk.encode_reply_can(fields["command"], fields["tool"], reason).hex().upper() == example["data"]


@pytest.mark.parametrize("code", range(len(rk.REPLY_CODES)))
def test_the_can_reply_is_the_payload_of_the_serial_reply(code):
    reason = rk.REPLY_CODES[code]
    data = rk.encode_reply_can(rk.CMD_SET_PREHEAT, 3, reason)
    serial = rk.parse_reply(rk.encode_reply(9, rk.CMD_SET_PREHEAT, 3, reason))
    parsed = rk.parse_reply_can(rk.CAN_ID_REPLY, data)
    assert parsed is not None and serial is not None
    assert {k: parsed[k] for k in ("ack", "cmd", "tool", "code", "reason")} == {k: serial[k] for k in ("ack", "cmd", "tool", "code", "reason")}
    assert data == bytes([rk.CMD_SET_PREHEAT, 3, code]) and parsed["ack"] == (code < 2)


@pytest.mark.parametrize("can_id,data", [
    (0x261, b""), (0x261, b"\x01\x00"), (0x261, b"\x01\x00\x00\x00"), (0x261, b"\x01\x00\x09"), (0x261, b"\x01\x00\xFF"),
    (0x260, b"\x01\x00\x00"), (0x262, b"\x01\x00\x00"), (0x1A3, b"\x01\x00\x00"), (0x400, b"\x01\x00\x00"),
])
def test_what_is_not_a_reply_is_refused(can_id, data):
    assert rk.parse_reply_can(can_id, data) is None
    if can_id == 0x261 and len(data) != 3:
        assert pr.decode_rack_reply(data, strict=True) is None     # the generated parser also refuses a length that is not three


def test_the_rack_answers_a_can_order_with_a_can_reply():
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0)
    applied = rack.receive_can(rk.CAN_ID_SET_PREHEAT, rk.encode_set_preheat_can(1, 0, 200), 0)
    assert applied.reason == "applied" and applied.can_frame == (0x261, bytes([1, 0, 0])) and applied.frame == b""
    again = rack.receive_can(rk.CAN_ID_SET_PREHEAT, rk.encode_set_preheat_can(1, 0, 200), 30)
    assert again.can_frame == (0x261, bytes([1, 0, 1]))
    too_hot = rack.receive_can(rk.CAN_ID_SET_PREHEAT, rk.encode_set_preheat_can(2, 0, 900), 100)
    assert too_hot.can_frame == (0x261, bytes([1, 0, rk.REPLY_CODES.index("temp_out_of_range")]))
    nobody = rack.receive_can(rk.CAN_ID_SET_PREHEAT, bytes(7), 200)
    assert nobody.can_frame is None and nobody.reason == ""
    serial = rack.receive(rk.encode_set_preheat(5, 0, 210), 400)
    assert serial.can_frame is None and serial.frame != b""          # a serial order is answered on the serial link only


def test_the_vectors_of_the_can_reply_are_what_the_simulator_builds():
    replies = RACK_VECTORS["can_replies"]
    assert [r["code"] for r in replies] == list(range(len(rk.REPLY_CODES))) and {r["id"] for r in replies} == {0x261}
    for r in replies:
        reason = rk.REPLY_CODES[r["code"]]
        assert rk.encode_reply_can(r["cmd"], r["tool"], reason).hex().upper() == r["data"]
        assert pr.encode_rack_reply(r["cmd"], r["tool"], r["code"]) == (0x261, bytes.fromhex(r["data"]))
        parsed = rk.parse_reply_can(r["id"], bytes.fromhex(r["data"]))
        assert parsed is not None and parsed["ack"] is r["ack"] and parsed["reason"] == reason
    assert len(RACK_VECTORS["can_replies_rejected"]) >= 5
    for r in RACK_VECTORS["can_replies_rejected"]:
        assert rk.parse_reply_can(r["id"], bytes.fromhex(r["data"])) is None, r["name"]
