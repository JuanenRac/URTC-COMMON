"""The crash capture record: layout, checksum, refusals, readable causes, the read over six frames and the identifiers of the specification."""
import json
import zlib
from pathlib import Path

import pytest

from urtc_common import crash_dump as cd

ROOT = Path(__file__).resolve().parent.parent
# The bytes the C test of the firmware holds for the same capture (written by hand, here from the model): counter 1, PC 0x08002468, LR 0x08001235,
# xPSR 0x61000000, CFSR 0x8200, HFSR 0x40000000, MMFAR 0xDEADBEEF, BFAR 0x40021000, frame at 0x20009F00, reset cause 0, kind 1, version 1.
CAPTURE = bytes.fromhex("43525348010000006824000835120008000000610082000000000040efbeadde00100240009f0020000101002241ab97")
EMPTY = bytes.fromhex("4352534800000000000000000000000000000000000000000000000000000000000000000000000000000100a6683675")


def example() -> bytes:
    return cd.build(seq=1, pc=0x08002468, lr=0x08001235, xpsr=0x61000000, cfsr=0x8200, hfsr=0x40000000, mmfar=0xDEADBEEF, bfar=0x40021000,
                    sp=0x20009F00, reset_cause=0, kind=cd.KIND_FAULT)


def test_the_layout_is_the_one_the_firmware_test_holds():
    assert example() == CAPTURE
    assert cd.build() == EMPTY
    assert len(CAPTURE) == cd.RECORD_SIZE == cd.FRAME_COUNT * 8


def test_a_good_record_is_read_back_field_by_field():
    dump = cd.parse(CAPTURE)
    assert (dump.seq, dump.pc, dump.lr, dump.xpsr) == (1, 0x08002468, 0x08001235, 0x61000000)
    assert (dump.cfsr, dump.hfsr, dump.mmfar, dump.bfar, dump.sp) == (0x8200, 0x40000000, 0xDEADBEEF, 0x40021000, 0x20009F00)
    assert dump.crashed and dump.kind_name == "fault"
    assert dump.cfsr_names == ["precise_data_bus_error", "bfar_valid"]
    assert dump.hfsr_names == ["forced"]
    assert dump.fault_address == 0x40021000


def test_the_empty_record_says_no_crash():
    dump = cd.parse(EMPTY)
    assert not dump.crashed and dump.seq == 0 and dump.kind_name == "none" and dump.fault_address is None
    assert cd.summary(dump) == "no crash since power-up"


def test_the_reset_cause_is_named():
    dump = cd.parse(cd.build(kind=cd.KIND_FAULT, reset_cause=0x01 | 0x10))
    assert dump.reset_cause_names == ["independent_watchdog", "reset_pin"]
    assert "reset: independent_watchdog,reset_pin" in cd.summary(dump)


def test_the_address_comes_from_the_register_the_status_says_is_valid():
    assert cd.parse(cd.build(kind=1, cfsr=1 << 7, mmfar=0x11, bfar=0x22)).fault_address == 0x11
    assert cd.parse(cd.build(kind=1, cfsr=(1 << 7) | (1 << 15), mmfar=0x11, bfar=0x22)).fault_address == 0x22
    assert cd.parse(cd.build(kind=1, cfsr=1 << 17, mmfar=0x11, bfar=0x22)).fault_address is None


def test_a_crash_without_a_stack_says_it():
    dump = cd.parse(cd.build(seq=3, kind=cd.KIND_FAULT_NO_FRAME, cfsr=1 << 17, hfsr=1 << 30, sp=4))
    assert dump.kind_name == "fault_no_frame" and dump.cfsr_names == ["invalid_state"]
    assert "stack not readable" in cd.summary(dump)


@pytest.mark.parametrize("bit", range(cd.RECORD_SIZE * 8))
def test_no_single_flipped_bit_is_believed(bit):
    raw = bytearray(CAPTURE)
    raw[bit // 8] ^= 1 << (bit % 8)
    with pytest.raises(cd.CrashDumpError):
        cd.parse(bytes(raw))


@pytest.mark.parametrize("length", [0, 1, 47, 49, 96])
def test_a_record_of_another_size_is_refused(length):
    with pytest.raises(cd.CrashDumpError, match="48 bytes"):
        cd.parse(bytes(length))


def test_a_good_checksum_does_not_rescue_a_wrong_version_kind_or_reserved_byte():
    body = bytearray(CAPTURE[:-4])
    for index, value, text in ((42, 2, "version"), (41, 9, "kind"), (43, 1, "kind or reserved")):
        changed = bytearray(body)
        changed[index] = value
        sealed = bytes(changed) + zlib.crc32(bytes(changed)).to_bytes(4, "little")
        with pytest.raises(cd.CrashDumpError, match=text):
            cd.parse(sealed)


def test_the_request_is_one_byte_and_only_operation_zero_exists():
    assert cd.query_request() == b"\x00"
    with pytest.raises(cd.CrashDumpError):
        cd.query_request(1)


def test_the_six_frames_make_the_record():
    frames = [CAPTURE[i:i + 8] for i in range(0, 48, 8)]
    assert cd.join_frames(frames) == CAPTURE
    assert cd.download(lambda: frames).pc == 0x08002468
    with pytest.raises(cd.CrashDumpError):
        cd.join_frames(frames[:5])
    with pytest.raises(cd.CrashDumpError, match="missing or incomplete"):
        cd.download(lambda: None)
    with pytest.raises(cd.CrashDumpError, match="missing or incomplete"):
        cd.download(lambda: frames[:5])
    with pytest.raises(cd.CrashDumpError, match="missing or incomplete"):
        cd.download(lambda: frames[:5] + [b"short"])


def test_the_json_names_the_causes_and_keeps_the_registers_in_hexadecimal():
    doc = json.loads(cd.to_json(cd.parse(CAPTURE), "2000-01-01T00:00:00Z"))
    assert doc["format"] == "urtc-crashdump/1" and doc["crashed"] is True and doc["crash_count"] == 1
    assert doc["registers"]["pc"] == "0x08002468" and doc["registers"]["bfar"] == "0x40021000"
    assert doc["fault_address"] == "0x40021000" and doc["causes"] == ["precise_data_bus_error", "bfar_valid", "forced"]
    assert doc["captured_at"] == "2000-01-01T00:00:00Z"
    assert json.loads(cd.to_json(cd.parse(EMPTY)))["fault_address"] is None


def test_the_identifiers_and_the_frame_layout_match_the_specification():
    spec = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
    messages = {int(m["id"], 16): m for m in spec["messages"]}
    assert cd.CAN_ID_QUERY == 0x1BC and cd.CAN_ID_RESPONSE == 0x1BD
    assert messages[cd.CAN_ID_QUERY]["name"] == "CRASH_DUMP_QUERY" and messages[cd.CAN_ID_RESPONSE]["name"] == "CRASH_DUMP_RESP"
    assert messages[cd.CAN_ID_RESPONSE]["layouts"][0]["frames"] == cd.FRAME_COUNT
    assert messages[cd.CAN_ID_RESPONSE]["answers"] == "0x1BC"
