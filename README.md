<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center">🇺🇸 <b>English</b> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### The CAN protocol as data: specification, generated codecs, conformance vectors and shared transports

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Honesty check - what actually runs today:** this repository holds a specification, generators, test vectors and a small Python library. All of it runs and is tested in CI, but so far only URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO use it (the identifiers, the magic payloads, the hardware ids and the shared vectors, as copies kept honest by a lock file); the firmware and the transports keep their own copies of the protocol until each one migrates. The tests that compare the specification with those copies read their text when the repositories are checked out next to this one, and skip when they are not. Nothing here has been run against a board or a CAN adapter: the transports are tested with fakes, and the specification says for every identifier which implementations define it, so the gaps are visible instead of assumed away.

---

> **Safety and security status:** this ecosystem is not a certified safety system, and no populated URTC board exists yet. The bootloaders check firmware images with CRC32 and a shared-key HMAC-SHA256, not with an asymmetric signature (planned); the published application images are signed with the public development key (`signing_key_kind: dev`), so anyone can produce an image the bootloader accepts; nothing has been transmitted to a real board. Read the [security baseline](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) and the [threat model](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) before relying on any statement here for the safety of a person.

## 📋 At a glance

| | |
|---|---|
| Version | `0.0.7` |
| Maturity | Scaffolding |
| Tests | 431 |
| Stack | JSON / Python |
| On real hardware | Simulated only: tested against emulators, fakes or simulators; no run on real hardware is recorded for this version |

## 🎯 Overview

The CAN protocol of the tool head, written once as data, and everything that follows from it:

* [Specification](spec/can_protocol.json): every identifier with its direction, length rule, layout, tools and gates, the magic payloads, the slave registers and the SLCAN subset, and which implementations define each one.
* [Contracts](docs/CONTRACTS.md): what an implementation must do, who implements what today, and the known gaps and differences.
* [Specification format](docs/SPEC_FORMAT.md): the keys of the file and how to add or change an identifier.
* [Migration](docs/MIGRATION.md): the order in which each repository can adopt it, and how a check keeps the copies equal.
* [Protocol table](docs/PROTOCOL_TABLE.md): every identifier in one table, generated from the specification.
* [Several tool heads on one bus](docs/MULTINODE.md): addressing, discovery and safety rules; implemented in the URTC firmware behind a switch that is off by default, tested on the host only and not tried on hardware.
* Interface helpers: `src/urtc_ui`: the language list, status badges and the formatting of identifiers, bitrates and frames that the desktop programs can share (no Qt needed; URTC-FLASHER and URTC-TESTER carry a copy made with `vendor_copy.py --set ui`).
* Firmware parts: `firmware_base/urtc_crc8.h`, the CRC-8 of the rack and vision serial frames in one place (copied with `vendor_copy.py --set firmware_base`), and `generated/urtc_fw_vectors.h`, the vectors the firmware itself must pass (version fields, the magic payloads, the check values of the CRC-8) as C tables (`--set fw_vectors`).
* The assertion of the host tests of the firmware: `firmware_base/urtc_test.h` holds `TEST_ASSERT`, the one macro the rack, the vision tool and the tool head firmware used to define three times; each repository copies it with `vendor_copy.py --set firmware_test` and keeps its own `test_runner.h` with its suites.
* [Conformance vectors](conformance/can_vectors.json): the bytes every implementation must reproduce: every layout, the refusals and the SLCAN streams.
* [Tool profiles](spec/tools.json): the 25 tool profiles (limits, watchdog, pins, expansion board) as data; `generate_tools.py` writes the TypeScript and Python tables and [the tool table](docs/TOOLS_TABLE.md). Also here: the fault recorder reader with CSV and JSON export (`blackbox.py`), the rack simulator (`rack_sim.py`), frames for fuzzing a board made from the specification (`fuzz.py`) and the [compatibility table](docs/COMPATIBILITY.md) of a release, made from `spec/versions.json`.
* **Virtual board and companion links:** `virtual_board.py` serves a board behind an SLCAN adapter on a TCP port (`python -m urtc_common.virtual_board`); type `socket://127.0.0.1:7777` where a tool asks for a serial port and the flasher, the tester and the gateway run end to end with no hardware. `sensor_frame.py` is the reference of the vision sensor frame; it and the rack serial frame are version 2, big-endian like the bus, with their vectors (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Self-update from a signed package:** `self_update.py` is the whole flow for a program that updates itself from a GitHub release, with no network and no window of its own (the caller passes the fetch and the progress): it offers only a strictly higher version with a package for the platform, downloads from the hosts of GitHub's release downloads only, checks the announced size and SHA-256 and the Ed25519 signature of `urtc-pkg/1|app|version|platform|sha256|size` against the key pinned in the program, extracts without ever leaving the folder (no `..`, absolute path, link or device), refuses to install while an operation on the bus is running, keeps the two latest releases, rolls back by itself when the first start fails and records every step. Standard library only; copied with `vendor_copy.py --set update`.
* **Tools:** `generate_constants.py` writes the C header, the TypeScript module, the Python module and the table (`--check` compares), `make_conformance.py` writes the vectors (`--check`), `vendor_copy.py` copies parts into another repository with a lock file and checks the copy, and `ci_validate.py` is the shared repository check. `make_glance.py` of URTC-DOCS writes the At a glance table.

## 🧩 Role in URTC

URTC-COMMON is where the CAN protocol of the tool head is written down once, as data, so that the firmware, URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO can stop keeping four separate readings of the same prose. It holds the specification, what is generated from it, the vectors every implementation must reproduce and the transport layer the two Python tools share. By itself it changes the behaviour of none of them: each repository adopts it step by step (see docs/MIGRATION.md).

## 📂 Repository Structure

```text
URTC-COMMON/
├── docs/         contracts, specification format, migration guide, generated protocol table
├── spec/         the specification (can_protocol.json) and its JSON Schema
├── generated/    the C header and the TypeScript module, written from the specification
├── firmware_base/ C parts the firmware repositories share (the CRC-8)
├── conformance/  the shared vectors
├── src/          the Python package: generated protocol, framing, SLCAN codec, transports, versions, vector runner
├── tools/        generators with --check, vendor_copy.py, and the shared CI checks of the ecosystem
├── tests/        unit tests, the comparison with the repositories next to this one, the TypeScript run of the vectors
├── images/       the banner
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ BUILD & RUN

**Requirements:** Python 3.10 or newer; pytest and jsonschema for the tests; Node 22.18 or newer to run the generated TypeScript against the vectors (optional)

```bash
python tools/generate_constants.py --check           # the C, TypeScript and Python files and the table are current
python tools/make_conformance.py --check             # the vectors are current
python -m urtc_common.cli conformance                # this package reproduces every vector
python tools/vendor_copy.py check TARGET --source .  # a copy in another repository was not edited and has not fallen behind
python -m pytest tests -q                            # the unit tests and the comparison with the repositories next to this one
```

`build.sh` / `build.bat` raise the version by one step (the ecosystem's odometer), install the package and run the tests; `build-test.sh` / `build-test.bat` check without changing any version; `run.sh` / `run.bat` start the command line (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Related Projects

URTC is made of independent repositories, each with its own version, tests and README. This is the family, by group:

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (this repository), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Beyond URTC:**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - the robot-arm motherboard whose CAN relay is documented as the bus the tool head sits on
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - the same idea for the HYDRA-UMC ecosystem
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - the same idea for the A.R.M.O.R. security ecosystem
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - the profile and the status dashboard of all the ecosystems

## 📚 Documentation & Community

Where to read more:

* [Contracts: what each implementation must do, and the known gaps](docs/CONTRACTS.md)
* [Specification format and how to change it](docs/SPEC_FORMAT.md)
* [Migration: how each repository adopts it](docs/MIGRATION.md)
* [Protocol table: every identifier and who implements it](docs/PROTOCOL_TABLE.md)
* [Several tool heads on one bus](docs/MULTINODE.md)
* [Changelog of this repository](CHANGELOG.md)
* [License (GPL-3.0-or-later)](LICENSE)
* Questions, ideas and reports: electrohobby3d@gmail.com

## 👤 AUTHOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENSE

GPL-3.0-or-later - see [LICENSE](LICENSE).
