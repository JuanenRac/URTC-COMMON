#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_bus_health_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Writes conformance/bus_health_vectors.json: the cases that hold the Python and the TypeScript copies of the bus-health judgement to the same answers.

Every case is run through ``urtc_common.bus_health`` here, and the file keeps the input and the answer. The web studio tests its own copy against the same file.

    python tools/make_bus_health_vectors.py            # write the file
    python tools/make_bus_health_vectors.py --check    # fail when it is out of date
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import bus_health as bh  # noqa: E402

OUT = ROOT / "conformance" / "bus_health_vectors.json"

QUIET = {"tec": 0, "rec": 0, "bus_off_count": 0}
SECTIONS: list[object] = [
    None, "oops", {}, {"tec_warn": 50, "rec_warn": 60, "bus_off_warn": 3, "legacy_heads": ["A", 7, True, None]},
    {"tec_warn": 0, "rec_warn": 256, "bus_off_warn": True, "legacy_heads": "A"}, {"tec_warn": 1.5, "rec_warn": "9"}, {"tec_warn": 1, "rec_warn": 255, "bus_off_warn": 255},
]
FRAMES: list[list[int]] = [[], [1, 2], [0, 0, 0, 16, 7, 65, 12, 228], [100, 0, 0, 16, 7, 65, 12, 228], [0, 100, 0], [0, 0, 1], [95, 95, 0], [96, 0, 0], [255, 255, 255]]
WARNINGS = [
    ([QUIET, QUIET], False, [], None),
    ([], False, [], None),
    ([{"tec": 96, "rec": 0, "bus_off_count": 0}], False, [], None),
    ([{"tec": 0, "rec": 96, "bus_off_count": 0}], False, [], None),
    ([{"tec": 0, "rec": 0, "bus_off_count": 1}], False, [], None),
    ([{"tec": 95, "rec": 95, "bus_off_count": 0}], False, [], None),
    ([{}], False, [], None),
    ([], True, [], None),
    ([QUIET], False, ["HEAD-OLD", "HEAD-NEW"], {"legacy_heads": ["HEAD-OLD"]}),
    ([{"tec": 120, "rec": 0, "bus_off_count": 0}], False, ["HEAD-OLD"], {"legacy_heads": ["HEAD-OLD"]}),
    ([{"tec": 120, "rec": 0, "bus_off_count": 0}], False, ["HEAD-NEW"], {"legacy_heads": ["HEAD-OLD"]}),
    ([{"tec": 120, "rec": 0, "bus_off_count": 0}], False, ["HEAD-OLD"], None),
    ([{"tec": 200, "rec": 0, "bus_off_count": 3}], True, ["1"], {"legacy_heads": [1]}),
    ([{"tec": 40, "rec": 0, "bus_off_count": 0}], False, [], {"tec_warn": 40}),
    ([{"tec": 39, "rec": 0, "bus_off_count": 0}], False, [], {"tec_warn": 40}),
    ([{"tec": 0, "rec": 0, "bus_off_count": 2}], False, [], {"bus_off_warn": 3}),
    ([QUIET, {"tec": 130, "rec": 0, "bus_off_count": 0}], False, [], None),
]


def thresholds_of(section: object) -> dict:
    limits = bh.thresholds_from_config(section)
    return {"tec_warn": limits.tec_warn, "rec_warn": limits.rec_warn, "bus_off_warn": limits.bus_off_warn, "legacy_heads": list(limits.legacy_heads)}


def build() -> dict:
    return {
        "about": "Cases of urtc_common.bus_health: the same answers are expected of every copy of the judgement (Python and TypeScript).",
        "thresholds": [{"section": section, "expected": thresholds_of(section)} for section in SECTIONS],
        "profiles": [{"frame": frame, "expected": bh.profile_from_frame(bytes(frame))} for frame in FRAMES],
        "warnings": [{"profiles": profiles, "found_nobody": nobody, "heads": heads, "section": section,
                      "expected": bh.warnings(profiles, nobody, heads, bh.thresholds_from_config(section))} for profiles, nobody, heads, section in WARNINGS],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            print("BUS_HEALTH_VECTORS=FAIL out of date: run tools/make_bus_health_vectors.py", file=sys.stderr)
            return 1
        print("BUS_HEALTH_VECTORS=PASS")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"BUS_HEALTH_VECTORS=PASS wrote {len(build()['warnings'])} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
