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
    embedded = json.loads((ROOT / "conformance" / "image_header_embedded_vectors.json").read_text(encoding="utf-8"))
    assert {c["status"] for c in data["cases"]} | {c["status"] for c in embedded["cases"]} == set(ih.STATUS_NAMES)
    signed = [c for c in data["cases"] if c.get("signature_ok") is not None]
    assert signed and all(c["signature_ok"] for c in signed)
    for case in data["cases"]:
        status, _ = ih.verify_image(bytes.fromhex(case["image"]))
        assert ih.STATUS_NAMES[status] == case["status"], case["name"]


def test_the_tool_checks_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(make_image_header_vectors, "JSON_OUT", tmp_path / "a.json")
    monkeypatch.setattr(make_image_header_vectors, "HEADER_OUT", tmp_path / "a.h")
    monkeypatch.setattr(make_image_header_vectors, "EMBEDDED_JSON_OUT", tmp_path / "b.json")
    monkeypatch.setattr(make_image_header_vectors, "EMBEDDED_HEADER_OUT", tmp_path / "b.h")
    assert make_image_header_vectors.main(["--check"]) == 1
    assert make_image_header_vectors.main([]) == 0
    assert make_image_header_vectors.main(["--check"]) == 0


def test_the_header_copy_sets_exist():
    import vendor_copy

    assert vendor_copy.SETS["firmware_image_header"] == ["firmware_base/urtc_image_header.h"]
    assert vendor_copy.SETS["image_header_test"] == ["tests/c/test_image_header.c"]
    assert vendor_copy.SETS["image_header_c"] == ["generated/image_header_vectors.h", "generated/image_header_embedded_vectors.h"]
    assert vendor_copy.SETS["image_header"] == ["src/urtc_common/image_header.py", "conformance/image_header_vectors.json",
                                                "conformance/image_header_embedded_vectors.json"]


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


# ---- the header inside the image ---------------------------------------------------------------------------------------------------
EMBEDDED = json.loads((ROOT / "conformance" / "image_header_embedded_vectors.json").read_text(encoding="utf-8"))


def _slot_binary(length: int = 768) -> bytes:
    raw = bytearray((i * 31 + 7) & 0x7F for i in range(length))
    raw[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = ih.embedded_slot(0x0303CC01, (0, 8, 1, 3))
    return bytes(raw)


def test_the_header_inside_the_image_leaves_the_code_and_the_vector_table_where_they_are():
    binary = _slot_binary()
    sealed = ih.seal_embedded(binary)
    assert len(sealed) == len(binary)
    assert sealed[:ih.EMBED_OFFSET] == binary[:ih.EMBED_OFFSET] and sealed[ih.EMBED_OFFSET + 32:] == binary[ih.EMBED_OFFSET + 32:]
    status, info = ih.verify_embedded(sealed)
    assert status == ih.OK and info is not None and info.embedded and not info.signed
    assert info.payload_length == len(sealed) and info.version == (0, 8, 1, 3) and info.hardware_id == 0x0303CC01
    assert ih.seal_embedded(sealed) == sealed   # sealing again gives the same bytes

    # the record of a release stays what the bootloaders rebuild (the flat header of the file, with the plain CRC-32) over the SHA-256 of the whole sealed file:
    # the embedded header is covered by that SHA-256, so it cannot be changed without breaking the signature
    flat = ih.make_header(sealed, 0x0303CC01, (0, 8, 1, 3))[:28]
    assert flat[:6] == b"URIH\x01\x20" and flat[6:8] == b"\x00\x00" and flat != sealed[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 28]


def test_the_crc_of_an_embedded_image_takes_its_own_header_as_zeros():
    sealed = ih.seal_embedded(_slot_binary())
    zeroed = sealed[:ih.EMBED_OFFSET] + bytes(32) + sealed[ih.EMBED_OFFSET + 32:]
    assert ih.parse_header(sealed[ih.EMBED_OFFSET:])[1].payload_crc32 == zlib.crc32(zeroed) & 0xFFFFFFFF == ih.embedded_crc(sealed)


def test_sealing_refuses_what_is_not_the_slot_of_the_firmware():
    with pytest.raises(ValueError, match="too short"):
        ih.seal_embedded(bytes(100))
    with pytest.raises(ValueError, match="no header slot"):
        ih.seal_embedded(bytes(768))
    with pytest.raises(ValueError, match="states hardware"):
        ih.seal_embedded(_slot_binary(), hardware_id=0x0303CB01)
    with pytest.raises(ValueError, match="states version"):
        ih.seal_embedded(_slot_binary(), version=(0, 8, 1, 4))
    ih.seal_embedded(_slot_binary(), hardware_id=0x0303CC01, version=(0, 8, 1, 3))


def test_every_way_to_break_an_embedded_image_has_its_reason():
    for case in EMBEDDED["cases"]:
        status, info = ih.verify_embedded(bytes.fromhex(case["image"]))
        assert ih.STATUS_NAMES[status] == case["status"], case["name"]
        assert (info is not None) == ("info" in case), case["name"]
    assert {c["status"] for c in EMBEDDED["cases"]} >= {"ok", "short", "bad_magic", "bad_version", "bad_size", "bad_header_crc", "bad_length", "bad_payload_crc",
                                                       "bad_flags", "not_sealed"}


def test_the_embedded_slot_the_firmware_emits_never_passes_for_a_sealed_header():
    slot = ih.embedded_slot(0x0303CC01, (0, 8, 1, 3))
    assert len(slot) == 32 and slot[:4] == b"URIH" and slot[28:] == bytes(4)
    assert ih.parse_header(slot)[0] == ih.BAD_HEADER_CRC
    assert ih.verify_embedded(_slot_binary())[0] == ih.NOT_SEALED


@pytest.mark.parametrize("case", EMBEDDED["policy_cases"], ids=lambda c: c["name"])
def test_the_switch_decides_the_same_everywhere(case):
    version = tuple(case["version"]) if case["version"] else None
    check = ih.inspect_image(bytes.fromhex(case["image"]), case["policy"], case["hardware_id"], version)
    assert (check.accepted, check.kind, check.reason, check.warn) == (case["accepted"], case["kind"], case["reason"], case["warn"])


def test_the_switch_is_conservative_and_a_present_header_is_never_ignored():
    assert ih.DEFAULT_POLICY == ih.POLICY_WARN
    assert ih.parse_policy(None) == ih.parse_policy("") == "warn" and ih.parse_policy(" Accept ") == "accept"
    assert ih.parse_policy("maybe") == ih.parse_policy(0) == "require"
    broken = bytearray(ih.seal_embedded(_slot_binary()))
    broken[700] ^= 1
    for policy in ih.POLICIES:
        assert not ih.inspect_image(bytes(broken), policy).accepted


def test_a_stamped_file_is_never_taken_for_a_firmware_image():
    stamped = ih.build_image(bytes(range(200)), 0x0303CC01, (0, 8, 1, 3))
    for policy in ih.POLICIES:
        check = ih.inspect_image(stamped, policy)
        assert not check.accepted and check.kind == ih.KIND_STAMPED_FILE and check.reason == ih.REASON_STAMPED


def test_the_embedded_c_header_set_is_kept_with_the_others():
    text = (ROOT / "firmware_base" / "urtc_image_header.h").read_text(encoding="utf-8")
    assert f"#define URTC_IMAGE_EMBED_OFFSET     0x{ih.EMBED_OFFSET:X}u" in text
    assert f"#define URTC_IMAGE_FLAG_EMBEDDED    0x{ih.FLAG_EMBEDDED:04X}u" in text
    assert "urtc_image_verify_embedded" in text and "URTC_IMAGE_EMBED_SLOT" in text
