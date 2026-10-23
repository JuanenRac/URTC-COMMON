# =============================================================================
# URTC-COMMON - tests/test_frame_layer.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The frame layer and the rate limiter shared by the rack and the vision sensor: the reference module against the existing vectors of both links, the rate vectors,
and the C headers compiled with the host compiler and held to the same vectors."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from urtc_common import frame_layer as fl
from urtc_common import rack_sim as rk
from urtc_common import sensor_frame as sf

ROOT = Path(__file__).resolve().parents[1]


def vectors(name: str) -> dict:
    return json.loads((ROOT / "conformance" / name).read_text(encoding="utf-8"))


def test_the_formats_are_the_ones_the_two_links_use():
    assert (fl.RACK.sof, fl.RACK.version, fl.RACK.header_size) == (rk.SOF, rk.VERSION, 5)
    assert (fl.SENSOR.sof, fl.SENSOR.version, fl.SENSOR.header_size) == (sf.SOF, sf.VERSION, sf.HEADER_SIZE)
    assert fl.RACK.max_payload == rk.MAX_PAYLOAD and fl.SENSOR.max_payload == sf.MAX_PAYLOAD
    assert fl.RACK.total_size(0) == 6 and fl.SENSOR.total_size(0) == 10 and fl.SENSOR.total_size(16) == 26


@pytest.mark.parametrize("name,fmt", [("rack_vectors.json", fl.RACK), ("sensor_vectors.json", fl.SENSOR)])
def test_every_parse_vector_of_both_links_gets_the_same_decision_from_the_shared_layer(name, fmt):
    cases = vectors(name)["parse"]
    assert len(cases) >= 7
    for case in cases:
        status, total = fl.validate(fmt, bytes.fromhex(case["hex"]))
        assert status == case["status"], case["name"]
        assert (total == len(bytes.fromhex(case["hex"]))) == (status == "ok")


@pytest.mark.parametrize("name,fmt,encode", [
    ("rack_vectors.json", fl.RACK, lambda f: rk.encode_frame(f["seq"], f["cmd"], bytes.fromhex(f["payload"]))),
    ("sensor_vectors.json", fl.SENSOR, lambda f: sf.encode_frame(f["sensor_id"], f["seq"], f["timestamp_ms"], bytes.fromhex(f["payload"]))),
])
def test_the_frames_of_both_links_validate_and_seal_back_to_themselves(name, fmt, encode):
    for entry in vectors(name)["frames"]:
        frame = bytes.fromhex(entry["frame"])
        assert encode(entry) == frame
        assert fl.validate(fmt, frame) == ("ok", len(frame))
        assert fl.seal(fmt, frame[:-1]) == frame
        assert fl.validate(fmt, frame + b"\xEE\xEE") == ("ok", len(frame))  # bytes after the frame are not looked at


def test_every_cut_and_every_flipped_byte_of_a_frame_is_refused_in_the_documented_order():
    frame = sf.encode_frame(1, 3, 123456, sf.encode_thermal_payload(2000))
    for cut in range(len(frame)):
        assert fl.validate(fl.SENSOR, frame[:cut])[0] == "incomplete"
    for index in range(len(frame)):
        damaged = bytearray(frame)
        damaged[index] ^= 0x01
        status = fl.validate(fl.SENSOR, bytes(damaged))[0]
        assert status != "ok"
        expected = {0: "bad_sof", 1: "unsupported_version"}.get(index)
        if expected:
            assert status == expected
        elif index == 8:
            assert status in {"incomplete", "crc_mismatch"}  # the length changed by one
        else:
            assert status == "crc_mismatch"


def test_the_rate_vectors_are_reproduced_by_the_reference_and_cover_the_wrap():
    data = vectors("rate_vectors.json")
    assert [c["name"] for c in data["cases"]] == [name for name, _i, _t in fl.RATE_CASES]
    for case in data["cases"]:
        limiter = fl.RateLimiter(case["min_interval_ms"])
        assert [limiter.allow(t) for t in case["times_ms"]] == case["allowed"], case["name"]
    wrap = next(c for c in data["cases"] if "wrap" in c["name"])
    assert wrap["times_ms"][0] > 0xFFFFFF00 and wrap["times_ms"][-1] < 0x100 and wrap["allowed"] == [True, False, False, True]


def test_the_generated_rate_header_has_one_row_per_case():
    text = (ROOT / "generated" / "rate_vectors.h").read_text(encoding="utf-8")
    assert text.count('\n    {"') == len(vectors("rate_vectors.json")["cases"])


def test_the_c_headers_pass_the_same_vectors_with_the_host_compiler(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("t.exe" if os.name == "nt" else "t")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Wno-unused-const-variable", f"-I{ROOT / 'firmware_base'}", f"-I{ROOT / 'generated'}",
            str(ROOT / "tests" / "c" / "test_frame_layer.c"), "-o", str(binary)]
    build = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
    if build.returncode != 0:
        build = subprocess.run(base, capture_output=True, text=True)  # a compiler with no sanitizer runtime (the MinGW of the Windows runner has none)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all vectors pass" in run.stdout
