# =============================================================================
# URTC-COMMON - tests/test_image_header.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The firmware image header: the Python reference, the vectors written from it and the C header held to them."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_image_header_vectors  # noqa: E402
from urtc_common import image_header as ih  # noqa: E402

KEY = bytes(range(32))


def test_a_header_is_32_bytes_and_reads_back():
    payload = bytes(range(200))
    header = ih.make_header(payload, 0x0303CC01, (0, 8, 1, 3))
    assert len(header) == 32 and header[:4] == b"URIH"
    status, info = ih.parse_header(header)
    assert status == ih.OK and info is not None
    assert info.version == (0, 8, 1, 3) and info.version_text() == "0.8.1.3"
    assert info.hardware_id == 0x0303CC01 and info.payload_length == 200 and info.payload_crc32 == zlib.crc32(payload) and not info.signed
    assert ih.pack_header(info) == header


def test_the_fourth_component_is_the_build_and_all_four_fit_their_fields():
    header = ih.make_header(b"x", 1, (0xFFFF, 0xFF, 0xFF, 0xFFFF))
    status, info = ih.parse_header(header)
    assert status == ih.OK and info is not None and info.version == (0xFFFF, 0xFF, 0xFF, 0xFFFF)
    assert header[12:18] == bytes.fromhex("FFFFFFFFFFFF")


def test_every_way_to_break_an_image_has_its_reason():
    image = ih.build_image(bytes(range(64)), 0x0303CC01, (0, 8, 0, 0))
    assert ih.verify_image(image)[0] == ih.OK
    assert ih.verify_image(image[:20])[0] == ih.SHORT
    assert ih.verify_image(b"X" + image[1:])[0] == ih.BAD_MAGIC
    assert ih.verify_image(image[:4] + b"\x02" + image[5:])[0] == ih.BAD_VERSION
    assert ih.verify_image(image[:5] + b"\x30" + image[6:])[0] == ih.BAD_SIZE
    assert ih.verify_image(image[:9] + b"\x00" + image[10:])[0] == ih.BAD_HEADER_CRC
    assert ih.verify_image(image[:-1])[0] == ih.BAD_LENGTH
    assert ih.verify_image(image + b"\x00")[0] == ih.BAD_LENGTH
    assert ih.verify_image(image[:40] + b"\xFF" + image[41:])[0] == ih.BAD_PAYLOAD_CRC


def test_the_signature_covers_the_identity_the_length_and_the_payload():
    payload = bytes(range(80))
    image = ih.build_image(payload, 0x0303CB01, (1, 2, 3, 4), key=KEY)
    status, info = ih.verify_image(image)
    assert status == ih.OK and info is not None and info.signed
    trailer = image[-32:]
    assert trailer == hmac.new(KEY, image[:28] + payload, hashlib.sha256).digest()
    # change the declared build: whoever forges it recomputes the header CRC, and the signature no longer holds
    forged = ih.pack_header(ih.ImageInfo(info.hardware_id, info.version_major, info.version_minor, info.version_patch, 9, info.flags, info.payload_length, info.payload_crc32))
    assert ih.verify_image(forged + image[32:])[0] == ih.OK
    assert ih.sign(KEY, forged, payload) != trailer


def test_the_vectors_on_disk_are_what_the_reference_writes():
    for path, text in make_image_header_vectors.outputs().items():
        assert path.read_bytes().decode("utf-8").replace("\r\n", "\n") == text, f"{path.name} is out of date: python tools/make_image_header_vectors.py"
    assert make_image_header_vectors.main(["--check"]) == 0


def test_the_vectors_cover_every_status_and_the_signature_check():
    data = json.loads((ROOT / "conformance" / "image_header_vectors.json").read_text(encoding="utf-8"))
    assert {c["status"] for c in data["cases"]} == set(ih.STATUS_NAMES)
    signed = [c for c in data["cases"] if c.get("signature_ok") is not None]
    assert signed and all(c["signature_ok"] for c in signed)
    for case in data["cases"]:
        status, _ = ih.verify_image(bytes.fromhex(case["image"]))
        assert ih.STATUS_NAMES[status] == case["status"], case["name"]


def test_the_tool_checks_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(make_image_header_vectors, "JSON_OUT", tmp_path / "a.json")
    monkeypatch.setattr(make_image_header_vectors, "HEADER_OUT", tmp_path / "a.h")
    assert make_image_header_vectors.main(["--check"]) == 1
    assert make_image_header_vectors.main([]) == 0
    assert make_image_header_vectors.main(["--check"]) == 0


def test_the_header_copy_sets_exist():
    import vendor_copy

    assert vendor_copy.SETS["firmware_image_header"] == ["firmware_base/urtc_image_header.h"]
    assert vendor_copy.SETS["image_header_c"] == ["generated/image_header_vectors.h"]
    assert vendor_copy.SETS["image_header"] == ["src/urtc_common/image_header.py", "conformance/image_header_vectors.json"]


def test_the_c_header_passes_the_same_vectors(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("image_header.exe" if os.name == "nt" else "image_header")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", f"-I{ROOT / 'firmware_base'}", f"-I{ROOT / 'generated'}",
            str(ROOT / "tests" / "c" / "test_image_header.c"), "-o", str(binary)]
    attempt = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
    if attempt.returncode != 0:
        build = subprocess.run(base, capture_output=True, text=True)   # a compiler with no sanitizer runtime
        assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all image header tests pass" in run.stdout
