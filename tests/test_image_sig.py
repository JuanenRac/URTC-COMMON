# =============================================================================
# URTC-COMMON - tests/test_image_sig.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. The trust table and the .imgsig record: the Python reference held to the shared vectors and to hand-written
expectations. Every key made here is a throwaway: derived from a label or generated at random for the test, never stored."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_image_sig_vectors as maker  # noqa: E402
from urtc_common import image_auth as ia, image_header as ih, image_sig as sg  # noqa: E402

DOC = json.loads((ROOT / "conformance" / "image_sig_vectors.json").read_text(encoding="utf-8"))
HAND_WRITTEN = ["ok", "ok", "unknown_key", "unknown_key", "unknown_key", "ok", "rollback_counter", "bad_signature", "bad_signature", "hardware_mismatch",
                "bad_signature", "bad_signature", "unknown_key", "bad_args"]


def test_vectors_are_current():
    assert maker.main(["--check"]) == 0


@pytest.mark.parametrize("c", DOC["table_cases"], ids=[c["name"] for c in DOC["table_cases"]])
def test_table_cases(c):
    data = bytes.fromhex(c["table"])
    if not c["valid"]:
        with pytest.raises(sg.TrustError):
            sg.parse_table(data)
        return
    keys = sg.parse_table(data)
    assert [[p.hex(), f] for p, f in keys] == c["keys"]
    assert [k.hex() for k in sg.trusted_keys(keys)] == c["trusted"]


@pytest.mark.parametrize("c", DOC["imgsig_text_cases"], ids=[c["name"] for c in DOC["imgsig_text_cases"]])
def test_imgsig_text_cases(c):
    if c["valid"]:
        assert len(sg.decode_imgsig(c["text"])) == 76
    else:
        with pytest.raises(sg.TrustError):
            sg.decode_imgsig(c["text"])


def test_verify_cases_match_the_hand_written_verdicts():
    assert [c["expected"] for c in DOC["verify_cases"]] == HAND_WRITTEN
    for c in DOC["verify_cases"]:
        got = sg.verify_image(c["imgsig"], sg.parse_table(bytes.fromhex(c["table"])), c["hardware_id"], bytes.fromhex(c["header"]),
                              bytes.fromhex(c["payload"]), c["floor"])
        assert got == c["expected"], c["name"]


def test_the_layout_is_the_documented_one():
    cur = sg.public_of(maker.seed("current"))
    table = sg.pack_table([(cur, sg.FLAG_CURRENT)])
    assert len(table) == sg.table_size(1) == 56 and sg.table_size(2) == 100
    assert table[:4] == b"TKEY" and table[4] == 1 and table[5] == 1
    assert table[8:16] == ia.key_id(cur) and table[16:48] == cur and table[48] == 1


def test_a_table_is_found_at_its_offset_in_a_binary():
    cur = sg.public_of(maker.seed("current"))
    table = sg.pack_table([(cur, sg.FLAG_CURRENT)])
    binary = bytes(range(256)) * 2 + table + b"\xaa" * 40
    assert sg.find_table(binary, 512) == [(cur, 1)]
    with pytest.raises(sg.TrustError):
        sg.find_table(binary, 513)
    with pytest.raises(sg.TrustError):
        sg.find_table(binary, len(binary))


def test_an_ephemeral_key_signs_and_only_its_own_table_verifies():
    seed = os.urandom(32)   # ephemeral: never written anywhere
    payload = os.urandom(300)
    header = ih.make_header(payload, maker.HARDWARE_MAIN, (0, 9, 0, 1), signed=False)[:28]
    text = sg.sign_image(seed, header, payload, 9)
    mine = sg.pack_table([(sg.public_of(seed), sg.FLAG_CURRENT)])
    other = sg.pack_table([(sg.public_of(os.urandom(32)), sg.FLAG_CURRENT)])
    assert sg.verify_image(text, sg.parse_table(mine), maker.HARDWARE_MAIN, header, payload) == "ok"
    assert sg.verify_image(text, sg.parse_table(other), maker.HARDWARE_MAIN, header, payload) == "unknown_key"


def test_the_development_seed_is_public_and_distinct_from_the_test_labels():
    assert len(sg.DEV_SEED) == 32 and sg.DEV_SEED != maker.seed("current")


def test_the_confirmation_of_the_slave_bootloader_matches_the_vector_the_firmware_holds():
    """The same inputs and the same expected tag are written in the firmware repository's host test (tests/test_slaveboot_update.c)."""
    nonce = bytes(range(16))
    digest = __import__("hashlib").sha256(b"abc").digest()
    message = sg.slave_confirm_message(nonce, digest, 0x0303CB01, 0, 0x8105, 1500, 7)
    assert len(message) == sg.SLAVE_CONFIRM_MESSAGE_SIZE == 80
    assert message.startswith(b"URTC-SLV-CONF-V2") and message[-4:] == bytes([0, 0, 0, 7])
    assert sg.slave_confirm_tag(nonce, digest, 0x0303CB01, 0, 0x8105, 1500, 7).hex() == "a637032764ca876c2bba6ca32e53ec8dab464342a9be65d52482a40d821f957f"
    # every field changes the tag, the counter included
    base = sg.slave_confirm_tag(nonce, digest, 0x0303CB01, 0, 0x8105, 1500, 7)
    assert sg.slave_confirm_tag(nonce, digest, 0x0303CB01, 0, 0x8105, 1500, 8) != base
    assert sg.slave_confirm_tag(nonce[::-1], digest, 0x0303CB01, 0, 0x8105, 1500, 7) != base
    with pytest.raises(sg.TrustError):
        sg.slave_confirm_message(nonce, digest, 0x0303CB01, 0, 0x8105, 1500, 1 << 32)
    with pytest.raises(sg.TrustError):
        sg.slave_confirm_message(nonce[:15], digest, 0x0303CB01, 0, 0x8105, 1500, 7)
