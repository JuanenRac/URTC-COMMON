<!--
=============================================================================
URTC-COMMON - docs/CONTRACTS.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Contracts

The CAN bus of the tool head is the one contract that crosses the firmware, two desktop tools and a web app. This repository makes it a piece of data that all of them can be checked against.

**The specification is the single source of truth.** `spec/can_protocol.json` says what every identifier is; everything else in this repository is either written from it or checked against it. A fact that is wrong in the specification is wrong everywhere; a fact that is right in the specification and wrong in an implementation is a failing check, not a surprise on a bench.

## What is in the contract

| Part | Where | What it fixes |
|---|---|---|
| Frame table | `messages` | 96 identifiers: name, direction, who handles it, the tools it is valid for, the length rule of every layout, every field (offset, type, range, enumeration), the gates (critical error, boot sequence, magic payload), the timing (telemetry period, watchdog), and which implementations define it |
| Magic payloads | `magic_payloads` | The four 4-byte values that make a destructive or one-shot command obeyed: enter the bootloader, authorise one downgrade, erase the saved state, reset the solder feeder position |
| Enumerations | `enums` | Tool profiles (25 plus the invalid marker), bootloader status, verify-fail reason, thermal fault, reset-cause flags, expansion board type, sensor variant and the small value sets of the commands |
| Constants | `constants` | The bitrate, the HardwareIDs, the flash page, the patch encoding, the timing every host must respect (watchdogs, grace window, acknowledgement timeout) and the limits the hosts offer |
| Registers | `registers` | The 23 registers of the expansion slave over its I2C link bus (bootloader and application), each tied to the CAN identifier that relays it |
| Procedures | `procedures` | The version query with its grace window, the minor field of the end-of-update frame, the order of versions |
| SLCAN | `slcan` | The subset of SLCAN that is relied on, and the bitrate codes |

All multi-byte fields are big-endian.

## What is generated, and what is checked

| File | Written by | Checked by |
|---|---|---|
| `generated/urtc_can_ids.h` | `tools/generate_constants.py` | `--check`, `tests/test_generated.py` |
| `generated/urtcCanIds.ts` | `tools/generate_constants.py` | the same, and the vectors run through Node |
| `src/urtc_common/protocol.py` | `tools/generate_constants.py` | the same, and the vectors run through Python |
| `docs/PROTOCOL_TABLE.md` | `tools/generate_constants.py` | `--check` |
| The generated blocks of `docs/CANBUS.TXT` of the firmware repository | `tools/generate_canbus_doc.py` | `--check`, `tests/test_canbus_doc.py`, and a digest in each marker that the firmware repository tests |
| The tool table of `docs/TOOLS.TXT` of the firmware repository | `tools/generate_tools_doc.py` | `--check` (also the order and the expansion board named by the prose), `tests/test_tools_doc.py`, and a digest in the marker that the firmware repository tests |
| `docs/STATUS.md` (what has run and what is pending) | `tools/status_table.py` | `--check`, `--check --siblings` in the nightly comparison, `tests/test_status_table.py` |
| The wheel, the source archive and `urtc_can_ids.h` of a release | `tools/make_release_artifacts.py` | `verify`, `reproduce`, `smoke`, `tests/test_release_artifacts.py` (see `docs/PACKAGE.md`) |
| `conformance/can_vectors.json` | `tools/make_conformance.py` | `--check` and both runners |

`--check` writes nothing and fails when a file differs from what the specification produces. A generated file is never edited by hand.

The vectors are computed with a small packer of their own, written apart from the generated encoder, and every example that carries hand-written bytes in the specification is compared with it. The generated Python and TypeScript are then run against the vectors, so two readings of the same layouts have to agree with each other and with the bytes written by hand.

## What an implementation must do

* **Send exactly what the layout says.** The generated builders refuse a value outside its range, a value that is not one of the defined values of a closed enumeration, a boolean or a float where an integer belongs, and a magic payload that is not the magic payload. They never clamp: a garbled count must not become a different, valid command.
* **Read what it is given, no more.** The generated parsers return nothing for a payload shorter than the layout needs, report a trailing byte that an older board does not send as absent (`None`), never as zero, and ignore bytes beyond the layout unless asked to be strict. Values are reported as received and are not range-checked.
* **Send the refresh before the watchdog, not at it.** Heaters, the laser, the drill, the UV driver, the hot-air blower and the printer nozzle are cut by the firmware when their command is not repeated within 250 ms; the layer fan within 1000 ms. The hosts repeat at 150 ms and 400 ms.
* **Treat a frame as one of the gated ones only when identifier and payload both match.** A magic payload on the wrong identifier is not a magic frame.
* **Handle the SLCAN subset strictly.** Standard `t` data frames only; every character after the `t` is a real hexadecimal digit; the line is exactly as long as its own DLC says; `T`, `r` and `R` lines are discarded; a status character glued to the front of a frame is skipped.

## Who implements what today

`implemented_by` in the specification records, for every identifier, whether the firmware, URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO define it. The counts below are read from the specification, and `tests/test_siblings.py` compares them with the text of the other repositories whenever those are checked out next to this one.

| Implementation | Identifiers defined | Of 96 |
|---|---|---|
| Firmware | 96 | all |
| URTC-WEB-STUDIO | 86 | not 0x1AA, 0x1AB, 0x1AC, 0x1AD, 0x1B8 to 0x1BA, 0x220 to 0x222 |
| URTC-TESTER | 60 | no bootloader or slave bridge frames; only the version patch frame (0x7E9) of the bootloader group; no 0x1A0, 0x1A2, 0x1A4, 0x1A6, 0x1AC, 0x1AD, 0x1B8 to 0x1BA |
| URTC-FLASHER | 38 | the bootloader, the slave bridge and the configuration registers only |

Ten identifiers are defined by all three host tools. The table of every identifier is [`PROTOCOL_TABLE.md`](PROTOCOL_TABLE.md).

## The companion links

Two links of the family do not travel on the CAN bus of the tool head but follow its byte order. Both are big-endian in every multi-byte value, like every temperature on the bus.

| Link | Frame | Version | Vectors | Reference |
|---|---|---|---|---|
| Tool rack, serial | start byte `0xA5`, version, sequence, command, length, payload, CRC-8; the temperature of `SET_PREHEAT` is two bytes, big-endian | rack serial frame version 2 | `conformance/rack_vectors.json`, `generated/rack_vectors.h` | `rack_sim.py` |
| Vision head, sensor | start byte `0xB6`, version, sensor, sequence, timestamp (four bytes, big-endian), length, payload, CRC-8; a thermal reading is a signed 16-bit number in hundredths of a degree, big-endian | sensor frame version 2 | `conformance/sensor_vectors.json`, `generated/sensor_vectors.h` | `sensor_frame.py` |

Version 1 of both frames was little-endian. A receiver at version 2 refuses a version 1 frame as an unsupported version, so an old sender can never be read as a different number. The CAN protocol of the tool head itself is unchanged (`protocol_version` stays at 1).

## Known gaps and differences

These are facts the specification records instead of hiding. None of them is changed by this repository.

1. **Two identifiers that no host implements.** `0x220` and `0x221` (write and read any application register of the expansion slave) exist in the firmware and are described in the prose of the firmware repository. The fault recorder (`0x1A8` and `0x1A9`) is read by URTC-TESTER and URTC-WEB-STUDIO, which export it as CSV and JSON. The health frame and the heater PID frames (`0x1B8` to `0x1BA`), like the multinode switch, have no panel in the hosts yet.
2. **`0x220` and `0x221` have no magic payload, and a built firmware has no list of registers.** Any node on the bus can write any application register of the expansion slave (PWM channels, sensor configuration). The bus has no sender authentication, so a host that implements them should restrict them to the registers it needs. The source of the firmware now drops the register that enters the bootloader and every register that is not on a closed list; a binary that includes that list has not been built yet, and the frames of the specification do not describe the list. A host should still send only the registers it needs.
3. **The firmware accepts longer frames than the prose says.** For 16 identifiers (0x120, 0x130, 0x140, 0x150, 0x160, 0x170, 0x173, 0x178, 0x1B0, 0x1C0, 0x1D0, 0x1E0, 0x1F0, 0x200, 0x252, 0x254) the prose gives an exact length and the firmware checks only a minimum; `firmware_accepts_dlc` records the real check of all 36 identifiers that have one. A sender follows the layout; a receiver ignores extra bytes.
4. **`0x120` is valid for more tools than the prose lists.** The prose names tools 1, 2, 3, 6, 7 and the soldering iron's feeder; the firmware routing table also sends tools 12 and 16 there, and both host tools already treat them as plain steppers.
5. **The read-back data frames are not always eight bytes.** The prose says eight; the bootloader sends the last frame as short as the image size requires (`0x7FE`, variant `data`).
6. **The prose says "12 tool profiles" in one description of `0x110`,** while the same document, the manifests and the firmware define 25.
7. **Names differ between implementations.** 20 identifiers are called by different names in the host tools (for example `GLOBAL_STATUS` and `STATUS_LED_CMD` for `0x100`); `client_names` records each one, and the canonical name is the one used in the generated code.
8. **The simulated board answers a slave version query with HardwareID `0x0303CC02`,** which is neither the main board (`0x0303CC01`) nor the slave (`0x0303CB01`). It is kept as it was in the flasher.
9. **Hosts disagree about SLCAN in a few places.** One reader requires the frame at the start of the line, another looks for the first `t`, a third (the web app) ignores anything after the payload. The shared codec takes the strictest reading that the vectors fix and marks the adapter-timestamp case as a tolerated difference.

## Rules for change

* **Additive first.** A new identifier, a new optional trailing byte or a new enumeration value is a change to the specification and nothing else; an older receiver ignores a trailing byte, and an older board never sends it. The grace window of the version query is the pattern: a board that predates a field never sends it, and a host that does not see it falls back.
* **`protocol_version`** counts changes of the protocol itself; **`format`** counts changes of the shape of the specification file (see [`SPEC_FORMAT.md`](SPEC_FORMAT.md)). Adding a key that readers may ignore keeps both; removing or renaming one raises `format`.
* **A wrong byte in a vector must fail every implementation at once.** That is the test of a change: edit one byte of a vector and the Python run, the TypeScript run and each migrated repository fail.
* **Nothing is hand-edited downstream.** A migrated repository holds a copy with a lock file; the check in [`MIGRATION.md`](MIGRATION.md) fails when a copy was edited or fell behind.
