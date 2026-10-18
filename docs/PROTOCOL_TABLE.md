<!--
GENERATED from spec/can_protocol.json by tools/generate_constants.py - do not edit by hand.
-->

# Protocol table

Every identifier of `spec/can_protocol.json`, one row each. **Dir**: H>B host to board, B>H board to host, both. **DLC**: the length rule of the layouts (request / response). **Implemented by**: F firmware, L URTC-FLASHER, T URTC-TESTER, W URTC-WEB-STUDIO; a dot means that implementation does not define the identifier.

| ID | Name | Dir | DLC | Tools | F L T W | Notes |
|---|---|---|---|---|---|---|
| `0x095` | IMPACT_EVENT | B>H | 1 | 11 | `F . T W` |  |
| `0x100` | GLOBAL_STATUS | H>B | 8 | any | `F . T W` |  |
| `0x110` | QUERY_ACTIVE_TOOL | H>B | any | any | `F . T W` |  |
| `0x111` | ACTIVE_TOOL_RESP | B>H | 4-6 | any | `F . T W` |  |
| `0x120` | MOTION_CMD | H>B | 5 | 0,1,2,3,6,7,12,16 | `F . T W` |  |
| `0x130` | SOLDER_SETPOINT | H>B | 2 | 0 | `F . T W` |  |
| `0x131` | SOLDER_FEEDER_RESET | H>B | 4 | 0 | `F . T W` | magic solder_feeder_reset |
| `0x132` | SOLDER_FEEDER_POS | both | any / 4 | 0 | `F . T W` |  |
| `0x135` | SOLDER_TELEMETRY | B>H | 2 | 0,19 | `F . T W` |  |
| `0x140` | DRILL_CMD | H>B | 2 | 5 | `F . T W` |  |
| `0x145` | VACUUM_TELEMETRY | B>H | 3 | 4 | `F . T W` |  |
| `0x147` | DRILL_TELEMETRY | B>H | 3 | 5 | `F . T W` |  |
| `0x150` | AOI_CMD | H>B | 3 | 8 | `F . T W` |  |
| `0x155` | AOI_TELEMETRY | B>H | 1 | 8 | `F . T W` |  |
| `0x160` | LASER_CMD | H>B | 2 | 9 | `F . T W` |  |
| `0x165` | LASER_TELEMETRY | B>H | 1 | 9 | `F . T W` |  |
| `0x170` | PRINTER_THERMAL_MOTION | H>B | 6 | 10 | `F . T W` |  |
| `0x173` | PRINTER_LAYERFAN_CMD | H>B | 1 | 10 | `F . T W` |  |
| `0x175` | PRINTER_HOTEND_TELEMETRY | B>H | 2 | 10 | `F . T W` |  |
| `0x177` | PRINTER_LAYERFAN_RPM | B>H | 2 | 10 | `F . T W` |  |
| `0x178` | PRINTER_HOTENDFAN_CMD | H>B | 1 | 10 | `F . T W` |  |
| `0x179` | PRINTER_HOTENDFAN_RPM | B>H | 2 | 10 | `F . T W` |  |
| `0x180` | EXPANSION_SPI_REQ | H>B | 2-8 | any | `F . T W` |  |
| `0x181` | EXPANSION_SPI_RESP | B>H | 2-8 | any | `F . T W` |  |
| `0x182` | EXPANSION_DIAG0_REQ | H>B | any | any | `F . T W` |  |
| `0x183` | EXPANSION_DIAG0_RESP | B>H | 1 | any | `F . T W` |  |
| `0x190` | FRAM_QUERY | H>B | any | any | `F L T W` |  |
| `0x191` | FRAM_STATE_RESP | B>H | 8 | any | `F L T W` |  |
| `0x192` | ERASE_FRAM | H>B | 4 | any | `F L T W` | magic erase_fram |
| `0x1A0` | SET_EXPANSION_TYPE | H>B | 1-8 | any | `F L . W` |  |
| `0x1A1` | EXPANSION_TYPE_RESP | both | any / 1 | any | `F L T W` |  |
| `0x1A2` | SET_FREE_TOOL | H>B | 1-8 | any | `F L . W` |  |
| `0x1A3` | FREE_TOOL_CONFIG_RESP | both | any / 2 | any | `F L T W` |  |
| `0x1A4` | SET_DEVICE_SERIAL | H>B | 1-8 | any | `F L . W` |  |
| `0x1A5` | PERIPHERAL_INFO_RESP | both | any / 2 | any | `F L T W` |  |
| `0x1A6` | SET_MLX_VARIANT | H>B | 1-8 | any | `F L . W` |  |
| `0x1A7` | MLX_VARIANT_RESP | both | any / 1 | any | `F L T W` |  |
| `0x1A8` | BLACKBOX_QUERY | H>B | 1-8 | any | `F . . .` | no host implements it |
| `0x1A9` | BLACKBOX_CHUNK | B>H | 8 | any | `F . . .` | no host implements it |
| `0x1AA` | THERMAL_STATS_QUERY | H>B | any | any | `F . T .` |  |
| `0x1AB` | THERMAL_STATS_RESP | B>H | 8 | any | `F . T .` |  |
| `0x1B0` | ELECTROMAGNET_CMD | H>B | 1 | 13 | `F . T W` |  |
| `0x1C0` | SPOT_WELD_CMD | H>B | 3 | 14 | `F . T W` |  |
| `0x1D0` | UV_CURING_CMD | H>B | 1 | 18 | `F . T W` |  |
| `0x1E0` | HOTAIR_CMD | H>B | 3 | 19 | `F . T W` |  |
| `0x1F0` | CRIMPING_CMD | H>B | 5 | 21 | `F . T W` |  |
| `0x200` | ULTRASONIC_WELD_CMD | H>B | 3 | 24 | `F . T W` |  |
| `0x210` | SLAVE_ENTER_BOOTLOADER | H>B | 4 | any | `F L . W` | magic enter_bootloader |
| `0x211` | SLAVE_START_UPDATE | H>B | 8 | any | `F L . W` |  |
| `0x212` | SLAVE_HMAC_CHUNK | H>B | 8 | any | `F L . W` |  |
| `0x213` | SLAVE_DATA | H>B | 1-8 | any | `F L . W` |  |
| `0x214` | SLAVE_END_UPDATE | H>B | 8 | any | `F L . W` |  |
| `0x215` | SLAVE_STATUS | both | any / 1 | any | `F L . W` |  |
| `0x216` | SLAVE_PROGRESS | both | any / 1 | any | `F L . W` |  |
| `0x217` | SLAVE_VERSION_RESP_1 | both | any / 8 | any | `F L . W` |  |
| `0x218` | SLAVE_VERSION_RESP_2 | B>H | 2 or 5 | any | `F L . W` |  |
| `0x219` | SLAVE_VERIFY_FAIL_REASON | both | any / 1 | any | `F L . W` |  |
| `0x220` | SLAVE_REG_WRITE | H>B | 2-8 | any | `F . . .` | no host implements it |
| `0x221` | SLAVE_REG_READ | both | 2 / 1-8 | any | `F . . .` | no host implements it |
| `0x230` | PASTE_JETTING_CONFIG | H>B | 3 | 23 | `F . T W` |  |
| `0x231` | PASTE_JETTING_PULSE | H>B | 3 | 23 | `F . T W` |  |
| `0x240` | ADS1115_CONFIG | H>B | 2 | 17 | `F . T W` |  |
| `0x241` | ADS1115_TRIGGER | H>B | any | 17 | `F . T W` |  |
| `0x242` | ADS1115_RESULT | both | any / 2 | 17 | `F . T W` |  |
| `0x243` | FLYING_PROBE_BASIC | B>H | 2 | 17 | `F . T W` |  |
| `0x250` | THERMAL_TRIGGER | H>B | any | 22 | `F . T W` |  |
| `0x251` | THERMAL_STATUS | both | any / 1 | 22 | `F . T W` |  |
| `0x252` | THERMAL_RAW_CHUNK_REQ | H>B | 1 | 22 | `F . T W` |  |
| `0x253` | THERMAL_RAW_CHUNK | B>H | 8 | 22 | `F . T W` |  |
| `0x254` | THERMAL_CAL_CHUNK_REQ | H>B | 1 | 22 | `F . T W` |  |
| `0x255` | THERMAL_CAL_CHUNK | B>H | 8 | 22 | `F . T W` |  |
| `0x7E9` | VERSION_PATCH_RESPONSE | B>H | 3-8 | any | `F L T W` |  |
| `0x7F0` | ENTER_BOOTLOADER | H>B | 4 | any | `F L . W` | magic enter_bootloader |
| `0x7F1` | START_UPDATE | H>B | 8 | any | `F L . W` |  |
| `0x7F2` | DATA | H>B | 1-8 | any | `F L . W` |  |
| `0x7F3` | PAGE_ACK | B>H | 4 | any | `F L . W` |  |
| `0x7F4` | END_UPDATE | H>B | 8 | any | `F L . W` |  |
| `0x7F5` | STATUS | B>H | 1-2 | any | `F L . W` |  |
| `0x7F6` | HEARTBEAT | B>H | 2 | any | `F L . W` |  |
| `0x7F7` | HMAC_CHUNK | H>B | 8 | any | `F L . W` |  |
| `0x7F8` | QUERY_VERSION | H>B | any | any | `F L T W` |  |
| `0x7F9` | VERSION_RESPONSE | B>H | 8 | any | `F L T W` |  |
| `0x7FA` | BOOTLOADER_VERSION_RESPONSE | B>H | 3 | any | `F L . W` |  |
| `0x7FB` | QUERY_ERROR_COUNTERS | H>B | any | any | `F L . W` |  |
| `0x7FC` | ERROR_COUNTERS_RESPONSE | B>H | 2 | any | `F L . W` |  |
| `0x7FD` | AUTHORIZE_DOWNGRADE | H>B | 4 | any | `F L . W` | magic authorize_downgrade |
| `0x7FE` | READBACK | both | any / 4 (size) / 1-8 (data) | any | `F L . W` |  |
| `0x7FF` | READBACK_PAGE_ACK | H>B | 4 | any | `F L . W` |  |

88 identifiers, 26 tool values, 23 slave registers, 4 magic payloads.

## Multinode extension

Several tool heads on one bus. Status: **designed not implemented in firmware**. These identifiers are not in the table above; the firmware does not implement them and no hardware test exists. See `docs/MULTINODE.md`.

| ID | Name | Dir | DLC | Notes |
|---|---|---|---|---|
| `0x400` | MN_DISCOVER | H>N | 2 | Ask every node to announce itself |
| `0x401` | MN_SELECT | H>N | 3 | Select the one node that the single-head frames address |
| `0x402` | MN_SAFE_STOP | H>N | 1 | Ask every node to enter its safe state |
| `0x420`-0x43F | MN_NODE_INFO | N>H | 8 | A node announces itself (identifier plus the node address) |
| `0x440`-0x45F | MN_NODE_STATUS | N>H | 4 | Periodic status of one node |
| `0x460`-0x47F | MN_NODE_CMD | H>N | 2-8 | One command to one node without selecting it |
| `0x480`-0x49F | MN_NODE_RESP | N>H | 2-8 | The answer of one node to NODE_CMD |
