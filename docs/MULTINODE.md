# Several tool heads on one bus (multinode)

**Status: implemented in the URTC firmware behind a switch that is off by default; tested on the host only, not on boards.** With the switch off the firmware answers as one head per bus, exactly as before. With it on, the node side below is what the firmware does (main application 0.3.8). No board has run it, and nothing in it has been tried on hardware. The flasher, the tester and the web studio carry a window that finds the heads and selects one (`urtc_common.node_picker`); it has been tried against the model only. What exists is the specification (`multinode` in `spec/can_protocol.json`), the generated constants and builders (C, Python, TypeScript), conformance vectors (`conformance/multinode_vectors.json`), host-side helpers with tests (`urtc_common.multinode`), scenarios of one node written by hand (`conformance/multinode_scenarios.json`, also as the C tables `generated/multinode_scenarios.h`), a model of nodes and of a bus that joins them (`urtc_common.multinode_sim`), a host session that finds the heads, selects one and refuses to send to one it has not confirmed (`urtc_common.multinode_host`) and, in the firmware repository, the node logic (`multinode.c`) with its host suite (`tests/test_multinode.c`), which replays the same scenarios. Where a statement below says what a node does, the firmware implements it; the sections on the switch and on what the firmware decided say how.

The block `0x260` to `0x26F` belongs to the tool rack (`rack` in the specification), below the first identifier of this extension (`0x400`); no frame of the extension is in it.

## The switch

The extension is off unless a persistent record in the board's F-RAM says otherwise. The default is off, and a blank, erased, zeroed, damaged or missing record reads as off, so a board that was never configured behaves as a single head and every frame and identifier of the single-head protocol is unchanged (the firmware's host suite checks all 2048 identifiers).

* `0x1AC` sets it: the four magic bytes `4D 4E 4F 44`, `enable` (0 or 1) and `instance`. `0x1AD` reads it: the stored value, the value in force, the instance and the node address. Both identifiers are in the single-head table (`SET_MULTINODE`, `MULTINODE_CONFIG_RESP`).
* The setting is read once at boot, so a change acts after the next power-up.
* While the extension is on, `0x1AC` reaches only the selected node, like every other single-head frame. While it is off, any host can switch it on; the protection is the same as for the other persistent settings (a magic payload against corrupted frames), not authentication, because the CAN bus has none (see the threat model in the firmware repository). Keep the bus closed.
* The record is its own F-RAM region (address 960, 8 bytes with a CRC-8), so the saved-state record and its version do not change.

## Goals and limits

* Several tool heads (each with its own URTC board) share one CAN bus and one host adapter.
* The single-head protocol keeps its identifiers and meaning. A bus with one head and a host that knows nothing of this extension behaves as it does today.
* The board's microcontroller keeps authority over its tool: it enforces its own limits, watchdogs and fault handling whatever the bus says (see Safety rules).
* One tool is active at a time. Several heads can be connected, announced and monitored at once; at most one is driven by single-head commands.
* Not a goal: a second bus per head, real-time guarantees across nodes, or addressing by anything other than the five identity jumpers (plus a serial for tie-breaking).

## Addressing

The firmware reads five identity jumpers (ID0 to ID4) once at boot. They give the tool address, 0 to 31. The extension reuses that value as the **node address** (5 bits, `MN_ADDRESS_MASK` = 31).

Consequences, stated plainly:

* Two heads of different tool types always have different addresses. Two heads of the same tool type have the same address and are a **conflict** until one is given another identity; the jumpers cannot tell them apart.
* The announcement carries `instance` (a number the board stores, for a second head of one type) and the device `serial`. The host tells two boards on one address apart by the serial. A node that detects the conflict sets `CONFLICT` in its state and ignores commands. A conflict is reported, never resolved silently.
* Address 31 is the free-configuration address: it is a valid node address like the others.

## Identifier layout

Everything new lives in `0x400`-`0x49F`. The single-head protocol uses `0x095`-`0x255` and `0x7E9`-`0x7FF`, so nothing collides (a test checks this against the specification). A lower identifier wins arbitration, so the order below is also the priority order.

| Identifier | Name | Dir | Payload |
|---|---|---|---|
| `0x400` | DISCOVER | host to all | `mn_version`, `slot_ms` |
| `0x401` | SELECT | host to all | `action` (0 deselect all, 1 select), `node`, `seq` |
| `0x402` | SAFE_STOP | host to all | `reason` |
| `0x420`+node | NODE_INFO | node to host | `tool`, `state`, `instance`, `mn_version`, `serial` (u32) |
| `0x440`+node | NODE_STATUS | node to host | `state`, `error`, `uptime_s` (u16) |
| `0x460`+node | NODE_CMD | host to one node | `func` (u16, a single-head identifier), up to 6 argument bytes |
| `0x480`+node | NODE_RESP | node to host | `func` (u16), up to 6 data bytes |

All multi-byte fields are big-endian, like the rest of the protocol. `state` is a set of flags: `SELECTED` 0x01, `FAULT` 0x02, `CONFLICT` 0x04, `BOOTLOADER` 0x08.

Within a range the node address is the low five bits, so a lower address wins arbitration: node 0 beats node 31. Within the extension, SAFE_STOP wins over every node frame.

## Discovery and enumeration

1. The host sends DISCOVER (`mn_version` = 1, `slot_ms` = 2 by default).
2. Each node answers with NODE_INFO after `address x slot_ms`, which spreads at most 32 answers over about 62 ms. Even when a frame takes longer than a slot (slow bitrates) the answers cannot corrupt each other: they have different identifiers and arbitration serialises them.
3. The host waits `discover_window_ms` (about 64 ms at 125 kbit/s and above, about 434 ms at 10 kbit/s) and builds a table (`urtc_common.multinode.NodeTable`).
4. Each node also sends NODE_INFO once when it starts and NODE_STATUS every second (`MN_STATUS_PERIOD_MS`). A node with no status for `MN_NODE_TIMEOUT_MS` (3.5 s) is treated as gone.
5. Two boards on one address send the same identifier with different data. That is a bit error on the data bits for both; each then sets `CONFLICT`, and the host sees a NODE_INFO with the conflict flag or a serial that changes.

### Compatibility with a host that does not know the extension

A node starts in **legacy mode**: it listens for 1.5 s after power-up. If it hears no other node's NODE_INFO or NODE_STATUS, it behaves exactly as a single head does today (it counts as selected). If it hears another node, it starts **unselected** and waits for SELECT. A host that does not know the extension therefore keeps working with one head, and with two it gets one head answering at most, never two answering the same query.

## Selecting the active node

Single-head frames (`0x100`-`0x255`, and the bootloader frames `0x7F0`-`0x7FF`) have no address. They are obeyed only by the **selected** node:

* SELECT with `action` = 1 and a node address selects that node and deselects the others. `seq` lets a host tell its own acknowledgement (the node's next NODE_STATUS shows `SELECTED`) from an older one.
* A selection lapses after `MN_SELECT_TIMEOUT_MS` (2 s) unless the host repeats SELECT. A host that dies leaves no node selected.
* Unselected nodes ignore every single-head identifier, including `0x7F0` (enter bootloader), `0x7F8` (query version). A firmware update therefore begins with SELECT, and the update tools must confirm `SELECTED` in the status before sending anything destructive.
* NODE_CMD is the short form for one small command to one node without selecting it: `func` is the single-head identifier, the arguments are up to 6 bytes. Commands with longer payloads, or that need a multi-frame exchange (firmware update, readback, thermal and black-box transfers), use SELECT and the single-head frames.

## Per-node frames: bus load

A classic data frame with an 11-bit identifier is 47 bits plus 8 per data byte, plus up to one stuff bit per four bits of the stuffed part. NODE_STATUS (4 bytes) is 79 bits, or 95 bits in the worst case. Worst-case load of the periodic traffic, one status frame per node per second (computed by `urtc_common.multinode.bus_load`):

| Bitrate | 1 node | 8 nodes | 32 nodes | Discovery answers of 32 nodes, back to back |
|---|---|---|---|---|
| 10 kbit/s | 0.9 % | 7.6 % | 30.4 % | 432 ms |
| 20 kbit/s | 0.5 % | 3.8 % | 15.2 % | 216 ms |
| 50 kbit/s | 0.2 % | 1.5 % | 6.1 % | 86 ms |
| 100 kbit/s | 0.1 % | 0.8 % | 3.0 % | 43 ms |
| 125 kbit/s | 0.1 % | 0.6 % | 2.4 % | 35 ms |
| 250 kbit/s | below 0.1 % | 0.3 % | 1.2 % | 17 ms |
| 500 kbit/s | below 0.1 % | 0.2 % | 0.6 % | 9 ms |
| 800 kbit/s | below 0.1 % | 0.1 % | 0.4 % | 5 ms |
| 1 Mbit/s | below 0.1 % | 0.1 % | 0.3 % | 4 ms |

The existing single-head traffic (telemetry about every 100 ms, motion commands) comes on top and is not included. At 10 and 20 kbit/s a full bus of 32 nodes leaves little room; use a lower node count or a faster bitrate there. These are arithmetic estimates, not measurements.

## Failure modes

| Failure | What happens |
|---|---|
| Two boards on one address | Both set `CONFLICT`, ignore commands, keep announcing; the host refuses to command that address and shows both serials. |
| A node disappears | No status for 3.5 s: the host marks it gone and stops commanding it. If it was selected, the selection has lapsed on its own. |
| The host disappears | Selections lapse in 2 s. Each node's own watchdog (`WATCHDOG_MS`) puts its tool in the safe state, as today. |
| Two nodes report `SELECTED` | The host treats it as no selection (`NodeTable.selected` returns none), sends SELECT with `action` = 0, and checks again. |
| A SELECT is lost | The node stays as it was; the host sees no `SELECTED` in the status and repeats. Nothing is sent to the old node meanwhile. |
| Bus-off or error passive on one node | The node leaves the bus under CAN rules; the others continue. The host sees it as gone. |
| A host that predates the extension | Legacy mode (above). |
| A node with a fault | `FAULT` in its state and its error code in NODE_STATUS; the host does not command it. The node's own fault handling is unchanged. |

## Safety rules

1. **The microcontroller keeps authority.** Limits, interlocks, thermal protection, the watchdog and the critical-error gate run on the board and cannot be bypassed by any frame. A command that the board would refuse in single-head mode is refused in multinode mode.
2. **One active tool.** Only the selected node obeys single-head commands. A host must not send a motion, heating or actuation command to a node it has not confirmed as selected and alive.
3. **SAFE_STOP only moves toward safety.** A node always obeys it by entering its safe state (heaters off, motion stopped, outputs released). No frame of the extension leaves the safe state; the node leaves it through its own conditions and the normal commands.
4. **No broadcast of anything destructive.** Enter-bootloader, erase and update frames are never broadcast and are obeyed only by the selected node, with the existing magic payloads and signature checks unchanged.
5. **A conflict or a latched fault refuses commands** at the host and at the node.
6. **No claim without a test on hardware.** Until a board runs this, the extension is host-tested only.

## What the firmware decided

The design left some points open. The firmware does this:

* **Listening window.** A node that has just started listens for `MN_LEGACY_LISTEN_MS` (1.5 s). It obeys no single-head frame in that window. A node that hears another node's `NODE_INFO` or `NODE_STATUS` becomes unselected; one that hears nobody becomes the one head on the bus (legacy mode, treated as selected, with no lapse).
* **Conflict.** A node never receives its own frames, so a frame on its own `NODE_INFO` or `NODE_STATUS` identifier can only come from another board. The node latches `CONFLICT`, puts its tool in the safe state once, ignores commands, cannot be selected and keeps announcing until the next power-up.
* **Serial.** The 32-bit serial in `NODE_INFO` is a fold of the 96-bit unique device ID of the microcontroller.
* **`NODE_CMD`.** The firmware answers only `func` `0x110` (the status query) with a `NODE_RESP` that carries the six bytes of `0x111`. Any other `func` is ignored, so this short form never actuates.
* **Safe state.** `SAFE_STOP` (and a conflict) sets the setpoints to zero, stops stepping, releases the heater and PWM outputs and locks the laser interlock, the same outputs the bootloader-entry command forces before it resets, but without latching the critical-error flag. A lapsed or withdrawn selection does not by itself switch an output off: each tool's own communication watchdog acts as in single-head mode (the electromagnet and the hotend fan keep their state on purpose).
* **Telemetry.** A node that is not selected sends no single-head telemetry. The collision frame `0x095` of the scan probe is an event and is sent whatever the selection.
* **Extended identifiers** are ignored while the extension is on.
* **Bootloader.** The bootloaders do not take part. Their frames reach only the selected application node, and `SELECT` comes first in an update.
* **`seq`** of `SELECT` is recorded and not otherwise interpreted.

## Impact by repository

| Repository | Change when the design is implemented | Done now |
|---|---|---|
| URTC (firmware) | Read the address into the node state; implement legacy-mode listening, DISCOVER, SELECT with timeout, NODE_INFO/STATUS/CMD/RESP, SAFE_STOP; ignore single-head identifiers when unselected; conflict detection; host tests and a two-board bench test. | The node side, behind the switch, with host tests that replay the shared scenarios. The two-board bench test is not done. |
| URTC-COMMON | Specification, generated constants and builders, vectors, host helpers. | Yes (this repository), with the model of nodes and the host session (`multinode_sim`, `multinode_host`) that the programs below can copy with `vendor_copy.py --set multinode`. |
| URTC-FLASHER | Discover and list nodes; SELECT and confirm before every update; never flash an unselected or conflicting node. | The window that finds the heads and selects one (`node_picker`, set `node_picker`), a gate that refuses single-head frames while several heads are on the bus and none is confirmed, the texts in the eight languages and a section of the quick guide. Tried against the model only. |
| URTC-TESTER | Node list and a node chooser in the bus monitor; per-node status; test one node at a time. | The same window and gate as the flasher. Per-node status in the bus monitor is not done. |
| URTC-WEB-STUDIO | Same node list over WebSerial; SELECT before the update; show the notice when more than one node answers. | The same list, confirmation, states and notices in TypeScript, held to the same vectors. Tried against a model of the bus only. |
| URTC-SMART-RACK | Uses its own serial link now; join the bus as a node only when its board exists. | Nothing. |
| URTC-VISION-TOOL | Reuses the thermal tool profile; one node among others; large transfers need SELECT. | Nothing. |
| HYDRA-UMC adapter | Carry the extension identifiers through the CAN adapter; expose the node table; keep one active tool per cell. | Nothing. |

## Open points

* Settled in the firmware: `instance` is stored in the switch record and set with `0x1AC`; NODE_STATUS carries the state and the error code only.
* Still open: whether a node should also release a held output when its selection lapses; the host programs; carrying the identifiers through the HYDRA-UMC adapter.
* Bench plan: two boards on one bus with an adapter that logs frames; check legacy mode with one board, discovery with two, a forced address conflict, selection timeout, and `SAFE_STOP` against each tool profile.

## What the host programs do when the selected head is lost

While a head is being driven the host keeps its selection alive and watches the status of the head (`MultinodeHost.tick`). If the head is gone, in conflict, faulted, in its bootloader, or no longer reports itself selected, the host forgets the selection (nothing is sent to a head again until it is selected and confirmed anew), records a `Lapse` and, by default, sends `SAFE_STOP` (reason `0x10`) so that every head goes to its safe state: no output stays on without a host watching it. The windows show the reason and what was done. The release can be switched off in the window (`release_on_lapse`); then the selection is still dropped and the window says that the outputs were left as they are. A head that is about to reset into its bootloader is not a lapse: `suspend` pauses the watch until the selection is released. Whether the firmware itself should put its outputs in the safe state when a selection lapses (today each tool's own communication watchdog acts) is a decision that is still open.
