#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/status_table.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The table of what has run and what is still pending, made from the manifests of the repositories.

Every repository says in ``urtc.project.json`` how mature it is (``maturity``), what kind of run backs that (``evidence``: host-test,
simulator, bench or field) and, in ``notes``, in its own words, what it is and what it has not done. The statements about what is
still missing are the clauses of the notes that say "never", "not yet", "needs a real ..." and the like; they are copied into
``spec/status.json`` and the table of ``docs/STATUS.md`` is made from that file, so it is never typed by hand and never says more than
the manifests say.

    python tools/status_table.py --refresh      # read the manifests of the repositories next to this one into spec/status.json
    python tools/status_table.py --write        # write docs/STATUS.md
    python tools/status_table.py --check        # fail when the file is out of date
    python tools/status_table.py --check --siblings   # also fail when spec/status.json lags behind the repositories next to this one
    python tools/status_table.py --markdown     # print the table
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "spec" / "status.json"
OUT = ROOT / "docs" / "STATUS.md"
BANNER = "GENERATED from spec/status.json by tools/status_table.py - do not edit by hand."
REPOS = (
    ("URTC", "Tool head firmware"), ("URTC-FLASHER", "Flasher"), ("URTC-GATEWAY", "Gateway in front of the bus"), ("URTC-TESTER", "Tester"),
    ("URTC-WEB-STUDIO", "Web studio"), ("URTC-UPDATER", "Updater"), ("URTC-SMART-RACK", "Smart rack"), ("URTC-VISION-TOOL", "Vision tool"),
    ("URTC-DOCS", "Documentation generator"), ("URTC-COMMON", "Shared protocol and code"),
)
# what a level of evidence means, in one phrase (the levels of tools/ci_validate.py)
EVIDENCE_TEXT = {
    "host-test": "Unit tests and scenarios on a PC",
    "simulator": "Run against a simulated or fake board",
    "bench": "Run on a real board on the bench",
    "field": "Used in the field",
}
# what no run below the bench can have shown
NOT_YET_ON_A_BOARD = "A run on a real board"
PENDING = re.compile(
    r"\b(never (been )?(run|used|tested|exercised|against)|and never|not yet|has not|have not|still need|needs? a real|need a real|does not exist|do not exist|no populated|only against|exercised only|host-tested only|no bus)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")
_CLAUSE = re.compile(r"\s*[,()]\s*|\s+-\s+")


def pending_clauses(notes: str) -> list[str]:
    """The clauses of the notes that say something has not been done, in the order they appear, each once and without a final full stop."""
    found: list[str] = []
    for sentence in _SENTENCE.split(" ".join(notes.split())):
        if not PENDING.search(sentence):
            continue
        clauses = [c.strip(" .;") for c in _CLAUSE.split(sentence) if c.strip(" .;")]
        keep = [c for c in clauses if PENDING.search(c)]
        # clauses too short to be understood on their own ("no bus") are shown with the whole sentence
        text = ", ".join(keep) if keep and all(len(c.split()) >= 5 for c in keep) else sentence.strip(" .;")
        if text and text not in found:
            found.append(text)
    return found


def refresh(base: Path) -> dict:
    projects = []
    for repo, title in REPOS:
        manifest = base / repo / "urtc.project.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        projects.append({
            "repo": repo, "title": title, "maturity": data.get("maturity", "-"), "evidence": data.get("evidence", "-"),
            "pending": pending_clauses(data.get("notes", "")),
        })
    return {"format": 1, "projects": projects}


def load() -> dict:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def render(doc: dict) -> str:
    lines = [f"<!-- {BANNER} -->", "", "## What has run and what is pending", "",
             "| Project | Maturity | What has run | Still pending |", "|---|---|---|---|"]
    for p in doc["projects"]:
        has_run = EVIDENCE_TEXT.get(p["evidence"], p["evidence"])
        pending = list(p["pending"])
        if p["evidence"] in ("host-test", "simulator") and not any("real board" in c.lower() or "real hardware" in c.lower() for c in pending):
            pending.insert(0, NOT_YET_ON_A_BOARD)
        cell = "<br>".join(c.replace("|", "\\|") for c in pending) if pending else "-"
        lines.append(f"| {p['title']} (`{p['repo']}`) | {p['maturity']} | {has_run} | {cell} |")
    lines += ["", "\"What has run\" is the `evidence` level of the manifest of each repository and \"Still pending\" is what its own notes say has not been done; "
              "no board of the family has been populated yet, so nothing here has been run on one.", ""]
    return "\n".join(lines)


def check(doc: dict, siblings: Path | None) -> list[str]:
    problems = []
    if not OUT.is_file() or OUT.read_bytes().decode("utf-8") != render(doc):
        problems.append("docs/STATUS.md is out of date (run python tools/status_table.py --write)")
    if siblings is not None:
        live = {p["repo"]: p for p in refresh(siblings)["projects"]}
        for p in doc["projects"]:
            if p["repo"] in live and live[p["repo"]] != p:
                problems.append(f"{p['repo']}: spec/status.json differs from its manifest (run --refresh)")
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
        STATUS.write_bytes((json.dumps(refresh(ROOT.parent), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        print("wrote spec/status.json")
    doc = load()
    if args.write or args.refresh:
        OUT.write_bytes(render(doc).encode("utf-8"))
        print("wrote docs/STATUS.md")
    if args.markdown:
        sys.stdout.write(render(doc))
    if args.check:
        problems = check(doc, ROOT.parent if args.siblings else None)
        if problems:
            print("STATUS=FAIL " + "; ".join(problems), file=sys.stderr)
            return 1
        print("STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
