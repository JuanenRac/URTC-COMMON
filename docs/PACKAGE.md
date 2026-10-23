<!--
=============================================================================
URTC-COMMON - docs/PACKAGE.md
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# The specification as an installable package

Each release of URTC-COMMON carries three files, so that anyone who needs the CAN protocol of the tool head can take it without cloning anything. It is not published on PyPI: the files are attached to the release on GitHub, signed by the same Ed25519 key of the releases that signs the update packages of the programs and the firmware.

| File | What it is | For |
|---|---|---|
| `urtc_common-<version>-py3-none-any.whl` | The Python package: frame builders and parsers, the SLCAN codec, the transports, the virtual board, the command line `urtc-common`, and the specification files as data | A Python program or script that speaks to a tool head |
| `urtc_common-<version>.tar.gz` | The source archive: the sources, `spec/`, `generated/`, `conformance/`, `docs/` and the `tools/` that build and check these files | Reading, auditing, rebuilding |
| `urtc_can_ids.h` | The generated C header: identifiers, length rules, offsets, enumerations and magic payloads | Firmware or a C program that does not want Python |

Every file has a `.sha256` and a `.sig` beside it.

## Verify, then install

The signature is checked with the tool of the source archive, which carries the key the programs trust (`RELEASE_KEY_ID` in `src/urtc_common/update_service.py`). Put the three files, their `.sha256` and their `.sig` in one folder, unpack the archive next to it and run:

```text
tar xzf urtc_common-<version>.tar.gz
python urtc_common-<version>/tools/make_release_artifacts.py verify downloads/
```

`VERIFY=PASS` for each of the three files means the hash is the recorded one, the signature is valid for the pinned key, every entry of the wheel is in its `RECORD` with the right hash, and the header inside the wheel is the header of the release. Anything else prints `RELEASE_FILES=FAIL` and the reason; do not install. Then, without the network and without any dependency:

```text
python -m pip install --no-index --no-deps downloads/urtc_common-<version>-py3-none-any.whl
urtc-common --version
urtc-common conformance          # the shared vectors run against the installed package
urtc-common files                # where the specification, the tool table, the C header and the vectors are
```

Python 3.10 or newer. The specification files are inside the package (`urtc_common/data/`); `urtc_common.specdata.path("spec")` returns the one of the installed copy, or the one of a checkout when the package runs from one, and `specdata.load_spec()` reads the specification as a dictionary.

## The C header

`urtc_can_ids.h` has no dependency: copy it into the firmware or add the folder to the include path. It is the same file a checkout keeps in `generated/`, and the same one the wheel carries; `make_release_artifacts.py verify` compares them. Firmware that keeps a copy should record the version of the release it came from and check it again when it takes a newer one (`tools/vendor_copy.py` does that for the repositories of the family).

## Rebuild the files yourself

```text
python tools/make_release_artifacts.py reproduce          # two builds in two folders give the same bytes
python tools/make_release_artifacts.py build --out out/ --no-sign
python tools/make_release_artifacts.py smoke out/         # unpack the wheel apart and run the vectors from it
```

The entries are sorted, their times are fixed, the wheel is stored without compression and the archive is compressed with the same settings every time, so the same checkout gives the same bytes with the same Python and the same zlib. Compare the `.sha256` you build with the one of the release; a different zlib can change the archive and nothing else, in which case compare the unpacked contents. The wheel is built from the files on disk and the archive from the files the repository tracks: build from a clean checkout of the tag.

## Publish a release (the owner)

1. The version is already raised and the changelog written (this tool never changes a version).
2. The checks of the repository pass (`URTC_CI=1 python tools/ci_validate.py`) and the CI of the commit to release is green.
3. `python tools/make_release_artifacts.py build --out out/` signs with the key of the releases (`--key`, `URTC_RELEASE_KEY` or `~/.urtc-keys/urtc_release_ed25519.pem`). It refuses a key other than the one the programs trust and never prints the key.
4. `python tools/make_release_artifacts.py verify out/` and `python tools/make_release_artifacts.py smoke out/`.
5. Attach the nine files of `out/` to the GitHub release of the tag, with the `key_id:` line printed by the build in the notes.
