# =============================================================================
# URTC-COMMON - tests/test_image_header_edges.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Edge cases of the image header: any byte flipped, random input, other buffer types, and the limits of the compatibility switch. Generated inputs use a fixed seed."""
from __future__ import annotations

import random
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import image_header as ih  # noqa: E402

HARDWARE = 0x0303CC01
VERSION = (0, 8, 1, 3)


def _sealed(length: int = 768) -> bytes:
    raw = bytearray((i * 31 + 7) & 0x7F for i in range(length))
    raw[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = ih.embedded_slot(HARDWARE, VERSION)
    return ih.seal_embedded(bytes(raw))


def test_no_single_bit_of_a_sealed_image_can_change_without_being_noticed():
    sealed = _sealed()
    assert ih.verify_embedded(sealed)[0] == ih.OK
    for index in range(len(sealed)):
        for bit in range(8):
            broken = bytearray(sealed)
            broken[index] ^= 1 << bit
            assert ih.verify_embedded(bytes(broken))[0] != ih.OK, (index, bit)


def test_a_flipped_bit_is_refused_by_every_policy_that_still_sees_the_header():
    sealed = _sealed()
    for index in range(ih.EMBED_OFFSET + 4, len(sealed), 7):   # the magic itself is the one thing that turns an image into a "legacy" one
        broken = bytearray(sealed)
        broken[index] ^= 0x10
        for policy in ih.POLICIES:
            assert not ih.inspect_image(bytes(broken), policy, HARDWARE, VERSION).accepted, (index, policy)
    spoiled_magic = bytearray(sealed)
    spoiled_magic[ih.EMBED_OFFSET] ^= 0x01
    assert not ih.inspect_image(bytes(spoiled_magic), ih.POLICY_REQUIRE).accepted


def test_random_bytes_never_raise_and_never_pass_for_an_image():
    rng = random.Random(1103)
    for _ in range(300):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 900)))
        assert ih.parse_header(blob)[0] != ih.OK or len(blob) >= ih.HEADER_SIZE
        assert ih.verify_image(blob)[0] != ih.OK
        assert ih.verify_embedded(blob)[0] != ih.OK
        for policy in ih.POLICIES:
            check = ih.inspect_image(blob, policy)
            assert check.kind in (ih.KIND_LEGACY, ih.KIND_EMBEDDED, ih.KIND_STAMPED_FILE)
            if check.kind != ih.KIND_LEGACY:
                assert not check.accepted


def test_a_header_with_valid_magic_and_random_tail_is_never_accepted():
    rng = random.Random(2207)
    for _ in range(200):
        body = struct.pack(">I", ih.MAGIC) + bytes(rng.randrange(256) for _ in range(28))
        status, info = ih.parse_header(body)
        assert status != ih.OK and info is None


def test_bytearray_and_memoryview_give_the_same_answer_as_bytes():
    sealed = _sealed()
    assert ih.verify_embedded(bytearray(sealed))[0] == ih.OK
    assert ih.verify_embedded(memoryview(sealed).tobytes())[0] == ih.OK
    assert ih.inspect_image(bytearray(sealed), ih.POLICY_REQUIRE, HARDWARE, VERSION).accepted
    assert ih.parse_header(bytearray(ih.make_header(b"abc", HARDWARE, VERSION)))[0] == ih.OK


def test_the_version_a_caller_expects_may_have_three_or_four_components():
    sealed = _sealed()
    assert ih.inspect_image(sealed, ih.POLICY_REQUIRE, version=(0, 8, 1)).accepted
    assert ih.inspect_image(sealed, ih.POLICY_REQUIRE, version=(0, 8)).accepted
    assert ih.inspect_image(sealed, ih.POLICY_REQUIRE, version=VERSION).accepted
    for wrong in ((0, 8, 2), (1, 8, 1), (0, 8, 1, 4), (0, 8, 1, 3, 0)):
        check = ih.inspect_image(sealed, ih.POLICY_ACCEPT, version=wrong)
        assert not check.accepted and check.reason == ih.REASON_VERSION and check.info is not None


def test_the_hardware_a_caller_expects_is_compared_exactly():
    sealed = _sealed()
    for wrong in (0, HARDWARE ^ 1, HARDWARE ^ 0x80000000, 0xFFFFFFFF):
        check = ih.inspect_image(sealed, ih.POLICY_ACCEPT, hardware_id=wrong)
        assert not check.accepted and check.reason == ih.REASON_HARDWARE
    assert ih.inspect_image(sealed, ih.POLICY_ACCEPT, hardware_id=HARDWARE).accepted


def test_hardware_is_checked_before_version_when_both_are_wrong():
    check = ih.inspect_image(_sealed(), ih.POLICY_WARN, hardware_id=1, version=(9, 9, 9))
    assert check.reason == ih.REASON_HARDWARE


def test_a_signed_flag_or_a_missing_embedded_flag_in_the_slot_is_refused():
    sealed = bytearray(_sealed())
    for flags in (ih.FLAG_EMBEDDED | ih.FLAG_SIGNED, 0, ih.FLAG_SIGNED):
        info = ih.ImageInfo(HARDWARE, 0, 8, 1, 3, flags, len(sealed), ih.embedded_crc(bytes(sealed)))
        forged = bytes(sealed[:ih.EMBED_OFFSET]) + ih.pack_header(info) + bytes(sealed[ih.EMBED_OFFSET + 32:])
        assert ih.verify_embedded(forged)[0] == ih.BAD_FLAGS, flags


def test_the_stated_length_must_be_the_length_of_the_whole_image():
    sealed = _sealed()
    assert ih.verify_embedded(sealed + b"\x00")[0] == ih.BAD_LENGTH
    assert ih.verify_embedded(sealed[:-1])[0] == ih.BAD_LENGTH
    smallest = _sealed(ih.EMBED_OFFSET + ih.HEADER_SIZE)
    assert ih.verify_embedded(smallest)[0] == ih.OK
    assert ih.verify_embedded(smallest[:-1])[0] == ih.SHORT


def test_a_slot_that_is_the_wrong_hardware_still_seals_when_no_hardware_is_asked_for():
    other = bytearray(768)
    other[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = ih.embedded_slot(0x12345678, (1, 2, 3, 4))
    sealed = ih.seal_embedded(bytes(other))
    status, info = ih.verify_embedded(sealed)
    assert status == ih.OK and info is not None and info.hardware_id == 0x12345678 and info.version_text() == "1.2.3.4"


def test_a_slot_with_a_reserved_byte_set_or_a_signature_flag_is_not_the_slot_of_the_firmware():
    base = bytearray(768)
    slot = bytearray(ih.embedded_slot(HARDWARE, VERSION))
    slot[18] = 1   # the reserved field
    base[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = slot
    with pytest.raises(ValueError, match="no header slot"):
        ih.seal_embedded(bytes(base))
    signed_slot = bytearray(ih.embedded_slot(HARDWARE, VERSION))
    signed_slot[7] |= ih.FLAG_SIGNED
    base[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = signed_slot
    with pytest.raises(ValueError, match="no header slot"):
        ih.seal_embedded(bytes(base))


def test_sealing_is_the_same_bytes_whatever_the_content_around_the_slot():
    rng = random.Random(77)
    for _ in range(20):
        raw = bytearray(rng.randrange(256) for _ in range(rng.randrange(ih.EMBED_OFFSET + 32, 2000)))
        raw[ih.EMBED_OFFSET:ih.EMBED_OFFSET + 32] = ih.embedded_slot(HARDWARE, VERSION)
        first = ih.seal_embedded(bytes(raw))
        assert ih.seal_embedded(bytes(raw)) == first and ih.seal_embedded(first) == first
        assert ih.verify_embedded(first)[0] == ih.OK
        assert zlib.crc32(first[:ih.EMBED_OFFSET]) == zlib.crc32(raw[:ih.EMBED_OFFSET])


@pytest.mark.parametrize("value", [None, "", "  ", "WARN", " Require\n", "accept", "ACCEPT ", "0", "false", "off", 0, 1, True, False, [], "reject", "rEqUiRe"])
def test_the_switch_never_loosens_on_a_strange_setting(value):
    parsed = ih.parse_policy(value)
    assert parsed in ih.POLICIES
    text = "" if value is None else str(value).strip().lower()
    if text in ("", "warn", "accept", "require"):
        assert parsed == (ih.DEFAULT_POLICY if text == "" else text)
    else:
        assert parsed == ih.POLICY_REQUIRE


def test_an_image_without_header_follows_the_switch_and_nothing_else():
    legacy = bytes(range(256)) * 4
    assert ih.inspect_image(legacy, ih.POLICY_ACCEPT).reason == ih.REASON_OK
    warned = ih.inspect_image(legacy, ih.POLICY_WARN)
    assert warned.accepted and warned.warn and warned.reason == ih.REASON_NO_HEADER
    refused = ih.inspect_image(legacy, ih.POLICY_REQUIRE)
    assert not refused.accepted and refused.reason == ih.REASON_REQUIRED
    assert ih.inspect_image(b"", ih.POLICY_REQUIRE).reason == ih.REASON_REQUIRED
    assert ih.inspect_image(b"", ih.POLICY_ACCEPT).accepted
