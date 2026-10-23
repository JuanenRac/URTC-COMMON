#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/vendor_copy.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Copy parts of URTC-COMMON into another repository, and keep the copies honest.

The other repositories do not depend on URTC-COMMON at run time: the tools are packaged with PyInstaller, the
web app is static and the firmware is built on its own. They carry a COPY, and this tool is what makes a copy
safe to carry:

    python tools/vendor_copy.py sync  TARGET --set python --set vectors   # copy, write the lock file
    python tools/vendor_copy.py status TARGET                              # what is there and what it is based on
    python tools/vendor_copy.py check  TARGET [--source PATH | --lock-only]

``sync`` copies the files of the chosen sets into TARGET (with LF endings) and writes ``urtc_common.lock.json``
there: the version of URTC-COMMON and the SHA-256 of every file. ``check`` fails when

* a copied file no longer matches the lock (somebody edited a generated file by hand), or
* with a checkout of URTC-COMMON at hand (``--source``, or the checkout this script lives in), a copied file
  differs from the current one (the copy fell behind).

``--as NAME`` gives a single copied file another name (a repository that already keeps the vectors under an
older file name). ``--lock-only`` checks only the first, for a repository that has no checkout of URTC-COMMON beside it.
Nothing here is ever imported by the code that ships: it is a development tool, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK_NAME = "urtc_common.lock.json"
SETS = {
    "python": [
        "src/urtc_common/__init__.py", "src/urtc_common/protocol.py", "src/urtc_common/framing.py", "src/urtc_common/slcan.py",
        "src/urtc_common/transports.py", "src/urtc_common/versioning.py", "src/urtc_common/quick_state.py", "src/urtc_common/conformance.py",
    ],
    "typescript": ["generated/urtcCanIds.ts"],
    "c": ["generated/urtc_can_ids.h"],
    "vectors": ["conformance/can_vectors.json"],
    "ui": [
        "src/urtc_ui/__init__.py", "src/urtc_ui/languages.py", "src/urtc_ui/status.py", "src/urtc_ui/formatting.py",
    ],
    "tool": ["tools/vendor_copy.py"],
    "tools_catalog": ["src/urtc_common/tools_catalog.py"],
    "tools_ts": ["generated/urtcTools.ts"],
    "blackbox": ["src/urtc_common/blackbox.py", "conformance/blackbox_vectors.json"],
    "rack": ["src/urtc_common/rack_sim.py", "src/urtc_common/rack_status.py", "conformance/rack_vectors.json"],
    "thermal": ["src/urtc_common/thermal_view.py", "conformance/thermal_vectors.json"],
    "rack_c": ["generated/rack_vectors.h"],
    "fuzz": ["src/urtc_common/fuzz.py", "conformance/fuzz_corpus.txt"],
    "virtual_board": ["src/urtc_common/virtual_board.py"],
    "update": ["src/urtc_common/self_update.py", "src/urtc_common/update_service.py", "src/urtc_common/update_controller.py", "src/urtc_common/launcher.py"],
    "update_qt": ["src/urtc_common/update_qt.py", "src/urtc_common/update_strings.py"],
    "update_qml": ["qml/UpdateDialog.qml"],
    "package_tool": ["tools/make_update_package.py"],
    "sensor": ["src/urtc_common/sensor_frame.py", "conformance/sensor_vectors.json"],
    "sensor_c": ["generated/sensor_vectors.h"],
    "compat": ["docs/COMPATIBILITY.md"],
    "firmware_base": ["firmware_base/urtc_crc8.h"],
    "firmware_test": ["firmware_base/urtc_test.h"],
    "fw_vectors": ["generated/urtc_fw_vectors.h"],
}


def normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def digest(data: bytes) -> str:
    return hashlib.sha256(normalized(data)).hexdigest()


def common_version(source: Path) -> str:
    text = (source / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def find_source(explicit: str | None) -> Path | None:
    for candidate in ([Path(explicit)] if explicit else [HERE.parent]):
        if (candidate / "spec" / "can_protocol.json").is_file():
            return candidate.resolve()
    return None


def read_lock(target: Path) -> dict | None:
    path = target / LOCK_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def target_name(relative: str) -> str:
    """The file keeps its own name inside the target (the package files are not nested)."""
    return Path(relative).name


def sync(source: Path, target: Path, sets: list[str], only: list[str] | None, rename: str | None = None) -> int:
    relatives: list[str] = []
    for name in sets:
        relatives += SETS[name]
    if only:
        relatives = [r for r in relatives if target_name(r) in only]
    if not relatives:
        print("VENDOR=FAIL nothing selected", file=sys.stderr)
        return 1
    if rename is not None and len(relatives) != 1:
        print("VENDOR=FAIL --as needs exactly one file selected", file=sys.stderr)
        return 1
    previous = read_lock(target) or {"files": {}}
    files = dict(previous.get("files", {}))
    target.mkdir(parents=True, exist_ok=True)
    for relative in relatives:
        data = normalized((source / relative).read_bytes())
        name = rename or target_name(relative)
        (target / name).write_bytes(data)
        files[name] = {"from": relative, "sha256": digest(data)}
        print(f"copied {relative} -> {name}")
    lock = {"format": 1, "urtc_common_version": common_version(source), "files": dict(sorted(files.items()))}
    (target / LOCK_NAME).write_bytes((json.dumps(lock, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {LOCK_NAME} (urtc-common {lock['urtc_common_version']}, {len(files)} files)")
    return 0


def problems(target: Path, source: Path | None) -> list[str]:
    lock = read_lock(target)
    if lock is None:
        return [f"{target}: no {LOCK_NAME}: this folder was not written by vendor_copy.py sync"]
    found: list[str] = []
    for name, entry in lock["files"].items():
        path = target / name
        if not path.is_file():
            found.append(f"{name}: listed in the lock but missing")
            continue
        if digest(path.read_bytes()) != entry["sha256"]:
            found.append(f"{name}: edited by hand (it no longer matches the lock); regenerate it with sync, never edit it")
            continue
        if source is not None:
            origin = source / entry["from"]
            if not origin.is_file():
                found.append(f"{name}: {entry['from']} no longer exists in URTC-COMMON")
            elif digest(origin.read_bytes()) != entry["sha256"]:
                found.append(f"{name}: behind URTC-COMMON {common_version(source)} (it was copied from {lock['urtc_common_version']}); run sync again")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sync", "status", "check"):
        command = sub.add_parser(name)
        command.add_argument("target", help="the folder inside the other repository that holds the copy")
        command.add_argument("--source", help="a checkout of URTC-COMMON (default: the one this script is in)")
        if name == "sync":
            command.add_argument("--set", dest="sets", action="append", choices=sorted(SETS), required=True)
            command.add_argument("--only", action="append", help="copy only the files with these names")
            command.add_argument("--as", dest="rename", help="the name of the copy, when exactly one file is selected (for a copy that keeps an older name)")
        if name == "check":
            command.add_argument("--lock-only", action="store_true", help="compare with the lock file only")
    args = parser.parse_args(argv)
    target = Path(args.target)
    source = find_source(args.source)
    if args.command == "sync":
        if source is None:
            print("VENDOR=FAIL no checkout of URTC-COMMON found (use --source)", file=sys.stderr)
            return 1
        return sync(source, target, args.sets, args.only, args.rename)
    if args.command == "status":
        lock = read_lock(target)
        if lock is None:
            print(f"{target}: no lock file")
            return 1
        print(f"{target}: copied from urtc-common {lock['urtc_common_version']}")
        for line in problems(target, source) or ["every file matches the lock" + (" and the checkout" if source else "")]:
            print(f"  {line}")
        return 0
    found = problems(target, None if args.lock_only else source)
    if args.lock_only is False and source is None:
        print("VENDOR_CHECK=FAIL no checkout of URTC-COMMON to compare with (use --source or --lock-only)", file=sys.stderr)
        return 1
    if found:
        print("\n".join(found), file=sys.stderr)
        print(f"VENDOR_CHECK=FAIL {len(found)} problem(s)", file=sys.stderr)
        return 1
    print("VENDOR_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
