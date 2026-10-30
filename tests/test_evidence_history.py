# =============================================================================
# URTC-COMMON - tests/test_evidence_history.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from urtc_common import evidence, evidence_history as history

SHA = "a" * 64


def record(when: str, kind: str = "flash", outcome: str = "pass", tool: str = "URTC-FLASHER", name: str = "board-1", **extra) -> dict:
    return evidence.build(kind=kind, outcome=outcome, timestamp_utc=when, tool=tool, tool_version="0.4.2", subject={"name": name, "version_before": "0.3.9", "version_after": "0.4.1"},
                          artifacts=[{"name": "fw.bin", "sha256": SHA, "bytes": 10}], **extra)


def write(folder: Path, name: str, content) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def test_reads_json_files_and_jsonl_lines_newest_first(tmp_path):
    write(tmp_path, "a.json", record("2026-01-01T10:00:00Z"))
    write(tmp_path, "b.jsonl", "\n".join(json.dumps(record(t, kind="test")) for t in ("2026-03-01T10:00:00Z", "2026-02-01T10:00:00Z")) + "\n\n")
    write(tmp_path, "notes.txt", "not evidence")
    entries = history.load_folder(tmp_path)
    assert len(entries) == 3 and all(e.valid for e in entries)
    chosen = history.select(entries)
    assert [e.time for e in chosen] == ["2026-03-01T10:00:00Z", "2026-02-01T10:00:00Z", "2026-01-01T10:00:00Z"]
    assert chosen[0].file == "b.jsonl" and chosen[0].line == 1


def test_a_record_edited_after_it_was_written_is_listed_as_not_valid(tmp_path):
    edited = record("2026-01-01T10:00:00Z")
    edited["outcome"] = "fail"                                       # the digest no longer matches
    write(tmp_path, "edited.json", edited)
    write(tmp_path, "garbage.json", "{ not json")
    write(tmp_path, "list.json", "[1, 2]")
    entries = history.load_folder(tmp_path)
    assert [e.valid for e in entries] == [False, False, False]
    assert "does not match" in entries[0].problems[0] and "not JSON" in entries[1].problems[0] and "JSON object" in entries[2].problems[0]
    assert sorted(e.file for e in history.select(entries, only_invalid=True)) == ["edited.json", "garbage.json", "list.json"]
    assert "[NOT VALID]" in history.to_text(entries) and "problem:" in history.to_text(entries)


def test_filters_by_kind_outcome_tool_time_and_text(tmp_path):
    write(tmp_path, "1.json", record("2026-01-01T10:00:00Z", kind="flash", outcome="pass", name="alpha"))
    write(tmp_path, "2.json", record("2026-02-01T10:00:00Z", kind="test", outcome="fail", tool="URTC-TESTER", name="beta", detail="bus off"))
    write(tmp_path, "3.json", record("2026-03-01T10:00:00Z", kind="install", outcome="error", tool="URTC-UPDATER", name="gamma"))
    entries = history.load_folder(tmp_path)
    names = lambda chosen: [e.record["subject"]["name"] for e in chosen]       # noqa: E731
    assert names(history.select(entries, kind="test")) == ["beta"]
    assert names(history.select(entries, outcome="error")) == ["gamma"]
    assert names(history.select(entries, tool="urtc-flasher")) == ["alpha"]
    assert names(history.select(entries, since="2026-02-01T00:00:00Z", until="2026-02-28T00:00:00Z")) == ["beta"]
    assert names(history.select(entries, text="BUS OFF")) == ["beta"]
    assert names(history.select(entries, text="fw.bin")) == ["gamma", "beta", "alpha"]
    assert history.select(entries, kind="session") == []


def test_summary_counts_and_the_exports_agree(tmp_path):
    write(tmp_path, "1.json", record("2026-01-01T10:00:00Z", outcome="pass"))
    write(tmp_path, "2.json", record("2026-02-01T10:00:00Z", outcome="fail"))
    write(tmp_path, "3.json", "{")
    entries = history.load_folder(tmp_path)
    s = history.summary(entries)
    assert s["records"] == 3 and s["valid"] == 2 and s["invalid"] == 1 and s["outcomes"]["pass"] == 1 and s["outcomes"]["fail"] == 1
    assert s["kinds"]["flash"] == 2 and s["first"] == "2026-01-01T10:00:00Z" and s["last"] == "2026-02-01T10:00:00Z"
    rows = list(csv.DictReader(io.StringIO(history.to_csv(entries))))
    assert len(rows) == 3 and list(rows[0]) == list(history.COLUMNS)
    document = json.loads(history.to_json(entries))
    assert document["format"] == "urtc-evidence-history/1" and document["summary"] == s and len(document["entries"]) == 3
    assert history.to_text([]) == "no records"


def test_recursive_reading_a_missing_folder_and_a_file_that_is_too_big(tmp_path, monkeypatch):
    write(tmp_path / "sub" / "deeper", "x.json", record("2026-01-01T10:00:00Z"))
    assert history.load_folder(tmp_path) == []
    deep = history.load_folder(tmp_path, recursive=True)
    assert len(deep) == 1 and deep[0].file == "sub/deeper/x.json"
    try:
        history.load_folder(tmp_path / "missing")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("a missing folder must be an error")
    monkeypatch.setattr(history, "SIZE_LIMIT", 10)
    big = history.load_folder(tmp_path, recursive=True)
    assert len(big) == 1 and not big[0].valid and "bigger" in big[0].problems[0]


def test_the_command_line_lists_and_fails_on_a_record_that_is_not_valid(tmp_path, capsys):
    write(tmp_path, "ok.json", record("2026-01-01T10:00:00Z"))
    assert history.main([str(tmp_path), "--format", "csv"]) == 0
    assert "timestamp_utc" in capsys.readouterr().out
    write(tmp_path, "bad.json", "{")
    assert history.main([str(tmp_path)]) == 1
    assert history.main([str(tmp_path), "--kind", "test"]) == 0
