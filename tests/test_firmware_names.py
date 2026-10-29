# =============================================================================
# URTC-COMMON - tests/test_firmware_names.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""How the files of a firmware release are named: the generated module, the specification and the programs that carry a copy of the rule."""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest

from urtc_common import firmware_names as names

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "spec" / "firmware_images.json").read_text(encoding="utf-8"))


def test_the_module_follows_the_specification():
    assert names.PREFIX == SPEC["prefix"] and names.BOARDS == tuple(SPEC["boards"]) and names.KINDS == tuple(SPEC["kinds"])
    assert names.IMAGE_EXTENSION == SPEC["image_extension"] and names.SIDECAR_SUFFIXES == tuple(SPEC["sidecar_suffixes"])


def test_every_combination_builds_and_parses_back():
    for board, kind in itertools.product(names.BOARDS, names.KINDS):
        for version in ("0.4.1", "0.8.0.2", "10.20.30"):
            name = names.image_name(board, kind, version)
            assert name == f"URTC_{board}_{kind}_v{version}.bin"
            assert names.parse_image_name(name) == (board, kind, version)


def test_the_case_of_the_name_does_not_matter_when_reading():
    assert names.parse_image_name("urtc_main_firmware_v0.4.1.BIN") == ("MAIN", "FIRMWARE", "0.4.1")
    assert names.image_name("main", "firmware", "0.4.1") == "URTC_MAIN_FIRMWARE_v0.4.1.bin"


@pytest.mark.parametrize("name", [
    "URTC_MAIN_FIRMWARE_v0.4.1.bin.sha256", "URTC_MAIN_FIRMWARE_v0.4.1.hex", "URTC_MAIN_FIRMWARE_v0.4.1", "URTC_MAIN_FIRMWARE_v.bin", "URTC_MAIN_FIRMWARE_v1.bin",
    "URTC_MAIN_FIRMWARE_va.b.bin", "URTC_TOP_FIRMWARE_v0.4.1.bin", "URTC_MAIN_APP_v0.4.1.bin", "XURTC_MAIN_FIRMWARE_v0.4.1.bin", " URTC_MAIN_FIRMWARE_v0.4.1.bin",
    "URTC_MAIN_FIRMWARE_v0.4.1.bin\n", "../URTC_MAIN_FIRMWARE_v0.4.1.bin", "",
])
def test_what_is_not_an_image_is_not_parsed(name):
    assert names.parse_image_name(name) is None


@pytest.mark.parametrize("args", [("TOP", "FIRMWARE", "1.2"), ("MAIN", "APP", "1.2"), ("MAIN", "FIRMWARE", "1"), ("MAIN", "FIRMWARE", "v1.2"), ("MAIN", "FIRMWARE", "1.2 ")])
def test_building_refuses_parts_that_are_not_listed(args):
    with pytest.raises(ValueError):
        names.image_name(*args)


def test_the_files_that_travel_with_an_image():
    image = names.image_name("MAIN", "FIRMWARE", "0.4.1")
    assert names.sidecar_names(image) == (image + ".sha256", image + ".manifest.json", image + ".sig")
    assert all(names.is_sidecar(item) for item in names.sidecar_names(image))
    assert not names.is_sidecar(image) and names.parse_image_name(names.sidecar_names(image)[0]) is None


def test_the_typescript_module_carries_the_same_rule():
    source = (ROOT / "generated" / "firmwareNames.ts").read_text(encoding="utf-8")
    pattern = re.search(r"FIRMWARE_IMAGE_NAME = /(.+)/i;", source).group(1)
    assert re.compile(pattern, re.IGNORECASE).pattern == names.IMAGE_NAME.pattern.replace("\\/", "/")
    for fragment in (json.dumps(SPEC["boards"]), json.dumps(SPEC["kinds"]), json.dumps(SPEC["sidecar_suffixes"])):
        assert fragment in source


def test_the_image_pattern_matches_the_images_of_the_other_programs(sibling):
    flasher = sibling("URTC-FLASHER/firmware")
    images = [item for item in flasher.iterdir() if item.suffix == ".bin"]
    assert images, "the flasher carries no image"
    for item in images:
        assert names.parse_image_name(item.name) is not None, item.name
    for item in flasher.iterdir():
        if item.suffix == ".bin" or item.name in {".gitkeep", "firmware_manifest.json", "firmware_manifest.json.sig"}:
            continue
        stem = next((image.name for image in images if item.name.startswith(image.name)), None)
        assert stem is not None and item.name[len(stem):] in {".sha256", ".manifest.json", ".sig", ".sha256.sig", ".manifest.json.sig"}, item.name


def test_the_flasher_lists_only_suffixes_the_specification_lists(sibling):
    source = sibling("URTC-FLASHER/flasher_github.py").read_text(encoding="utf-8")
    listed = re.search(r"SIDECAR_SUFFIXES\s*=\s*\(([^)]*)\)", source).group(1)
    suffixes = re.findall(r'"([^"]+)"', listed)
    assert suffixes and set(suffixes) <= set(names.SIDECAR_SUFFIXES)


def test_the_web_studio_reads_the_names_with_the_generated_rule(sibling):
    source = sibling("URTC-WEB-STUDIO/src/lib/firmwareImage.ts").read_text(encoding="utf-8")
    assert "firmwareNames" in source
