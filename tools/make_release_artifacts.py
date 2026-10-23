#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_release_artifacts.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Build, sign and check the files that publish the specification with a release of URTC-COMMON.

    python tools/make_release_artifacts.py build  --out out/            # wheel, source archive and C header, signed
    python tools/make_release_artifacts.py build  --out out/ --no-sign  # the same bytes, without the key
    python tools/make_release_artifacts.py verify out/                  # hashes, signatures, wheel record, version
    python tools/make_release_artifacts.py reproduce                    # two builds in two folders give the same bytes
    python tools/make_release_artifacts.py smoke  out/                  # install the wheel apart and run the vectors

Three files go to the release, each with ``<file>.sha256`` and ``<file>.sig``:

* ``urtc_common-<version>-py3-none-any.whl``  the Python package (not published on PyPI: it is attached to the release)
* ``urtc_common-<version>.tar.gz``            the source archive: what a checkout tracks that a user of the specification needs
* ``urtc_can_ids.h``                          the generated C header, for firmware that does not want Python

Nothing here depends on the order of files or on the clock: the entries are sorted, their times are fixed, the wheel is stored
without compression and the archive is compressed with the same settings every time, so the same checkout gives the same bytes
with the same Python. The signature is the Ed25519 signature, by the key of the releases, of
``urtc-pkg/1|urtc-common|<version>|<kind>|<sha256>|<size>``, the text the programs already verify for their own packages; ``kind``
is ``py3-none-any``, ``source`` or ``c-header``. The private key is never printed and never in a repository (``--key``,
``URTC_RELEASE_KEY`` or ``~/.urtc-keys/urtc_release_ed25519.pem``). This tool does not publish anything and does not change a version.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import make_update_package as mup  # noqa: E402
from urtc_common import self_update as su  # noqa: E402
from urtc_common import update_service as svc  # noqa: E402

APP = "urtc-common"
DIST = "urtc_common"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
PACKAGES = ("urtc_common", "urtc_ui")
DATA = {"can_protocol.json": "spec/can_protocol.json", "tools.json": "spec/tools.json", "urtc_can_ids.h": "generated/urtc_can_ids.h",
        "can_vectors.json": "conformance/can_vectors.json"}
SOURCE_DIRS = ("src", "spec", "generated", "conformance", "docs", "tools")
SOURCE_FILES = ("pyproject.toml", "LICENSE", "README.md", "CHANGELOG.md", "requirements-dev.lock")
KINDS = {"wheel": "py3-none-any", "sdist": "source", "header": "c-header"}


class ReleaseError(Exception):
    """An artifact is missing, altered or does not belong to the version."""


# --- the project --------------------------------------------------------------------------------------------------
def project(root: Path = ROOT) -> dict:
    """Name, version and metadata read from ``pyproject.toml``."""
    import tomllib
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if data["name"] != APP:
        raise ReleaseError(f"the project is called {data['name']!r}, not {APP!r}")
    su.parse_version(data["version"])
    return data


def names(version: str) -> dict[str, str]:
    return {"wheel": f"{DIST}-{version}-py3-none-any.whl", "sdist": f"{DIST}-{version}.tar.gz", "header": "urtc_can_ids.h"}


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- the wheel ----------------------------------------------------------------------------------------------------
def wheel_files(root: Path) -> dict[str, bytes]:
    """Path inside the wheel -> content, sorted, without the dist-info."""
    files: dict[str, bytes] = {}
    for package in PACKAGES:
        for path in sorted((root / "src" / package).rglob("*.py")):
            if "__pycache__" not in path.parts:
                files[path.relative_to(root / "src").as_posix()] = path.read_bytes()
    for name, source in DATA.items():
        files[f"{DIST}/data/{name}"] = (root / source).read_bytes()
    return dict(sorted(files.items()))


def metadata_text(info: dict, readme: str) -> str:
    lines = ["Metadata-Version: 2.1", f"Name: {info['name']}", f"Version: {info['version']}", f"Summary: {info['description']}"]
    if "Homepage" in info.get("urls", {}):
        lines.append(f"Home-page: {info['urls']['Homepage']}")
    author = (info.get("authors") or [{}])[0]
    if author:
        lines += [f"Author: {author.get('name', '')}", f"Author-email: {author.get('email', '')}"]
    lines += ["License: GPL-3.0-or-later", "Keywords: " + ",".join(info.get("keywords", [])), "License-File: LICENSE",
              "Classifier: License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
              "Classifier: Programming Language :: Python :: 3", "Classifier: Operating System :: OS Independent",
              f"Requires-Python: {info['requires-python']}"]
    for extra, requirements in info.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        lines += [f'Requires-Dist: {requirement}; extra == "{extra}"' for requirement in requirements]
    lines += ["Description-Content-Type: text/markdown", "", readme]
    return "\n".join(lines)


def record_line(path: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"{path},sha256={digest},{len(data)}"


def build_wheel(root: Path = ROOT) -> bytes:
    info = project(root)
    version = info["version"]
    dist_info = f"{DIST}-{version}.dist-info"
    files = wheel_files(root)
    scripts = "\n".join(["[console_scripts]", *(f"{name} = {target}" for name, target in info.get("scripts", {}).items())]) + "\n"
    extra = {
        f"{dist_info}/METADATA": metadata_text(info, (root / "README.md").read_text(encoding="utf-8")).encode("utf-8"),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: urtc-common make_release_artifacts\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist_info}/entry_points.txt": scripts.encode("utf-8"),
        f"{dist_info}/top_level.txt": ("\n".join(PACKAGES) + "\n").encode("utf-8"),
        f"{dist_info}/licenses/LICENSE": (root / "LICENSE").read_bytes(),
    }
    files.update(extra)
    record = "\n".join([*(record_line(path, data) for path, data in files.items()), f"{dist_info}/RECORD,,"]) + "\n"
    files[f"{dist_info}/RECORD"] = record.encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for path, data in files.items():
            entry = zipfile.ZipInfo(path, FIXED_TIME)
            entry.compress_type = zipfile.ZIP_STORED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
    return buffer.getvalue()


# --- the source archive -------------------------------------------------------------------------------------------
def source_files(root: Path) -> list[str]:
    """What the archive carries: the tracked files of the folders that matter, or the files on disk when this is not a checkout."""
    wanted: list[str] = []
    try:
        listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout.decode("utf-8")
        tracked = [name for name in listing.split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        tracked = [p.relative_to(root).as_posix() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
                   and ".git" not in p.parts and ".venv" not in p.parts]
    for name in tracked:
        if (name in SOURCE_FILES or name.split("/")[0] in SOURCE_DIRS) and (root / name).is_file():
            wanted.append(name)
    return sorted(set(wanted))


def build_sdist(root: Path = ROOT) -> bytes:
    version = project(root)["version"]
    prefix = f"{DIST}-{version}"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name in source_files(root):
            data = (root / name).read_bytes()
            member = tarfile.TarInfo(f"{prefix}/{name}")
            member.size, member.mtime, member.mode = len(data), 0, 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            archive.addfile(member, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=out, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(raw.getvalue())
    return out.getvalue()


# --- build, sign, verify -----------------------------------------------------------------------------------------
def build_all(out: Path, seed: bytes | None, root: Path = ROOT) -> dict[str, Path]:
    version = project(root)["version"]
    table = names(version)
    payloads = {"wheel": build_wheel(root), "sdist": build_sdist(root), "header": (root / "generated" / "urtc_can_ids.h").read_bytes()}
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for kind, data in payloads.items():
        path = out / table[kind]
        path.write_bytes(data)
        sha = sha256_of(data)
        path.with_name(path.name + ".sha256").write_text(f"{sha}  {path.name}\n", encoding="ascii")
        if seed is not None:
            signature = mup.sign(seed, su.package_message(APP, version, KINDS[kind], sha, len(data)))
            path.with_name(path.name + ".sig").write_text(signature.hex() + "\n", encoding="ascii")
        written[kind] = path
    return written


def verify_wheel(data: bytes, version: str) -> None:
    dist_info = f"{DIST}-{version}.dist-info"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names_in = archive.namelist()
        if len(names_in) != len(set(names_in)):
            raise ReleaseError("the wheel has a repeated entry")
        record_name = f"{dist_info}/RECORD"
        if record_name not in names_in:
            raise ReleaseError("the wheel has no RECORD for this version")
        listed = {}
        for line in archive.read(record_name).decode("utf-8").splitlines():
            path, digest, size = line.rsplit(",", 2)
            listed[path] = (digest, size)
        for name in names_in:
            if name == record_name:
                continue
            if name not in listed:
                raise ReleaseError(f"{name} is in the wheel but not in its RECORD")
            if record_line(name, archive.read(name)) != f"{name},{listed[name][0]},{listed[name][1]}":
                raise ReleaseError(f"{name} does not match its RECORD")
        missing = set(listed) - set(names_in)
        if missing - {record_name}:
            raise ReleaseError(f"the RECORD lists {sorted(missing)[0]}, which the wheel does not have")
        meta = archive.read(f"{dist_info}/METADATA").decode("utf-8")
        if not re.search(rf"(?m)^Version: {re.escape(version)}$", meta):
            raise ReleaseError("the METADATA of the wheel is of another version")
        init = archive.read(f"{DIST}/__init__.py").decode("utf-8")
        if f'__version__ = "{version}"' not in init:
            raise ReleaseError("urtc_common/__init__.py says another version than the file name")


def verify_all(folder: Path, public_key_hex: str | None = None, key_id: str | None = None) -> list[str]:
    """Check the three files, their hashes and signatures. Returns the lines to print; raises ``ReleaseError`` on the first problem."""
    public_key_hex = public_key_hex or svc.RELEASE_PUBLIC_KEY_HEX
    key_id = key_id or hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]
    wheels = sorted(folder.glob(f"{DIST}-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise ReleaseError(f"expected one wheel in {folder}, found {len(wheels)}")
    version = wheels[0].name[len(DIST) + 1:-len("-py3-none-any.whl")]
    lines = []
    for kind, name in names(version).items():
        path = folder / name
        if not path.is_file():
            raise ReleaseError(f"{name} is missing")
        data = path.read_bytes()
        sha = sha256_of(data)
        recorded = (folder / (name + ".sha256")).read_text(encoding="ascii").split()
        if recorded[0].lower() != sha or (len(recorded) > 1 and recorded[1] != name):
            raise ReleaseError(f"{name} does not match its .sha256")
        try:
            signature = bytes.fromhex((folder / (name + ".sig")).read_text(encoding="ascii").strip())
        except (OSError, ValueError) as error:
            raise ReleaseError(f"{name} has no readable .sig") from error
        message = su.package_message(APP, version, KINDS[kind], sha, len(data))
        if not su.ed25519_verify(bytes.fromhex(public_key_hex), message, signature):
            raise ReleaseError(f"the signature of {name} is not valid for key {key_id}")
        if kind == "wheel":
            verify_wheel(data, version)
        if kind == "header" and b"GENERATED" not in data[:600]:
            raise ReleaseError("the header does not say that it is generated")
        lines.append(f"VERIFY=PASS {name} sha256 {sha} key_id {key_id}")
    with zipfile.ZipFile(wheels[0]) as archive:
        if archive.read(f"{DIST}/data/urtc_can_ids.h") != (folder / "urtc_can_ids.h").read_bytes():
            raise ReleaseError("the header inside the wheel is not the header of the release")
    return lines


def smoke(wheel: Path) -> str:
    """Unpack the wheel in an empty folder and run the shared vectors from there, with an interpreter that ignores the environment."""
    with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as work:
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(folder)
        code = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "import urtc_common, pathlib\n"
            "from urtc_common import specdata, cli\n"
            "assert pathlib.Path(urtc_common.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())\n"
            "assert specdata.path('header').is_file() and specdata.load_spec()['protocol_version'] >= 1\n"
            "assert specdata.path('vectors').resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())\n"
            "raise SystemExit(cli.main(['conformance']))\n"
        )
        result = subprocess.run([sys.executable, "-I", "-c", code, folder], capture_output=True, text=True, cwd=work)
        if result.returncode != 0:
            raise ReleaseError(f"the installed wheel failed: {result.stdout.strip()} {result.stderr.strip()}")
        return "SMOKE=PASS " + result.stdout.strip().splitlines()[-1]


def reproduce(root: Path = ROOT) -> str:
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first = build_all(Path(a), None, root)
        second = build_all(Path(b), None, root)
        for kind in first:
            if first[kind].read_bytes() != second[kind].read_bytes():
                raise ReleaseError(f"{first[kind].name} is not the same in two builds")
        return "REPRODUCIBLE=PASS " + " ".join(f"{p.name}:{sha256_of(p.read_bytes())[:12]}" for p in first.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.add_argument("--key")
    b.add_argument("--no-sign", action="store_true", help="write the files and their .sha256 only")
    v = sub.add_parser("verify")
    v.add_argument("folder")
    s = sub.add_parser("smoke")
    s.add_argument("folder")
    sub.add_parser("reproduce")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            seed = None if args.no_sign else mup.read_seed(mup.key_path(args.key))
            if seed is not None and hashlib.sha256(mup.public_key_of(seed)).hexdigest()[:16] != svc.RELEASE_KEY_ID:
                print(f"RELEASE_FILES=FAIL the key signs as another key than the one the programs trust ({svc.RELEASE_KEY_ID})", file=sys.stderr)
                return 1
            if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip():
                print("RELEASE_FILES=WARN the working tree has uncommitted changes: the wheel is built from the files on disk, the archive from the tracked ones",
                      file=sys.stderr)
            for kind, path in build_all(Path(args.out), seed).items():
                print(f"RELEASE_FILES=PASS {path}")
            if seed is not None:
                print(f"key_id: {svc.RELEASE_KEY_ID}")
            return 0
        if args.command == "verify":
            print("\n".join(verify_all(Path(args.folder))))
            return 0
        if args.command == "smoke":
            print(smoke(next(Path(args.folder).glob(f"{DIST}-*-py3-none-any.whl"))))
            return 0
        print(reproduce())
        return 0
    except (ReleaseError, su.UpdateError, StopIteration, OSError) as error:
        print(f"RELEASE_FILES=FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
