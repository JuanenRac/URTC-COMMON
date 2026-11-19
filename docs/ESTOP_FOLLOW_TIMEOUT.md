# Configurable silence of the master (ESTOP_FOLLOW)

A head with the ESTOP_FOLLOW feature on goes back to its safe state when it is ready and hears no new heartbeat of the master of the emergency stop
for a while. That while is `ESTOP_ALIVE_TIMEOUT_MS`, 100 ms. It can now be set per head, inside hard limits. A head nobody configured behaves exactly as
before.

## The constants (spec/can_protocol.json)

| Name | Value | Meaning |
|---|---|---|
| `ESTOP_ALIVE_TIMEOUT_MS` | 100 ms | The default, used when nothing is configured or the configured value is rejected |
| `ESTOP_ALIVE_TIMEOUT_MIN_MS` | 20 ms | Lowest accepted value |
| `ESTOP_ALIVE_TIMEOUT_MAX_MS` | 500 ms | Highest accepted value |

Why these limits. The bus can lose or delay a frame; below 20 ms a single late heartbeat
latches a healthy head (nuisance stops that teach operators to bypass the function). Above 500 ms a tool can run half a second after the master died,
which is longer than the stop time a laser, a spindle or a heater is expected to have. Both numbers are conservative and live in the specification, not in
the code of any one side.

## Rules

1. Not set (or 0): the default, 100 ms.
2. A value inside 20 to 500 ms is taken as it is.
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

## Not done yet

- The way the master announces its value on the wire is not defined: the heartbeat on 0x001 has no free byte and a new frame kind would be taken as a
  stop by the heads that exist. The logic (`set_master_timeout`, `EstopFollow_SetMasterTimeout`) is ready and tested; the frame that feeds it needs a
  decision about the protocol of the stack.
- Reading the value in use back from a head over the bus is waiting for the same decision.
- Nothing here has run on a board. This is not a certified safety function and never replaces a hardware emergency stop.
