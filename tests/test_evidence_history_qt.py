# =============================================================================
# URTC-COMMON - tests/test_evidence_history_qt.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The history window: its texts in the eight languages, the Qt object over a folder of records and the QML dialog that binds to it (offscreen; the Qt
parts are skipped where PySide6 is not installed)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from urtc_common import evidence
from urtc_common import evidence_history_strings as st

ROOT = Path(__file__).resolve().parents[1]
SHA = "b" * 64
ENGLISH = st.STRINGS["english"]


def placeholders(value: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", value))


def record(when: str, kind: str = "flash", outcome: str = "pass", tool: str = "URTC-FLASHER", name: str = "board-1") -> dict:
    return evidence.build(kind=kind, outcome=outcome, timestamp_utc=when, tool=tool, tool_version="0.4.2", subject={"name": name, "version_before": "0.3.9", "version_after": "0.4.1"},
                          artifacts=[{"name": "fw.bin", "sha256": SHA, "bytes": 10}])


def make_folder(base: Path) -> Path:
    folder = base / "evidence"
    folder.mkdir()
    edited = record("2026-01-03T10:00:00Z", outcome="pass", name="edited-board")
    edited["outcome"] = "fail"                                    # edited after it was written: its digest no longer matches
    files = {
        "a.json": record("2026-01-01T10:00:00Z", name="alpha"),
        "b.json": record("2026-01-02T10:00:00Z", kind="test", outcome="fail", tool="URTC-TESTER", name="beta"),
        "c.json": edited,
    }
    for name, content in files.items():
        (folder / name).write_text(json.dumps(content), encoding="utf-8")
    (folder / "broken.json").write_text("{ nope", encoding="utf-8")
    return folder


# -- the texts -----------------------------------------------------------------------------------------------------
def test_there_are_eight_languages_with_the_same_codes_as_the_selector():
    from urtc_ui.languages import LANGUAGES as selector

    assert set(st.STRINGS) == set(st.LANGUAGES) == {code for code, _ in selector}


def test_every_language_has_every_key_with_the_same_placeholders_and_no_empty_text():
    for language, table in st.STRINGS.items():
        assert set(table) == set(ENGLISH), language
        for key, value in table.items():
            assert value.strip(), (language, key)
            assert placeholders(value) == placeholders(ENGLISH[key]), (language, key)


def test_the_other_languages_are_translated_not_copied():
    for language, table in st.STRINGS.items():
        if language == "english":
            continue
        same = [key for key, value in table.items() if value == ENGLISH[key] and len(value) > 12]
        assert same == [], (language, same)


def test_the_portuguese_is_the_european_one():
    joined = " ".join(st.STRINGS["portuguese"].values())
    assert "ficheiro" in joined and "registo" in joined and "Pasta" in joined
    assert "arquivo" not in joined and "registro" not in joined and "Baixar" not in joined


def test_every_outcome_and_kind_of_a_record_has_a_text():
    for name in evidence.OUTCOMES:
        assert st.outcome_key(name) in ENGLISH
    for name in evidence.KINDS:
        assert st.kind_key(name) in ENGLISH
    assert st.text("klingon", "EH_TITLE") == "History of operations" and st.text("german", "EH_NOPE") == "EH_NOPE"
    assert st.text("spanish", "EH_FOLDER", folder="X") == "Carpeta: X"


# -- the Qt object ---------------------------------------------------------------------------------------------------
pyside = pytest.importorskip("PySide6", reason="PySide6 is not installed here")
from urtc_common.evidence_history_qt import ROW_LIMIT, EvidenceHistoryModel  # noqa: E402


def test_the_window_lists_the_records_newest_first_with_what_failed_its_check(tmp_path):
    folder = make_folder(tmp_path)
    model = EvidenceHistoryModel(lambda: folder)
    rows = model.rows
    assert [r["board"] for r in rows if r["board"] != "-"] == ["edited-board", "beta", "alpha"]
    assert model.summaryText == "4 of 4 record(s) shown; 2 valid, 2 not valid" and model.emptyText == ""
    edited = rows[0]
    assert not edited["valid"] and edited["checkText"] == "NOT VALID" and edited["problems"] and edited["file"] == "c.json"
    assert next(r for r in rows if r["file"] == "broken.json")["problems"][0].startswith("not JSON")
    alpha = next(r for r in rows if r["board"] == "alpha")
    assert alpha["valid"] and alpha["kindText"] == "Flash" and alpha["outcomeText"] == "Passed" and alpha["tool"] == "URTC-FLASHER 0.4.2" and alpha["version"] == "0.3.9 -> 0.4.1"


def test_the_filters_work_on_what_was_read_and_say_when_nothing_matches(tmp_path):
    folder = make_folder(tmp_path)
    model = EvidenceHistoryModel(lambda: folder, lambda: "english")
    model.setOutcomeIndex(list(evidence.OUTCOMES).index("fail") + 1)
    assert model.outcomeIndex == 2 and sorted(r["board"] for r in model.rows) == ["beta", "edited-board"]
    model.setOutcomeIndex(0)
    model.setQuery("ALPHA")
    assert [r["board"] for r in model.rows] == ["alpha"] and model.summaryText.startswith("1 of 4")
    model.setQuery("nothing like this")
    assert model.rows == [] and model.emptyText == "No record matches the filter."
    model.setQuery("")
    model.setOnlyInvalid(True)
    assert model.onlyInvalid and sorted(r["file"] for r in model.rows) == ["broken.json", "c.json"]
    model.setOnlyInvalid(False)
    assert len(model.rows) == 4


def test_the_window_says_why_the_list_is_empty(tmp_path):
    assert EvidenceHistoryModel(lambda: None).emptyText.startswith("There is no folder of records yet")
    missing = tmp_path / "nothing"
    assert EvidenceHistoryModel(lambda: missing, lambda: "spanish").emptyText == f"La carpeta {missing} no existe."
    empty = tmp_path / "empty"
    empty.mkdir()
    model = EvidenceHistoryModel(lambda: empty, lambda: "portuguese")
    assert model.emptyText == "Não há registos nesta pasta." and model.rows == [] and model.summaryText == ""


def test_the_window_reads_again_when_asked_and_follows_the_language(tmp_path):
    folder = make_folder(tmp_path)
    language = ["english"]
    model = EvidenceHistoryModel(lambda: folder, lambda: language[0])
    assert len(model.rows) == 4
    (folder / "d.json").write_text(json.dumps(record("2026-02-01T10:00:00Z", name="delta")), encoding="utf-8")
    assert len(model.rows) == 4                                  # nothing changes until it is asked to read again
    model.refresh()
    assert len(model.rows) == 5 and model.rows[0]["board"] == "delta"
    seen = []
    model.changed.connect(lambda: seen.append(1))
    language[0] = "german"
    model.languageChanged()
    assert seen and model.title == "Verlauf der Vorgänge" and model.rows[0]["kindText"] == "Flash" and model.rows[0]["outcomeText"] == "Bestanden"
    assert model.outcomeChoices[0] == "Alle" and len(model.outcomeChoices) == 1 + len(evidence.OUTCOMES) and len(model.headers) == 7
    assert model.rows[0]["checkText"] == "Gültig"


def test_the_window_shows_a_bounded_number_of_rows_and_changes_nothing_on_disk(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    lines = "\n".join(json.dumps(record(f"2026-01-01T10:{i // 60:02d}:{i % 60:02d}Z", name=f"b{i}")) for i in range(ROW_LIMIT + 20))
    (folder / "log.jsonl").write_text(lines + "\n", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    model = EvidenceHistoryModel(lambda: folder)
    assert len(model.rows) == ROW_LIMIT
    assert model.summaryText.startswith(f"{ROW_LIMIT + 20} of {ROW_LIMIT + 20}")
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


def test_an_unknown_kind_or_outcome_in_a_record_is_shown_as_it_is(tmp_path):
    folder = tmp_path / "odd"
    folder.mkdir()
    odd = record("2026-01-01T10:00:00Z")
    odd["kind"], odd["outcome"] = "mystery", "maybe"
    (folder / "odd.json").write_text(json.dumps(odd), encoding="utf-8")
    row = EvidenceHistoryModel(lambda: folder).rows[0]
    assert row["kindText"] == "mystery" and row["outcomeText"] == "maybe" and not row["valid"]


# -- the dialog ----------------------------------------------------------------------------------------------------------
HOST = """
import json, sys
from PySide6.QtCore import QObject, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from urtc_common.evidence_history_qt import EvidenceHistoryModel
QQuickStyle.setStyle("Basic")
app = QGuiApplication([])
messages = []
qInstallMessageHandler(lambda mode, context, message: messages.append(message))
model = EvidenceHistoryModel(lambda: sys.argv[2], language=lambda: "chinese")
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("history", model)
engine.load(QUrl.fromLocalFile(sys.argv[1]))
root = engine.rootObjects()[0] if engine.rootObjects() else None
opened = False
rows = 0
if root is not None:
    dialog = root.findChild(QObject, "evidenceHistoryDialog")
    dialog.open()
    app.processEvents()
    app.processEvents()
    opened = bool(dialog.property("opened"))
    model.setOnlyInvalid(True)
    app.processEvents()
    rows = len(model.rows)
print("RESULT " + json.dumps({"loaded": root is not None, "opened": opened, "rows": rows, "title": model.title, "messages": messages}))
sys.stdout.flush()
import os
os._exit(0)
"""

WINDOW = """
import QtQuick
import QtQuick.Controls
ApplicationWindow {
    visible: true
    width: 1000
    height: 700
    EvidenceHistoryDialog { objectName: "evidenceHistoryDialog"; model: history }
}
"""


def test_the_dialog_loads_and_opens_without_qml_errors(tmp_path):
    target = tmp_path / "qml"
    target.mkdir()
    (target / "EvidenceHistoryDialog.qml").write_text((ROOT / "qml" / "EvidenceHistoryDialog.qml").read_text(encoding="utf-8"), encoding="utf-8")
    (target / "Window.qml").write_text(WINDOW, encoding="utf-8")
    folder = make_folder(tmp_path)
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.pathsep.join([str(ROOT / "src"), *filter(None, [os.environ.get("PYTHONPATH")])]))
    done = subprocess.run([sys.executable, "-c", HOST, str(target / "Window.qml"), str(folder)], capture_output=True, text=True, env=environment, timeout=120,
                          stdin=subprocess.DEVNULL)
    line = next((entry for entry in done.stdout.splitlines() if entry.startswith("RESULT ")), None)
    assert line is not None, done.stderr[-2000:]
    result = json.loads(line[len("RESULT "):])
    assert result["loaded"], result["messages"]
    problems = [m for m in result["messages"] if ".qml" in m or "QML" in m]
    assert problems == [], " | ".join(problems)
    assert result["opened"] and result["rows"] == 2 and result["title"] == "操作历史"


def test_the_report_button_writes_the_report_files_with_every_record_and_does_not_touch_the_records(tmp_path):
    folder = make_folder(tmp_path)
    before = {p.name: p.read_bytes() for p in folder.glob("*.json")}
    model = EvidenceHistoryModel(lambda: folder, lambda: "portuguese")
    model.setOnlyInvalid(True)
    assert model.reportText == "Relatório" and model.reportStatus == ""
    model.writeReport()
    page = (folder / "evidence_report.html").read_text(encoding="utf-8")
    assert page.count('<section class="record') == 4 and "NÃO VÁLIDO" in page and (folder / "evidence_report.pdf").read_bytes().startswith(b"%PDF-")
    assert model.reportStatus.startswith("Relatório escrito: ") and {p.name: p.read_bytes() for p in folder.glob("*.json")} == before
    model.writeReport()                                   # the report files are not records: a second run gives the same bytes
    assert (folder / "evidence_report.html").read_text(encoding="utf-8") == page
    missing = EvidenceHistoryModel(lambda: tmp_path / "nothing", lambda: "english")
    missing.writeReport()
    assert missing.reportStatus.startswith("The report could not be written")


def test_the_window_counts_and_lists_the_other_records_apart_and_never_calls_them_not_valid(tmp_path):
    folder = make_folder(tmp_path)
    (folder / "urtc_update_report_x.json").write_text(json.dumps({
        "tool": "URTC Flasher", "tool_version": "0.4.3", "timestamp_utc": "2026-01-05T10:00:00Z", "target": "s", "image": {"file": "fw.bin"}, "result": "OK",
        "report_sha256": SHA}), encoding="utf-8")
    (folder / "ping_1.json").write_text(json.dumps({
        "test_name": "ping", "outcome": "PASS", "adapter": "simulate", "firmware_version": "0.4.1", "bus": "can", "bitrate": 500000, "log_file": "ping.log",
        "log_sha256": SHA}), encoding="utf-8")
    model = EvidenceHistoryModel(lambda: folder, lambda: "english")
    assert len(model.rows) == 4 and all(r["file"] not in ("ping_1.json", "urtc_update_report_x.json") for r in model.rows)
    assert model.othersCount == 2 and "2 other record(s)" in model.summaryText and model.summaryText.startswith("4 of 4 record(s) shown; 2 valid, 2 not valid")
    assert "ping_1.json  -  test result record" in model.othersText and "urtc_update_report_x.json  -  update report" in model.othersText
    model.setOnlyInvalid(True)
    assert sorted(r["file"] for r in model.rows) == ["broken.json", "c.json"] and model.othersCount == 2     # a filter does not hide them
    model.setOnlyInvalid(False)
    model.setQuery("ping")
    assert model.rows == [] and model.othersCount == 2


def test_a_folder_with_only_other_records_says_so_in_the_window(tmp_path):
    folder = tmp_path / "only"
    folder.mkdir()
    (folder / "ping_1.json").write_text(json.dumps({
        "test_name": "ping", "outcome": "PASS", "adapter": "simulate", "firmware_version": "0.4.1", "bus": "can", "bitrate": 500000, "log_file": "ping.log",
        "log_sha256": SHA}), encoding="utf-8")
    model = EvidenceHistoryModel(lambda: folder, lambda: "portuguese")
    assert model.rows == [] and model.emptyText == st.text("portuguese", "EH_ONLY_OTHERS") and "ping_1.json" in model.othersText
