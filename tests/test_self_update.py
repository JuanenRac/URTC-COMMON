# =============================================================================
# URTC-COMMON - tests/test_self_update.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Update of an application from a signed package: version rules, hosts, download, verification, extraction, install, rollback."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile

import pytest

from urtc_common import self_update as su

# ---- a signer, only for the tests (RFC 8032) -------------------------------------------------------------------
_P, _Q = su._P, su._Q


def _clamp_secret(seed: bytes):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _compress(point) -> bytes:
    x, y, z, _ = point
    zi = pow(z, _P - 2, _P)
    x, y = x * zi % _P, y * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def public_key(seed: bytes) -> bytes:
    a, _ = _clamp_secret(seed)
    return _compress(su._mul(a, su.BASE_POINT))


def sign(seed: bytes, message: bytes) -> bytes:
    a, prefix = _clamp_secret(seed)
    public = _compress(su._mul(a, su.BASE_POINT))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _Q
    r_bytes = _compress(su._mul(r, su.BASE_POINT))
    k = int.from_bytes(hashlib.sha512(r_bytes + public + message).digest(), "little") % _Q
    return r_bytes + ((r + k * a) % _Q).to_bytes(32, "little")


SEED = bytes(range(32))
PUBLIC = public_key(SEED)
KEY_ID = hashlib.sha256(PUBLIC).hexdigest()[:16]


def test_the_verifier_agrees_with_the_published_test_vector_of_rfc_8032():
    public = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    signature = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert su.ed25519_verify(public, b"", signature)
    assert not su.ed25519_verify(public, b"x", signature)
    assert public_key(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")) == public
    assert sign(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"), b"") == signature


def test_the_verifier_refuses_malformed_input():
    good = sign(SEED, b"m")
    assert su.ed25519_verify(PUBLIC, b"m", good)
    assert not su.ed25519_verify(PUBLIC[:31], b"m", good)
    assert not su.ed25519_verify(PUBLIC, b"m", good[:63])
    assert not su.ed25519_verify(PUBLIC, b"m", good[:32] + bytes(32))
    flipped = bytearray(good)
    flipped[0] ^= 1
    assert not su.ed25519_verify(PUBLIC, b"m", bytes(flipped))


# ---- versions and platforms ------------------------------------------------------------------------------------
def test_versions_have_three_or_four_components_and_only_a_higher_one_is_an_update():
    assert su.parse_version("0.8.0.1") == (0, 8, 0, 1)
    assert su.parse_version("v0.4.1") == (0, 4, 1, 0)
    assert su.is_newer("0.7.9", "0.8.0.0")
    assert su.is_newer("0.8.0.9", "0.8.1.0")
    assert not su.is_newer("0.4.1", "0.4.1")
    assert not su.is_newer("0.4.1", "0.4.0")
    assert not su.is_newer("0.8.0.0", "0.7.9")
    for bad in ("", "1", "1.2", "1.2.3.4.5", "a.b.c", "1.2.3-rc1"):
        with pytest.raises(su.UpdateError) as caught:
            su.parse_version(bad)
        assert caught.value.code == "bad_version"


def test_the_platform_tag():
    assert su.platform_tag("Windows", "AMD64") == "windows-x64"
    assert su.platform_tag("Linux", "x86_64") == "linux-x64"
    assert su.platform_tag("Linux", "aarch64") == "linux-arm64"
    with pytest.raises(su.UpdateError):
        su.platform_tag("Plan9", "x86_64")


# ---- the release listing ---------------------------------------------------------------------------------------
BASE = "https://github.com/JuanenRac/URTC-FLASHER/releases/download/v0.5.0/"


def release(version="0.5.0", platform="windows-x64", app="urtc-flasher", size=10, extra=None, body="key_id: " + KEY_ID, **flags):
    name = su.package_name(app, version, platform)
    assets = [{"name": n, "browser_download_url": BASE + n, "size": s} for n, s in ((name, size), (name + ".sha256", 80), (name + ".sig", 130))]
    data = {"tag_name": "v" + version, "published_at": "2026-01-01T00:00:00Z", "body": body, "assets": assets + (extra or [])}
    data.update(flags)
    return data


def test_a_higher_version_with_a_package_for_the_platform_is_offered():
    offer = su.find_update(release(), "urtc-flasher", "0.4.1", "windows-x64")
    assert offer is not None
    assert (offer.version, offer.package.name, offer.key_id) == ("0.5.0", "urtc-flasher-0.5.0-windows-x64.zip", KEY_ID)
    assert su.package_name("urtc-flasher", "0.5.0", "linux-x64").endswith(".tar.gz")


def test_nothing_is_offered_for_an_equal_older_draft_prerelease_or_other_platform_release():
    assert su.find_update(release(), "urtc-flasher", "0.5.0", "windows-x64") is None
    assert su.find_update(release(), "urtc-flasher", "0.6.0", "windows-x64") is None
    assert su.find_update(release(draft=True), "urtc-flasher", "0.4.1", "windows-x64") is None
    assert su.find_update(release(prerelease=True), "urtc-flasher", "0.4.1", "windows-x64") is None
    assert su.find_update(release(), "urtc-flasher", "0.4.1", "linux-x64") is None
    assert su.find_update({"tag_name": "nightly", "assets": []}, "urtc-flasher", "0.4.1", "windows-x64") is None


def test_a_release_with_a_package_but_no_checksum_or_signature_is_reported_not_offered():
    data = release()
    data["assets"] = [a for a in data["assets"] if not a["name"].endswith(".sig")]
    with pytest.raises(su.UpdateError) as caught:
        su.find_update(data, "urtc-flasher", "0.4.1", "windows-x64")
    assert caught.value.code == "incomplete_release"


def test_a_package_from_another_host_or_a_plain_http_url_is_refused():
    data = release()
    data["assets"][0]["browser_download_url"] = "https://evil.example/urtc-flasher-0.5.0-windows-x64.zip"
    with pytest.raises(su.UpdateError) as caught:
        su.find_update(data, "urtc-flasher", "0.4.1", "windows-x64")
    assert caught.value.code == "bad_host"
    with pytest.raises(su.UpdateError):
        su.check_host("http://github.com/x")
    su.check_host("https://objects.githubusercontent.com/x")


def test_a_package_announced_bigger_than_the_limit_is_refused():
    with pytest.raises(su.UpdateError) as caught:
        su.find_update(release(size=su.MAX_PACKAGE_BYTES + 1), "urtc-flasher", "0.4.1", "windows-x64")
    assert caught.value.code == "too_big"


# ---- a fake server and packages ------------------------------------------------------------------------------
def make_zip(version="0.5.0", app="urtc-flasher", info=True, extra=None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        if info:
            zf.writestr("app_info.json", json.dumps({"name": app, "version": version}))
        zf.writestr("bin/app.exe", b"MZ" + bytes(100))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return out.getvalue()


class Server:
    """Answers the three URLs of one release; ``cut_after`` closes the package early, like a lost connection."""

    def __init__(self, package: bytes, seed: bytes = SEED, announce_size=None, tamper_sha=False, cut_after=None, version="0.5.0"):
        self.package = package
        self.cut_after = cut_after
        digest = hashlib.sha256(package).hexdigest()
        self.name = su.package_name("urtc-flasher", version, "windows-x64")
        self.sha = ("0" * 64 if tamper_sha else digest) + "  " + self.name
        self.sig = sign(seed, su.package_message("urtc-flasher", version, "windows-x64", digest, len(package))).hex()
        self.offer = su.find_update(release(version=version, size=announce_size if announce_size is not None else len(package)),
                                    "urtc-flasher", "0.4.1", "windows-x64")
        self.requested: list[str] = []

    def __call__(self, url):
        self.requested.append(url)
        body = {BASE + self.name: self.package, BASE + self.name + ".sha256": self.sha.encode(), BASE + self.name + ".sig": self.sig.encode()}[url]
        if url.endswith(self.name) and self.cut_after is not None:
            return Cut(body[: self.cut_after])
        return io.BytesIO(body)


class Cut(io.BytesIO):
    """A body that ends early with no error: the size check has to notice."""


def fetched(tmp_path, server, **kw):
    return su.download_package(server.offer, server, tmp_path / "cache", **kw)


def test_a_good_package_is_downloaded_verified_and_reported_with_its_progress(tmp_path):
    server = Server(make_zip())
    seen: list[tuple[int, int]] = []
    path, sha, signature = fetched(tmp_path, server, progress=lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == server.package and seen[-1] == (len(server.package), len(server.package))
    su.verify_package(server.offer, path, sha, signature, PUBLIC.hex(), KEY_ID)
    assert not list((tmp_path / "cache").glob("*.part"))


def test_a_connection_cut_in_the_middle_leaves_nothing_behind(tmp_path):
    server = Server(make_zip(), cut_after=50)
    with pytest.raises(su.UpdateError) as caught:
        fetched(tmp_path, server)
    assert caught.value.code == "size_mismatch"
    assert list((tmp_path / "cache").iterdir()) == []


def test_a_package_that_does_not_match_its_announced_checksum_is_refused_and_removed(tmp_path):
    with pytest.raises(su.UpdateError) as caught:
        fetched(tmp_path, Server(make_zip(), tamper_sha=True))
    assert caught.value.code == "sha256_mismatch"
    assert list((tmp_path / "cache").iterdir()) == []


def test_a_package_bigger_than_announced_is_refused(tmp_path):
    with pytest.raises(su.UpdateError) as caught:
        fetched(tmp_path, Server(make_zip(), announce_size=20))
    assert caught.value.code == "too_big"
    assert list((tmp_path / "cache").iterdir()) == []


def test_a_signature_by_another_key_is_refused(tmp_path):
    server = Server(make_zip(), seed=bytes(range(1, 33)))
    path, sha, signature = fetched(tmp_path, server)
    with pytest.raises(su.UpdateError) as caught:
        su.verify_package(server.offer, path, sha, signature, PUBLIC.hex(), KEY_ID)
    assert caught.value.code == "bad_signature"


def test_a_release_that_declares_another_key_identifier_is_refused(tmp_path):
    server = Server(make_zip())
    path, sha, signature = fetched(tmp_path, server)
    with pytest.raises(su.UpdateError) as caught:
        su.verify_package(server.offer, path, sha, signature, PUBLIC.hex(), "ffffffffffffffff")
    assert caught.value.code == "key_mismatch"


def test_a_package_changed_after_the_download_is_refused(tmp_path):
    server = Server(make_zip())
    path, sha, signature = fetched(tmp_path, server)
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(su.UpdateError) as caught:
        su.verify_package(server.offer, path, sha, signature, PUBLIC.hex(), KEY_ID)
    assert caught.value.code == "sha256_mismatch"


def test_a_signature_for_another_app_or_version_does_not_pass(tmp_path):
    server = Server(make_zip())
    path, sha, signature = fetched(tmp_path, server)
    other = su.Offer("urtc-tester", server.offer.version, server.offer.platform, server.offer.tag, "", "", server.offer.package, server.offer.sha256, server.offer.signature, KEY_ID)
    with pytest.raises(su.UpdateError):
        su.verify_package(other, path, sha, signature, PUBLIC.hex(), KEY_ID)


# ---- extraction ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../evil.txt", "C:/evil.txt", "..\\evil.txt"])
def test_a_zip_with_a_path_outside_the_folder_is_refused(tmp_path, name):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(make_zip(extra={name: b"x"}))
    with pytest.raises(su.UpdateError) as caught:
        su.safe_extract(archive, tmp_path / "out")
    assert caught.value.code == "unsafe_path"
    assert not (tmp_path / "evil.txt").exists()


def test_a_tar_with_a_link_a_device_or_a_path_outside_the_folder_is_refused(tmp_path):
    for kind in ("link", "dotdot", "device"):
        archive = tmp_path / f"{kind}.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            info = tarfile.TarInfo({"link": "lnk", "dotdot": "../evil", "device": "dev"}[kind])
            if kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            elif kind == "device":
                info.type = tarfile.CHRTYPE
            else:
                info.size = 1
            tf.addfile(info, io.BytesIO(b"x") if kind == "dotdot" else None)
        with pytest.raises(su.UpdateError):
            su.safe_extract(archive, tmp_path / "out" / kind)
    assert not (tmp_path / "evil").exists()


def test_a_tar_gz_package_extracts_with_its_executable_bit(tmp_path):
    archive = tmp_path / "ok.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name, data, mode in (("app_info.json", b"{}", 0o644), ("bin/run", b"#!/bin/sh\n", 0o755)):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tf.addfile(info, io.BytesIO(data))
    assert su.safe_extract(archive, tmp_path / "out") == 2
    assert (tmp_path / "out" / "bin" / "run").read_bytes().startswith(b"#!")


def test_an_archive_of_another_kind_is_refused(tmp_path):
    (tmp_path / "x.rar").write_bytes(b"x")
    with pytest.raises(su.UpdateError) as caught:
        su.safe_extract(tmp_path / "x.rar", tmp_path / "out")
    assert caught.value.code == "unknown_archive"


# ---- install, rollback, first start ----------------------------------------------------------------------------
def install(tmp_path, version, **kw):
    package = make_zip(version=version, **kw)
    archive = tmp_path / f"pkg-{version}.zip"
    archive.write_bytes(package)
    offer = su.find_update(release(version=version, size=len(package)), "urtc-flasher", "0.0.1", "windows-x64")
    return su.install_package(archive, tmp_path / "root", offer, sha256_hex="abc"), offer


def test_an_install_switches_current_keeps_two_releases_and_writes_the_history(tmp_path):
    for version in ("0.5.0", "0.5.1", "0.5.2"):
        folder, _ = install(tmp_path, version)
        assert (folder / "bin" / "app.exe").is_file()
    root = tmp_path / "root"
    assert su.current_version(root) == "0.5.2"
    assert su.installed_versions(root) == ["0.5.1", "0.5.2"]
    history = su.read_history(root)
    assert [h["to"] for h in history] == ["0.5.0", "0.5.1", "0.5.2"] and history[-1]["previous"] == "0.5.1"


def test_an_install_is_refused_while_an_operation_is_running_and_touches_nothing(tmp_path):
    package = make_zip()
    archive = tmp_path / "p.zip"
    archive.write_bytes(package)
    offer = su.find_update(release(size=len(package)), "urtc-flasher", "0.4.1", "windows-x64")
    with pytest.raises(su.UpdateError) as caught:
        su.install_package(archive, tmp_path / "root", offer, busy_reason="a firmware update is running")
    assert caught.value.code == "busy" and not (tmp_path / "root").exists()


def test_a_package_whose_app_info_does_not_match_what_was_announced_is_not_installed(tmp_path):
    install(tmp_path, "0.5.0")
    with pytest.raises(su.UpdateError) as caught:
        install(tmp_path, "0.5.1", info=False)
    assert caught.value.code == "app_info_missing"
    package = make_zip(version="0.9.9")
    archive = tmp_path / "wrong.zip"
    archive.write_bytes(package)
    offer = su.find_update(release(version="0.5.1", size=len(package)), "urtc-flasher", "0.0.1", "windows-x64")
    with pytest.raises(su.UpdateError) as caught:
        su.install_package(archive, tmp_path / "root", offer)
    assert caught.value.code == "app_info_mismatch"
    root = tmp_path / "root"
    assert su.current_version(root) == "0.5.0" and su.installed_versions(root) == ["0.5.0"]
    assert not list((root / "releases").glob("*.partial"))
    assert [h["result"] for h in su.read_history(root)] == ["ok", "refused", "refused"]


def test_rollback_goes_to_the_previous_release_and_fails_when_there_is_none(tmp_path):
    install(tmp_path, "0.5.0")
    root = tmp_path / "root"
    with pytest.raises(su.UpdateError) as caught:
        su.rollback(root)
    assert caught.value.code == "nothing_to_roll_back"
    install(tmp_path, "0.5.1")
    assert su.rollback(root) == "0.5.0" and su.current_version(root) == "0.5.0"
    assert su.read_history(root)[-1]["event"] == "rollback"


def test_a_new_release_that_fails_its_first_start_is_replaced_by_the_previous_one(tmp_path):
    install(tmp_path, "0.5.0")
    install(tmp_path, "0.5.1")
    root = tmp_path / "root"
    assert su.finish_first_start(root, True) is None and su.current_version(root) == "0.5.1"
    assert su.finish_first_start(root, False) == "0.5.0" and su.current_version(root) == "0.5.0"
    last = su.read_history(root)[-1]
    assert last["event"] == "rollback" and last["reason"] == "first start failed"


def test_a_failed_first_start_with_nothing_to_go_back_to_is_recorded(tmp_path):
    install(tmp_path, "0.5.0")
    assert su.finish_first_start(tmp_path / "root", False) is None
    assert "nothing to go back to" in su.read_history(tmp_path / "root")[-1]["result"]


def test_the_history_survives_a_damaged_line(tmp_path):
    install(tmp_path, "0.5.0")
    with open(tmp_path / "root" / "history.jsonl", "a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    assert len(su.read_history(tmp_path / "root")) == 1
