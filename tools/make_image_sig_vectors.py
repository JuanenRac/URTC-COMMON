#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_image_sig_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write ``conformance/image_sig_vectors.json``: the trust table and the ``.imgsig`` record, byte for byte.

[FIRMWARE] sin compilar placa ni flashear. The vectors are for the Python reference and for any other implementation (a bootloader twin, a web page) that must
read the same bytes. Every key here is a throwaway TEST key derived from a label: it signs nothing but these vectors and is no secret. A release key is never
in this repository. ``--check`` writes nothing and fails when the file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import image_auth as ia  # noqa: E402
from urtc_common import image_header as ih  # noqa: E402
from urtc_common import image_sig as sg  # noqa: E402

OUTPUT = ROOT / "conformance" / "image_sig_vectors.json"
HARDWARE_MAIN = 0x0303CC01
HARDWARE_SLAVE = 0x0303CB01


def seed(label: str) -> bytes:
    return hashlib.sha256(b"urtc throwaway test key image-sig " + label.encode()).digest()


def public(label: str) -> bytes:
    return sg.public_of(seed(label))


def table_cases() -> list[dict]:
    cur, nxt, old = public("current"), public("next"), public("old")
    good = sg.pack_table([(cur, sg.FLAG_CURRENT), (nxt, sg.FLAG_NEXT)])
    one = sg.pack_table([(cur, sg.FLAG_CURRENT)])
    revoked = sg.pack_table([(old, sg.FLAG_REVOKED), (cur, sg.FLAG_CURRENT)])

    def bad(name: str, data: bytes) -> dict:
        return {"name": name, "table": data.hex(), "valid": False}

    def refresh(body: bytes) -> bytes:   # a table whose CRC is right but whose content is wrong
        import struct
        import zlib
        return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)

    def flip(data: bytes, index: int, mask: int = 1) -> bytes:
        out = bytearray(data)
        out[index] ^= mask
        return bytes(out)

    body = good[:-4]
    cases = [
        {"name": "one current key", "table": one.hex(), "valid": True, "keys": [[cur.hex(), 1]], "trusted": [cur.hex()]},
        {"name": "current and next", "table": good.hex(), "valid": True, "keys": [[cur.hex(), 1], [nxt.hex(), 2]], "trusted": [cur.hex(), nxt.hex()]},
        {"name": "a revoked key stays in the table and is not trusted", "table": revoked.hex(), "valid": True,
         "keys": [[old.hex(), 4], [cur.hex(), 1]], "trusted": [cur.hex()]},
        {"name": "bytes after the table are ignored", "table": (one + b"\xff" * 20).hex(), "valid": True, "keys": [[cur.hex(), 1]], "trusted": [cur.hex()]},
        bad("bad magic", flip(good, 0)),
        bad("unknown schema", refresh(body[:4] + bytes([2]) + body[5:])),
        bad("zero keys", refresh(body[:5] + bytes([0]) + body[6:8])),
        bad("three keys", refresh(body[:5] + bytes([3]) + body[6:])),
        bad("table flags not zero", refresh(body[:6] + bytes([1]) + body[7:])),
        bad("a flipped bit in a public key", flip(good, 20)),
        bad("a flipped bit in the CRC", flip(good, len(good) - 1)),
        bad("a key id that is not the hash of the key", refresh(body[:8] + flip(body[8:], 0))),
        bad("unknown flag bit", refresh(body[:48] + bytes([0x08]) + body[49:])),
        bad("no flag at all", refresh(body[:48] + bytes([0x00]) + body[49:])),
        bad("current and next at once", refresh(body[:48] + bytes([0x03]) + body[49:])),
        bad("revoked together with current", refresh(body[:48] + bytes([0x05]) + body[49:])),
        bad("padding not zero", refresh(body[:49] + bytes([1]) + body[50:])),
        bad("the same key twice", refresh(body[:52] + body[8:52] + body[96:])),
        bad("cut short", good[:-1]),
        bad("two current keys", refresh(body[:92] + bytes([0x01]) + body[93:])),
    ]
    for case in cases:
        data = bytes.fromhex(case["table"])
        try:
            keys = sg.parse_table(data)
            assert case["valid"], case["name"]
            assert [[p.hex(), f] for p, f in keys] == case["keys"], case["name"]
            assert [k.hex() for k in sg.trusted_keys(keys)] == case["trusted"], case["name"]
        except sg.TrustError:
            assert not case["valid"], case["name"]
    return cases


def imgsig_text_cases() -> list[dict]:
    record = ia.make_record(seed("current"), bytes(28), bytes(32), 1)
    line = record.hex()
    cases = [("lower case with a line end", line + "\n", True), ("no line end", line, True), ("upper case", line.upper() + "\n", True),
             ("one digit short", line[:-1] + "\n", False), ("one digit long", line + "0\n", False), ("a non-hex digit", "g" + line[1:] + "\n", False),
             ("two line ends", line + "\n\n", False), ("a space at the end", line + " \n", False), ("two lines", line[:76] + "\n" + line[76:] + "\n", False),
             ("empty", "", False), ("a carriage return", line + "\r\n", False)]
    out = []
    for name, text, valid in cases:
        try:
            assert sg.decode_imgsig(text) == record and valid, name
        except sg.TrustError:
            assert not valid, name
        out.append({"name": name, "text": text, "valid": valid})
    return out


def verify_cases() -> list[dict]:
    payload = bytes((i * 13 + 5) & 0xFF for i in range(100))
    header = ih.make_header(payload, HARDWARE_MAIN, (0, 8, 1, 3), signed=False)[:ia.HEADER_BYTES]
    cur, nxt, old = public("current"), public("next"), public("old")
    table = sg.pack_table([(cur, sg.FLAG_CURRENT), (nxt, sg.FLAG_NEXT)])
    revoked_table = sg.pack_table([(old, sg.FLAG_REVOKED), (cur, sg.FLAG_CURRENT)])

    def flip(data: bytes, index: int) -> bytes:
        out = bytearray(data)
        out[index] ^= 1
        return bytes(out)

    def case(name: str, table_bytes: bytes, text: str, hdr: bytes = header, body: bytes = payload, hardware: int = HARDWARE_MAIN, floor: int = 0) -> dict:
        return {"name": name, "table": table_bytes.hex(), "imgsig": text, "header": hdr.hex(), "payload": body.hex(), "hardware_id": hardware, "floor": floor,
                "expected": sg.verify_image(text, sg.parse_table(table_bytes), hardware, hdr, body, floor)}

    good = sg.sign_image(seed("current"), header, payload, 5)
    return [
        case("signed by the current key", table, good),
        case("signed by the next key", table, sg.sign_image(seed("next"), header, payload, 5)),
        case("the next key is not in a table that lists only the current one", sg.pack_table([(cur, sg.FLAG_CURRENT)]), sg.sign_image(seed("next"), header, payload, 5)),
        case("signed by a key nobody lists", table, sg.sign_image(seed("stranger"), header, payload, 5)),
        case("signed by a revoked key", revoked_table, sg.sign_image(seed("old"), header, payload, 5)),
        case("a counter equal to the floor", table, good, floor=5),
        case("a counter below the floor", table, good, floor=6),
        case("a flipped bit in the payload", table, good, body=flip(payload, 50)),
        case("a flipped bit in the header", table, good, hdr=flip(header, 14)),
        case("another hardware id", table, good, hardware=HARDWARE_SLAVE),
        case("a flipped bit in the signature", table, good[:100] + format(int(good[100], 16) ^ 1, "x") + good[101:]),
        case("a flipped bit in the counter", table, good[:17] + format(int(good[17], 16) ^ 1, "x") + good[18:]),
        case("a flipped bit in the key id", table, format(int(good[0], 16) ^ 1, "x") + good[1:]),
        case("a malformed file", table, good[:-3] + "\n"),
    ]


def render() -> str:
    doc = {
        "format": 1,
        "about": "Trust table and .imgsig vectors. Keys are throwaway test keys derived from labels (see tools/make_image_sig_vectors.py); no secret is here.",
        "table_cases": table_cases(),
        "imgsig_text_cases": imgsig_text_cases(),
        "verify_cases": verify_cases(),
    }
    return json.dumps(doc, indent=1, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="write nothing; fail when the file differs")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{OUTPUT.name} is out of date: run tools/make_image_sig_vectors.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT.name} is current")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
