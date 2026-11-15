#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_estop_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Writes the vectors of the emergency stop frame as a tool head follows it.

Every frame and every scenario is run through ``urtc_common.estop_follow``; the input, the state that is expected and the effect that follows are kept in
``conformance/estop_follow_vectors.json`` and as C tables in ``generated/estop_follow_vectors.h``, which the firmware repository replays against
``fw_estop_follow.c``.

    python tools/make_estop_vectors.py            # write the files
    python tools/make_estop_vectors.py --check    # fail when they are out of date
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import estop_follow as ef  # noqa: E402
from urtc_common import protocol as R  # noqa: E402

OUT = ROOT / "conformance" / "estop_follow_vectors.json"
OUT_H = ROOT / "generated" / "estop_follow_vectors.h"

# kind, detail, source, epoch, sequence
FRAMES = [
    ("trip by the operator, brain, epoch 1, sequence 1", (1, 1, 0, 1, 1)),
    ("trip by a controller fault on slot 3", (1, 6, 3, 6, 13)),
    ("trip by the CM5 bridge, stop-all", (1, 2, 16, 255, 65535)),
    ("trip with the unspecified reason", (1, 255, 8, 0, 0)),
    ("release for epoch 5", (2, 0, 0, 5, 12)),
    ("alive, not tripped", (3, 0, 0, 0, 300)),
    ("alive, tripped", (3, 1, 0, 9, 0)),
]
MALFORMED = [
    ("complement of the kind is wrong", "01010001010000fe"),
    ("complement of the detail is wrong", "010100010100fe00"),
    ("seven bytes", "010100010100fe"),
    ("nine bytes", "010100010100fefe00"),
    ("no bytes", ""),
    ("unknown kind with a valid complement", "040000010100fbff"),
    ("trip with an unknown reason", "012000010100fedf"),
    ("trip from an unknown source", "010109010100fefe"),
    ("release from a slot board", "020003010100fdff"),
    ("release with a detail", "020100010100fdfe"),
    ("alive from the CM5 bridge", "030010010100fcff"),
    ("alive with an unknown state", "030200010100fcfd"),
]
SEQ_CASES = [
    (False, 0, 0), (True, 1, 0), (True, 0, 0), (True, 0x7FFF, 0), (True, 0x8000, 0), (True, 0, 0xFFFF), (True, 5, 0xFFFE), (True, 0xFFFF, 0), (True, 100, 99), (True, 99, 100),
]
RELEASE = "020000{e:02x}{s:02x}00fdff"

# Each scenario starts from a head that has just powered up (latched). A step has "frame" (hex, delivered at time t) or "do" (tick or bus_off).
# "expect" is the state after the step. The first ten are those of the stack's own contract for a node; the last two are about the head.
SCENARIOS = [
    {"name": "power-up: latched, and nothing is heard", "steps": [{"t": 0, "do": "tick", "expect": "LATCHED"}, {"t": 5000, "do": "tick", "expect": "LATCHED"}]},
    {"name": "normal way out: announce, release for the same epoch", "steps": [
        {"t": 0, "frame": "030100050a00fcfe", "expect": "LATCHED"},
        {"t": 20, "frame": "030100050b00fcfe", "expect": "LATCHED"},
        {"t": 30, "frame": "020000050c00fdff", "expect": "READY"}]},
    {"name": "a replayed or mismatched release does not end a newer trip", "steps": [
        {"t": 0, "frame": "030100050a00fcfe"},
        {"t": 10, "frame": "020000050b00fdff", "expect": "READY"},
        {"t": 100, "frame": "010603060d00fef9", "expect": "LATCHED"},
        {"t": 110, "frame": "030100060e00fcfe", "expect": "LATCHED"},
        {"t": 120, "frame": "020000050f00fdff", "expect": "LATCHED"},
        {"t": 130, "frame": "020000060c00fdff", "expect": "LATCHED"},
        {"t": 140, "frame": "020000061000fdff", "expect": "READY"}]},
    {"name": "a release without a live master is ignored", "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 150, "frame": "020000011300fdff", "expect": "LATCHED"}]},
    {"name": "a release before any announcement is ignored (epoch unknown)", "steps": [{"t": 0, "frame": "020000011300fdff", "expect": "LATCHED"}]},
    {"name": "silence of the master latches a ready head, exactly after the timeout", "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 120, "do": "tick", "expect": "READY"},
        {"t": 121, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a frozen sender (same sequence again) does not keep the head alive", "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 60, "frame": "030000011400fcff", "expect": "READY"},
        {"t": 120, "do": "tick", "expect": "READY"},
        {"t": 121, "do": "tick", "expect": "LATCHED"}]},
    {"name": "the sequence wraps from 65535 to 0 and still counts as newer", "steps": [
        {"t": 0, "frame": "03010001fafffcfe"},
        {"t": 10, "frame": "02000001fefffdff"},
        {"t": 20, "frame": "03000001fffffcff"},
        {"t": 60, "frame": "030000010000fcff"},
        {"t": 150, "do": "tick", "expect": "READY"},
        {"t": 161, "do": "tick", "expect": "LATCHED"}]},
    {"name": "the clock wraps at 32 bits and the timeout still counts", "steps": [
        {"t": 4294967200, "frame": "030100011200fcfe"},
        {"t": 4294967210, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 4294967290, "frame": "030000011400fcff"},
        {"t": 94, "do": "tick", "expect": "READY"},
        {"t": 95, "do": "tick", "expect": "LATCHED"}]},
    {"name": "an alive frame that says tripped recovers a trip this head never heard", "steps": [
        {"t": 0, "frame": "030100021c00fcfe"},
        {"t": 10, "frame": "020000021d00fdff", "expect": "READY"},
        {"t": 20, "frame": "030100031e00fcfe", "expect": "LATCHED"}]},
    {"name": "malformed frames on 0x001 are a trip", "steps": [
        {"t": 0, "frame": "030100012800fcfe"},
        {"t": 10, "frame": "020000012900fdff", "expect": "READY"},
        {"t": 20, "frame": "01010001010000fe", "expect": "LATCHED"},
        {"t": 30, "frame": "030100012a00fcfe"},
        {"t": 40, "frame": "020000012b00fdff", "expect": "READY"},
        {"t": 50, "frame": "0101", "expect": "LATCHED"},
        {"t": 60, "frame": "030100012c00fcfe"},
        {"t": 70, "frame": "020000012d00fdff", "expect": "READY"},
        {"t": 80, "frame": "020003012e00fdff", "expect": "LATCHED"}]},
    {"name": "bus-off latches, and the bus coming back does not release", "steps": [
        {"t": 0, "frame": "030100013200fcfe"},
        {"t": 10, "frame": "020000013300fdff", "expect": "READY"},
        {"t": 20, "do": "bus_off", "expect": "LATCHED"},
        {"t": 30, "frame": "030000013400fcff", "expect": "LATCHED"}]},
    {"name": "after a bus-off a release waits for a new heartbeat of the master", "steps": [
        {"t": 0, "frame": "030100010a00fcfe"},
        {"t": 10, "frame": "020000010b00fdff", "expect": "READY"},
        {"t": 20, "do": "bus_off", "expect": "LATCHED"},
        {"t": 30, "frame": "020000010c00fdff", "expect": "LATCHED"},
        {"t": 40, "frame": "030000010d00fcff", "expect": "LATCHED"},
        {"t": 50, "frame": "020000010e00fdff", "expect": "READY"}]},
]


def run_scenario(scenario: dict) -> dict:
    node = ef.Node()
    steps = []
    for step in scenario["steps"]:
        if "frame" in step:
            effect = node.on_frame(step["t"], bytes.fromhex(step["frame"]))
        elif step["do"] == "tick":
            effect = node.tick(step["t"])
        else:
            effect = node.on_bus_off()
        out = dict(step)
        out["state_after"] = "READY" if node.state == ef.STATE_READY else "LATCHED"
        out["stop_reason"] = effect.stop_reason
        out["released"] = effect.released
        if "expect" in step:
            assert step["expect"] == out["state_after"], (scenario["name"], step)
        steps.append(out)
    return {"name": scenario["name"], "steps": steps}


def build() -> dict:
    frames = []
    for name, (kind, detail, source, epoch, seq) in FRAMES:
        data = ef.encode(kind, detail, source, epoch, seq)
        frame = ef.decode(data)
        assert frame == ef.Frame(kind, detail, source, epoch, seq), name
        frames.append({"name": name, "kind": kind, "detail": detail, "source": source, "epoch": epoch, "seq": seq, "data_hex": data.hex()})
    malformed = []
    for name, hexa in MALFORMED:
        assert ef.decode(bytes.fromhex(hexa)) is None, name
        malformed.append({"name": name, "data_hex": hexa})
    return {
        "format": 1,
        "about": "Frames and scenarios of the emergency stop frame as a tool head follows it, run through urtc_common.estop_follow. Time is in milliseconds.",
        "constants": {
            "can_id": R.ESTOP_CAN_ID, "alive_timeout_ms": R.ESTOP_ALIVE_TIMEOUT_MS,
            "reason_stop": R.ERROR_REASON_ESTOP, "reason_silence": R.ERROR_REASON_ESTOP_SILENCE,
        },
        "frames": frames,
        "malformed": malformed,
        "seq_newer": [{"have_last": h, "candidate": c, "last": ls, "newer": ef.seq_newer(c, h, ls)} for h, c, ls in SEQ_CASES],
        "scenarios": [run_scenario(s) for s in SCENARIOS],
    }


def b(value: bool) -> str:
    return "1" if value else "0"


def bytes_c(hexa: str) -> str:
    raw = bytes.fromhex(hexa)
    padded = list(raw) + [0] * (9 - len(raw))
    return "{" + ", ".join(f"0x{x:02X}" for x in padded) + "}"


def c_header(data: dict) -> str:
    lines = [
        "// GENERATED from spec by tools/make_estop_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef ESTOP_FOLLOW_VECTORS_H",
        "#define ESTOP_FOLLOW_VECTORS_H",
        "",
        "#include <stdint.h>",
        "",
        "// A frame of nine bytes at most (a longer one is a stop by its length alone, which the nine-byte case covers).",
        "typedef struct { uint8_t dlc; uint8_t data[9]; uint8_t kind, detail, source, epoch; uint16_t seq; } estop_frame_case_t;",
        "typedef struct { uint8_t dlc; uint8_t data[9]; } estop_malformed_case_t;",
        "typedef struct { uint8_t have_last; uint16_t candidate, last; uint8_t newer; } estop_seq_case_t;",
        "// kind: 0 a frame, 1 a tick, 2 a bus-off. expect_state: 0 latched, 1 ready, 255 not checked. state_after is the twin's state; stop_reason is 0 when no stop applies.",
        "typedef struct { uint8_t scenario; uint32_t t; uint8_t kind, dlc; uint8_t data[9]; uint8_t expect_state, state_after, stop_reason, released; } estop_step_t;",
        "",
        "static const estop_frame_case_t ESTOP_FRAME_CASES[] = {",
    ]
    for f in data["frames"]:
        lines.append(f"    {{8, {bytes_c(f['data_hex'])}, {f['kind']}, {f['detail']}, {f['source']}, {f['epoch']}, {f['seq']}u}},")
    lines += ["};", "", "static const estop_malformed_case_t ESTOP_MALFORMED_CASES[] = {"]
    for m in data["malformed"]:
        lines.append(f"    {{{len(m['data_hex']) // 2}, {bytes_c(m['data_hex'])}}},")
    lines += ["};", "", "static const estop_seq_case_t ESTOP_SEQ_CASES[] = {"]
    for s in data["seq_newer"]:
        lines.append(f"    {{{b(s['have_last'])}, {s['candidate']}u, {s['last']}u, {b(s['newer'])}}},")
    lines += ["};", "", "static const estop_step_t ESTOP_STEPS[] = {"]
    for i, scenario in enumerate(data["scenarios"]):
        for step in scenario["steps"]:
            if "frame" in step:
                kind, dlc, payload = 0, len(step["frame"]) // 2, bytes_c(step["frame"])
            else:
                kind, dlc, payload = (1 if step["do"] == "tick" else 2), 0, bytes_c("")
            expect = {"LATCHED": "0", "READY": "1"}.get(step.get("expect", ""), "255")
            after = "1" if step["state_after"] == "READY" else "0"
            lines.append(f"    {{{i}, {step['t']}u, {kind}, {dlc}, {payload}, {expect}, {after}, {step['stop_reason']}, {b(step['released'])}}},")
    lines += [
        "};", "",
        f"#define ESTOP_SCENARIO_COUNT {len(data['scenarios'])}",
        "#define ESTOP_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "",
        "#endif // ESTOP_FOLLOW_VECTORS_H", "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    outputs = {OUT: json.dumps(data, indent=2) + "\n", OUT_H: c_header(data)}
    stale = [path for path, text in outputs.items() if not path.exists() or path.read_bytes().replace(b"\r\n", b"\n") != text.encode("utf-8")]
    if args.check:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}")
        print("ESTOP_VECTORS=" + ("FAIL" if stale else "PASS"))
        return 1 if stale else 0
    for path, text in outputs.items():
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
