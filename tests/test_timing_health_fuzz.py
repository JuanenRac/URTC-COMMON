# =============================================================================
# URTC-COMMON - tests/test_timing_health_fuzz.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The bit timing and the bus-health judgement over many generated inputs (a fixed seed, so a failure repeats): what must hold for every clock, rate and counter."""
from __future__ import annotations

import random

import pytest

from urtc_common import bus_health as bh
from urtc_common import can_timing as ct

SEED = 20261112


def _clock_and_rate_cases(count: int = 400):
    rng = random.Random(SEED)
    clocks = [8_000_000, 16_000_000, 24_000_000, 32_000_000, 36_000_000, 48_000_000, 64_000_000, 72_000_000, 80_000_000]
    rates = [10_000, 20_000, 50_000, 100_000, 125_000, 250_000, 500_000, 800_000, 1_000_000]
    for _ in range(count):
        yield rng.choice(clocks), rng.choice(rates), rng.randrange(500, 901), rng.randrange(0, 7)


def test_every_timing_that_is_found_is_exact_and_within_the_limits_of_the_controller():
    found = 0
    for clock, rate, sample, sjw in _clock_and_rate_cases():
        timing = ct.compute(clock, rate, sample, sjw)
        if timing is None:
            continue
        found += 1
        assert timing.rate(clock) == rate and clock % (rate * timing.total_tq) == 0
        assert 1 <= timing.prescaler <= 1024 and 8 <= timing.total_tq <= 25
        assert 1 <= timing.bs1 <= 16 and 1 <= timing.bs2 <= 8
        assert 1 <= timing.sjw <= min(4, timing.bs2)
    assert found > 100      # the generated cases are not all impossible ones


def test_the_search_is_deterministic_and_does_not_depend_on_the_order_of_the_calls():
    cases = list(_clock_and_rate_cases(120))
    first = [ct.compute(*case) for case in cases]
    second = [ct.compute(*case) for case in reversed(cases)][::-1]
    assert first == second


def test_the_sample_point_stays_close_to_the_wanted_one_when_there_is_room():
    for clock, rate, sample, sjw in _clock_and_rate_cases():
        timing = ct.compute(clock, rate, sample, sjw)
        if timing is not None and timing.total_tq >= 16:
            assert abs(timing.sample_permille - sample) <= 200, (clock, rate, sample, timing)


def test_the_tolerance_is_never_negative_and_a_longer_resynchronisation_never_lowers_it():
    for clock, rate, sample, _sjw in _clock_and_rate_cases():
        narrow = ct.compute(clock, rate, sample, 1)
        wide = ct.compute(clock, rate, sample, 4)
        if narrow is None or wide is None:
            assert narrow is None and wide is None
            continue
        assert narrow.tolerance_ppm >= 0 and wide.tolerance_ppm >= narrow.tolerance_ppm


@pytest.mark.parametrize("clock, rate, sample", [(0, 1_000_000, 875), (-1, 1_000_000, 875), (32_000_000, 0, 875), (32_000_000, -5, 875),
                                                 (32_000_000, 1_000_000, 499), (32_000_000, 1_000_000, 901), (7, 1_000_000, 875), (32_000_000, 33_000_000, 875)])
def test_impossible_inputs_give_no_timing_and_never_raise(clock, rate, sample):
    assert ct.compute(clock, rate, sample) is None


def test_a_table_has_one_row_per_clock_and_rate_whatever_the_clocks():
    rng = random.Random(SEED)
    clocks = {f"clock {i}": rng.choice([0, 3, 8_000_000, 32_000_000, 48_000_000]) for i in range(8)}
    rows = ct.table(clocks)
    assert len(rows) == len(clocks) * 2
    for row in rows:
        if row["timing"] is not None:
            assert row["actual"] == row["bitrate"] and row["error_ppm"] == 0


def test_the_mixed_rate_warning_only_depends_on_the_set_of_known_rates():
    rng = random.Random(SEED)
    for _ in range(200):
        rates = [rng.choice([0, 125_000, 500_000, 1_000_000]) for _ in range(rng.randrange(0, 7))]
        warning = ct.mixed_rate_warning(rates)
        shuffled = rates[:]
        rng.shuffle(shuffled)
        assert warning == ct.mixed_rate_warning(shuffled)
        assert (warning is not None) == (len({r for r in rates if r}) > 1)


# ---- bus health --------------------------------------------------------------------------------------------------------------------------------

def _profiles(rng: random.Random):
    return [{"tec": rng.randrange(0, 256), "rec": rng.randrange(0, 256), "bus_off_count": rng.randrange(0, 4)} for _ in range(rng.randrange(0, 6))]


def test_the_codes_are_always_known_unique_and_most_serious_first():
    rng = random.Random(SEED)
    for _ in range(500):
        found = bh.warnings(_profiles(rng), rng.random() < 0.5, [rng.choice(["a", "b", 7]) for _ in range(rng.randrange(0, 3))],
                            bh.Thresholds(legacy_heads=("a", "7")))
        assert set(found) <= set(bh.CODES) and len(found) == len(set(found))
        assert found == sorted(found, key=bh.CODES.index)


def test_more_errors_never_remove_a_warning():
    rng = random.Random(SEED)
    for _ in range(300):
        profiles = _profiles(rng)
        worse = [{"tec": min(255, p["tec"] + 10), "rec": min(255, p["rec"] + 10), "bus_off_count": p["bus_off_count"] + 1} for p in profiles]
        before = bh.warnings(profiles, heads_on_bus=["a"], thresholds=bh.Thresholds(legacy_heads=("a",)))
        after = bh.warnings(worse, heads_on_bus=["a"], thresholds=bh.Thresholds(legacy_heads=("a",)))
        assert set(before) <= set(after)


def test_a_threshold_from_any_configuration_is_inside_the_limits():
    rng = random.Random(SEED)
    junk = [None, True, False, 0, -3, 1, 96, 255, 256, 10**9, 1.5, "96", [], {}, (1,), float("nan")]
    for _ in range(300):
        section = {key: rng.choice(junk) for key in ("tec_warn", "rec_warn", "bus_off_warn") if rng.random() < 0.8}
        if rng.random() < 0.5:
            section["legacy_heads"] = rng.choice([None, "a", ["a", 3, None, True, [1], "b"], 5, {}])
        limits = bh.thresholds_from_config(section)
        for value in (limits.tec_warn, limits.rec_warn, limits.bus_off_warn):
            assert isinstance(value, int) and bh.LIMITS[0] <= value <= bh.LIMITS[1]
        assert all(isinstance(name, str) for name in limits.legacy_heads)


@pytest.mark.parametrize("section", [None, 5, "x", [], (), 1.5, True])
def test_a_section_that_is_not_a_table_gives_the_defaults(section):
    assert bh.thresholds_from_config(section) == bh.Thresholds()


def test_the_frames_that_are_too_short_are_dropped_and_the_others_keep_their_order():
    rng = random.Random(SEED)
    frames = [bytes(rng.randrange(256) for _ in range(rng.randrange(0, 9))) for _ in range(200)]
    profiles = bh.profiles_from_frames(frames)
    assert len(profiles) == sum(1 for frame in frames if len(frame) >= 3)
    kept = [frame for frame in frames if len(frame) >= 3]
    assert [(p["tec"], p["rec"], p["bus_off_count"]) for p in profiles] == [tuple(frame[:3]) for frame in kept]


class _Bus:
    def __init__(self, frames):
        self.frames = list(frames)

    def read_frame(self, timeout=0.0):
        return self.frames.pop(0) if self.frames else None


def test_the_tap_keeps_only_the_health_frames_and_never_more_than_it_was_asked_to():
    rng = random.Random(SEED)
    frames = [(rng.choice([0x1B8, 0x1B8, 0x100, 0x7EA]), bytes([i % 256, 0, 0])) for i in range(300)]
    bus = _Bus(frames)
    tap = bh.HealthTap(bus, keep=16)
    seen = []
    while True:
        frame = bus.read_frame(0.0)
        if frame is None:
            break
        seen.append(frame)
    assert seen == frames                       # the tap changes nothing of what the caller reads
    taken = tap.take()
    health = [data for can_id, data in frames if can_id == 0x1B8]
    assert taken == health[-16:] and tap.take() == []
    tap.release()


def test_a_tap_over_a_bus_with_no_reader_never_touches_it():
    class Silent:
        pass
    bus = Silent()
    tap = bh.HealthTap(bus)
    assert not hasattr(bus, "read_frame") and tap.take() == []
    tap.release()
    assert not hasattr(bus, "read_frame")
