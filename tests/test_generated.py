# =============================================================================
# URTC-COMMON - tests/test_generated.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The generated files are current and say what the specification says."""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import generate_constants

from sources import c_defines, text, ts_array, ts_ints
from urtc_common import protocol

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "generated" / "urtc_can_ids.h"
TYPESCRIPT = ROOT / "generated" / "urtcCanIds.ts"
PYTHON = ROOT / "src" / "urtc_common" / "protocol.py"


def test_the_generator_check_passes():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "generate_constants.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "GENERATED=PASS" in result.stdout


def test_every_generated_file_is_what_the_specification_produces(spec):
    for path, content in generate_constants.outputs(spec).items():
        assert path.read_bytes().decode("utf-8") == content, path


def test_an_edited_generated_file_would_be_caught(spec, tmp_path, monkeypatch):
    outputs = generate_constants.outputs(spec)
    edited = outputs[HEADER].replace("URTC_CAN_ID_MOTION_CMD 0x120u", "URTC_CAN_ID_MOTION_CMD 0x121u")
    assert edited != outputs[HEADER]
    copy = tmp_path / "urtc_can_ids.h"
    copy.write_text(edited, encoding="utf-8")
    monkeypatch.setattr(generate_constants, "outputs", lambda _spec: {copy: outputs[HEADER]})
    assert generate_constants.main(["--check"]) == 1


def test_check_writes_nothing():
    before = {p: p.stat().st_mtime_ns for p in generate_constants.outputs(generate_constants.load_spec())}
    assert generate_constants.main(["--check"]) == 0
    assert before == {p: p.stat().st_mtime_ns for p in before}


def test_the_python_module_has_every_identifier_with_the_right_value(spec):
    for message in spec["messages"]:
        assert getattr(protocol, f"CAN_ID_{message['name']}") == int(message["id"], 16)
    assert set(protocol.MESSAGES) == {int(m["id"], 16) for m in spec["messages"]}


def test_the_typescript_module_has_every_identifier_with_the_right_value(spec):
    assert ts_ints(TYPESCRIPT, "CAN_ID_") == {f"CAN_ID_{m['name']}": int(m["id"], 16) for m in spec["messages"]}


def test_the_c_header_has_every_identifier_with_the_right_value(spec):
    assert c_defines(HEADER, "URTC_CAN_ID_") == {f"URTC_CAN_ID_{m['name']}": int(m["id"], 16) for m in spec["messages"]}


def test_the_three_languages_agree_on_constants_enums_and_registers(spec):
    py = {k: v for k, v in vars(protocol).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    ts = ts_ints(TYPESCRIPT)
    c = c_defines(HEADER, "URTC_")
    for const in spec["constants"]:
        name, value = const["name"], const["value"]
        assert py[name] == value, name
        if isinstance(value, int):
            assert ts[name] == value, name
            assert c[f"URTC_{name}"] == value, name
    for enum in spec["enums"]:
        for entry in enum["values"]:
            name = f"{enum['prefix']}{entry['name']}"
            assert py[name] == entry["value"] and ts[name] == entry["value"] and c[f"URTC_{name}"] == entry["value"], name
    prefixes = {"slave_bootloader": "SLAVE_BOOT_REG_", "slave_application": "SLAVE_APP_REG_"}
    for key, block in spec["registers"].items():
        for entry in block["entries"]:
            name = f"{prefixes[key]}{entry['name']}"
            assert py[name] == entry["id"] and ts[name] == entry["id"] and c[f"URTC_{name}"] == entry["id"], name


def test_the_magic_payloads_agree_in_the_three_languages(spec):
    header = text(HEADER)
    for magic in spec["magic_payloads"]:
        data = bytes.fromhex(magic["data"])
        assert getattr(protocol, f"MAGIC_{magic['name'].upper()}") == data
        assert ts_array(TYPESCRIPT, f"MAGIC_{magic['name'].upper()}") == list(data)
        match = re.search(rf"URTC_MAGIC_{magic['name'].upper()}_INIT \{{ ([^}}]*) \}}", header)
        assert match and [int(x, 16) for x in match.group(1).split(",")] == list(data)


def test_the_c_header_is_self_consistent(spec):
    header = text(HEADER)
    assert header.count("#ifndef URTC_CAN_IDS_H") == 1 and header.rstrip().endswith("#endif /* URTC_CAN_IDS_H */")
    assert "#include <stdint.h>" in header
    names = re.findall(r"^#define (\w+)", header, re.M)
    assert len(names) == len(set(names))
    c = c_defines(HEADER)
    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = generate_constants.layout_key(message, layout).upper()
            assert 0 <= c[f"URTC_DLC_{key}_MIN"] <= c[f"URTC_DLC_{key}_MAX"] <= 8, key


def test_the_python_module_uses_only_the_standard_library():
    tree = ast.parse(text(PYTHON))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__"}, imported


def test_generated_files_say_they_are_generated_and_carry_the_licence():
    for path in (HEADER, TYPESCRIPT, PYTHON, ROOT / "docs" / "PROTOCOL_TABLE.md"):
        content = text(path)
        assert "GENERATED from spec/can_protocol.json" in content, path
        if path.suffix != ".md":
            assert "GPL-3.0-or-later" in content
    assert "\r" not in text(HEADER)


def test_each_layout_has_a_builder_and_a_parser(spec):
    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = generate_constants.layout_key(message, layout)
            assert callable(getattr(protocol, f"encode_{key}")) and callable(getattr(protocol, f"decode_{key}"))
            assert key in protocol.LAYOUTS


def test_the_table_for_people_lists_every_identifier(spec):
    table = text(ROOT / "docs" / "PROTOCOL_TABLE.md")
    for message in spec["messages"]:
        assert f"`{message['id']}` | {message['name']} |" in table


def test_encoders_refuse_instead_of_clamping():
    import pytest

    with pytest.raises(ValueError):
        protocol.encode_motion_cmd(1, 2**32)
    with pytest.raises(ValueError):
        protocol.encode_solder_setpoint(446)
    with pytest.raises(ValueError):
        protocol.encode_paste_jetting_config(4, 1000)
    with pytest.raises(TypeError):
        protocol.encode_motion_cmd(True, 5)
    with pytest.raises(TypeError):
        protocol.encode("motion_cmd", direction=1, steps=1.5)
    with pytest.raises(ValueError):
        protocol.encode("erase_fram", magic=b"\x00\x00\x00\x00")
    with pytest.raises(TypeError):
        protocol.encode("motion_cmd", direction=1, steps=5, extra=1)


def test_a_magic_frame_carries_its_payload_by_default():
    assert protocol.encode_enter_bootloader() == (0x7F0, bytes.fromhex("B0071D5A"))
    assert protocol.encode_authorize_downgrade() == (0x7FD, bytes.fromhex("D09E12AD"))
    assert protocol.encode_erase_fram() == (0x192, bytes.fromhex("E3A5E0FF"))
    assert protocol.encode_solder_feeder_reset() == (0x131, b"RSP0")


def test_decoders_report_missing_optional_bytes_as_none_not_zero():
    short = protocol.decode_active_tool_resp(bytes.fromhex("0A000100"))
    assert short["thermal_fault"] is None and short["reset_cause"] is None
    full = protocol.decode_active_tool_resp(bytes.fromhex("0A00010002FF"))
    assert full["thermal_fault"] == 2 and full["reset_cause"] == 0xFF
    assert protocol.decode_active_tool_resp(bytes.fromhex("0A0001")) is None


def test_strict_decoding_enforces_the_length_rule():
    assert protocol.decode_page_ack(bytes.fromhex("0000000500")) == {"page_index": 5}
    assert protocol.decode_page_ack(bytes.fromhex("0000000500"), strict=True) is None
    assert protocol.decode_page_ack(bytes.fromhex("000005")) is None


def test_minor_field_helpers():
    assert protocol.minor_field_pack(3, 5) == 0x8503
    assert protocol.minor_field_pack(3, None) == 3
    assert protocol.minor_field_pack(3, 128) == 3 and protocol.minor_field_pack(3, protocol.PATCH_UNKNOWN) == 3
    assert protocol.minor_field_minor(0x8503) == 3 and protocol.minor_field_patch(0x8503) == 5 and protocol.minor_field_patch(3) is None
    assert protocol.version_compare((0, 3, 5), (0, 3, 6)) == 1
    assert protocol.version_compare((0, 3, None), (0, 3, 4)) == 0
