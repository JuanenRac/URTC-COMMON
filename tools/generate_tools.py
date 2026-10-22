#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/generate_tools.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the tool tables of the programs, the web studio and the documents from spec/tools.json.

The tool profiles (identifier, limits, watchdog, pins, features, expansion board needed) are written down once, in
``spec/tools.json``. This tool turns them into:

* ``generated/urtcTools.ts``           TypeScript: the profiles the web studio lists in its tool catalog and the head picker
* ``src/urtc_common/tools_catalog.py`` Python: the same for the tester (names, kinds, limits), standard library only
* ``docs/TOOLS_TABLE.md``              the table the READMEs and the documents quote

``--check`` writes nothing and fails when a file differs from what the specification produces, and when a tool is
missing from (or is not in the same order as) the ``tools`` of the protocol specification.

Usage:
    python tools/generate_tools.py           # write the files
    python tools/generate_tools.py --check   # verify they are current
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "tools.json"
PROTOCOL = ROOT / "spec" / "can_protocol.json"
BANNER = "GENERATED from spec/tools.json by tools/generate_tools.py - do not edit by hand."
KINDS = ("motion", "telemetry", "external", "actuator")
EXPANSION = ("none", "recommended", "required")


def load() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def validate(doc: dict, protocol: dict) -> list[str]:
    """Problems found in the tool file; an empty list means it is consistent with the protocol specification."""
    problems: list[str] = []
    real = [t for t in protocol["tools"] if t["id"] < 25]
    tools = doc["tools"]
    if [t["id"] for t in tools] != [t["id"] for t in real]:
        problems.append("the identifiers differ from the tools of spec/can_protocol.json")
    for tool, ref in zip(tools, real):
        if tool["name"] != ref["name"] or tool["title"] != ref["title"]:
            problems.append(f"tool {tool['id']}: name or title differs from the protocol specification")
        if tool["kind"] not in KINDS:
            problems.append(f"tool {tool['id']}: unknown kind {tool['kind']!r}")
        if tool["expansion_board"] not in EXPANSION:
            problems.append(f"tool {tool['id']}: unknown expansion_board {tool['expansion_board']!r}")
        lim = tool["limits"]
        if not lim["min"] <= lim["default"] <= lim["max"]:
            problems.append(f"tool {tool['id']}: default outside the limits")
        if len(tool["icon_frames"]) != 4:
            problems.append(f"tool {tool['id']}: an animation has four frames")
    return problems


def _ts(doc: dict) -> str:
    profiles = []
    for t in doc["tools"]:
        p = {
            "id": t["id"], "name": t["display_name"], "category": t["category"], "description": t["description"],
            "heroMetricLabel": t["hero_metric"]["label"], "heroMetricUnit": t["hero_metric"]["unit"],
            "defaultSetpoint": t["limits"]["default"], "minVal": t["limits"]["min"], "maxVal": t["limits"]["max"],
        }
        if "watchdog_ms" in t:
            p["watchdogMs"] = t["watchdog_ms"]
        p.update({"pinsUsed": t["pins_used"], "features": t["features"], "iconFrames": t["icon_frames"],
                  "kind": t["kind"], "shortName": t["short_name"], "expansionBoard": t["expansion_board"]})
        profiles.append(p)
    body = json.dumps(profiles, indent=2, ensure_ascii=False)
    return (
        f"// {BANNER}\n"
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        "// GPL-3.0-or-later - see LICENSE\n\n"
        "export type UrtcToolKind = 'motion' | 'telemetry' | 'external' | 'actuator';\n"
        "export type UrtcExpansionNeed = 'none' | 'recommended' | 'required';\n\n"
        "export interface UrtcToolProfile {\n"
        "  id: number;\n  name: string;\n  category: 'Shipped (v0.0)' | 'Expansion (v0.1)';\n  description: string;\n"
        "  heroMetricLabel: string;\n  heroMetricUnit: string;\n  defaultSetpoint: number;\n  minVal: number;\n  maxVal: number;\n"
        "  watchdogMs?: number;\n  pinsUsed: string[];\n  features: string[];\n  iconFrames: string[];\n"
        "  kind: UrtcToolKind;\n  shortName: string;\n  expansionBoard: UrtcExpansionNeed;\n}\n\n"
        f"export const URTC_TOOL_PROFILES: UrtcToolProfile[] = {body};\n"
    )


def _py(doc: dict) -> str:
    rows = []
    for t in doc["tools"]:
        rows.append({
            "id": t["id"], "name": t["name"], "title": t["title"], "display_name": t["display_name"],
            "short_name": t["short_name"], "kind": t["kind"], "category": t["category"],
            "minimum": t["limits"]["min"], "default": t["limits"]["default"], "maximum": t["limits"]["max"],
            "unit": t["hero_metric"]["unit"], "metric": t["hero_metric"]["label"],
            "watchdog_ms": t.get("watchdog_ms"), "expansion_board": t["expansion_board"],
            "features": t["features"],
        })
    body = json.dumps(rows, indent=4, ensure_ascii=False)
    body = body.replace(": null", ": None")
    return (
        '"""' + BANNER + "\n\nThe tool profiles of the tool head as data (standard library only).\n"
        "Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        'GPL-3.0-or-later - see LICENSE\n"""\n'
        "from __future__ import annotations\n\n"
        f"TOOLS: tuple[dict, ...] = tuple({body})\n\n"
        'TOOL_NAMES: dict[int, str] = {tool["id"]: tool["short_name"] for tool in TOOLS}\n'
        'TOOL_KINDS: dict[int, str] = {tool["id"]: tool["kind"] for tool in TOOLS}\n\n\n'
        "def tool_by_id(tool_id: int) -> dict | None:\n"
        '    """The profile of a tool identifier, or None for an identifier that is no tool."""\n'
        "    for tool in TOOLS:\n"
        '        if tool["id"] == tool_id:\n'
        "            return tool\n"
        "    return None\n"
    )


def _md(doc: dict) -> str:
    lines = [
        f"<!-- {BANNER} -->", "",
        "# Tool table", "",
        "| ID | Tool | Kind | Range (default) | Watchdog | Expansion board |",
        "|---:|---|---|---|---:|---|",
    ]
    for t in doc["tools"]:
        lim = t["limits"]
        unit = t["hero_metric"]["unit"]
        wd = f"{t['watchdog_ms']} ms" if "watchdog_ms" in t else "-"
        lines.append(f"| {t['id']} (0x{t['id']:02X}) | {t['display_name']} | {t['kind']} | {lim['min']} to {lim['max']} {unit} ({lim['default']}) | {wd} | {t['expansion_board']} |")
    return "\n".join(lines) + "\n"


def outputs(doc: dict) -> dict[Path, str]:
    return {
        ROOT / "generated" / "urtcTools.ts": _ts(doc),
        ROOT / "src" / "urtc_common" / "tools_catalog.py": _py(doc),
        ROOT / "docs" / "TOOLS_TABLE.md": _md(doc),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="write nothing; fail when a generated file is out of date")
    args = parser.parse_args(argv)
    doc = load()
    problems = validate(doc, json.loads(PROTOCOL.read_text(encoding="utf-8")))
    if problems:
        print("TOOLS=FAIL " + "; ".join(problems), file=sys.stderr)
        return 1
    stale = []
    for path, text in outputs(doc).items():
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if args.check:
            if current != text:
                stale.append(path.relative_to(ROOT).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if current != text:
            path.write_bytes(text.encode("utf-8"))
            print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if args.check:
        if stale:
            print("TOOLS=FAIL out of date: " + ", ".join(stale) + " (run python tools/generate_tools.py)", file=sys.stderr)
            return 1
        print("TOOLS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
