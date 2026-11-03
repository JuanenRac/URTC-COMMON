# =============================================================================
# URTC-COMMON - tests/test_tool_panels.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The panel of each tool (controls, readings, commands) is data in spec/tools.json: it is checked and turned into TypeScript."""
from __future__ import annotations

import copy
import json

import generate_tools as gen


def spec():
    return gen.load(), json.loads(gen.PROTOCOL.read_text(encoding="utf-8"))


def test_the_panels_of_the_specification_are_consistent():
    doc, protocol = spec()
    assert gen.validate_panels(doc, protocol) == []
    assert sum("panel" in t for t in doc["tools"]) >= 14


def test_a_panel_that_borrows_another_one_resolves_to_it():
    doc, _ = spec()
    tools = doc["tools"]
    assert gen.resolve_panel(tools, tools[2]) == gen.resolve_panel(tools, tools[1])


def test_the_generated_panels_carry_the_identifier_of_each_message():
    doc, protocol = spec()
    panels = gen._panels(doc, protocol)
    drill = panels[5]["sections"][0]
    assert drill["actions"][0]["canId"] == 0x140
    assert [r["canId"] for r in drill["telemetry"]] == [0x147, 0x147]
    assert panels[24]["sections"][0]["actions"][0]["canId"] == 0x200


def test_an_unknown_encoder_message_or_control_is_refused():
    doc, protocol = spec()
    bad = copy.deepcopy(doc)
    drill = next(t for t in bad["tools"] if t["id"] == 5)["panel"]["sections"][0]
    drill["actions"][0]["encoder"] = "nope"
    drill["actions"][1]["message"] = "NOT_A_MESSAGE"
    drill["actions"][0]["args"] = ["speed", "missing"]
    problems = "\n".join(gen.validate_panels(bad, protocol))
    assert "unknown encoder 'nope'" in problems
    assert "not in the protocol" in problems
    assert "control 'missing'" in problems


def test_a_control_outside_its_range_a_keepalive_without_an_off_command_and_a_bad_borrow_are_refused():
    doc, protocol = spec()
    bad = copy.deepcopy(doc)
    tools = {t["id"]: t for t in bad["tools"]}
    tools[5]["panel"]["sections"][0]["controls"][0]["default"] = 999
    del tools[18]["panel"]["sections"][0]["actions"][0]["off_encoder"]
    tools[2]["panel"] = {"same_as": 4}
    tools[4]["panel"] = {"same_as": 2}
    problems = "\n".join(gen.validate_panels(bad, protocol))
    assert "min <= default <= max" in problems
    assert "keepalive needs off_encoder" in problems
    assert "same_as does not name" in problems


def test_a_panel_text_needs_a_key_and_its_default_or_a_plain_text():
    doc, protocol = spec()
    bad = copy.deepcopy(doc)
    next(t for t in bad["tools"] if t["id"] == 13)["panel"]["sections"][0]["title"] = {"key": "only.key"}
    assert any("a text needs key and default" in p for p in gen.validate_panels(bad, protocol))


def test_the_generated_typescript_is_current():
    doc, _ = spec()
    out = gen.outputs(doc)
    path = gen.ROOT / "generated" / "urtcTools.ts"
    assert path.read_bytes().decode("utf-8") == out[path]
