# =============================================================================
# URTC-COMMON - tests/test_rack_chip_faults.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Faults and cuts in the whole chain of the rack: the serial link, the rack that holds the targets, the heater loop of the head and the thermal check.

Everything here runs on simulated time and simulated parts (``SimulatedRack``, ``SolderingIronModel``, ``verify_slot``): the evidence is the simulator,
never a board. The numbers of the heater are the estimates of ``heater_model.json``; what these tests hold is the BEHAVIOUR under a fault (the target is
given up, the verdict names the fault, a damaged frame never moves a target), not the true temperature of an iron.
"""
from __future__ import annotations

import pytest

from urtc_common import rack_sim as rk
from urtc_common.heater_sim import SolderingIronModel

IRON = 0   # tool id of the soldering iron in the rack tables


def _rack(**kw) -> rk.SimulatedRack:
    rack = rk.SimulatedRack(**kw)
    rack.set_slot(0, IRON)
    return rack


def _order(seq: int, target: int, tool: int = IRON) -> bytes:
    return rk.encode_set_preheat(seq, tool, target)


# ---- the serial link: bytes lost, noise, a cut in the middle of a frame ----------------------------------------------------------------
def test_a_frame_cut_in_half_is_dropped_by_the_silence_and_the_next_one_still_works():
    rack = _rack()
    frame = _order(1, 200)
    assert rack.receive_stream(frame[:4], now_ms=1000) == []          # the cable was pulled here
    assert rack.slots[0].target_c == 0
    replies = rack.receive_stream(_order(2, 210), now_ms=1000 + rk.DEFRAMER_TIMEOUT_MS + 5)
    assert [r.reason for r in replies] == ["applied"] and rack.slots[0].target_c == 210
    assert rack.deframer.stats.timeouts == 1 and rack.deframer.stats.dropped_bytes >= 4


def test_one_lost_byte_costs_one_frame_and_not_the_following_ones():
    rack = _rack(min_interval_ms=0)
    stream = bytearray(_order(1, 100) + _order(2, 150) + _order(3, 220))
    del stream[len(_order(1, 100)) + 3]                               # a byte of the second frame never arrived
    replies = rack.receive_stream(bytes(stream), now_ms=500)
    assert rack.slots[0].target_c == 220                              # the third arrived intact
    assert 150 not in [r.target_c for r in replies if r.target_c is not None]   # the damaged one never set anything
    assert rack.deframer.stats.frames_ok == 2


def test_a_flipped_bit_is_never_obeyed():
    rack = _rack(min_interval_ms=0)
    for bit in range(8 * len(_order(1, 300))):
        rack.deframer.reset()
        damaged = bytearray(_order(7, 300))
        damaged[bit // 8] ^= 1 << (bit % 8)
        rack.slots[0].target_c = 0
        rack.last_seq.clear()
        rack.receive_stream(bytes(damaged), now_ms=2000 + bit * 100)
        assert rack.slots[0].target_c in (0, 300)   # a CRC-8 catches every single-bit flip; a flip can never produce another target
        if rack.slots[0].target_c == 300:
            assert bytes(damaged) == _order(7, 300)  # only the untouched frame can set it


def test_noise_between_frames_is_skipped_and_counted():
    rack = _rack(min_interval_ms=0)
    stream = b"\x00\xff\x13" + _order(1, 180) + b"\xb7\x99" + _order(2, 190)
    replies = rack.receive_stream(stream, now_ms=100)
    assert [r.reason for r in replies] == ["applied", "applied"] and rack.slots[0].target_c == 190
    assert rack.deframer.stats.dropped_bytes >= 5


# ---- the link is lost: every target goes to the safe state, and coming back does not restore it ----------------------------------------
def test_a_link_cut_sends_the_target_to_zero_and_the_comeback_starts_from_nothing():
    rack = _rack()
    rack.receive(_order(1, 250), now_ms=0)
    assert rack.slots[0].target_c == 250
    assert rack.tick(rk.LINK_TIMEOUT_MS - 1) == 0 and rack.slots[0].target_c == 250   # still inside the window
    assert rack.tick(rk.LINK_TIMEOUT_MS) == 1 and rack.slots[0].target_c == 0
    assert "link lost" in rack.log[-1]
    rack.receive(_order(2, 0), now_ms=rk.LINK_TIMEOUT_MS + 50)       # the host comes back and says nothing about heating
    assert rack.slots[0].target_c == 0                               # nothing is restored on its own


def test_the_preheat_limit_gives_up_a_target_that_the_host_keeps_refreshing():
    rack = _rack(preheat_max_ms=1000, min_interval_ms=0)
    seq = 0
    for t in range(0, 1200, 100):
        seq += 1
        rack.receive(_order(seq, 250), now_ms=t)
        rack.tick(t)
    assert rack.slots[0].target_c == 0 and 0 in rack.expired
    reply = rack.receive(_order(seq + 1, 250), now_ms=1300)          # asking again does not heat again
    assert rack.slots[0].target_c == 0 and "pre-heat limit" in reply.detail
    rack.receive(_order(seq + 2, 0), now_ms=1400)                    # a zero releases it
    rack.receive(_order(seq + 3, 200), now_ms=1500)
    assert rack.slots[0].target_c == 200


def test_a_flood_of_commands_is_held_and_the_target_does_not_jump():
    rack = _rack()
    rack.receive(_order(1, 200), now_ms=1000)
    held = rack.receive(_order(2, 399), now_ms=1000 + rk.COMMAND_MIN_INTERVAL_MS - 1)
    assert held.reason == "held_rate" and rack.slots[0].target_c == 200


def test_an_order_for_a_tool_that_cannot_heat_or_is_out_of_range_zeroes_the_slot_it_names():
    rack = _rack()
    rack.receive(_order(1, 250), now_ms=0)
    reply = rack.receive(_order(2, rk.RACK_CEILING_C + 1), now_ms=100)
    assert reply.reason == "temp_out_of_range" and rack.slots[0].target_c == 0     # an order that cannot be believed leaves the safe state, not the old target


# ---- the chain: rack target -> heater loop -> thermal check, with a fault in the head ------------------------------------------------------
def _run_chain(model: SolderingIronModel, rack: rk.SimulatedRack, target: int, seconds: float, host_alive_until: float | None = None):
    """The host refreshes the order every 100 ms (until ``host_alive_until``); the head follows the target the rack holds. Returns the verdicts every 5 s."""
    verdicts = []
    seq = 0
    now_ms = 0
    steps = int(seconds * 10)
    for step in range(steps):
        alive = host_alive_until is None or step / 10 < host_alive_until
        if alive:
            seq += 1
            rack.receive(_order(seq, target), now_ms=now_ms)
        rack.tick(now_ms)
        held = rack.slots[0].target_c
        if held > 0:
            model.set_target(held)       # the head only gets its watchdog fed while the rack holds a target
        model.advance(0.1)
        now_ms += 100
        if step % 50 == 49:
            verdicts.append(rk.verify_slot(True, held, model.temperature_c, model.config["ambient_c"], now_ms))
    return verdicts


def test_a_healthy_chain_is_heating_and_then_reached():
    verdicts = _run_chain(SolderingIronModel(), _rack(), 250, 30.0)
    assert verdicts[0] == rk.SLOT_HEATING and verdicts[-1] == rk.SLOT_REACHED


def test_a_dead_heater_is_reported_as_not_reached_after_the_time_limit():
    model = SolderingIronModel({"heater_power_w": 0.0})               # the element is open: it never warms
    verdicts = _run_chain(model, _rack(), 250, 70.0)
    assert verdicts[0] == rk.SLOT_HEATING and verdicts[-1] == rk.SLOT_NOT_REACHED


def test_a_heater_stuck_on_is_reported_as_overshoot():
    class StuckOn(SolderingIronModel):
        def _step(self, dt: float) -> None:
            super()._step(dt)
            cfg = self.config   # a switch welded shut: half of the full power reaches the element whatever the loop decides
            self.temperature_c += 0.5 * cfg["heater_power_w"] / cfg["heat_capacity_j_per_k"] * dt

    model = StuckOn()
    verdicts = _run_chain(model, _rack(), 200, 60.0)
    assert verdicts[-1] == rk.SLOT_OVERSHOOT


def test_a_cut_of_the_host_cools_the_head_by_itself_and_the_thermal_check_ends_idle():
    model = SolderingIronModel()
    rack = _rack()
    verdicts = _run_chain(model, rack, 300, 120.0, host_alive_until=30.0)    # the link dies at 30 s
    assert rack.slots[0].target_c == 0 and model.setpoint_c == 0
    assert verdicts[-1] == rk.SLOT_IDLE_OK                                    # cooled below the "still hot" mark, no hand on anything


def test_an_empty_slot_that_is_hot_is_a_heater_where_there_should_be_none():
    assert rk.verify_slot(False, 0, 25.0 + rk.VERIFY_EMPTY_HOT_C + 1, 25.0, 0) == rk.SLOT_EMPTY_HOT
    assert rk.verify_slot(True, 0, 25.0 + rk.VERIFY_IDLE_HOT_C + 1, 25.0, 0) == rk.SLOT_IDLE_HOT
    assert rk.verify_slot(True, 250, float("nan"), 25.0, 10_000) == rk.SLOT_UNKNOWN     # a pixel without a number says nothing


# ---- physics sanity of the plant (so a change of the parameters cannot make the simulator silently absurd) ----------------------------------------
@pytest.mark.parametrize("target", [150, 250, 350])
def test_the_steady_duty_matches_the_heat_the_iron_loses(target):
    model = SolderingIronModel()
    for _ in range(600):
        model.set_target(target)
        model.advance(0.1)
    cfg = model.config
    expected = cfg["loss_w_per_k"] * (target - cfg["ambient_c"]) / cfg["heater_power_w"]
    assert abs(model.duty - expected) < 0.05 and abs(model.temperature_c - target) < 2.0


def test_a_lower_setpoint_never_drives_the_heater_and_the_iron_does_not_undershoot_much():
    model = SolderingIronModel()
    for _ in range(300):
        model.set_target(350)
        model.advance(0.1)
    low = []
    for _ in range(600):
        model.set_target(200)
        model.advance(0.1)
        low.append(model.temperature_c)
    assert min(low) > 200 - 15 and abs(low[-1] - 200) < 3
    assert model.duty >= 0.0


def test_a_warmer_room_still_reaches_the_target_with_less_effort():
    cold, warm = SolderingIronModel({"ambient_c": 10.0}), SolderingIronModel({"ambient_c": 35.0})
    for model in (cold, warm):
        for _ in range(600):
            model.set_target(300)
            model.advance(0.1)
    assert abs(cold.temperature_c - 300) < 2 and abs(warm.temperature_c - 300) < 2
    assert warm.duty < cold.duty
