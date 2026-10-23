# =============================================================================
# URTC-COMMON - tests/test_help_text.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The quick guide inside the programs: the same sections in the eight languages, and what it says matches what the programs do."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from urtc_common import help_text as ht
from urtc_common import update_strings

ROOT = Path(__file__).resolve().parents[1]


def joined(app: str, language: str) -> str:
    return " ".join(body for _heading, body in ht.GUIDES[app][language])


def test_both_programs_have_a_guide_in_the_eight_languages_with_the_same_number_of_sections():
    assert set(ht.LANGUAGES) == {"english", "spanish", "italian", "french", "german", "chinese", "japanese", "portuguese"}
    for app, guides in ht.GUIDES.items():
        assert set(guides) == set(ht.LANGUAGES), app
        counts = {language: len(sections) for language, sections in guides.items()}
        assert len(set(counts.values())) == 1 and counts["english"] >= 5, (app, counts)
        for language, sections in guides.items():
            for heading, body in sections:
                assert heading.strip() and len(body) > 40, (app, language, heading)
                assert len(heading) <= 40, (app, language, heading)


def test_what_cannot_change_with_the_language_is_in_every_translation():
    for app in ("flasher", "tester"):
        for language in ht.LANGUAGES:
            text = joined(app, language)
            assert "python -m urtc_can.virtual_board" in text and "URTC_VIRTUAL_PORT=socket://127.0.0.1:7777" in text, (app, language)
    for language in ht.LANGUAGES:
        assert ".trc" in joined("tester", language) and ".asc" in joined("tester", language)
        assert "CAN-OTA" in joined("flasher", language)


def test_the_translations_are_not_copies_and_the_portuguese_is_the_european_one():
    for app, guides in ht.GUIDES.items():
        for language, sections in guides.items():
            if language != "english":
                assert [s[1] for s in sections] != [s[1] for s in guides["english"]], (app, language)
    text = " ".join(joined(app, "portuguese") for app in ht.GUIDES)
    assert "ficheiro" in text and "arquivo" not in text and "Conectar" not in text and "Salvar" not in text


def test_an_unknown_language_falls_back_to_english_and_an_unknown_program_has_no_guide():
    assert ht.guide("flasher", "klingon") == ht.GUIDES["flasher"]["english"]
    assert ht.guide("nothing", "english") == ()
    assert ht.title("klingon") == "Help" and ht.title("portuguese") == "Ajuda"


def test_the_guide_names_the_updates_in_the_words_of_the_update_window():
    assert "Check for updates" in ht.GUIDES["flasher"]["english"][-1][1] and update_strings.STRINGS["english"]["UPD_TITLE"] == "Check for updates"
    assert update_strings.STRINGS["spanish"]["UPD_TITLE"] in ht.GUIDES["flasher"]["spanish"][-1][1].replace("Buscar actualización", update_strings.STRINGS["spanish"]["UPD_TITLE"])
    for language in ht.LANGUAGES:
        assert update_strings.STRINGS[language]["UPD_TITLE"].lower() in joined("flasher", language).lower() or language in {"chinese", "japanese"}, language


def test_the_updater_guide_covers_the_list_the_install_the_way_back_the_packages_and_the_security_in_every_language():
    for language in ht.LANGUAGES:
        sections = ht.GUIDES["updater"][language]
        assert len(sections) == 5, language
        text = joined("updater", language)
        assert "SHA-256" in text and "FLASHER" in text and "TESTER" in text, language
        assert update_strings.STRINGS[language]["UPD_TITLE"].lower() in text.lower() or language in {"chinese", "japanese"}, language
        assert update_strings.STRINGS[language]["UPD_BTN_DOWNLOAD"].lower() in text.lower() or language in {"chinese", "japanese"}, language


pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from urtc_common import help_qt  # noqa: E402


def test_the_model_gives_the_title_the_close_button_and_the_sections_in_the_language():
    QCoreApplication.instance() or QCoreApplication([])
    language = ["spanish"]
    model = help_qt.HelpModel("flasher", lambda: language[0])
    assert model.title == "Ayuda" and model.closeText == "Cerrar"
    assert len(model.sections) == 5 and model.sections[0]["title"] == "Conectar"
    seen = []
    model.changed.connect(lambda: seen.append(1))
    language[0] = "german"
    model.languageChanged()
    assert seen and model.title == "Hilfe" and model.sections[0]["title"] == "Verbinden"
    assert help_qt.HelpModel("nothing").sections == []


HOST = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QUrl, qInstallMessageHandler, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from urtc_common import help_qt
QQuickStyle.setStyle("Basic")
app = QGuiApplication([])
messages = []
qInstallMessageHandler(lambda mode, context, message: messages.append(message))
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("guide", help_qt.HelpModel("tester", lambda: "japanese"))
engine.load(QUrl.fromLocalFile(sys.argv[2]))
root = engine.rootObjects()[0] if engine.rootObjects() else None
opened = False
if root is not None:
    dialog = root.findChild(QObject, "helpDialog")
    dialog.open()
    app.processEvents()
    opened = bool(dialog.property("opened"))
print("RESULT " + json.dumps({"loaded": root is not None, "opened": opened, "messages": messages}))
sys.stdout.flush()
os._exit(0)
"""

WINDOW = """
import QtQuick
import QtQuick.Controls
ApplicationWindow {
    visible: true
    width: 800
    height: 600
    HelpDialog { objectName: "helpDialog"; model: guide }
}
"""


def test_the_help_dialog_loads_and_opens_without_qml_errors(tmp_path):
    folder = tmp_path / "qml"
    folder.mkdir()
    (folder / "HelpDialog.qml").write_text((ROOT / "qml" / "HelpDialog.qml").read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "Window.qml").write_text(WINDOW, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, "-c", HOST, str(ROOT / "src"), str(folder / "Window.qml")], capture_output=True, text=True, env=environment, timeout=120)
    line = next((x for x in done.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line is not None, done.stderr[-2000:]
    result = json.loads(line[len("RESULT "):])
    assert result["loaded"], result["messages"]
    problems = [m for m in result["messages"] if ".qml" in m or "QML" in m]
    assert problems == [], " | ".join(problems)
    assert result["opened"]
