# =============================================================================
# URTC-COMMON - tests/test_update_strings.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The texts of the update window: the same keys and placeholders in the eight languages, a text for every error code."""
from __future__ import annotations

import re
from pathlib import Path

from urtc_common import self_update as su
from urtc_common import update_strings as st

ENGLISH = st.STRINGS["english"]


def placeholders(value: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", value))


def test_there_are_eight_languages_with_the_same_codes_as_the_selector():
    from urtc_ui.languages import LANGUAGES as selector

    assert set(st.STRINGS) == set(st.LANGUAGES) == {code for code, _ in selector}


def test_every_language_has_every_key_with_the_same_placeholders_and_no_empty_text():
    for language, table in st.STRINGS.items():
        assert set(table) == set(ENGLISH), language
        for key, value in table.items():
            assert value.strip(), (language, key)
            assert placeholders(value) == placeholders(ENGLISH[key]), (language, key)


def test_the_other_languages_are_translated_not_copied():
    for language, table in st.STRINGS.items():
        if language == "english":
            continue
        same = [key for key, value in table.items() if value == ENGLISH[key] and len(value) > 12]
        assert same == [], (language, same)


def test_the_portuguese_is_the_european_one():
    pt = st.STRINGS["portuguese"]
    assert "A transferir" in pt["UPD_DOWNLOADING"] and "ficheiro" in pt["UPD_ERR_CORRUPT"]
    assert "Baixando" not in " ".join(pt.values()) and "arquivo" not in " ".join(pt.values())


def test_every_error_code_the_update_raises_has_a_text():
    source = Path(su.__file__).parent
    codes = set()
    for name in ("self_update.py", "update_service.py", "launcher.py"):
        codes |= set(re.findall(r'UpdateError\("([a-z0-9_]+)"', (source / name).read_text(encoding="utf-8")))
    launcher_only = {"no_current_release", "entry_missing", "entry_outside"}  # the launcher has no window: it prints
    for code in sorted(codes - launcher_only):
        assert st.error_key(code) in ENGLISH
        if code not in {"bad_app"}:
            assert st.error_key(code) != "UPD_ERR_UNEXPECTED" or code == "unexpected", code
    assert st.error_key("something_new") == "UPD_ERR_UNEXPECTED"


def test_text_fills_the_placeholders_and_falls_back_to_english_and_to_the_key():
    assert st.text("spanish", "UPD_UP_TO_DATE", installed="0.4.1") == "Tienes la última versión (0.4.1)."
    assert st.text("klingon", "UPD_UP_TO_DATE", installed="1.0.0") == "You have the latest version (1.0.0)."
    assert st.text("english", "UPD_NO_SUCH_KEY") == "UPD_NO_SUCH_KEY"
    assert st.text("english", "UPD_AVAILABLE", version="2.0.0") == "Version 2.0.0 is available (you have {installed})."
