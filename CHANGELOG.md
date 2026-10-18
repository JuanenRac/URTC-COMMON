# Changelog: URTC-COMMON 🧩

All notable changes to this project will be documented in this file. The
version number follows this ecosystem's "odometer" scheme: PATCH +1 on
every real build, rolling into MINOR past 9 (`0.0.9` -> `0.1.0`); MAJOR is
bumped manually only. See `bump_version.py`.

## [0.0.3] - Multinode design and shared interface helpers

- docs/MULTINODE.md designs several tool heads on one CAN bus: the node address from the five identity jumpers, a new identifier block 0x400-0x49F that clashes with nothing, discovery, selecting the one active node, per-node status and command frames, bus load at every supported bitrate, failure modes, safety rules and the impact on each repository. It is a design: the firmware does not implement it and nothing was tried on hardware.
- spec/can_protocol.json gains an optional multinode section (backward compatible, marked designed and not implemented in firmware); the schema, the C header, the TypeScript module, the Python module and docs/PROTOCOL_TABLE.md are regenerated from it.
- New conformance/multinode_vectors.json, written by tools/make_multinode_vectors.py with an independent packer, and tests that reproduce every vector, check that no identifier clashes with the single-head protocol and refuse out-of-range node addresses.
- New urtc_common.multinode: node address from the jumpers, frame length and worst-case bus load, discovery timing and a node table that tracks liveness, selection and address conflicts.
- New urtc_ui package with logic the desktop programs can share and that needs no Qt: the eight-language list and a selector model, status badges, and formatting of identifiers, bitrates, frames, sizes and durations, with tests. The programs do not use it yet.
- The READMEs in eight languages list the multinode design and the interface helpers.

## [0.0.2] - Generated module adopted by the clients

- The generated TypeScript module passes the strict type check: versionCompare no longer indexes a tuple with a loop variable.
- The sibling tests read an identifier that a program takes from the generated module (X = protocol.X in Python, generated.X in TypeScript) as the value of that module, so a program that adopted the module is still compared with the specification.
- docs/MIGRATION.md records that URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO carry the generated module and the shared vectors, each with its lock file and a test that fails when a copy is edited by hand or falls behind.
- The specification no longer marks 0x1A8 and 0x1A9 as missing from the prose (the firmware documentation describes them now), and records that URTC-TESTER reads the version patch frame 0x7E9; docs/PROTOCOL_TABLE.md and docs/CONTRACTS.md follow, and the comparison with the prose expects every identifier to be described.
- The comparison with URTC-WEB-STUDIO reads the list of verify-fail reason codes that the web studio words in its locales, instead of an English table.
- docs/CONTRACTS.md says that the source of the firmware has a closed list of slave registers for 0x220 and 0x221 that no built binary includes yet.
- bump_manifest_version.py prints URTC instead of the name of another ecosystem.

## [0.0.1] - The CAN protocol as data

- **Specification:** `spec/can_protocol.json` (format 1, with its JSON Schema) describes all 88 identifiers of the tool-head bus: direction, who handles each, the tools it is valid for, the length rule and the typed layout of every request and response, the gates (critical error, boot sequence, magic payload), the watchdog and telemetry timing, 16 enumerations, 37 constants, the four magic payloads, the 23 registers of the expansion slave, the version procedures and the SLCAN subset. Every entry records which of the firmware, URTC-FLASHER, URTC-TESTER and URTC-WEB-STUDIO define it, so the gaps are explicit: `0x220`, `0x221`, `0x1A8` and `0x1A9` exist in the firmware and in no host (the last two are not in the protocol prose either), and `0x220`/`0x221` carry a note about the missing allow-list.
- **Generated code:** `tools/generate_constants.py` writes a C header, a TypeScript module and a Python module from the specification, with the constants, the tables and one pure builder and one pure parser per layout, and `docs/PROTOCOL_TABLE.md`. `--check` writes nothing and fails when a file is out of date. Builders refuse an out-of-range value, a value outside a closed enumeration and a wrong magic payload instead of clamping them; parsers report a byte that older firmware does not send as absent, never as zero.
- **Conformance vectors:** `conformance/can_vectors.json` keeps the nine sections that the flasher, the tester and the web studio already share, unchanged, and adds an encode and a decode vector for every layout, the legacy short forms, the encodes that must be refused, the full identifier list and SLCAN byte streams (extended frames, remote frames, glued status characters, noise, a split line). `tools/make_conformance.py` writes them with a packer of its own, independent of the generated encoder, and checks the hand-written example bytes of the specification against it.
- **Python package:** `urtc_common` holds the SLCAN codec (strict hexadecimal, standard data frames only), a classic-frame type, the version and quick-state readers, a runner for the vectors and a small command line. The transports (SLCAN serial, SocketCAN, python-can and a simulated board, plus listen-only bitrate detection) are extracted from the two copies the flasher and the tester kept and merged so that each fix of either copy applies once; they take their serial port, socket and python-can module as parameters, so they are tested with fakes.
- **Comparison with the other repositories:** `tests/test_siblings.py` reads the text of the firmware, the flasher, the tester and the web studio, when they are checked out next to this repository, and fails when an identifier, a magic payload, a tool or status table, a length check, a gate, a limit, a register or the list of identifiers of the protocol prose stops agreeing with the specification. It skips when they are absent: nothing depends on those repositories.
- **Copies for other repositories:** `tools/vendor_copy.py` copies chosen parts into another repository with a lock file of SHA-256 sums, and its `check` fails when a copy was edited by hand or fell behind. Nothing in the other repositories uses it yet; `docs/MIGRATION.md` lists the order in which each can.
- **Documents:** `docs/CONTRACTS.md` (the contract, who implements what, the known gaps and differences, the rules for change), `docs/SPEC_FORMAT.md`, `docs/MIGRATION.md` and the generated `docs/PROTOCOL_TABLE.md`; the README in eight languages.
- **CI:** the baseline workflow runs the shared validation, the generator checks and the tests on Linux and Windows; a nightly workflow runs the comparison with every repository of the ecosystem fetched next to this one.
