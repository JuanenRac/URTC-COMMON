# =============================================================================
# URTC-COMMON - tests/test_virtual_board_rotation.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. The virtual bootloader announces two fingerprints, takes a signed rotation command with the time of the host and
lets the window run out on its own clock (evidence = simulator)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_key_rotation_command_vectors as maker  # noqa: E402
from urtc_common import key_rotation as kr, key_rotation_command as krc, protocol  # noqa: E402
from urtc_common.virtual_board import VirtualBoard  # noqa: E402

A, B = maker.KID["A"], maker.KID["B"]
T0 = 1_700_000_000


def board(allow=True) -> VirtualBoard:
    trust = krc.Trust({A: maker.PUB["A"], B: maker.PUB["B"]})
    return VirtualBoard(bootloader=True, key_rotation=krc.State(kr.Rotation(A), trust, allow=allow))


def ask(b: VirtualBoard):
    frames = b.handle(protocol.CAN_ID_BOOTLOADER_SELECT, bytes([kr.STATUS_OP]))
    keys = [d for i, d in frames if i == protocol.CAN_ID_BOOTLOADER_KEY_ID]
    status = next(d for i, d in frames if i == protocol.CAN_ID_BOOTLOADER_SELECT_RESPONSE)
    return keys, kr.parse_status(status)


def send(b: VirtualBoard, record: bytes) -> None:
    for chunk in krc.to_chunks(record):
        assert b.handle(protocol.CAN_ID_BOOTLOADER_SIGNATURE_CHUNK, chunk) == []


def test_before_any_command_one_fingerprint_and_no_window():
    keys, st = ask(board())
    assert keys == [A] and st == {"count": 1, "rotating": False, "current_revoked": False, "seconds_left": 0xFFFFFFFF}


def test_a_signed_command_with_the_host_time_starts_the_overlap_and_the_window_runs_out():
    b = board()
    b.advance(10)
    send(b, krc.sign(maker.SEEDS["A"], B, A, 120, T0, 1))
    assert b.last_rotation_result == "ok"
    keys, st = ask(b)
    assert keys == [B, A] and st["rotating"] and st["seconds_left"] == 120
    b.advance(119)
    keys, st = ask(b)
    assert keys == [B, A] and st["seconds_left"] == 1
    b.advance(1)
    keys, st = ask(b)
    assert keys == [B] and not st["rotating"]


def test_a_reset_loses_the_clock_and_fails_closed():
    b = board()
    send(b, krc.sign(maker.SEEDS["A"], B, A, 3600, T0, 1))
    b.reboot()
    b.enter_bootloader()
    keys, st = ask(b)
    assert keys == [B] and st["count"] == 1      # the previous key cannot be placed in time until the host sends the time again
    send(b, krc.sign(maker.SEEDS["B"], B, None, 0, T0 + 5, 2))
    assert b.last_rotation_result == "ok"


def test_refusals_leave_the_state_alone():
    b = board(allow=False)
    send(b, krc.sign(maker.SEEDS["A"], B, A, 60, T0, 1))
    assert b.last_rotation_result == "disabled" and ask(b)[0] == [A]
    c = board()
    send(c, krc.sign(maker.SEEDS["C"], B, A, 60, T0, 1))
    assert c.last_rotation_result == "unknown_signer" and ask(c)[0] == [A]


def test_the_keys_are_announced_after_the_version_answer_and_not_by_a_bootloader_without_rotation():
    frames = board().handle(protocol.CAN_ID_QUERY_VERSION, b"")
    ids = [i for i, _ in frames]
    assert protocol.CAN_ID_BOOTLOADER_KEY_ID in ids and ids.index(protocol.CAN_ID_BOOTLOADER_KEY_ID) == ids.index(protocol.CAN_ID_VERSION_RESPONSE) + 1
    plain = VirtualBoard(bootloader=True).handle(protocol.CAN_ID_QUERY_VERSION, b"")
    assert protocol.CAN_ID_BOOTLOADER_KEY_ID not in [i for i, _ in plain]
