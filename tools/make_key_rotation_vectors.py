#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_key_rotation_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Writes conformance/key_rotation_vectors.json: which fingerprints a bootloader announces and accepts during a rotation window.

The expectations are written by hand here (not computed by the module under test); the tests hold src/urtc_common/key_rotation.py to them. Every
fingerprint is a throwaway: the first 8 bytes of the SHA-512 of a label. ``--check`` writes nothing and fails when the file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fp(label: str) -> str:
    return hashlib.sha512(b"rotation-test-key:" + label.encode()).digest()[:8].hex()


NEW, OLD, OTHER = fp("new"), fp("old"), fp("stranger")


def case(name, current, previous, window_s, started_at, now, accepted, revoked=(), unknown=(), flags=0, status=None):
    return {"name": name, "current": current, "previous": previous, "window_s": window_s, "started_at": started_at, "now": now, "revoked": list(revoked),
            "accepted": accepted, "refused": [OTHER, *unknown], "flags": flags, "seconds_left": status}


def cases() -> list[dict]:
    NO = 0xFFFFFFFF
    return [
        case("both valid inside the window", NEW, OLD, 3600, 1000, 1500, [NEW, OLD], flags=1, status=3100),
        case("both valid on the first second", NEW, OLD, 3600, 1000, 1000, [NEW, OLD], flags=1, status=3600),
        case("both valid on the last second", NEW, OLD, 3600, 1000, 4599, [NEW, OLD], flags=1, status=1),
        case("the old key expires when the window ends", NEW, OLD, 3600, 1000, 4600, [NEW], status=NO),
        case("the old key stays expired long after", NEW, OLD, 3600, 1000, 10**9, [NEW], status=NO),
        case("window of zero: only the current key", NEW, OLD, 0, 1000, 1000, [NEW], status=NO),
        case("clock before the start fails closed", NEW, OLD, 3600, 1000, 999, [NEW], status=NO),
        case("no previous key", NEW, None, 3600, 1000, 1500, [NEW], status=NO),
        case("the same fingerprint twice counts once", NEW, NEW, 3600, 1000, 1500, [NEW], status=NO),
        case("a revoked previous key is refused inside the window", NEW, OLD, 3600, 1000, 1500, [NEW], revoked=[OLD], status=NO),
        case("a revoked current key leaves nothing trusted", NEW, OLD, 3600, 1000, 1500, [], revoked=[NEW], flags=2, status=NO),
        case("a revoked current key outside the window leaves nothing", NEW, None, 0, 0, 5, [], revoked=[NEW], flags=2, status=NO),
    ]


def about() -> str:
    return ("Rotation of the signing key: the fingerprints announced on 0x7ED (the current one first, the previous one only inside the window) and the status "
            "on 0x7EB (05, count, flags, seconds left, 0xFFFFFFFF without a window). Times are monotonic seconds. Fingerprints are throwaway labels. "
            "'refused' lists fingerprints that must never be accepted in that case.")


def outputs() -> dict[Path, str]:
    doc = {"format": 1, "about": about(), "frame_ids": {"announce": "0x7ED", "status": "0x7EB"}, "status_op": 5, "max_announced": 2, "cases": cases()}
    return {ROOT / "conformance" / "key_rotation_vectors.json": json.dumps(doc, indent=2) + "\n"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None
        if current != text:
            if args.check:
                stale.append(path.name)
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {path.name}")
    if stale:
        print("KEY_ROTATION_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_key_rotation_vectors.py)", file=sys.stderr)
        return 1
    print("KEY_ROTATION_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
