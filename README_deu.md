<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | 🇩🇪 <b>Deutsch</b> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### Das CAN-Protokoll als Daten: Spezifikation, generierte Codecs, Konformitätsvektoren und gemeinsame Transporte

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.8-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Ehrlichkeitsprüfung - was heute wirklich läuft:** dieses Repository enthält eine Spezifikation, Generatoren, Testvektoren und eine kleine Python-Bibliothek. Alles läuft und wird in der CI getestet, aber bisher verwenden es nur URTC-FLASHER, URTC-TESTER und URTC-WEB-STUDIO (die Identifier, die Magic-Payloads, die Hardware-IDs und die gemeinsamen Vektoren, als Kopien, die eine Lock-Datei ehrlich hält); die Firmware und die Transporte behalten ihre eigene Kopie des Protokolls, bis jedes einzelne migriert. Die Tests, die die Spezifikation mit diesen Kopien vergleichen, lesen deren Text, wenn die Repositories neben diesem ausgecheckt sind, und werden übersprungen, wenn nicht. Nichts davon wurde gegen eine Platine oder einen CAN-Adapter ausgeführt: Die Transporte werden mit Attrappen getestet, und die Spezifikation nennt für jeden Identifier, welche Implementierungen ihn definieren, sodass die Lücken sichtbar sind, statt als gelöst angenommen zu werden.

---

> **Stand von Sicherheit (Safety) und Security:** Dieses Ökosystem ist kein zertifiziertes Sicherheitssystem, und es existiert noch keine bestückte URTC-Platine. Die Bootloader prüfen Firmware-Images mit CRC32 und einem HMAC-SHA256 mit gemeinsamem Schlüssel, nicht mit einer asymmetrischen Signatur (geplant); die veröffentlichten Anwendungs-Images sind mit dem öffentlichen Entwicklungsschlüssel signiert (`signing_key_kind: dev`), sodass jeder ein vom Bootloader akzeptiertes Image erzeugen kann; an eine echte Platine wurde noch nichts gesendet. Lesen Sie die [Sicherheitsbasis](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) und das [Bedrohungsmodell](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md), bevor Sie sich für die Sicherheit einer Person auf eine Aussage hier verlassen.

## 📋 Auf einen Blick

| | |
|---|---|
| Version | `0.0.8` |
| Reifegrad | Gerüst |
| Tests | 718 |
| Technik | JSON / Python |
| Auf echter Hardware | Nur simuliert: gegen Emulatoren, Attrappen oder Simulatoren getestet; für diese Version ist kein Lauf auf echter Hardware vermerkt |

<!-- urtc-section:status_common -->
## 🚦 Projektstatus

🟢 fertig und überprüft · 🟡 funktioniert, mit bekannten Grenzen · 🟠 halb fertig oder nicht überprüft · 🔴 nicht gemacht oder funktioniert nicht. Nichts ist grün, wenn es nie auf echter Hardware lief.

| Teil | Status | Was das Repository belegen kann |
| --- | :---: | --- |
| Software | 🟡 | Gemeinsamer Code der anderen Programme; nur durch Tests am PC geprüft. |
| Tests | 🟢 | Die Testsuite besteht bei jedem Push in der CI. |
| Sicherheit | 🟡 | Releases werden mit Ed25519 signiert und vor der Nutzung geprüft; der Umgang mit den Schlüsseln wurde von niemand anderem geprüft. |
| Dokumentation | 🟡 | README in acht Sprachen und Referenzdokumente; die Übersetzungen wurden nicht von Muttersprachlern geprüft. |

<!-- /urtc-section:status_common -->

## 🎯 Überblick

Das CAN-Protokoll des Werkzeugkopfs, einmal als Daten geschrieben, und alles, was daraus folgt:

* [Spezifikation](spec/can_protocol.json): jeder Identifier mit Richtung, Längenregel, Aufbau, Werkzeugen und Sperren, die magischen Nutzlasten, die Slave-Register und die SLCAN-Teilmenge, und welche Implementierungen jeden einzelnen definieren.
* [Verträge](docs/CONTRACTS.md): was eine Implementierung tun muss, wer heute was implementiert, und die bekannten Lücken und Unterschiede.
* [Spezifikationsformat](docs/SPEC_FORMAT.md): die Schlüssel der Datei und wie ein Identifier hinzugefügt oder geändert wird.
* [Migration](docs/MIGRATION.md): die Reihenfolge, in der jedes Repository sie übernehmen kann, und wie eine Prüfung die Kopien gleich hält.
* [Protokolltabelle](docs/PROTOCOL_TABLE.md): alle Identifier in einer Tabelle, aus der Spezifikation erzeugt.
* [Mehrere Werkzeugköpfe an einem Bus](docs/MULTINODE.md): Adressierung, Erkennung und Sicherheitsregeln; in der URTC-Firmware hinter einem standardmäßig ausgeschalteten Schalter umgesetzt, nur auf dem Rechner getestet und nicht an Hardware erprobt.
* Oberflächen-Hilfen: `src/urtc_ui`: die Sprachliste, Statusabzeichen und die Formatierung von Identifiern, Bitraten und Frames, die die Desktop-Programme gemeinsam nutzen können (ohne Qt; URTC-FLASHER und URTC-TESTER tragen eine mit `vendor_copy.py --set ui` erstellte Kopie).
* Firmware-Bausteine: `firmware_base/urtc_crc8.h`, das CRC-8 der seriellen Rahmen von Rack und Vision an einer Stelle (kopiert mit `vendor_copy.py --set firmware_base`), und `generated/urtc_fw_vectors.h`, die Vektoren, die die Firmware selbst bestehen muss (Versionsfelder, Magic-Nutzdaten, Prüfwerte des CRC-8) als C-Tabellen (`--set fw_vectors`).
* Rahmenschicht und Ratenbegrenzer der seriellen Verbindungen: `firmware_base/urtc_frame.h` (Startbyte, Version, Länge, Vollständigkeit und CRC-8 eines Rahmens, dessen Längenbyte an einer vorgegebenen Stelle sitzt, und der Weg zurück) und `firmware_base/urtc_rate_limiter.h` (der Mindestabstand zwischen angenommenen Nachrichten, über den Überlauf des Millisekundenzählers hinweg), mit einer Python-Referenz (`frame_layer.py`), Raten-Vektoren und einem C-Test, der beide Header an jeden Parse-Vektor des Racks und des Vision-Sensors bindet (kopiert mit `vendor_copy.py --set firmware_frame`)
* Ein Glossar der Formulierungen, die mehrere Programme verwenden: `spec/i18n/glossary.json` nennt jede einmal in den acht Sprachen und listet die Schlüssel von Flasher, Tester, Web-Studio und Updater, die sie so sagen müssen (Schließen, Aktualisieren, Leeren, Heizungs-PID, Portsuche ...); `tools/i18n_glossary.py` prüft die Datei, prüft die Programme neben diesem Repository (Groß-/Kleinschreibung, Akzente und Satzzeichen werden verziehen, ein anderes Wort nicht) und schreibt die abweichenden Zeilen der `.lng`- und `.json`-Dateien um; der nächtliche Vergleich führt es aus
* Eine Quelle für die Sprachdateien: `spec/i18n/catalog/<Programm>.json` enthält alle Texte von Flasher, Tester, Web-Studio und Updater in den acht Sprachen (ein Text, den das Glossar nennt, ist ein Verweis darauf); `tools/i18n_generate.py sync` schreibt die `.lng`-, `.json`- und `.py`-Dateien jedes Programms mit einem Lock (`urtc_i18n.lock.json`) und einem eigenen Test, und `check` (auch im nächtlichen Vergleich) schlägt fehl, wenn eine Datei nicht das ist, was der Katalog erzeugt.
* Die Kurzanleitung in den Programmen und die gemeinsamen README-Abschnitte: `help_text.py` (je fünf kurze Schritte für Flasher, Tester und Updater in den acht Sprachen), `help_qt.py` und `qml/HelpDialog.qml` (das Hilfefenster; kopiert mit `--set help` und `--set help_qml`) sowie `spec/readme/sections.json` mit `tools/readme_sections.py` („So wird aktualisiert“, „Erstes Flashen ohne Hardware“ und „Kompatibilität“, einmal in den acht Sprachen geschrieben und zwischen Markierungskommentare vor die Lizenzüberschrift der README-Dateien der Repositories gesetzt, die sie aufführen; `check` läuft im nächtlichen Vergleich)
* Die Assertion der Host-Tests der Firmware: `firmware_base/urtc_test.h` enthält `TEST_ASSERT`, das Makro, das die Firmware von Rack, Vision-Tool und Werkzeugkopf dreimal definiert hatte; jedes Repository kopiert es mit `vendor_copy.py --set firmware_test` und behält sein eigenes `test_runner.h` mit seinen Suiten.
* [Konformitätsvektoren](conformance/can_vectors.json): die Bytes, die jede Implementierung reproduzieren muss: jeder Aufbau, die Ablehnungen und die SLCAN-Datenströme.
* [Werkzeugprofile](spec/tools.json): die 25 Werkzeugprofile (Grenzen, Watchdog, Pins, Erweiterungsplatine) als Daten; `generate_tools.py` schreibt die TypeScript- und Python-Tabellen und [die Werkzeugtabelle](docs/TOOLS_TABLE.md). Außerdem: der Leser der Blackbox mit CSV- und JSON-Export (`blackbox.py`), der Rack-Simulator (`rack_sim.py`), aus der Spezifikation erzeugte Frames zum Fuzzing einer Platine (`fuzz.py`) und die [Kompatibilitätstabelle](docs/COMPATIBILITY.md) einer Version, erzeugt aus `spec/versions.json`; und die [Statustabelle](docs/STATUS.md) dessen, was gelaufen ist und was noch aussteht, erzeugt aus den Manifesten der Repositories (`status_table.py`).
* **Virtuelle Platine und Zusatzverbindungen:** `virtual_board.py` stellt eine Platine hinter einem SLCAN-Adapter an einem TCP-Port bereit (`python -m urtc_common.virtual_board`); wo ein Werkzeug einen seriellen Port verlangt, `socket://127.0.0.1:7777` eingeben, und Flasher, Tester und Gateway laufen ohne Hardware durchgängig. `sensor_frame.py` ist die Referenz des Sensorrahmens des Vision-Kopfes; er und der serielle Rahmen des Racks sind Version 2, Big-Endian wie der Bus, mit ihren Vektoren (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Selbstaktualisierung aus einem signierten Paket:** `self_update.py` ist der gesamte Ablauf für ein Programm, das sich aus einem GitHub-Release selbst aktualisiert, ohne eigenes Netzwerk und Fenster (der Aufrufer übergibt Download und Fortschritt): Es bietet nur eine strikt höhere Version mit Paket für die Plattform an, lädt nur von den Hosts der GitHub-Release-Downloads, prüft angekündigte Größe, SHA-256 und die Ed25519-Signatur von `urtc-pkg/1|App|Version|Plattform|sha256|Größe` gegen den im Programm fest hinterlegten Schlüssel, entpackt ohne je den Ordner zu verlassen (kein `..`, kein absoluter Pfad, kein Link, kein Gerät), verweigert die Installation, solange eine Operation auf dem Bus läuft, behält die zwei neuesten Releases, geht von selbst zurück, wenn der erste Start scheitert, und protokolliert jeden Schritt. Nur Standardbibliothek; kopiert mit `vendor_copy.py --set update`.
* **Das Menü „Nach Updates suchen“ der Programme, zum Zeichnen bereit:** `update_service.py` enthält die Optionen (alle vorsichtig: keine Prüfung, wenn die Person sie nicht verlangt, `auto_check` aus, `require_confirmation` an, keine Option, Prüfsumme oder Signatur zu überspringen oder einen Host hinzuzufügen; Einstellungen und `URTC_UPDATE_*`-Variablen, die Umgebung gewinnt und `lowering_warnings` meldet, wenn ein Lauf einen Schutz senkt), den angehefteten Ed25519-Schlüssel der Releases samt Kennung und die Schritte `check` / `prepare` / `install` / `rollback`; `update_controller.py` ist der Zustandsautomat, den ein Fenster zeichnet (Prüfen, verfügbar, Download, bereit, Installation, installiert, mit Fortschritt und kodiertem Fehler) und installiert erst nach `confirm_install`; `launcher.py` startet das Release, auf das `current.txt` zeigt, und kehrt zum vorherigen zurück, wenn ein Erststart scheitert; `tools/make_update_package.py` baut das reproduzierbare `.zip` / `.tar.gz` eines Releases mit `.sha256` und `.sig` und prüft es mit dem angehefteten Schlüssel. Kopiert mit `vendor_copy.py --set update`.
* **Werkzeuge:** `generate_constants.py` schreibt den C-Header, das TypeScript-Modul, das Python-Modul und die Tabelle (`--check` vergleicht), `make_conformance.py` schreibt die Vektoren (`--check`), `vendor_copy.py` kopiert Teile mit einer Sperrdatei in ein anderes Repository und prüft die Kopie, und `ci_validate.py` ist die gemeinsame Repository-Prüfung. `make_glance.py` von URTC-DOCS schreibt die Tabelle Auf einen Blick.
* **Installierbares Paket:** Jedes Release enthält ein signiertes Python-Wheel (`urtc-common`, nicht auf PyPI), ein signiertes Quellarchiv und die signierte generierte C-Header-Datei, reproduzierbar gebaut von `make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); die Signatur ist die der Releases, der die Programme bereits vertrauen. Siehe [die Anleitung](docs/PACKAGE.md). `generate_canbus_doc.py` schreibt die Referenztabellen von `docs/CANBUS.TXT` im Firmware-Repository aus der Spezifikation (der Text darum bleibt unberührt, `--check` vergleicht).

## 🧩 Rolle in URTC

URTC-COMMON ist der Ort, an dem das CAN-Protokoll des Werkzeugkopfs einmal als Daten aufgeschrieben wird, damit die Firmware, URTC-FLASHER, URTC-TESTER und URTC-WEB-STUDIO nicht mehr vier getrennte Lesarten desselben Textes pflegen müssen. Es enthält die Spezifikation, das daraus Erzeugte, die Vektoren, die jede Implementierung reproduzieren muss, und die Transportschicht, die die beiden Python-Werkzeuge teilen. Für sich allein ändert es das Verhalten keines davon: Jedes Repository übernimmt es Schritt für Schritt (siehe docs/MIGRATION.md).

## 📂 Repository-Struktur

```text
URTC-COMMON/
├── docs/         Verträge, Spezifikationsformat, Migrationsanleitung, der Multinode-Entwurf, das Paket und die erzeugten Tabellen (Protokoll, Werkzeuge, Status, Kompatibilität)
├── spec/         die Spezifikation (can_protocol.json) und ihr JSON-Schema, die Werkzeugprofile, die Versions- und Statusdaten und der Katalog der Texte der Programme (i18n/)
├── generated/    der C-Header und das TypeScript-Modul, aus der Spezifikation erzeugt, und die Vektor-Header für die Firmware
├── firmware_base/ C-Bausteine, die die Firmware-Repositories teilen (das CRC-8, die Rahmenschicht, der Ratenbegrenzer und das Test-Makro)
├── conformance/  die gemeinsamen Vektoren
├── qml/          Qt-Quick-Fenster, die die Programme teilen (Kurzanleitung, Werkzeugköpfe, Update-Suche)
├── src/          das Python-Paket: erzeugtes Protokoll, Rahmen, SLCAN-Codec, Transporte, Versionen, Vektorläufer, virtuelle Platine, Modelle von Rack und Knoten, Selbstaktualisierung, Hilfe und das Fenster der Werkzeugköpfe
├── tools/        Generatoren mit --check, vendor_copy.py und die gemeinsamen CI-Prüfungen des Ökosystems
├── tests/        Unit-Tests, der Vergleich mit den Repositories neben diesem und der TypeScript-Lauf der Vektoren
├── images/       das Banner
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, requirements-dev.lock, ruff.toml, CHANGELOG.md, LICENSE
```

## 🛠️ BUILD & AUSFÜHRUNG

**Voraussetzungen:** Python 3.10 oder neuer; pytest und jsonschema für die Tests; Node 22.18 oder neuer, um das erzeugte TypeScript gegen die Vektoren auszuführen (optional)

```bash
python tools/generate_constants.py --check           # die C-, TypeScript- und Python-Dateien und die Tabelle sind aktuell
python tools/make_conformance.py --check             # die Vektoren sind aktuell
python -m urtc_common.cli conformance                # dieses Paket reproduziert jeden Vektor
python tools/vendor_copy.py check TARGET --source .  # eine Kopie in einem anderen Repository wurde nicht von Hand geändert und ist nicht veraltet
python -m pytest tests -q                            # die Unit-Tests und der Vergleich mit den Repositories neben diesem
python -m mypy                                       # die Typprüfung von urtc_common und urtc_ui
```

`build.sh` / `build.bat` erhöhen die Version um einen Schritt (der Kilometerzähler des Ökosystems), installieren das Paket und führen die Tests aus; `build-test.sh` / `build-test.bat` prüfen, ohne eine Version zu ändern; `run.sh` / `run.bat` starten die Befehlszeile (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Verwandte Projekte

URTC besteht aus unabhängigen Repositories mit jeweils eigener Version, eigenen Tests und eigenem README. Das ist die Familie, nach Gruppen:

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (dieses Repository), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Über URTC hinaus:**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - die Hauptplatine des Roboterarms, deren CAN-Relay als der Bus dokumentiert ist, an dem der Werkzeugkopf hängt
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - dieselbe Idee für das Ökosystem HYDRA-UMC
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - dieselbe Idee für das Sicherheits-Ökosystem A.R.M.O.R.
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - das Profil und das Status-Dashboard aller Ökosysteme

## 📚 Dokumentation & Community

Wo man mehr liest:

* [Verträge: was jede Implementierung tun muss, und die bekannten Lücken](docs/CONTRACTS.md)
* [Spezifikationsformat und wie man es ändert](docs/SPEC_FORMAT.md)
* [Migration: wie jedes Repository sie übernimmt](docs/MIGRATION.md)
* [Protokolltabelle: jeder Identifier und wer ihn implementiert](docs/PROTOCOL_TABLE.md)
* [Mehrere Werkzeugköpfe an einem Bus](docs/MULTINODE.md)
* [Änderungsprotokoll dieses Repositories](CHANGELOG.md)
* [Lizenz (GPL-3.0-or-later)](LICENSE)
* Fragen, Ideen und Meldungen: electrohobby3d@gmail.com

## 👤 AUTOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LIZENZ

GPL-3.0-or-later - siehe [LICENSE](LICENSE).
