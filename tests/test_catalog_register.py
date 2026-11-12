# =============================================================================
# URTC-COMMON - tests/test_catalog_register.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The register of the texts of the catalogs: German and French address the reader formally (Sie, vous), Portuguese in the third person (você), Spanish and Italian informally (tu),
Chinese with 你. A text that slips into another register is found here, so it is fixed in the catalog and not in a copy."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CATALOGS = Path(__file__).resolve().parents[1] / "spec" / "i18n" / "catalog"

# case matters: STEP/DIR/EN is a signal name, "Dir" at the start of a sentence is the pronoun
FORBIDDEN = {
    "german": re.compile(r"\b(du|Du|dich|Dich|dein\w*|Dein\w*|dir|Dir|euch|Euch)\b"),
    "french": re.compile(r"\b(tu|Tu|toi|Toi|ton|Ton|tes|Tes)\b"),
    "portuguese": re.compile(r"\b(tu|Tu|teu|Teu|tua|Tua|teus|tuas|contigo)\b"),
    "spanish": re.compile(r"\b(usted|Usted|ustedes|Ustedes)\b"),
    "chinese": re.compile("您"),
}


def _entries():
    for path in sorted(CATALOGS.glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
            if isinstance(entry.get("text"), dict):
                yield path.name, entry["key"], entry["text"]


@pytest.mark.parametrize("language", sorted(FORBIDDEN))
def test_no_text_slips_into_another_register(language):
    wrong = []
    for name, key, texts in _entries():
        text = texts.get(language)
        if isinstance(text, str) and FORBIDDEN[language].search(text):
            wrong.append(f"{name}:{key}")
    assert wrong == [], wrong[:10]


def test_german_and_french_do_use_the_formal_form_somewhere():
    german = [t["german"] for _n, _k, t in _entries() if "german" in t]
    french = [t["french"] for _n, _k, t in _entries() if "french" in t]
    assert any(re.search(r"\b(Sie|Ihre|Ihr|Ihnen)\b", text) for text in german)
    assert any(re.search(r"\bvous|votre|vos\b", text) for text in french)


def test_every_text_of_every_language_is_non_empty_and_has_the_same_placeholders_as_english():
    problems = []
    for name, key, texts in _entries():
        reference = sorted(re.findall(r"\{\{?\w+\}?\}", texts.get("english", "")))
        for language, text in texts.items():
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{name}:{key}:{language}: empty")
            elif sorted(re.findall(r"\{\{?\w+\}?\}", text)) != reference:
                problems.append(f"{name}:{key}:{language}: placeholders")
    assert problems == [], problems[:10]


def test_the_eight_languages_are_in_every_entry():
    expected = {"english", "spanish", "german", "french", "italian", "japanese", "chinese", "portuguese"}
    missing = [f"{name}:{key}" for name, key, texts in _entries() if set(texts) != expected]
    assert missing == [], missing[:10]
