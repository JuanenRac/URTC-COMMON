#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/min_common.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Keep the ``min_common`` of every manifest equal to the version of URTC-COMMON that its repository carries.

A repository that carries copies of URTC-COMMON has one or more ``urtc_common.lock.json`` files, each with the version the copy was made from. The oldest
of them is the oldest version of the shared contracts the repository works with, and that is what its ``urtc.project.json`` says in ``min_common``. The
updater reads the field and only warns (it never holds an update back), so a wrong value would be a false notice; this tool keeps it true::

    python tools/min_common.py check [REPO ...]          # list the repositories whose manifest says something else; exit 1 when there is one
    python tools/min_common.py apply [REPO ...]          # write the value into the manifest (the rest of the file is left byte for byte)

Without a repository it takes every ``URTC*`` folder next to this repository. A repository without any lock (it carries no copy) must not have the field
and is left alone. ``vendor_copy.py sync`` and ``refresh`` call ``apply`` for the repository they wrote into, so a re-pin updates the manifest by itself.
Standard library only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

LOCK_NAME = "urtc_common.lock.json"
MANIFEST = "urtc.project.json"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
SKIP_DIRS = {".git", "node_modules", "dist", "build", "target", "__pycache__", ".venv"}


def _key(text: str) -> tuple[int, ...]:
    numbers = [int(part) for part in text.split(".")]
    return tuple(numbers + [0] * (4 - len(numbers)))


def lock_files(repo: Path) -> list[Path]:
    """The lock files of the repository: the tracked ones when it is a git checkout, otherwise a walk that skips the usual build folders."""
    try:
        listed = subprocess.run(["git", "-C", str(repo), "ls-files", "--", f"*{LOCK_NAME}"], capture_output=True, text=True, timeout=60, check=True).stdout.split("\n")
        found = [repo / line.strip() for line in listed if line.strip()]
        if found:
            return found
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    stack = [repo]
    while stack:
        folder = stack.pop()
        try:
            children = list(folder.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name not in SKIP_DIRS:
                stack.append(child)
            elif child.name == LOCK_NAME:
                found.append(child)
    return sorted(found)


def pinned(repo: Path) -> str | None:
    """The oldest URTC-COMMON version among the locks of the repository; None when it has no lock or none holds a readable version."""
    versions: list[str] = []
    for path in lock_files(repo):
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("urtc_common_version")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, str) and VERSION_RE.fullmatch(value):
            versions.append(value)
    return min(versions, key=_key) if versions else None


def declared(repo: Path) -> str | None:
    try:
        value = json.loads((repo / MANIFEST).read_text(encoding="utf-8")).get("min_common")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def problem(repo: Path) -> str | None:
    """What is wrong with the ``min_common`` of the repository, or None."""
    if not (repo / MANIFEST).is_file():
        return None
    want, have = pinned(repo), declared(repo)
    if want is None:
        return f"{repo.name}: min_common is {have!r} but the repository carries no copy of URTC-COMMON" if have is not None else None
    if have is None:
        return f"{repo.name}: min_common is missing (the copies of URTC-COMMON are from {want})"
    if have != want:
        return f"{repo.name}: min_common is {have} but the oldest copy of URTC-COMMON is {want}"
    return None


def apply(repo: Path) -> bool:
    """Write the right ``min_common`` into the manifest, changing nothing else; True when the file changed."""
    path = repo / MANIFEST
    if not path.is_file():
        return False
    want = pinned(repo)
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    current = re.search(r'(?m)^(\s*)"min_common"\s*:\s*"[^"]*",?[ \t]*\r?\n', raw)
    if want is None:
        if current is None:
            return False
        # the field closes the object when it is the last one; take care of the comma before it
        cleaned = raw[: current.start()] + raw[current.end():]
        cleaned = re.sub(r",(\s*\})", r"\1", cleaned)
        path.write_bytes(cleaned.encode("utf-8"))
        return True
    if current is not None:
        line = f'{current.group(1)}"min_common": "{want}"' + ("," if current.group(0).rstrip().endswith(",") else "") + newline
        updated = raw[: current.start()] + line + raw[current.end():]
    else:
        head = re.search(r'(?m)^(\s*)"version"\s*:\s*"[^"]*",[ \t]*\r?\n', raw)
        if head is None:
            return False
        updated = raw[: head.end()] + f'{head.group(1)}"min_common": "{want}",{newline}' + raw[head.end():]
    if updated == raw:
        return False
    json.loads(updated)  # never leave a manifest that does not parse
    path.write_bytes(updated.encode("utf-8"))
    return True


def repos(arguments: list[str]) -> list[Path]:
    if arguments:
        return [Path(a).resolve() for a in arguments]
    base = Path(__file__).resolve().parents[2]
    return sorted(p for p in base.glob("URTC*") if p.is_dir() and (p / MANIFEST).is_file())


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("check", "apply"):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    command, folders = args[0], repos(args[1:])
    if command == "apply":
        for repo in folders:
            if apply(repo):
                print(f"{repo.name}: min_common written")
        return 0
    found = [text for repo in folders if (text := problem(repo))]
    for text in found:
        print(f"MIN_COMMON=FAIL {text}", file=sys.stderr)
    if not found:
        print(f"MIN_COMMON=PASS {len(folders)} repositories")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
