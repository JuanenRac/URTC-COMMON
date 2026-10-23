#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_node_picker_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write conformance/node_picker_vectors.json: what the node picker says about a head and about the switch of the extension.

The rules live in ``urtc_common.node_picker`` (Python) and in the web studio (TypeScript); both are held to this file, which is
made from the Python rules over every combination that matters, so a change of a rule shows up as a change of this file.

Usage:
    python tools/make_node_picker_vectors.py           # write the file
    python tools/make_node_picker_vectors.py --check   # fail when the file differs from what the rules produce
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "conformance" / "node_picker_vectors.json"

from urtc_common import node_picker as np_  # noqa: E402
from urtc_common import node_picker_strings as strings  # noqa: E402
from urtc_common import protocol as p  # noqa: E402

REASONS = [
    "not announced", "gone (no status for too long)", "another board uses its address", "a fault is latched", "in its bootloader",
    "not confirmed selected", "did not confirm the selection", "not ready",
]


def build() -> dict:
    classify = []
    for state, conflict, alive in itertools.product(
            [0, p.MN_STATE_SELECTED, p.MN_STATE_FAULT, p.MN_STATE_CONFLICT, p.MN_STATE_BOOTLOADER,
             p.MN_STATE_SELECTED | p.MN_STATE_FAULT, p.MN_STATE_SELECTED | p.MN_STATE_BOOTLOADER, p.MN_STATE_FAULT | p.MN_STATE_BOOTLOADER],
            [False, True], [True, False]):
        classify.append({"state": state, "conflict": conflict, "alive": alive, "status": np_.classify_node(state, conflict, alive)})
    switch = [{"config": config, "switch": np_.switch_state(config)} for config in (
        None, {}, {"stored": 0, "running": 0}, {"stored": 1, "running": 1}, {"stored": 1, "running": 0}, {"stored": 0, "running": 1})]
    fail = [{"reason": reason, "key": strings.fail_key(reason)} for reason in REASONS]
    return {
        "about": "What the node picker says about a head and about the switch of the multinode extension. Made by tools/make_node_picker_vectors.py; do not edit by hand.",
        "state_bits": {"selected": p.MN_STATE_SELECTED, "fault": p.MN_STATE_FAULT, "conflict": p.MN_STATE_CONFLICT, "bootloader": p.MN_STATE_BOOTLOADER},
        "classify": classify, "switch": switch, "fail": fail,
    }


def render() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = render()
    if args.check:
        if not OUT.exists() or OUT.read_bytes().decode("utf-8") != content:
            print("NODE_PICKER_VECTORS=FAIL out of date (run python tools/make_node_picker_vectors.py)", file=sys.stderr)
            return 1
        print("NODE_PICKER_VECTORS=PASS")
        return 0
    OUT.write_bytes(content.encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
