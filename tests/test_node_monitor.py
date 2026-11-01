# =============================================================================
# URTC-COMMON - tests/test_node_monitor.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Whose a frame is on a bus with several tool heads, and how much of the bus each node uses."""
from __future__ import annotations

import pytest

from urtc_common import node_monitor as nm
from urtc_common import protocol as p
from urtc_common.multinode import frame_bits


def test_the_node_of_every_extension_frame_is_in_its_identifier():
    assert nm.owner(p.MN_ID_NODE_INFO_BASE + 7) == ("NODE_INFO", 7)
    assert nm.owner(p.MN_ID_NODE_STATUS_BASE + 31) == ("NODE_STATUS", 31)
    assert nm.owner(p.MN_ID_NODE_CMD_BASE) == ("NODE_CMD", 0)
    assert nm.owner(p.MN_ID_NODE_RESP_BASE + 5) == ("NODE_RESP", 5)


def test_the_frames_of_the_host_to_every_node_and_the_single_head_frames_have_no_node():
    for identifier, kind in ((p.MN_ID_DISCOVER, "DISCOVER"), (p.MN_ID_SELECT, "SELECT"), (p.MN_ID_SAFE_STOP, "SAFE_STOP")):
        assert nm.owner(identifier) == (kind, None)
    for identifier in (0x110, 0x130, 0x7F8, 0x255, 0x3FF, 0x41F, 0x4A0, 0x7FF):
        assert nm.owner(identifier) == ("SINGLE", None), hex(identifier)


def test_every_identifier_of_the_extension_is_classified_and_none_outside_it():
    for base, count in p.MN_RANGES.items():
        assert nm.owner(base)[0] == p.MN_NAMES[base] and nm.owner(base + count - 1)[0] == p.MN_NAMES[base]
        assert nm.owner(base + count)[0] != p.MN_NAMES[base] or count == 1


def test_labels_and_node_filters():
    assert nm.label(7) == "N07" and nm.label(None) == ""
    assert nm.parse_nodes("n5, N07 12 n99 nx n-1 n31") == {5, 7, 31}
    assert nm.parse_nodes("") == set()


class Clock:
    now = 100.0

    def __call__(self) -> float:
        return self.now


def test_the_frames_are_counted_for_their_node_and_the_load_is_the_bits_over_the_bitrate():
    clock = Clock()
    stats = nm.NodeBusStats(window_s=1.0, clock=clock)
    for _ in range(10):
        assert stats.note(p.MN_ID_NODE_STATUS_BASE + 3, bytes(4)) == 3
    rows = stats.snapshot(500_000)
    assert len(rows) == 1 and rows[0]["node"] == 3 and rows[0]["frames_per_s"] == 10.0
    assert rows[0]["load_percent"] == pytest.approx(100.0 * 10 * frame_bits(4) / 500_000)
    assert rows[0]["kinds"] == {"NODE_STATUS": 10}


def test_a_single_head_frame_belongs_to_the_selected_node_once_a_status_frame_says_which():
    clock = Clock()
    stats = nm.NodeBusStats(window_s=5.0, clock=clock)
    assert stats.note(0x110, b"") is None                                           # nobody is known to be selected yet
    stats.note(p.MN_ID_NODE_STATUS_BASE + 4, bytes([p.MN_STATE_SELECTED, 0, 0, 9]))
    assert stats.selected == 4 and stats.note(0x110, b"") == 4
    stats.note(p.MN_ID_NODE_STATUS_BASE + 4, bytes([0, 0, 0, 10]))                  # it says it is no longer selected
    assert stats.selected is None and stats.note(0x110, b"") is None
    rows = stats.snapshot()
    assert [row["node"] for row in rows] == [4, None]
    assert rows[0]["kinds"]["SINGLE"] == 1 and rows[1]["kinds"]["SINGLE"] == 2


def test_old_frames_leave_the_window_and_the_summary_has_no_words_of_a_language():
    clock = Clock()
    stats = nm.NodeBusStats(window_s=1.0, clock=clock)
    stats.note(p.MN_ID_NODE_INFO_BASE + 1, bytes(8))
    clock.now += 2.0
    assert stats.snapshot() == []
    stats.note(p.MN_ID_NODE_STATUS_BASE + 12, bytes(4))
    stats.note(0x7F8, b"")
    lines = stats.summary_lines(500_000)
    assert lines[0].startswith("N12") and "NODE_STATUS 1" in lines[0] and lines[1].startswith("--")
