# =============================================================================
# URTC-COMMON - tests/test_screenshots_check.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The screenshots of a README: the manifest and the pictures are checked, the section is written after Architecture in the eight languages, and the
sibling repositories that have screenshots carry it."""
from __future__ import annotations

import json
from pathlib import Path

import readme_sections as rs
import screenshots_check as sc

ROOT = Path(__file__).resolve().parents[1]
PNG = sc.PNG_MAGIC + b"\x00" * 64
TEXT = {code: f"text {code}" for code in sc.LANGS}


def make_repo(base: Path, name: str = "URTC-SAMPLE", files: tuple[str, ...] = ("overview.png",), weight: int = 0) -> Path:
    repo = base / name
    (repo / "docs").mkdir(parents=True)
    (repo / "images" / "screenshots").mkdir(parents=True)
    screens = [{"file": file, "alt": TEXT, "caption": TEXT} for file in files]
    (repo / "docs" / "screenshots.json").write_text(json.dumps({"screens": screens}), encoding="utf-8")
    for file in files:
        (repo / "images" / "screenshots" / file).write_bytes(PNG + b"\x00" * weight)
    (repo / "docs" / "structure.json").write_text('{"cards": [{"rows": [{"name": "images/"}]}]}', encoding="utf-8")
    (repo / "README.md").write_text("".join(f"images/screenshots/{file}\n" for file in files), encoding="utf-8")
    return repo


def test_a_repository_without_a_manifest_has_nothing_to_check(tmp_path):
    (tmp_path / "docs").mkdir()
    assert sc.problems(tmp_path) == [] and sc.run_in_ci(tmp_path) == [] and sc.section("english", tmp_path) is None


def test_a_good_repository_passes(tmp_path):
    assert sc.run_in_ci(make_repo(tmp_path, files=("a.png", "b.png"))) == []


def test_every_way_of_going_wrong_is_reported(tmp_path):
    repo = make_repo(tmp_path, files=("a.png",))
    (repo / "images" / "screenshots" / "a.png").write_bytes(b"not a png")
    assert any("not a PNG" in problem for problem in sc.problems(repo))
    (repo / "images" / "screenshots" / "a.png").write_bytes(PNG + b"\x00" * sc.MAX_BYTES)
    assert any("at most" in problem for problem in sc.problems(repo))
    (repo / "images" / "screenshots" / "a.png").unlink()
    assert any("does not exist" in problem for problem in sc.problems(repo))
    (repo / "images" / "screenshots" / "stray.png").write_bytes(PNG)
    assert any("stray.png: not listed" in problem for problem in sc.problems(repo))
    data = {"screens": [{"file": "a.png", "alt": {"en": "x"}, "caption": TEXT}, {"file": "a.png", "alt": TEXT, "caption": TEXT}, {"file": "../b.png"}]}
    (repo / "docs" / "screenshots.json").write_text(json.dumps(data), encoding="utf-8")
    found = " | ".join(sc.problems(repo))
    assert "'alt' lacks es" in found and "listed twice" in found and "must be the name of a .png" in found
    (repo / "docs" / "screenshots.json").write_text("{not json", encoding="utf-8")
    assert sc.problems(repo) == ["docs/screenshots.json is not valid JSON"]


def test_more_than_eight_pictures_are_too_many(tmp_path):
    repo = make_repo(tmp_path, files=tuple(f"s{i}.png" for i in range(sc.MAX_SHOTS + 1)))
    assert any("at most 8" in problem for problem in sc.problems(repo))


def test_the_tree_and_the_readme_have_to_carry_the_pictures(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "structure.json").write_text("{}", encoding="utf-8")
    (repo / "README.md").write_text("nothing", encoding="utf-8")
    found = sc.tree_problems(repo)
    assert any("structure.json" in problem for problem in found) and any("README.md does not show" in problem for problem in found)


def test_the_section_is_written_after_architecture_in_the_eight_languages(tmp_path):
    repo = make_repo(tmp_path)
    section = sc.section("english", repo)
    assert rs.validate({"sections": [section]}) == [] and section["universal"] == {"after": "architecture"}
    assert set(section["heading"]) == set(rs.FILES) == set(section["body"])
    assert section["heading"]["portuguese"] == "Capturas de ecrã" and section["emoji"] == "🖼️"
    for body in section["body"].values():
        assert body.count('<img src="images/screenshots/overview.png"') == 1 and "<em>text " in body
    readme = "# T\n\n## 🏛️ Architecture\n\nText.\n\n## ✨ Features\n\nMore.\n\n## 📜 LICENSE\n\nGPL.\n"
    written = rs.render(readme, [section], "english")
    assert written.index("## 🏛️ Architecture") < written.index("## 🖼️ Screenshots") < written.index("## ✨ Features")
    assert rs.render(written, [section], "english") == written  # a second run changes nothing


def test_the_sibling_repositories_with_screenshots_are_valid_and_carry_the_section():
    base = ROOT.parent
    repos = [path for path in base.glob("URTC-*") if sc.has(path)]
    for repo in repos:
        assert sc.run_in_ci(repo) == [], repo.name
    if repos:
        found, _missing = rs.differences(rs.load(), base)
        assert not [line for line in found if "Screenshots" in line or "screenshots" in line]
