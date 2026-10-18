# =============================================================================
# URTC-COMMON - tests/test_ui.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""urtc_ui: the shared language list, status badges and formatting helpers (no Qt needed)."""
from __future__ import annotations

import pytest

import urtc_ui
from urtc_common import protocol as p
from urtc_ui import (Level, LanguageModel, badge_for, connection_badge, format_bitrate, format_bytes, format_can_id,
                     format_duration_ms, format_frame, format_hex, format_uptime, normalize_language, parse_bitrate, parse_can_id)


def test_the_package_imports_no_qt():
    for module in (urtc_ui, urtc_ui.languages, urtc_ui.status, urtc_ui.formatting):
        code = [line for line in open(module.__file__, encoding="utf-8").read().splitlines() if line.startswith(("import ", "from "))]
        assert not [line for line in code if "PySide" in line or "PyQt" in line], module.__name__


def test_there_are_eight_languages_with_unique_codes():
    codes = [c for c, _ in urtc_ui.LANGUAGES]
    assert len(codes) == 8 == len(set(codes)) and codes[0] == "english"
    assert dict(urtc_ui.LANGUAGES)["portuguese"] == "Português"


def test_normalize_language():
    assert normalize_language("german") == "german"
    assert normalize_language("pt_PT") == "portuguese" and normalize_language("pt-BR") == "portuguese"
    assert normalize_language("zh_CN.UTF-8") == "chinese" and normalize_language("JA") == "japanese"
    assert normalize_language("klingon") == "english" and normalize_language(None) == "english" and normalize_language("") == "english"


def test_language_model_selects_by_position():
    model = LanguageModel("fr")
    assert model.current == "french" and model.names()[model.index()] == "Français"
    assert model.choose(model.index()) is None
    assert model.choose(4) == "german" and model.current == "german"
    for bad in (-1, 8, True, "1", None):
        assert model.code_at(bad) is None and model.choose(bad) is None
    assert model.current == "german"


def test_badges():
    assert badge_for("OK").level is Level.OK and badge_for("nonsense").level is Level.UNKNOWN
    assert badge_for(Level.ERROR).key == "STATUS_ERROR"
    assert len({badge_for(l).colour for l in Level}) == len(Level)
    assert connection_badge(None).level is Level.UNKNOWN
    assert connection_badge(False).key == "STATUS_DISCONNECTED"
    assert connection_badge(True, listening_only=True).key == "STATUS_LISTEN_ONLY"
    assert connection_badge(True).key == "STATUS_CONNECTED"


def test_can_id_formatting_and_parsing_round_trip():
    assert format_can_id(0x1A0) == "0x1A0" and format_can_id(0x7FF) == "0x7FF"
    assert format_can_id(0x123, extended=True) == "0x00000123"
    for text, value in (("0x1a0", 0x1A0), ("1A0h", 0x1A0), ("416", 416)):
        assert parse_can_id(text) == value
    for bad in (-1, 0x800, True, "x"):
        with pytest.raises(ValueError):
            format_can_id(bad)
    for bad in ("0x800", "zz", "", "0x"):
        with pytest.raises(ValueError):
            parse_can_id(bad)
    assert parse_can_id("0x800", extended=True) == 0x800


def test_frame_formatting():
    assert format_hex(b"\x01\xab") == "01 AB" and format_hex(b"") == ""
    assert format_frame(0x120, bytes([1, 2, 3])) == "0x120#01 02 03"


def test_bitrate_labels_match_the_slcan_table():
    for label, _code in p.SLCAN_BITRATES:
        assert format_bitrate(parse_bitrate(label)) == label
    assert format_bitrate(500000) == "500 kbit/s" and format_bitrate(1000000) == "1 Mbit/s" and format_bitrate(800) == "800 bit/s"
    assert parse_bitrate("500k") == 500000 and parse_bitrate("1 Mbps") == 1000000 and parse_bitrate("125000") == 125000
    for bad in ("fast", "0", "-5k", "1.5"):
        with pytest.raises(ValueError):
            parse_bitrate(bad)
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            format_bitrate(bad)


def test_sizes_and_durations():
    assert format_bytes(0) == "0 B" and format_bytes(1023) == "1023 B" and format_bytes(1536) == "1.5 KiB"
    assert format_bytes(5 * 1024 * 1024) == "5.0 MiB"
    assert format_duration_ms(250) == "250 ms" and format_duration_ms(2500) == "2.5 s" and format_duration_ms(3000) == "3 s"
    assert format_duration_ms(125000) == "2 min 5 s" and format_duration_ms(120000) == "2 min"
    assert format_uptime(0) == "0 s" and format_uptime(59) == "59 s" and format_uptime(3725) == "1 h 2 min" and format_uptime(90000) == "1 d 1 h"
    for func in (format_bytes, format_duration_ms, format_uptime):
        with pytest.raises(ValueError):
            func(-1)
