"""The frame layer and the rate limiter of the serial links of the tool rack and of the vision sensor: the reference of the C headers
``firmware_base/urtc_frame.h`` and ``firmware_base/urtc_rate_limiter.h``.

Both links frame a message the same way (start byte, version, header fields, payload length, payload, CRC-8 of everything before
it) and differ in where the length byte sits. ``validate`` decides whether a buffer holds one good frame, in the order the C code
decides it; ``RateLimiter`` is the minimum interval between accepted messages, right across the wrap of the 32-bit millisecond
counter. The vectors of the rate limiter (``conformance/rate_vectors.json``, ``generated/rate_vectors.h``) are produced from
this module, and the existing parse vectors of the rack and of the sensor are checked against it by the tests, so the C headers,
this module and both repositories cannot drift apart unnoticed.

Standard library only. Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
"""
from __future__ import annotations

from dataclasses import dataclass

STATUSES = ("ok", "incomplete", "bad_sof", "unsupported_version", "length_out_of_range", "crc_mismatch")
WRAP = 1 << 32


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class FrameFormat:
    sof: int
    version: int
    length_index: int  # position of the payload length byte; the header ends there
    max_payload: int

    @property
    def header_size(self) -> int:
        return self.length_index + 1

    def total_size(self, payload_len: int) -> int:
        return self.header_size + payload_len + 1


RACK = FrameFormat(sof=0xA5, version=2, length_index=4, max_payload=16)
SENSOR = FrameFormat(sof=0xB6, version=2, length_index=8, max_payload=16)


def validate(fmt: FrameFormat, buf: bytes) -> tuple[str, int]:
    """(status, total length). The length is 0 unless the status is ``ok``; bytes after the frame are not looked at."""
    if len(buf) < fmt.total_size(0):
        return "incomplete", 0
    if buf[0] != fmt.sof:
        return "bad_sof", 0
    if buf[1] != fmt.version:
        return "unsupported_version", 0
    payload_len = buf[fmt.length_index]
    if payload_len > fmt.max_payload:
        return "length_out_of_range", 0
    covered = fmt.header_size + payload_len
    if len(buf) < covered + 1:
        return "incomplete", 0
    if crc8(buf[:covered]) != buf[covered]:
        return "crc_mismatch", 0
    return "ok", covered + 1


def seal(fmt: FrameFormat, body: bytes) -> bytes:
    """The frame for a buffer that holds the header and the payload: the CRC-8 of everything is appended."""
    return bytes(body) + bytes([crc8(body)])


class RateLimiter:
    """The minimum interval between two accepted messages, decided with the counter the caller passes in."""

    def __init__(self, min_interval_ms: int) -> None:
        self.min_interval_ms = min_interval_ms
        self.last_accept_ms = 0
        self.has_accepted_any = False

    def allow(self, now_ms: int) -> bool:
        now_ms %= WRAP
        if not self.has_accepted_any:
            self.last_accept_ms = now_ms
            self.has_accepted_any = True
            return True
        if (now_ms - self.last_accept_ms) % WRAP < self.min_interval_ms:
            return False
        self.last_accept_ms = now_ms
        return True


RATE_CASES = (
    ("the first message is always accepted", 100, (0,)),
    ("inside the interval refused, at the interval accepted", 100, (0, 50, 99, 100, 150, 199, 200)),
    ("a refused message does not move the window", 100, (1000, 1099, 1100, 1150, 1200)),
    ("an interval of zero accepts everything", 0, (5, 5, 5, 6)),
    ("across the wrap of the millisecond counter", 100, (0xFFFFFFF0, 0x00000010, 0x00000053, 0x00000054)),
    ("the largest interval", 0xFFFFFFFF, (0, 0xFFFFFFFE, 0xFFFFFFFF)),
    ("a clock that goes backwards counts as a long time ago", 10, (1000, 900)),
)


def rate_vectors() -> dict:
    cases = []
    for name, interval, times in RATE_CASES:
        limiter = RateLimiter(interval)
        cases.append({"name": name, "min_interval_ms": interval, "times_ms": list(times), "allowed": [limiter.allow(t) for t in times]})
    return {"format": 1, "about": "Decisions of the minimum-interval limiter of a link; the C header and the reference module both pass them.", "cases": cases}
