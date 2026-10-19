<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### Il protocollo CAN come dati: specifica, codec generati, vettori di conformità e trasporti condivisi

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Verifica di onestà - cosa funziona davvero oggi:** questo repository contiene una specifica, generatori, vettori di test e una piccola libreria Python. Tutto viene eseguito e testato in CI, ma finora lo usano solo URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO (gli identificatori, i payload magici, gli identificatori hardware e i vettori condivisi, come copie tenute oneste da un file di lock); il firmware e i trasporti mantengono la propria copia del protocollo finché ciascuno non migra. I test che confrontano la specifica con quelle copie ne leggono il testo quando i repository sono clonati accanto a questo, e vengono saltati quando non lo sono. Nulla di tutto ciò è stato eseguito su una scheda o su un adattatore CAN: i trasporti sono testati con simulazioni, e la specifica indica per ogni identificatore quali implementazioni lo definiscono, così le lacune sono visibili invece di essere date per risolte.

---

> **Stato di sicurezza (safety e security):** questo ecosistema non è un sistema di sicurezza certificato e non esiste ancora alcuna scheda URTC assemblata. I bootloader controllano le immagini firmware con CRC32 e un HMAC-SHA256 a chiave condivisa, non con una firma asimmetrica (prevista); le immagini applicative pubblicate sono firmate con la chiave pubblica di sviluppo (`signing_key_kind: dev`), quindi chiunque può produrre un'immagine accettata dal bootloader; nulla è stato trasmesso a una scheda reale. Leggi la [base di sicurezza](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e il [modello delle minacce](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) prima di fidarti di qualsiasi affermazione qui per la sicurezza di una persona.

## 📋 In breve

| | |
|---|---|
| Versione | `0.0.5` |
| Maturità | Impalcatura |
| Test | 217 |
| Tecnologia | JSON / Python |
| Su hardware reale | Solo simulato: provato con emulatori, test double o simulatori; per questa versione non risulta alcuna esecuzione su hardware reale |

## 🎯 Panoramica

Il protocollo CAN della testa utensile, scritto una sola volta come dati, e tutto ciò che ne deriva:

* [Specifica](spec/can_protocol.json): ogni identificatore con direzione, regola di lunghezza, struttura, utensili e blocchi, i payload magici, i registri dello slave e il sottoinsieme SLCAN, e quali implementazioni definiscono ciascuno.
* [Contratti](docs/CONTRACTS.md): che cosa deve fare un'implementazione, chi implementa che cosa oggi, e le lacune e differenze note.
* [Formato della specifica](docs/SPEC_FORMAT.md): le chiavi del file e come aggiungere o modificare un identificatore.
* [Migrazione](docs/MIGRATION.md): l'ordine in cui ogni repository può adottarla e come un controllo mantiene uguali le copie.
* [Tabella del protocollo](docs/PROTOCOL_TABLE.md): tutti gli identificatori in una tabella, generata dalla specifica.
* [Più teste utensile su un bus](docs/MULTINODE.md): indirizzamento, scoperta e regole di sicurezza; implementati nel firmware URTC dietro un interruttore spento per impostazione predefinita, provati solo su computer e non provati su hardware.
* Aiuti per l'interfaccia: `src/urtc_ui`: l'elenco delle lingue, i badge di stato e la formattazione di identificatori, velocità e frame che i programmi desktop possono condividere (senza Qt; URTC-FLASHER e URTC-TESTER ne portano una copia fatta con `vendor_copy.py --set ui`).
* [Vettori di conformità](conformance/can_vectors.json): i byte che ogni implementazione deve riprodurre: ogni struttura, i rifiuti e i flussi SLCAN.
* **Strumenti:** `generate_constants.py` scrive l'header C, il modulo TypeScript, il modulo Python e la tabella (`--check` confronta), `make_conformance.py` scrive i vettori (`--check`), `vendor_copy.py` copia parti in un altro repository con un file di blocco e verifica la copia, e `ci_validate.py` è il controllo condiviso dei repository. `make_glance.py` di URTC-DOCS scrive la tabella In breve.

## 🧩 Ruolo in URTC

URTC-COMMON è il luogo in cui il protocollo CAN della testa utensile viene scritto una sola volta, come dati, così che il firmware, URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO smettano di mantenere quattro letture distinte della stessa prosa. Contiene la specifica, ciò che ne viene generato, i vettori che ogni implementazione deve riprodurre e il livello di trasporto che i due strumenti Python condividono. Da solo non cambia il comportamento di nessuno di loro: ogni repository lo adotta passo dopo passo (vedi docs/MIGRATION.md).

## 📂 Struttura del repository

```text
URTC-COMMON/
├── docs/         contratti, formato della specifica, guida alla migrazione, tabella del protocollo generata
├── spec/         la specifica (can_protocol.json) e il suo schema JSON
├── generated/    l'header C e il modulo TypeScript, scritti dalla specifica
├── conformance/  i vettori condivisi
├── src/          il pacchetto Python: protocollo generato, frame, codec SLCAN, trasporti, versioni, esecutore dei vettori
├── tools/        generatori con --check, vendor_copy.py e i controlli CI condivisi dell'ecosistema
├── tests/        test unitari, il confronto con i repository accanto a questo e l'esecuzione TypeScript dei vettori
├── images/       il banner
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ COMPILAZIONE ED ESECUZIONE

**Requisiti:** Python 3.10 o successivo; pytest e jsonschema per i test; Node 22.18 o successivo per eseguire il TypeScript generato sui vettori (facoltativo)

```bash
python tools/generate_constants.py --check           # i file C, TypeScript e Python e la tabella sono aggiornati
python tools/make_conformance.py --check             # i vettori sono aggiornati
python -m urtc_common.cli conformance                # questo pacchetto riproduce ogni vettore
python tools/vendor_copy.py check TARGET --source .  # una copia in un altro repository non è stata modificata a mano e non è rimasta indietro
python -m pytest tests -q                            # i test unitari e il confronto con i repository accanto a questo
```

`build.sh` / `build.bat` avanzano la versione di un passo (il contachilometri dell'ecosistema), installano il pacchetto ed eseguono i test; `build-test.sh` / `build-test.bat` verificano senza cambiare alcuna versione; `run.sh` / `run.bat` avviano la riga di comando (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Progetti correlati

URTC è fatto di repository indipendenti, ciascuno con la propria versione, i propri test e il proprio README. Ecco la famiglia, per gruppi:

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (questo repository), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Oltre URTC:**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - la scheda madre del braccio robotico, il cui relay CAN è documentato come il bus a cui si collega la testa utensile
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - la stessa idea per l'ecosistema HYDRA-UMC
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - la stessa idea per l'ecosistema di sicurezza A.R.M.O.R.
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - il profilo e il pannello di stato di tutti gli ecosistemi

## 📚 Documentazione e comunità

Dove leggere di più:

* [Contratti: che cosa deve fare ogni implementazione e le lacune note](docs/CONTRACTS.md)
* [Formato della specifica e come modificarla](docs/SPEC_FORMAT.md)
* [Migrazione: come la adotta ogni repository](docs/MIGRATION.md)
* [Tabella del protocollo: ogni identificatore e chi lo implementa](docs/PROTOCOL_TABLE.md)
* [Più teste utensile su un bus](docs/MULTINODE.md)
* [Registro delle modifiche di questo repository](CHANGELOG.md)
* [Licenza (GPL-3.0-or-later)](LICENSE)
* Domande, idee e segnalazioni: electrohobby3d@gmail.com

## 👤 AUTORE

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENZA

GPL-3.0-or-later - vedi [LICENSE](LICENSE).
