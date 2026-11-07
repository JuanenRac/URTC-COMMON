# =============================================================================
# URTC-COMMON - tests/test_gap_cases.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. Limits and refusals the other tests do not reach: the trust table, the .imgsig text, the rotation
command and the bus-load arithmetic. Keys are throwaway values derived from a label. Fast and deterministic."""
from __future__ import annotations

import hashlib
import random
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import image_auth as ia  # noqa: E402
from urtc_common import image_sig as isg  # noqa: E402
from urtc_common import key_rotation_command as krc  # noqa: E402
from urtc_common import multinode as mn  # noqa: E402


def _pub(label: str) -> bytes:
    return hashlib.sha256(label.encode()).digest()


# ---- the trust table -------------------------------------------------------------------------------------------------------------------
def test_a_table_holds_one_or_two_keys():
    for count in (0, 3):
        with pytest.raises(isg.TrustError, match="one or two"):
            isg.pack_table([(_pub(str(i)), isg.FLAG_CURRENT) for i in range(count)])


def test_a_public_key_is_32_bytes():
    for size in (0, 31, 33):
        with pytest.raises(isg.TrustError, match="32 bytes"):
            isg.pack_table([(bytes(size), isg.FLAG_CURRENT)])


def test_only_valid_states_of_a_key_are_packed():
    pub = _pub("k")
    bad_flags = (0, 8, 16, 0xFF, isg.FLAG_REVOKED | isg.FLAG_CURRENT, isg.FLAG_REVOKED | isg.FLAG_NEXT, isg.FLAG_CURRENT | isg.FLAG_NEXT)
    for flags in bad_flags:
        with pytest.raises(isg.TrustError, match="not a valid state"):
            isg.pack_table([(pub, flags)])
    for flags in (isg.FLAG_CURRENT, isg.FLAG_NEXT, isg.FLAG_REVOKED):
        assert isg.parse_table(isg.pack_table([(pub, flags)])) == [(pub, flags)]


def test_a_table_round_trips_and_names_its_keys():
    keys = [(_pub("a"), isg.FLAG_CURRENT), (_pub("b"), isg.FLAG_NEXT)]
    table = isg.parse_table(isg.pack_table(keys))
    assert table == keys
    assert len(isg.pack_table(keys)) == isg.table_size(2)
    assert isg.fingerprints(table) == [ia.key_id(_pub("a")).hex(), ia.key_id(_pub("b")).hex()]
    assert isg.fingerprints([]) == []
    assert isg.parse_table(isg.pack_table(keys) + b"trailing bytes are ignored") == keys


def test_every_single_byte_change_to_a_table_is_refused_or_changes_it():
    keys = [(_pub("a"), isg.FLAG_CURRENT), (_pub("b"), isg.FLAG_NEXT)]
    good = isg.pack_table(keys)
    for index in range(len(good)):
        broken = bytearray(good)
        broken[index] ^= 0x01
        try:
            parsed = isg.parse_table(bytes(broken))
        except isg.TrustError:
            continue
        assert parsed != keys, f"a flipped bit at byte {index} went unnoticed"


def test_every_cut_of_a_table_is_refused():
    good = isg.pack_table([(_pub("a"), isg.FLAG_CURRENT), (_pub("b"), isg.FLAG_NEXT)])
    for size in range(len(good)):
        with pytest.raises(isg.TrustError):
            isg.parse_table(good[:size])


def test_a_table_with_a_repeated_key_or_two_current_keys_is_refused():
    def table(entries):
        body = isg.TABLE_MAGIC + bytes([isg.TABLE_SCHEMA, len(entries), 0, 0])
        for public, flags in entries:
            body += ia.key_id(public) + public + bytes([flags]) + bytes(3)
        return body + (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "little")

    with pytest.raises(isg.TrustError, match="twice"):
        isg.parse_table(table([(_pub("a"), isg.FLAG_CURRENT), (_pub("a"), isg.FLAG_NEXT)]))
    with pytest.raises(isg.TrustError, match="more than one current"):
        isg.parse_table(table([(_pub("a"), isg.FLAG_CURRENT), (_pub("b"), isg.FLAG_CURRENT)]))
    assert isg.parse_table(table([(_pub("a"), isg.FLAG_CURRENT), (_pub("b"), isg.FLAG_REVOKED)]))


# ---- the .imgsig text ------------------------------------------------------------------------------------------------------------------
def test_an_imgsig_is_one_line_of_the_record_in_hex():
    record = bytes(range(ia.RECORD_SIZE))
    text = isg.encode_imgsig(record)
    assert text == record.hex() + "\n" and isg.decode_imgsig(text) == record and isg.decode_imgsig(text.upper()) == record
    assert isg.decode_imgsig(text[:-1]) == record
    for size in (0, 1, ia.RECORD_SIZE - 1, ia.RECORD_SIZE + 1):
        with pytest.raises(isg.TrustError, match="bytes"):
            isg.encode_imgsig(bytes(size))


def test_a_malformed_imgsig_is_refused():
    good = isg.encode_imgsig(bytes(ia.RECORD_SIZE))[:-1]
    for bad in ("", good[:-1], good + "0", good[:-1] + "g", good[:-1] + " ", "\n" + good, good + "\n\n", good + "\r\n", " " + good):
        with pytest.raises(isg.TrustError):
            isg.decode_imgsig(bad)


def test_the_counter_of_a_signature_is_32_bits():
    seed = _pub("seed")
    header, payload = bytes(ia.HEADER_BYTES), b"image"
    for counter in (-1, 0x100000000):
        with pytest.raises(isg.TrustError, match="32 bits"):
            isg.sign_image(seed, header, payload, counter)
    for counter in (0, 1, 0xFFFFFFFF):
        text = isg.sign_image(seed, header, payload, counter)
        assert len(isg.decode_imgsig(text)) == ia.RECORD_SIZE
    assert isg.sign_image(seed, header, payload, 1) == isg.sign_image(seed, header, payload, 1)
    assert isg.sign_image(seed, header, payload, 1) != isg.sign_image(seed, header, payload, 2)
    assert isg.sign_image(seed, header, payload, 1) != isg.sign_image(seed, header, payload + b"!", 1)


# ---- the signed rotation command -------------------------------------------------------------------------------------------------------
def test_the_body_and_the_chunks_refuse_the_wrong_size():
    for size in (0, krc.BODY_SIZE - 1, krc.BODY_SIZE + 1):
        with pytest.raises(krc.RotationCommandError, match="36"):
            krc.message(bytes(size))
    assert krc.message(bytes(krc.BODY_SIZE)) == krc.DOMAIN + bytes(krc.BODY_SIZE)
    for size in (0, krc.RECORD_SIZE - 1, krc.RECORD_SIZE + 1):
        with pytest.raises(krc.RotationCommandError, match="100"):
            krc.to_chunks(bytes(size))
        with pytest.raises(krc.RotationCommandError, match="100"):
            krc.parse(bytes(size))


def test_the_chunks_carry_the_record_in_order_and_the_last_is_padded():
    record = bytes(range(krc.RECORD_SIZE))
    chunks = krc.to_chunks(record)
    assert len(chunks) == krc.CHUNK_COUNT and all(len(c) == 8 and krc.is_chunk(c) for c in chunks)
    assert [c[0] for c in chunks] == [krc.CHUNK_FLAG | n for n in range(krc.CHUNK_COUNT)]
    joined = b"".join(c[1:] for c in chunks)
    assert joined[:krc.RECORD_SIZE] == record and joined[krc.RECORD_SIZE:] == bytes(len(joined) - krc.RECORD_SIZE)


def test_what_is_and_is_not_a_chunk():
    flag = krc.CHUNK_FLAG
    assert krc.is_chunk(bytes([flag]) + bytes(7)) and krc.is_chunk(bytes([flag + krc.CHUNK_COUNT - 1]) + bytes(7))
    assert not krc.is_chunk(bytes([flag + krc.CHUNK_COUNT]) + bytes(7)) and not krc.is_chunk(bytes([flag - 1]) + bytes(7))
    assert not krc.is_chunk(bytes([flag]) + bytes(6)) and not krc.is_chunk(bytes([flag]) + bytes(8)) and not krc.is_chunk(b"")


def test_a_signed_command_parses_into_its_fields_and_is_deterministic():
    seed = _pub("release")
    new, prev = _pub("new"), _pub("old")
    record = krc.sign(seed, krc.key_id(new), krc.key_id(prev), 600, 1234, 7)
    assert record == krc.sign(seed, krc.key_id(new), krc.key_id(prev), 600, 1234, 7)
    command = krc.parse(record)
    assert (command.window_s, command.host_time, command.counter) == (600, 1234, 7)


# ---- the bus-load arithmetic -----------------------------------------------------------------------------------------------------------
def test_the_frame_size_grows_with_the_data_and_the_worst_case_adds_stuff_bits():
    sizes = [mn.frame_bits(dlc) for dlc in range(9)]
    assert all(b - a == 8 for a, b in zip(sizes, sizes[1:]))
    for dlc in range(9):
        assert mn.frame_bits(dlc, True) > mn.frame_bits(dlc)
    for bad in (-1, 9, 100, 1.5, "8", None, True):
        with pytest.raises(ValueError, match="dlc"):
            mn.frame_bits(bad)


def test_the_bus_load_is_the_sum_of_the_traffic_over_the_bit_rate():
    assert mn.bus_load([], 500000) == 0.0
    one = mn.bus_load([(8, 100)], 500000)
    assert one == pytest.approx(100 * mn.frame_bits(8) / 500000)
    assert mn.bus_load([(8, 100), (8, 100)], 500000) == pytest.approx(2 * one)
    assert mn.bus_load([(8, 100)], 250000) == pytest.approx(2 * one)
    assert mn.bus_load([(8, 100)], 500000, worst_case=True) > one
    for rate in (0, -1):
        with pytest.raises(ValueError, match="bitrate"):
            mn.bus_load([(8, 1)], rate)


def test_the_discover_delay_is_the_address_times_the_slot():
    last = mn.p.MN_ADDRESS_MASK
    assert mn.discover_answer_delay_ms(0) == 0
    assert mn.discover_answer_delay_ms(last) == last * mn.p.MN_DISCOVER_SLOT_MS
    assert mn.discover_answer_delay_ms(3, slot_ms=5) == 15
    for bad in (-1, last + 1, 1000):
        with pytest.raises(ValueError, match="outside"):
            mn.discover_answer_delay_ms(bad)
    delays = [mn.discover_answer_delay_ms(n) for n in range(last + 1)]
    assert delays == sorted(delays) and len(set(delays)) == len(delays)


def test_random_tables_and_commands_never_crash_the_parsers():
    rng = random.Random(20260507)
    for _ in range(500):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 120)))
        try:
            isg.parse_table(blob)
        except isg.TrustError:
            pass
        try:
            krc.parse(blob)
        except krc.RotationCommandError:
            pass
        assert krc.is_chunk(blob) in (True, False)
