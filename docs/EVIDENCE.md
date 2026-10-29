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
