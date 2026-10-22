"""Frames for fuzzing a board (or the virtual board), made from the protocol specification.

For every identifier a host can send, valid frames (the examples of the specification and the edges of every field range) and
invalid ones (a length the specification does not allow, a value one past a range, a value that is no member of a strict
enumeration) are made, then frames of random identifiers and bytes. The same seed gives the same frames, so a failing frame can be
replayed.

Standard library only. Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
"""
from __future__ import annotations

import random
from dataclasses import dataclass

WIDTH = {"u8": 1, "u16": 2, "u24": 3, "u32": 4, "i16": 2, "i32": 4}
VALID, INVALID, RANDOM = "valid", "invalid", "random"


@dataclass(frozen=True)
class FuzzFrame:
    can_id: int
    data: bytes
    kind: str          # valid, invalid or random
    note: str = ""

    def line(self) -> str:
        return f"{self.can_id:03X} {self.data.hex().upper() or '-'} {self.kind} {self.note}".rstrip()


def parse_line(line: str) -> FuzzFrame:
    parts = line.split(" ", 3)
    return FuzzFrame(int(parts[0], 16), b"" if parts[1] == "-" else bytes.fromhex(parts[1]), parts[2], parts[3] if len(parts) > 3 else "")


def _lengths(dlc: dict) -> tuple[list[int], list[int]]:
    """(allowed lengths, lengths worth trying that the specification refuses)."""
    if dlc.get("any"):
        return list(range(0, 9)), []
    if "exact" in dlc:
        ok = [dlc["exact"]]
    elif "one_of" in dlc:
        ok = list(dlc["one_of"])
    else:
        ok = list(range(dlc["min"], dlc["max"] + 1))
    return ok, [n for n in range(0, 9) if n not in ok]


def _width(field: dict) -> int:
    return field.get("width") or WIDTH.get(field["type"], 0)


def _pack(layout: dict, values: dict, length: int) -> bytes:
    buf = bytearray(max(length, 0))
    for f in layout["fields"]:
        off, width = f.get("offset"), _width(f)
        if off is None or not width or off + width > length:
            continue
        v = values.get(f["name"], 0)
        if f["type"] == "bytes":
            raw = bytes.fromhex(v) if isinstance(v, str) else bytes(width)
            buf[off:off + width] = raw[:width].ljust(width, b"\x00")
        else:
            buf[off:off + width] = (v & ((1 << (8 * width)) - 1)).to_bytes(width, "big")
    return bytes(buf)


def _edges(field: dict) -> tuple[list[int], list[int]]:
    """(valid values worth trying, values just outside) for one numeric field."""
    width = _width(field) or 1
    top = (1 << (8 * width)) - 1
    if "range" in field:
        lo, hi = field["range"]
        good = sorted({lo, hi, (lo + hi) // 2})
        bad = [v for v in (lo - 1, hi + 1, top) if 0 <= v <= top and not lo <= v <= hi]
        return good, sorted(set(bad))
    return [0, 1, top], []


def generate(spec: dict, seed: int = 1, random_count: int = 400) -> list[FuzzFrame]:
    rng = random.Random(seed)
    out: list[FuzzFrame] = []
    sent_ids = []
    enums = {e["name"]: {v["value"] for v in e["values"]} for e in spec["enums"]}
    for m in spec["messages"]:
        if m["direction"] == "board_to_host":
            continue
        can_id = int(m["id"], 16)
        sent_ids.append(can_id)
        for layout in m["layouts"]:
            if layout["role"] == "response":
                continue
            ok_lengths, bad_lengths = _lengths(layout["dlc"])
            for ex in layout.get("examples", []):
                out.append(FuzzFrame(can_id, bytes.fromhex(ex["data"]), VALID, "example"))
            numeric = [f for f in layout["fields"] if f["type"] != "bytes" and f.get("offset") is not None and _width(f)]
            full = max(ok_lengths) if ok_lengths else 0
            base = {f["name"]: 0 for f in numeric}
            for f in numeric:
                good, bad = _edges(f)
                for v in good:
                    out.append(FuzzFrame(can_id, _pack(layout, {**base, f["name"]: v}, full), VALID, f"{f['name']}={v}"))
                for v in bad:
                    out.append(FuzzFrame(can_id, _pack(layout, {**base, f["name"]: v}, full), INVALID, f"{f['name']}={v} outside the range"))
                if f.get("strict_enum") and f.get("enum") in enums:
                    wrong = next((v for v in range(0, 256) if v not in enums[f["enum"]]), None)
                    if wrong is not None:
                        out.append(FuzzFrame(can_id, _pack(layout, {**base, f["name"]: wrong}, full), INVALID, f"{f['name']}={wrong} not in {f['enum']}"))
            for n in bad_lengths:
                out.append(FuzzFrame(can_id, bytes(rng.randrange(256) for _ in range(n)), INVALID, f"length {n}"))
    for _ in range(random_count):
        can_id = rng.choice(sent_ids) if rng.random() < 0.7 else rng.randrange(0, 0x800)
        n = rng.randrange(0, 9)
        out.append(FuzzFrame(can_id, bytes(rng.randrange(256) for _ in range(n)), RANDOM))
    # the ids at the edge of the standard range, with every length
    for can_id in (0x000, 0x7FF):
        for n in (0, 1, 8):
            out.append(FuzzFrame(can_id, bytes(rng.randrange(256) for _ in range(n)), RANDOM, "edge identifier"))
    return out
