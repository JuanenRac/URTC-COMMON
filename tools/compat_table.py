#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/compat_table.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The compatibility table of a release (protocol, firmware, programs) made from spec/versions.json.

``spec/versions.json`` records which version of every project of the family was current, which version of the protocol it
speaks and which copy of this repository's shared code it carries. The table that goes into the body of a release and into
``docs/COMPATIBILITY.md`` is generated from it, so it is never typed by hand.

    python tools/compat_table.py --refresh      # read the manifests of the repositories next to this one into spec/versions.json
    python tools/compat_table.py --write        # write docs/COMPATIBILITY.md
    python tools/compat_table.py --check        # fail when the file is out of date, or the protocol version differs from the spec
    python tools/compat_table.py --check --siblings   # also fail when spec/versions.json lags behind the repositories next to this one
    python tools/compat_table.py --markdown     # print the table (for a release body)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "spec" / "versions.json"
PROTOCOL = ROOT / "spec" / "can_protocol.json"
OUT = ROOT / "docs" / "COMPATIBILITY.md"
BANNER = "GENERATED from spec/versions.json by tools/compat_table.py - do not edit by hand."
REPOS = (
    ("URTC", "Tool head firmware", "firmware"), ("URTC-FLASHER", "Flasher", "program"), ("URTC-GATEWAY", "Gateway in front of the bus", "program"), ("URTC-TESTER", "Tester", "program"),
    ("URTC-WEB-STUDIO", "Web studio", "program"), ("URTC-UPDATER", "Updater", "program"), ("URTC-SMART-RACK", "Smart rack", "firmware"),
    ("URTC-VISION-TOOL", "Vision tool", "firmware"), ("URTC-DOCS", "Documentation generator", "program"), ("URTC-COMMON", "Shared protocol and code", "library"),
)


def load() -> dict:
    return json.loads(VERSIONS.read_text(encoding="utf-8"))


def common_version_of(repo_dir: Path) -> str | None:
    """The version of URTC-COMMON a repository carries, from its lock file (the first one found)."""
    for lock in sorted(repo_dir.rglob("urtc_common.lock.json")):
        if any(part in {"node_modules", ".venv", "build", "dist"} for part in lock.parts):
            continue
        try:
            return json.loads(lock.read_text(encoding="utf-8")).get("urtc_common_version")
        except (OSError, ValueError):
            return None
    return None


def refresh(base: Path) -> dict:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))["protocol_version"]
    projects = []
    for repo, title, kind in REPOS:
        manifest = base / repo / "urtc.project.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        entry = {"repo": repo, "title": title, "kind": kind, "version": data["version"]}
        comps = data.get("components") or []
        if comps:
            entry["components"] = [{"name": c["name"], "version": c["version"]} for c in comps]
        carried = data["version"] if repo == "URTC-COMMON" else common_version_of(base / repo)
        if carried:
            entry["common"] = carried
        projects.append(entry)
    return {"format": 1, "protocol_version": protocol, "projects": projects}


def render(doc: dict) -> str:
    lines = [f"<!-- {BANNER} -->", "", "## Compatibility", "",
             f"Protocol version **{doc['protocol_version']}** (identifiers, layouts and magic payloads of `spec/can_protocol.json`).", "",
             "| Project | Kind | Version | Shared code |", "|---|---|---|---|"]
    for p in doc["projects"]:
        version = p["version"]
        if p.get("components"):
            version += " (" + ", ".join(f"{c['name'].replace('URTC_', '').replace('_', ' ').lower()} {c['version']}" for c in p["components"]) + ")"
        lines.append(f"| {p['title']} (`{p['repo']}`) | {p['kind']} | {version} | {p.get('common', '-')} |")
    lines += ["", "Every project listed speaks the protocol version above; \"Shared code\" is the version of URTC-COMMON the project carries a checked copy of.", ""]
    return "\n".join(lines)


def check(doc: dict, siblings: Path | None) -> list[str]:
    problems = []
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))["protocol_version"]
    if doc["protocol_version"] != protocol:
        problems.append(f"protocol_version is {doc['protocol_version']} but the specification says {protocol}")
    if not OUT.is_file() or OUT.read_bytes().decode("utf-8") != render(doc):
        problems.append("docs/COMPATIBILITY.md is out of date (run python tools/compat_table.py --write)")
    if siblings is not None:
        live = {p["repo"]: p for p in refresh(siblings)["projects"]}
        for p in doc["projects"]:
            if p["repo"] in live and live[p["repo"]] != p:
                problems.append(f"{p['repo']}: spec/versions.json says {p['version']}, the repository says {live[p['repo']]['version']} (run --refresh)")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--siblings", action="store_true", help="with --check: compare with the repositories next to this one")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    if args.refresh:
        doc = refresh(ROOT.parent)
        VERSIONS.write_bytes((json.dumps(doc, indent=2) + "\n").encode("utf-8"))
        print("wrote spec/versions.json")
    doc = load()
    if args.write or args.refresh:
        OUT.write_bytes(render(doc).encode("utf-8"))
        print("wrote docs/COMPATIBILITY.md")
    if args.markdown:
        sys.stdout.write(render(doc))
    if args.check:
        problems = check(doc, ROOT.parent if args.siblings else None)
        if problems:
            print("COMPAT=FAIL " + "; ".join(problems), file=sys.stderr)
            return 1
        print("COMPAT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
