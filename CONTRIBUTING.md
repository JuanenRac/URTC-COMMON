# Contributing to URTC-COMMON 🧩

This repository holds the CAN protocol of the tool head as data, and the code and vectors that follow from it. A contribution that makes the specification more accurate, or an implementation more faithful to it, is the most useful kind.

## Technology Stack
- **Specification and vectors**: JSON, with a JSON Schema.
- **Generators and package**: Python 3.10+, standard library only at run time; pytest and jsonschema for the tests; pyserial and python-can are optional and only needed by the transports that use them.
- **TypeScript output**: checked by running the vectors through Node 22.18 or newer (optional).

## Guidelines
1. **The specification is the source.** Change `spec/can_protocol.json`, run `python tools/generate_constants.py` and `python tools/make_conformance.py`, and commit the result. Never edit a generated file by hand (`--check` fails on it).
2. **Say what an implementation really does.** `implemented_by`, `client_names` and `firmware_accepts_dlc` are checked against the text of the other repositories by `tests/test_siblings.py`; if you change one, the test says whether the claim is true.
3. **Do not add behaviour to a client here.** This repository describes and checks; the other repositories adopt it on their own schedule (see `docs/MIGRATION.md`). An identifier that no host implements stays recorded as such until one does.
4. **A safety limit is a refusal.** Builders reject an out-of-range value; they never clamp it into a different, valid command.
5. **Eight languages.** The README exists in English, Spanish, French, Italian, German, Chinese, Japanese and European Portuguese, with the same sections and links; `tools/ci_validate.py` compares them.
6. **Nothing private in public files.** No dates, no names of private notes, no tracking codes, no secrets, no addresses of a real installation.
7. **Tests.** `python -m pytest tests -q` must pass. Use `build-test.sh` / `build-test.bat` to check without changing the version; `build.sh` / `build.bat` raise it.
