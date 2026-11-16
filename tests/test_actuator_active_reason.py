"""The reason byte 8 of 0x219: the master bridge refused the end of a slave update while an actuator was active."""

from __future__ import annotations

import json
import pathlib

from urtc_common import protocol

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_reason_is_in_the_generated_constants() -> None:
    assert protocol.SLAVE_VERIFY_FAIL_REASON_ACTUATOR_ACTIVE == 0x08
    assert protocol.ENUM_NAMES["slave_verify_fail_reason"][8] == "ACTUATOR_ACTIVE"
    assert "URTC_SLAVE_VERIFY_FAIL_REASON_ACTUATOR_ACTIVE 0x08u" in (ROOT / "generated" / "urtc_can_ids.h").read_text(encoding="utf-8")


def test_the_specification_names_the_reason_and_the_refusal() -> None:
    spec = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
    text = json.dumps(spec)
    assert "ACTUATOR_ACTIVE" in text
    assert "actuator" in text.lower()


def test_the_flasher_catalog_has_the_text_in_eight_languages() -> None:
    catalog = json.loads((ROOT / "spec" / "i18n" / "catalog" / "flasher.json").read_text(encoding="utf-8"))
    entries = catalog["entries"] if isinstance(catalog, dict) and "entries" in catalog else catalog
    rows = [e for e in entries if e.get("key") == "ERR_ACTUATOR_ACTIVE"]
    assert len(rows) == 1
    assert set(rows[0]["text"]) == {"english", "spanish", "german", "french", "italian", "japanese", "chinese", "portuguese"}
    assert all(v.strip() for v in rows[0]["text"].values())
