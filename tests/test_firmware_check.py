# =============================================================================
# URTC-COMMON - tests/test_firmware_check.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The comparison of the firmware a program carries with the newest official release: the parsing, the cache, the limits and the texts."""
from __future__ import annotations

import io
import json
import re
import urllib.error

import pytest

from urtc_common import firmware_check as fc
from urtc_common import firmware_check_strings as strings


class Stream(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def release(tag="v0.4.5", prerelease=False, draft=False, extra=()):
    names = ["URTC_MAIN_FIRMWARE_v0.4.5.bin", "URTC_SLAVE_FIRMWARE_v0.2.9.bin", "URTC_MAIN_BOOTLOADER_v0.4.7.bin", "URTC_SLAVE_BOOTLOADER_v0.3.1.bin",
             "URTC_MAIN_FIRMWARE_v0.4.5.bin.sha256", "notes.txt", *extra]
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": [{"name": name} for name in names]}


class Network:
    def __init__(self, answer):
        self.answer = answer
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return Stream(json.dumps(self.answer).encode("utf-8") if not isinstance(self.answer, bytes) else self.answer)


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://api.github.com/x", code, "x", headers or {}, None)  # type: ignore[arg-type]


def test_the_images_of_a_release_are_read_by_name_and_sidecars_are_ignored():
    assert fc.images_of_release(release()) == {
        ("MAIN", "FIRMWARE"): "0.4.5", ("SLAVE", "FIRMWARE"): "0.2.9", ("MAIN", "BOOTLOADER"): "0.4.7", ("SLAVE", "BOOTLOADER"): "0.3.1"}


def test_the_highest_version_wins_when_two_images_share_a_slot_and_a_bad_listing_is_refused():
    assert fc.images_in(["URTC_MAIN_FIRMWARE_v0.4.5.bin", "URTC_MAIN_FIRMWARE_v0.10.0.bin"]) == {("MAIN", "FIRMWARE"): "0.10.0"}
    for bad in (None, [], {"assets": "x"}, "text"):
        with pytest.raises(fc.FirmwareCheckError) as caught:
            fc.images_of_release(bad)
        assert caught.value.code == "bad_release"


def test_a_folder_is_read_for_its_images(tmp_path):
    (tmp_path / "URTC_MAIN_FIRMWARE_v0.4.1.bin").write_bytes(b"x")
    (tmp_path / "URTC_MAIN_FIRMWARE_v0.4.1.bin.sha256").write_text("x")
    (tmp_path / ".gitkeep").write_text("")
    assert fc.images_in_folder(tmp_path) == {("MAIN", "FIRMWARE"): "0.4.1"}
    assert fc.images_in_folder(tmp_path / "missing") == {}


def test_every_state_of_the_comparison():
    latest = {("MAIN", "FIRMWARE"): "0.4.5", ("SLAVE", "FIRMWARE"): "0.2.9", ("MAIN", "BOOTLOADER"): "0.4.7"}
    local = {("MAIN", "FIRMWARE"): "0.4.5", ("SLAVE", "FIRMWARE"): "0.2.8", ("SLAVE", "BOOTLOADER"): "0.3.1"}
    rows = {(row.board, row.kind): row.state for row in fc.compare(local, latest)}
    assert rows == {("MAIN", "FIRMWARE"): fc.CURRENT, ("MAIN", "BOOTLOADER"): fc.ABSENT, ("SLAVE", "FIRMWARE"): fc.OUTDATED, ("SLAVE", "BOOTLOADER"): fc.NOT_RELEASED}
    assert fc.compare({("MAIN", "FIRMWARE"): "0.5.0"}, {("MAIN", "FIRMWARE"): "0.4.5"})[0].state == fc.AHEAD
    assert fc.compare({("MAIN", "FIRMWARE"): "0.10.0"}, {("MAIN", "FIRMWARE"): "0.9.0"})[0].state == fc.AHEAD  # numbers, not text


def test_one_request_is_enough_while_the_cache_is_fresh(tmp_path):
    network, cache, clock = Network(release()), tmp_path / "cache.json", [1000.0]
    first = fc.latest_release(network, cache, lambda: clock[0])
    assert first.tag == "v0.4.5" and not first.from_cache and network.urls == ["https://api.github.com/repos/JuanenRac/URTC/releases/latest"]
    clock[0] += 3599
    again = fc.latest_release(network, cache, lambda: clock[0])
    assert again.from_cache and again.images == first.images and len(network.urls) == 1
    clock[0] += 2
    assert not fc.latest_release(network, cache, lambda: clock[0]).from_cache and len(network.urls) == 2
    assert not fc.latest_release(network, cache, lambda: clock[0], force=True).from_cache and len(network.urls) == 3


def test_a_cache_of_another_repository_or_a_broken_one_is_not_used(tmp_path):
    network, cache = Network(release()), tmp_path / "cache.json"
    fc.latest_release(network, cache, lambda: 1.0, repo="JuanenRac/URTC")
    fc.latest_release(network, cache, lambda: 2.0, repo="Other/Repo")
    assert len(network.urls) == 2
    cache.write_text("not json")
    fc.latest_release(network, cache, lambda: 3.0)
    assert len(network.urls) == 3


def test_a_failed_request_is_not_repeated_at_once(tmp_path):
    cache, clock = tmp_path / "cache.json", [10.0]
    with pytest.raises(fc.FirmwareCheckError) as first:
        fc.latest_release(Network(OSError("unreachable")), cache, lambda: clock[0])
    assert first.value.code == "network"
    working = Network(release())
    clock[0] += 30
    with pytest.raises(fc.FirmwareCheckError) as soon:
        fc.latest_release(working, cache, lambda: clock[0])
    assert soon.value.code == "too_soon" and working.urls == []
    clock[0] += 31
    assert fc.latest_release(working, cache, lambda: clock[0]).tag == "v0.4.5"


def test_a_failure_keeps_the_last_good_answer_for_the_next_time(tmp_path):
    cache, clock = tmp_path / "cache.json", [0.0]
    fc.latest_release(Network(release()), cache, lambda: clock[0])
    clock[0] = 5000.0
    with pytest.raises(fc.FirmwareCheckError):
        fc.latest_release(Network(OSError("down")), cache, lambda: clock[0])
    saved = json.loads(cache.read_text())
    assert saved["tag"] == "v0.4.5" and saved["failed_at"] == 5000.0


@pytest.mark.parametrize("error,code", [
    (lambda: http_error(403, {"X-RateLimit-Remaining": "0"}), "rate_limit"),
    (lambda: http_error(429), "rate_limit"),
    (lambda: http_error(403), "network"),
    (lambda: http_error(404), "no_release"),
    (lambda: http_error(500), "network"),
    (lambda: urllib.error.URLError("offline"), "network"),
    (lambda: TimeoutError("slow"), "network"),
])
def test_the_errors_have_stable_codes(error, code):
    with pytest.raises(fc.FirmwareCheckError) as caught:
        fc.latest_release(Network(error()))
    assert caught.value.code == code


def test_a_pre_release_a_draft_an_empty_or_a_strange_listing_is_never_compared():
    for answer, code in ((release(prerelease=True), "no_release"), (release(draft=True), "no_release"), ({"tag_name": "v1", "assets": []}, "no_release"),
                         ({"nothing": 1}, "bad_release"), (b"not json", "bad_release"), (b"x" * (fc.MAX_LISTING_BYTES + 5), "bad_release")):
        with pytest.raises(fc.FirmwareCheckError) as caught:
            fc.latest_release(Network(answer))
        assert caught.value.code == code


def test_only_github_over_https_is_asked():
    # the host is fixed in the module: the repository name cannot change it
    network = Network(release())
    fc.latest_release(network)
    assert all(url.startswith("https://api.github.com/") for url in network.urls)


def test_check_returns_the_release_and_the_rows():
    latest, rows = fc.check({("MAIN", "FIRMWARE"): "0.4.4"}, Network(release()))
    assert latest.tag == "v0.4.5"
    assert [r.state for r in rows if (r.board, r.kind) == ("MAIN", "FIRMWARE")] == [fc.OUTDATED]


def test_the_lines_are_written_in_every_language():
    latest = {("MAIN", "FIRMWARE"): "0.4.5", ("SLAVE", "FIRMWARE"): "0.2.9"}
    current = fc.compare(latest, latest)
    mixed = fc.compare({("MAIN", "FIRMWARE"): "0.4.4", ("SLAVE", "BOOTLOADER"): "0.3.1"}, {**latest, ("MAIN", "BOOTLOADER"): "0.4.7"})
    for language in strings.LANGUAGES:
        assert fc.describe(current, "v0.4.5", language) == [strings.text(language, "FWC_ALL_CURRENT", tag="v0.4.5")]
        lines = fc.describe(mixed, "v0.4.5", language, cached_minutes=7)
        assert len(lines) == len(mixed) + 1 and all(lines) and "{" not in "".join(lines)
        assert any("0.4.4" in line and "0.4.5" in line for line in lines)
    assert "main board - application" in fc.describe(mixed, "v0.4.5")[0]


def test_the_texts_have_the_same_keys_and_placeholders_in_the_eight_languages():
    assert tuple(strings.STRINGS) == strings.LANGUAGES and len(strings.LANGUAGES) == 8
    reference = strings.STRINGS["english"]
    holders = lambda value: sorted(re.findall(r"\{(\w+)\}", value))  # noqa: E731
    for language, table in strings.STRINGS.items():
        assert set(table) == set(reference), language
        for key, value in table.items():
            assert value.strip(), (language, key)
            assert holders(value) == holders(reference[key]), (language, key)


def test_every_error_code_has_a_text_in_every_language():
    for code in ("rate_limit", "network", "no_release", "bad_release", "too_soon", "unknown"):
        for language in strings.LANGUAGES:
            line = fc.describe_error(fc.FirmwareCheckError(code, "why"), language)
            assert line and "{" not in line
    assert strings.text("klingon", "FWC_TITLE") == strings.STRINGS["english"]["FWC_TITLE"]
