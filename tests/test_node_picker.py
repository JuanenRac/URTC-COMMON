# =============================================================================
# URTC-COMMON - tests/test_node_picker.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The node picker: the state of each head, the switch of the extension, the confirmation, the lapse and the gate on single-head frames."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from urtc_common import multinode_host as mh
from urtc_common import node_picker as np_
from urtc_common import node_picker_strings as strings
from urtc_common import protocol as p
from urtc_common import transports

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "conformance" / "node_picker_vectors.json").read_text(encoding="utf-8"))
SINGLE_HEAD = 0x120


def test_the_vectors_are_current():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_node_picker_vectors.py"), "--check"], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("case", VECTORS["classify"])
def test_a_head_is_classified_as_the_vectors_say(case):
    assert np_.classify_node(case["state"], case["conflict"], case["alive"]) == case["status"]


@pytest.mark.parametrize("case", VECTORS["switch"])
def test_the_switch_is_read_as_the_vectors_say(case):
    assert np_.switch_state(case["config"]) == case["switch"]


@pytest.mark.parametrize("case", VECTORS["fail"])
def test_a_refusal_has_its_text(case):
    assert strings.fail_key(case["reason"]) == case["key"]


def test_the_texts_exist_in_the_eight_languages_with_the_same_placeholders():
    english = strings.STRINGS["english"]
    assert set(strings.STRINGS) == set(strings.LANGUAGES) and len(strings.LANGUAGES) == 8
    holder = re.compile(r"\{(\w+)\}")
    for language, table in strings.STRINGS.items():
        assert set(table) == set(english), language
        for key, value in table.items():
            assert value.strip(), (language, key)
            assert set(holder.findall(value)) == set(holder.findall(english[key])), (language, key)
    for key in english:
        if key.startswith(("NP_ST_", "NP_COL_", "NP_BUS_")):
            assert len({table[key] for table in strings.STRINGS.values()}) > 1, key


def test_a_bus_where_nobody_answers_is_a_single_head_and_everything_passes():
    picker, _bus = np_.sim_picker(())
    picker.scan()
    assert picker.mode == np_.MODE_LEGACY and picker.rows() == [] and picker.may_send()
    sent = []

    class Wire:
        def send_frame(self, can_id, data=b""):
            sent.append(can_id)

    np_.GatedTransport(Wire(), picker).send_frame(SINGLE_HEAD, b"")
    assert sent == [SINGLE_HEAD]
    assert [n.key for n in picker.take_notices()] == ["NP_SW_UNKNOWN", "NP_MSG_LEGACY"]


def test_finding_the_heads_lists_them_without_selecting_any():
    picker, bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1})
    picker.scan()
    rows = picker.rows()
    assert [(r.address, r.status, r.selectable, r.mine) for r in rows] == [(2, "ready", True, False), (5, "ready", True, False)]
    assert rows[0].serial == "00001002" and picker.selected is None and not picker.may_send()
    assert [n.key for n in picker.take_notices()] == ["NP_MSG_FOUND"]
    assert bus.nodes[0].obeyed == [] and bus.nodes[1].obeyed == []
    snap = picker.snapshot("spanish")
    assert snap["summary"] == "2 cabezal(es) en el bus" and snap["rows"][0]["status_text"] == "Listo" and snap["switch"] == "on"


def test_nothing_is_selected_until_the_person_confirms():
    picker, _bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1})
    picker.scan()
    assert picker.ask(5) and picker.pending == 5
    assert "address 5" in picker.snapshot()["confirm_text"]
    assert picker.selected is None
    picker.cancel()
    assert picker.pending is None and picker.selected is None and not picker.confirm()
    picker.ask(5)
    assert picker.confirm() and picker.selected == 5 and picker.may_send()
    row = [r for r in picker.rows() if r.address == 5][0]
    assert row.status == "selected" and row.mine
    assert picker.take_notices()[-1].key == "NP_MSG_SELECTED"
    picker.release()
    assert picker.selected is None and not picker.may_send()


def test_a_head_that_cannot_be_selected_says_why_and_nothing_is_selected():
    picker, bus = np_.sim_picker((6, 6, 9))
    bus.nodes[1].serial = 0x9999
    picker.scan()
    rows = {r.address: r for r in picker.rows()}
    assert rows[6].status == "conflict" and not rows[6].selectable and rows[9].selectable
    assert not picker.ask(6)
    assert picker.take_notices()[-1].key == "NP_FAIL_CONFLICT"
    bus.nodes[2].fault = True
    bus.nodes[2].status_now = True
    bus.step(5)
    picker.host.ingest()
    assert [r.status for r in picker.rows() if r.address == 9] == ["fault"]
    assert not picker.ask(9) and not picker.ask(20)
    assert [n.key for n in picker.take_notices()][-2:] == ["NP_FAIL_FAULT", "NP_FAIL_NOT_ANNOUNCED"]
    assert picker.selected is None


def test_a_head_that_stops_answering_shows_as_lost():
    picker, bus = np_.sim_picker((4,))
    picker.scan()
    bus.nodes[0].enabled = False
    bus.step(p.MN_NODE_TIMEOUT_MS + 100)
    assert [r.status for r in picker.rows()] == ["lost"]
    assert not picker.ask(4)
    assert picker.take_notices()[-1].key == "NP_FAIL_GONE"


def test_the_switch_that_is_off_or_waiting_for_a_power_up_is_said():
    for config, key, level in (({"stored": 0, "running": 0}, "NP_SW_OFF", "info"), ({"stored": 1, "running": 0}, "NP_SW_PENDING_ON", "warning"),
                               ({"stored": 0, "running": 1}, "NP_SW_PENDING_OFF", "warning"), (None, "NP_SW_UNKNOWN", "info")):
        picker, _bus = np_.sim_picker((3,), config=config)
        picker.scan()
        notice = picker.take_notices()[0]
        assert (notice.key, notice.level) == (key, level)
    picker, _bus = np_.sim_picker((3,), config={"stored": 1, "running": 1})
    picker.scan()
    assert "NP_SW_ON" not in [n.key for n in picker.take_notices()]


def test_losing_the_selected_head_is_shown_and_the_heads_are_put_in_their_safe_state():
    picker, bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1})
    picker.scan()
    picker.ask(2)
    picker.confirm()
    picker.take_notices()
    bus.nodes[0].enabled = False
    for _ in range(p.MN_NODE_TIMEOUT_MS // 10 + 20):
        bus.step(10)
        picker.tick()
    notice = picker.take_notices()[-1]
    assert notice.key == "NP_LAPSE_RELEASED" and notice.level == "warning" and notice.params["node"] == 2
    assert "safe state" in picker.render(notice, "english") and "estado seguro" in picker.render(notice, "spanish")
    assert "stopped answering" in picker.render(notice, "english")
    assert bus.safe_state_calls.get(5) == 1 and picker.selected is None and not picker.may_send()


def test_the_release_can_be_switched_off_and_the_notice_says_the_outputs_were_left():
    picker, bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1}, release_on_lapse=False)
    assert picker.release_on_lapse is False
    picker.scan()
    picker.ask(2)
    picker.confirm()
    bus.nodes[0].fault = True
    bus.nodes[0].status_now = True
    for _ in range(30):
        bus.step(10)
        picker.tick()
    notice = [n for n in picker.take_notices() if n.key.startswith("NP_LAPSE")][-1]
    assert notice.key == "NP_LAPSE_KEPT" and notice.level == "error" and bus.safe_state_calls == {}
    picker.release_on_lapse = True
    assert picker.release_on_lapse and picker.snapshot()["release_on_lapse"] is True


def test_with_heads_on_the_bus_a_single_head_frame_goes_only_to_the_confirmed_head():
    picker, bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1})
    sent = []

    class Wire:
        def send_frame(self, can_id, data=b""):
            sent.append(can_id)
            bus.host_send(can_id, data)

        def other(self):
            return "underneath"

    wire = np_.GatedTransport(Wire(), picker)
    wire.send_frame(SINGLE_HEAD, b"")                    # not searched yet: passes (the heads ignore it by themselves)
    picker.scan()
    with pytest.raises(np_.NodeBlocked):
        wire.send_frame(SINGLE_HEAD, b"")
    with pytest.raises(transports.TransportError):
        wire.send_frame(p.CAN_ID_ENTER_BOOTLOADER, b"")
    wire.send_frame(*p.encode_mn_discover(p.MN_VERSION, 2))   # the frames of the extension are not single-head frames
    assert SINGLE_HEAD not in sent[1:] and p.CAN_ID_ENTER_BOOTLOADER not in sent
    picker.ask(2)
    picker.confirm()
    wire.send_frame(SINGLE_HEAD, b"")
    assert sent[-1] == SINGLE_HEAD and bus.nodes[0].obeyed and not bus.nodes[1].obeyed
    assert wire.other() == "underneath"


def test_entering_the_bootloader_of_the_selected_head_lets_its_bootloader_frames_through_and_is_not_a_lapse():
    picker, bus = np_.sim_picker((2, 5), config={"stored": 1, "running": 1})
    picker.scan()
    picker.ask(2)
    picker.confirm()
    sent = []

    class Wire:
        def send_frame(self, can_id, data=b""):
            sent.append(can_id)

    wire = np_.GatedTransport(Wire(), picker)
    wire.send_frame(p.CAN_ID_ENTER_BOOTLOADER, b"")
    bus.nodes[0].enabled = False                          # the head reset into its bootloader and stopped reporting
    for _ in range(p.MN_NODE_TIMEOUT_MS // 10 + 20):
        bus.step(10)
        picker.tick()
    wire.send_frame(0x7F1, b"")
    assert sent == [p.CAN_ID_ENTER_BOOTLOADER, 0x7F1]
    assert [n for n in picker.take_notices() if n.key.startswith("NP_LAPSE")] == [] and bus.safe_state_calls == {}
    with pytest.raises(np_.NodeBlocked):
        wire.send_frame(SINGLE_HEAD, b"")                 # anything else still needs a confirmed head
    picker.release()
    with pytest.raises(np_.NodeBlocked):
        wire.send_frame(0x7F1, b"")


class _Transport:
    """Hands out the frames a test gives it, one per read."""

    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.sent = []

    def send_frame(self, can_id, data=b""):
        self.sent.append((can_id, bytes(data)))

    def read_frame(self, timeout=0.05):
        return self.incoming.pop(0) if self.incoming else None


def test_the_transport_adapters_send_read_and_ask_the_head_for_its_switch():
    answer = p.encode_multinode_config_resp_response(1, 0, 0, 3)
    transport = _Transport([(0x120, b"\x01"), answer])
    assert np_.config_reader_for(transport, timeout_s=0.2)() == {"stored": 1, "running": 0, "instance": 0, "address": 3}
    assert transport.sent[0] == p.encode_multinode_config_resp_request()
    assert np_.config_reader_for(_Transport(), timeout_s=0.02)() is None
    sender = _Transport([(0x440 + 3, b"\x00\x00\x00\x01")])
    io = np_.transport_io(sender)
    io.advance(1)
    frames = io.poll()
    assert [(f[1], f[2]) for f in frames] == [(0x443, b"\x00\x00\x00\x01")] and io.poll() == []
    io.send(0x400, b"\x01\x02")
    assert sender.sent == [(0x400, b"\x01\x02")]


def test_a_failing_transport_becomes_a_notice_not_a_crash():
    class Broken:
        def send_frame(self, can_id, data=b""):
            raise transports.TransportError("adapter unplugged")

        def read_frame(self, timeout=0.05):
            return None

    picker = np_.NodePicker(mh.MultinodeHost(np_.transport_io(Broken())))
    picker.scan()
    notice = picker.take_notices()[-1]
    assert notice.key == "NP_MSG_SCAN_FAILED" and notice.level == "error" and picker.mode == np_.MODE_IDLE
    assert "adapter unplugged" in picker.render(notice, "german")


def test_the_web_studio_catalog_says_the_same_as_the_table():
    catalog = json.loads((ROOT / "spec" / "i18n" / "catalog" / "web-studio.json").read_text(encoding="utf-8"))
    entries = {entry["key"]: entry["text"] for entry in catalog["entries"] if entry["key"].startswith("nodes.")}
    assert len(entries) == len(strings.STRINGS["english"])
    for key, value in strings.STRINGS["english"].items():
        wanted = {language: re.sub(r"\{(\w+)\}", r"{{\1}}", strings.STRINGS[language][key]) for language in strings.LANGUAGES}
        assert entries["nodes." + key[3:].lower()] == wanted, key
