# =============================================================================
# URTC-COMMON - tests/test_blackbox_recorder.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The model of the recorder of the firmware (``blackbox.Recorder``) and the scenarios the firmware is held to."""
from __future__ import annotations

import json
from pathlib import Path

from urtc_common import blackbox as bb

ROOT = Path(__file__).resolve().parents[1]


def vectors() -> list[dict]:
    return json.loads((ROOT / "conformance" / "blackbox_vectors.json").read_text(encoding="utf-8"))["recorder"]


def tick(recorder, n, error=False, tick_ms=None, thermal=0, endstop=False):
    return recorder.tick(1000 + n * 150 if tick_ms is None else tick_ms, 0, 300, 320, endstop, error, thermal)


def test_a_record_is_flushed_once_for_each_rising_edge_of_the_error_flag():
    r = bb.Recorder()
    assert [tick(r, i) for i in range(3)] == [None, None, None]
    first = tick(r, 3, error=True)
    assert first is not None and bb.parse(first).trigger_index == 3
    assert tick(r, 4, error=True) is None and tick(r, 5, error=True) is None  # it stays raised: no second flush
    assert tick(r, 6) is None  # the flag falls: the latch is re-armed
    assert tick(r, 7, error=True) is not None


def test_a_flushed_record_is_what_the_reader_decodes_oldest_first_before_and_after_the_wrap():
    r = bb.Recorder()
    for i in range(10):
        tick(r, i)
    record = bb.parse(tick(r, 10, error=True))
    assert record.sample_count == 11 and record.write_index == 11 and [s.tick_ms for s in record.samples] == [1000 + i * 150 for i in range(11)]
    r = bb.Recorder()
    for i in range(100):
        tick(r, i)
    record = bb.parse(tick(r, 100, error=True))
    assert record.sample_count == bb.SAMPLES and record.write_index == 101 % bb.SAMPLES
    assert [s.tick_ms for s in record.samples] == [1000 + i * 150 for i in range(101 - bb.SAMPLES, 101)]


def test_the_flags_carry_the_end_stop_the_error_and_the_thermal_guard_code():
    r = bb.Recorder()
    record = bb.parse(tick(r, 0, error=True, thermal=2, endstop=True))
    sample = record.samples[0]
    assert (sample.endstop, sample.system_error, sample.thermal_fault) == (True, True, 2) and sample.flags == 0b1011
    assert bb.parse(tick(bb.Recorder(), 0, error=True, thermal=7)).samples[0].thermal_fault == 3  # only two bits are kept


def test_the_tick_counter_is_kept_to_32_bits():
    r = bb.Recorder()
    record = bb.parse(r.tick(0x1_0000_0005, 0, 0x1_0001, 0x1_0002, False, True, 0))
    assert record.samples[0].tick_ms == 5 and record.samples[0].current_temperature == 1 and record.samples[0].target_temperature == 2


def test_the_scenarios_of_the_vectors_are_reproduced_by_the_model_and_their_records_decode():
    data = vectors()
    assert len(data) >= 7
    for scenario in data:
        model = bb.Recorder()
        flushes, last = [], None
        for index, step in enumerate(scenario["steps"]):
            record = model.tick(step["tick_ms"], step["tool_id"], step["current"], step["target"], bool(step["endstop"]), bool(step["error"]), step["thermal_code"])
            if record is not None:
                flushes.append(index)
                last = record
        assert flushes == scenario["flush_steps"], scenario["name"]
        assert (last.hex().upper() if last else None) == scenario["record"], scenario["name"]
        if last:
            assert bb.parse(last).trigger_index is not None, scenario["name"]
    assert any(len(s["flush_steps"]) == 2 for s in data) and any(s["record"] is None for s in data)


def test_the_generated_header_has_a_table_for_every_scenario():
    text = (ROOT / "generated" / "blackbox_vectors.h").read_text(encoding="utf-8")
    for n, scenario in enumerate(vectors()):
        assert f"BB_VEC_STEPS_{n}[]" in text and f"BB_VEC_FLUSH_{n}[]" in text
        assert (f"BB_VEC_RECORD_{n}[]" in text) == (scenario["record"] is not None)
