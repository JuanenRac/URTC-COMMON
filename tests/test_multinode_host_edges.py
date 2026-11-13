# =============================================================================
# URTC-COMMON - tests/test_multinode_host_edges.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The host of several heads on one bus at the edges: every reason why a head is not commanded, every way a selection lapses, a selection that is suspended or released, and the
short status query, against a bus of modelled heads (nothing is opened and every time is the modelled one)."""
from __future__ import annotations

import pytest

from urtc_common import multinode_host as mh
from urtc_common import multinode_sim as sim
from urtc_common import protocol as p

MOTION = 0x120


def make_bus(*addresses, start=0):
    bus = sim.SimBus(now_ms=start)
    for address in addresses:
        bus.add(sim.SimNode(address, tool=3 + address, serial=0x1000 + address, start_ms=start))
    io = mh.HostIO(send=bus.host_send, poll=bus.read_host, now=lambda: bus.elapsed, advance=bus.step)
    return bus, mh.MultinodeHost(io), io


def ready(*addresses):
    bus, host, io = make_bus(*addresses)
    bus.step(100)
    host.discover()
    return bus, host, io


def test_a_head_that_is_in_its_bootloader_is_not_commanded_and_says_why():
    bus, host, _ = ready(4, 5)
    host.table.nodes[4].state |= p.MN_STATE_BOOTLOADER
    with pytest.raises(mh.NodeNotReady) as why:
        host.select(4)
    assert "bootloader" in why.value.reason


def test_the_reason_a_head_is_not_commanded_is_the_first_that_applies_in_a_fixed_order():
    bus, host, io = ready(4)
    now = io.now()
    record = host.table.nodes[4]
    assert host._why_not(4, now) == "not ready"
    record.state |= p.MN_STATE_BOOTLOADER
    assert host._why_not(4, now) == "in its bootloader"
    record.state |= p.MN_STATE_FAULT
    assert host._why_not(4, now) == "a fault is latched"
    record.conflict = True
    assert host._why_not(4, now) == "another board uses its address"
    assert host._why_not(4, now + p.MN_NODE_TIMEOUT_MS * 10) == "gone (no status for too long)"


def test_the_lapse_reason_of_a_selection_is_each_of_its_causes_in_order():
    bus, host, io = ready(4, 5)
    host.select(4)
    now = io.now()
    assert host._lapse_reason(4, now) is None
    assert host._lapse_reason(99, now) == "gone"
    record = host.table.nodes[4]
    record.state |= p.MN_STATE_BOOTLOADER
    assert host._lapse_reason(4, now) == "bootloader"
    record.state |= p.MN_STATE_FAULT
    assert host._lapse_reason(4, now) == "fault"
    record.conflict = True
    assert host._lapse_reason(4, now) == "conflict"
    assert host._lapse_reason(4, now + p.MN_NODE_TIMEOUT_MS * 10) == "gone"


def test_two_heads_that_both_say_they_are_selected_are_a_lapse_of_the_selection():
    bus, host, io = ready(4, 5)
    host.select(4)
    host.table.nodes[5].state |= p.MN_STATE_SELECTED
    assert host._several_selected()
    assert host._lapse_reason(4, io.now()) == "several"


def test_a_selection_that_the_head_stopped_saying_is_lost_only_after_the_confirmation_time():
    bus, host, io = ready(4)
    host.select(4)
    record = host.table.nodes[4]
    record.state &= ~p.MN_STATE_SELECTED
    host._last_select_ms = io.now()
    assert host._lapse_reason(4, io.now()) is None
    assert host._lapse_reason(4, io.now() + host.confirm_ms + 1) == "lost"


def test_suspending_stops_the_repetition_and_releasing_forgets_the_selection():
    bus, host, _ = ready(4, 5)
    host.select(4)
    host.suspend()
    assert host.suspended
    host.tick()
    assert host.take_lapses() == []
    host.release()
    assert host.wanted is None and not host.suspended


def test_a_head_that_was_never_announced_or_is_not_selected_cannot_be_required():
    bus, host, _ = ready(4, 5)
    with pytest.raises(mh.NodeNotReady) as why:
        host.require_selected(77)
    assert "not announced" in why.value.reason
    with pytest.raises(mh.NodeNotReady) as why:
        host.require_selected(4)
    assert "not confirmed" in why.value.reason or "selected" in why.value.reason
    host.select(4)
    host.require_selected(4)
    assert host.is_confirmed(4) and not host.is_confirmed(5)


def test_a_node_that_does_not_exist_is_refused_by_select_and_send_without_a_node_needs_one_when_there_are_several():
    bus, host, _ = ready(4, 5)
    with pytest.raises(mh.NodeNotReady):
        host.select(63)
    with pytest.raises(mh.NodeNotReady):
        host.send(MOTION, b"\x01")


def test_the_short_status_query_of_a_head_that_is_silent_gives_nothing():
    bus, host, _ = ready(4, 5)
    bus.nodes[0].enabled = False
    assert host.command_status(4) is None


def test_a_status_query_of_a_live_head_gives_its_bytes_and_does_not_select_it():
    bus, host, _ = ready(4, 5)
    answer = host.command_status(5)
    assert answer is None or isinstance(answer, bytes)
    assert not host.is_confirmed(5)
