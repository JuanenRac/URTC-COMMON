# Evidence records (`urtc-evidence/1`)

The flasher writes an update report, the tester a result record and the updater a line of its install log. Each says the same kind of thing in its own words: which tool did what, when, to which board or project, over which transport, with which files, and how it ended. `urtc-evidence/1` is one shape for all of them, so a record can be attached to a build, a ticket or a hardware-validation report and read the same way whichever program wrote it.

The description for other languages is `spec/evidence.schema.json`; the code is `src/urtc_common/evidence.py`. A test holds the two together.

## Fields

| Field | Meaning |
|---|---|
| `format` | always `urtc-evidence/1` |
| `kind` | `flash`, `test`, `install` or `session` |
| `outcome` | `pass`, `fail`, `error` or `skipped` |
| `timestamp_utc` | ISO 8601 time with `Z` or an offset |
| `tool`, `tool_version` | the program that wrote the record |
| `operator` | the user name, when known |
| `subject` | what it was done to: `name`, `hardware_id` (`0x` and eight capital hexadecimal digits), `version_before`, `version_after`, `commit_before`, `commit_after`, `key_id` |
| `transport` | how the board was reached: `adapter`, `bus`, `bitrate` |
| `artifacts` | the files involved, each with `name`, `sha256` and, when known, `bytes` |
| `detail` | a short text (500 characters at most) |
| `evidence_sha256` | SHA-256 of the record without this field, as compact JSON with the keys sorted |

A field that is not known is left out, never written empty. A field that is not in the table, an unknown `kind` or `outcome` and a malformed hash make the record invalid: a reader never guesses.

## What the digest means

`evidence_sha256` shows that the record was not changed after it was written. It does not say who wrote it. A program that needs that signs the record with the key of the user (`record_signing`) and keeps the signature next to it.

## Converting the records that exist

`from_update_report` (flasher), `from_result_record` (tester) and `from_updater_line` (updater) build a record from what those programs already write; they change nothing in the originals. `verify` returns the list of problems of a record, empty when it is well formed and its digest matches.

## Listing the records of a folder

`evidence_history.py` reads the `.json` and `.jsonl` files of a folder and returns the records it finds, newest first, each one with the problems `verify` reports (empty when it passes). A file that is not JSON, a line that is not a record and a record of another format are listed as not valid, with what is wrong; nothing is changed on disk.

**Files that are not evidence.** The folder of the evidence also holds two kinds of file that the programs write and that are not evidence: the update report of the flasher (`urtc_update_report_<time>.json`) and the result record of the tester (`<name>_<time>.json`). They are told apart by their **shape**, never by their name (`other_kind`): the exact set of keys of the report or of the record and the type of its main values, and a record that says it is evidence (`format` or `evidence_sha256`) is always checked as evidence. They come back as entries with `other` set (`update_report` or `result_record`), without problems; they are **counted apart** (`summary()` has `others` and `other_kinds`; the numbers of records, valid and not valid are evidence only), **listed by name and type** (`others_of`, the `others` list of the JSON, a section of the text, of the window and of the report) and are never shown as NOT VALID and never left out. JSON of any other shape stays NOT VALID. The checks of these two kinds (the digest of the update report, the hash of the log of a result record) belong to the program that wrote them; the history only says they are there. The CSV has the fixed columns of the evidence, so it lists the other records on the standard error output instead. The programs show the history in two ways:

* **The History window**, the same in URTC-FLASHER, URTC-TESTER and URTC-UPDATER: `evidence_history_qt.py` (the Qt object), `qml/EvidenceHistoryDialog.qml` (the window) and `evidence_history_strings.py` (its texts in the eight languages, with the Portuguese of Portugal). It lists the kind, the result, the tool, the board, the versions and whether each record still passes its check; it can be filtered by result and by text and reduced to the records that fail, reads the folder again each time it opens, shows at most 500 rows (and says how many there are) and changes nothing. A program carries it with `tools/vendor_copy.py sync TARGET --set history_qt --set history_qml`.
* **The command line**: `urtc_flasher.py --history FOLDER [--json]`, `urtc_tester.py --headless history [FOLDER] [--json]` and `urtc-updater --cli evidence --history FOLDER [--json]` list the same records, print a summary (counts by result and kind, first and last time) and exit with status 1 when any record is not valid (the other records never make it fail: with only valid evidence and other records the status is 0). None of them opens a bus.

URTC-WEB-STUDIO reads the same records in its Evidence tab, from files the person chooses, with the same rules and the same digest.

## The report

`evidence_report.py` turns the records of a folder into a report that can be attached to a build or a hardware-validation file: one HTML page (`to_html`) or one PDF (`to_pdf`); `render(entries, "html"|"pdf", language)` returns the bytes. Its texts are in `evidence_report_strings.py` in the eight languages, with the Portuguese of Portugal.

* **Every record is listed.** A summary (records, valid, not valid, by result, by kind, by origin, first and last time), a table with one row per record and a section per record with its fields. A record that fails its check (edited after it was written, not JSON, another format) is marked NOT VALID in the table and in its section, with what is wrong; nothing is left out. The other records (see above) are counted in the summary on their own line and listed by name and type in a section of their own, after the records.
* **The origin is stated.** SIMULATED when the adapter of the record is a simulation or its detail says the bus was simulated; REPLAY OF A TRACE for a recorded trace; REAL ADAPTER when another adapter is named; NOT STATED when the record names none. REAL ADAPTER only means that no simulation is stated: it does not mean a board was validated.
* **What the digest proves.** A matching `evidence_sha256` shows that the record was not changed after it was written; it does not say who wrote it. The report says so on its first page.
* **The HTML is self-contained.** No script, no external resource, a content policy that forbids both, plain tables with captions and header cells, a language attribute. Every text that comes from a record is escaped, and control and direction characters are replaced, so a hostile record cannot inject markup.
* **The PDF is written by the module itself** (PDF 1.4, A4, no compression, no date). Western text is set in the standard font Courier, with no font inside. Chinese and Japanese (and any text with a character Courier cannot show) are set in a SUBSET of Noto Sans CJK that the file embeds as a Type0 / CIDFontType2 font (Identity-H, `CIDToGIDMap /Identity`, a `ToUnicode` map so the text can be selected, copied and searched): the Simplified Chinese forms for Chinese, the Japanese forms for Japanese. A character the subset lacks is printed as a hollow square (U+25A1) and the report says, near its top, how many different characters were replaced: never a silent `?`. The HTML keeps every character, and can be printed from a browser when a richer PDF is wanted. The PDF measures the glyphs and wraps by width; the same records give the same bytes.
* **The same records give the same bytes.** The report reads no clock; it prints only the times the records carry, in the order of `evidence_history.select`.

The History window has a Report button that writes `evidence_report.html` and `evidence_report.pdf` in the folder, with every record of it (the filters of the window do not apply); `urtc_tester.py --headless report --evidence-dir D --out FILE [--format html|pdf] [--language L]` does the same without a window. A program carries the module with `tools/vendor_copy.py sync TARGET --set report` (the set `history_qt` includes it).

## The font of the PDF

`src/urtc_common/evidence_report_fonts.py` holds the two font subsets as data (about 0.73 MB for the Chinese one and 0.59 MB for the Japanese one, deflated; the PDF embeds only the one it needs, so a Chinese report is about 0.74 MB and a Japanese one about 0.6 MB; Western reports embed no font and stay small). The programs read the module with the standard library only; the tool that makes it is a development tool and is never needed to run them.

* **Source and license:** Noto Sans CJK (Sans, variable TrueType, made static at the default weight) from the official `notofonts/noto-cjk` repository at the commit pinned in `tools/make_report_font.py`, under the **SIL Open Font License 1.1**. The license text is saved next to the data (`src/urtc_common/evidence_report_fonts_OFL.txt`) and copied with it into every program that carries the report, and each of them names it in its `NOTICE`. The subset is a modified version of the font and keeps the license of the font; the program code stays GPL-3.0-or-later. The font has a reserved name ("Source") that the subset does not use.
* **What the subset holds:** ASCII, Latin-1, the usual punctuation and symbols, the CJK punctuation, the kana, the full-width forms, every character of the text catalogs of the report and of the history window in the eight languages, and the first-level kanji or hanzi of the national standards (JIS X 0208 level 1 for the Japanese subset, GB 2312 level 1 for the Chinese one): the everyday words of an operator name or a note. Rarer characters are replaced by the square and counted. A test holds that every catalog character is in both subsets.
* **How to regenerate it (reproducible):** download `Sans/Variable/TTF/NotoSansCJKsc-VF.ttf`, `NotoSansCJKjp-VF.ttf` and `Sans/LICENSE` from the pinned commit into an empty folder outside the repository, create a virtual environment with `pip install fonttools`, and run `python tools/make_report_font.py --font-dir FOLDER` (`--measure` only prints the sizes). The tool checks the SHA-256 of every downloaded file against the pinned values, fails if a catalog character is missing from the font, and writes the module and the license text. Run it again whenever a text of `evidence_report_strings.py` or `evidence_history_strings.py` gains a character.
