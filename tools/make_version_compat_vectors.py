#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_version_compat_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the signed command that changes the version rule for an image without a patch, and the C table the firmware checks itself against.

* ``conformance/version_compat_vectors.json``   the decision on a command (valid, other head, other key, altered, replay, older counter, busy...) and the
  reading of the record that keeps the setting
* ``generated/version_compat_vectors.h``        the same as C tables

Every key here is a throwaway TEST key: it signs nothing but these vectors and is no secret. A release key is never in this repository.
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
from urtc_common import bl_serial as sr  # noqa: E402
from urtc_common import ed25519  # noqa: E402
from urtc_common import version_compat as vc  # noqa: E402

UID = (0x12345678, 0x9ABCDEF0, 0x0F1E2D3C)
OTHER_UID = (0x12345678, 0x9ABCDEF0, 0x0F1E2D3D)
DEV_SEED = hashlib.sha256(b"urtc public development image key v1").digest()   # the public development key that a "dev" bootloader trusts: no secret


def seed(label: str) -> bytes:
    """The first key is the public development key, so that the host suites of the bootloader (which trusts it) can replay the commands."""
    if label == "compat-a":
        return DEV_SEED
    return hashlib.sha256(b"urtc throwaway test key " + label.encode()).digest()


def keys() -> list[bytes]:
    return [ed25519.public_key(seed("compat-a")), ed25519.public_key(seed("compat-b"))]


def flip(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 1]) + data[index + 1:]


def command_cases() -> list[dict]:
    current = bs.serial_from_uid(*UID)
    lenient = vc.make_command(seed("compat-a"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 5)
    cases: list[dict] = []

    def add(name: str, command: bytes, **kw) -> None:
        c = {"uid": UID, "current_serial": current, "trusted": [0], "stored_counter": 4, "enabled": True, "busy": False}
        c.update(kw)
        status, mode, counter = vc.decide(command, c["uid"], c["current_serial"], [keys()[i] for i in c["trusted"]], c["stored_counter"], c["enabled"], c["busy"])
        cases.append({"name": name, "uid": [f"{w:08X}" for w in c["uid"]], "current_serial": f"{c['current_serial']:08X}", "trusted": c["trusted"],
                      "stored_counter": c["stored_counter"], "enabled": c["enabled"], "busy": c["busy"], "command": command.hex().upper(), "status": status,
                      "status_name": vc.STATUS_NAMES[status], "mode": mode, "counter": counter})

    add("a valid command that accepts an image without a patch", lenient)
    add("a valid command back to the strict rule", vc.make_command(seed("compat-a"), UID, current, vc.MODE_STRICT, 6), stored_counter=5)
    add("the first command of a board with nothing stored", vc.make_command(seed("compat-a"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 1), stored_counter=0)
    add("the same command again is a replay", lenient, stored_counter=5)
    add("a command older than the stored one is a replay", lenient, stored_counter=9)
    add("the counter 0 is never accepted", vc.make_command(seed("compat-a"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 0), stored_counter=0)
    add("a command made for another head fails", vc.make_command(seed("compat-a"), OTHER_UID, current, vc.MODE_ACCEPT_PATCHLESS, 5))
    add("the same command on another head is not for it", lenient, uid=OTHER_UID, current_serial=bs.serial_from_uid(*OTHER_UID))
    add("signed by a key the bootloader does not trust", vc.make_command(seed("compat-b"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 5))
    add("signed by the second trusted key", vc.make_command(seed("compat-b"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 5), trusted=[0, 1])
    add("a mode changed after signing", flip(lenient, 15))
    add("a counter changed after signing", flip(lenient, 19))
    add("a signature with a bit changed", flip(lenient, 40))
    add("a key id with a bit changed", flip(lenient, 5))
    add("the mode 0 is not a mode", vc.make_command(seed("compat-a"), UID, current, 0, 5))
    add("the mode 3 is not a mode", vc.make_command(seed("compat-a"), UID, current, 3, 5))
    serial_command = sr.make_command(seed("compat-a"), UID, current, vc.MODE_ACCEPT_PATCHLESS, 5)
    add("a signed serial command is not a command of this kind", serial_command)
    add("a bootloader built without the feature", lenient, enabled=False)
    add("an update is in progress", lenient, busy=True)
    add("a bootloader that trusts nobody", lenient, trusted=[])
    return cases


def record_cases() -> list[dict]:
    good = vc.record_pack(vc.MODE_ACCEPT_PATCHLESS, 7)
    cases: list[dict] = []
    for name, record in (("blank flash", b"\xff" * 16), ("zeros", bytes(16)), ("accept stored", good), ("strict stored", vc.record_pack(vc.MODE_STRICT, 8)),
                         ("a mode that does not exist", vc.record_pack(9, 3)), ("the mode 0", vc.record_pack(0, 3)), ("a wrong CRC", flip(good, 12)),
                         ("a mode changed in flash", flip(good, 4)), ("a counter changed in flash", flip(good, 8)), ("no magic", flip(good, 0)),
                         ("a write cut before the CRC", good[:12] + b"\xff" * 4)):
        value = vc.record_read(record)
        cases.append({"name": name, "record": record.hex().upper(), "valid": value is not None, "mode": value[0] if value else 0,
                      "counter": value[1] if value else 0})
    return cases


def hex_array(name: str, raw: bytes) -> str:
    return f"static const uint8_t {name}[] = {{{', '.join(f'0x{b:02X}' for b in raw)}}};"


def c_header(commands: list[dict], records: list[dict]) -> str:
    lines = ["// GENERATED by tools/make_version_compat_vectors.py - do not edit by hand.",
             "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>", "// GPL-3.0-or-later - see LICENSE",
             "#ifndef VERSION_COMPAT_VECTORS_H", "#define VERSION_COMPAT_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
             "static const uint8_t VERSION_COMPAT_KEYS[][32] = {"]
    for k in keys():
        lines.append("    {" + ", ".join(f"0x{b:02X}" for b in k) + "},")
    lines += ["};", "", "typedef struct {", "    const char *name;", "    uint32_t uid[3];", "    uint32_t current_serial;",
              "    unsigned trusted_mask;       // bit i: VERSION_COMPAT_KEYS[i] is trusted", "    uint32_t stored_counter;", "    int enabled, busy;",
              "    const uint8_t *command;      // 84 bytes", "    int status;", "    uint32_t mode, counter;", "} version_compat_command_vec_t;", ""]
    for i, c in enumerate(commands):
        lines.append(hex_array(f"version_compat_cmd_{i}", bytes.fromhex(c["command"])))
    lines += ["", "static const version_compat_command_vec_t VERSION_COMPAT_COMMAND_VECTORS[] = {"]
    for i, c in enumerate(commands):
        mask = sum(1 << t for t in c["trusted"])
        uid = ", ".join(f"0x{w}u" for w in c["uid"])
        lines.append(f"    {{\"{c['name']}\", {{{uid}}}, 0x{c['current_serial']}u, {mask}u, {c['stored_counter']}u, {int(c['enabled'])}, {int(c['busy'])}, "
                     f"version_compat_cmd_{i}, {c['status']}, {c['mode']}u, {c['counter']}u}},")
    lines += ["};", "", f"#define VERSION_COMPAT_COMMAND_VECTOR_COUNT {len(commands)}u", "",
              "typedef struct {", "    const char *name;", "    uint8_t record[16];", "    int valid;", "    uint32_t mode, counter;", "} version_compat_record_vec_t;", "",
              "static const version_compat_record_vec_t VERSION_COMPAT_RECORD_VECTORS[] = {"]
    for c in records:
        raw = ", ".join(f"0x{b:02X}" for b in bytes.fromhex(c["record"]))
        lines.append(f"    {{\"{c['name']}\", {{{raw}}}, {int(c['valid'])}, {c['mode']}u, {c['counter']}u}},")
    lines += ["};", "", f"#define VERSION_COMPAT_RECORD_VECTOR_COUNT {len(records)}u", "", "#endif // VERSION_COMPAT_VECTORS_H", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, str]:
    commands, records = command_cases(), record_cases()
    doc = {"about": "Throwaway test keys only. The command is 84 bytes: target, key id, mode, counter, signature.", "public_keys": [k.hex().upper() for k in keys()],
           "statuses": list(vc.STATUS_NAMES), "commands": commands, "records": records}
    return {ROOT / "conformance" / "version_compat_vectors.json": json.dumps(doc, indent=2) + "\n",
            ROOT / "generated" / "version_compat_vectors.h": c_header(commands, records)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None
        if current != text:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("VERSION_COMPAT_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_version_compat_vectors.py)", file=sys.stderr)
        return 1
    print("VERSION_COMPAT_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
