# =============================================================================
# URTC-COMMON - tests/test_evidence_signing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional Ed25519 signature of an evidence record: outside the digest, over it, shown in the history and in the report."""
from __future__ import annotations

import copy
import html
import json

import pytest

from urtc_common import evidence, evidence_history, evidence_report, evidence_report_strings
from urtc_common import record_signing as rs

SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
OTHER_SEED = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
PUBLIC = rs.public_key(SEED)


def record(**changes) -> dict:
    values = dict(kind="test", outcome="pass", timestamp_utc="2026-01-02T03:04:05Z", tool="URTC Tester", tool_version="1.2.3", detail="ok")
    values.update(changes)
    return evidence.build(**values)


def folder_with(tmp_path, *records) -> list:
    for number, item in enumerate(records):
        (tmp_path / f"r{number}.json").write_text(json.dumps(item), encoding="utf-8")
    return evidence_history.load_folder(tmp_path)


# --- characterization: what the digest and the check did before the signature existed ---

def test_an_unsigned_record_keeps_its_digest_and_passes():
    item = record()
    assert evidence.verify(item) == []
    assert "signature" not in item
    assert item["evidence_sha256"] == evidence.digest(item)


def test_signing_does_not_change_the_digest():
    item = record()
    signed = rs.sign_evidence(item, SEED)
    assert signed["evidence_sha256"] == item["evidence_sha256"]
    assert evidence.digest(signed) == item["evidence_sha256"]
    assert evidence.verify(signed) == []
    assert "signature" not in item          # the original is not changed


# --- the signature itself ---

def test_a_valid_signature_verifies_and_names_its_key():
    signed = rs.sign_evidence(record(), SEED)
    assert rs.verify_evidence(signed)
    assert rs.verify_evidence(signed, PUBLIC)
    assert signed["signature"]["key_id"] == rs.key_id(PUBLIC)
    assert signed["signature"]["algorithm"] == "Ed25519"
    assert rs.evidence_state(signed) == "valid"
    assert rs.evidence_state(signed, PUBLIC) == "valid"


def test_the_state_of_an_unsigned_record_is_unsigned():
    assert rs.evidence_state(record()) == "unsigned"
    assert not rs.verify_evidence(record())


def test_a_signature_by_another_key_is_told_apart_when_a_key_is_given():
    signed = rs.sign_evidence(record(), OTHER_SEED)
    assert rs.evidence_state(signed) == "valid"                   # no key pinned: the block and the record belong together
    assert rs.evidence_state(signed, PUBLIC) == "other_key"       # pinned: not by that key
    assert not rs.verify_evidence(signed, PUBLIC)


@pytest.mark.parametrize("field,value", [("outcome", "fail"), ("detail", "changed"), ("tool_version", "9.9.9")])
def test_editing_a_signed_record_breaks_the_check_and_the_signature(field, value):
    signed = rs.sign_evidence(record(), SEED)
    edited = {**signed, field: value}
    assert evidence.verify(edited)                 # the digest no longer matches
    assert not rs.verify_evidence(edited)
    assert rs.evidence_state(edited) == "invalid"


def test_editing_the_digest_too_still_breaks_the_signature():
    signed = rs.sign_evidence(record(), SEED)
    forged = {**signed, "outcome": "fail"}
    forged["evidence_sha256"] = evidence.digest(forged)      # an editor who fixes the digest
    assert evidence.verify(forged) == []                    # the digest alone cannot tell
    assert not rs.verify_evidence(forged)                   # the signature can
    assert rs.evidence_state(forged) == "invalid"


def test_a_signature_cut_from_another_record_does_not_pass():
    first, second = record(detail="one"), record(detail="two")
    graft = {**second, "signature": rs.sign_evidence(first, SEED)["signature"]}
    assert evidence.verify(graft) == []
    assert rs.evidence_state(graft) == "invalid"


@pytest.mark.parametrize("block", [
    None, [], "x", {}, {"algorithm": "RSA"},
    {"algorithm": "Ed25519", "key_id": "0" * 16, "public_key": "0" * 64},                              # no signature
    {"algorithm": "Ed25519", "key_id": "0" * 16, "public_key": "0" * 64, "signature": "0" * 127},      # too short
    {"algorithm": "Ed25519", "key_id": "0" * 16, "public_key": "0" * 64, "signature": "0" * 128, "extra": 1},
    {"algorithm": "Ed25519", "key_id": "0" * 16, "public_key": "Z" * 64, "signature": "0" * 128},
])
def test_a_malformed_block_makes_the_record_not_valid(block):
    item = {**record(), "signature": block}
    assert any("signature" in problem for problem in evidence.verify(item))
    assert rs.evidence_state(item) == "invalid"


def test_a_well_formed_block_with_wrong_numbers_is_invalid_not_unsigned():
    item = {**record(), "signature": {"algorithm": "Ed25519", "key_id": rs.key_id(PUBLIC), "public_key": PUBLIC.hex(), "signature": "00" * 64}}
    assert evidence.verify(item) == []
    assert rs.evidence_state(item) == "invalid"


def test_a_record_that_is_not_valid_is_never_signed():
    broken = {**record(), "outcome": "fail"}        # the digest no longer matches
    with pytest.raises(rs.SigningError):
        rs.sign_evidence(broken, SEED)


def test_signing_twice_replaces_the_block():
    once = rs.sign_evidence(record(), SEED)
    twice = rs.sign_evidence(once, OTHER_SEED)
    assert twice["signature"]["key_id"] == rs.key_id(rs.public_key(OTHER_SEED))
    assert rs.verify_evidence(twice)


def test_a_signature_of_another_kind_is_not_an_evidence_signature():
    item = record()
    block = rs.make_signature(SEED, rs.KIND_REPORT, item["evidence_sha256"])
    assert not rs.verify_evidence({**item, "signature": block})


def test_the_key_file_is_the_one_in_the_environment_and_is_not_printed(tmp_path, monkeypatch, capsys):
    key = tmp_path / "k.key"
    monkeypatch.setenv(rs.KEY_ENV, str(key))
    signed = rs.sign_evidence(record())
    assert key.is_file()
    assert rs.verify_evidence(signed)
    assert key.read_text().strip() not in json.dumps(signed)
    out = capsys.readouterr()
    assert key.read_text().strip() not in out.out + out.err


def test_parse_public_key():
    assert rs.parse_public_key(PUBLIC.hex() + "\n") == PUBLIC
    for bad in ("", "zz", "00" * 31, "00" * 33):
        with pytest.raises(rs.SigningError):
            rs.parse_public_key(bad)


# --- the history and the report ---

def test_the_history_gives_the_state_of_every_signature(tmp_path):
    signed, other, bad = rs.sign_evidence(record(detail="a"), SEED), rs.sign_evidence(record(detail="b"), OTHER_SEED), rs.sign_evidence(record(detail="c"), SEED)
    bad = {**bad, "outcome": "fail"}
    entries = folder_with(tmp_path, signed, other, bad, record(detail="d"))
    states = {e.record["detail"]: evidence_history.signature_state(e, PUBLIC) for e in entries}
    assert states == {"a": "valid", "b": "other_key", "c": "invalid", "d": "unsigned"}
    summary = evidence_history.summary(entries)
    assert summary["signed"] == 3 and summary["signature_invalid"] == 1


def test_a_record_that_fails_its_check_is_not_rescued_by_its_signature(tmp_path):
    signed = rs.sign_evidence(record(), SEED)
    forged = {**signed, "outcome": "fail"}
    (entry,) = folder_with(tmp_path, forged)
    assert not entry.valid
    assert evidence_history.signature_state(entry) == "invalid"


def test_without_the_signing_module_a_signature_is_unchecked_not_valid(tmp_path, monkeypatch):
    signed = rs.sign_evidence(record(), SEED)
    (entry,) = folder_with(tmp_path, signed)
    monkeypatch.setattr(evidence_history, "_record_signing", None)    # as in a copy that does not carry the signing module
    entry.sig_cache = ""
    assert evidence_history.signature_state(entry) == "unchecked"


def test_the_history_json_carries_the_state(tmp_path):
    entries = folder_with(tmp_path, rs.sign_evidence(record(), SEED))
    document = json.loads(evidence_history.to_json(entries))
    assert document["entries"][0]["signature"] == "valid"
    assert document["summary"]["signed"] == 1


def test_the_text_history_flags_an_invalid_signature(tmp_path):
    forged = {**rs.sign_evidence(record(), SEED), "detail": "x"}
    forged["evidence_sha256"] = evidence.digest(forged)
    entries = folder_with(tmp_path, forged)
    assert "SIGNATURE NOT VALID" in evidence_history.to_text(entries)


@pytest.mark.parametrize("language", evidence_report_strings.LANGUAGES)
def test_the_report_shows_the_signature_in_every_language(tmp_path, language):
    good = rs.sign_evidence(record(detail="good"), SEED)
    forged = {**rs.sign_evidence(record(detail="forged"), SEED), "detail": "forged!"}
    forged["evidence_sha256"] = evidence.digest(forged)
    entries = folder_with(tmp_path, good, forged, record(detail="plain"))
    page = evidence_report.to_html(entries, language)
    for key in ("ER_SIGNATURE", "ER_SIG_VALID", "ER_SIG_INVALID", "ER_SIG_UNSIGNED", "ER_BANNER_SIG_INVALID", "ER_SIG_NOTE"):
        assert html.escape(evidence_report_strings.text(language, key), quote=True) in page, key
    assert rs.key_id(PUBLIC) in page
    text = evidence_report.to_text(entries, language)
    assert evidence_report_strings.text(language, "ER_BANNER_SIG_INVALID") in text
    assert evidence_report.render(entries, "pdf", language).startswith(b"%PDF")


def test_the_report_tells_a_signature_by_another_key_when_the_key_is_given(tmp_path):
    entries = folder_with(tmp_path, rs.sign_evidence(record(), OTHER_SEED))
    assert evidence_report_strings.text("english", "ER_SIG_OTHER_KEY") in evidence_report.to_html(entries, "english", PUBLIC)
    assert evidence_report_strings.text("english", "ER_SIG_OTHER_KEY") not in evidence_report.to_html(entries, "english")


def test_the_report_never_prints_a_seed(tmp_path):
    entries = folder_with(tmp_path, rs.sign_evidence(record(), SEED))
    assert SEED.hex() not in evidence_report.to_html(entries) + evidence_report.to_text(entries)


def test_the_same_signed_records_give_the_same_report(tmp_path):
    entries = folder_with(tmp_path, rs.sign_evidence(record(), SEED))
    assert evidence_report.to_html(copy.copy(entries)) == evidence_report.to_html(entries)


def test_new_strings_have_the_same_placeholders_in_every_language():
    keys = [k for k in evidence_report_strings.STRINGS["english"] if "SIG" in k or k == "ER_F_KEY_ID"]
    assert len(keys) >= 10
    for language in evidence_report_strings.LANGUAGES:
        for key in keys:
            assert evidence_report_strings.STRINGS[language].get(key, "").strip(), (language, key)
