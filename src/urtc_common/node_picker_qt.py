# =============================================================================
# URTC-COMMON - src/urtc_common/node_picker_qt.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Qt object behind ``NodePickerDialog.qml``: the rows, the texts and the buttons of the window that selects one of several tool heads.

The program creates one ``NodePickerModel`` around a ``node_picker.NodePicker``, exposes it to QML and opens the dialog from its menu.
Finding the heads and selecting one wait for the bus, so they run in a thread of their own and the window shows ``busy`` meanwhile;
``sync=True`` runs them in place (tests and pictures without a bus). A timer keeps the selection alive while a head is selected, and
what the picker says (a lapse included) reaches the person as a message and, for a lapse, also as ``lapseText``. PySide6 is imported
here and nowhere else of the node picker.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from . import node_picker as npk
from . import node_picker_strings as strings

TICK_MS = 500


class NodePickerModel(QObject):
    changed = Signal()
    _finished = Signal()

    def __init__(self, picker: npk.NodePicker, language: Callable[[], str] = lambda: "english",
                 save_release: Callable[[bool], None] | None = None, sync: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.picker = picker
        self._language = language
        picker.language = language
        self._save_release = save_release
        self._sync = sync
        self._busy = False
        self._shot: dict = picker.snapshot(language())
        self._messages: list[dict] = []
        self._lapse = ""
        self._finished.connect(self._refresh)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    # -- text ------------------------------------------------------------------------------------------------------
    @Slot(str, result=str)
    def t(self, key: str) -> str:
        return strings.text(self._language(), key)

    @Property(str, notify=changed)
    def title(self) -> str:
        return self.t("NP_TITLE")

    @Property(str, notify=changed)
    def summary(self) -> str:
        return self._shot["summary"]

    @Property(str, notify=changed)
    def switchText(self) -> str:
        return self._shot["switch_text"] if self._shot["searched"] else ""

    @Property(str, notify=changed)
    def switchLevel(self) -> str:
        return "warning" if self._shot["switch"] in (npk.SW_PENDING_ON, npk.SW_PENDING_OFF) else "info"

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._messages[-1]["text"] if self._messages else self.t("NP_MSG_NOT_SEARCHED")

    @Property(str, notify=changed)
    def messageLevel(self) -> str:
        return self._messages[-1]["level"] if self._messages else "info"

    @Property("QVariantList", notify=changed)
    def messages(self) -> list:
        return list(self._messages[-4:])

    @Property(str, notify=changed)
    def lapseText(self) -> str:
        return self._lapse

    @Property(str, notify=changed)
    def confirmText(self) -> str:
        return self._shot["confirm_text"]

    # -- state -----------------------------------------------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def rows(self) -> list:
        return self._shot["rows"]

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=changed)
    def mode(self) -> str:
        return self._shot["mode"]

    @Property(int, notify=changed)
    def selected(self) -> int:
        return -1 if self._shot["selected"] is None else int(self._shot["selected"])

    @Property(bool, notify=changed)
    def hasSelection(self) -> bool:
        return self._shot["selected"] is not None

    @Property(bool, notify=changed)
    def releaseOnLapse(self) -> bool:
        return bool(self._shot["release_on_lapse"])

    @Property(bool, notify=changed)
    def mayShowRows(self) -> bool:
        return self._shot["mode"] == npk.MODE_MULTI

    # -- actions ---------------------------------------------------------------------------------------------------
    @Slot()
    def find(self) -> None:
        self._run(self.picker.scan)

    @Slot(int)
    def ask(self, node: int) -> None:
        self.picker.ask(node)
        self._refresh()

    @Slot()
    def confirm(self) -> None:
        self._run(self.picker.confirm)

    @Slot()
    def cancel(self) -> None:
        self.picker.cancel()
        self._refresh()

    @Slot()
    def release(self) -> None:
        self._run(self.picker.release)

    @Slot(bool, result=bool)
    def needsWarningForRelease(self, value: bool) -> bool:
        """True when the change lowers the protection (it switches the release of the heads off): the dialog asks first."""
        return not value and self.picker.release_on_lapse

    @Slot(bool)
    def setReleaseOnLapse(self, value: bool) -> None:
        self.picker.release_on_lapse = bool(value)
        if self._save_release:
            self._save_release(bool(value))
        self._refresh()

    @Slot()
    def languageChanged(self) -> None:
        self._refresh()

    def start(self) -> None:
        """Start the timer that keeps the selection alive and notices a lapse (the program calls it once, after creating the model)."""
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # -- inside ----------------------------------------------------------------------------------------------------
    def _run(self, work: Callable[[], object]) -> None:
        if self._busy:
            return
        self._busy = True
        self.changed.emit()
        if self._sync:
            work()
            self._busy = False
            self._refresh()
            return

        def job() -> None:
            try:
                work()
            finally:
                self._busy = False
                self._finished.emit()

        threading.Thread(target=job, daemon=True, name="urtc-node-picker").start()

    def _tick(self) -> None:
        if self._busy or self.picker.selected is None:
            return
        self._run(self.picker.tick)

    def _refresh(self) -> None:
        language = self._language()
        for notice in self.picker.take_notices():
            text = self.picker.render(notice, language)
            self._messages.append({"text": text, "level": notice.level})
            if notice.key in ("NP_LAPSE_RELEASED", "NP_LAPSE_KEPT"):
                self._lapse = text
            elif notice.key in ("NP_MSG_SELECTED", "NP_MSG_RELEASED"):
                self._lapse = ""
        del self._messages[:-12]
        self._shot = self.picker.snapshot(language)
        self.changed.emit()
