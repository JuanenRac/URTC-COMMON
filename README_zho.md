<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | 🇨🇳 <b>简体中文</b> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### 作为数据的 CAN 协议：规范、生成的编解码器、一致性向量和共享传输层

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**诚实性检查 - 今天真正能运行的部分：** 本仓库包含一份规范、若干生成器、测试向量和一个小型 Python 库。所有内容都在 CI 中运行并经过测试，但目前只有 URTC-FLASHER、URTC-TESTER 和 URTC-WEB-STUDIO 在使用它（标识符、魔术载荷、硬件 ID 和共享向量，作为由锁文件保证一致的副本）；固件和传输层在各自迁移之前仍保留自己的协议副本。将规范与这些副本进行比较的测试，会在这些仓库与本仓库并排检出时读取它们的文本，否则跳过。这里的任何内容都没有在电路板或 CAN 适配器上运行过：传输层用模拟对象测试，规范则为每个标识符标明哪些实现定义了它，因此缺口是可见的，而不是被默认为已解决。

---

> **安全与安防现状:**本生态系统不是经认证的安全系统,目前也不存在已组装的 URTC 电路板。引导程序使用 CRC32 和共享密钥的 HMAC-SHA256 校验固件映像,而非非对称签名(计划中);已发布的应用映像使用公开的开发密钥签名(`signing_key_kind: dev`),因此任何人都可以生成引导程序接受的映像;尚未向任何真实电路板发送过任何内容。在依赖此处任何说法来保障人身安全之前,请先阅读[安全基线](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md)和[威胁模型](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md)。

## 📋 速览

| | |
|---|---|
| 版本 | `0.0.7` |
| 成熟度 | 雏形 |
| 测试 | 430 |
| 技术栈 | JSON / Python |
| 真实硬件 | 仅模拟：使用模拟器、替身或仿真测试；此版本没有在真实硬件上运行的记录 |

## 🎯 简介

工具头的 CAN 协议只写一次，以数据形式保存，并由它派生出所有内容：

* [规范](spec/can_protocol.json): 每个标识符的方向、长度规则、布局、适用工具和限制条件，魔术载荷、从机寄存器和 SLCAN 子集，以及哪些实现定义了每一项。
* [契约](docs/CONTRACTS.md): 实现必须做到的事、目前谁实现了什么，以及已知的缺口和差异。
* [规范格式](docs/SPEC_FORMAT.md): 文件的键，以及如何添加或修改标识符。
* [迁移](docs/MIGRATION.md): 各仓库采用它的顺序，以及检查如何保持副本一致。
* [协议表](docs/PROTOCOL_TABLE.md): 由规范生成的、包含全部标识符的一张表。
* [一条总线上的多个工具头](docs/MULTINODE.md): 寻址、发现和安全规则；已在 URTC 固件中实现，位于默认关闭的开关之后，仅在计算机上测试，尚未在硬件上试过。
* 界面辅助模块: `src/urtc_ui`：桌面程序可以共用的语言列表、状态徽章以及标识符、比特率和帧的格式化（不需要 Qt；URTC-FLASHER 和 URTC-TESTER 携带用 `vendor_copy.py --set ui` 生成的副本）。
* 固件部件: `firmware_base/urtc_crc8.h`，把工具架和视觉串行帧的 CRC-8 集中在一处（用 `vendor_copy.py --set firmware_base` 复制），以及 `generated/urtc_fw_vectors.h`，以 C 表格形式给出固件自身必须通过的向量（版本字段、魔术载荷、CRC-8 校验值）（`--set fw_vectors`）。
* [一致性向量](conformance/can_vectors.json): 每个实现都必须重现的字节：每种布局、被拒绝的输入和 SLCAN 数据流。
* [工具配置](spec/tools.json)：25 个工具配置（限值、看门狗、引脚、扩展板）以数据形式保存；`generate_tools.py` 生成 TypeScript 和 Python 表格以及[工具表](docs/TOOLS_TABLE.md)。此外还有：支持导出 CSV 和 JSON 的黑匣子读取器（`blackbox.py`）、机架模拟器（`rack_sim.py`）、根据规范生成的用于板卡模糊测试的帧（`fuzz.py`），以及由 `spec/versions.json` 生成的发布[兼容性表](docs/COMPATIBILITY.md)。
* **虚拟板与辅助链路：** `virtual_board.py` 在 TCP 端口上提供一块位于 SLCAN 适配器之后的板子（`python -m urtc_common.virtual_board`）；在工具要求串口的地方输入 `socket://127.0.0.1:7777`，刷写器、测试器和网关即可在没有硬件的情况下端到端运行。`sensor_frame.py` 是视觉头传感器帧的参考实现；它和机架串口帧都是版本 2，与总线一样采用大端序，并附有各自的向量（`conformance/sensor_vectors.json`、`generated/sensor_vectors.h`）。
* **从已签名的包自我更新：** `self_update.py` 是程序从 GitHub 发布版自我更新的完整流程，自身不涉及网络和窗口（下载与进度由调用方传入）：只提供平台对应包且版本严格更高的更新，只从 GitHub 发布下载所用的主机下载，用程序中固定的密钥核对公布的大小、SHA-256 以及 `urtc-pkg/1|应用|版本|平台|sha256|大小` 的 Ed25519 签名，解压时绝不离开目标文件夹（不允许 `..`、绝对路径、链接或设备），总线上有操作进行时拒绝安装，保留最近两个发布版，首次启动失败时自动回退，并记录每一步。仅用标准库；用 `vendor_copy.py --set update` 复制。
* **工具：** `generate_constants.py` 写出 C 头文件、TypeScript 模块、Python 模块和协议表（`--check` 用于比对），`make_conformance.py` 写出向量（`--check`），`vendor_copy.py` 带锁文件把部分内容复制到其他仓库并检查副本，`ci_validate.py` 是通用的仓库检查。URTC-DOCS 的 `make_glance.py` 负责写出“速览”表。

## 🧩 在 URTC 中的角色

URTC-COMMON 是工具头 CAN 协议以数据形式只写一次的地方，这样固件、URTC-FLASHER、URTC-TESTER 和 URTC-WEB-STUDIO 就不必再各自维护同一份文字的四种解读。它包含规范、由规范生成的内容、每个实现都必须重现的向量，以及两个 Python 工具共用的传输层。它本身不会改变其中任何一个的行为：各仓库逐步采用它（参见 docs/MIGRATION.md）。

## 📂 仓库结构

```text
URTC-COMMON/
├── docs/         契约、规范格式、迁移指南、生成的协议表
├── spec/         规范（can_protocol.json）及其 JSON Schema
├── generated/    由规范生成的 C 头文件和 TypeScript 模块
├── firmware_base/ 各固件仓库共用的 C 部件（CRC-8）
├── conformance/  共享向量
├── src/          Python 包：生成的协议、帧、SLCAN 编解码、传输层、版本、向量运行器
├── tools/        带 --check 的生成器、vendor_copy.py 以及生态系统通用的 CI 检查
├── tests/        单元测试、与相邻仓库的比较，以及向量的 TypeScript 运行
├── images/       横幅
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ 构建与运行

**要求：** Python 3.10 或更高版本；测试需要 pytest 和 jsonschema；用生成的 TypeScript 运行向量需要 Node 22.18 或更高版本（可选）

```bash
python tools/generate_constants.py --check           # C、TypeScript 和 Python 文件以及协议表都是最新的
python tools/make_conformance.py --check             # 向量是最新的
python -m urtc_common.cli conformance                # 本包重现每一个向量
python tools/vendor_copy.py check TARGET --source .  # 其他仓库中的副本没有被手工修改，也没有落后
python -m pytest tests -q                            # 单元测试以及与相邻仓库的比较
```

`build.sh` / `build.bat` 把版本提升一步（生态系统的里程表方案），安装软件包并运行测试；`build-test.sh` / `build-test.bat` 在不更改任何版本的情况下检查；`run.sh` / `run.bat` 启动命令行（`conformance`、`describe`、`decode`、`slcan`）。

## 🔗 相关项目

URTC 由相互独立的仓库组成，每个仓库都有自己的版本、测试和 README。以下是按组划分的家族：

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (本仓库), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**URTC 之外：**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - 机械臂主板，其 CAN 中继在文档中被记载为工具头所接入的总线
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - 同样的思路，用于 HYDRA-UMC 生态
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - 同样的思路，用于 A.R.M.O.R. 安防生态
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - 所有生态的个人主页和状态面板

## 📚 文档与社区

更多阅读：

* [契约：每个实现必须做到的事和已知缺口](docs/CONTRACTS.md)
* [规范格式及修改方法](docs/SPEC_FORMAT.md)
* [迁移：各仓库如何采用](docs/MIGRATION.md)
* [协议表：每个标识符及其实现者](docs/PROTOCOL_TABLE.md)
* [一条总线上的多个工具头](docs/MULTINODE.md)
* [本仓库的变更日志](CHANGELOG.md)
* [许可证（GPL-3.0-or-later）](LICENSE)
* 问题、想法和报告：electrohobby3d@gmail.com

## 👤 作者

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 许可证

GPL-3.0-or-later - 参见 [LICENSE](LICENSE)。
