#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/stamp_image.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Put the 32-byte image header (docs/IMAGE_HEADER.md) in front of a firmware binary, or check a stamped image.

    python tools/stamp_image.py stamp URTC_MAIN_FIRMWARE_v0.8.1.3.bin --hardware main
    python tools/stamp_image.py stamp app.bin --hardware 0x303CB01 --version 0.8.1.3 --out app.urimg
    python tools/stamp_image.py check URTC_MAIN_FIRMWARE_v0.8.1.3.urimg

``stamp`` writes ``<name>.urimg`` next to the binary (or ``--out``): the header followed by the bytes of the binary, so
the identity, the version, the length and the CRC-32 travel with the file. The binary itself is not changed, which makes
this a step after the build, with no change to the linker script. The version is read from ``--version`` or from the
``_vMAJOR.MINOR.PATCH[.BUILD]`` part of the file name. ``--hardware`` is ``main``, ``slave`` or a number (the
HardwareID of generated/urtc_can_ids.h). The same bytes come out every time. ``check`` exits 1 with the reason when the
image is not whole.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import image_header as ih  # noqa: E402

HARDWARE = {"main": 0x0303CC01, "slave": 0x0303CB01}
VERSION_IN_NAME = re.compile(r"_v(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(text: str) -> tuple[int, int, int, int]:
    parts = text.split(".")
    if not 3 <= len(parts) <= 4 or not all(part.isdigit() for part in parts):
        raise ValueError(f"version '{text}' is not MAJOR.MINOR.PATCH[.BUILD]")
    numbers = [int(part) for part in parts] + [0] * (4 - len(parts))
    if numbers[0] > 0xFFFF or numbers[1] > 0xFF or numbers[2] > 0xFF or numbers[3] > 0xFFFF:
        raise ValueError(f"version '{text}' does not fit the fields of the header")
    return numbers[0], numbers[1], numbers[2], numbers[3]


def parse_hardware(text: str) -> int:
    if text in HARDWARE:
        return HARDWARE[text]
    try:
        value = int(text, 0)
    except ValueError:
        raise ValueError(f"hardware '{text}' is not main, slave or a number") from None
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"hardware '{text}' does not fit 32 bits")
    return value


def stamp(binary: Path, hardware: int, version: tuple[int, int, int, int], out: Path) -> ih.ImageInfo:
    image = ih.build_image(binary.read_bytes(), hardware, version)
    status, info = ih.verify_image(image)
    if status != ih.OK or info is None:
        raise ValueError("the stamped image does not verify: " + ih.STATUS_NAMES[status])
    out.write_bytes(image)
    return info


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("stamp")
    one.add_argument("binary", type=Path)
    one.add_argument("--hardware", required=True)
    one.add_argument("--version")
    one.add_argument("--out", type=Path)
    two = sub.add_parser("check")
    two.add_argument("image", type=Path)
    args = parser.parse_args(argv)

    if args.command == "check":
        status, info = ih.verify_image(args.image.read_bytes())
        if status != ih.OK or info is None:
            print(f"STAMP_IMAGE=FAIL {args.image.name}: {ih.STATUS_NAMES[status]}")
            return 1
        print(f"STAMP_IMAGE=PASS {args.image.name} hardware=0x{info.hardware_id:08X} version={info.version_text()} length={info.payload_length}")
        return 0

    try:
        hardware = parse_hardware(args.hardware)
        if args.version:
            version = parse_version(args.version)
        else:
            found = VERSION_IN_NAME.search(args.binary.name)
            if found is None:
                raise ValueError("no --version and no _vMAJOR.MINOR.PATCH in the file name")
            version = parse_version(".".join(part for part in found.groups() if part is not None))
        out = args.out or args.binary.with_suffix(".urimg")
        info = stamp(args.binary, hardware, version, out)
    except (ValueError, OSError) as error:
        print(f"STAMP_IMAGE=FAIL {error}")
        return 1
    print(f"STAMP_IMAGE=WROTE {out.name} hardware=0x{info.hardware_id:08X} version={info.version_text()} length={info.payload_length}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
