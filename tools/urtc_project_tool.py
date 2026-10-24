#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/urtc_project_tool.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""One entry point for the checks and generators of a URTC repository.

    python tools/urtc_project_tool.py list                  # what this repository has
    python tools/urtc_project_tool.py ci                     # the validation the CI runs (URTC_CI=1)
    python tools/urtc_project_tool.py test                  # the tests of the repository
    python tools/urtc_project_tool.py i18n                   # the language files against the catalog
    python tools/urtc_project_tool.py vendor                 # the copies of the shared code against their lock
    python tools/urtc_project_tool.py constants | compat | status | sections | tools-doc | canbus-doc
    python tools/urtc_project_tool.py ci --repo ../URTC-FLASHER     # another repository
    python tools/urtc_project_tool.py test -- -k records            # what follows ``--`` goes to the tool

Each command runs a script that already exists in the repository (or in URTC-COMMON for the ones only it has), with the
interpreter that runs this one, and returns its exit code. A command whose script is not there is not offered (``list``)
and ends with exit code 2. Nothing here changes a file by itself: the commands are the ``--check`` forms of the generators.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Command:
    name: str
    script: str
    arguments: tuple[str, ...]
    help: str
    ci_flag: bool = False


COMMANDS: tuple[Command, ...] = (
    Command("ci", "tools/ci_validate.py", (), "The validation the CI runs", ci_flag=True),
    Command("test", "tools/build_test.py", (), "The tests of the repository"),
    Command("i18n", "tools/i18n_generate.py", ("check",), "Language files against the catalog"),
    Command("vendor", "tools/vendor_copy.py", ("check",), "Copies of the shared code against their lock (give the folder of the copy after --)"),
    Command("constants", "tools/generate_constants.py", ("--check",), "Generated constants against the specification"),
    Command("compat", "tools/compat_table.py", ("--check",), "The compatibility table"),
    Command("status", "tools/status_table.py", ("--check",), "The table of what has run and what is pending"),
    Command("sections", "tools/readme_sections.py", ("check",), "The README sections written once for every repository"),
    Command("tools-doc", "tools/generate_tools_doc.py", ("--check",), "The tool table of the firmware document"),
    Command("canbus-doc", "tools/generate_canbus_doc.py", ("--check",), "The reference half of the CAN document"),
)


def available(repo: Path) -> list[Command]:
    return [command for command in COMMANDS if (repo / command.script).is_file()]


def find(name: str) -> Command | None:
    return next((command for command in COMMANDS if command.name == name), None)


def run_command(
    command: Command, repo: Path, extra: Sequence[str] = (), runner: Callable[..., int] | None = None,
) -> int:
    script = repo / command.script
    if not script.is_file():
        print(f"urtc_project_tool: {repo.name} has no {command.script}", file=sys.stderr)
        return 2
    argv = [sys.executable, str(script), *command.arguments, *extra]
    env = {**os.environ, "URTC_CI": "1"} if command.ci_flag else None
    if runner is not None:
        return runner(argv, cwd=str(repo), env=env)
    return subprocess.call(argv, cwd=str(repo), env=env)


def main(argv: Sequence[str] | None = None, runner: Callable[..., int] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", help="list, or one of: " + ", ".join(command.name for command in COMMANDS))
    parser.add_argument("--repo", default=str(HERE.parent), help="the repository (default: the one this script is in)")
    parser.add_argument("extra", nargs="*", help="after --, arguments for the tool")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.command == "list":
        for command in available(repo):
            print(f"{command.name:11} {command.script:34} {command.help}")
        return 0
    command = find(args.command)
    if command is None:
        print(f"urtc_project_tool: unknown command {args.command!r}; try 'list'", file=sys.stderr)
        return 2
    return run_command(command, repo, args.extra, runner)


if __name__ == "__main__":
    sys.exit(main())
