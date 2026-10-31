# =============================================================================
# URTC-COMMON - tests/test_sim_characterization.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""What the simulators do today, written down before the bus scenarios were added.

These tests fix the behaviour of the rack model and of the in-memory bootloader exactly as it was, so a change to the simulated bus can be told apart
from a change to the simulators themselves: the scenarios are an option placed around them and none of these results may move.
"""
from __future__ import annotations

from urtc_common import protocol
from urtc_common import rack_sim as rk
from urtc_common.transports import MockCAN


def _reasons(rack: rk.SimulatedRack, steps: list[tuple[int, int, int, int]]) -> list[str]:
    """Send (gap_ms, seq, tool, target) orders in serial form; the reason of each reply."""
    now, out = 0, []
    for gap, seq, tool, target in steps:
        now += gap
        out.append(rack.receive(rk.encode_set_preheat(seq, tool, target), now).reason)
    return out


def test_the_rack_answers_a_fixed_sequence_the_same_way():
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0, 7)
    steps = [(20, 1, 0, 300), (0, 1, 0, 300), (5, 2, 0, 310), (20, 3, 0, 500), (20, 4, 3, 100), (20, 5, 31, 0), (20, 6, 0, 0)]
    assert _reasons(rack, steps) == ["applied", "repeat", "held_rate", "temp_out_of_range", "not_heatable", "tool_absent", "applied"]


def test_the_rack_in_can_form_sets_a_target_and_gives_no_frame():
    rack = rk.SimulatedRack()
    rack.set_slot(1, 10, 3)
    reply = rack.receive_can(rk.CAN_ID_SET_PREHEAT, rk.encode_set_preheat_can(1, 10, 250), 100)
    assert (reply.kind, reply.action, reply.reason, reply.frame) == ("ack", "set_target", "applied", b"")
    assert rack.slots[1].target_c == 250


def test_a_lost_link_sends_every_target_to_the_safe_state():
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0)
    rack.receive(rk.encode_set_preheat(1, 0, 200), 0)
    assert rack.slots[0].target_c == 200
    assert rack.tick(rk.LINK_TIMEOUT_MS) == 1 and rack.slots[0].target_c == 0


def test_the_free_head_waits_for_a_valid_answer():
    assert rk.classify_jumper(0x1F) == ("free", None)
    assert rk.parse_free_tool_reply(bytes([0x1F, 6])) == 5
    for bad in (bytes([0x1F, 0]), bytes([0x1F, 26]), bytes([0x1F]), bytes([0x05, 6])):
        assert rk.parse_free_tool_reply(bad) is None


def test_the_in_memory_bootloader_answers_the_version_query_in_a_fixed_order():
    board = MockCAN(delay=0, installed_version=(0, 2), installed_patch=3)
    board.send_frame(protocol.CAN_ID_QUERY_VERSION, b"")
    got = []
    while (frame := board.read_frame()) is not None:
        got.append(frame[0])
    assert got == [protocol.CAN_ID_VERSION_RESPONSE, protocol.CAN_ID_BOOTLOADER_VERSION_RESPONSE, protocol.CAN_ID_VERSION_PATCH_RESPONSE]


def test_the_in_memory_bootloader_acknowledges_pages_of_an_update():
    board = MockCAN(delay=0)
    board.send_frame(protocol.CAN_ID_START_UPDATE, (4096).to_bytes(4, "big") + bytes(4))
    assert [board.read_frame() for _ in range(2)] == [(protocol.CAN_ID_STATUS, bytes([protocol.STATUS_ERASING])),
                                                      (protocol.CAN_ID_STATUS, bytes([protocol.STATUS_RECEIVING]))]
    assert board.read_frame() is None
