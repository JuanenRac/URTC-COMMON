# =============================================================================
# URTC-COMMON - tests/test_cli.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The command line of the package: what each command prints and the exit code it returns."""
from __future__ import annotations

import json

import pytest

from urtc_common import cli, protocol, specdata


def run(capsys: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str, str]:
    code = cli.main(list(arguments))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_an_identifier_is_read_as_hexadecimal_decimal_or_a_name():
    assert cli._resolve("0x120") == 0x120
    assert cli._resolve("288") == 0x120
    assert cli._resolve("motion_cmd") == protocol.CAN_ID_MOTION_CMD
    assert cli._resolve("MOTION_CMD") == protocol.CAN_ID_MOTION_CMD
    assert cli._resolve("NOT_A_MESSAGE") is None


def test_the_layouts_of_an_identifier_are_listed():
    assert cli._layouts_of(protocol.CAN_ID_MOTION_CMD) == ["motion_cmd"]
    assert cli._layouts_of(0x001) == []


def test_conformance_passes_on_the_shared_vectors(capsys):
    code, out, _err = run(capsys, "conformance")
    assert code == 0
    assert out.startswith("CONFORMANCE=PASS ")


def test_conformance_fails_on_a_vector_file_that_is_not_reproduced(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.conformance, "load", lambda path: {name: [{}] for name in cli.conformance.SECTIONS})
    monkeypatch.setattr(cli.conformance, "check_all", lambda vectors: ["vector 1 differs", "vector 2 differs"])
    code, _out, err = run(capsys, "conformance", "--vectors", str(tmp_path / "vectors.json"))
    assert code == 1
    assert "vector 1 differs" in err
    assert "CONFORMANCE=FAIL 2 vector(s) not reproduced" in err


def test_describe_shows_the_direction_and_the_fields(capsys):
    code, out, _err = run(capsys, "describe", "MOTION_CMD")
    assert code == 0
    first = out.splitlines()[0]
    assert first.startswith("0x120 ")
    assert "direction" in out and "steps" in out
    assert "+1 steps: u32" in out


def test_describe_refuses_an_unknown_identifier(capsys):
    code, out, err = run(capsys, "describe", "NOTHING")
    assert (code, out) == (1, "")
    assert "unknown identifier: NOTHING" in err


def test_decode_prints_each_layout_that_fits(capsys):
    code, out, _err = run(capsys, "decode", "0x120", "01 00 00 00 0A")
    assert code == 0
    line = out.strip().splitlines()[0]
    assert line.startswith("motion_cmd: ")
    fields = json.loads(line.split(": ", 1)[1])
    assert fields["direction"] == 1 and fields["steps"] == 10


def test_decode_refuses_an_unknown_identifier_a_bad_payload_and_a_payload_that_fits_nowhere(capsys):
    code, _out, err = run(capsys, "decode", "NOTHING", "00")
    assert code == 1 and "unknown identifier" in err
    code, _out, err = run(capsys, "decode", "0x120", "ZZ")
    assert code == 1 and "hexadecimal" in err
    code, _out, err = run(capsys, "decode", "0x120", "")
    assert code == 1 and "no layout of this identifier fits that payload" in err


def test_slcan_decodes_a_line_and_refuses_garbage(capsys):
    code, out, _err = run(capsys, "slcan", "t1205010A000000")
    assert code == 0
    assert out.startswith("0x120 ") and "dlc=5" in out and "data=" in out
    code, _out, err = run(capsys, "slcan", "not a frame")
    assert code == 1 and "not a valid standard SLCAN data frame" in err


def test_files_lists_every_specification_file(capsys):
    code, out, _err = run(capsys, "files")
    assert code == 0
    lines = out.strip().splitlines()
    assert [line.split(":", 1)[0] for line in lines] == list(specdata.FILES)


def test_the_virtual_board_command_hands_its_own_options_over(monkeypatch):
    seen: list[list[str]] = []
    from urtc_common import virtual_board

    monkeypatch.setattr(virtual_board, "main", lambda options: seen.append(list(options)) or 0)
    assert cli.main(["virtual-board", "--port", "0", "--once"]) == 0
    assert seen == [["--port", "0", "--once"]]


def test_the_version_option_prints_the_name_and_exits(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.startswith("urtc-common ")


def test_a_command_is_required(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main([])
    assert stopped.value.code == 2
