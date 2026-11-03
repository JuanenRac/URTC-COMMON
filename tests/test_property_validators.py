# =============================================================================
# URTC-COMMON - tests/test_property_validators.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. Property-based tests of the security validators: the key rotation, the image authentication and the parsers.

The cases come from a small generator with a FIXED seed (``random.Random``), so a run is the same on every machine and no test dependency is needed. The
number of cases per property is bounded (``CASES``) to keep the whole file under a few seconds.
"""
from __future__ import annotations

import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import ed25519, frame_layer as fl, image_auth as ia, image_header as ih, key_rotation as kr  # noqa: E402

CASES = 300
SEED = 7001


def rng(name: str) -> random.Random:
    return random.Random(f"{SEED}:{name}")


def kid(r: random.Random) -> bytes:
    return bytes(r.randrange(256) for _ in range(8))


# --- key rotation -------------------------------------------------------------------------------------------------------------------------------
def random_rotation(r: random.Random) -> tuple[kr.Rotation, int]:
    cur, prev, other = kid(r), kid(r), kid(r)
    revoked = frozenset(k for k in (cur, prev, other) if r.random() < 0.2)
    window = r.choice([0, 1, 2, 60, r.randrange(0, 100000)])
    started = r.randrange(0, 1000000)
    now = started + r.choice([-5, -1, 0, 1, window - 1, window, window + 1, r.randrange(-100, 200000)])
    return kr.Rotation(cur, r.choice([None, prev, prev, cur]), window, started, revoked), max(now, 0)


def test_unknown_fingerprint_is_never_accepted():
    r = rng("unknown")
    for _ in range(CASES):
        rot, now = random_rotation(r)
        stranger = kid(r)
        if stranger in (rot.current, rot.previous):
            continue
        assert not kr.is_accepted(rot, now, stranger)
        assert kr.host_check(kr.announce(rot, now)[0], stranger) in ("no_data", "differs")


def test_accepted_is_exactly_the_announced_set_and_bounded():
    r = rng("announced")
    for _ in range(CASES):
        rot, now = random_rotation(r)
        ids = kr.active_key_ids(rot, now)
        assert len(ids) <= kr.MAX_ANNOUNCED and len(set(ids)) == len(ids)
        assert all(i not in rot.revoked for i in ids)
        assert set(ids) <= {rot.current, rot.previous}
        for k in (rot.current, rot.previous):
            if k is not None:
                assert kr.is_accepted(rot, now, k) == (k in ids)
        frames, status = kr.announce(rot, now)
        assert frames == ids and len(status) == 7
        parsed = kr.parse_status(status)
        assert parsed is not None and parsed["count"] == len(ids)


def test_previous_key_expires_exactly_at_the_end_of_the_window():
    r = rng("expiry")
    for _ in range(CASES):
        cur, prev = kid(r), kid(r)
        if cur == prev:
            continue
        window, started = r.randrange(1, 100000), r.randrange(0, 1000000)
        rot = kr.Rotation(cur, prev, window, started)
        assert kr.is_accepted(rot, started, prev)
        assert kr.is_accepted(rot, started + window - 1, prev)
        assert not kr.is_accepted(rot, started + window, prev)
        assert not kr.is_accepted(rot, started + window + r.randrange(0, 100000), prev)
        assert kr.is_accepted(rot, started + window + 5, cur)
        assert kr.seconds_left(rot, started + window - 1) == 1
        assert kr.seconds_left(rot, started) == window


def test_window_zero_or_negative_and_clock_before_start_refuse_the_previous_key():
    r = rng("zero")
    for _ in range(CASES):
        cur, prev = kid(r), kid(r)
        if cur == prev:
            continue
        started = r.randrange(1, 1000000)
        now = r.randrange(0, 2000000)
        assert not kr.is_accepted(kr.Rotation(cur, prev, 0, started), now, prev)
        assert not kr.is_accepted(kr.Rotation(cur, prev, -r.randrange(1, 100), started), now, prev)
        assert not kr.is_accepted(kr.Rotation(cur, prev, 100, started), started - r.randrange(1, started + 1), prev)
        assert kr.seconds_left(kr.Rotation(cur, prev, 0, started), now) == kr.NO_WINDOW


def test_revoked_current_leaves_nothing_trusted_and_revoked_previous_never_passes():
    r = rng("revoked")
    for _ in range(CASES):
        cur, prev = kid(r), kid(r)
        if cur == prev:
            continue
        rot = kr.Rotation(cur, prev, 1000, 0, frozenset({cur}))
        assert kr.active_key_ids(rot, r.randrange(0, 2000)) == []
        rot = kr.Rotation(cur, prev, 1000, 0, frozenset({prev}))
        assert not kr.is_accepted(rot, r.randrange(0, 2000), prev)


def test_status_parser_rejects_everything_that_is_not_a_status():
    r = rng("status")
    for _ in range(CASES * 3):
        n = r.choice([0, 1, 6, 7, 7, 7, 8, 9, 16])
        payload = bytes(r.randrange(256) for _ in range(n))
        parsed = kr.parse_status(payload)
        valid = n == 7 and payload[0] == kr.STATUS_OP and payload[1] <= kr.MAX_ANNOUNCED and not payload[2] & ~3
        assert (parsed is not None) == valid
    for flags in range(256):   # every flag bit outside the two known ones is refused
        assert (kr.parse_status(bytes([5, 1, flags, 0, 0, 0, 0])) is not None) == (flags & ~3 == 0)


def test_wrong_length_fingerprints_are_refused_and_never_matched():
    r = rng("lengths")
    rot = kr.Rotation(b"N" * 8, b"O" * 8, 60, 0)
    for _ in range(CASES):
        n = r.choice([n for n in range(0, 20) if n != 8])
        k = bytes(r.randrange(256) for _ in range(n))
        assert not kr.is_accepted(rot, 1, k)
        assert kr.host_check([k], b"N" * 8) == "no_data"


# --- image authentication -----------------------------------------------------------------------------------------------------------------------
SEED_A, SEED_B = bytes(range(32)), bytes(range(32, 64))
PUB_A, PUB_B = ed25519.public_key(SEED_A), ed25519.public_key(SEED_B)
HARDWARE = 0x1234
PAYLOAD = b"firmware payload"


def header(version=(0, 1, 2, 3), hardware=HARDWARE) -> bytes:
    return ih.make_header(PAYLOAD, hardware, version, signed=True)[: ia.HEADER_BYTES]


SHA = ia.hashlib.sha256(PAYLOAD).digest()
H28 = header()
GOOD = ia.make_record(SEED_A, H28, SHA, 7)


def test_ed25519_only_never_accepts_anything_but_a_valid_trusted_signature():
    r = rng("policy")
    # a valid record is the only way to get OK, whatever the HMAC says
    for hmac_ok in (False, True):
        assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, None, False, H28, SHA, GOOD, hmac_ok) == (ia.OK, 7)
    for _ in range(CASES):
        hmac_ok = r.random() < 0.5
        keys = r.choice([[], [PUB_B], [PUB_A, PUB_B], [PUB_B, PUB_A]])
        choice = r.randrange(5)
        if choice == 0:
            record = None
        elif choice == 1:
            record = bytes(r.randrange(256) for _ in range(ia.RECORD_SIZE))
        elif choice == 2:   # one flipped bit in the good record
            b = bytearray(GOOD)
            b[r.randrange(ia.RECORD_SIZE)] ^= 1 << r.randrange(8)
            record = bytes(b)
        elif choice == 3:   # signature of a stranger
            record = ia.make_record(SEED_B, H28, SHA, 7)
        else:
            record = GOOD
        status, _ = ia.decide(ia.POLICY_ED25519_ONLY, keys, HARDWARE, 0, None, False, H28, SHA, record, hmac_ok)
        legit = record == GOOD and PUB_A in keys
        legit = legit or (record == ia.make_record(SEED_B, H28, SHA, 7) and PUB_B in keys)
        assert (status == ia.OK) == legit
        # the HMAC result never changes the outcome under ed25519_only
        assert status == ia.decide(ia.POLICY_ED25519_ONLY, keys, HARDWARE, 0, None, False, H28, SHA, record, not hmac_ok)[0]


def test_a_signature_does_not_transfer_to_another_image_counter_or_hardware():
    r = rng("transfer")
    for _ in range(60):
        other_sha = bytes(r.randrange(256) for _ in range(32))
        assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, None, False, H28, other_sha, GOOD, True)[0] == ia.BAD_SIGNATURE
        other_header = bytearray(H28)
        i = r.choice([i for i in range(ia.HEADER_BYTES) if not 8 <= i < 12])   # not the hardware id: that is a different status
        other_header[i] ^= 1 << r.randrange(8)
        assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, None, False, bytes(other_header), SHA, GOOD, True)[0] == ia.BAD_SIGNATURE
        hw = r.randrange(0, 1 << 32)
        if hw != HARDWARE:
            h = bytearray(H28)
            h[8:12] = struct.pack(">I", hw)
            assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, None, False, bytes(h), SHA, GOOD, True)[0] == ia.HARDWARE_MISMATCH
        # a record with a changed counter field no longer verifies (the counter is signed)
        forged = GOOD[:8] + struct.pack(">I", r.randrange(0, 1 << 32)) + GOOD[12:]
        if forged != GOOD:
            assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, None, False, H28, SHA, forged, True)[0] != ia.OK


def test_rollback_rules_hold_for_any_counter_and_version():
    r = rng("rollback")
    for _ in range(CASES):
        floor = r.randrange(0, 20)
        status, new = ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, floor, None, False, H28, SHA, GOOD, False)
        if 7 < floor:
            assert status == ia.ROLLBACK_COUNTER and new == floor
        else:
            assert status == ia.OK and new == 7
        installed = tuple(r.randrange(0, 3) for _ in range(4))
        allowed = r.random() < 0.5
        status, _ = ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, installed, allowed, H28, SHA, GOOD, False)
        older = (0, 1, 2, 3) < installed
        assert (status == ia.ROLLBACK_VERSION) == (older and not allowed)


def test_bad_arguments_and_unknown_policies_are_refused():
    r = rng("args")
    for _ in range(CASES):
        policy = r.randrange(-3, 6)
        h = bytes(r.randrange(256) for _ in range(r.choice([0, 27, 28, 28, 29])))
        s = bytes(r.randrange(256) for _ in range(r.choice([0, 31, 32, 32, 33])))
        rec = r.choice([None, bytes(r.randrange(256) for _ in range(r.choice([0, 75, 76, 77])))])
        status, counter = ia.decide(policy, [PUB_A], HARDWARE, 5, None, False, h, s, rec, True)
        malformed = len(h) != 28 or len(s) != 32 or policy not in (0, 1, 2) or (rec is not None and len(rec) != 76)
        if malformed:
            assert (status, counter) == (ia.BAD_ARGS, 5)
        if policy == ia.POLICY_ED25519_ONLY and status == ia.OK:
            raise AssertionError("ed25519_only accepted a random record")


def test_default_policy_is_ed25519_only():
    assert ia.POLICY_DEFAULT == ia.POLICY_ED25519_ONLY == 0 and ia.POLICY_NAMES[ia.POLICY_DEFAULT] == "ed25519_only"


def test_message_and_key_id_lengths():
    r = rng("message")
    for _ in range(CASES):
        a, b, c = (r.choice([7, 8, 9, 27, 28, 29, 31, 32, 33]) for _ in range(3))
        ok = a == 28 and b == 32 and c == 8
        try:
            m = ia.message(bytes(a), bytes(b), 1, bytes(c))
            assert ok and len(m) == ia.MESSAGE_SIZE
        except ValueError:
            assert not ok


# --- image header and frame parsers -------------------------------------------------------------------------------------------------------------
def test_image_header_parser_never_raises_and_only_accepts_what_it_built():
    r = rng("header")
    good = ih.make_header(PAYLOAD, HARDWARE, (1, 2, 3, 4))
    assert ih.parse_header(good)[0] == ih.OK
    for _ in range(CASES * 2):
        b = bytearray(good)
        for _ in range(r.randrange(1, 4)):
            b[r.randrange(len(b))] ^= 1 << r.randrange(8)
        data = bytes(b)[: r.choice([r.randrange(0, 40), 32, 32, 40])]
        status, info = ih.parse_header(data)
        assert (info is not None) == (status == ih.OK)
        if status == ih.OK:
            assert len(data) >= ih.HEADER_SIZE and data[: ih.HEADER_SIZE] == ih.pack_header(info)   # a change inside the header never goes unseen
    for n in range(ih.HEADER_SIZE):
        assert ih.parse_header(good[:n]) == (ih.SHORT, None)
    for _ in range(CASES):
        data = bytes(r.randrange(256) for _ in range(r.randrange(0, 80)))
        assert ih.verify_image(data)[0] != ih.OK


def test_image_length_and_crc_are_enforced_for_any_payload():
    r = rng("image")
    for _ in range(CASES):
        payload = bytes(r.randrange(256) for _ in range(r.randrange(0, 50)))
        image = ih.build_image(payload, HARDWARE, (0, 1, 0, 0))
        assert ih.verify_image(image)[0] == ih.OK
        assert ih.verify_image(image + b"\x00")[0] == ih.BAD_LENGTH
        if payload:
            assert ih.verify_image(image[:-1])[0] == ih.BAD_LENGTH
            b = bytearray(image)
            b[ih.HEADER_SIZE + r.randrange(len(payload))] ^= 1 << r.randrange(8)
            assert ih.verify_image(bytes(b))[0] == ih.BAD_PAYLOAD_CRC


def test_frame_parser_length_and_range_limits():
    r = rng("frames")
    for fmt in (fl.RACK, fl.SENSOR):
        for _ in range(CASES):
            n = r.randrange(0, fmt.max_payload + 6)
            body = bytearray(r.randrange(256) for _ in range(fmt.header_size + min(n, 40)))
            body[0], body[1], body[fmt.length_index] = fmt.sof, fmt.version, n
            frame = fl.seal(fmt, bytes(body))
            status, total = fl.validate(fmt, frame)
            if n > fmt.max_payload:
                assert (status, total) == ("length_out_of_range", 0)
            elif len(body) == fmt.header_size + n:
                assert (status, total) == ("ok", len(frame))
                assert fl.validate(fmt, frame + b"\xff")[1] == len(frame)
                assert fl.validate(fmt, frame[:-1])[0] in ("incomplete",)
                b = bytearray(frame)
                b[r.randrange(len(b))] ^= 1 << r.randrange(8)
                assert fl.validate(fmt, bytes(b))[0] != "ok"
        for _ in range(CASES):   # arbitrary bytes: a documented status, a zero length unless ok, never an exception
            data = bytes(r.randrange(256) for _ in range(r.randrange(0, 40)))
            status, total = fl.validate(fmt, data)
            assert status in ("ok", "incomplete", "bad_sof", "unsupported_version", "length_out_of_range", "crc_mismatch")
            assert (total > 0) == (status == "ok")


# --- cases added after a mutation run (a mutant that survived is a behaviour nothing checked) ---------------------------------------------------
def test_status_fields_follow_their_flag_bits():
    r = rng("status-fields")
    for flags in range(4):
        for count in range(3):
            secs = r.randrange(0, 1 << 32)
            parsed = kr.parse_status(struct.pack(">BBBI", kr.STATUS_OP, count, flags, secs))
            assert parsed == {"count": count, "rotating": bool(flags & 1), "current_revoked": bool(flags & 2), "seconds_left": secs}
    # the byte after the flags is not a flag: a set bit there changes nothing
    assert kr.parse_status(bytes([5, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF]))["rotating"] is False
    assert kr.parse_status(bytes([5, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF]))["current_revoked"] is False


def test_seconds_left_is_clamped_below_the_no_window_marker():
    cur, prev = b"C" * 8, b"P" * 8
    rot = kr.Rotation(cur, prev, 1 << 33, 0)
    assert kr.seconds_left(rot, 0) == kr.NO_WINDOW - 1
    assert kr.seconds_left(rot, (1 << 33) - 5) == 5


def test_rotation_defaults_are_fail_closed_and_the_record_is_immutable():
    rot = kr.Rotation(b"C" * 8)
    assert (rot.previous, rot.window_s, rot.started_at, rot.revoked) == (None, 0, 0, frozenset())
    assert kr.active_key_ids(rot, 10**9) == [b"C" * 8]
    try:
        rot.window_s = 5  # type: ignore[misc]
    except Exception as error:
        assert type(error).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("a Rotation must not be changed after it is made")
    try:
        kr.active_key_ids(kr.Rotation(b"short"), 0)
    except ValueError as error:
        assert str(error) == "a key fingerprint is 8 bytes"


def test_hmac_only_never_moves_the_counter_and_never_looks_at_the_record():
    r = rng("hmac-only")
    for _ in range(CASES):
        floor = r.randrange(0, 20)
        record = r.choice([None, GOOD, bytes(r.randrange(256) for _ in range(ia.RECORD_SIZE))])
        status, counter = ia.decide(ia.POLICY_HMAC_ONLY, [PUB_A], HARDWARE, floor, None, False, H28, SHA, record, True)
        assert (status, counter) == (ia.OK, floor)           # a record with a lower counter is not a rollback of a path that does not use it
        assert ia.decide(ia.POLICY_HMAC_ONLY, [PUB_A], HARDWARE, floor, None, False, H28, SHA, record, False) == (ia.BAD_HMAC, floor)


def test_the_same_version_may_be_installed_again_and_an_older_one_may_not():
    installed = (0, 1, 2, 3)
    assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, installed, False, H28, SHA, GOOD, False)[0] == ia.OK
    assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, (0, 1, 2, 4), False, H28, SHA, GOOD, False)[0] == ia.ROLLBACK_VERSION
    assert ia.decide(ia.POLICY_ED25519_ONLY, [PUB_A], HARDWARE, 0, (0, 1, 2, 4), True, H28, SHA, GOOD, False)[0] == ia.OK


def test_a_wrong_length_in_the_signed_record_says_so():
    try:
        ia.message(b"x", SHA, 1, b"k" * 8)
    except ValueError as error:
        assert str(error) == "wrong length in the signed record"
    else:
        raise AssertionError("a short header must be refused")
