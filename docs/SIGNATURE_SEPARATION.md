# Separating the signature from the image

**Status: design with a host reference. The formats below are fixed, implemented in Python (`src/urtc_common/image_sig.py`) and held to shared vectors (`conformance/image_sig_vectors.json`). Nothing is built for a board, no bootloader reads them yet and no release uses them.** It extends `BOOTLOADER_AUTH.md` (the Ed25519 verifier, the 88-byte signed record, the policy, the rotation window), which is already written and tested on the host, with the one thing it did not cover: how the official firmware can be **compiled by a public build service without any private key leaving the maintainer's computer**.

## 1. The model today and why it blocks a public build

* A bootloader authenticates an application image with an HMAC-SHA256 whose 32-byte key is **compiled into the bootloader** (`bootloader_crypto.c`, `slaveboot_crypto.c`). A symmetric key cannot tell verifying from signing: whoever can verify can sign, so the key must be inside the image and the job that compiles the image must hold it.
* A build service must not hold that key, and a key inside a downloadable, attested binary is readable by anybody. So the service builds with the **public development key** (`signing_key_kind: dev`): a bench build, never an official one. The official bootloaders are compiled on the maintainer's machine.
* Only the **bootloaders** carry the key. The application images do not: their HMAC is computed after the build and published beside the image. The bootloaders are not updated over the bus; they are flashed through the debug port.

## 2. Target architecture

1. **The image is compiled with no secret.** No job holds a private key and no binary contains one.
2. **The bootloader holds only public keys**, in a *trust table* at a fixed place of the binary. Reading a board gives no power to sign.
3. **The signature is a separate record**, made on the maintainer's machine after the build, over the header, the SHA-256 of the payload and the rollback counter. It does not need a rebuild: the same bytes the service built are the bytes that are signed.
4. **The local release step pins the trust table.** Before signing, the tool reads the table of every bootloader it is about to sign (fixed offset, no disassembly) and compares the key identifiers with the ones it has pinned. A build made with another table is refused before any key is read.

Algorithm: Ed25519 (RFC 8032), verification only on the board. Alternatives considered:

| Option | Verdict |
|---|---|
| Ed25519, public key in the bootloader | **Chosen.** One image for the whole fleet, no secret in the image, clean rotation |
| HMAC with a per-device key derived from a master key and the unique ID | Every board needs its own record and provisioning; the release stops being one public set of files |
| HMAC with the key in the metadata page (provisioned once over the debug port) | The image holds no secret, but the key is shared by the fleet and readable from a board. Useful only as a bridge (section 7) |
| Header signature with a table of rotatable keys | This is the chosen option with the table of section 3.3 |

## 3. Formats (schema 1)

### 3.1 The signed record and the record that travels

Unchanged from `BOOTLOADER_AUTH.md`:

* Signed record, 88 bytes: `URTC-IMG-SIG-V1` and a zero (16) | bytes 0 to 27 of the image header (28) | SHA-256 of the payload (32) | rollback counter, big-endian (4) | key id (8).
* Record that travels, 76 bytes: key id (8) | counter (4) | Ed25519 signature (64), sent as 11 frames on `0x7EC`.
* The **key id** is the first 8 bytes of the SHA-512 of the public key. The hardware id is inside the signed bytes, so an image for the main board does not install on the expansion slave.

New in a release: each image has a `<image>.imgsig` file (the 76 bytes as one line of hexadecimal) and its manifest gains `image_record_hex`, `image_counter` and `image_key_id`. `hmac_sha256` stays while bootloaders that only know the HMAC are in use.

**The `.imgsig` file** is the 76-byte record as exactly 152 hexadecimal digits on one line (lower case is written, upper case is read), with at most one line end after it. A reader refuses anything else (a short or long line, a non-hex digit, a second line, a carriage return, trailing spaces). The same bytes go in `image_record_hex` of the manifest.

The image-signing key is **not** the key that signs release assets (`RELEASE_SIGNING.md`): the two use different domains and different keys, so a stolen asset key does not open the boards.

### 3.2 Versioning

The domain string carries the schema (`V1`). A bootloader that does not know a schema, a table version or a metadata record version refuses it and keeps the installed application. Tools refuse a record whose schema they do not know.

### 3.3 The trust table

A linker section placed at a fixed offset of the bootloader (the offset is a constant shared with the release tools; a test fails if the two disagree). Little-endian:

| Field | Bytes |
|---|---|
| magic `TKEY` | 4 |
| schema (1) | 1 |
| number of keys (1 or 2) | 1 |
| table flags | 2 |
| per key: key id (8), public key (32), flags (1: current, 2: next, 4: revoked), 3 zero bytes | 44 each |
| CRC-32 of everything above | 4 |

With one key the table is 56 bytes and with two it is 100. A reader refuses: a wrong magic or schema, a number of keys other than 1 or 2, non-zero table flags, a CRC-32 (zlib) that does not match, a key id that is not the first 8 bytes of the SHA-512 of its key, a flag byte that is zero, has an unknown bit, sets *current* with *next* or *revoked* with anything else, a non-zero padding, a key listed twice, or more than one *current* key. A key marked *revoked* stays in the table and is never trusted.

**Fixed offsets.** The section is placed by the linker at a constant offset of each bootloader image, counted from the first byte of the binary: `0x200` for the main and the slave bootloaders (after the vector table). The offset is a field of the public key file (`keys/image_trust.json` of the firmware repository) so the release tool and the test read the same number; until a bootloader is built with the section, the offset describes the layout the linker script must produce. It is generated from a **public** file kept in the repository (accepted key ids, the lowest counter the bootloader will ever accept, the default policy), never from a secret variable. A test reads the table back from the compiled binary and compares it with that file. The same code builds two flavours that differ only by the table: *release* (production keys) and *dev* (a development key whose seed is public, for the bench).

### 3.4 Rotation and revocation

* **Rotation** is the two-fingerprint scheme of `BOOTLOADER_AUTH.md`: the table lists `[current, next]`; releases are signed with `current` until the fleet has the bootloader that knows `next`; the following bootloader lists `[next, next2]`. The overlap window is the parameter `rotation_window_s`; the two identifiers are announced on `0x7ED`.
* **Revocation** has three tools: the next bootloader leaves the key out; a release raises the counter so nothing signed earlier comes back; a *revoked* flag in the table retires a key that is still present. A revocation **command on the bus** is deliberately absent: a stolen key could use it to lock out the good one.

### 3.5 Anti-rollback and metadata

* The counter is signed. The floor the bootloader enforces is the larger of the floor kept in its metadata and the minimum compiled into the bootloader, so even a lost metadata page cannot lower it. A signed image whose counter is below the floor is refused; after a good install the floor becomes the image's counter. Nothing overrides it, not even an authorised downgrade of the *version*.
* The metadata is an **append-only log with a generation number**: each record has magic, schema, type, length, generation, payload (policy, floor, rotation start and window, the installed image's header, digest and record, copy state) and a CRC-32, padded to the programming unit of the chip. The valid record with the highest generation wins; a record cut short by a power failure fails its CRC and the previous one stays. The page is erased only when full. Where a second erase unit is free, the state alternates between two units instead.
* This is a staged slot with an atomic commit, **not** an executable A/B: the application is linked for one address. A third slot for a known-good image does not fit in the flash; a known-good image and signed deltas live on the host side, and the board always receives a complete image with its record.

### 3.7 The expansion slave: the master verifies, the slave confirms

The measured slave bootloader (13676 of 18432 bytes) cannot hold the verifier, which needs about 7 KB more. The application of the slave is **not** moved: every tool that knows its start address keeps working. Instead:

* The **master** verifies the same 76-byte record for the slave image, under the keys of the trust table of **its own** bootloader (read from flash at the fixed offset), over the header of the slave image (the slave's hardware id inside) and the SHA-256 of the bytes it relays. The record travels on `0x21A` `SLAVE_RECORD_CHUNK`: eleven frames of an index and seven bytes, as `0x7EC` does for the main board.
* The **slave** checks size, hardware id, CRC-32, the SHA-256 of what it received against the digest it was sent (the `0x212` frames now carry a SHA-256, not an HMAC), and the version rule. It then waits in status `0x08` (AWAIT_CONFIRM) for `REG_CONFIRM` (`0x0A`): 32 bytes, the SHA-256 of a 76-byte message (`"URTC-SLV-CONF-V1"`, the 16-byte nonce the slave published in `REG_CHALLENGE` `0x09`, the image SHA-256, hardware id, version major, version minor field, size). It rebuilds the message from its own values, reads its backup slot again and compares. No confirmation in ten seconds, a wrong tag or an altered image: status VERIFY_FAIL with reason `0x06` NOT_CONFIRMED (or `0x03` when the digest no longer matches), main slot untouched. It fails closed.
* **Honest limits.** The tag is a hash, not a MAC: there is no secret to share and none is put back in the image. The slave trusts the master through the link bus, so a device on that bus can compute the tag. The nonce is a freshness value (the chip has no random source), not a secret. The slave keeps no rollback counter; it applies its version rule only. The check at boot is a keyless SHA-256. The details and the host tests are in the firmware repository (`docs/SLAVE_BOOT_CONFIRMATION.md`).
### 3.6 What replaces the boot-time HMAC

Once the signature is verified at install time, the check at every boot only has to catch corruption of the flash: a SHA-256 of the installed application stored in the metadata, with no key. Protecting the boot pages against being rewritten through the debug port is a chip setting (read and write protection) that has to be reviewed on a board.

## 4. Cost

Nothing here has been measured on a board or built for one, so there are no new figures.

* **Known from files already in the repository:** the main bootloader image is 18132 bytes in a 30 KB region; the slave bootloader is 13100 bytes in an 18 KB region. Those are the sizes of the published binaries, which may predate the sources.
* **Not known:** the size of the verifier, its stack and its time. `BOOTLOADER_AUTH.md` estimates 5 to 8 KB; `FIRMWARE_SIGNING.TXT` estimates 10 to 16 KB. Both are unmeasured and they disagree. The slave bootloader does not hold the verifier (measured: 13676 of 18432 bytes, about 7 KB short): the master verifies for it and the slave confirms (section 3.7); its application stays where it is.
* **Library:** the verifier is written for this repository (GPL-3.0-or-later) on the compact TweetNaCl design (public domain): the smallest and slowest option. Monocypher (BSD-2-Clause or CC0) and ed25519-donna (public domain or MIT) are larger and faster and are compatible with the licence. The decision is taken after measuring.
* **How to measure without compiling on a workstation:** a read-only job of the build service compiles the verifier alone for Cortex-M4 (`-Os`, `-ffunction-sections`, `-fstack-usage`) and prints `arm-none-eabi-size -A` and the stack file; links each bootloader with and without the table and verifier and prints the headroom against the region of the linker script (failing under a configured threshold); and may give an order of magnitude of the time with an emulator's instruction counter. The reliable time is the cycle counter on a board.

### 4.1 The size report (specification of the read-only job)

The build service gains one job that holds no secret and publishes numbers; it never changes a binary.

1. **Verifier alone:** compile `urtc_ed25519.c` (and the SHA-512 it needs) with the pinned toolchain for Cortex-M4 with `-Os -ffunction-sections -fdata-sections -fstack-usage`; print `arm-none-eabi-size -A` of the object and the `.su` file.
2. **Bootloaders with and without:** link each bootloader twice, with and without the table and the verifier, from the same sources; print `.text`, `.rodata`, `.data` and `.bss` of both and the difference.
3. **Headroom:** for each bootloader print the free bytes of its region of the linker script; fail when the headroom with the verifier is under a threshold that is a configuration value (default 512 bytes), and when the stack of the deepest verifier call chain plus the existing worst case does not fit the RAM reserved for the bootloader stack.
4. **Time:** only an order of magnitude from an emulator's instruction counter, marked as such. The reliable time is the cycle counter on a board.
5. The report is a build artifact and a table in the job summary; it is the evidence for the decisions of section 4 (library, slave bootloader).

## 5. Tests

* **On the host, in CI:** RFC 8032 vectors; the record, the table and the metadata with shared generated vectors (`--check` fails when stale); the bootloader twin (the real C of the main bootloader behind an SLCAN-style port) extended to Ed25519: a good install, a flipped bit in the header, the payload, the signature or the key id, a counter below the floor, an older version, a corrupt table, rotation with one and with two keys, the default policy, and a power cut at **every** write of the metadata on the simulated flash; and a test that the compiled table equals the public key file.
* **On the bench:** the verification time with the cycle counter, the stack high-water mark, the watchdog during verification, real power cuts during the copy and during a metadata write, the first flashing of the new bootloader, a rotation with the clock.

## 6. Release flow

1. **Build service:** compiles the release and dev flavours with no secret, produces `SHA256SUMS`, a build manifest and an attestation, and checks that two builds give the same bytes. It checks that each binary contains the table it should and declares it. The result is an unsigned draft.
2. **Local release tool:** verifies the attestation, that the commit built is the one requested, and that the trust table of each bootloader equals the pinned key ids. Then it makes the Ed25519 image record of each image with the image-signing key, the HMAC while it is still needed, and the release-asset signatures. It signs into a temporary folder and moves the set only when every signature verified.
3. **Publishing:** the release workflow verifies, without any secret, that every image record verifies under the public key of the table.
4. **The board** checks the record. The flasher, the updater and the web studio verify it before sending it and show both fingerprints and the rotation window.

## 7. Boards already deployed

A bootloader that only knows the HMAC keeps accepting HMAC records and is changed only through the debug port. During the transition a release therefore carries both records: the HMAC (computed locally with the existing key file, no rebuild) and the Ed25519 record. The first official bootloader of the new scheme has the policy `ed25519_only` (value 0, fails closed).

If one board has to accept both kinds, the policy `either` needs the HMAC key; to keep the image free of secrets that key sits in a **key slot of the metadata page**, written once over the debug port. Retiring the HMAC is a parameter: the tools stop producing HMAC records from a configured date, and the bootloader accepts the HMAC only for images below a configured counter (it has no clock), after which a command signed with Ed25519 erases the slot for good. The policy can be made stricter over the bus; making it looser needs the debug port.

## 8. Open points

These are not decided and nothing here depends on them: a rollback counter on the slave, and how the confirmation could be authenticated without a shared secret; whether the metadata page alternates two erase units or keeps one append-only log in the units that exist; where the known-good image of the host lives and how a delta is signed; and how a key is revoked beyond the three tools of section 3.4. The library stays the compact TweetNaCl design until the size report says otherwise. The policy of the first official bootloader is `ed25519_only`, so the HMAC key slot of section 7 is not needed for a board that has never run the old scheme.

## 9. Plan

1. The public key file, the trust-table generator and the test that reads the table back from a binary.
2. Shared vectors for the table, the metadata records and the counter; the Python and C references.
3. The metadata log in portable C with a power-cut test over every write.
4. The bootloader twin with Ed25519, the table, the floor and the policy.
5. The key slot, the signed retirement command and the sunset counter.
6. The slave bootloader: measured; the master verifies and the slave confirms (section 3.7).
7. The release tools: signing the image record, the pin of the table, the manifest fields, the verification of the set.
8. The flasher, the updater and the web studio: verify, transport and show the fingerprints, in eight languages.
9. The build-service changes: accept the release table, report sizes and headroom.
10. Bench: time, stack, power cuts, the first flashing, rotation.
11. First official release built by the service and signed locally.

Steps 1 to 5, 7 and 8 need no board. Steps 6 (final decision), 10 and 11 do.
