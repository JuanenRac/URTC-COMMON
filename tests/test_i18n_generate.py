# =============================================================================
# URTC-COMMON - tests/test_i18n_generate.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The catalog of texts and the generator of the language files: the catalogs are complete, what they generate is what the programs next to this repository ship,
and the parsing, the glossary references and the refusals work on small examples."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("i18n_generate", ROOT / "tools" / "i18n_generate.py")
gen = importlib.util.module_from_spec(spec)
sys.modules["i18n_generate"] = gen
spec.loader.exec_module(gen)

LANGUAGES = gen.LANGUAGES


def texts(value: str) -> dict[str, str]:
    return {language: f"{value} {language}" for language in LANGUAGES}


def small_catalog(kind: str = "lng", program: str = "flasher") -> dict:
    return {
        "format": 1, "program": program, "kind": kind,
        "header": {language: [f"# header {language}"] for language in LANGUAGES},
        "entries": [{"key": "A_ONE", "text": texts("one")}, {"key": "A_TWO", "text": texts("two {n}"), "before": {"english": ["# a section"]}}],
    }


@pytest.mark.parametrize("program", sorted(gen.PROGRAMS))
def test_every_catalog_is_complete_and_valid(program):
    catalog = gen.load_catalog(gen.PROGRAMS[program]["catalog"])
    assert gen.validate(catalog) == []
    assert catalog["entries"], program


@pytest.mark.parametrize("program", sorted(gen.PROGRAMS))
def test_the_programs_next_to_this_repository_ship_what_the_catalog_generates(program):
    if not (ROOT.parent / program).is_dir():
        pytest.skip(f"{program} is not next to this repository")
    assert gen.check_program(program, ROOT.parent) == []


def test_the_catalog_files_are_written_in_the_stable_form():
    for program in gen.PROGRAMS.values():
        path = gen.CATALOGS / f"{program['catalog']}.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") == gen.dump_catalog(catalog), path.name


def test_a_glossary_text_is_a_reference_and_follows_the_glossary():
    glossary = {"close": texts("Close")}
    catalog = small_catalog()
    catalog["entries"].append({"key": "A_CLOSE", "glossary": "close"})
    assert gen.validate(catalog, glossary) == []
    lines = gen.generate(catalog, glossary)["language/german.lng"].decode("utf-8").splitlines()
    assert "A_CLOSE=Close german" in lines
    glossary["close"]["german"] = "Schliessen"
    assert "A_CLOSE=Schliessen" in gen.generate(catalog, glossary)["language/german.lng"].decode("utf-8").splitlines()


def test_a_lng_file_has_the_header_the_comment_before_a_key_and_a_line_break_written_as_backslash_n():
    catalog = small_catalog()
    catalog["entries"][0]["text"]["english"] = r"first\nsecond"
    out = gen.generate(catalog, {})["language/english.lng"].decode("utf-8")
    assert out.splitlines()[:3] == ["# header english", "", r"A_ONE=first\nsecond"]
    assert out.splitlines()[3:5] == ["", "# a section"] and out.endswith("\n") and "\r" not in out
    assert "# a section" not in gen.generate(catalog, {})["language/german.lng"].decode("utf-8")


def test_a_json_file_is_nested_by_the_dots_of_the_keys():
    catalog = {"format": 1, "program": "web-studio", "kind": "json", "entries": [{"key": "app.title", "text": texts("T")}, {"key": "app.sub.x", "text": texts("X")}, {"key": "b", "text": texts("B")}]}
    files = gen.generate(catalog, {})
    tree = json.loads(files["src/locales/es.json"])
    assert tree == {"app": {"title": "T spanish", "sub": {"x": "X spanish"}}, "b": "B spanish"}
    assert "src/locales/generated.test.ts" in files and "tests/test_i18n_generated.py" not in files


def test_the_table_of_the_updater_is_a_python_file_that_holds_the_eight_languages():
    catalog = {"format": 1, "program": "updater", "kind": "py", "entries": [{"key": "k", "text": {language: f'a "{language}"\nb' for language in LANGUAGES}}]}
    files = gen.generate(catalog, {})
    source = files["src/urtc_updater/translations_data.py"].decode("utf-8")
    scope: dict = {}
    exec(compile(source, "translations_data.py", "exec"), scope)
    assert sorted(scope["TRANSLATIONS"]) == sorted(gen.CODES.values())
    assert scope["TRANSLATIONS"]["de"]["k"] == 'a "german"\nb' and "tests/test_i18n_generated.py" in files


def test_a_line_after_a_key_without_an_equals_sign_is_the_rest_of_its_value_and_one_after_a_blank_is_dropped():
    raw = b"# head\n\nKEY_A=first\r\nsecond\nKEY_B=x\n\nlost line\nKEY_C=y\n"
    header, entries, dropped = gen.parse_lng(raw)
    assert header == ["# head"] and [e["key"] for e in entries] == ["KEY_A", "KEY_B", "KEY_C"]
    assert entries[0]["value"] == r"first\nsecond" and dropped == ["lost line"]


def test_the_catalog_refuses_what_would_ship_a_broken_text():
    catalog = small_catalog()
    catalog["entries"][1]["text"]["french"] = "deux"          # a placeholder missing
    del catalog["entries"][0]["text"]["japanese"]               # a language missing
    catalog["entries"].append({"key": "A_ONE", "text": texts("again")})  # a key twice
    catalog["entries"].append({"key": "A_GLOSS", "glossary": "nothing"})
    catalog["entries"].append({"key": "A_BREAK", "text": texts("a\nb")})
    problems = " | ".join(gen.validate(catalog, {}))
    for expected in ("different placeholders", "japanese", "listed twice", "unknown glossary entry nothing", "real line break"):
        assert expected in problems, problems


def test_a_file_edited_by_hand_is_found(tmp_path):
    program = "URTC-TESTER"
    (tmp_path / program).mkdir()
    gen.sync(program, tmp_path)
    assert gen.check_program(program, tmp_path) == []
    target = tmp_path / program / "language" / "german.lng"
    target.write_text(target.read_text(encoding="utf-8") + "EXTRA=1\n", encoding="utf-8")
    problems = gen.check_program(program, tmp_path)
    assert any("german.lng is not what the catalog generates" in problem for problem in problems)



def test_the_program_side_test_passes_in_a_synced_folder_and_fails_after_an_edit(tmp_path):
    import subprocess

    program = "URTC-FLASHER"
    (tmp_path / program).mkdir()
    gen.sync(program, tmp_path)
    run = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path / program / "tests" / "test_i18n_generated.py")]
    assert subprocess.run(run, capture_output=True, text=True, check=False).returncode == 0
    target = tmp_path / program / "language" / "english.lng"
    target.write_text(target.read_text(encoding="utf-8") + "EXTRA=1\n", encoding="utf-8")
    result = subprocess.run(run, capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "english.lng differs from the lock" in result.stdout
