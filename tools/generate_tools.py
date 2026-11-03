#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/generate_tools.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the tool tables of the programs, the web studio and the documents from spec/tools.json.

The tool profiles (identifier, limits, watchdog, pins, features, expansion board needed) are written down once, in
``spec/tools.json``. This tool turns them into:

* ``generated/urtcTools.ts``           TypeScript: the profiles the web studio lists in its tool catalog and the head picker, with
                                       the ``panel`` of each tool (its controls, readings and commands) that the studio draws
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
# The frame encoders a panel may name (lib/toolFrames.ts of the web studio) and how many controls each one takes.
ENCODERS = {
    "drillCommand": 2, "drillStop": 0, "aoiRingCommand": 2, "laserCommand": 2, "laserOff": 0, "powerByte": 1, "powerOff": 0,
    "electromagnetCommand": 0, "hotAirCommand": 2, "hotAirOff": 0, "motionMove": 2, "motionStop": 1, "weldFire": 1,
    "pasteJettingConfig": 2, "pasteJettingPulse": 3,
}
CONTROL_TYPES = ("range", "number", "select", "checkbox")
ACTION_TYPES = ("keepalive", "send", "stop", "latched")
CONFIRM_KINDS = ("drill", "laser", "uv", "weld", "heater", "motion", "paste")


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


def _text_ok(text: object, what: str, problems: list[str]) -> None:
    """A label is either ``{"key", "default"}`` (an existing translated text) or ``{"text"}`` (one that is not translated)."""
    if not isinstance(text, dict) or not (("key" in text and "default" in text) or "text" in text):
        problems.append(f"{what}: a text needs key and default, or text")


def resolve_panel(tools: list[dict], tool: dict) -> dict | None:
    """The panel of a tool; ``same_as`` borrows the panel of another tool."""
    panel = tool.get("panel")
    if panel and "same_as" in panel:
        other = next((t for t in tools if t["id"] == panel["same_as"]), None)
        return other.get("panel") if other and "same_as" not in other.get("panel", {}) else None
    return panel


def validate_panels(doc: dict, protocol: dict) -> list[str]:
    """Problems found in the ``panel`` of the tools (the controls, the readings and the commands of each tool panel)."""
    problems: list[str] = []
    messages = {m["name"] for m in protocol["messages"]}
    for tool in doc["tools"]:
        if "panel" not in tool:
            continue
        where = f"tool {tool['id']} panel"
        panel = resolve_panel(doc["tools"], tool)
        if panel is None:
            problems.append(f"{where}: same_as does not name a tool with a panel of its own")
            continue
        if "same_as" in tool["panel"] and set(tool["panel"]) != {"same_as"}:
            problems.append(f"{where}: same_as stands alone")
        controls: dict[str, dict] = {}  # the controls are shared by the sections of a panel: a pulse uses the channel set above it
        for index, section in enumerate(panel.get("sections", [])):
            at = f"{where} section {index}"
            _text_ok(section.get("title"), f"{at} title", problems)
            for optional in ("subtitle", "notice"):
                if optional in section:
                    _text_ok(section[optional], f"{at} {optional}", problems)
            for control in section.get("controls", []):
                cid = control.get("id")
                if not cid or cid in controls:
                    problems.append(f"{at}: control without a unique id ({cid!r})")
                    continue
                controls[cid] = control
                if control.get("type") not in CONTROL_TYPES:
                    problems.append(f"{at}: control {cid} has an unknown type {control.get('type')!r}")
                _text_ok(control.get("label"), f"{at} control {cid} label", problems)
                if control.get("type") in ("range", "number"):
                    low, high, default = control.get("min"), control.get("max"), control.get("default")
                    if not all(isinstance(v, (int, float)) for v in (low, high, default)) or not low <= default <= high:
                        problems.append(f"{at}: control {cid} needs min <= default <= max")
                if control.get("type") == "select":
                    values = [o.get("value") for o in control.get("options", [])]
                    if not values or control.get("default") not in values or len(set(values)) != len(values):
                        problems.append(f"{at}: control {cid} needs options and a default among them")
                    for option in control.get("options", []):
                        _text_ok(option.get("label"), f"{at} control {cid} option", problems)
                if control.get("type") == "checkbox" and not isinstance(control.get("default"), bool):
                    problems.append(f"{at}: control {cid} needs a true or false default")
            for reading in section.get("telemetry", []):
                if reading.get("message") not in messages:
                    problems.append(f"{at}: telemetry {reading.get('id')} names a message that is not in the protocol")
                if reading.get("width") not in (1, 2) or not isinstance(reading.get("offset"), int) or reading["offset"] < 0:
                    problems.append(f"{at}: telemetry {reading.get('id')} needs an offset and a width of 1 or 2")
                _text_ok(reading.get("label"), f"{at} telemetry label", problems)
            actions = section.get("actions", [])
            if not controls and not section.get("telemetry") and not actions:
                problems.append(f"{at}: nothing to show")
            for action in actions:
                kind = action.get("type")
                if kind not in ACTION_TYPES:
                    problems.append(f"{at}: unknown action type {kind!r}")
                    continue
                if action.get("message") not in messages:
                    problems.append(f"{at}: an action names a message that is not in the protocol ({action.get('message')!r})")
                names = [action.get("encoder")] + ([action["off_encoder"]] if "off_encoder" in action else [])
                for name in names:
                    if name not in ENCODERS:
                        problems.append(f"{at}: unknown encoder {name!r}")
                if action.get("encoder") in ENCODERS and len(action.get("args", [])) != ENCODERS[action["encoder"]]:
                    problems.append(f"{at}: encoder {action['encoder']} takes {ENCODERS[action['encoder']]} arguments")
                for arg in action.get("args", []) + action.get("reset", []):
                    if arg not in controls:
                        problems.append(f"{at}: an action uses control {arg!r}, which this panel does not have")
                if "confirm" in action and action["confirm"] not in CONFIRM_KINDS:
                    problems.append(f"{at}: unknown confirmation kind {action['confirm']!r}")
                if "confirm_value" in action and action["confirm_value"] not in controls:
                    problems.append(f"{at}: confirm_value is not a control of the panel")
                if kind == "keepalive" and ("off_encoder" not in action or not isinstance(action.get("watchdog_ms"), int)):
                    problems.append(f"{at}: a keepalive needs off_encoder and watchdog_ms")
                if kind in ("send", "stop", "latched"):
                    _text_ok(action.get("label"), f"{at} action label", problems)
    return problems


def _panels(doc: dict, protocol: dict) -> dict[int, dict]:
    """The panels with the identifier of each message beside its name, as the web studio receives them."""
    ids = {m["name"]: int(m["id"], 16) for m in protocol["messages"]}

    def walk(node):
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                out[key] = walk(value)
                if key == "message":
                    out["canId"] = ids[value]
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return {t["id"]: walk(resolve_panel(doc["tools"], t)) for t in doc["tools"] if "panel" in t}


_PANEL_TYPES = """/** A text of a panel: an existing translated text (key and its English default), or a plain one that is not translated. */
export type UrtcPanelText = { key: string; default: string; param?: string } | { text: string };

export type UrtcPanelControl =
  | { id: string; type: 'range' | 'number'; label: UrtcPanelText; min: number; max: number; default: number }
  | { id: string; type: 'select'; label: UrtcPanelText; default: string | number; options: { value: string | number; label: UrtcPanelText }[] }
  | { id: string; type: 'checkbox'; label: UrtcPanelText; default: boolean };

export interface UrtcPanelReading {
  id: string; label: UrtcPanelText; message: string; canId: number; offset: number; width: 1 | 2;
  format?: 'yes_no'; unit?: string; graph_max?: number;
}

export interface UrtcPanelAction {
  type: 'keepalive' | 'send' | 'stop' | 'latched';
  message: string; canId: number; encoder: string; args?: string[]; description?: string;
  label?: UrtcPanelText; confirm?: string; confirm_value?: string;
  off_encoder?: string; off_description?: string; watchdog_ms?: number; reset?: string[];
  description_on?: string; description_off?: string;
}

export interface UrtcPanelSection {
  title: UrtcPanelText; subtitle?: UrtcPanelText; notice?: UrtcPanelText;
  controls?: UrtcPanelControl[]; telemetry?: UrtcPanelReading[]; actions?: UrtcPanelAction[];
}

export interface UrtcToolPanel { sections: UrtcPanelSection[] }

"""


def _ts(doc: dict, protocol: dict) -> str:
    panels = _panels(doc, protocol)
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
        if t["id"] in panels:
            p["panel"] = panels[t["id"]]
        profiles.append(p)
    body = json.dumps(profiles, indent=2, ensure_ascii=False)
    return (
        f"// {BANNER}\n"
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        "// GPL-3.0-or-later - see LICENSE\n\n"
        "export type UrtcToolKind = 'motion' | 'telemetry' | 'external' | 'actuator';\n"
        "export type UrtcExpansionNeed = 'none' | 'recommended' | 'required';\n\n"
        + _PANEL_TYPES +
        "export interface UrtcToolProfile {\n"
        "  id: number;\n  name: string;\n  category: 'Shipped (v0.0)' | 'Expansion (v0.1)';\n  description: string;\n"
        "  heroMetricLabel: string;\n  heroMetricUnit: string;\n  defaultSetpoint: number;\n  minVal: number;\n  maxVal: number;\n"
        "  watchdogMs?: number;\n  pinsUsed: string[];\n  features: string[];\n  iconFrames: string[];\n"
        "  kind: UrtcToolKind;\n  shortName: string;\n  expansionBoard: UrtcExpansionNeed;\n  panel?: UrtcToolPanel;\n}\n\n"
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
        ROOT / "generated" / "urtcTools.ts": _ts(doc, json.loads(PROTOCOL.read_text(encoding="utf-8"))),
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
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    problems = validate(doc, protocol) + validate_panels(doc, protocol) + validate_images(load_images())
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
