# =============================================================================
# URTC-COMMON - tests/test_key_rotation.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. Rotation of the signing key: two fingerprints inside a configurable window, one outside."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_key_rotation_vectors as maker  # noqa: E402
from urtc_common import ed25519, image_auth as ia, key_rotation as kr  # noqa: E402

DOC = json.loads((ROOT / "conformance" / "key_rotation_vectors.json").read_text(encoding="utf-8"))


def rot_of(c):
    return kr.Rotation(bytes.fromhex(c["current"]), bytes.fromhex(c["previous"]) if c["previous"] else None, c["window_s"], c["started_at"],
                       frozenset(bytes.fromhex(r) for r in c["revoked"]))


def test_vectors_are_current():
    assert maker.main(["--check"]) == 0


@pytest.mark.parametrize("c", DOC["cases"], ids=[c["name"] for c in DOC["cases"]])
def test_vector_cases(c):
    rot = rot_of(c)
    frames, status = kr.announce(rot, c["now"])
    assert [f.hex() for f in frames] == c["accepted"]
    parsed = kr.parse_status(status)
    assert parsed and parsed["count"] == len(c["accepted"]) and parsed["seconds_left"] == c["seconds_left"]
    assert status[2] == c["flags"]
    for a in c["accepted"]:
        assert kr.is_accepted(rot, c["now"], bytes.fromhex(a))
    for r in c["refused"]:
        assert not kr.is_accepted(rot, c["now"], bytes.fromhex(r))


def test_window_is_a_parameter_not_a_constant():
    new, old = b"N" * 8, b"O" * 8
    for window in (1, 60, 86400):
        r = kr.Rotation(new, old, window, 100)
        assert kr.is_accepted(r, 100 + window - 1, old) and not kr.is_accepted(r, 100 + window, old)


def test_malformed_inputs_never_accepted():
    r = kr.Rotation(b"N" * 8, b"O" * 8, 60, 0)
    assert not kr.is_accepted(r, 1, b"N" * 7) and not kr.is_accepted(r, 1, b"")
    with pytest.raises(ValueError):
        kr.active_key_ids(kr.Rotation(b"short"), 0)
    assert kr.parse_status(b"\x05\x03\x00\x00\x00\x00\x00") is None and kr.parse_status(b"\x06\x01\x00\x00\x00\x00\x00") is None
    assert kr.parse_status(b"\x05\x01\x04\x00\x00\x00\x00") is None and kr.parse_status(b"\x05\x01") is None


def test_host_check():
    a, b = b"A" * 8, b"B" * 8
    assert kr.host_check([], a) == "no_data" and kr.host_check([a, b], b) == "match" and kr.host_check([a], b) == "differs"
    assert kr.host_check([a, b, b"C" * 8], b"C" * 8) == "differs" and kr.host_check([b"short"], a) == "no_data"


def _signed(seed: bytes):
    header = bytes(8) + (0x1234).to_bytes(4, "big") + bytes(16)
    sha = hashlib.sha256(b"payload").digest()
    return header, sha, ia.make_record(seed, header, sha, 1)


def test_policy_is_not_relaxed_and_expired_key_cannot_install():
    seed_old, seed_new = b"\x01" * 32, b"\x02" * 32
    pub_old, pub_new = ed25519.public_key(seed_old), ed25519.public_key(seed_new)
    rot = kr.Rotation(ia.key_id(pub_new), ia.key_id(pub_old), 100, 0)
    header, sha, rec_old = _signed(seed_old)

    def installable(now, policy=ia.POLICY_ED25519_ONLY, record=rec_old):
        active = set(kr.active_key_ids(rot, now))
        keys = [k for k in (pub_old, pub_new) if ia.key_id(k) in active]
        return ia.decide(policy, keys, 0x1234, 0, None, False, header, sha, record, False)[0]

    assert installable(50) == ia.OK                        # both valid
    assert installable(100) == ia.UNKNOWN_KEY              # the old key expired with the window
    assert installable(100, ia.POLICY_ED25519_ONLY, _signed(seed_new)[2]) == ia.OK
    assert ia.POLICY_DEFAULT == ia.POLICY_ED25519_ONLY     # the rotation does not touch the default policy
    assert installable(100, ia.POLICY_EITHER) == ia.UNKNOWN_KEY   # no HMAC fallback was granted by the rotation
