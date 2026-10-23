#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_multinode_scenarios.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the scenarios of one node of the multinode extension, and the C table the firmware replays.

* ``conformance/multinode_scenarios.json``  each scenario starts one node (address, tool, instance, serial, start time) and plays steps:
  a time, optionally one received frame, and what must follow: the verdict of the node on the received frame (pass it to the
  single-head dispatcher or consume it), the effects it asks for (safe state, answer to a node command), the frames the node
  has due at that time, and whether it may obey single-head frames.
* ``generated/multinode_scenarios.h``       the same as C tables, replayed by the host suite of the firmware against ``multinode.c``.

The expectations are written below by hand from the rules in ``docs/MULTINODE.md``; they are not computed by any model of the node.
``urtc_common.multinode_sim`` and the firmware are both held to them. A time in a step is an offset from the start of the node, and
the clock is the 32-bit millisecond counter of the board (the last scenario starts just before it wraps).

Usage:
    python tools/make_multinode_scenarios.py           # write the files
    python tools/make_multinode_scenarios.py --check   # fail when a file differs from what this tool produces
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "conformance" / "multinode_scenarios.json"
OUT_H = ROOT / "generated" / "multinode_scenarios.h"
ABOUT = (
    "Scenarios of one node of the multinode extension, with the expectations written by hand from docs/MULTINODE.md. "
    "Hex strings have no separators; ids are written 0xNNN; 't' is the offset in ms from the start of the node, whose clock is the 32-bit "
    "millisecond counter of the board. 'verdict' is what the node does with the received frame: 'pass' hands it to the single-head "
    "dispatcher, 'consume' keeps it. 'emit' lists, in order, the frames the node has due after that frame; 'may' is whether it may obey "
    "single-head frames at that moment."
)
NO_EFFECT = {"safe_stop": 0, "answer_cmd": 0, "cmd_func": 0}

SELECT = "0x401"
SINGLE = "0x120"  # a single-head identifier (plain stepper move): what only the selected node may obey


def info(address: int, state: int, tool: int = 3, instance: int = 0, serial: str = "0A0B0C0D") -> dict:
    return {"id": f"0x{0x420 + address:03X}", "data": f"{tool:02X}{state:02X}{instance:02X}01{serial}"}


def status(address: int, state: int, error: int, uptime_s: int) -> dict:
    return {"id": f"0x{0x440 + address:03X}", "data": f"{state:02X}{error:02X}{uptime_s:04X}"}


def step(t: int, emit=(), may: int = 0, rx=None, verdict: str | None = None, effects: dict | None = None, fault: int = 0, error: int = 0) -> dict:
    out: dict = {"t": t}
    if rx is not None:
        out["rx"] = {"id": rx[0], "data": rx[1]}
        out["verdict"] = verdict
        out["effects"] = {**NO_EFFECT, **(effects or {})}
    if fault or error:
        out["fault"], out["error"] = fault, error
    out["emit"] = list(emit)
    out["may"] = may
    return out


def node(address: int = 5, start_ms: int = 0, tool: int = 3, instance: int = 0, serial: int = 0x0A0B0C0D) -> dict:
    return {"address": address, "tool": tool, "instance": instance, "enabled": 1, "serial": f"{serial:08X}", "start_ms": start_ms}


def scenarios() -> list[dict]:
    a = 5
    out = []

    out.append({"name": "alone on the bus: listens, then behaves as the one head", "node": node(a), "steps": [
        step(0),
        step(9),
        step(10, [info(a, 0)]),
        step(999),
        step(1000, [status(a, 0, 0, 1)]),
        step(1499, rx=(SINGLE, "0000000000"), verdict="consume"),
        step(1500, rx=(SINGLE, "0000000000"), verdict="pass", may=1),
        step(2000, [status(a, 1, 0, 2)], may=1),
    ]})

    out.append({"name": "hears another node: starts unselected and waits", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 0, 0, 0)], rx=("0x421", "0000000000000000"), verdict="consume"),
        step(1500, [status(a, 0, 0, 1)], rx=(SINGLE, "0000000000"), verdict="consume"),
        step(2600, [status(a, 0, 0, 2)], rx=("0x441", "00000000"), verdict="consume"),
    ]})

    out.append({"name": "selected, repeated, lapsed, taken away", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 0, 0, 0)], rx=("0x421", "0000000000000000"), verdict="consume"),
        step(2000, [status(a, 1, 0, 2)], may=1, rx=(SELECT, "010509"), verdict="consume"),
        step(2500, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(3000, [status(a, 1, 0, 3)], may=1),
        step(3999, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(4000, [status(a, 0, 0, 4)], may=0, rx=(SINGLE, "0000000000"), verdict="consume"),
        step(4100, [status(a, 1, 0, 4)], may=1, rx=(SELECT, "010501"), verdict="consume"),
        step(4200, [status(a, 0, 0, 4)], may=0, rx=(SELECT, "010602"), verdict="consume"),
        step(4250, [status(a, 1, 0, 4)], may=1, rx=(SELECT, "010503"), verdict="consume"),
        step(4300, [status(a, 0, 0, 4)], may=0, rx=(SELECT, "000004"), verdict="consume"),
        step(4400, [], may=0, rx=(SELECT, "0105"), verdict="consume"),
        step(4410, [], may=0, rx=(SELECT, "020500"), verdict="consume"),
        step(4420, [], may=0, rx=(SELECT, "012000"), verdict="consume"),
    ]})

    out.append({"name": "a malformed select changes nothing for a selected node", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 0, 0, 0)], rx=("0x421", "0000000000000000"), verdict="consume"),
        step(200, [status(a, 1, 0, 0)], may=1, rx=(SELECT, "010501"), verdict="consume"),
        step(300, [], may=1, rx=(SELECT, "0105"), verdict="consume"),
        step(310, [], may=1, rx=(SELECT, "020500"), verdict="consume"),
        step(320, [], may=1, rx=(SELECT, "012000"), verdict="consume"),
        step(330, [], may=1, rx=(SELECT, "01050000"), verdict="consume"),
        step(340, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
    ]})

    out.append({"name": "another board on the same address: conflict, safe state, never selected", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 4, 0, 0)], rx=("0x445", "01000000"), verdict="consume", effects={"safe_stop": 1}),
        step(200, [], rx=("0x445", "01000000"), verdict="consume"),
        step(300, [], rx=(SELECT, "010503"), verdict="consume"),
        step(1500, [status(a, 4, 0, 1)], rx=(SINGLE, "0000000000"), verdict="consume"),
        step(1600, [], rx=("0x465", "0110"), verdict="consume"),
        step(1700, [], rx=("0x425", "0300000100000000"), verdict="consume"),
        step(1800, [], rx=(SELECT, "010504"), verdict="consume"),
    ]})

    out.append({"name": "a selected node that meets a board on its address leaves the selection", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 0, 0, 0)], rx=("0x421", "0000000000000000"), verdict="consume"),
        step(200, [status(a, 1, 0, 0)], may=1, rx=(SELECT, "010501"), verdict="consume"),
        step(300, [status(a, 4, 0, 0)], may=0, rx=("0x445", "01000000"), verdict="consume", effects={"safe_stop": 1}),
    ]})

    out.append({"name": "safe stop is obeyed in every phase and changes no phase", "node": node(a), "steps": [
        step(50, [info(a, 0)], rx=("0x402", "07"), verdict="consume", effects={"safe_stop": 1}),
        step(60, [], rx=("0x402", "0700"), verdict="consume"),
        step(70, [], rx=("0x402", ""), verdict="consume"),
        step(1500, [status(a, 1, 0, 1)], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(1600, [], may=1, rx=("0x402", "03"), verdict="consume", effects={"safe_stop": 1}),
        step(1700, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
    ]})

    out.append({"name": "the node command answers the status query and nothing else", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(20, [], rx=("0x465", "0110"), verdict="consume", effects={"answer_cmd": 1, "cmd_func": 0x110}),
        step(30, [], rx=("0x465", "0120"), verdict="consume"),
        step(40, [], rx=("0x465", "01"), verdict="consume"),
        step(50, [], rx=("0x466", "0110"), verdict="consume"),
        step(60, [], rx=("0x465", "0110000000000000"), verdict="consume", effects={"answer_cmd": 1, "cmd_func": 0x110}),
        step(70, [], rx=("0x464", "0110"), verdict="consume"),
        step(80, [], rx=("0x485", "0110"), verdict="consume"),
    ]})

    out.append({"name": "discovery spreads the answers by address and refuses odd requests", "node": node(a), "steps": [
        step(10, [info(a, 0)]),
        step(100, [], rx=("0x400", "0102"), verdict="consume"),
        step(109, []),
        step(110, [info(a, 0)]),
        step(200, [], rx=("0x400", "010A"), verdict="consume"),
        step(249, []),
        step(250, [info(a, 0)]),
        step(300, [], rx=("0x400", "0100"), verdict="consume"),
        step(310, [], rx=("0x400", "0133"), verdict="consume"),
        step(320, [], rx=("0x400", "0002"), verdict="consume"),
        step(325, [], rx=("0x400", "01"), verdict="consume"),
        step(330, [], rx=("0x400", "0201"), verdict="consume"),
        step(334, []),
        step(335, [info(a, 0)]),
        step(350, [], rx=("0x400", "010200"), verdict="consume"),
        step(400, []),
    ]})

    out.append({"name": "address 0 answers a discovery at once, address 31 last", "node": node(0, tool=7, instance=2, serial=0x01020304), "steps": [
        step(0, [info(0, 0, tool=7, instance=2, serial="01020304")]),
        step(100, [info(0, 0, tool=7, instance=2, serial="01020304")], rx=("0x400", "0102"), verdict="consume"),
    ]})
    out.append({"name": "address 31 answers a discovery after 62 ms", "node": node(31, tool=9, serial=0xDEADBEEF), "steps": [
        step(61, []),
        step(62, [info(31, 0, tool=9, serial="DEADBEEF")]),
        step(100, [], rx=("0x400", "0102"), verdict="consume"),
        step(161, []),
        step(162, [info(31, 0, tool=9, serial="DEADBEEF")]),
    ]})

    out.append({"name": "a fault and its code are reported in the announcement and the status", "node": node(a), "steps": [
        step(10, [info(a, 2)], fault=1, error=0x2A),
        step(1000, [status(a, 2, 0x2A, 1)], fault=1, error=0x2A),
        step(1500, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass", fault=1, error=0x2A),
        step(2000, [status(a, 3, 0x2A, 2)], may=1, fault=1, error=0x2A),
        step(3000, [status(a, 1, 0, 3)], may=1),
    ]})

    out.append({"name": "the millisecond counter wraps in the middle of a listening window", "node": node(a, start_ms=0xFFFFFC00), "steps": [
        step(10, [info(a, 0)]),
        step(1000, [status(a, 0, 0, 1)]),
        step(1023, [], rx=(SINGLE, "0000000000"), verdict="consume"),
        step(1500, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(2000, [status(a, 1, 0, 2)], may=1),
        step(2100, [status(a, 1, 0, 2)], may=1, rx=(SELECT, "010505"), verdict="consume"),
    ]})

    out.append({"name": "a selection made across the wrap of the counter lapses on time", "node": node(a, start_ms=0xFFFFFC00), "steps": [
        step(10, [info(a, 0)]),
        step(100, [status(a, 0, 0, 0)], rx=("0x421", "0000000000000000"), verdict="consume"),
        step(900, [status(a, 1, 0, 0)], may=1, rx=(SELECT, "010501"), verdict="consume"),
        step(1900, [status(a, 1, 0, 1)], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(2899, [], may=1, rx=(SINGLE, "0000000000"), verdict="pass"),
        step(2900, [status(a, 0, 0, 2)], may=0, rx=(SINGLE, "0000000000"), verdict="consume"),
    ]})
    return out


def build() -> dict:
    return {"format": 1, "about": ABOUT, "scenarios": scenarios()}


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def _frame_c(frame: dict) -> str:
    data = bytes.fromhex(frame["data"])
    padded = ", ".join(f"0x{b:02X}" for b in data.ljust(8, b"\0"))
    return f"{{{int(frame['id'], 16)}u, {len(data)}, {{{padded}}}}}"


def render_header() -> str:
    spec = build()
    lines = [
        "// =============================================================================",
        "// URTC-COMMON - generated/multinode_scenarios.h",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "// =============================================================================",
        "// GENERATED from conformance/multinode_scenarios.json by tools/make_multinode_scenarios.py - do not edit by hand.",
        "// The steps a node of the multinode extension must follow; the firmware repository replays them against multinode.c.",
        "#ifndef URTC_MULTINODE_SCENARIOS_H",
        "#define URTC_MULTINODE_SCENARIOS_H",
        "",
        "#include <stdint.h>",
        "",
        "#define URTC_MN_SCENARIO_EMIT_MAX 2",
        "#define URTC_MN_VERDICT_NONE 0",
        "#define URTC_MN_VERDICT_PASS 1",
        "#define URTC_MN_VERDICT_CONSUME 2",
        "",
        "typedef struct { uint32_t id; uint8_t dlc; uint8_t data[8]; } urtc_mn_frame_t;",
        "typedef struct {",
        "    uint32_t t;                 // offset in ms from the start of the node",
        "    uint8_t has_rx;             // a frame is received before the node is asked for what is due",
        "    urtc_mn_frame_t rx;",
        "    uint8_t verdict;            // URTC_MN_VERDICT_* of the received frame",
        "    uint8_t fx_safe_stop, fx_answer_cmd;",
        "    uint16_t fx_cmd_func;",
        "    uint8_t fault, error;       // what the board reports to the node at this step",
        "    uint8_t emit_count;",
        "    urtc_mn_frame_t emit[URTC_MN_SCENARIO_EMIT_MAX];",
        "    uint8_t may;                // may the node obey single-head frames after this step",
        "} urtc_mn_step_t;",
        "typedef struct {",
        "    const char *name;",
        "    uint8_t address, tool, instance, enabled;",
        "    uint32_t serial, start_ms;",
        "    uint16_t first_step, step_count;",
        "} urtc_mn_scenario_t;",
        "",
        "static const urtc_mn_step_t URTC_MN_STEPS[] = {",
    ]
    rows = []
    index = []
    for sc in spec["scenarios"]:
        index.append((sc, len(rows)))
        for st in sc["steps"]:
            emits = st["emit"]
            if len(emits) > 2:
                raise SystemExit(f"{sc['name']}: more than two frames due in one step")
            rx = st.get("rx")
            verdict = {"pass": "URTC_MN_VERDICT_PASS", "consume": "URTC_MN_VERDICT_CONSUME", None: "URTC_MN_VERDICT_NONE"}[st.get("verdict")]
            fx = st.get("effects", NO_EFFECT)
            emit_c = ", ".join(_frame_c(e) for e in emits) if emits else "{0}"
            rows.append(
                f"    {{{st['t']}u, {1 if rx else 0}, {_frame_c({'id': rx['id'], 'data': rx['data']}) if rx else '{0, 0, {0}}'}, {verdict}, "
                f"{fx['safe_stop']}, {fx['answer_cmd']}, 0x{fx['cmd_func']:X}, {st.get('fault', 0)}, {st.get('error', 0)}, {len(emits)}, "
                f"{{{emit_c}}}, {st['may']}}},")
    lines += rows
    lines += ["};", "", "static const urtc_mn_scenario_t URTC_MN_SCENARIOS[] = {"]
    for sc, first in index:
        n = sc["node"]
        lines.append(f"    {{\"{sc['name']}\", {n['address']}, {n['tool']}, {n['instance']}, {n['enabled']}, 0x{n['serial']}u, {n['start_ms']}u, {first}, {len(sc['steps'])}}},")
    lines += ["};", "", "#endif // URTC_MULTINODE_SCENARIOS_H", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    files = {OUT: render(), OUT_H: render_header()}
    if args.check:
        stale = [p.name for p, content in files.items() if not p.exists() or p.read_bytes().decode("utf-8").replace("\r\n", "\n") != content]
        if stale:
            print(f"MULTINODE_SCENARIOS=FAIL out of date: {', '.join(stale)} (run python tools/make_multinode_scenarios.py)", file=sys.stderr)
            return 1
        print("MULTINODE_SCENARIOS=PASS")
        return 0
    for path, content in files.items():
        path.write_bytes(content.encode("utf-8"))
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
