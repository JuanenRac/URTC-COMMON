# Configurable silence of the master (ESTOP_FOLLOW)

A head with the ESTOP_FOLLOW feature on goes back to its safe state when it is ready and hears no new heartbeat of the master of the emergency stop
for a while. That while is `ESTOP_ALIVE_TIMEOUT_MS`, 100 ms. It can now be set per head, inside hard limits. A head nobody configured behaves exactly as
before.

## The constants (spec/can_protocol.json)

| Name | Value | Meaning |
|---|---|---|
| `ESTOP_ALIVE_TIMEOUT_MS` | 100 ms | The default, used when nothing is configured or the configured value is rejected |
| `ESTOP_ALIVE_TIMEOUT_MIN_MS` | 40 ms | Lowest accepted value |
| `ESTOP_ALIVE_TIMEOUT_MAX_MS` | 500 ms | Highest accepted value |

Why these limits. The bus can lose or delay a frame; below 40 ms a single late heartbeat
latches a healthy head (nuisance stops that teach operators to bypass the function). Above 500 ms a tool can run half a second after the master died,
which is longer than the stop time a laser, a spindle or a heater is expected to have. Both numbers are conservative and live in the specification, not in
the code of any one side. The silence check of the head runs every 20 ms, so the real silence is the configured value plus up to 20 ms; with a
minimum of 20 ms that was up to twice the value, with 40 ms it is at most half as much again, which is why 40 ms is the lowest value.

## Rules

1. Not set (or 0): the default, 100 ms.
2. A value inside 40 to 500 ms is taken as it is.
3. A value outside the limits is rejected: the default is used and the status says `rejected` (a warning). It is never accepted in silence and never clamped.
4. If the master announces its own value, the head uses the LOWER of the two. The head is never more tolerant than its own configuration: a master
   value above the head's changes nothing; a lower one shortens the silence. When the two differ the status says `master differs` (a warning).
   A master value outside the limits is ignored (status `master rejected`).
5. The value in use is the one every decision of the head reads: the release check ("the master was heard within the timeout") and the silence check.

## Where each side takes the value

| Side | Source of the configured value |
|---|---|
| Python reference and host twins (`urtc_common.estop_follow`, the copies in the flasher and the tester, the virtual board) | `Node(alive_timeout_ms)`; from a configuration mapping with the key `estop_alive_timeout_ms` (`timeout_from_config`) |
| Head firmware (`fw_estop_follow.h`) | `EstopFollow_SetTimeout(n, requested_ms)`, fed by the record of the persistent switches in F-RAM (bytes 0 and 1 of its reserved area, little endian; 0 = default) |

The decisions are the same on both sides: `tools/make_estop_vectors.py` writes the tables (`timeout_config`, `timeout_master`) and the scenarios with a
configured and an announced timeout, and the firmware replays them.

## Status codes

| Code | Name | Meaning |
|---|---|---|
| 0 | ok | The configured value, or the default when none was set, is in use |
| 1 | rejected | The configured value was outside the limits; the default is in use |
| 2 | master differs | The master announced another value; the lower of the two is in use |
| 3 | master rejected | The master announced a value outside the limits; it is ignored |

## On the bus (0x1AE and 0x1AF)

The value is written and read over the CAN bus with the two frames of the optional switches. Nothing changes for a host that does not know the new forms:
the old lengths and the old queries behave exactly as before. Every 16-bit field is big endian, like the rest of the protocol (the F-RAM record keeps it
as two bytes, low byte first).

| Frame | Form | Meaning |
|---|---|---|
| 0x1AE, DLC 5 or 6 | as before | Sets the switches. The stored silence is kept. |
| 0x1AE, DLC 8 | `FEAT`, mask, second mask, `estop_timeout_ms` (u16) | Sets the switches and the silence. 0 clears it (the default applies); otherwise 40 to 500. Any other value: the whole frame is ignored, nothing is stored, nothing is answered. |
| 0x1AF, empty or any byte except 2, 3 and 4 | as before | Three-byte answer. |
| 0x1AF, one byte `02` | as before | Six-byte answer. |
| 0x1AF, one byte `03` | new | Eight-byte answer: the six bytes, then the silence IN FORCE (0 while ESTOP_FOLLOW is not running). |
| 0x1AF, one byte `04` | new | Eight-byte answer with the silence STORED in the record (0 = the default). |
| 0x1AE, DLC 8 accepted | | Answered with the eight-byte form carrying the stored silence. |

Like the switches, a written silence is in force after the next power-up; the query `03` shows what is running and `04` what will run.

The heartbeat on 0x001 is not touched: it has no free byte and a new kind of frame would be taken as a stop. The master announces its value by answering the
eight-byte query: the host (or a tool that watches the bus) reads the value of the master and the one of the head and applies the rule of the lower one
(`effective_timeout`). The firmware of a head does not act on an answer it hears from another board by itself, because an answer carries no identity of its sender.

A host must ask the user before it writes the silence and never writes it while a firmware update is in progress. The twin of the decisions is in
`urtc_common.estop_follow` (`parse_features_write`, `query_form`, `encode_timeout_answer`); the vectors are in `conformance/estop_follow_vectors.json`
(`feature_writes`, `feature_queries`, `timeout_answers`).

## Not done yet

- A head does not shorten its own silence by itself from an announcement heard on the bus (see above); the logic (`set_master_timeout`, `EstopFollow_SetMasterTimeout`) is ready and tested.
- Nothing here has run on a board. This is not a certified safety function and never replaces a hardware emergency stop.
