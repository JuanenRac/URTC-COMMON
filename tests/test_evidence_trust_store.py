# =============================================================================
# URTC-COMMON - tests/test_evidence_trust_store.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The trust store of public keys (alias -> key): "signed by <alias>", "unknown key" and "invalid" in the history, the report and the window of the history;
an explicit public key wins over the store; a store never holds a private key."""
from __future__ import annotations

import html
import json

import pytest

from urtc_common import evidence, evidence_history, evidence_report, evidence_report_strings
from urtc_common import record_signing as rs

SEED_A = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
SEED_B = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
PUB_A, PUB_B = rs.public_key(SEED_A), rs.public_key(SEED_B)
STORE = {"Ana (bench 1)": PUB_A}


def record(detail: str = "ok") -> dict:
    return evidence.build(kind="test", outcome="pass", timestamp_utc="2026-01-02T03:04:05Z", tool="URTC Tester", tool_version="1.2.3", detail=detail)


def entries_of(tmp_path, *records):
    for number, item in enumerate(records):
        (tmp_path / f"r{number}.json").write_text(json.dumps(item), encoding="utf-8")
    return evidence_history.load_folder(tmp_path)


# -- characterization: without a store the states are the ones there were --------------------------------------------------------------------------
def test_without_a_store_the_states_are_unchanged():
    signed = rs.sign_evidence(record(), SEED_A)
    assert rs.evidence_state(signed) == "valid"
    assert rs.evidence_state(signed, PUB_A) == "valid"
    assert rs.evidence_state(signed, PUB_B) == "other_key"
    assert rs.evidence_state(record()) == "unsigned"
    assert rs.evidence_state({**signed, "detail": "x"}) == "invalid"
    assert rs.evidence_state(signed, None, {}) == "valid"          # an empty store is no store
    assert rs.evidence_state(signed, None, None) == "valid"


# -- the matrix: signature (good, other key, bad, none) x store (has the key, does not, empty) x explicit key -----------------------------------
@pytest.mark.parametrize("signer,store,public,expected", [
    (SEED_A, STORE, None, "trusted"),
    (SEED_B, STORE, None, "unknown_key"),
    (SEED_A, {"Bea": PUB_B}, None, "unknown_key"),
    (SEED_A, {}, None, "valid"),
    (SEED_A, STORE, PUB_A, "valid"),         # the explicit key matches
    (SEED_A, STORE, PUB_B, "other_key"),     # the explicit key wins over a store that does trust the signer
    (SEED_B, STORE, PUB_B, "valid"),         # ... and over a store that does not know the signer
    (SEED_B, {}, PUB_A, "other_key"),
])
def test_the_state_of_a_good_signature(signer, store, public, expected):
    assert rs.evidence_state(rs.sign_evidence(record(), signer), public, store) == expected


@pytest.mark.parametrize("store,public", [(STORE, None), ({}, None), (STORE, PUB_A), (None, PUB_B)])
def test_a_signature_that_fails_is_invalid_whatever_the_store_says(store, public):
    signed = rs.sign_evidence(record(), SEED_A)
    forged = {**signed, "detail": "changed"}
    forged["evidence_sha256"] = evidence.digest(forged)         # the digest is fixed, the signature cannot be
    assert rs.evidence_state(forged, public, store) == "invalid"
    cut = {**record("another"), "signature": signed["signature"]}        # a signature of another record
    assert rs.evidence_state(cut, public, store) == "invalid"


@pytest.mark.parametrize("store,public", [(STORE, None), ({}, None), (None, PUB_A)])
def test_an_unsigned_record_is_unsigned_whatever_the_store_says(store, public):
    assert rs.evidence_state(record(), public, store) == "unsigned"


def test_the_alias_is_the_first_in_order_when_two_aliases_name_one_key():
    signed = rs.sign_evidence(record(), SEED_A)
    assert rs.signer_alias(signed, {"Zed": PUB_A, "Abe": PUB_A, "Bea": PUB_B}) == "Abe"
    assert rs.signer_alias(signed, {"Bea": PUB_B}) == ""
    assert rs.signer_alias(signed, None) == ""
    assert rs.signer_alias(record(), STORE) == ""


# -- reading the store from a configuration ---------------------------------------------------------------------------------------------------------
def test_the_store_is_read_from_the_configuration():
    store, problems = rs.trust_store_from_config({"trusted_keys": {"Ana": PUB_A.hex(), "Bea.2": PUB_B.hex().upper()}})
    assert store == {"Ana": PUB_A, "Bea.2": PUB_B} and problems == []


@pytest.mark.parametrize("config", [{}, {"trusted_keys": None}, [], "x", None])
def test_no_store_is_an_empty_store_without_problems(config):
    assert rs.trust_store_from_config(config) == ({}, [])


def test_a_store_that_is_not_an_object_is_refused_as_a_whole():
    for bad in ([], "abc", 3, [PUB_A.hex()]):
        store, problems = rs.trust_store_from_config({"trusted_keys": bad})
        assert store == {} and len(problems) == 1


def test_an_entry_that_is_not_a_public_key_is_left_out_and_named_without_its_value():
    secret = "ab" * 31 + "zz"
    store, problems = rs.trust_store_from_config({"trusted_keys": {
        "Good": PUB_A.hex(), "Short": "ab" * 31, "Long": "ab" * 33, "Text": secret, "Number": 5, "None": None, "": PUB_B.hex(), "Bad/alias": PUB_B.hex(), "x" * 41: PUB_B.hex()}})
    assert list(store) == ["Good"]
    assert len(problems) == 8
    assert secret not in "\n".join(problems)
    assert all(PUB_B.hex() not in p for p in problems)


def test_a_key_left_out_is_not_trusted_the_safe_side():
    store, _ = rs.trust_store_from_config({"trusted_keys": {"Ana": "nope"}})
    assert rs.evidence_state(rs.sign_evidence(record(), SEED_A), None, store) == "valid"      # no store at all: not "trusted"


# -- the history ----------------------------------------------------------------------------------------------------------------------------------
def test_the_history_gives_the_alias_and_asks_the_slow_check_once(tmp_path, monkeypatch):
    entries = entries_of(tmp_path, rs.sign_evidence(record("a"), SEED_A), rs.sign_evidence(record("b"), SEED_B), record("c"))
    by = {e.record["detail"]: e for e in entries}
    calls = []
    original = rs.verify_evidence
    monkeypatch.setattr(rs, "verify_evidence", lambda *a, **k: calls.append(1) or original(*a, **k))
    assert evidence_history.signature_state(by["a"], None, STORE) == "trusted"
    assert evidence_history.signature_alias(by["a"], STORE) == "Ana (bench 1)"
    assert evidence_history.signature_state(by["a"], PUB_B, STORE) == "other_key"
    assert evidence_history.signature_state(by["a"]) == "valid"
    assert len(calls) == 1
    assert evidence_history.signature_state(by["b"], None, STORE) == "unknown_key"
    assert evidence_history.signature_alias(by["b"], STORE) == ""
    assert evidence_history.signature_state(by["c"], None, STORE) == "unsigned"


def test_a_record_that_fails_its_check_is_never_trusted(tmp_path):
    forged = {**rs.sign_evidence(record(), SEED_A), "outcome": "fail"}
    (entry,) = entries_of(tmp_path, forged)
    assert evidence_history.signature_state(entry, None, STORE) == "invalid"
    assert evidence_history.signature_alias(entry, STORE) == ""


def test_without_the_signing_module_nothing_is_trusted(tmp_path, monkeypatch):
    (entry,) = entries_of(tmp_path, rs.sign_evidence(record(), SEED_A))
    monkeypatch.setattr(evidence_history, "_record_signing", None)
    assert evidence_history.signature_state(entry, None, STORE) == "unchecked"
    assert evidence_history.signature_alias(entry, STORE) == ""


# -- the report -------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("language", evidence_report_strings.LANGUAGES)
def test_the_report_says_signed_by_the_alias_unknown_key_and_invalid_in_every_language(tmp_path, language):
    forged = {**rs.sign_evidence(record("forged"), SEED_A), "detail": "forged!"}
    forged["evidence_sha256"] = evidence.digest(forged)
    entries = entries_of(tmp_path, rs.sign_evidence(record("mine"), SEED_A), rs.sign_evidence(record("theirs"), SEED_B), forged)
    page = evidence_report.to_html(entries, language, None, STORE)
    st = evidence_report_strings.text
    assert html.escape(st(language, "ER_SIG_TRUSTED", alias="Ana (bench 1)"), quote=True) in page
    assert html.escape(st(language, "ER_SIG_UNKNOWN_KEY"), quote=True) in page
    assert html.escape(st(language, "ER_SIG_INVALID"), quote=True) in page
    assert "{alias}" not in page
    text = evidence_report.to_text(entries, language, None, STORE)
    assert st(language, "ER_SIG_TRUSTED", alias="Ana (bench 1)") in text and st(language, "ER_SIG_UNKNOWN_KEY") in text
    assert evidence_report.render(entries, "pdf", language, None, STORE).startswith(b"%PDF")


def test_the_report_summary_counts_the_new_states(tmp_path):
    entries = entries_of(tmp_path, rs.sign_evidence(record("a"), SEED_A), rs.sign_evidence(record("b"), SEED_B), record("c"))
    items = evidence_report._items(entries, "english", None, STORE)
    counts = evidence_report._summary(items, entries)["signatures"]
    assert counts["trusted"] == 1 and counts["unknown_key"] == 1 and counts["unsigned"] == 1 and counts["valid"] == 0


def test_an_explicit_key_wins_in_the_report(tmp_path):
    entries = entries_of(tmp_path, rs.sign_evidence(record(), SEED_A))
    page = evidence_report.to_html(entries, "english", PUB_B, STORE)
    assert evidence_report_strings.text("english", "ER_SIG_OTHER_KEY") in page
    assert "Ana (bench 1)" not in page


def test_markup_and_ampersands_are_not_aliases_so_nothing_can_reach_the_page(tmp_path):
    store, problems = rs.trust_store_from_config({"trusted_keys": {"A<b>": PUB_A.hex(), "Ok & Co": PUB_A.hex(), "x" + chr(10) + "y": PUB_A.hex(), "Ok@Co-1": PUB_A.hex()}})
    assert list(store) == ["Ok@Co-1"] and len(problems) == 3
    entries = entries_of(tmp_path, rs.sign_evidence(record(), SEED_A))
    assert "Signed by Ok@Co-1" in evidence_report.to_html(entries, "english", None, store)


def test_the_report_never_holds_a_seed_or_the_store_of_other_keys(tmp_path):
    entries = entries_of(tmp_path, rs.sign_evidence(record(), SEED_A))
    page = evidence_report.to_html(entries, "english", None, {"Ana": PUB_A, "Bea": PUB_B})
    assert SEED_A.hex() not in page and SEED_B.hex() not in page
    assert "Bea" not in page                                    # only the alias of the signer is named


def test_the_strings_of_the_new_states_exist_in_every_language():
    for language in evidence_report_strings.LANGUAGES:
        trusted = evidence_report_strings.STRINGS[language]["ER_SIG_TRUSTED"]
        assert "{alias}" in trusted
        assert evidence_report_strings.STRINGS[language]["ER_SIG_UNKNOWN_KEY"].strip()


# -- the window of the history ----------------------------------------------------------------------------------------------------------------------
def test_the_window_shows_a_column_with_the_state_of_the_signature(tmp_path):
    pytest.importorskip("PySide6", reason="PySide6 is not installed here")
    from urtc_common.evidence_history_qt import EvidenceHistoryModel

    forged = {**rs.sign_evidence(record("forged"), SEED_A), "detail": "x"}
    forged["evidence_sha256"] = evidence.digest(forged)
    entries_of(tmp_path, rs.sign_evidence(record("mine"), SEED_A), rs.sign_evidence(record("theirs"), SEED_B), forged, record("plain"))
    plain = EvidenceHistoryModel(lambda: tmp_path)
    assert len(plain.headers) == 8 and plain.headers[-1] == "Signature"
    assert sorted(r["signatureState"] for r in plain.rows) == ["invalid", "unsigned", "valid", "valid"]
    trusting = EvidenceHistoryModel(lambda: tmp_path, trusted=lambda: STORE)
    by_state = {r["signatureState"]: r["signatureText"] for r in trusting.rows}
    assert by_state["trusted"] == "Signed by Ana (bench 1)" and by_state["unknown_key"] == "Valid signature, unknown key"
    assert by_state["invalid"] == "SIGNATURE NOT VALID" and by_state["unsigned"] == "Not signed"
    pinned = EvidenceHistoryModel(lambda: tmp_path, trusted=lambda: STORE, public=lambda: PUB_B)
    assert sorted(r["signatureState"] for r in pinned.rows) == ["invalid", "other_key", "unsigned", "valid"]    # the key given wins over the store
    german = EvidenceHistoryModel(lambda: tmp_path, language=lambda: "german", trusted=lambda: STORE)
    assert german.headers[-1] == "Signatur" and any(r["signatureText"] == "Signiert von Ana (bench 1)" for r in german.rows)


# -- the switch of the programs that sign ---------------------------------------------------------------------------------------------------------
def test_the_signing_switch_is_on_only_when_it_is_exactly_true():
    assert rs.signing_settings({}) == (False, "")
    for value in ("true", "yes", 1, 0, None, [], {"on": True}, "false", False):
        assert rs.signing_settings({"sign_evidence": value})[0] is False
    assert rs.signing_settings({"sign_evidence": True}) == (True, "")
    assert rs.signing_settings({"sign_evidence": True, "record_key_file": "/k/x.key"}) == (True, "/k/x.key")
    assert rs.signing_settings({"record_key_file": 5, "sign_evidence": True}) == (True, "")
    for config in (None, [], "x"):
        assert rs.signing_settings(config) == (False, "")
