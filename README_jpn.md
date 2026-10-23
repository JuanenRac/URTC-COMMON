<p align="center">
  <img src="images/URTC_COMMON_BANNER.svg" alt="URTC-COMMON banner" width="100%">
</p>

# 🧩 URTC-COMMON

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | 🇯🇵 <b>日本語</b> | <a href="README_por.md">🇵🇹 Português</a></p>

### データとしての CAN プロトコル：仕様、生成されたコーデック、適合ベクトル、共有トランスポート

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Format-JSON%20%2B%20Python-083fa1.svg" alt="Format">
  <img src="https://img.shields.io/badge/Languages-8-00E5FF.svg" alt="Languages">
  <img src="https://img.shields.io/badge/Version-0.0.1-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**正直さの確認 - 今日実際に動くもの：** このリポジトリには、仕様、ジェネレーター、テストベクトル、小さな Python ライブラリが入っています。すべて CI で実行・テストされていますが、これまでに使っているのは URTC-FLASHER、URTC-TESTER、URTC-WEB-STUDIO だけです（識別子、マジックペイロード、ハードウェア ID、共有ベクトルを、ロックファイルで管理されたコピーとして）。ファームウェアとトランスポートは、それぞれが移行するまで各自のプロトコルのコピーを持ち続けます。仕様とそれらのコピーを比較するテストは、リポジトリがこのリポジトリの隣にチェックアウトされているときにそのテキストを読み、ないときはスキップされます。ここにあるものは基板や CAN アダプターに対して実行されたことはありません。トランスポートは疑似オブジェクトでテストされ、仕様は各識別子をどの実装が定義しているかを示すので、欠落は解決済みとみなされず、見える形で残ります。

---

> **安全性とセキュリティの現状:** このエコシステムは認証された安全システムではなく、実装済みの URTC 基板もまだ存在しません。ブートローダーはファームウェアイメージを CRC32 と共有鍵の HMAC-SHA256 で検査しており、非対称署名ではありません(予定)。公開されているアプリケーションイメージは公開の開発用鍵(`signing_key_kind: dev`)で署名されているため、誰でもブートローダーが受け入れるイメージを作れます。実際の基板には何も送信されていません。ここに書かれた内容を人の安全のために頼る前に、[セキュリティベースライン](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md)と[脅威モデル](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md)をお読みください。

## 📋 ひと目で

| | |
|---|---|
| バージョン | `0.0.7` |
| 成熟度 | 足場段階 |
| テスト | 532 |
| 技術 | JSON / Python |
| 実機での確認 | シミュレーションのみ：エミュレーター、模擬部品、シミュレーターで試験済み。このバージョンについて実機での動作記録はありません |

## 🎯 概要

ツールヘッドの CAN プロトコルを一度だけデータとして書き、そこから導かれるものすべて：

* [仕様](spec/can_protocol.json): 各識別子の方向、長さの規則、レイアウト、対象ツールとゲート、マジックペイロード、スレーブのレジスタ、SLCAN のサブセット、そして各識別子を定義している実装。
* [コントラクト](docs/CONTRACTS.md): 実装が守るべきこと、現在どの実装が何を実装しているか、そして既知の欠落と相違。
* [仕様のフォーマット](docs/SPEC_FORMAT.md): ファイルのキーと、識別子の追加・変更の方法。
* [移行](docs/MIGRATION.md): 各リポジトリが採用できる順序と、チェックがコピーを一致させ続ける仕組み。
* [プロトコル表](docs/PROTOCOL_TABLE.md): 仕様から生成された、すべての識別子を一つにまとめた表。
* [1本のバスに複数のツールヘッド](docs/MULTINODE.md): アドレス指定・検出・安全規則。URTC ファームウェアに、既定でオフのスイッチの背後で実装済みで、コンピュータ上でのみテストされ、ハードウェアでは試していません。
* インターフェース用ヘルパー: `src/urtc_ui`: デスクトップ用プログラムが共有できる言語一覧、状態バッジ、識別子・ビットレート・フレームの書式整形（Qt不要。URTC-FLASHER と URTC-TESTER は `vendor_copy.py --set ui` で作ったコピーを持っています）。
* ファームウェア部品: `firmware_base/urtc_crc8.h`（ラックとビジョンのシリアルフレームの CRC-8 を一か所にまとめたもの。`vendor_copy.py --set firmware_base` でコピー）と、`generated/urtc_fw_vectors.h`（ファームウェア自身が通すべきベクター。バージョン欄、マジックペイロード、CRC-8 の確認値）を C のテーブルとして提供します（`--set fw_vectors`）。
* シリアルリンクのフレーム層とレートリミッター：`firmware_base/urtc_frame.h`（長さバイトが決まった位置にあるフレームの開始バイト、バージョン、長さ、完全性、CRC-8 の判定と、逆方向の組み立て）と `firmware_base/urtc_rate_limiter.h`（受理したメッセージ間の最小間隔。ミリ秒カウンターの桁あふれをまたいでも正しく動作）。Python のリファレンス（`frame_layer.py`）、レートのベクター、そして両ヘッダーをラックとビジョンセンサーのすべての解析ベクターに照らす C テストが付きます（`vendor_copy.py --set firmware_frame` でコピー）
* 複数のプログラムが使う語句の用語集：`spec/i18n/glossary.json` は各語句を 8 言語で一度だけ定め、その通りに表示すべきフラッシャー、テスター、Web スタジオ、アップデーターのキーを列挙します（閉じる、更新、クリア、ヒーターの PID、ポートの検索 など）。`tools/i18n_glossary.py` はファイルを検証し、このリポジトリの隣にあるプログラムを検査し（大文字小文字、アクセント、句読点の違いは許容し、別の語は許容しません）、異なる `.lng` と `.json` の行を書き換えます。夜間の比較でも実行されます
* 言語ファイルの単一ソース：`spec/i18n/catalog/<プログラム>.json` がフラッシャー、テスター、Web スタジオ、アップデーターのすべてのテキストを 8 言語で保持します（用語集が挙げるテキストはその参照です）。`tools/i18n_generate.py sync` が各プログラムの `.lng`、`.json`、`.py` ファイルをロック（`urtc_i18n.lock.json`）と専用テストとともに書き出し、`check`（夜間の比較にも含まれます）はファイルがカタログの生成物と異なると失敗します。
* プログラム内のクイックガイドと共有される README セクション：`help_text.py`（フラッシャー、テスター、アップデーターそれぞれに 5 つの短い手順、8 言語）、`help_qt.py` と `qml/HelpDialog.qml`（ヘルプウィンドウ。`--set help` と `--set help_qml` でコピー）、そして `spec/readme/sections.json` と `tools/readme_sections.py`（「更新のしくみ」「ハードウェアなしの最初の書き込み」「互換性」を 8 言語で一度だけ書き、掲載するリポジトリの README ファイルのライセンス見出しの前にマーカーコメントで挟んで配置します。`check` は夜間の比較で実行されます）
* ファームウェアのホストテスト用アサーション: `firmware_base/urtc_test.h` は `TEST_ASSERT` を収めます。ラック、ビジョンツール、ツールヘッドの各ファームウェアが 3 回定義していたマクロです。各リポジトリは `vendor_copy.py --set firmware_test` でコピーし、自分のスイートを宣言する `test_runner.h` は各自で持ちます。
* [適合ベクトル](conformance/can_vectors.json): すべての実装が再現しなければならないバイト列：各レイアウト、拒否される入力、SLCAN ストリーム。
* [ツールプロファイル](spec/tools.json)：25 種類のツールプロファイル（上限・下限、ウォッチドッグ、ピン、拡張ボード）をデータとして保持します。`generate_tools.py` が TypeScript と Python の表および[ツール一覧表](docs/TOOLS_TABLE.md)を生成します。ほかに、CSV と JSON に書き出せるブラックボックスの読み取り機能（`blackbox.py`）、ラックのシミュレーター（`rack_sim.py`）、仕様から作るボードのファジング用フレーム（`fuzz.py`）、`spec/versions.json` から作るリリースの[互換性表](docs/COMPATIBILITY.md)があります。
* **仮想ボードと補助リンク:** `virtual_board.py` は SLCAN アダプターの背後にあるボードを TCP ポートで提供します (`python -m urtc_common.virtual_board`)。ツールがシリアルポートを尋ねる場所に `socket://127.0.0.1:7777` を入力すると、フラッシャー、テスター、ゲートウェイがハードウェアなしで最初から最後まで動きます。`sensor_frame.py` はビジョンヘッドのセンサーフレームのリファレンスで、これとラックのシリアルフレームはバス同様にビッグエンディアンのバージョン 2 で、ベクトル (`conformance/sensor_vectors.json`、`generated/sensor_vectors.h`) があります。
* **署名付きパッケージからの自己更新:** `self_update.py` は、GitHub のリリースから自分自身を更新するプログラムのための一連の流れ全体です。独自のネットワークやウィンドウは持たず（呼び出し側がダウンロードと進捗を渡します）、プラットフォーム向けパッケージのある厳密に高いバージョンだけを提示し、GitHub のリリースダウンロード用ホストからだけ取得し、告知されたサイズ、SHA-256、プログラムに固定された鍵による `urtc-pkg/1|アプリ|バージョン|プラットフォーム|sha256|サイズ` の Ed25519 署名を確認し、フォルダーの外に出ずに展開し（`..`、絶対パス、リンク、デバイスは不可）、バス上の操作が実行中はインストールを拒否し、直近 2 つのリリースを保持し、最初の起動に失敗したら自動で戻し、すべての手順を記録します。標準ライブラリのみ。`vendor_copy.py --set update` でコピーします。
* **描画するだけで使える、プログラムの「更新を確認」メニュー:** `update_service.py` にオプション（すべて保守的: 本人が求めない限り確認しない、`auto_check` は無効、`require_confirmation` は有効、チェックサムや署名を省く設定もホストを追加する設定もない。設定と `URTC_UPDATE_*` 環境変数があり、環境変数が優先され、実行が保護を下げると `lowering_warnings` が知らせる）、識別子付きで固定したリリースの Ed25519 鍵、`check` / `prepare` / `install` / `rollback` の各手順があります。`update_controller.py` はウィンドウが描画する状態機械（確認中、更新あり、ダウンロード中、準備完了、インストール中、完了。進捗とコード化されたエラー付き）で、`confirm_install` の後にだけインストールします。`launcher.py` は `current.txt` が指すリリースを起動し、初回起動に失敗すると前のリリースに戻します。`tools/make_update_package.py` はリリースの再現可能な `.zip` / `.tar.gz` を `.sha256` と `.sig` 付きで作り、固定した鍵で検証します。`vendor_copy.py --set update` でコピーします。
* **ツール：** `generate_constants.py` は C ヘッダー、TypeScript モジュール、Python モジュール、表を書き出します（`--check` で比較）。`make_conformance.py` はベクトルを書き出します（`--check`）。`vendor_copy.py` はロックファイル付きで他のリポジトリに一部をコピーし、そのコピーを検査します。`ci_validate.py` は共通のリポジトリ検査です。URTC-DOCS の `make_glance.py` が「ひと目で」の表を書きます。

## 🧩 URTC での役割

URTC-COMMON は、ツールヘッドの CAN プロトコルをデータとして一度だけ書き下す場所です。これにより、ファームウェア、URTC-FLASHER、URTC-TESTER、URTC-WEB-STUDIO が同じ文章の四通りの解釈を別々に保つ必要がなくなります。仕様、そこから生成されるもの、すべての実装が再現すべきベクトル、二つの Python ツールが共有するトランスポート層を収めています。これ自体はどれの動作も変えません。各リポジトリが段階的に採用します（docs/MIGRATION.md を参照）。

## 📂 リポジトリ構成

```text
URTC-COMMON/
├── docs/         コントラクト、仕様のフォーマット、移行ガイド、生成されたプロトコル表
├── spec/         仕様（can_protocol.json）とその JSON スキーマ
├── generated/    仕様から書き出した C ヘッダーと TypeScript モジュール
├── firmware_base/ ファームウェアのリポジトリが共有する C 部品（CRC-8）
├── conformance/  共有ベクトル
├── src/          Python パッケージ：生成されたプロトコル、フレーム、SLCAN コーデック、トランスポート、バージョン、ベクトル実行器
├── tools/        --check 付きジェネレーター、vendor_copy.py、エコシステム共通の CI 検査
├── tests/        ユニットテスト、隣のリポジトリとの比較、ベクトルの TypeScript 実行
├── images/       バナー
├── build.sh / build.bat, build-test.sh / build-test.bat, run.sh / run.bat
└── urtc.project.json, pyproject.toml, CHANGELOG.md, LICENSE
```

## 🛠️ ビルドと実行

**必要なもの：** Python 3.10 以降。テスト用に pytest と jsonschema。生成された TypeScript をベクトルに対して実行するには Node 22.18 以降（任意）

```bash
python tools/generate_constants.py --check           # C、TypeScript、Python のファイルと表が最新である
python tools/make_conformance.py --check             # ベクトルが最新である
python -m urtc_common.cli conformance                # このパッケージがすべてのベクトルを再現する
python tools/vendor_copy.py check TARGET --source .  # 他のリポジトリのコピーが手で編集されておらず、遅れてもいない
python -m pytest tests -q                            # ユニットテストと、隣のリポジトリとの比較
```

`build.sh` / `build.bat` はバージョンを一段階上げ（エコシステムのオドメーター方式）、パッケージをインストールしてテストを実行します。`build-test.sh` / `build-test.bat` はバージョンを変えずに検査します。`run.sh` / `run.bat` はコマンドライン（`conformance`、`describe`、`decode`、`slcan`）を起動します。

## 🔗 関連プロジェクト

URTC は独立したリポジトリで構成され、それぞれに固有のバージョン、テスト、README があります。グループ別のファミリーは次のとおりです：

* **URTC Tool Platform:** [URTC](https://github.com/JuanenRac/URTC), **URTC-COMMON** (このリポジトリ), [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER), [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY), [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK), [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER), [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL), [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)
* **Ecosystem Operations:** [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS), [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER)

**URTC の外：**

* **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** - ロボットアームのマザーボード。そのCANリレーが、ツールヘッドが接続されるバスとして文書化されています
* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - HYDRA-UMC エコシステム向けの同じ考え方
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - A.R.M.O.R. セキュリティエコシステム向けの同じ考え方
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - すべてのエコシステムのプロフィールとステータスダッシュボード

## 📚 ドキュメントとコミュニティ

さらに読むには：

* [コントラクト：各実装が守るべきことと既知の欠落](docs/CONTRACTS.md)
* [仕様のフォーマットと変更方法](docs/SPEC_FORMAT.md)
* [移行：各リポジトリの採用方法](docs/MIGRATION.md)
* [プロトコル表：各識別子と実装している側](docs/PROTOCOL_TABLE.md)
* [1本のバスに複数のツールヘッド](docs/MULTINODE.md)
* [このリポジトリの変更履歴](CHANGELOG.md)
* [ライセンス（GPL-3.0-or-later）](LICENSE)
* 質問、アイデア、報告：electrohobby3d@gmail.com

## 👤 作者

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 ライセンス

GPL-3.0-or-later - [LICENSE](LICENSE) を参照してください。
