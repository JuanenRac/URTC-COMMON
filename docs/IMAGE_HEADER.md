# The header in front of a firmware image

A 32-byte header that says what a firmware binary is before anything trusts it: the hardware it is built for, its version as four components (`major.minor.patch.build`), its length and its CRC-32. It describes an image to the tools that handle it (the tool head, the expansion slave, the tool rack and the vision head). It has two forms. The *flat* form (a `.urimg` file) puts it in front of a binary and is never flashed. The *embedded* form puts it INSIDE the flashed binary at a fixed offset, so the image that reaches the flash carries its own identity, length and CRC-32 while the flash map and the vector table stay where the linker put them (see "The header inside the image"). The signature is a separate record in both (`SIGNATURE_SEPARATION.md`).

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

## The header inside the image

The firmware emits the header as a 32-byte *slot* in its own linker section, at the fixed offset `EMBED_OFFSET` = `0x200` of the image: after the vector table (the STM32F303 table is `0x188` bytes, and the linker script asserts that it ends before the offset) and below the first code. Nothing moves: the vector table stays at the start of the image, the flash map is the same and the image is the same length as before.

* Flag bit 1 (`0x0002`, `FLAG_EMBEDDED`) says the header is inside the image. It cannot be combined with the HMAC trailer (bit 0).
* `payload_length` is the length of the **whole image** and `payload_crc32` is the CRC-32 of the whole image **with the 32 bytes of the header taken as zeros**, so the header can be filled in after the link.
* The firmware writes the slot at compile time with `URTC_IMAGE_EMBED_SLOT(hardware, major, minor, patch, build)`: magic, flags, hardware id and the four version components it already knows; length, CRC-32 and header CRC are zero. A slot nobody sealed is refused as `not_sealed` (its header CRC is zero), so an image that skipped the post-build step cannot pass for a sealed one.
* The post-build step, `python tools/stamp_image.py seal IMAGE.bin`, checks that the slot is there, fills in the length, the CRC-32 and the header CRC in place and verifies the result. With `--hardware` or `--version` it refuses a firmware that states something else. The same bytes come out every time.
* A reader (`urtc_image_verify_embedded` in C, `verify_embedded` in Python, the TypeScript port of the web studio) reports `ok`, `short`, `bad_magic`, `bad_version`, `bad_size`, `bad_header_crc`, `bad_flags`, `bad_length`, `bad_payload_crc` or `not_sealed`.
* The signature record (`<image>.imgsig`) keeps its form and is made exactly as before: over the 28 bytes of the header the bootloaders rebuild from the update (hardware, version, length and the plain CRC-32 of the received bytes), the SHA-256 of the **whole file** that is flashed and the rollback counter. The embedded header is part of that file, so changing its identity, length or CRC changes the SHA-256 and breaks the signature; no bootloader has to change to accept a sealed image.

### The compatibility switch

Images built before the header was embedded have none, and the boards in the field still accept them. Every tool that reads a file to flash decides with one function, `inspect_image` (the same decision, with the same words, in Python and in TypeScript; `conformance/image_header_embedded_vectors.json` holds the cases):

| Switch | An image with a valid header | An image without a header |
| --- | --- | --- |
| `accept` | accepted | accepted |
| `warn` (the default) | accepted | accepted, and the tool says it could not check the identity |
| `require` | accepted | refused |

Whatever the switch says: a header that is there is always checked, and a bad one is refused (a wrong CRC, a length that is not the image, a slot nobody sealed, a hardware id that is not the board's, a version that is not the one the file name states); a `.urimg` file (the flat form) is never flashed; and a value of the switch that is not one of the three words means `require`. The setting is `image_header_policy` in the configuration of the flasher and of the web studio and `image_header_check` of the gateway.

### Who does what

* The firmware (`URTC`): the slot, the linker section at `0x200` and the assertion on the vector table, for the main application and the expansion slave application; a self check of the image by `urtc_image_verify_embedded`.
* The release tooling: `stamp_image.py seal` after the build, then the `.imgsig` over the sealed file.
* The flasher and the web studio: read the header of the file, show hardware, version and length in the log, apply the switch before the first frame is sent.
* The tester: `image-info` prints what a file states and what the switch decides.
* The gateway: reads the start of an update that passes through (the size and hardware of `0x7F1`, then the first bytes of the data) and drops the rest of an update whose header is bad or does not match.

### What is pending a board

Everything above is exercised on the host with simulated parts. Still to be proven on a real board: that a bootloader receives and flashes a sealed image of the application, and that the application then reads the same header back from its flash (`image-info` against a read-back image). The bootloaders themselves do not carry the header yet.
