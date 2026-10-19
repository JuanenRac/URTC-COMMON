# =============================================================================
# URTC-COMMON - tests/test_vendor_copy.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""vendor_copy: a copy is safe to carry because a hand edit and a stale copy are both caught."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import vendor_copy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source(tmp_path) -> Path:
    """A throw-away copy of the parts of URTC-COMMON that the tool reads, so the real files are never touched."""
    root = tmp_path / "URTC-COMMON"
    for name in sum(vendor_copy.SETS.values(), []) + ["spec/can_protocol.json", "pyproject.toml"]:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, root / name)
    return root


def run(*args) -> int:
    return vendor_copy.main([str(a) for a in args])


def test_sync_copies_the_chosen_sets_and_writes_the_lock(source, tmp_path):
    target = tmp_path / "client" / "urtc_can"
    assert run("sync", target, "--source", source, "--set", "python", "--set", "vectors") == 0
    names = {p.name for p in target.iterdir()}
    assert {"protocol.py", "slcan.py", "transports.py", "can_vectors.json", vendor_copy.LOCK_NAME} <= names
    assert "urtcCanIds.ts" not in names
    lock = json.loads((target / vendor_copy.LOCK_NAME).read_text(encoding="utf-8"))
    assert lock["format"] == 1 and lock["urtc_common_version"] == vendor_copy.common_version(ROOT)
    assert lock["files"]["protocol.py"]["from"] == "src/urtc_common/protocol.py"
    assert run("check", target, "--source", source) == 0


def test_a_copy_is_the_source_byte_for_byte_with_lf_endings(source, tmp_path):
    target = tmp_path / "c"
    (source / "generated" / "urtc_can_ids.h").write_bytes((ROOT / "generated" / "urtc_can_ids.h").read_bytes().replace(b"\n", b"\r\n"))
    assert run("sync", target, "--source", source, "--set", "c") == 0
    assert b"\r" not in (target / "urtc_can_ids.h").read_bytes()
    assert (target / "urtc_can_ids.h").read_bytes() == (ROOT / "generated" / "urtc_can_ids.h").read_bytes()


def test_a_hand_edit_is_caught_even_without_a_checkout(source, tmp_path, capsys):
    target = tmp_path / "t"
    run("sync", target, "--source", source, "--set", "typescript")
    with open(target / "urtcCanIds.ts", "a", encoding="utf-8") as handle:
        handle.write("export const CAN_ID_HAND_MADE = 0x7AA;\n")
    assert run("check", target, "--lock-only") == 1
    assert "edited by hand" in capsys.readouterr().err


def test_a_copy_that_fell_behind_is_caught_with_a_checkout(source, tmp_path, capsys):
    target = tmp_path / "t"
    run("sync", target, "--source", source, "--set", "c")
    assert run("check", target, "--source", source) == 0
    with open(source / "generated" / "urtc_can_ids.h", "a", encoding="utf-8") as handle:
        handle.write("/* a newer protocol */\n")
    assert run("check", target, "--lock-only") == 0
    assert run("check", target, "--source", source) == 1
    assert "behind URTC-COMMON" in capsys.readouterr().err
    assert run("sync", target, "--source", source, "--set", "c") == 0
    assert run("check", target, "--source", source) == 0


def test_windows_line_endings_in_the_copy_do_not_count_as_an_edit(source, tmp_path):
    target = tmp_path / "t"
    run("sync", target, "--source", source, "--set", "vectors")
    path = target / "can_vectors.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert run("check", target, "--source", source) == 0


def test_a_missing_file_and_a_missing_lock_are_problems(source, tmp_path, capsys):
    target = tmp_path / "t"
    assert run("check", target, "--lock-only") == 1
    assert "not written by vendor_copy.py" in capsys.readouterr().err
    run("sync", target, "--source", source, "--set", "c")
    (target / "urtc_can_ids.h").unlink()
    assert run("check", target, "--lock-only") == 1
    assert "missing" in capsys.readouterr().err


def test_check_without_a_checkout_or_lock_only_refuses_to_pass(tmp_path, source, monkeypatch, capsys):
    target = tmp_path / "t"
    run("sync", target, "--source", source, "--set", "c")
    monkeypatch.setattr(vendor_copy, "HERE", tmp_path / "nowhere" / "tools")
    assert run("check", target) == 1
    assert "no checkout" in capsys.readouterr().err


def test_sync_can_copy_single_files_and_keeps_the_others_in_the_lock(source, tmp_path):
    target = tmp_path / "t"
    run("sync", target, "--source", source, "--set", "python", "--only", "slcan.py", "--only", "protocol.py")
    assert sorted(p.name for p in target.iterdir()) == sorted([vendor_copy.LOCK_NAME, "protocol.py", "slcan.py"])
    run("sync", target, "--source", source, "--set", "vectors")
    lock = json.loads((target / vendor_copy.LOCK_NAME).read_text(encoding="utf-8"))
    assert sorted(lock["files"]) == ["can_vectors.json", "protocol.py", "slcan.py"]
    assert run("sync", target, "--source", source, "--set", "python", "--only", "nothing.py") == 1


def test_status_reports_what_the_copy_is_based_on(source, tmp_path, capsys):
    target = tmp_path / "t"
    assert run("status", target) == 1
    run("sync", target, "--source", source, "--set", "c")
    capsys.readouterr()
    assert run("status", target, "--source", source) == 0
    assert "copied from urtc-common" in capsys.readouterr().out


def test_the_script_runs_as_a_program():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "vendor_copy.py"), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "sync" in result.stdout


def test_the_package_files_that_are_copied_are_importable_as_a_folder_of_their_own(source, tmp_path):
    """A copy lives under another name, so the package must only use relative imports."""
    target = tmp_path / "client" / "urtc_can"
    run("sync", target, "--source", source, "--set", "python", "--set", "vectors")
    script = ("import urtc_can.protocol as p, urtc_can.slcan as s, urtc_can.transports as t, urtc_can.conformance as c; "
              "print(p.CAN_ID_MOTION_CMD, s.encode_line(0x100), c.check_all(c.load('urtc_can/can_vectors.json')))")
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=target.parent)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[:2] == ["288", "t1000"] and result.stdout.strip().endswith("[]")


def test_a_single_file_can_keep_the_name_a_repository_already_uses(source, tmp_path):
    target = tmp_path / "fixtures"
    assert run("sync", target, "--source", source, "--set", "vectors", "--as", "can_conformance_vectors.json") == 0
    assert (target / "can_conformance_vectors.json").is_file() and not (target / "can_vectors.json").exists()
    assert run("check", target, "--source", source) == 0
    assert run("sync", target, "--source", source, "--set", "python", "--as", "x.py") == 1


def test_the_tool_itself_can_be_copied_into_another_repository(source, tmp_path):
    target = tmp_path / "tools"
    assert run("sync", target, "--source", source, "--set", "tool") == 0
    assert (target / "vendor_copy.py").read_bytes() == (ROOT / "tools" / "vendor_copy.py").read_bytes().replace(b"\r\n", b"\n")


def test_the_ui_package_is_copied_as_a_folder_a_program_can_import(source, tmp_path):
    target = tmp_path / "client" / "urtc_ui"
    assert run("sync", target, "--source", source, "--set", "ui") == 0
    assert sorted(path.name for path in target.glob("*.py")) == ["__init__.py", "formatting.py", "languages.py", "status.py"]
    assert run("check", target, "--source", source) == 0
    script = "import urtc_ui; print(urtc_ui.LanguageModel('spanish').index(), urtc_ui.format_bitrate(500000))"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=target.parent)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[0] == "1" and "500" in result.stdout
