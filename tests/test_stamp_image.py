# =============================================================================
# URTC-COMMON - tests/test_stamp_image.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""tools/stamp_image.py: the header goes in front of a binary, the name gives the version and a broken image is refused."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import stamp_image  # noqa: E402
from urtc_common import image_header as ih  # noqa: E402


def test_stamping_puts_the_header_in_front_and_leaves_the_binary_alone(tmp_path):
    payload = bytes(range(256)) * 3
    binary = tmp_path / "URTC_MAIN_FIRMWARE_v0.8.1.3.bin"
    binary.write_bytes(payload)
    assert stamp_image.main(["stamp", str(binary), "--hardware", "main"]) == 0
    stamped = (tmp_path / "URTC_MAIN_FIRMWARE_v0.8.1.3.urimg").read_bytes()
    assert binary.read_bytes() == payload and stamped[32:] == payload
    status, info = ih.verify_image(stamped)
    assert status == ih.OK and info is not None
    assert info.version == (0, 8, 1, 3) and info.hardware_id == 0x0303CC01
    assert stamp_image.main(["check", str(tmp_path / "URTC_MAIN_FIRMWARE_v0.8.1.3.urimg")]) == 0


def test_the_same_input_gives_the_same_bytes_and_a_three_part_name_has_build_zero(tmp_path):
    binary = tmp_path / "slave_v1.2.3.bin"
    binary.write_bytes(b"\x01\x02\x03\x04")
    first, second = tmp_path / "a.urimg", tmp_path / "b.urimg"
    assert stamp_image.main(["stamp", str(binary), "--hardware", "slave", "--out", str(first)]) == 0
    assert stamp_image.main(["stamp", str(binary), "--hardware", "0x303CB01", "--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    assert ih.parse_header(first.read_bytes())[1].version == (1, 2, 3, 0)


def test_a_missing_version_a_bad_hardware_and_a_broken_image_are_refused(tmp_path, capsys):
    binary = tmp_path / "plain.bin"
    binary.write_bytes(b"abc")
    assert stamp_image.main(["stamp", str(binary), "--hardware", "main"]) == 1
    assert stamp_image.main(["stamp", str(binary), "--hardware", "nope", "--version", "1.0.0"]) == 1
    assert stamp_image.main(["stamp", str(binary), "--hardware", "main", "--version", "70000.0.0"]) == 1
    good = tmp_path / "good.urimg"
    assert stamp_image.main(["stamp", str(binary), "--hardware", "main", "--version", "1.0.0", "--out", str(good)]) == 0
    broken = tmp_path / "broken.urimg"
    broken.write_bytes(good.read_bytes()[:-1])
    assert stamp_image.main(["check", str(broken)]) == 1
    assert "bad_length" in capsys.readouterr().out


@pytest.mark.parametrize("text", ["1.2", "1.2.x", "1.2.3.4.5", "256.0.0.0".replace("256", "70000")])
def test_a_version_that_is_not_four_numbers_is_refused(text):
    with pytest.raises(ValueError):
        stamp_image.parse_version(text)
