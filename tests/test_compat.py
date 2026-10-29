# =============================================================================
# URTC-COMMON - tests/test_compat.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The compatibility matrix against what is installed: the order of versions, the states, the firmware the programs carry and the texts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from urtc_common import compat

ROOT = Path(__file__).resolve().parents[1]
MATRIX = {
    "format": 1, "protocol_version": 1,
    "projects": [
        {"repo": "URTC", "title": "Tool head", "kind": "firmware", "version": "0.4.1", "components": [{"name": "URTC_MAIN_FIRMWARE", "version": "0.4.1"}], "common": "0.0.7"},
        {"repo": "URTC-FLASHER", "title": "Flasher", "kind": "program", "version": "0.4.1", "common": "0.0.7"},
        {"repo": "URTC-WEB-STUDIO", "title": "Web studio", "kind": "program", "version": "0.3.7", "common": "0.0.7"},
        {"repo": "URTC-TESTER", "title": "Tester", "kind": "program", "version": "0.4.2"},
    ],
}


def states(rows):
    return {row.repo: row.state for row in rows}


def test_parse_version_accepts_three_and_four_components_only():
    assert compat.parse_version("0.4.1") == (0, 4, 1)
    assert compat.parse_version(" 0.8.0.2 ") == (0, 8, 0, 2)
    for bad in (None, "", "1", "1.2.3.4.5", "v1.2.3", "1.x.3", "1..2"):
        assert compat.parse_version(bad) is None


def test_a_missing_fourth_component_counts_as_zero():
    rows = compat.compare({"format": 1, "protocol_version": 1, "projects": [{"repo": "A", "version": "0.8.0"}]}, {"A": "0.8.0.0"})
    assert rows[0].state == compat.MATCH
    rows = compat.compare({"format": 1, "protocol_version": 1, "projects": [{"repo": "A", "version": "0.8.0"}]}, {"A": "0.8.0.1"})
    assert rows[0].state == compat.NEWER


def test_every_state_is_reachable_and_unreadable_is_never_a_match():
    rows = compat.compare(MATRIX, {"URTC": "0.4.1", "URTC-FLASHER": "0.3.0", "URTC-WEB-STUDIO": "0.9.0", "URTC-TESTER": None})
    assert states(rows) == {"URTC": "match", "URTC-FLASHER": "older", "URTC-WEB-STUDIO": "newer", "URTC-TESTER": "unknown"}
    assert states(compat.compare(MATRIX, {}))["URTC"] == compat.MISSING
    assert compat.summary(rows) == {"match": 1, "newer": 1, "older": 1, "missing": 0, "unknown": 1}


def test_unreadable_installed_version_text_is_unknown():
    assert compat.compare(MATRIX, {"URTC": "banana"})[0].state == compat.UNKNOWN


def test_shared_code_copy_is_compared_when_the_matrix_names_one():
    rows = compat.compare(MATRIX, {"URTC": "0.4.1", "URTC-FLASHER": "0.4.1", "URTC-TESTER": "0.4.2"}, {"URTC-FLASHER": "0.0.5"})
    by = {row.repo: row for row in rows}
    assert by["URTC-FLASHER"].common_state == compat.OLDER
    assert by["URTC"].common_state == compat.UNKNOWN  # installed, matrix names a copy, none recorded
    assert by["URTC-TESTER"].common_state == compat.MATCH  # the matrix names no copy: nothing to compare
    assert by["URTC-WEB-STUDIO"].common_state == compat.MISSING


@pytest.mark.parametrize("broken", [{}, {"format": 2, "protocol_version": 1, "projects": []}, {"format": 1, "protocol_version": "1", "projects": []},
                                    {"format": 1, "protocol_version": 1, "projects": [{"repo": "A"}]},
                                    {"format": 1, "protocol_version": 1, "projects": [{"version": "1.0.0"}]}])
def test_load_matrix_refuses_a_malformed_document(broken):
    with pytest.raises(ValueError):
        compat.load_matrix(broken)


def test_the_generated_matrix_loads_and_equals_the_specification_file():
    generated = ROOT / "generated" / "compat.json"
    assert compat.load_matrix(generated)["protocol_version"] == json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))["protocol_version"]
    assert generated.read_bytes() == (ROOT / "spec" / "versions.json").read_bytes()


def make_workspace(tmp_path: Path, *, flasher_fw="0.3.9", web_fw="0.4.1", head="0.4.1"):
    def project(name, version, common=None, extra=None):
        folder = tmp_path / name
        folder.mkdir()
        manifest = {"name": name, "version": version, **(extra or {})}
        (folder / "urtc.project.json").write_text(json.dumps(manifest), encoding="utf-8")
        if common:
            (folder / "urtc_common.lock.json").write_text(json.dumps({"urtc_common_version": common, "files": {}}), encoding="utf-8")
        return folder

    project("URTC", head, extra={"components": [{"name": "URTC_MAIN_FIRMWARE", "version": head}]})
    flasher = project("URTC-FLASHER", "0.4.1", "0.0.7")
    web = project("URTC-WEB-STUDIO", "0.3.7", "0.0.6")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "notes").mkdir()  # a folder with no manifest is never a project
    for folder, version in ((flasher / "firmware", flasher_fw), (web / "public" / "firmware", web_fw)):
        folder.mkdir(parents=True)
        if version:
            (folder / f"URTC_MAIN_FIRMWARE_v{version}.bin").write_bytes(b"x")
            (folder / "URTC_MAIN_FIRMWARE_v0.1.0.bin").write_bytes(b"x")
    return tmp_path


def test_installed_versions_reads_manifests_and_locks_and_skips_other_folders(tmp_path):
    workspace = make_workspace(tmp_path)
    versions, carried = compat.installed_versions(workspace)
    assert versions == {"URTC": "0.4.1", "URTC-FLASHER": "0.4.1", "URTC-WEB-STUDIO": "0.3.7"}
    assert carried == {"URTC-FLASHER": "0.0.7", "URTC-WEB-STUDIO": "0.0.6"}
    assert compat.installed_versions(tmp_path / "absent") == ({}, {})


def test_a_broken_manifest_or_lock_is_unknown_not_a_crash(tmp_path):
    (tmp_path / "URTC-FLASHER").mkdir()
    (tmp_path / "URTC-FLASHER" / "urtc.project.json").write_text("{not json", encoding="utf-8")
    versions, _ = compat.installed_versions(tmp_path)
    assert versions == {"URTC-FLASHER": None}
    assert compat.compare(MATRIX, versions)[1].state == compat.UNKNOWN


def test_bundled_firmware_is_the_newest_main_image_of_each_program(tmp_path):
    workspace = make_workspace(tmp_path, flasher_fw="0.3.9", web_fw=None)
    assert compat.bundled_firmware(workspace) == {"URTC-FLASHER": "0.3.9", "URTC-WEB-STUDIO": None}
    assert compat.bundled_firmware(tmp_path / "nothing") == {}


def test_firmware_findings_name_the_program_that_carries_other_firmware():
    assert compat.firmware_findings("0.4.1", None, {"URTC-FLASHER": "0.4.1"}) == []
    found = compat.firmware_findings("0.4.1", None, {"URTC-FLASHER": "0.3.9", "URTC-WEB-STUDIO": "0.5.0", "X": None})
    assert found == [("URTC-FLASHER", "older", "0.3.9", "0.4.1"), ("URTC-WEB-STUDIO", "newer", "0.5.0", "0.4.1"), ("X", "unknown", None, "0.4.1")]
    # the installed tool head repository wins over the matrix: an update of it is what would make the carried firmware old
    assert compat.firmware_findings("0.4.1", "0.4.4", {"URTC-FLASHER": "0.4.1"}) == [("URTC-FLASHER", "older", "0.4.1", "0.4.4")]
    assert compat.firmware_findings(None, None, {"URTC-FLASHER": "0.4.1"}) == []


def test_main_firmware_version_prefers_the_component():
    assert compat.main_firmware_version(MATRIX) == "0.4.1"
    assert compat.main_firmware_version({"format": 1, "protocol_version": 1, "projects": [{"repo": "URTC", "version": "0.5.0"}]}) == "0.5.0"
    assert compat.main_firmware_version({"format": 1, "protocol_version": 1, "projects": []}) is None


def test_protocol_note_only_when_the_versions_differ():
    assert compat.protocol_note(MATRIX, None) is None and compat.protocol_note(MATRIX, 1) is None
    assert "2" in compat.protocol_note(MATRIX, 2)


def test_report_puts_the_pieces_together(tmp_path):
    workspace = make_workspace(tmp_path)
    result = compat.report(MATRIX, workspace, "spanish")
    assert result["any_installed"] and result["protocol"] == 1
    assert states(result["rows"])["URTC-TESTER"] == compat.MISSING
    assert any("URTC-FLASHER" in line and "0.3.9" in line for line in result["firmware"])
    assert not compat.report(MATRIX, tmp_path / "empty")["any_installed"]


def test_report_says_the_firmware_is_right_when_it_is(tmp_path):
    workspace = make_workspace(tmp_path, flasher_fw="0.4.1", web_fw="0.4.1")
    # the stray 0.1.0 images are older than the newest one, so they do not count
    assert compat.report(MATRIX, workspace)["firmware"] == [compat.text("english", "firmware_ok", version="0.4.1")]


def test_texts_exist_in_the_eight_languages_with_the_same_keys_and_placeholders():
    assert compat.LANGUAGES == ("english", "spanish", "italian", "french", "german", "chinese", "japanese", "portuguese")
    english = compat.STRINGS["english"]
    for language, table in compat.STRINGS.items():
        assert set(table) == set(english), language
        for key, value in table.items():
            assert value.strip(), (language, key)
            assert set(re.findall(r"{(\w+)}", value)) == set(re.findall(r"{(\w+)}", english[key])), (language, key)
    # no language is a copy of the English one
    for language in compat.LANGUAGES[1:]:
        assert compat.STRINGS[language]["title"] != english["title"]
    assert "ficheiro" not in compat.STRINGS["portuguese"]["close"]
    assert compat.text("klingon", "close") == "Close"


def test_the_window_model_shows_rows_and_follows_the_language(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from urtc_common.compat_qt import CompatModel

    workspace = make_workspace(tmp_path)
    language = ["english"]
    model = CompatModel(MATRIX, lambda: workspace, lambda: language[0])
    assert model.title == "Compatibility" and "1" in model.intro
    assert [row["repo"] for row in model.rows] == ["URTC", "URTC-FLASHER", "URTC-WEB-STUDIO", "URTC-TESTER"]
    assert model.rows[-1]["state"] == "missing" and model.emptyText == ""
    assert model.firmwareLines and model.headers[0] == "Project"
    language[0] = "german"
    model.languageChanged()
    assert model.title == "Kompatibilität" and model.closeText == "Schließen"
    assert CompatModel(MATRIX, lambda: tmp_path / "empty").emptyText != ""
    # the model only reads: the workspace is exactly as it was
    assert sorted(p.name for p in workspace.iterdir()) == [".hidden", "URTC", "URTC-FLASHER", "URTC-WEB-STUDIO", "notes"]


def test_the_dialog_loads_in_qml_offscreen(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from urtc_common.compat_qt import CompatModel

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(ROOT / "qml" / "CompatDialog.qml")))
    model = CompatModel(MATRIX, lambda: make_workspace(tmp_path))
    dialog = component.create()
    assert dialog is not None, component.errorString()
    dialog.setProperty("model", model)
    assert dialog.property("title") == "Compatibility"
    del app
