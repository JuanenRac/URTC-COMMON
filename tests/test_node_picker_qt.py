# =============================================================================
# URTC-COMMON - tests/test_node_picker_qt.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Qt object of the node picker window and the QML dialog that binds to it (offscreen; skipped where PySide6 is not installed)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from urtc_common import node_picker as npk  # noqa: E402
from urtc_common import node_picker_qt as npq  # noqa: E402
from urtc_common import protocol as p  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"stored": 1, "running": 1}


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def make(language="english", sync=True, **kwargs):
    picker, bus = npk.sim_picker((2, 5), config=kwargs.pop("config", CONFIG), **kwargs)
    saved = []
    return npq.NodePickerModel(picker, language=lambda: language, save_release=saved.append, sync=sync), picker, bus, saved


def test_the_window_before_a_search_asks_for_one_and_shows_no_rows():
    model, _picker, _bus, _saved = make()
    assert model.message.startswith("Press Find heads") and model.rows == [] and not model.mayShowRows and not model.hasSelection
    assert model.selected == -1 and model.title == "Tool heads on the bus" and model.switchText == ""


def test_finding_selecting_and_releasing_say_each_step_in_the_language():
    model, picker, bus, _saved = make("spanish")
    model.find()
    assert model.mayShowRows and [r["address"] for r in model.rows] == [2, 5] and model.summary == "2 cabezal(es) en el bus"
    assert model.rows[0]["status_text"] == "Listo" and "encontrado" in model.message
    model.ask(5)
    assert "dirección 5" in model.confirmText and not model.hasSelection and bus.nodes[1].obeyed == []
    model.cancel()
    assert model.confirmText == "" and not model.hasSelection
    model.ask(5)
    model.confirm()
    assert model.hasSelection and model.selected == 5 and model.summary == "Cabezal 5 seleccionado" and "confirmado" in model.message
    assert [r["mine"] for r in model.rows] == [False, True]
    model.release()
    assert not model.hasSelection and model.message == "Se soltó la selección." and picker.selected is None


def test_a_refused_head_shows_why_and_the_busy_flag_is_back_down():
    model, _picker, bus, _saved = make("german")
    bus.nodes[0].fault = True
    bus.nodes[0].status_now = True
    model.find()
    bus.step(5)
    model.picker.host.ingest()
    model._refresh()
    model.ask(2)
    assert model.messageLevel == "error" and "Fehler" in model.message and not model.busy and model.confirmText == ""


def test_a_lost_head_raises_the_banner_and_a_new_selection_clears_it(app):
    model, _picker, bus, _saved = make("english")
    model.find()
    model.ask(2)
    model.confirm()
    bus.nodes[0].enabled = False
    for _ in range(p.MN_NODE_TIMEOUT_MS // 10 + 20):
        bus.step(10)
        model._tick()
    assert "safe state" in model.lapseText and not model.hasSelection and model.messageLevel == "warning"
    model.ask(5)
    model.confirm()
    assert model.lapseText == "" and model.selected == 5


def test_lowering_the_protection_is_flagged_and_saved_through_the_callback():
    model, _picker, _bus, saved = make()
    assert model.releaseOnLapse and model.needsWarningForRelease(False) and not model.needsWarningForRelease(True)
    model.setReleaseOnLapse(False)
    assert not model.releaseOnLapse and saved == [False] and not model.needsWarningForRelease(False)


def test_the_work_can_run_in_a_thread_and_ends_with_the_window_free(app):
    model, _picker, _bus, _saved = make(sync=False)
    seen = []
    model.changed.connect(lambda: seen.append(model.busy))
    model.find()
    for _ in range(300):
        app.processEvents()
        if not model.busy and model.rows:
            break
        time.sleep(0.01)
    assert model.rows and not model.busy and True in seen


def test_the_language_change_signal_refreshes_the_texts():
    model, _picker, _bus, _saved = make("english")
    model.find()
    seen = []
    model.changed.connect(lambda: seen.append(1))
    model._language = lambda: "japanese"
    model.languageChanged()
    assert seen and model.t("NP_BTN_FIND") == "ヘッドを探す" and model.summary.startswith("バス上に")


HOST = """
import json, sys
from PySide6.QtCore import QObject, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from urtc_common import node_picker as npk, node_picker_qt as npq
QQuickStyle.setStyle("Basic")
app = QGuiApplication([])
messages = []
qInstallMessageHandler(lambda mode, context, message: messages.append(message))
picker, bus = npk.sim_picker((2, 5, 5), config={"stored": 1, "running": 1})
bus.nodes[2].serial = 0x77
model = npq.NodePickerModel(picker, language=lambda: "chinese", sync=True)
model.find()
model.ask(2)
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("nodes", model)
engine.load(QUrl.fromLocalFile(sys.argv[1]))
root = engine.rootObjects()[0] if engine.rootObjects() else None
opened = False
confirm_open = False
if root is not None:
    dialog = root.findChild(QObject, "nodeDialog")
    dialog.open()
    app.processEvents()
    app.processEvents()
    opened = bool(dialog.property("opened"))
    confirm = dialog.findChild(QObject, "confirmBox")
    confirm_open = bool(confirm.property("opened")) if confirm is not None else False
print("RESULT " + json.dumps({"loaded": root is not None, "opened": opened, "confirm": confirm_open, "messages": messages}))
sys.stdout.flush()
import os
os._exit(0)
"""

WINDOW = """
import QtQuick
import QtQuick.Controls
ApplicationWindow {
    visible: true
    width: 900
    height: 700
    NodePickerDialog { objectName: "nodeDialog"; model: nodes }
}
"""


def test_the_dialog_loads_opens_and_asks_for_the_confirmation_without_qml_errors(tmp_path):
    target = tmp_path / "qml"
    target.mkdir()
    (target / "NodePickerDialog.qml").write_text((ROOT / "qml" / "NodePickerDialog.qml").read_text(encoding="utf-8"), encoding="utf-8")
    (target / "Window.qml").write_text(WINDOW, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT / "tools"), *filter(None, [os.environ.get("PYTHONPATH")])]))
    done = subprocess.run([sys.executable, "-c", HOST, str(target / "Window.qml")], capture_output=True, text=True, env=environment, timeout=120,
                          stdin=subprocess.DEVNULL)
    line = next((entry for entry in done.stdout.splitlines() if entry.startswith("RESULT ")), None)
    assert line is not None, done.stderr[-2000:]
    result = json.loads(line[len("RESULT "):])
    assert result["loaded"], result["messages"]
    problems = [m for m in result["messages"] if ".qml" in m or "QML" in m]
    assert problems == [], " | ".join(problems)
    assert result["opened"] and result["confirm"]


def test_the_window_works_before_a_connection_and_takes_the_picker_when_one_opens():
    model = npq.NodePickerModel(language=lambda: "portuguese", sync=True)
    assert not model.connected and model.rows == [] and model.summary == "Sem cabeças multinó"
    model.find()
    assert "Ligue-se primeiro" in model.message and model.messageLevel == "warning"
    model.ask(3)
    model.confirm()
    model.cancel()
    model.release()
    model.restoreReleaseOption(False)
    picker, _bus = npk.sim_picker((2,), config=CONFIG)
    model.attach(picker)
    assert model.connected and picker.release_on_lapse is False       # the option saved last time reaches the new picker
    model.find()
    assert [r["address"] for r in model.rows] == [2]
    model.attach(None)
    assert not model.connected and model.rows == [] and model.message.startswith("Prima Procurar")


def test_the_window_keeps_off_the_bus_while_the_program_uses_it():
    busy = [True]
    picker, _bus = npk.sim_picker((2,), config=CONFIG)
    model = npq.NodePickerModel(picker, sync=True, app_busy=lambda: busy[0])
    model.find()
    assert model.rows == []                                            # refused: an exchange of the program is running
    busy[0] = False
    model.find()
    assert [r["address"] for r in model.rows] == [2]
