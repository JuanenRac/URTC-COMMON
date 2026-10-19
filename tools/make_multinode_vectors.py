#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_multinode_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write conformance/multinode_vectors.json from the multinode section of spec/can_protocol.json.

Each example of a frame gives one encode vector (fields to identifier and bytes) and one decode vector. The bytes come from
the independent packer of make_conformance.py, and every example that carries hand-written bytes is compared with it. Ranged
frames are written for the first node, a middle node and the last node. The extension is implemented in the firmware behind a
switch that is off by default and is tested on the host only.

Usage:
    python tools/make_multinode_vectors.py           # write the file
    python tools/make_multinode_vectors.py --check   # fail when the file differs from what the specification produces
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_conformance as mc  # noqa: E402

SPEC = ROOT / "spec" / "can_protocol.json"
OUT = ROOT / "conformance" / "multinode_vectors.json"
NODES = (0, 5, 31)
ABOUT = (
    "Vectors of the multinode extension (several tool heads on one bus). The firmware implements them behind a switch that is off by default; they are tested on the host only, not on boards. "
    "Hex strings have no separators; ids are written 0xNNN; 'node' is the node address added to the base identifier of a ranged frame."
)


def build(spec: dict) -> dict:
    mn = spec["multinode"]
    encode, decode, rejected = [], [], []
    for frame in mn["frames"]:
        layout = frame["layout"]
        base = int(frame["id"], 16)
        nodes = NODES if frame["span"] > 1 else (None,)
        for example in layout["examples"]:
            data = mc.ref_encode(layout, example["fields"]).hex().upper()
            if example["data"] != data:
                raise SystemExit(f"{frame['name']}: example {example['name']!r} says {example['data']} but the layout packs {data}")
            for node in nodes:
                can_id = base + (node or 0)
                entry = {"name": f"{frame['name']} {example['name']}" + (f" node {node}" if node is not None else ""), "frame": frame["name"],
                         "id": mc.hex_id(can_id), "data": data, "fields": example["fields"]}
                if node is not None:
                    entry["node"] = node
                encode.append(entry)
                decode.append(dict(entry))
        if frame["span"] > 1:
            rejected.append({"name": f"{frame['name']} node 32", "frame": frame["name"], "node": 32})
            rejected.append({"name": f"{frame['name']} node -1", "frame": frame["name"], "node": -1})
    return {"format": 1, "about": ABOUT, "protocol_version": spec["protocol_version"], "status": mn["status"],
            "encode": encode, "decode": decode, "rejected": rejected}


def render(spec: dict) -> str:
    return json.dumps(build(spec), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = render(json.loads(SPEC.read_text(encoding="utf-8")))
    if args.check:
        if not OUT.exists() or OUT.read_bytes().decode("utf-8") != content:
            print("MULTINODE_VECTORS=FAIL out of date (run python tools/make_multinode_vectors.py)", file=sys.stderr)
            return 1
        print("MULTINODE_VECTORS=PASS")
        return 0
    OUT.write_bytes(content.encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
