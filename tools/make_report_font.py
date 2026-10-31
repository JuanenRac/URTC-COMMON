#!/usr/bin/env python3
# =============================================================================
# URTC-COMMON - tools/make_report_font.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Generate ``src/urtc_common/evidence_report_fonts.py``: the font subsets the PDF of the evidence report embeds for Chinese and Japanese.

A DEVELOPMENT tool: it needs ``fonttools`` (``pip install fonttools``, in a virtual environment of its own), which the programs never need at run time. The result,
one Python module with the subsets as data, is committed; the programs only read that module (standard library only).

Source of the fonts (reproducible): the official ``notofonts/noto-cjk`` repository, variable fonts ``Sans/Variable/TTF/NotoSansCJKsc-VF.ttf`` (Simplified Chinese
forms) and ``NotoSansCJKjp-VF.ttf`` (Japanese forms), SIL Open Font License 1.1, at the commit pinned below. Download them (and ``Sans/LICENSE``) into an
EMPTY folder, outside this repository::

    https://raw.githubusercontent.com/notofonts/noto-cjk/<COMMIT>/Sans/Variable/TTF/NotoSansCJKsc-VF.ttf
    https://raw.githubusercontent.com/notofonts/noto-cjk/<COMMIT>/Sans/Variable/TTF/NotoSansCJKjp-VF.ttf
    https://raw.githubusercontent.com/notofonts/noto-cjk/<COMMIT>/Sans/LICENSE

and run::

    python tools/make_report_font.py --font-dir <that folder>            # writes the module and the license text
    python tools/make_report_font.py --font-dir <that folder> --measure  # only prints the sizes

The tool checks the SHA-256 of each downloaded file against the pinned values, makes the font static (default weight), keeps only the glyphs listed below, and
stores each subset deflate-compressed (the PDF embeds those bytes as they are, so the same module always gives the same PDF).

Glyphs kept: ASCII, Latin-1, the usual punctuation and symbols, the CJK punctuation, the kana, the full-width forms, every character of the text catalogs of the
report and of the history window in the eight languages, and the kanji/hanzi of the first level of the national standards (JIS X 0208 level 1 for the Japanese
subset, GB 2312 level 1 for the Chinese one), which cover the everyday words of operator names and notes. A character that is not in the subset is printed by the
report as a visible replacement and the report says so.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

COMMIT = "f8d157532fbfaeda587e826d4cd5b21a49186f7c"
SOURCES = {
    "sc": ("NotoSansCJKsc-VF.ttf", "990c807e79c25662a5a9ecf7f971baeb2bf2eab9a559e5ecf15cdfdb8561d21f"),
    "jp": ("NotoSansCJKjp-VF.ttf", "240c9b83bf7b386edbae39995ae7e068ed4583f484d92e4a74c34158b5f27b1a"),
}
LICENSE_FILE = ("LICENSE", "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2")
REPLACEMENT = 0x25A1   # WHITE SQUARE: what the report prints for a character the subset lacks
OUT_MODULE = ROOT / "src" / "urtc_common" / "evidence_report_fonts.py"
OUT_LICENSE = ROOT / "src" / "urtc_common" / "evidence_report_fonts_OFL.txt"

PUNCTUATION = (
    list(range(0x20, 0x7F)) + list(range(0xA0, 0x100))
    + list(range(0x2010, 0x2028)) + [0x2030, 0x2032, 0x2033, 0x2039, 0x203A, 0x203B, 0x20AC, 0x2122]
    + list(range(0x2190, 0x219A)) + list(range(0x2200, 0x2210)) + [0x2212, 0x2260, 0x2264, 0x2265]
    + list(range(0x2500, 0x2504)) + [0x25A0, REPLACEMENT, 0x25B2, 0x25B6, 0x25BC, 0x25C0, 0x25CB, 0x25CF, 0x2713, 0x2717, 0xFFFD]
    + list(range(0x3000, 0x3040)) + list(range(0x3041, 0x3097)) + [0x3099, 0x309A, 0x309B, 0x309C, 0x309D, 0x309E]
    + list(range(0x30A0, 0x3100)) + list(range(0xFF01, 0xFF5F)) + list(range(0xFF61, 0xFFA0))
)


def catalog_characters() -> set[int]:
    """Every character of the text catalogs the report prints, in every language."""
    from urtc_common import evidence_history_strings as history
    from urtc_common import evidence_report_strings as report
    found: set[int] = set()
    for module in (history, report):
        for table in module.STRINGS.values():
            for value in table.values():
                found.update(ord(c) for c in value)
    return {c for c in found if c >= 0x20}


def level_one(codec: str, first: int, last: int) -> set[int]:
    """The characters of the first level of a national standard, decoded with the codec of the standard library."""
    found: set[int] = set()
    for lead in range(first, last + 1):
        for trail in range(0x40, 0xFF):
            try:
                char = bytes([lead, trail]).decode(codec)
            except UnicodeDecodeError:
                continue
            if len(char) == 1:
                found.add(ord(char))
    return found


def wanted(kind: str) -> set[int]:
    base = set(PUNCTUATION) | catalog_characters()
    if kind == "sc":
        return base | level_one("gb2312", 0xB0, 0xD7)    # rows 16-55 of GB 2312: level 1 (3755 hanzi)
    return base | level_one("shift_jis", 0x88, 0x98)    # JIS X 0208 level 1 kanji (2965), lead bytes 0x88-0x98 (partly level 2 at 0x98)


def build(path: Path, characters: set[int]) -> tuple[bytes, dict[int, tuple[int, int]], str]:
    """The static subset as TrueType bytes, the map character -> (glyph id, advance in 1/1000 em), and the font name."""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(str(path))
    defaults = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
    font = instancer.instantiateVariableFont(font, defaults, inplace=False)
    cmap = font.getBestCmap()
    keep = sorted(c for c in characters if c in cmap)
    options = subset.Options()
    options.hinting = False
    options.glyph_names = False
    options.notdef_outline = True
    options.layout_features = []
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    options.name_languages = [0x409]
    options.legacy_kern = False
    options.drop_tables += ["GSUB", "GPOS", "GDEF", "vhea", "vmtx", "STAT", "BASE", "DSIG", "MVAR", "HVAR", "avar", "fvar", "gvar", "VVAR", "cvar"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=keep)
    subsetter.subset(font)
    font.recalcTimestamp = False
    from io import BytesIO
    buffer = BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    check = TTFont(BytesIO(data))
    order = check.getGlyphOrder()
    index = {name: number for number, name in enumerate(order)}
    mapping = {code: (index[name], round(check["hmtx"][name][0] * 1000 / check["head"].unitsPerEm)) for code, name in check.getBestCmap().items()}
    family = check["name"].getDebugName(1) or "?"
    return data, mapping, family


def wrap_b64(data: bytes, width: int = 100) -> str:
    text = base64.b64encode(data).decode("ascii")
    return "\n".join('    "' + text[i:i + width] + '"' for i in range(0, len(text), width))


def render(fonts: dict[str, tuple[bytes, dict[int, tuple[int, int]], str]], license_text: str) -> str:
    try:
        from fontTools import version as tools_version
    except ImportError:   # pragma: no cover - checked earlier
        tools_version = "unknown"
    head = f'''# =============================================================================
# URTC-COMMON - src/urtc_common/evidence_report_fonts.py
# GENERATED by tools/make_report_font.py - do not edit by hand.
# The font data below is a SUBSET of Noto Sans CJK (SIL Open Font License 1.1; the text is in evidence_report_fonts_OFL.txt)
# Copyright 2014-2021 Adobe (http://www.adobe.com/); the subset is generated with fonttools {tools_version}.
# The program code of URTC-COMMON is GPL-3.0-or-later; this font data keeps the license of the font.
# =============================================================================
"""Font subsets for the PDF of the evidence report (Chinese and Japanese), as data.

``FONTS[name]`` has ``family`` (the font family), ``ttf`` (the deflate-compressed TrueType subset, embedded in the PDF as it is), ``length`` (its size once
inflated), ``glyphs`` (character code -> (glyph id, advance in 1/1000 em)) and ``replacement`` (the character printed for one the subset lacks).
Source: github.com/notofonts/noto-cjk at commit {COMMIT}. Standard library only.
"""
from __future__ import annotations

import base64
import json
import zlib
from functools import lru_cache
from typing import Any

SOURCE_COMMIT = "{COMMIT}"
LICENSE_NAME = "SIL Open Font License 1.1"
REPLACEMENT = 0x{REPLACEMENT:X}
'''
    body = []
    for name, (data, mapping, family) in sorted(fonts.items()):
        packed = zlib.compress(data, 9)
        table = json.dumps({str(code): [gid, adv] for code, (gid, adv) in sorted(mapping.items())}, separators=(",", ":"))
        table_packed = zlib.compress(table.encode("ascii"), 9)
        body.append(f'''
_{name.upper()}_FAMILY = {family!r}
_{name.upper()}_LENGTH = {len(data)}
_{name.upper()}_TTF = (
{wrap_b64(packed)}
)
_{name.upper()}_GLYPHS = (
{wrap_b64(table_packed)}
)
''')
    tail = '''

def _load(family: str, length: int, ttf: str, glyphs: str) -> dict[str, Any]:
    raw = json.loads(zlib.decompress(base64.b64decode(glyphs)).decode("ascii"))
    return {
        "family": family, "length": length, "ttf": base64.b64decode(ttf), "replacement": REPLACEMENT,
        "glyphs": {int(code): (int(pair[0]), int(pair[1])) for code, pair in raw.items()},
    }


@lru_cache(maxsize=None)
def font(name: str) -> dict[str, Any]:
    """The subset ``sc`` (Simplified Chinese forms) or ``jp`` (Japanese forms); ``KeyError`` for another name."""
    if name == "sc":
        return _load(_SC_FAMILY, _SC_LENGTH, _SC_TTF, _SC_GLYPHS)
    if name == "jp":
        return _load(_JP_FAMILY, _JP_LENGTH, _JP_TTF, _JP_GLYPHS)
    raise KeyError(name)


NAMES = ("sc", "jp")
'''
    return head + "".join(body) + tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--font-dir", required=True, help="the empty folder with the downloaded fonts and LICENSE")
    parser.add_argument("--measure", action="store_true", help="only print the sizes")
    args = parser.parse_args()
    folder = Path(args.font_dir)
    try:
        import fontTools  # noqa: F401
    except ImportError:
        print("make_report_font: fonttools is needed (pip install fonttools, in a virtual environment)", file=sys.stderr)
        return 2
    for name, expected in [*SOURCES.values(), LICENSE_FILE]:
        file = folder / name
        if not file.is_file():
            print(f"make_report_font: {file} is missing", file=sys.stderr)
            return 2
        found = hashlib.sha256(file.read_bytes()).hexdigest()
        if found != expected:
            print(f"make_report_font: {name} has SHA-256 {found}, expected {expected}", file=sys.stderr)
            return 2
    fonts = {}
    for kind, (name, _digest) in SOURCES.items():
        data, mapping, family = build(folder / name, wanted(kind))
        fonts[kind] = (data, mapping, family)
        print(f"{kind}: {family}: {len(mapping)} characters, {len(data)} bytes, {len(zlib.compress(data, 9))} bytes deflated")
        missing = sorted(c for c in catalog_characters() if c not in mapping)
        if missing:
            print(f"make_report_font: {kind} lacks catalog characters: {[hex(c) for c in missing]}", file=sys.stderr)
            return 1
    if args.measure:
        return 0
    license_text = (folder / LICENSE_FILE[0]).read_text(encoding="utf-8")
    OUT_MODULE.write_text(render(fonts, license_text), encoding="utf-8", newline="\n")
    OUT_LICENSE.write_text(
        "Noto Sans CJK (subset embedded in the PDF of the evidence report)\n"
        f"Source: https://github.com/notofonts/noto-cjk at commit {COMMIT} (Sans/Variable/TTF, Sans/LICENSE)\n"
        "Copyright 2014-2021 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'.\n"
        "The subset is a modified version of the font (static instance, reduced glyph set); it is distributed under the same license.\n\n"
        + license_text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT_MODULE.name} ({OUT_MODULE.stat().st_size} bytes) and {OUT_LICENSE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
