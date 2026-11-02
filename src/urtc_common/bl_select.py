# =============================================================================
# URTC-COMMON - src/urtc_common/bl_select.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Addressing one bootloader by its serial number on a bus that has several: the host reference of ``firmware_base/urtc_bl_select.h``.

[FIRMWARE] The bootloader side is designed and tested on the host only; no board runs it. See ``docs/BOOTLOADER_AUTH.md``.

The serial number is 32 bits folded from the 96-bit unique ID of the STM32 (the same fold the application uses for its multinode serial). A bootloader that
has no valid serial (blank or all ones) takes no part and answers as before. A bootloader that hears a command on ``0x7EA`` switches to *addressed mode*:
from then on it obeys the single-head bootloader frames (``0x7F0`` to ``0x7FF``) only while it is selected. Selection lapses after ``SELECT_LAPSE_MS``
unless it is repeated, except while an update runs; addressed mode lapses after ``ADDRESSED_LAPSE_MS`` without a command, which gives the single-head behaviour
back to a host that went away.

The identifiers ``0x7EA`` to ``0x7ED`` are PROPOSED: they are free in ``spec/can_protocol.json`` but are not written into it until the owner confirms the block.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ID_CMD = 0x7EA          # host to bootloaders
ID_RESP = 0x7EB         # bootloader to host
ID_SIG_CHUNK = 0x7EC    # host to the selected bootloader: one chunk of the signature record
ID_KEY_ID = 0x7ED       # selected bootloader to host: the identifier of a trusted key
PROPOSED_IDS = (ID_CMD, ID_RESP, ID_SIG_CHUNK, ID_KEY_ID)
LEGACY_FIRST, LEGACY_LAST = 0x7F0, 0x7FF   # the single-head bootloader commands

OP_PROBE, OP_SELECT, OP_RELEASE, OP_UID = 1, 2, 3, 4
PRESENT_MARK = 0xA5
SELECT_LAPSE_MS = 2000
ADDRESSED_LAPSE_MS = 10000
SERIAL_BLANK = (0x00000000, 0xFFFFFFFF)
_MASK = 0xFFFFFFFF


def _rotl(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (32 - bits))) & _MASK


def serial_from_uid(w0: int, w1: int, w2: int) -> int:
    """The 32-bit serial the application also reports: ``w0 ^ rotl(w1, 11) ^ rotl(w2, 22)``."""
    return (w0 ^ _rotl(w1, 11) ^ _rotl(w2, 22)) & _MASK


def serial_is_valid(serial: int) -> bool:
    return serial not in SERIAL_BLANK


def probe_frame(nbits: int, prefix: int) -> bytes:
    """Who has a serial that starts with the first ``nbits`` bits of ``prefix`` (the most significant bits)?"""
    return bytes([OP_PROBE, nbits]) + (prefix & _MASK).to_bytes(4, "big")


def select_frame(serial: int, seq: int) -> bytes:
    return bytes([OP_SELECT]) + serial.to_bytes(4, "big") + bytes([seq & 0xFF])


def release_frame() -> bytes:
    return bytes([OP_RELEASE])


def uid_frame(part: int) -> bytes:
    return bytes([OP_UID, part])


def _matches(serial: int, nbits: int, prefix: int) -> bool:
    if nbits == 0:
        return True
    shift = 32 - nbits
    return (serial >> shift) == ((prefix & _MASK) >> shift)


@dataclass
class BootloaderNode:
    """The model of one bootloader (and the behaviour ``urtc_bl_select.h`` implements)."""

    uid: tuple[int, int, int]
    addressed: bool = False
    selected: bool = False
    last_cmd_ms: int = 0
    select_ms: int = 0
    serial: int = field(init=False)

    def __post_init__(self) -> None:
        self.serial = serial_from_uid(*self.uid)

    def _lapse(self, now_ms: int, busy: bool) -> None:
        if busy:
            return
        if self.addressed and ((now_ms - self.last_cmd_ms) & _MASK) > ADDRESSED_LAPSE_MS:
            self.addressed = False
            self.selected = False
        if self.selected and ((now_ms - self.select_ms) & _MASK) > SELECT_LAPSE_MS:
            self.selected = False

    def on_cmd(self, now_ms: int, data: bytes, busy: bool = False) -> tuple[int, bytes] | None:
        """A frame on ``0x7EA``. Returns ``(id, data)`` of the answer, or None."""
        if not serial_is_valid(self.serial):
            return None
        self._lapse(now_ms, busy)
        op = data[0] if data else 0
        if op == OP_PROBE and len(data) == 6 and data[1] <= 32:
            self._heard(now_ms)
            if _matches(self.serial, data[1], int.from_bytes(data[2:6], "big")):
                return ID_RESP, bytes([OP_PROBE, PRESENT_MARK])
        elif op == OP_SELECT and len(data) == 6:
            self._heard(now_ms)
            if int.from_bytes(data[1:5], "big") == self.serial:
                self.selected = True
                self.select_ms = now_ms & _MASK
                return ID_RESP, bytes([OP_SELECT]) + data[1:5] + bytes([data[5]])
            self.selected = False
        elif op == OP_RELEASE and len(data) == 1:
            self._heard(now_ms)
            self.selected = False
        elif op == OP_UID and len(data) == 2:
            self._heard(now_ms)
            if self.selected and data[1] < 3:
                return ID_RESP, bytes([OP_UID, data[1]]) + self.uid[data[1]].to_bytes(4, "big")
        return None

    def _heard(self, now_ms: int) -> None:
        self.addressed = True
        self.last_cmd_ms = now_ms & _MASK

    def accepts(self, now_ms: int, can_id: int, busy: bool = False) -> bool:
        """Should this bootloader obey a frame with this identifier right now?"""
        if not serial_is_valid(self.serial):
            return True
        self._lapse(now_ms, busy)
        if not (LEGACY_FIRST <= can_id <= LEGACY_LAST):
            return True
        return (not self.addressed) or self.selected


def enumerate_serials(probe: Callable[[int, int], bool]) -> list[int]:
    """Find every serial on the bus with a binary search over its bits.

    ``probe(nbits, prefix)`` sends a probe and says whether anyone answered. Bootloaders that match all send the SAME frame, which the bus allows, so
    several answers never corrupt each other. An empty result means no bootloader announces a serial (an older one, or none): the host keeps the
    single-head behaviour. Costs at most ``1 + 64 * N`` probes for N heads.
    """
    found: list[int] = []
    stack: list[tuple[int, int]] = [(0, 0)]
    while stack:
        nbits, prefix = stack.pop()
        if not probe(nbits, prefix):
            continue
        if nbits == 32:
            found.append(prefix)
            continue
        stack.append((nbits + 1, prefix | (1 << (31 - nbits))))
        stack.append((nbits + 1, prefix))
    return sorted(found)
