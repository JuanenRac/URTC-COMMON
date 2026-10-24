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
    assert [s["id"] for s in spec["sections"] if not s["id"].startswith("status_")] == ["updates", "first_flash", "heads", "compatibility"]
    # nine repositories have their own status table (the README of URTC-DOCS is written by its own generator), with the same rows lit in the same eight languages
    status = [s for s in spec["sections"] if s["id"].startswith("status_")]
    assert len(status) == 9 and all(len(s["repos"]) == 1 and s["emoji"] == "💡" for s in status)
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
