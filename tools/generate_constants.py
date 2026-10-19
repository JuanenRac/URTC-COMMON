#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/generate_constants.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the constants and the frame builders and parsers from spec/can_protocol.json.

The specification is the only place where an identifier, a layout or a magic
payload is written down. This tool turns it into:

* ``generated/urtc_can_ids.h``       C: identifiers, length rules, offsets, enums, magic payloads
* ``generated/urtcCanIds.ts``        TypeScript: the same, plus pure encode_/decode_ functions
* ``src/urtc_common/protocol.py``    Python: the same, plus pure encode_/decode_ functions (stdlib only)
* ``docs/PROTOCOL_TABLE.md``         the table of every identifier and who implements it

None of them is edited by hand. ``--check`` writes nothing and fails when a file differs
from what the specification produces, so a copy that was not regenerated is caught.

Usage:
    python tools/generate_constants.py           # write the files
    python tools/generate_constants.py --check   # verify they are current
"""
from __future__ import annotations

import argparse
import json
import pprint
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "can_protocol.json"
WIDTH = {"u8": 1, "u16": 2, "u24": 3, "u32": 4, "i16": 2, "i32": 4}
BANNER = "GENERATED from spec/can_protocol.json by tools/generate_constants.py - do not edit by hand."
HEADER_LICENSE = (
    "Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
    "GPL-3.0-or-later - see LICENSE"
)


def load_spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def layout_key(message: dict, layout: dict) -> str:
    """The name that identifies one layout: the message name, plus the role when there are several."""
    base = message["name"].lower()
    if len(message["layouts"]) == 1:
        return base
    suffix = layout["role"] + (f"_{layout['variant']}" if layout.get("variant") else "")
    return f"{base}_{suffix}"


def camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part.capitalize() for part in rest)


def hex_id(value: int) -> str:
    return f"0x{value:03X}"


def const_value(value) -> str:
    if isinstance(value, float):
        return repr(value)
    return f"0x{value:X}" if value > 9 else str(value)


def tool_list(message: dict):
    return None if message["tools"] == "any" else list(message["tools"])


def dlc_rule(layout: dict) -> dict:
    return layout["dlc"]


def dlc_min_max(rule: dict) -> tuple[int, int]:
    if "exact" in rule:
        return rule["exact"], rule["exact"]
    if "one_of" in rule:
        return min(rule["one_of"]), max(rule["one_of"])
    if "min" in rule:
        return rule["min"], rule["max"]
    return 0, 8


def mn_key(frame: dict) -> str:
    return "mn_" + frame["name"].lower()


def mn_base_name(frame: dict) -> str:
    return "MN_ID_" + frame["name"] + ("_BASE" if frame["span"] > 1 else "")


def mn_params(frame: dict) -> list[tuple[str, str]]:
    """(name, kind) of the values a multinode builder takes, kind being 'int' or 'bytes'."""
    return [(f["name"], "bytes" if f["type"] == "bytes" else "int") for f in frame["layout"]["fields"]]


def runtime_field(field: dict) -> dict:
    """The part of a field the encoder and the decoder need, as plain data."""
    data = {"name": field["name"], "type": field["type"], "offset": field["offset"]}
    if field["type"] != "bytes":
        data["width"] = WIDTH[field["type"]]
    if "range" in field:
        data["range"] = field["range"]
    if field.get("optional"):
        data["optional"] = True
    if "present_from_dlc" in field:
        data["present_from_dlc"] = field["present_from_dlc"]
    if "fixed" in field:
        data["fixed"] = field["fixed"]
    if "length" in field:
        data["length"] = field["length"]
    if field.get("rest"):
        data["rest"] = True
    if "derived_length_of" in field:
        data["length_field"] = field["derived_length_of"]
    return data


def runtime_layouts(spec: dict) -> dict[str, dict]:
    enums = {e["name"]: e for e in spec["enums"]}
    out: dict[str, dict] = {}
    for message in spec["messages"]:
        for layout in message["layouts"]:
            fields = []
            for field in layout["fields"]:
                item = runtime_field(field)
                if field.get("strict_enum"):
                    item["allowed"] = [entry["value"] for entry in enums[field["enum"]]["values"]]
                fields.append(item)
            out[layout_key(message, layout)] = {
                "id": int(message["id"], 16),
                "role": layout["role"],
                "dlc": layout["dlc"],
                "fields": fields,
            }
    for frame in spec.get("multinode", {}).get("frames", []):
        layout = frame["layout"]
        out[mn_key(frame)] = {
            "id": int(frame["id"], 16),
            "role": layout["role"],
            "dlc": layout["dlc"],
            "fields": [runtime_field(field) for field in layout["fields"]],
        }
    return out


def message_table(spec: dict) -> dict[int, dict]:
    table: dict[int, dict] = {}
    for message in spec["messages"]:
        entry = {
            "name": message["name"],
            "group": message["group"],
            "direction": message["direction"],
            "handled_by": message["handled_by"],
            "tools": tool_list(message),
        }
        gates = message.get("gates")
        if gates:
            entry["gates"] = gates
        timing = message.get("timing")
        if timing:
            entry["timing"] = timing
        table[int(message["id"], 16)] = entry
    return table


def pyrepr(obj, indent: int = 0) -> str:
    text = pprint.pformat(obj, width=118, sort_dicts=False)
    if indent:
        pad = " " * indent
        text = text.replace("\n", "\n" + pad)
    return text


def pydict(table: dict, indent: int = 4) -> str:
    """A dict with one entry per line; each value on one line, so a generated table stays short to read."""
    pad = " " * indent
    body = "".join(pad + repr(key) + ": " + repr(value) + ",\n" for key, value in table.items())
    return "{\n" + body + "}"


def jsrepr(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
PY_RUNTIME = '''
# ---------------------------------------------------------------------------
# pure encoders and decoders (the runtime below is the same in every generated copy)
# ---------------------------------------------------------------------------
_INT_LIMITS = {
    "u8": (0, 0xFF), "u16": (0, 0xFFFF), "u24": (0, 0xFFFFFF), "u32": (0, 0xFFFFFFFF),
    "i16": (-0x8000, 0x7FFF), "i32": (-0x80000000, 0x7FFFFFFF),
}
_WIDTHS = {"u8": 1, "u16": 2, "u24": 3, "u32": 4, "i16": 2, "i32": 4}


def dlc_allows(rule, length):
    """Whether a payload of this length satisfies a length rule of the specification."""
    if "exact" in rule:
        return length == rule["exact"]
    if "one_of" in rule:
        return length in rule["one_of"]
    if "min" in rule:
        return rule["min"] <= length <= rule["max"]
    return 0 <= length <= DLC_MAX


def _dlc_floor(rule):
    if "exact" in rule:
        return rule["exact"]
    if "one_of" in rule:
        return min(rule["one_of"])
    return rule.get("min", 0)


def _as_bytes(value, name):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise TypeError(f"{name} must be bytes")


def _int_value(field, value):
    name = field["name"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    low, high = _INT_LIMITS[field["type"]]
    if not low <= value <= high:
        raise ValueError(f"{name} {value} does not fit {field['type']}")
    if "range" in field and not field["range"][0] <= value <= field["range"][1]:
        raise ValueError(f"{name} {value} is outside {field['range'][0]}..{field['range'][1]}")
    if "allowed" in field and value not in field["allowed"]:
        raise ValueError(f"{name} {value} is not one of the defined values")
    return value


def encode(layout, **values):
    """Build (identifier, payload) for a layout. Rejects anything out of range instead of clamping it."""
    spec = LAYOUTS[layout]
    fields = spec["fields"]
    names = {f["name"] for f in fields}
    unknown = set(values) - names
    if unknown:
        raise TypeError(f"unknown field(s) for {layout}: {', '.join(sorted(unknown))}")
    derived = {f["length_field"]: f["name"] for f in fields if "length_field" in f}
    out = bytearray()
    skipped = False
    byte_values = {}
    for field in fields:
        if field["type"] == "bytes":
            if field["name"] in values:
                raw = _as_bytes(values[field["name"]], field["name"])
            elif "fixed" in field:
                raw = bytes.fromhex(field["fixed"])
            elif field.get("optional"):
                raw = None
            else:
                raise TypeError(f"missing field {field['name']}")
            if raw is not None:
                if "fixed" in field and raw != bytes.fromhex(field["fixed"]):
                    raise ValueError(f"{field['name']} must be {field['fixed']}")
                if "length" in field and len(raw) != field["length"]:
                    raise ValueError(f"{field['name']} must be {field['length']} bytes")
                byte_values[field["name"]] = raw
    for field in fields:
        name = field["name"]
        if field["type"] == "bytes":
            raw = byte_values.get(name)
            if raw is None:
                skipped = True
                continue
            if skipped:
                raise ValueError(f"{name} follows an omitted optional field")
            out += raw
            continue
        if name in derived:
            value = len(byte_values[derived[name]])
            if name in values and values[name] != value:
                raise ValueError(f"{name} must equal the length of {derived[name]}")
        elif name in values and values[name] is not None:
            value = values[name]
        elif field.get("optional"):
            skipped = True
            continue
        else:
            raise TypeError(f"missing field {name}")
        if skipped:
            raise ValueError(f"{name} follows an omitted optional field")
        value = _int_value(field, value)
        out += value.to_bytes(_WIDTHS[field["type"]], "big", signed=field["type"].startswith("i"))
    if not dlc_allows(spec["dlc"], len(out)):
        raise ValueError(f"{layout}: a payload of {len(out)} bytes does not satisfy the length rule {spec['dlc']}")
    return spec["id"], bytes(out)


def decode(layout, data, strict=False):
    """Read a payload. None when it is too short (or, with strict, when it does not satisfy the length rule).

    Optional fields that the payload is too short to hold are None: not reported, never zero.
    Extra trailing bytes are ignored unless strict. Values are reported as received, never range-checked.
    """
    spec = LAYOUTS[layout]
    data = bytes(data)
    length = len(data)
    if strict and not dlc_allows(spec["dlc"], length):
        return None
    if length < _dlc_floor(spec["dlc"]):
        return None
    result = {}
    for field in spec["fields"]:
        name = field["name"]
        offset = field["offset"]
        if field["type"] == "bytes":
            if "length_field" in field:
                size = result[field["length_field"]]
                if length - offset < size:
                    return None
                result[name] = data[offset:offset + size]
            elif "length" in field:
                if length < offset + field["length"]:
                    if field.get("optional"):
                        result[name] = None
                        continue
                    return None
                result[name] = data[offset:offset + field["length"]]
            else:
                result[name] = data[offset:]
            continue
        width = _WIDTHS[field["type"]]
        needed = field.get("present_from_dlc", offset + width)
        if length < needed or length < offset + width:
            if field.get("optional"):
                result[name] = None
                continue
            return None
        result[name] = int.from_bytes(data[offset:offset + width], "big", signed=field["type"].startswith("i"))
    return result


def minor_field_pack(minor, patch=None):
    """The 16-bit minor field of the end-of-update frame: legacy, or 0x80 | patch in the high byte."""
    if patch is None or patch == PATCH_UNKNOWN or not 0 <= patch <= PATCH_MAX:
        return minor
    return ((PATCH_FLAG | patch) << 8) | (minor & 0xFF)


def minor_field_minor(field):
    return field & 0xFF


def minor_field_patch(field):
    """The patch carried by a minor field, or None for a legacy field."""
    high = (field >> 8) & 0xFF
    return (high & PATCH_MAX) if high & PATCH_FLAG else None


def version_compare(installed, candidate):
    """Order of a candidate against the installed version, each (major, minor, patch or None).

    1 when the candidate is newer, 0 when equal, -1 when older. Major and minor decide; the patch only
    when both versions carry one.
    """
    for left, right in zip(installed[:2], candidate[:2]):
        if right != left:
            return 1 if right > left else -1
    if installed[2] is None or candidate[2] is None:
        return 0
    if candidate[2] != installed[2]:
        return 1 if candidate[2] > installed[2] else -1
    return 0
'''


def render_python_multinode(spec: dict) -> list[str]:
    mn = spec.get("multinode")
    if not mn:
        return []
    lines: list[str] = []
    add = lines.append
    add("# ---------------------------------------------------------------------------")
    add("# multinode extension (" + mn.get("status_title", mn["status"].replace("_", " ")) + "): see docs/MULTINODE.md")
    add("# ---------------------------------------------------------------------------")
    for const in mn["constants"]:
        add(f"{const['name']} = {const_value(const['value'])}  # {const['title']}" + (f" ({const['unit']})" if const.get("unit") else ""))
    for flag in mn["state_flags"]:
        add(f"MN_STATE_{flag['name']} = 0x{1 << flag['bit']:02X}  # {flag['title']}")
    for action in mn["select_actions"]:
        add(f"MN_SELECT_{action['name']} = {action['value']}  # {action['title']}")
    for frame in mn["frames"]:
        add(f"{mn_base_name(frame)} = {hex_id(int(frame['id'], 16))}  # {frame['title']}" + (f" (+ node address, {frame['span']} identifiers)" if frame["span"] > 1 else ""))
    add("MN_RANGES = " + pyrepr({int(f["id"], 16): f["span"] for f in mn["frames"]}))
    add("MN_NAMES = " + pyrepr({int(f["id"], 16): f["name"] for f in mn["frames"]}))
    add("")
    add("")
    add("def mn_node_id(base: int, node: int) -> int:")
    add('    """The identifier of a node-addressed frame: the base of its range plus the node address."""')
    add("    if MN_RANGES.get(base, 1) == 1:")
    add('        raise ValueError(f"0x{base:03X} is not the base of an addressed range")')
    add("    if not isinstance(node, int) or isinstance(node, bool) or not 0 <= node <= MN_ADDRESS_MASK:")
    add('        raise ValueError(f"node address {node!r} is outside 0..{MN_ADDRESS_MASK}")')
    add("    return base + node")
    add("")
    add("")
    add("def mn_split_id(can_id: int):")
    add('    """(name, node) for an identifier of the extension (node is None for a broadcast frame), or None for any other identifier."""')
    add("    for base, span in MN_RANGES.items():")
    add("        if base <= can_id < base + span:")
    add("            return MN_NAMES[base], (can_id - base if span > 1 else None)")
    add("    return None")
    add("")
    add("")
    for frame in mn["frames"]:
        key = mn_key(frame)
        ranged = frame["span"] > 1
        params = mn_params(frame)
        sig = ", ".join((["node: int"] if ranged else []) + [f"{n}: {'bytes' if k == 'bytes' else 'int'}" for n, k in params])
        call = ", ".join(f"{n}={n}" for n, _ in params)
        add(f"def encode_{key}({sig}) -> tuple[int, bytes]:")
        add(f'    """{frame["title"]} ({hex_id(int(frame["id"], 16))}{" + node" if ranged else ""}, {frame["layout"]["role"]})."""')
        add(f'    can_id, data = encode("{key}", {call})')
        add("    return " + ("mn_node_id(can_id, node), data" if ranged else "can_id, data"))
        add("")
        add("")
        add(f"def decode_{key}(data: bytes, strict: bool = False) -> dict | None:")
        add(f'    """Fields of {hex_id(int(frame["id"], 16))}, or None when the payload is too short."""')
        add(f'    return decode("{key}", data, strict)')
        add("")
        add("")
    return lines


def render_python(spec: dict) -> str:
    enums = spec["enums"]
    layouts = runtime_layouts(spec)
    table = message_table(spec)
    lines: list[str] = []
    add = lines.append
    add('"""URTC CAN protocol: constants, tables and pure frame builders and parsers.')
    add("")
    add(BANNER)
    add("")
    add("Standard library only, so this file can also be copied on its own into a tool.")
    add('"""')
    add("# =============================================================================")
    for part in HEADER_LICENSE.splitlines():
        add(f"# {part}")
    add("# =============================================================================")
    add("from __future__ import annotations")
    add("")
    add(f"PROTOCOL_VERSION = {spec['protocol_version']}")
    add(f'BYTE_ORDER = "{spec["byte_order"]}"')
    add("")
    add("# --- constants ---")
    for const in spec["constants"]:
        add(f"{const['name']} = {const_value(const['value'])}  # {const['title']}" + (f" ({const['unit']})" if const.get("unit") else ""))
    add("")
    add("# --- identifiers ---")
    for message in spec["messages"]:
        add(f"CAN_ID_{message['name']} = {hex_id(int(message['id'], 16))}  # {message['title']}")
    add("")
    add("# --- enumerations ---")
    for enum in enums:
        add(f"# {enum['title']}")
        for entry in enum["values"]:
            add(f"{enum['prefix']}{entry['name']} = 0x{entry['value']:02X}")
        add("")
    add("ENUM_NAMES = " + pyrepr({e["name"]: {x["value"]: x["name"] for x in e["values"]} for e in enums}))
    add("ENUM_TITLES = " + pyrepr({e["name"]: {x["value"]: x["title"] for x in e["values"]} for e in enums}))
    add("TOOL_NAMES = ENUM_TITLES[\"tool\"]")
    add("")
    add("# --- magic payloads: a destructive or one-shot command is only obeyed with exactly these four bytes ---")
    for magic in spec["magic_payloads"]:
        add(f'MAGIC_{magic["name"].upper()} = bytes.fromhex("{magic["data"]}")  # {magic["title"]} (0x{int(magic["id"], 16):03X})')
    add("MAGIC_PAYLOADS = " + pyrepr({m["name"]: {"id": int(m["id"], 16), "data": m["data"]} for m in spec["magic_payloads"]}))
    add("")
    add("# --- registers of the expansion slave over the I2C link bus ---")
    prefixes = {"slave_bootloader": "SLAVE_BOOT_REG_", "slave_application": "SLAVE_APP_REG_"}
    for key, block in spec["registers"].items():
        for entry in block["entries"]:
            add(f"{prefixes[key]}{entry['name']} = 0x{entry['id']:02X}")
    add("")
    add("# --- SLCAN ---")
    add("SLCAN_BITRATES = " + pyrepr([tuple(item) for item in spec["slcan"]["bitrate_codes"]]))
    add(f'SLCAN_BITRATE_DEFAULT_CODE = "{spec["slcan"]["bitrate_default_code"]}"')
    add(f"SLCAN_RX_BUFFER_LIMIT = {spec['slcan']['rx_buffer_limit']}")
    add("")
    add("# --- one record per identifier ---")
    add("MESSAGES = " + pydict(table))
    add("")
    add("# --- one record per layout (the data the encoder and the decoder run on) ---")
    add("LAYOUTS = " + pydict(layouts))
    add(PY_RUNTIME.rstrip("\n"))
    add("")
    add("# ---------------------------------------------------------------------------")
    add("# one builder and one parser per layout")
    add("# ---------------------------------------------------------------------------")
    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = layout_key(message, layout)
            derived = {f["derived_length_of"] for f in layout["fields"] if "derived_length_of" in f}
            params = []
            for field in layout["fields"]:
                if field["name"] in derived:
                    continue
                if field["type"] == "bytes":
                    hint = "bytes"
                    default = ""
                    if "fixed" in field:
                        default = " = None"
                        hint = "bytes | None"
                    elif field.get("optional"):
                        default = " = None"
                        hint = "bytes | None"
                else:
                    hint = "int"
                    default = ""
                    if field.get("optional"):
                        default = " = None"
                        hint = "int | None"
                params.append((field["name"], hint, default))
            params.sort(key=lambda item: bool(item[2]))  # parameters with a default go last (the call passes keywords)
            signature = ", ".join(f"{n}: {h}{d}" for n, h, d in params)
            call = ", ".join(f"{n}={n}" for n, _, _ in params)
            if layout["role"] == "request" and not params:
                add(f"def encode_{key}() -> tuple[int, bytes]:")
                add(f'    """{message["title"]}: the frame the host sends ({hex_id(int(message["id"], 16))})."""')
                add(f'    return encode("{key}")')
            else:
                add(f"def encode_{key}({signature}) -> tuple[int, bytes]:")
                add(f'    """{message["title"]} ({hex_id(int(message["id"], 16))}, {layout["role"]}{", " + layout["variant"] if layout.get("variant") else ""})."""')
                if any(p[2] for p in params):
                    add("    values = {k: v for k, v in dict(" + call + ").items() if v is not None}")
                    add(f'    return encode("{key}", **values)')
                else:
                    add(f'    return encode("{key}", {call})')
            add("")
            add("")
            add(f"def decode_{key}(data: bytes, strict: bool = False) -> dict | None:")
            add(f'    """Fields of {hex_id(int(message["id"], 16))} ({layout["role"]}{", " + layout["variant"] if layout.get("variant") else ""}), or None when the payload is too short."""')
            add(f'    return decode("{key}", data, strict)')
            add("")
            add("")
    lines.extend(render_python_multinode(spec))
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------
TS_RUNTIME = '''
// ---------------------------------------------------------------------------
// pure encoders and decoders (the runtime below is the same in every generated copy)
// ---------------------------------------------------------------------------
export interface LayoutField {
  name: string;
  type: string;
  offset: number;
  width?: number;
  range?: [number, number];
  optional?: boolean;
  present_from_dlc?: number;
  fixed?: string;
  length?: number;
  rest?: boolean;
  length_field?: string;
  allowed?: number[];
}
export interface Layout {
  id: number;
  role: string;
  dlc: { exact?: number; min?: number; max?: number; one_of?: number[]; any?: boolean };
  fields: LayoutField[];
}
export type FieldValue = number | number[] | null;
export type Fields = Record<string, FieldValue>;

const INT_LIMITS: Record<string, [number, number]> = {
  u8: [0, 0xff], u16: [0, 0xffff], u24: [0, 0xffffff], u32: [0, 0xffffffff],
  i16: [-0x8000, 0x7fff], i32: [-0x80000000, 0x7fffffff],
};
const WIDTHS: Record<string, number> = { u8: 1, u16: 2, u24: 3, u32: 4, i16: 2, i32: 4 };

function hexToBytes(hex: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < hex.length; i += 2) out.push(Number.parseInt(hex.slice(i, i + 2), 16));
  return out;
}

export function dlcAllows(rule: Layout['dlc'], length: number): boolean {
  if (rule.exact !== undefined) return length === rule.exact;
  if (rule.one_of !== undefined) return rule.one_of.includes(length);
  if (rule.min !== undefined && rule.max !== undefined) return length >= rule.min && length <= rule.max;
  return length >= 0 && length <= DLC_MAX;
}

function dlcFloor(rule: Layout['dlc']): number {
  if (rule.exact !== undefined) return rule.exact;
  if (rule.one_of !== undefined) return Math.min(...rule.one_of);
  return rule.min ?? 0;
}

function checkInt(field: LayoutField, value: unknown): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) throw new TypeError(`${field.name} must be an integer`);
  const [low, high] = INT_LIMITS[field.type];
  if (value < low || value > high) throw new RangeError(`${field.name} ${value} does not fit ${field.type}`);
  if (field.range && (value < field.range[0] || value > field.range[1])) throw new RangeError(`${field.name} ${value} is outside ${field.range[0]}..${field.range[1]}`);
  if (field.allowed && !field.allowed.includes(value)) throw new RangeError(`${field.name} ${value} is not one of the defined values`);
  return value;
}

function checkBytes(name: string, value: unknown): number[] {
  if (!Array.isArray(value) && !(value instanceof Uint8Array)) throw new TypeError(`${name} must be a byte array`);
  const bytes = Array.from(value as ArrayLike<number>);
  if (bytes.some((b) => !Number.isInteger(b) || b < 0 || b > 255)) throw new RangeError(`${name} holds a value that is not a byte`);
  return bytes;
}

/** Build the frame for a layout. Throws on anything out of range instead of clamping it. */
export function encode(layout: string, values: Record<string, unknown> = {}): { id: number; data: number[] } {
  const spec = LAYOUTS[layout];
  const names = new Set(spec.fields.map((f) => f.name));
  for (const key of Object.keys(values)) if (!names.has(key)) throw new TypeError(`unknown field ${key} for ${layout}`);
  const derived = new Map<string, string>();
  for (const f of spec.fields) if (f.length_field) derived.set(f.length_field, f.name);
  const byteValues = new Map<string, number[]>();
  for (const f of spec.fields) {
    if (f.type !== 'bytes') continue;
    let raw: number[] | null = null;
    if (values[f.name] !== undefined && values[f.name] !== null) raw = checkBytes(f.name, values[f.name]);
    else if (f.fixed !== undefined) raw = hexToBytes(f.fixed);
    else if (!f.optional) throw new TypeError(`missing field ${f.name}`);
    if (raw !== null) {
      if (f.fixed !== undefined && raw.join(',') !== hexToBytes(f.fixed).join(',')) throw new RangeError(`${f.name} must be ${f.fixed}`);
      if (f.length !== undefined && raw.length !== f.length) throw new RangeError(`${f.name} must be ${f.length} bytes`);
      byteValues.set(f.name, raw);
    }
  }
  const out: number[] = [];
  let skipped = false;
  for (const f of spec.fields) {
    if (f.type === 'bytes') {
      const raw = byteValues.get(f.name);
      if (raw === undefined) { skipped = true; continue; }
      if (skipped) throw new RangeError(`${f.name} follows an omitted optional field`);
      out.push(...raw);
      continue;
    }
    let value: unknown;
    const source = derived.get(f.name);
    if (source !== undefined) {
      value = byteValues.get(source)!.length;
      if (values[f.name] !== undefined && values[f.name] !== value) throw new RangeError(`${f.name} must equal the length of ${source}`);
    } else if (values[f.name] !== undefined && values[f.name] !== null) value = values[f.name];
    else if (f.optional) { skipped = true; continue; }
    else throw new TypeError(`missing field ${f.name}`);
    if (skipped) throw new RangeError(`${f.name} follows an omitted optional field`);
    const n = checkInt(f, value);
    const width = WIDTHS[f.type];
    const unsigned = n < 0 ? n + 2 ** (8 * width) : n;
    for (let i = width - 1; i >= 0; i--) out.push(Math.floor(unsigned / 2 ** (8 * i)) % 256);
  }
  if (!dlcAllows(spec.dlc, out.length)) throw new RangeError(`${layout}: a payload of ${out.length} bytes does not satisfy the length rule`);
  return { id: spec.id, data: out };
}

/** Read a payload; null when it is too short (or, with strict, does not satisfy the length rule). Missing optional fields are null. */
export function decode(layout: string, data: ArrayLike<number>, strict = false): Fields | null {
  const spec = LAYOUTS[layout];
  const bytes = Array.from(data);
  const length = bytes.length;
  if (strict && !dlcAllows(spec.dlc, length)) return null;
  if (length < dlcFloor(spec.dlc)) return null;
  const result: Fields = {};
  for (const f of spec.fields) {
    const offset = f.offset;
    if (f.type === 'bytes') {
      if (f.length_field) {
        const size = result[f.length_field] as number;
        if (length - offset < size) return null;
        result[f.name] = bytes.slice(offset, offset + size);
      } else if (f.length !== undefined) {
        if (length < offset + f.length) {
          if (f.optional) { result[f.name] = null; continue; }
          return null;
        }
        result[f.name] = bytes.slice(offset, offset + f.length);
      } else result[f.name] = bytes.slice(offset);
      continue;
    }
    const width = WIDTHS[f.type];
    const needed = f.present_from_dlc ?? offset + width;
    if (length < needed || length < offset + width) {
      if (f.optional) { result[f.name] = null; continue; }
      return null;
    }
    let value = 0;
    for (let i = 0; i < width; i++) value = value * 256 + bytes[offset + i];
    if (f.type.startsWith('i') && value >= 2 ** (8 * width - 1)) value -= 2 ** (8 * width);
    result[f.name] = value;
  }
  return result;
}

/** The 16-bit minor field of the end-of-update frame: legacy, or 0x80 | patch in the high byte. */
export function minorFieldPack(minor: number, patch: number | null = null): number {
  if (patch === null || patch === PATCH_UNKNOWN || patch < 0 || patch > PATCH_MAX) return minor;
  return ((PATCH_FLAG | patch) << 8) | (minor & 0xff);
}
export function minorFieldMinor(field: number): number {
  return field & 0xff;
}
/** The patch carried by a minor field, or null for a legacy field. */
export function minorFieldPatch(field: number): number | null {
  const high = (field >> 8) & 0xff;
  return high & PATCH_FLAG ? high & PATCH_MAX : null;
}
/** 1 when the candidate is newer, 0 when equal, -1 when older; the patch decides only when both carry one. */
export function versionCompare(installed: [number, number, number | null], candidate: [number, number, number | null]): number {
  for (let i = 0; i < 2; i++) {
    const have = installed[i] as number;
    const want = candidate[i] as number;
    if (want !== have) return want > have ? 1 : -1;
  }
  const havePatch = installed[2];
  const wantPatch = candidate[2];
  if (havePatch === null || wantPatch === null) return 0;
  if (wantPatch !== havePatch) return wantPatch > havePatch ? 1 : -1;
  return 0;
}
'''


def render_typescript_multinode(spec: dict) -> list[str]:
    mn = spec.get("multinode")
    if not mn:
        return []
    lines: list[str] = []
    add = lines.append
    add("// ---------------------------------------------------------------------------")
    add("// multinode extension (" + mn.get("status_title", mn["status"].replace("_", " ")) + "): see docs/MULTINODE.md")
    add("// ---------------------------------------------------------------------------")
    for const in mn["constants"]:
        add(f"export const {const['name']} = {const_value(const['value'])}; // {const['title']}" + (f" ({const['unit']})" if const.get("unit") else ""))
    for flag in mn["state_flags"]:
        add(f"export const MN_STATE_{flag['name']} = 0x{1 << flag['bit']:02X}; // {flag['title']}")
    for action in mn["select_actions"]:
        add(f"export const MN_SELECT_{action['name']} = {action['value']}; // {action['title']}")
    for frame in mn["frames"]:
        add(f"export const {mn_base_name(frame)} = {hex_id(int(frame['id'], 16))}; // {frame['title']}" + (f" (+ node address, {frame['span']} identifiers)" if frame["span"] > 1 else ""))
    add("export const MN_RANGES: Record<number, number> = " + jsrepr({str(int(f["id"], 16)): f["span"] for f in mn["frames"]}) + ";")
    add("export const MN_NAMES: Record<number, string> = " + jsrepr({str(int(f["id"], 16)): f["name"] for f in mn["frames"]}) + ";")
    add("")
    add("/** The identifier of a node-addressed frame: the base of its range plus the node address. */")
    add("export function mnNodeId(base: number, node: number): number {")
    add("  if ((MN_RANGES[base] ?? 1) === 1) throw new Error(`0x${base.toString(16)} is not the base of an addressed range`);")
    add("  if (!Number.isInteger(node) || node < 0 || node > MN_ADDRESS_MASK) throw new Error(`node address ${node} is outside 0..${MN_ADDRESS_MASK}`);")
    add("  return base + node;")
    add("}")
    add("")
    add("/** [name, node] for an identifier of the extension (node is null for a broadcast frame), or null for any other identifier. */")
    add("export function mnSplitId(canId: number): [string, number | null] | null {")
    add("  for (const [key, span] of Object.entries(MN_RANGES)) {")
    add("    const base = Number(key);")
    add("    if (canId >= base && canId < base + span) return [MN_NAMES[base], span > 1 ? canId - base : null];")
    add("  }")
    add("  return null;")
    add("}")
    add("")
    for frame in mn["frames"]:
        key = mn_key(frame)
        cname = camel(key)
        cname = cname[0].upper() + cname[1:]
        ranged = frame["span"] > 1
        params = (["node: number"] if ranged else []) + [f"{camel(n)}: {'number[] | Uint8Array' if k == 'bytes' else 'number'}" for n, k in mn_params(frame)]
        inner = ", ".join(f"{n}: {camel(n)}" for n, _ in mn_params(frame))
        add(f"/** {frame['title']} ({hex_id(int(frame['id'], 16))}{' + node' if ranged else ''}, {frame['layout']['role']}). */")
        add(f"export function encode{cname}({', '.join(params)}): {{ id: number; data: number[] }} {{")
        add(f"  const frame = encode('{key}', {{ {inner} }});")
        add("  return " + ("{ id: mnNodeId(frame.id, node), data: frame.data };" if ranged else "frame;"))
        add("}")
        add(f"/** Fields of {hex_id(int(frame['id'], 16))}, or null when the payload is too short. */")
        add(f"export function decode{cname}(data: ArrayLike<number>, strict = false): Fields | null {{")
        add(f"  return decode('{key}', data, strict);")
        add("}")
        add("")
    return lines


def render_typescript(spec: dict) -> str:
    enums = spec["enums"]
    layouts = runtime_layouts(spec)
    table = message_table(spec)
    lines: list[str] = []
    add = lines.append
    add("// =============================================================================")
    add("// URTC CAN protocol: constants, tables and pure frame builders and parsers.")
    add(f"// {BANNER}")
    for part in HEADER_LICENSE.splitlines():
        add(f"// {part}")
    add("// Only erasable TypeScript syntax is used, so the file also runs under a type-stripping runtime.")
    add("// =============================================================================")
    add("")
    add(f"export const PROTOCOL_VERSION = {spec['protocol_version']};")
    add(f"export const BYTE_ORDER = '{spec['byte_order']}';")
    add("")
    add("// --- constants ---")
    for const in spec["constants"]:
        add(f"export const {const['name']} = {const_value(const['value'])}; // {const['title']}" + (f" ({const['unit']})" if const.get("unit") else ""))
    add("")
    add("// --- identifiers ---")
    for message in spec["messages"]:
        add(f"export const CAN_ID_{message['name']} = {hex_id(int(message['id'], 16))}; // {message['title']}")
    add("")
    add("// --- enumerations ---")
    for enum in enums:
        add(f"// {enum['title']}")
        for entry in enum["values"]:
            add(f"export const {enum['prefix']}{entry['name']} = 0x{entry['value']:02X};")
        add("")
    add("export const ENUM_NAMES: Record<string, Record<number, string>> = " + jsrepr({e["name"]: {str(x["value"]): x["name"] for x in e["values"]} for e in enums}) + ";")
    add("export const ENUM_TITLES: Record<string, Record<number, string>> = " + jsrepr({e["name"]: {str(x["value"]): x["title"] for x in e["values"]} for e in enums}) + ";")
    add("export const TOOL_NAMES: Record<number, string> = ENUM_TITLES.tool;")
    add("")
    add("// --- magic payloads: a destructive or one-shot command is only obeyed with exactly these four bytes ---")
    for magic in spec["magic_payloads"]:
        data = [int(magic["data"][i:i + 2], 16) for i in range(0, 8, 2)]
        add(f"export const MAGIC_{magic['name'].upper()} = {jsrepr(data)}; // {magic['title']} (0x{int(magic['id'], 16):03X})")
    add("")
    add("// --- registers of the expansion slave over the I2C link bus ---")
    prefixes = {"slave_bootloader": "SLAVE_BOOT_REG_", "slave_application": "SLAVE_APP_REG_"}
    for key, block in spec["registers"].items():
        for entry in block["entries"]:
            add(f"export const {prefixes[key]}{entry['name']} = 0x{entry['id']:02X};")
    add("")
    add("// --- SLCAN ---")
    add("export const SLCAN_BITRATES: [string, string][] = " + jsrepr(spec["slcan"]["bitrate_codes"]) + ";")
    add(f"export const SLCAN_BITRATE_DEFAULT_CODE = '{spec['slcan']['bitrate_default_code']}';")
    add(f"export const SLCAN_RX_BUFFER_LIMIT = {spec['slcan']['rx_buffer_limit']};")
    add("")
    add("// --- one record per identifier ---")
    add("export const MESSAGES: Record<number, { name: string; group: string; direction: string; handled_by: string; tools: number[] | null; gates?: Record<string, unknown>; timing?: Record<string, number> }> = " + jsrepr({str(k): v for k, v in table.items()}) + ";")
    add("")
    add("// --- one record per layout (the data the encoder and the decoder run on) ---")
    add("export const LAYOUTS: Record<string, Layout> = " + jsrepr(layouts) + ";")
    add(TS_RUNTIME.rstrip("\n"))
    add("")
    add("// ---------------------------------------------------------------------------")
    add("// one builder and one parser per layout")
    add("// ---------------------------------------------------------------------------")
    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = layout_key(message, layout)
            cname = camel(key)
            derived = {f["derived_length_of"] for f in layout["fields"] if "derived_length_of" in f}
            params = []
            for field in layout["fields"]:
                if field["name"] in derived:
                    continue
                if field["type"] == "bytes":
                    optional = field.get("optional") or "fixed" in field
                    params.append(f"{camel(field['name'])}{'?' if optional else ''}: number[] | Uint8Array")
                else:
                    params.append(f"{camel(field['name'])}{'?' if field.get('optional') else ''}: number")
            params.sort(key=lambda item: "?:" in item)  # optional parameters go last
            add(f"/** {message['title']} ({hex_id(int(message['id'], 16))}, {layout['role']}{', ' + layout['variant'] if layout.get('variant') else ''}). */")
            if params:
                add(f"export function encode{cname[0].upper()}{cname[1:]}({', '.join(params)}): {{ id: number; data: number[] }} {{")
                inner = ", ".join(f"{f['name']}: {camel(f['name'])}" for f in layout["fields"] if f["name"] not in derived)
                add(f"  return encode('{key}', {{ {inner} }});")
            else:
                add(f"export function encode{cname[0].upper()}{cname[1:]}(): {{ id: number; data: number[] }} {{")
                add(f"  return encode('{key}');")
            add("}")
            add(f"/** Fields of {hex_id(int(message['id'], 16))}, or null when the payload is too short. */")
            add(f"export function decode{cname[0].upper()}{cname[1:]}(data: ArrayLike<number>, strict = false): Fields | null {{")
            add(f"  return decode('{key}', data, strict);")
            add("}")
            add("")
    lines.extend(render_typescript_multinode(spec))
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# C
# ---------------------------------------------------------------------------
def render_c(spec: dict) -> str:
    lines: list[str] = []
    add = lines.append
    add("/* =============================================================================")
    add(f" * URTC CAN protocol: identifiers, length rules, field offsets, enumerations and magic payloads.")
    add(f" * {BANNER}")
    for part in HEADER_LICENSE.splitlines():
        add(f" * {part}")
    add(" * All multi-byte fields are big-endian. The names carry a URTC_ prefix so this header can be")
    add(" * included next to the firmware's own definitions without a clash.")
    add(" * ============================================================================= */")
    add("#ifndef URTC_CAN_IDS_H")
    add("#define URTC_CAN_IDS_H")
    add("")
    add("#include <stdint.h>")
    add("")
    add(f"#define URTC_PROTOCOL_VERSION {spec['protocol_version']}")
    add("")
    add("/* --- constants --- */")
    for const in spec["constants"]:
        value = const["value"]
        if isinstance(value, float):
            add(f"#define URTC_{const['name']} {value!r}  /* {const['title']} */")
        else:
            add(f"#define URTC_{const['name']} 0x{value:X}u  /* {const['title']} */")
    add("")
    add("/* --- identifiers, and the length rule of every layout --- */")
    for message in spec["messages"]:
        add(f"#define URTC_CAN_ID_{message['name']} 0x{int(message['id'], 16):03X}u  /* {message['title']} */")
        for layout in message["layouts"]:
            key = layout_key(message, layout).upper()
            low, high = dlc_min_max(layout["dlc"])
            add(f"#define URTC_DLC_{key}_MIN {low}u")
            add(f"#define URTC_DLC_{key}_MAX {high}u")
            for field in layout["fields"]:
                add(f"#define URTC_{key}_{field['name'].upper()}_OFFSET {field['offset']}u")
    add("")
    add("/* --- enumerations --- */")
    for enum in spec["enums"]:
        add(f"/* {enum['title']} */")
        for entry in enum["values"]:
            add(f"#define URTC_{enum['prefix']}{entry['name']} 0x{entry['value']:02X}u")
        add("")
    add("/* --- magic payloads --- */")
    for magic in spec["magic_payloads"]:
        data = ", ".join(f"0x{magic['data'][i:i + 2]}" for i in range(0, 8, 2))
        add(f"#define URTC_MAGIC_{magic['name'].upper()}_INIT {{ {data} }}  /* {magic['title']} (0x{int(magic['id'], 16):03X}) */")
    add("")
    add("/* --- registers of the expansion slave over the I2C link bus --- */")
    prefixes = {"slave_bootloader": "URTC_SLAVE_BOOT_REG_", "slave_application": "URTC_SLAVE_APP_REG_"}
    for key, block in spec["registers"].items():
        for entry in block["entries"]:
            add(f"#define {prefixes[key]}{entry['name']} 0x{entry['id']:02X}u")
    add("")
    mn = spec.get("multinode")
    if mn:
        add("/* --- multinode extension (" + mn.get("status_title", mn["status"].replace("_", " ")) + "): see docs/MULTINODE.md --- */")
        for const in mn["constants"]:
            add(f"#define URTC_{const['name']} 0x{const['value']:X}u  /* {const['title']} */")
        for flag in mn["state_flags"]:
            add(f"#define URTC_MN_STATE_{flag['name']} 0x{1 << flag['bit']:02X}u  /* {flag['title']} */")
        for action in mn["select_actions"]:
            add(f"#define URTC_MN_SELECT_{action['name']} {action['value']}u  /* {action['title']} */")
        for frame in mn["frames"]:
            add(f"#define URTC_{mn_base_name(frame)} 0x{int(frame['id'], 16):03X}u  /* {frame['title']}" + (f" (+ node address, {frame['span']} identifiers)" if frame["span"] > 1 else "") + " */")
            key = mn_key(frame).upper()
            low, high = dlc_min_max(frame["layout"]["dlc"])
            add(f"#define URTC_DLC_{key}_MIN {low}u")
            add(f"#define URTC_DLC_{key}_MAX {high}u")
            for field in frame["layout"]["fields"]:
                add(f"#define URTC_{key}_{field['name'].upper()}_OFFSET {field['offset']}u")
        add("#define URTC_MN_NODE_ID(base, node) ((uint16_t)((base) + ((node) & URTC_MN_ADDRESS_MASK)))")
        add("")
    add("#endif /* URTC_CAN_IDS_H */")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# the table for people
# ---------------------------------------------------------------------------
def dlc_text(rule: dict) -> str:
    if "exact" in rule:
        return str(rule["exact"])
    if "one_of" in rule:
        return " or ".join(str(n) for n in rule["one_of"])
    if "min" in rule:
        return f"{rule['min']}-{rule['max']}"
    return "any"


def render_table(spec: dict) -> str:
    lines = [
        "<!--",
        f"{BANNER}",
        "-->",
        "",
        "# Protocol table",
        "",
        "Every identifier of `spec/can_protocol.json`, one row each. **Dir**: H>B host to board, B>H board to host, both. "
        "**DLC**: the length rule of the layouts (request / response). **Implemented by**: F firmware, L URTC-FLASHER, T URTC-TESTER, W URTC-WEB-STUDIO; "
        "a dot means that implementation does not define the identifier.",
        "",
        "| ID | Name | Dir | DLC | Tools | F L T W | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    arrows = {"host_to_board": "H>B", "board_to_host": "B>H", "both": "both"}
    for message in spec["messages"]:
        dlcs = []
        for layout in message["layouts"]:
            text = dlc_text(layout["dlc"])
            if layout["role"] == "response" and any(x["role"] == "request" for x in message["layouts"]):
                text = f"/ {text}" + (f" ({layout['variant']})" if layout.get("variant") else "")
            dlcs.append(text)
        tools = "any" if message["tools"] == "any" else ",".join(str(t) for t in message["tools"])
        impl = message["implemented_by"]
        flags = " ".join(letter if impl[key] else "." for key, letter in (("firmware", "F"), ("flasher", "L"), ("tester", "T"), ("web_studio", "W")))
        notes = []
        if message.get("documented_in_prose") is False:
            notes.append("not in the prose")
        if "needs_magic" in message.get("gates", {}):
            notes.append("magic " + message["gates"]["needs_magic"])
        if not any(impl[k] for k in ("flasher", "tester", "web_studio")):
            notes.append("no host implements it")
        lines.append(
            f"| `{message['id']}` | {message['name']} | {arrows[message['direction']]} | {' '.join(dlcs)} | {tools} | `{flags}` | {'; '.join(notes)} |"
        )
    lines += ["", f"{len(spec['messages'])} identifiers, {len(spec['tools'])} tool values, "
              f"{sum(len(b['entries']) for b in spec['registers'].values())} slave registers, {len(spec['magic_payloads'])} magic payloads.", ""]
    mn = spec.get("multinode")
    if mn:
        lines += [
            "## Multinode extension",
            "",
            f"{mn['title']}. Status: **{mn.get('status_title', mn['status'].replace('_', ' '))}**. These identifiers are not in the table above and are not tested on boards. See `docs/MULTINODE.md`.",
            "",
            "| ID | Name | Dir | DLC | Notes |",
            "|---|---|---|---|---|",
        ]
        for frame in mn["frames"]:
            end = f"-0x{int(frame['id'], 16) + frame['span'] - 1:03X}" if frame["span"] > 1 else ""
            lines.append(f"| `{frame['id']}`{end} | MN_{frame['name']} | {'H>N' if frame['direction'] == 'host_to_node' else 'N>H'} | {dlc_text(frame['layout']['dlc'])} | {frame['title']} |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def outputs(spec: dict) -> dict[Path, str]:
    return {
        ROOT / "generated" / "urtc_can_ids.h": render_c(spec),
        ROOT / "generated" / "urtcCanIds.ts": render_typescript(spec),
        ROOT / "src" / "urtc_common" / "protocol.py": render_python(spec),
        ROOT / "docs" / "PROTOCOL_TABLE.md": render_table(spec),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="write nothing; fail when a generated file is out of date")
    args = parser.parse_args(argv)
    spec = load_spec()
    stale = []
    for path, text in outputs(spec).items():
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if args.check:
            if current != text:
                stale.append(label(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if current != text:
            path.write_bytes(text.encode("utf-8"))
            print(f"wrote {label(path)}")
    if args.check:
        if stale:
            print("GENERATED=FAIL out of date: " + ", ".join(stale) + " (run python tools/generate_constants.py)", file=sys.stderr)
            return 1
        print("GENERATED=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
