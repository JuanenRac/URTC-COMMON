# =============================================================================
# URTC-COMMON - tests/test_evidence_other_records.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The files that sit in the folder of the evidence but are not evidence (the update report of the flasher, the result record of the tester): told apart
by their shape, counted and listed apart in the history and in the report, never NOT VALID and never left out; any other shape stays NOT VALID."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from urtc_common import evidence, evidence_history as history, evidence_report
from urtc_common import evidence_history_strings as hist
from urtc_common import evidence_report_strings as st

SHA = "c" * 64


def evidence_record(when: str, outcome: str = "pass") -> dict:
    return evidence.build(kind="flash", outcome=outcome, timestamp_utc=when, tool="URTC-FLASHER", tool_version="0.4.3",
                          subject={"name": "board-1", "version_before": "0.3.9", "version_after": "0.4.1"}, artifacts=[{"name": "fw.bin", "sha256": SHA, "bytes": 10}])


def update_report(signed: bool = False) -> dict:
    report = {"tool": "URTC Flasher", "tool_version": "0.4.3", "timestamp_utc": "2026-01-05T10:00:00Z", "operator": "ana", "target": "slave-1",
              "hardware_id": "0x0000ABCD", "image": {"file": "fw.bin", "size": 10, "sha256": SHA, "signing_key_kind": "release"},
              "version_before": "0.3.9", "version_after": "0.4.1", "result": "OK", "report_sha256": SHA}
    if signed:
        report["signature"] = {"algorithm": "ed25519", "public_key": "00", "value": "00"}
    return report


def result_record(**changes) -> dict:
    data = {"test_name": "ping", "outcome": "PASS", "adapter": "simulate", "firmware_version": "0.4.1", "bus": "can", "bitrate": 500000,
            "log_file": "ping.log", "log_sha256": SHA, "detail": ""}
    data.update(changes)
    return data


def write(folder: Path, name: str, content) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def mixed_folder(tmp_path: Path) -> Path:
    write(tmp_path, "urtc_evidence_1.json", evidence_record("2026-01-01T10:00:00Z"))
    write(tmp_path, "urtc_update_report_20260105_100000.json", update_report())
    write(tmp_path, "ping_20260106_090000.json", result_record())
    return tmp_path


# -- recognition by shape -----------------------------------------------------------------------------------------------------------------------
def test_an_update_report_and_a_result_record_are_other_records_not_evidence(tmp_path):
    entries = history.load_folder(mixed_folder(tmp_path))
    by_file = {e.file: e for e in entries}
    assert by_file["urtc_update_report_20260105_100000.json"].other == "update_report"
    assert by_file["ping_20260106_090000.json"].other == "result_record"
    assert by_file["urtc_evidence_1.json"].other == "" and by_file["urtc_evidence_1.json"].valid
    assert all(e.problems == [] for e in entries)
    assert [e.file for e in history.select(entries)] == ["urtc_evidence_1.json"]
    assert [e.file for e in history.others_of(entries)] == ["ping_20260106_090000.json", "urtc_update_report_20260105_100000.json"]


def test_the_shape_decides_not_the_file_name(tmp_path):
    write(tmp_path, "evidence.json", update_report(signed=True))
    write(tmp_path, "urtc_update_report_fake.json", {"hello": "world"})
    write(tmp_path, "records.jsonl", json.dumps(result_record()) + "\n" + json.dumps(result_record(test_name="pong")) + "\n")
    by_file = {(e.file, e.line): e for e in history.load_folder(tmp_path)}
    assert by_file[("evidence.json", 0)].other == "update_report"
    assert not by_file[("urtc_update_report_fake.json", 0)].valid and by_file[("urtc_update_report_fake.json", 0)].other == ""
    assert by_file[("records.jsonl", 1)].other == "result_record" and by_file[("records.jsonl", 2)].other == "result_record"


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("report_sha256"),                  # a key of the shape is missing
    lambda r: r.update(extra="x"),                     # a key the shape does not have
    lambda r: r.update(image="fw.bin"),                # the wrong type
    lambda r: r.update(tool=3),
    lambda r: r.update(format="urtc-evidence/1"),      # it claims to be evidence: it is checked as evidence
    lambda r: r.update(evidence_sha256=SHA),
])
def test_a_report_that_does_not_fit_the_shape_is_not_valid(tmp_path, mutation):
    report = update_report()
    mutation(report)
    write(tmp_path, "x.json", report)
    [entry] = history.load_folder(tmp_path)
    assert entry.other == "" and not entry.valid and entry.problems


@pytest.mark.parametrize("change", [{"bitrate": "500000"}, {"bitrate": True}, {"log_sha256": 5}, {"extra": 1}, {"format": "urtc-evidence/1"}])
def test_a_result_record_that_does_not_fit_the_shape_is_not_valid(tmp_path, change):
    write(tmp_path, "x.json", result_record(**change))
    [entry] = history.load_folder(tmp_path)
    assert entry.other == "" and not entry.valid


def test_a_result_record_without_its_log_hash_is_not_valid(tmp_path):
    data = result_record()
    del data["log_sha256"]
    write(tmp_path, "x.json", data)
    [entry] = history.load_folder(tmp_path)
    assert not entry.valid and entry.other == ""


def test_an_edited_evidence_record_is_still_not_valid_next_to_other_records(tmp_path):
    folder = mixed_folder(tmp_path)
    edited = evidence_record("2026-01-02T10:00:00Z")
    edited["outcome"] = "fail"
    write(folder, "edited.json", edited)
    write(folder, "garbage.json", "{ no")
    entries = history.load_folder(folder)
    assert sorted(e.file for e in entries if not e.valid) == ["edited.json", "garbage.json"]
    assert history.summary(entries)["invalid"] == 2


# -- counts, text, JSON, exit code --------------------------------------------------------------------------------------------------------------
def test_the_summary_counts_the_other_records_apart(tmp_path):
    summary = history.summary(history.load_folder(mixed_folder(tmp_path)))
    assert summary["records"] == 1 and summary["valid"] == 1 and summary["invalid"] == 0
    assert summary["others"] == 2 and summary["other_kinds"] == {"update_report": 1, "result_record": 1}
    assert summary["first"] == summary["last"] == "2026-01-01T10:00:00Z"     # the time of an other record is not the time of the evidence


def test_history_exits_zero_with_only_valid_evidence_and_other_records_and_lists_them(tmp_path, capsys):
    folder = mixed_folder(tmp_path)
    assert history.main([str(folder)]) == 0
    out = capsys.readouterr().out
    assert "[NOT VALID]" not in out
    assert "2 other record(s)" in out and "urtc_update_report_20260105_100000.json  [update_report]" in out and "ping_20260106_090000.json  [result_record]" in out
    write(folder, "bad.json", "{")
    assert history.main([str(folder)]) == 1


def test_a_filter_does_not_hide_the_other_records(tmp_path, capsys):
    folder = mixed_folder(tmp_path)
    assert history.main([str(folder), "--kind", "test"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("no records") and "2 other record(s)" in out


def test_the_json_export_lists_the_others_and_counts_them(tmp_path, capsys):
    folder = mixed_folder(tmp_path)
    assert history.main([str(folder), "--format", "json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["summary"]["others"] == 2 and len(document["entries"]) == 1
    assert document["others"] == [{"file": "ping_20260106_090000.json", "type": "result_record"},
                                  {"file": "urtc_update_report_20260105_100000.json", "type": "update_report"}]
    assert json.loads(history.to_json([]))["others"] == []


def test_the_csv_says_on_stderr_what_it_leaves_out(tmp_path, capsys):
    folder = mixed_folder(tmp_path)
    assert history.main([str(folder), "--format", "csv"]) == 0
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 2 and "other record(s), not evidence" in captured.err and "ping_20260106_090000.json" in captured.err


def test_only_other_records_is_not_an_error(tmp_path, capsys):
    write(tmp_path, "a.json", update_report())
    assert history.main([str(tmp_path)]) == 0
    assert "no records" in capsys.readouterr().out


# -- the report ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("language", st.LANGUAGES)
def test_the_report_lists_the_other_records_by_name_and_type_in_every_language(tmp_path, language):
    entries = history.load_folder(mixed_folder(tmp_path))
    page = evidence_report.to_html(entries, language)
    assert "urtc_update_report_20260105_100000.json" in page and "ping_20260106_090000.json" in page
    assert hist.text(language, "EH_OTHER_UPDATE_REPORT") in page and hist.text(language, "EH_OTHER_RESULT_RECORD") in page
    assert st.text(language, "ER_OTHERS") in page and st.text(language, "ER_OTHERS_NOTE") in page
    text = evidence_report.to_text(entries, language)
    assert "urtc_update_report_20260105_100000.json" in text and hist.text(language, "EH_OTHER_RESULT_RECORD") in text
    assert page.count('class="bad"') == 0 and page.count("record bad") == 0


def test_the_report_counts_the_evidence_without_the_other_records_and_stays_deterministic(tmp_path):
    entries = history.load_folder(mixed_folder(tmp_path))
    info = evidence_report._summary(evidence_report._items(entries, "english"), entries)
    assert info["records"] == 1 and info["invalid"] == 0 and info["others"] == 2
    for fmt in evidence_report.FORMATS:
        assert evidence_report.render(entries, fmt, "english") == evidence_report.render(list(reversed(entries)), fmt, "english")
    assert b"urtc_update_report_20260105_100000.json" in evidence_report.to_pdf(entries)


def test_a_folder_with_nothing_but_other_records_still_gives_a_report_that_lists_them(tmp_path):
    write(tmp_path, "a.json", result_record())
    page = evidence_report.to_html(history.load_folder(tmp_path))
    assert "a.json" in page and "Other records, not evidence" in page


def test_the_report_of_a_folder_without_other_records_has_no_section_for_them(tmp_path):
    write(tmp_path, "a.json", evidence_record("2026-01-01T10:00:00Z"))
    page = evidence_report.to_html(history.load_folder(tmp_path))
    assert 'id="others"' not in page


def test_a_file_name_with_markup_is_escaped_in_the_list_of_other_records(tmp_path):
    write(tmp_path, "a&b'x.json", result_record())
    page = evidence_report.to_html(history.load_folder(tmp_path))
    assert "a&b'x.json" not in page and "a&amp;b&#x27;x.json" in page
