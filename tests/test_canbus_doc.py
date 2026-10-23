# =============================================================================
# URTC-COMMON - tests/test_canbus_doc.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The CAN document of the firmware: its reference is generated from the specification and the prose around it is left alone."""
from __future__ import annotations

import copy

import generate_canbus_doc as gen
from sources import text

CANBUS = "URTC/docs/CANBUS.TXT"
PROSE = "Hand-written prose that must survive every run.\nID: 0x123 [Master -> Tool Head]\nDLC: 8 bytes\n"


def test_every_block_has_a_renderer_and_a_title():
    assert set(gen.RENDERERS) == set(gen.TITLES)


def test_the_prose_is_kept_byte_for_byte_and_the_blocks_are_added_once(spec):
    blocks = gen.generated_blocks(spec)
    merged = gen.merge(PROSE, blocks)
    assert merged.startswith(PROSE)
    assert gen.merge(merged, blocks) == merged                      # running again changes nothing
    assert merged.count("[[ BEGIN GENERATED index ") == 1
    assert gen.verify_digests(merged) == []
    # prose written between two blocks (a note under a table) is also kept when the blocks are replaced
    between = merged.replace("[[ END GENERATED index ]]\n", "[[ END GENERATED index ]]\nA hand-written note under the index.\n")
    assert "A hand-written note under the index." in gen.merge(between, blocks)


def test_a_hand_edit_of_a_generated_block_is_found_without_the_specification(spec):
    merged = gen.merge(PROSE, gen.generated_blocks(spec))
    assert gen.verify_digests(merged) == []
    edited = merged.replace("| 0x100 | GLOBAL_STATUS |", "| 0x100 | GLOBAL_STATUS_EDITED |")
    assert gen.verify_digests(edited) == ["index"]
    assert gen.verify_digests(edited.replace("GLOBAL_STATUS_EDITED", "GLOBAL_STATUS")) == []


def test_a_hand_edit_is_overwritten_by_the_next_run(spec):
    blocks = gen.generated_blocks(spec)
    merged = gen.merge(PROSE, blocks)
    edited = merged.replace("GLOBAL_STATUS", "GLOBAL_STATUS_EDITED")
    assert gen.merge(edited, blocks) == merged


def test_a_new_identifier_in_the_specification_reaches_the_document_without_touching_the_tool(spec):
    changed = copy.deepcopy(spec)
    extra = copy.deepcopy(changed["messages"][1])
    extra.update(id="0x7FE", name="NODE_ID_QUERY", title="A new frame added later")
    changed["messages"].append(extra)
    before = gen.merge(PROSE, gen.generated_blocks(spec))
    after = gen.merge(before, gen.generated_blocks(changed))
    assert "0x7FE | NODE_ID_QUERY" in after and "### 0x7FE NODE_ID_QUERY - A new frame added later" in after
    assert "NODE_ID_QUERY" not in before
    assert after.startswith(PROSE) and gen.verify_digests(after) == []
    assert f"{len(changed['messages'])} identifiers" in after


def test_every_identifier_has_a_row_and_a_section(spec):
    index = "\n".join(gen.render_index(spec))
    layouts = "\n".join(gen.render_layouts(spec))
    for message in spec["messages"]:
        assert f"| {message['id']} | {message['name']} |" in index
        assert f"### {message['id']} {message['name']} - " in layouts
    for example in (e for m in spec["messages"] for lay in m["layouts"] for e in lay["examples"]):
        assert example["data"] == "" or example["data"] in layouts


def test_the_generated_text_does_not_look_like_the_prose_the_other_tests_scan(spec):
    generated = "\n".join(gen.generated_blocks(spec).values())
    assert not gen.re.search(r"(?m)^ID: 0x", generated)
    assert not gen.re.search(r"(?m)^  0x[0-9A-F]{3} ->", generated)
    assert not gen.re.search(r"(?m)^DLC: ", generated)


def test_the_document_of_the_firmware_is_what_the_specification_produces(spec, sibling):
    path = sibling(CANBUS)
    current, _newline = gen.read(path)
    assert gen.merge(current, gen.generated_blocks(spec)) == current, "run tools/generate_canbus_doc.py"
    assert gen.verify_digests(current) == []
    assert "[[ BEGIN GENERATED layouts " in text(path)


def test_the_command_line_check(tmp_path, spec, capsys):
    path = tmp_path / "CANBUS.TXT"
    path.write_bytes(PROSE.replace("\n", "\r\n").encode("utf-8"))
    assert gen.main(["--file", str(path), "--check"]) == 1
    assert gen.main(["--file", str(path)]) == 0
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")      # the line ends of the file are kept
    assert gen.main(["--file", str(path), "--check"]) == 0
    assert gen.main(["--file", str(path)]) == 0 and "already current" in capsys.readouterr().out
    path.write_bytes(raw.replace(b"GLOBAL_STATUS", b"GLOBAL_STATUS_EDITED"))
    assert gen.main(["--file", str(path), "--check"]) == 1
    assert gen.main(["--file", str(tmp_path / "missing.TXT")]) == 2
