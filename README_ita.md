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
  <img src="https://img.shields.io/badge/Version-0.0.7-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Verifica di onestà - cosa funziona davvero oggi:** questo repository contiene una specifica, generatori, vettori di test e una piccola libreria Python. Tutto viene eseguito e testato in CI, ma finora lo usano solo URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO (gli identificatori, i payload magici, gli identificatori hardware e i vettori condivisi, come copie tenute oneste da un file di lock); il firmware e i trasporti mantengono la propria copia del protocollo finché ciascuno non migra. I test che confrontano la specifica con quelle copie ne leggono il testo quando i repository sono clonati accanto a questo, e vengono saltati quando non lo sono. Nulla di tutto ciò è stato eseguito su una scheda o su un adattatore CAN: i trasporti sono testati con simulazioni, e la specifica indica per ogni identificatore quali implementazioni lo definiscono, così le lacune sono visibili invece di essere date per risolte.

---

> **Stato di sicurezza (safety e security):** questo ecosistema non è un sistema di sicurezza certificato e non esiste ancora alcuna scheda URTC assemblata. I bootloader controllano le immagini firmware con CRC32 e un HMAC-SHA256 a chiave condivisa, non con una firma asimmetrica (prevista); le immagini applicative pubblicate sono firmate con la chiave pubblica di sviluppo (`signing_key_kind: dev`), quindi chiunque può produrre un'immagine accettata dal bootloader; nulla è stato trasmesso a una scheda reale. Leggi la [base di sicurezza](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e il [modello delle minacce](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) prima di fidarti di qualsiasi affermazione qui per la sicurezza di una persona.

## 📋 In breve

| | |
|---|---|
| Versione | `0.0.7` |
| Maturità | Impalcatura |
| Test | 718 |
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
* Parti di firmware: `firmware_base/urtc_crc8.h`, il CRC-8 dei frame seriali del rack e della visione in un solo posto (copiato con `vendor_copy.py --set firmware_base`), e `generated/urtc_fw_vectors.h`, i vettori che il firmware stesso deve superare (campi di versione, payload magici, valori di controllo del CRC-8) come tabelle C (`--set fw_vectors`).
* Il livello di trama e il limitatore di frequenza dei collegamenti seriali: `firmware_base/urtc_frame.h` (byte iniziale, versione, lunghezza, completezza e CRC-8 di una trama il cui byte di lunghezza sta in una posizione data, e il percorso inverso) e `firmware_base/urtc_rate_limiter.h` (l'intervallo minimo tra messaggi accettati, attraverso il riavvolgimento del contatore di millisecondi), con un riferimento Python (`frame_layer.py`), vettori di frequenza e un test C che sottopone entrambi gli header a ogni vettore di analisi del rack e del sensore di visione (copiati con `vendor_copy.py --set firmware_frame`)
* Un glossario delle espressioni che più programmi dicono: `spec/i18n/glossary.json` nomina ciascuna una sola volta, nelle otto lingue, ed elenca le chiavi di flasher, tester, web studio e updater che devono dirla così (Chiudi, Aggiorna, Pulisci, PID del riscaldatore, Ricerca porte ...); `tools/i18n_glossary.py` verifica il file, verifica i programmi accanto a questo repository (maiuscole, accenti e punteggiatura sono perdonati, una parola diversa no) e riscrive le righe dei file `.lng` e `.json` che differiscono; il confronto notturno lo esegue
* Una sola fonte per i file di lingua: `spec/i18n/catalog/<programma>.json` contiene tutti i testi di flasher, tester, web studio e updater nelle otto lingue (un testo che il glossario nomina ne è un riferimento); `tools/i18n_generate.py sync` scrive i file `.lng`, `.json` e `.py` di ogni programma con un lock (`urtc_i18n.lock.json`) e un test proprio, e `check` (anche nel confronto notturno) fallisce quando un file non è ciò che genera il catalogo.
* La guida rapida nei programmi e le sezioni di README che condividono: `help_text.py` (cinque brevi passi ciascuno per il flasher, il tester e l'updater nelle otto lingue), `help_qt.py` e `qml/HelpDialog.qml` (la finestra di aiuto; copiati con `--set help` e `--set help_qml`), e `spec/readme/sections.json` con `tools/readme_sections.py` («Come si aggiorna», «Primo flash senza hardware» e «Compatibilità», scritte una sola volta nelle otto lingue e messe tra commenti segnaposto prima del titolo della licenza dei file README dei repository che le elencano; `check` gira nel confronto notturno)
* L'asserzione dei test host del firmware: `firmware_base/urtc_test.h` contiene `TEST_ASSERT`, la macro che il firmware del rack, dello strumento di visione e della testa utensile definiva tre volte; ogni repository la copia con `vendor_copy.py --set firmware_test` e tiene il proprio `test_runner.h` con le sue suite.
* [Vettori di conformità](conformance/can_vectors.json): i byte che ogni implementazione deve riprodurre: ogni struttura, i rifiuti e i flussi SLCAN.
* [Profili degli utensili](spec/tools.json): i 25 profili degli utensili (limiti, watchdog, pin, scheda di espansione) come dati; `generate_tools.py` scrive le tabelle TypeScript e Python e [la tabella degli utensili](docs/TOOLS_TABLE.md). Inoltre: il lettore della scatola nera con esportazione in CSV e JSON (`blackbox.py`), il simulatore del rack (`rack_sim.py`), frame per il fuzzing di una scheda creati dalla specifica (`fuzz.py`) e la [tabella di compatibilità](docs/COMPATIBILITY.md) di una release, creata da `spec/versions.json`; e la [tabella di stato](docs/STATUS.md) di ciò che è stato eseguito e di ciò che manca ancora, creata dai manifest dei repository (`status_table.py`).
* **Scheda virtuale e collegamenti complementari:** `virtual_board.py` serve una scheda dietro un adattatore SLCAN su una porta TCP (`python -m urtc_common.virtual_board`); digita `socket://127.0.0.1:7777` dove uno strumento chiede una porta seriale e il flasher, il tester e il gateway funzionano da un capo all'altro senza hardware. `sensor_frame.py` è il riferimento della trama del sensore della testa di visione; essa e la trama seriale del rack sono in versione 2, big-endian come il bus, con i loro vettori (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Autoaggiornamento da un pacchetto firmato:** `self_update.py` è l'intero flusso per un programma che si aggiorna da solo da una release GitHub, senza rete né finestra proprie (chi lo chiama passa il download e l'avanzamento): offre solo una versione strettamente maggiore con pacchetto per la piattaforma, scarica solo dagli host di download delle release GitHub, controlla la dimensione annunciata, lo SHA-256 e la firma Ed25519 di `urtc-pkg/1|app|versione|piattaforma|sha256|dimensione` con la chiave fissata nel programma, estrae senza mai uscire dalla cartella (niente `..`, percorso assoluto, collegamento o dispositivo), rifiuta di installare finché è in corso un'operazione sul bus, conserva le due ultime release, torna indietro da sola se il primo avvio fallisce e registra ogni passo. Solo libreria standard; si copia con `vendor_copy.py --set update`.
* **Il menu «Cerca aggiornamenti» dei programmi, pronto da disegnare:** `update_service.py` contiene le opzioni (tutte prudenti: nessun controllo senza richiesta della persona, `auto_check` spento, `require_confirmation` acceso, nessuna opzione per saltare il checksum o la firma né per aggiungere un host; impostazioni e variabili `URTC_UPDATE_*`, l'ambiente prevale e `lowering_warnings` segnala quando un'esecuzione abbassa una protezione), la chiave Ed25519 delle release fissata con il suo identificativo e i passi `check` / `prepare` / `install` / `rollback`; `update_controller.py` è la macchina a stati che una finestra disegna (controllo, disponibile, download, pronto, installazione, installato, con avanzamento ed errore codificato) e installa solo dopo `confirm_install`; `launcher.py` avvia la release indicata da `current.txt` e torna alla precedente se un primo avvio fallisce; `tools/make_update_package.py` costruisce lo `.zip` / `.tar.gz` riproducibile di una release con `.sha256` e `.sig` e lo verifica con la chiave fissata. Copiato con `vendor_copy.py --set update`.
* **Strumenti:** `generate_constants.py` scrive l'header C, il modulo TypeScript, il modulo Python e la tabella (`--check` confronta), `make_conformance.py` scrive i vettori (`--check`), `vendor_copy.py` copia parti in un altro repository con un file di blocco e verifica la copia, e `ci_validate.py` è il controllo condiviso dei repository. `make_glance.py` di URTC-DOCS scrive la tabella In breve.
* **Pacchetto installabile:** ogni release allega una wheel Python firmata (`urtc-common`, non su PyPI), un archivio dei sorgenti firmato e l'header C generato, anch'esso firmato, costruiti in modo riproducibile da `make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); la firma è quella delle release, di cui i programmi si fidano già. Vedi [la guida](docs/PACKAGE.md). `generate_canbus_doc.py` scrive le tabelle di riferimento di `docs/CANBUS.TXT` del repository del firmware dalla specifica (il testo intorno non viene toccato, `--check` confronta).

## 🧩 Ruolo in URTC

URTC-COMMON è il luogo in cui il protocollo CAN della testa utensile viene scritto una sola volta, come dati, così che il firmware, URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO smettano di mantenere quattro letture distinte della stessa prosa. Contiene la specifica, ciò che ne viene generato, i vettori che ogni implementazione deve riprodurre e il livello di trasporto che i due strumenti Python condividono. Da solo non cambia il comportamento di nessuno di loro: ogni repository lo adotta passo dopo passo (vedi docs/MIGRATION.md).

## 📂 Struttura del repository

```text
URTC-COMMON/
├── docs/         contratti, formato della specifica, guida alla migrazione, il progetto multinodo, il pacchetto e le tabelle generate (protocollo, utensili, stato, compatibilità)
├── spec/         la specifica (can_protocol.json) e il suo schema JSON, i profili degli utensili, i dati di versione e di stato e il catalogo dei testi dei programmi (i18n/)
├── generated/    l'header C e il modulo TypeScript, scritti dalla specifica, e gli header dei vettori per il firmware
├── firmware_base/ parti C condivise dai repository di firmware (il CRC-8, il livello di frame, il limitatore di frequenza e la macro di test)
├── conformance/  i vettori condivisi
├── qml/          finestre Qt Quick condivise dai programmi (guida rapida, teste utensile, ricerca aggiornamenti)
├── src/          il pacchetto Python: protocollo generato, frame, codec SLCAN, trasporti, versioni, esecutore dei vettori, scheda virtuale, modelli del rack e dei nodi, autoaggiornamento, aiuto e finestra delle teste utensile
├── tools/        generatori con --check, vendor_copy.py e i controlli CI condivisi dell'ecosistema
├── tests/        test unitari, il confronto con i repository accanto a questo e l'esecuzione TypeScript dei vettori
├── images/       il banner
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, requirements-dev.lock, ruff.toml, CHANGELOG.md, LICENSE
```

## 🛠️ COMPILAZIONE ED ESECUZIONE

**Requisiti:** Python 3.10 o successivo; pytest e jsonschema per i test; Node 22.18 o successivo per eseguire il TypeScript generato sui vettori (facoltativo)

```bash
python tools/generate_constants.py --check           # i file C, TypeScript e Python e la tabella sono aggiornati
python tools/make_conformance.py --check             # i vettori sono aggiornati
python -m urtc_common.cli conformance                # questo pacchetto riproduce ogni vettore
python tools/vendor_copy.py check TARGET --source .  # una copia in un altro repository non è stata modificata a mano e non è rimasta indietro
python -m pytest tests -q                            # i test unitari e il confronto con i repository accanto a questo
python -m mypy                                       # il controllo dei tipi di urtc_common e urtc_ui
```

`build.sh` / `build.bat` avanzano la versione di un passo (il contachilometri dell'ecosistema), installano il pacchetto ed eseguono i test; `build-test.sh` / `build-test.bat` verificano senza cambiare alcuna versione; `run.sh` / `run.bat` avviano la riga di comando (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Progetti correlati

URTC è fatto di repository indipendenti, ciascuno con la propria versione, i propri test e il proprio README. Ecco la famiglia, per gruppi:

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (questo repository), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
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
