# =============================================================================
# URTC-COMMON - tests/test_siblings.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""What the other repositories hard-code today, compared with the specification.

These tests only READ the text of the sibling checkouts, when they sit next to this repository (or in the
folder named by URTC_WORKSPACE). When a checkout is absent the test is skipped, so nothing here is a
dependency of this repository: it is the instrument that shows a disagreement, and the reason the
specification can be trusted to describe what the implementations really do.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sources import HEX, c_defines, python_bytes, python_dict, python_ints, python_dict_keys, text, ts_array, ts_ints, ts_record

FLASHER_CONFIG = "URTC-FLASHER/flasher_config.py"
FLASHER_PROTOCOL = "URTC-FLASHER/flasher_protocol.py"
TESTER_CONFIG = "URTC-TESTER/tester_config.py"
WEB_IDS = "URTC-WEB-STUDIO/src/lib/canIds.ts"
WEB_FLASHER = "URTC-WEB-STUDIO/src/lib/flasher.ts"
WEB_LIMITS = "URTC-WEB-STUDIO/src/lib/toolLimits.ts"
FIRMWARE = "URTC/src/F303-master"
BOOT_COMMON = "URTC/src/F303-master/boot/bootloader_common.h"
VERSION_WIRE = "URTC/src/common/urtc_version_wire.h"
CANBUS = "URTC/docs/CANBUS.TXT"


def by_id(spec):
    return {int(m["id"], 16): m for m in spec["messages"]}


def firmware_source(sibling) -> str:
    root = sibling(FIRMWARE)
    parts = []
    for path in sorted(root.rglob("*")):
        if path.suffix in (".c", ".h") and "hal" not in path.parts:
            parts.append(text(path))
    return "\n".join(parts)


# ---------------------------------------------------------------------------------------------------------------------
# identifiers: who defines which, under which name
# ---------------------------------------------------------------------------------------------------------------------
def check_client(spec, found: dict[str, int], key: str):
    table = by_id(spec)
    names = {}
    for name, value in found.items():
        assert value in table, f"{key} defines {name} = 0x{value:03X}, which the specification does not have"
        names.setdefault(value, []).append(name)
    for value, listed in names.items():
        spec_name = table[value].get("client_names", {}).get(key)
        assert spec_name is not None, f"{key}: 0x{value:03X} {listed} is not recorded in the specification"
        assert spec_name in listed, f"{key}: 0x{value:03X} is called {listed}, the specification says {spec_name}"
    defined = set(names)
    claimed = {value for value, message in table.items() if message["implemented_by"][key]}
    assert defined == claimed, f"{key}: defines {sorted(defined - claimed)} that the spec says it lacks, lacks {sorted(claimed - defined)} that the spec says it has"


def test_flasher_defines_exactly_the_identifiers_the_specification_says(spec, sibling):
    check_client(spec, python_ints(sibling(FLASHER_CONFIG), "CAN_ID_"), "flasher")


def test_tester_defines_exactly_the_identifiers_the_specification_says(spec, sibling):
    check_client(spec, python_ints(sibling(TESTER_CONFIG), "CAN_ID_"), "tester")


def test_web_studio_defines_exactly_the_identifiers_the_specification_says(spec, sibling):
    found = ts_ints(sibling(WEB_IDS), "CAN_ID_")
    found.update(ts_ints(sibling(WEB_FLASHER), "CAN_ID_"))
    check_client(spec, found, "web_studio")


def test_the_firmware_bootloader_header_defines_the_identifiers_the_specification_says(spec, sibling):
    found = c_defines(sibling(BOOT_COMMON), "CAN_ID_")
    found["CAN_ID_VERSION_PATCH_RESPONSE"] = c_defines(sibling(VERSION_WIRE), "URTC_CAN_ID_VERSION_")["URTC_CAN_ID_VERSION_PATCH"]
    table = by_id(spec)
    for name, value in found.items():
        assert value in table, name
        recorded = table[value].get("client_names", {}).get("firmware")
        if recorded:
            assert recorded == name
        assert table[value]["implemented_by"]["firmware"]


def test_the_firmware_handles_every_identifier_of_the_specification_and_no_other(spec, sibling):
    source = firmware_source(sibling)
    handled = {int(v, 16) for v in re.findall(r"(?:StdId\s*[=!]=\s*|StdId\s*=\s*|case\s+)(0x[0-9A-Fa-f]{3})\b", source)}
    handled |= {int(v, 16) for v in re.findall(r"CAN_ID_[A-Z_]+\s+(0x[0-9A-Fa-f]{3})\b", text(sibling(BOOT_COMMON)))}
    handled |= {0x7E9}  # URTC_CAN_ID_VERSION_PATCH, a named constant in the shared wire header
    known = set(by_id(spec))
    assert handled - known == set(), "the firmware handles identifiers that the specification lacks"
    # identifiers answered by the bootloader or by a table lookup have no StdId comparison in the application source
    never_compared = known - handled
    answered = {v for v in never_compared if by_id(spec)[v]["handled_by"] in ("bootloader", "both") or by_id(spec)[v]["direction"] == "board_to_host"}
    assert never_compared <= answered or never_compared <= answered | {0x217}, sorted(never_compared - answered)


# ---------------------------------------------------------------------------------------------------------------------
# magic payloads
# ---------------------------------------------------------------------------------------------------------------------
def test_magic_payloads_in_the_hosts_and_the_firmware_equal_the_specification(spec, sibling):
    magic = {m["name"]: bytes.fromhex(m["data"]) for m in spec["magic_payloads"]}
    flasher = sibling(FLASHER_CONFIG)
    assert python_bytes(flasher, "ERASE_FRAM_MAGIC") == magic["erase_fram"]
    assert python_bytes(sibling(TESTER_CONFIG), "ERASE_FRAM_MAGIC") == magic["erase_fram"]
    assert ts_array(sibling(WEB_IDS), "ERASE_FRAM_MAGIC") == list(magic["erase_fram"])
    assert ts_array(sibling(WEB_IDS), "SOLDER_FEEDER_RESET_MAGIC") == list(magic["solder_feeder_reset"])
    assert ts_array(sibling(WEB_FLASHER), "AUTHORIZE_DOWNGRADE_MAGIC") == list(magic["authorize_downgrade"])
    assert ts_array(sibling(WEB_FLASHER), "ENTER_BOOTLOADER_MAGIC") == list(magic["enter_bootloader"])
    protocol = text(sibling(FLASHER_PROTOCOL))
    for name, pattern in (("enter_bootloader", r"CAN_ID_ENTER_BOOTLOADER,\s*bytes\(\[([^\]]*)\]"), ("authorize_downgrade", r"CAN_ID_AUTHORIZE_DOWNGRADE,\s*bytes\(\[([^\]]*)\]")):
        literals = [bytes(int(x, 16) for x in found.split(",")) for found in re.findall(pattern, protocol)]
        assert literals and all(literal == magic[name] for literal in literals), name
    slave = re.findall(r"CAN_ID_SLAVE_ENTER_BOOTLOADER,\s*bytes\(\[([^\]]*)\]", protocol)
    assert slave and all(bytes(int(x, 16) for x in found.split(",")) == magic["enter_bootloader"] for found in slave)


def test_the_firmware_compares_against_the_same_four_bytes(spec, sibling):
    source = firmware_source(sibling) + text(sibling("URTC/src/F303-master/boot/bootloader_protocol.c"))
    for magic in spec["magic_payloads"]:
        data = bytes.fromhex(magic["data"])
        comparison = " && ".join(f"[A-Za-z]+\\[{i}\\] == 0x{b:02X}" for i, b in enumerate(data))
        assert re.search(comparison, source, re.I), magic["name"]


# ---------------------------------------------------------------------------------------------------------------------
# tables of names and codes
# ---------------------------------------------------------------------------------------------------------------------
def test_tool_names_are_the_same_in_the_flasher_the_tester_and_the_web_studio(spec, sibling):
    titles = {t["id"]: t["title"] for t in spec["tools"] if t["id"] < 25}
    assert python_dict(sibling(FLASHER_CONFIG), "TOOL_NAMES") == titles
    # the tester and the web studio take their names from the generated tool profiles, which must carry exactly these names
    assert "tools_catalog.TOOL_NAMES" in text(sibling(TESTER_CONFIG))
    assert "URTC_TOOL_PROFILES.map(p => [p.id, p.shortName])" in text(sibling(WEB_IDS))
    tools = json.loads((Path(__file__).resolve().parents[1] / "spec" / "tools.json").read_text(encoding="utf-8"))["tools"]
    assert {t["id"]: t["short_name"] for t in tools} == titles


def test_tool_values_equal_the_firmware_enumeration(spec, sibling):
    source = text(sibling("URTC/src/F303-master/firmware_common.h"))
    found = {int(value): name for name, value in re.findall(r"^\s*TOOL_([A-Z0-9_]+)\s*=\s*(\d+)", source, re.M)}
    ours = {t["id"]: t["name"] for t in spec["tools"]}
    # the firmware calls the 3D printer TOOL_3D_PRINTER; an identifier cannot start with a digit in the generated names
    found[10] = "PRINTER_3D"
    assert found == ours


def test_bootloader_status_and_verify_reason_codes_agree_everywhere(spec, sibling):
    enums = {e["name"]: {v["value"]: v["name"] for v in e["values"]} for e in spec["enums"]}
    boot = c_defines(sibling(BOOT_COMMON))
    assert {v: n for n, v in boot.items() if n.startswith("STATUS_")} == {v: f"STATUS_{n}" for v, n in enums["bootloader_status"].items()}
    assert {v: n for n, v in boot.items() if n.startswith("VERIFY_FAIL_REASON_")} == {v: f"VERIFY_FAIL_REASON_{n}" for v, n in enums["verify_fail_reason"].items()}
    assert sorted(python_dict_keys(sibling(FLASHER_CONFIG), "STATUS_NAMES")) == sorted(enums["bootloader_status"])
    assert sorted(python_dict_keys(sibling(FLASHER_CONFIG), "VERIFY_FAIL_REASONS")) == sorted(enums["verify_fail_reason"])
    web = text(sibling(WEB_IDS))
    codes = re.search(r"VERIFY_FAIL_CODES[^=]*=\s*\[(.*?)\]", web, re.S)
    assert codes, "the web studio lists the verify-fail reason codes it can word"
    assert sorted(int(k, 0) for k in re.findall(r"0x[0-9a-fA-F]+", codes.group(1))) == sorted(enums["verify_fail_reason"])


def test_expansion_and_sensor_tables_have_the_same_number_of_entries(spec, sibling):
    enums = {e["name"]: len(e["values"]) for e in spec["enums"]}
    for path in (FLASHER_CONFIG, TESTER_CONFIG):
        source = text(sibling(path))
        assert len(re.findall(r'^\s*"\d - ', re.search(r"EXPANSION_BOARD_TYPES = \[(.*?)\]", source, re.S).group(1), re.M)) == enums["expansion_board_type"]
        assert len(re.findall(r'^\s*"\d - ', re.search(r"MLX_SENSOR_VARIANTS = \[(.*?)\]", source, re.S).group(1), re.M)) == enums["mlx_sensor_variant"]
    web = text(sibling(WEB_IDS))
    assert len(re.findall(r"^\s*'", re.search(r"EXPANSION_BOARD_TYPES = \[(.*?)\];", web, re.S).group(1), re.M)) == enums["expansion_board_type"]
    assert len(re.findall(r"^\s*'", re.search(r"MLX_SENSOR_VARIANTS = \[(.*?)\];", web, re.S).group(1), re.M)) == enums["mlx_sensor_variant"]


def test_motion_tool_sets_match_the_routing_table_of_the_firmware(spec, sibling):
    motion = {i for i in by_id(spec)[0x120]["tools"] if i != 0}
    tester = text(sibling(TESTER_CONFIG))
    assert {int(x) for x in re.search(r"MOTION_TOOL_IDS = \{([^}]*)\}", tester).group(1).split(",")} == motion
    web = text(sibling(WEB_IDS))
    assert {int(x) for x in re.search(r"MOTION_TOOL_IDS = new Set\(\[([^\]]*)\]", web).group(1).split(",")} == motion


def routed_tools(source: str) -> dict[str, set[int]]:
    routes: dict[str, set[int]] = {}
    pending: list[int] = []
    for line in source.splitlines():
        case = re.match(r"\s*case\s+(\d+):\s*(?:return\s+(CAN_ROUTE_[A-Z0-9_]+);)?", line)
        if case:
            pending.append(int(case.group(1)))
            if case.group(2):
                routes.setdefault(case.group(2), set()).update(pending)
                pending = []
            continue
        ret = re.match(r"\s*return\s+(CAN_ROUTE_[A-Z0-9_]+);", line)
        if ret and pending:
            routes.setdefault(ret.group(1), set()).update(pending)
            pending = []
    return routes


def test_the_tools_of_every_command_follow_the_dispatch_routing_of_the_firmware(spec, sibling):
    routes = routed_tools(text(sibling("URTC/src/F303-master/firmware_can_dispatch_routing.c")))
    expected = {
        0x120: ("CAN_ROUTE_MOTION_ONLY", "CAN_ROUTE_SOLDERING_AND_MOTION"), 0x130: ("CAN_ROUTE_SOLDERING_AND_MOTION",), 0x131: ("CAN_ROUTE_SOLDERING_AND_MOTION",),
        0x132: ("CAN_ROUTE_SOLDERING_AND_MOTION",), 0x140: ("CAN_ROUTE_DRILL",), 0x150: ("CAN_ROUTE_AOI",), 0x160: ("CAN_ROUTE_LASER",),
        0x170: ("CAN_ROUTE_3DPRINTER",), 0x173: ("CAN_ROUTE_3DPRINTER",), 0x178: ("CAN_ROUTE_3DPRINTER",), 0x1B0: ("CAN_ROUTE_ELECTROMAGNET",),
        0x1D0: ("CAN_ROUTE_UVCURING",), 0x1E0: ("CAN_ROUTE_HOTAIR",), 0x1F0: ("CAN_ROUTE_CRIMPING",), 0x230: ("CAN_ROUTE_PASTEJETTING",),
        0x231: ("CAN_ROUTE_PASTEJETTING",), 0x240: ("CAN_ROUTE_FLYINGPROBE",), 0x241: ("CAN_ROUTE_FLYINGPROBE",), 0x242: ("CAN_ROUTE_FLYINGPROBE",),
        0x250: ("CAN_ROUTE_THERMALINSPECTION",), 0x252: ("CAN_ROUTE_THERMALINSPECTION",), 0x254: ("CAN_ROUTE_THERMALINSPECTION",),
    }
    table = by_id(spec)
    for frame_id, names in expected.items():
        tools = set().union(*(routes[name] for name in names))
        assert set(table[frame_id]["tools"]) == tools, f"0x{frame_id:03X}: the spec says {table[frame_id]['tools']}, the routing says {sorted(tools)}"
    # the weld commands share one route, each fires only for its own tool
    assert routes["CAN_ROUTE_WELDPULSE"] == set(table[0x1C0]["tools"]) | set(table[0x200]["tools"])


def test_gates_of_the_firmware_match_the_specification(spec, sibling):
    source = firmware_source(sibling)
    gated = {int(m.group(1), 16) for m in re.finditer(r"StdId == (0x[0-9A-Fa-f]{3})[^{;]{0,160}?!boot_sequence_active", source, re.S)}
    spec_gated = {int(m["id"], 16) for m in spec["messages"] if m.get("gates", {}).get("blocked_during_boot_sequence")}
    assert gated == spec_gated, (sorted(gated ^ spec_gated))


def test_length_checks_of_the_firmware_match_the_specification(spec, sibling):
    source = firmware_source(sibling)
    table = by_id(spec)
    found = {}
    for m in re.finditer(r"StdId == (0x[0-9A-Fa-f]{3})\s*&&\s*rxHeader\.DLC\s*(>=|==)\s*(\d+)", source):
        found[int(m.group(1), 16)] = (m.group(2), int(m.group(3)))
    assert len(found) >= 30
    for frame_id, (op, n) in found.items():
        message = table[frame_id]
        rule = message.get("firmware_accepts_dlc")
        assert rule is not None, f"0x{frame_id:03X}: the firmware checks DLC {op} {n} and the spec has no firmware_accepts_dlc"
        if op == "==":
            assert rule == {"exact": n}, (hex(frame_id), rule, n)
        else:
            assert rule == {"min": n, "max": 8}, (hex(frame_id), rule, n)
    # every rule the specification records for the firmware is really in its source
    for frame_id, message in table.items():
        if "firmware_accepts_dlc" in message:
            assert frame_id in found, f"0x{frame_id:03X}: the spec records a firmware length check that the source does not have"
    # whatever the firmware accepts, the layout the hosts must send is never looser than that
    for frame_id, message in table.items():
        rule = message.get("firmware_accepts_dlc")
        if not rule:
            continue
        for layout in message["layouts"]:
            if layout["role"] != "request":
                continue
            sent = layout["dlc"]
            lowest = sent.get("exact", sent.get("min", 0))
            assert lowest >= rule.get("exact", rule.get("min", 0)) or "any" in sent, hex(frame_id)


# ---------------------------------------------------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------------------------------------------------
def test_hardware_ids_and_patch_constants_agree(spec, sibling):
    const = {c["name"]: c["value"] for c in spec["constants"]}
    flasher = python_ints(sibling(FLASHER_CONFIG))
    tester = python_ints(sibling(TESTER_CONFIG))
    assert flasher["THIS_HARDWARE_ID"] == tester["THIS_HARDWARE_ID"] == const["HARDWARE_ID_MAIN"]
    assert flasher["SLAVE_HARDWARE_ID"] == const["HARDWARE_ID_SLAVE"]
    assert flasher["PATCH_UNKNOWN"] == const["PATCH_UNKNOWN"] and flasher["PATCH_FLAG"] == const["PATCH_FLAG"]
    assert flasher["FLASH_PAGE_SIZE"] == const["FLASH_PAGE_SIZE"]
    web = ts_ints(sibling(WEB_FLASHER))
    assert web["THIS_HARDWARE_ID"] == const["HARDWARE_ID_MAIN"] and web["SLAVE_HARDWARE_ID"] == const["HARDWARE_ID_SLAVE"]
    assert web["PATCH_UNKNOWN"] == const["PATCH_UNKNOWN"] and web["PATCH_FLAG"] == const["PATCH_FLAG"] and web["FLASH_PAGE_SIZE"] == const["FLASH_PAGE_SIZE"]
    assert web["PATCH_FLAG_ACCEPTS_IN_END_UPDATE"] == const["PATCH_FLAG_ACCEPTS_IN_END_UPDATE"]
    boot = c_defines(sibling(BOOT_COMMON))
    assert boot["THIS_HARDWARE_ID"] == const["HARDWARE_ID_MAIN"]
    wire = c_defines(sibling(VERSION_WIRE))
    assert wire["URTC_PATCH_UNKNOWN"] == const["PATCH_UNKNOWN"] and wire["URTC_MINOR_PATCH_FLAG"] == const["PATCH_FLAG"] and wire["URTC_PATCH_MAX"] == const["PATCH_MAX"]
    assert wire["URTC_PATCH_FLAG_END_UPDATE_PATCH"] == const["PATCH_FLAG_ACCEPTS_IN_END_UPDATE"]
    assert wire["URTC_SLAVE_VERSION_EXT_MARKER"] == const["SLAVE_VERSION_EXT_MARKER"]


def test_the_slave_hardware_id_of_the_slave_firmware(spec, sibling):
    const = {c["name"]: c["value"] for c in spec["constants"]}
    slave = c_defines(sibling("URTC/src/F303-slave/slave_common.h"))
    if "THIS_HARDWARE_ID" in slave:
        assert slave["THIS_HARDWARE_ID"] == const["HARDWARE_ID_SLAVE"]
    assert slave["I2C_SLAVE_ADDRESS"] == const["SLAVE_I2C_ADDRESS"]


def test_limits_and_timings_the_hosts_use_equal_the_specification(spec, sibling):
    const = {c["name"]: c["value"] for c in spec["constants"]}
    tester = python_ints(sibling(TESTER_CONFIG))
    assert tester["SETPOINT_MAX_C"] == const["HEATER_SETPOINT_MAX_C"]
    assert tester["AOI_STROBE_MAX_MS"] == const["AOI_STROBE_MAX_MS"]
    limits = ts_ints(sibling(WEB_LIMITS))
    assert limits["MAX_HEATER_SETPOINT_C"] == const["HEATER_SETPOINT_MAX_C"]
    assert limits["AOI_STROBE_MAX_MS"] == const["AOI_STROBE_MAX_MS"] and limits["PASTE_PULSE_MAX_MS"] == const["PASTE_PULSE_MAX_MS"]
    web = ts_ints(sibling(WEB_IDS))
    assert web["WELD_PULSE_MAX_MS"] == const["WELD_PULSE_MAX_MS"]
    assert web["KEEPALIVE_INTERVAL_MS"] == const["KEEPALIVE_INTERVAL_MS"]
    assert web["LAYERFAN_KEEPALIVE_INTERVAL_MS"] == const["LAYER_FAN_KEEPALIVE_INTERVAL_MS"]
    assert web["THERMAL_CHUNK_COUNT"] == const["THERMAL_CHUNK_COUNT_MLX90640"]
    # a host keeps every refresh interval under the watchdog it serves
    assert const["KEEPALIVE_INTERVAL_MS"] < const["WATCHDOG_MS"] and const["LAYER_FAN_KEEPALIVE_INTERVAL_MS"] < const["LAYER_FAN_WATCHDOG_MS"]
    assert tester["BITRATE_500K_SLCAN_CODE" if "BITRATE_500K_SLCAN_CODE" in tester else "THIS_HARDWARE_ID"] is not None
    config = text(sibling(TESTER_CONFIG))
    assert re.search(r'BITRATE_500K_SLCAN_CODE = "6"', config)
    assert re.search(r'\("500 kbit/s", "6"\)', config)


def test_slcan_bitrate_codes_equal_the_specification(spec, sibling):
    table = [tuple(x) for x in spec["slcan"]["bitrate_codes"]]
    for path in (FLASHER_CONFIG, TESTER_CONFIG):
        source = text(sibling(path))
        block = re.search(r"SLCAN_BITRATES = \[(.*?)\]\n", source, re.S).group(1)
        assert re.findall(r'\("([^"]+)", "(\d)"\)', block) == table


def test_slave_registers_equal_the_specification(spec, sibling):
    boot = {n: v for n, v in c_defines(sibling("URTC/src/F303-slave/boot/slaveboot_common.h"), "REG_").items()}
    app = {n: v for n, v in c_defines(sibling("URTC/src/F303-slave/slave_common.h"), "REG_").items()}
    spec_boot = {f"REG_{e['name']}": e["id"] for e in spec["registers"]["slave_bootloader"]["entries"]}
    spec_app = {f"REG_{e['name']}": e["id"] for e in spec["registers"]["slave_application"]["entries"]}
    assert boot == spec_boot
    assert app == spec_app


# ---------------------------------------------------------------------------------------------------------------------
# the prose
# ---------------------------------------------------------------------------------------------------------------------
# 0x260-0x26F are reserved for the tool rack: the prose says so, the firmware answers none of them, the specification does not list them.
RACK_RESERVED = set(range(0x260, 0x270))


def test_the_prose_and_the_specification_list_the_same_identifiers(spec, sibling):
    prose = text(sibling(CANBUS))
    headers = {int(v, 16) for v in re.findall(r"^ID: (0x[0-9A-Fa-f]+)", prose, re.M)}
    summary = {int(v, 16) for v in re.findall(r"^  (0x[0-9A-F]{3}) ->", prose, re.M)}
    documented = (headers | summary) - RACK_RESERVED
    table = by_id(spec)
    assert documented <= set(table), sorted(documented - set(table))
    not_in_prose = set(table) - documented
    assert not_in_prose == {v for v, m in table.items() if m.get("documented_in_prose") is False} == set()
    # an identifier that appears only in the summary and the section intro is the one a scan of the headers would miss
    assert summary - headers == {0x243}
    assert len(headers - RACK_RESERVED) == 94


def test_exact_lengths_in_the_prose_are_the_lengths_of_the_specification(spec, sibling):
    prose = text(sibling(CANBUS))
    table = by_id(spec)
    checked = 0
    for block in re.split(r"(?m)^(?=ID: 0x)", prose):
        header = re.match(r"ID: (0x[0-9A-Fa-f]+)", block)
        if not header or int(header.group(1), 16) in RACK_RESERVED:
            continue
        length = re.search(r"(?m)^DLC: (\d+) bytes?\b", block)
        if not length:
            continue
        message = table[int(header.group(1), 16)]
        n = int(length.group(1))
        rules = [layout["dlc"] for layout in message["layouts"]]
        assert any(rule.get("exact") == n or rule.get("min") == n or rule.get("max") == n or n in rule.get("one_of", []) for rule in rules), (header.group(1), n, rules)
        checked += 1
    assert checked > 50


# ---------------------------------------------------------------------------------------------------------------------
# the multinode extension in the firmware
# ---------------------------------------------------------------------------------------------------------------------
def test_the_firmware_multinode_header_has_the_values_of_the_specification(spec, sibling):
    header = sibling(f"{FIRMWARE}/multinode.h")
    found = c_defines(header, "MN_")
    mn = spec["multinode"]
    for constant in mn["constants"]:
        assert found.get(constant["name"]) == constant["value"], constant["name"]
    for flag in mn["state_flags"]:
        assert found.get(f"MN_STATE_{flag['name']}") == 1 << flag["bit"], flag["name"]
    for action in mn["select_actions"]:
        assert found.get(f"MN_SELECT_ACTION_{action['name']}") == action["value"], action["name"]
    for frame in mn["frames"]:
        assert found.get(f"MN_ID_{frame['name']}") == int(frame["id"], 16), frame["name"]
    assert found["MN_ID_FIRST"] == 0x400 and found["MN_ID_LAST"] == 0x49F


def test_the_firmware_multinode_switch_frames_are_the_ones_of_the_specification(spec, sibling):
    source = text(sibling(f"{FIRMWARE}/firmware_multinode.c"))
    table = by_id(spec)
    assert {0x1AC, 0x1AD} <= set(table)
    message = table[0x1AC]
    assert message["layouts"][0]["dlc"] == {"exact": 6} and message["firmware_accepts_dlc"] == {"exact": 6}
    magic = next(f for f in message["layouts"][0]["fields"] if f["name"] == "magic")["fixed"]
    comparison = " && ".join(f"rxData\[{i}\] == 0x{b:02X}" for i, b in enumerate(bytes.fromhex(magic)))
    assert re.search(comparison, source, re.I)
    assert re.search(r"StdId\s*[!=]=\s*0x1AD", source)
