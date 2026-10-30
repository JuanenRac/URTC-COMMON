#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_extra_vectors.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the vectors of the fault recorder and of the rack, and the C table the rack firmware checks itself against.

* ``conformance/blackbox_vectors.json``  records (hex) with the rows and the CSV a reader must produce, records it must refuse and the scenarios the recorder of the firmware replays
* ``generated/blackbox_vectors.h``       the recorder scenarios as C tables (the firmware repository replays them against ``firmware_blackbox.c``)
* ``conformance/rack_vectors.json``      serial frames, command checks, CAN data and short link scenarios of the rack
* ``conformance/fuzz_corpus.txt``        frames for fuzzing a board made from the specification (valid, invalid and random), one per line
* ``conformance/sensor_vectors.json``    frames and thermal readings of the sensor link of the vision head
* ``conformance/rate_vectors.json``      decisions of the minimum-interval limiter of a link (reference: ``urtc_common.frame_layer``)
* ``generated/rate_vectors.h``           the rate vectors as C tables (the firmware repositories that use ``urtc_rate_limiter.h`` compile them into a host test)
* ``generated/sensor_vectors.h``         the sensor vectors as C tables (the vision repository compiles them into a host test)
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
from urtc_common import frame_layer as fl  # noqa: E402
from urtc_common import fuzz  # noqa: E402
from urtc_common import rack_sim as rk  # noqa: E402
from urtc_common import sensor_frame as sf  # noqa: E402
from urtc_common import thermal_view as tv  # noqa: E402

BB_OUT = ROOT / "conformance" / "blackbox_vectors.json"
BB_H = ROOT / "generated" / "blackbox_vectors.h"
RK_OUT = ROOT / "conformance" / "rack_vectors.json"
RK_H = ROOT / "generated" / "rack_vectors.h"
SF_OUT = ROOT / "conformance" / "sensor_vectors.json"
SF_H = ROOT / "generated" / "sensor_vectors.h"
RATE_OUT = ROOT / "conformance" / "rate_vectors.json"
RATE_H = ROOT / "generated" / "rate_vectors.h"
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
            "record_size": bb.RECORD_SIZE, "chunks": bb.CHUNK_COUNT, "valid": ok, "invalid": bad, "recorder": recorder_vectors()}


# Scenarios of the recorder: the inputs of each tick (tick_ms, tool, current, target, end-stop, error flag, thermal code) and what the model flushes.
RECORDER_FIELDS = ("tick_ms", "tool_id", "current", "target", "endstop", "error", "thermal_code")


def recorder_scenarios() -> list[tuple[str, list[tuple]]]:
    def run(count, start=1000, error_from=None, error_until=None, thermal=0, endstop_at=(), wrap_at=None):
        out = []
        for i in range(count):
            error = error_from is not None and i >= error_from and (error_until is None or i < error_until)
            tick = start + i * 150
            if wrap_at is not None and i >= wrap_at:
                tick = (start + i * 150) & 0xFFFFFFFF
            out.append((tick & 0xFFFFFFFF, 0, 300 + (i * 7) % 60, 320, i in endstop_at, error, thermal if error else 0))
        return out

    return [
        ("no fault, no flush", run(10)),
        ("the first fault flushes the ring that was filled so far", run(30, error_from=20)),
        ("a fault after the ring wrapped flushes a full ring", run(101, error_from=100)),
        ("a fault that stays raised flushes once", run(40, error_from=12)),
        ("the latch is re-armed when the flag falls and a second fault flushes again", run(60, error_from=5, error_until=9) + [(1000 + (60 + i) * 150, 0, 305, 320, False, 15 + i >= 18, 0) for i in range(8)]),
        ("the end-stop and the thermal guard code travel in the flags", run(12, error_from=6, thermal=2, endstop_at=(2, 6))),
        ("the tick counter wraps inside the window", run(40, start=4_294_967_000, error_from=33)),
    ]


def recorder_vectors() -> list[dict]:
    out = []
    for name, steps in recorder_scenarios():
        model = bb.Recorder()
        flushes = []
        last = None
        for index, step in enumerate(steps):
            record = model.tick(*step)
            if record is not None:
                flushes.append(index)
                last = record
        out.append({"name": name, "steps": [dict(zip(RECORDER_FIELDS, (*step[:4], int(step[4]), int(step[5]), step[6]))) for step in steps],
                    "flush_steps": flushes, "record": last.hex().upper() if last is not None else None})
    return out


def blackbox_header(scenarios: list[dict]) -> str:
    lines = [
        "// GENERATED from spec by tools/make_extra_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef BLACKBOX_VECTORS_H", "#define BLACKBOX_VECTORS_H", "", "#include <stdint.h>", "",
        "typedef struct { uint32_t tick_ms; uint8_t tool_id; uint16_t current, target; uint8_t endstop, error, thermal_code; } bb_vec_step_t;",
        "// flush_steps lists the ticks (0-based) after which the recorder must have written the record; record is the last one flushed (NULL: none).",
        "typedef struct { const char *name; int step_count; const bb_vec_step_t *steps; int flush_count; const int *flush_steps; const uint8_t *record; } bb_vec_scenario_t;",
        "",
    ]
    for n, sc in enumerate(scenarios):
        lines.append(f"static const bb_vec_step_t BB_VEC_STEPS_{n}[] = {{")
        for step in sc["steps"]:
            lines.append(f"    {{{step['tick_ms']}u, {step['tool_id']}, {step['current']}, {step['target']}, {step['endstop']}, {step['error']}, {step['thermal_code']}}},")
        lines.append("};")
        flush = ", ".join(str(i) for i in sc["flush_steps"]) or "0"
        lines.append(f"static const int BB_VEC_FLUSH_{n}[] = {{{flush}}};")
        if sc["record"]:
            data = bytes.fromhex(sc["record"])
            rows = [", ".join(f"0x{b:02X}" for b in data[i:i + 16]) for i in range(0, len(data), 16)]
            lines.append(f"static const uint8_t BB_VEC_RECORD_{n}[] = {{")
            lines += [f"    {row}," for row in rows]
            lines.append("};")
        lines.append("")
    lines.append("static const bb_vec_scenario_t BB_VEC_SCENARIOS[] = {")
    for n, sc in enumerate(scenarios):
        record = f"BB_VEC_RECORD_{n}" if sc["record"] else "0"
        lines.append(f'    {{"{sc["name"]}", {len(sc["steps"])}, BB_VEC_STEPS_{n}, {len(sc["flush_steps"])}, BB_VEC_FLUSH_{n}, {record}}},')
    lines += ["};", "", "#define BB_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // BLACKBOX_VECTORS_H", ""]
    return "\n".join(lines)


def rack_stream_scenarios() -> list[dict]:
    """Streams of bytes with the time each piece arrived, played through the deframer of the rack: the frames that come out and the counters."""
    good = rk.encode_set_preheat(1, 0, 200)
    second = rk.encode_set_preheat(2, 19, 300)
    third = rk.encode_set_preheat(3, 0, 0)
    bad_crc = good[:-1] + bytes([good[-1] ^ 0xFF])
    bad_version = good[:1] + b"\x01" + good[2:]
    # a header that says 3 bytes of payload, followed by a whole real frame: the first candidate swallows the start of the real frame
    hiding = bytes([0xA5, 0x02, 0x00, 0x01, 0x03]) + second
    scenarios = [
        ("a frame in one piece", 20, [(0, good)]),
        ("a frame in pieces, each within the timeout", 20, [(0, good[:2]), (10, good[2:5]), (20, good[5:])]),
        ("two frames in one burst", 20, [(0, good + second)]),
        ("a frame split at every byte", 20, [(i, good[i:i + 1]) for i in range(len(good))]),
        ("noise before and between the frames", 20, [(0, b"\x00\x13\xFF" + good + b"\x42" + second)]),
        ("a frame cut short by a silence, then a whole one", 20, [(0, good[:4]), (100, second)]),
        ("a silence of exactly the timeout keeps the frame", 20, [(0, good[:4]), (20, good[4:])]),
        ("a silence of one more drops it", 20, [(0, good[:4]), (21, good[4:])]),
        ("the clock of the milliseconds wraps inside a frame", 20, [(0xFFFFFFF0, good[:4]), (4, good[4:])]),
        ("a bad crc, then a good frame", 20, [(0, bad_crc + second)]),
        ("a bad crc inside a burst of three frames", 20, [(0, good + bad_crc + second + third)]),
        ("a version this rack does not speak, then a good frame", 20, [(0, bad_version + second)]),
        ("a length of 17 is refused at once", 20, [(0, bytes([0xA5, 0x02, 0x01, 0x01, 0x11]) + second)]),
        ("a header that hides the start of a real frame", 20, [(0, hiding)]),
        ("thirty start bytes in a row", 20, [(0, b"\xA5" * 30)]),
        ("a frame after thirty start bytes", 20, [(0, b"\xA5" * 30 + good)]),
        ("a timeout of 5 ms (a faster link)", 5, [(0, good[:3]), (6, good[3:])]),
        ("a frame of the longest payload", 20, [(0, rk.encode_frame(9, 1, bytes(range(16))))]),
        ("a start byte alone, then silence, then a whole frame", 20, [(0, b"\xA5"), (50, good)]),
    ]
    out = []
    for name, timeout, events in scenarios:
        d = rk.StreamDeframer(timeout)
        frames: list[bytes] = []
        for t, chunk in events:
            frames += d.feed(chunk, t)
        out.append({
            "name": name, "timeout_ms": timeout, "events": [{"time_ms": t, "hex": chunk.hex().upper()} for t, chunk in events],
            "frames": [f.hex().upper() for f in frames],
            "stats": {k: getattr(d.stats, k) for k in ("frames_ok", "crc_errors", "bad_headers", "resyncs", "timeouts", "dropped_bytes")},
        })
    return out


def rack_vectors() -> dict:
    frames = []
    for name, seq, cmd, payload in (("set 200 C on the soldering iron", 1, 1, bytes([0, 0, 200])), ("set 0 on the hot air nozzle", 255, 1, bytes([19, 0, 0])),
                                    ("unknown command, empty", 7, 0x7E, b""), ("full payload", 9, 1, bytes(range(16)))):
        frames.append({"name": name, "seq": seq, "cmd": cmd, "payload": payload.hex().upper(), "frame": rk.encode_frame(seq, cmd, payload).hex().upper()})
    good = rk.encode_set_preheat(3, 0, 250)
    parse = [{"name": "good frame", "hex": good.hex().upper(), "status": "ok"}]
    parse.append({"name": "short", "hex": good[:5].hex().upper(), "status": "incomplete"})
    parse.append({"name": "frame cut after the header", "hex": good[:7].hex().upper(), "status": "incomplete"})
    parse.append({"name": "wrong start byte", "hex": (b"\x5A" + good[1:]).hex().upper(), "status": "bad_sof"})
    parse.append({"name": "version 1, the little-endian layout", "hex": (good[:1] + b"\x01" + good[2:]).hex().upper(), "status": "unsupported_version"})
    parse.append({"name": "length 17", "hex": (good[:4] + b"\x11" + good[5:]).hex().upper(), "status": "length_out_of_range"})
    parse.append({"name": "bad crc", "hex": (good[:-1] + bytes([good[-1] ^ 0xFF])).hex().upper(), "status": "crc_mismatch"})
    validate = []
    for name, payload in (("soldering 250", bytes([0, 0, 250])), ("soldering 400", bytes([0, 1, 144])), ("soldering 401", bytes([0, 1, 145])),
                          ("printer 310", bytes([10, 1, 54])), ("printer 311", bytes([10, 1, 55])), ("hot air 400", bytes([19, 1, 144])),
                          ("gripper 0 (no heater, target 0)", bytes([6, 0, 0])), ("gripper 100", bytes([6, 0, 100])),
                          ("no tool (31)", bytes([31, 0, 0])), ("tool 25", bytes([25, 0, 0])), ("tool byte 32", bytes([32, 0, 0])),
                          ("two bytes", bytes([0, 1])), ("four bytes", bytes([0, 0, 1, 0])), ("empty", b"")):
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
        {"name": "every refusal says why", "steps": [
            (0, rk.encode_frame(1, 1, b"")), (10, rk.encode_frame(2, 1, bytes([0, 0]))), (20, rk.encode_set_preheat(3, 31, 0)),
            (30, rk.encode_set_preheat(4, 0, 401)), (40, rk.encode_set_preheat(5, 27, 0)), (50, rk.encode_set_preheat(6, 6, 100)),
            (60, rk.encode_frame(7, 0x40, bytes([1, 2])))]},
        {"name": "a command that comes too soon is held and the next one is obeyed", "steps": [
            (0, rk.encode_set_preheat(1, 0, 200)), (5, rk.encode_set_preheat(2, 0, 250)), (19, rk.encode_set_preheat(2, 0, 250)),
            (20, rk.encode_set_preheat(2, 0, 250)), (25, rk.encode_set_preheat(1, 19, 300))]},
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
            "streams": rack_stream_scenarios(),
            "limits": {"ceiling_c": rk.RACK_CEILING_C, "link_timeout_ms": rk.LINK_TIMEOUT_MS, "printer_c": rk.MAX_PREHEAT_C[10]}}


def sensor_vectors() -> dict:
    frames = []
    for name, sensor_id, seq, stamp, payload in (("thermal 20.00 C", 1, 3, 123456, sf.encode_thermal_payload(2000)), ("thermal negative", 1, 255, 1, sf.encode_thermal_payload(-1250)),
                                                 ("trigger, no payload", 2, 1, 0, b""), ("timestamp with every byte different", 1, 7, 0x01020304, sf.encode_thermal_payload(300)),
                                                 ("largest timestamp, full payload", 1, 0, 0xFFFFFFFF, bytes(range(16)))):
        frames.append({"name": name, "sensor_id": sensor_id, "seq": seq, "timestamp_ms": stamp, "payload": payload.hex().upper(),
                       "frame": sf.encode_frame(sensor_id, seq, stamp, payload).hex().upper()})
    good = sf.encode_frame(1, 3, 123456, sf.encode_thermal_payload(2000))
    parse = [{"name": "good frame", "hex": good.hex().upper(), "status": "ok"},
             {"name": "short", "hex": good[:4].hex().upper(), "status": "incomplete"},
             {"name": "one byte short", "hex": good[:-1].hex().upper(), "status": "incomplete"},
             {"name": "wrong start byte", "hex": (b"\x00" + good[1:]).hex().upper(), "status": "bad_sof"},
             {"name": "version 1, the little-endian layout", "hex": (good[:1] + b"\x01" + good[2:]).hex().upper(), "status": "unsupported_version"},
             {"name": "length 17", "hex": (good[:8] + b"\x11" + good[9:]).hex().upper(), "status": "length_out_of_range"},
             {"name": "bad crc", "hex": (good[:-1] + bytes([good[-1] ^ 0xFF])).hex().upper(), "status": "crc_mismatch"},
             {"name": "corrupted payload", "hex": (good[:9] + bytes([good[9] ^ 1]) + good[10:]).hex().upper(), "status": "crc_mismatch"}]
    thermal = []
    for name, payload in (("20.00 C", sf.encode_thermal_payload(2000)), ("zero", sf.encode_thermal_payload(0)), ("-40.00 C", sf.encode_thermal_payload(-4000)),
                          ("just below -40.00 C", sf.encode_thermal_payload(-4001)), ("300.00 C", sf.encode_thermal_payload(30000)),
                          ("just above 300.00 C", sf.encode_thermal_payload(30001)), ("2000 sent little-endian is 53255 and is refused", bytes([0xD0, 0x07])),
                          ("one byte", b"\x07"), ("three bytes", b"\x00\x07\xd0"), ("empty", b"")):
        status, value = sf.validate_thermal(payload)
        thermal.append({"name": name, "payload": payload.hex().upper(), "status": status, "centidegrees": value})
    return {"format": 1, "about": "Frames and thermal readings of the sensor link of the vision head, every multi-byte value big-endian; the vision firmware and the reference module both pass them.",
            "frames": frames, "parse": parse, "thermal": thermal,
            "limits": {"version": sf.VERSION, "min_centidegrees_c": sf.MIN_TEMP_CENTIDEGREES_C, "max_centidegrees_c": sf.MAX_TEMP_CENTIDEGREES_C}}


SENSOR_ORDER = ("ok", "incomplete", "bad_sof", "unsupported_version", "length_out_of_range", "crc_mismatch")
READING_ORDER = ("ok", "wrong_payload_len", "temp_out_of_range")


def sensor_header(v: dict) -> str:
    def arr(data: bytes) -> str:
        return "{" + ", ".join(f"0x{b:02X}" for b in data) + "}" if data else "{0}"

    lines = [
        "// GENERATED from spec by tools/make_extra_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef SENSOR_VECTORS_H", "#define SENSOR_VECTORS_H", "", "#include <stdint.h>", "",
        "typedef struct { const char *name; uint8_t sensor_id, seq; uint32_t timestamp_ms; uint8_t payload_len; uint8_t payload[16]; uint8_t frame_len; uint8_t frame[26]; } sensor_vec_frame_t;",
        "typedef struct { const char *name; uint8_t len; uint8_t buf[26]; int status; } sensor_vec_parse_t; // sensor_frame_status_t order",
        "typedef struct { const char *name; uint8_t len; uint8_t payload[4]; int status; int centidegrees; } sensor_vec_thermal_t; // sensor_reading_status_t order",
        "",
        "static const sensor_vec_frame_t SENSOR_VEC_FRAMES[] = {",
    ]
    for f in v["frames"]:
        p, fr = bytes.fromhex(f["payload"]), bytes.fromhex(f["frame"])
        lines.append(f'    {{"{f["name"]}", {f["sensor_id"]}, {f["seq"]}, {f["timestamp_ms"]}u, {len(p)}, {arr(p)}, {len(fr)}, {arr(fr)}}},')
    lines += ["};", "", "static const sensor_vec_parse_t SENSOR_VEC_PARSE[] = {"]
    for p in v["parse"]:
        b = bytes.fromhex(p["hex"])
        lines.append(f'    {{"{p["name"]}", {len(b)}, {arr(b)}, {SENSOR_ORDER.index(p["status"])}}},')
    lines += ["};", "", "static const sensor_vec_thermal_t SENSOR_VEC_THERMAL[] = {"]
    for t in v["thermal"]:
        b = bytes.fromhex(t["payload"])
        lines.append(f'    {{"{t["name"]}", {len(b)}, {arr(b)}, {READING_ORDER.index(t["status"])}, {0 if t["centidegrees"] is None else t["centidegrees"]}}},')
    lines += ["};", "", "#define SENSOR_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // SENSOR_VECTORS_H", ""]
    return "\n".join(lines)


def rate_header(v: dict) -> str:
    longest = max(len(c["times_ms"]) for c in v["cases"])
    lines = [
        "// GENERATED from spec by tools/make_extra_vectors.py - do not edit by hand.",
        "// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "// GPL-3.0-or-later - see LICENSE",
        "#ifndef RATE_VECTORS_H", "#define RATE_VECTORS_H", "", "#include <stdint.h>", "",
        f"typedef struct {{ const char *name; uint32_t min_interval_ms; uint8_t count; uint32_t times_ms[{longest}]; uint8_t allowed[{longest}]; }} rate_vec_case_t;",
        "", "static const rate_vec_case_t RATE_VEC_CASES[] = {",
    ]
    for c in v["cases"]:
        times = ", ".join(f"{t}u" for t in c["times_ms"])
        allowed = ", ".join("1" if a else "0" for a in c["allowed"])
        lines.append(f'    {{"{c["name"]}", {c["min_interval_ms"]}u, {len(c["times_ms"])}, {{{times}}}, {{{allowed}}}}},')
    lines += ["};", "", "#define RATE_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // RATE_VECTORS_H", ""]
    return "\n".join(lines)


class _Watchdog:
    """The decision of the firmware's rack_link_decide for a frame, written down independently of the C code."""

    def __init__(self) -> None:
        self.last_rx: int | None = None
        self.seq: dict[int, int] = {}
        self.accepted: dict[int, int] = {}

    def decide(self, buf: bytes, now: int) -> dict:
        """The decision for a frame and the reply frame (hex) the rack sends for it; "" when nobody is told."""
        none = {"action": "none", "tool": 0, "temp": 0, "ack": 0, "reply": ""}
        status, frame = rk.parse_frame(buf)
        if frame is None:
            return none
        if self.last_rx is not None and now - self.last_rx >= rk.LINK_TIMEOUT_MS:
            self.seq.clear()
            self.accepted.clear()
        self.last_rx = now
        seq = frame["seq"]

        def reply(reason: str, tool: int) -> str:
            return rk.encode_reply(seq, frame["cmd"], tool, reason).hex().upper()

        if frame["cmd"] != rk.CMD_SET_PREHEAT:
            return {**none, "reply": reply("unknown_command", rk.REPLY_TOOL_NONE)}
        if not frame["payload"]:
            return {**none, "reply": reply("wrong_length", rk.REPLY_TOOL_NONE)}
        sent_tool = frame["payload"][0]
        status, tool, target = rk.validate_set_preheat(frame["payload"])
        if status != "ok":
            told = reply(rk.STATUS_TO_REPLY[status], sent_tool)
            if sent_tool <= rk.TOOL_ID_LAST:
                return {"action": "safe_state", "tool": sent_tool, "temp": 0, "ack": 0, "reply": told}
            return {**none, "reply": told}
        prev = self.seq.get(tool)
        if prev is not None:
            d = (seq - prev) & 0xFF
            if d == 0 or d >= 128:
                return {**none, "ack": 1, "reply": reply("repeat", tool)}
        last = self.accepted.get(tool)
        if last is not None and ((now - last) & 0xFFFFFFFF) < rk.COMMAND_MIN_INTERVAL_MS:
            return {**none, "reply": reply("held_rate", tool)}
        self.accepted[tool] = now
        self.seq[tool] = seq
        return {"action": "set_target", "tool": tool, "temp": target, "ack": 1, "reply": reply("applied", tool)}


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
        "typedef struct { int scenario; const char *name; uint32_t time_ms; uint8_t len; uint8_t buf[24]; int action; int tool; int temp; int ack; uint8_t reply_len; uint8_t reply[9]; } rack_vec_step_t; // rack_action_t order; the reply frame (none: length 0)",
        "typedef struct { int stream; uint32_t time_ms; uint8_t len; uint8_t data[40]; } rack_vec_stream_event_t; // bytes that arrived together",
        "typedef struct { int stream; uint8_t len; uint8_t frame[22]; } rack_vec_stream_frame_t; // a frame the deframer must hand over, in order",
        "typedef struct { const char *name; uint32_t timeout_ms; uint32_t frames_ok, crc_errors, bad_headers, resyncs, timeouts, dropped_bytes; } rack_vec_stream_t;",
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
            reply = bytes.fromhex(s["reply"])
            lines.append(f'    {{{i}, "{sc["name"]}", {s["time_ms"]}, {len(b)}, {arr(b)}, {ACTION_ORDER.index(s["action"])}, {s["tool"]}, {s["temp"]}, {s["ack"]}, {len(reply)}, {arr(reply)}}},')
    lines += ["};", "", "static const rack_vec_verify_t RACK_VEC_VERIFY[] = {"]
    for c in v["verify"]:
        measured = "NAN" if c["measured_c"] is None else repr(float(c["measured_c"])) + "f"
        lines.append(f'    {{"{c["name"]}", {1 if c["occupied"] else 0}, {c["commanded_c"]}, {measured}, {float(c["ambient_c"])!r}f, {c["elapsed_ms"]}u, {rk.SLOT_VERDICTS.index(c["verdict"])}}},')
    lines += ["};", "", "static const rack_vec_stream_t RACK_VEC_STREAMS[] = {"]
    for s in v["streams"]:
        st = s["stats"]
        lines.append(f'    {{"{s["name"]}", {s["timeout_ms"]}u, {st["frames_ok"]}u, {st["crc_errors"]}u, {st["bad_headers"]}u, {st["resyncs"]}u, {st["timeouts"]}u, {st["dropped_bytes"]}u}},')
    lines += ["};", "", "static const rack_vec_stream_event_t RACK_VEC_STREAM_EVENTS[] = {"]
    for i, s in enumerate(v["streams"]):
        for e in s["events"]:
            b = bytes.fromhex(e["hex"])
            lines.append(f'    {{{i}, {e["time_ms"]}u, {len(b)}, {arr(b)}}},')
    lines += ["};", "", "static const rack_vec_stream_frame_t RACK_VEC_STREAM_FRAMES[] = {"]
    for i, s in enumerate(v["streams"]):
        for f in s["frames"]:
            b = bytes.fromhex(f)
            lines.append(f'    {{{i}, {len(b)}, {arr(b)}}},')
    lines += ["};", "", "#define RACK_VEC_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))", "", "#endif // RACK_VECTORS_H", ""]
    return "\n".join(lines)


CRC8_CASES = (
    ("empty", b""), ("one zero byte", b"\x00"), ("one 0xFF byte", b"\xff"), ("four zero bytes", b"\x00" * 4),
    ("the check text", b"123456789"), ("a rack frame header", bytes([0xA5, 0x02, 0x01, 0x01, 0x03, 0x00, 0x00, 0xC8])),
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
    sv = sensor_vectors()
    rate = fl.rate_vectors()
    bbv = blackbox_vectors()
    return {
        BB_OUT: json.dumps(bbv, indent=2) + "\n",
        BB_H: blackbox_header(bbv["recorder"]),
        RK_OUT: json.dumps(rv, indent=2) + "\n",
        RK_H: rack_header(rv),
        SF_OUT: json.dumps(sv, indent=2) + "\n",
        SF_H: sensor_header(sv),
        RATE_OUT: json.dumps(rate, indent=2) + "\n",
        RATE_H: rate_header(rate),
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
