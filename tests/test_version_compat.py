# =============================================================================
# URTC-COMMON - tests/test_version_compat.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The signed command that changes the version rule for an image without a patch: the Python reference, its vectors, the frames and the C twin."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import make_version_compat_vectors as tool
import pytest
from urtc_common import bl_select as bs
from urtc_common import bl_serial as sr
from urtc_common import ed25519, protocol
from urtc_common import version_compat as vc

ROOT = tool.ROOT
SEED = os.urandom(32)                       # an ephemeral key: nothing here uses a key of the workshop
PUBLIC = ed25519.public_key(SEED)
UID = (0xDEADBEEF, 0x01234567, 0x89ABCDEF)
CURRENT = bs.serial_from_uid(*UID)


def command(mode=vc.MODE_ACCEPT_PATCHLESS, counter=1, uid=UID, current=CURRENT, seed=SEED):
    return vc.make_command(seed, uid, current, mode, counter)


def test_a_command_is_twelve_frames_with_their_own_range_of_indexes():
    cmd = command()
    frames = vc.chunks(cmd)
    assert len(cmd) == vc.COMMAND_SIZE == 84 and len(frames) == 12 and all(len(f) == 8 for f in frames)
    assert [f[0] for f in frames] == list(range(0x40, 0x4C))
    assert not {f[0] for f in frames} & {f[0] for f in sr.chunks(sr.make_command(SEED, UID, CURRENT, 5, 1))}   # never read as a serial command
    assert vc.query_frame() == bytes([0x60, 0, 0, 0, 0, 0, 0, 0])
    assert b"".join(f[1:] for f in frames) == cmd
    with pytest.raises(ValueError):
        vc.chunks(cmd[:-1])


def test_the_identifiers_and_the_slave_register_do_not_collide_with_the_specification():
    assert (vc.ID_COMMAND, vc.ID_RESULT) == (sr.ID_CHUNK, sr.ID_RESULT)
    boot_registers = {value for name, value in vars(protocol).items() if name.startswith("SLAVE_BOOT_REG_")}
    assert vc.SLAVE_REG not in boot_registers


def test_a_valid_command_a_bad_signature_a_replay_and_an_older_counter():
    assert vc.decide(command(counter=5), UID, CURRENT, [PUBLIC], 4) == (vc.OK, vc.MODE_ACCEPT_PATCHLESS, 5)
    assert vc.decide(command(counter=5), UID, CURRENT, [PUBLIC], 5) == (vc.REPLAY, 0, 0)
    assert vc.decide(command(counter=5), UID, CURRENT, [PUBLIC], 8) == (vc.REPLAY, 0, 0)
    assert vc.decide(command(seed=os.urandom(32)), UID, CURRENT, [PUBLIC], 0)[0] == vc.UNKNOWN_KEY
    bad = command()[:-1] + bytes([command()[-1] ^ 1])
    assert vc.decide(bad, UID, CURRENT, [PUBLIC], 0)[0] == vc.BAD_SIGNATURE
    assert vc.decide(command(mode=7), UID, CURRENT, [PUBLIC], 0)[0] == vc.BAD_MODE
    assert vc.decide(command(), UID, CURRENT, [PUBLIC], 0, enabled=False)[0] == vc.DISABLED
    assert vc.decide(command(), UID, CURRENT, [PUBLIC], 0, busy=True)[0] == vc.BUSY
    assert vc.decide(command(current=CURRENT ^ 1), UID, CURRENT, [PUBLIC], 0)[0] == vc.NOT_FOR_ME


def test_every_bit_of_the_command_counts():
    cmd = command()
    for index in range(4, len(cmd)):                      # the target (first four bytes) only says who answers
        flipped = cmd[:index] + bytes([cmd[index] ^ 0x80]) + cmd[index + 1:]
        assert vc.decide(flipped, UID, CURRENT, [PUBLIC], 0)[0] in (vc.UNKNOWN_KEY, vc.BAD_SIGNATURE), index


def test_a_signature_made_for_the_serial_command_is_not_valid_here_nor_the_other_way_round():
    serial_cmd = sr.make_command(SEED, UID, CURRENT, vc.MODE_ACCEPT_PATCHLESS, 5)
    assert vc.decide(serial_cmd, UID, CURRENT, [PUBLIC], 0)[0] == vc.BAD_SIGNATURE
    assert sr.decide(command(counter=5), UID, CURRENT, [PUBLIC], 0)[0] == sr.BAD_SIGNATURE


def test_the_rule_in_force_the_answer_and_the_record():
    assert vc.effective_mode(vc.MODE_NONE) == vc.MODE_STRICT and vc.effective_mode(vc.MODE_NONE, False) == vc.MODE_ACCEPT_PATCHLESS
    assert vc.effective_mode(vc.MODE_ACCEPT_PATCHLESS) == vc.MODE_ACCEPT_PATCHLESS and vc.effective_mode(99) == vc.MODE_STRICT
    frame = vc.answer_frame(vc.OK, vc.MODE_ACCEPT_PATCHLESS, True, 7)
    assert vc.parse_answer(frame) == (vc.OK, vc.MODE_ACCEPT_PATCHLESS, True, 7)
    assert vc.parse_answer(sr.result_frame(sr.OK, 0xC5C5C5C5)) is None and vc.parse_answer(b"\xC4" + frame[1:]) is None
    assert vc.parse_answer(frame[:2] + b"\x00" + frame[3:]) is None
    record = vc.record_pack(vc.MODE_STRICT, 3)
    assert len(record) == vc.RECORD_SIZE and record[:4] == b"VCV1" and vc.record_read(record) == (vc.MODE_STRICT, 3)
    assert vc.record_read(b"\xff" * 16) is None and vc.record_read(record[:15]) is None


def test_the_vector_files_are_current_and_the_reference_reproduces_them():
    assert tool.main(["--check"]) == 0
    data = json.loads((ROOT / "conformance" / "version_compat_vectors.json").read_text(encoding="utf-8"))
    keys = tool.keys()
    for case in data["commands"]:
        uid = tuple(int(w, 16) for w in case["uid"])
        got = vc.decide(bytes.fromhex(case["command"]), uid, int(case["current_serial"], 16), [keys[i] for i in case["trusted"]], case["stored_counter"],
                        case["enabled"], case["busy"])
        assert got == (case["status"], case["mode"], case["counter"]), case["name"]
    assert {c["status_name"] for c in data["commands"]} >= {"ok", "replay", "bad_signature", "unknown_key", "bad_mode", "disabled", "busy", "not_for_me"}
    for case in data["records"]:
        value = vc.record_read(bytes.fromhex(case["record"]))
        assert (value is not None) == case["valid"], case["name"]


def test_the_c_code_passes_the_same_vectors(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("version_compat.exe" if os.name == "nt" else "version_compat")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", f"-I{ROOT / 'firmware_base'}", f"-I{ROOT / 'generated'}",
            str(ROOT / "tests" / "c" / "test_version_compat.c"), str(ROOT / "firmware_base" / "urtc_ed25519.c"), "-o", str(binary)]
    attempt = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
    if attempt.returncode != 0:
        build = subprocess.run(base, capture_output=True, text=True)   # a compiler with no sanitizer runtime
        assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all version compatibility tests pass" in run.stdout


def test_the_copy_sets_exist():
    import vendor_copy

    assert vendor_copy.SETS["firmware_version_compat"] == ["firmware_base/urtc_version_compat.h"]
    assert vendor_copy.SETS["version_compat_c"] == ["generated/version_compat_vectors.h"]
    assert vendor_copy.SETS["version_compat"] == ["src/urtc_common/version_compat.py", "conformance/version_compat_vectors.json"]
