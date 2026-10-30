<!--
=============================================================================
URTC-COMMON - docs/FREE_TOOL.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Free configuration of a tool head

A tool head reads five ID jumpers. The readings `0x00` to `0x18` name a tool profile, `0x19` to `0x1E` name nothing, and `0x1F` (all five jumpers installed) is the **free configuration**: the head does not say which tool it is, because its firmware takes the tool from a register of its own F-RAM (`0x1A2` writes it, `0x1A3` reports it).

For the head this is a fixed behaviour: with no valid register it falls back to the safe, inert state. This page fixes what the **rack** (and any other program that reads heads by their jumpers) does with such a head. A rack must not take `0x1F` for "no tool" and must not guess a tool: it asks the head, checks the answer and uses the identity with the same flow as a head read from jumpers.

## The rules

1. **Classify the jumper reading** (bits above the fifth are ignored): `0x00`..`0x18` is a **direct** tool; `0x1F` is **free**; `0x19`..`0x1E` is **invalid** and is never asked anything.
2. **A free head has no identity until it answers.** Its slot holds no tool, so every target for it is refused (tool not racked) and the pre-heat plan orders nothing. A silent or invalid head is the safe state, not "a head without a tool".
3. **The query is `0x1A3`** (host to head, any payload, ignored). The answer is two bytes: the raw jumper reading and the **selection** (`0` = not set, `1`..`25` = tool id plus one). `0x1A2` is the write and is never used to ask.
4. **An answer is valid** when it has at least two bytes, the first one is `0x1F` (a head whose jumpers read anything else is not in free mode) and the second one is `1`..`25`. The tool is the selection minus one (`0x00`..`0x18`). Everything else names no tool: selection `0`, `26`..`255`, a short answer, another jumper reading. Extra bytes are ignored.
5. **Timing** (four values, held in a configuration structure, never in the logic):

   | Value | Default | Meaning |
   |---|---|---|
   | `query_timeout_ms` | 250 | how long one query waits for the answer |
   | `max_attempts` | 3 | queries of one round, the first one included (0 counts as 1) |
   | `retry_backoff_ms` | 2000 | pause after a round without a valid answer, before the next round |
   | `refresh_period_ms` | 5000 | while resolved, ask again this often; 0 = never |

   A round is up to `max_attempts` queries, each one waiting `query_timeout_ms`. A round without a valid answer leaves the head invalid for `retry_backoff_ms` and then starts again, for as long as the head sits in the slot. Any answer that arrives (also one nobody asked for, such as the answer to a write) is used.
6. **Events.** The first valid answer **resolves** the head. The same tool again **confirms** it. Another tool is a **change of tool**: the slot takes the new tool with no pre-heat target, exactly as when a head is swapped. An invalid answer, or a whole round of silence, **withdraws** the identity (the slot is emptied, any target goes) and the back-off applies.
7. **Time wraps.** Deadlines are compared with unsigned arithmetic, so a round that crosses the wrap of the millisecond counter behaves like any other.

## What the head does today

The head reads its F-RAM register once, at boot. A selection written with `0x1A2` reaches the answer of `0x1A3` after the next power cycle of the head. The refresh of the rack therefore notices a change made by swapping the head, or made and then restarted; a change that needs no restart is a change of the head's firmware, not of this contract.

## Where it is checked

* `src/urtc_common/rack_sim.py`: `classify_jumper`, `parse_free_tool_reply`, `FreeToolConfig`, `FreeToolResolver`, and in `SimulatedRack` `set_slot_jumpers`, `free_tool_step` and `slot_identity`.
* `conformance/rack_vectors.json` (key `free_tool`) and `generated/rack_vectors.h`: the default timing, every jumper reading, the answers that name a tool and the scenarios of the query (answer at once, silence and back-off, late answer, unset or foreign answers, refresh, hot change, withdrawal, refresh switched off, one attempt per round, wrap of the clock). The rack firmware repository replays them against its own code.
* `tests/test_free_tool.py`: the model against the vectors, and the behaviour of the slots.
