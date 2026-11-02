#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_bootloader_auth_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the bootloader authentication and of the addressing by serial number, and the C tables the firmware checks itself against.

[FIRMWARE] sin compilar placa ni flashear: the vectors are for host tests of portable C and of the Python reference.

* ``conformance/ed25519_vectors.json``         Ed25519 signatures: RFC 8032 cases, padding-boundary lengths and each way a signature can be wrong
* ``conformance/signed_image_vectors.json``    the decision to install an image: signed, altered, other key, rollback, no serial of the hardware...
* ``conformance/bootloader_select_vectors.json``  scenarios of one bootloader answering the frames of ``0x7EA`` and gating the single-head frames (with or without a
  programmable serial), and scenarios of a whole bus: enumeration and the detection of a duplicate serial
* ``generated/ed25519_vectors.h``, ``generated/signed_image_vectors.h``, ``generated/bootloader_select_vectors.h``   the same as C tables

Every key here is a throwaway TEST key derived from a label: it signs nothing but these vectors and is no secret. A release key is never in this repository.
``--check`` writes nothing and fails when a file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import bl_select as bs  # noqa: E402
from urtc_common import ed25519, image_auth as ia  # noqa: E402
from urtc_common import image_header as ih  # noqa: E402

HARDWARE_MAIN = 0x0303CC01
HARDWARE_SLAVE = 0x0303CB01


def test_seed(label: str) -> bytes:
    return hashlib.sha256(b"urtc throwaway test key " + label.encode()).digest()


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
def ed25519_cases() -> list[dict]:
    cases: list[dict] = []

    def add(name: str, pk: bytes, msg: bytes, sig: bytes, valid: bool, source: str) -> None:
        cases.append({"name": name, "source": source, "public_key": pk.hex().upper(), "message": msg.hex().upper(), "signature": sig.hex().upper(), "valid": valid})

    rfc1_sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    rfc2_sk = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    for number, sk, msg in ((1, rfc1_sk, b""), (2, rfc2_sk, b"\x72")):
        add(f"RFC 8032 test {number}", ed25519.public_key(sk), msg, ed25519.sign(sk, msg), True, "rfc8032")
    seed = test_seed("a")
    pk = ed25519.public_key(seed)
    for length in (0, 1, 3, 55, 56, 111, 112, 127, 128, 129, 200, 1000):
        msg = bytes((i * 7 + length) & 0xFF for i in range(length))
        add(f"a valid signature over {length} bytes", pk, msg, ed25519.sign(seed, msg), True, "own")
    msg = b"URTC bootloader test message"
    sig = ed25519.sign(seed, msg)

    def flip(data: bytes, index: int, mask: int = 0x01) -> bytes:
        out = bytearray(data)
        out[index] ^= mask
        return bytes(out)

    add("a flipped bit in R", pk, msg, flip(sig, 3), False, "own")
    add("a flipped bit in S", pk, msg, flip(sig, 40), False, "own")
    add("a flipped bit in the message", pk, flip(msg, 5), sig, False, "own")
    add("a message one byte longer", pk, msg + b"\x00", sig, False, "own")
    add("a message one byte shorter", pk, msg[:-1], sig, False, "own")
    add("another public key", ed25519.public_key(test_seed("b")), msg, sig, False, "own")
    s_plus_l = (int.from_bytes(sig[32:], "little") + ed25519.L).to_bytes(32, "little")
    add("a scalar that is not below the group order (S + L)", pk, msg, sig[:32] + s_plus_l, False, "own")
    add("a scalar of all ones", pk, msg, sig[:32] + b"\xff" * 32, False, "own")
    add("an all-zero signature", pk, msg, bytes(64), False, "own")
    add("a public key whose y is not reduced", bytes([0xED] + [0xFF] * 30 + [0x7F]), msg, sig, False, "own")
    off_curve = next(bytes([n]) + bytes(31) for n in range(2, 256) if ed25519.decompress(bytes([n]) + bytes(31)) is None)
    add("a public key that is not a point of the curve", off_curve, msg, sig, False, "own")
    add("a public key of all zeros", bytes(32), msg, sig, False, "own")
    for case in cases:
        assert ed25519.verify(bytes.fromhex(case["public_key"]), bytes.fromhex(case["message"]), bytes.fromhex(case["signature"])) == case["valid"], case["name"]
    return cases


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
KEY_LABELS = ("current", "next", "stranger")


def signed_image_keys() -> list[bytes]:
    return [ed25519.public_key(test_seed("image " + label)) for label in KEY_LABELS]


def signed_image_cases() -> list[dict]:
    seeds = [test_seed("image " + label) for label in KEY_LABELS]
    keys = signed_image_keys()
    payload = bytes((i * 13 + 5) & 0xFF for i in range(100))
    sha = hashlib.sha256(payload).digest()
    version = (0, 8, 1, 3)
    header = ih.make_header(payload, HARDWARE_MAIN, version, signed=False)[:ia.HEADER_BYTES]

    def flip(data: bytes, index: int) -> bytes:
        out = bytearray(data)
        out[index] ^= 1
        return bytes(out)

    def record(seed_index: int, counter: int, hdr: bytes = header, digest: bytes = sha) -> bytes:
        return ia.make_record(seeds[seed_index], hdr, digest, counter)

    base = {"policy": ia.POLICY_ED25519_ONLY, "trusted": [0], "hardware_id": HARDWARE_MAIN, "installed_counter": 5, "installed_version": (0, 8, 1, 2),
            "downgrade_authorized": False, "header": header, "sha": sha, "record": record(0, 5), "hmac_ok": False}
    older_header = ih.make_header(payload, HARDWARE_MAIN, (0, 8, 0, 9), signed=False)[:ia.HEADER_BYTES]
    other_payload_sha = hashlib.sha256(payload + b"x").digest()
    good = record(0, 5)
    spec: list[tuple[str, dict]] = [
        ("a good image signed by the trusted key", {}),
        ("a good image with a higher counter raises the floor", {"record": record(0, 7)}),
        ("rotation: signed by the next key when both are trusted", {"trusted": [0, 1], "record": record(1, 5)}),
        ("rotation: signed by the next key when only the current one is trusted", {"record": record(1, 5)}),
        ("signed by a key nobody trusts", {"record": record(2, 5)}),
        ("no trusted key at all", {"trusted": []}),
        ("a flipped bit in the signature", {"record": good[:12] + flip(good[12:], 10)}),
        ("a payload that is not the one signed", {"sha": other_payload_sha}),
        ("a version that is not the one signed", {"header": flip(header, 15)}),
        ("a counter raised without signing again", {"record": good[:8] + (6).to_bytes(4, "big") + good[12:]}),
        ("the key id of another trusted key on a signature of the first", {"trusted": [0, 1], "record": ia.key_id(keys[1]) + good[8:]}),
        ("an image built for other hardware", {"hardware_id": HARDWARE_SLAVE}),
        ("a counter below the floor", {"record": record(0, 3)}),
        ("an older version without authorisation", {"header": older_header, "record": record(0, 5, older_header)}),
        ("an older version the owner authorised", {"header": older_header, "record": record(0, 5, older_header), "downgrade_authorized": True}),
        ("an older version and a counter below the floor, authorised: the counter still refuses", {"header": older_header, "record": record(0, 4, older_header), "downgrade_authorized": True}),
        ("no signature when only Ed25519 is accepted, even with a good HMAC", {"record": None, "hmac_ok": True}),
        ("transition: no signature and a good HMAC", {"policy": ia.POLICY_EITHER, "record": None, "hmac_ok": True}),
        ("transition: no signature and no HMAC", {"policy": ia.POLICY_EITHER, "record": None}),
        ("transition: a signature that fails and a good HMAC", {"policy": ia.POLICY_EITHER, "record": good[:12] + flip(good[12:], 10), "hmac_ok": True}),
        ("transition: a signature that fails and no HMAC", {"policy": ia.POLICY_EITHER, "record": good[:12] + flip(good[12:], 10)}),
        ("transition: a good signature and no HMAC", {"policy": ia.POLICY_EITHER, "record": record(0, 8)}),
        ("legacy: a good HMAC", {"policy": ia.POLICY_HMAC_ONLY, "record": None, "hmac_ok": True}),
        ("legacy: a bad HMAC", {"policy": ia.POLICY_HMAC_ONLY, "record": None}),
        ("legacy: a bad HMAC is not rescued by a good signature", {"policy": ia.POLICY_HMAC_ONLY}),
        ("the installed version is not known", {"installed_version": None, "header": older_header, "record": record(0, 5, older_header)}),
    ]
    out = []
    for name, changes in spec:
        c = {**base, **changes}
        trusted = [keys[i] for i in c["trusted"]]
        status, counter = ia.decide(c["policy"], trusted, c["hardware_id"], c["installed_counter"], c["installed_version"], c["downgrade_authorized"], c["header"], c["sha"],
                                    c["record"], c["hmac_ok"])
        out.append({"name": name, "policy": c["policy"], "trusted": c["trusted"], "hardware_id": c["hardware_id"], "installed_counter": c["installed_counter"],
                    "installed_version": list(c["installed_version"]) if c["installed_version"] else None, "downgrade_authorized": c["downgrade_authorized"],
                    "header": c["header"].hex().upper(), "payload_sha256": c["sha"].hex().upper(), "record": c["record"].hex().upper() if c["record"] else None,
                    "hmac_ok": c["hmac_ok"], "status": ia.STATUS_NAMES[status], "status_code": status, "new_counter": counter})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
NODE_UIDS = {"a": (0x11111111, 0x22222222, 0x33333333), "no_serial_zero": (0, 0, 0), "no_serial_ones": (0xFFFFFFFF, 0, 0)}
PROGRAMMED = 0x00C0FFEE
BLANK_RECORD = (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
# the metadata record of the programmable serial that goes with each node: None when the head has none
NODE_RECORDS: dict[str, tuple[int, int, int] | None] = {
    "prog": bs.serial_record(PROGRAMMED),
    "prog_bad_check": (bs.SERIAL_RECORD_MAGIC, PROGRAMMED, 0x12345678),
    "prog_bad_magic": (0x55525332, PROGRAMMED, ~PROGRAMMED & 0xFFFFFFFF),
    "prog_blank": BLANK_RECORD,
    "prog_zero": bs.serial_record(0),
    "prog_ones": bs.serial_record(0xFFFFFFFF),
}
NODE_UIDS.update({k: NODE_UIDS["a"] for k in NODE_RECORDS})


def select_scenarios() -> list[dict]:
    uid_a = NODE_UIDS["a"]
    serial_a = bs.serial_from_uid(*uid_a)
    other = serial_a ^ 0x00010000
    top = serial_a & 0xFFFF0000
    flipped_top = (serial_a ^ 0x80000000) & 0xFFFFFFFF

    def cmd(t: int, data: bytes, busy: bool = False) -> dict:
        return {"kind": "cmd", "t": t, "data": data.hex().upper(), "busy": busy}

    def gate(t: int, can_id: int, busy: bool = False) -> dict:
        return {"kind": "gate", "t": t, "id": can_id, "busy": busy}

    raw: list[tuple[str, str, list[dict]]] = [
        ("a bootloader nobody addresses behaves as it always did", "a", [gate(100, 0x7F8), gate(200, 0x7F0), gate(30000, 0x7F1), gate(30001, 0x110)]),
        ("a probe is answered by whoever matches the prefix", "a", [
            cmd(10, bs.probe_frame(0, 0)), cmd(20, bs.probe_frame(32, serial_a)), cmd(30, bs.probe_frame(16, top)), cmd(40, bs.probe_frame(1, flipped_top)),
            cmd(50, bs.probe_frame(32, other))]),
        ("a probe with more than 32 bits, or the wrong length, is ignored and addresses nobody", "a", [
            cmd(10, bytes([1, 33, 0, 0, 0, 0])), cmd(20, bytes([1, 0, 0, 0, 0])), cmd(30, bytes([9, 0, 0, 0, 0, 0])), cmd(40, b""), gate(50, 0x7F8)]),
        ("selecting by serial opens the single-head frames, selecting another closes them", "a", [
            cmd(10, bs.probe_frame(0, 0)), gate(20, 0x7F8), cmd(30, bs.select_frame(serial_a, 7)), gate(40, 0x7F8), gate(50, 0x7F1), gate(60, 0x110),
            cmd(70, bs.select_frame(other, 8)), gate(80, 0x7F8), gate(90, 0x7E9), gate(100, 0x7FF)]),
        ("a selection lapses unless it is repeated", "a", [
            cmd(1000, bs.select_frame(serial_a, 1)), gate(2999, 0x7F8), gate(3001, 0x7F8), gate(3002, 0x7F8), cmd(4000, bs.select_frame(serial_a, 2)),
            cmd(5000, bs.select_frame(serial_a, 3)), gate(6999, 0x7F8), gate(7001, 0x7F8)]),
        ("a selection holds while an update runs", "a", [
            cmd(0, bs.select_frame(serial_a, 1)), gate(1500, 0x7F2, True), gate(5000, 0x7F2, True), gate(9000, 0x7F4, True), gate(9001, 0x7F4)]),
        ("addressed mode lapses and gives the single-head behaviour back", "a", [
            cmd(0, bs.probe_frame(0, 0)), gate(5000, 0x7F8), gate(10000, 0x7F8), gate(10001, 0x7F8)]),
        ("the 96-bit unique ID is read only from the selected bootloader", "a", [
            cmd(0, bs.uid_frame(0)), cmd(10, bs.select_frame(serial_a, 1)), cmd(20, bs.uid_frame(0)), cmd(30, bs.uid_frame(1)), cmd(40, bs.uid_frame(2)),
            cmd(50, bs.uid_frame(3)), cmd(60, bytes([4]))]),
        ("a release leaves nobody selected", "a", [cmd(0, bs.select_frame(serial_a, 1)), gate(10, 0x7F8), cmd(20, bs.release_frame()), gate(30, 0x7F8), gate(40, 0x110)]),
        ("a bootloader whose unique ID folds to zero takes no part", "no_serial_zero", [cmd(10, bs.probe_frame(0, 0)), cmd(20, bs.select_frame(0, 1)), gate(30, 0x7F8)]),
        ("a bootloader whose unique ID folds to all ones takes no part", "no_serial_ones", [cmd(10, bs.probe_frame(0, 0)), cmd(20, bs.select_frame(0xFFFFFFFF, 1)), gate(30, 0x7F8)]),
        ("a programmed serial takes priority over the fold of the unique ID", "prog", [
            cmd(10, bs.probe_frame(32, PROGRAMMED)), cmd(20, bs.probe_frame(32, serial_a)), cmd(30, bs.probe_frame(8, PROGRAMMED)), cmd(40, bs.select_frame(serial_a, 1)),
            gate(50, 0x7F8), cmd(60, bs.select_frame(PROGRAMMED, 2)), gate(70, 0x7F8), cmd(80, bs.uid_frame(0)), cmd(90, bs.uid_frame(2))]),
        ("a record with a wrong check leaves the fold of the unique ID in charge", "prog_bad_check", [
            cmd(10, bs.probe_frame(32, serial_a)), cmd(20, bs.probe_frame(32, PROGRAMMED)), cmd(30, bs.select_frame(serial_a, 1)), gate(40, 0x7F8)]),
        ("a record with a wrong magic leaves the fold of the unique ID in charge", "prog_bad_magic", [
            cmd(10, bs.probe_frame(32, serial_a)), cmd(20, bs.select_frame(PROGRAMMED, 1)), gate(30, 0x7F8), cmd(40, bs.select_frame(serial_a, 2)), gate(50, 0x7F8)]),
        ("blank metadata flash leaves the fold of the unique ID in charge", "prog_blank", [
            cmd(10, bs.probe_frame(32, serial_a)), cmd(20, bs.select_frame(serial_a, 1)), gate(30, 0x7F8)]),
        ("a programmed serial of zero is not a serial: the fold is used", "prog_zero", [cmd(10, bs.probe_frame(32, serial_a)), cmd(20, bs.select_frame(serial_a, 1)), gate(30, 0x7F8)]),
        ("a programmed serial of all ones is not a serial: the fold is used", "prog_ones", [cmd(10, bs.probe_frame(32, serial_a)), cmd(20, bs.select_frame(serial_a, 1)), gate(30, 0x7F8)]),
        ("the millisecond counter wraps", "a", [cmd(0xFFFFFF00, bs.select_frame(serial_a, 1)), gate(0x00000100, 0x7F8), gate(0x00000900, 0x7F8)]),
    ]
    out = []
    for name, node_key, steps in raw:
        node = bs.BootloaderNode(NODE_UIDS[node_key], NODE_RECORDS.get(node_key))
        recorded = []
        for step in steps:
            entry = dict(step)
            if step["kind"] == "cmd":
                reply = node.on_cmd(step["t"], bytes.fromhex(step["data"]), step["busy"])
                if reply is not None:
                    assert reply[0] == bs.ID_RESP
                entry["reply"] = reply[1].hex().upper() if reply else ""
                entry["accept"] = None
            else:
                entry["reply"] = ""
                entry["accept"] = node.accepts(step["t"], step["id"], step["busy"])
            entry["selected"] = node.selected
            entry["addressed"] = node.addressed
            recorded.append(entry)
        record = NODE_RECORDS.get(node_key)
        out.append({"name": name, "uid": [f"0x{w:08X}" for w in NODE_UIDS[node_key]], "record": [f"0x{w:08X}" for w in record] if record else None,
                    "serial": f"0x{node.serial:08X}", "serial_source": node.serial_source, "steps": recorded})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
def bus_scenarios() -> list[dict]:
    """A whole bus: the host enumerates the serials, selects one, reads the three words of the unique ID and decides whether two heads share the serial."""
    fold_a = bs.serial_from_uid(1, 2, 3)
    clash_a, clash_b = (0x10, 0x20, 0x30), (0x10 ^ 0x800, 0x20 ^ 1, 0x30)   # one fold, two unique IDs
    assert bs.serial_from_uid(*clash_a) == bs.serial_from_uid(*clash_b)
    raw: list[tuple[str, list[tuple[tuple[int, int, int], tuple[int, int, int] | None]], int | None]] = [
        ("one head: nothing to confuse", [((1, 2, 3), None)], fold_a),
        ("two heads with different serials", [((1, 2, 3), None), ((4, 5, 6), None)], fold_a),
        ("two heads whose unique IDs fold to one serial", [(clash_a, None), (clash_b, None)], bs.serial_from_uid(*clash_a)),
        ("a programmed serial removes the clash of two folded serials", [(clash_a, bs.serial_record(0x00A00001)), (clash_b, bs.serial_record(0x00A00002))], 0x00A00001),
        ("two heads programmed with one serial", [((1, 2, 3), bs.serial_record(PROGRAMMED)), ((4, 5, 6), bs.serial_record(PROGRAMMED))], PROGRAMMED),
        ("a programmed serial equal to the fold of another head", [((1, 2, 3), None), ((7, 8, 9), bs.serial_record(fold_a))], fold_a),
        ("a programmed head and a folded head with different serials", [((1, 2, 3), bs.serial_record(PROGRAMMED)), ((4, 5, 6), None)], PROGRAMMED),
        ("heads that announce no serial: the host keeps the single-head behaviour", [((0, 0, 0), None), ((0xFFFFFFFF, 0, 0), None)], None),
    ]
    out = []
    for name, nodes_spec, select_serial in raw:
        nodes = [bs.BootloaderNode(uid, rec) for uid, rec in nodes_spec]

        def probe(nbits: int, prefix: int, nodes: list[bs.BootloaderNode] = nodes) -> bool:
            replies = {r[1] for n in nodes if (r := n.on_cmd(0, bs.probe_frame(nbits, prefix)))}
            assert len(replies) <= 1
            return bool(replies)

        enumerated = bs.enumerate_serials(probe)
        duplicate = False
        if select_serial is not None:
            answered = bool({r[1] for n in nodes if (r := n.on_cmd(1, bs.select_frame(select_serial, 1)))})
            words = [sorted({r[1] for n in nodes if (r := n.on_cmd(2, bs.uid_frame(part)))}) for part in range(3)]
            duplicate = bs.duplicate_suspected(answered, words)
        out.append({"name": name, "nodes": [{"uid": [f"0x{w:08X}" for w in uid], "record": [f"0x{w:08X}" for w in rec] if rec else None} for uid, rec in nodes_spec],
                    "select": f"0x{select_serial:08X}" if select_serial is not None else None, "enumerated": [f"0x{x:08X}" for x in enumerated], "duplicate": duplicate})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
def hex_array(name: str, raw: bytes, const: str = "static const uint8_t") -> str:
    return f"{const} {name}[] = {{{', '.join(f'0x{b:02X}' for b in raw) if raw else '0'}}};"


def c_ed25519(cases: list[dict]) -> str:
    lines = ["// GENERATED by tools/make_bootloader_auth_vectors.py - do not edit by hand.", "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
             "// GPL-3.0-or-later - see LICENSE", "#ifndef ED25519_VECTORS_H", "#define ED25519_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
             "typedef struct {", "    const char *name;", "    const uint8_t *public_key;     // 32 bytes", "    const uint8_t *message;", "    size_t message_length;",
             "    const uint8_t *signature;      // 64 bytes", "    int valid;", "} ed25519_vec_t;", ""]
    for i, c in enumerate(cases):
        lines.append(hex_array(f"ed25519_pk_{i}", bytes.fromhex(c["public_key"])))
        lines.append(hex_array(f"ed25519_msg_{i}", bytes.fromhex(c["message"])))
        lines.append(hex_array(f"ed25519_sig_{i}", bytes.fromhex(c["signature"])))
    lines += ["", "static const ed25519_vec_t ED25519_VECTORS[] = {"]
    for i, c in enumerate(cases):
        lines.append(f"    {{\"{c['name']}\", ed25519_pk_{i}, ed25519_msg_{i}, {len(c['message']) // 2}u, ed25519_sig_{i}, {1 if c['valid'] else 0}}},")
    lines += ["};", "", f"#define ED25519_VECTOR_COUNT {len(cases)}u", "", "#endif // ED25519_VECTORS_H", ""]
    return "\n".join(lines)


def c_signed_image(cases: list[dict]) -> str:
    keys = signed_image_keys()
    lines = ["// GENERATED by tools/make_bootloader_auth_vectors.py - do not edit by hand.", "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
             "// GPL-3.0-or-later - see LICENSE", "#ifndef SIGNED_IMAGE_VECTORS_H", "#define SIGNED_IMAGE_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
             "// the three throwaway TEST public keys the cases refer to by index (current, next, stranger)",
             "static const uint8_t SIGNED_IMAGE_KEYS[3][32] = {"]
    for key in keys:
        lines.append("    {" + ", ".join(f"0x{b:02X}" for b in key) + "},")
    lines += ["};", "", "typedef struct {", "    const char *name;", "    int policy;", "    unsigned trusted_mask;       // bit i: SIGNED_IMAGE_KEYS[i] is trusted, in index order",
              "    uint32_t hardware_id;", "    uint32_t installed_counter;", "    int version_known;", "    uint16_t major;", "    uint8_t minor, patch;", "    uint16_t build;",
              "    int downgrade_authorized;", "    const uint8_t *header;       // 28 bytes", "    const uint8_t *payload_sha256;", "    const uint8_t *record;      // 76 bytes, or NULL",
              "    int hmac_ok;", "    int status;                  // urtc_auth_status_t", "    uint32_t new_counter;", "} signed_image_vec_t;", ""]
    for i, c in enumerate(cases):
        lines.append(hex_array(f"signed_image_header_{i}", bytes.fromhex(c["header"])))
        lines.append(hex_array(f"signed_image_sha_{i}", bytes.fromhex(c["payload_sha256"])))
        if c["record"]:
            lines.append(hex_array(f"signed_image_record_{i}", bytes.fromhex(c["record"])))
    lines += ["", "static const signed_image_vec_t SIGNED_IMAGE_VECTORS[] = {"]
    for i, c in enumerate(cases):
        mask = sum(1 << k for k in c["trusted"])
        v = c["installed_version"] or [0, 0, 0, 0]
        record = f"signed_image_record_{i}" if c["record"] else "NULL"
        lines.append(f"    {{\"{c['name']}\", {c['policy']}, {mask}u, 0x{c['hardware_id']:08X}u, {c['installed_counter']}u, {1 if c['installed_version'] else 0}, "
                     f"{v[0]}u, {v[1]}u, {v[2]}u, {v[3]}u, {1 if c['downgrade_authorized'] else 0}, signed_image_header_{i}, signed_image_sha_{i}, {record}, "
                     f"{1 if c['hmac_ok'] else 0}, {c['status_code']}, {c['new_counter']}u}},")
    lines += ["};", "", f"#define SIGNED_IMAGE_VECTOR_COUNT {len(cases)}u", "", "#endif // SIGNED_IMAGE_VECTORS_H", ""]
    return "\n".join(lines)


def c_select(scenarios: list[dict], buses: list[dict]) -> str:
    lines = ["// GENERATED by tools/make_bootloader_auth_vectors.py - do not edit by hand.", "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
             "// GPL-3.0-or-later - see LICENSE", "#ifndef BOOTLOADER_SELECT_VECTORS_H", "#define BOOTLOADER_SELECT_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
             "typedef struct {", "    int is_gate;                 // 0: a frame on 0x7EA, 1: a single-head frame to be gated", "    uint32_t t;", "    uint16_t id;                 // gate only",
             "    uint8_t dlc;", "    uint8_t data[8];", "    int busy;", "    uint8_t reply_dlc;           // 0: no answer", "    uint8_t reply[8];", "    int accept;                  // gate only",
             "    int selected, addressed;     // after the step", "} select_step_t;", "",
             "typedef struct {", "    const char *name;", "    uint32_t uid[3];", "    int has_record;              // a programmable-serial record is present in the metadata",
             "    uint32_t record[3];          // magic, serial, check", "    uint32_t serial;", "    const select_step_t *steps;", "    size_t step_count;", "} select_scenario_t;", ""]
    for i, s in enumerate(scenarios):
        lines.append(f"static const select_step_t select_steps_{i}[] = {{")
        for st in s["steps"]:
            data = bytes.fromhex(st.get("data", ""))
            reply = bytes.fromhex(st["reply"])
            pad = lambda b: ", ".join(f"0x{x:02X}" for x in (b + bytes(8))[:8])  # noqa: E731
            gate = st["kind"] == "gate"
            lines.append(f"    {{{1 if gate else 0}, {st['t']}u, 0x{st.get('id', 0):03X}u, {len(data)}, {{{pad(data)}}}, {1 if st['busy'] else 0}, {len(reply)}, {{{pad(reply)}}}, "
                         f"{(1 if st['accept'] else 0) if gate else 0}, {1 if st['selected'] else 0}, {1 if st['addressed'] else 0}}},")
        lines.append("};")
    lines += ["", "static const select_scenario_t SELECT_SCENARIOS[] = {"]
    for i, s in enumerate(scenarios):
        uid = ", ".join(s["uid"])
        rec = ", ".join(s["record"] if s["record"] else ["0", "0", "0"])
        lines.append(f"    {{\"{s['name']}\", {{{uid}}}, {1 if s['record'] else 0}, {{{rec}}}, {s['serial']}u, select_steps_{i}, {len(s['steps'])}u}},")
    lines += ["};", "", f"#define SELECT_SCENARIO_COUNT {len(scenarios)}u", ""]
    lines += ["typedef struct {", "    uint32_t uid[3];", "    int has_record;", "    uint32_t record[3];", "} bus_node_t;", "",
              "typedef struct {", "    const char *name;", "    size_t node_count;", "    bus_node_t nodes[3];", "    int has_select;", "    uint32_t select_serial;",
              "    size_t enumerated_count;", "    uint32_t enumerated[3];   // ascending", "    int duplicate;", "} bus_scenario_t;", "", "static const bus_scenario_t BUS_SCENARIOS[] = {"]
    for b in buses:
        nodes = []
        for n in b["nodes"]:
            rec = ", ".join(n["record"] if n["record"] else ["0", "0", "0"])
            nodes.append(f"{{{{{', '.join(n['uid'])}}}, {1 if n['record'] else 0}, {{{rec}}}}}")
        enum = ", ".join(f"{x}u" for x in b["enumerated"]) or "0"
        lines.append(f"    {{\"{b['name']}\", {len(b['nodes'])}u, {{{', '.join(nodes)}}}, {1 if b['select'] else 0}, {(b['select'] or '0')}u, {len(b['enumerated'])}u, "
                     f"{{{enum}}}, {1 if b['duplicate'] else 0}}},")
    lines += ["};", "", f"#define BUS_SCENARIO_COUNT {len(buses)}u", "", "#endif // BOOTLOADER_SELECT_VECTORS_H", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
def outputs() -> dict[Path, str]:
    ed = ed25519_cases()
    si = signed_image_cases()
    sel = select_scenarios()
    bus = bus_scenarios()
    about_keys = "Throwaway test keys derived from labels: they sign only these vectors and are no secret."
    return {
        ROOT / "conformance" / "ed25519_vectors.json": json.dumps({"format": 1, "about": "Ed25519 (RFC 8032) signatures: what a verifier must accept and what it must refuse. " + about_keys, "cases": ed}, indent=2) + "\n",
        ROOT / "conformance" / "signed_image_vectors.json": json.dumps({
            "format": 1, "about": "The decision to install an image: the signed record, the policy, the rollback rules. " + about_keys, "key_labels": list(KEY_LABELS),
            "public_keys": [k.hex().upper() for k in signed_image_keys()], "policies": list(ia.POLICY_NAMES), "statuses": list(ia.STATUS_NAMES), "cases": si}, indent=2) + "\n",
        ROOT / "conformance" / "bootloader_select_vectors.json": json.dumps({
            "format": 2, "about": "One bootloader answering the frames of 0x7EA and gating the single-head frames, step by step, with or without a programmable serial in "
            "the metadata; and whole buses where the host enumerates the serials and decides whether two heads share one.",
            "serial_record": {"magic": f"0x{bs.SERIAL_RECORD_MAGIC:08X}", "words": ["magic", "serial", "complement of the serial"]}, "scenarios": sel, "bus_scenarios": bus}, indent=2) + "\n",
        ROOT / "generated" / "ed25519_vectors.h": c_ed25519(ed),
        ROOT / "generated" / "signed_image_vectors.h": c_signed_image(si),
        ROOT / "generated" / "bootloader_select_vectors.h": c_select(sel, bus),
    }


def shown(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None
        if current != text:
            if args.check:
                stale.append(shown(path))
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {shown(path)}")
    if stale:
        print("BOOTLOADER_AUTH_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_bootloader_auth_vectors.py)", file=sys.stderr)
        return 1
    print("BOOTLOADER_AUTH_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
