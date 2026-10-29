# =============================================================================
# URTC-COMMON - tests/test_ring.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The shared byte ring of the firmware repositories, built and run with the host compiler.

A second build adds a real producer thread against a real consumer thread (where the compiler has pthreads): the
ordering the header promises is only really tested by two threads, one per side.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _build(tmp_path: Path, extra: list[str], sanitize: bool) -> Path:
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("ring.exe" if os.name == "nt" else "ring")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", f"-I{ROOT / 'firmware_base'}", str(ROOT / "tests" / "c" / "test_ring.c"), "-o", str(binary), *extra]
    if sanitize:
        attempt = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
        if attempt.returncode == 0:
            return binary
    build = subprocess.run(base, capture_output=True, text=True)  # a compiler with no sanitizer runtime (the MinGW of the Windows runner has none)
    assert build.returncode == 0, build.stderr
    return binary


def test_the_ring_follows_its_rules(tmp_path):
    binary = _build(tmp_path, [], sanitize=True)
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all ring tests pass" in run.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="the stress build needs POSIX threads")
def test_a_producer_thread_and_a_consumer_thread_keep_every_byte_in_order(tmp_path):
    binary = _build(tmp_path, ["-DURTC_RING_THREADS", "-O2", "-pthread"], sanitize=False)
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all ring tests pass" in run.stdout


def test_the_copy_set_carries_the_header_and_nothing_else():
    sys.path.insert(0, str(ROOT / "tools"))
    import vendor_copy

    assert vendor_copy.SETS["firmware_ring"] == ["firmware_base/urtc_ring.h"]
