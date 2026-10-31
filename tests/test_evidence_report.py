# =============================================================================
# URTC-COMMON - tests/test_evidence_report.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The evidence report: the same records give the same bytes, nothing from a record can inject markup, a record that fails its check is shown as such,
the origin (simulated or not) is stated, an empty folder gives a report, and the PDF is a well formed file."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from urtc_common import evidence, evidence_history, evidence_report
from urtc_common import evidence_history_strings as hist
from urtc_common import evidence_report_strings as st

SHA = "d" * 64
HOSTILE = '<script>alert(1)</script>"><img src=x onerror=alert(2)>&amp;\u202e\x00'


def record(when: str, *, outcome: str = "pass", name: str = "board-1", adapter: str | None = None, detail: str = "", kind: str = "test") -> dict:
    extra = {"transport": {"adapter": adapter, "bus": "can", "bitrate": 500000}} if adapter else {}
    return evidence.build(kind=kind, outcome=outcome, timestamp_utc=when, tool="URTC-TESTER", tool_version="0.4.4", detail=detail,
                          subject={"name": name, "version_before": "0.3.9", "version_after": "0.4.1"}, artifacts=[{"name": "run.log", "sha256": SHA, "bytes": 10}], **extra)


def folder_with(tmp_path: Path, records: dict[str, object]) -> Path:
    for name, content in records.items():
        (tmp_path / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return tmp_path


def entries_of(folder: Path):
    return evidence_history.load_folder(folder)


def mixed(tmp_path: Path):
    edited = record("2026-01-03T10:00:00Z", name="edited-board")
    edited["outcome"] = "fail"
    return entries_of(folder_with(tmp_path, {
        "a.json": record("2026-01-01T10:00:00Z", name="alpha", adapter="simulate:scenario:lossy", detail="SIMULATED bus with a scenario"),
        "b.json": record("2026-01-02T10:00:00Z", name="beta", adapter="serial:COM3"),
        "c.json": edited, "broken.json": "{ nope", "plain.json": record("2026-01-04T10:00:00Z", name="gamma", kind="flash"),
    }))


def test_the_same_records_give_the_same_bytes_in_both_formats(tmp_path):
    entries = mixed(tmp_path)
    for fmt in evidence_report.FORMATS:
        for language in st.LANGUAGES:
            assert evidence_report.render(entries, fmt, language) == evidence_report.render(list(reversed(entries)), fmt, language)
    first = evidence_report.render(entries, "html")
    assert first == evidence_report.render(entries_of(tmp_path), "html")


def test_the_report_reads_no_clock(tmp_path):
    entries = mixed(tmp_path)
    page = evidence_report.to_html(entries)
    assert re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", page) and set(re.findall(r"20\d\d-\d\d-\d\d", page)) <= {"2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"}
    assert b"CreationDate" not in evidence_report.to_pdf(entries) and b"ModDate" not in evidence_report.to_pdf(entries)


def test_the_page_is_self_contained(tmp_path):
    page = evidence_report.to_html(mixed(tmp_path))
    assert "<script" not in page.lower() and "http://" not in page and "https://" not in page and "src=" not in page and "url(" not in page
    assert "Content-Security-Policy" in page and "default-src &#x27;none&#x27;" in page
    assert "<caption>" in page and 'scope="col"' in page and 'scope="row"' in page and '<html lang="en">' in page


def test_hostile_text_in_a_record_is_escaped_everywhere(tmp_path):
    bad = evidence.build(kind="test", outcome="pass", timestamp_utc="2026-02-01T10:00:00Z", tool="URTC-TESTER", tool_version="0.4.4", operator=HOSTILE, detail=HOSTILE[:400],
                         subject={"name": HOSTILE}, artifacts=[{"name": HOSTILE, "sha256": SHA}], transport={"adapter": HOSTILE, "bus": "can", "bitrate": 500000})
    hostile_other = dict(bad, outcome=HOSTILE, kind=HOSTILE, tool=HOSTILE, evidence_sha256=HOSTILE)
    folder = folder_with(tmp_path, {"x.json": bad, "y.json": hostile_other, "a&amp;'onerror=x;.json": bad})
    for language in st.LANGUAGES:
        page = evidence_report.to_html(entries_of(folder), language)
        assert "<script>" not in page and "<img " not in page and "\u202e" not in page and "\x00" not in page
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "&amp;amp;" in page and "a&amp;amp;&#x27;onerror=x;.json" in page
        assert len(re.findall(r"<script", page, flags=re.I)) == 0
    assert evidence_report.render(entries_of(folder), "pdf")[:5] == b"%PDF-"


def test_an_edited_record_and_a_file_that_is_not_json_are_shown_as_not_valid_with_the_reason(tmp_path):
    entries = mixed(tmp_path)
    page = evidence_report.to_html(entries)
    assert page.count("NOT VALID") >= 2 * 2 and "fails its check and must not be trusted" in page
    assert "evidence_sha256 does not match" in page or "digest" in page.lower()
    assert "not JSON" in page and "edited-board" in page and "broken.json" in page
    assert "2 " in page
    text = evidence_report.to_text(entries)
    assert text.count("*** NOT VALID") == 2 and "not JSON" in text


def test_nothing_is_left_out(tmp_path):
    entries = mixed(tmp_path)
    page = evidence_report.to_html(entries)
    assert len(re.findall(r'<section class="record', page)) == len(entries) == 5
    assert evidence_history.summary(entries)["invalid"] == 2


def test_the_origin_is_stated(tmp_path):
    page = evidence_report.to_html(mixed(tmp_path))
    assert "SIMULATED" in page and "REAL ADAPTER" in page and "NOT STATED" in page
    assert evidence_report.origin(record("2026-01-01T10:00:00Z", adapter="simulate:scenario:x")) == "simulated"
    assert evidence_report.origin(record("2026-01-01T10:00:00Z", detail="SIMULATED bus")) == "simulated"
    assert evidence_report.origin(record("2026-01-01T10:00:00Z", adapter="replay:trace.trc")) == "replay"
    assert evidence_report.origin(record("2026-01-01T10:00:00Z", adapter="python-can:PCAN")) == "real"
    assert evidence_report.origin(record("2026-01-01T10:00:00Z")) == "unknown"
    assert evidence_report.origin({"transport": "not a dict", "detail": 5}) == "unknown"


def test_an_empty_folder_gives_a_report_that_says_so(tmp_path):
    entries = entries_of(tmp_path)
    page = evidence_report.to_html(entries)
    assert "There are no records in the folder." in page and "<h2 id=\"list\">" not in page
    pdf = evidence_report.to_pdf(entries)
    assert pdf.startswith(b"%PDF-") and b"There are no records" in pdf and pdf.count(b"/Type /Page ") == 1


def test_the_pdf_is_well_formed(tmp_path):
    many = {f"r{i:03}.json": record(f"2026-03-{(i % 28) + 1:02}T10:00:00Z", name=f"board-{i}", adapter="simulate:x") for i in range(40)}
    pdf = evidence_report.to_pdf(entries_of(folder_with(tmp_path, many)))
    assert pdf.startswith(b"%PDF-1.4\n") and pdf.rstrip().endswith(b"%%EOF")
    pages = pdf.count(b"/Type /Page ")
    assert pages > 1
    start = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
    assert pdf[start:start + 4] == b"xref"
    table = pdf[start:].split(b"\n")
    count = int(table[1].split()[1])
    offsets = [int(line.split()[0]) for line in table[3:2 + count]]
    for number, offset in enumerate(offsets, 1):
        assert pdf[offset:].startswith(b"%d 0 obj\n" % number)
    for match in re.finditer(rb"<< /Length (\d+) >>\nstream\n", pdf):
        length = int(match.group(1))
        assert pdf[match.end() + length:match.end() + length + 10] == b"\nendstream"
    assert f"Page 1 of {pages}".encode() in pdf


def test_the_pdf_survives_parentheses_and_backslashes(tmp_path):
    odd = record("2026-02-01T10:00:00Z", name="a(b)c\\d")
    pdf = evidence_report.to_pdf(entries_of(folder_with(tmp_path, {"o.json": odd})))
    assert b"a\\(b\\)c\\\\d" in pdf and b"Evidence report" in pdf and b"/FontFile2" not in pdf


def test_every_language_has_the_same_keys_and_placeholders():
    english = st.STRINGS["english"]
    assert set(st.STRINGS) == set(st.LANGUAGES) == set(hist.LANGUAGES)
    for language, table in st.STRINGS.items():
        assert set(table) == set(english), language
        for key, value in table.items():
            assert re.findall(r"\{(\w+)\}", value) == re.findall(r"\{(\w+)\}", english[key]) or set(re.findall(r"\{(\w+)\}", value)) == set(re.findall(r"\{(\w+)\}", english[key])), (language, key)
            assert value.strip()
    assert "relatório" in st.STRINGS["portuguese"]["ER_TITLE"].lower() and "ficheiro" in st.STRINGS["portuguese"]["ER_COL_FILE"].lower()


def test_every_language_renders_html_with_its_language_attribute(tmp_path):
    entries = mixed(tmp_path)
    for language in st.LANGUAGES:
        page = evidence_report.to_html(entries, language)
        assert f'<html lang="{st.HTML_LANG[language]}">' in page and st.STRINGS[language]["ER_TITLE"] in page


def test_an_unknown_format_is_refused(tmp_path):
    with pytest.raises(ValueError):
        evidence_report.render(entries_of(tmp_path), "docx")
