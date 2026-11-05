# =============================================================================
# URTC-COMMON - tests/test_bl_serial.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The signed command that programs the serial number of a bootloader: the Python reference, its vectors and the frames."""
from __future__ import annotations

import json
import os

import make_bl_serial_vectors as tool
import pytest
from urtc_common import bl_select as bs
from urtc_common import bl_serial as sr
from urtc_common import ed25519

SEED = os.urandom(32)                       # an ephemeral key: nothing here uses a key of the workshop
PUBLIC = ed25519.public_key(SEED)
UID = (0xDEADBEEF, 0x01234567, 0x89ABCDEF)
CURRENT = bs.serial_from_uid(*UID)


def command(serial=0x00ABCDEF, counter=1, uid=UID, current=CURRENT, seed=SEED):
    return sr.make_command(seed, uid, current, serial, counter)


def test_a_command_is_84_bytes_in_twelve_frames_of_eight():
    cmd = command()
    assert len(cmd) == sr.COMMAND_SIZE == 84
    frames = sr.chunks(cmd)
    assert len(frames) == 12 and all(len(f) == 8 for f in frames) and [f[0] for f in frames] == list(range(12))
    assert b"".join(f[1:] for f in frames) == cmd
    with pytest.raises(ValueError):
        sr.chunks(cmd[:-1])


def test_a_valid_command_for_this_head_is_accepted_and_names_what_to_store():
    assert sr.decide(command(), UID, CURRENT, [PUBLIC], 0) == (sr.OK, 0x00ABCDEF, 1)


def test_a_command_signed_for_another_head_or_by_another_key_fails():
    other_uid = (UID[0], UID[1], UID[2] ^ 1)
    assert sr.decide(command(uid=other_uid), UID, CURRENT, [PUBLIC], 0)[0] == sr.BAD_SIGNATURE
    assert sr.decide(command(seed=os.urandom(32)), UID, CURRENT, [PUBLIC], 0)[0] == sr.UNKNOWN_KEY
    assert sr.decide(command(), UID, CURRENT, [], 0)[0] == sr.UNKNOWN_KEY


def test_every_bit_of_the_command_counts():
    cmd = command()
    for index in range(4, len(cmd)):                      # the target (first four bytes) only says who answers; the rest is signed or is the signature
        flipped = cmd[:index] + bytes([cmd[index] ^ 0x80]) + cmd[index + 1:]
        assert sr.decide(flipped, UID, CURRENT, [PUBLIC], 0)[0] in (sr.UNKNOWN_KEY, sr.BAD_SIGNATURE), index


def test_a_command_for_another_target_is_not_answered_at_all():
    assert sr.decide(command(current=CURRENT ^ 1), UID, CURRENT, [PUBLIC], 0)[0] == sr.NOT_FOR_ME


def test_the_counter_must_be_higher_than_the_stored_one():
    assert sr.decide(command(counter=5), UID, CURRENT, [PUBLIC], 4)[0] == sr.OK
    assert sr.decide(command(counter=5), UID, CURRENT, [PUBLIC], 5)[0] == sr.REPLAY
    assert sr.decide(command(counter=5), UID, CURRENT, [PUBLIC], 6)[0] == sr.REPLAY
    assert sr.decide(command(counter=0), UID, CURRENT, [PUBLIC], 0)[0] == sr.REPLAY   # the first command needs 1 or more


def test_a_serial_that_is_no_serial_the_switch_and_a_running_update():
    assert sr.decide(command(serial=0), UID, CURRENT, [PUBLIC], 0)[0] == sr.BAD_SERIAL
    assert sr.decide(command(serial=0xFFFFFFFF), UID, CURRENT, [PUBLIC], 0)[0] == sr.BAD_SERIAL
    assert sr.decide(command(), UID, CURRENT, [PUBLIC], 0, enabled=False)[0] == sr.DISABLED
    assert sr.decide(command(), UID, CURRENT, [PUBLIC], 0, busy=True)[0] == sr.BUSY


def test_the_message_names_the_unique_id_the_serial_the_counter_and_the_key():
    kid = sr.key_id(PUBLIC)
    msg = sr.message(UID, 0x11223344, 0x55667788, kid)
    assert len(msg) == 44 and msg[:16] == b"URTC-SERIAL-V1\x00\x00"
    assert msg[16:28].hex() == "deadbeef0123456789abcdef" and msg[28:36].hex() == "1122334455667788" and msg[36:] == kid
    with pytest.raises(ValueError):
        sr.message(UID[:2], 1, 1, kid)


def test_the_result_frame_is_the_status_and_the_serial():
    assert sr.result_frame(sr.OK, 0x00C0FFEE).hex().upper() == "0000C0FFEE"
    assert sr.result_frame(sr.REPLAY, 1) == bytes([3, 0, 0, 0, 1])


def test_the_two_slots_of_the_record():
    a, b, blank = sr.slot_pack(0x0A0A0A0A, 3), sr.slot_pack(0x0B0B0B0B, 7), b"\xff" * 16
    assert sr.pick(blank, blank) is None
    assert sr.pick(a, blank) == (0x0A0A0A0A, 3) and sr.pick(blank, b) == (0x0B0B0B0B, 7)
    assert sr.pick(a, b) == sr.pick(b, a) == (0x0B0B0B0B, 7)
    assert sr.pick(sr.slot_pack(1, 4), sr.slot_pack(2, 4)) == (1, 4)             # a tie: the first
    assert sr.pick(b"\xff" * 4 + a[4:], b) == (0x0B0B0B0B, 7)                      # no magic: not a record
    assert sr.pick(sr.slot_pack(0, 9), a) == (0x0A0A0A0A, 3)                       # the serial 0 is no record
    assert len(a) == sr.SLOT_BYTES and a[:4] == b"1SRU"                            # "URS1" as a little-endian word


def test_the_vector_files_are_current_and_the_reference_reproduces_them():
    assert tool.main(["--check"]) == 0
    data = json.loads((tool.ROOT / "conformance" / "bl_serial_vectors.json").read_text(encoding="utf-8"))
    keys = tool.keys()
    assert data["public_keys"] == [k.hex().upper() for k in keys]
    for case in data["commands"]:
        uid = tuple(int(w, 16) for w in case["uid"])
        status, serial, counter = sr.decide(bytes.fromhex(case["command"]), uid, int(case["current_serial"], 16), [keys[i] for i in case["trusted"]],
                                            case["stored_counter"], case["enabled"], case["busy"])
        assert (status, f"{serial:08X}", counter) == (case["status"], case["serial"], case["counter"]), case["name"]
    kinds = {case["status_name"] for case in data["commands"]}
    assert {"ok", "replay", "bad_signature", "unknown_key", "bad_serial", "disabled", "busy", "not_for_me"} <= kinds
    for case in data["slots"]:
        value = sr.pick(bytes.fromhex(case["slot_a"]), bytes.fromhex(case["slot_b"]))
        assert (None if value is None else f"{value[0]:08X}") == case["serial"], case["name"]


def test_the_vectors_use_the_public_development_key_and_no_key_of_the_workshop():
    assert tool.DEV_SEED == __import__("hashlib").sha256(b"urtc public development image key v1").digest()
    assert tool.keys()[0] == ed25519.public_key(tool.DEV_SEED)
