#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_safety_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Writes the vectors of the clear-error command and of the communication watchdog.

Every case is run through ``urtc_common.safety_policy`` and the input and the answer are kept in ``conformance/safety_policy_vectors.json`` and as C tables
in ``generated/safety_policy_vectors.h``, which the firmware repository replays against ``fw_safety_policy.c``.

    python tools/make_safety_vectors.py            # write the files
    python tools/make_safety_vectors.py --check    # fail when they are out of date
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import protocol as R  # noqa: E402
from urtc_common import safety_policy as sp  # noqa: E402

OUT = ROOT / "conformance" / "safety_policy_vectors.json"
OUT_H = ROOT / "generated" / "safety_policy_vectors.h"

CLEAR_INPUTS = [
    # feature, latched, reason, temperature, actuators_off
    (False, True, R.ERROR_REASON_COMMS_WATCHDOG, 20, True),
    (False, False, R.ERROR_REASON_NONE, 20, True),
    (True, False, R.ERROR_REASON_NONE, 20, True),
    (True, True, R.ERROR_REASON_TOOL_ID, 20, True),
    (True, True, R.ERROR_REASON_COMMS_WATCHDOG, 49, True),
    (True, True, R.ERROR_REASON_COMMS_WATCHDOG, 50, True),
    (True, True, R.ERROR_REASON_COMMS_WATCHDOG, 51, True),
    (True, True, R.ERROR_REASON_THERMAL, 0, True),
    (True, True, R.ERROR_REASON_THERMAL, 300, True),
    (True, True, R.ERROR_REASON_SENSOR, sp.TEMPERATURE_UNKNOWN, True),
    (True, True, R.ERROR_REASON_COMMS_WATCHDOG, 20, False),
    (True, True, R.ERROR_REASON_STEPPER_SILENCE, 20, False),
    (True, True, R.ERROR_REASON_MAGNET_RELEASE, 0, True),
    (True, True, R.ERROR_REASON_FAN_STALL, 35, True),
    (True, True, R.ERROR_REASON_UNKNOWN, 20, True),
    (True, True, R.ERROR_REASON_TOOL_ID, 300, False),
    (True, True, R.ERROR_REASON_THERMAL, sp.TEMPERATURE_UNKNOWN, False),
    (False, False, R.ERROR_REASON_TOOL_ID, sp.TEMPERATURE_UNKNOWN, False),
]
LIMIT_INPUTS = [
    (0, 0), (1, 0), (100, 500), (500, 500), (1000, 500), (1500, 500), (4000, 500), (4000, 0), (10000, 500), (100000, 500), (100000, 2000), (100000, 1),
    (4294967295, 1), (4294967295, 500), (4294967295, 65535), (7, 3), (999, 1000), (2000, 1000),
]
STOP_INPUTS = [
    (True, True, 1001, 1000), (True, True, 1000, 1000), (True, True, 999, 1000), (False, True, 5000, 1000), (True, False, 5000, 1000),
    (True, True, 0, 0), (True, True, 1, 0), (True, True, 4294967295, 4294967294), (True, True, 4294967295, 4294967295), (False, False, 4294967295, 0),
]
MAGNET_INPUTS = [
    (True, True, True, 5001), (True, True, True, 5000), (True, True, True, 4999), (True, True, False, 60000), (True, False, True, 60000),
    (False, True, True, 60000), (False, False, True, 60000), (True, True, True, 0), (True, True, True, 4294967295),
]


def build() -> dict:
    return {
        "format": 1,
        "about": "Cases of the clear-error command and of the communication watchdog, run through urtc_common.safety_policy. Temperature 65535 is unknown.",
        "constants": {
            "clear_error_max_temp_c": R.CLEAR_ERROR_MAX_TEMP_C, "stepper_silence_min_ms": R.STEPPER_SILENCE_MIN_MS,
            "stepper_silence_percent": R.STEPPER_SILENCE_PERCENT, "magnet_silence_ms": R.MAGNET_SILENCE_MS, "default_speed_sps": sp.DEFAULT_SPEED_SPS,
        },
        "clear": [
            {"feature_on": f, "error_latched": e, "reason": r, "temperature_c": t, "actuators_off": a, "result": sp.clear_error_decision(f, e, r, t, a)}
            for f, e, r, t, a in CLEAR_INPUTS
        ],
        "stepper_limit": [{"steps": s, "speed_sps": v, "limit_ms": sp.stepper_silence_limit_ms(s, v)} for s, v in LIMIT_INPUTS],
        "stepper_stop": [
            {"feature_on": f, "moving": m, "silence_ms": s, "limit_ms": limit, "stop": sp.stepper_must_stop(f, m, s, limit)} for f, m, s, limit in STOP_INPUTS
        ],
        "magnet": [
            {"watchdog_on": w, "release_on": r, "energised": e, "silence_ms": s, "release": sp.magnet_must_release(w, r, e, s)} for w, r, e, s in MAGNET_INPUTS
        ],
    }


def b(value: bool) -> str:
    return "1" if value else "0"


def c_header(data: dict) -> str:
    lines = [
        "// GENERATED from spec by tools/make_safety_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef SAFETY_POLICY_VECTORS_H",
        "#define SAFETY_POLICY_VECTORS_H",
        "",
        "#include <stdint.h>",
        "",
        "typedef struct { uint8_t feature_on, error_latched, reason; uint16_t temperature_c; uint8_t actuators_off, result; } safety_clear_case_t;",
        "typedef struct { uint32_t steps, speed_sps, limit_ms; } safety_limit_case_t;",
        "typedef struct { uint8_t feature_on, moving; uint32_t silence_ms, limit_ms; uint8_t stop; } safety_stop_case_t;",
        "typedef struct { uint8_t watchdog_on, release_on, energised; uint32_t silence_ms; uint8_t release; } safety_magnet_case_t;",
        "",
        "static const safety_clear_case_t SAFETY_CLEAR_CASES[] = {",
    ]
    lines += [f"    {{{b(c['feature_on'])}, {b(c['error_latched'])}, {c['reason']}, {c['temperature_c']}u, {b(c['actuators_off'])}, {c['result']}}}," for c in data["clear"]]
    lines += ["};", "", "static const safety_limit_case_t SAFETY_LIMIT_CASES[] = {"]
    lines += [f"    {{{c['steps']}u, {c['speed_sps']}u, {c['limit_ms']}u}}," for c in data["stepper_limit"]]
    lines += ["};", "", "static const safety_stop_case_t SAFETY_STOP_CASES[] = {"]
    lines += [f"    {{{b(c['feature_on'])}, {b(c['moving'])}, {c['silence_ms']}u, {c['limit_ms']}u, {b(c['stop'])}}}," for c in data["stepper_stop"]]
    lines += ["};", "", "static const safety_magnet_case_t SAFETY_MAGNET_CASES[] = {"]
    lines += [f"    {{{b(c['watchdog_on'])}, {b(c['release_on'])}, {b(c['energised'])}, {c['silence_ms']}u, {b(c['release'])}}}," for c in data["magnet"]]
    lines += ["};", "", "#define SAFETY_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // SAFETY_POLICY_VECTORS_H", ""]
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
        print("SAFETY_VECTORS=" + ("FAIL" if stale else "PASS"))
        return 1 if stale else 0
    for path, text in outputs.items():
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
