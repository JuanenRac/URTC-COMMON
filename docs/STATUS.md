<!-- GENERATED from spec/status.json by tools/status_table.py - do not edit by hand. -->

## What has run and what is pending

| Project | Maturity | What has run | Still pending |
|---|---|---|---|
| Tool head firmware (`URTC`) | functional | Run against a simulated or fake board | no populated board exists yet, so it has never run on a real board; its receive path and the bootloader of the master run on a PC against virtual boards |
| Flasher (`URTC-FLASHER`) | functional | Run against a simulated or fake board | exercised only against a simulated bootloader, never against a real board |
| Gateway in front of the bus (`URTC-GATEWAY`) | scaffolding | Run against a simulated or fake board | A run on a real board<br>It has never been run with a real bus |
| Tester (`URTC-TESTER`) | functional | Run against a simulated or fake board | exercised only against fake transports and never against a real board |
| Web studio (`URTC-WEB-STUDIO`) | functional | Run against a simulated or fake board | A run on a real board<br>the Web Serial path has never been run against a USB-CAN adapter |
| Updater (`URTC-UPDATER`) | established | Unit tests and scenarios on a PC | A run on a real board |
| Smart rack (`URTC-SMART-RACK`) | functional | Run against a simulated or fake board | A run on a real board<br>It has never been run on a board<br>Real CAN/F-RAM/GPIO I/O needs a real PCB, which does not exist yet |
| Vision tool (`URTC-VISION-TOOL`) | functional | Run against a simulated or fake board | A run on a real board<br>and has never been run on a board or with a real sensor<br>real dual-modal capture and per-pixel calibration still need a real PCB and real cameras |
| Documentation generator (`URTC-DOCS`) | functional | Unit tests and scenarios on a PC | A run on a real board<br>Scaffolding on purpose: the nightly comparison of all the repositories has not yet been exercised over time |
| Shared protocol and code (`URTC-COMMON`) | functional | Run against a simulated or fake board | A run on a real board |

"What has run" is the `evidence` level of the manifest of each repository and "Still pending" is what its own notes say has not been done; no board of the family has been populated yet, so nothing here has been run on one.
