#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/generate_tools_doc.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the tool table of docs/TOOLS.TXT of the firmware repository from spec/tools.json, and check the prose beside it.

docs/TOOLS.TXT says in prose, tool by tool, what each profile does and which peripherals it uses. What it says about the number of a
tool and about its expansion board must never disagree with the specification, so this tool

  * writes the table of the 25 profiles (identifier, name, kind, range, watchdog, expansion board) between generated markers, in the
    same way tools/generate_canbus_doc.py writes the reference of the CAN document (the prose is left untouched; the digest in the
    marker finds a hand edit in a repository that has no specification), and
  * checks the heading of every section ("N. Name - ID 0xNN": the number, the identifier and the order) and the expansion board it
    names (none needed, recommended or required) against the profile with that identifier.

Usage:
    python tools/generate_tools_doc.py            # write the table
    python tools/generate_tools_doc.py --check    # fail when the table is not what the specification produces, or the prose disagrees
    python tools/generate_tools_doc.py --file PATH
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import generate_canbus_doc as canbus

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "spec" / "tools.json"
TARGET = "URTC/docs/TOOLS.TXT"
NOTICE = "Generated from spec/tools.json of URTC-COMMON by tools/generate_tools_doc.py. Do not edit between the markers."
ANNEX_TITLE = "GENERATED REFERENCE (from the specification in URTC-COMMON)"
BLOCK = "tool_table"
TITLE = "Tool table"
HEADING = re.compile(r"^(?P<number>\d+)\. (?P<name>.+) - ID 0x(?P<id>[0-9A-Fa-f]{2})\s*$", re.M)
EXPANSION = re.compile(r"^Expansion board:\s*(?P<word>none|recommended|required)\b", re.M | re.I)


def target_path() -> Path:
    return Path(os.environ.get("URTC_WORKSPACE", ROOT.parent)) / TARGET


def load_tools() -> list[dict]:
    return json.loads(TOOLS.read_text(encoding="utf-8"))["tools"]


def range_text(tool: dict) -> str:
    limits = tool["limits"]
    unit = tool.get("hero_metric", {}).get("unit", "")
    return f"{limits['min']} to {limits['max']} {unit} ({limits['default']})".replace("  ", " ").strip()


def render(tools: list[dict]) -> list[str]:
    rows = []
    for t in tools:
        watchdog = f"{t['watchdog_ms']} ms" if t.get("watchdog_ms") else "-"
        rows.append([f"{t['id']} (0x{t['id']:02X})", t["display_name"], t["kind"], range_text(t), watchdog, t.get("expansion_board", "none")])
    return canbus.table(["ID", "Tool", "Kind", "Range (default)", "Watchdog", "Expansion board"], rows)


def block(tools: list[dict]) -> str:
    body = "\n".join([NOTICE, "", *render(tools)]) + "\n"
    return f"[[ BEGIN GENERATED {BLOCK} sha256={canbus.digest(body)} ]]\n{body}[[ END GENERATED {BLOCK} ]]\n"


def merge(text: str, new: str) -> str:
    pattern = re.compile(rf"^\[\[ BEGIN GENERATED {BLOCK} sha256=[0-9a-f]{{64}} \]\]\n.*?^\[\[ END GENERATED {BLOCK} \]\]\n", re.M | re.S)
    if pattern.search(text):
        return pattern.sub(lambda _m: new, text, count=1)
    if ANNEX_TITLE not in text:
        rule = "-" * 77
        text = text.rstrip("\n") + f"\n\n\n{rule}\n{ANNEX_TITLE}\n{rule}\n"
    return text.rstrip("\n") + f"\n\n{TITLE}\n\n{new}"


def prose_problems(text: str, tools: list[dict]) -> list[str]:
    """What the prose says about a tool that the specification does not: the number, the identifier, the order, the expansion board."""
    problems = []
    by_id = {t["id"]: t for t in tools}
    headings = list(HEADING.finditer(text))
    if len(headings) != len(tools):
        problems.append(f"the document has {len(headings)} tool sections and the specification {len(tools)} profiles")
    for index, m in enumerate(headings):
        identifier = int(m.group("id"), 16)
        tool = by_id.get(identifier)
        if tool is None:
            problems.append(f"section {m.group('number')} is for ID 0x{identifier:02X}, which the specification does not have")
            continue
        if int(m.group("number")) != identifier + 1 or index != identifier:
            problems.append(f"section {m.group('number')} ({m.group('name')}) is out of order for ID 0x{identifier:02X}")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        expansion = EXPANSION.search(text, m.end(), end)
        said = expansion.group("word").lower() if expansion else "none"
        wanted = tool.get("expansion_board", "none")
        if said != wanted:
            problems.append(f"ID 0x{identifier:02X} ({tool['display_name']}): the text says the expansion board is {said}, the specification says {wanted}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="write nothing; fail when the table or the prose disagrees with the specification")
    parser.add_argument("--file", type=Path, default=None, help=f"the document to update (default: {TARGET} next to this repository)")
    args = parser.parse_args(argv)
    path = args.file or target_path()
    if not path.exists():
        print(f"{path} not found (set URTC_WORKSPACE or pass --file)", file=sys.stderr)
        return 2
    text, newline = canbus.read(path)
    tools = load_tools()
    problems = prose_problems(text, tools)
    merged = merge(text, block(tools))
    if args.check:
        if merged != text:
            problems.append("the tool table is not what the specification produces: run tools/generate_tools_doc.py")
        if problems:
            print("TOOLS_DOC=FAIL " + "; ".join(problems), file=sys.stderr)
            return 1
        print(f"TOOLS_DOC=PASS tools={len(tools)}")
        return 0
    if problems:
        print("the prose disagrees with the specification (the table is written anyway): " + "; ".join(problems), file=sys.stderr)
    if merged != text:
        path.write_bytes(merged.replace("\n", newline).encode("utf-8"))
        print(f"updated {path}")
    else:
        print("already current")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
