# =============================================================================
# URTC-COMMON - tests/test_spec.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The specification is well formed and consistent with itself."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
WIDTH = {"u8": 1, "u16": 2, "u24": 3, "u32": 4, "i16": 2, "i32": 4}


def ids(spec):
    return [int(m["id"], 16) for m in spec["messages"]]


def schema():
    return json.loads((ROOT / "spec" / "can_protocol.schema.json").read_text(encoding="utf-8"))


def test_the_schema_is_a_valid_schema_and_the_spec_satisfies_it(spec):
    jsonschema.Draft7Validator.check_schema(schema())
    errors = [f"{list(e.path)}: {e.message[:120]}" for e in jsonschema.Draft7Validator(schema()).iter_errors(spec)]
    assert errors == []


def test_the_schema_refuses_what_a_typo_would_produce(spec):
    validator = jsonschema.Draft7Validator(schema())

    def broken(change):
        copy = json.loads(json.dumps(spec))
        change(copy)
        return list(validator.iter_errors(copy))

    assert broken(lambda s: s["messages"][0].update({"direcion": "host_to_board"}))
    assert broken(lambda s: s["messages"][0].update({"id": "0x800"}))
    assert broken(lambda s: s["messages"][3]["layouts"][0].update({"dlc": {"exact": 9}}))
    assert broken(lambda s: s["magic_payloads"][0].update({"data": "B0071D"}))
    assert broken(lambda s: s["messages"][3].update({"direction": "sideways"}))
    assert broken(lambda s: s.update({"format": 2}))


def test_identifiers_are_unique_standard_ids_and_sorted(spec):
    values = ids(spec)
    assert len(values) == len(set(values))
    assert all(0 <= v <= 0x7FF for v in values)
    assert values == sorted(values)


def test_names_are_unique(spec):
    names = [m["name"] for m in spec["messages"]]
    assert len(names) == len(set(names))
    prefixes = [e["prefix"] for e in spec["enums"]]
    assert len(prefixes) == len(set(prefixes))
    constants = [c["name"] for c in spec["constants"]]
    assert len(constants) == len(set(constants))
    assert not any(name.startswith("CAN_ID_") for name in constants)


def test_statistics_the_documents_quote(spec):
    assert len(spec["messages"]) == 95
    assert len(spec["tools"]) == 26 and [t["id"] for t in spec["tools"]] == list(range(26))
    assert sum(len(b["entries"]) for b in spec["registers"].values()) == 23
    assert len(spec["magic_payloads"]) == 4


def test_every_layout_fits_a_classic_frame(spec):
    for message in spec["messages"]:
        for layout in message["layouts"]:
            end = 0
            for field in layout["fields"]:
                assert field["offset"] == end, (message["name"], field["name"])
                if field["type"] == "bytes":
                    width = field.get("length")
                    assert width or field.get("rest"), (message["name"], field["name"])
                    if width:
                        assert field.get("width") == width
                        end += width
                else:
                    assert field["width"] == WIDTH[field["type"]]
                    end += field["width"]
                assert end <= 8, (message["name"], layout["role"])
            rule = layout["dlc"]
            if "exact" in rule:
                assert end <= rule["exact"]
                assert rule["exact"] == end or any(f.get("rest") for f in layout["fields"]), (message["name"], rule, end)
            if "min" in rule:
                assert rule["min"] <= rule["max"] <= 8
            if "one_of" in rule:
                assert max(rule["one_of"]) <= 8


def test_the_required_part_of_a_layout_is_never_longer_than_its_minimum_length(spec):
    for message in spec["messages"]:
        for layout in message["layouts"]:
            rule = layout["dlc"]
            if "any" in rule:
                continue
            floor = rule.get("exact", rule.get("min", min(rule.get("one_of", [0]))))
            required = sum(f.get("width", 0) for f in layout["fields"] if not f.get("optional") and not f.get("rest"))
            assert required <= floor, (message["name"], required, floor)


def test_direction_agrees_with_the_roles_of_the_layouts(spec):
    for message in spec["messages"]:
        roles = {layout["role"] for layout in message["layouts"]}
        expected = {"host_to_board": {"request"}, "board_to_host": {"response"}, "both": {"request", "response"}}[message["direction"]]
        assert roles == expected, message["name"]


def test_layouts_of_one_message_are_told_apart(spec):
    for message in spec["messages"]:
        keys = [(layout["role"], layout.get("variant")) for layout in message["layouts"]]
        assert len(keys) == len(set(keys)), message["name"]


def test_references_resolve(spec):
    all_ids = set(ids(spec))
    enums = {e["name"] for e in spec["enums"]}
    magic = {m["name"] for m in spec["magic_payloads"]}
    tools = {t["id"] for t in spec["tools"]}
    for message in spec["messages"]:
        if "answers" in message:
            assert int(message["answers"], 16) in all_ids
        for answered in message.get("answered_by", []):
            assert int(answered, 16) in all_ids
        if message["tools"] != "any":
            assert set(message["tools"]) <= tools
        if "needs_magic" in message.get("gates", {}):
            assert message["gates"]["needs_magic"] in magic
        for layout in message["layouts"]:
            for field in layout["fields"]:
                if "enum" in field:
                    assert field["enum"] in enums, (message["name"], field["name"])
                if field.get("derived_length_of"):
                    assert field["derived_length_of"] in {f["name"] for f in layout["fields"]}
    for entry in spec["magic_payloads"]:
        assert int(entry["id"], 16) in all_ids
        for other in entry.get("also_on", []):
            assert int(other, 16) in all_ids


def test_a_magic_payload_is_four_bytes_and_every_gated_message_uses_it(spec):
    by_name = {m["name"]: m for m in spec["magic_payloads"]}
    for entry in spec["magic_payloads"]:
        assert len(entry["data"]) == 8
    for message in spec["messages"]:
        name = message.get("gates", {}).get("needs_magic")
        if not name:
            continue
        fixed = [f for layout in message["layouts"] for f in layout["fields"] if f.get("fixed")]
        assert len(fixed) == 1 and fixed[0]["fixed"] == by_name[name]["data"], message["name"]
        assert message["id"] == by_name[name]["id"] or message["id"] in by_name[name].get("also_on", [])
    # four distinct payloads: one cannot be mistaken for another
    assert len({m["data"] for m in spec["magic_payloads"]}) == 4


def test_enum_values_are_unique_and_flags_are_single_bits(spec):
    for enum in spec["enums"]:
        values = [v["value"] for v in enum["values"]]
        names = [v["name"] for v in enum["values"]]
        assert len(values) == len(set(values)) and len(names) == len(set(names)), enum["name"]
        if enum["kind"] == "flags":
            assert all(v & (v - 1) == 0 for v in values), enum["name"]


def test_registers_are_unique_per_block_and_link_to_a_real_message(spec):
    all_ids = {m["id"] for m in spec["messages"]}
    for key, block in spec["registers"].items():
        values = [e["id"] for e in block["entries"]]
        assert len(values) == len(set(values)), key
        names = [e["name"] for e in block["entries"]]
        assert len(names) == len(set(names)), key
        for entry in block["entries"]:
            if "can" in entry:
                assert entry["can"] in all_ids


def test_the_version_registers_exist(spec):
    boot = {e["name"]: e["id"] for e in spec["registers"]["slave_bootloader"]["entries"]}
    assert boot["QUERY_VERSION_EXT"] == 0x08 and boot["QUERY_VERSION"] == 0x06 and boot["VERIFY_FAIL_REASON"] == 0x07


def test_examples_obey_their_own_ranges(spec):
    for message in spec["messages"]:
        for layout in message["layouts"]:
            for example in layout.get("examples", []):
                for field in layout["fields"]:
                    if field["name"] in example["fields"] and "range" in field:
                        assert field["range"][0] <= example["fields"][field["name"]] <= field["range"][1], (message["name"], example["name"])


def test_every_layout_with_fields_has_an_example(spec):
    for message in spec["messages"]:
        for layout in message["layouts"]:
            assert layout.get("examples"), (message["name"], layout["role"])


def test_known_gaps_are_recorded_not_papered_over(spec):
    by_id = {m["id"]: m for m in spec["messages"]}
    hosts = ("flasher", "tester", "web_studio")
    for gap in ("0x220", "0x221"):
        assert not any(by_id[gap]["implemented_by"][h] for h in hosts), gap
        assert by_id[gap]["implemented_by"]["firmware"]
    for done in ("0x1A8", "0x1A9"):  # the tester and the web studio read the fault recorder now; the flasher does not
        assert by_id[done]["implemented_by"]["tester"] and by_id[done]["implemented_by"]["web_studio"] and not by_id[done]["implemented_by"]["flasher"]
    assert "documented_in_prose" not in by_id["0x1A8"] and "documented_in_prose" not in by_id["0x1A9"], "the fault recorder frames are described in the prose of the firmware repository"
    assert any("security gap" in n for n in by_id["0x220"]["notes"])
    assert not by_id["0x1AA"]["implemented_by"]["web_studio"] and by_id["0x1AA"]["implemented_by"]["tester"]


def test_every_identifier_is_in_the_firmware(spec):
    assert all(m["implemented_by"]["firmware"] for m in spec["messages"])


def test_critical_error_gates_follow_the_dispatcher(spec):
    by_id = {m["id"]: m for m in spec["messages"]}
    open_in_error = {i for i, m in by_id.items() if m.get("gates", {}).get("blocked_by_critical_error") is False}
    assert {"0x100", "0x110", "0x7F0", "0x7F8", "0x7FB"} <= open_in_error
    for blocked in ("0x160", "0x130", "0x192", "0x180"):
        assert by_id[blocked]["gates"]["blocked_by_critical_error"] is True
