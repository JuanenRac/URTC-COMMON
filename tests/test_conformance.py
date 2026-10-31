# =============================================================================
# URTC-COMMON - tests/test_conformance.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The shared vectors: complete, current, reproduced by Python and by the generated TypeScript, and equal to the copies in use."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import make_conformance
import pytest

from urtc_common import conformance

ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = ROOT / "conformance" / "can_vectors.json"


def test_the_file_is_utf8_json_with_lf_endings_and_every_section(vectors):
    raw = VECTOR_FILE.read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw
    assert vectors["format"] == 2 and vectors["about"]
    for section in conformance.SECTIONS:
        assert isinstance(vectors[section], list) and vectors[section], section
    assert set(vectors) == {"format", "about", *conformance.SECTIONS}


def test_this_package_reproduces_every_vector(vectors):
    assert conformance.check_all(vectors) == []


def test_the_generator_check_passes():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_conformance.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "CONFORMANCE=PASS" in result.stdout


def test_the_file_is_what_the_specification_produces(spec, vectors):
    assert VECTOR_FILE.read_bytes().decode("utf-8") == make_conformance.render(spec, vectors)


def test_every_layout_of_the_specification_has_an_encode_and_a_decode_vector(spec, vectors):
    layouts = {make_conformance.layout_key(m, layout) for m in spec["messages"] for layout in m["layouts"]}
    layouts |= {"rack_" + f["name"].lower() for f in spec["rack"]["frames"]}   # the frames of the rack have the same vectors
    assert {e["layout"] for e in vectors["frames_encode"]} == layouts
    assert {e["layout"] for e in vectors["frames_decode"]} == layouts


def test_every_identifier_is_in_the_vectors_once(spec, vectors):
    assert [e["id"] for e in vectors["identifiers_all"]] == [m["id"] for m in spec["messages"]]


def test_decode_vectors_cover_the_legacy_short_forms_and_the_refusals(vectors):
    names = " | ".join(e["name"] for e in vectors["frames_decode"])
    assert "four bytes (older firmware)" in names and "five bytes" in names and "legacy form" in names
    assert any(e["fields"] is None for e in vectors["frames_decode"])
    assert any(e.get("strict") for e in vectors["frames_decode"])
    assert len(vectors["frames_rejected"]) >= 30
    assert any("not the magic one" in e["name"] for e in vectors["frames_rejected"])


def test_the_slcan_vectors_include_the_extended_frame_and_the_lenient_hex_cases(vectors):
    names = {e["name"] for e in vectors["slcan_decode"]}
    assert {"signed identifier", "0x-prefixed identifier", "underscore in identifier"} <= names
    assert any("extended frame" in n for n in names) and any("remote request" in n for n in names)
    streams = {e["name"] for e in vectors["slcan_stream"]}
    assert any("extended" in n for n in streams) and any("status character" in n for n in streams)


def test_a_wrong_vector_is_caught(vectors):
    broken = copy.deepcopy(vectors)
    broken["frames_encode"][0]["frame"]["data"] = "FF" + broken["frames_encode"][0]["frame"]["data"][2:]
    assert any(line.startswith("frames_encode") for line in conformance.check_all(broken))
    broken = copy.deepcopy(vectors)
    broken["magic_payloads"][0]["data"] = "00000000"
    assert any(line.startswith("magic_payloads") for line in conformance.check_all(broken))
    broken = copy.deepcopy(vectors)
    broken["frames_rejected"][0]["fields"] = copy.deepcopy(broken["frames_encode"][0]["fields"])
    broken["frames_rejected"][0]["layout"] = broken["frames_encode"][0]["layout"]
    assert any(line.startswith("frames_rejected") for line in conformance.check_all(broken))
    broken = copy.deepcopy(vectors)
    del broken["slcan_stream"]
    assert any("slcan_stream" in line for line in conformance.check_all(broken))


def test_the_generator_refuses_an_example_whose_bytes_disagree_with_its_layout(spec):
    wrong = copy.deepcopy(spec)
    wrong["messages"][0]["layouts"][0]["examples"][0]["data"] = "02"
    with pytest.raises(SystemExit):
        make_conformance.build(wrong)


def test_the_independent_packer_agrees_with_the_generated_encoder(spec):
    from urtc_common import protocol

    for message in spec["messages"]:
        for layout in message["layouts"]:
            key = make_conformance.layout_key(message, layout)
            for example in layout.get("examples", []):
                fields = {k: (bytes.fromhex(v) if isinstance(v, str) else v) for k, v in example["fields"].items()}
                _, data = protocol.encode(key, **fields)
                assert data == make_conformance.ref_encode(layout, example["fields"]), (key, example["name"])


# ---- the copies the other repositories keep today ----------------------------------------------------------------------------
COPIES = (
    "URTC-DOCS/tests/fixtures/can_conformance_vectors.json",
    "URTC-FLASHER/tests/fixtures/can_conformance_vectors.json",
    "URTC-TESTER/tests/fixtures/can_conformance_vectors.json",
    "URTC-WEB-STUDIO/src/lib/canConformance.vectors.json",
)


@pytest.mark.parametrize("relative", COPIES)
def test_the_hand_written_sections_equal_the_copy_in_use(relative, sibling, vectors):
    other = json.loads(sibling(relative).read_text(encoding="utf-8"))
    for section in conformance.SECTIONS_LEGACY:
        assert vectors[section] == other[section], f"{relative}: {section}"


# ---- the generated TypeScript -------------------------------------------------------------------------------------------------
def test_the_generated_typescript_reproduces_the_vectors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run([node, str(ROOT / "tests" / "ts" / "run_vectors.mjs")], capture_output=True, text=True, timeout=120)
    if result.returncode != 0 and ("ERR_UNKNOWN_FILE_EXTENSION" in result.stderr or "Unknown file extension" in result.stderr):
        pytest.skip("this Node does not strip TypeScript types (22.18 or newer does)")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["problems"] == []
    assert report["checked"] > 300
