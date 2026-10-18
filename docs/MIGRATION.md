<!--
=============================================================================
URTC-COMMON - docs/MIGRATION.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Migration

Nothing in the other repositories uses URTC-COMMON yet. This page is the order in which each one can adopt it, one step at a time, with every step leaving that repository green and able to stop there.

## Why a copy and not a dependency

URTC-FLASHER and URTC-TESTER are packaged with PyInstaller, URTC-WEB-STUDIO is a static web app, the firmware is built on its own, and none of them should fail to build because another repository moved. So a client carries a **copy** of the parts it needs, written by `tools/vendor_copy.py` together with a lock file, and a check makes that copy impossible to neglect.

```text
python tools/vendor_copy.py sync  TARGET --set python --set vectors   # copy and write urtc_common.lock.json
python tools/vendor_copy.py check TARGET --lock-only                  # in the client: was a copy edited by hand?
python tools/vendor_copy.py check TARGET --source ../URTC-COMMON      # with a checkout: did the copy fall behind?
```

The sets are `python` (the package files), `typescript`, `c`, `vectors` and `tool` (the script itself, so a client can run `check` without a checkout of this repository). `--only NAME` copies single files and `--as NAME` keeps an older file name for a single file.

## How `check` keeps the copies equal

1. **A copy cannot be edited by hand.** The lock holds the SHA-256 of every file (line endings normalised). `check --lock-only` runs in the CI of the client, needs nothing else, and fails with "edited by hand" if a copied file changed.
2. **A copy cannot fall behind unnoticed.** `check --source` compares each file with the one in a checkout of this repository and fails with "behind URTC-COMMON". It runs in the nightly workflow of URTC-DOCS, which already fetches every repository of the ecosystem next to it, and by hand before a release.
3. **An implementation cannot drift from the specification unnoticed.** `tests/test_siblings.py` in this repository reads the text of the firmware and of the three host tools and fails when an identifier, a magic payload, a tool table, a status code, a length check, a limit or a register stops agreeing with the specification. It skips when those repositories are not next to this one, and it is never a build dependency of any of them.
4. **A change of the protocol fails everywhere at once.** The vectors are the same file in every client, so one wrong byte in a vector fails each migrated repository's own test run, in its own language.

A client therefore needs only one line in its CI (`check --lock-only`) and one test that runs the vectors; the rest is automatic.

## Order

Every step is small, adds a test before it removes code, and is worth keeping on its own.

### 1. The vectors (all four clients)

1. In the client: `python /path/to/URTC-COMMON/tools/vendor_copy.py sync tests/fixtures --set vectors --as can_conformance_vectors.json` (URTC-WEB-STUDIO: target `src/lib`, `--as canConformance.vectors.json`).
2. Nothing else changes: the file holds the nine sections the client already runs, unchanged, plus the new ones. The client's existing test keeps passing; add `check` to its CI.
3. Optionally run the new sections (`frames_encode`, `frames_decode`, `frames_rejected`, `slcan_stream`, `identifiers_all`) with the client's own reader. For a Python client: `urtc_common.conformance.check_all()`; for the web app: `tests/ts/run_vectors.mjs` shows how.

### 2. The identifiers and magic payloads (URTC-FLASHER, URTC-TESTER, URTC-WEB-STUDIO)

1. Copy the generated module: `--set python --only protocol.py` into a package folder of the client (for example `urtc_can/`), or `--set typescript` into `src/lib/generated/`.
2. Add a test that every constant the client defines today equals the generated one. This is what `tests/test_siblings.py` already does from the outside; inside the client it makes the change a one-line diff.
3. Replace the hand-written values by aliases of the generated ones, keeping the client's own names (`client_names` in the specification lists them): `CAN_ID_SLAVE_VERSION_RESP_1 = protocol.CAN_ID_SLAVE_VERSION_RESP_1`. Delete the literal magic bytes (`bytes([0xB0, 0x07, 0x1D, 0x5A])`) in favour of `protocol.MAGIC_ENTER_BOOTLOADER`.
4. The identifiers a client lacks (see the table in [`CONTRACTS.md`](CONTRACTS.md)) are added only when the client needs them. The four that no host implements stay unimplemented until they have a reason and, for `0x220` and `0x221`, an allow-list.

### 3. The firmware (URTC)

1. Copy `urtc_can_ids.h` into the firmware sources (`--set c`). Its names carry a `URTC_` prefix, so it can sit beside the existing `#define`s.
2. Add a host-compiled test with one `_Static_assert` per identifier that the firmware defines by name (`CAN_ID_ENTER_BOOTLOADER == URTC_CAN_ID_ENTER_BOOTLOADER`, and so on). It emits no code, so it cannot change a binary.
3. Replace the literals in the dispatcher (`rxHeader.StdId == 0x120`) by the generated names only when the two binaries built before and after are byte-identical. Compare the `.bin` files; if they differ, the change is not what it was meant to be.
4. Later: a C table of the vectors, so that the firmware's own host tests run the same bytes as the three other implementations.

### 4. The transports (URTC-FLASHER, then URTC-TESTER)

The two Python tools each keep a copy of the SLCAN, SocketCAN (and, in the flasher, python-can and simulated) transports. They had diverged: each had fixes the other lacked. `urtc_common.transports` is the merge with every fix applied once.

1. Copy the package files (`--set python`) into `urtc_can/`.
2. Make `flasher_transports.py` (or `tester_transports.py`) a thin module that re-exports `SLCAN`, `SocketCAN`, `PythonCAN`, `MockCAN`, the error classes and the helpers, so the GUI and the tests keep importing what they import today. Pass `translate=` to `SocketCAN` to keep the warnings in the tool's own languages.
3. Run the tool's whole test suite. Its existing tests are the specification of the behaviour that must not change. The behaviour differences are listed below; any test that depended on one of them is a decision, not a surprise.
4. URTC-TESTER keeps its bus-statistics decorator (`_instrument_with_bus_stats`) around the imported classes; the classes have the same methods.
5. Delete the old class bodies in the same commit that adds the re-export.

**Behaviour differences of the merged transports** (each takes the fix that one of the two copies already had):

| Where | Flasher copy | Tester copy | Merged |
|---|---|---|---|
| SLCAN write | no lock | lock, typed error | lock, typed error |
| SLCAN read of a failed port | raw serial exception | typed error | typed error |
| SLCAN receive buffer on open | kept | cleared | cleared |
| SLCAN line with a status character in front | frame found | line dropped | frame found |
| SLCAN non-ASCII noise | ignored bytes | line dropped | line dropped |
| SLCAN transmit in listen-only | allowed | refused | refused |
| SLCAN buffer over 4096 bytes | whole buffer dropped | whole buffer dropped | dropped only while it holds no complete line |
| SocketCAN failed bind | socket closed | socket left open | socket closed |
| SocketCAN full transmit queue | retried five times | error at once | retried five times |
| SocketCAN read error | logged | pause, not logged | logged and a short pause |
| Clock | wall clock | monotonic clock | monotonic clock |

### 5. Frame builders (URTC-TESTER, URTC-WEB-STUDIO)

1. URTC-TESTER: express each function of `advanced_protocol.py` as a call of the matching generated `encode_*`, keeping the function as a wrapper that translates its labels (`"forward"`, `"night"`) into values. The ranges are the same as the ones it enforces today; the vectors say so.
2. URTC-WEB-STUDIO builds the per-tool frames inside React components, so they cannot be compared with anything yet. First move them into plain functions (a condition that stays in force whatever is generated), then replace those functions by the generated `encode*` ones, and run `tests/ts/run_vectors.mjs`-style checks against the shared file.

### 6. What stays for later

* `sequences/*.json`: the full frame trace of an update, of each verification failure, of a read-back whose size is not a multiple of eight, and of a version query with and without the patch frame, so that the simulated board is generated from them instead of being a second reading of the prose.
* A C table of the vectors for the firmware's host tests.
* A TypeScript SLCAN codec generated from the `slcan` section (the web app has its own today).
* Deciding whether the specification replaces the prose as the reference (the prose would then be generated from it) or the prose stays the reference and a scan of its `ID:` headers only watches. `tests/test_siblings.py` already performs that scan, and it is the reason the identifier the prose lists only in a summary is not missed.

## Rollback

Every step above is a copy plus a test. To undo one, restore the old file and delete the lock: nothing in this repository changes, and no client depends on a version of it.
