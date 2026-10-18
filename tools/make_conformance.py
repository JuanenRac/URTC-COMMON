#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_conformance.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the generated sections of conformance/can_vectors.json from spec/can_protocol.json.

The file holds two kinds of section:

* the sections that were agreed first and are written by hand (identifiers, magic payloads, SLCAN lines, the
  quick state, the version query, the minor field and the version order); this tool keeps them exactly as they
  are in the file, and ``--check`` compares them with nothing but their own presence;
* the sections that follow from the specification: one encode vector and one decode vector per example of every
  layout, the decode cases of short and legacy forms, the encodes that must be refused, the identifier list and
  the SLCAN byte streams.

The expected bytes are computed here with a deliberately small packer of its own (struct and plain loops, written
apart from the generated encoder), and every example that carries hand-written bytes in the specification is
compared with it, so the generated code is checked against a second, independent reading of the same layouts.

Usage:
    python tools/make_conformance.py           # write the file
    python tools/make_conformance.py --check   # fail when the file differs from what the specification produces
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "can_protocol.json"
VECTORS = ROOT / "conformance" / "can_vectors.json"
LEGACY = ("identifiers", "magic_payloads", "slcan_encode", "slcan_encode_rejected", "slcan_decode", "quick_state", "version_query", "minor_field", "version_order")
GENERATED = ("identifiers_all", "frames_encode", "frames_decode", "frames_rejected", "slcan_stream")
FORMAT = 2
ABOUT = (
    "Cross-implementation CAN protocol vectors. Every URTC client that implements a vector must reproduce it byte for byte. "
    "Hex strings have no separators; ids are written 0xNNN. A vector may carry a note when the readers are allowed to differ. "
    "The sections up to version_order are written by hand; identifiers_all, frames_encode, frames_decode, frames_rejected and "
    "slcan_stream are generated from spec/can_protocol.json by tools/make_conformance.py."
)
STRUCT = {"u8": ">B", "u16": ">H", "u32": ">I", "i16": ">h", "i32": ">i"}


def layout_key(message: dict, layout: dict) -> str:
    base = message["name"].lower()
    if len(message["layouts"]) == 1:
        return base
    return f"{base}_{layout['role']}" + (f"_{layout['variant']}" if layout.get("variant") else "")


def dlc_floor(rule: dict) -> int:
    if "exact" in rule:
        return rule["exact"]
    if "one_of" in rule:
        return min(rule["one_of"])
    return rule.get("min", 0)


def dlc_ok(rule: dict, length: int) -> bool:
    if "exact" in rule:
        return length == rule["exact"]
    if "one_of" in rule:
        return length in rule["one_of"]
    if "min" in rule:
        return rule["min"] <= length <= rule["max"]
    return length <= 8


# ---------------------------------------------------------------------------
# the independent packer
# ---------------------------------------------------------------------------
def ref_encode(layout: dict, values: dict) -> bytes:
    out = b""
    derived = {f["derived_length_of"]: f["name"] for f in layout["fields"] if "derived_length_of" in f}
    for field in layout["fields"]:
        name, kind = field["name"], field["type"]
        if kind == "bytes":
            raw = bytes.fromhex(values.get(name, field.get("fixed", "")))
            out += raw
        elif name in derived:
            out += struct.pack(">B", len(bytes.fromhex(values[derived[name]])))
        elif name in values and values[name] is not None:
            if kind == "u24":
                out += values[name].to_bytes(3, "big")
            else:
                out += struct.pack(STRUCT[kind], values[name])
    return out


def ref_decode(layout: dict, data: bytes) -> dict | None:
    if len(data) < dlc_floor(layout["dlc"]):
        return None
    out: dict = {}
    for field in layout["fields"]:
        name, kind, offset = field["name"], field["type"], field["offset"]
        if kind == "bytes":
            if "derived_length_of" in field:
                size = out[field["derived_length_of"]]
                if len(data) - offset < size:
                    return None
                out[name] = data[offset:offset + size].hex().upper()
            elif "length" in field:
                if len(data) < offset + field["length"]:
                    return None
                out[name] = data[offset:offset + field["length"]].hex().upper()
            else:
                out[name] = data[offset:].hex().upper()
            continue
        width = field["width"]
        needed = field.get("present_from_dlc", offset + width)
        if len(data) < needed or len(data) < offset + width:
            if field.get("optional"):
                out[name] = None
                continue
            return None
        if kind == "u24":
            out[name] = int.from_bytes(data[offset:offset + 3], "big")
        else:
            out[name] = struct.unpack(STRUCT[kind], data[offset:offset + width])[0]
    return out


# ---------------------------------------------------------------------------
def hex_id(value: int) -> str:
    return f"0x{value:03X}"


def build(spec: dict) -> dict:
    enums = {e["name"]: e for e in spec["enums"]}
    encode, decode, rejected = [], [], []
    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = layout_key(message, layout)
            frame_id = message["id"]
            for example in layout.get("examples", []):
                data = ref_encode(layout, example["fields"])
                if "data" in example and example["data"].upper() != data.hex().upper():
                    raise SystemExit(f"{key}: example {example['name']!r} says {example['data']} but the layout packs {data.hex().upper()}")
                if not dlc_ok(layout["dlc"], len(data)):
                    raise SystemExit(f"{key}: example {example['name']!r} does not satisfy the length rule")
                fields = {k: (v.upper() if isinstance(v, str) else v) for k, v in example["fields"].items()}
                name = f"{message['name']} {layout['role']}{' ' + layout['variant'] if layout.get('variant') else ''}: {example['name']}"
                encode.append({"name": name, "message": message["name"], "layout": key, "fields": fields, "frame": {"id": frame_id, "data": data.hex().upper()}})
                back = ref_decode(layout, data)
                decode.append({"name": name, "message": message["name"], "layout": key, "frame": {"id": frame_id, "data": data.hex().upper()}, "fields": back})
            for case in layout.get("decode_cases", []):
                data = bytes.fromhex(case["data"])
                decode.append({"name": f"{message['name']} {layout['role']}: {case['name']}", "message": message["name"], "layout": key,
                               "frame": {"id": frame_id, "data": case["data"]}, "fields": ref_decode(layout, data)})
            examples = layout.get("examples", [])
            if examples:
                base = ref_encode(layout, examples[0]["fields"])
                floor = dlc_floor(layout["dlc"])
                if floor > 0:
                    short = base[:floor - 1]
                    decode.append({"name": f"{message['name']} {layout['role']}: {len(short)} bytes is too short", "message": message["name"], "layout": key,
                                   "frame": {"id": frame_id, "data": short.hex().upper()}, "fields": None})
                if "exact" in layout["dlc"] and len(base) < 8:
                    long = base + b"\x00"
                    decode.append({"name": f"{message['name']} {layout['role']}: one byte too many is refused when strict", "message": message["name"], "layout": key,
                                   "frame": {"id": frame_id, "data": long.hex().upper()}, "fields": None, "strict": True})
            if layout["role"] != "request":
                pass
            # encodes that must be refused: first field with a range or a closed enum, and a wrong magic
            if examples:
                first = examples[0]["fields"]
                for field in layout["fields"]:
                    if field["type"] == "bytes":
                        if "fixed" in field:
                            wrong = dict(first)
                            wrong[field["name"]] = "00" * (len(field["fixed"]) // 2)
                            rejected.append({"name": f"{message['name']}: a payload that is not the magic one", "message": message["name"], "layout": key, "fields": wrong})
                        continue
                    if field["name"] not in first:
                        continue
                    if "range" in field and field["range"][1] + 1 < 2 ** (8 * field["width"]):
                        wrong = dict(first)
                        wrong[field["name"]] = field["range"][1] + 1
                        rejected.append({"name": f"{message['name']}: {field['name']} above its maximum", "message": message["name"], "layout": key, "fields": wrong})
                    if "range" in field and field["range"][0] > 0:
                        wrong = dict(first)
                        wrong[field["name"]] = field["range"][0] - 1
                        rejected.append({"name": f"{message['name']}: {field['name']} below its minimum", "message": message["name"], "layout": key, "fields": wrong})
                    if field.get("strict_enum"):
                        used = {e["value"] for e in enums[field["enum"]]["values"]}
                        unused = next(v for v in range(1, 256) if v not in used)
                        wrong = dict(first)
                        wrong[field["name"]] = unused
                        rejected.append({"name": f"{message['name']}: {field['name']} {unused} is not a defined value", "message": message["name"], "layout": key, "fields": wrong})
    identifiers_all = [{"id": m["id"], "name": m["name"]} for m in spec["messages"]]
    return {
        "identifiers_all": identifiers_all,
        "frames_encode": encode,
        "frames_decode": decode,
        "frames_rejected": rejected,
        "slcan_stream": slcan_streams(),
    }


def slcan_streams() -> list[dict]:
    def h(text: str) -> str:
        return text.encode("latin-1").hex().upper()

    return [
        {"name": "two frames in one chunk", "chunks": [h("t1110\rt1A6101\r")], "frames": [{"id": "0x111", "data": ""}, {"id": "0x1A6", "data": "01"}]},
        {"name": "a line split over three reads", "chunks": [h("t7F98"), h("000303CC"), h("01000003\r")], "frames": [{"id": "0x7F9", "data": "000303CC01000003"}]},
        {"name": "a terminator alone and an empty line", "chunks": [h("\r\r\rt1000\r")], "frames": [{"id": "0x100", "data": ""}]},
        {"name": "transmit acknowledgements between frames", "chunks": [h("z\rt1000\rZ\rt1101AA\r")], "frames": [{"id": "0x100", "data": ""}, {"id": "0x110", "data": "AA"}]},
        {"name": "a status character glued to the front of a frame", "chunks": [h("zt1000\r")], "frames": [{"id": "0x100", "data": ""}]},
        {"name": "a bus error bell before a frame", "chunks": [h("\at1000\r")], "frames": [{"id": "0x100", "data": ""}]},
        {"name": "an extended frame is skipped", "chunks": [h("T0000011180102030405060708\rt1110\r")], "frames": [{"id": "0x111", "data": ""}]},
        {"name": "remote frames are skipped", "chunks": [h("r1110\rR000001110\rt1110\r")], "frames": [{"id": "0x111", "data": ""}]},
        {"name": "a line of non-ASCII noise is skipped", "chunks": ["FFFE80" + h("t1110\r") + "C3A9" + h("\rt1000\r")], "frames": [{"id": "0x100", "data": ""}]},
        {"name": "a malformed line does not stop the next one", "chunks": [h("t11140102\rt+1F0\rt1G10\rt1101BB\r")], "frames": [{"id": "0x110", "data": "BB"}]},
        {"name": "more than 4096 bytes without a terminator are discarded", "chunks": [h("A" * 5000), h("t1000\r")], "frames": [{"id": "0x100", "data": ""}]},
        {"name": "a frame still unfinished produces nothing", "chunks": [h("t1111AA")], "frames": []},
    ]


def render(spec: dict, current: dict | None) -> str:
    out: dict = {"format": FORMAT, "about": ABOUT}
    legacy_source = current if current is not None else {}
    for section in LEGACY:
        if section not in legacy_source:
            raise SystemExit(f"conformance/can_vectors.json lacks the hand-written section {section}")
        out[section] = legacy_source[section]
    out.update(build(spec))
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    current = json.loads(VECTORS.read_text(encoding="utf-8")) if VECTORS.is_file() else None
    text = render(spec, current)
    existing = VECTORS.read_bytes().decode("utf-8") if VECTORS.is_file() else None
    if args.check:
        if existing != text:
            print("CONFORMANCE=FAIL conformance/can_vectors.json is out of date (run python tools/make_conformance.py)", file=sys.stderr)
            return 1
        print("CONFORMANCE=PASS")
        return 0
    if existing != text:
        VECTORS.write_bytes(text.encode("utf-8"))
        print("wrote conformance/can_vectors.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
