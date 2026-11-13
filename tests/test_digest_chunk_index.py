# =============================================================================
# URTC-COMMON - tests/test_digest_chunk_index.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The implicit index of the four digest chunks (0x212) of the slave relay: a counter that 0x211 zeroes and 0x214 checks."""
from __future__ import annotations

from pathlib import Path

from urtc_common import protocol

SPEC = Path(__file__).resolve().parents[1] / "spec" / "can_protocol.json"


def relay_verdict(events: list[str]) -> int | None:
    """Reference model of the rule the master bridge applies: the reason it reports at 0x214, or None when the end frame goes on."""
    count = 0
    verdict: int | None = None
    for event in events:
        if event == "start":
            count = 0
            verdict = None
        elif event == "chunk":
            count += 1
        elif event == "end" and 1 <= count < 4:
            verdict = protocol.SLAVE_VERIFY_FAIL_REASON_DIGEST_CHUNK_MISSING
    return verdict


def test_the_reason_is_in_the_enum_with_a_name_and_a_title() -> None:
    assert protocol.SLAVE_VERIFY_FAIL_REASON_DIGEST_CHUNK_MISSING == 0x07
    assert protocol.ENUM_NAMES["slave_verify_fail_reason"][7] == "DIGEST_CHUNK_MISSING"
    assert "digest chunks" in protocol.ENUM_TITLES["slave_verify_fail_reason"][7]


def test_the_reason_does_not_collide_with_the_other_verify_fail_reasons() -> None:
    assert 7 not in protocol.ENUM_NAMES["verify_fail_reason"]
    assert 7 != protocol.SLAVE_VERIFY_FAIL_REASON_NOT_CONFIRMED


def test_four_chunks_pass() -> None:
    assert relay_verdict(["start", "chunk", "chunk", "chunk", "chunk", "end"]) is None


def test_every_lost_chunk_is_named() -> None:
    for kept in (1, 2, 3):
        events = ["start"] + ["chunk"] * kept + ["end"]
        assert relay_verdict(events) == 7


def test_a_sender_without_digest_behaves_as_before() -> None:
    assert relay_verdict(["start", "end"]) is None


def test_a_new_start_forgets_the_chunks_of_an_aborted_attempt() -> None:
    assert relay_verdict(["start", "chunk", "chunk", "start", "chunk", "chunk", "chunk", "chunk", "end"]) is None
    assert relay_verdict(["start", "chunk", "chunk", "chunk", "start", "chunk", "end"]) == 7


def test_the_specification_says_so() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert "The frames carry no index" in text
    assert "DIGEST_CHUNK_MISSING" in text
