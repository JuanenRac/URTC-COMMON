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
IMAGES = ROOT / "spec" / "firmware_images.json"
IMAGES_BANNER = "GENERATED from spec/firmware_images.json by tools/generate_tools.py - do not edit by hand."
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


def _c_ids(doc: dict, protocol: dict) -> str:
    """The identifiers of the tool profiles as C macros: the numbering the tool head, the rack and the vision tool share."""
    invalid = [t for t in protocol["tools"] if t["id"] >= len(doc["tools"])]
    lines = [
        f"/* {BANNER}", " * Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>", " * GPL-3.0-or-later - see LICENSE", " *",
        " * The five-bit tool identifier of a tool head (its ID jumpers, or the byte stored in its F-RAM): 0 .. URTC_TOOL_ID_LAST are tool profiles, the values",
        " * after them up to 30 are not assigned to any tool, and 31 means a free configuration (the tool is chosen by a value stored in the head).", " */",
        "#ifndef URTC_TOOL_IDS_H", "#define URTC_TOOL_IDS_H", "",
    ]
    for t in doc["tools"]:
        lines.append(f"#define URTC_TOOL_ID_{t['name']} {t['id']}u")
    last = doc["tools"][-1]["id"]
    lines += ["", f"#define URTC_TOOL_ID_COUNT {len(doc['tools'])}u", f"#define URTC_TOOL_ID_LAST {last}u",
              f"#define URTC_TOOL_ID_FIRST_INVALID {invalid[0]['id'] if invalid else last + 1}u", "#define URTC_TOOL_ID_FREE_CONFIG 31u", "#define URTC_TOOL_ID_MASK 0x1Fu", "", "#endif /* URTC_TOOL_IDS_H */", ""]
    return "\n".join(lines)

def load_images() -> dict:
    return json.loads(IMAGES.read_text(encoding="utf-8"))


def validate_images(doc: dict) -> list[str]:
    problems: list[str] = []
    for key in ("prefix", "boards", "kinds", "version", "image_extension", "sidecar_suffixes"):
        if key not in doc:
            problems.append(f"firmware_images.json has no {key}")
    if problems:
        return problems
    if not all(isinstance(name, str) and name.isupper() and name.isalpha() for name in doc["boards"] + doc["kinds"] + [doc["prefix"]]):
        problems.append("the prefix, the boards and the kinds are capital letters")
    if not doc["image_extension"].startswith(".") or any(not suffix.startswith(".") for suffix in doc["sidecar_suffixes"]):
        problems.append("an extension or a suffix starts with a dot")
    if len(set(doc["sidecar_suffixes"])) != len(doc["sidecar_suffixes"]):
        problems.append("a suffix is listed twice")
    return problems


def _image_regex(doc: dict) -> str:
    return f"^{doc['prefix']}_({'|'.join(doc['boards'])})_({'|'.join(doc['kinds'])})_v({doc['version']})" + doc["image_extension"].replace(".", "\\.") + "$"


def _images_py(doc: dict) -> str:
    return (
        '"""' + IMAGES_BANNER + "\n\nHow the files of a firmware release are named (standard library only).\n"
        "Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        'GPL-3.0-or-later - see LICENSE\n"""\n'
        "from __future__ import annotations\n\nimport re\n\n"
        f"PREFIX = {doc['prefix']!r}\nBOARDS = {tuple(doc['boards'])!r}\nKINDS = {tuple(doc['kinds'])!r}\n"
        f"IMAGE_EXTENSION = {doc['image_extension']!r}\nSIDECAR_SUFFIXES = {tuple(doc['sidecar_suffixes'])!r}\n"
        f"IMAGE_NAME = re.compile({_image_regex(doc)!r}, re.IGNORECASE)\n\n\n"
        "def image_name(board: str, kind: str, version: str) -> str:\n"
        '    """``URTC_MAIN_FIRMWARE_v0.4.1.bin`` from its parts; a board or kind that is not listed is refused."""\n'
        "    if board.upper() not in BOARDS or kind.upper() not in KINDS or not re.fullmatch(r\"" + doc["version"] + "\", version):\n"
        '        raise ValueError(f"not a firmware image: {board!r} {kind!r} {version!r}")\n'
        '    return f"{PREFIX}_{board.upper()}_{kind.upper()}_v{version}{IMAGE_EXTENSION}"\n\n\n'
        "def parse_image_name(name: str) -> tuple[str, str, str] | None:\n"
        '    """``(board, kind, version)`` of an image file name, or None when it is not one (a sidecar is not an image)."""\n'
        "    match = IMAGE_NAME.fullmatch(name)\n"
        "    return (match.group(1).upper(), match.group(2).upper(), match.group(3)) if match else None\n\n\n"
        "def sidecar_names(image: str) -> tuple[str, ...]:\n"
        '    """The files that travel with an image: its name plus each suffix."""\n'
        "    return tuple(image + suffix for suffix in SIDECAR_SUFFIXES)\n\n\n"
        "def is_sidecar(name: str) -> bool:\n"
        "    return name.endswith(SIDECAR_SUFFIXES)\n"
    )


def _images_ts(doc: dict) -> str:
    regex = _image_regex(doc).replace("/", "\\/")
    return (
        f"// {IMAGES_BANNER}\n"
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        "// GPL-3.0-or-later - see LICENSE\n\n"
        f"export const FIRMWARE_PREFIX = {json.dumps(doc['prefix'])};\n"
        f"export const FIRMWARE_BOARDS = {json.dumps(doc['boards'])} as const;\n"
        f"export const FIRMWARE_KINDS = {json.dumps(doc['kinds'])} as const;\n"
        f"export const FIRMWARE_IMAGE_EXTENSION = {json.dumps(doc['image_extension'])};\n"
        f"export const FIRMWARE_SIDECAR_SUFFIXES = {json.dumps(doc['sidecar_suffixes'])} as const;\n"
        f"export const FIRMWARE_IMAGE_NAME = /{regex}/i;\n\n"
        "export interface FirmwareImageName { board: (typeof FIRMWARE_BOARDS)[number]; kind: (typeof FIRMWARE_KINDS)[number]; version: string }\n\n"
        "/** The parts of an image file name, or null when the name is not an image (a sidecar is not an image). */\n"
        "export function parseFirmwareImageName(name: string): FirmwareImageName | null {\n"
        "  const m = FIRMWARE_IMAGE_NAME.exec(name);\n"
        "  return m ? { board: m[1].toUpperCase() as FirmwareImageName['board'], kind: m[2].toUpperCase() as FirmwareImageName['kind'], version: m[3] } : null;\n"
        "}\n\n"
        "/** The name of the file that travels with an image, for one suffix of FIRMWARE_SIDECAR_SUFFIXES. */\n"
        "export function firmwareSidecarName(image: string, suffix: (typeof FIRMWARE_SIDECAR_SUFFIXES)[number]): string {\n"
        "  return image + suffix;\n"
        "}\n"
    )

def outputs(doc: dict) -> dict[Path, str]:
    return {
        ROOT / "generated" / "urtcTools.ts": _ts(doc),
        ROOT / "src" / "urtc_common" / "tools_catalog.py": _py(doc),
        ROOT / "docs" / "TOOLS_TABLE.md": _md(doc),
        ROOT / "generated" / "urtc_tool_ids.h": _c_ids(doc, json.loads(PROTOCOL.read_text(encoding="utf-8"))),
        ROOT / "src" / "urtc_common" / "firmware_names.py": _images_py(load_images()),
        ROOT / "generated" / "firmwareNames.ts": _images_ts(load_images()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="write nothing; fail when a generated file is out of date")
    args = parser.parse_args(argv)
    doc = load()
    problems = validate(doc, json.loads(PROTOCOL.read_text(encoding="utf-8"))) + validate_images(load_images())
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
