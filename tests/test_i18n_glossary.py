# =============================================================================
# URTC-COMMON - tests/test_i18n_glossary.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The glossary of the phrases several programs say: the file is well formed, the comparison forgives only case, accents and punctuation, the rewriting changes nothing else,
and the programs next to this repository say the glossary (skipped where they are not)."""
from __future__ import annotations

import json
from pathlib import Path

import i18n_glossary as g
import pytest

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent


def test_the_glossary_file_is_well_formed_and_covers_the_four_programs():
    data = g.load()
    assert g.validate(data) == []
    assert len(data["entries"]) >= 60
    repos = {c["repo"] for e in data["entries"] for c in e["consumers"]}
    assert repos == set(g.REPOS)
    assert all(len(e["consumers"]) >= 2 for e in data["entries"])
    assert len({e["id"] for e in data["entries"]}) == len(data["entries"])


def entry(**changes):
    base = {"id": "close", "text": {language: f"close-{language}" for language in g.LANGUAGES}, "consumers": [{"repo": "URTC-FLASHER", "key": "BTN_CLOSE"}]}
    base.update(changes)
    return base


def test_validation_reports_a_missing_language_a_blank_text_different_placeholders_an_unknown_program_and_a_repeated_id():
    texts = {language: "x {count}" for language in g.LANGUAGES}
    assert g.validate({"format": 1, "entries": [entry(text=texts)]}) == []
    short = dict(texts)
    del short["german"]
    assert any("eight languages" in p for p in g.validate({"format": 1, "entries": [entry(text=short)]}))
    blank = {**texts, "french": "  "}
    assert any("empty" in p for p in g.validate({"format": 1, "entries": [entry(text=blank)]}))
    other = {**texts, "italian": "x {total}"}
    assert any("placeholders" in p for p in g.validate({"format": 1, "entries": [entry(text=other)]}))
    assert any("unknown consumer" in p for p in g.validate({"format": 1, "entries": [entry(text=texts, consumers=[{"repo": "URTC-OTHER", "key": "A"}])]}))
    assert any("no program" in p for p in g.validate({"format": 1, "entries": [entry(text=texts, consumers=[])]}))
    assert any("twice" in p for p in g.validate({"format": 1, "entries": [entry(text=texts), entry(text=texts)]}))
    assert g.validate({"format": 2, "entries": []}) == ["format must be 1"]


def test_the_comparison_forgives_case_accents_punctuation_and_the_digraphs_of_capitals_but_not_a_word():
    assert g.normalize("Detección automática...") == g.normalize("DETECCION AUTOMATICA")
    assert g.normalize("Tastverhältnis (%)") == g.normalize("TASTVERHAELTNIS (%)")
    assert g.normalize("Connect:") == g.normalize("connect")
    assert g.normalize("Löschen") != g.normalize("Leeren")
    assert g.normalize("{{count}} lines") == g.normalize("{count} lines")
    assert g.placeholders("a {x} b {{y}}") == {"x", "y"}


def fake_programs(tmp_path: Path, flasher_close: str = "Close", web_close: str = "Close") -> Path:
    for language in g.LANGUAGES:
        folder = tmp_path / "URTC-FLASHER" / "language"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{language}.lng").write_text(f"# comment\nBTN_CLOSE={flasher_close if language == 'english' else 'Zu'}\nOTHER=keep me\n", encoding="utf-8")
        locales = tmp_path / "URTC-WEB-STUDIO" / "src" / "locales"
        locales.mkdir(parents=True, exist_ok=True)
        (locales / f"{g.CODES[language]}.json").write_text(
            '{\n  "common": {\n    "close": "%s",\n    "other": "keep me"\n  }\n}\n' % (web_close if language == "english" else "Zu"), encoding="utf-8")
    return tmp_path


def glossary_for_fake() -> dict:
    texts = {language: ("Close" if language == "english" else "Zu") for language in g.LANGUAGES}
    return {"format": 1, "entries": [{"id": "close", "text": texts, "consumers": [{"repo": "URTC-FLASHER", "key": "BTN_CLOSE"}, {"repo": "URTC-WEB-STUDIO", "key": "common.close"}]}]}


def test_programs_that_say_the_glossary_have_no_difference_and_missing_programs_are_noted(tmp_path):
    base = fake_programs(tmp_path)
    found, missing = g.differences(glossary_for_fake(), base)
    assert found == [] and missing == ["URTC-TESTER", "URTC-UPDATER"]


def test_a_different_word_a_missing_key_and_a_changed_placeholder_are_found(tmp_path):
    base = fake_programs(tmp_path, flasher_close="Shut", web_close="CLOSE")
    found, _ = g.differences(glossary_for_fake(), base)
    assert [(f["repo"], f["language"], f["found"]) for f in found] == [("URTC-FLASHER", "english", "Shut")]  # the capitals of the other are forgiven
    data = glossary_for_fake()
    data["entries"][0]["consumers"].append({"repo": "URTC-FLASHER", "key": "NO_SUCH_KEY"})
    assert any(f["found"] is None and f["key"] == "NO_SUCH_KEY" for f in g.differences(data, base)[0])


def test_apply_rewrites_only_the_lines_that_differ_in_lng_and_json_files(tmp_path):
    base = fake_programs(tmp_path, flasher_close="Shut", web_close="Shut")
    data = glossary_for_fake()
    assert g.apply_to("URTC-FLASHER", data, base) == 1
    assert g.apply_to("URTC-WEB-STUDIO", data, base) == 1
    english = (base / "URTC-FLASHER" / "language" / "english.lng").read_text(encoding="utf-8")
    assert english == "# comment\nBTN_CLOSE=Close\nOTHER=keep me\n"
    web = (base / "URTC-WEB-STUDIO" / "src" / "locales" / "en.json").read_text(encoding="utf-8")
    assert json.loads(web) == {"common": {"close": "Close", "other": "keep me"}} and web.endswith("}\n")
    assert g.differences(data, base)[0] == []
    assert g.apply_to("URTC-FLASHER", data, base) == 0
    with pytest.raises(SystemExit):
        g.apply_to("URTC-UPDATER", data, base)


def test_apply_keeps_a_title_in_capitals_without_accents(tmp_path):
    assert g.in_the_style_of("ENERGISIEREN", "Aktivieren") == "AKTIVIEREN"
    assert g.in_the_style_of("TASTVERHAELTNIS (%)", "Tastverhältnis (%)") == "TASTVERHAELTNIS (%)"
    assert g.in_the_style_of("Tastverhältnis", "Leeren") == "Leeren"
    assert g.in_the_style_of("接続に失敗", "接続に失敗しました") == "接続に失敗しました"


def test_the_command_line(tmp_path, capsys):
    assert g.main(["check"]) == 0 and "I18N_GLOSSARY=PASS" in capsys.readouterr().out
    base = fake_programs(tmp_path, flasher_close="Shut")
    original = g.load
    g.load = glossary_for_fake
    try:
        assert g.main(["siblings", "--base", str(base)]) == 1
        assert g.main(["apply", "URTC-FLASHER", "--base", str(base)]) == 0
        assert g.main(["siblings", "--base", str(base)]) == 0
    finally:
        g.load = original
    assert "I18N_SIBLINGS=PASS" in capsys.readouterr().out


def test_the_programs_next_to_this_repository_say_the_glossary():
    present = [name for name in g.REPOS if (SIBLINGS / name).is_dir()]
    if len(present) < 2:
        pytest.skip("the programs are not next to this repository")
    found, _ = g.differences(g.load(), SIBLINGS)
    assert found == [], "\n".join(f"{f['repo']} {f['key']} [{f['language']}] says {f['found']!r}, the glossary says {f['canonical']!r}" for f in found[:20])


def test_the_update_window_says_the_common_words_like_the_glossary():
    from urtc_common import update_strings

    by_id = {e["id"]: e for e in g.load()["entries"]}
    for glossary_id, key in (("close", "UPD_BTN_CLOSE"), ("cancel", "UPD_BTN_CANCEL")):
        for language in g.LANGUAGES:
            assert g.normalize(update_strings.STRINGS[language][key]) == g.normalize(by_id[glossary_id]["text"][language]), (glossary_id, language)
