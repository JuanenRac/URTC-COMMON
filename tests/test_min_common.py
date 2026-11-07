# =============================================================================
# URTC-COMMON - tests/test_min_common.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""min_common: the manifest says the oldest URTC-COMMON the repository carries, and a re-pin keeps it true."""
from __future__ import annotations

import json

import min_common


def _repo(tmp_path, locks, manifest='{\r\n  "name": "URTC-X",\r\n  "version": "1.2.3",\r\n  "role": "tool"\r\n}\r\n', name="URTC-X"):
    root = tmp_path / name
    root.mkdir()
    (root / "urtc.project.json").write_bytes(manifest.encode("utf-8"))
    for folder, version in locks.items():
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / "urtc_common.lock.json").write_text(json.dumps({"format": 1, "urtc_common_version": version, "files": {}}), encoding="utf-8")
    return root


def test_the_oldest_lock_is_the_pin(tmp_path):
    root = _repo(tmp_path, {"tools": "0.1.9", "src": "0.2.4", "docs": "0.10.0"})
    assert min_common.pinned(root) == "0.1.9"


def test_versions_are_compared_as_numbers_not_as_text(tmp_path):
    root = _repo(tmp_path, {"a": "0.10.0", "b": "0.9.0"})
    assert min_common.pinned(root) == "0.9.0"


def test_apply_adds_the_field_after_version_and_keeps_the_line_endings(tmp_path):
    root = _repo(tmp_path, {"tools": "0.2.4"})
    assert min_common.problem(root) is not None
    assert min_common.apply(root) is True
    raw = (root / "urtc.project.json").read_bytes().decode("utf-8")
    assert raw == '{\r\n  "name": "URTC-X",\r\n  "version": "1.2.3",\r\n  "min_common": "0.2.4",\r\n  "role": "tool"\r\n}\r\n'
    assert min_common.problem(root) is None
    assert min_common.apply(root) is False   # the second time there is nothing to change


def test_apply_corrects_a_wrong_value_and_check_notices_it(tmp_path):
    root = _repo(tmp_path, {"tools": "0.2.4"}, '{\n  "version": "1.2.3",\n  "min_common": "0.1.0",\n  "role": "tool"\n}\n')
    assert "0.1.0" in min_common.problem(root)
    assert min_common.apply(root) is True
    assert json.loads((root / "urtc.project.json").read_text(encoding="utf-8"))["min_common"] == "0.2.4"


def test_a_repository_without_copies_has_no_field(tmp_path):
    root = _repo(tmp_path, {})
    assert min_common.problem(root) is None
    root2 = _repo(tmp_path, {}, '{\n  "version": "1.2.3",\n  "min_common": "0.2.4"\n}\n', "URTC-Y")
    assert min_common.problem(root2) is not None
    assert min_common.apply(root2) is True
    assert "min_common" not in json.loads((root2 / "urtc.project.json").read_text(encoding="utf-8"))


def test_main_check_and_apply(tmp_path, capsys):
    root = _repo(tmp_path, {"tools": "0.2.4"})
    assert min_common.main(["check", str(root)]) == 1
    assert min_common.main(["apply", str(root)]) == 0
    assert min_common.main(["check", str(root)]) == 0
    assert min_common.main(["nonsense"]) == 2
    assert "MIN_COMMON=PASS" in capsys.readouterr().out


def test_every_manifest_next_to_this_repository_says_its_pin():
    """With the other repositories of the family beside this one, none says a min_common that is not the oldest copy it carries (skipped alone, as in CI)."""
    import pytest
    siblings = [p for p in min_common.repos([]) if p.name != "URTC-COMMON"]
    if not siblings:
        pytest.skip("no sibling repositories")
    assert [text for repo in siblings if (text := min_common.problem(repo))] == []
