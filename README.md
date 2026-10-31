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
  <img src="https://img.shields.io/badge/Version-0.0.8-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tests-1398-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Honesty check - what actually runs today:** this repository holds a specification, generators, test vectors and a small Python library. All of it runs and is tested in CI, but so far only URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO use it (the identifiers, the magic payloads, the hardware ids and the shared vectors, as copies kept honest by a lock file); the firmware and the transports keep their own copies of the protocol until each one migrates. The tests that compare the specification with those copies read their text when the repositories are checked out next to this one, and skip when they are not. Nothing here has been run against a board or a CAN adapter: the transports are tested with fakes, and the specification says for every identifier which implementations define it, so the gaps are visible instead of assumed away.

---

> **Safety and security status:** this ecosystem is not a certified safety system, and no populated URTC board exists yet. The bootloaders check firmware images with CRC32 and a shared-key HMAC-SHA256, not with an asymmetric signature (planned); the published application images are signed with the public development key (`signing_key_kind: dev`), so anyone can produce an image the bootloader accepts; nothing has been transmitted to a real board. Read the [security baseline](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) and the [threat model](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) before relying on any statement here for the safety of a person.

## 📋 At a glance

| | |
|---|---|
| Version | `0.1.1` |
| Maturity | Scaffolding |
| Tests | 1398 |
| Stack | JSON / Python |
| On real hardware | Simulated only: tested against emulators, fakes or simulators; no run on real hardware is recorded for this version |

**Jump to:** [Overview](#-overview) · [Architecture](#-architecture) · [Quick start](#-quick-start) · [Testing](#-testing) · [Structure](#-repository-structure) · [Related](#-related-projects)

<!-- urtc-section:status_common -->
## 🚦 Project status

🟢 done and verified · 🟡 works, with known limits · 🟠 half done or not verified · 🔴 not done or not working. Nothing is green if it never ran on real hardware.

| Part | Status | What the repository can show |
| --- | :---: | --- |
| Software | 🟡 | Shared code used by the other programs; checked only by tests on a PC. |
| Tests | 🟡 | The test suite passes in the CI on every push. |
| Security | 🟡 | Releases are signed with Ed25519 and checked before use; the key handling was not reviewed by anyone else. |
| Documentation | 🟡 | README in eight languages and reference documents; the translations were not reviewed by native speakers. |

<!-- /urtc-section:status_common -->

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
* The frame layer and the rate limiter of the serial links: `firmware_base/urtc_frame.h` (start byte, version, length, completeness and CRC-8 of a frame whose length byte sits at a given position, and the way back) and `firmware_base/urtc_rate_limiter.h` (the minimum interval between accepted messages, across the wrap of the millisecond counter), with a Python reference (`frame_layer.py`), rate vectors and a C test that holds both headers to every parse vector of the rack and of the vision sensor (copied with `vendor_copy.py --set firmware_frame`)
* A glossary of the phrases several programs say: `spec/i18n/glossary.json` names each one once, in the eight languages, and lists the keys of the flasher, the tester, the web studio and the updater that must say it that way (Close, Refresh, Clear, Heater PID, Port search ...); `tools/i18n_glossary.py` checks the file, checks the programs next to this repository (case, accents and punctuation are forgiven, a different word is not) and rewrites the lines of the `.lng` and `.json` files that differ; the nightly comparison runs it
* One source for the language files: `spec/i18n/catalog/<program>.json` holds every text of the flasher, the tester, the web studio and the updater in the eight languages (a text the glossary names is a reference to it); `tools/i18n_generate.py sync` writes the `.lng`, `.json` and `.py` files of each program with a lock (`urtc_i18n.lock.json`) and a test of its own, and `check` (also in the nightly comparison) fails when a file is not what the catalog generates.
* The quick guide inside the programs and the README sections they share: `help_text.py` (short steps each for the flasher, the tester and the updater in the eight languages), `help_qt.py` and `qml/HelpDialog.qml` (the Help window; copied with `--set help` and `--set help_qml`), and `spec/readme/sections.json` with `tools/readme_sections.py` (the Project status of each program and the parts that several README files share, written once in the eight languages and put between marker comments in their place of the layout; `check` runs in the nightly comparison)
* The assertion of the host tests of the firmware: `firmware_base/urtc_test.h` holds `TEST_ASSERT`, the one macro the rack, the vision tool and the tool head firmware used to define three times; each repository copies it with `vendor_copy.py --set firmware_test` and keeps its own `test_runner.h` with its suites.
* [Conformance vectors](conformance/can_vectors.json): the bytes every implementation must reproduce: every layout, the refusals and the SLCAN streams.
* [Tool profiles](spec/tools.json): the 25 tool profiles (limits, watchdog, pins, expansion board) as data; `generate_tools.py` writes the TypeScript and Python tables and [the tool table](docs/TOOLS_TABLE.md). Also here: the fault recorder reader with CSV and JSON export (`blackbox.py`), the rack simulator (`rack_sim.py`), frames for fuzzing a board made from the specification (`fuzz.py`) and the [compatibility table](docs/COMPATIBILITY.md) of a release, made from `spec/versions.json`; and the [status table](docs/STATUS.md) of what has run and what is still pending, made from the manifests of the repositories (`status_table.py`).
* [Free configuration of a head](docs/FREE_TOOL.md): what a rack does with a head whose ID jumpers read `0x1F`: it asks (`0x1A3`), checks the answer and uses the identity like one read from jumpers; until then the head stays in the safe state. Modelled in `rack_sim.py`, with shared vectors (`conformance/rack_vectors.json`) that the rack firmware replays.
* [Scenarios for the simulated bus](docs/BUS_SCENARIOS.md): the faults of a CAN bus in a JSON file (`urtc-scenario/1`): frames lost, repeated, reordered, delayed, lost in bursts or cut short, a node that stays silent or refuses a command with its reason, and a head in free configuration that answers `0x1A3` and `0x1A2` in different ways. `bus_scenario.py` checks the file strictly, applies it to any simulated transport and generates test scenarios from a seed; the same seed gives the same frames. Off unless asked for; the flasher and the tester run their plans against it with `--scenario` and leave an evidence record that says it was a simulation.
* **Virtual board and companion links:** `virtual_board.py` serves a board behind an SLCAN adapter on a TCP port (`python -m urtc_common.virtual_board`); type `socket://127.0.0.1:7777` where a tool asks for a serial port and the flasher, the tester and the gateway run end to end with no hardware. `sensor_frame.py` is the reference of the vision sensor frame; it and the rack serial frame are version 2, big-endian like the bus, with their vectors (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Self-update from a signed package:** `self_update.py` is the whole flow for a program that updates itself from a GitHub release, with no network and no window of its own (the caller passes the fetch and the progress): it offers only a strictly higher version with a package for the platform, downloads from the hosts of GitHub's release downloads only, checks the announced size and SHA-256 and the Ed25519 signature of `urtc-pkg/1|app|version|platform|sha256|size` against the key pinned in the program, extracts without ever leaving the folder (no `..`, absolute path, link or device), refuses to install while an operation on the bus is running, keeps the two latest releases, rolls back by itself when the first start fails and records every step. Standard library only; copied with `vendor_copy.py --set update`.
* **The "Check for updates" menu of the programs, ready to draw:** `update_service.py` holds the options (all conservative: no check unless the person asks, `auto_check` off, `require_confirmation` on, no option to skip the checksum or the signature or to add a host; settings and `URTC_UPDATE_*` variables, the environment wins and `lowering_warnings` says when a run lowers a protection), the Ed25519 key of the releases pinned with its identifier, and the steps `check` / `prepare` / `install` / `rollback`; `update_controller.py` is the state machine a window draws (checking, available, downloading, ready, installing, installed, with a progress and a coded error) and installs only after `confirm_install`; `launcher.py` runs the release `current.txt` points to and goes back to the previous one when a first start fails; `tools/make_update_package.py` builds the reproducible `.zip` / `.tar.gz` of a release with its `.sha256` and `.sig` and checks it with the pinned key. Copied with `vendor_copy.py --set update`.
* **Tools:** `generate_constants.py` writes the C header, the TypeScript module, the Python module and the table (`--check` compares), `make_conformance.py` writes the vectors (`--check`), `vendor_copy.py` copies parts into another repository with a lock file and checks the copy, and `ci_validate.py` is the shared repository check. `make_glance.py` of URTC-DOCS writes the At a glance table.
* **Installable package:** each release attaches a signed Python wheel (`urtc-common`, not on PyPI), a signed source archive and the signed generated C header, built reproducibly by `make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); the signature is the one of the releases that the programs already trust. See [the guide](docs/PACKAGE.md). `generate_canbus_doc.py` writes the reference tables of `docs/CANBUS.TXT` of the firmware repository from the specification (the prose around them is left alone, `--check` compares).

- **Evidence records and their history:** `evidence.py` writes and checks the records (`urtc-evidence/1`, [docs/EVIDENCE.md](docs/EVIDENCE.md)); `evidence_history.py` lists those of a folder, newest first, each one checked; `evidence_history_qt.py`, `qml/EvidenceHistoryDialog.qml` and `evidence_history_strings.py` (eight languages) are the History window that URTC-FLASHER, URTC-TESTER and URTC-UPDATER share (copied with `vendor_copy.py --set history_qt` and `--set history_qml`).

- **Notes of a release:** `tools/changelog_section.py VERSION [--heading] [--compat]` prints the section of the CHANGELOG of one version and, with `--compat`, the compatibility table of `docs/COMPATIBILITY.md` after it; the programs carry a copy (`vendor_copy.py --set release_notes`, with `--set compat` for the table) so that the body of their release has the same shape.

## 🧩 Role in URTC

URTC-COMMON is where the CAN protocol of the tool head is written down once, as data, so that the firmware, URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO can stop keeping four separate readings of the same prose. It holds the specification, what is generated from it, the vectors every implementation must reproduce and the transport layer the two Python tools share. By itself it changes the behaviour of none of them: each repository adopts it step by step (see docs/MIGRATION.md).

## 🏛️ Architecture

<p align="center">
  <img src="images/architecture.svg" alt="URTC-COMMON architecture: who uses it, what it holds and what it depends on" width="100%">
</p>

How the parts of this repository fit together: who uses it, what it holds and what it depends on. The picture is drawn from `docs/architecture.json` and checked against the code.

## 🚀 Quick start

**Requirements:** Python 3.10 or newer; pytest and jsonschema for the tests; Node 22.18 or newer to run the generated TypeScript against the vectors (optional)

```bash
python tools/generate_constants.py --check           # the C, TypeScript and Python files and the table are current
python tools/make_conformance.py --check             # the vectors are current
python -m urtc_common.cli conformance                # this package reproduces every vector
python tools/vendor_copy.py check TARGET --source .  # a copy in another repository was not edited and has not fallen behind
python -m pytest tests -q                            # the unit tests and the comparison with the repositories next to this one
python -m mypy                                       # the type check of urtc_common and urtc_ui
```

## 🧪 Testing

The suite has 1398 tests (`python -m pytest tests -q`). They check the specification against its schema, the generated C, TypeScript and Python files against what the generators write, the conformance vectors in Python, in TypeScript with Node and in C with a host compiler, the SLCAN codec and the transports with fakes, the virtual board, the signed self-update flow, and the comparison with the repositories checked out next to this one. A few tests skip where an optional tool (Node, a C compiler, PySide6) or a neighbouring repository is missing. `python -m mypy` type-checks the package.

## 🏗️ Build & Release

`build.sh` / `build.bat` install the package and run the tests; `build-test.sh` / `build-test.bat` check without changing any version; `run.sh` / `run.bat` start the command line (`conformance`, `describe`, `decode`, `slcan`). Each release attaches a signed Python wheel (`urtc-common`, not on PyPI), a signed source archive and the signed generated C header, built reproducibly by `tools/make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); see [the package guide](docs/PACKAGE.md).

## 📂 Repository Structure

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of URTC-COMMON" width="100%">
</p>

<details>
<summary>Text version of the tree</summary>

```text
URTC-COMMON/
├── spec/                                            the specification, tool profiles, versions and the catalog of texts
├── src/urtc_common/                                 the Python package: protocol, SLCAN, transports, virtual board, self-update
├── tools/                                           generators with --check, vendor_copy.py and the shared CI checks
├── docs/                                            contracts, format, migration guide and generated tables
├── conformance/                                     the shared vectors
├── generated/                                       C header, TypeScript module and vector headers
├── firmware_base/                                   C parts the firmware repositories share
├── qml/                                             Qt Quick windows the programs share
├── tests/                                           unit tests and the comparison with sibling repositories
├── .github/                                         CI workflow, issue and pull-request templates
├── images/                                          banner and the pictures of this README
├── build.sh build.bat                               build scripts
├── build-test.sh build-test.bat                     build and test scripts that change nothing in the repository
├── test.sh test.bat                                 run the tests
├── run.sh run.bat                                   start the program
├── urtc.project.json                                manifest: version, role, maturity and build command
├── CHANGELOG.md                                     what changed in each version
├── SECURITY.md SUPPORT.md LICENSE                   security policy, support and license
├── NOTICE                                           licenses of the third-party parts it carries
├── CONTRIBUTING.md CODE_OF_CONDUCT.md               how to contribute and the code of conduct
├── .gitattributes .gitignore                        Git settings
├── bump_version.py bump_manifest_version.py         scripts that raise the version
└── pyproject.toml requirements-dev.lock ruff.toml   package, locked tools and lint settings
```

</details>

## 🗺️ Roadmap & Known limits

**Known limits today**

* Nothing here has run against a board or a CAN adapter: the transports are tested with fakes, and the specification says for every identifier which implementations define it, so the gaps are visible.
* The firmware and the transports keep their own copies of the protocol until each one migrates; only URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO use this repository today.
* The tests that compare the specification with the other repositories read their text when those are checked out next to this one, and skip when they are not.

**Next**

* Move each repository onto the specification step by step ([migration guide](docs/MIGRATION.md)).

## 🌍 Languages

README and texts exist in English, Spanish, French, Italian, German, Chinese, Japanese and European Portuguese.

## 🔗 Related Projects

URTC is made of independent repositories, each with its own version, tests and README. This is the family, by group:

* **URTC Tool Platform:**
  * [URTC](https://github.com/JuanenRac/URTC) - firmware of the tool-head board (25 tool profiles, CAN bootloader) and the CAN protocol reference.
  * **URTC-COMMON** (this repository) - the CAN protocol written once as data (specification, generated tables, conformance vectors) and the code the programs share.
  * [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER) - desktop tool that updates the board firmware over CAN or over SWD/JTAG.
  * [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY) - gateway in front of the CAN bus: lets only listed identifiers through, limits their rate and asks for a session key.
  * [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK) - hardware-independent C logic and command protocol for a tool rack with pre-heating and lifecycle tracking.
  * [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER) - desktop live CAN-bus tester that shows the controls and telemetry of the tool profile a board reports.
  * [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL) - sensor-frame protocol in C and a Python thermal/RGB companion for an inspection tool head.
  * [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO) - browser app that flashes and tests the board over Web Serial and SLCAN, with nothing to install.
* **Ecosystem Operations:**
  * [URTC-DEVTOOLS](https://github.com/JuanenRac/URTC-DEVTOOLS) - the shared repository tools of the family as one versioned set, with a lock file that tells a copy that was edited from one that fell behind.
  * [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS) - architecture, interfaces, security baseline and generated catalogue of the ecosystem, plus the tools that compare all repositories.
  * [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER) - desktop tool that detects, installs and updates the repositories of the URTC family, one explicit action at a time.

**Sister projects (independent, with the same base and tools):**

* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - sister project: the documentation hub of HYDRA-UMC, an independent ecosystem that shares this one's base and tools
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - sister project: the documentation hub of A.R.M.O.R., the security ecosystem, also independent and on the same base
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - the profile and the status dashboard of all the ecosystems

## 📚 Documentation

Where to read more:

* [Contracts: what each implementation must do, and the known gaps](docs/CONTRACTS.md)
* [Specification format and how to change it](docs/SPEC_FORMAT.md)
* [Migration: how each repository adopts it](docs/MIGRATION.md)
* [Protocol table: every identifier and who implements it](docs/PROTOCOL_TABLE.md)
* [Several tool heads on one bus](docs/MULTINODE.md)
* [Changelog of this repository](CHANGELOG.md)
* [License (GPL-3.0-or-later)](LICENSE)
* Questions, ideas and reports: electrohobby3d@gmail.com

## 🤝 Contributing & Community

* Before a pull request run `URTC_CI=1 python tools/ci_validate.py`: it must pass. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).
* The README exists in eight languages: a change to the text is made in all eight files, and the sections shared with other repositories are written by `tools/readme_sections.py` of URTC-COMMON.
* Do not describe as working on a board what has only been built.
* Report a vulnerability privately: [SECURITY.md](SECURITY.md). Questions, ideas and reports: electrohobby3d@gmail.com ([SUPPORT.md](SUPPORT.md)).

## 👤 AUTHOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENSE

GPL-3.0-or-later - see [LICENSE](LICENSE).
