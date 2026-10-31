# =============================================================================
# URTC-COMMON - tests/test_bus_scenario.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The scenarios of the simulated bus: the file is checked strictly, every fault does what the document says, the same seed gives the same
frames, and no scenario can make a node say something it did not."""
from __future__ import annotations

import json

import pytest

from urtc_common import bus_scenario as bs
from urtc_common import rack_sim as rk


class FakeTime:
    """A clock and a sleep that move together, so a delay costs no real time."""

    def __init__(self) -> None:
        self.now = 1000.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Node:
    """A tiny node: the tool query is answered with the tool, the version query with a counter, every other frame is kept."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, bytes]] = []
        self.queue: list[tuple[int, bytes]] = []
        self.produced: list[tuple[int, bytes]] = []
        self.count = 0

    def open_channel(self, *args, **kwargs) -> None:
        pass

    def close_channel(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send_frame(self, can_id: int, data: bytes = b"") -> None:
        self.sent.append((can_id, bytes(data)))
        if can_id == 0x110:
            self.say((0x111, bytes([0, 0, 0, 0, 0, 0, 0, 0])))
        elif can_id == 0x7F8:
            self.count += 1
            self.say((0x7F9, bytes([1, 0, 3, 3, 0, 0, self.count, 9])))

    def say(self, frame: tuple[int, bytes]) -> None:
        self.queue.append(frame)
        self.produced.append(frame)

    def read_frame(self, timeout: float = 0.05):
        return self.queue.pop(0) if self.queue else None


def make(faults: list[dict], seed: int = 1, **kwargs):
    node, time_ = Node(), FakeTime()
    scenario = bs.from_dict({"format": bs.FORMAT, "name": "t", "seed": seed, "faults": faults})
    return bs.FaultyBus(node, scenario, clock=time_.clock, sleep=time_.sleep, **kwargs), node, time_


def drain(bus: bs.FaultyBus, limit: int = 100) -> list[tuple[int, bytes]]:
    out = []
    for _ in range(limit):
        frame = bus.read_frame(0.01)
        if frame is None:
            break
        out.append(frame)
    return out


# ---- the file ----------------------------------------------------------------------------------------------------------------
def doc(*faults, **more):
    return {"format": bs.FORMAT, "name": "x", "faults": list(faults), **more}


def test_a_scenario_with_no_faults_is_valid_and_empty_is_allowed():
    assert bs.validate(doc()) == []
    assert bs.from_dict(doc()).seed == 0


BAD = [
    ("not an object", [1]),
    ("wrong format", {**doc(), "format": "urtc-scenario/2"}),
    ("no name", {"format": bs.FORMAT, "faults": []}),
    ("bad name", doc(name="a b")),
    ("unknown top field", doc(extra=1)),
    ("bool seed", doc(seed=True)),
    ("negative seed", doc(seed=-1)),
    ("seed too large", doc(seed=2 ** 32)),
    ("faults not a list", {"format": bs.FORMAT, "name": "x", "faults": {}}),
    ("too many rules", doc(*[{"fault": "drop"}] * 65)),
    ("rule not an object", doc("drop")),
    ("unknown fault", doc({"fault": "explode"})),
    ("unknown field", doc({"fault": "drop", "bogus": 1})),
    ("per_mille 0", doc({"fault": "drop", "per_mille": 0})),
    ("per_mille float", doc({"fault": "drop", "per_mille": 5.5})),
    ("bad direction", doc({"fault": "drop", "direction": "up"})),
    ("id out of range", doc({"fault": "drop", "id": 0x800})),
    ("id bool", doc({"fault": "drop", "id": True})),
    ("id empty list", doc({"fault": "drop", "id": []})),
    ("copies 4", doc({"fault": "duplicate", "copies": 4})),
    ("window 1", doc({"fault": "reorder", "window": 1})),
    ("delay none", doc({"fault": "delay"})),
    ("delay both", doc({"fault": "delay", "ms": 5, "min_ms": 1, "max_ms": 2})),
    ("delay min only", doc({"fault": "delay", "min_ms": 1})),
    ("delay inverted", doc({"fault": "delay", "min_ms": 9, "max_ms": 2})),
    ("burst no length", doc({"fault": "burst_loss"})),
    ("burst period not above length", doc({"fault": "burst_loss", "length": 3, "period": 3})),
    ("burst per_mille", doc({"fault": "burst_loss", "length": 1, "per_mille": 500})),
    ("truncate dlc 8", doc({"fault": "truncate", "dlc": 8})),
    ("mute per_mille", doc({"fault": "mute", "per_mille": 10})),
    ("reject no id", doc({"fault": "reject", "reason": "tool_absent", "reply_id": 0x261})),
    ("reject acknowledgement reason", doc({"fault": "reject", "id": 0x260, "reason": "applied", "reply_id": 0x261})),
    ("reject reply id out of range", doc({"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": 0x800})),
    ("reject reply id not a number", doc({"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": "reply"})),
    ("reject reply id null", doc({"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": None})),
    ("reject direction", doc({"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": 0x261, "direction": "rx"})),
    ("free_tool no answer", doc({"fault": "free_tool"})),
    ("free_tool valid without tool", doc({"fault": "free_tool", "answer": "valid"})),
    ("free_tool tool 25", doc({"fault": "free_tool", "answer": "valid", "tool": 25})),
    ("free_tool tool with unset", doc({"fault": "free_tool", "answer": "unset", "tool": 1})),
    ("free_tool selection 25", doc({"fault": "free_tool", "answer": "out_of_range", "selection": 25})),
    ("free_tool jumper 31", doc({"fault": "free_tool", "answer": "foreign", "jumper": 31})),
    ("free_tool id", doc({"fault": "free_tool", "answer": "silent", "id": 0x1A3})),
]


@pytest.mark.parametrize("label,document", BAD, ids=[label for label, _ in BAD])
def test_anything_not_understood_is_refused(label, document):
    assert bs.validate(document), label
    with pytest.raises(bs.ScenarioError):
        bs.from_dict(document)


def test_the_text_is_read_strictly():
    for text in ('{"format": "urtc-scenario/1", "name": "x", "name": "y", "faults": []}',
                 '{"format": "urtc-scenario/1", "name": "x", "faults": [], "seed": NaN}', "not json", "[]",
                 json.dumps(doc()) + " " * 70000):
        with pytest.raises(bs.ScenarioError):
            bs.parse(text)


def test_a_scenario_survives_writing_and_reading():
    scenario = bs.generate(5, kinds=bs.GENERATED_KINDS + bs.NODE_PROFILES, rules=8)
    assert bs.parse(scenario.to_json()) == scenario


def test_a_file_that_cannot_be_read_is_an_error(tmp_path):
    with pytest.raises(bs.ScenarioError):
        bs.load(tmp_path / "missing.json")


# ---- the faults --------------------------------------------------------------------------------------------------------------
def test_no_rules_changes_nothing():
    bus, node, _ = make([])
    bus.send_frame(0x110, b"")
    bus.send_frame(0x7F8, b"")
    assert drain(bus) == [(0x111, bytes(8)), (0x7F9, bytes([1, 0, 3, 3, 0, 0, 1, 9]))]
    assert node.sent == [(0x110, b""), (0x7F8, b"")] and not bus.events and not bus.stats


def test_drop_with_a_window_and_an_id():
    bus, node, _ = make([{"fault": "drop", "direction": "tx", "id": 0x7F8, "from": 1, "count": 2}])
    for _ in range(5):
        bus.send_frame(0x7F8, b"")
    bus.send_frame(0x110, b"")
    assert [f for f in node.sent if f[0] == 0x7F8] == [(0x7F8, b"")] * 3 and (0x110, b"") in node.sent
    assert bus.stats["drop"] == 2


def test_drop_of_the_answers():
    bus, _, _ = make([{"fault": "drop", "direction": "rx"}])
    bus.send_frame(0x110, b"")
    assert drain(bus) == []


def test_duplicate_repeats_the_frame():
    bus, node, _ = make([{"fault": "duplicate", "direction": "tx", "copies": 2}])
    bus.send_frame(0x7F8, b"")
    assert len(node.sent) == 3 and len(drain(bus)) == 3


def test_truncate_cuts_to_the_minimum_length():
    bus, node, _ = make([{"fault": "truncate", "dlc": 3, "direction": "rx"}])
    bus.send_frame(0x110, b"")
    assert drain(bus) == [(0x111, bytes(3))]
    bus2, node2, _ = make([{"fault": "truncate", "dlc": 0, "direction": "tx"}])
    bus2.send_frame(0x260, bytes(8))
    assert node2.sent == [(0x260, b"")]


def test_delay_holds_the_frame_until_its_time():
    bus, node, t = make([{"fault": "delay", "direction": "rx", "ms": 200}])
    bus.send_frame(0x110, b"")
    start = t.now
    assert bus.read_frame(0.05) is None            # the answer is due in 200 ms
    assert bus.read_frame(0.5) == (0x111, bytes(8))
    assert 0.2 <= t.now - start <= 0.3


def test_delay_of_a_sent_frame_reaches_the_node_later():
    bus, node, t = make([{"fault": "delay", "direction": "tx", "ms": 100}])
    bus.send_frame(0x110, b"")
    assert node.sent == []
    assert bus.read_frame(0.5) == (0x111, bytes(8)) and t.now - 1000.0 >= 0.1


def test_reorder_releases_a_full_window_shuffled_and_a_partial_one_as_it_is():
    bus, _, _ = make([{"fault": "reorder", "direction": "rx", "window": 4}], seed=3)
    for _ in range(4):
        bus.send_frame(0x7F8, b"")
    got = [frame[1][6] for frame in drain(bus)]
    assert sorted(got) == [1, 2, 3, 4] and got != [1, 2, 3, 4]
    bus.send_frame(0x7F8, b"")
    bus.send_frame(0x7F8, b"")
    assert [frame[1][6] for frame in drain(bus)] == [5, 6]


def test_burst_loss_drops_runs_of_frames():
    bus, node, _ = make([{"fault": "burst_loss", "direction": "tx", "length": 2, "period": 5, "from": 1}])
    for _ in range(10):
        bus.send_frame(0x7F8, b"")
    assert len(node.sent) == 6 and bus.stats["burst_loss"] == 4        # frames 1,2 and 6,7 of the ten are lost


def test_mute_stops_the_answers_for_a_while():
    bus, node, _ = make([{"fault": "mute", "direction": "tx", "from": 1, "count": 2}])
    for _ in range(4):
        bus.send_frame(0x110, b"")
    assert len(node.sent) == 2 and len(drain(bus)) == 2    # the node did not hear two orders, so it answered two
    bus, node, _ = make([{"fault": "mute", "direction": "rx", "from": 1, "count": 2}])
    for _ in range(4):
        bus.send_frame(0x110, b"")
    assert len(node.sent) == 4 and len(drain(bus)) == 2    # the node heard all four and two answers never arrived


def test_reject_answers_with_the_reason_and_keeps_the_order_from_the_node():
    bus, node, _ = make([{"fault": "reject", "id": 0x260, "reason": "held_rate"}])    # no reply_id: the standard identifier of the reply of the rack
    bus.send_frame(0x260, rk.encode_set_preheat_can(1, 0, 300))
    frames = drain(bus)
    code = rk.REPLY_CODES.index("held_rate")
    assert frames == [(0x261, bytes([rk.CMD_SET_PREHEAT, 0, code]))] and node.sent == []
    assert rk.REPLY_CODES == bs.REPLY_CODES and rk.CMD_SET_PREHEAT == bs.CMD_SET_PREHEAT and rk.CAN_ID_SET_PREHEAT == bs.CAN_ID_SET_PREHEAT
    assert rk.CAN_ID_REPLY == bs.CAN_ID_REPLY == 0x261
    assert rk.parse_reply_can(*frames[0]) == {"ack": False, "cmd": 1, "tool": 0, "code": code, "reason": "held_rate"}


def test_reject_without_a_reply_id_is_valid_and_an_explicit_one_still_works():
    assert bs.validate(doc({"fault": "reject", "id": 0x260, "reason": "tool_absent"})) == []
    bus, _, _ = make([{"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": 0x3F0}])
    bus.send_frame(0x260, rk.encode_set_preheat_can(1, 0, 300))
    assert [can_id for can_id, _ in drain(bus)] == [0x3F0]                           # another identifier, named on purpose
    bus, _, _ = make([{"fault": "reject", "id": 0x260, "reason": "tool_absent", "reply_id": 0x261}])
    bus.send_frame(0x260, rk.encode_set_preheat_can(1, 0, 300))
    assert [can_id for can_id, _ in drain(bus)] == [0x261]                           # naming the standard one is the same as leaving it out


def test_a_generated_reject_leaves_the_reply_id_out_unless_another_one_is_asked_for():
    for seed in range(40):
        for rule in bs.generate(seed, kinds=("reject",), rules=4).faults:
            assert "reply_id" not in rule
        for rule in bs.generate(seed, kinds=("reject",), rules=4, reply_id=0x3F0).faults:
            assert rule["reply_id"] == 0x3F0
        for rule in bs.generate(seed, kinds=("reject",), rules=4, reply_id=0x261).faults:
            assert "reply_id" not in rule


@pytest.mark.parametrize("reason", bs.REFUSAL_REASONS)
def test_every_refusal_reason_is_a_refusal_of_the_rack(reason):
    bus, _, _ = make([{"fault": "reject", "id": 0x260, "reason": reason}])
    bus.send_frame(0x260, rk.encode_set_preheat_can(1, 0, 300))
    payload = drain(bus)[0][1]
    frame = rk.encode_reply(1, payload[0], payload[1], reason)
    assert rk.parse_reply(frame) is not None and rk.parse_reply(frame)["ack"] is False and payload[2] == rk.REPLY_CODES.index(reason)


def test_reject_with_deliver_still_reaches_the_node():
    bus, node, _ = make([{"fault": "reject", "id": 0x260, "reason": "tool_absent", "deliver": True}])
    bus.send_frame(0x260, bytes(8))
    assert node.sent == [(0x260, bytes(8))]


@pytest.mark.parametrize("answer,extra,tool", [
    ("valid", {"tool": 5}, 5), ("unset", {}, None), ("foreign", {"jumper": 4}, None), ("out_of_range", {"selection": 40}, None),
    ("short", {}, None), ("silent", {}, "none"),
])
def test_free_tool_head_answers_the_way_the_contract_judges(answer, extra, tool):
    bus, node, _ = make([{"fault": "free_tool", "answer": answer, **extra}])
    bus.send_frame(0x1A3, b"")
    frames = drain(bus)
    assert node.sent == []
    if tool == "none":
        assert frames == []
        return
    assert len(frames) == 1 and frames[0][0] == 0x1A3
    assert rk.parse_free_tool_reply(frames[0][1]) == tool


def test_a_selection_written_to_a_free_head_counts_after_the_power_cycle():
    bus, _, _ = make([{"fault": "free_tool", "answer": "unset"}])
    bus.send_frame(0x1A2, bytes([7]))
    assert rk.parse_free_tool_reply(drain(bus)[0][1]) is None          # still the old register
    bus.power_cycle()
    bus.send_frame(0x1A3, b"")
    assert rk.parse_free_tool_reply(drain(bus)[0][1]) == 6


def test_a_selection_out_of_range_is_not_stored_by_the_head():
    bus, _, _ = make([{"fault": "free_tool", "answer": "unset", "answer_to_write": False}])
    bus.send_frame(0x1A2, bytes([200]))
    assert drain(bus) == []
    bus.power_cycle()
    bus.send_frame(0x1A3, b"")
    assert rk.parse_free_tool_reply(drain(bus)[0][1]) is None


def test_the_rack_resolver_never_resolves_on_a_scenario_without_a_valid_answer():
    for answer, extra in (("unset", {}), ("foreign", {"jumper": 2}), ("out_of_range", {"selection": 99}), ("short", {}), ("silent", {})):
        bus, _, t = make([{"fault": "free_tool", "answer": answer, **extra}])
        resolver = rk.FreeToolResolver()
        now = 0
        for _ in range(40):
            now += 100
            query, event = resolver.step(now, None)
            if query:
                bus.send_frame(0x1A3, b"")
                for _, payload in drain(bus):
                    resolver.step(now, payload)
        assert not resolver.resolved, answer


# ---- the same seed, the same frames ------------------------------------------------------------------------------------------
def trace_of(scenario: bs.Scenario, seed: int | None = None) -> list:
    node, t = Node(), FakeTime()
    bus = bs.FaultyBus(node, scenario, seed=seed, clock=t.clock, sleep=t.sleep)
    out: list = []
    for index in range(30):
        bus.send_frame((0x110, 0x7F8, 0x260)[index % 3], bytes(range(index % 8)))
        t.now += 0.003
        out.append(("rx", bus.read_frame(0.02)))
    out.append(("rest", drain(bus)))
    return out + [("sent", node.sent), ("events", list(bus.events))]


@pytest.mark.parametrize("seed", range(12))
def test_the_same_scenario_and_seed_give_the_same_frames(seed):
    scenario = bs.generate(seed, kinds=bs.GENERATED_KINDS + bs.NODE_PROFILES, rules=5)
    assert trace_of(scenario) == trace_of(scenario)


def test_another_seed_gives_another_sequence_for_a_random_rule():
    scenario = bs.from_dict(doc({"fault": "drop", "per_mille": 500}, seed=1))
    traces = {json.dumps(trace_of(scenario, seed=s), default=repr) for s in range(8)}
    assert len(traces) > 1
    assert trace_of(scenario, seed=4) == trace_of(scenario, seed=4)


def test_the_seed_of_the_run_may_replace_the_one_of_the_file_but_must_be_valid():
    scenario = bs.from_dict(doc())
    with pytest.raises(bs.ScenarioError):
        bs.FaultyBus(Node(), scenario, seed=-1)


def test_the_generator_is_deterministic_and_always_valid():
    for seed in range(300):
        first = bs.generate(seed, kinds=bs.GENERATED_KINDS + bs.NODE_PROFILES)
        assert first == bs.generate(seed, kinds=bs.GENERATED_KINDS + bs.NODE_PROFILES)
        assert bs.validate(first.as_dict()) == []
        for rule in first.faults:
            assert not (rule["fault"] == "free_tool" and rule["answer"] == "valid")
    assert bs.generate_suite(9, 20) == bs.generate_suite(9, 20)
    assert len({s.seed for s in bs.generate_suite(9, 20)}) > 1


def test_the_generator_combines_several_kinds():
    seen = set()
    for scenario in bs.generate_suite(2, 60):
        seen |= {rule["fault"] for rule in scenario.faults}
    assert seen == set(bs.GENERATED_KINDS)


def test_the_generator_refuses_what_it_does_not_know():
    for call in (lambda: bs.generate(-1), lambda: bs.generate(1, kinds=("explode",)), lambda: bs.generate(1, kinds=()),
                 lambda: bs.generate(1, rules=0), lambda: bs.generate_suite(1, 0)):
        with pytest.raises(bs.ScenarioError):
            call()


# ---- a scenario cannot make something up -------------------------------------------------------------------------------------
def _is_prefix_of_one(frame: tuple[int, bytes], produced: list[tuple[int, bytes]]) -> bool:
    return any(frame[0] == p[0] and p[1].startswith(frame[1]) for p in produced)


@pytest.mark.parametrize("seed", range(150))
def test_no_generated_scenario_invents_a_frame(seed):
    """Whatever the generated scenario does, every frame that comes back is one the node produced (maybe shortened) and every frame the node
    saw is one that was sent (maybe shortened): so a check that the node never satisfies cannot pass."""
    scenario = bs.generate(seed)
    node, t = Node(), FakeTime()
    bus = bs.FaultyBus(node, scenario, clock=t.clock, sleep=t.sleep)
    sent: list[tuple[int, bytes]] = []
    got: list[tuple[int, bytes]] = []
    for index in range(40):
        frame = ((0x110, 0x7F8, 0x260)[index % 3], bytes(range(index % 8)))
        sent.append(frame)
        bus.send_frame(*frame)
        t.now += 0.002
        answer = bus.read_frame(0.02)
        if answer is not None:
            got.append(answer)
    bus.flush()
    got += drain(bus)
    for frame in got:
        assert _is_prefix_of_one(frame, node.produced), (seed, frame)
    for frame in node.sent:
        assert _is_prefix_of_one(frame, sent), (seed, frame)


@pytest.mark.parametrize("seed", range(200))
def test_a_plan_that_must_fail_does_not_pass_under_any_generated_scenario(seed):
    """The check 'the node says it is tool 5' cannot pass, because the node is tool 0: no generated scenario changes that."""
    scenario = bs.generate(seed, kinds=bs.GENERATED_KINDS + bs.NODE_PROFILES)
    node, t = Node(), FakeTime()
    bus = bs.FaultyBus(node, scenario, clock=t.clock, sleep=t.sleep)
    seen_tool_5 = False
    for _ in range(20):
        bus.send_frame(0x110, b"")
        for _ in range(3):
            frame = bus.read_frame(0.05)
            if frame and frame[0] == 0x111 and len(frame[1]) >= 1 and frame[1][0] == 5:
                seen_tool_5 = True
    assert not seen_tool_5


def test_a_node_is_never_made_to_answer_a_command_it_was_not_sent():
    scenario = bs.from_dict(doc({"fault": "duplicate", "copies": 3}, {"fault": "delay", "ms": 5}, {"fault": "reorder", "window": 3}))
    bus, node, t = make(scenario.faults and list(scenario.faults))
    bus.send_frame(0x110, b"")
    bus.flush()
    drain(bus)
    assert all(frame[0] == 0x110 for frame in node.sent)


# ---- the command line ---------------------------------------------------------------------------------------------------------
def test_the_command_line_validates_and_generates(tmp_path, capsys):
    scenario = tmp_path / "s.json"
    scenario.write_text(bs.generate(3).to_json(), encoding="utf-8")
    assert bs.main(["validate", str(scenario)]) == 0
    scenario.write_text('{"format": "urtc-scenario/1"}', encoding="utf-8")
    assert bs.main(["validate", str(scenario)]) == 1
    assert bs.main(["generate", "--seed", "4", "--count", "3", "--out", str(tmp_path / "out")]) == 0
    files = sorted((tmp_path / "out").glob("*.json"))
    assert len(files) == 3 and all(bs.load(f) for f in files)
    again = tmp_path / "again"
    bs.main(["generate", "--seed", "4", "--count", "3", "--out", str(again)])
    assert [f.read_text() for f in files] == [f.read_text() for f in sorted(again.glob("*.json"))]
    assert bs.main(["generate", "--seed", "1", "--kinds", "explode"]) == 1
    capsys.readouterr()
    assert bs.main(["generate", "--seed", "2"]) == 0 and json.loads(capsys.readouterr().out)["format"] == bs.FORMAT


# ---- the document ------------------------------------------------------------------------------------------------------------
def test_the_document_names_every_kind_reason_and_answer():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "docs" / "BUS_SCENARIOS.md").read_text(encoding="utf-8")
    for word in bs.KINDS + bs.REFUSAL_REASONS + bs.FREE_TOOL_ANSWERS + bs.DIRECTIONS:
        assert f"`{word}`" in text, word
    assert bs.FORMAT in text


def test_virtual_time_moves_only_when_asked_and_a_read_costs_time():
    t = bs.VirtualTime(10.0)
    assert t.clock() == 10.0
    t.sleep(0.5)
    t.sleep(-1)
    assert t.clock() == 10.5
    node = Node()
    bus = bs.FaultyBus(node, bs.from_dict(doc()), clock=t.clock, sleep=t.sleep, read_cost_s=0.001)
    bus.read_frame(0.01)
    assert t.clock() > 10.5
