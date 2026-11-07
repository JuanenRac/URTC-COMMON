# =============================================================================
# URTC-COMMON - tests/test_key_rotation_command.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. The signed rotation command with the time of the host: the Python reference held to the shared vectors."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_key_rotation_command_vectors as maker  # noqa: E402
from urtc_common import image_auth as ia, key_rotation as kr, key_rotation_command as krc  # noqa: E402

DOC = json.loads((ROOT / "conformance" / "key_rotation_command_vectors.json").read_text(encoding="utf-8"))


def state_of(c) -> krc.State:
    rot = kr.Rotation(bytes.fromhex(c["current"]), bytes.fromhex(c["previous"]) if c["previous"] else None, 0, 0, frozenset(bytes.fromhex(r) for r in c["revoked"]))
    trust = krc.Trust({bytes.fromhex(t["id"]): bytes.fromhex(t["public"]) for t in c["trust"]})
    return krc.State(rot, trust, c["last_counter"], c["last_time"], 0, c["allow"], c["max_window_s"])


def test_vectors_are_current():
    assert maker.main(["--check"]) == 0


@pytest.mark.parametrize("c", DOC["cases"], ids=[c["name"] for c in DOC["cases"]])
def test_vector_cases(c):
    before = state_of(c)
    after, reason = krc.decide(before, bytes.fromhex(c["record"]), c["uptime"])
    assert reason == c["reason"]
    if c["expect"] is None:
        assert after == before          # a refused command changes nothing
        return
    e = c["expect"]
    assert after.rotation.current.hex() == e["current"]
    assert (after.rotation.previous.hex() if after.rotation.previous else None) == e["previous"]
    assert after.rotation.window_s == e["window_s"] and after.rotation.started_at == e["started_at"]
    assert after.last_counter == e["last_counter"] and after.last_host_time == e["last_time"] and after.clock_offset == e["clock_offset"]


def test_the_time_of_the_host_drives_the_window():
    c = next(x for x in DOC["cases"] if x["name"].startswith("accepted: the current key hands over"))
    after, reason = krc.decide(state_of(c), bytes.fromhex(c["record"]), 500)
    assert reason == "ok"
    for uptime, ids in ((500, 2), (500 + 3599, 2), (500 + 3600, 1), (500 + 10**6, 1)):
        assert len(kr.active_key_ids(after.rotation, krc.now_of(after, uptime))) == ids
    frames, status = kr.announce(after.rotation, krc.now_of(after, 500 + 60))
    assert len(frames) == 2 and frames[0].hex() == c["expect"]["current"] and kr.parse_status(status)["seconds_left"] == 3540


def test_a_replay_after_a_reset_of_the_counter_is_refused_but_a_new_command_goes_through():
    c = next(x for x in DOC["cases"] if x["name"].startswith("accepted: the current key hands over"))
    after, _ = krc.decide(state_of(c), bytes.fromhex(c["record"]), 500)
    again, reason = krc.decide(after, bytes.fromhex(c["record"]), 600)
    assert reason in ("replayed_counter", "signer_not_current") and again == after


def test_chunks_roundtrip_and_misorder_drops_them():
    record = bytes.fromhex(DOC["cases"][0]["record"])
    chunks = krc.to_chunks(record)
    assert len(chunks) == 15 and all(len(x) == 8 and krc.is_chunk(x) for x in chunks) and chunks[0][0] == 0x80 and chunks[-1][0] == 0x8E
    asm = krc.Assembler()
    got = [asm.feed(x) for x in chunks]
    assert got[:-1] == [None] * 14 and got[-1] == record
    asm = krc.Assembler()
    assert asm.feed(chunks[0]) is None and asm.feed(chunks[2]) is None and asm.parts == []
    assert asm.feed(bytes([0x05, 0, 0, 0, 0, 0, 0, 0])) is None      # a signature chunk of an image is not ours
    assert not krc.is_chunk(bytes([0x0A]) + bytes(7)) and not krc.is_chunk(bytes([0x8F]) + bytes(7)) and not krc.is_chunk(bytes([0x80]) + bytes(6))


def test_sign_uses_a_derived_signer_and_checks_sizes():
    seed = maker.SEEDS["A"]
    rec = krc.sign(seed, maker.KID["B"], None, 60, 5, 1)
    assert krc.parse(rec).signer == ia.key_id(maker.PUB["A"]) and krc.parse(rec).previous == krc.NO_KEY and len(rec) == 100
    with pytest.raises(krc.RotationCommandError):
        krc.sign(seed, b"short", None, 60, 5, 1)
    with pytest.raises(krc.RotationCommandError):
        krc.sign(seed, maker.KID["B"], None, 2**32, 5, 1)
    with pytest.raises(krc.RotationCommandError):
        krc.parse(b"x" * 99)


def test_reasons_are_all_covered_by_the_vectors():
    assert {c["reason"] for c in DOC["cases"]} == set(krc.REASONS)


def test_the_c_twin_passes_the_same_vectors(tmp_path):
    import os
    import shutil
    import subprocess

    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("key_rotation_command.exe" if os.name == "nt" else "key_rotation_command")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", f"-I{ROOT / 'firmware_base'}", f"-I{ROOT / 'generated'}",
            str(ROOT / "tests" / "c" / "test_key_rotation_cmd.c"), str(ROOT / "firmware_base" / "urtc_ed25519.c"), "-o", str(binary)]
    attempt = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
    if attempt.returncode != 0:
        build = subprocess.run(base, capture_output=True, text=True)
        assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all key rotation command tests pass" in run.stdout
