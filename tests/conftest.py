# =============================================================================
# URTC-COMMON - tests/conftest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Shared fixtures. Nothing here needs the sibling repositories; the tests that read them skip when they are absent."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture(scope="session")
def spec() -> dict:
    return json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def vectors() -> dict:
    return json.loads((ROOT / "conformance" / "can_vectors.json").read_text(encoding="utf-8"))


def workspace() -> Path:
    """The folder that holds the repositories of the ecosystem next to this one (URTC_WORKSPACE overrides it)."""
    return Path(os.environ.get("URTC_WORKSPACE", ROOT.parent))


@pytest.fixture(scope="session")
def sibling():
    """sibling('URTC-FLASHER/flasher_config.py') -> the path, or a skip when that checkout is not next to this one."""

    def find(relative: str) -> Path:
        path = workspace() / relative
        if not path.exists():
            pytest.skip(f"{relative.split('/')[0]} is not checked out next to this repository")
        return path

    return find
