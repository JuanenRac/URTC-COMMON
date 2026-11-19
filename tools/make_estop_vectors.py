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
    {"name": "a head configured at 50 ms latches after exactly 50 ms of silence", "alive_timeout_ms": 50, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 70, "do": "tick", "expect": "READY"},
        {"t": 71, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a head configured at 500 ms waits the whole 500 ms", "alive_timeout_ms": 500, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 520, "do": "tick", "expect": "READY"},
        {"t": 521, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a configured value below the limit is rejected and the default of 100 ms is used", "alive_timeout_ms": 39, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 120, "do": "tick", "expect": "READY"},
        {"t": 121, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a configured value above the limit is rejected and the default of 100 ms is used", "alive_timeout_ms": 501, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 120, "do": "tick", "expect": "READY"},
        {"t": 121, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a master that announces a lower timeout than the head's is obeyed (the lower one wins)", "alive_timeout_ms": 200, "master_timeout_ms": 60, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 80, "do": "tick", "expect": "READY"},
        {"t": 81, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a master that announces a higher timeout than the head's never makes the head more tolerant", "alive_timeout_ms": 60, "master_timeout_ms": 400, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 80, "do": "tick", "expect": "READY"},
        {"t": 81, "do": "tick", "expect": "LATCHED"}]},
    {"name": "a master that announces a value outside the limits is ignored", "alive_timeout_ms": 150, "master_timeout_ms": 5000, "steps": [
        {"t": 0, "frame": "030100011200fcfe"},
        {"t": 10, "frame": "020000011300fdff", "expect": "READY"},
        {"t": 20, "frame": "030000011400fcff"},
        {"t": 170, "do": "tick", "expect": "READY"},
        {"t": 171, "do": "tick", "expect": "LATCHED"}]},
]

# Resolution of a configured value: requested (0 = not set), the milliseconds in use and the status (0 ok, 1 rejected).
TIMEOUT_CONFIG_CASES = [
    (0, 100, 0), (100, 100, 0), (40, 40, 0), (500, 500, 0), (39, 100, 1), (20, 100, 1), (501, 100, 1), (1, 100, 1), (65535, 100, 1), (250, 250, 0),
]
# Writes of 0x1AE (data as hex) and queries of 0x1AF. The expected results are computed by the twin; the cases are chosen to cover every length, the limits of the
# silence (0, 39, 40, 500, 501, 65535) and the old forms, which must behave as they always did.
WRITE_CASES = [
    "4645415400", "464541540A", "464541542001", "4645415480", "46454154800000", "4645415480000032", "4645415480000000", "4645415480000028",
    "46454154800001F4", "4645415480000027", "46454154800001F5", "4645415480FFFF", "464541548000FFFF", "4645415480000014", "4645415480000001",
    "464541548000", "46454154800003", "464541548000003200", "4645415480000032", "46454154FF0300FF", "464541548004", "4645415480040032", "4645415501", "4645415400000000",
    "47454154800000", "", "464541", "46454154", "4645415480010064", "4645415480030064",
]
QUERY_CASES = ["", "00", "01", "02", "03", "04", "05", "FF", "0203", "0304", "0000"]
ANSWER_CASES = [(0, 0, 0, 0, 0), (0x80, 0x80, 0, 0, 50), (0x80, 0, 0, 0, 100), (0x80, 0x80, 1, 1, 500), (0xFF, 0xFF, 3, 3, 40), (2, 0, 0, 0, 0), (0x80, 0x80, 0, 0, 255), (0x80, 0x80, 0, 0, 256)]
# The head's own value, what the master announced (0 = nothing), the milliseconds in use and the status (0 ok, 2 differs and the lower is used, 3 ignored).
TIMEOUT_MASTER_CASES = [
    (100, 0, 100, 0), (100, 100, 100, 0), (100, 60, 60, 2), (100, 300, 100, 2), (40, 500, 40, 2), (500, 40, 40, 2), (100, 39, 100, 3), (100, 20, 100, 3), (100, 501, 100, 3), (60, 65535, 60, 3),
]


def run_scenario(scenario: dict) -> dict:
    node = ef.Node(scenario.get("alive_timeout_ms"))
    if "master_timeout_ms" in scenario:
        node.set_master_timeout(scenario["master_timeout_ms"])
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
    out = {"name": scenario["name"], "steps": steps}
    for key in ("alive_timeout_ms", "master_timeout_ms"):
        if key in scenario:
            out[key] = scenario[key]
    return out


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
    writes = []
    for hexa in WRITE_CASES:
        w = ef.parse_features_write(bytes.fromhex(hexa))
        writes.append({"data_hex": hexa, "valid": w is not None, "mask": w.mask if w else 0, "mask_ext": w.mask_ext if w else 0,
                       "timeout_ms": -1 if (w is None or w.timeout_ms is None) else w.timeout_ms})
    queries = [{"data_hex": hexa, "form": ef.query_form(bytes.fromhex(hexa))} for hexa in QUERY_CASES]
    answers = []
    for stored, running, stored_ext, running_ext, ms in ANSWER_CASES:
        data = ef.encode_timeout_answer(stored, running, stored_ext, running_ext, ms)
        assert ef.decode_timeout_answer(data)["timeout_ms"] == ms
        answers.append({"stored": stored, "running": running, "stored_ext": stored_ext, "running_ext": running_ext, "timeout_ms": ms, "data_hex": data.hex()})
    return {
        "format": 2,
        "about": "Frames and scenarios of the emergency stop frame as a tool head follows it, run through urtc_common.estop_follow. Time is in milliseconds.",
        "constants": {
            "can_id": R.ESTOP_CAN_ID, "alive_timeout_ms": R.ESTOP_ALIVE_TIMEOUT_MS,
            "reason_stop": R.ERROR_REASON_ESTOP, "reason_silence": R.ERROR_REASON_ESTOP_SILENCE,
            "alive_timeout_min_ms": R.ESTOP_ALIVE_TIMEOUT_MIN_MS, "alive_timeout_max_ms": R.ESTOP_ALIVE_TIMEOUT_MAX_MS,
        },
        "frames": frames,
        "malformed": malformed,
        "seq_newer": [{"have_last": h, "candidate": c, "last": ls, "newer": ef.seq_newer(c, h, ls)} for h, c, ls in SEQ_CASES],
        "scenarios": [run_scenario(s) for s in SCENARIOS],
        "timeout_config": [dict(zip(("requested", "ms", "status"), (r, *ef.resolve_timeout(r)))) for r, _, _ in TIMEOUT_CONFIG_CASES],
        "timeout_master": [dict(zip(("own", "master", "ms", "status"), (o, m, *ef.effective_timeout(o, m)))) for o, m, _, _ in TIMEOUT_MASTER_CASES],
        "feature_writes": writes,
        "feature_queries": queries,
        "timeout_answers": answers,
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
        "typedef struct { uint16_t requested, ms; uint8_t status; } estop_timeout_config_case_t;",
        "typedef struct { uint16_t own, master, ms; uint8_t status; } estop_timeout_master_case_t;",
        "// The silence of the master on the bus. A write of 0x1AE: valid = 0 when the firmware ignores it; timeout_ms is -1 when the write keeps the stored silence.",
        "typedef struct { uint8_t dlc; uint8_t data[9]; uint8_t valid, mask, mask_ext; int32_t timeout_ms; } estop_write_case_t;",
        "// A query of 0x1AF: form 0 three bytes, 1 six bytes, 2 eight bytes with the silence in force, 3 eight bytes with the stored silence.",
        "typedef struct { uint8_t dlc; uint8_t data[9]; uint8_t form; } estop_query_case_t;",
        "typedef struct { uint8_t stored, running, stored_ext, running_ext; uint16_t timeout_ms; uint8_t data[9]; } estop_answer_case_t;",
        "// Per scenario: the timeout the head is configured with (0 = not set) and the one the master announces (0 = nothing).",
        "typedef struct { uint16_t own, master; } estop_scenario_cfg_t;",
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
    lines += ["};", "", "static const estop_scenario_cfg_t ESTOP_SCENARIO_CFG[] = {"]
    for scenario in data["scenarios"]:
        lines.append(f"    {{{scenario.get('alive_timeout_ms', 0)}u, {scenario.get('master_timeout_ms', 0)}u}},")
    lines += ["};", "", "static const estop_timeout_config_case_t ESTOP_TIMEOUT_CONFIG_CASES[] = {"]
    for c in data["timeout_config"]:
        lines.append(f"    {{{c['requested']}u, {c['ms']}u, {c['status']}}},")
    lines += ["};", "", "static const estop_timeout_master_case_t ESTOP_TIMEOUT_MASTER_CASES[] = {"]
    for c in data["timeout_master"]:
        lines.append(f"    {{{c['own']}u, {c['master']}u, {c['ms']}u, {c['status']}}},")
    lines += ["};", "", "static const estop_write_case_t ESTOP_WRITE_CASES[] = {"]
    for c in data["feature_writes"]:
        lines.append(f"    {{{len(c['data_hex']) // 2}, {bytes_c(c['data_hex'])}, {b(c['valid'])}, {c['mask']}, {c['mask_ext']}, {c['timeout_ms']}}},")
    lines += ["};", "", "static const estop_query_case_t ESTOP_QUERY_CASES[] = {"]
    for c in data["feature_queries"]:
        lines.append(f"    {{{len(c['data_hex']) // 2}, {bytes_c(c['data_hex'])}, {c['form']}}},")
    lines += ["};", "", "static const estop_answer_case_t ESTOP_ANSWER_CASES[] = {"]
    for c in data["timeout_answers"]:
        lines.append(f"    {{{c['stored']}, {c['running']}, {c['stored_ext']}, {c['running_ext']}, {c['timeout_ms']}u, {bytes_c(c['data_hex'])}}},")
    lines += [
        "};", "",
        f"#define ESTOP_SCENARIO_COUNT {len(data['scenarios'])}",
        f"#define ESTOP_TIMEOUT_MIN_MS {data['constants']['alive_timeout_min_ms']}u",
        f"#define ESTOP_TIMEOUT_MAX_MS {data['constants']['alive_timeout_max_ms']}u",
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
