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

`evidence_history.py` reads the `.json` and `.jsonl` files of a folder and returns the records it finds, newest first, each one with the problems `verify` reports (empty when it passes). A file that is not JSON, a line that is not a record and a record of another format are listed as not valid, with what is wrong; nothing is changed on disk. The programs show it in two ways:

* **The History window**, the same in URTC-FLASHER, URTC-TESTER and URTC-UPDATER: `evidence_history_qt.py` (the Qt object), `qml/EvidenceHistoryDialog.qml` (the window) and `evidence_history_strings.py` (its texts in the eight languages, with the Portuguese of Portugal). It lists the kind, the result, the tool, the board, the versions and whether each record still passes its check; it can be filtered by result and by text and reduced to the records that fail, reads the folder again each time it opens, shows at most 500 rows (and says how many there are) and changes nothing. A program carries it with `tools/vendor_copy.py sync TARGET --set history_qt --set history_qml`.
* **The command line**: `urtc_flasher.py --history FOLDER [--json]`, `urtc_tester.py --headless history [FOLDER] [--json]` and `urtc-updater --cli evidence --history FOLDER [--json]` list the same records, print a summary (counts by result and kind, first and last time) and exit with status 1 when any record is not valid. None of them opens a bus.

URTC-WEB-STUDIO reads the same records in its Evidence tab, from files the person chooses, with the same rules and the same digest.
