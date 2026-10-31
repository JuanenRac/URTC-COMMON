# =============================================================================
# URTC-COMMON - tests/test_evidence_history_characterization.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""What the history does with a folder, pinned before the files that are not evidence were told apart: the list, the summary, the exports and the exit
code for evidence records, for a file that is not JSON and for JSON of a shape nobody knows. These stay true after the change."""
from __future__ import annotations

import json
from pathlib import Path

from urtc_common import evidence, evidence_history as history

SHA = "b" * 64


def record(when: str, outcome: str = "pass") -> dict:
    return evidence.build(kind="flash", outcome=outcome, timestamp_utc=when, tool="URTC-FLASHER", tool_version="0.4.3",
                          subject={"name": "board-1", "version_before": "0.3.9", "version_after": "0.4.1"}, artifacts=[{"name": "fw.bin", "sha256": SHA, "bytes": 10}])


def write(folder: Path, name: str, content) -> None:
    (folder / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def test_evidence_only_folder_is_all_valid_and_exits_zero(tmp_path, capsys):
    write(tmp_path, "a.json", record("2026-01-01T10:00:00Z"))
    write(tmp_path, "b.json", record("2026-01-02T10:00:00Z", "fail"))
    entries = history.load_folder(tmp_path)
    assert [e.valid for e in entries] == [True, True]
    summary = history.summary(entries)
    assert summary["records"] == 2 and summary["valid"] == 2 and summary["invalid"] == 0
    assert history.main([str(tmp_path)]) == 0
    assert "[NOT VALID]" not in capsys.readouterr().out


def test_unknown_json_shapes_and_non_json_are_not_valid_and_make_history_fail(tmp_path, capsys):
    write(tmp_path, "ok.json", record("2026-01-01T10:00:00Z"))
    write(tmp_path, "unknown.json", {"something": "else", "number": 3})
    write(tmp_path, "garbage.json", "{ no")
    write(tmp_path, "list.json", "[1]")
    entries = history.load_folder(tmp_path)
    assert sorted(e.file for e in entries if not e.valid) == ["garbage.json", "list.json", "unknown.json"]
    assert history.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert out.count("[NOT VALID]") == 3
    assert history.summary(entries)["invalid"] == 3


def test_the_json_export_keeps_its_keys(tmp_path):
    write(tmp_path, "a.json", record("2026-01-01T10:00:00Z"))
    document = json.loads(history.to_json(history.load_folder(tmp_path)))
    assert document["format"] == "urtc-evidence-history/1" and set(document) >= {"format", "summary", "entries"}
    assert set(document["summary"]) >= {"records", "valid", "invalid", "outcomes", "kinds", "first", "last"}
