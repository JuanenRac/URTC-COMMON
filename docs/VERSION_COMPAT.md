# The version rule for an image without a patch number

A flasher that predates the PATCH number sends only the minor. When the installed version has a patch, the bootloaders read such an image as patch 0 and
refuse it as older (the strict rule). Until now the only way to relax this was a build option. This page describes a second way, kept in the board and changed
by a signed command. **It is off in the builds**: a bootloader built without it behaves exactly as before and does not read anything described here.

## The modes

| Mode | Value | An image without a patch against an installed patch of the same major.minor |
|---|---|---|
| nothing stored | 0 | the rule of the build, which is strict by default |
| strict | 1 | refused as older |
| accept_patchless | 2 | accepted |

Major and minor still decide, two known patches are still compared, and the signed rollback counter still refuses anything below its floor. A damaged or
unreadable record reads as nothing stored.

## The command

On `0x7EE`, 12 frames of 8 bytes whose first byte is `0x40` to `0x4B` (the serial command uses `0x00` to `0x0B`), carrying 84 bytes, big-endian:

    target (4) | key id (8) | mode (4) | counter (4) | Ed25519 signature (64)

`target` is the serial the head answers with; any other head stays silent. The signature covers 44 bytes: `URTC-VERCOMPAT-1` | unique ID of the head (12) |
mode (4) | counter (4) | key id (8). The signing key must be one the trust table of the bootloader holds. The counter must be higher than the stored one, so
a command cannot be sent twice and an older one cannot undo a newer one. A command signed for the serial number is not valid here and the other way round.

A frame whose first byte is `0x60` asks for the state and changes nothing.

## The answer

On `0x7EF`, 8 bytes: `0xC5` | status | mode in force | flags (bit 0: a mode is stored) | stored counter (4, big-endian). The statuses are those of
`urtc_vc_status_t` (ok, bad signature, unknown key, replay, bad mode, flash failed, disabled, busy). A bootloader without the feature answers nothing.

## The expansion slave

The slave has no signature verifier and keeps no setting. The head keeps it and, when it relays the end of a slave update with `accept_patchless` in force,
writes `0xA5` to the register `0x0D` of the slave bootloader just before. The slave forgets it at every start of an update.

## Signing

`urtc_common.version_compat.make_command(seed, uid, serial, mode, counter)` builds the command from a private seed that the caller reads from a file of its
own. No key is part of this repository except the public development key that only a bench bootloader trusts.
