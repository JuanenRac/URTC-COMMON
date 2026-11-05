# Testing strategy: property-based tests and mutation checks of the security validators

The decisions that keep an unsigned or foreign firmware image out (the rotation of the signing key, the policy `ed25519_only`, the rollback rules, the parsers of headers and frames) are tested three ways: hand-written cases, shared conformance vectors, and the property-based tests described here.

## Property-based tests

`tests/test_property_validators.py` states rules that must hold for every input and checks them on generated cases. The cases come from a small generator with a fixed seed (`random.Random`), so a run is the same on every machine, nothing is installed to run it, and the whole file takes a few seconds. The rules:

| Module | Rule checked on generated inputs |
| --- | --- |
| `key_rotation` | a fingerprint that is not announced is never accepted; the previous key is valid exactly until the window ends and not one second longer; a window of zero (or less) and a clock that reads before the start accept only the current key; a revoked key is never accepted and a revoked current key leaves nothing trusted; at most two fingerprints, never a repeat; the status parser accepts exactly the 7-byte frames with a known flag set |
| `image_auth` | under `ed25519_only` an image is accepted only with a valid signature of a trusted key, whatever the HMAC result says, whatever bytes the record holds and in whatever combination the keys are given; a signature does not move to another payload, header, counter or hardware id; the rollback counter and the version rules hold for any floor; `hmac_only` never moves the counter; wrong lengths and unknown policies are refused; the default policy is `ed25519_only` |
| `image_header` | the parser never raises, accepts only a header it could have written, and any bit changed inside the header or the payload is seen |
| `frame_layer` | the length and range limits of the rack and sensor frames, the trailing bytes after a frame, a missing or changed byte |

## Mutation checks (local only)

Mutation testing changes the code of a module in small ways (a `<` for a `<=`, a constant, a condition) and runs the tests: a change the tests do not notice is a behaviour nobody checks. It is a measure of the tests, not a part of the build: it is **not** run in the CI, and a run takes several minutes. To repeat it, in a throwaway virtual environment (mutmut needs a runner that maps every failing exit code to 1, because mutmut 2 counts only the exit code 1 as a kill):

```
python -m pip install "mutmut<3" pytest
mutmut run --paths-to-mutate src/urtc_common/key_rotation.py --runner "python runner.py tests/test_property_validators.py tests/test_key_rotation.py"
mutmut results
```

| Module | Mutants | Killed by the first run | Killed after the added tests | Left |
| --- | --- | --- | --- | --- |
| `key_rotation.py` | 88 | 70 (79.5 %) | 85 (96.6 %) | 3, none relevant |
| `image_auth.py` | 100 | 95 (95 %) | 98 (98 %) | 2, none relevant |

The tests added after the first run check the fields of the status frame one flag at a time, the clamp of the seconds left, the defaults and immutability of a `Rotation`, the behaviour of `hmac_only` with a stale record, the reinstall of the same version and the error texts. The mutants that remain are equivalent changes (a `<=` for a `<` on a window of zero gives the same answer, a slice that ends past the end of the payload, the starting value of a variable that every branch overwrites) or a change to a type annotation, which nothing at run time reads.

## Builds on this PC

A test or a tool that needs a C compiler, WSL, Cargo, Gradle or an npm build asks `urtc_common.local_build` first. It may build on a CI runner (`CI` or `GITHUB_ACTIONS` set) or when the developer sets `ALLOW_LOCAL_BUILD=1`; anywhere else it reports that the build was skipped (never that it passed) and says how to allow it. The file is one text for the family: `tools/vendor_copy.py sync TARGET --set local_build` copies it and `check` keeps the copies honest.
