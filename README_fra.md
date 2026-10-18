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
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Vérification d'honnêteté - ce qui fonctionne réellement aujourd'hui :** ce dépôt contient une spécification, des générateurs, des vecteurs de test et une petite bibliothèque Python. Tout s'exécute et est testé en CI, mais jusqu'ici seuls URTC-FLASHER, URTC-TESTER et URTC-WEB-STUDIO l'utilisent (les identifiants, les charges magiques, les identifiants matériels et les vecteurs partagés, sous forme de copies surveillées par un fichier de verrouillage) ; le firmware et les transports gardent leur propre copie du protocole jusqu'à ce que chacun migre. Les tests qui comparent la spécification à ces copies lisent leur texte lorsque les dépôts sont clonés à côté de celui-ci, et sont ignorés sinon. Rien de tout cela n'a été exécuté face à une carte ou à un adaptateur CAN : les transports sont testés avec des simulations, et la spécification indique pour chaque identifiant quelles implémentations le définissent, de sorte que les lacunes sont visibles au lieu d'être tenues pour résolues.

---

> **État de la sûreté et de la cybersécurité :** cet écosystème n'est pas un système de sécurité certifié et aucune carte URTC assemblée n'existe encore. Les bootloaders contrôlent les images de firmware par CRC32 et un HMAC-SHA256 à clé partagée, pas par une signature asymétrique (prévue) ; les images d'application publiées sont signées avec la clé publique de développement (`signing_key_kind: dev`), si bien que n'importe qui peut produire une image acceptée par le bootloader ; rien n'a été transmis à une carte réelle. Lisez la [base de sécurité](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) et le [modèle de menaces](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) avant de vous fier à une affirmation d'ici pour la sécurité d'une personne.

## 📋 En un coup d'œil

| | |
|---|---|
| Version | `0.0.2` |
| Maturité | Ébauche |
| Tests | 217 |
| Technologie | JSON / Python |
| Sur matériel réel | Simulé seulement : testé avec des émulateurs, des doubles de test ou des simulateurs ; aucune exécution sur du matériel réel n'est consignée pour cette version |

## 🎯 Vue d'ensemble

Le protocole CAN de la tête d'outil, écrit une seule fois comme données, et tout ce qui en découle :

* [Spécification](spec/can_protocol.json): chaque identifiant avec sa direction, sa règle de longueur, sa structure, ses outils et ses verrous, les charges magiques, les registres de l'esclave et le sous-ensemble SLCAN, et quelles implémentations définissent chacun.
* [Contrats](docs/CONTRACTS.md): ce qu'une implémentation doit faire, qui implémente quoi aujourd'hui, et les lacunes et différences connues.
* [Format de la spécification](docs/SPEC_FORMAT.md): les clés du fichier et comment ajouter ou modifier un identifiant.
* [Migration](docs/MIGRATION.md): l'ordre dans lequel chaque dépôt peut l'adopter, et comment une vérification garde les copies identiques.
* [Table du protocole](docs/PROTOCOL_TABLE.md): tous les identifiants dans une table, générée à partir de la spécification.
* [Vecteurs de conformité](conformance/can_vectors.json): les octets que toute implémentation doit reproduire : chaque structure, les refus et les flux SLCAN.
* **Outils :** `generate_constants.py` écrit l'en-tête C, le module TypeScript, le module Python et la table (`--check` compare), `make_conformance.py` écrit les vecteurs (`--check`), `vendor_copy.py` copie des parties dans un autre dépôt avec un fichier de verrouillage et vérifie la copie, et `ci_validate.py` est la vérification commune des dépôts. `make_glance.py` d'URTC-DOCS écrit le tableau En un coup d'œil.

## 🧩 Rôle dans URTC

URTC-COMMON est l'endroit où le protocole CAN de la tête d'outil est écrit une seule fois, comme données, afin que le firmware, URTC-FLASHER, URTC-TESTER et URTC-WEB-STUDIO cessent de tenir quatre lectures distinctes du même texte. Il contient la spécification, ce qui en est généré, les vecteurs que toute implémentation doit reproduire et la couche de transport que partagent les deux outils Python. À lui seul, il ne change le comportement d'aucun d'eux : chaque dépôt l'adopte pas à pas (voir docs/MIGRATION.md).

## 📂 Structure du dépôt

```text
URTC-COMMON/
├── docs/         contrats, format de la spécification, guide de migration, table du protocole générée
├── spec/         la spécification (can_protocol.json) et son schéma JSON
├── generated/    l'en-tête C et le module TypeScript, écrits à partir de la spécification
├── conformance/  les vecteurs partagés
├── src/          le paquet Python : protocole généré, trames, codec SLCAN, transports, versions, exécuteur de vecteurs
├── tools/        générateurs avec --check, vendor_copy.py et les vérifications de CI communes de l'écosystème
├── tests/        tests unitaires, la comparaison avec les dépôts voisins et l'exécution TypeScript des vecteurs
├── images/       la bannière
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ COMPILATION ET EXÉCUTION

**Prérequis :** Python 3.10 ou plus récent ; pytest et jsonschema pour les tests ; Node 22.18 ou plus récent pour exécuter le TypeScript généré contre les vecteurs (facultatif)

```bash
python tools/generate_constants.py --check           # les fichiers C, TypeScript et Python et la table sont à jour
python tools/make_conformance.py --check             # les vecteurs sont à jour
python -m urtc_common.cli conformance                # ce paquet reproduit chaque vecteur
python tools/vendor_copy.py check TARGET --source .  # une copie dans un autre dépôt n'a pas été modifiée à la main et n'a pas pris de retard
python -m pytest tests -q                            # les tests unitaires et la comparaison avec les dépôts voisins
```

`build.sh` / `build.bat` font avancer la version d'un cran (le compteur kilométrique de l'écosystème), installent le paquet et lancent les tests ; `build-test.sh` / `build-test.bat` vérifient sans changer aucune version ; `run.sh` / `run.bat` lancent la ligne de commande (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Projets liés

URTC est fait de dépôts indépendants, chacun avec sa version, ses tests et son README. Voici la famille, par groupes :

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (ce dépôt), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Au-delà de URTC :**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - la carte mère du bras robotique, dont le relais CAN est documenté comme le bus sur lequel se branche la tête d'outil
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - la même idée pour l'écosystème HYDRA-UMC
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - la même idée pour l'écosystème de sécurité A.R.M.O.R.
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - le profil et le tableau d'état de tous les écosystèmes

## 📚 Documentation et communauté

Pour en savoir plus :

* [Contrats : ce que chaque implémentation doit faire, et les lacunes connues](docs/CONTRACTS.md)
* [Format de la spécification et comment le modifier](docs/SPEC_FORMAT.md)
* [Migration : comment chaque dépôt l'adopte](docs/MIGRATION.md)
* [Table du protocole : chaque identifiant et qui l'implémente](docs/PROTOCOL_TABLE.md)
* [Journal des modifications de ce dépôt](CHANGELOG.md)
* [Licence (GPL-3.0-or-later)](LICENSE)
* Questions, idées et rapports : electrohobby3d@gmail.com

## 👤 AUTEUR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENCE

GPL-3.0-or-later - voir [LICENSE](LICENSE).
