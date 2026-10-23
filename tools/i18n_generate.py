#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/i18n_generate.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""One source for the language files of the programs: the catalog writes the ``.lng``, the ``.json`` and the ``.py`` that each program ships.

The flasher and the tester keep their texts in ``language/<language>.lng``, the web studio in ``src/locales/<code>.json`` and the updater in a Python table.
They said the same words in different ways and the glossary (``spec/i18n/glossary.json``, ``tools/i18n_glossary.py``) had to find and correct the drift. Here
the texts live once, in ``spec/i18n/catalog/<program>.json``, in the eight languages; a text the glossary names is a reference to the glossary entry, so changing
the glossary changes every program that says it. The language files of the programs are generated from the catalog and carry a lock::

    python tools/i18n_generate.py sync  URTC-TESTER     # write the files of the program and its urtc_i18n.lock.json
    python tools/i18n_generate.py check                 # the catalog, and every program next to this repository against what the catalog generates
    python tools/i18n_generate.py check URTC-TESTER     # the same for one program
    python tools/i18n_generate.py import URTC-TESTER    # one-off: read the current files of a program into a new catalog (a program that has no catalog yet)

``check`` fails when a catalog is incomplete (a language or a placeholder missing, an unknown glossary entry) or when a file of a program is not exactly what the
catalog generates, that is, when somebody edited a generated file by hand. A program tests the lock on its own, without this repository
(``spec/i18n/test_i18n_generated.py``, copied with the set ``i18n_test``). Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ROOT / "spec" / "i18n" / "catalog"
GLOSSARY = ROOT / "spec" / "i18n" / "glossary.json"
LOCK_NAME = "urtc_i18n.lock.json"
# the test each program carries to check its own lock: (where it goes in the program, its original here)
TESTS = {"py": ("tests/test_i18n_generated.py", "test_i18n_generated.py"), "ts": ("src/locales/generated.test.ts", "test_i18n_generated.test.ts")}
LANGUAGES = ("english", "spanish", "german", "french", "italian", "japanese", "chinese", "portuguese")
CODES = {"english": "en", "spanish": "es", "german": "de", "french": "fr", "italian": "it", "japanese": "ja", "chinese": "zh", "portuguese": "pt"}
PROGRAMS = {
    "URTC-FLASHER": {"catalog": "flasher", "kind": "lng"},
    "URTC-TESTER": {"catalog": "tester", "kind": "lng"},
    "URTC-WEB-STUDIO": {"catalog": "web-studio", "kind": "json"},
    "URTC-UPDATER": {"catalog": "updater", "kind": "py", "path": "src/urtc_updater/translations_data.py"},
}
PLACEHOLDER = re.compile(r"\{\{?(\w+)\}?\}")


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text or ""))


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --- the catalog file ------------------------------------------------------------------------------------------------------------
def load_catalog(name: str, folder: Path = CATALOGS) -> dict:
    return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))


def dump_catalog(catalog: dict) -> str:
    """Stable text: the head, then one entry per line, so a change of one text is a change of one line."""
    head = {key: value for key, value in catalog.items() if key != "entries"}
    out = ["{"]
    for key, value in head.items():
        out.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    out.append('  "entries": [')
    entries = catalog["entries"]
    for index, entry in enumerate(entries):
        out.append("    " + json.dumps(entry, ensure_ascii=False) + ("," if index + 1 < len(entries) else ""))
    out += ["  ]", "}"]
    return "\n".join(out) + "\n"


def glossary_texts() -> dict[str, dict[str, str]]:
    data = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    return {entry["id"]: entry["text"] for entry in data["entries"]}


def entry_text(entry: dict, language: str, glossary: dict[str, dict[str, str]], kind: str) -> str:
    """The text of one entry in one language the way the program stores it (a ``.lng`` value keeps a line break as ``\\n``)."""
    if "glossary" in entry:
        text = glossary[entry["glossary"]][language]
        return text.replace("\n", "\\n") if kind == "lng" else text
    return entry["text"][language]


def validate(catalog: dict, glossary: dict[str, dict[str, str]] | None = None) -> list[str]:
    glossary = glossary if glossary is not None else glossary_texts()
    problems: list[str] = []
    name = catalog.get("program", "?")
    if catalog.get("format") != 1:
        problems.append(f"{name}: format must be 1")
    if catalog.get("kind") not in ("lng", "json", "py"):
        problems.append(f"{name}: unknown kind {catalog.get('kind')!r}")
    seen: set[str] = set()
    kind = catalog.get("kind", "")
    for entry in catalog.get("entries", []):
        key = entry.get("key", "?")
        if key in seen:
            problems.append(f"{name}: {key} listed twice")
        seen.add(key)
        if "glossary" in entry:
            if entry["glossary"] not in glossary:
                problems.append(f"{name}: {key} names the unknown glossary entry {entry['glossary']}")
            continue
        texts = entry.get("text", {})
        if sorted(texts) != sorted(LANGUAGES):
            problems.append(f"{name}: {key} needs exactly the eight languages ({', '.join(sorted(set(LANGUAGES) ^ set(texts)))} differ)")
            continue
        if any(not isinstance(texts[language], str) or not texts[language].strip() for language in LANGUAGES):
            problems.append(f"{name}: {key} has an empty text")
            continue
        if len({frozenset(_placeholders(texts[language])) for language in LANGUAGES}) != 1:
            problems.append(f"{name}: {key} has different placeholders in the languages")
        if kind == "lng" and any("\n" in texts[language] or "\r" in texts[language] for language in LANGUAGES):
            problems.append(f"{name}: {key} has a real line break (a .lng value writes it as \\n)")
    if kind == "lng":
        for language in LANGUAGES:
            if not catalog.get("header", {}).get(language):
                problems.append(f"{name}: no header lines for {language}")
    return problems


# --- reading the files a program has today (the import) --------------------------------------------------------------------------
def parse_lng(raw: bytes) -> tuple[list[str], list[dict], list[str]]:
    """(header comment lines, entries ``{key, value, before}``, the lines that were dropped). A line without ``=`` right after a key line
    is the rest of that value (the reader of the programs would have ignored it: it is joined with ``\\n``); one after a blank line is dropped."""
    lines = _lf(raw).decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    header: list[str] = []
    index = 0
    while index < len(lines) and lines[index].startswith("#"):
        header.append(lines[index])
        index += 1
    entries: list[dict] = []
    pending: list[str] = []
    blank = False
    dropped: list[str] = []
    for line in lines[index:]:
        if line == "":
            blank = True
            continue
        if line.startswith("#"):
            pending.append(line)
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            entries.append({"key": key.strip(), "value": value, "before": pending})
            pending, blank = [], False
        elif entries and not blank and not pending:
            entries[-1]["value"] += "\\n" + line
        else:
            dropped.append(line)
    if pending:
        dropped.extend(pending)
    return header, entries, dropped


def _flat(node: dict, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, value in node.items():
        if isinstance(value, dict):
            out += _flat(value, prefix + key + ".")
        elif isinstance(value, str):
            out.append((prefix + key, value))
        else:
            raise ValueError(f"{prefix + key}: a text must be a string")
    return out


def read_program(repo: Path, kind: str) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[str]], dict[str, dict[str, list[str]]], list[str]]:
    """(language -> [(key, text)] in the order of the file, the header lines per language, the comments before each key per language, notes)."""
    tables: dict[str, list[tuple[str, str]]] = {}
    headers: dict[str, list[str]] = {}
    befores: dict[str, dict[str, list[str]]] = {}
    notes: list[str] = []
    if kind == "py":
        sys.path.insert(0, str(repo / "src"))
        try:
            import importlib
            module = importlib.import_module("urtc_updater.i18n")
        finally:
            sys.path.remove(str(repo / "src"))
        for language in LANGUAGES:
            tables[language] = [(key, value) for key, value in module.TRANSLATIONS[CODES[language]].items() if isinstance(value, str)]
        return tables, headers, befores, notes
    for language in LANGUAGES:
        if kind == "lng":
            header, entries, dropped = parse_lng((repo / "language" / f"{language}.lng").read_bytes())
            tables[language] = [(entry["key"], entry["value"]) for entry in entries]
            headers[language] = header
            befores[language] = {entry["key"]: entry["before"] for entry in entries if entry["before"]}
            notes += [f"{repo.name} {language}: dropped {line[:60]!r}" for line in dropped]
        else:
            tables[language] = _flat(json.loads((repo / "src" / "locales" / f"{CODES[language]}.json").read_text(encoding="utf-8")))
    return tables, headers, befores, notes


def build_catalog(name: str, kind: str, repo: Path, glossary: dict[str, dict[str, str]] | None = None) -> tuple[dict, list[str]]:
    glossary = glossary if glossary is not None else glossary_texts()
    tables, headers, befores, notes = read_program(repo, kind)
    english = tables["english"]
    keys = [key for key, _ in english]
    for language in LANGUAGES:
        if set(k for k, _ in tables[language]) != set(keys):
            raise ValueError(f"{repo.name}: {language} does not have the same keys as english")
    by_language = {language: dict(tables[language]) for language in LANGUAGES}
    decoded_glossary = {text_id: dict(texts) for text_id, texts in glossary.items()}
    by_text: dict[tuple[str, ...], str] = {tuple(texts[language] for language in LANGUAGES): text_id for text_id, texts in decoded_glossary.items()}
    entries: list[dict] = []
    for key in keys:
        texts = {language: by_language[language][key] for language in LANGUAGES}
        decoded = tuple(texts[language].replace("\\n", "\n") if kind == "lng" else texts[language] for language in LANGUAGES)
        entry: dict = {"key": key}
        if decoded in by_text:
            entry["glossary"] = by_text[decoded]
        else:
            entry["text"] = texts
        before = {language: befores[language][key] for language in LANGUAGES if key in befores.get(language, {})}
        if before:
            entry["before"] = before
        entries.append(entry)
    catalog: dict = {"format": 1, "program": name, "kind": kind}
    if headers:
        catalog["header"] = headers
    catalog["entries"] = entries
    return catalog, notes


# --- generating -----------------------------------------------------------------------------------------------------------------
def generate(catalog: dict, glossary: dict[str, dict[str, str]] | None = None) -> dict[str, bytes]:
    """The files of the program, by their path inside it (always with LF line ends)."""
    glossary = glossary if glossary is not None else glossary_texts()
    kind = catalog["kind"]
    files: dict[str, bytes] = {}
    if kind == "lng":
        for language in LANGUAGES:
            out = list(catalog["header"][language]) + [""]
            for entry in catalog["entries"]:
                before = entry.get("before", {}).get(language, [])
                if before:
                    if out[-1] != "":
                        out.append("")
                    out += before
                out.append(f"{entry['key']}={entry_text(entry, language, glossary, kind)}")
            files[f"language/{language}.lng"] = ("\n".join(out) + "\n").encode("utf-8")
    elif kind == "json":
        for language in LANGUAGES:
            tree: dict = {}
            for entry in catalog["entries"]:
                node = tree
                *path, leaf = entry["key"].split(".")
                for part in path:
                    node = node.setdefault(part, {})
                node[leaf] = entry_text(entry, language, glossary, kind)
            files[f"src/locales/{CODES[language]}.json"] = (json.dumps(tree, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    else:
        out = [
            "# =============================================================================",
            "# URTC-UPDATER - the texts of the window in the eight languages: translations_data.py",
            "# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
            "# GPL-3.0-or-later - see LICENSE",
            "#",
            "# Generated from the catalog of URTC-COMMON (spec/i18n/catalog/updater.json) by tools/i18n_generate.py; edit the catalog, not this file.",
            "# =============================================================================",
            "from __future__ import annotations",
            "",
            "TRANSLATIONS: dict[str, dict[str, str]] = {",
        ]
        for language in LANGUAGES:
            out.append(f'    "{CODES[language]}": {{')
            for entry in catalog["entries"]:
                out.append(f"        {json.dumps(entry['key'])}: {json.dumps(entry_text(entry, language, glossary, kind), ensure_ascii=False)},")
            out.append("    },")
        out.append("}")
        files[PROGRAMS[_repo_of(catalog["program"])]["path"]] = ("\n".join(out) + "\n").encode("utf-8")
    target, template = TESTS["ts" if kind == "json" else "py"]
    files[target] = _lf((ROOT / "spec" / "i18n" / template).read_bytes())
    return files


def _repo_of(program: str) -> str:
    for repo, spec in PROGRAMS.items():
        if spec["catalog"] == program:
            return repo
    raise ValueError(f"unknown program {program}")


def lock_for(catalog_path: Path, files: dict[str, bytes], version: str) -> dict:
    return {
        "format": 1,
        "urtc_common_version": version,
        "catalog": f"spec/i18n/catalog/{catalog_path.name}",
        "catalog_sha256": _sha(_lf(catalog_path.read_bytes())),
        "files": {path: _sha(content) for path, content in sorted(files.items())},
    }


def common_version() -> str:
    try:
        return json.loads((ROOT / "urtc.project.json").read_text(encoding="utf-8")).get("version", "0")
    except (OSError, ValueError):
        return "0"


def sync(repo_name: str, base: Path) -> list[str]:
    spec = PROGRAMS[repo_name]
    catalog = load_catalog(spec["catalog"])
    problems = validate(catalog)
    if problems:
        raise SystemExit("\n".join(problems))
    files = generate(catalog)
    target = base / repo_name
    for path, content in files.items():
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    lock = lock_for(CATALOGS / f"{spec['catalog']}.json", files, common_version())
    (target / LOCK_NAME).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    return sorted(files)


def check_program(repo_name: str, base: Path) -> list[str]:
    spec = PROGRAMS[repo_name]
    catalog = load_catalog(spec["catalog"])
    problems = validate(catalog)
    target = base / repo_name
    if problems or not target.is_dir():
        return problems
    files = generate(catalog)
    for path, content in files.items():
        found = target / path
        if not found.is_file():
            problems.append(f"{repo_name}: {path} is missing (run sync)")
        elif _lf(found.read_bytes()) != content:
            problems.append(f"{repo_name}: {path} is not what the catalog generates (edited by hand, or the catalog changed: run sync)")
    expected = json.loads(json.dumps(lock_for(CATALOGS / f"{spec['catalog']}.json", files, "x")))
    lock_path = target / LOCK_NAME
    if not lock_path.is_file():
        problems.append(f"{repo_name}: no {LOCK_NAME} (run sync)")
    else:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if lock.get("catalog_sha256") != expected["catalog_sha256"] or lock.get("files") != expected["files"]:
            problems.append(f"{repo_name}: {LOCK_NAME} does not match the catalog (run sync)")
    return problems


def import_program(repo_name: str, base: Path) -> tuple[Path, list[str]]:
    spec = PROGRAMS[repo_name]
    catalog, notes = build_catalog(spec["catalog"], spec["kind"], base / repo_name)
    problems = validate(catalog)
    if problems:
        raise SystemExit("\n".join(problems))
    path = CATALOGS / f"{spec['catalog']}.json"
    CATALOGS.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_catalog(catalog), encoding="utf-8", newline="\n")
    return path, notes


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sync", "import"):
        command = sub.add_parser(name)
        command.add_argument("repo", choices=sorted(PROGRAMS))
        command.add_argument("--base", default=str(ROOT.parent), help="the folder that holds the programs (default: next to this repository)")
    check = sub.add_parser("check")
    check.add_argument("repo", nargs="?", choices=sorted(PROGRAMS))
    check.add_argument("--base", default=str(ROOT.parent))
    args = parser.parse_args(argv)
    base = Path(args.base)
    if args.command == "import":
        path, notes = import_program(args.repo, base)
        for note in notes:
            print("note:", note)
        print(f"{path.relative_to(ROOT)} written")
        return 0
    if args.command == "sync":
        written = sync(args.repo, base)
        print(f"{args.repo}: {len(written)} file(s) written, {LOCK_NAME} updated")
        return 0
    problems: list[str] = []
    checked = 0
    for repo_name in ([args.repo] if args.repo else sorted(PROGRAMS)):
        if not (CATALOGS / f"{PROGRAMS[repo_name]['catalog']}.json").is_file():
            problems.append(f"{repo_name}: no catalog")
            continue
        if not (base / repo_name).is_dir():
            print(f"note: {repo_name} is not next to this repository, skipped")
            problems += validate(load_catalog(PROGRAMS[repo_name]["catalog"]))
            continue
        problems += check_program(repo_name, base)
        checked += 1
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"I18N_GENERATE=FAIL {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"I18N_GENERATE=PASS {checked} program(s) match their catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
