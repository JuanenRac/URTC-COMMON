#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_image_header_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the firmware image header and the C table the firmware repositories check their copy against.

* ``conformance/image_header_vectors.json``  images (hex) with the version they carry, the status a reader must give and, for a good one, the fields it reads
* ``generated/image_header_vectors.h``       the same cases as C tables (a firmware repository compiles them into a host test of ``urtc_image_header.h``)
* ``conformance/image_header_embedded_vectors.json`` and ``generated/image_header_embedded_vectors.h``  the same for the EMBEDDED form (the header inside the
  flashed binary at a fixed offset) and, in the JSON, the cases of ``inspect_image`` (what a consumer decides for each switch value)

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
EMBEDDED_JSON_OUT = ROOT / "conformance" / "image_header_embedded_vectors.json"
EMBEDDED_HEADER_OUT = ROOT / "generated" / "image_header_embedded_vectors.h"
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


def _binary(length: int, seed: int = 7) -> bytes:
    """A stand-in for a linked binary: bytes that are not the magic anywhere."""
    return bytes((i * 31 + seed) & 0x7F for i in range(length))


def _slot_image(length: int, hardware_id: int, version: tuple[int, int, int, int], seed: int = 7) -> bytes:
    raw = bytearray(_binary(length, seed))
    raw[ih.EMBED_OFFSET:ih.EMBED_OFFSET + ih.HEADER_SIZE] = ih.embedded_slot(hardware_id, version)
    return bytes(raw)


def embedded_cases() -> list[dict]:
    good = ih.seal_embedded(_slot_image(768, HARDWARE_MAIN, (0, 8, 1, 3)))
    slave = ih.seal_embedded(_slot_image(1024, HARDWARE_SLAVE, (1, 2, 3, 4), 11))
    smallest = ih.seal_embedded(_slot_image(ih.EMBED_OFFSET + ih.HEADER_SIZE, HARDWARE_MAIN, (0, 0, 0, 0)))
    largest = ih.seal_embedded(_slot_image(800, 0xFFFFFFFF, (0xFFFF, 0xFF, 0xFF, 0xFFFF)))
    unsealed = _slot_image(768, HARDWARE_MAIN, (0, 8, 1, 3))

    def flip(image: bytes, index: int, mask: int = 0x01) -> bytes:
        out = bytearray(image)
        out[index] ^= mask
        return bytes(out)

    def with_header(image: bytes, **fields) -> bytes:
        status, info = ih.parse_header(image[ih.EMBED_OFFSET:])
        assert info is not None, status
        values = {**info.__dict__, **fields}
        return image[:ih.EMBED_OFFSET] + ih.pack_header(ih.ImageInfo(**values)) + image[ih.EMBED_OFFSET + ih.HEADER_SIZE:]

    at = ih.EMBED_OFFSET
    raw = [
        ("a sealed image", good),
        ("a sealed image of the expansion slave", slave),
        ("an image that is only the offset and the header", smallest),
        ("the largest value of every field", largest),
        ("the slot the firmware emitted, never sealed", unsealed),
        ("one byte fewer than the header needs", good[:at + ih.HEADER_SIZE - 1]),
        ("no bytes at all", b""),
        ("the magic is wrong", flip(good, at)),
        ("a header version this reader does not know", flip(good, at + 4, 0x02)),
        ("a header that does not say it is 32 bytes", flip(good, at + 5, 0x10)),
        ("a flipped bit in the hardware id", flip(good, at + 9)),
        ("a flipped bit in the version", flip(good, at + 15)),
        ("a flipped bit in the header CRC", flip(good, at + 31)),
        ("a header that does not say it is embedded", with_header(good, flags=0)),
        ("an embedded header that also claims a signature trailer", with_header(good, flags=ih.FLAG_EMBEDDED | ih.FLAG_SIGNED)),
        ("an image one byte shorter than the header says", good[:-1]),
        ("an image one byte longer than the header says", good + b"\x00"),
        ("a flipped bit in the code", flip(good, 600)),
        ("a flipped bit in the vector table", flip(good, 4)),
        ("a header that states a length the image cannot have", with_header(good, payload_length=0xFFFFFFFF)),
        ("a binary with no header slot at all", _binary(768)),
    ]
    out = []
    for name, image in raw:
        status, info = ih.verify_embedded(image)
        entry: dict = {"name": name, "image": image.hex().upper(), "status": ih.STATUS_NAMES[status], "status_code": status}
        if info is not None:
            entry["info"] = {"hardware_id": info.hardware_id, "version": list(info.version), "flags": info.flags, "payload_length": info.payload_length,
                             "payload_crc32": info.payload_crc32}
        out.append(entry)
    return out


def policy_cases() -> list[dict]:
    """What ``inspect_image`` decides: a consumer in any language must give the same accepted/kind/reason for the same bytes and the same switch."""
    base = {c["name"]: bytes.fromhex(c["image"]) for c in embedded_cases()}
    good = base["a sealed image"]
    flat = ih.build_image(_binary(300), HARDWARE_MAIN, (0, 8, 1, 3))
    legacy = _binary(768)
    spec = [
        ("a sealed image under warn", good, "warn", None, None),
        ("a sealed image under accept", good, "accept", None, None),
        ("a sealed image under require", good, "require", None, None),
        ("a sealed image for the hardware and version that are asked for", good, "require", HARDWARE_MAIN, (0, 8, 1, 3)),
        ("a sealed image for another hardware", good, "warn", HARDWARE_SLAVE, None),
        ("a sealed image of another version", good, "warn", None, (0, 8, 1, 4)),
        ("a version given with three parts is compared with the first three", good, "warn", None, (0, 8, 1)),
        ("a version given with three parts that differs", good, "warn", None, (0, 8, 2)),
        ("a corrupted sealed image is refused even under accept", base["a flipped bit in the code"], "accept", None, None),
        ("a never sealed slot is refused even under accept", base["the slot the firmware emitted, never sealed"], "accept", None, None),
        ("a binary without a header under warn is accepted with a warning", legacy, "warn", None, None),
        ("a binary without a header under accept", legacy, "accept", None, None),
        ("a binary without a header under require is refused", legacy, "require", None, None),
        ("an unknown switch value is the strictest", legacy, "sometimes", None, None),
        ("an empty switch value is the default", legacy, "", None, None),
        ("a stamped file (header in front) is never flashed", flat, "accept", None, None),
        ("an empty file under warn", b"", "warn", None, None),
    ]
    out = []
    for name, image, policy, hardware, version in spec:
        check = ih.inspect_image(image, policy, hardware, version)
        out.append({"name": name, "image": image.hex().upper(), "policy": policy, "hardware_id": hardware, "version": list(version) if version else None,
                    "accepted": check.accepted, "kind": check.kind, "reason": check.reason, "warn": check.warn})
    return out


def embedded_vectors() -> dict:
    return {"format": 1, "about": "The header INSIDE a flashed binary (32 bytes, big-endian, at a fixed offset): what a reader must accept, with the fields it reads, what it must refuse, "
                                  "with the reason, and what a consumer decides for each value of the compatibility switch (accept, warn, require).",
            "embed_offset": ih.EMBED_OFFSET, "header_size": ih.HEADER_SIZE, "flag_embedded": ih.FLAG_EMBEDDED, "statuses": list(ih.STATUS_NAMES),
            "policies": list(ih.POLICIES), "default_policy": ih.DEFAULT_POLICY, "cases": embedded_cases(), "policy_cases": policy_cases()}


def c_embedded_header(data: dict) -> str:
    lines = [
        "// GENERATED from spec by tools/make_image_header_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef IMAGE_HEADER_EMBEDDED_VECTORS_H", "#define IMAGE_HEADER_EMBEDDED_VECTORS_H", "", "#include <stddef.h>", "#include <stdint.h>", "",
        "typedef struct {",
        "    const char *name;",
        "    const uint8_t *image;",
        "    size_t length;",
        "    int status;                    // urtc_image_status_t of urtc_image_verify_embedded",
        "    int has_info;                  // 1 when the image is good and the fields below are what a reader must read",
        "    uint32_t hardware_id;",
        "    uint16_t major;",
        "    uint8_t minor, patch;",
        "    uint16_t build, flags;",
        "    uint32_t payload_length, payload_crc32;",
        "} image_header_embedded_vec_t;", "",
    ]
    for index, case in enumerate(data["cases"]):
        raw = bytes.fromhex(case["image"])
        body = ", ".join(f"0x{b:02X}" for b in raw) if raw else "0"
        lines.append(f"static const uint8_t image_header_embedded_image_{index}[] = {{{body}}};")
    lines += ["", "static const image_header_embedded_vec_t IMAGE_HEADER_EMBEDDED_VECTORS[] = {"]
    for index, case in enumerate(data["cases"]):
        info = case.get("info")
        length = len(case["image"]) // 2
        if info:
            m, mi, p, b = info["version"]
            fields = f"1, 0x{info['hardware_id']:08X}u, {m}u, {mi}u, {p}u, {b}u, {info['flags']}u, {info['payload_length']}u, 0x{info['payload_crc32']:08X}u"
        else:
            fields = "0, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u"
        lines.append(f"    {{\"{case['name']}\", image_header_embedded_image_{index}, {length}u, {case['status_code']}, {fields}}},")
    lines += ["};", "", f"#define IMAGE_HEADER_EMBEDDED_VECTOR_COUNT {len(data['cases'])}u", "", "#endif // IMAGE_HEADER_EMBEDDED_VECTORS_H", ""]
    return "\n".join(lines)


def outputs() -> dict[Path, str]:
    data = vectors()
    embedded = embedded_vectors()
    return {JSON_OUT: json.dumps(data, indent=2) + "\n", HEADER_OUT: c_header(data),
            EMBEDDED_JSON_OUT: json.dumps(embedded, indent=2) + "\n", EMBEDDED_HEADER_OUT: c_embedded_header(embedded)}


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
