# =============================================================================
# URTC-COMMON - tests/test_status_table.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The table of what has run and what is pending: how the notes of a manifest are read, that the file is current and that the
repositories next to this one still say what it says (the comparison skips when they are not there)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import status_table

ROOT = Path(__file__).resolve().parents[1]


def test_the_clauses_that_say_something_was_not_done_are_taken_from_the_notes():
    notes = (
        "GUI flashing tool (CAN-OTA + SWD), exercised only against a simulated bootloader (MockCAN), never against a real board. "
        "Deadlines use time.monotonic(), not the civil clock."
    )
    assert status_table.pending_clauses(notes) == ["exercised only against a simulated bootloader, never against a real board"]


def test_a_design_rule_that_says_never_is_not_a_pending_item():
    assert status_table.pending_clauses("A tool is never in two slots at once. Everything is checked by tests.") == []


def test_a_clause_too_short_to_be_understood_comes_with_its_sentence():
    assert status_table.pending_clauses("Host-tested only: no bus, adapter or board has been used.") == ["Host-tested only: no bus, adapter or board has been used"]


def test_the_same_statement_is_listed_once():
    notes = "It has not yet been exercised over time. It has not yet been exercised over time."
    assert status_table.pending_clauses(notes) == ["It has not yet been exercised over time"]


def test_a_run_on_a_real_board_is_pending_below_the_bench_unless_the_notes_already_say_it():
    doc = {"projects": [
        {"repo": "A", "title": "One", "maturity": "functional", "evidence": "host-test", "pending": []},
        {"repo": "B", "title": "Two", "maturity": "functional", "evidence": "simulator", "pending": ["never against a real board"]},
        {"repo": "C", "title": "Three", "maturity": "established", "evidence": "bench", "pending": []},
    ]}
    rows = [line for line in status_table.render(doc).splitlines() if line.startswith("| ") and "`" in line]
    assert rows[0].endswith("| Unit tests and scenarios on a PC | A run on a real board |")
    assert rows[1].endswith("| Run against a simulated or fake board | never against a real board |")
    assert rows[2].endswith("| Run on a real board on the bench | - |")


def test_a_bar_inside_a_note_does_not_break_the_table():
    doc = {"projects": [{"repo": "A", "title": "One", "maturity": "m", "evidence": "bench", "pending": ["a | b not yet"]}]}
    assert "a \\| b not yet" in status_table.render(doc)


def test_the_file_is_current():
    assert status_table.check(status_table.load(), None) == []


def test_a_file_edited_by_hand_is_reported(monkeypatch, tmp_path):
    stale = tmp_path / "STATUS.md"
    stale.write_text("edited\n", encoding="utf-8")
    monkeypatch.setattr(status_table, "OUT", stale)
    assert any("out of date" in problem for problem in status_table.check(status_table.load(), None))


def test_the_repositories_next_to_this_one_still_say_what_the_file_says():
    base = ROOT.parent
    if not (base / "URTC" / "urtc.project.json").is_file():
        pytest.skip("the other repositories are not next to this one")
    assert status_table.check(status_table.load(), base) == []


def test_refresh_reads_the_manifests_it_finds(tmp_path):
    (tmp_path / "URTC-TESTER").mkdir()
    (tmp_path / "URTC-TESTER" / "urtc.project.json").write_text(
        json.dumps({"maturity": "functional", "evidence": "simulator", "notes": "Only against fakes, never against a real board."}), encoding="utf-8")
    projects = status_table.refresh(tmp_path)["projects"]
    assert projects == [{"repo": "URTC-TESTER", "title": "Tester", "maturity": "functional", "evidence": "simulator", "pending": ["Only against fakes, never against a real board"]}]
