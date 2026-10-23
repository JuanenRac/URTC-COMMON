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

Each section sits between two marker comments, ``<!-- urtc-section:ID -->`` and ``<!-- /urtc-section:ID -->``, immediately before the heading of
the license (the first ``## 📜``) of each README, in the order of the specification. Everything outside the markers is left as it is, so the rest
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
        if any(token in str(section.get("body")) for token in ("SONNET", "audit", "Claude")):
            problems.append(f"{name}: a reference that does not belong in a public README")
    return problems


def block(section: dict, language: str, newline: str) -> str:
    identifier = section["id"]
    lines = [f"<!-- urtc-section:{identifier} -->", f"## {section['emoji']} {section['heading'][language]}", "", *section["body"][language].split("\n"), f"<!-- /urtc-section:{identifier} -->"]
    return newline.join(lines)


_BLOCK = re.compile(r"<!-- urtc-section:([a-z0-9_]+) -->.*?<!-- /urtc-section:\1 -->(?:\r?\n){1,2}", re.S)


def render(text: str, sections: list[dict], language: str) -> str:
    """The README text with the sections of this repository written before the license heading (and no older copy of them left)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    cleaned = _BLOCK.sub("", text)
    position = cleaned.find(newline + LICENSE_HEADING)
    if position < 0:
        raise ValueError("the README has no license heading (## 📜)")
    position += len(newline)
    blocks = (newline + newline).join(block(section, language, newline) for section in sections)
    return cleaned[:position] + blocks + newline + newline + cleaned[position:]


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
        for language, name in FILES.items():
            path = folder / name
            if not path.is_file():
                found.append(f"{repo}/{name}: missing")
                continue
            text = path.read_bytes().decode("utf-8")
            try:
                expected = render(text, wanted, language)
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
    for language, name in FILES.items():
        path = folder / name
        text = path.read_bytes().decode("utf-8")
        expected = render(text, wanted, language)
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
