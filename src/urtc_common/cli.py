# =============================================================================
# URTC-COMMON - src/urtc_common/cli.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Small command line over the package: run the vectors, look an identifier up, decode a payload or an SLCAN line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, conformance, protocol
from .slcan import decode_line


def _resolve(text: str) -> int | None:
    """An identifier from ``0x120``, ``288`` or a canonical name such as MOTION_CMD."""
    try:
        return int(text, 0)
    except ValueError:
        return getattr(protocol, f"CAN_ID_{text.upper()}", None)


def _layouts_of(can_id: int) -> list[str]:
    return [key for key, layout in protocol.LAYOUTS.items() if layout["id"] == can_id]


def cmd_conformance(args: argparse.Namespace) -> int:
    vectors = conformance.load(Path(args.vectors)) if args.vectors else conformance.load()
    problems = conformance.check_all(vectors)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"CONFORMANCE=FAIL {len(problems)} vector(s) not reproduced", file=sys.stderr)
        return 1
    count = sum(len(vectors[name]) for name in conformance.SECTIONS)
    print(f"CONFORMANCE=PASS {count} vectors in {len(conformance.SECTIONS)} sections")
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    can_id = _resolve(args.identifier)
    info = protocol.MESSAGES.get(can_id) if can_id is not None else None
    if info is None:
        print(f"unknown identifier: {args.identifier}", file=sys.stderr)
        return 1
    print(f"0x{can_id:03X} {info['name']}  ({info['direction']}, handled by {info['handled_by']}, group {info['group']})")
    print(f"  tools: {'any' if info['tools'] is None else info['tools']}")
    for key in _layouts_of(can_id):
        layout = protocol.LAYOUTS[key]
        print(f"  {key} [{layout['role']}] dlc {layout['dlc']}")
        for field in layout["fields"]:
            print(f"    +{field['offset']} {field['name']}: {field['type']}")
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    can_id = _resolve(args.identifier)
    if can_id is None or can_id not in protocol.MESSAGES:
        print(f"unknown identifier: {args.identifier}", file=sys.stderr)
        return 1
    try:
        data = bytes.fromhex(args.payload.replace(" ", ""))
    except ValueError:
        print("the payload must be hexadecimal bytes", file=sys.stderr)
        return 1
    shown = False
    for key in _layouts_of(can_id):
        fields = protocol.decode(key, data)
        if fields is not None:
            shown = True
            printable = {name: (value.hex().upper() if isinstance(value, bytes) else value) for name, value in fields.items()}
            print(f"{key}: {json.dumps(printable)}")
    if not shown:
        print("no layout of this identifier fits that payload", file=sys.stderr)
        return 1
    return 0


def cmd_slcan(args: argparse.Namespace) -> int:
    frame = decode_line(args.line)
    if frame is None:
        print("not a valid standard SLCAN data frame", file=sys.stderr)
        return 1
    print(f"{frame.id_hex()} {frame.name() or '(unknown identifier)'} dlc={frame.dlc} data={frame.data_hex()}")
    return 0


def cmd_virtual_board(args: argparse.Namespace) -> int:
    from . import virtual_board

    return virtual_board.main(args.options)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="urtc-common", description=__doc__)
    parser.add_argument("--version", action="version", version=f"urtc-common {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("conformance", help="run the shared vectors against this package")
    run.add_argument("--vectors", help="a vectors file (default: conformance/can_vectors.json)")
    run.set_defaults(func=cmd_conformance)
    describe = sub.add_parser("describe", help="show an identifier: direction, tools and layouts")
    describe.add_argument("identifier", help="0x120, 288 or MOTION_CMD")
    describe.set_defaults(func=cmd_describe)
    decode = sub.add_parser("decode", help="decode a payload for an identifier")
    decode.add_argument("identifier")
    decode.add_argument("payload", help="hexadecimal bytes, for example 0A000100")
    decode.set_defaults(func=cmd_decode)
    line = sub.add_parser("slcan", help="decode one received SLCAN line")
    line.add_argument("line")
    line.set_defaults(func=cmd_slcan)
    board = sub.add_parser("virtual-board", help="serve a virtual board behind an SLCAN adapter on a TCP port (options as for python -m urtc_common.virtual_board)")
    board.add_argument("options", nargs=argparse.REMAINDER)
    board.set_defaults(func=cmd_virtual_board)
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["virtual-board"]:
        return cmd_virtual_board(argparse.Namespace(options=arguments[1:]))  # its own options, which this parser would not know
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
