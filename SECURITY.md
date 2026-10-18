# Security Policy 🔒 (URTC-COMMON)

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x  | ✅ Yes             |

## Reporting a Vulnerability

**CRITICAL: Do not report safety-critical vulnerabilities through public GitHub issues.**

This repository describes the CAN protocol of the tool head and carries code that builds and parses its frames and talks to a CAN adapter. What a report here can be about:

1. **A specification entry that is unsafe or false**, for example a limit, a gate or a magic payload that does not match the firmware, or a command that the specification lets a host send without the protection the firmware relies on.
2. **A builder or parser that accepts what it must refuse**, for example a value outside its range encoded as another valid command, or a frame accepted as a magic frame without its payload.
3. **A transport defect** that could write to the wrong interface, lose or interleave frames, or hide an error.
4. **A secret or private detail** in a public file.

How to report:

1. **Email**: send a detailed report to `electrohobby3d@gmail.com`.
2. **Response**: initial acknowledgment within 48 hours.

We follow a coordinated disclosure policy so that hardware safety is addressed before a public release. The bus itself has no sender authentication; `docs/CONTRACTS.md` lists the gaps that follow from that and are known.
