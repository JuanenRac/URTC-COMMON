"""Free configuration of a head (ID jumpers 0x1F): the model of the rack against the shared vectors, and the rules of the contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from urtc_common import rack_sim as rk

ROOT = Path(__file__).resolve().parents[1]
FREE = json.loads((ROOT / "conformance" / "rack_vectors.json").read_text(encoding="utf-8"))["free_tool"]


@pytest.mark.parametrize("v", FREE["jumpers"], ids=lambda v: f"jumpers {v['raw']:#04x}")
def test_jumper_readings_are_classified_like_the_vectors(v):
    assert rk.classify_jumper(v["raw"]) == (v["kind"], v["tool"])


def test_only_a_reading_of_31_asks_the_head():
    kinds = [rk.classify_jumper(raw)[0] for raw in range(32)]
    assert kinds[:25] == ["direct"] * 25
    assert kinds[25:31] == ["invalid"] * 6
    assert kinds[31] == "free"


@pytest.mark.parametrize("v", FREE["replies"], ids=lambda v: v["name"])
def test_replies_name_a_tool_like_the_vectors(v):
    assert rk.parse_free_tool_reply(bytes.fromhex(v["payload"])) == v["tool"]


def test_the_defaults_are_the_ones_of_the_vectors():
    assert rk.FreeToolConfig().__dict__ == FREE["defaults"]


@pytest.mark.parametrize("sc", FREE["scenarios"], ids=lambda s: s["name"])
def test_scenarios_play_like_the_vectors(sc):
    res = rk.FreeToolResolver(rk.FreeToolConfig(**sc["config"]))
    for step in sc["steps"]:
        reply = None if step["reply"] is None else bytes.fromhex(step["reply"])
        query, event = res.step(step["time_ms"], reply)
        assert (query, event, -1 if res.tool is None else res.tool) == (step["query"], step["event"], step["tool"]), step


def test_a_head_in_free_mode_has_no_identity_and_no_target_until_it_answers():
    rack = rk.SimulatedRack()
    assert rack.set_slot_jumpers(0, 0x1F) == "free"
    assert rack.slot_identity(0) == "pending" and not rack.slots[0].occupied
    reply = rack.receive(rk.encode_set_preheat(1, 0, 250), 0)
    assert reply.action == "none" and "not racked" in reply.detail and rack.slots[0].target_c == 0  # nothing is applied to a head without identity
    query, event = rack.free_tool_step(0, 0)
    assert query and event == "none"
    query, event = rack.free_tool_step(0, 100, bytes([0x1F, 0x01]))
    assert event == "resolved" and rack.slot_identity(0) == "tool" and rack.slots[0].tool_id == 0
    rack.receive(rk.encode_set_preheat(2, 0, 250), 200)
    assert rack.slots[0].target_c == 250


def test_a_change_of_tool_drops_the_target_and_a_lost_answer_empties_the_slot():
    rack = rk.SimulatedRack()
    rack.set_slot_jumpers(1, 0xFF)
    rack.free_tool_step(1, 0)
    rack.free_tool_step(1, 10, bytes([0x1F, 0x01]))
    rack.receive(rk.encode_set_preheat(1, 0, 250), 20)
    assert rack.slots[1].target_c == 250
    rack.free_tool_step(1, 5010)
    _, event = rack.free_tool_step(1, 5020, bytes([0x1F, 0x0B]))
    assert event == "changed" and rack.slots[1].tool_id == 10 and rack.slots[1].target_c == 0
    _, event = rack.free_tool_step(1, 5030, bytes([0x1F, 0x00]))
    assert event == "lost" and rack.slot_identity(1) == "pending"


def test_direct_and_invalid_jumpers_never_ask():
    rack = rk.SimulatedRack()
    assert rack.set_slot_jumpers(2, 0x0A) == "direct" and rack.slots[2].tool_id == 10
    assert rack.free_tool_step(2, 0) == (False, "none")
    assert rack.set_slot_jumpers(3, 0x1E) == "invalid" and rack.slot_identity(3) == "invalid"
    assert rack.free_tool_step(3, 0) == (False, "none")
    rack.set_slot_jumpers(4, 0x1F)
    rack.set_slot_jumpers(4, 0x05)
    assert rack.slot_identity(4) == "tool" and rack.free_tool_step(4, 0) == (False, "none")
