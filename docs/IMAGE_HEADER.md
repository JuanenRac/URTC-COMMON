# The header in front of a firmware image

A 32-byte header that says what a firmware binary is before anything trusts it: the hardware it is built for, its version as four components (`major.minor.patch.build`), its length and its CRC-32. It describes an image to the tools that handle it (the tool head, the expansion slave, the tool rack and the vision head). **It is never part of the flashed image:** the binary that goes into the flash is exactly what the linker produced, with the flash map and the vector table of the unsigned build; the header is rebuilt from the file name and the binary wherever it is needed, and the signature is a separate record (`SIGNATURE_SEPARATION.md`).

All multi-byte fields are big-endian, like the bus.

| Offset | Size | Field | Meaning |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | `URIH` (`55 52 49 48`) |
| 4 | 1 | `header_version` | 1 |
| 5 | 1 | `header_size` | 32 |
| 6 | 2 | `flags` | bit 0: a 32-byte HMAC-SHA256 trailer follows the payload |
| 8 | 4 | `hardware_id` | the HardwareID the image is built for (`generated/urtc_can_ids.h`) |
| 12 | 2 | `version_major` | |
| 14 | 1 | `version_minor` | |
| 15 | 1 | `version_patch` | |
| 16 | 2 | `version_build` | the fourth component |
| 18 | 2 | reserved | 0 |
| 20 | 4 | `payload_length` | bytes after the header (the trailer is not counted) |
| 24 | 4 | `payload_crc32` | CRC-32 of the payload (zlib) |
| 28 | 4 | `header_crc32` | CRC-32 of bytes 0 to 27 |

A reader checks the magic, the header version, the size and the header CRC; for a whole image it also checks that the bytes after the header are exactly the payload (and the trailer when the signed flag is set) and that the payload has the CRC-32 the header states. Each way to fail has its own status (`short`, `bad_magic`, `bad_version`, `bad_size`, `bad_header_crc`, `bad_length`, `bad_payload_crc`).

## Signed metadata

What a release signs is the first 28 bytes of this header (hardware, version, length, CRC-32), the SHA-256 of the payload and a rollback counter, as the Ed25519 record of `SIGNATURE_SEPARATION.md` (`<image>.imgsig`, 76 bytes). The identity, the length and the CRC therefore cannot be changed without breaking the signature. The record is made by the tooling of the release on the maintainer's machine, never by the header code, and it is not appended to the image. The HMAC trailer (flag bit 0) belongs to the bootloaders of the earlier generation and is not produced for a release any more.

## Where it lives

* `firmware_base/urtc_image_header.h`: the C header (pack, parse, verify), copied into the firmware repositories with `python tools/vendor_copy.py sync TARGET --set firmware_image_header`.
* `src/urtc_common/image_header.py`: the Python reference (pack, parse, verify, sign), set `image_header`.
* `conformance/image_header_vectors.json` and `generated/image_header_vectors.h`: the shared vectors, written by `python tools/make_image_header_vectors.py` (`--check` fails when they are out of date); the C header and the reference are both held to them in `tests/`.

## Stamping a release image

`python tools/stamp_image.py stamp FILE.bin --hardware main|slave|NUMBER [--version MAJOR.MINOR.PATCH[.BUILD]]` writes `FILE.urimg`: the header followed by the unchanged binary, the same bytes every time, with the version read from the `_vX.Y.Z` part of the file name when `--version` is not given. `python tools/stamp_image.py check FILE.urimg` verifies a stamped image and says why it fails. This is a step after the build and needs no change to the linker script; the flashed layout is untouched.

## What is not done, on purpose

The flashed image does not carry the header, and this will not change: putting a header in front of the code would move the vector table and change the flash map of every firmware and every bootloader, and could leave a board unable to start. The header and the signature are described to the tools and travel in the frames of the update (`0x7EC` for the tool head, `0x21A` for the expansion slave). `stamp_image.py` writes a `.urimg` file for tools that want the header and the binary in one file; that file is never flashed. The version frame on the bus (`0x7F9`) still carries three components; a frame with the fourth is a change of the specification and of the bootloaders.
