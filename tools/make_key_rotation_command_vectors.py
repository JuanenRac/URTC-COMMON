#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_key_rotation_command_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Writes conformance/key_rotation_command_vectors.json and generated/key_rotation_command_vectors.h: signed rotation commands and what a bootloader decides.

The records are made with the Python reference and throwaway seeds (the first 32 bytes of the SHA-256 of a label); the EXPECTED reasons and states are
written by hand here, never computed by the code under test. Ed25519 is deterministic, so the output is stable. ``--check`` writes nothing and fails when
a file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import ed25519, image_auth as ia, key_rotation_command as krc  # noqa: E402


def seed(label: str) -> bytes:
    return hashlib.sha256(b"rotation-command-test-seed:" + label.encode()).digest()


SEEDS = {name: seed(name) for name in ("A", "B", "C")}
PUB = {name: ed25519.public_key(s) for name, s in SEEDS.items()}
KID = {name: ia.key_id(p) for name, p in PUB.items()}
T0 = 1_700_000_000


def flip(record: bytes, at: int) -> bytes:
    return record[:at] + bytes([record[at] ^ 0x01]) + record[at + 1:]


def case(name, record, reason, *, current="A", previous=None, revoked=(), trust=("A", "B"), allow=True, last_counter=0, last_time=0, max_window=krc.DEFAULT_MAX_WINDOW_S,
         uptime=500, expect=None):
    return {"name": name, "record": record.hex(), "reason": reason, "current": KID[current].hex(), "previous": KID[previous].hex() if previous else None,
            "revoked": [KID[r].hex() for r in revoked], "trust": [{"id": KID[t].hex(), "public": PUB[t].hex()} for t in trust], "allow": allow,
            "last_counter": last_counter, "last_time": last_time, "max_window_s": max_window, "uptime": uptime, "expect": expect}


def good(signer="A", new="B", previous="A", window=3600, host_time=T0, counter=1):
    return krc.sign(SEEDS[signer], KID[new], KID[previous] if previous else None, window, host_time, counter)


def accepted(current, previous, window, started_at=T0, counter=1, uptime=500):
    return {"current": KID[current].hex(), "previous": KID[previous].hex() if previous else None, "window_s": window, "started_at": started_at,
            "last_counter": counter, "last_time": started_at, "clock_offset": started_at - uptime}


def cases() -> list[dict]:
    rec = good()
    return [
        case("accepted: the current key hands over to the next with an hour of overlap", rec, "ok", expect=accepted("B", "A", 3600)),
        case("accepted: no overlap when the previous key is left out", good(previous=None), "ok", expect=accepted("B", None, 0)),
        case("accepted: a window of zero keeps only the new key", good(window=0), "ok", expect=accepted("B", "A", 0)),
        case("accepted: the highest counter", good(counter=0xFFFFFFFF), "ok", expect=accepted("B", "A", 3600, counter=0xFFFFFFFF)),
        case("accepted: the clock offset follows the uptime", good(host_time=T0 + 77), "ok", uptime=1234, expect=accepted("B", "A", 3600, T0 + 77, 1, 1234)),
        case("refused: the option is off by default", rec, "disabled", allow=False),
        case("refused: a record of 99 bytes", rec[:99], "malformed"),
        case("refused: a record of 101 bytes", rec + b"\x00", "malformed"),
        case("refused: a signer that is not in the trust table", good(signer="C"), "unknown_signer"),
        case("refused: signed by the previous key during a window", good(signer="A", new="A", previous=None), "signer_not_current", current="B", previous="A"),
        case("refused: the current key is revoked", rec, "signer_not_current", revoked=("A",)),
        case("refused: a changed window breaks the signature", flip(rec, 27), "bad_signature"),
        case("refused: a changed host time breaks the signature", flip(rec, 31), "bad_signature"),
        case("refused: a changed signature", flip(rec, 90), "bad_signature"),
        case("refused: a signature made without the domain of rotation", rec[:36] + ed25519.sign(SEEDS["A"], rec[:36]), "bad_signature"),
        case("refused: a replayed counter", rec, "replayed_counter", last_counter=1),
        case("refused: a counter below the last one", rec, "replayed_counter", last_counter=9),
        case("refused: the host time goes back", rec, "time_backwards", last_time=T0 + 1),
        case("refused: the host time is zero", good(host_time=0), "time_backwards"),
        case("refused: a new key that is not in the table", good(new="C"), "unknown_new_key"),
        case("refused: a revoked new key", rec, "revoked_new_key", revoked=("B",)),
        case("refused: the previous key is not the one trusted now", good(previous="B"), "bad_previous"),
        case("refused: the new key is also the previous one", good(new="A", previous="A"), "bad_previous", trust=("A", "B")),
        case("refused: a window above the maximum", good(window=86401), "window_too_long", max_window=86400),
        case("accepted: a window equal to the maximum", good(window=86400), "ok", max_window=86400, expect=accepted("B", "A", 86400)),
    ]


def about() -> str:
    return ("Signed rotation command (100 bytes: signer, new current, previous, window, host time, counter, signature) and the reason a bootloader gives. "
            "Fingerprints are the first 8 bytes of the SHA-512 of a throwaway public key. 'expect' is the state after an accepted command (clock_offset = host time - uptime). "
            "'reason' is one of: " + ", ".join(krc.REASONS) + ".")


def arr(data: bytes) -> str:
    return "{" + ", ".join(f"0x{b:02X}" for b in data) + "}" if data else "{0}"


def c_header(cases_: list[dict]) -> str:
    lines = ["// GENERATED by tools/make_key_rotation_command_vectors.py - do not edit by hand.", "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
             "// GPL-3.0-or-later - see LICENSE", "#ifndef KEY_ROTATION_COMMAND_VECTORS_H", "#define KEY_ROTATION_COMMAND_VECTORS_H", "", "#include <stddef.h>",
             "#include <stdint.h>", "", "typedef struct {", "    const char *name;", "    const uint8_t *record;", "    size_t record_length;", "    int reason;",
             "    uint8_t current[8], previous[8];", "    int has_previous;", "    const uint8_t (*revoked)[8];", "    size_t revoked_count;",
             "    uint8_t trust_id[2][8], trust_public[2][32];", "    size_t trust_count;", "    int allow;", "    uint32_t last_counter, last_time, max_window_s, uptime;",
             "    int expect_ok;", "    uint8_t expect_current[8], expect_previous[8];", "    int expect_has_previous;",
             "    uint32_t expect_window_s, expect_started_at, expect_counter, expect_offset;", "} key_rotation_command_vec_t;", ""]
    for i, c in enumerate(cases_):
        rows = [bytes.fromhex(r) for r in c["revoked"]]
        lines.append(f"static const uint8_t krc_record_{i}[] = {arr(bytes.fromhex(c['record']))};")
        lines.append(f"static const uint8_t krc_revoked_{i}[][8] = {{{', '.join(arr(r) for r in rows) if rows else '{0}'}}};")
    lines += ["", "static const key_rotation_command_vec_t KEY_ROTATION_COMMAND_VECTORS[] = {"]
    for i, c in enumerate(cases_):
        e = c["expect"]
        tid = [bytes.fromhex(t["id"]) for t in c["trust"]] + [bytes(8)] * (2 - len(c["trust"]))
        tpub = [bytes.fromhex(t["public"]) for t in c["trust"]] + [bytes(32)] * (2 - len(c["trust"]))
        prev = bytes.fromhex(c["previous"]) if c["previous"] else bytes(8)
        e_cur = bytes.fromhex(e["current"]) if e else bytes(8)
        e_prev = bytes.fromhex(e["previous"]) if e and e["previous"] else bytes(8)
        lines.append(
            f"    {{\"{c['name']}\", krc_record_{i}, {len(bytes.fromhex(c['record']))}u, {krc.REASONS.index(c['reason'])}, {arr(bytes.fromhex(c['current']))}, {arr(prev)}, "
            f"{int(c['previous'] is not None)}, krc_revoked_{i}, {len(c['revoked'])}u, {{{arr(tid[0])}, {arr(tid[1])}}}, {{{arr(tpub[0])}, {arr(tpub[1])}}}, "
            f"{len(c['trust'])}u, {int(c['allow'])}, {c['last_counter']}u, {c['last_time']}u, {c['max_window_s']}u, {c['uptime']}u, {int(e is not None)}, "
            f"{arr(e_cur)}, {arr(e_prev)}, {int(bool(e and e['previous']))}, {e['window_s'] if e else 0}u, {e['started_at'] if e else 0}u, "
            f"{e['last_counter'] if e else 0}u, {(e['clock_offset'] & 0xFFFFFFFF) if e else 0}u}},")
    lines += ["};", "", f"#define KEY_ROTATION_COMMAND_VECTOR_COUNT {len(cases_)}u", "", "#endif // KEY_ROTATION_COMMAND_VECTORS_H", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, str]:
    doc = {"format": 1, "about": about(), "frame_id": "0x7EC", "chunk_flag": krc.CHUNK_FLAG, "chunk_count": krc.CHUNK_COUNT, "record_size": krc.RECORD_SIZE,
           "domain": krc.DOMAIN.hex(), "reasons": list(krc.REASONS), "cases": cases()}
    return {ROOT / "conformance" / "key_rotation_command_vectors.json": json.dumps(doc, indent=2) + "\n",
            ROOT / "generated" / "key_rotation_command_vectors.h": c_header(doc["cases"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None
        if current != text:
            if args.check:
                stale.append(path.name)
            else:
                path.write_bytes(text.encode("utf-8"))
                print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("out of date: " + ", ".join(stale) + " (run tools/make_key_rotation_command_vectors.py)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
