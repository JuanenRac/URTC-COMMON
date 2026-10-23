# =============================================================================
# URTC-COMMON - tests/test_release_artifacts.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The wheel, the source archive and the C header of a release: reproducible, signed, verified and usable once installed apart."""
from __future__ import annotations

import io
import json
import re
import tarfile
import zipfile
from pathlib import Path

import pytest

import make_release_artifacts as mra
from urtc_common import specdata

SEED = bytes(range(32))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("release")
    mra.build_all(out, SEED)
    return out


def public_hex() -> str:
    return mra.mup.public_key_of(SEED).hex()


def test_two_builds_give_the_same_bytes():
    assert mra.reproduce().startswith("REPRODUCIBLE=PASS")


def test_the_three_files_are_there_with_a_hash_and_a_signature(built):
    version = mra.project()["version"]
    for name in mra.names(version).values():
        assert (built / name).is_file() and (built / (name + ".sha256")).is_file() and (built / (name + ".sig")).is_file()
    assert (built / "urtc_can_ids.h").read_bytes() == (mra.ROOT / "generated" / "urtc_can_ids.h").read_bytes()


def test_a_good_set_verifies_with_the_key_that_signed_it_and_not_with_the_key_of_the_programs(built):
    lines = mra.verify_all(built, public_hex())
    assert len(lines) == 3 and all(line.startswith("VERIFY=PASS") for line in lines)
    with pytest.raises(mra.ReleaseError, match="signature"):
        mra.verify_all(built)                                         # the pinned key of the releases did not sign this test set


def test_an_altered_file_is_refused(built, tmp_path):
    version = mra.project()["version"]
    for kind in ("wheel", "sdist", "header"):
        copy = tmp_path / kind
        copy.mkdir()
        for path in built.iterdir():
            (copy / path.name).write_bytes(path.read_bytes())
        target = copy / mra.names(version)[kind]
        data = bytearray(target.read_bytes())
        data[len(data) // 2] ^= 0x01
        target.write_bytes(bytes(data))
        with pytest.raises(mra.ReleaseError, match="does not match its .sha256"):
            mra.verify_all(copy, public_hex())
        # even with the hash file rewritten to match, the signature is the check
        sha = mra.sha256_of(bytes(data))
        (copy / (target.name + ".sha256")).write_text(f"{sha}  {target.name}\n", encoding="ascii")
        with pytest.raises(mra.ReleaseError, match="signature|RECORD|zip|BadZip"):
            mra.verify_all(copy, public_hex())


def test_a_missing_signature_or_file_is_refused(built, tmp_path):
    for path in built.iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "urtc_can_ids.h.sig").unlink()
    with pytest.raises(mra.ReleaseError, match="no readable .sig"):
        mra.verify_all(tmp_path, public_hex())
    (tmp_path / "urtc_can_ids.h").unlink()
    with pytest.raises(mra.ReleaseError, match="missing"):
        mra.verify_all(tmp_path, public_hex())


def test_a_wheel_with_an_entry_the_record_does_not_list_is_refused(built):
    version = mra.project()["version"]
    data = (built / mra.names(version)["wheel"]).read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item))
        target.writestr("urtc_common/extra.py", b"print('x')\n")
    with pytest.raises(mra.ReleaseError, match="not in its RECORD"):
        mra.verify_wheel(out.getvalue(), version)
    with pytest.raises(mra.ReleaseError, match="no RECORD for this version"):
        mra.verify_wheel(data, "9.9.9")


def test_the_wheel_carries_the_package_and_the_specification_files(built):
    version = mra.project()["version"]
    with zipfile.ZipFile(built / mra.names(version)["wheel"]) as wheel:
        listed = set(wheel.namelist())
        assert {"urtc_common/protocol.py", "urtc_common/specdata.py", "urtc_ui/languages.py", "urtc_common/data/can_protocol.json",
                "urtc_common/data/urtc_can_ids.h", "urtc_common/data/can_vectors.json", "urtc_common/data/tools.json"} <= listed
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in listed)
        assert all(info.date_time == mra.FIXED_TIME for info in wheel.infolist())
        meta = wheel.read(f"urtc_common-{version}.dist-info/METADATA").decode("utf-8")
        assert f"Version: {version}" in meta and "Requires-Python: >=3.10" in meta and 'Requires-Dist: pyserial>=3.5; extra == "serial"' in meta
        assert "urtc-common = urtc_common.cli:main" in wheel.read(f"urtc_common-{version}.dist-info/entry_points.txt").decode("utf-8")
        assert json.loads(wheel.read("urtc_common/data/can_protocol.json")) == json.loads((mra.ROOT / "spec" / "can_protocol.json").read_text(encoding="utf-8"))


def test_the_source_archive_has_one_folder_and_no_stray_file(built):
    version = mra.project()["version"]
    with tarfile.open(built / mra.names(version)["sdist"]) as archive:
        members = archive.getmembers()
    assert all(m.name.startswith(f"urtc_common-{version}/") and m.mtime == 0 and m.uid == 0 for m in members)
    inside = {m.name.split("/", 1)[1] for m in members}
    assert {"pyproject.toml", "spec/can_protocol.json", "generated/urtc_can_ids.h", "src/urtc_common/cli.py"} <= inside
    assert not any(re.search(r"(^|/)(\.venv|__pycache__|node_modules)(/|$)", name) for name in inside)


def test_the_wheel_runs_apart_from_the_checkout(built):
    version = mra.project()["version"]
    assert mra.smoke(built / mra.names(version)["wheel"]).startswith("SMOKE=PASS CONFORMANCE=PASS")


def test_the_data_files_are_found_in_the_checkout_and_in_an_installed_copy():
    for kind in specdata.FILES:
        assert specdata.path(kind).is_file()
    assert specdata.load_spec()["protocol_version"] >= 1


def test_the_command_line(tmp_path, capsys):
    assert mra.main(["build", "--out", str(tmp_path), "--no-sign"]) == 0
    assert mra.main(["verify", str(tmp_path)]) == 1                   # without signatures nothing verifies
    assert "RELEASE_FILES=FAIL" in capsys.readouterr().err
    assert mra.main(["smoke", str(tmp_path)]) == 0
    assert mra.main(["verify", str(tmp_path / "missing")]) == 1
