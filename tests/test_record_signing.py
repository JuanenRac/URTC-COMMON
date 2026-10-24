# =============================================================================
# URTC-COMMON - tests/test_record_signing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Signing of session records and update reports with a key of the user."""
from __future__ import annotations

import stat
import sys

import pytest

from urtc_common import record_signing as rs
from urtc_common import self_update as su

# RFC 8032, section 7.1, test 1 (empty message).
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUBLIC = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)

MANIFEST = {"log_file": "session_log.txt", "log_sha256": "ab" * 32, "log_bytes": 120, "port": "COM3"}


def test_rfc8032_vector():
    assert rs.public_key(SEED) == PUBLIC
    assert rs.sign(SEED, b"") == SIGNATURE
    assert su.ed25519_verify(PUBLIC, b"", SIGNATURE)


def test_second_rfc_vector():
    seed = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    public = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
    assert rs.public_key(seed) == public
    assert su.ed25519_verify(public, bytes.fromhex("72"), rs.sign(seed, bytes.fromhex("72")))


def test_session_round_trip_and_tampering():
    signed = rs.sign_session(MANIFEST, SEED)
    assert signed["signature"]["key_id"] == rs.key_id(PUBLIC)
    assert signed["signature"]["algorithm"] == "Ed25519"
    assert rs.verify_session(signed)
    # the context is not signed; the name, the hash and the size of the log are
    assert rs.verify_session({**signed, "port": "COM9"})
    for field, value in (("log_sha256", "cd" * 32), ("log_bytes", 121), ("log_file", "other.txt")):
        assert not rs.verify_session({**signed, field: value})


def test_signature_of_another_kind_does_not_pass():
    report = {"report_sha256": "ef" * 32, "log_file": "x", "log_sha256": "ef" * 32, "log_bytes": 1}
    signed = rs.sign_report(report, SEED)
    assert rs.verify_report(signed)
    assert not rs.verify_session({**signed})
    assert not rs.verify_report({**signed, "report_sha256": "00" * 32})


@pytest.mark.parametrize("block", [None, {}, [], {"algorithm": "RSA"}, {"algorithm": "Ed25519", "public_key": "zz", "signature": "00"}])
def test_malformed_blocks_are_refused(block):
    record = {**MANIFEST, "signature": block}
    assert not rs.verify_session(record)


def test_key_id_must_match_the_public_key():
    signed = rs.sign_session(MANIFEST, SEED)
    signed["signature"]["key_id"] = "0" * 16
    assert not rs.verify_session(signed)


def test_key_file_is_created_once_and_reused(tmp_path):
    path = tmp_path / "keys" / "records.key"
    first = rs.load_seed(path)
    assert len(first) == 32 and path.is_file()
    assert rs.load_seed(path) == first
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_key_file_without_create_and_bad_content(tmp_path):
    with pytest.raises(rs.SigningError):
        rs.load_seed(tmp_path / "none.key", create=False)
    bad = tmp_path / "bad.key"
    bad.write_text("not hex", encoding="ascii")
    with pytest.raises(rs.SigningError):
        rs.load_seed(bad)
    bad.write_text("00" * 5, encoding="ascii")
    with pytest.raises(rs.SigningError):
        rs.load_seed(bad)


def test_environment_names_the_key_file(tmp_path, monkeypatch):
    path = tmp_path / "mine.key"
    monkeypatch.setenv(rs.KEY_ENV, str(path))
    assert rs.default_key_path() == path
    signed = rs.sign_session(MANIFEST)
    assert path.is_file() and rs.verify_session(signed)
