# =============================================================================
# URTC-COMMON - tests/test_parser_properties.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Properties of the parsers that read what other people write (an evidence file, a trust store, a bus scenario, a line of the adapter): whatever they are given
they answer with their own refusal, never with an exception of their own making, never accept what they should refuse, and what they accept round-trips.

The inputs are made from fixed seeds (the same run every time) by mutating valid ones and by pure noise; there is no network, no clock and no file outside the
temporary folder of the test."""
from __future__ import annotations

import copy
import json
import random
import string
from typing import Any

import pytest

from urtc_common import bus_scenario, evidence, evidence_history, slcan
from urtc_common import record_signing as rs

SEEDS = range(40)
SEED_KEY = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")


def good_record(detail: str = "ok") -> dict:
    return evidence.build(kind="test", outcome="pass", timestamp_utc="2026-01-02T03:04:05Z", tool="URTC Tester", tool_version="1.2.3", operator="op",
                          subject={"name": "board", "version_after": "1.0.0"}, transport={"adapter": "simulate", "bus": "can", "bitrate": 500000},
                          artifacts=[{"name": "f.bin", "sha256": "a" * 64, "bytes": 3}], detail=detail)


def junk(rng: random.Random, depth: int = 0) -> Any:
    """Any JSON-like value, including the ones that are hard on a parser: huge numbers, nested lists, odd texts, booleans in the place of numbers."""
    kind = rng.randrange(9 if depth < 3 else 6)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice([True, False])
    if kind == 2:
        return rng.choice([0, -1, 1, 2**63, -(2**70), 10**30])
    if kind == 3:
        return rng.choice([0.0, -0.0, 1.5, 1e308, float("inf"), float("nan")])
    if kind == 4:
        return "".join(rng.choice(string.printable + "é‮\u0000日本") for _ in range(rng.randrange(0, 30)))
    if kind == 5:
        return rng.choice(["", " ", "0x1F", "ab" * 32, "../../etc/passwd", "<script>", "\n"])
    if kind == 6:
        return [junk(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    return {rng.choice(["a", "kind", "outcome", "signature", "format", "keys", "subject"]): junk(rng, depth + 1) for _ in range(rng.randrange(0, 4))}


def mutate(rng: random.Random, value: Any) -> Any:
    """A copy of a valid document with one place changed to something else."""
    doc = copy.deepcopy(value)
    paths: list[list[Any]] = []

    def walk(node: Any, path: list[Any]) -> None:
        paths.append(path)
        if isinstance(node, dict):
            for key, item in node.items():
                walk(item, path + [key])
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, path + [index])

    walk(doc, [])
    path = rng.choice(paths)
    if not path:
        return junk(rng)
    parent = doc
    for step in path[:-1]:
        parent = parent[step]
    if rng.random() < 0.2 and isinstance(parent, dict):
        del parent[path[-1]]
    else:
        parent[path[-1]] = junk(rng)
    return doc


# -- the evidence record ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_verify_never_raises_and_a_changed_record_is_never_valid_with_the_old_digest(seed):
    rng = random.Random(seed)
    base = good_record()
    changed = mutate(rng, base)
    problems = evidence.verify(changed)                          # must answer with a list, whatever the input
    assert isinstance(problems, list)
    if changed != base:
        assert problems, "a changed record kept a valid shape and digest"


@pytest.mark.parametrize("seed", SEEDS)
def test_verify_answers_pure_noise_with_problems(seed):
    rng = random.Random(1000 + seed)
    value = junk(rng)
    assert evidence.verify(value) and isinstance(evidence.verify(value), list)


def test_the_digest_does_not_depend_on_the_order_of_the_keys_and_ignores_the_signature():
    record = good_record()
    shuffled = dict(reversed(list(record.items())))
    assert evidence.digest(shuffled) == evidence.digest(record)
    assert evidence.digest(rs.sign_evidence(record, SEED_KEY)) == evidence.digest(record)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_signed_record_verifies_and_any_change_breaks_the_signature(seed):
    rng = random.Random(2000 + seed)
    signed = rs.sign_evidence(good_record(detail=f"d{seed}"), SEED_KEY)
    assert rs.verify_evidence(signed) and rs.evidence_state(signed) == "valid"
    changed = mutate(rng, signed)
    if changed != signed:
        assert rs.evidence_state(changed) in ("invalid", "unsigned")           # never "valid", never an exception
        assert not rs.verify_evidence(changed) if isinstance(changed, dict) else True


@pytest.mark.parametrize("seed", SEEDS)
def test_the_signature_check_never_raises_on_noise_and_never_accepts_it(seed):
    rng = random.Random(3000 + seed)
    record = good_record()
    record["signature"] = junk(rng)
    assert rs.evidence_state(record) in ("invalid", "unsigned")
    assert rs.verify_evidence(record) is False
    block = {"algorithm": "Ed25519", "key_id": "".join(rng.choice("0123456789abcdef") for _ in range(16)),
             "public_key": "".join(rng.choice("0123456789abcdef") for _ in range(64)), "signature": "".join(rng.choice("0123456789abcdef") for _ in range(128))}
    assert rs.check_signature(block, rs.KIND_EVIDENCE, record["evidence_sha256"]) is False


# -- reading evidence from files --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(15))
def test_a_file_of_garbage_lines_is_listed_never_raised_and_never_called_valid(tmp_path, seed):
    rng = random.Random(4000 + seed)
    lines = []
    for _ in range(rng.randrange(1, 12)):
        pick = rng.randrange(4)
        lines.append(json.dumps(junk(rng), allow_nan=True) if pick == 0 else json.dumps(mutate(rng, good_record())) if pick == 1
                     else "".join(rng.choice(string.printable) for _ in range(rng.randrange(0, 60))) if pick == 2 else "{" * rng.randrange(1, 50))
    path = tmp_path / "x.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    entries = evidence_history.load_file(path)
    for entry in entries:
        assert isinstance(entry.problems, list)
        assert entry.valid == (not entry.problems)
        if entry.valid and not entry.other:
            assert evidence.verify(entry.record) == []                     # what is listed as valid really is
    summary = evidence_history.summary(entries)
    assert summary["records"] == summary["valid"] + summary["invalid"]


def test_an_enormous_nesting_and_a_huge_line_are_refused_not_followed(tmp_path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 100_000, encoding="utf-8")
    (entry,) = evidence_history.load_file(path)
    assert not entry.valid
    big = tmp_path / "big.json"
    big.write_text(json.dumps({"x": "y" * 9_000_000}), encoding="utf-8")
    (entry,) = evidence_history.load_file(big)
    assert not entry.valid and "bigger" in entry.problems[0]


# -- the trust store --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_the_trust_store_keeps_only_aliases_and_public_keys_and_never_raises(seed):
    rng = random.Random(5000 + seed)
    config = {"trusted_keys": {str(junk(rng))[:50]: junk(rng) for _ in range(rng.randrange(0, 8))} if rng.random() < 0.8 else junk(rng)}
    store, problems = rs.trust_store_from_config(config)
    assert isinstance(problems, list)
    for alias, key in store.items():
        assert rs._ALIAS.match(alias) and isinstance(key, bytes) and len(key) == 32


@pytest.mark.parametrize("seed", SEEDS)
def test_a_good_store_round_trips_whatever_the_case_and_the_junk_around_it(seed):
    rng = random.Random(6000 + seed)
    keys = {f"K{i}": rs.public_key(bytes([rng.randrange(256) for _ in range(32)])) for i in range(rng.randrange(1, 6))}
    config = {"trusted_keys": {a: (k.hex().upper() if rng.random() < 0.5 else k.hex()) for a, k in keys.items()}, "other": junk(rng)}
    store, problems = rs.trust_store_from_config(config)
    assert store == keys and problems == []


# -- the bus scenario ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_a_scenario_is_accepted_or_refused_with_its_own_error(seed):
    rng = random.Random(7000 + seed)
    base = {"format": bus_scenario.FORMAT, "name": "s", "seed": 3, "faults": [{"kind": "drop", "probability": 0.5}]}
    doc = mutate(rng, base) if seed % 3 else junk(rng)
    try:
        scenario = bus_scenario.parse(json.dumps(doc, allow_nan=True))
    except bus_scenario.ScenarioError:
        return
    assert isinstance(scenario, bus_scenario.Scenario)
    assert bus_scenario.validate(json.loads(json.dumps(doc, allow_nan=True))) == []          # accepted means the validator found nothing


@pytest.mark.parametrize("text", ["", "{", "[]", "null", "nan", '{"a":NaN}', '{"a":1,"a":2}', "\x00", '{"format": 5}', "[" * 5000, '"' * 3])
def test_hostile_scenario_texts_are_refused_with_the_scenario_error(text):
    with pytest.raises(bus_scenario.ScenarioError):
        bus_scenario.parse(text)


# -- one line of the adapter ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_a_line_of_noise_is_a_frame_or_nothing_never_an_exception(seed):
    rng = random.Random(8000 + seed)
    alphabet = "tT0123456789abcdefABCDEFrR\r\n\x07 xz"
    for _ in range(50):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 30)))
        frame = slcan.decode_line(line)
        assert frame is None or (0 <= frame.id <= 0x7FF and len(frame.data) <= 8)


@pytest.mark.parametrize("seed", SEEDS)
def test_what_is_encoded_decodes_to_the_same_frame(seed):
    rng = random.Random(9000 + seed)
    can_id = rng.randrange(0, 0x800)
    data = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 9)))
    frame = slcan.decode_line(slcan.encode_line(can_id, data))
    assert frame is not None and frame.id == can_id and frame.data == data


def test_a_reader_given_noise_in_odd_pieces_never_raises_never_grows_without_bound_and_yields_only_valid_frames():
    reader = slcan.LineReader()
    rng = random.Random(1)
    for _ in range(300):
        chunk = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 60)))
        for frame in reader.frames(chunk):
            assert 0 <= frame.id <= 0x7FF and len(frame.data) <= 8
        assert len(reader.buffer) <= max(reader.limit, 60 + reader.limit)
