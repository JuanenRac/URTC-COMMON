# =============================================================================
# URTC-COMMON - tests/test_update_cuts.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A check or a download cut in the middle, and update files damaged on disk: the window must get an error it can show, never
stay busy for ever or fail to open."""
from __future__ import annotations

import http.client
import io

import pytest

from urtc_common import self_update as su
from urtc_common import update_controller as ctl
from urtc_common import update_service as svc


class Cut(io.BytesIO):
    def read(self, *args):
        raise http.client.IncompleteRead(b"{", 100)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def service(tmp_path, fetch):
    return svc.UpdateService("urtc-flasher", "0.4.0", root=tmp_path, fetch=fetch, platform="windows-x64")


def offer():
    base = "https://github.com/JuanenRac/URTC-FLASHER/releases/download/v0.5.0/x.zip"
    return su.Offer("urtc-flasher", "0.5.0", "windows-x64", "v0.5.0", "", "", su.Asset("x.zip", base, 3), su.Asset("x.zip.sha256", base + ".sha256", 65), su.Asset("x.zip.sig", base + ".sig", 129), "")


@pytest.mark.parametrize("failure", [Cut(), None], ids=["incomplete-read", "bad-status-line"])
def test_a_cut_check_is_a_network_error(tmp_path, failure):
    def fetch(url):
        if failure is None:
            raise http.client.BadStatusLine("garbage")
        return Cut()

    with pytest.raises(OSError):
        service(tmp_path, fetch).check()


def test_a_cut_download_is_a_network_error_and_leaves_no_part(tmp_path):
    with pytest.raises(OSError):
        service(tmp_path, lambda url: Cut()).prepare(offer())
    downloads = tmp_path / "downloads"
    assert not downloads.exists() or list(downloads.iterdir()) == []


def test_the_window_leaves_the_busy_state_after_a_cut(tmp_path):
    controller = ctl.UpdateController(service(tmp_path, lambda url: Cut()), background=False)
    assert controller.check()
    assert controller.snapshot()["state"] == ctl.ERROR
    assert controller.check(), "a new check must be possible"


@pytest.mark.parametrize("raw", [b"\xff\xfe0\x00", b"0.5.0\xf1", b""])
def test_a_damaged_current_version_file_is_no_version(tmp_path, raw):
    (tmp_path / "current.txt").write_bytes(raw)
    assert su.current_version(tmp_path) is None


def test_a_damaged_history_keeps_its_readable_lines(tmp_path):
    (tmp_path / "history.jsonl").write_bytes(b'{"event": "check"}\n{"event": "inst\xf1\n[cut\n5\n{"event": "install"}\n')
    assert [entry["event"] for entry in su.read_history(tmp_path)] == ["check", "install"]
