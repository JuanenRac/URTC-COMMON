# Bootloader identity and image authentication

**Status: designed, with portable C and a Python reference tested on the host. Nothing is built for a board and nothing is flashed.** No bootloader calls this code yet. The identifiers `0x7EA` to `0x7ED` are confirmed and written in `spec/can_protocol.json` with the formats below. Where a statement says what a bootloader does, it describes what the code in `firmware_base/` does on the host.

Two things are missing from the bootloaders today, and they are designed together because both change what happens between the host and a board during an update:

1. **Which head is it?** The bootloader has no identity. With several heads on one bus every bootloader answers `0x7F8` with `0x7F9`/`0x7FA`, and the answer to "what version is installed?" is ambiguous.
2. **Who signed this?** Images are authenticated with an HMAC-SHA256 whose key is built into the bootloader. Anyone who can read a bootloader can sign an image. An Ed25519 signature needs only a *public* key in the bootloader, so reading it gives no power to sign.

| Piece | File |
|---|---|
| Ed25519 verifier and the SHA-512 it needs (C) | `firmware_base/urtc_ed25519.h`, `urtc_ed25519.c` |
| The decision to install an image (C) | `firmware_base/urtc_auth.h` |
| Addressing by serial number (C) | `firmware_base/urtc_bl_select.h` |
| Python references | `src/urtc_common/ed25519.py`, `image_auth.py`, `bl_select.py` |
| Shared vectors | `conformance/ed25519_vectors.json`, `signed_image_vectors.json`, `bootloader_select_vectors.json` and the C tables in `generated/` |
| Tests | `tests/test_bootloader_auth.py`, `tests/c/test_bootloader_auth.c` |
| Texts in eight languages | `spec/i18n/catalog/bootloader-auth.json` |

`python tools/make_bootloader_auth_vectors.py` writes the vectors (`--check` fails when they are out of date). Every key in the vectors is a throwaway test key derived from a label; no release key exists in this repository and none ever belongs here.

## 1. Identity by serial number

### The serial

The STM32F303 has a 96-bit unique ID. The serial is 32 bits folded from it with the same function the application already uses for its multinode serial:

```
serial = w0 ^ rotl(w1, 11) ^ rotl(w2, 22)
```

so a head reports one number in the bootloader and in the application. `0` and `0xFFFFFFFF` (a blank or erased ID) are not serials: a bootloader whose ID folds to one of them takes no part in anything below and behaves exactly as today.

### The programmable serial

A head can be given a serial of its own, which is the way out of a duplicate. It is an optional record of **three 32-bit words** in the bootloader's metadata flash (words as the Cortex-M stores them, little-endian in memory; the values below are the numbers):

| Word | Meaning |
|---|---|
| 0 | magic `0x55525331` (the ASCII `URS1`) |
| 1 | the serial |
| 2 | the bitwise complement of word 1 |

Rules:

* **Priority.** When the record is valid it **replaces** the fold of the unique ID: the head probes, selects and answers with the programmed serial, and the application is expected to report the same one. When there is no valid record the fold is used, exactly as before.
* **Valid** means the magic is right, the third word is the complement of the second, and the serial is neither `0` nor `0xFFFFFFFF`. A blank page (`0xFFFFFFFF` everywhere), a wrong magic or check, or an unusable serial all give the fold back; nothing is ever refused because of a damaged record.
* **The unique ID does not change.** `UID` always answers the real 96-bit ID, so a programmed serial hides nothing from the duplicate check.
* **Duplicates.** The host enumerates the serials, selects one and reads the three UID words. Two heads that share the selected serial answer one identifier with different words (the host sees two different payloads, or nothing at all because the bus destroyed the clashing frames after the selection was answered): `duplicate_suspected` in `bl_select.py` says so, and the host refuses to update and asks the user to disconnect one head. This covers two programmed heads with one serial, a programmed serial equal to the fold of another head, and a folded clash that nobody has remedied.
* **Writing it** is a step of Studio (a setting of the head), not of the bootloader's update frames, and is not part of this design yet: only the reading side and the vectors exist.

Vectors: the scenarios of `conformance/bootloader_select_vectors.json` cover a programmed serial (it wins over the fold; the fold's serial no longer selects), a record with a wrong check or magic, blank metadata, a serial of zero or all ones, and whole buses (`bus_scenarios`: serial present, absent, duplicated, fold against programmed).

### Frames

The block `0x7EA` to `0x7ED` is confirmed and written in `spec/can_protocol.json`. Every existing identifier (`0x110`, `0x111`, `0x7E9`, `0x7F0` to `0x7FF`) keeps its meaning and its bytes. All multi-byte fields are big-endian.

| Identifier | Direction | Payload |
|---|---|---|
| `0x7EA` PROBE | host to all | `01`, `nbits` (0 to 32), `prefix` (4 bytes) |
| `0x7EA` SELECT | host to all | `02`, `serial` (4), `seq` |
| `0x7EA` RELEASE | host to all | `03` |
| `0x7EA` UID | host to the selected | `04`, `part` (0 to 2) |
| `0x7EB` answer | bootloader to host | PROBE: `01 A5`; SELECT: `02 serial seq`; UID: `04 part word(4)` |
| `0x7EC` | host to the selected | one chunk of the signature record (section 2) |
| `0x7ED` | selected to host | the 8-byte identifier of a trusted key, sent right after the answer to `0x7F8` |

A frame with an unknown operation or the wrong length is ignored and changes nothing.

### Finding the heads without collisions

Two nodes must never send the same identifier with different data: the bus would see a bit error and both would retry. The probe avoids it by design. A PROBE asks "does anyone have a serial whose first `nbits` bits are those of `prefix`?", and every bootloader that matches sends the **same** two bytes `01 A5`. Identical frames sent at the same moment are legal on CAN: they merge into one.

The host walks the 32 bits as a binary tree (`enumerate_serials` in `bl_select.py`): ask for the empty prefix, then for each branch that answers, one more bit. For N heads it takes at most `1 + 64 N` probes, each a frame and an answer or a silence of a few milliseconds, so a bus of four heads is enumerated in well under a second at 125 kbit/s. If the first probe (the empty prefix) gets no answer, no bootloader announces a serial: the host keeps the single-head behaviour it has today.

### Selecting one head

SELECT carries the serial; the head that has it becomes *selected* and answers, every other head becomes unselected. After that the single-head frames `0x7F0` to `0x7FF` are obeyed **only by the selected head**. The host then asks for the version (`0x7F8`) and everything else as before; no existing frame changes.

* **Addressed mode.** A bootloader that hears any valid frame on `0x7EA` is in addressed mode and ignores `0x7F0`-`0x7FF` until it is selected. With nobody addressing it, it behaves exactly as it does now. Addressed mode ends `URTC_BL_ADDRESSED_LAPSE_MS` (10 s) after the last frame, so a host that went away leaves the bus in the single-head state.
* **Timeout.** A selection ends `URTC_BL_SELECT_LAPSE_MS` (2 s) after the last SELECT; the host repeats SELECT while it waits. While an update runs neither timer cuts the transfer off: the bootloader's own inactivity timeout does.
* **Duplicate serials.** Thirty-two bits make an accidental clash very unlikely but not impossible. After SELECT the host reads the three words of the unique ID (UID, parts 0 to 2). Two selected heads would answer with different words under one identifier; the host sees corrupted or inconsistent frames and refuses to update, telling the user to disconnect one head.
* **Wrap.** Times are a free-running 32-bit millisecond counter compared as unsigned differences.

### Compatibility

| Host | Bootloader | Result |
|---|---|---|
| old | old | unchanged |
| old | new | the new bootloader never hears `0x7EA`, so it is not addressed and answers as today |
| new | old | the probe gets no answer: the host keeps the single-head behaviour |
| new | new, one head | the host may select it (or not): both work |
| new | new, several heads | the host selects one; the others stay silent to the single-head frames |
| new | new and old on one bus | the old head answers everything; after the probe, an answer to `0x7F8` with nobody selected can only come from an old head, and the host refuses to update and asks for one head at a time |

**The key fingerprint.** The first precheck of the flashing tools read a `0x7FA` frame of eleven bytes (version plus eight bytes of fingerprint). A classic CAN frame carries at most eight data bytes, so such a frame cannot exist on this bus and that precheck could never work. `0x7FA` is exactly three bytes (major, minor, patch) and a frame of any other length is not a bootloader version. The identifier of a trusted key travels on `0x7ED` (eight bytes), sent by a bootloader that holds a trusted Ed25519 key right after its answers to `0x7F8`; the precheck of the tools reads that frame. A bootloader that does not send it (an old one, or one without a key) gives "no data": never a difference and never an error. With several heads only the selected one answers `0x7F8`, so only its fingerprint arrives.

## 2. Ed25519 image authentication

### What is signed

A bootloader cannot hold a 112 KB image in RAM, so the signature does not cover the image bytes. It covers a fixed 88-byte record that commits to them:

| Field | Bytes | Meaning |
|---|---|---|
| domain | 16 | `URTC-IMG-SIG-V1` and a zero: a signature made for another purpose cannot be replayed here |
| header | 28 | bytes 0 to 27 of the image header (`IMAGE_HEADER.md`): hardware id, the four version components, payload length and CRC-32 |
| sha256 | 32 | SHA-256 of the payload, streamed over the flash by the bootloader's existing SHA-256 |
| counter | 4 | the rollback counter, big-endian |
| key id | 8 | the first 8 bytes of the SHA-512 of the public key that signs |

The record that travels with the image is `key id (8) | counter (4) | signature (64)`: **76 bytes**. It is sent as 11 frames on `0x7EC`, `index` (0 to 10) followed by seven bytes (the last one padded with zeros), after `START_UPDATE` and next to the HMAC chunks of today. Until the header is placed in the image itself, the bootloader builds the same 28 bytes from the fields of `START_UPDATE`; the signing tool builds them from the image it signs.

The hardware id is in the signed bytes, so an image signed for the main board does not install on the expansion slave; the check is made before anything else.

### Policy

A setting in the bootloader's metadata, configurable from Studio, with the strict value as the default and as the value `0` (a zeroed structure fails closed):

| Value | Name | Installs an image when |
|---|---|---|
| 0 | `ed25519_only` | its Ed25519 signature verifies under a trusted key |
| 1 | `either` | the Ed25519 signature verifies, **or** the HMAC-SHA256 of today verifies (transition only) |
| 2 | `hmac_only` | the HMAC verifies (today's behaviour) |

Order of the checks: hardware id; authentication by the policy; then the rollback rules. An image nobody vouched for gets an authentication status and reveals nothing about the installed version. Statuses: `ok`, `bad_args`, `not_signed`, `unknown_key`, `bad_signature`, `bad_hmac`, `hardware_mismatch`, `rollback_counter`, `rollback_version`.

### Anti-rollback

Two different protections:

* **The counter** is signed. The bootloader stores a floor in its metadata and refuses an Ed25519-signed image whose counter is below it; after a successful install the floor becomes the image's counter. A release raises the counter only when an older image must never run again (a security fix). Nothing overrides the counter, not even an authorised downgrade.
* **The version** is signed too (it is in the header bytes). An older version than the installed one is refused unless the owner authorised a downgrade, as the bootloader already allows with `0x7FD`. This also applies to images accepted through the HMAC.

### Keys and rotation

The bootloader embeds one or two **public** keys: the current one and, ahead of time, the next. Rotation needs no special frame:

1. A bootloader release embeds `[current, next]`; both verify.
2. Releases are signed with `current` until the fleet has the new bootloader, then with `next`.
3. The following bootloader embeds `[next, next2]`; `current` is retired.

A key that must stop being trusted at once is retired the same way and the counter is raised in the same release so that images it signed cannot come back. The private key stays with whoever builds the release, never in a repository or in a tool shipped to users. The key identifier is what the tools already compare as the "signing key" fingerprint.

### Transition from the HMAC

1. A bootloader with policy `either` and the Ed25519 key installs both kinds of image; releases carry both the HMAC and the Ed25519 record.
2. When the fleet has it, the policy goes to `ed25519_only` and the HMAC key leaves the build.

The first bootloader of the transition ships with `ed25519_only` from the start (value `0`, fails closed): a head that has not received the first Ed25519 release is updated through the existing path of its current bootloader, and `either` and `hmac_only` remain available as explicit choices, never as the default. In the code this is `URTC_AUTH_DEFAULT_POLICY` and `image_auth.POLICY_DEFAULT`.

### Size, time and the implementation

Estimates, **not measured on a board** (nothing is built for one):

* **Code and data:** the verifier, the SHA-512 and the constants are expected to take roughly 5 to 8 KB of flash (including the 640-byte round-constant table) against about 12 KB free in the master bootloader. To be measured with the real toolchain; the slave bootloader's free space is not known yet.
* **RAM:** about 2 to 3 KB of stack at the deepest point (the curve points and the temporaries of an addition). No heap.
* **Time:** one verification is two scalar multiplications by a 256-bit scalar. On a 72 MHz Cortex-M4 this is expected to be of the order of a second. It runs once, after the last data frame. The code calls `URTC_ED25519_YIELD()` every 8 bits of each scalar, which the bootloader defines to refresh its watchdog.
* **Implementation:** written for this repository under the licence of the repository (GPL-3.0-or-later). The group arithmetic follows the compact **TweetNaCl** design (Bernstein, Lange, Schwabe and others, public domain): 16 limbs of 16 bits and no data-dependent table lookups. The constants are standard (RFC 8032 and FIPS 180-4; the file `tools/make_bootloader_auth_vectors.py` and the tests check them against an independent Python implementation, and the C code against the RFC 8032 vectors). No other code was copied. Two checks that the original leaves to the caller are made: the scalar of the signature must be below the group order, and a public key whose `y` is not reduced is refused. Verification only: the code holds no secret.
* **Timing:** the data-dependent branches in verification are on public values (the signature and the public key); the final comparison is constant-time.

## 3. Tests

* Ed25519: RFC 8032 cases, messages across the SHA-512 padding boundaries, and each way a signature can be wrong (a flipped bit in `R`, in `S`, in the message, another key, `S + L`, all ones, all zeros, a `y` that is not reduced, a point not on the curve). The Python tests also make a random throwaway key per run and break its signature in several places.
* Installation: a good image, a higher counter, rotation with both keys, rotation with only the old key, a stranger's key, no keys, a flipped bit in the signature, another payload, another version, a raised counter, a swapped key id, other hardware, a counter below the floor, an older version with and without authorisation, no signature under each policy, the HMAC under each policy.
* Serial: the programmable serial (present, absent, damaged, blank, unusable, equal to another head's fold, shared by two heads), the detection of a duplicate on whole buses, a head nobody addresses, probes by prefix, malformed frames, selection and deselection, lapse of selection and of addressed mode, a transfer that keeps its selection, the unique ID, a release, serials that cannot be used, and the wrap of the millisecond counter. A model of several heads checks that enumeration finds every one within the bound and that a duplicate serial shows in the unique ID.

The C code is compiled with `-Wall -Wextra -Wconversion -Werror` and, where the compiler has them, the address and undefined-behaviour sanitizers.

## 4. Open points

* **Writing the programmable serial** into the metadata (a Studio setting, with its own confirmation) and how the application learns it: the record and its reading are specified here; the writing is not.
* **Which key a bootloader reports on `0x7ED` when it trusts two** (rotation): the design sends the first, current one; the tools compare the fingerprint of the image's key with it.
* **Everything that needs a board:** the real flash and stack figures, the verification time, a streaming `sha256_flash_region` next to the existing HMAC code, the metadata fields for the policy and the floor, and the integration into the update state machine. None of it is started: the bootloaders are not touched.
* **Signing a release** with an Ed25519 key is a step of the release machine (`firmware_signing.py` produces the HMAC today); the key is created by the owner and kept outside the repositories.
