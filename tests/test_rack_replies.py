# =============================================================================
# URTC-COMMON - tests/test_rack_replies.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The answer of the rack to a command: an acknowledgement or a refusal with its reason.

The firmware writes the frame (rack_reply.c of URTC-SMART-RACK) and the programs read it; the model in ``rack_sim`` does both, and the
vectors in ``conformance/rack_vectors.json`` hold the reply of every step of the link scenarios, which the firmware reproduces byte for byte.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from urtc_common import rack_sim as rk

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "conformance" / "rack_vectors.json").read_text(encoding="utf-8"))


def test_an_acknowledgement_and_a_refusal_round_trip():
    for reason in rk.REPLY_CODES:
        frame = rk.encode_reply(9, rk.CMD_SET_PREHEAT, 3, reason)
        reply = rk.parse_reply(frame)
        assert reply is not None
        assert reply["reason"] == reason and reply["seq"] == 9 and reply["cmd"] == rk.CMD_SET_PREHEAT and reply["tool"] == 3
        assert reply["ack"] == (reason in ("applied", "repeat"))
        assert frame[3] == (rk.CMD_ACK if reply["ack"] else rk.CMD_NACK)


def test_a_reply_that_is_not_well_formed_is_refused():
    good = rk.encode_reply(1, 1, 0, "applied")
    assert rk.parse_reply(good[:-1]) is None                                            # cut
    assert rk.parse_reply(rk.encode_frame(1, rk.CMD_ACK, bytes([1, 0]))) is None        # two bytes of payload
    assert rk.parse_reply(rk.encode_frame(1, rk.CMD_ACK, bytes([1, 0, 4]))) is None     # an acknowledgement that carries a refusal code
    assert rk.parse_reply(rk.encode_frame(1, rk.CMD_NACK, bytes([1, 0, 0]))) is None    # a refusal that carries an acknowledgement code
    assert rk.parse_reply(rk.encode_frame(1, rk.CMD_NACK, bytes([1, 0, len(rk.REPLY_CODES)]))) is None  # a code that does not exist
    assert rk.parse_reply(rk.encode_frame(1, rk.CMD_SET_PREHEAT, bytes([1, 0, 0]))) is None  # not a reply at all
    assert rk.parse_reply(b"") is None


@pytest.mark.parametrize("payload,reason", [
    (bytes([0, 0, 200]), "applied"), (bytes([0, 1, 145]), "temp_out_of_range"), (bytes([6, 0, 100]), "not_heatable"),
    (bytes([31, 0, 0]), "tool_absent"), (bytes([27, 0, 0]), "tool_invalid"), (bytes([0, 1]), "wrong_length"),
])
def test_the_simulated_rack_tells_why(payload, reason):
    rack = rk.SimulatedRack()
    reply = rack.receive(rk.encode_frame(5, rk.CMD_SET_PREHEAT, payload), 0)
    assert reply.reason == reason
    parsed = rk.parse_reply(reply.frame)
    assert parsed is not None and parsed["reason"] == reason and parsed["seq"] == 5 and parsed["tool"] == payload[0]


def test_a_repeat_a_flood_and_an_unknown_command():
    rack = rk.SimulatedRack()
    assert rack.receive(rk.encode_set_preheat(1, 0, 200), 0).reason == "applied"
    assert rack.receive(rk.encode_set_preheat(1, 0, 200), 30).reason == "repeat"           # the same sequence again
    held = rack.receive(rk.encode_set_preheat(2, 0, 220), 10)                              # sooner than the interval after the one applied
    assert held.reason == "held_rate" and held.kind == "nack" and rk.parse_reply(held.frame)["ack"] is False
    assert rack.receive(rk.encode_set_preheat(2, 0, 220), 20).reason == "applied"          # the interval has passed: the same sequence is new
    unknown = rack.receive(rk.encode_frame(3, 0x40, bytes([1])), 40)
    assert unknown.reason == "unknown_command" and rk.parse_reply(unknown.frame)["tool"] == rk.REPLY_TOOL_NONE
    empty = rack.receive(rk.encode_frame(4, rk.CMD_SET_PREHEAT, b""), 50)
    assert empty.reason == "wrong_length" and rk.parse_reply(empty.frame)["tool"] == rk.REPLY_TOOL_NONE


def test_noise_and_can_commands_get_no_serial_reply():
    rack = rk.SimulatedRack()
    assert rack.receive(b"\xA5\x01\x02", 0).frame == b""
    can = rack.receive_can(rk.CAN_ID_SET_PREHEAT, rk.encode_set_preheat_can(1, 0, 200), 10)
    assert can.reason == "applied" and can.frame == b""      # a CAN command is answered on the bus by its own frame, not by a serial one


def test_the_simulated_rack_gives_the_replies_of_the_shared_scenarios():
    for scenario in VECTORS["scenarios"]:
        rack = rk.SimulatedRack()
        for step in scenario["steps"]:
            reply = rack.receive(bytes.fromhex(step["frame"]), step["time_ms"])
            assert reply.frame.hex().upper() == step["reply"], (scenario["name"], step["time_ms"])


def test_every_reason_is_in_the_shared_vectors():
    seen = {rk.parse_reply(bytes.fromhex(step["reply"]))["reason"] for scenario in VECTORS["scenarios"] for step in scenario["steps"] if step["reply"]}
    assert seen == set(rk.REPLY_CODES)


def test_the_interval_between_commands_can_be_changed_or_switched_off():
    rack = rk.SimulatedRack(min_interval_ms=0)
    assert rack.receive(rk.encode_set_preheat(1, 0, 200), 0).reason == "applied"
    assert rack.receive(rk.encode_set_preheat(2, 0, 210), 1).reason == "applied"        # no limit: nothing is held
    slow = rk.SimulatedRack(min_interval_ms=500)
    assert slow.receive(rk.encode_set_preheat(1, 0, 200), 0).reason == "applied"
    assert slow.receive(rk.encode_set_preheat(2, 0, 210), 200).reason == "held_rate"    # each held frame keeps the link alive (the watchdog is 250 ms)
    assert slow.receive(rk.encode_set_preheat(2, 0, 210), 400).reason == "held_rate"
    assert slow.receive(rk.encode_set_preheat(2, 0, 210), 500).reason == "applied"
