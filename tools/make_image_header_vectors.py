#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_image_header_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the firmware image header and the C table the firmware repositories check their copy against.

* ``conformance/image_header_vectors.json``  images (hex) with the version they carry, the status a reader must give and, for a good one, the fields it reads
* ``generated/image_header_vectors.h``       the same cases as C tables (a firmware repository compiles them into a host test of ``urtc_image_header.h``)

The cases come from the reference in ``urtc_common.image_header``: well-formed images (unsigned and signed, empty and with a payload, the largest values of
every field) and images each broken in one way (a short buffer, the magic, the version, the size, a flipped bit of the header, a payload that is longer or
shorter than the header says, a flipped bit of the payload, a missing signature trailer). ``--check`` writes nothing and fails when a file differs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import image_header as ih  # noqa: E402

JSON_OUT = ROOT / "conformance" / "image_header_vectors.json"
HEADER_OUT = ROOT / "generated" / "image_header_vectors.h"
HARDWARE_MAIN = 0x0303CC01
HARDWARE_SLAVE = 0x0303CB01
DEV_KEY = bytes(range(32))   # a key for the vectors only: it signs nothing but test images


def _payload(length: int) -> bytes:
    return bytes((i * 13 + 5) & 0xFF for i in range(length))


def cases() -> list[dict]:
    good = ih.build_image(_payload(100), HARDWARE_MAIN, (0, 8, 1, 3))
    signed = ih.build_image(_payload(64), HARDWARE_SLAVE, (1, 2, 3, 4), key=DEV_KEY)
    empty = ih.build_image(b"", HARDWARE_MAIN, (0, 0, 0, 0))
    largest = ih.build_image(_payload(8), 0xFFFFFFFF, (0xFFFF, 0xFF, 0xFF, 0xFFFF))

    def flip(image: bytes, index: int, mask: int = 0x01) -> bytes:
        out = bytearray(image)
        out[index] ^= mask
        return bytes(out)

    def with_header(image: bytes, **fields) -> bytes:
        status, info = ih.parse_header(image)
        assert info is not None, status
        values = {**info.__dict__, **fields}
        return ih.pack_header(ih.ImageInfo(**values)) + image[ih.HEADER_SIZE:]

    raw = [
        ("an image with a payload", good),
        ("an empty payload", empty),
        ("the largest value of every field", largest),
        ("a signed image carries its trailer", signed),
        ("fewer bytes than a header", good[:31]),
        ("no bytes at all", b""),
        ("the magic is wrong", flip(good, 0)),
        ("a header version this reader does not know", flip(good, 4, 0x02)),
        ("a header that does not say it is 32 bytes", flip(good, 5, 0x10)),
        ("a flipped bit in the hardware id", flip(good, 9)),
        ("a flipped bit in the version", flip(good, 15)),
        ("a flipped bit in the header CRC", flip(good, 31)),
        ("a payload one byte shorter than the header says", good[:-1]),
        ("a payload one byte longer than the header says", good + b"\x00"),
        ("a flipped bit in the payload", flip(good, 50)),
        ("a signed image without its trailer", signed[:-ih.SIGNATURE_SIZE]),
        ("a trailer on an image that is not signed", good + bytes(ih.SIGNATURE_SIZE)),
        ("a payload length that cannot fit in the bytes given", with_header(good, payload_length=0xFFFFFFFF)),
    ]
    out = []
    for name, image in raw:
        status, info = ih.verify_image(image)
        entry: dict = {"name": name, "image": image.hex().upper(), "status": ih.STATUS_NAMES[status], "status_code": status}
        if info is not None:
            entry["info"] = {"hardware_id": info.hardware_id, "version": list(info.version), "flags": info.flags, "payload_length": info.payload_length,
                             "payload_crc32": info.payload_crc32}
            entry["header"] = image[:ih.HEADER_SIZE].hex().upper()
            entry["signature_ok"] = ih.sign(DEV_KEY, image[:ih.HEADER_SIZE], image[ih.HEADER_SIZE:ih.HEADER_SIZE + info.payload_length]) == image[ih.HEADER_SIZE + info.payload_length:] if info.signed else None
        out.append(entry)
    return out


def vectors() -> dict:
    return {"format": 1, "about": "The header in front of a firmware image (32 bytes, big-endian): what a reader must accept, with the fields it reads, and what it must refuse, with the reason.",
            "header_size": ih.HEADER_SIZE, "magic": f"0x{ih.MAGIC:08X}", "statuses": list(ih.STATUS_NAMES), "signing_key_for_the_vectors": DEV_KEY.hex().upper(), "cases": cases()}


def c_header(data: dict) -> str:
    lines = [
        "// GENERATED from spec by tools/make_image_header_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef IMAGE_HEADER_VECTORS_H", "#define IMAGE_HEADER_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
        "typedef struct {",
        "    const char *name;",
        "    const uint8_t *image;",
        "    size_t length;",
        "    int status;                    // urtc_image_status_t",
        "    int has_info;                  // 1 when the image is good and the fields below are what a reader must read",
        "    uint32_t hardware_id;",
        "    uint16_t major;",
        "    uint8_t minor, patch;",
        "    uint16_t build, flags;",
        "    uint32_t payload_length, payload_crc32;",
        "} image_header_vec_t;", "",
    ]
    for index, case in enumerate(data["cases"]):
        raw = bytes.fromhex(case["image"])
        body = ", ".join(f"0x{b:02X}" for b in raw) if raw else "0"
        lines.append(f"static const uint8_t image_header_image_{index}[] = {{{body}}};")
    lines += ["", "static const image_header_vec_t IMAGE_HEADER_VECTORS[] = {"]
    for index, case in enumerate(data["cases"]):
        info = case.get("info")
        length = len(case["image"]) // 2
        if info:
            m, mi, p, b = info["version"]
            fields = f"1, 0x{info['hardware_id']:08X}u, {m}u, {mi}u, {p}u, {b}u, {info['flags']}u, {info['payload_length']}u, 0x{info['payload_crc32']:08X}u"
        else:
            fields = "0, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u"
        lines.append(f"    {{\"{case['name']}\", image_header_image_{index}, {length}u, {case['status_code']}, {fields}}},")
    lines += ["};", "", f"#define IMAGE_HEADER_VECTOR_COUNT {len(data['cases'])}u", "", "#endif // IMAGE_HEADER_VECTORS_H", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, str]:
    data = vectors()
    return {JSON_OUT: json.dumps(data, indent=2) + "\n", HEADER_OUT: c_header(data)}


def shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


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
        print("IMAGE_HEADER_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_image_header_vectors.py)", file=sys.stderr)
        return 1
    print("IMAGE_HEADER_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
