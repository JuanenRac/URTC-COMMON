# The header in front of a firmware image

A 32-byte header that says what a firmware binary is before anything trusts it: the hardware it is built for, its version as four components (`major.minor.patch.build`), its length and its CRC-32. It is meant for the images of every URTC firmware (the tool head, the expansion slave, the tool rack and the vision head) and for the bootloaders and tools that handle them.

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

The signature of a release (HMAC-SHA256) covers bytes 0 to 27 of the header followed by the payload, and is the trailer of the image. The identity, the length and the CRC that the header states therefore cannot be changed without breaking the signature: a forger who fixes the header CRC still does not have the key. The signature is made by the tooling that builds the release, never by the header code.

## Where it lives

* `firmware_base/urtc_image_header.h`: the C header (pack, parse, verify), copied into the firmware repositories with `python tools/vendor_copy.py sync TARGET --set firmware_image_header`.
* `src/urtc_common/image_header.py`: the Python reference (pack, parse, verify, sign), set `image_header`.
* `conformance/image_header_vectors.json` and `generated/image_header_vectors.h`: the shared vectors, written by `python tools/make_image_header_vectors.py` (`--check` fails when they are out of date); the C header and the reference are both held to them in `tests/`.

## What is not done yet

Nothing puts the header in an image. That is a change to the linker script and the post-build step of each firmware and to the bootloaders that would read it, followed by a build and a flash on the bench. The version frame on the bus (`0x7F9`) still carries three components; a frame with the fourth is a change of the specification and of the bootloaders.
