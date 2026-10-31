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
  <img src="https://img.shields.io/badge/Version-0.0.8-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tests-1398-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Verifica di onestà - cosa funziona davvero oggi:** questo repository contiene una specifica, generatori, vettori di test e una piccola libreria Python. Tutto viene eseguito e testato in CI, ma finora lo usano solo URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO (gli identificatori, i payload magici, gli identificatori hardware e i vettori condivisi, come copie tenute oneste da un file di lock); il firmware e i trasporti mantengono la propria copia del protocollo finché ciascuno non migra. I test che confrontano la specifica con quelle copie ne leggono il testo quando i repository sono clonati accanto a questo, e vengono saltati quando non lo sono. Nulla di tutto ciò è stato eseguito su una scheda o su un adattatore CAN: i trasporti sono testati con simulazioni, e la specifica indica per ogni identificatore quali implementazioni lo definiscono, così le lacune sono visibili invece di essere date per risolte.

---

> **Stato di sicurezza (safety e security):** questo ecosistema non è un sistema di sicurezza certificato e non esiste ancora alcuna scheda URTC assemblata. I bootloader controllano le immagini firmware con CRC32 e un HMAC-SHA256 a chiave condivisa, non con una firma asimmetrica (prevista); le immagini applicative pubblicate sono firmate con la chiave pubblica di sviluppo (`signing_key_kind: dev`), quindi chiunque può produrre un'immagine accettata dal bootloader; nulla è stato trasmesso a una scheda reale. Leggi la [base di sicurezza](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e il [modello delle minacce](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) prima di fidarti di qualsiasi affermazione qui per la sicurezza di una persona.

## 📋 In breve

| | |
|---|---|
| Versione | `0.1.2` |
| Maturità | Impalcatura |
| Test | 1398 |
| Tecnologia | JSON / Python |
| Su hardware reale | Solo simulato: provato con emulatori, test double o simulatori; per questa versione non risulta alcuna esecuzione su hardware reale |

**Vai a:** [Panoramica](#-panoramica) · [Architettura](#-architettura) · [Avvio rapido](#-avvio-rapido) · [Test](#-test) · [Struttura](#-struttura-del-repository) · [Correlati](#-progetti-correlati)

<!-- urtc-section:status_common -->
## 🚦 Stato del progetto

🟢 fatto e verificato · 🟡 funziona, con limiti noti · 🟠 a metà o non verificato · 🔴 non fatto o non funzionante. Nulla è verde se non ha mai girato su hardware reale.

| Parte | Stato | Ciò che il repository può dimostrare |
| --- | :---: | --- |
| Software | 🟡 | Codice condiviso dagli altri programmi; verificato solo con test su PC. |
| Test | 🟡 | La suite di test passa nella CI a ogni push. |
| Sicurezza | 🟡 | Le versioni sono firmate con Ed25519 e verificate prima dell'uso; la gestione delle chiavi non è stata rivista da nessun altro. |
| Documentazione | 🟡 | README in otto lingue e documenti di riferimento; le traduzioni non sono state riviste da madrelingua. |

<!-- /urtc-section:status_common -->

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
* La guida rapida nei programmi e le sezioni di README che condividono: `help_text.py` (brevi passi ciascuno per il flasher, il tester e l'updater nelle otto lingue), `help_qt.py` e `qml/HelpDialog.qml` (la finestra di aiuto; copiati con `--set help` e `--set help_qml`), e `spec/readme/sections.json` con `tools/readme_sections.py` (lo Stato del progetto di ogni programma e le parti che più README condividono, scritte una sola volta nelle otto lingue e messe tra commenti segnaposto al loro posto nella struttura; `check` gira nel confronto notturno)
* L'asserzione dei test host del firmware: `firmware_base/urtc_test.h` contiene `TEST_ASSERT`, la macro che il firmware del rack, dello strumento di visione e della testa utensile definiva tre volte; ogni repository la copia con `vendor_copy.py --set firmware_test` e tiene il proprio `test_runner.h` con le sue suite.
* [Vettori di conformità](conformance/can_vectors.json): i byte che ogni implementazione deve riprodurre: ogni struttura, i rifiuti e i flussi SLCAN.
* [Profili degli utensili](spec/tools.json): i 25 profili degli utensili (limiti, watchdog, pin, scheda di espansione) come dati; `generate_tools.py` scrive le tabelle TypeScript e Python e [la tabella degli utensili](docs/TOOLS_TABLE.md). Inoltre: il lettore della scatola nera con esportazione in CSV e JSON (`blackbox.py`), il simulatore del rack (`rack_sim.py`), frame per il fuzzing di una scheda creati dalla specifica (`fuzz.py`) e la [tabella di compatibilità](docs/COMPATIBILITY.md) di una release, creata da `spec/versions.json`; e la [tabella di stato](docs/STATUS.md) di ciò che è stato eseguito e di ciò che manca ancora, creata dai manifest dei repository (`status_table.py`).
* [Configurazione libera di una testa](docs/FREE_TOOL.md): cosa fa un rack con una testa i cui jumper di ID leggono `0x1F`: interroga (`0x1A3`), verifica la risposta e usa l'identità come quella di una testa letta dai jumper; fino ad allora la testa resta nello stato sicuro. Modellato in `rack_sim.py`, con vettori condivisi (`conformance/rack_vectors.json`) che il firmware del rack riproduce.
* [Scenari del bus simulato](docs/BUS_SCENARIOS.md): i guasti di un bus CAN in un file JSON (`urtc-scenario/1`): frame persi, ripetuti, riordinati, ritardati, persi a raffiche o accorciati, un nodo che resta in silenzio o rifiuta un comando con il suo motivo, e una testa in configurazione libera che risponde a `0x1A3` e `0x1A2` in modi diversi. `bus_scenario.py` controlla il file con rigore, lo applica a qualsiasi trasporto simulato e genera scenari di prova da un seed; lo stesso seed dà gli stessi frame. Disattivato salvo richiesta; il flasher e il tester eseguono i loro piani contro di esso con `--scenario` e lasciano un record di evidenza che dice che era una simulazione.
* **Scheda virtuale e collegamenti complementari:** `virtual_board.py` serve una scheda dietro un adattatore SLCAN su una porta TCP (`python -m urtc_common.virtual_board`); digita `socket://127.0.0.1:7777` dove uno strumento chiede una porta seriale e il flasher, il tester e il gateway funzionano da un capo all'altro senza hardware. `sensor_frame.py` è il riferimento della trama del sensore della testa di visione; essa e la trama seriale del rack sono in versione 2, big-endian come il bus, con i loro vettori (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Autoaggiornamento da un pacchetto firmato:** `self_update.py` è l'intero flusso per un programma che si aggiorna da solo da una release GitHub, senza rete né finestra proprie (chi lo chiama passa il download e l'avanzamento): offre solo una versione strettamente maggiore con pacchetto per la piattaforma, scarica solo dagli host di download delle release GitHub, controlla la dimensione annunciata, lo SHA-256 e la firma Ed25519 di `urtc-pkg/1|app|versione|piattaforma|sha256|dimensione` con la chiave fissata nel programma, estrae senza mai uscire dalla cartella (niente `..`, percorso assoluto, collegamento o dispositivo), rifiuta di installare finché è in corso un'operazione sul bus, conserva le due ultime release, torna indietro da sola se il primo avvio fallisce e registra ogni passo. Solo libreria standard; si copia con `vendor_copy.py --set update`.
* **Il menu «Cerca aggiornamenti» dei programmi, pronto da disegnare:** `update_service.py` contiene le opzioni (tutte prudenti: nessun controllo senza richiesta della persona, `auto_check` spento, `require_confirmation` acceso, nessuna opzione per saltare il checksum o la firma né per aggiungere un host; impostazioni e variabili `URTC_UPDATE_*`, l'ambiente prevale e `lowering_warnings` segnala quando un'esecuzione abbassa una protezione), la chiave Ed25519 delle release fissata con il suo identificativo e i passi `check` / `prepare` / `install` / `rollback`; `update_controller.py` è la macchina a stati che una finestra disegna (controllo, disponibile, download, pronto, installazione, installato, con avanzamento ed errore codificato) e installa solo dopo `confirm_install`; `launcher.py` avvia la release indicata da `current.txt` e torna alla precedente se un primo avvio fallisce; `tools/make_update_package.py` costruisce lo `.zip` / `.tar.gz` riproducibile di una release con `.sha256` e `.sig` e lo verifica con la chiave fissata. Copiato con `vendor_copy.py --set update`.
* **Strumenti:** `generate_constants.py` scrive l'header C, il modulo TypeScript, il modulo Python e la tabella (`--check` confronta), `make_conformance.py` scrive i vettori (`--check`), `vendor_copy.py` copia parti in un altro repository con un file di blocco e verifica la copia, e `ci_validate.py` è il controllo condiviso dei repository. `make_glance.py` di URTC-DOCS scrive la tabella In breve.
* **Pacchetto installabile:** ogni release allega una wheel Python firmata (`urtc-common`, non su PyPI), un archivio dei sorgenti firmato e l'header C generato, anch'esso firmato, costruiti in modo riproducibile da `make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); la firma è quella delle release, di cui i programmi si fidano già. Vedi [la guida](docs/PACKAGE.md). `generate_canbus_doc.py` scrive le tabelle di riferimento di `docs/CANBUS.TXT` del repository del firmware dalla specifica (il testo intorno non viene toccato, `--check` confronta).

- **Record di evidenza e la loro cronologia:** `evidence.py` scrive e controlla i record (`urtc-evidence/1`, [docs/EVIDENCE.md](docs/EVIDENCE.md)); `evidence_history.py` elenca quelli di una cartella, dal più recente, ciascuno controllato; `evidence_history_qt.py`, `qml/EvidenceHistoryDialog.qml` e `evidence_history_strings.py` (otto lingue) sono la finestra Storico condivisa da URTC-FLASHER, URTC-TESTER e URTC-UPDATER (copiata con `vendor_copy.py --set history_qt` e `--set history_qml`).

- **Note di una versione:** `tools/changelog_section.py VERSION [--heading] [--compat]` stampa la sezione del CHANGELOG di una versione e, con `--compat`, la tabella di compatibilità di `docs/COMPATIBILITY.md` di seguito; i programmi ne portano una copia (`vendor_copy.py --set release_notes`, con `--set compat` per la tabella) perché il corpo del loro rilascio abbia la stessa forma.

## 🧩 Ruolo in URTC

URTC-COMMON è il luogo in cui il protocollo CAN della testa utensile viene scritto una sola volta, come dati, così che il firmware, URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO smettano di mantenere quattro letture distinte della stessa prosa. Contiene la specifica, ciò che ne viene generato, i vettori che ogni implementazione deve riprodurre e il livello di trasporto che i due strumenti Python condividono. Da solo non cambia il comportamento di nessuno di loro: ogni repository lo adotta passo dopo passo (vedi docs/MIGRATION.md).

## 🏛️ Architettura

<p align="center">
  <img src="images/architecture.svg" alt="Architettura di URTC-COMMON: chi lo usa, che cosa contiene e da che cosa dipende" width="100%">
</p>

Come si incastrano le parti di questo repository: chi lo usa, che cosa contiene e da che cosa dipende. L'immagine è disegnata da `docs/architecture.json` e verificata rispetto al codice.

## 🚀 Avvio rapido

**Requisiti:** Python 3.10 o successivo; pytest e jsonschema per i test; Node 22.18 o successivo per eseguire il TypeScript generato sui vettori (facoltativo)

```bash
python tools/generate_constants.py --check           # i file C, TypeScript e Python e la tabella sono aggiornati
python tools/make_conformance.py --check             # i vettori sono aggiornati
python -m urtc_common.cli conformance                # questo pacchetto riproduce ogni vettore
python tools/vendor_copy.py check TARGET --source .  # una copia in un altro repository non è stata modificata a mano e non è rimasta indietro
python -m pytest tests -q                            # i test unitari e il confronto con i repository accanto a questo
python -m mypy                                       # il controllo dei tipi di urtc_common e urtc_ui
```

## 🧪 Test

La suite ha 1398 test (`python -m pytest tests -q`). Verificano la specifica rispetto al suo schema, i file C, TypeScript e Python generati rispetto a ciò che scrivono i generatori, i vettori di conformità in Python, in TypeScript con Node e in C con un compilatore del computer, il codec SLCAN e i trasporti con finti, la scheda virtuale, il flusso di aggiornamento automatico firmato e il confronto con i repository clonati accanto a questo. Alcuni test vengono saltati quando manca uno strumento opzionale (Node, un compilatore C, PySide6) o un repository vicino. `python -m mypy` controlla i tipi del pacchetto.

## 🏗️ Compilazione e rilascio

`build.sh` / `build.bat` installano il pacchetto ed eseguono i test; `build-test.sh` / `build-test.bat` controllano senza cambiare alcuna versione; `run.sh` / `run.bat` avviano la riga di comando (`conformance`, `describe`, `decode`, `slcan`). Ogni release allega una wheel Python firmata (`urtc-common`, non su PyPI), un archivio sorgente firmato e l'header C generato firmato, costruiti in modo riproducibile da `tools/make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`); vedi [la guida del pacchetto](docs/PACKAGE.md).

## 📂 Struttura del repository

<p align="center">
  <img src="images/repository-structure.svg" alt="Struttura del repository URTC-COMMON" width="100%">
</p>

<details>
<summary>Versione testuale dell'albero</summary>

```text
URTC-COMMON/
├── spec/                                            la specifica, i profili degli utensili, le versioni e il catalogo dei testi
├── src/urtc_common/                                 il pacchetto Python: protocollo, SLCAN, trasporti, scheda virtuale, autoaggiornamento
├── tools/                                           generatori con --check, vendor_copy.py e i controlli di CI condivisi
├── docs/                                            contratti, formato, guida alla migrazione e tabelle generate
├── conformance/                                     i vettori condivisi
├── generated/                                       header C, modulo TypeScript e header dei vettori
├── firmware_base/                                   parti in C condivise dai repository del firmware
├── qml/                                             finestre Qt Quick condivise dai programmi
├── tests/                                           test unitari e il confronto con i repository vicini
├── .github/                                         workflow di CI e modelli per issue e pull request
├── images/                                          banner e immagini di questo README
├── build.sh build.bat                               script di compilazione
├── build-test.sh build-test.bat                     script di compilazione e test che non cambiano nulla nel repository
├── test.sh test.bat                                 eseguono i test
├── run.sh run.bat                                   avviano il programma
├── urtc.project.json                                manifesto: versione, ruolo, maturità e comando di compilazione
├── CHANGELOG.md                                     che cosa è cambiato in ogni versione
├── SECURITY.md SUPPORT.md LICENSE                   politica di sicurezza, supporto e licenza
├── NOTICE                                           licenze delle parti di terzi incluse
├── CONTRIBUTING.md CODE_OF_CONDUCT.md               come contribuire e codice di condotta
├── .gitattributes .gitignore                        impostazioni di Git
├── bump_version.py bump_manifest_version.py         script che alzano la versione
└── pyproject.toml requirements-dev.lock ruff.toml   pacchetto, strumenti bloccati e impostazioni di lint
```

</details>

## 🗺️ Roadmap e limiti noti

**Limiti noti oggi**

* Niente di tutto questo è stato eseguito su una scheda o su un adattatore CAN: i trasporti sono testati con finti, e la specifica dice per ogni identificatore quali implementazioni lo definiscono, così le lacune sono visibili.
* Il firmware e i trasporti mantengono le proprie copie del protocollo finché ciascuno non migra; oggi solo URTC-FLASHER, URTC-TESTER e URTC-WEB-STUDIO usano questo repository.
* I test che confrontano la specifica con gli altri repository ne leggono il testo quando sono clonati accanto a questo, e vengono saltati altrimenti.

**Prossimi passi**

* Portare ogni repository sulla specifica passo dopo passo ([guida alla migrazione](docs/MIGRATION.md)).

## 🌍 Lingue

Il README e i testi esistono in inglese, spagnolo, francese, italiano, tedesco, cinese, giapponese e portoghese europeo.

## 🔗 Progetti correlati

URTC è fatto di repository indipendenti, ciascuno con la propria versione, i propri test e il proprio README. Ecco la famiglia, per gruppi:

* **URTC Tool Platform:**
  * [URTC](https://github.com/JuanenRac/URTC) - firmware della scheda della testa utensile (25 profili utensile, bootloader CAN) e riferimento del protocollo CAN.
  * **URTC-COMMON** (questo repository) - il protocollo CAN scritto una sola volta come dati (specifica, tabelle generate, vettori di conformità) e il codice condiviso dai programmi.
  * [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER) - strumento desktop che aggiorna il firmware della scheda via CAN o via SWD/JTAG.
  * [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY) - gateway davanti al bus CAN: lascia passare solo gli identificatori di un elenco, ne limita la frequenza e chiede una chiave di sessione.
  * [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK) - logica C indipendente dall'hardware e protocollo di comandi per un portautensili con preriscaldamento e tracciamento del ciclo di vita.
  * [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER) - tester desktop del bus CAN in tempo reale che mostra i comandi e la telemetria del profilo utensile segnalato da una scheda.
  * [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL) - protocollo di frame del sensore in C e un companion Python termico/RGB per una testa utensile di ispezione.
  * [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO) - app per browser che programma e collauda la scheda via Web Serial e SLCAN, senza installare nulla.
* **Ecosystem Operations:**
  * [URTC-DEVTOOLS](https://github.com/JuanenRac/URTC-DEVTOOLS) - gli strumenti di repository condivisi della famiglia come un insieme versionato, con un file di lock che distingue una copia modificata da una rimasta indietro.
  * [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS) - architettura, interfacce, base di sicurezza e catalogo generato dell'ecosistema, più gli strumenti che confrontano tutti i repository.
  * [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER) - strumento desktop che rileva, installa e aggiorna i repository della famiglia URTC, un'azione esplicita alla volta.

**Progetti fratelli (indipendenti, con la stessa base e gli stessi strumenti):**

* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - progetto fratello: il centro di documentazione di HYDRA-UMC, un ecosistema indipendente che condivide base e strumenti con questo
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - progetto fratello: il centro di documentazione di A.R.M.O.R., l'ecosistema di sicurezza, anch'esso indipendente e sulla stessa base
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - il profilo e il pannello di stato di tutti gli ecosistemi

## 📚 Documentazione

Dove leggere di più:

* [Contratti: che cosa deve fare ogni implementazione e le lacune note](docs/CONTRACTS.md)
* [Formato della specifica e come modificarla](docs/SPEC_FORMAT.md)
* [Migrazione: come la adotta ogni repository](docs/MIGRATION.md)
* [Tabella del protocollo: ogni identificatore e chi lo implementa](docs/PROTOCOL_TABLE.md)
* [Più teste utensile su un bus](docs/MULTINODE.md)
* [Registro delle modifiche di questo repository](CHANGELOG.md)
* [Licenza (GPL-3.0-or-later)](LICENSE)
* Domande, idee e segnalazioni: electrohobby3d@gmail.com

## 🤝 Contribuire e comunità

* Prima di una pull request esegui `URTC_CI=1 python tools/ci_validate.py`: deve passare. Vedi [CONTRIBUTING.md](CONTRIBUTING.md) e il [codice di condotta](CODE_OF_CONDUCT.md).
* Il README esiste in otto lingue: una modifica del testo si fa in tutti e otto i file, e le sezioni condivise con altri repository le scrive `tools/readme_sections.py` di URTC-COMMON.
* Non descrivere come funzionante su una scheda ciò che è stato solo compilato.
* Segnala una vulnerabilità in privato: [SECURITY.md](SECURITY.md). Domande, idee e segnalazioni: electrohobby3d@gmail.com ([SUPPORT.md](SUPPORT.md)).

## 👤 AUTORE

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENZA

GPL-3.0-or-later - vedi [LICENSE](LICENSE).
