# =============================================================================
# URTC-COMMON - tests/test_multinode_sim.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The model of a node against the scenarios the firmware also replays, and a host session against a bus of modelled nodes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from urtc_common import multinode_host as mh
from urtc_common import multinode_sim as sim
from urtc_common import protocol as p

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = json.loads((ROOT / "conformance" / "multinode_scenarios.json").read_text(encoding="utf-8"))["scenarios"]
SINGLE_HEAD = p.CAN_ID_MOTION_CMD if hasattr(p, "CAN_ID_MOTION_CMD") else 0x120


def test_scenarios_are_current():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_multinode_scenarios.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_there_are_scenarios_for_every_rule():
    names = " ".join(s["name"] for s in SCENARIOS)
    for word in ("alone", "another node", "selected", "conflict", "safe stop", "node command", "discovery", "fault", "wraps"):
        assert word in names


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_the_model_follows_every_scenario(scenario):
    spec = scenario["node"]
    node = sim.SimNode(spec["address"], tool=spec["tool"], instance=spec["instance"], serial=int(spec["serial"], 16),
                       enabled=bool(spec["enabled"]), start_ms=spec["start_ms"])
    for number, step in enumerate(scenario["steps"]):
        now = (spec["start_ms"] + step["t"]) & 0xFFFFFFFF
        label = f"{scenario['name']} step {number} (t={step['t']})"
        if "rx" in step:
            rx = step["rx"]
            verdict, fx = node.on_rx(int(rx["id"], 16), bytes.fromhex(rx["data"]), now)
            assert verdict == step["verdict"], label
            want = step["effects"]
            assert (int(fx.safe_stop), int(fx.answer_cmd), fx.cmd_func) == (want["safe_stop"], want["answer_cmd"], want["cmd_func"]), label
        emitted = []
        while (frame := node.service(now, bool(step.get("fault", 0)), step.get("error", 0))) is not None:
            emitted.append({"id": f"0x{frame[0]:03X}", "data": frame[1].hex().upper()})
            assert len(emitted) <= 2, label
        assert emitted == [{"id": e["id"], "data": e["data"].upper()} for e in step["emit"]], label
        assert int(node.may_single_head()) == step["may"], label


# ---- a host against a bus of modelled nodes ---------------------------------------------------------------------------------
def make_bus(*addresses, start=0):
    bus = sim.SimBus(now_ms=start)
    for address in addresses:
        bus.add(sim.SimNode(address, tool=3 + address, serial=0x1000 + address, start_ms=start))
    io = mh.HostIO(send=bus.host_send, poll=bus.read_host, now=lambda: bus.elapsed, advance=bus.step)
    return bus, mh.MultinodeHost(io), io


def obeyed_ids(node):
    return [i for i, _d in node.obeyed]


def test_discovery_lists_every_head_with_its_serial():
    bus, host, _ = make_bus(2, 9, 31)
    bus.step(50)
    found = host.discover()
    assert found == [2, 9, 31] and not host.legacy
    assert [host.node_info(n).serial for n in found] == [0x1002, 0x1009, 0x101F]
    assert [host.node_info(n).tool for n in found] == [5, 12, 34]


def test_a_bus_without_the_extension_is_a_single_head_and_frames_pass_through():
    bus = sim.SimBus()
    sent = []
    io = mh.HostIO(send=lambda i, d: sent.append((i, d)), poll=lambda: [], now=lambda: bus.elapsed, advance=bus.step)
    host = mh.MultinodeHost(io)
    assert host.discover(10) == [] and host.legacy
    host.send(SINGLE_HEAD, b"\x00\x01")
    host.send_destructive(0x7F0, bytes.fromhex("B0071D5A"), node=None)
    assert sent[-2:] == [(SINGLE_HEAD, b"\x00\x01"), (0x7F0, bytes.fromhex("B0071D5A"))]


def test_only_the_selected_head_obeys_and_the_others_never_actuate():
    bus, host, _ = make_bus(2, 9)
    bus.step(100)
    host.discover()
    host.select(9)
    host.send(SINGLE_HEAD, b"\x01", node=9)
    heads = {n.address: n for n in bus.nodes}
    assert obeyed_ids(heads[9]) == [SINGLE_HEAD] and obeyed_ids(heads[2]) == []
    host.select(2)
    host.send(SINGLE_HEAD, b"\x02", node=2)
    assert obeyed_ids(heads[2]) == [SINGLE_HEAD] and obeyed_ids(heads[9]) == [SINGLE_HEAD]
    assert heads[9].obeyed[0][1] == b"\x01" and heads[2].obeyed[0][1] == b"\x02"
    # the head that was taken away is no longer selected: the host refuses to send to it
    with pytest.raises(mh.NodeNotReady):
        host.send(SINGLE_HEAD, b"\x03", node=9)
    with pytest.raises(mh.NodeNotReady):
        host.send(SINGLE_HEAD, b"\x03")        # several heads: it has to say which


def test_an_unselected_head_ignores_the_bootloader_frames_and_the_host_does_not_send_them_unconfirmed():
    bus, host, _ = make_bus(1, 2)
    bus.step(100)
    host.discover()
    with pytest.raises(mh.NodeNotReady):
        host.send_destructive(0x7F0, bytes.fromhex("B0071D5A"), node=1)
    bus.host_send(0x7F0, bytes.fromhex("B0071D5A"))    # a frame that goes out anyway reaches nobody
    assert all(obeyed_ids(n) == [] for n in bus.nodes)
    host.select(1)
    host.send_destructive(0x7F0, bytes.fromhex("B0071D5A"), node=1)
    heads = {n.address: n for n in bus.nodes}
    assert obeyed_ids(heads[1]) == [0x7F0] and obeyed_ids(heads[2]) == []
    for bad in (p.MN_ID_SELECT, 0x421):
        with pytest.raises(ValueError):
            host.send(bad, b"")
    with pytest.raises(ValueError):
        host.send_destructive(SINGLE_HEAD, b"", node=1)


def test_a_selection_lapses_when_the_host_stops_and_tick_keeps_it():
    bus, host, _ = make_bus(4)
    bus.step(100)
    host.discover()
    host.select(4)
    for _ in range(6):                     # six seconds of work with the host repeating SELECT
        for _ in range(100):
            bus.step(10)
            host.tick()
        host.require_selected(4)
    host.release()
    bus.step(50)
    host.ingest()
    with pytest.raises(mh.NodeNotReady):
        host.require_selected(4)
    host.select(4)
    bus.step(p.MN_SELECT_TIMEOUT_MS + 200)  # the host dies: no more SELECT
    host.ingest()
    with pytest.raises(mh.NodeNotReady):
        host.require_selected(4)
    assert bus.nodes[0].phase == sim.PHASE_UNSELECTED


def test_two_boards_on_one_address_are_refused_and_stop_their_tools():
    bus, host, _ = make_bus(6, 6)
    bus.nodes[1].serial = 0x9999
    bus.step(100)
    host.discover()
    assert bus.nodes[0].conflict and bus.nodes[1].conflict
    assert bus.safe_state_calls == {6: 2}           # each board put its tool in the safe state once
    with pytest.raises(mh.NodeNotReady) as why:
        host.select(6)
    assert "address" in why.value.reason
    bus.host_send(*p.encode_mn_select(p.MN_SELECT_SELECT, 6, 1))
    assert all(not n.may_single_head() for n in bus.nodes)


def test_safe_stop_reaches_every_head_whatever_its_phase():
    bus, host, _ = make_bus(1, 2, 3)
    bus.step(100)
    host.discover()
    host.select(2)
    host.safe_stop(7)
    assert bus.safe_state_calls == {1: 1, 2: 1, 3: 1}
    assert [n.stop_reason for n in bus.nodes] == [7, 7, 7]
    host.require_selected(2)                         # safe stop does not change who is selected


def test_a_head_that_disappears_or_faults_is_not_commanded():
    bus, host, _ = make_bus(1, 2)
    bus.step(100)
    host.discover()
    bus.nodes[0].fault = True
    bus.nodes[0].status_now = True
    bus.step(5)
    host.ingest()
    with pytest.raises(mh.NodeNotReady) as why:
        host.select(1)
    assert "fault" in why.value.reason
    bus.nodes[1].enabled = False                      # the board loses power
    bus.step(p.MN_NODE_TIMEOUT_MS + 100)
    host.ingest()
    with pytest.raises(mh.NodeNotReady) as why:
        host.select(2)
    assert "gone" in why.value.reason
    with pytest.raises(mh.NodeNotReady):
        host.select(17)                               # never announced


def test_the_short_status_query_answers_without_selecting():
    bus, host, _ = make_bus(3, 8)
    bus.step(100)
    host.discover()
    assert host.command_status(8) == bytes(6)
    assert host.command_status(20) is None
    assert all(n.obeyed == [] for n in bus.nodes) and not any(n.may_single_head() for n in bus.nodes)


def test_a_status_from_a_node_never_announced_triggers_a_new_discovery():
    bus, host, _ = make_bus(1)
    bus.step(100)
    host.discover()
    late = bus.add(sim.SimNode(12, serial=0x4242, start_ms=bus.now))
    bus.step(1100)                                    # its first status arrives before anybody asked for it
    host.ingest()
    bus.step(100)
    host.ingest()
    assert host.node_info(12) is not None and host.node_info(12).serial == late.serial


def test_the_counter_wrap_does_not_confuse_a_session():
    bus, host, _ = make_bus(1, 2, start=0xFFFFFE00)
    bus.step(100)
    host.discover()
    host.select(2)
    for _ in range(50):
        bus.step(100)
        host.tick()
    host.require_selected(2)
    assert bus.now < 0x10000                          # it did wrap
