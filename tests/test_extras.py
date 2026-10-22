# =============================================================================
# URTC-COMMON - tests/test_extras.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Tool profiles as data, the fault recorder, the rack simulator, the fuzz frames and the compatibility table."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import compat_table
import generate_tools
import make_extra_vectors
import pytest

from urtc_common import blackbox as bb
from urtc_common import fuzz, rack_sim as rk, tools_catalog

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "tools" / script), *args], capture_output=True, text=True)


# ---- tools ------------------------------------------------------------------------------------------------------------------
def test_the_tool_file_is_consistent_with_the_protocol_specification(spec):
    assert generate_tools.validate(generate_tools.load(), spec) == []
    assert len(generate_tools.load()["tools"]) == 25


def test_a_tool_profile_with_a_default_outside_its_limits_is_refused(spec):
    doc = json.loads(json.dumps(generate_tools.load()))
    doc["tools"][3]["limits"]["default"] = doc["tools"][3]["limits"]["max"] + 1
    assert any("default outside" in p for p in generate_tools.validate(doc, spec))


def test_a_tool_missing_from_the_file_is_refused(spec):
    doc = json.loads(json.dumps(generate_tools.load()))
    del doc["tools"][7]
    assert generate_tools.validate(doc, spec)


def test_the_generated_tool_files_are_current():
    result = _run("generate_tools.py", "--check")
    assert result.returncode == 0, result.stderr
    assert "TOOLS=PASS" in result.stdout


def test_the_generated_python_catalog_matches_the_file():
    doc = generate_tools.load()
    assert [t["id"] for t in tools_catalog.TOOLS] == list(range(25))
    assert tools_catalog.TOOL_NAMES == {t["id"]: t["short_name"] for t in doc["tools"]}
    assert tools_catalog.tool_by_id(0)["watchdog_ms"] == 250
    assert tools_catalog.tool_by_id(99) is None


def test_the_heater_limits_agree_with_the_rack_limits():
    for tool_id, ceiling in rk.MAX_PREHEAT_C.items():
        assert tools_catalog.tool_by_id(tool_id)["maximum"] >= 0
        assert ceiling <= rk.RACK_CEILING_C


def test_every_tool_command_identifier_lists_only_real_tools(spec):
    ids = {t["id"] for t in generate_tools.load()["tools"]}
    for m in spec["messages"]:
        if isinstance(m["tools"], list):
            assert set(m["tools"]) <= ids, m["name"]


# ---- fault recorder ---------------------------------------------------------------------------------------------------------
VECTORS = json.loads((ROOT / "conformance" / "blackbox_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vec", VECTORS["valid"], ids=lambda v: v["name"])
def test_blackbox_valid_records(vec):
    rec = bb.parse(bytes.fromhex(vec["hex"]))
    assert rec.sample_count == vec["sample_count"] and rec.write_index == vec["write_index"]
    assert rec.trigger_index == vec["trigger_index"]
    assert bb.rows(rec) == vec["rows"]
    assert bb.to_csv(rec) == vec["csv"]
    assert [r["index"] for r in bb.rows(rec)] == list(range(len(rec.samples)))


@pytest.mark.parametrize("vec", VECTORS["invalid"], ids=lambda v: v["name"])
def test_blackbox_invalid_records_are_refused(vec):
    with pytest.raises(bb.BlackBoxError, match=vec["error"]):
        bb.parse(bytes.fromhex(vec["hex"]))


def test_blackbox_wrap_puts_the_oldest_sample_first():
    rec = bb.parse(bytes.fromhex(VECTORS["valid"][1]["hex"]))
    ticks = [s.tick_ms for s in rec.samples]
    assert ticks == [(4_294_966_000 + i * 150) & 0xFFFFFFFF for i in range(67)]
    rows = bb.rows(rec)
    assert rows[0]["ms_before_last"] == 66 * 150 and rows[-1]["ms_before_last"] == 0


def test_blackbox_sizes_match_the_firmware_header():
    header = (ROOT.parent / "URTC" / "src" / "F303-master" / "firmware_common.h")
    if not header.is_file():
        pytest.skip("URTC is not next to this repository")
    text = header.read_text(encoding="utf-8", errors="replace")
    assert f"sizeof(BlackBoxRecord_t) == {bb.RECORD_SIZE}" in text
    assert f"#define BLACKBOX_SAMPLES {bb.SAMPLES}" in text
    assert f"#define BLACKBOX_VERSION {bb.VERSION}" in text
    assert "0x424C4B42" in text


def test_blackbox_download_asks_for_every_chunk_and_refuses_a_gap():
    raw = bytes.fromhex(VECTORS["valid"][0]["hex"]).ljust(bb.CHUNK_COUNT * bb.CHUNK_BYTES, b"\x00")
    asked = []

    def ask(i):
        asked.append(i)
        return raw[i * 32:(i + 1) * 32]

    assert bb.download(ask).sample_count == 12 and asked == list(range(22))
    with pytest.raises(bb.BlackBoxError, match="chunk 3"):
        bb.download(lambda i: None if i == 3 else raw[i * 32:(i + 1) * 32])
    with pytest.raises(bb.BlackBoxError):
        bb.chunk_request(22)
    assert bb.join_frames([b"\x01" * 8] * 4) == b"\x01" * 32
    with pytest.raises(bb.BlackBoxError):
        bb.join_frames([b"\x01" * 8] * 3)


def test_blackbox_json_carries_the_trigger_and_the_capture_time():
    rec = bb.parse(bytes.fromhex(VECTORS["valid"][1]["hex"]))
    doc = json.loads(bb.to_json(rec, "capture time"))
    assert doc["format"] == "urtc-blackbox/1" and doc["trigger_index"] == 60 and doc["captured_at"] == "capture time"
    assert doc["trigger_tick_ms"] == rec.samples[60].tick_ms and len(doc["samples"]) == 67


def test_the_fault_trigger_fires_once_per_rising_edge():
    t = bb.FaultTrigger()
    seq = [b"\x00\x00\x00\x00", b"\x00\x01\x00\x00", b"\x00\x01\x00\x00", b"\x00\x00\x00\x00", b"\x00\x01\x00\x00", b"\x00"]
    assert [t.feed(p) for p in seq] == [False, True, False, False, True, False]


def test_build_and_parse_roundtrip_for_every_write_index():
    samples = [bb.Sample(i * 150, 0, 300 + i, 320, 0) for i in range(67)]
    for widx in (0, 1, 33, 66):
        assert bb.parse(bb.build(samples, widx)).samples == samples


# ---- rack -------------------------------------------------------------------------------------------------------------------
RACK = json.loads((ROOT / "conformance" / "rack_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("v", RACK["frames"], ids=lambda v: v["name"])
def test_rack_frames_encode_to_the_vector_bytes_and_parse_back(v):
    frame = rk.encode_frame(v["seq"], v["cmd"], bytes.fromhex(v["payload"]))
    assert frame.hex().upper() == v["frame"]
    assert rk.parse_frame(frame) == ("ok", {"seq": v["seq"], "cmd": v["cmd"], "payload": bytes.fromhex(v["payload"])})


@pytest.mark.parametrize("v", RACK["parse"], ids=lambda v: v["name"])
def test_rack_parse_statuses(v):
    assert rk.parse_frame(bytes.fromhex(v["hex"]))[0] == v["status"]


@pytest.mark.parametrize("v", RACK["validate"], ids=lambda v: v["name"])
def test_rack_command_validation(v):
    status, tool, target = rk.validate_set_preheat(bytes.fromhex(v["payload"]))
    assert status == v["status"]
    if status == "ok":
        assert (tool, target) == (v["tool"], v["target"])


@pytest.mark.parametrize("v", RACK["can"], ids=lambda v: v["name"])
def test_rack_can_data(v):
    assert rk.encode_set_preheat_can(v["seq"], v["tool"], v["target"]).hex().upper() == v["data"]
    reply = rk.SimulatedRack().receive_can(v["id"], bytes.fromhex(v["data"]), 0)
    assert reply.kind in ("ack", "nack")


@pytest.mark.parametrize("sc", RACK["scenarios"], ids=lambda s: s["name"])
def test_rack_scenarios_decide_like_the_firmware(sc):
    rack = rk.SimulatedRack()
    for slot, tool in enumerate((0, 19, 6, 10)):
        rack.set_slot(slot, tool, serial=slot + 1)
    for step in sc["steps"]:
        reply = rack.receive(bytes.fromhex(step["frame"]), step["time_ms"])
        action = {"set_target": "set_target", "safe_state": "safe_state"}.get(reply.action, "none")
        assert action == step["action"], step
        assert (reply.kind == "ack") == bool(step["ack"]), step
        if action != "none":
            assert (reply.tool_id, reply.target_c) == (step["tool"], step["temp"]), step


def test_rack_sends_every_target_to_the_safe_state_when_the_link_goes_quiet():
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0, 5)
    assert rack.receive(rk.encode_set_preheat(1, 0, 250), 0).action == "set_target"
    assert rack.slots[0].target_c == 250
    assert rack.tick(100) == 0
    assert rack.tick(10_000) == 1 and rack.slots[0].target_c == 0


def test_rack_preheat_limit_latches_until_zero_or_a_swap_and_can_be_switched_off():
    rack = rk.SimulatedRack(preheat_max_ms=1000)
    rack.set_slot(0, 0, 5)
    rack.receive(rk.encode_set_preheat(1, 0, 250), 0)
    for t, seq in ((200, 2), (400, 3), (600, 4), (800, 5)):
        rack.receive(rk.encode_set_preheat(seq, 0, 250), t)
    assert rack.slots[0].target_c == 250
    rack.receive(rk.encode_set_preheat(6, 0, 250), 1000)
    assert rack.slots[0].target_c == 0 and 0 in rack.expired
    assert "limit" in rack.receive(rk.encode_set_preheat(7, 0, 250), 1100).detail
    assert rack.receive(rk.encode_set_preheat(8, 0, 0), 1200).action == "set_target"
    assert rack.receive(rk.encode_set_preheat(9, 0, 200), 1300).action == "set_target"
    unlimited = rk.SimulatedRack(preheat_max_ms=None)
    unlimited.set_slot(0, 0, 5)
    t = 0
    for seq in range(1, 100):
        unlimited.receive(rk.encode_set_preheat(seq, 0, 250), t)
        t += 200
    assert unlimited.slots[0].target_c == 250


def test_rack_identity_is_the_type_and_the_serial_and_a_tool_is_in_one_slot():
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0, 7)
    rack.set_slot(1, 0, 9)  # the same type with another serial number is another physical unit
    assert rack.slots[0].unit_key == "0:7" and rack.slots[1].unit_key == "0:9"
    rack.set_slot(2, 0, 7)  # the same unit moved: its old slot is cleared
    assert not rack.slots[0].occupied and rack.slots[2].unit_key == "0:7"
    rack.set_slot(3, 5)     # no serial known: no unit identity
    assert rack.slots[3].unit_key is None
    status = rack.status()
    assert status["occupied"] == 3 and status["slots"][2]["unit"] == "0:7"


# ---- fuzz frames ------------------------------------------------------------------------------------------------------------
def test_fuzz_frames_are_the_same_for_the_same_seed_and_all_kinds_appear(spec):
    a, b = fuzz.generate(spec, seed=5, random_count=50), fuzz.generate(spec, seed=5, random_count=50)
    assert a == b and a != fuzz.generate(spec, seed=6, random_count=50)
    assert {f.kind for f in a} == {fuzz.VALID, fuzz.INVALID, fuzz.RANDOM}
    assert all(0 <= f.can_id <= 0x7FF and len(f.data) <= 8 for f in a)


def test_valid_fuzz_frames_decode_with_the_generated_protocol_and_invalid_ones_do_not(spec):
    by_id = {int(m["id"], 16): m for m in spec["messages"]}
    for f in fuzz.generate(spec, seed=1, random_count=0):
        if f.kind == fuzz.RANDOM:
            continue
        m = by_id[f.can_id]
        request = next(lay for lay in m["layouts"] if lay["role"] != "response")
        dlc = request["dlc"]
        ok_len = dlc.get("any") or ("exact" in dlc and len(f.data) == dlc["exact"]) or ("min" in dlc and dlc["min"] <= len(f.data) <= dlc["max"]) \
            or ("one_of" in dlc and len(f.data) in dlc["one_of"])
        if f.kind == fuzz.VALID:
            assert ok_len, f.line()
        elif f.note.startswith("length "):
            assert not ok_len, f.line()


def test_fuzz_corpus_line_roundtrip(spec):
    for f in fuzz.generate(spec, seed=2, random_count=20):
        assert fuzz.parse_line(f.line()) == f


def test_extra_vector_files_are_current():
    result = _run("make_extra_vectors.py", "--check")
    assert result.returncode == 0, result.stderr
    assert make_extra_vectors.outputs()


# ---- compatibility table ----------------------------------------------------------------------------------------------------
def test_the_compatibility_table_is_current_and_names_the_protocol():
    doc = compat_table.load()
    assert compat_table.check(doc, None) == []
    text = compat_table.render(doc)
    assert "Protocol version **1**" in text and "`URTC-TESTER`" in text


def test_a_protocol_version_that_differs_from_the_specification_is_reported():
    doc = json.loads(json.dumps(compat_table.load()))
    doc["protocol_version"] = 2
    assert any("protocol_version" in p for p in compat_table.check(doc, None))


def test_the_table_lists_a_manifest_version_it_is_given(tmp_path):
    (tmp_path / "URTC-TESTER").mkdir()
    (tmp_path / "URTC-TESTER" / "urtc.project.json").write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
    projects = compat_table.refresh(tmp_path)["projects"]
    assert projects == [{"repo": "URTC-TESTER", "title": "Tester", "kind": "program", "version": "9.9.9"}]


# ---- thermal view ------------------------------------------------------------------------------------------------------------
THERMAL = json.loads((ROOT / "conformance" / "thermal_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", THERMAL["false_color"], ids=lambda c: c["name"])
def test_false_color_reproduces_the_vectors(case):
    from urtc_common import thermal_view as tv
    frame = [[float("nan") if v is None else v for v in row] for row in case["frame"]]
    rng = tuple(case["range"]) if case["range"] else None
    assert tv.to_rgb_bytes(frame, rng).hex().upper() == case["rgb"]


def test_false_color_edges():
    from urtc_common import thermal_view as tv
    assert tv.color_of(0.0, 0.0, 10.0) == (0, 0, 0) and tv.color_of(10.0, 0.0, 10.0) == (255, 255, 255)
    assert tv.color_of(float("nan"), 0.0, 10.0) == tv.INVALID_COLOR and tv.color_of(float("inf"), 0.0, 10.0) == tv.INVALID_COLOR
    assert tv.color_of(-5.0, 0.0, 10.0) == (0, 0, 0) and tv.color_of(50.0, 0.0, 10.0) == (255, 255, 255)
    lo, hi = tv.scale_of([[30.0, 30.0]])
    assert (lo, hi) == (29.5, 30.5)
    with pytest.raises(tv.ThermalError):
        tv.scale_of([[1.0]], (5.0, 5.0))
    assert tv.scale_of([[float("nan")]]) == (0.0, 1.0)


@pytest.mark.parametrize("case", THERMAL["chunks"], ids=lambda c: c["name"])
def test_thermal_chunks_decode_to_the_vectors(case):
    from urtc_common import thermal_view as tv
    assert tv.decode_chunk(bytes.fromhex(case["hex"])) == case["values"]


def test_an_image_is_put_back_together_and_an_incomplete_one_is_refused():
    from urtc_common import thermal_view as tv
    frame = tv.synthetic_frame(32, 24)
    chunks = tv.encode_chunks(frame)
    assert len(chunks) == tv.chunk_count("90640") == 48 and tv.chunk_count("90641") == 12
    assert tv.assemble(chunks, "90640") == frame
    del chunks[7]
    with pytest.raises(tv.ThermalError, match="first 7"):
        tv.assemble(chunks, "90640")
    with pytest.raises(tv.ThermalError):
        tv.decode_chunk(b"\x00" * 31)
    with pytest.raises(tv.ThermalError):
        tv.shape("12345")


def test_region_statistics_skip_invalid_pixels_and_refuse_a_bad_region():
    from urtc_common import thermal_view as tv
    frame = [[20.0, 40.0, float("nan")], [60.0, 80.0, 100.0]]
    stats = tv.region_stats(frame, 0, 0, 3, 2)
    assert (stats.minimum, stats.maximum, stats.mean, stats.pixels, stats.invalid) == (20.0, 100.0, 60.0, 5, 1)
    assert tv.region_stats([[float("nan")]], 0, 0, 1, 1) is None
    for bad in ((0, 0, 4, 1), (1, 1, 1, 2), (-1, 0, 1, 1)):
        with pytest.raises(tv.ThermalError):
            tv.region_stats(frame, *bad)


# ---- thermal check of a slot ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("case", RACK["verify"], ids=lambda c: c["name"])
def test_slot_verdicts_reproduce_the_vectors(case):
    assert rk.verify_slot(case["occupied"], case["commanded_c"], case["measured_c"], case["ambient_c"], case["elapsed_ms"]) == case["verdict"]


# ---- status page -------------------------------------------------------------------------------------------------------------
def test_the_status_snapshot_the_card_and_the_page_agree_and_escape_everything():
    from urtc_common import rack_status
    rack = rk.SimulatedRack()
    rack.set_slot(0, 0, 7)
    rack.set_slot(1, 19, 2)
    rack.receive(rk.encode_set_preheat(1, 0, 250), 0)
    snap = rack_status.snapshot(rack.status(), {"0:7": {"cycles": 3, "heater_seconds": 90, "faults": 0, "maintenance": True}},
                                {0: "reached", 1: "overshoot"}, name="<script>bench</script>")
    assert snap["occupied"] == 2 and snap["heating"] == 1 and snap["maintenance_due"] == 1
    assert any("maintenance due" in a for a in snap["alarms"]) and any("overshoot" in a for a in snap["alarms"])
    assert rack_status.card(snap)["state"] == "alarm"
    page = rack_status.to_html(snap)
    assert "<script>" not in page and "&lt;script&gt;" in page and "src=" not in page and "http" not in page
    assert json.loads(rack_status.to_json(snap))["slots"][0]["unit"] == "0:7"
    quiet = rack_status.snapshot(rk.SimulatedRack().status())
    assert rack_status.card(quiet)["state"] == "ok" and quiet["alarms"] == []
