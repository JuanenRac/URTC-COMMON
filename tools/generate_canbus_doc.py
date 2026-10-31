#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/generate_canbus_doc.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the data of docs/CANBUS.TXT of the firmware repository from spec/can_protocol.json.

The CAN document of the firmware is prose written by hand (why a frame exists, what the firmware does with it) plus a reference
that must never disagree with the specification: the index of identifiers, the field layouts with their examples, the tool
profiles, the enumerations, the constants, the magic payloads, the registers of the expansion slave and the multinode frames.
That reference is generated here. The prose is the template: it is read and written back untouched, and only the blocks between
the markers

    [[ BEGIN GENERATED <name> sha256=<digest of the text between the markers> ]]
    ...
    [[ END GENERATED <name> ]]

are replaced. A block that does not exist yet is appended at the end of the file, so a new kind of data is one new renderer
below, and a new identifier in the specification is one run of this tool, with no change to this file. The digest in the marker
lets a repository without the specification (the firmware repository) find a generated block that was edited by hand.

Usage:
    python tools/generate_canbus_doc.py            # write the blocks
    python tools/generate_canbus_doc.py --check    # fail when a block is not what the specification produces
    python tools/generate_canbus_doc.py --file PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "can_protocol.json"
TOOLS = ROOT / "spec" / "tools.json"
TARGET = "URTC/docs/CANBUS.TXT"
NOTICE = "Generated from spec/can_protocol.json of URTC-COMMON by tools/generate_canbus_doc.py. Do not edit between the markers."
ANNEX_TITLE = "GENERATED REFERENCE (from the specification in URTC-COMMON)"
BEGIN = re.compile(r"^\[\[ BEGIN GENERATED (?P<name>[a-z0-9_]+) sha256=(?P<digest>[0-9a-f]{64}) \]\]$", re.M)
ARROWS = {"host_to_board": "host to board", "board_to_host": "board to host", "both": "both ways"}


def target_path() -> Path:
    return Path(os.environ.get("URTC_WORKSPACE", ROOT.parent)) / TARGET


def load_spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def dlc_text(rule: dict) -> str:
    if "exact" in rule:
        return str(rule["exact"])
    if "one_of" in rule:
        return " or ".join(str(n) for n in rule["one_of"])
    if "min" in rule:
        return f"{rule['min']}-{rule['max']}"
    return "any"


def cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines


def tools_of(message: dict) -> str:
    return "any" if message["tools"] == "any" else ",".join(str(t) for t in message["tools"])


# ---------------------------------------------------------------------------
# renderers: each returns the lines of one block
# ---------------------------------------------------------------------------
def render_summary(spec: dict) -> list[str]:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))["tools"]
    slave = sum(len(b["entries"]) for b in spec["registers"].values())
    return [
        f"{spec['title']}: protocol version {spec['protocol_version']}, byte order {spec['byte_order']}.",
        f"{len(spec['messages'])} identifiers, {len(tools)} tool profiles, {len(spec['enums'])} enumerations, "
        f"{len(spec['constants'])} constants, {len(spec['magic_payloads'])} magic payloads, {slave} registers of the expansion slave.",
        "",
        spec["about"],
    ]


def render_index(spec: dict) -> list[str]:
    rows = []
    for m in spec["messages"]:
        dlcs = []
        for layout in m["layouts"]:
            text = dlc_text(layout["dlc"])
            if layout["role"] == "response" and any(x["role"] == "request" for x in m["layouts"]):
                text = f"/ {text}"
            dlcs.append(text)
        rows.append([m["id"], m["name"], ARROWS[m["direction"]], " ".join(dlcs), tools_of(m), m["group"], m["title"]])
    return table(["ID", "Name", "Direction", "DLC", "Tools", "Group", "Title"], rows)


def field_rows(layout: dict) -> list[list[object]]:
    rows = []
    for f in layout["fields"]:
        width = f.get("width", f.get("length", "rest" if f.get("rest") else "?"))
        extra = []
        if "range" in f:
            extra.append(f"{f['range'][0]}..{f['range'][1]}")
        if "unit" in f:
            extra.append(f["unit"])
        if "enum" in f:
            extra.append(f"enum {f['enum']}")
        if f.get("optional"):
            extra.append("optional")
        if "fixed" in f:
            extra.append(f"fixed {f['fixed']}")
        if "present_from_dlc" in f:
            extra.append(f"from DLC {f['present_from_dlc']}")
        rows.append([f["offset"], width, f["type"], f["name"], ", ".join(extra), f.get("note", "")])
    return rows


def render_layouts(spec: dict) -> list[str]:
    lines: list[str] = []
    for m in spec["messages"]:
        lines += [f"### {m['id']} {m['name']} - {m['title']}", ""]
        facts = [ARROWS[m["direction"]], f"handled by the {m['handled_by'].replace('_', ' ')}", f"tools: {tools_of(m)}"]
        gates = m.get("gates", {})
        if gates.get("blocked_by_critical_error") is True:
            facts.append("refused while a critical error is declared")
        elif gates.get("blocked_by_critical_error") is False:
            facts.append("answered even while a critical error is declared")
        if "needs_magic" in gates:
            facts.append(f"needs the magic payload {gates['needs_magic']}")
        if m.get("read_only"):
            facts.append("read only")
        if "timing" in m:
            facts.append("timing: " + ", ".join(f"{k} {v}" for k, v in m["timing"].items()))
        if "firmware_accepts_dlc" in m:
            facts.append(f"the firmware accepts DLC {dlc_text(m['firmware_accepts_dlc'])}")
        lines += ["; ".join(facts) + ".", ""]
        for layout in m["layouts"]:
            name = layout["role"] + (f" ({layout['variant']})" if layout.get("variant") else "")
            lines += [f"{name}, DLC {dlc_text(layout['dlc'])}" + (f": {layout['note']}" if layout.get("note") else ""), ""]
            if layout["fields"]:
                lines += table(["Byte", "Width", "Type", "Field", "Values", "Note"], field_rows(layout))
            else:
                lines += ["(no payload)"]
            for example in layout.get("examples", []):
                values = ", ".join(f"{k}={v}" for k, v in example["fields"].items())
                lines += ["", f"Example {example['name']}: data {example['data'] or '(empty)'}" + (f" ({values})" if values else "")]
            lines.append("")
        for note in m.get("notes", []):
            lines += [f"Note: {note}"]
        if m.get("notes"):
            lines.append("")
    return lines[:-1] if lines and lines[-1] == "" else lines


def render_tools(spec: dict) -> list[str]:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))["tools"]
    rows = [[t["id"], t["name"], t["title"], t.get("kind", ""), t.get("category", ""), t.get("watchdog_ms", "")] for t in tools]
    return table(["Value", "Name", "Title", "Kind", "Category", "Watchdog ms"], rows)


def render_enums(spec: dict) -> list[str]:
    lines: list[str] = []
    for enum in spec["enums"]:
        lines += [f"{enum['name']} - {enum['title']} (prefix {enum['prefix']}, {enum['kind']})", ""]
        lines += table(["Value", "Name", "Title"], [[v["value"] if enum["kind"] == "value" else f"0x{v['value']:02X}", v["name"], v.get("title", "")]
                                                     for v in enum["values"]])
        lines.append("")
    return lines[:-1]


def render_constants(spec: dict) -> list[str]:
    return table(["Name", "Value", "Unit", "Group", "Title"], [[c["name"], c["value"], c.get("unit", ""), c.get("group", ""), c["title"]]
                                                                for c in spec["constants"]])


def render_magic(spec: dict) -> list[str]:
    rows = [[p["name"], p["id"], p["data"], ", ".join(p.get("also_on", [])), p["title"]] for p in spec["magic_payloads"]]
    return table(["Name", "ID", "Data", "Also on", "Title"], rows)


def render_registers(spec: dict) -> list[str]:
    lines: list[str] = []
    for key, block in spec["registers"].items():
        lines += [f"{key}: {block['title']}", ""]
        lines += table(["Register", "Name", "Access", "Length", "CAN", "Title"],
                       [[e["id"], e["name"], e["access"], e["length"], e.get("can", ""), e["title"]] for e in block["entries"]])
        lines.append("")
    return lines[:-1]


def render_procedures(spec: dict) -> list[str]:
    lines: list[str] = []
    for key, p in spec["procedures"].items():
        lines += [f"{key}: {p['title']}", ""]
        for part in ("request", "answers"):
            if part == "request" and "request" in p:
                lines.append(f"request {p['request']['id']} data {p['request']['data']}")
            if part == "answers" and "answers" in p:
                for a in p["answers"]:
                    grace = f", within {a['grace_ms']} ms" if "grace_ms" in a else ""
                    lines.append(f"answer {a['id']} ({'required' if a['required'] else 'optional'}) from {', '.join(a['from'])}{grace}")
        if "rule" in p:
            lines.append(p["rule"])
        lines.append("")
    return lines[:-1]


def render_multinode(spec: dict) -> list[str]:
    mn = spec["multinode"]
    lines = [f"{mn['title']}. Status: {mn.get('status_title', mn['status'].replace('_', ' '))}.", ""]
    rows = []
    for f in mn["frames"]:
        end = f"-0x{int(f['id'], 16) + f['span'] - 1:03X}" if f["span"] > 1 else ""
        rows.append([f"{f['id']}{end}", f["name"], "host to node" if f["direction"] == "host_to_node" else "node to host", dlc_text(f["layout"]["dlc"]), f["title"]])
    return lines + table(["ID", "Name", "Direction", "DLC", "Title"], rows)


def render_rack(spec: dict) -> list[str]:
    rack = spec["rack"]
    lines = [f"{rack['title']}. {rack['about']}", ""]
    directions = {"host_to_rack": "host to rack", "rack_to_host": "rack to host"}
    lines += table(["ID", "Name", "Direction", "DLC", "Title"],
                   [[f["id"], f["name"], directions[f["direction"]], dlc_text(f["layout"]["dlc"]), f["title"]] for f in rack["frames"]])
    for f in rack["frames"]:
        lines += ["", f"{f['id']} {f['name']} - {f['title']}", ""]
        lines += table(["Byte", "Width", "Type", "Field", "Values", "Note"], field_rows(f["layout"]))
        for example in f["layout"].get("examples", []):
            values = ", ".join(f"{k}={v}" for k, v in example["fields"].items())
            lines += ["", f"Example {example['name']}: data {example['data']} ({values})"]
        for note in f.get("notes", []):
            lines += ["", f"Note: {note}"]
    lines += ["", "Reasons of the reply (byte 2 of 0x261):", ""]
    lines += table(["Code", "Name", "Kind", "Meaning"], [[r["value"], r["name"], r["kind"], r["title"]] for r in rack["reply_reasons"]])
    return lines


RENDERERS = {
    "summary": render_summary, "index": render_index, "layouts": render_layouts, "tools": render_tools, "enums": render_enums,
    "constants": render_constants, "magic": render_magic, "registers": render_registers, "procedures": render_procedures,
    "multinode": render_multinode, "rack": render_rack,
}
TITLES = {
    "summary": "A. Summary", "index": "B. Index of identifiers", "layouts": "C. Field layouts and examples", "tools": "D. Tool profiles",
    "enums": "E. Enumerations", "constants": "F. Constants", "magic": "G. Magic payloads", "registers": "H. Registers of the expansion slave",
    "procedures": "I. Procedures", "multinode": "J. Several heads on one bus (multinode)",
    "rack": "K. Tool rack frames (0x260-0x261)",
}


def digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def block_text(name: str, lines: list[str]) -> str:
    body = "\n".join([NOTICE, "", *lines]) + "\n"
    return f"[[ BEGIN GENERATED {name} sha256={digest(body)} ]]\n{body}[[ END GENERATED {name} ]]\n"


def generated_blocks(spec: dict) -> dict[str, str]:
    return {name: block_text(name, render(spec)) for name, render in RENDERERS.items()}


def split_blocks(text: str) -> dict[str, tuple[str, str]]:
    """name -> (declared digest, body) of every generated block found in ``text`` (LF line ends)."""
    found = {}
    for m in BEGIN.finditer(text):
        end = text.find(f"[[ END GENERATED {m.group('name')} ]]\n", m.end())
        if end < 0:
            raise ValueError(f"block {m.group('name')} has no end marker")
        found[m.group("name")] = (m.group("digest"), text[m.end() + 1:end])
    return found


def verify_digests(text: str) -> list[str]:
    """Names of the blocks whose text no longer matches the digest in their marker (hand edits). Needs no specification."""
    return [name for name, (declared, body) in split_blocks(text).items() if digest(body) != declared]


def merge(text: str, blocks: dict[str, str]) -> str:
    """The prose in ``text`` with every generated block replaced by the new one; missing blocks are appended under the annex title."""
    for name, new in blocks.items():
        pattern = re.compile(rf"^\[\[ BEGIN GENERATED {name} sha256=[0-9a-f]{{64}} \]\]\n.*?^\[\[ END GENERATED {name} \]\]\n", re.M | re.S)
        if pattern.search(text):
            text = pattern.sub(lambda _m, new=new: new, text, count=1)
            continue
        if ANNEX_TITLE not in text:
            rule = "-" * 77
            text = text.rstrip("\n") + f"\n\n\n{rule}\n{ANNEX_TITLE}\n{rule}\n"
        text = text.rstrip("\n") + f"\n\n{TITLES[name]}\n\n{new}"
    return text


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="write nothing; fail when a block differs from the specification")
    parser.add_argument("--file", type=Path, default=None, help=f"the document to update (default: {TARGET} next to this repository)")
    args = parser.parse_args(argv)
    path = args.file or target_path()
    if not path.exists():
        print(f"{path} not found (set URTC_WORKSPACE or pass --file)", file=sys.stderr)
        return 2
    text, newline = read(path)
    merged = merge(text, generated_blocks(load_spec()))
    if args.check:
        if merged != text:
            print(f"{path} is not what the specification produces: run tools/generate_canbus_doc.py", file=sys.stderr)
            return 1
        print(f"CANBUS_DOC=PASS blocks={len(RENDERERS)}")
        return 0
    if merged != text:
        path.write_bytes(merged.replace("\n", newline).encode("utf-8"))
        print(f"updated {path}")
    else:
        print("already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
