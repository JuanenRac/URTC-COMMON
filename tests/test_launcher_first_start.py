# =============================================================================
# URTC-COMMON - tests/test_launcher_first_start.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional minimum duration of a first start: a quick exit with code 0 that never reported ``mark_started``."""
from __future__ import annotations

import json

from urtc_common import launcher
from urtc_common import self_update as su


def installed_root(base, versions=("0.4.0", "0.5.0"), entry="app.py"):
    root = base / "root"
    for version in versions:
        folder = root / "releases" / version
        folder.mkdir(parents=True)
        (folder / entry).write_text("print('hi')\n", encoding="utf-8")
        (folder / "app_info.json").write_text(json.dumps({"name": "urtc-flasher", "version": version, "entry": entry}), encoding="utf-8")
    su._write_current(root, versions[-1])
    (root / launcher.PENDING_FILE).write_text(versions[-1] + "\n", encoding="utf-8")
    return root


def clock_of(*times):
    ticks = iter(times)
    return lambda: next(ticks)


def test_without_a_minimum_a_quick_exit_with_code_zero_is_a_good_start(tmp_path, monkeypatch):
    monkeypatch.delenv(launcher.FIRST_START_MIN_ENV, raising=False)
    root = installed_root(tmp_path)
    assert launcher.launch(root, run=lambda command, cwd: 0, clock=clock_of(100.0)) == 0
    assert su.current_version(root) == "0.5.0"


def test_with_a_minimum_a_quick_exit_goes_back_and_a_long_first_start_stays(tmp_path, monkeypatch):
    monkeypatch.setenv(launcher.FIRST_START_MIN_ENV, "10")
    quick = installed_root(tmp_path / "quick")
    assert launcher.launch(quick, run=lambda command, cwd: 0, clock=clock_of(100.0, 102.0)) == 0
    assert su.current_version(quick) == "0.4.0"
    long = installed_root(tmp_path / "long")
    assert launcher.launch(long, run=lambda command, cwd: 0, clock=clock_of(100.0, 140.0)) == 0
    assert su.current_version(long) == "0.5.0"


def test_the_setting_is_a_number_above_zero_and_anything_else_means_no_minimum():
    assert launcher.first_start_min_seconds({launcher.FIRST_START_MIN_ENV: "2.5"}) == 2.5
    for value in ("", "0", "-3", "soon", "nan"):
        assert launcher.first_start_min_seconds({launcher.FIRST_START_MIN_ENV: value}) == 0.0
    assert launcher.first_start_min_seconds({}) == 0.0
