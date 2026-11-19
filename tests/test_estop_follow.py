# =============================================================================
# URTC-COMMON - tests/test_estop_follow.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A tool head that follows the emergency stop frame: the specification, the reference decisions, the vectors the firmware replays and the virtual board."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_estop_vectors  # noqa: E402
from urtc_common import estop_follow as ef  # noqa: E402
from urtc_common import protocol as p  # noqa: E402
from urtc_common import safety_policy as sp  # noqa: E402
from urtc_common.virtual_board import VirtualBoard  # noqa: E402

SPEC = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "conformance" / "estop_follow_vectors.json").read_text(encoding="utf-8"))
ENUMS = {entry["name"]: {v["name"]: v["value"] for v in entry["values"]} for entry in SPEC["enums"]}
CONSTANTS = {c["name"]: c for c in SPEC["constants"]}

TRIP = ef.encode(ef.KIND_TRIP, 1, ef.SOURCE_BRAIN, 3, 10)
ALIVE = lambda seq, epoch=3: ef.encode(ef.KIND_ALIVE, ef.ALIVE_OK, ef.SOURCE_BRAIN, epoch, seq)   # noqa: E731
ALIVE_TRIPPED = lambda seq, epoch=3: ef.encode(ef.KIND_ALIVE, ef.ALIVE_TRIPPED, ef.SOURCE_BRAIN, epoch, seq)   # noqa: E731
RELEASE = lambda seq, epoch=3: ef.encode(ef.KIND_RELEASE, 0, ef.SOURCE_BRAIN, epoch, seq)   # noqa: E731


# ---------------------------------------------------------------------------------------------------------------------
# the specification
# ---------------------------------------------------------------------------------------------------------------------
def test_the_feature_is_the_eighth_switch_and_the_masks_reach_it():
    features = ENUMS["firmware_feature"]
    assert features["ESTOP_FOLLOW"] == 128 == p.FEATURE_ESTOP_FOLLOW
    assert len(set(features.values())) == len(features) and all(v & (v - 1) == 0 for v in features.values())


def test_the_two_reasons_and_the_two_constants_are_in_the_specification():
    reasons = ENUMS["error_reason"]
    assert reasons["ESTOP"] == 9 == p.ERROR_REASON_ESTOP and reasons["ESTOP_SILENCE"] == 10 == p.ERROR_REASON_ESTOP_SILENCE
    assert len(set(reasons.values())) == len(reasons)
    assert CONSTANTS["ESTOP_CAN_ID"]["value"] == 1 == p.ESTOP_CAN_ID
    assert CONSTANTS["ESTOP_ALIVE_TIMEOUT_MS"]["value"] == 100 == p.ESTOP_ALIVE_TIMEOUT_MS and CONSTANTS["ESTOP_ALIVE_TIMEOUT_MS"]["unit"] == "ms"


def test_the_stop_identifier_beats_every_identifier_of_the_head_protocol():
    ids = [int(m["id"], 16) for m in SPEC["messages"] if m["id"].startswith("0x")]
    assert p.ESTOP_CAN_ID < min(ids), "0x001 must win the arbitration against every frame of the head protocol"


def test_a_stop_of_the_stack_is_never_lifted_by_the_clear_error_command():
    for reason in (p.ERROR_REASON_ESTOP, p.ERROR_REASON_ESTOP_SILENCE):
        assert sp.clear_error_decision(True, True, reason, 20, True) == p.CLEAR_ERROR_REFUSED_NOT_CLEARABLE
    assert sp.clear_error_decision(True, True, p.ERROR_REASON_COMMS_WATCHDOG, 20, True) == p.CLEAR_ERROR_CLEARED


# ---------------------------------------------------------------------------------------------------------------------
# the frame
# ---------------------------------------------------------------------------------------------------------------------
def test_every_frame_of_the_vectors_round_trips():
    for case in VECTORS["frames"]:
        data = bytes.fromhex(case["data_hex"])
        assert ef.encode(case["kind"], case["detail"], case["source"], case["epoch"], case["seq"]) == data
        assert ef.decode(data) == ef.Frame(case["kind"], case["detail"], case["source"], case["epoch"], case["seq"])


def test_every_malformed_frame_is_rejected_and_is_a_stop():
    for case in VECTORS["malformed"]:
        data = bytes.fromhex(case["data_hex"])
        assert ef.decode(data) is None, case["name"]
        node = ef.Node()
        node.on_frame(0, ALIVE_TRIPPED(1))
        node.on_frame(1, RELEASE(2))
        assert node.state == ef.STATE_READY
        assert node.on_frame(2, data).stop_reason == p.ERROR_REASON_ESTOP, case["name"]
        assert node.state == ef.STATE_LATCHED


def test_no_frame_of_eight_random_bytes_is_refused_as_a_stop_unless_it_is_well_formed():
    rng = random.Random(1)
    for _ in range(3000):
        data = bytes(rng.randrange(256) for _ in range(8))
        node = ef.Node()
        node.on_frame(0, ALIVE_TRIPPED(1))
        node.on_frame(1, RELEASE(2))
        effect = node.on_frame(2, data)
        frame = ef.decode(data)
        if frame is None or frame.kind == ef.KIND_TRIP or (frame.kind == ef.KIND_ALIVE and frame.detail == ef.ALIVE_TRIPPED):
            assert effect.stop_reason == p.ERROR_REASON_ESTOP and node.state == ef.STATE_LATCHED
        else:
            assert effect.stop_reason == 0


def test_the_sequence_order_is_modular():
    for case in VECTORS["seq_newer"]:
        assert ef.seq_newer(case["candidate"], case["have_last"], case["last"]) is case["newer"]
    assert ef.seq_newer(0, True, 0xFFFF) and not ef.seq_newer(0xFFFF, True, 0) and not ef.seq_newer(7, True, 7)


# ---------------------------------------------------------------------------------------------------------------------
# the scenarios
# ---------------------------------------------------------------------------------------------------------------------
def test_every_scenario_ends_where_the_vectors_say():
    assert len(VECTORS["scenarios"]) == len(make_estop_vectors.SCENARIOS)
    for scenario in VECTORS["scenarios"]:
        node = ef.Node(scenario.get("alive_timeout_ms"))
        if "master_timeout_ms" in scenario:
            node.set_master_timeout(scenario["master_timeout_ms"])
        for step in scenario["steps"]:
            if "frame" in step:
                effect = node.on_frame(step["t"], bytes.fromhex(step["frame"]))
            elif step["do"] == "tick":
                effect = node.tick(step["t"])
            else:
                effect = node.on_bus_off()
            assert (node.state == ef.STATE_READY) == (step["state_after"] == "READY"), (scenario["name"], step)
            assert effect.stop_reason == step["stop_reason"] and effect.released is step["released"], (scenario["name"], step)
            if "expect" in step:
                assert step["expect"] == step["state_after"]


def test_the_head_powers_up_latched_and_a_silent_bus_never_readies_it():
    node = ef.Node()
    assert node.state == ef.STATE_LATCHED
    for t in range(0, 10000, 7):
        assert node.tick(t) == ef.Effect()
    assert node.state == ef.STATE_LATCHED


def test_the_silence_of_the_master_is_a_stop_with_its_own_reason_exactly_after_the_timeout():
    node = ef.Node()
    node.on_frame(0, ALIVE_TRIPPED(1))
    assert node.on_frame(10, RELEASE(2)).released
    node.on_frame(20, ALIVE(3, 3))
    timeout = p.ESTOP_ALIVE_TIMEOUT_MS
    assert node.tick(20 + timeout) == ef.Effect()
    assert node.tick(20 + timeout + 1) == ef.Effect(stop_reason=p.ERROR_REASON_ESTOP_SILENCE)
    assert node.state == ef.STATE_LATCHED


def test_a_release_is_refused_when_any_of_its_conditions_fails():
    def ready_after(frames):
        n = ef.Node()
        for t, data in frames:
            n.on_frame(t, data)
        return n

    assert ready_after([(0, ALIVE_TRIPPED(1)), (10, RELEASE(2))]).state == ef.STATE_READY
    assert ready_after([(0, RELEASE(2))]).state == ef.STATE_LATCHED                             # epoch unknown
    assert ready_after([(0, ALIVE_TRIPPED(1)), (10, RELEASE(2, epoch=4))]).state == ef.STATE_LATCHED   # another epoch
    assert ready_after([(0, ALIVE_TRIPPED(5)), (10, RELEASE(5))]).state == ef.STATE_LATCHED      # not newer
    assert ready_after([(0, ALIVE_TRIPPED(1)), (101, RELEASE(2))]).state == ef.STATE_LATCHED     # the master is not live
    assert ready_after([(0, ALIVE_TRIPPED(1)), (100, RELEASE(2))]).state == ef.STATE_READY       # exactly at the timeout it still is


def test_the_time_wraps_at_32_bits():
    node = ef.Node()
    node.on_frame(0xFFFFFFF0, ALIVE_TRIPPED(1))
    assert node.on_frame(0xFFFFFFF8, RELEASE(2)).released
    assert node.tick((0xFFFFFFF0 + 100) & 0xFFFFFFFF) == ef.Effect()     # 0x54, exactly at the timeout
    assert node.tick((0xFFFFFFF0 + 101) & 0xFFFFFFFF).stop_reason == p.ERROR_REASON_ESTOP_SILENCE


def test_property_a_stop_frame_always_latches_whatever_came_before():
    rng = random.Random(7)
    for _ in range(500):
        node = ef.Node()
        t = 0
        for _ in range(rng.randrange(1, 12)):
            t += rng.randrange(0, 60)
            kind = rng.choice((ef.KIND_ALIVE, ef.KIND_RELEASE))
            node.on_frame(t, ef.encode(kind, 0, ef.SOURCE_BRAIN, rng.randrange(3), rng.randrange(65536)))
        assert node.on_frame(t + 1, TRIP).stop_reason == p.ERROR_REASON_ESTOP
        assert node.state == ef.STATE_LATCHED


def test_the_vectors_on_disk_are_the_ones_the_tool_writes():
    assert make_estop_vectors.build() == VECTORS
    assert make_estop_vectors.c_header(VECTORS).encode("utf-8") == (ROOT / "generated" / "estop_follow_vectors.h").read_bytes().replace(b"\r\n", b"\n")


# ---------------------------------------------------------------------------------------------------------------------
# the virtual board
# ---------------------------------------------------------------------------------------------------------------------
def test_a_virtual_head_without_the_feature_ignores_the_stop_frame():
    board = VirtualBoard()
    assert board.handle(p.ESTOP_CAN_ID, TRIP) == [] and board.system_error is False


def test_a_virtual_head_with_the_feature_powers_up_latched_and_follows_the_stop():
    board = VirtualBoard(features=p.FEATURE_ESTOP_FOLLOW, error_reason=p.ERROR_REASON_NONE, clear_result=0)
    assert board.system_error and board.error_reason == p.ERROR_REASON_ESTOP
    board.handle(p.ESTOP_CAN_ID, ALIVE_TRIPPED(1))
    board.advance(0.01)
    board.handle(p.ESTOP_CAN_ID, RELEASE(2))
    assert board.system_error is False and board.error_reason == p.ERROR_REASON_NONE
    board.advance(0.05)
    assert board.system_error is False
    board.advance(0.2)                                   # the master fell silent
    assert board.system_error and board.error_reason == p.ERROR_REASON_ESTOP_SILENCE
    board.handle(p.ESTOP_CAN_ID, TRIP)
    assert board.error_reason == p.ERROR_REASON_ESTOP_SILENCE, "the first reason of an error wins"


def test_the_clear_error_command_does_not_lift_a_stop_of_the_stack():
    board = VirtualBoard(features=p.FEATURE_ESTOP_FOLLOW | p.FEATURE_CLEAR_ERROR, error_reason=p.ERROR_REASON_NONE, clear_result=0)
    board.handle(p.CAN_ID_CLEAR_ERROR, p.MAGIC_CLEAR_ERROR)
    assert board.system_error and board.clear_result == p.CLEAR_ERROR_REFUSED_NOT_CLEARABLE


def test_a_release_does_not_lift_an_error_that_did_not_come_from_a_stop():
    board = VirtualBoard(features=p.FEATURE_ESTOP_FOLLOW)
    board.handle(p.ESTOP_CAN_ID, ALIVE_TRIPPED(1))
    board.system_error, board.error_reason = True, p.ERROR_REASON_THERMAL
    board.handle(p.ESTOP_CAN_ID, RELEASE(2))
    assert board.system_error and board.error_reason == p.ERROR_REASON_THERMAL


# ---------------------------------------------------------------------------------------------------------------------
# the configurable silence of the master
# ---------------------------------------------------------------------------------------------------------------------
def test_the_timeout_constants_are_in_the_specification_and_the_default_is_unchanged():
    assert CONSTANTS["ESTOP_ALIVE_TIMEOUT_MS"]["value"] == 100 == p.ESTOP_ALIVE_TIMEOUT_MS == ef.TIMEOUT_DEFAULT_MS
    assert CONSTANTS["ESTOP_ALIVE_TIMEOUT_MIN_MS"]["value"] == 40 == ef.TIMEOUT_MIN_MS
    assert CONSTANTS["ESTOP_ALIVE_TIMEOUT_MAX_MS"]["value"] == 500 == ef.TIMEOUT_MAX_MS
    assert ef.TIMEOUT_MIN_MS <= ef.TIMEOUT_DEFAULT_MS <= ef.TIMEOUT_MAX_MS


def test_a_head_nobody_configured_behaves_exactly_as_before():
    node = ef.Node()
    assert node.alive_timeout_ms == 100 and node.timeout_status == ef.TIMEOUT_OK
    assert ef.Node(0).alive_timeout_ms == 100 and ef.Node(None).alive_timeout_ms == 100


def test_every_value_inside_the_limits_is_taken_and_every_one_outside_is_rejected():
    for value in range(ef.TIMEOUT_MIN_MS, ef.TIMEOUT_MAX_MS + 1):
        assert ef.resolve_timeout(value) == (value, ef.TIMEOUT_OK)
    for value in list(range(1, ef.TIMEOUT_MIN_MS)) + [ef.TIMEOUT_MAX_MS + 1, 1000, 65535, 2 ** 32, -1, -100]:
        assert ef.resolve_timeout(value) == (100, ef.TIMEOUT_REJECTED), value
    for junk in (True, 50.0, "50", b"50"):
        assert ef.resolve_timeout(junk) == (100, ef.TIMEOUT_REJECTED), junk   # type: ignore[arg-type]


def test_the_configuration_file_key():
    assert ef.CONFIG_KEY == "estop_alive_timeout_ms"
    assert ef.timeout_from_config({}) == (100, ef.TIMEOUT_OK)
    assert ef.timeout_from_config({"estop_alive_timeout_ms": 250}) == (250, ef.TIMEOUT_OK)
    assert ef.timeout_from_config({"estop_alive_timeout_ms": 5}) == (100, ef.TIMEOUT_REJECTED)


def test_the_master_value_never_makes_the_head_more_tolerant():
    for own in (40, 60, 100, 250, 500):
        for master in (None, 0, 19, 20, 39, 40, 60, 100, 300, 500, 501, 65535):
            value, status = ef.effective_timeout(own, master)
            assert value <= own, (own, master)
            if master and ef.TIMEOUT_MIN_MS <= master <= ef.TIMEOUT_MAX_MS:
                assert value == min(own, master)
                assert status == (ef.TIMEOUT_OK if master == own else ef.TIMEOUT_MASTER_DIFFERS)
            elif master:
                assert value == own and status == ef.TIMEOUT_MASTER_REJECTED
            else:
                assert value == own and status == ef.TIMEOUT_OK


def test_a_rejected_head_value_stays_reported_when_the_master_agrees():
    node = ef.Node(7)
    assert node.timeout_status == ef.TIMEOUT_REJECTED and node.alive_timeout_ms == 100
    assert node.set_master_timeout(100) == ef.TIMEOUT_REJECTED
    assert node.set_master_timeout(40) == ef.TIMEOUT_MASTER_DIFFERS and node.alive_timeout_ms == 40


def test_the_timeout_tables_of_the_vectors_are_the_reference_answers():
    for case in VECTORS["timeout_config"]:
        assert ef.resolve_timeout(case["requested"]) == (case["ms"], case["status"])
    for case in VECTORS["timeout_master"]:
        assert ef.effective_timeout(case["own"], case["master"]) == (case["ms"], case["status"])
    assert VECTORS["constants"]["alive_timeout_min_ms"] == 40 and VECTORS["constants"]["alive_timeout_max_ms"] == 500


def test_the_silence_is_exact_at_the_edges_of_the_limits():
    for timeout in (ef.TIMEOUT_MIN_MS, 100, ef.TIMEOUT_MAX_MS):
        node = ef.Node(timeout)
        node.on_frame(0, ALIVE_TRIPPED(1))
        node.on_frame(1, RELEASE(2))
        node.on_frame(2, ALIVE(3))
        assert node.tick(2 + timeout).stop_reason == 0 and node.state == ef.STATE_READY
        assert node.tick(3 + timeout).stop_reason == p.ERROR_REASON_ESTOP_SILENCE and node.state == ef.STATE_LATCHED


def test_the_virtual_head_uses_the_configured_timeout():
    board = VirtualBoard(features=p.FEATURE_ESTOP_FOLLOW, error_reason=p.ERROR_REASON_NONE, clear_result=0, estop_alive_timeout_ms=40)
    board.handle(p.ESTOP_CAN_ID, ALIVE_TRIPPED(1))
    board.advance(0.005)
    board.handle(p.ESTOP_CAN_ID, RELEASE(2))
    assert board.system_error is False
    board.advance(0.02)
    assert board.system_error is False
    board.advance(0.02)                                  # 45 ms of silence: above the 40 ms of this head, below the default 100 ms
    assert board.system_error and board.error_reason == p.ERROR_REASON_ESTOP_SILENCE


# ---------------------------------------------------------------------------------------------------------------------
# the silence of the master on the bus: 0x1AE with DLC 8 writes it, 0x1AF with the byte 3 or 4 asks for it
# ---------------------------------------------------------------------------------------------------------------------
def test_the_wire_frames_of_the_silence_round_trip_and_are_big_endian():
    identifier, data = p.encode_set_features_request_estop_timeout(0x80, 0, 50, magic=b"FEAT")
    assert (identifier, data) == (0x1AE, bytes.fromhex("4645415480000032"))
    assert p.decode_set_features_request_estop_timeout(data)["estop_timeout_ms"] == 50
    assert p.encode_features_resp_request_estop_timeout(3) == (0x1AF, b"\x03")
    assert p.encode_features_resp_request_estop_timeout(4) == (0x1AF, b"\x04")
    _, answer = p.encode_features_resp_response_estop_timeout(0x80, 0x80, 255, 0, 0, 3, 500)
    assert answer == ef.encode_timeout_answer(0x80, 0x80, 0, 0, 500) and answer[6:] == b"\x01\xf4"
    assert ef.decode_timeout_answer(answer)["timeout_ms"] == 500
    assert ef.decode_timeout_answer(answer[:6]) is None


def test_the_old_write_and_query_forms_behave_exactly_as_before():
    assert ef.parse_features_write(bytes.fromhex("464541542001")) == ef.FeaturesWrite(0x20, 0x01, ef.KEEP_STORED_TIMEOUT, 6)
    assert ef.parse_features_write(bytes.fromhex("4645415480")) == ef.FeaturesWrite(0x80, 0, ef.KEEP_STORED_TIMEOUT, 5)   # keeps the stored silence
    assert ef.query_form(b"") == ef.QUERY_BASIC and ef.query_form(b"\x00") == ef.QUERY_BASIC and ef.query_form(b"\x02") == ef.QUERY_EXTENDED
    assert ef.query_form(b"\x03\x03") == ef.QUERY_BASIC     # only a query of exactly one byte asks for more


def test_a_write_of_the_silence_is_taken_only_inside_the_limits_and_never_in_part():
    for ms in range(0, 65536):
        data = bytes.fromhex("464541548000") + ms.to_bytes(2, "big")
        write = ef.parse_features_write(data)
        if ms == 0 or ef.TIMEOUT_MIN_MS <= ms <= ef.TIMEOUT_MAX_MS:
            assert write == ef.FeaturesWrite(0x80, 0, ms, 8), ms
        else:
            assert write is None, ms   # the whole frame is ignored: not even the switches change
    assert ef.parse_features_write(bytes.fromhex("46454154800000")) is None     # DLC 7
    assert ef.parse_features_write(bytes.fromhex("464541548000003200")) is None  # DLC 9
    assert ef.parse_features_write(bytes.fromhex("4645415480040032")) is None    # a switch of the second byte this firmware does not have


def test_the_wire_vectors_are_the_ones_of_the_twin():
    for case in VECTORS["feature_writes"]:
        write = ef.parse_features_write(bytes.fromhex(case["data_hex"]))
        assert (write is not None) == case["valid"], case
        if write:
            assert (write.mask, write.mask_ext) == (case["mask"], case["mask_ext"])
            assert case["timeout_ms"] == (-1 if write.timeout_ms is None else write.timeout_ms)
    for case in VECTORS["feature_queries"]:
        assert ef.query_form(bytes.fromhex(case["data_hex"])) == case["form"], case
    for case in VECTORS["timeout_answers"]:
        data = ef.encode_timeout_answer(case["stored"], case["running"], case["stored_ext"], case["running_ext"], case["timeout_ms"])
        assert data.hex() == case["data_hex"]
    assert {c["timeout_ms"] for c in VECTORS["feature_writes"] if c["valid"]} >= {-1, 0, 40, 50, 500}
    assert not any(c["valid"] for c in VECTORS["feature_writes"] if c["data_hex"].endswith(("0027", "01F5", "0014", "0001")) and len(c["data_hex"]) == 16)


def test_a_master_that_answers_with_a_lower_silence_shortens_the_head_but_never_lengthens_it():
    answer = ef.decode_timeout_answer(ef.encode_timeout_answer(0x80, 0x80, 0, 0, 60))
    node = ef.Node(200)
    assert node.set_master_timeout(answer["timeout_ms"]) == ef.TIMEOUT_MASTER_DIFFERS and node.alive_timeout_ms == 60
    node = ef.Node(60)
    node.set_master_timeout(400)
    assert node.alive_timeout_ms == 60
    node = ef.Node(100)
    assert node.set_master_timeout(0) == ef.TIMEOUT_OK and node.alive_timeout_ms == 100   # a board with ESTOP_FOLLOW off answers 0: nothing announced
