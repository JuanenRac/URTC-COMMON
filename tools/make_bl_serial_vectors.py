#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_bl_serial_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the signed command that programs the serial number of a bootloader, and the C table the firmware checks itself against.

* ``conformance/bl_serial_vectors.json``   the decision on a command (valid, other head, other key, altered, replay, disabled, busy...) and the choice
  between the two slots of the record
* ``generated/bl_serial_vectors.h``        the same as C tables

Every key here is a throwaway TEST key derived from a label: it signs nothing but these vectors and is no secret. A release key is never in this repository.
``--check`` writes nothing and fails when a file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import bl_select as bs  # noqa: E402
from urtc_common import bl_serial as sr  # noqa: E402
from urtc_common import ed25519  # noqa: E402

UID = (0x12345678, 0x9ABCDEF0, 0x0F1E2D3C)
OTHER_UID = (0x12345678, 0x9ABCDEF0, 0x0F1E2D3D)


DEV_SEED = hashlib.sha256(b"urtc public development image key v1").digest()   # the public development key that a "dev" bootloader trusts: no secret


def seed(label: str) -> bytes:
    """The first key is the public development key, so that the host suites of the bootloader (which trusts it) can replay the commands."""
    if label == "serial-a":
        return DEV_SEED
    return hashlib.sha256(b"urtc throwaway test key " + label.encode()).digest()


def keys() -> list[bytes]:
    return [ed25519.public_key(seed("serial-a")), ed25519.public_key(seed("serial-b"))]


def flip(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 1]) + data[index + 1:]


def command_cases() -> list[dict]:
    current = bs.serial_from_uid(*UID)
    good = sr.make_command(seed("serial-a"), UID, current, 0x00C0FFEE, 5)
    cases: list[dict] = []

    def add(name: str, command: bytes, **kw) -> None:
        c = {"uid": UID, "current_serial": current, "trusted": [0], "stored_counter": 4, "enabled": True, "busy": False}
        c.update(kw)
        status, serial, counter = sr.decide(command, c["uid"], c["current_serial"], [keys()[i] for i in c["trusted"]], c["stored_counter"], c["enabled"], c["busy"])
        cases.append({"name": name, "uid": [f"{w:08X}" for w in c["uid"]], "current_serial": f"{c['current_serial']:08X}", "trusted": c["trusted"],
                      "stored_counter": c["stored_counter"], "enabled": c["enabled"], "busy": c["busy"], "command": command.hex().upper(), "status": status,
                      "status_name": sr.STATUS_NAMES[status], "serial": f"{serial:08X}", "counter": counter})

    add("a valid command", good)
    add("a valid command for the first write (nothing stored)", sr.make_command(seed("serial-a"), UID, current, 0x00C0FFEE, 1), stored_counter=0)
    add("a replay: the counter equals the stored one", good, stored_counter=5)
    add("a replay: the counter is below the stored one", good, stored_counter=9)
    add("a command made for another head fails", sr.make_command(seed("serial-a"), OTHER_UID, current, 0x00C0FFEE, 5))
    add("the same command on another head is not for it", good, uid=OTHER_UID, current_serial=bs.serial_from_uid(*OTHER_UID))
    add("signed by a key the bootloader does not trust", sr.make_command(seed("serial-b"), UID, current, 0x00C0FFEE, 5))
    add("signed by the second trusted key", sr.make_command(seed("serial-b"), UID, current, 0x00C0FFEE, 5), trusted=[0, 1])
    add("a serial changed after signing", flip(good, 15))
    add("a counter changed after signing", flip(good, 19))
    add("a signature with a bit changed", flip(good, 40))
    add("a key id with a bit changed", flip(good, 5))
    add("the serial 0 is refused", sr.make_command(seed("serial-a"), UID, current, 0, 5))
    add("the serial 0xFFFFFFFF is refused", sr.make_command(seed("serial-a"), UID, current, 0xFFFFFFFF, 5))
    add("a bootloader built without the programmable serial", good, enabled=False)
    add("an update is in progress", good, busy=True)
    add("a bootloader that trusts nobody", good, trusted=[])
    return cases


def slot_cases() -> list[dict]:
    blank = b"\xff" * 16
    a, b = sr.slot_pack(0x0A0A0A0A, 3), sr.slot_pack(0x0B0B0B0B, 7)
    no_magic = b"\xff" * 4 + sr.slot_pack(0x0D0D0D0D, 11)[4:]      # the magic is programmed last, so a cut write has none
    good_check = sr.slot_pack(0x0E0E0E0E, 13)
    bad_check = good_check[:8] + b"\x00\x00\x00\x00" + good_check[12:]
    zero = sr.slot_pack(0, 15)
    cases: list[dict] = []
    for name, x, y in (("both blank", blank, blank), ("only the first", a, blank), ("only the second", blank, b), ("the second is newer", a, b),
                       ("the first is newer", b, a), ("equal counters: the first", sr.slot_pack(0x01010101, 4), sr.slot_pack(0x02020202, 4)),
                       ("a record without a magic", no_magic, a), ("a record with a wrong complement", bad_check, a), ("the serial 0 is no record", zero, b)):
        value = sr.pick(x, y)
        cases.append({"name": name, "slot_a": x.hex().upper(), "slot_b": y.hex().upper(), "serial": f"{value[0]:08X}" if value else None,
                      "counter": value[1] if value else None})
    return cases


def hex_array(name: str, raw: bytes) -> str:
    return f"static const uint8_t {name}[] = {{{', '.join(f'0x{b:02X}' for b in raw) if raw else '0'}}};"


def c_header(commands: list[dict], slots: list[dict]) -> str:
    lines = ["// GENERATED by tools/make_bl_serial_vectors.py - do not edit by hand.", "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
             "// GPL-3.0-or-later - see LICENSE", "#ifndef BL_SERIAL_VECTORS_H", "#define BL_SERIAL_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
             "static const uint8_t BL_SERIAL_KEYS[][32] = {"]
    for k in keys():
        lines.append("    {" + ", ".join(f"0x{b:02X}" for b in k) + "},")
    lines += ["};", "", "typedef struct {", "    const char *name;", "    uint32_t uid[3];", "    uint32_t current_serial;",
              "    unsigned trusted_mask;       // bit i: BL_SERIAL_KEYS[i] is trusted", "    uint32_t stored_counter;", "    int enabled, busy;",
              "    const uint8_t *command;      // 84 bytes", "    int status;", "    uint32_t serial, counter;", "} bl_serial_command_vec_t;", ""]
    for i, c in enumerate(commands):
        lines.append(hex_array(f"bl_serial_cmd_{i}", bytes.fromhex(c["command"])))
    lines += ["", "static const bl_serial_command_vec_t BL_SERIAL_COMMAND_VECTORS[] = {"]
    for i, c in enumerate(commands):
        mask = sum(1 << t for t in c["trusted"])
        uid = ", ".join(f"0x{w}u" for w in c["uid"])
        lines.append(f"    {{\"{c['name']}\", {{{uid}}}, 0x{c['current_serial']}u, {mask}u, {c['stored_counter']}u, {int(c['enabled'])}, {int(c['busy'])}, "
                     f"bl_serial_cmd_{i}, {c['status']}, 0x{c['serial']}u, {c['counter']}u}},")
    lines += ["};", "", f"#define BL_SERIAL_COMMAND_VECTOR_COUNT {len(commands)}u", "",
              "typedef struct {", "    const char *name;", "    uint32_t slot_a[4], slot_b[4];", "    int valid;", "    uint32_t serial, counter;", "} bl_serial_slot_vec_t;", "",
              "static const bl_serial_slot_vec_t BL_SERIAL_SLOT_VECTORS[] = {"]
    for c in slots:
        a = struct.unpack("<IIII", bytes.fromhex(c["slot_a"]))
        b = struct.unpack("<IIII", bytes.fromhex(c["slot_b"]))
        valid = c["serial"] is not None
        lines.append(f"    {{\"{c['name']}\", {{{', '.join(f'0x{w:08X}u' for w in a)}}}, {{{', '.join(f'0x{w:08X}u' for w in b)}}}, {int(valid)}, "
                     f"0x{c['serial'] or '0'}u, {c['counter'] or 0}u}},")
    lines += ["};", "", f"#define BL_SERIAL_SLOT_VECTOR_COUNT {len(slots)}u", "", "#endif // BL_SERIAL_VECTORS_H", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, str]:
    commands, slots = command_cases(), slot_cases()
    doc = {"about": "Throwaway test keys only. The command is 84 bytes: target, key id, serial, counter, signature.", "public_keys": [k.hex().upper() for k in keys()],
           "statuses": list(sr.STATUS_NAMES), "commands": commands, "slots": slots}
    return {ROOT / "conformance" / "bl_serial_vectors.json": json.dumps(doc, indent=2) + "\n", ROOT / "generated" / "bl_serial_vectors.h": c_header(commands, slots)}


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
        print("BL_SERIAL_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_bl_serial_vectors.py)", file=sys.stderr)
        return 1
    print("BL_SERIAL_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
