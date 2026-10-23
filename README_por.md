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
| Versão | `0.0.7` |
| Maturidade | Estrutura inicial |
| Testes | 431 |
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
* Peças de firmware: `firmware_base/urtc_crc8.h`, o CRC-8 das tramas série do rack e da visão num só sítio (copiado com `vendor_copy.py --set firmware_base`), e `generated/urtc_fw_vectors.h`, os vetores que o próprio firmware tem de passar (campos de versão, cargas mágicas, valores de verificação do CRC-8) como tabelas C (`--set fw_vectors`).
* A camada de trama e o limitador de cadência das ligações série: `firmware_base/urtc_frame.h` (byte inicial, versão, comprimento, completude e CRC-8 de uma trama cujo byte de comprimento está numa posição dada, e o caminho inverso) e `firmware_base/urtc_rate_limiter.h` (o intervalo mínimo entre mensagens aceites, através do retorno a zero do contador de milissegundos), com uma referência em Python (`frame_layer.py`), vetores de cadência e um teste em C que sujeita ambos os cabeçalhos a cada vetor de análise do rack e do sensor de visão (copiados com `vendor_copy.py --set firmware_frame`)
* Um glossário das expressões que vários programas dizem: `spec/i18n/glossary.json` nomeia cada uma uma só vez, nas oito línguas, e lista as chaves do flasher, do tester, do estúdio web e do updater que a têm de dizer assim (Fechar, Atualizar, Limpar, PID do aquecedor, Pesquisa de portas ...); `tools/i18n_glossary.py` verifica o ficheiro, verifica os programas ao lado deste repositório (maiúsculas, acentos e pontuação são perdoados, uma palavra diferente não) e reescreve as linhas dos ficheiros `.lng` e `.json` que diferem; a comparação noturna executa-o
* Uma só fonte para os ficheiros de idioma: `spec/i18n/catalog/<programa>.json` guarda todos os textos do flasher, do tester, do web studio e do atualizador nos oito idiomas (um texto que o glossário nomeia é uma referência a ele); `tools/i18n_generate.py sync` escreve os ficheiros `.lng`, `.json` e `.py` de cada programa com um lock (`urtc_i18n.lock.json`) e um teste próprio, e `check` (também na comparação noturna) falha quando um ficheiro não é o que o catálogo gera.
* O guia rápido dentro dos programas e as secções de README que partilham: `help_text.py` (cinco passos curtos para cada um de flasher, tester e atualizador nas oito línguas), `help_qt.py` e `qml/HelpDialog.qml` (a janela de ajuda; copiados com `--set help` e `--set help_qml`), e `spec/readme/sections.json` com `tools/readme_sections.py` («Como se atualiza», «Primeira gravação sem hardware» e «Compatibilidade», escritas uma só vez nas oito línguas e colocadas entre comentários marcadores antes do título da licença dos ficheiros README dos repositórios que as listam; `check` corre na comparação noturna)
* A asserção dos testes de host do firmware: `firmware_base/urtc_test.h` contém `TEST_ASSERT`, a macro que o firmware do rack, da ferramenta de visão e da cabeça definia três vezes; cada repositório copia-a com `vendor_copy.py --set firmware_test` e mantém o seu próprio `test_runner.h` com as suas suites.
* [Vetores de conformidade](conformance/can_vectors.json): os bytes que toda a implementação deve reproduzir: cada estrutura, as recusas e os fluxos SLCAN.
* [Perfis de ferramenta](spec/tools.json): os 25 perfis de ferramenta (limites, watchdog, pinos, placa de expansão) como dados; o `generate_tools.py` escreve as tabelas de TypeScript e Python e [a tabela de ferramentas](docs/TOOLS_TABLE.md). Também aqui: o leitor da caixa negra com exportação para CSV e JSON (`blackbox.py`), o simulador do rack (`rack_sim.py`), tramas para testar uma placa com fuzzing, criadas a partir da especificação (`fuzz.py`) e a [tabela de compatibilidade](docs/COMPATIBILITY.md) de uma versão, criada a partir de `spec/versions.json`.
* **Placa virtual e ligações complementares:** `virtual_board.py` serve uma placa atrás de um adaptador SLCAN numa porta TCP (`python -m urtc_common.virtual_board`); escreva `socket://127.0.0.1:7777` onde uma ferramenta pede uma porta série e o programador, o testador e a gateway funcionam de ponta a ponta sem hardware. `sensor_frame.py` é a referência da trama do sensor da cabeça de visão; ela e a trama série do rack são a versão 2, big-endian como o barramento, com os seus vetores (`conformance/sensor_vectors.json`, `generated/sensor_vectors.h`).
* **Autoatualização a partir de um pacote assinado:** `self_update.py` é todo o fluxo de um programa que se atualiza sozinho a partir de uma release do GitHub, sem rede nem janela próprias (quem o chama passa a descarga e o progresso): oferece apenas uma versão estritamente superior com pacote para a plataforma, descarrega só dos anfitriões de descargas de releases do GitHub, verifica o tamanho anunciado, o SHA-256 e a assinatura Ed25519 de `urtc-pkg/1|app|versão|plataforma|sha256|tamanho` com a chave fixada no programa, extrai sem nunca sair da pasta (sem `..`, caminho absoluto, ligação ou dispositivo), recusa instalar enquanto uma operação no bus estiver a decorrer, mantém as duas últimas releases, volta atrás sozinha se o primeiro arranque falhar e regista cada passo. Só biblioteca padrão; copia-se com `vendor_copy.py --set update`.
* **O menu «Procurar atualizações» dos programas, pronto a desenhar:** `update_service.py` contém as opções (todas prudentes: nenhuma verificação sem pedido da pessoa, `auto_check` desligado, `require_confirmation` ligado, nenhuma opção para saltar a soma de verificação ou a assinatura nem para acrescentar um anfitrião; definições e variáveis `URTC_UPDATE_*`, o ambiente prevalece e `lowering_warnings` avisa quando uma execução baixa uma proteção), a chave Ed25519 das versões fixada com o seu identificador e os passos `check` / `prepare` / `install` / `rollback`; `update_controller.py` é a máquina de estados que uma janela desenha (a verificar, disponível, a transferir, pronto, a instalar, instalado, com progresso e erro codificado) e só instala depois de `confirm_install`; `launcher.py` arranca a versão para onde `current.txt` aponta e volta à anterior se um primeiro arranque falhar; `tools/make_update_package.py` constrói o `.zip` / `.tar.gz` reproduzível de uma versão com o seu `.sha256` e `.sig` e verifica-o com a chave fixada. Copiado com `vendor_copy.py --set update`.
* **Ferramentas:** `generate_constants.py` escreve o cabeçalho C, o módulo TypeScript, o módulo Python e a tabela (`--check` compara), `make_conformance.py` escreve os vetores (`--check`), `vendor_copy.py` copia partes para outro repositório com um ficheiro de bloqueio e verifica a cópia, e `ci_validate.py` é a verificação partilhada dos repositórios. O `make_glance.py` do URTC-DOCS escreve a tabela Num relance.

## 🧩 Papel no URTC

O URTC-COMMON é o lugar onde o protocolo CAN da cabeça de ferramenta é escrito uma só vez, como dados, para que o firmware, o URTC-FLASHER, o URTC-TESTER e o URTC-WEB-STUDIO deixem de manter quatro leituras distintas do mesmo texto. Contém a especificação, o que dela se gera, os vetores que toda a implementação deve reproduzir e a camada de transporte que as duas ferramentas Python partilham. Por si só não altera o comportamento de nenhuma delas: cada repositório adota-o passo a passo (ver docs/MIGRATION.md).

## 📂 Estrutura do repositório

```text
URTC-COMMON/
├── docs/         contratos, formato da especificação, guia de migração, tabela do protocolo gerada
├── spec/         a especificação (can_protocol.json) e o seu esquema JSON
├── generated/    o cabeçalho C e o módulo TypeScript, escritos a partir da especificação
├── firmware_base/ peças C partilhadas pelos repositórios de firmware (o CRC-8)
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

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (este repositório), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
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
