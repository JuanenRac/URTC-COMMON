<!--
=============================================================================
URTC-COMMON - docs/BUS_SCENARIOS.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Scenarios for the simulated bus (`urtc-scenario/1`)

The simulators of the family (the in-memory bootloader of the flasher, the simulated head of the tester, the virtual board, the rack model) answer every frame at once and never lose one. A real bus does not. A **scenario** is a file that says which faults the bus has, so a plan can be run against a simulator that misbehaves the same way every time, with no hardware.

* **Off by default.** Nothing changes unless a scenario is asked for: `--scenario FILE` on the command line of the tester (with its simulated head) or of the flasher (with its mock transport). The simulators behave exactly as before without it.
* **Only simulators.** The programs refuse a scenario together with a real adapter.
* **Strict.** A file with an unknown field, a value out of range, a wrong type, a key written twice or `NaN` is refused as a whole; nothing is guessed.
* **Deterministic.** Every choice comes from one generator seeded by the scenario (`seed`, or `--seed` on the command line). The same scenario and the same seed give the same frames in the same order.
* **It cannot invent.** A scenario can take frames away, repeat them, move them, shorten them, or make the node stay silent or refuse a command. It cannot make a node say that something worked: a check that the simulated node never satisfies cannot pass under any scenario the generator makes.

The code is `src/urtc_common/bus_scenario.py` (copied into the tester and the flasher by `tools/vendor_copy.py --set bus_scenario`); `FaultyBus` wraps any simulated transport.

## The file

```json
{
  "format": "urtc-scenario/1",
  "name": "lossy-and-slow",
  "description": "one answer in five is lost, the rest arrive late",
  "seed": 7,
  "faults": [
    {"fault": "drop", "direction": "rx", "per_mille": 200},
    {"fault": "delay", "direction": "rx", "min_ms": 5, "max_ms": 40}
  ]
}
```

| Field | Meaning |
|---|---|
| `format` | always `urtc-scenario/1` |
| `name` | 1 to 64 letters, digits, `.`, `_` or `-` |
| `description` | optional text, 300 characters at most |
| `seed` | optional whole number, 0 to 4294967295 (default 0) |
| `faults` | a list of at most 64 rules, applied in order (may be empty: the bus is then transparent) |

The file is 64 KiB at most.

### Fields every rule can have

| Field | Meaning |
|---|---|
| `fault` | the kind (below) |
| `direction` | `tx` (frames sent to the node), `rx` (frames that come back) or `both` (default) |
| `id` | a CAN identifier (number or `"0x1A3"`), or a list of up to 16; without it every identifier |
| `from` | skip this many matching frames first (default 0) |
| `count` | act on this many matching frames after `from` (default: all) |
| `per_mille` | chance of acting on a matching frame, 1 to 1000 (default 1000: always) |

The frames are counted per rule and per direction. A chance below 1000 takes one number from the generator of the scenario for each matching frame inside the window, so the order of the choices is fixed.

### The frame faults

| `fault` | What it does | Extra fields |
|---|---|---|
| `drop` | the frame is lost | none |
| `duplicate` | the frame arrives again | `copies` 1 to 3 (default 1) |
| `reorder` | frames are collected and released in another order | `window` 2 to 8 (default 2): a full window is released shuffled by the seeded generator; a window that has not filled when the program waits for an answer is released as it is |
| `delay` | the frame arrives later | `ms` (1 to 60000), or `min_ms` and `max_ms` together (the delay is then chosen from the generator) |
| `burst_loss` | runs of lost frames | `length` 1 to 64, optional `period` (greater than `length`): `length` frames are lost, then `period` minus `length` pass, and so on from `from`. No `per_mille`, no `count` |
| `truncate` | the frame is cut to a minimum length | `dlc` 0 to 7: only the first `dlc` bytes are kept |
| `mute` | the node does not answer | none. On `tx` the node never hears the frame, on `rx` its answers are lost. No `per_mille` |

### The node faults

They act on the frames sent to the node (no `direction`) and are answered by the bus itself.

`reject` refuses a command and says why. `id` is the command, `reason` is one of the refusals of the rack (`wrong_length`, `tool_absent`, `temp_out_of_range`, `tool_invalid`, `not_heatable`, `held_rate`, `unknown_command`), `reply_id` is the identifier the refusal is sent with (the rack contract fixes the payload, not an identifier for the CAN form, so the scenario names it). The payload is three bytes, as in the reply frame of the rack: the command answered (`cmd`, default `0x01`), the first data byte of the command it refused (`0xFF` if none) and the code of the reason. The command does not reach the node unless `"deliver": true`.

`free_tool` is a head whose ID jumpers read `0x1F` (see [FREE_TOOL.md](FREE_TOOL.md)). It answers `0x1A3` (the query) with a frame of `0x1A3` and takes `0x1A2` (the write). `answer` is what it says:

| `answer` | Frame | Valid for the rack? |
|---|---|---|
| `valid` | `0x1F`, `tool + 1` (`tool` 0 to 24) | yes |
| `unset` | `0x1F`, `0` | no |
| `foreign` | `jumper` (0 to 30), `1` | no (another jumper reading) |
| `out_of_range` | `0x1F`, `selection` (26 to 255) | no |
| `short` | `0x1F` only (a one-byte frame, shorter than the two the answer needs) | no |
| `silent` | nothing | no |

A write with `0x1A2` stores a selection (0 to 25) that becomes the answer after `FaultyBus.power_cycle()`, like the head, which reads its register once at boot; a selection above 25 is ignored. By default the write is also answered (`answer_to_write`, default true) with the answer in force. The frames of the head do not reach the node unless `"deliver": true`.

Frames the bus makes (a refusal, an answer of the head) go through the `rx` rules like any other, so a `delay` or a `drop` on `rx` also affects them.

## The generator

`generate(seed)` makes a scenario from a seed: one to four rules of the kinds asked for, with their numbers taken from the seeded generator. The same seed and the same arguments give the same scenario, and every scenario it makes is valid. `generate_suite(seed, count)` makes a list whose seeds come from `seed` in order. By default it uses the frame faults; `reject` and `free_tool` can be asked for, and a generated head never answers with a valid tool.

```
python -m urtc_common.bus_scenario generate --seed 42 --count 5 --out scenarios
python -m urtc_common.bus_scenario generate --seed 42 --kinds drop,delay,burst_loss
python -m urtc_common.bus_scenario validate scenarios/generated-1234.json
```

(In the tester and the flasher the module is `urtc_can.bus_scenario`.)

## Using a scenario

```
python urtc_tester.py --headless run-plan plans/identify_and_selftest.json --transport simulate --scenario lossy.json
python urtc_flasher.py --cli --transport mock --file firmware.bin --no-trigger --scenario lossy.json --evidence-dir evidence
```

The run writes the usual records. The result record and the `urtc-evidence/1` record say that the transport was a simulation with the scenario, its seed and what it did (`scenario lossy seed 7: delay 12, drop 3`), so the evidence of a run against a faulty bus cannot be taken for one made on a board. Exit codes are the usual ones; a scenario that is not valid is a usage error (2) and runs nothing.

What a scenario run shows is that a plan, or an update, reacts correctly when the bus misbehaves in the way the scenario describes. It does not show that a real board or a real adapter behaves that way: the simulated node and the scenario are written by the same hand.
