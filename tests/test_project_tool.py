# =============================================================================
# URTC-COMMON - tests/test_project_tool.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The single entry point for the checks of a repository."""
from __future__ import annotations

import sys
from pathlib import Path

import urtc_project_tool as tool

ROOT = Path(__file__).resolve().parents[1]


def test_list_shows_only_what_the_repository_has(tmp_path, capsys):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ci_validate.py").write_text("", encoding="utf-8")
    assert tool.main(["list", "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "ci" in out and "tools/ci_validate.py" in out and "i18n" not in out


def test_every_command_of_this_repository_points_at_a_script_that_exists():
    here = {command.name for command in tool.available(ROOT)}
    assert {"ci", "test", "i18n", "vendor", "constants", "compat", "status", "sections", "tools-doc", "canbus-doc"} <= here


def test_a_command_runs_its_script_with_this_interpreter_and_the_ci_flag(tmp_path):
    calls = []
    runner = lambda argv, cwd, env: calls.append((argv, cwd, env)) or 7  # noqa: E731
    assert tool.main(["ci", "--repo", str(ROOT)], runner) == 7
    argv, cwd, env = calls[0]
    assert argv == [sys.executable, str(ROOT / "tools" / "ci_validate.py")] and cwd == str(ROOT) and env["URTC_CI"] == "1"
    calls.clear()
    tool.main(["i18n", "--repo", str(ROOT), "URTC-FLASHER"], runner)
    assert calls[0][0][2:] == ["check", "URTC-FLASHER"] and calls[0][2] is None


def test_unknown_and_missing_commands_end_with_code_2(tmp_path, capsys):
    assert tool.main(["nothing", "--repo", str(tmp_path)]) == 2
    assert "unknown command" in capsys.readouterr().err
    assert tool.main(["ci", "--repo", str(tmp_path)], lambda *a, **k: 0) == 2
    assert "has no tools/ci_validate.py" in capsys.readouterr().err
