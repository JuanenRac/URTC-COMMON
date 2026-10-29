#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/readme_sections.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The sections that several README files carry, written once in the eight languages (``spec/readme/sections.json``) and kept equal.

    python tools/readme_sections.py list
    python tools/readme_sections.py check [--base FOLDER]          # every listed repository next to this one: the sections are there and equal
    python tools/readme_sections.py apply URTC-FLASHER [--base FOLDER]   # write them in the eight README files of one repository

Each section sits between two marker comments, ``<!-- urtc-section:ID -->`` and ``<!-- /urtc-section:ID -->``, in its place in the universal layout of the
README: Project status right after At a glance, and the parts that belong to Architecture, Features or Quick start at the end of that section, as a level-three
heading. A README that does not have that section yet gets the block immediately before the heading of the license (the first ``## 📜``), as before. The
order is that of the specification. Everything outside the markers is left as it is, so the rest
of a README stays hand-written; a section that moved or was edited by hand is put back by ``apply`` and reported by ``check``. All eight languages
get the same sections with the same emoji, which is what the parity check of the README files compares. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "readme" / "sections.json"
FILES = {
    "english": "README.md", "spanish": "README_spa.md", "german": "README_deu.md", "french": "README_fra.md",
    "italian": "README_ita.md", "japanese": "README_jpn.md", "chinese": "README_zho.md", "portuguese": "README_por.md",
}
LICENSE_HEADING = "## 📜"


def load(path: Path = SPEC) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(spec: dict) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for section in spec.get("sections", []):
        name = section.get("id", "?")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in seen:
            problems.append(f"{name}: not a unique identifier")
        seen.add(name)
        for key in ("heading", "body"):
            if sorted(section.get(key, {})) != sorted(FILES):
                problems.append(f"{name}: {key} needs exactly the eight languages")
            elif any(not str(value).strip() for value in section[key].values()):
                problems.append(f"{name}: an empty {key}")
        if not section.get("emoji") or not section.get("repos"):
            problems.append(f"{name}: needs an emoji and the repositories that carry it")
        if any(token in str(section.get("body")) for token in ("SON" + "NET", "au" + "dit", "Cla" + "ude")) or "odo" + "meter" in str(section.get("body")).lower():
            problems.append(f"{name}: a reference that does not belong in a public README")
        place = section.get("universal")
        if place is not None:
            anchor = place.get("after") or place.get("in")
            if ("after" in place) == ("in" in place) or anchor not in UNIVERSAL_ICONS:
                problems.append(f"{name}: a universal place is 'after' or 'in' one of {', '.join(UNIVERSAL_ICONS)}")
            if "in" in place and sorted(place.get("heading", {})) != sorted(FILES):
                problems.append(f"{name}: the universal heading needs exactly the eight languages")
    return problems


# The universal layout of the README (22 sections in a fixed order): the icon that identifies each section a shared block can be placed in.
UNIVERSAL_ICONS = {"glance": "📋", "architecture": "🏛", "features": "✨", "quickstart": "🚀"}
HEADING_LINE = re.compile(r"^## (?:\d+\.\s+)?(\S+)\s+(.*)$")
# the name of those sections in the eight languages: an old README can use the same icon for something else (a roadmap with the rocket), so the name must match too
UNIVERSAL_NAMES = {
    "glance": {"At a glance", "De un vistazo", "En un coup d'œil", "In breve", "Auf einen Blick", "速览", "ひと目で", "Num relance"},
    "architecture": {"Architecture", "Arquitectura", "Architettura", "Architektur", "架构", "アーキテクチャ", "Arquitetura"},
    "features": {"Features", "Funciones", "Fonctionnalités", "Funzionalità", "Funktionen", "功能", "機能", "Funcionalidades"},
    "quickstart": {"Quick start", "Inicio rápido", "Démarrage rapide", "Avvio rapido", "Schnellstart", "快速开始", "クイックスタート", "Início rápido"},
}


def block(section: dict, language: str, newline: str, level: int = 2) -> str:
    """A shared section between its two markers: a level-two heading with its emoji, or (inside a universal section) a level-three heading without one."""
    identifier = section["id"]
    if level == 3:
        heading = f"### {section['universal']['heading'][language]}"
    else:
        heading = f"## {section['emoji']} {section['heading'][language]}"
    lines = [f"<!-- urtc-section:{identifier} -->", heading, "", *section["body"][language].split("\n"), f"<!-- /urtc-section:{identifier} -->"]
    return newline.join(lines)


_BLOCK = re.compile(r"<!-- urtc-section:([a-z0-9_]+) -->.*?<!-- /urtc-section:\1 -->(?:\r?\n){1,2}", re.S)


def section_end(text: str, newline: str, anchor: str) -> int | None:
    """Where the level-two section of the universal layout called `anchor` ends (the start of the next level-two heading, code blocks left alone), or None when the README has no such section."""
    icon = UNIVERSAL_ICONS[anchor]
    position, fence, start = 0, False, None
    for line in text.split(newline):
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and line.startswith("## "):
            if start is not None:
                return position
            found = HEADING_LINE.match(line)
            if found and found.group(1).replace("️", "") == icon and found.group(2).strip() in UNIVERSAL_NAMES[anchor]:
                start = position
        position += len(line) + len(newline)
    return len(text) if start is not None else None


def insert_at(text: str, position: int, block_text: str, newline: str) -> str:
    before = text[:position]
    gap = "" if before.endswith(newline + newline) or not before else newline
    return before + gap + block_text + newline + newline + text[position:]


def anchors_of(text: str) -> set[str]:
    """The universal sections that this README (normally the English one) has, so that all eight languages of a repository place their blocks the same way."""
    newline = "\r\n" if "\r\n" in text else "\n"
    cleaned = _BLOCK.sub("", text)
    return {anchor for anchor in UNIVERSAL_ICONS if section_end(cleaned, newline, anchor) is not None}


def render(text: str, sections: list[dict], language: str, anchors: set[str] | None = None) -> str:
    """The README text with the shared sections written in their place (and no older copy of them left).

    A section that has a ``universal`` place goes there when the README has the section that place names: ``{"after": "glance"}`` is the end of At a glance (Project status is
    always the second section) and ``{"in": "quickstart", "heading": {...}}`` is a level-three part at the end of that section. A README that does not have that section yet
    (it is not in the universal layout) keeps the block, as a level-two section, just before the license heading, as before."""
    newline = "\r\n" if "\r\n" in text else "\n"
    cleaned = _BLOCK.sub("", text)
    if cleaned.find(newline + LICENSE_HEADING) < 0:
        raise ValueError("the README has no license heading (## 📜)")
    if anchors is None:
        anchors = anchors_of(cleaned)
    legacy: list[dict] = []
    placed: list[tuple[dict, int]] = []
    for section in sections:
        place = section.get("universal")
        anchor = (place.get("after") or place.get("in")) if place else None
        if anchor and anchor in anchors:
            if section_end(cleaned, newline, anchor) is None:
                raise ValueError(f"the README has no {anchor} section in the universal layout, and the English one has")
            placed.append((section, 3 if "in" in place else 2))
        else:
            legacy.append(section)
    for section, level in placed:
        place = section["universal"]
        end = section_end(cleaned, newline, place.get("after") or place["in"])
        cleaned = insert_at(cleaned, end, block(section, language, newline, level), newline)
    if legacy:
        position = cleaned.find(newline + LICENSE_HEADING) + len(newline)
        blocks = (newline + newline).join(block(section, language, newline) for section in legacy)
        cleaned = cleaned[:position] + blocks + newline + newline + cleaned[position:]
    return cleaned


def sections_of(spec: dict, repo: str) -> list[dict]:
    return [section for section in spec["sections"] if repo in section["repos"]]


def repos_of(spec: dict) -> list[str]:
    return sorted({repo for section in spec["sections"] for repo in section["repos"]})


def differences(spec: dict, base: Path) -> tuple[list[str], list[str]]:
    """(files whose sections are missing or differ, repositories not found next to this one)."""
    found: list[str] = []
    missing: list[str] = []
    for repo in repos_of(spec):
        folder = base / repo
        if not folder.is_dir():
            missing.append(repo)
            continue
        wanted = sections_of(spec, repo)
        english = folder / FILES["english"]
        anchors = anchors_of(english.read_bytes().decode("utf-8")) if english.is_file() else set()
        for language, name in FILES.items():
            path = folder / name
            if not path.is_file():
                found.append(f"{repo}/{name}: missing")
                continue
            text = path.read_bytes().decode("utf-8")
            try:
                expected = render(text, wanted, language, anchors)
            except ValueError as error:
                found.append(f"{repo}/{name}: {error}")
                continue
            if expected != text:
                found.append(f"{repo}/{name}: the shared sections are missing or differ")
    return found, missing


def apply(spec: dict, repo: str, base: Path) -> int:
    folder = base / repo
    wanted = sections_of(spec, repo)
    if not wanted:
        raise SystemExit(f"{repo} carries no shared section")
    changed = 0
    anchors = anchors_of((folder / FILES["english"]).read_bytes().decode("utf-8"))
    for language, name in FILES.items():
        path = folder / name
        text = path.read_bytes().decode("utf-8")
        expected = render(text, wanted, language, anchors)
        if expected != text:
            path.write_bytes(expected.encode("utf-8"))
            changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    check = sub.add_parser("check")
    check.add_argument("--base", default=str(ROOT.parent))
    write = sub.add_parser("apply")
    write.add_argument("repo")
    write.add_argument("--base", default=str(ROOT.parent))
    args = parser.parse_args(argv)
    spec = load()
    problems = validate(spec)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"README_SECTIONS=FAIL {len(problems)} problem(s) in the specification", file=sys.stderr)
        return 1
    if args.command == "list":
        for section in spec["sections"]:
            print(f"{section['id']:15} {section['emoji']}  {section['heading']['english']:34} {', '.join(section['repos'])}")
        return 0
    if args.command == "apply":
        print(f"{args.repo}: {apply(spec, args.repo, Path(args.base))} file(s) written")
        return 0
    found, missing = differences(spec, Path(args.base))
    for repo in missing:
        print(f"note: {repo} is not next to this repository, skipped")
    if found:
        print("\n".join(found), file=sys.stderr)
        print(f"README_SECTIONS=FAIL {len(found)} file(s) (run: python tools/readme_sections.py apply REPOSITORY)", file=sys.stderr)
        return 1
    print("README_SECTIONS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
