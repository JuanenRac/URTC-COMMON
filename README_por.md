<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | 🇵🇹 <b>Português</b></p>

### O protocolo CAN como dados: especificação, codecs gerados, vetores de conformidade e transportes partilhados

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**Verificação de honestidade - o que funciona mesmo hoje:** este repositório contém uma especificação, geradores, vetores de teste e uma pequena biblioteca Python. Tudo é executado e testado em CI, mas até agora só a utilizam o URTC-FLASHER, o URTC-TESTER e o URTC-WEB-STUDIO (os identificadores, as cargas mágicas, os identificadores de hardware e os vetores partilhados, como cópias vigiadas por um ficheiro de bloqueio); o firmware e os transportes mantêm a sua própria cópia do protocolo até cada um migrar. Os testes que comparam a especificação com essas cópias leem o seu texto quando os repositórios estão clonados ao lado deste, e são ignorados quando não estão. Nada disto foi executado contra uma placa ou um adaptador CAN: os transportes são testados com simulações, e a especificação indica para cada identificador quais as implementações que o definem, de modo que as lacunas ficam visíveis em vez de se darem por resolvidas.

---

> **Estado de segurança (safety e security):** este ecossistema não é um sistema de segurança certificado e ainda não existe nenhuma placa URTC montada. Os bootloaders verificam as imagens de firmware com CRC32 e um HMAC-SHA256 de chave partilhada, não com uma assinatura assimétrica (prevista); as imagens de aplicação publicadas estão assinadas com a chave pública de desenvolvimento (`signing_key_kind: dev`), pelo que qualquer pessoa pode produzir uma imagem que o bootloader aceita; nada foi transmitido a uma placa real. Leia a [base de segurança](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e o [modelo de ameaças](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md) antes de confiar em qualquer afirmação aqui para a segurança de uma pessoa.

## 📋 Num relance

| | |
|---|---|
| Versão | `0.0.2` |
| Maturidade | Estrutura inicial |
| Testes | 217 |
| Tecnologia | JSON / Python |
| Em hardware real | Só simulado: testado com emuladores, dublês de teste ou simuladores; não há registo de execução em hardware real para esta versão |

## 🎯 Visão geral

O protocolo CAN da cabeça de ferramenta, escrito uma só vez como dados, e tudo o que dele decorre:

* [Especificação](spec/can_protocol.json): cada identificador com a sua direção, regra de comprimento, estrutura, ferramentas e bloqueios, as cargas mágicas, os registos do escravo e o subconjunto SLCAN, e quais as implementações que definem cada um.
* [Contratos](docs/CONTRACTS.md): o que uma implementação deve fazer, quem implementa o quê hoje, e as lacunas e diferenças conhecidas.
* [Formato da especificação](docs/SPEC_FORMAT.md): as chaves do ficheiro e como acrescentar ou alterar um identificador.
* [Migração](docs/MIGRATION.md): a ordem pela qual cada repositório a pode adotar e como uma verificação mantém as cópias iguais.
* [Tabela do protocolo](docs/PROTOCOL_TABLE.md): todos os identificadores numa tabela, gerada a partir da especificação.
* [Várias cabeças de ferramenta num barramento](docs/MULTINODE.md): endereçamento, descoberta e regras de segurança; implementados no firmware URTC atrás de um interruptor desligado por predefinição, testados apenas no computador e não testados em hardware.
* Auxiliares de interface: `src/urtc_ui`: a lista de idiomas, os distintivos de estado e a formatação de identificadores, débitos e tramas que os programas de ambiente de trabalho podem partilhar (sem Qt; o URTC-FLASHER e o URTC-TESTER trazem uma cópia feita com `vendor_copy.py --set ui`).
* [Vetores de conformidade](conformance/can_vectors.json): os bytes que toda a implementação deve reproduzir: cada estrutura, as recusas e os fluxos SLCAN.
* **Ferramentas:** `generate_constants.py` escreve o cabeçalho C, o módulo TypeScript, o módulo Python e a tabela (`--check` compara), `make_conformance.py` escreve os vetores (`--check`), `vendor_copy.py` copia partes para outro repositório com um ficheiro de bloqueio e verifica a cópia, e `ci_validate.py` é a verificação partilhada dos repositórios. O `make_glance.py` do URTC-DOCS escreve a tabela Num relance.

## 🧩 Papel no URTC

O URTC-COMMON é o lugar onde o protocolo CAN da cabeça de ferramenta é escrito uma só vez, como dados, para que o firmware, o URTC-FLASHER, o URTC-TESTER e o URTC-WEB-STUDIO deixem de manter quatro leituras distintas do mesmo texto. Contém a especificação, o que dela se gera, os vetores que toda a implementação deve reproduzir e a camada de transporte que as duas ferramentas Python partilham. Por si só não altera o comportamento de nenhuma delas: cada repositório adota-o passo a passo (ver docs/MIGRATION.md).

## 📂 Estrutura do repositório

```text
URTC-COMMON/
├── docs/         contratos, formato da especificação, guia de migração, tabela do protocolo gerada
├── spec/         a especificação (can_protocol.json) e o seu esquema JSON
├── generated/    o cabeçalho C e o módulo TypeScript, escritos a partir da especificação
├── conformance/  os vetores partilhados
├── src/          o pacote Python: protocolo gerado, tramas, codec SLCAN, transportes, versões, executor de vetores
├── tools/        geradores com --check, vendor_copy.py e as verificações de CI partilhadas do ecossistema
├── tests/        testes unitários, a comparação com os repositórios ao lado deste e a execução dos vetores em TypeScript
├── images/       o banner
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ COMPILAÇÃO E EXECUÇÃO

**Requisitos:** Python 3.10 ou superior; pytest e jsonschema para os testes; Node 22.18 ou superior para executar o TypeScript gerado contra os vetores (opcional)

```bash
python tools/generate_constants.py --check           # os ficheiros C, TypeScript e Python e a tabela estão atualizados
python tools/make_conformance.py --check             # os vetores estão atualizados
python -m urtc_common.cli conformance                # este pacote reproduz todos os vetores
python tools/vendor_copy.py check TARGET --source .  # uma cópia noutro repositório não foi editada à mão nem ficou desatualizada
python -m pytest tests -q                            # os testes unitários e a comparação com os repositórios ao lado deste
```

`build.sh` / `build.bat` sobem a versão um passo (o conta-quilómetros do ecossistema), instalam o pacote e executam os testes; `build-test.sh` / `build-test.bat` verificam sem alterar nenhuma versão; `run.sh` / `run.bat` iniciam a linha de comandos (`conformance`, `describe`, `decode`, `slcan`).

## 🔗 Projetos relacionados

O URTC é feito de repositórios independentes, cada um com a sua versão, os seus testes e o seu README. Esta é a família, por grupos:

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (este repositório), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**Para além do URTC:**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - a placa-mãe do braço robótico, cujo relé CAN está documentado como o barramento onde a cabeça de ferramenta se liga
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - a mesma ideia para o ecossistema HYDRA-UMC
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - a mesma ideia para o ecossistema de segurança A.R.M.O.R.
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - o perfil e o painel de estado de todos os ecossistemas

## 📚 Documentação e comunidade

Onde ler mais:

* [Contratos: o que cada implementação deve fazer e as lacunas conhecidas](docs/CONTRACTS.md)
* [Formato da especificação e como a alterar](docs/SPEC_FORMAT.md)
* [Migração: como cada repositório a adota](docs/MIGRATION.md)
* [Tabela do protocolo: cada identificador e quem o implementa](docs/PROTOCOL_TABLE.md)
* [Várias cabeças de ferramenta num barramento](docs/MULTINODE.md)
* [Registo de alterações deste repositório](CHANGELOG.md)
* [Licença (GPL-3.0-or-later)](LICENSE)
* Perguntas, ideias e relatórios: electrohobby3d@gmail.com

## 👤 AUTOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENÇA

GPL-3.0-or-later - consulte [LICENSE](LICENSE).
