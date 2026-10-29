<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | 🇫🇷 <b>Français</b> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### Le protocole CAN comme données : spécification, codecs générés, vecteurs de conformité et transports partagés

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.8-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tests-718-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Vérification d'honnêteté - ce qui fonctionne réellement aujourd'hui :** ce dépôt contient une spécification, des générateurs, des vecteurs de test et une petite bibliothèque Python. Tout s'exécute et est testé en CI, mais jusqu'ici seuls URTC-FLASHER, URTC-TESTER et URTC-WEB-STUDIO l'utilisent (les identifiants, les charges magiques, les identifiants matériels et les vecteurs partagés, sous forme de copies surveillées par un fichier de verrouillage) ; le firmware et les transports gardent leur propre copie du protocole jusqu'à ce que chacun migre. Les tests qui comparent la spécification à ces copies lisent leur texte lorsque les dépôts sont clonés à côté de celui-ci, et sont ignorés sinon. Rien de tout cela n'a été exécuté face à une carte ou à un adaptateur CAN : les transports sont testés avec des simulations, et la spécification indique pour chaque identifiant quelles implémentations le définissent, de sorte que les lacunes sont visibles au lieu d'être tenues pour résolues.

---

> **État de la sûreté et de la cybersécurité :** cet écosystème n'est pas un système de sécurité certifié et aucune carte URTC assemblée n'existe encore. Les bootloaders contrôlent les images de firmware par CRC32 et un HMAC-SHA256 à clé partagée, pas par une signature asymétrique (prévue) ; les images d'application publiées sont signées avec la clé publique de développement (`signing_key_kind: dev`), si bien que n'importe qui peut produire une image acceptée par le bootloader ; rien n'a été transmis à une carte réelle. Lisez la [base de sécurité](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) et le [modèle de menaces](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) avant de vous fier à une affirmation d'ici pour la sécurité d'une personne.

## 📋 En un coup d'œil

| | |
|---|---|
| Version | `0.0.8` |
| Maturité | Ébauche |
| Tests | 718 |
| Technologie | JSON / Python |
| Sur matériel réel | Simulé seulement : testé avec des émulateurs, des doubles de test ou des simulateurs ; aucune exécution sur du matériel réel n'est consignée pour cette version |

**Aller à :** [Présentation](#-présentation) · [Architecture](#-architecture) · [Démarrage rapide](#-démarrage-rapide) · [Tests](#-tests) · [Structure](#-structure-du-dépôt) · [Liés](#-projets-liés)

<!-- urtc-section:status_common -->
## 🚦 État du projet

🟢 fait et vérifié · 🟡 fonctionne, avec des limites connues · 🟠 à moitié fait ou non vérifié · 🔴 non fait ou non fonctionnel. Rien n'est vert si cela n'a jamais tourné sur du vrai matériel.

| Partie | État | Ce que le dépôt peut démontrer |
| --- | :---: | --- |
| Logiciel | 🟡 | Code partagé par les autres programmes ; vérifié seulement par des tests sur PC. |
| Tests | 🟢 | La suite de tests passe dans la CI à chaque push. |
| Sécurité | 🟡 | Les versions sont signées en Ed25519 et vérifiées avant usage ; la gestion des clés n'a été relue par personne d'autre. |
| Documentation | 🟡 | README en huit langues et documents de référence ; les traductions n'ont pas été relues par des locuteurs natifs. |

<!-- /urtc-section:status_common -->

## 🎯 Présentation

Le protocole CAN de la tête d'outil, écrit une seule fois comme données, et tout ce qui en découle :

* [Spécification](spec/can_protocol.json): chaque identifiant avec sa direction, sa règle de longueur, sa structure, ses outils et ses verrous, les charges magiques, les registres de l'esclave et le sous-ensemble SLCAN, et quelles implémentations définissent chacun.
* [Contrats](docs/CONTRACTS.md): ce qu'une implémentation doit faire, qui implémente quoi aujourd'hui, et les lacunes et différences connues.
* [Format de la spécification](docs/SPEC_FORMAT.md): les clés du fichier et comment ajouter ou modifier un identifiant.
* [Migration](docs/MIGRATION.md): l'ordre dans lequel chaque dépôt peut l'adopter, et comment une vérification garde les copies identiques.
* [Table du protocole](docs/PROTOCOL_TABLE.md): tous les identifiants dans une table, générée à partir de la spécification.
* [Plusieurs têtes d'outil sur un bus](docs/MULTINODE.md): adressage, découverte et règles de sécurité ; implémentés dans le firmware URTC derrière un interrupteur éteint par défaut, testés seulement sur ordinateur et non essayés sur du matériel.
* Aides d'interface: `src/urtc_ui` : la liste des langues, les pastilles d'état et le formatage des identifiants, débits et trames que les programmes de bureau peuvent partager (sans Qt ; URTC-FLASHER et URTC-TESTER en portent une copie faite avec `vendor_copy.py --set ui`).
* Éléments de firmware : `firmware_base/urtc_crc8.h`, le CRC-8 des trames série du rack et de la vision en un seul endroit (copié avec `vendor_copy.py --set firmware_base`), et `generated/urtc_fw_vectors.h`, les vecteurs que le firmware lui-même doit réussir (champs de version, charges magiques, valeurs de contrôle du CRC-8) sous forme de tables C (`--set fw_vectors`).
* La couche de trame et le limiteur de cadence des liaisons série : `firmware_base/urtc_frame.h` (octet de départ, version, longueur, complétude et CRC-8 d'une trame dont l'octet de longueur est à une position donnée, et le chemin inverse) et `firmware_base/urtc_rate_limiter.h` (l'intervalle minimal entre messages acceptés, à travers le débordement du compteur de millisecondes), avec une référence Python (`frame_layer.py`), des vecteurs de cadence et un test C qui soumet les deux en-têtes à chaque vecteur d'analyse du rack et du capteur de vision (copiés avec `vendor_copy.py --set firmware_frame`)
* Un glossaire des expressions que plusieurs programmes disent : `spec/i18n/glossary.json` nomme chacune une seule fois, dans les huit langues, et liste les clés du flasher, du testeur, du studio web et de l'updater qui doivent la dire ainsi (Fermer, Actualiser, Effacer, PID du chauffage, Recherche de ports ...) ; `tools/i18n_glossary.py` vérifie le fichier, vérifie les programmes voisins de ce dépôt (la casse, les accents et la ponctuation sont pardonnés, un mot différent non) et réécrit les lignes des fichiers `.lng` et `.json` qui diffèrent ; la comparaison de nuit l'exécute
* Une seule source pour les fichiers de langue : `spec/i18n/catalog/<programme>.json` contient tous les textes du flasher, du testeur, du web studio et de l'outil de mise à jour dans les huit langues (un texte que nomme le glossaire en est une référence) ; `tools/i18n_generate.py sync` écrit les fichiers `.lng`, `.json` et `.py` de chaque programme avec un lock (`urtc_i18n.lock.json`) et un test propre, et `check` (aussi dans la comparaison nocturne) échoue quand un fichier n'est pas ce que génère le catalogue.
* Le guide rapide dans les programmes et les sections de README qu'ils partagent : `help_text.py` (cinq courtes étapes chacun pour le flasher, le testeur et l'outil de mise à jour dans les huit langues), `help_qt.py` et `qml/HelpDialog.qml` (la fenêtre d'aide ; copiés avec `--set help` et `--set help_qml`), et `spec/readme/sections.json` avec `tools/readme_sections.py` (l'État du projet de chaque programme et les parties que plusieurs README partagent, écrites une seule fois dans les huit langues et placées entre des commentaires repères à leur place dans la structure ; `check` tourne dans la comparaison de nuit)
* L'assertion des tests hôte du firmware : `firmware_base/urtc_test.h` contient `TEST_ASSERT`, la macro que les firmwares du rack, de l'outil de vision et de la tête d'outil définissaient trois fois ; chaque dépôt la copie avec `vendor_copy.py --set firmware_test` et garde son propre `test_runner.h` avec ses suites.
* [Vecteurs de conformité](conformance/can_vectors.json): les octets que toute implémentation doit reproduire : chaque structure, les refus et les flux SLCAN.
* [Profils d'outil](spec/tools.json) : les 25 profils d'outil (limites, chien de garde, broches, carte d'extension) comme données ; `generate_tools.py` écrit les tables TypeScript et Python et [la table des outils](docs/TOOLS_TABLE.md). Aussi ici : le lecteur de la boîte noire avec export CSV et JSON (`blackbox.py`), le simulateur du rack (`rack_sim.py`), des trames pour tester une carte par fuzzing, produites à partir de la spécification (`fuzz.py`) et le [tableau de compatibilité](docs/COMPATIBILITY.md) d'une version, produit à partir de `spec/versions.json` ; et le [tableau d'état](docs/STATUS.md) de ce qui a tourné et de ce qui reste à faire, produit à partir des manifestes des dépôts (`status_table.py`).
* **Carte virtuelle et liaisons complémentaires :** `virtual_board.py` sert une carte derrière un adaptateur SLCAN sur un port TCP (`python -m urtc_common.virtual_board`) ; saisissez `socket://127.0.0.1:7777` là où un outil demande un port série et le flasheur, le testeur et la passerelle fonctionnent de bout en bout sans matériel. `sensor_frame.py` est la référence de la trame du capteur de la tête de vision ; elle et la trame série du rack sont en version 2, big-endian comme le bus, avec leurs vecteurs (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Auto-mise à jour depuis un paquet signé :** `self_update.py` est tout le parcours d'un programme qui se met à jour seul depuis une release GitHub, sans réseau ni fenêtre propres (l'appelant fournit le téléchargement et la progression) : il ne propose qu'une version strictement supérieure avec un paquet pour la plateforme, télécharge uniquement depuis les hôtes de téléchargement des releases GitHub, vérifie la taille annoncée, le SHA-256 et la signature Ed25519 de `urtc-pkg/1|app|version|plateforme|sha256|taille` avec la clé fixée dans le programme, extrait sans jamais sortir du dossier (ni `..`, ni chemin absolu, ni lien, ni périphérique), refuse d'installer tant qu'une opération sur le bus est en cours, garde les deux dernières releases, revient seul en arrière si le premier démarrage échoue et consigne chaque étape. Bibliothèque standard seulement ; copié avec `vendor_copy.py --set update`.
* **Le menu « Rechercher une mise à jour » des programmes, prêt à dessiner :** `update_service.py` contient les options (toutes prudentes : aucune vérification sans demande de la personne, `auto_check` désactivé, `require_confirmation` activé, aucune option pour ignorer la somme de contrôle ou la signature ni pour ajouter un hôte ; réglages et variables `URTC_UPDATE_*`, l'environnement l'emporte et `lowering_warnings` signale qu'une exécution abaisse une protection), la clé Ed25519 des releases épinglée avec son identifiant, et les étapes `check` / `prepare` / `install` / `rollback` ; `update_controller.py` est la machine à états qu'une fenêtre dessine (vérification, disponible, téléchargement, prêt, installation, installé, avec progression et erreur codée) et n'installe qu'après `confirm_install` ; `launcher.py` lance la release visée par `current.txt` et revient à la précédente si un premier démarrage échoue ; `tools/make_update_package.py` construit le `.zip` / `.tar.gz` reproductible d'une release avec son `.sha256` et son `.sig` et le vérifie avec la clé épinglée. Copié avec `vendor_copy.py --set update`.
* **Outils :** `generate_constants.py` écrit l'en-tête C, le module TypeScript, le module Python et la table (`--check` compare), `make_conformance.py` écrit les vecteurs (`--check`), `vendor_copy.py` copie des parties dans un autre dépôt avec un fichier de verrouillage et vérifie la copie, et `ci_validate.py` est la vérification commune des dépôts. `make_glance.py` d'URTC-DOCS écrit le tableau En un coup d'œil.
* **Paquet installable :** chaque release joint une roue Python signée (`urtc-common`, absente de PyPI), une archive de sources signée et l'en-tête C généré, signé lui aussi, construits de façon reproductible par `make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`) ; la signature est celle des releases, en laquelle les programmes ont déjà confiance. Voir [le guide](docs/PACKAGE.md). `generate_canbus_doc.py` écrit les tableaux de référence de `docs/CANBUS.TXT` du dépôt du firmware à partir de la spécification (le texte autour n'est pas touché, `--check` compare).

## 🧩 Rôle dans URTC

URTC-COMMON est l'endroit où le protocole CAN de la tête d'outil est écrit une seule fois, comme données, afin que le firmware, URTC-FLASHER, URTC-TESTER et URTC-WEB-STUDIO cessent de tenir quatre lectures distinctes du même texte. Il contient la spécification, ce qui en est généré, les vecteurs que toute implémentation doit reproduire et la couche de transport que partagent les deux outils Python. À lui seul, il ne change le comportement d'aucun d'eux : chaque dépôt l'adopte pas à pas (voir docs/MIGRATION.md).

## 🏛️ Architecture

<p align="center">
  <img src="images/architecture.svg" alt="Architecture de URTC-COMMON : qui l'utilise, ce qu'il contient et de quoi il dépend" width="100%">
</p>

Comment les parties de ce dépôt s'articulent : qui l'utilise, ce qu'il contient et de quoi il dépend. L'image est dessinée à partir de `docs/architecture.json` et vérifiée par rapport au code.

## 🚀 Démarrage rapide

**Prérequis :** Python 3.10 ou plus récent ; pytest et jsonschema pour les tests ; Node 22.18 ou plus récent pour exécuter le TypeScript généré contre les vecteurs (facultatif)

```bash
python tools/generate_constants.py --check           # les fichiers C, TypeScript et Python et la table sont à jour
python tools/make_conformance.py --check             # les vecteurs sont à jour
python -m urtc_common.cli conformance                # ce paquet reproduit chaque vecteur
python tools/vendor_copy.py check TARGET --source .  # une copie dans un autre dépôt n'a pas été modifiée à la main et n'a pas pris de retard
python -m pytest tests -q                            # les tests unitaires et la comparaison avec les dépôts voisins
python -m mypy                                       # le contrôle des types de urtc_common et urtc_ui
```

## 🧪 Tests

La suite compte 718 tests (`python -m pytest tests -q`). Ils vérifient la spécification par rapport à son schéma, les fichiers C, TypeScript et Python générés par rapport à ce qu'écrivent les générateurs, les vecteurs de conformité en Python, en TypeScript avec Node et en C avec un compilateur de la machine, le codec SLCAN et les transports avec des faux, la carte virtuelle, le flux de mise à jour automatique signée et la comparaison avec les dépôts récupérés à côté de celui-ci. Quelques tests sont ignorés quand un outil optionnel (Node, un compilateur C, PySide6) ou un dépôt voisin manque. `python -m mypy` vérifie les types du paquet.

## 🏗️ Compilation et publication

`build.sh` / `build.bat` installent le paquet et lancent les tests ; `build-test.sh` / `build-test.bat` vérifient sans changer aucune version ; `run.sh` / `run.bat` lancent la ligne de commande (`conformance`, `describe`, `decode`, `slcan`). Chaque release joint une roue Python signée (`urtc-common`, absente de PyPI), une archive source signée et l'en-tête C généré signé, construits de façon reproductible par `tools/make_release_artifacts.py` (`build`, `verify`, `reproduce`, `smoke`) ; voir [le guide du paquet](docs/PACKAGE.md).

## 📂 Structure du dépôt

<p align="center">
  <img src="images/repository-structure.svg" alt="Structure du dépôt URTC-COMMON" width="100%">
</p>

<details>
<summary>Version texte de l'arborescence</summary>

```text
URTC-COMMON/
├── spec/                                            la spécification, les profils d'outils, les versions et le catalogue de textes
├── src/urtc_common/                                 le paquet Python : protocole, SLCAN, transports, carte virtuelle, mise à jour automatique
├── tools/                                           générateurs avec --check, vendor_copy.py et les contrôles de CI partagés
├── docs/                                            contrats, format, guide de migration et tableaux générés
├── conformance/                                     les vecteurs partagés
├── generated/                                       en-tête C, module TypeScript et en-têtes de vecteurs
├── firmware_base/                                   parties en C partagées par les dépôts de firmware
├── qml/                                             fenêtres Qt Quick partagées par les programmes
├── tests/                                           tests unitaires et la comparaison avec les dépôts voisins
├── .github/                                         workflow de CI et modèles d'issues et de pull requests
├── images/                                          bannière et images de ce README
├── build.sh build.bat                               scripts de compilation
├── build-test.sh build-test.bat                     scripts de compilation et de test qui ne changent rien dans le dépôt
├── test.sh test.bat                                 lancent les tests
├── run.sh run.bat                                   lancent le programme
├── urtc.project.json                                manifeste : version, rôle, maturité et commande de compilation
├── CHANGELOG.md                                     ce qui a changé à chaque version
├── SECURITY.md SUPPORT.md LICENSE                   politique de sécurité, assistance et licence
├── CONTRIBUTING.md CODE_OF_CONDUCT.md               comment contribuer et code de conduite
├── .gitattributes .gitignore                        réglages Git
├── bump_version.py bump_manifest_version.py         scripts qui augmentent la version
└── pyproject.toml requirements-dev.lock ruff.toml   paquet, outils figés et réglages de lint
```

</details>

## 🗺️ Feuille de route et limites connues

**Limites connues aujourd'hui**

* Rien de tout cela n'a tourné sur une carte ni sur un adaptateur CAN : les transports sont testés avec des faux, et la spécification indique pour chaque identifiant quelles implémentations le définissent, de sorte que les lacunes se voient.
* Le firmware et les transports gardent leurs propres copies du protocole jusqu'à leur migration ; aujourd'hui seuls URTC-FLASHER, URTC-TESTER et URTC-WEB-STUDIO utilisent ce dépôt.
* Les tests qui comparent la spécification aux autres dépôts lisent leur texte quand ils sont récupérés à côté de celui-ci, et sont ignorés sinon.

**Ensuite**

* Faire passer chaque dépôt sur la spécification pas à pas ([guide de migration](docs/MIGRATION.md)).

## 🌍 Langues

Le README et les textes existent en anglais, espagnol, français, italien, allemand, chinois, japonais et portugais européen.

## 🔗 Projets liés

URTC est fait de dépôts indépendants, chacun avec sa version, ses tests et son README. Voici la famille, par groupes :

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (ce dépôt), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Projets frères (indépendants, avec la même base et les mêmes outils) :**

* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - projet frère : le centre de documentation de HYDRA-UMC, un écosystème indépendant qui partage la base et les outils de celui-ci
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - projet frère : le centre de documentation d'A.R.M.O.R., l'écosystème de sécurité, lui aussi indépendant et construit sur la même base
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - le profil et le tableau d'état de tous les écosystèmes

## 📚 Documentation

Pour en savoir plus :

* [Contrats : ce que chaque implémentation doit faire, et les lacunes connues](docs/CONTRACTS.md)
* [Format de la spécification et comment le modifier](docs/SPEC_FORMAT.md)
* [Migration : comment chaque dépôt l'adopte](docs/MIGRATION.md)
* [Table du protocole : chaque identifiant et qui l'implémente](docs/PROTOCOL_TABLE.md)
* [Plusieurs têtes d'outil sur un bus](docs/MULTINODE.md)
* [Journal des modifications de ce dépôt](CHANGELOG.md)
* [Licence (GPL-3.0-or-later)](LICENSE)
* Questions, idées et rapports : electrohobby3d@gmail.com

## 🤝 Contribuer et communauté

* Avant une pull request, lancez `URTC_CI=1 python tools/ci_validate.py` : il doit réussir. Voir [CONTRIBUTING.md](CONTRIBUTING.md) et le [code de conduite](CODE_OF_CONDUCT.md).
* Le README existe en huit langues : une modification du texte se fait dans les huit fichiers, et les sections partagées avec d'autres dépôts sont écrites par `tools/readme_sections.py` d'URTC-COMMON.
* Ne décrivez pas comme fonctionnant sur une carte ce qui a seulement été compilé.
* Signalez une vulnérabilité en privé : [SECURITY.md](SECURITY.md). Questions, idées et rapports : electrohobby3d@gmail.com ([SUPPORT.md](SUPPORT.md)).

## 👤 AUTEUR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENCE

GPL-3.0-or-later - voir [LICENSE](LICENSE).
