# =============================================================================
# URTC-COMMON - tests/sources.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Readers for the values the other repositories hard-code today. They only read text; nothing is imported from them."""
from __future__ import annotations

import ast
import re
from pathlib import Path

HEX = r"0[xX][0-9A-Fa-f]+"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def python_ints(path: Path, prefix: str = "") -> dict[str, int]:
    """Top-level ``NAME = 0x...`` assignments of a Python file."""
    out = {}
    for match in re.finditer(rf"^({re.escape(prefix)}[A-Z0-9_]+)\s*=\s*({HEX}|\d+)\b", text(path), re.M):
        out[match.group(1)] = int(match.group(2), 0)
    return out


def python_literal(path: Path, name: str):
    """The value of a top-level literal assignment (a dict, list or bytes call is evaluated safely)."""
    tree = ast.parse(text(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise KeyError(name)


def python_dict_keys(path: Path, name: str) -> list[int]:
    return [ast.literal_eval(key) for key in python_literal(path, name).keys]


def python_dict(path: Path, name: str) -> dict:
    return ast.literal_eval(python_literal(path, name))


def python_bytes(path: Path, name: str) -> bytes:
    node = python_literal(path, name)
    # bytes([0xE3, ...])
    return bytes(ast.literal_eval(node.args[0]))


def ts_ints(path: Path, prefix: str = "") -> dict[str, int]:
    out = {}
    for match in re.finditer(rf"export const ({re.escape(prefix)}[A-Z0-9_]+)\s*=\s*({HEX}|\d+)\b", text(path)):
        out[match.group(1)] = int(match.group(2), 0)
    return out


def ts_array(path: Path, name: str) -> list[int]:
    match = re.search(rf"export const {name}\s*=\s*\[([^\]]*)\]", text(path))
    assert match, name
    return [int(x.strip(), 0) for x in match.group(1).split(",") if x.strip()]


def ts_record_keys(path: Path, name: str) -> list[int]:
    match = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", text(path), re.S)
    assert match, name
    return [int(k, 0) for k in re.findall(r"^\s*(0x[0-9A-Fa-f]+|\d+)\s*:", match.group(1), re.M)]


def ts_record(path: Path, name: str) -> dict[int, str]:
    match = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", text(path), re.S)
    assert match, name
    return {int(k, 0): v for k, v in re.findall(r"^\s*(0x[0-9A-Fa-f]+|\d+)\s*:\s*'([^']*)'", match.group(1), re.M)}


def c_defines(path: Path, prefix: str = "") -> dict[str, int]:
    out = {}
    for match in re.finditer(rf"^#define\s+({re.escape(prefix)}[A-Za-z0-9_]+)\s+\(?({HEX}|\d+)[uUlL]*\)?", text(path), re.M):
        out[match.group(1)] = int(match.group(2), 0)
    return out
