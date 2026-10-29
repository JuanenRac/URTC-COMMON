# =============================================================================
# URTC-COMMON - tests/test_evidence.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""``urtc-evidence/1``: the shape, the digest, every refusal, and the three records of the programs turned into it."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from urtc_common import evidence

ROOT = Path(__file__).resolve().parents[1]
SHA = "ab" * 32


def sample(**changes):
    values = dict(kind="flash", outcome="pass", timestamp_utc="2026-01-02T03:04:05Z", tool="URTC Flasher", tool_version="0.4.1", operator="someone",
                  subject={"name": "main", "hardware_id": "0x0000A001", "version_before": "0.3.9", "version_after": "0.4.1"},
                  transport={"adapter": "slcan", "bus": "can0", "bitrate": 500000}, artifacts=[{"name": "image.bin", "sha256": SHA, "bytes": 1024}], detail="done")
    values.update(changes)
    return evidence.build(**values)


def test_a_built_record_is_well_formed_and_carries_its_digest():
    record = sample()
    assert evidence.verify(record) == []
    assert record["format"] == "urtc-evidence/1" and record["evidence_sha256"] == evidence.digest(record)


def test_the_digest_does_not_depend_on_the_order_of_the_keys_and_json_round_trips():
    record = sample()
    shuffled = dict(reversed(list(record.items())))
    assert evidence.digest(shuffled) == record["evidence_sha256"]
    assert evidence.verify(json.loads(json.dumps(record, indent=2))) == []


@pytest.mark.parametrize("edit", [
    lambda r: r.update(outcome="fail"), lambda r: r["subject"].update(version_after="9.9.9"), lambda r: r["artifacts"][0].update(bytes=1),
    lambda r: r.update(detail="other"), lambda r: r["transport"].update(bitrate=125000),
])
def test_any_edit_after_writing_is_noticed(edit):
    record = copy.deepcopy(sample())
    edit(record)
    assert any("does not match" in problem for problem in evidence.verify(record))


@pytest.mark.parametrize("edit,fragment", [
    (lambda r: r.update(format="urtc-evidence/2"), "format"),
    (lambda r: r.update(extra=1), "extra"),
    (lambda r: r.update(kind="boot"), "kind"),
    (lambda r: r.update(outcome="ok"), "outcome"),
    (lambda r: r.update(timestamp_utc="yesterday"), "timestamp_utc"),
    (lambda r: r.update(tool=" "), "tool"),
    (lambda r: r.update(operator=3), "operator"),
    (lambda r: r.update(evidence_sha256="XYZ"), "evidence_sha256"),
    (lambda r: r["subject"].update(hardware_id="0xa001"), "subject.hardware_id"),
    (lambda r: r["subject"].update(color="red"), "subject.color"),
    (lambda r: r["subject"].update(version_after="v1"), "subject.version_after"),
    (lambda r: r["transport"].update(bitrate=True), "transport.bitrate"),
    (lambda r: r["transport"].update(bitrate=0), "transport.bitrate"),
    (lambda r: r["artifacts"][0].update(sha256="ABC"), "artifacts[0].sha256"),
    (lambda r: r["artifacts"][0].update(bytes=-1), "artifacts[0].bytes"),
    (lambda r: r["artifacts"].append({"name": "x"}), "needs a name and a sha256"),
    (lambda r: r.update(artifacts=[]), "artifacts"),
    (lambda r: r.update(subject={}), "subject"),
    (lambda r: r.update(detail="x" * 501), "detail"),
])
def test_a_malformed_record_is_refused_with_the_reason(edit, fragment):
    record = copy.deepcopy(sample())
    edit(record)
    problems = evidence.verify(record)
    assert problems and any(fragment in problem for problem in problems), problems


def test_a_record_that_is_not_an_object_is_refused():
    for value in (None, [], "text", 3):
        assert evidence.verify(value)


def test_build_refuses_what_verify_would_and_names_everything():
    with pytest.raises(ValueError) as caught:
        evidence.build(kind="nope", outcome="nope", timestamp_utc="x", tool="", tool_version="1.0")
    assert "kind" in str(caught.value) and "outcome" in str(caught.value) and "tool" in str(caught.value)


def test_empty_parts_are_left_out_and_a_long_detail_is_cut():
    record = evidence.build(kind="test", outcome="skipped", timestamp_utc="2026-01-02T03:04:05+01:00", tool="t", tool_version="1.0",
                            subject={"name": "x", "key_id": ""}, detail="y" * 900)
    assert record["subject"] == {"name": "x"} and len(record["detail"]) == 500 and "transport" not in record and "operator" not in record


def test_update_report_of_the_flasher_becomes_a_flash_record():
    report = {"tool": "URTC Flasher", "tool_version": "0.4.1", "timestamp_utc": "2026-01-02T03:04:05Z", "operator": "me", "target": "main", "hardware_id": "0x0000A001",
              "image": {"file": "URTC_MAIN_FIRMWARE_v0.4.1.bin", "size": 2048, "sha256": SHA, "signing_key_kind": "release"}, "version_before": "0.3.9", "version_after": "0.4.1",
              "result": "success", "report_sha256": SHA}
    record = evidence.from_update_report(report)
    assert evidence.verify(record) == [] and record["kind"] == "flash" and record["outcome"] == "pass"
    assert record["subject"]["version_before"] == "0.3.9" and record["artifacts"] == [{"name": "URTC_MAIN_FIRMWARE_v0.4.1.bin", "sha256": SHA, "bytes": 2048}]
    assert evidence.from_update_report({**report, "result": "failed"})["outcome"] == "fail"
    assert evidence.from_update_report({**report, "result": "weird"})["outcome"] == "error"
    no_ids = {**report, "hardware_id": None, "version_before": None, "operator": ""}
    assert "hardware_id" not in evidence.from_update_report(no_ids)["subject"]


def test_result_record_of_the_tester_becomes_a_test_record():
    result = {"test_name": "thermal", "outcome": "pass", "adapter": "slcan", "firmware_version": "0.4.1", "bus": "can0", "bitrate": 500000, "log_file": "a.log", "log_sha256": SHA, "detail": ""}
    record = evidence.from_result_record(result, tool_version="0.4.2", timestamp_utc="2026-01-02T03:04:05Z")
    assert evidence.verify(record) == [] and record["kind"] == "test" and record["transport"]["bitrate"] == 500000
    assert record["artifacts"] == [{"name": "a.log", "sha256": SHA}]
    with pytest.raises(ValueError):
        evidence.from_result_record({**result, "outcome": "maybe"}, tool_version="0.4.2", timestamp_utc="2026-01-02T03:04:05Z")


def test_line_of_the_updater_becomes_an_install_record():
    line = {"timestamp": "2026-01-02T03:04:05+00:00", "updaterVersion": "0.1.8", "user": "me", "project": "URTC-FLASHER", "ok": True, "versionBefore": "0.4.0",
            "versionAfter": "0.4.1", "commitBefore": "a" * 40, "commitAfter": "b" * 40, "message": "updated"}
    record = evidence.from_updater_line(line)
    assert evidence.verify(record) == [] and record["timestamp_utc"].endswith("Z") and record["outcome"] == "pass"
    failed = evidence.from_updater_line({**line, "ok": False, "versionAfter": None, "commitAfter": None})
    assert failed["outcome"] == "fail" and "version_after" not in failed["subject"]


def test_the_documented_fields_are_the_fields_of_the_code():
    schema = json.loads((ROOT / "spec" / "evidence.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["format"]["const"] == evidence.FORMAT
    assert tuple(schema["properties"]) == evidence.FIELDS
    assert tuple(schema["properties"]["kind"]["enum"]) == evidence.KINDS and tuple(schema["properties"]["outcome"]["enum"]) == evidence.OUTCOMES
    assert tuple(schema["properties"]["subject"]["properties"]) == evidence.SUBJECT_FIELDS
    assert tuple(schema["properties"]["transport"]["properties"]) == evidence.TRANSPORT_FIELDS
    assert tuple(schema["properties"]["artifacts"]["items"]["properties"]) == evidence.ARTIFACT_FIELDS
    assert set(schema["required"]) == {"format", "kind", "outcome", "timestamp_utc", "tool", "tool_version", "evidence_sha256"}
