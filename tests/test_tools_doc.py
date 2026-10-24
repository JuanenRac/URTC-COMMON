# =============================================================================
# URTC-COMMON - tests/test_tools_doc.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The tool table of the firmware document is generated from the specification, and what the prose says about each tool is checked."""
from __future__ import annotations

import copy

import generate_tools_doc as gen

TOOLS_DOC = "URTC/docs/TOOLS.TXT"
PROSE = (
    "Intro.\n\n1. Soldering Station (T12) - ID 0x00\nText.\nExpansion board: none needed.\n\n"
    "2. Spot Welder - ID 0x01\nText.\nExpansion board: recommended if the head is far.\n\n"
    "3. Tester - ID 0x02\nText with no expansion line.\n"
)


def tools():
    return [
        {"id": 0, "display_name": "T12", "kind": "motion", "limits": {"min": 150, "max": 445, "default": 320}, "hero_metric": {"unit": "°C"}, "watchdog_ms": 250, "expansion_board": "none"},
        {"id": 1, "display_name": "Welder", "kind": "actuator", "limits": {"min": 1, "max": 100, "default": 15}, "hero_metric": {"unit": "ms"}, "expansion_board": "recommended"},
        {"id": 2, "display_name": "Tester", "kind": "telemetry", "limits": {"min": 0, "max": 36, "default": 3.3}, "hero_metric": {"unit": "V"}, "expansion_board": "none"},
    ]


def test_the_table_has_a_row_for_every_profile_of_the_specification():
    spec = gen.load_tools()
    lines = gen.render(spec)
    assert len(lines) == len(spec) + 2
    assert all(f"| {t['id']} (0x{t['id']:02X}) | {t['display_name']} |" in "\n".join(lines) for t in spec)


def test_the_prose_is_kept_and_the_table_is_added_once():
    block = gen.block(tools())
    merged = gen.merge(PROSE, block)
    assert merged.startswith(PROSE)
    assert gen.merge(merged, block) == merged
    assert merged.count("[[ BEGIN GENERATED tool_table ") == 1
    assert gen.canbus.verify_digests(merged) == []


def test_a_hand_edit_of_the_table_is_found_and_overwritten():
    block = gen.block(tools())
    merged = gen.merge(PROSE, block)
    edited = merged.replace("| Welder |", "| Welder 2 |")
    assert gen.canbus.verify_digests(edited) == ["tool_table"]
    assert gen.merge(edited, block) == merged


def test_a_prose_that_agrees_with_the_specification_has_no_problem():
    assert gen.prose_problems(PROSE, tools()) == []


def test_a_wrong_expansion_board_is_reported():
    text = PROSE.replace("recommended if the head is far", "required")
    assert any("Welder" in p and "required" in p and "recommended" in p for p in gen.prose_problems(text, tools()))


def test_a_section_out_of_order_or_for_an_unknown_identifier_is_reported():
    swapped = PROSE.replace("ID 0x01", "ID 0x05")
    assert any("0x05" in p and "does not have" in p for p in gen.prose_problems(swapped, tools()))
    renumbered = PROSE.replace("2. Spot Welder", "3. Spot Welder")
    assert any("out of order" in p for p in gen.prose_problems(renumbered, tools()))
    assert any("tool sections" in p for p in gen.prose_problems(PROSE + "\n4. Extra - ID 0x03\nText.\n", tools()))


def test_a_new_profile_in_the_specification_reaches_the_table_without_touching_the_tool():
    changed = copy.deepcopy(tools())
    extra = copy.deepcopy(changed[2])
    extra.update(id=3, display_name="Added later")
    changed.append(extra)
    after = gen.merge(gen.merge(PROSE, gen.block(tools())), gen.block(changed))
    assert "| 3 (0x03) | Added later |" in after


def test_the_document_of_the_firmware_is_what_the_specification_produces(sibling):
    path = sibling(TOOLS_DOC)
    current, _newline = gen.canbus.read(path)
    assert gen.merge(current, gen.block(gen.load_tools())) == current, "run tools/generate_tools_doc.py"
    assert gen.prose_problems(current, gen.load_tools()) == []
    assert gen.canbus.verify_digests(current) == []


def test_the_command_line_check(tmp_path, capsys):
    path = tmp_path / "TOOLS.TXT"
    spec = gen.load_tools()
    prose = "".join(f"{t['id'] + 1}. {t['display_name']} - ID 0x{t['id']:02X}\nText.\nExpansion board: {t.get('expansion_board', 'none')}.\n\n" for t in spec)
    path.write_bytes(prose.replace("\n", "\r\n").encode("utf-8"))
    assert gen.main(["--file", str(path), "--check"]) == 1
    assert gen.main(["--file", str(path)]) == 0
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert gen.main(["--file", str(path), "--check"]) == 0
    assert gen.main(["--file", str(path)]) == 0 and "already current" in capsys.readouterr().out
    path.write_bytes(raw.replace(b"Expansion board: none", b"Expansion board: required", 1))
    assert gen.main(["--file", str(path), "--check"]) == 1
    assert gen.main(["--file", str(tmp_path / "missing.TXT")]) == 2
