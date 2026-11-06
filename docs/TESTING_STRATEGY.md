# Testing strategy: property-based tests and mutation checks of the security validators

The decisions that keep an unsigned or foreign firmware image out (the rotation of the signing key, the policy `ed25519_only`, the rollback rules, the parsers of headers and frames) are tested three ways: hand-written cases, shared conformance vectors, and the property-based tests described here.

## Property-based tests

`tests/test_property_validators.py` states rules that must hold for every input and checks them on generated cases. The cases come from a small generator with a fixed seed (`random.Random`), so a run is the same on every machine, nothing is installed to run it, and the whole file takes a few seconds. The rules:

| Module | Rule checked on generated inputs |
| --- | --- |
| `key_rotation` | a fingerprint that is not announced is never accepted; the previous key is valid exactly until the window ends and not one second longer; a window of zero (or less) and a clock that reads before the start accept only the current key; a revoked key is never accepted and a revoked current key leaves nothing trusted; at most two fingerprints, never a repeat; the status parser accepts exactly the 7-byte frames with a known flag set |
| `image_auth` | under `ed25519_only` an image is accepted only with a valid signature of a trusted key, whatever the HMAC result says, whatever bytes the record holds and in whatever combination the keys are given; a signature does not move to another payload, header, counter or hardware id; the rollback counter and the version rules hold for any floor; `hmac_only` never moves the counter; wrong lengths and unknown policies are refused; the default policy is `ed25519_only` |
| `image_header` | the parser never raises, accepts only a header it could have written, and any bit changed inside the header or the payload is seen |
| `frame_layer` | the length and range limits of the rack and sensor frames, the trailing bytes after a frame, a missing or changed byte |

## Mutation checks (local only)

Mutation testing changes the code of a module in small ways (a `<` for a `<=`, a constant, a condition) and runs the tests: a change the tests do not notice is a behaviour nobody checks. It is a measure of the tests, not a part of the build: it is **not** run in the CI, and a run takes several minutes. To repeat it, in a throwaway virtual environment (mutmut needs a runner that maps every failing exit code to 1, because mutmut 2 counts only the exit code 1 as a kill):

```
python -m pip install "mutmut<3" pytest
mutmut run --paths-to-mutate src/urtc_common/key_rotation.py --runner "python runner.py tests/test_property_validators.py tests/test_key_rotation.py"
mutmut results
```

| Module | Mutants | Killed by the first run | Killed after the added tests | Left |
| --- | --- | --- | --- | --- |
| `key_rotation.py` | 88 | 70 (79.5 %) | 85 (96.6 %) | 3, none relevant |
| `image_auth.py` | 100 | 95 (95 %) | 98 (98 %) | 2, none relevant |

The tests added after the first run check the fields of the status frame one flag at a time, the clamp of the seconds left, the defaults and immutability of a `Rotation`, the behaviour of `hmac_only` with a stale record, the reinstall of the same version and the error texts. The mutants that remain are equivalent changes (a `<=` for a `<` on a window of zero gives the same answer, a slice that ends past the end of the payload, the starting value of a variable that every branch overwrites) or a change to a type annotation, which nothing at run time reads.

## Software benches of the family (what runs without a board)

Every program of the family that would otherwise need a board, a rack or a sensor can be run against a simulator, and the continuous integration of its repository does so on every push. The run says nothing about the electronics, the timing of the interrupts or a real adapter; the manifest of each repository says `simulator` as its evidence and nothing is marked as run on a board.

| Repository | The simulator | How to start it | What the CI runs |
|---|---|---|---|
| `URTC-COMMON` | `virtual_board` (a tool head behind an SLCAN adapter on a TCP port), `rack_sim` (the rack), `heater_sim`, `multinode_sim`, `bus_scenario` (a bus that loses, repeats, delays and cuts frames, with a seed) | `urtc-virtual-board --port 7777`, then `socket://127.0.0.1:7777` where a port is asked for | the unit tests and the conformance vectors against the C code |
| `URTC` | the virtual board of the application and the twin of the bootloader of the master (the real C compiled for the host, with the sanitizers) | `python tools/fuzz_virtual_board.py`, `python tools/bootloader_twin.py --check`, or `urtc-virtual-board --firmware-repo DIR [--firmware-bootloader]` | both, as a step of their own, and inside the unit tests |
| `URTC-TESTER` | the simulated head and `--scenario` for a faulty bus; replay of recordings | `python urtc_tester.py --cli selftest --transport simulate [--scenario FILE]` or `--transport replay` for a recorded trace (see `docs/HEADLESS.md`) | its tests, which also reach the virtual board of the firmware |
| `URTC-FLASHER` | the mock transport and `--scenario`; the twin of the bootloader | `python urtc_flasher.py --cli --transport mock --file FIRMWARE [--scenario FILE]` | its tests, including an update through the real bootloader of the master |
| `URTC-SMART-RACK` | the virtual rack (`tests/virtual_rack.c`: the real rack logic behind a text port) | `python tools/rack_bench.py` | 17 scenarios and two seeded random runs with injected faults, compared step by step with `rack_sim` |
| `URTC-VISION-TOOL` | the virtual sensor link (`tests/virtual_sensor.c`: the real receive path behind a text port) | `python tools/sensor_bench.py` | 15 scenarios and two seeded random runs with injected faults, compared step by step with a reference written from the rules of the link |
| `URTC-GATEWAY` | the virtual board of this package, behind an SLCAN bus | the tests set it up; by hand, `python -m urtc_common.virtual_board --port 7777` and `urtc-gateway run --bus socket://127.0.0.1:7777` | a peer with a session key sends frames over TCP: one is answered by the board, a wrong key, a replayed counter and the order to enter the bootloader are refused |

The benches of the rack and of the sensor link read their scenarios from code, write any of them as a script (`--dump DIR`) and play a recorded script back (`--replay FILE`). The bench of the rack imports `urtc_common.rack_sim` (set `URTC_COMMON_SRC` to this repository's `src`), so a change to the model that the firmware does not follow fails the CI of the rack, and the other way round.

## Builds on this PC

A test or a tool that needs a C compiler, WSL, Cargo, Gradle or an npm build asks `urtc_common.local_build` first. It may build on a CI runner (`CI` or `GITHUB_ACTIONS` set) or when the developer sets `ALLOW_LOCAL_BUILD=1`; anywhere else it reports that the build was skipped (never that it passed) and says how to allow it. The file is one text for the family: `tools/vendor_copy.py sync TARGET --set local_build` copies it and `check` keeps the copies honest.
