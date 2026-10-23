# =============================================================================
# URTC-COMMON - src/urtc_common/specdata.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Where the specification files are, whether this package runs from a checkout or was installed from a wheel.

A checkout keeps them in ``spec/``, ``generated/`` and ``conformance/``; the wheel carries the same files in ``urtc_common/data/``.
The checkout wins when both exist, so a developer always reads the files they are editing.
"""
from __future__ import annotations

import json
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent
_CHECKOUT = _PACKAGE.parents[1]

# name -> (folder in a checkout, file name in the checkout and in the wheel)
FILES = {
    "spec": ("spec", "can_protocol.json"),
    "tools": ("spec", "tools.json"),
    "header": ("generated", "urtc_can_ids.h"),
    "vectors": ("conformance", "can_vectors.json"),
}


def path(kind: str) -> Path:
    """The file of ``kind`` ('spec', 'tools', 'header' or 'vectors'): from the checkout when it is there, else from the installed data."""
    folder, name = FILES[kind]
    candidate = _CHECKOUT / folder / name
    return candidate if candidate.is_file() else _PACKAGE / "data" / name


def load_spec() -> dict:
    """The CAN specification (``can_protocol.json``) as a dictionary."""
    return json.loads(path("spec").read_text(encoding="utf-8"))
