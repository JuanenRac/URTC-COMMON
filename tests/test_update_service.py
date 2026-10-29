# =============================================================================
# URTC-COMMON - tests/test_update_service.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The options, the steps and the launcher of the update, and the tool that builds and signs a package."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import make_update_package as mk
import pytest

from urtc_common import launcher
from urtc_common import self_update as su
from urtc_common import update_service as svc

SEED = bytes(range(32))
PUBLIC = mk.public_key_of(SEED)
KEY_ID = hashlib.sha256(PUBLIC).hexdigest()[:16]
BASE = "https://github.com/JuanenRac/URTC-FLASHER/releases/download/v0.5.0/"


class Stream(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_package(tmp_path, version="0.5.0", platform="windows-x64", app="urtc-flasher", entry="flasher.exe"):
    source = tmp_path / "dist"
    source.mkdir(parents=True)
    (source / entry).write_bytes(b"MZ-not-really")
    (source / "data").mkdir()
    (source / "data" / "x.txt").write_text("hello", encoding="utf-8")
    package, key_id = mk.build(app, version, platform, source, entry, tmp_path / "out", SEED)
    assert key_id == KEY_ID
    return package


def server(package: Path, version="0.5.0", platform="windows-x64", app="urtc-flasher", tamper=None):
    name = package.name
    files = {BASE + name: package.read_bytes(), BASE + name + ".sha256": (package.parent / (name + ".sha256")).read_bytes(),
             BASE + name + ".sig": (package.parent / (name + ".sig")).read_bytes()}
    if tamper:
        files[BASE + name] = tamper(files[BASE + name])
    listing = {
        "tag_name": "v" + version, "published_at": "x", "body": "Notes\nkey_id: " + KEY_ID,
        "assets": [{"name": Path(u).name, "browser_download_url": u, "size": len(d)} for u, d in files.items()],
    }
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/releases/latest"):
            return Stream(json.dumps(listing).encode())
        return Stream(files[url])

    return fetch, calls


def service(tmp_path, fetch, installed="0.4.0", policy=None, busy=None):
    return svc.UpdateService("urtc-flasher", installed, tmp_path / "root", policy or svc.UpdatePolicy(), PUBLIC.hex(), KEY_ID,
                             fetch=fetch, platform="windows-x64", busy=busy)


# ---- the pinned key ---------------------------------------------------------------------------------------------
def test_the_pinned_key_identifier_is_derived_from_the_key_and_the_same_key_signs_the_images():
    assert svc.RELEASE_KEY_ID == hashlib.sha256(bytes.fromhex(svc.RELEASE_PUBLIC_KEY_HEX)).hexdigest()[:16]
    assert len(svc.RELEASE_PUBLIC_KEY_HEX) == 64
    sibling = Path(__file__).resolve().parents[2] / "URTC" / "tools" / "release_sign.py"
    if sibling.is_file():
        assert svc.RELEASE_PUBLIC_KEY_HEX in sibling.read_text(encoding="utf-8")


# ---- the options ------------------------------------------------------------------------------------------------
def test_the_defaults_never_update_by_themselves_and_ask_for_confirmation():
    policy = svc.policy_from({}, {})
    assert (policy.auto_check, policy.require_confirmation) == (False, True)


def test_the_settings_and_the_environment_change_the_options_and_the_environment_wins():
    policy = svc.policy_from({"update_auto_check": True, "update_require_confirmation": False}, {})
    assert (policy.auto_check, policy.require_confirmation) == (True, False)
    policy = svc.policy_from({"update_auto_check": True}, {svc.ENV_AUTO_CHECK: "0", svc.ENV_REQUIRE_CONFIRMATION: "off"})
    assert (policy.auto_check, policy.require_confirmation) == (False, False)
    policy = svc.policy_from({"update_auto_check": "yes", "update_require_confirmation": 0}, {})
    assert (policy.auto_check, policy.require_confirmation) == (False, True)  # not booleans: the defaults


def test_a_lower_protection_is_reported():
    saved = svc.UpdatePolicy()
    assert svc.lowering_warnings(saved, saved) == []
    assert svc.lowering_warnings(saved, svc.UpdatePolicy(auto_check=True, require_confirmation=False)) == ["confirmation_off", "auto_check_on"]
    assert svc.is_lowering(saved, svc.UpdatePolicy(require_confirmation=False))
    assert not svc.is_lowering(svc.UpdatePolicy(auto_check=True, require_confirmation=False), saved)


def test_where_the_releases_are_kept(tmp_path):
    assert svc.default_root("urtc-flasher", {svc.ENV_ROOT: str(tmp_path)}) == tmp_path / "urtc-flasher"
    assert svc.default_root("urtc-flasher", {"LOCALAPPDATA": str(tmp_path)}, "Windows") == tmp_path / "URTC" / "urtc-flasher"
    assert svc.default_root("urtc-flasher", {"XDG_DATA_HOME": str(tmp_path)}, "Linux") == tmp_path / "URTC" / "urtc-flasher"
    assert svc.default_root("urtc-flasher", {}, "Darwin").parts[-3:] == ("Application Support", "URTC", "urtc-flasher")


# ---- the steps --------------------------------------------------------------------------------------------------
def test_check_prepare_and_install_a_signed_package(tmp_path):
    package = make_package(tmp_path)
    fetch, calls = server(package)
    s = service(tmp_path, fetch)
    offer = s.check()
    assert offer is not None and offer.version == "0.5.0"
    assert calls == ["https://api.github.com/repos/JuanenRac/URTC-FLASHER/releases/latest"]  # nothing downloaded by the check
    assert s.current() is None
    prepared = s.prepare(offer)
    assert prepared.path.is_file() and s.current() is None  # verified, not installed
    final = s.install(prepared, confirmed=True)
    assert s.current() == "0.5.0" and (final / "flasher.exe").is_file() and (final / "data" / "x.txt").read_text() == "hello"
    assert svc.pending_first_start(s.root) == "0.5.0"
    assert not prepared.path.exists()
    events = [(h["event"], h["result"]) for h in s.history()]
    assert ("check", "offer") in events and ("verify", "ok") in events and ("install", "ok") in events


def test_nothing_is_offered_for_the_installed_or_a_newer_version(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    assert service(tmp_path, fetch, installed="0.5.0").check() is None
    assert service(tmp_path, fetch, installed="0.6.0").check() is None


def test_install_refuses_without_the_confirmation_of_the_person(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    s = service(tmp_path, fetch)
    prepared = s.prepare(s.check())
    with pytest.raises(su.UpdateError) as caught:
        s.install(prepared)
    assert caught.value.code == "confirmation_required" and s.current() is None
    relaxed = service(tmp_path, fetch, policy=svc.UpdatePolicy(require_confirmation=False))
    relaxed.install(prepared)  # the person turned the confirmation off in the settings
    assert relaxed.current() == "0.5.0"


def test_a_tampered_package_is_refused_and_removed_before_install(tmp_path):
    package = make_package(tmp_path)

    def tamper(data):
        return data[:-1] + bytes([data[-1] ^ 1])

    fetch, _ = server(package, tamper=tamper)
    s = service(tmp_path, fetch)
    with pytest.raises(su.UpdateError) as caught:
        s.prepare(s.check())
    assert caught.value.code in {"sha256_mismatch", "bad_signature"}
    assert not list((s.root / "downloads").glob("*")) and s.current() is None


def test_a_package_signed_by_another_key_is_refused(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    other = svc.UpdateService("urtc-flasher", "0.4.0", tmp_path / "root", svc.UpdatePolicy(), mk.public_key_of(bytes(32)).hex(), KEY_ID,
                              fetch=fetch, platform="windows-x64")
    with pytest.raises(su.UpdateError) as caught:
        other.prepare(other.check())
    assert caught.value.code == "bad_signature"


def test_a_release_that_declares_another_key_is_refused(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    s = service(tmp_path, fetch)
    wrong = svc.UpdateService("urtc-flasher", "0.4.0", tmp_path / "root", svc.UpdatePolicy(), PUBLIC.hex(), "0" * 16, fetch=fetch, platform="windows-x64")
    with pytest.raises(su.UpdateError) as caught:
        wrong.prepare(s.check())
    assert caught.value.code == "key_mismatch"


def test_install_is_refused_while_the_bus_is_busy(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    s = service(tmp_path, fetch, busy=lambda: "a flash is running")
    prepared = s.prepare(s.check())
    with pytest.raises(su.UpdateError) as caught:
        s.install(prepared, confirmed=True)
    assert caught.value.code == "busy" and s.current() is None


def test_a_listing_that_is_not_json_or_too_big_is_a_typed_error(tmp_path):
    s = service(tmp_path, lambda url: Stream(b"<html>"))
    with pytest.raises(su.UpdateError) as caught:
        s.check()
    assert caught.value.code == "bad_release_listing"
    big = service(tmp_path, lambda url: Stream(b" " * (2 * 1024 * 1024 + 5)))
    with pytest.raises(su.UpdateError) as caught:
        big.check()
    assert caught.value.code == "too_big"


def test_the_default_fetch_refuses_another_host_before_any_connection():
    with pytest.raises(su.UpdateError) as caught:
        svc.urllib_fetch("https://example.com/x")
    assert caught.value.code == "bad_host"
    with pytest.raises(su.UpdateError):
        svc.urllib_fetch("http://api.github.com/x")


def test_rollback_and_mark_started(tmp_path):
    first = make_package(tmp_path / "a", version="0.5.0")
    fetch, _ = server(first)
    s = service(tmp_path, fetch)
    s.install(s.prepare(s.check()), confirmed=True)
    assert svc.mark_started(s.root) is True and svc.pending_first_start(s.root) is None
    assert svc.mark_started(s.root) is False
    # a second release on top of the first
    second_dir = tmp_path / "b"
    second_dir.mkdir()
    second = make_package(second_dir, version="0.5.1")
    base = "https://github.com/JuanenRac/URTC-FLASHER/releases/download/v0.5.1/"
    name = second.name
    files = {base + name: second.read_bytes(), base + name + ".sha256": (second.parent / (name + ".sha256")).read_bytes(), base + name + ".sig": (second.parent / (name + ".sig")).read_bytes()}
    listing = {"tag_name": "v0.5.1", "body": "key_id: " + KEY_ID, "assets": [{"name": Path(u).name, "browser_download_url": u, "size": len(d)} for u, d in files.items()]}
    s2 = svc.UpdateService("urtc-flasher", "0.5.0", s.root, svc.UpdatePolicy(), PUBLIC.hex(), KEY_ID, platform="windows-x64",
                           fetch=lambda url: Stream(json.dumps(listing).encode() if url.endswith("/latest") else files[url]))
    s2.install(s2.prepare(s2.check()), confirmed=True)
    assert s2.current() == "0.5.1"
    assert s2.rollback() == "0.5.0" and s2.current() == "0.5.0"


# ---- the launcher -----------------------------------------------------------------------------------------------
def installed_root(tmp_path, versions=("0.5.0",), entry="app.py"):
    root = tmp_path / "root"
    for version in versions:
        folder = root / "releases" / version
        folder.mkdir(parents=True)
        (folder / entry).write_text("print('hi')\n", encoding="utf-8")
        (folder / "app_info.json").write_text(json.dumps({"name": "urtc-flasher", "version": version, "entry": entry}), encoding="utf-8")
    su._write_current(root, versions[-1])
    return root


def test_the_launcher_resolves_the_entry_of_the_current_release(tmp_path):
    root = installed_root(tmp_path)
    assert launcher.resolve_entry(root) == (root / "releases" / "0.5.0" / "app.py").resolve()


def test_the_launcher_refuses_a_missing_release_or_an_entry_outside_the_folder(tmp_path):
    with pytest.raises(su.UpdateError) as caught:
        launcher.resolve_entry(tmp_path / "nothing")
    assert caught.value.code == "no_current_release"
    root = installed_root(tmp_path)
    info = root / "releases" / "0.5.0" / "app_info.json"
    for entry, code in (("../../../x", "entry_outside"), ("missing.exe", "entry_missing"), ("", "entry_missing")):
        info.write_text(json.dumps({"entry": entry}), encoding="utf-8")
        with pytest.raises(su.UpdateError) as caught:
            launcher.resolve_entry(root)
        assert caught.value.code == code
    info.write_text("not json", encoding="utf-8")
    with pytest.raises(su.UpdateError) as caught:
        launcher.resolve_entry(root)
    assert caught.value.code == "app_info_missing"


def test_a_first_start_that_fails_goes_back_to_the_previous_release(tmp_path):
    root = installed_root(tmp_path, ("0.4.0", "0.5.0"))
    (root / launcher.PENDING_FILE).write_text("0.5.0\n", encoding="utf-8")
    seen = []
    code = launcher.launch(root, ["--x"], run=lambda command, cwd: seen.append((command, cwd)) or 7)
    assert code == 7 and su.current_version(root) == "0.4.0"
    assert seen[0][0][-1] == "--x" and seen[0][0][0] == sys.executable
    assert not (root / launcher.PENDING_FILE).exists()
    assert any(h.get("event") == "rollback" for h in su.read_history(root))


def test_a_first_start_that_works_stays_and_no_pending_start_never_rolls_back(tmp_path):
    root = installed_root(tmp_path, ("0.4.0", "0.5.0"))
    (root / launcher.PENDING_FILE).write_text("0.5.0\n", encoding="utf-8")
    assert launcher.launch(root, run=lambda command, cwd: 0) == 0 and su.current_version(root) == "0.5.0"
    assert launcher.launch(root, run=lambda command, cwd: 9) == 9 and su.current_version(root) == "0.5.0"  # a later crash is not a first start


def test_the_launcher_command_line(tmp_path, capsys):
    assert launcher.main(["--help"]) == 0
    assert launcher.main([]) == 2
    assert launcher.main([str(tmp_path / "none")]) == 3
    assert "no_current_release" in capsys.readouterr().err


# ---- the tool that builds the package -------------------------------------------------------------------------
def test_a_built_package_passes_the_check_of_the_programs_and_is_reproducible(tmp_path):
    package = make_package(tmp_path)
    again = tmp_path / "again"
    again.mkdir()
    (tmp_path / "dist" / "flasher.exe").stat()
    other, _ = mk.build("urtc-flasher", "0.5.0", "windows-x64", tmp_path / "dist", "flasher.exe", again, SEED)
    assert other.read_bytes() == package.read_bytes()  # the same bytes every time
    with zipfile.ZipFile(package) as archive:
        assert sorted(archive.namelist()) == ["app_info.json", "data/x.txt", "flasher.exe"]
        info = json.loads(archive.read("app_info.json"))
    assert info == {"entry": "flasher.exe", "name": "urtc-flasher", "platform": "windows-x64", "version": "0.5.0"}
    sha = (package.parent / (package.name + ".sha256")).read_text().split()[0]
    assert sha == hashlib.sha256(package.read_bytes()).hexdigest()
    assert su.ed25519_verify(PUBLIC, su.package_message("urtc-flasher", "0.5.0", "windows-x64", sha, package.stat().st_size),
                             bytes.fromhex((package.parent / (package.name + ".sig")).read_text().strip()))


def test_a_tar_package_for_linux(tmp_path):
    package = make_package(tmp_path, platform="linux-x64", entry="flasher")
    assert package.name == "urtc-flasher-0.5.0-linux-x64.tar.gz"
    destination = tmp_path / "x"
    assert su.safe_extract(package, destination) == 3
    assert json.loads((destination / "app_info.json").read_text())["platform"] == "linux-x64"


def test_the_build_refuses_a_missing_entry_a_bad_name_and_a_bad_version(tmp_path):
    source = tmp_path / "d"
    source.mkdir()
    (source / "a.exe").write_bytes(b"x")
    for kwargs in ({"entry": "b.exe"}, {"app": "Bad Name"}, {"source": tmp_path / "nope"}):
        arguments = {"app": "urtc-flasher", "version": "0.5.0", "platform": "windows-x64", "source": source, "entry": "a.exe", "out": tmp_path / "o", "seed": SEED}
        arguments.update(kwargs)
        with pytest.raises(SystemExit):
            mk.build(**arguments)
    with pytest.raises(su.UpdateError):
        mk.build("urtc-flasher", "x", "windows-x64", source, "a.exe", tmp_path / "o", SEED)


def test_the_pem_of_a_key_is_read_and_a_wrong_file_is_refused(tmp_path):
    der = bytes.fromhex("302e020100300506032b657004220420") + SEED
    pem = tmp_path / "k.pem"
    pem.write_text("-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----\n", encoding="ascii")
    assert mk.read_seed(pem) == SEED
    pem.write_text("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n", encoding="ascii")
    with pytest.raises(SystemExit):
        mk.read_seed(pem)


def test_the_command_line_builds_and_verifies_with_the_pinned_key_only(tmp_path, capsys):
    source = tmp_path / "d"
    source.mkdir()
    (source / "a.exe").write_bytes(b"x")
    der = bytes.fromhex("302e020100300506032b657004220420") + SEED
    pem = tmp_path / "k.pem"
    pem.write_text("-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PRIVATE KEY-----\n", encoding="ascii")
    assert mk.main(["public", "--key", str(pem)]) == 0
    assert capsys.readouterr().out.strip() == PUBLIC.hex()
    # this test key is not the key of the releases: the build says so and the package is not trusted
    code = mk.main(["build", "--app", "urtc-flasher", "--version", "0.5.0", "--platform", "windows-x64", "--source", str(source), "--entry", "a.exe", "--out", str(tmp_path / "o"), "--key", str(pem)])
    assert code == 1 and "the programs trust" in capsys.readouterr().err
    with pytest.raises(su.UpdateError) as caught:
        mk.verify(tmp_path / "o" / "urtc-flasher-0.5.0-windows-x64.zip")
    assert caught.value.code == "bad_signature"
    assert mk.main(["verify", str(tmp_path / "o" / "urtc-flasher-0.5.0-windows-x64.zip")]) == 1


def test_verify_refuses_a_file_that_is_not_a_package(tmp_path):
    with pytest.raises(SystemExit):
        mk.verify(tmp_path / "x.rar")


# ---- the state machine behind the menu ---------------------------------------------------------------------------
from urtc_common import update_controller as uc  # noqa: E402


def controller(tmp_path, fetch, **kwargs):
    seen = []
    return uc.UpdateController(service(tmp_path, fetch, **kwargs), seen.append, background=False), seen


def test_the_controller_goes_through_the_steps_and_installs_only_after_the_confirmation(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    c, seen = controller(tmp_path, fetch)
    assert c.state == uc.IDLE and c.check()
    assert c.snapshot()["state"] == uc.AVAILABLE and c.snapshot()["version"] == "0.5.0" and "Notes" in c.snapshot()["notes"]
    assert not c.install()  # not downloaded yet
    assert c.download() and c.state == uc.READY
    assert not c.install() and c.snapshot()["error_code"] == "confirmation_required" and c.state == uc.READY
    assert c.confirm_install() and c.install()
    assert c.state == uc.INSTALLED and c.snapshot()["current"] == "0.5.0"
    assert [s["state"] for s in seen][:3] == [uc.CHECKING, uc.AVAILABLE, uc.DOWNLOADING]
    assert any(s["progress"] == 100 for s in seen)


def test_the_controller_reports_the_latest_version_and_errors_with_a_code(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    c, _ = controller(tmp_path, fetch, installed="0.5.0")
    c.check()
    assert c.state == uc.UP_TO_DATE
    c2, _ = controller(tmp_path, lambda url: (_ for _ in ()).throw(OSError("offline")))
    c2.check()
    assert c2.state == uc.ERROR and c2.snapshot()["error_code"] == "unexpected" and "offline" in c2.snapshot()["error_text"]


def test_the_controller_never_checks_on_start_unless_the_person_turned_it_on(tmp_path):
    package = make_package(tmp_path)
    fetch, calls = server(package)
    c, _ = controller(tmp_path, fetch)
    assert c.startup_check() is False and calls == [] and c.state == uc.IDLE
    c2, _ = controller(tmp_path / "b", fetch, policy=svc.UpdatePolicy(auto_check=True))
    assert c2.startup_check() is True and c2.state == uc.AVAILABLE
    assert not c2.install()  # even with the automatic check, nothing is installed by itself


def test_the_controller_confirmation_is_for_one_package_and_a_busy_bus_is_an_error(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    c, _ = controller(tmp_path, fetch, busy=lambda: "bus in use")
    c.check()
    c.download()
    c.confirm_install()
    assert c.install() is True and c.state == uc.ERROR and c.snapshot()["error_code"] == "busy"
    assert not c.confirm_install()  # an error needs a new check
    c.dismiss()
    assert c.state == uc.IDLE and c.snapshot()["version"] == ""


def test_the_controller_rolls_back_and_refuses_while_busy(tmp_path):
    package = make_package(tmp_path)
    fetch, _ = server(package)
    c, _ = controller(tmp_path, fetch)
    assert not c.roll_back() and c.snapshot()["error_code"] == "nothing_to_roll_back"
    c.check()
    c.download()
    c.confirm_install()
    c.install()
    assert c.snapshot()["can_roll_back"] is False
    c._state = uc.CHECKING
    assert not c.check() and not c.roll_back()
    c.dismiss()
    assert c._state == uc.CHECKING  # a running step is not dismissed


def test_the_controller_can_run_in_a_worker_thread(tmp_path):
    import threading
    package = make_package(tmp_path)
    fetch, _ = server(package)
    done = threading.Event()
    c = uc.UpdateController(service(tmp_path, fetch), lambda shot: done.set() if shot["state"] == uc.AVAILABLE else None)
    assert c.check()
    assert done.wait(10) and c.state == uc.AVAILABLE


# ---- a package file picked by hand ---------------------------------------------------------------------------------
def test_a_package_file_is_verified_and_installed_and_the_file_stays(tmp_path):
    package = make_package(tmp_path)
    s = service(tmp_path, lambda url: (_ for _ in ()).throw(AssertionError("no network for a local file")))
    prepared = s.prepare_local(package)
    assert prepared.offer.version == "0.5.0" and prepared.sha256 == hashlib.sha256(package.read_bytes()).hexdigest()
    s.install(prepared, confirmed=True)
    assert s.current() == "0.5.0" and package.is_file()
    assert any(h.get("source") == "file" for h in s.history())


def test_a_package_file_is_refused_for_another_program_system_version_or_without_its_companions(tmp_path):
    package = make_package(tmp_path)
    s = service(tmp_path, None)

    def refused(candidate, code, service_=s):
        with pytest.raises(su.UpdateError) as caught:
            service_.prepare_local(candidate)
        assert caught.value.code == code

    refused(tmp_path / "notes.txt", "bad_package_name")
    refused(package, "app_info_mismatch", svc.UpdateService("urtc-tester", "0.4.0", tmp_path / "r", svc.UpdatePolicy(), PUBLIC.hex(), KEY_ID, fetch=None, platform="windows-x64"))
    refused(package, "unsupported_platform", svc.UpdateService("urtc-flasher", "0.4.0", tmp_path / "r", svc.UpdatePolicy(), PUBLIC.hex(), KEY_ID, fetch=None, platform="linux-x64"))
    refused(package, "not_newer", service(tmp_path, None, installed="0.5.0"))
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    copy = lonely / package.name
    copy.write_bytes(package.read_bytes())
    refused(copy, "incomplete_release")
    (lonely / (package.name + ".sha256")).write_text((package.parent / (package.name + ".sha256")).read_text())
    (lonely / (package.name + ".sig")).write_text(bytes(64).hex() + "\n")
    refused(copy, "bad_signature")


def test_a_redirect_to_plain_http_or_to_another_host_is_refused_and_one_to_a_release_host_is_followed():
    import urllib.request

    handler = svc._CheckedRedirects()
    request = urllib.request.Request("https://github.com/JuanenRac/x/releases/download/v1/x.zip")
    for target in ("http://objects.githubusercontent.com/x", "https://evil.example/x", "ftp://github.com/x"):
        with pytest.raises(su.UpdateError) as caught:
            handler.redirect_request(request, None, 302, "Found", {}, target)
        assert caught.value.code == "bad_host"
    followed = handler.redirect_request(request, None, 302, "Found", {}, "https://objects.githubusercontent.com/x")
    assert followed is not None and followed.full_url == "https://objects.githubusercontent.com/x"
