# =============================================================================
# URTC-COMMON - src/urtc_common/can_timing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The bit timing of the CAN bus of the tool heads, from the one specification of the bit rate (spec/can_protocol.json).

The heads run at 1 Mbit/s (``BITRATE``); 500 kbit/s (``BITRATE_LEGACY``) stays as the documented option for early boards. This module is the Python reference of
``src/F303-master/can_bit_timing.h`` of the firmware repository: the same search, so the table below is what the firmware computes from the clock of each chip. A
timing is accepted only when its rate is EXACT (an error of 0 ppm from the clock of the chip) and its sample point is not below ``CAN_SAMPLE_POINT_MIN_PERMILLE``.

Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import protocol as p

BITRATE_DEFAULT = p.BITRATE
BITRATE_LEGACY = p.BITRATE_LEGACY
SAMPLE_POINT_PERMILLE = p.CAN_SAMPLE_POINT_PERMILLE
SAMPLE_POINT_MIN_PERMILLE = p.CAN_SAMPLE_POINT_MIN_PERMILLE
SJW_TQ = p.CAN_SJW_TQ

# The clock of the CAN peripheral of each chip family the heads use (Hz). The master and the bootloader of the master run it from APB1 at 32 MHz; the other
# entries are the clocks the calculation is also held to, so a board with another clock still gets an exact timing.
PERIPHERAL_CLOCKS_HZ = {
    "STM32F303 master and its bootloader (APB1)": 32_000_000,
    "36 MHz peripheral clock": 36_000_000,
    "48 MHz peripheral clock": 48_000_000,
    "64 MHz peripheral clock": 64_000_000,
}

# What the bus can be, by the rate: the longest trunk in metres that the usual guidance gives and the number of terminations (a 120 ohm resistor at each end).
# At 1 Mbit/s the trunk is short and the stubs of every head have to be short too; at 500 kbit/s there is more room. They are guidance, not a measurement.
BUS_LIMITS = {
    1_000_000: {"max_trunk_m": 25, "max_stub_m": 0.3, "terminations": 2},
    500_000: {"max_trunk_m": 100, "max_stub_m": 0.6, "terminations": 2},
}


@dataclass(frozen=True)
class Timing:
    prescaler: int
    bs1: int
    bs2: int
    sjw: int

    @property
    def total_tq(self) -> int:
        return 1 + self.bs1 + self.bs2

    def rate(self, pclk_hz: int) -> int:
        return pclk_hz // (self.prescaler * self.total_tq)

    @property
    def sample_permille(self) -> int:
        return (1000 * (1 + self.bs1)) // self.total_tq

    @property
    def tolerance_ppm(self) -> int:
        """The largest oscillator error either way that the two conditions of the CAN specification allow (the one the firmware prints as its tolerance)."""
        n = self.total_tq
        df1 = (self.sjw * 1_000_000) // (20 * n)
        d2 = 2 * (13 * n - self.bs2)
        df2 = (min(self.bs1, self.bs2) * 1_000_000) // d2 if d2 else 0
        return min(df1, df2)


def compute(pclk_hz: int, bitrate_bps: int, sample_permille: int = SAMPLE_POINT_PERMILLE, sjw_tq: int = SJW_TQ) -> Timing | None:
    """The exact timing with the most time quanta whose sample point is the closest to the wanted one, or None when none gives this rate from this clock.

    The same search as ``urtc_can_bt_compute`` of the firmware: 25 down to 8 quanta, an exact divisor of the clock, the segments from the sample point."""
    if pclk_hz <= 0 or bitrate_bps <= 0 or not 500 <= sample_permille <= 900:
        return None
    best: tuple[int, int, int, int, int] | None = None   # error, tq, prescaler, bs1, bs2
    for tq in range(25, 7, -1):
        denominator = bitrate_bps * tq
        if pclk_hz % denominator:
            continue
        prescaler = pclk_hz // denominator
        if not 1 <= prescaler <= 1024:
            continue
        bs2 = min(8, max(1, (tq * (1000 - sample_permille) + 500) // 1000))
        if tq < 1 + bs2 + 1:
            continue
        bs1 = tq - 1 - bs2
        if not 1 <= bs1 <= 16:
            continue
        error = abs((1000 * (1 + bs1)) // tq - sample_permille)
        if best is None or error < best[0] or (error == best[0] and tq > best[1]):
            best = (error, tq, prescaler, bs1, bs2)
    if best is None:
        return None
    _error, _tq, prescaler, bs1, bs2 = best
    return Timing(prescaler, bs1, bs2, min(max(sjw_tq, 1), 4, bs2))


def table(clocks: dict[str, int] | None = None, rates: tuple[int, ...] = (BITRATE_DEFAULT, BITRATE_LEGACY)) -> list[dict]:
    """One row per clock and rate: the timing, the rate it really gives, the error of that rate in ppm, the sample point and the tolerance."""
    rows = []
    for name, clock in (PERIPHERAL_CLOCKS_HZ if clocks is None else clocks).items():
        for rate in rates:
            timing = compute(clock, rate)
            if timing is None:
                rows.append({"clock": name, "pclk_hz": clock, "bitrate": rate, "timing": None})
                continue
            actual = timing.rate(clock)
            rows.append({"clock": name, "pclk_hz": clock, "bitrate": rate, "timing": timing, "actual": actual,
                         "error_ppm": (actual - rate) * 1_000_000 // rate, "sample_permille": timing.sample_permille, "tolerance_ppm": timing.tolerance_ppm})
    return rows


def mixed_rate_warning(rates: list[int]) -> str | None:
    """The warning a tool shows when the heads it found do not all speak at the same rate, or None. ``rates`` are the bit rates the heads state; an unknown one is skipped."""
    known = sorted({r for r in rates if r})
    if len(known) <= 1:
        return None
    return "mixed_bitrates: " + ", ".join(f"{r // 1000} kbit/s" for r in known)
