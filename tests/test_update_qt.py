# =============================================================================
# URTC-COMMON - tests/test_update_qt.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Qt object of the update window and the QML dialog that binds to it (offscreen; skipped where PySide6 is not installed)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402

import test_update_service as base  # noqa: E402

from urtc_common import update_controller as uc  # noqa: E402
from urtc_common import update_qt  # noqa: E402
from urtc_common import update_service as svc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    instance = QCoreApplication.instance() or QCoreApplication([])
    yield instance


def settle(app, model, wanted, limit=200):
    for _ in range(limit):
        app.processEvents()
        if model.state == wanted:
            return
        import time
        time.sleep(0.01)
    raise AssertionError(f"state {model.state}, wanted {wanted}")


def make_model(tmp_path, language="english", saved=None, **kwargs):
    package = base.make_package(tmp_path)
    fetch, _ = base.server(package)
    service = base.service(tmp_path, fetch, **kwargs)
    return update_qt.UpdateModel(service, language=lambda: language, save_options=lambda a, c: saved.append((a, c)) if saved is not None else None)


def test_the_model_goes_from_check_to_install_and_says_it_in_the_language(app, tmp_path):
    model = make_model(tmp_path, "spanish")
    assert model.state == "idle" and model.canCheck and not model.canDownload and model.statusText == ""
    model.check()
    settle(app, model, "available")
    assert "0.5.0" in model.statusText and "Hay una versión" in model.statusText and model.canDownload and "Notes" in model.notes
    model.download()
    settle(app, model, "ready")
    assert model.canInstall and "firma es válida" in model.statusText
    model.install()
    settle(app, model, "installed")
    assert "0.5.0" in model.statusText and model.t("UPD_BTN_CLOSE") == "Cerrar"


def test_an_error_is_said_with_the_text_of_its_code(app, tmp_path):
    model = make_model(tmp_path, "german", busy=lambda: "ein Flash läuft")
    model.check()
    settle(app, model, "available")
    model.download()
    settle(app, model, "ready")
    model.install()
    settle(app, model, "error")
    assert model.isError and "ein Flash läuft" in model.statusText and "Jetzt nicht" in model.statusText


def test_the_options_are_saved_through_the_callback_and_lowering_one_is_flagged(app, tmp_path):
    saved = []
    model = make_model(tmp_path, saved=saved)
    assert not model.autoCheck and model.requireConfirmation
    assert model.needsWarningForAuto(True) and not model.needsWarningForAuto(False)
    assert model.needsWarningForConfirmation(False) and not model.needsWarningForConfirmation(True)
    model.setRequireConfirmation(False)
    model.setAutoCheck(True)
    assert saved == [(False, False), (True, False)]
    assert model.autoCheck and not model.requireConfirmation
    assert model.controller.service.policy == svc.UpdatePolicy(auto_check=True, require_confirmation=False)


def test_the_startup_check_does_nothing_by_default(app, tmp_path):
    model = make_model(tmp_path)
    model.startupCheck()
    app.processEvents()
    assert model.state == "idle"


def test_dismiss_and_the_language_change_signal(app, tmp_path):
    model = make_model(tmp_path)
    seen = []
    model.changed.connect(lambda: seen.append(1))
    model.languageChanged()
    assert seen
    model.check()
    settle(app, model, "available")
    model.dismiss()
    settle(app, model, "idle")
    assert model.version == "" and uc.IDLE == "idle"


HOST = """
import json, sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
import test_update_service as base
from urtc_common import update_qt
import tempfile, pathlib
QQuickStyle.setStyle("Basic")
app = QGuiApplication([])
messages = []
qInstallMessageHandler(lambda mode, context, message: messages.append(message))
tmp = pathlib.Path(tempfile.mkdtemp())
package = base.make_package(tmp)
fetch, _ = base.server(package)
model = update_qt.UpdateModel(base.service(tmp, fetch), language=lambda: "japanese")
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("updates", model)
engine.load(QUrl.fromLocalFile(sys.argv[2]))
root = engine.rootObjects()[0] if engine.rootObjects() else None
opened = False
if root is not None:
    dialog = root.findChild(__import__("PySide6.QtCore", fromlist=["QObject"]).QObject, "updateDialog")
    dialog.open()
    app.processEvents()
    opened = bool(dialog.property("opened"))
print("RESULT " + json.dumps({"loaded": root is not None, "opened": opened, "messages": messages}))
sys.stdout.flush()
import os
os._exit(0)
"""

WINDOW = """
import QtQuick
import QtQuick.Controls
ApplicationWindow {
    visible: true
    width: 800
    height: 600
    UpdateDialog { objectName: "updateDialog"; model: updates }
}
"""


def test_the_dialog_loads_and_opens_without_qml_errors(tmp_path):
    shutil_target = tmp_path / "qml"
    shutil_target.mkdir()
    (shutil_target / "UpdateDialog.qml").write_text((ROOT / "qml" / "UpdateDialog.qml").read_text(encoding="utf-8"), encoding="utf-8")
    (shutil_target / "Window.qml").write_text(WINDOW, encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT / "tools")]))
    done = subprocess.run([sys.executable, "-c", HOST, str(ROOT / "tests"), str(shutil_target / "Window.qml")], capture_output=True, text=True, env=environment, timeout=120)
    line = next((l for l in done.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line is not None, done.stderr[-2000:]
    result = json.loads(line[len("RESULT "):])
    assert result["loaded"], result["messages"]
    problems = [m for m in result["messages"] if ".qml" in m or "QML" in m]
    assert problems == [], " | ".join(problems)
    assert result["opened"]
