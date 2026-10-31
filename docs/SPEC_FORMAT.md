<!--
=============================================================================
URTC-COMMON - docs/SPEC_FORMAT.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Specification format

`spec/can_protocol.json` is the data; `spec/can_protocol.schema.json` is its JSON Schema (draft-07) and `tests/test_spec.py` checks both the schema and rules the schema cannot express. This page describes format **1**.

## Top level

| Key | Meaning |
|---|---|
| `format` | The shape of this file. Raised when a key is removed, renamed or changes meaning. |
| `protocol_version` | The version of the protocol itself. |
| `byte_order` | `big`: every multi-byte field. |
| `clients` | The four implementations that `implemented_by` talks about: `firmware`, `flasher`, `tester`, `web_studio`. |
| `groups` | Display order and titles of the groups of identifiers. |
| `tools` | The tool profiles: `id`, `name`, `title`. 0 to 24, and 25 for no tool assigned. |
| `enums` | Named sets of values, see below. |
| `constants` | Named numbers with a title, a group (`protocol` or `timing`) and optionally a unit. |
| `magic_payloads` | Name, identifier (and `also_on`), the four bytes as hex, a title. |
| `registers` | Registers of the expansion slave: `slave_bootloader` and `slave_application`. |
| `procedures` | The version query, the minor field and the version order, in words and data. |
| `slcan` | The SLCAN subset: rules, commands, bitrate codes, buffer limit. |
| `messages` | One record per identifier, sorted by identifier. |
| `rack` | The two CAN frames of the tool rack, apart from `messages` (see below). Optional for a reader; added without raising `format`. |
| `multinode` | The extension that lets several heads share a bus (see `MULTINODE.md`). |

## The rack section

`rack` holds what the tool rack (URTC-SMART-RACK) puts on the bus. It is not part of `messages` because the tool head does not answer these identifiers and the counts the other documents quote (96 identifiers) are those of the head.

| Key | Meaning |
|---|---|
| `range` | `first` and `last`: the block of identifiers `0x260` to `0x26F` reserved for the rack. Every frame of the section is inside it and no message of the head is. |
| `constants` | `RACK_*` numbers (the command code of the pre-heat order, the tool byte that means no tool, the length of the reply). |
| `reply_reasons` | The codes of byte 2 of the reply, each with a `kind` (`acknowledgement` or `refusal`) and a title. Codes are contiguous from 0; the order is the one of the firmware (`rack_reply_code_t`). |
| `frames` | `0x260` `SET_PREHEAT` (host to rack, 8 bytes) and `0x261` `REPLY` (rack to host, 3 bytes: the command answered, the tool byte, the reason). A frame has a `layout` like the layouts of a message, so the generators give it `encode_rack_*` and `decode_rack_*` and the conformance vectors cover it. |

The generated code names the identifiers `RACK_ID_SET_PREHEAT` and `RACK_ID_REPLY` (in C, `URTC_RACK_ID_*`); the prefix `CAN_ID_` stays for the messages of the head. A gateway forwards `0x261` towards the network and refuses `0x260` and `0x261` towards the bus. `tests/test_rack_frames.py` checks that no identifier of any group (messages, rack, multinode ranges, magic payloads, free-tool pair, bootloader) is also one of another.

## A message

```json
{
  "id": "0x120",
  "name": "MOTION_CMD",
  "group": "motion",
  "title": "Plain stepper move (direction and step count)",
  "direction": "host_to_board",
  "handled_by": "application",
  "tools": [0, 1, 2, 3, 6, 7, 12, 16],
  "gates": {"blocked_by_critical_error": true, "blocked_during_boot_sequence": true},
  "firmware_accepts_dlc": {"min": 5, "max": 8},
  "layouts": [ ... ],
  "implemented_by": {"firmware": true, "flasher": false, "tester": true, "web_studio": true},
  "client_names": {"tester": "CAN_ID_MOTION_CMD", "web_studio": "CAN_ID_MOTION_CMD"}
}
```

| Key | Meaning |
|---|---|
| `name` | The canonical name. Generated constants are `CAN_ID_<name>`. Unique. |
| `direction` | `host_to_board`, `board_to_host`, or `both` (the same identifier is a query and its answer). It agrees with the roles of the layouts. |
| `handled_by` | `application`, `bootloader`, or `both` (answered by whichever is running). |
| `tools` | `"any"`, or the tool ids for which the identifier is valid. For the tool commands this is what the firmware routing table sends to the handler. |
| `gates` | `blocked_by_critical_error` (`false` for the few frames the firmware still processes during a critical error), `blocked_during_boot_sequence`, `needs_magic` (a name from `magic_payloads`). |
| `answers`, `answered_by` | The question an answer belongs to, and the answers to a question. |
| `timing` | `period_ms` of automatic telemetry, `watchdog_ms` of a command that must be repeated. |
| `firmware_accepts_dlc` | The length check the firmware really makes, when it differs in form from the layout. |
| `documented_in_prose` | `false` for an identifier that exists in the firmware and in no prose. Absent otherwise. |
| `read_only` | A query without side effects. |
| `implemented_by` | Whether each implementation **defines or handles** the identifier. Read from their sources by the comparison tests. |
| `client_names` | The constant each implementation calls it, when it differs from the canonical one. |
| `notes` | Sentences that do not fit a key. |

## A layout

A layout is one shape of payload. A message has one layout, or several when the identifier is a query and its answer, or when the answer has forms told apart by length.

```json
{
  "role": "request",
  "dlc": {"exact": 5},
  "fields": [{"name": "direction", "type": "u8", "offset": 0, "width": 1, "enum": "motion_direction", "strict_enum": true},
             {"name": "steps", "type": "u32", "offset": 1, "width": 4}],
  "examples": [{"name": "forward 1000 steps", "fields": {"direction": 1, "steps": 1000}, "data": "01000003E8"}],
  "decode_cases": [{"name": "four bytes (older firmware)", "data": "0A000100"}]
}
```

* `role`: `request` (the host sends it) or `response` (the board sends it). `variant` (optional) tells apart several responses of one identifier, for example the `size` and the `data` frames of a read-back.
* `dlc` is one of `{"exact": n}`, `{"min": a, "max": b}`, `{"one_of": [a, b]}` or `{"any": true}`.
* `frames` marks a payload that is split over that many consecutive frames, concatenated in order.
* `examples` are the source of the generated vectors. `data` is optional hand-written hex; when present the generator compares it with its own packer and refuses a disagreement.
* `decode_cases` are payloads for the decode vectors only (short and legacy forms).
* The generated function names come from the message name in lower case, plus `_request`, `_response` and the variant when the message has several layouts: `encode_motion_cmd`, `decode_readback_response_size`.

## A field

| Key | Meaning |
|---|---|
| `name`, `offset`, `width` | Position in the payload. Offsets are contiguous. |
| `type` | `u8`, `u16`, `u24`, `u32`, `i16`, `i32` (big-endian) or `bytes`. |
| `range` | `[min, max]` the builders accept. Narrower than the type when the protocol or the firmware says so. |
| `enum`, `strict_enum` | The enumeration the values come from; with `strict_enum` the builders refuse any other value. |
| `unit` | A unit for people. |
| `fixed` | A `bytes` field with one allowed value (a magic payload). The builder fills it in. |
| `optional` | The field is absent in older firmware. The parser returns `None` for it, never zero. |
| `present_from_dlc` | The payload length from which an optional field is present, when it is not simply its own end. |
| `length`, `rest`, `derived_length_of` | A `bytes` field of fixed length, one that takes the rest of the payload, or one whose length is given by an earlier `u8` field (that field is then computed by the builder). |
| `note` | A sentence about the field. |

## Adding or changing an identifier

1. Edit `spec/can_protocol.json`. Give every layout at least one example; put hand-written `data` on the ones that matter for safety.
2. Run `python tools/generate_constants.py`, then `python tools/make_conformance.py`.
3. Run `python -m pytest tests -q`. A new identifier fails the statistics test on purpose; update the numbers it quotes and the ones in [`CONTRACTS.md`](CONTRACTS.md).
4. If the change is not additive, raise `format` or `protocol_version`, the schema and the changelog together. A new optional section (as `multinode` and `rack` were) is additive: `format` and `protocol_version` stay, and the schema, the changelog and this page say so.
5. Each migrated repository then runs its own `check` and picks the new copy up (see [`MIGRATION.md`](MIGRATION.md)).

The values under `implemented_by` and `client_names` are not guessed: `tests/test_siblings.py` reads the other repositories and fails when they stop agreeing, so an implementation that gains or loses an identifier shows up as a failing test here.
