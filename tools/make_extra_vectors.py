#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_extra_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the fault recorder and of the rack, and the C table the rack firmware checks itself against.

* ``conformance/blackbox_vectors.json``  records (hex) with the rows and the CSV a reader must produce, and records it must refuse
* ``conformance/rack_vectors.json``      serial frames, command checks, CAN data and short link scenarios of the rack
* ``conformance/fuzz_corpus.txt``        frames for fuzzing a board made from the specification (valid, invalid and random), one per line
* ``generated/rack_vectors.h``           the rack vectors as C tables (the rack repository compiles them into a host test)
* ``generated/urtc_fw_vectors.h``        the vectors of ``conformance/can_vectors.json`` that the firmware itself must pass and the check
                                         values of the shared checksum, as C tables (the firmware repository compiles them into a host test)

``--check`` writes nothing and fails when a file differs from what this tool produces.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from urtc_common import blackbox as bb  # noqa: E402
from urtc_common import fuzz  # noqa: E402
from urtc_common import rack_sim as rk  # noqa: E402
from urtc_common import thermal_view as tv  # noqa: E402

BB_OUT = ROOT / "conformance" / "blackbox_vectors.json"
RK_OUT = ROOT / "conformance" / "rack_vectors.json"
RK_H = ROOT / "generated" / "rack_vectors.h"
FW_H = ROOT / "generated" / "urtc_fw_vectors.h"
CAN_VECTORS = ROOT / "conformance" / "can_vectors.json"
FUZZ_OUT = ROOT / "conformance" / "fuzz_corpus.txt"
TV_OUT = ROOT / "conformance" / "thermal_vectors.json"
PROTOCOL_ORDER = ("ok", "incomplete", "bad_sof", "unsupported_version", "length_out_of_range", "crc_mismatch")
COMMAND_ORDER = ("ok", "wrong_payload_len", "tool_id_absent", "temp_out_of_range", "tool_id_invalid", "tool_not_heatable")
ACTION_ORDER = ("none", "set_target", "safe_state")


def _samples(count: int, start_tick: int, error_at: int | None, tool: int = 0) -> list[bb.Sample]:
    out = []
    for i in range(count):
        temp = 300 + (i * 3) % 40 if error_at is None or i < error_at else 460
        flags = 0
        if error_at is not None and i >= error_at:
            flags = 0x02 | (1 << 2)
        out.append(bb.Sample((start_tick + i * 150) & 0xFFFFFFFF, tool, temp, 320, flags))
    return out


def blackbox_vectors() -> dict:
    ok = []
    for name, count, widx, start, err in (("partial ring, no fault", 12, None, 1000, None), ("full ring after a wrap", 67, 20, 4_294_966_000, 60),
                                           ("full ring, write index 0", 67, 0, 500, 66)):
        raw = bb.build(_samples(count, start, err), widx)
        rec = bb.parse(raw)
        ok.append({"name": name, "hex": raw.hex().upper(), "sample_count": rec.sample_count, "write_index": rec.write_index,
                   "trigger_index": rec.trigger_index, "rows": bb.rows(rec), "csv": bb.to_csv(rec)})
    good = bytes(bb.build(_samples(5, 100, None)))
    bad = []
    flipped = bytearray(good)
    flipped[10] ^= 0x01
    bad.append({"name": "one flipped byte", "hex": bytes(flipped).hex().upper(), "error": "checksum"})
    no_magic = bytearray(good)
    no_magic[0] ^= 0xFF
    bad.append({"name": "no magic number", "hex": bytes(no_magic).hex().upper(), "error": "magic"})
    ver = bytearray(good)
    ver[4] = 3
    bad.append({"name": "unknown version", "hex": bytes(ver).hex().upper(), "error": "version"})
    bad.append({"name": "too short", "hex": good[:100].hex().upper(), "error": "record is"})
    return {"format": 1, "about": "Fault recorder records: what a reader must decode and what it must refuse. The layout is the firmware's, little-endian.",
            "record_size": bb.RECORD_SIZE, "chunks": bb.CHUNK_COUNT, "valid": ok, "invalid": bad}


def rack_vectors() -> dict:
    frames = []
    for name, seq, cmd, payload in (("set 200 C on the soldering iron", 1, 1, bytes([0, 200, 0])), ("set 0 on the hot air nozzle", 255, 1, bytes([19, 0, 0])),
                                    ("unknown command, empty", 7, 0x7E, b""), ("full payload", 9, 1, bytes(range(16)))):
        frames.append({"name": name, "seq": seq, "cmd": cmd, "payload": payload.hex().upper(), "frame": rk.encode_frame(seq, cmd, payload).hex().upper()})
    good = rk.encode_set_preheat(3, 0, 250)
    parse = [{"name": "good frame", "hex": good.hex().upper(), "status": "ok"}]
    parse.append({"name": "short", "hex": good[:5].hex().upper(), "status": "incomplete"})
    parse.append({"name": "frame cut after the header", "hex": good[:7].hex().upper(), "status": "incomplete"})
    parse.append({"name": "wrong start byte", "hex": (b"\x5A" + good[1:]).hex().upper(), "status": "bad_sof"})
    parse.append({"name": "version 2", "hex": (good[:1] + b"\x02" + good[2:]).hex().upper(), "status": "unsupported_version"})
    parse.append({"name": "length 17", "hex": (good[:4] + b"\x11" + good[5:]).hex().upper(), "status": "length_out_of_range"})
    parse.append({"name": "bad crc", "hex": (good[:-1] + bytes([good[-1] ^ 0xFF])).hex().upper(), "status": "crc_mismatch"})
    validate = []
    for name, payload in (("soldering 250", bytes([0, 250, 0])), ("soldering 400", bytes([0, 144, 1])), ("soldering 401", bytes([0, 145, 1])),
                          ("printer 310", bytes([10, 54, 1])), ("printer 311", bytes([10, 55, 1])), ("hot air 400", bytes([19, 144, 1])),
                          ("gripper 0 (no heater, target 0)", bytes([6, 0, 0])), ("gripper 100", bytes([6, 100, 0])),
                          ("no tool (31)", bytes([31, 0, 0])), ("tool 25", bytes([25, 0, 0])), ("tool byte 32", bytes([32, 0, 0])),
                          ("two bytes", bytes([0, 1])), ("four bytes", bytes([0, 1, 0, 0])), ("empty", b"")):
        status, tool, target = rk.validate_set_preheat(payload)
        validate.append({"name": name, "payload": payload.hex().upper(), "status": status, "tool": tool if status == "ok" else None,
                         "target": target if status == "ok" else None})
    can = []
    for name, seq, tool, target in (("soldering 250", 4, 0, 250), ("hot air 350", 200, 19, 350), ("off", 0, 5, 0)):
        can.append({"name": name, "id": rk.CAN_ID_SET_PREHEAT, "seq": seq, "tool": tool, "target": target,
                    "data": rk.encode_set_preheat_can(seq, tool, target).hex().upper()})
    # Short link scenarios: each step is (time, frame) and the decision the firmware takes.
    scenarios = [
        {"name": "apply, retransmit, stale, new", "steps": [
            (0, rk.encode_set_preheat(10, 0, 200)), (20, rk.encode_set_preheat(10, 0, 200)), (40, rk.encode_set_preheat(9, 0, 250)), (60, rk.encode_set_preheat(11, 0, 250))]},
        {"name": "refused command sends the tool to the safe state", "steps": [
            (0, rk.encode_set_preheat(1, 0, 200)), (10, rk.encode_set_preheat(2, 0, 500)), (20, rk.encode_set_preheat(2, 0, 200))]},
        {"name": "silence resets the sequences", "steps": [
            (0, rk.encode_set_preheat(50, 19, 300)), (100, rk.encode_set_preheat(50, 19, 300)), (1000, rk.encode_set_preheat(50, 19, 300))]},
        {"name": "noise changes nothing", "steps": [
            (0, rk.encode_set_preheat(1, 0, 200)), (10, b"\xA5\x01\x02"), (20, rk.encode_frame(2, 0x7E, b"")), (30, rk.encode_set_preheat(1, 6, 100))]},
    ]
    out_scen = []
    for sc in scenarios:
        lw = _Watchdog()
        steps = []
        for t, buf in sc["steps"]:
            decision = lw.decide(buf, t)
            steps.append({"time_ms": t, "frame": buf.hex().upper(), **decision})
        out_scen.append({"name": sc["name"], "steps": steps})
    verify = []
    for name, occupied, commanded, measured, ambient, elapsed in (
            ("no reading", True, 200, None, 24.0, 0), ("empty and cold", False, 0, 25.0, 24.0, 0), ("empty with a heater on", False, 0, 80.0, 24.0, 0),
            ("empty, a little warm", False, 0, 60.0, 24.0, 0), ("idle and cool", True, 0, 30.0, 24.0, 0), ("idle and still hot", True, 0, 120.0, 24.0, 0),
            ("heating, early", True, 300, 150.0, 24.0, 5000), ("heating, too slow", True, 300, 150.0, 24.0, 60000), ("reached", True, 300, 290.0, 24.0, 20000),
            ("reached, just inside", True, 300, 285.0, 24.0, 20000), ("just outside, early", True, 300, 284.0, 24.0, 59999), ("overshoot", True, 300, 330.0, 24.0, 90000),
            ("overshoot edge", True, 300, 325.0, 24.0, 90000)):
        verify.append({"name": name, "occupied": occupied, "commanded_c": commanded, "measured_c": measured, "ambient_c": ambient, "elapsed_ms": elapsed,
                       "verdict": rk.verify_slot(occupied, commanded, measured, ambient, elapsed)})
    return {"format": 1, "about": "Frames, command checks, CAN data, link scenarios and thermal slot checks of the tool rack; the rack firmware and the simulator both pass them.",
            "frames": frames, "parse": parse, "validate": validate, "can": can, "scenarios": out_scen, "verify": verify,
            "limits": {"ceiling_c": rk.RACK_CEILING_C, "link_timeout_ms": rk.LINK_TIMEOUT_MS, "printer_c": rk.MAX_PREHEAT_C[10]}}


class _Watchdog:
    """The decision of the firmware's rack_link_decide for a frame, written down independently of the C code."""

    def __init__(self) -> None:
        self.last_rx: int | None = None
        self.seq: dict[int, int] = {}

    def decide(self, buf: bytes, now: int) -> dict:
        none = {"action": "none", "tool": 0, "temp": 0, "ack": 0}
        status, frame = rk.parse_frame(buf)
        if frame is None:
            return none
        if self.last_rx is not None and now - self.last_rx >= rk.LINK_TIMEOUT_MS:
            self.seq.clear()
        self.last_rx = now
        if frame["cmd"] != rk.CMD_SET_PREHEAT:
            return none
        status, tool, target = rk.validate_set_preheat(frame["payload"])
        if status != "ok":
            if frame["payload"] and frame["payload"][0] <= rk.TOOL_ID_LAST:
                return {"action": "safe_state", "tool": frame["payload"][0], "temp": 0, "ack": 0}
            return none
        prev = self.seq.get(tool)
        if prev is not None:
            d = (frame["seq"] - prev) & 0xFF
            if d == 0 or d >= 128:
                return {**none, "ack": 1}
        self.seq[tool] = frame["seq"]
        return {"action": "set_target", "tool": tool, "temp": target, "ack": 1}


def rack_header(v: dict) -> str:
    def arr(data: bytes) -> str:
        return "{" + ", ".join(f"0x{b:02X}" for b in data) + "}" if data else "{0}"

    lines = [
        "// GENERATED from spec by tools/make_extra_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef RACK_VECTORS_H", "#define RACK_VECTORS_H", "", "#include <math.h>", "#include <stdint.h>", "",
        "typedef struct { const char *name; uint8_t seq, cmd, payload_len; uint8_t payload[16]; uint8_t frame_len; uint8_t frame[22]; } rack_vec_frame_t;",
        "typedef struct { const char *name; uint8_t len; uint8_t buf[24]; int status; } rack_vec_parse_t; // protocol_status_t order",
        "typedef struct { const char *name; uint8_t len; uint8_t payload[4]; int status; int tool; int target; } rack_vec_validate_t; // rack_command_status_t order",
        "typedef struct { const char *name; uint8_t seq, tool; uint16_t target; uint8_t data[8]; } rack_vec_can_t;",
        "typedef struct { const char *name; int occupied; int commanded_c; float measured_c; float ambient_c; uint32_t elapsed_ms; int verdict; } rack_vec_verify_t; // slot_verdict_t order",
        "typedef struct { int scenario; const char *name; uint32_t time_ms; uint8_t len; uint8_t buf[24]; int action; int tool; int temp; int ack; } rack_vec_step_t; // rack_action_t order",
        "",
    ]
    lines.append("static const rack_vec_frame_t RACK_VEC_FRAMES[] = {")
    for f in v["frames"]:
        p, fr = bytes.fromhex(f["payload"]), bytes.fromhex(f["frame"])
        lines.append(f'    {{"{f["name"]}", {f["seq"]}, {f["cmd"]}, {len(p)}, {arr(p)}, {len(fr)}, {arr(fr)}}},')
    lines += ["};", "", "static const rack_vec_parse_t RACK_VEC_PARSE[] = {"]
    for p in v["parse"]:
        b = bytes.fromhex(p["hex"])
        lines.append(f'    {{"{p["name"]}", {len(b)}, {arr(b)}, {PROTOCOL_ORDER.index(p["status"])}}},')
    lines += ["};", "", "static const rack_vec_validate_t RACK_VEC_VALIDATE[] = {"]
    for p in v["validate"]:
        b = bytes.fromhex(p["payload"])
        tool = -1 if p["tool"] is None else p["tool"]
        target = -1 if p["target"] is None else p["target"]
        lines.append(f'    {{"{p["name"]}", {len(b)}, {arr(b)}, {COMMAND_ORDER.index(p["status"])}, {tool}, {target}}},')
    lines += ["};", "", "static const rack_vec_can_t RACK_VEC_CAN[] = {"]
    for c in v["can"]:
        lines.append(f'    {{"{c["name"]}", {c["seq"]}, {c["tool"]}, {c["target"]}, {arr(bytes.fromhex(c["data"]))}}},')
    lines += ["};", "", "static const rack_vec_step_t RACK_VEC_STEPS[] = {"]
    for i, sc in enumerate(v["scenarios"]):
        for s in sc["steps"]:
            b = bytes.fromhex(s["frame"])
            lines.append(f'    {{{i}, "{sc["name"]}", {s["time_ms"]}, {len(b)}, {arr(b)}, {ACTION_ORDER.index(s["action"])}, {s["tool"]}, {s["temp"]}, {s["ack"]}}},')
    lines += ["};", "", "static const rack_vec_verify_t RACK_VEC_VERIFY[] = {"]
    for c in v["verify"]:
        measured = "NAN" if c["measured_c"] is None else repr(float(c["measured_c"])) + "f"
        lines.append(f'    {{"{c["name"]}", {1 if c["occupied"] else 0}, {c["commanded_c"]}, {measured}, {float(c["ambient_c"])!r}f, {c["elapsed_ms"]}u, {rk.SLOT_VERDICTS.index(c["verdict"])}}},')
    lines += ["};", "", "#define RACK_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // RACK_VECTORS_H", ""]
    return "\n".join(lines)


CRC8_CASES = (
    ("empty", b""), ("one zero byte", b"\x00"), ("one 0xFF byte", b"\xff"), ("four zero bytes", b"\x00" * 4),
    ("the check text", b"123456789"), ("a rack frame header", bytes([0xA5, 0x01, 0x01, 0x01, 0x03, 0x00, 0xC8, 0x00])),
    ("the 255 byte ramp", bytes(range(255))),
)


def fw_header() -> str:
    """The vectors of can_vectors.json that a firmware can be held to, as C tables."""
    data = json.loads(CAN_VECTORS.read_text(encoding="utf-8"))
    ids = ", ".join(f"0x{int(i['id'], 16):03X}u" for i in data["identifiers_all"])

    def patch(value: int | None) -> int:
        return 0xFF if value is None or value < 0 else value

    lines = [
        "// GENERATED from spec by tools/make_extra_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef URTC_FW_VECTORS_H", "#define URTC_FW_VECTORS_H", "", "#include <stdint.h>", "",
        "// a test that uses only some of the tables must not get an unused-variable warning for the others",
        "#if defined(__GNUC__)", "#define URTC_VEC_TABLE static const __attribute__((unused))", "#else", "#define URTC_VEC_TABLE static const", "#endif", "",
        "// patch 0xFF = no patch number (the firmware's URTC_PATCH_UNKNOWN); a patch above 0x7F is what the firmware drops",
        "typedef struct { uint8_t minor; uint8_t patch; int accepts_patch; uint16_t expect; } urtc_vec_minor_t;",
        "// expect: -1 the candidate is older, 0 same or not comparable, 1 newer; patch 0xFF = unknown",
        "typedef struct { uint8_t inst_major, inst_minor, inst_patch, cand_major, cand_minor, cand_patch; int expect; } urtc_vec_order_t;",
        "typedef struct { const char *name; uint16_t id; uint8_t data[4]; } urtc_vec_magic_t;",
        "typedef struct { const char *name; uint8_t len; uint8_t data[255]; uint8_t crc; } urtc_vec_crc8_t;", "",
        f"URTC_VEC_TABLE uint16_t URTC_VEC_IDENTIFIERS[] = {{{ids}}};", "",
        "URTC_VEC_TABLE urtc_vec_minor_t URTC_VEC_MINOR[] = {",
    ]
    for c in data["minor_field"]:
        lines.append(f'    {{{c["minor"]}, {patch(c["patch"])}, {1 if c["bootloader_accepts_patch"] else 0}, {c["expect"]}u}},')
    lines += ["};", "", "URTC_VEC_TABLE urtc_vec_order_t URTC_VEC_ORDER[] = {"]
    for c in data["version_order"]:
        i, n = c["installed"], c["candidate"]
        lines.append(f'    {{{i[0]}, {i[1]}, {patch(i[2])}, {n[0]}, {n[1]}, {patch(n[2])}, {c["expect"]}}},')
    lines += ["};", "", "URTC_VEC_TABLE urtc_vec_magic_t URTC_VEC_MAGIC[] = {"]
    for m in data["magic_payloads"]:
        raw = bytes.fromhex(m["data"])
        lines.append(f'    {{"{m["name"]}", 0x{int(m["id"], 16):03X}u, {{' + ", ".join(f"0x{b:02X}" for b in raw) + "}},")
    lines += ["};", "", "URTC_VEC_TABLE urtc_vec_crc8_t URTC_VEC_CRC8[] = {"]
    for name, raw in CRC8_CASES:
        body = ", ".join(f"0x{b:02X}" for b in raw) if raw else "0"
        lines.append(f'    {{"{name}", {len(raw)}, {{{body}}}, 0x{rk.crc8(raw):02X}}},')
    lines += ["};", "", "#define URTC_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // URTC_FW_VECTORS_H", ""]
    return "\n".join(lines)


def thermal_vectors() -> dict:
    cases = []
    frames = {
        "ramp": [[20.0, 25.0, 30.0, 35.0], [40.0, 45.0, 50.0, 55.0], [60.0, 65.0, 70.0, 75.0]],
        "uniform": [[30.0] * 4 for _ in range(3)],
        "with an invalid pixel": [[20.0, 40.0, float("nan"), 80.0], [20.0, 40.0, 60.0, 80.0], [20.0, 40.0, 60.0, 80.0]],
    }
    for name, frame in frames.items():
        for label, rng in (("own scale", None), ("fixed 20 to 100", (20.0, 100.0))):
            cases.append({"name": f"{name}, {label}", "frame": [[None if v != v else v for v in row] for row in frame],
                          "range": rng, "rgb": tv.to_rgb_bytes(frame, rng).hex().upper()})
    sample = [[22.5 + 0.5 * (x + y * 4) for x in range(4)] for y in range(4)]
    chunks = tv.encode_chunks(sample)
    chunk_cases = [{"name": "one chunk of a 4x4 image", "hex": chunks[0].hex().upper(), "values": tv.decode_chunk(chunks[0])},
                   {"name": "limits of int16", "hex": "7FFF8000" + "0000" * 14, "values": tv.decode_chunk(bytes.fromhex("7FFF8000" + "0000" * 14))}]
    return {"format": 1, "about": "False colour of thermal frames (RGB bytes row after row) and decoded thermal chunks; the tester, the web studio and the vision companion reproduce them (the vision companion within one level per channel).",
            "false_color": cases, "chunks": chunk_cases}


def fuzz_corpus() -> str:
    spec = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
    tx = " ".join(f"{int(m['id'], 16):03X}" for m in spec["messages"] if m["direction"] in ("board_to_host", "both"))
    head = ("# Frames for fuzzing a board, made from spec/can_protocol.json by tools/make_extra_vectors.py: <id> <data hex or -> <kind> <note>\n"
            f"# transmit_ids: {tx}\n")
    return head + "\n".join(f.line() for f in fuzz.generate(spec, seed=1, random_count=400)) + "\n"


def outputs() -> dict[Path, str]:
    rv = rack_vectors()
    return {
        BB_OUT: json.dumps(blackbox_vectors(), indent=2) + "\n",
        RK_OUT: json.dumps(rv, indent=2) + "\n",
        RK_H: rack_header(rv),
        FW_H: fw_header(),
        FUZZ_OUT: fuzz_corpus(),
        TV_OUT: json.dumps(thermal_vectors(), indent=2) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if args.check:
            if current != text:
                stale.append(path.relative_to(ROOT).as_posix())
        elif current != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if args.check:
        if stale:
            print("EXTRA_VECTORS=FAIL out of date: " + ", ".join(stale) + " (run python tools/make_extra_vectors.py)", file=sys.stderr)
            return 1
        print("EXTRA_VECTORS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
