# =============================================================================
# URTC-COMMON - tests/test_tool_panel_model.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The panel of a tool as a model without a screen: frame builders, control values, readings, query answers and the picture."""
from __future__ import annotations

import inspect
import json

import pytest
from urtc_common import tool_panel_model as m
from urtc_common.tool_panels import PANELS


def actions():
    for tool_id, panel in PANELS.items():
        for section in panel["sections"]:
            for action in section.get("actions", []):
                yield tool_id, action


def test_every_encoder_a_panel_names_exists_and_takes_the_arguments_the_panel_gives():
    seen = set()
    for tool_id, action in actions():
        for key, args_key in (("encoder", "args"), ("off_encoder", None)):
            name = action.get(key)
            if not name:
                continue
            assert name in m.ENCODERS, (tool_id, name)
            seen.add(name)
            if args_key:
                count = len(action.get(args_key, [])) + (1 if action["type"] == "latched" else 0)   # a latched command is given its state
                params = inspect.signature(m.ENCODERS[name]).parameters
                assert len(params) == count, (tool_id, name, count)
            else:
                assert len(inspect.signature(m.ENCODERS[name]).parameters) == 0, (tool_id, name)
    assert {"motionMove", "motionStop", "solderSetpoint", "solderOff", "weldFire", "thermalMotion"} <= seen


def test_every_panel_can_be_given_its_first_values_and_every_action_can_be_encoded_from_them():
    encoded = 0
    for tool_id, panel in PANELS.items():
        values = m.initial_values(panel)
        for section in panel["sections"]:
            for action in section.get("actions", []):
                if action.get("encoder") and action["type"] == "latched":
                    assert m.ENCODERS[action["encoder"]](True) == [1] and m.ENCODERS[action["encoder"]](False) == [0]
                elif action.get("encoder"):
                    payload = m.encode_action(action["encoder"], values, action.get("args"), bool(action.get("gate_first")), True)
                    assert all(0 <= b <= 255 for b in payload), (tool_id, action["encoder"])
                    assert len(payload) <= 8, (tool_id, action["encoder"])
                    encoded += 1
                if action.get("off_encoder"):
                    assert len(m.ENCODERS[action["off_encoder"]]()) <= 8
    assert encoded >= 20


def test_a_value_that_does_not_fit_is_brought_to_the_nearest_one_and_never_wrapped():
    assert m.byte(300) == 255 and m.byte(-4) == 0 and m.byte(float("nan")) == 0 and m.byte(2.5) == 3 and m.byte("17") == 17
    assert m.be16(70000) == [0xFF, 0xFF] and m.be16(-1) == [0, 0] and m.be16(0x1234) == [0x12, 0x34]
    assert m.ENCODERS["drillCommand"](300, "ccw") == [255, 1] and m.ENCODERS["drillCommand"](10, "cw") == [10, 0]
    assert m.ENCODERS["weldFire"](99999) == [1, 0x07, 0xD0] and m.ENCODERS["weldFire"](0) == [1, 0, 1]
    assert m.ENCODERS["laserCommand"](50, True) == [50, 1] and m.ENCODERS["laserCommand"](50, "yes") == [50, 0]
    assert m.ENCODERS["thermalMotion"](320, "fwd", 0x123456) == [0x01, 0x40, 1, 0x12, 0x34, 0x56]
    assert m.ENCODERS["thermalMotion"](320, "rev", 1 << 30)[2:] == [0, 0xFF, 0xFF, 0xFF]
    assert m.ENCODERS["thermalMotionOff"]() == [0, 0, 1, 0, 0, 0]
    assert m.ENCODERS["feederReset"]() == [0x52, 0x53, 0x50, 0x30]
    assert m.ENCODERS["pasteJettingConfig"](2, 1000) == [2, 0x03, 0xE8]
    assert m.ENCODERS["hotAirCommand"](250, 70) == [0, 250, 70] and m.ENCODERS["hotAirOff"]() == [0, 0, 0]


def test_a_move_of_zero_steps_or_more_than_fit_is_refused_not_turned_into_another_move():
    assert m.ENCODERS["motionMove"]("fwd", 200) == [1, 0, 0, 0, 200]
    assert m.ENCODERS["motionMove"]("rev", 0xFFFFFFFF) == [0, 255, 255, 255, 255]
    for bad in (0, -5, 1.5, 2**32, float("nan"), "x"):
        with pytest.raises(ValueError):
            m.ENCODERS["motionMove"]("fwd", bad)
    assert m.ENCODERS["motionStop"]("fwd") == [1, 0, 0, 0, 0]


def test_the_configuration_word_is_one_to_four_hexadecimal_digits():
    assert m.config_word_to_bytes("0x8483") == [0x84, 0x83] and m.config_word_to_bytes(" 1f ") == [0, 0x1F]
    for bad in ("", "0x", "12345", "zz", "0x12g"):
        with pytest.raises(ValueError):
            m.config_word_to_bytes(bad)


def test_the_first_value_of_a_gated_command_is_zero_while_the_repeated_command_is_off():
    values = {"temp": 300, "dir": "fwd", "steps": 5}
    assert m.encode_action("thermalMotion", values, ["temp", "dir", "steps"], True, False) == [0, 0, 1, 0, 0, 5]
    assert m.encode_action("thermalMotion", values, ["temp", "dir", "steps"], True, True) == [0x01, 0x2C, 1, 0, 0, 5]
    assert m.encode_action("motionStop", values, ["dir"]) == [1, 0, 0, 0, 0]
    assert m.encode_action("solderSetpoint", values, [250]) == [0, 250]   # a number in args stands for itself


def test_a_control_value_is_held_to_its_range_and_junk_falls_back_to_the_lowest():
    control = {"id": "x", "type": "number", "min": 10, "max": 100, "default": 50, "label": {"text": "x"}}
    assert m.clamp_control(control, 500) == 100 and m.clamp_control(control, "5") == 10 and m.clamp_control(control, "42px") == 42
    assert m.clamp_control(control, "abc") == 10 and m.clamp_control(control, "") == 10 and m.clamp_control(control, "-7") == 10
    assert m.clamp_control({"type": "select"}, "fwd") == "fwd"


def test_a_reading_is_big_endian_and_none_when_the_frame_is_too_short():
    two = {"offset": 1, "width": 2}
    assert m.reading_of(two, [0, 0x01, 0x2C]) == 300 and m.reading_of(two, [0, 1]) is None
    assert m.reading_of({"offset": 0, "width": 1}, [7]) == 7
    signed = {"offset": 0, "width": 4, "signed": True}
    assert m.decode_value(signed, [0xFF, 0xFF, 0xFF, 0xFE]) == -2 and m.decode_value(signed, [0, 0, 1, 0]) == 256
    assert m.decode_value(signed, [0, 0, 1]) is None
    assert m.decode_value({"offset": 0, "width": 2}, [0xFF, 0xFF]) == 65535


def test_counters_and_last_seen_readings_follow_only_the_frames_of_their_event():
    count = {"format": "count", "offset": 0, "width": 1, "match": 1}
    seen = {"format": "last_seen", "offset": 0, "width": 1, "match": 1}
    state = {"value": None, "seen": None}
    state = m.reading_step(count, [1], "t1", state)
    state = m.reading_step(count, [0], "t2", state)
    state = m.reading_step(count, [1], "t3", state)
    assert state["value"] == 2
    assert m.reading_step(seen, [1], "t4", state)["seen"] == "t4"
    assert m.reading_step(seen, [0], "t5", {"value": None, "seen": "t4"})["seen"] == "t4"
    plain = {"offset": 0, "width": 2, "unit": "C"}
    assert m.reading_step(plain, [1, 0], "t", {"value": None, "seen": None})["value"] == 256
    assert m.reading_step(plain, [1], "t", {"value": 5, "seen": None})["value"] == 5
    assert m.is_event_frame({"offset": 3}, [])    # no match named: every frame counts
    assert not m.is_event_frame({"offset": 3, "match": 1}, [1])


def test_what_a_reading_shows():
    assert m.reading_shown({"format": "yes_no"}, 1, None, "Yes", "No") == ("Yes", "on")
    assert m.reading_shown({"format": "yes_no"}, 0, None, "Yes", "No") == ("No", "off")
    assert m.reading_shown({"format": "count"}, None, None, "", "") == ("0", "plain")
    assert m.reading_shown({"format": "last_seen"}, None, None, "", "") == ("--", "plain")
    assert m.reading_shown({"unit": "C"}, 321, None, "", "") == ("321 C", "plain")
    assert m.reading_shown({}, None, None, "", "") == ("--", "plain")


def test_a_text_is_translated_with_its_values_or_shown_plain():
    key = {"key": "a.b", "default": "Reading... {{pct}}%"}
    assert m.panel_text(None, key, {"pct": 40}) == "Reading... 40%"
    assert m.panel_text(lambda k, d: "Leyendo {{pct}}", key, {"pct": 7}) == "Leyendo 7"
    assert m.panel_text(None, {"text": "on {tool}"}, {"tool": "Drill"}) == "on Drill"
    result = {"states": [{"value": 1, "label": {"key": "k", "default": "Running"}}]}
    assert m.result_text(None, result, 1) == "Running" and m.result_text(None, result, 255) == "0xff"
    assert m.result_text(None, {}, 12) == "12" and m.result_text(None, result, None) == "--"
    control = {"type": "range", "min": 1, "max": 9, "label": {"key": "k", "default": "d", "param": "value"}}
    assert m.label_params(control, 4) == {"value": 4, "min": 1, "max": 9}
    assert m.label_params({"type": "select", "label": {"text": "x"}}, "a") == {}


def test_the_picture_is_signed_sixteen_bit_pixels_over_the_scale():
    assert m.image_pixels([0x09, 0xC4, 0xFF, 0x9C, 0x01], 100) == [25.0, -1.0]   # an odd last byte is dropped
    cold, hot = m.heat_colour(0, 100), m.heat_colour(100, 100)
    assert cold[2] > cold[0] and hot[0] > hot[2]
    assert m.heat_colour(-50, 100) == cold and m.heat_colour(500, 100) == hot and m.heat_colour(5, 0) == cold


class FakeBus:
    def __init__(self, replies=None, frames=None):
        self.replies, self.frames, self.sent, self.flushed = replies or {}, list(frames or []), [], []

    def send_frame(self, can_id, data, description=""):
        self.sent.append((can_id, list(data), description))

    def wait_for_frame(self, can_id, timeout_ms):
        return self.frames.pop(0) if self.frames else None

    def request(self, can_id, data, response_id, timeout_ms, description=""):
        self.sent.append((can_id, list(data), description))
        return self.replies.get(response_id)

    def flush_frames(self, can_id=None):
        self.flushed.append(can_id)


def test_asking_the_board_for_a_value():
    feeder = next(a for _, a in actions() if a["type"] == "query")
    bus = FakeBus(replies={feeder.get("respCanId", feeder["canId"]): [0xFF, 0xFF, 0xFF, 0xFE]})
    assert m.ask_value(bus, feeder) == -2
    assert bus.sent == [(feeder["canId"], [], feeder["description"])]
    assert m.ask_value(FakeBus(), feeder) is None                                  # nothing came back
    assert m.ask_value(FakeBus(replies={feeder["canId"]: [1]}), feeder) is None    # too short


def test_pulling_the_thermal_picture_chunk_by_chunk():
    image = next(a for _, a in actions() if a["type"] == "image")
    chunks, per = image["chunks"], image["frames_per_chunk"]
    frames = [[0x09, 0xC4, 0x09, 0xC4, 0x09, 0xC4, 0x09, 0xC4]] * (chunks * per)
    bus, progress = FakeBus(frames=frames), []
    pixels = m.pull_image(bus, image, progress.append)
    assert len(pixels) == chunks * per * 4 and set(pixels) == {25.0}
    assert [s[1] for s in bus.sent] == [[c] for c in range(chunks)] and len(bus.flushed) == chunks
    assert progress[-1] == 100 and progress == sorted(progress)
    with pytest.raises(TimeoutError, match="chunk 0, frame 1"):
        m.pull_image(FakeBus(frames=[[0] * 8]), image)


def test_the_generated_panel_data_is_the_json_of_the_specification():
    from generate_tools import PROTOCOL, _panels, load

    doc, protocol = load(), json.loads(PROTOCOL.read_text(encoding="utf-8"))
    expected = _panels(doc, protocol)
    assert PANELS == expected
    assert m.panel_of(5) == expected[5] and m.panel_of(9999) is None
