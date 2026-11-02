# =============================================================================
# URTC-COMMON - tests/test_bootloader_auth.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""[FIRMWARE] sin compilar placa ni flashear. Ed25519, the decision to install an image and the addressing by serial: the Python references, the shared vectors and
the portable C held to the same cases. Every key made here is a throwaway: generated at random for the test, never stored."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import i18n_generate as gen  # noqa: E402
import make_bootloader_auth_vectors as maker  # noqa: E402
from urtc_common import bl_select as bs  # noqa: E402
from urtc_common import ed25519, image_auth as ia  # noqa: E402

RFC1 = ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", b"",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


def load(name: str) -> dict:
    return json.loads((ROOT / "conformance" / name).read_text(encoding="utf-8"))


# --- Ed25519 ----------------------------------------------------------------------------------------------------------------------------------
def test_the_reference_matches_rfc_8032():
    seed, pk, msg, sig = RFC1
    assert ed25519.public_key(bytes.fromhex(seed)).hex() == pk
    assert ed25519.sign(bytes.fromhex(seed), msg).hex() == sig
    assert ed25519.verify(bytes.fromhex(pk), msg, bytes.fromhex(sig))


def test_every_shared_ed25519_case_gets_its_verdict():
    cases = load("ed25519_vectors.json")["cases"]
    assert len(cases) >= 20
    assert {c["source"] for c in cases} == {"rfc8032", "own"}
    for c in cases:
        assert ed25519.verify(bytes.fromhex(c["public_key"]), bytes.fromhex(c["message"]), bytes.fromhex(c["signature"])) == c["valid"], c["name"]
    assert any(not c["valid"] for c in cases) and any(c["valid"] for c in cases)


def test_a_fresh_random_key_signs_and_every_change_breaks_it():
    rng = random.Random(os.urandom(16))   # an ephemeral key for this run only
    seed = bytes(rng.randrange(256) for _ in range(32))
    pk = ed25519.public_key(seed)
    msg = bytes(rng.randrange(256) for _ in range(77))
    sig = ed25519.sign(seed, msg)
    assert ed25519.verify(pk, msg, sig)
    for index in range(0, 64, 9):
        broken = bytearray(sig)
        broken[index] ^= 0x10
        assert not ed25519.verify(pk, msg, bytes(broken))
    assert not ed25519.verify(pk, msg + b"!", sig)
    assert not ed25519.verify(ed25519.public_key(bytes(32)), msg, sig)
    assert not ed25519.verify(pk[:31], msg, sig) and not ed25519.verify(pk, msg, sig[:63])
    with pytest.raises(ValueError):
        ed25519.public_key(b"short")


# --- the decision to install an image ---------------------------------------------------------------------------------------------------------
def test_every_shared_install_case_gets_its_status():
    data = load("signed_image_vectors.json")
    keys = [bytes.fromhex(k) for k in data["public_keys"]]
    assert keys == maker.signed_image_keys()
    assert data["statuses"] == list(ia.STATUS_NAMES)
    seen = set()
    for c in data["cases"]:
        version = tuple(c["installed_version"]) if c["installed_version"] else None
        status, counter = ia.decide(c["policy"], [keys[i] for i in c["trusted"]], c["hardware_id"], c["installed_counter"], version, c["downgrade_authorized"],
                                    bytes.fromhex(c["header"]), bytes.fromhex(c["payload_sha256"]), bytes.fromhex(c["record"]) if c["record"] else None, c["hmac_ok"])
        assert (ia.STATUS_NAMES[status], counter) == (c["status"], c["new_counter"]), c["name"]
        seen.add(c["status"])
    assert seen == set(ia.STATUS_NAMES) - {"bad_args"}


def test_the_conservative_default_is_the_strict_policy():
    assert ia.POLICY_ED25519_ONLY == 0
    header = bytes(28)
    assert ia.decide(0, [], 0, 0, None, False, header, bytes(32), None, True)[0] == ia.NOT_SIGNED   # a good HMAC alone does not install an image


def test_the_record_layout_and_the_key_id():
    seed = hashlib.sha256(b"throwaway").digest()
    header, digest = bytes(range(28)), bytes(range(32))
    record = ia.make_record(seed, header, digest, 9)
    assert len(record) == ia.RECORD_SIZE == 76 and len(ia.message(header, digest, 9, record[:8])) == ia.MESSAGE_SIZE == 88
    assert record[:8] == ia.key_id(ed25519.public_key(seed)) == hashlib.sha512(ed25519.public_key(seed)).digest()[:8]
    assert record[8:12] == (9).to_bytes(4, "big")
    assert ia.decide(0, [ed25519.public_key(seed)], ia.header_hardware_id(header), 9, None, False, header, digest, record, False) == (ia.OK, 9)
    for bad in (b"", header[:-1]):
        assert ia.decide(0, [], 0, 0, None, False, bad, digest, None, False)[0] == ia.BAD_ARGS
    assert ia.decide(7, [], 0, 0, None, False, header, digest, None, False)[0] == ia.BAD_ARGS
    with pytest.raises(ValueError):
        ia.message(header, digest[:-1], 0, record[:8])


# --- addressing by serial ---------------------------------------------------------------------------------------------------------------------
def test_every_shared_scenario_replays_on_the_reference():
    scenarios = load("bootloader_select_vectors.json")["scenarios"]
    assert len(scenarios) >= 17
    assert {sc["serial_source"] for sc in scenarios} == {"uid", "programmed"}
    for sc in scenarios:
        record = tuple(int(w, 16) for w in sc["record"]) if sc["record"] else None
        node = bs.BootloaderNode(tuple(int(w, 16) for w in sc["uid"]), record)
        assert node.serial == int(sc["serial"], 16) and node.serial_source == sc["serial_source"]
        for step in sc["steps"]:
            if step["kind"] == "cmd":
                reply = node.on_cmd(step["t"], bytes.fromhex(step["data"]), step["busy"])
                assert (reply[1].hex().upper() if reply else "") == step["reply"], sc["name"]
            else:
                assert node.accepts(step["t"], step["id"], step["busy"]) == step["accept"], sc["name"]
            assert (node.selected, node.addressed) == (step["selected"], step["addressed"]), sc["name"]


def test_the_serial_folds_the_unique_id_like_the_application():
    assert bs.serial_from_uid(1, 0, 0) == 1 and bs.serial_from_uid(0, 1, 0) == 1 << 11 and bs.serial_from_uid(0, 0, 1) == 1 << 22
    assert bs.serial_from_uid(0, 0x80000000, 0) == 1 << 10   # the rotation wraps around
    assert not bs.serial_is_valid(0) and not bs.serial_is_valid(0xFFFFFFFF) and bs.serial_is_valid(1)


def probe_bus(nodes: list[bs.BootloaderNode]):
    log: list[tuple[int, int]] = []

    def probe(nbits: int, prefix: int) -> bool:
        log.append((nbits, prefix))
        replies = {r[1] for n in nodes if (r := n.on_cmd(0, bs.probe_frame(nbits, prefix)))}
        assert len(replies) <= 1, "every answer to a probe is the same frame, so several answers never differ"
        return bool(replies)

    return probe, log


def test_enumeration_finds_every_head_with_a_bounded_number_of_probes():
    rng = random.Random(7)
    for count in (0, 1, 2, 3, 6):
        nodes = [bs.BootloaderNode((rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32))) for _ in range(count)]
        probe, log = probe_bus(nodes)
        found = bs.enumerate_serials(probe)
        assert found == sorted(n.serial for n in nodes)
        assert len(log) <= 1 + 64 * max(count, 1)


def test_an_old_bus_answers_nothing_and_a_duplicate_serial_shows_in_the_unique_id():
    probe, log = probe_bus([])
    assert bs.enumerate_serials(probe) == [] and log == [(0, 0)]   # no head announces a serial: keep the single-head behaviour
    twin_a, twin_b = bs.BootloaderNode((1, 2, 3)), bs.BootloaderNode((1, 2, 3))
    other = bs.BootloaderNode((4, 5, 6))
    assert twin_a.serial == twin_b.serial != other.serial
    assert bs.enumerate_serials(probe_bus([twin_a, twin_b, other])[0]) == sorted({twin_a.serial, other.serial})   # two heads, one serial
    twin_c = bs.BootloaderNode((9, 8, 7))
    assert bs.serial_from_uid(*twin_c.uid) != twin_a.serial
    # the unique ID tells two heads with one serial apart: the host selects, reads the three words and sees them differ
    collide = bs.BootloaderNode((0x10, 0x20, 0x30))
    clash = bs.BootloaderNode((0x10 ^ 0x800, 0x20 ^ 1, 0x30))   # 0x800 and rotl(1, 11) cancel: same serial, other unique ID
    assert clash.serial == collide.serial and clash.uid != collide.uid
    for node in (collide, clash):
        node.on_cmd(0, bs.select_frame(collide.serial, 1))
    words = [[bytes(r[1]) for n in (collide, clash) if (r := n.on_cmd(5, bs.uid_frame(part)))] for part in range(3)]
    assert any(a != b for a, b in (pair for pair in words if len(pair) == 2)), "the host sees two different unique IDs and refuses"


def test_the_block_is_written_in_the_specification_with_the_formats_of_the_design():
    spec = json.loads((ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))
    messages = {m["id"]: m for m in spec["messages"]}
    assert [f"0x{i:03X}" for i in bs.BLOCK_IDS] == ["0x7EA", "0x7EB", "0x7EC", "0x7ED"] and all(f"0x{i:03X}" in messages for i in bs.BLOCK_IDS)
    assert [lay["variant"] for lay in messages["0x7EA"]["layouts"]] == ["probe", "select", "release", "uid"]
    assert [lay["dlc"] for lay in messages["0x7EA"]["layouts"]] == [{"exact": 6}, {"exact": 6}, {"exact": 1}, {"exact": 2}]
    assert messages["0x7EC"]["layouts"][0]["dlc"] == {"exact": 8} and messages["0x7ED"]["layouts"][0]["dlc"] == {"exact": 8}
    # the classic CAN frame carries at most 8 data bytes: nothing of the block, and not 0x7FA, may be longer, and 0x7FA is exactly the three bytes of the version
    for message in messages.values():
        for layout in message["layouts"]:
            assert layout["dlc"].get("exact", layout["dlc"].get("max", 0)) <= 8
    assert messages["0x7FA"]["layouts"][0]["dlc"] == {"exact": 3}
    assert [f["name"] for f in messages["0x7FA"]["layouts"][0]["fields"]] == ["major", "minor", "patch"]
    assert "0x7ED" in [a["id"] for a in spec["procedures"]["version_query"]["answers"]]
    header = (ROOT / "generated" / "urtc_can_ids.h").read_text(encoding="utf-8")
    used = {int(m, 16) for m in re.findall(r"#define URTC_CAN_ID_\w+ 0x([0-9A-Fa-f]+)u", header)}
    assert set(bs.BLOCK_IDS) <= used and max(used) == 0x7FF


def test_the_policy_by_default_is_the_strict_one():
    assert ia.POLICY_DEFAULT == ia.POLICY_ED25519_ONLY == 0 and ia.POLICY_NAMES[ia.POLICY_DEFAULT] == "ed25519_only"
    text = (ROOT / "firmware_base" / "urtc_auth.h").read_text(encoding="utf-8")
    assert "#define URTC_AUTH_DEFAULT_POLICY URTC_AUTH_ED25519_ONLY" in text
    assert "ed25519_only" in (ROOT / "docs" / "BOOTLOADER_AUTH.md").read_text(encoding="utf-8")


def test_the_programmable_serial_has_priority_and_an_unusable_record_gives_the_fold_back():
    uid = (0x11111111, 0x22222222, 0x33333333)
    fold = bs.serial_from_uid(*uid)
    assert bs.serial_record(0x00C0FFEE) == (bs.SERIAL_RECORD_MAGIC, 0x00C0FFEE, 0xFF3F0011) and bs.SERIAL_RECORD_MAGIC == int.from_bytes(b"URS1", "big")
    node = bs.BootloaderNode(uid, bs.serial_record(0x00C0FFEE))
    assert (node.serial, node.serial_source) == (0x00C0FFEE, "programmed") and node.uid == uid   # the unique ID is still the real one
    for record in (None, (0xFFFFFFFF,) * 3, (0, 0, 0), (bs.SERIAL_RECORD_MAGIC, 7, 7), (1, 7, ~7 & 0xFFFFFFFF), bs.serial_record(0), bs.serial_record(0xFFFFFFFF)):
        assert bs.serial_from_record(record) is None
        plain = bs.BootloaderNode(uid, record)
        assert (plain.serial, plain.serial_source) == (fold, "uid")
    assert bs.serial_from_record(bs.serial_record(1)) == 1


def test_every_shared_bus_scenario_replays_on_the_reference():
    buses = load("bootloader_select_vectors.json")["bus_scenarios"]
    assert len(buses) >= 8 and {b["duplicate"] for b in buses} == {False, True}
    for b in buses:
        nodes = [bs.BootloaderNode(tuple(int(w, 16) for w in n["uid"]), tuple(int(w, 16) for w in n["record"]) if n["record"] else None) for n in b["nodes"]]
        probe, _ = probe_bus(nodes)
        assert bs.enumerate_serials(probe) == [int(x, 16) for x in b["enumerated"]], b["name"]
        if b["select"] is None:
            assert not b["duplicate"]
            continue
        serial = int(b["select"], 16)
        answered = bool([r for n in nodes if (r := n.on_cmd(1, bs.select_frame(serial, 1)))])
        words = [sorted({r[1] for n in nodes if (r := n.on_cmd(2, bs.uid_frame(part)))}) for part in range(3)]
        assert bs.duplicate_suspected(answered, words) == b["duplicate"], b["name"]


def test_the_host_detects_a_duplicate_from_different_words_or_from_silence():
    same = [[b"\x00\x00"], [b"\x01\x00"], [b"\x02\x00"]]
    assert not bs.duplicate_suspected(True, same)
    assert bs.duplicate_suspected(True, [[b"a", b"b"], [b"c"], [b"d"]])          # two different words under one identifier
    assert bs.duplicate_suspected(True, [[b"a"], [], [b"d"]])                    # the bus destroyed the clashing frames
    assert not bs.duplicate_suspected(False, [[], [], []])                       # nothing was selected: no head announces a serial


# --- the files --------------------------------------------------------------------------------------------------------------------------------
def test_the_vector_files_are_up_to_date():
    assert maker.main(["--check"]) == 0


def test_the_catalog_of_texts_is_complete_in_eight_languages():
    catalog = gen.load_catalog("bootloader-auth")
    assert gen.validate(catalog) == []
    keys = {e["key"] for e in catalog["entries"]}
    for name in ia.STATUS_NAMES[1:]:
        assert f"AUTH_STATUS_{name.upper()}" in keys
    for name in ia.POLICY_NAMES:
        assert f"AUTH_POLICY_{name.upper()}" in keys
    assert (gen.CATALOGS / "bootloader-auth.json").read_bytes().replace(b"\r\n", b"\n").decode("utf-8") == gen.dump_catalog(catalog)
    portuguese = " ".join(e["text"]["portuguese"] for e in catalog["entries"] if "text" in e)
    assert "arquivo" not in portuguese and "você" not in portuguese and "usuário" not in portuguese   # Portugal, not Brazil


def test_the_c_code_passes_the_same_vectors(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no host C compiler")
    binary = tmp_path / ("bootloader_auth.exe" if os.name == "nt" else "bootloader_auth")
    base = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", f"-I{ROOT / 'firmware_base'}", f"-I{ROOT / 'generated'}",
            str(ROOT / "tests" / "c" / "test_bootloader_auth.c"), str(ROOT / "firmware_base" / "urtc_ed25519.c"), "-o", str(binary)]
    attempt = subprocess.run(base + ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"], capture_output=True, text=True)
    if attempt.returncode != 0:
        build = subprocess.run(base, capture_output=True, text=True)   # a compiler with no sanitizer runtime
        assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all bootloader authentication tests pass" in run.stdout


def test_the_copy_sets_exist():
    import vendor_copy

    assert vendor_copy.SETS["firmware_bootloader_auth"] == ["firmware_base/urtc_ed25519.h", "firmware_base/urtc_ed25519.c", "firmware_base/urtc_auth.h",
                                                            "firmware_base/urtc_bl_select.h"]
    assert vendor_copy.SETS["bootloader_auth_c"] == ["generated/ed25519_vectors.h", "generated/signed_image_vectors.h", "generated/bootloader_select_vectors.h"]
    assert vendor_copy.SETS["bootloader_auth_test"] == ["tests/c/test_bootloader_auth.c"]
    assert vendor_copy.SETS["bootloader_auth"] == ["src/urtc_common/ed25519.py", "src/urtc_common/image_auth.py", "src/urtc_common/bl_select.py",
                                                   "conformance/ed25519_vectors.json", "conformance/signed_image_vectors.json", "conformance/bootloader_select_vectors.json"]
