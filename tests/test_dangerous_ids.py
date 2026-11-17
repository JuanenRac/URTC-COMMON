# =============================================================================
# URTC-COMMON - tests/test_dangerous_ids.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The rule that tells which identifiers a host must not send without being sure, over the real table of the protocol and over small tables of its own."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from urtc_common import protocol
from urtc_common.dangerous_ids import dangerous_reason

TABLE = protocol.MESSAGES


def test_the_identifiers_that_change_what_a_board_is_are_dangerous():
    for can_id in (0x7F0, 0x7F1, 0x7F2, 0x7F4, 0x7EA, 0x192, 0x1A0, 0x1AE, 0x1B9, 0x210, 0x211, 0x21A, 0x7FD):
        assert dangerous_reason(can_id, TABLE), hex(can_id)


def test_a_question_changes_nothing_whatever_its_group():
    assert dangerous_reason(0x7F8, TABLE) is None   # QUERY_VERSION is in the bootloader group
    assert dangerous_reason(0x7FB, TABLE) is None   # QUERY_ERROR_COUNTERS


def test_an_identifier_the_specification_does_not_know_is_not_judged():
    assert dangerous_reason(0x7FF + 1, TABLE) is None
    assert dangerous_reason(0x001, {}) is None


def test_the_reason_names_what_the_identifier_does():
    assert "magic" in dangerous_reason(0x192, TABLE)
    assert "bootloader" in dangerous_reason(0x7F1, TABLE)
    assert "setting" in dangerous_reason(0x1B9, TABLE)


def test_the_rule_on_a_small_table():
    table = {
        1: {"name": "SET_X", "group": "configuration"},
        2: {"name": "QUERY_X", "group": "bootloader"},
        3: {"name": "MOVE", "group": "motion"},
        4: {"name": "ERASE", "group": "global", "gates": {"needs_magic": "erase"}},
        5: {"name": "UPDATE", "group": "slave_bridge"},
        6: {"name": "PID_CONFIG", "group": "configuration"},
    }
    assert [dangerous_reason(i, table) is not None for i in (1, 2, 3, 4, 5, 6)] == [True, False, False, True, True, True]
