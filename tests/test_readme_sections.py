# =============================================================================
# URTC-COMMON - tests/test_readme_sections.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The sections the README files share: the specification is well formed, a section goes in once before the license heading and nothing else of
the file changes, and the README files of the repositories next to this one carry them."""
from __future__ import annotations

from pathlib import Path

import pytest
import readme_sections as rs

ROOT = Path(__file__).resolve().parents[1]


NL = chr(10)


def test_the_specification_is_well_formed_and_every_listed_repository_has_a_section():
    spec = rs.load()
    assert rs.validate(spec) == []
    assert [s["id"] for s in spec["sections"] if not s["id"].startswith("status_")] == ["updates", "first_flash", "heads", "bus_scenarios", "evidence_report", "compatibility"]
    # nine repositories have their own status table (the README of URTC-DOCS is written by its own generator), with the same rows lit in the same eight languages
    status = [s for s in spec["sections"] if s["id"].startswith("status_")]
    assert len(status) == 9 and all(len(s["repos"]) == 1 and s["emoji"] == "🚦" and s["universal"] == {"after": "glance"} for s in status)
    for section in status:
        assert all(("🟢" in row or "🟡" in row or "🟠" in row or "🔴" in row) for row in section["body"]["english"].splitlines()[4:])
        assert len({body.count(NL) for body in section["body"].values()}) == 1
    assert "URTC-FLASHER" in rs.repos_of(spec) and "URTC" in rs.repos_of(spec)
    for section in spec["sections"]:
        assert set(section["heading"]) == set(rs.FILES) and set(section["body"]) == set(rs.FILES)


def test_validation_reports_a_missing_language_a_repeated_identifier_and_a_reference_that_does_not_belong():
    base = rs.load()["sections"][0]
    broken = {"sections": [{**base, "heading": {k: v for k, v in base["heading"].items() if k != "german"}}]}
    assert any("eight languages" in p for p in rs.validate(broken))
    assert any("unique" in p for p in rs.validate({"sections": [base, base]}))
    leaky = {"sections": [{**base, "body": {**base["body"], "english": "see the audit"}}]}
    assert any("does not belong" in p for p in rs.validate(leaky))
    assert any("emoji" in p for p in rs.validate({"sections": [{**base, "emoji": ""}]}))


README = "# Title\n\nText.\n\n## 🔗 Related\n\nLinks.\n\n## 📜 LICENSE\n\nGPL.\n"


def test_the_sections_go_before_the_license_heading_once_and_nothing_else_changes():
    spec = rs.load()
    wanted = [s for s in rs.sections_of(spec, "URTC-FLASHER") if not s["id"].startswith("status_")]
    once = rs.render(README, wanted, "english")
    assert once.startswith("# Title\n\nText.\n\n## 🔗 Related\n\nLinks.\n\n<!-- urtc-section:updates -->\n## 🔄 How it updates")
    assert once.endswith("<!-- /urtc-section:compatibility -->\n\n## 📜 LICENSE\n\nGPL.\n")
    assert once.count("urtc-section:updates -->") == 2 and once.index("updates") < once.index("first_flash") < once.index("compatibility")
    assert rs.render(once, wanted, "english") == once  # putting them again changes nothing


def test_an_edited_or_moved_section_is_put_back_and_the_line_endings_of_the_file_are_kept():
    wanted = rs.sections_of(rs.load(), "URTC-TESTER")
    once = rs.render(README, wanted, "spanish")
    edited = once.replace("Cómo se actualiza", "Otra cosa")
    assert rs.render(edited, wanted, "spanish") == once
    crlf = rs.render(README.replace("\n", "\r\n"), wanted, "german")
    assert "\r\n" in crlf and "\n" not in crlf.replace("\r\n", "")
    assert rs.render(crlf, wanted, "german") == crlf


def test_a_readme_without_a_license_heading_is_refused():
    with pytest.raises(ValueError):
        rs.render("# Title\n\nText.\n", rs.sections_of(rs.load(), "URTC"), "english")


UNIVERSAL = ("# Title\n\n## 📋 At a glance\n\n| | |\n|---|---|\n\n## 🎯 Overview\n\nText.\n\n## 🏛️ Architecture\n\nDiagram.\n\n## ✨ Features\n\nThings.\n\n"
             "```text\n## 🚀 Quick start\n```\n\n## 🚀 Quick start\n\nRun it.\n\n## 🧪 Testing\n\nTests.\n\n## 📜 LICENSE\n\nGPL.\n")


def test_in_a_readme_with_the_universal_sections_the_blocks_go_to_their_place():
    wanted = rs.sections_of(rs.load(), "URTC-FLASHER")
    status = rs.sections_of(rs.load(), "URTC-FLASHER")[-1]
    assert status["id"] == "status_flasher"
    text = rs.render(UNIVERSAL, wanted, "english")
    order, fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        elif not fence and line.startswith("##"):
            order.append(line)
    assert order[:3] == ["## 📋 At a glance", "## 🚦 Project status", "## 🎯 Overview"]
    assert order.index("### How it updates") == order.index("## 🏛️ Architecture") + 1
    assert order.index("### Several tool heads on one bus") == order.index("## ✨ Features") + 1
    quick = order.index("## 🚀 Quick start")
    assert order[quick + 1:quick + 3] == ["### First run without hardware", "### Requirements & compatibility"]
    assert order[quick + 3] == "## 🧪 Testing" and order[-1] == "## 📜 LICENSE"
    assert text.count("## 🚀 Quick start") == 2   # the one inside the code block is left alone
    assert rs.render(text, wanted, "english") == text
    assert "### Requisitos y compatibilidad" in rs.render(UNIVERSAL.replace("Quick start", "Inicio rápido"), wanted, "spanish")


def test_a_roadmap_that_uses_the_same_icon_is_not_taken_for_quick_start():
    old = "# T\n\n## 📋 At a glance\n\nx\n\n## 🚀 ROADMAP\n\nlater\n\n## 📜 LICENSE\n\nGPL.\n"
    text = rs.render(old, rs.sections_of(rs.load(), "URTC-UPDATER"), "english")
    assert "### Requirements & compatibility" not in text and "## 🧩 Compatibility" in text   # kept where it was, before the license
    assert text.index("## 🚦 Project status") < text.index("## 🚀 ROADMAP")                       # but the status is the second section


def test_every_language_places_its_blocks_like_the_english_readme_does(tmp_path):
    """A translation whose old heading happens to carry the name of a universal section must not get its blocks in another place than the English one."""
    old_english = "# T\n\n## 📋 At a glance\n\nx\n\n## 🚀 Getting Started\n\nrun\n\n## 📜 LICENSE\n\nGPL.\n"
    old_chinese = old_english.replace("At a glance", "速览").replace("Getting Started", "快速开始")
    folder = tmp_path / "URTC-UPDATER"
    folder.mkdir()
    for language, name in rs.FILES.items():
        (folder / name).write_text(old_chinese if language == "chinese" else old_english, encoding="utf-8")
    rs.apply(rs.load(), "URTC-UPDATER", tmp_path)
    english, chinese = (folder / "README.md").read_text(encoding="utf-8"), (folder / "README_zho.md").read_text(encoding="utf-8")
    assert "### " not in english and "### " not in chinese
    assert chinese.index("urtc-section:compatibility") > chinese.index("快速开始")   # before the license, as in English
    assert chinese.index("urtc-section:compatibility") > chinese.index("## 📜") - 400 and chinese.count("urtc-section:compatibility") == 2


def test_a_universal_place_must_be_well_formed():
    base = dict(rs.load()["sections"][1])
    assert any("universal place" in p for p in rs.validate({"sections": [{**base, "universal": {"after": "nowhere"}}]}))
    assert any("universal place" in p for p in rs.validate({"sections": [{**base, "universal": {"after": "glance", "in": "features"}}]}))
    assert any("universal heading" in p for p in rs.validate({"sections": [{**base, "universal": {"in": "features", "heading": {"english": "x"}}}]}))
    assert any("does not belong" in p for p in rs.validate({"sections": [{**base, "body": {**base["body"], "english": "an Odo" + "meter rule"}}]}))


def fake_repo(base: Path, repo: str) -> None:
    folder = base / repo
    folder.mkdir()
    for name in rs.FILES.values():
        (folder / name).write_text(README, encoding="utf-8")


def test_check_and_apply_on_a_folder_of_repositories(tmp_path, capsys):
    spec = rs.load()
    for repo in rs.repos_of(spec):
        fake_repo(tmp_path, repo)
    found, missing = rs.differences(spec, tmp_path)
    assert len(found) == 8 * len(rs.repos_of(spec)) and missing == []
    assert rs.main(["check", "--base", str(tmp_path)]) == 1
    for repo in rs.repos_of(spec):
        assert rs.apply(spec, repo, tmp_path) == 8
        assert rs.apply(spec, repo, tmp_path) == 0
    assert rs.differences(spec, tmp_path) == ([], [])
    assert rs.main(["check", "--base", str(tmp_path)]) == 0
    assert "README_SECTIONS=PASS" in capsys.readouterr().out
    (tmp_path / "URTC-FLASHER" / "README_por.md").write_text(README, encoding="utf-8")
    assert rs.differences(spec, tmp_path)[0] == ["URTC-FLASHER/README_por.md: the shared sections are missing or differ"]
    (tmp_path / "URTC-FLASHER" / "README_ita.md").unlink()
    assert any("missing" in line for line in rs.differences(spec, tmp_path)[0])
    with pytest.raises(SystemExit):
        rs.apply(spec, "URTC-OTHER", tmp_path)


def test_the_command_line_lists_the_sections(capsys):
    assert rs.main(["list"]) == 0
    assert "How it updates" in capsys.readouterr().out


def test_the_readme_files_of_the_repositories_next_to_this_one_carry_the_sections():
    base = ROOT.parent
    spec = rs.load()
    if not any((base / repo).is_dir() for repo in rs.repos_of(spec)):
        pytest.skip("the repositories are not next to this one")
    found, _missing = rs.differences(spec, base)
    assert found == [], "\n".join(found[:12])


def test_the_repositories_next_to_this_one_carry_the_current_sections():
    """Where the family is checked out side by side, no README is behind the specification (skipped in a lone checkout)."""
    spec = rs.load()
    if not all((rs.ROOT.parent / repo).is_dir() for repo in rs.repos_of(spec)):
        pytest.skip("the other repositories are not next to this one")
    found, _missing = rs.differences(spec, rs.ROOT.parent)
    assert found == []
