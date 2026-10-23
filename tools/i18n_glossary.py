#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/i18n_glossary.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The glossary of the words and phrases that more than one URTC program says, and the check that they say them the same way.

The programs keep their texts in four places: the ``.lng`` files of the flasher and the tester, the ``locales/*.json`` of the web studio and
``i18n.py`` of the updater. Each is right on its own, but a phrase that appears in more than one (Close, Refresh, Clear, Heater PID, Port
search ...) drifts: a German "Löschen" in one program and "Leeren" in another, a Portuguese "Autodeteção" next to "Deteção automática". The
glossary (``spec/i18n/glossary.json``) names each such phrase once, in the eight languages, and lists the keys of the programs that must say it::

    python tools/i18n_glossary.py check                 # the glossary file itself (eight languages, same placeholders, known programs)
    python tools/i18n_glossary.py siblings              # every listed key of the programs next to this repository against the glossary
    python tools/i18n_glossary.py apply URTC-TESTER     # rewrite the lines of the .lng / .json files that differ (text edit, nothing else changes)

The comparison ignores case, accents, punctuation and spacing (and the AE, OE, UE a title in capitals writes for an umlaut: a title in capitals and a sentence say the same thing) and reads a placeholder as
its name whatever the braces (``{count}``, ``{{count}}``). What it does not forgive is a different word. A program that has a real reason to say
it differently is simply not listed for that entry. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "spec" / "i18n" / "glossary.json"
LANGUAGES = ("english", "spanish", "german", "french", "italian", "japanese", "chinese", "portuguese")
CODES = {"english": "en", "spanish": "es", "german": "de", "french": "fr", "italian": "it", "japanese": "ja", "chinese": "zh", "portuguese": "pt"}
REPOS = ("URTC-FLASHER", "URTC-TESTER", "URTC-WEB-STUDIO", "URTC-UPDATER")


def normalize(text: str) -> str:
    """Case, accents, punctuation and spacing do not count; a placeholder counts as its name."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^0-9a-zĀ-￿]+", "", text.lower())
    # the capitals of a title are written without umlauts (AE, OE, UE): the same word
    return text.replace("ae", "a").replace("oe", "o").replace("ue", "u")


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{\{?(\w+)\}?\}", text or ""))


# --- the four ways the programs keep their texts ------------------------------------------------------------------------------
def read_lng(repo: Path, language: str) -> dict[str, str]:
    out: dict[str, str] = {}
    path = repo / "language" / f"{language}.lng"
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.replace("\\n", "\n")
    return out


def read_json_locale(repo: Path, language: str) -> dict[str, str]:
    path = repo / "src" / "locales" / f"{CODES[language]}.json"
    if not path.is_file():
        return {}
    flat: dict[str, str] = {}

    def walk(prefix: str, node: dict) -> None:
        for key, value in node.items():
            if isinstance(value, dict):
                walk(prefix + key + ".", value)
            elif isinstance(value, str):
                flat[prefix + key] = value

    walk("", json.loads(path.read_text(encoding="utf-8")))
    return flat


def read_updater(repo: Path, language: str) -> dict[str, str]:
    source = repo / "src" / "urtc_updater" / "i18n.py"
    if not source.is_file():
        return {}
    import importlib

    sys.path.insert(0, str(repo / "src"))
    try:
        module = importlib.import_module("urtc_updater.i18n")
    finally:
        sys.path.remove(str(repo / "src"))
    table = module.TRANSLATIONS.get(CODES[language], {})
    return {key: value for key, value in table.items() if isinstance(value, str)}


READERS = {"URTC-FLASHER": read_lng, "URTC-TESTER": read_lng, "URTC-WEB-STUDIO": read_json_locale, "URTC-UPDATER": read_updater}


def read_all(repo_name: str, base: Path) -> dict[str, dict[str, str]] | None:
    repo = base / repo_name
    if not repo.is_dir():
        return None
    return {language: READERS[repo_name](repo, language) for language in LANGUAGES}


# --- the glossary ----------------------------------------------------------------------------------------------------------------
def load(path: Path = GLOSSARY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    if data.get("format") != 1:
        problems.append("format must be 1")
    for entry in data.get("entries", []):
        name = entry.get("id", "?")
        if name in seen:
            problems.append(f"{name}: listed twice")
        seen.add(name)
        texts = entry.get("text", {})
        if sorted(texts) != sorted(LANGUAGES):
            problems.append(f"{name}: needs exactly the eight languages ({', '.join(sorted(set(LANGUAGES) ^ set(texts)))} differ)")
            continue
        if any(not isinstance(texts[language], str) or not texts[language].strip() for language in LANGUAGES):
            problems.append(f"{name}: an empty text")
        names = {language: placeholders(texts[language]) for language in LANGUAGES}
        if len({frozenset(v) for v in names.values()}) != 1:
            problems.append(f"{name}: the placeholders differ between languages")
        if not entry.get("consumers"):
            problems.append(f"{name}: no program lists it")
        for consumer in entry.get("consumers", []):
            if consumer.get("repo") not in REPOS or not consumer.get("key"):
                problems.append(f"{name}: unknown consumer {consumer}")
    return problems


def differences(data: dict, base: Path) -> tuple[list[dict], list[str]]:
    """(the keys that say something else, the programs that were not found next to this repository)."""
    tables: dict[str, dict[str, dict[str, str]] | None] = {name: read_all(name, base) for name in REPOS}
    missing = [name for name, table in tables.items() if table is None]
    found: list[dict] = []
    for entry in data["entries"]:
        for consumer in entry["consumers"]:
            table = tables.get(consumer["repo"])
            if table is None:
                continue
            for language in LANGUAGES:
                value = table[language].get(consumer["key"])
                if value is None:
                    found.append({"id": entry["id"], "repo": consumer["repo"], "key": consumer["key"], "language": language, "canonical": entry["text"][language], "found": None})
                elif normalize(value) != normalize(entry["text"][language]) or placeholders(value) != placeholders(entry["text"][language]):
                    found.append({"id": entry["id"], "repo": consumer["repo"], "key": consumer["key"], "language": language, "canonical": entry["text"][language], "found": value})
    return found, missing


def in_the_style_of(found: str, canonical: str) -> str:
    """The canonical text written the way the line it replaces is written: a title in capitals stays in capitals, without accents or umlauts."""
    letters = [c for c in found if c.isalpha()]
    if letters and all(c.isupper() for c in letters if c.isascii() or c.isalpha()) and any(c.isascii() for c in letters):
        text = canonical.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "ss")
        text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
        return text.upper()
    return canonical


# --- rewriting the programs ------------------------------------------------------------------------------------------------------
def apply_to(repo_name: str, data: dict, base: Path) -> int:
    """Puts the canonical text in the lines of the ``.lng`` / ``.json`` files that differ. Returns how many lines changed. The updater's ``i18n.py`` is edited by hand."""
    if repo_name not in ("URTC-FLASHER", "URTC-TESTER", "URTC-WEB-STUDIO"):
        raise SystemExit(f"{repo_name}: not rewritten by this tool (edit it by hand)")
    found, _ = differences(data, base)
    changes = 0
    repo = base / repo_name
    by_file: dict[Path, list[dict]] = {}
    for item in found:
        if item["repo"] != repo_name or item["found"] is None:
            continue
        path = repo / "language" / f"{item['language']}.lng" if repo_name != "URTC-WEB-STUDIO" else repo / "src" / "locales" / f"{CODES[item['language']]}.json"
        by_file.setdefault(path, []).append(item)
    for path, items in by_file.items():
        raw = path.read_bytes().decode("utf-8")
        for item in items:
            item = {**item, "canonical": in_the_style_of(item["found"], item["canonical"])}
            if repo_name == "URTC-WEB-STUDIO":
                leaf = item["key"].split(".")[-1]
                old = json.dumps(item["found"], ensure_ascii=False)
                new = json.dumps(item["canonical"], ensure_ascii=False)
                pattern = f'"{leaf}": {old}'
                if raw.count(pattern) != 1:
                    print(f"  skipped {item['key']} in {path.name}: the line is not unique", file=sys.stderr)
                    continue
                raw = raw.replace(pattern, f'"{leaf}": {new}')
            else:
                old_line = f"{item['key']}={item['found']}".replace("\n", "\\n")
                new_line = f"{item['key']}={item['canonical']}".replace("\n", "\\n")
                if raw.count(old_line) != 1:
                    print(f"  skipped {item['key']} in {path.name}: the line is not unique", file=sys.stderr)
                    continue
                raw = raw.replace(old_line, new_line)
            changes += 1
        path.write_bytes(raw.encode("utf-8"))
    return changes


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sibling = sub.add_parser("siblings")
    sibling.add_argument("--base", default=str(ROOT.parent), help="the folder that holds the programs (default: next to this repository)")
    apply_p = sub.add_parser("apply")
    apply_p.add_argument("repo", choices=("URTC-FLASHER", "URTC-TESTER", "URTC-WEB-STUDIO"))
    apply_p.add_argument("--base", default=str(ROOT.parent))
    args = parser.parse_args(argv)
    data = load()
    problems = validate(data)
    if args.command == "check" or problems:
        if problems:
            print("\n".join(problems), file=sys.stderr)
            print(f"I18N_GLOSSARY=FAIL {len(problems)} problem(s)", file=sys.stderr)
            return 1
        print(f"I18N_GLOSSARY=PASS {len(data['entries'])} entries")
        return 0
    if args.command == "apply":
        changed = apply_to(args.repo, data, Path(args.base))
        print(f"{args.repo}: {changed} line(s) rewritten")
        return 0
    found, missing = differences(data, Path(args.base))
    for name in missing:
        print(f"note: {name} is not next to this repository, skipped")
    for item in found:
        print(f"{item['repo']} {item['key']} [{item['language']}]: says {item['found']!r}, the glossary says {item['canonical']!r} ({item['id']})")
    if found:
        print(f"I18N_SIBLINGS=FAIL {len(found)} difference(s)", file=sys.stderr)
        return 1
    print("I18N_SIBLINGS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
