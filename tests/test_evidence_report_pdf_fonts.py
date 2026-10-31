# =============================================================================
# URTC-COMMON - tests/test_evidence_report_pdf_fonts.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The PDF of the evidence report with an embedded font: Chinese and Japanese text, the structure of the file, the same bytes for the same input."""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

from urtc_common import evidence, evidence_history, evidence_report
from urtc_common import evidence_history_strings as hist
from urtc_common import evidence_report_fonts as fonts
from urtc_common import evidence_report_strings as st

HERE = Path(__file__).resolve().parent
SHA = "e" * 64
CHINESE_NAME = "测试板 主控制器"
JAPANESE_NAME = "試験基板 ステータス"


def record(when: str, name: str, *, detail: str = "", operator: str = "") -> dict:
    extra = {"operator": operator} if operator else {}
    return evidence.build(kind="test", outcome="pass", timestamp_utc=when, tool="URTC-TESTER", tool_version="0.4.4", detail=detail, **extra,
                          subject={"name": name, "version_before": "0.3.9", "version_after": "0.4.1"}, artifacts=[{"name": "run.log", "sha256": SHA, "bytes": 10}])


def entries_of(tmp_path: Path, **records: dict):
    for name, content in records.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")
    return evidence_history.load_folder(tmp_path)


class Pdf:
    """A small reader for the files this module writes: objects by number, streams, the glyph ids printed and the ToUnicode map."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        start = int(re.search(rb"startxref\n(\d+)\n", data).group(1))   # type: ignore[union-attr]
        assert data[start:start + 4] == b"xref"
        table = data[start:].split(b"\n")
        count = int(table[1].split()[1])
        self.offsets = [int(line.split()[0]) for line in table[3:2 + count]]
        self.size = count

    def body(self, number: int) -> bytes:
        offset = self.offsets[number - 1]
        assert self.data[offset:].startswith(b"%d 0 obj\n" % number)
        return self.data[offset:self.data.index(b"\nendobj\n", offset)].split(b"\n", 1)[1]

    def stream(self, number: int) -> tuple[bytes, bytes]:
        body = self.body(number)
        head, _, rest = body.partition(b"\nstream\n")
        length = int(re.search(rb"/Length (\d+)", head).group(1))   # type: ignore[union-attr]
        assert rest[length:] == b"\nendstream"
        return head, rest[:length]

    def objects_with(self, needle: bytes) -> list[int]:
        return [n for n in range(1, self.size) if needle in self.body(n)[:400]]

    def unicode_map(self) -> dict[int, str]:
        number = int(re.search(rb"/ToUnicode (\d+) 0 R", self.body(3)).group(1))   # type: ignore[union-attr]
        _, data = self.stream(number)
        blocks = re.findall(rb"beginbfchar\n(.*?)\nendbfchar", data, re.S)
        return {int(g, 16): bytes.fromhex(u.decode()).decode("utf-16-be") for block in blocks for g, u in re.findall(rb"<([0-9A-F]{4})> <([0-9A-F]+)>", block)}

    def text(self) -> str:
        mapping = self.unicode_map()
        out = []
        for number in range(1, self.size):
            body = self.body(number)
            if b"/Type /Page " in body and b"/Contents" in body:
                _, content = self.stream(int(re.search(rb"/Contents (\d+) 0 R", body).group(1)))   # type: ignore[union-attr]
                for line in content.split(b"\n"):
                    found = re.match(rb"<([0-9A-F]*)> (?:'|Tj)$", line)
                    if found:
                        hexed = found.group(1).decode()
                        out.append("".join(mapping[int(hexed[i:i + 4], 16)] for i in range(0, len(hexed), 4)))
        return "\n".join(out)


def squeezed(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_chinese_text_can_be_read_back_from_the_pdf(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME, detail="结果正常"))
    pdf = Pdf(evidence_report.to_pdf(entries, "chinese"))
    text = squeezed(pdf.text())
    assert squeezed(st.STRINGS["chinese"]["ER_TITLE"]) in text and squeezed(CHINESE_NAME) in text and "结果正常" in text
    assert "?" not in pdf.text() and "□" not in pdf.text()


def test_japanese_text_can_be_read_back_from_the_pdf(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", JAPANESE_NAME, detail="結果は正常です"))
    pdf = Pdf(evidence_report.to_pdf(entries, "japanese"))
    text = squeezed(pdf.text())
    assert squeezed(st.STRINGS["japanese"]["ER_TITLE"]) in text and squeezed(JAPANESE_NAME) in text and "結果は正常です" in text
    assert "?" not in pdf.text() and "□" not in pdf.text()


def test_the_structure_of_the_pdf_with_a_font_is_sound(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME))
    data = evidence_report.to_pdf(entries, "chinese")
    pdf = Pdf(data)
    assert data.startswith(b"%PDF-1.4\n") and data.rstrip().endswith(b"%%EOF")
    for number in range(1, pdf.size):
        pdf.body(number)                       # every offset of the xref points at its object
    type0 = pdf.body(3)
    assert b"/Subtype /Type0" in type0 and b"/Encoding /Identity-H" in type0 and b"/DescendantFonts [5 0 R]" in type0
    cid = pdf.body(5)
    assert b"/Subtype /CIDFontType2" in cid and b"/CIDToGIDMap /Identity" in cid and b"/W [" in cid and b"/FontDescriptor 6 0 R" in cid
    assert b"/FontFile2 7 0 R" in pdf.body(6)
    head, packed = pdf.stream(7)
    assert int(re.search(rb"/Length1 (\d+)", head).group(1)) == len(zlib.decompress(packed))   # type: ignore[union-attr]
    assert zlib.decompress(packed)[:4] == b"\x00\x01\x00\x00"                                  # a TrueType font program
    assert b"beginbfchar" in pdf.stream(8)[1]
    widths = dict(re.findall(rb"(\d+) \[(\d+)\]", cid))
    assert widths and set(widths) >= {str(g).encode() for g in pdf.unicode_map()}


def test_the_same_input_gives_the_same_bytes_for_the_pdf_with_a_font(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME), b=record("2026-01-02T10:00:00Z", JAPANESE_NAME))
    for language in ("chinese", "japanese"):
        first = evidence_report.to_pdf(entries, language)
        assert first == evidence_report.to_pdf(list(reversed(entries)), language) == evidence_report.to_pdf(evidence_history.load_folder(tmp_path), language)


def test_every_language_makes_a_pdf_whose_text_reads_back(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", "board-1", operator="Ana"))
    for language in st.LANGUAGES:
        data = evidence_report.to_pdf(entries, language)
        assert data.startswith(b"%PDF-1.4\n")
        if language in ("chinese", "japanese"):
            assert b"/FontFile2" in data and squeezed(st.STRINGS[language]["ER_TITLE"]) in squeezed(Pdf(data).text())
        else:
            assert b"/FontFile2" not in data and b"/BaseFont /Courier" in data and st.STRINGS[language]["ER_TITLE"].encode("cp1252") in data


def test_chinese_and_japanese_text_in_a_western_report_goes_in_the_embedded_font(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME), b=record("2026-01-02T10:00:00Z", "かな", detail="ひらがな"))
    for language in ("english", "portuguese"):
        pdf = Pdf(evidence_report.to_pdf(entries, language))
        text = pdf.text()
        assert squeezed(CHINESE_NAME) in squeezed(text) and "ひらがな" in text
        assert b"/FontFile2" in pdf.data and "□" not in text and "?" not in text


def test_a_character_the_font_lacks_is_a_visible_square_and_the_report_says_so(tmp_path):
    name = "board \U0001F600 \U0001F601 x"
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", name))
    for language in ("chinese", "english"):
        text = Pdf(evidence_report.to_pdf(entries, language)).text()
        assert "board □ □ x" in text
        assert st.text(language, "ER_PDF_SUBST", count=2) in text
        assert "\U0001F600" not in text


def test_no_substitution_note_when_every_character_is_there(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME))
    text = Pdf(evidence_report.to_pdf(entries, "chinese")).text()
    assert st.text("chinese", "ER_PDF_SUBST", count=0) not in text and "□" not in text


def test_a_long_line_is_wrapped_inside_the_page(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME, detail="长" * 400))
    pdf = Pdf(evidence_report.to_pdf(entries, "chinese"))
    glyphs = fonts.font("sc")["glyphs"]
    for line in pdf.text().split("\n"):
        assert sum(glyphs[ord(c)][1] for c in line) <= evidence_report.PDF_WIDTH * 1000 / evidence_report.PDF_SIZE
    assert pdf.text().count("长") == 400


def test_the_size_of_the_pdf_and_of_the_font_data_stays_reasonable(tmp_path):
    entries = entries_of(tmp_path, a=record("2026-01-01T10:00:00Z", CHINESE_NAME))
    assert len(evidence_report.to_pdf(entries, "chinese")) < 1_000_000 and len(evidence_report.to_pdf(entries, "japanese")) < 900_000
    assert sum(len(fonts.font(name)["ttf"]) for name in fonts.NAMES) < 2_000_000


def test_the_subsets_hold_every_character_of_every_catalog_in_every_language():
    needed = {ord(c) for module in (st, hist) for table in module.STRINGS.values() for value in table.values() for c in value if c >= " "}
    for name in fonts.NAMES:
        glyphs = fonts.font(name)["glyphs"]
        assert not sorted(c for c in needed if c not in glyphs), name
        assert fonts.REPLACEMENT in glyphs and glyphs[fonts.REPLACEMENT][0] > 0
        assert ord(" ") in glyphs and ord("A") in glyphs and 0xE9 in glyphs


def test_the_license_of_the_font_travels_with_it():
    text = (HERE.parent / "src" / "urtc_common" / "evidence_report_fonts_OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in text and "notofonts/noto-cjk" in text
    module = (HERE.parent / "src" / "urtc_common" / "evidence_report_fonts.py").read_text(encoding="utf-8")
    assert "SIL Open Font License 1.1" in module and fonts.LICENSE_NAME == "SIL Open Font License 1.1"
