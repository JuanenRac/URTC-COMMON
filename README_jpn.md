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
  <img src="https://img.shields.io/badge/Version-0.0.8-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Tests-1398-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Maturity-scaffolding-FFB020.svg" alt="Maturity">
</p>

---

**正直さの確認 - 今日実際に動くもの：** このリポジトリには、仕様、ジェネレーター、テストベクトル、小さな Python ライブラリが入っています。すべて CI で実行・テストされていますが、これまでに使っているのは URTC-FLASHER、URTC-TESTER、URTC-WEB-STUDIO だけです（識別子、マジックペイロード、ハードウェア ID、共有ベクトルを、ロックファイルで管理されたコピーとして）。ファームウェアとトランスポートは、それぞれが移行するまで各自のプロトコルのコピーを持ち続けます。仕様とそれらのコピーを比較するテストは、リポジトリがこのリポジトリの隣にチェックアウトされているときにそのテキストを読み、ないときはスキップされます。ここにあるものは基板や CAN アダプターに対して実行されたことはありません。トランスポートは疑似オブジェクトでテストされ、仕様は各識別子をどの実装が定義しているかを示すので、欠落は解決済みとみなされず、見える形で残ります。

---

> **安全性とセキュリティの現状:** このエコシステムは認証された安全システムではなく、実装済みの URTC 基板もまだ存在しません。ブートローダーはファームウェアイメージを CRC32 と共有鍵の HMAC-SHA256 で検査しており、非対称署名ではありません(予定)。公開されているアプリケーションイメージは公開の開発用鍵(`signing_key_kind: dev`)で署名されているため、誰でもブートローダーが受け入れるイメージを作れます。実際の基板には何も送信されていません。ここに書かれた内容を人の安全のために頼る前に、[セキュリティベースライン](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/SECURITY_BASELINE.md)と[脅威モデル](https://github.com/JuanenRac/URTC-DOCS/blob/main/docs/THREAT_MODEL.md)をお読みください。

## 📋 ひと目で

| | |
|---|---|
| バージョン | `0.1.1` |
| 成熟度 | 足場段階 |
| テスト | 1398 |
| 技術 | JSON / Python |
| 実機での確認 | シミュレーションのみ：エミュレーター、模擬部品、シミュレーターで試験済み。このバージョンについて実機での動作記録はありません |

**移動先：** [概要](#-概要) · [アーキテクチャ](#-アーキテクチャ) · [クイックスタート](#-クイックスタート) · [テスト](#-テスト) · [構成](#-リポジトリの構成) · [関連](#-関連プロジェクト)

<!-- urtc-section:status_common -->
## 🚦 プロジェクトの状況

🟢 完了・検証済み · 🟡 動作するが既知の制限あり · 🟠 途中、または未検証 · 🔴 未実施または動作しない。実機で一度も動いていないものは緑になりません。

| 項目 | 状態 | リポジトリが示せること |
| --- | :---: | --- |
| ソフトウェア | 🟡 | 他のプログラムが使う共通コード。PC 上のテストでのみ確認しています。 |
| テスト | 🟡 | テストスイートはプッシュごとに CI で通ります。 |
| セキュリティ | 🟡 | リリースは Ed25519 で署名され、使用前に検証されます。鍵の扱いは他の人によるレビューを受けていません。 |
| ドキュメント | 🟡 | 8 言語の README と参照ドキュメントがあります。翻訳はネイティブによるレビューを受けていません。 |

<!-- /urtc-section:status_common -->

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
* プログラム内のクイックガイドと共有される README セクション：`help_text.py`（フラッシャー、テスター、アップデーターそれぞれに短い手順、8 言語）、`help_qt.py` と `qml/HelpDialog.qml`（ヘルプウィンドウ。`--set help` と `--set help_qml` でコピー）、そして `spec/readme/sections.json` と `tools/readme_sections.py`（各プログラムのプロジェクトの状況と、複数の README が共有する部分を 8 言語で一度だけ書き、マーカーコメントで挟んで構成上の所定の位置に配置します。`check` は夜間の比較で実行されます）
* ファームウェアのホストテスト用アサーション: `firmware_base/urtc_test.h` は `TEST_ASSERT` を収めます。ラック、ビジョンツール、ツールヘッドの各ファームウェアが 3 回定義していたマクロです。各リポジトリは `vendor_copy.py --set firmware_test` でコピーし、自分のスイートを宣言する `test_runner.h` は各自で持ちます。
* [適合ベクトル](conformance/can_vectors.json): すべての実装が再現しなければならないバイト列：各レイアウト、拒否される入力、SLCAN ストリーム。
* [ツールプロファイル](spec/tools.json)：25 種類のツールプロファイル（上限・下限、ウォッチドッグ、ピン、拡張ボード）をデータとして保持します。`generate_tools.py` が TypeScript と Python の表および[ツール一覧表](docs/TOOLS_TABLE.md)を生成します。ほかに、CSV と JSON に書き出せるブラックボックスの読み取り機能（`blackbox.py`）、ラックのシミュレーター（`rack_sim.py`）、仕様から作るボードのファジング用フレーム（`fuzz.py`）、`spec/versions.json` から作るリリースの[互換性表](docs/COMPATIBILITY.md)と、各リポジトリのマニフェストから作る、実行済みの内容と未了の内容の[状態表](docs/STATUS.md)（`status_table.py`）があります。
* [ヘッドのフリー構成](docs/FREE_TOOL.md): IDジャンパが `0x1F` を示すヘッドをラックがどう扱うか。ラックは問い合わせ(`0x1A3`)、応答を検証し、ジャンパで読み取ったヘッドと同じように識別情報を使います。それまでヘッドは安全状態のままです。`rack_sim.py` でモデル化し、ラックのファームウェアが再生する共有ベクタ(`conformance/rack_vectors.json`)を備えます。
* [シミュレートされたバスのシナリオ](docs/BUS_SCENARIOS.md)：CAN バスの障害を JSON ファイル（`urtc-scenario/1`）で記述します。フレームの欠落・重複・順序入れ替え・遅延・バースト欠落・短縮、無応答のノードや理由付きでコマンドを拒否するノード、`0x1A3` と `0x1A2` にさまざまな形で応答する自由構成のヘッドを扱えます。`bus_scenario.py` はファイルを厳密に検査し、任意のシミュレート転送に適用し、シードからテスト用シナリオを生成します。同じシードなら同じフレームになります。求めない限り無効で、フラッシャーとテスターは `--scenario` でプランを実行し、シミュレーションだったことを記したエビデンス記録を残します。
* **仮想ボードと補助リンク:** `virtual_board.py` は SLCAN アダプターの背後にあるボードを TCP ポートで提供します (`python -m urtc_common.virtual_board`)。ツールがシリアルポートを尋ねる場所に `socket://127.0.0.1:7777` を入力すると、フラッシャー、テスター、ゲートウェイがハードウェアなしで最初から最後まで動きます。`sensor_frame.py` はビジョンヘッドのセンサーフレームのリファレンスで、これとラックのシリアルフレームはバス同様にビッグエンディアンのバージョン 2 で、ベクトル (`conformance/sensor_vectors.json`、`generated/sensor_vectors.h`) があります。
* **署名付きパッケージからの自己更新:** `self_update.py` は、GitHub のリリースから自分自身を更新するプログラムのための一連の流れ全体です。独自のネットワークやウィンドウは持たず（呼び出し側がダウンロードと進捗を渡します）、プラットフォーム向けパッケージのある厳密に高いバージョンだけを提示し、GitHub のリリースダウンロード用ホストからだけ取得し、告知されたサイズ、SHA-256、プログラムに固定された鍵による `urtc-pkg/1|アプリ|バージョン|プラットフォーム|sha256|サイズ` の Ed25519 署名を確認し、フォルダーの外に出ずに展開し（`..`、絶対パス、リンク、デバイスは不可）、バス上の操作が実行中はインストールを拒否し、直近 2 つのリリースを保持し、最初の起動に失敗したら自動で戻し、すべての手順を記録します。標準ライブラリのみ。`vendor_copy.py --set update` でコピーします。
* **描画するだけで使える、プログラムの「更新を確認」メニュー:** `update_service.py` にオプション（すべて保守的: 本人が求めない限り確認しない、`auto_check` は無効、`require_confirmation` は有効、チェックサムや署名を省く設定もホストを追加する設定もない。設定と `URTC_UPDATE_*` 環境変数があり、環境変数が優先され、実行が保護を下げると `lowering_warnings` が知らせる）、識別子付きで固定したリリースの Ed25519 鍵、`check` / `prepare` / `install` / `rollback` の各手順があります。`update_controller.py` はウィンドウが描画する状態機械（確認中、更新あり、ダウンロード中、準備完了、インストール中、完了。進捗とコード化されたエラー付き）で、`confirm_install` の後にだけインストールします。`launcher.py` は `current.txt` が指すリリースを起動し、初回起動に失敗すると前のリリースに戻します。`tools/make_update_package.py` はリリースの再現可能な `.zip` / `.tar.gz` を `.sha256` と `.sig` 付きで作り、固定した鍵で検証します。`vendor_copy.py --set update` でコピーします。
* **ツール：** `generate_constants.py` は C ヘッダー、TypeScript モジュール、Python モジュール、表を書き出します（`--check` で比較）。`make_conformance.py` はベクトルを書き出します（`--check`）。`vendor_copy.py` はロックファイル付きで他のリポジトリに一部をコピーし、そのコピーを検査します。`ci_validate.py` は共通のリポジトリ検査です。URTC-DOCS の `make_glance.py` が「ひと目で」の表を書きます。
* **インストール可能なパッケージ:** 各リリースには、署名付きの Python ホイール(`urtc-common`、PyPI には公開しません)、署名付きのソースアーカイブ、署名付きの生成済み C ヘッダーが添付されます。これらは `make_release_artifacts.py`(`build`、`verify`、`reproduce`、`smoke`)で再現可能にビルドされ、署名は各プログラムがすでに信頼しているリリース鍵のものです。[ガイド](docs/PACKAGE.md)を参照してください。`generate_canbus_doc.py` は、ファームウェア側リポジトリの `docs/CANBUS.TXT` の参照表を仕様から書き出します(周囲の本文には触れず、`--check` で比較します)。

- **証跡レコードとその履歴：** `evidence.py` がレコード（`urtc-evidence/1`、[docs/EVIDENCE.md](docs/EVIDENCE.md)）を書き込んで検査し、`evidence_history.py` がフォルダー内のレコードを新しい順に一つずつ検査して一覧にします。`evidence_history_qt.py`、`qml/EvidenceHistoryDialog.qml`、`evidence_history_strings.py`（8 言語）は URTC-FLASHER、URTC-TESTER、URTC-UPDATER が共有する履歴ウィンドウです（`vendor_copy.py --set history_qt` と `--set history_qml` でコピー）。

- **リリースノート：** `tools/changelog_section.py VERSION [--heading] [--compat]` は、あるバージョンの CHANGELOG の節を出力し、`--compat` を付けると続けて `docs/COMPATIBILITY.md` の互換性表を出力します。各プログラムはそのコピー（`vendor_copy.py --set release_notes`、表には `--set compat`）を持ち、リリースの本文が同じ形になります。

## 🧩 URTC での役割

URTC-COMMON は、ツールヘッドの CAN プロトコルをデータとして一度だけ書き下す場所です。これにより、ファームウェア、URTC-FLASHER、URTC-TESTER、URTC-WEB-STUDIO が同じ文章の四通りの解釈を別々に保つ必要がなくなります。仕様、そこから生成されるもの、すべての実装が再現すべきベクトル、二つの Python ツールが共有するトランスポート層を収めています。これ自体はどれの動作も変えません。各リポジトリが段階的に採用します（docs/MIGRATION.md を参照）。

## 🏛️ アーキテクチャ

<p align="center">
  <img src="images/architecture.svg" alt="URTC-COMMON のアーキテクチャ：誰が使い、何を持ち、何に依存するか" width="100%">
</p>

このリポジトリの各部分の関係：誰が使い、何を持ち、何に依存するか。図は `docs/architecture.json` から描かれ、コードと照合されます。

## 🚀 クイックスタート

**必要なもの：** Python 3.10 以降。テスト用に pytest と jsonschema。生成された TypeScript をベクトルに対して実行するには Node 22.18 以降（任意）

```bash
python tools/generate_constants.py --check           # C、TypeScript、Python のファイルと表が最新である
python tools/make_conformance.py --check             # ベクトルが最新である
python -m urtc_common.cli conformance                # このパッケージがすべてのベクトルを再現する
python tools/vendor_copy.py check TARGET --source .  # 他のリポジトリのコピーが手で編集されておらず、遅れてもいない
python -m pytest tests -q                            # ユニットテストと、隣のリポジトリとの比較
python -m mypy                                       # urtc_common と urtc_ui の型チェック
```

## 🧪 テスト

テストスイートは 1398 件です（`python -m pytest tests -q`）。仕様とそのスキーマ、生成された C・TypeScript・Python ファイルとジェネレーターの出力、Python・Node 上の TypeScript・ホストコンパイラ上の C での適合ベクトル、SLCAN コーデックと模擬を使ったトランスポート、仮想ボード、署名付き自己更新の流れ、そしてこのリポジトリの隣にチェックアウトされたリポジトリとの比較を検査します。任意のツール（Node、C コンパイラ、PySide6）や隣のリポジトリがない場合、一部のテストはスキップされます。`python -m mypy` がパッケージの型を検査します。

## 🏗️ ビルドとリリース

`build.sh` / `build.bat` はパッケージをインストールしてテストを実行します。`build-test.sh` / `build-test.bat` はバージョンを変えずに検査します。`run.sh` / `run.bat` はコマンドライン（`conformance`、`describe`、`decode`、`slcan`）を起動します。各リリースには、署名付きの Python wheel（`urtc-common`、PyPI には無し）、署名付きのソースアーカイブ、署名付きの生成 C ヘッダーが付属し、`tools/make_release_artifacts.py`（`build`、`verify`、`reproduce`、`smoke`）で再現可能にビルドされます。[パッケージガイド](docs/PACKAGE.md)を参照してください。

## 📂 リポジトリの構成

<p align="center">
  <img src="images/repository-structure.svg" alt="URTC-COMMON のリポジトリ構成" width="100%">
</p>

<details>
<summary>ツリーのテキスト版</summary>

```text
URTC-COMMON/
├── spec/                                            仕様、ツールプロファイル、バージョン、テキストカタログ
├── src/urtc_common/                                 Python パッケージ：プロトコル、SLCAN、トランスポート、仮想ボード、自己更新
├── tools/                                           --check 付きのジェネレーター、vendor_copy.py、共有 CI チェック
├── docs/                                            コントラクト、形式、移行ガイド、生成された表
├── conformance/                                     共有ベクトル
├── generated/                                       C ヘッダー、TypeScript モジュール、ベクトルヘッダー
├── firmware_base/                                   ファームウェアのリポジトリが共有する C の部品
├── qml/                                             各プログラムが共有する Qt Quick ウィンドウ
├── tests/                                           ユニットテストと隣接リポジトリとの比較
├── .github/                                         CI ワークフローと Issue・プルリクエストのテンプレート
├── images/                                          バナーとこの README の画像
├── build.sh build.bat                               ビルドスクリプト
├── build-test.sh build-test.bat                     リポジトリを変更しないビルド・テストのスクリプト
├── test.sh test.bat                                 テストを実行
├── run.sh run.bat                                   プログラムを起動
├── urtc.project.json                                マニフェスト：バージョン、役割、成熟度、ビルドコマンド
├── CHANGELOG.md                                     各バージョンの変更内容
├── SECURITY.md SUPPORT.md LICENSE                   セキュリティポリシー、サポート、ライセンス
├── NOTICE                                           同梱するサードパーティ部分のライセンス
├── CONTRIBUTING.md CODE_OF_CONDUCT.md               貢献方法と行動規範
├── .gitattributes .gitignore                        Git の設定
├── bump_version.py bump_manifest_version.py         バージョンを上げるスクリプト
└── pyproject.toml requirements-dev.lock ruff.toml   パッケージ、固定されたツール、lint 設定
```

</details>

## 🗺️ ロードマップと既知の制限

**現時点で分かっている制限**

* ここにあるものは、実機のボードや CAN アダプターでは一度も動かしていません。トランスポートは模擬で試験され、仕様は各識別子をどの実装が定義しているかを示すので、欠けている部分が見えます。
* ファームウェアとトランスポートは、それぞれが移行するまで独自のプロトコルのコピーを持ちます。現在このリポジトリを使うのは URTC-FLASHER、URTC-TESTER、URTC-WEB-STUDIO だけです。
* 仕様を他のリポジトリと比較するテストは、それらがこのリポジトリの隣にチェックアウトされているときにその内容を読み、ないときはスキップされます。

**次のステップ**

* 各リポジトリを段階的に仕様へ移行します（[移行ガイド](docs/MIGRATION.md)）。

## 🌍 言語

README とテキストは、英語、スペイン語、フランス語、イタリア語、ドイツ語、中国語、日本語、ヨーロッパポルトガル語で提供されています。

## 🔗 関連プロジェクト

URTC は独立したリポジトリで構成され、それぞれに固有のバージョン、テスト、README があります。グループ別のファミリーは次のとおりです：

* **URTC Tool Platform:**
  * [URTC](https://github.com/JuanenRac/URTC) - ツールヘッド基板のファームウェア(25 のツールプロファイル、CAN ブートローダー)と CAN プロトコルのリファレンス。
  * **URTC-COMMON** (このリポジトリ) - 一度だけデータとして書かれた CAN プロトコル(仕様、生成された表、適合ベクトル)と、各プログラムが共有するコード。
  * [URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER) - CAN または SWD/JTAG で基板のファームウェアを更新するデスクトップツール。
  * [URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY) - CAN バスの手前に置くゲートウェイ。一覧にある識別子だけを通し、レートを制限し、セッション鍵を求めます。
  * [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK) - 予熱とライフサイクル追跡を備えたツールラック向けの、ハードウェア非依存の C ロジックとコマンドプロトコル。
  * [URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER) - 基板が報告するツールプロファイルの操作部とテレメトリを表示する、デスクトップ用のライブ CAN バステスター。
  * [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL) - C のセンサーフレームプロトコルと、検査用ツールヘッド向けの Python サーマル/RGB コンパニオン。
  * [URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO) - Web Serial と SLCAN で基板の書き込みとテストを行うブラウザアプリ。インストール不要。
* **Ecosystem Operations:**
  * [URTC-DEVTOOLS](https://github.com/JuanenRac/URTC-DEVTOOLS) - ファミリー共通のリポジトリツールを、版数付きの一つのセットとして提供します。ロックファイルで、編集されたコピーと古いままのコピーを見分けられます。
  * [URTC-DOCS](https://github.com/JuanenRac/URTC-DOCS) - エコシステムのアーキテクチャ、インターフェース、セキュリティベースライン、生成されたカタログと、全リポジトリを比較するツール。
  * [URTC-UPDATER](https://github.com/JuanenRac/URTC-UPDATER) - URTC ファミリーのリポジトリを検出・インストール・更新するデスクトップツール。操作は一つずつ明示的に行います。

**姉妹プロジェクト（独立しており、基盤とツールを共有）：**

* **[HYDRA-UMC-DOCS](https://github.com/JuanenRac/HYDRA-UMC-DOCS)** - 姉妹プロジェクト：HYDRA-UMC のドキュメントハブ。基盤とツールを共有する独立したエコシステム
* **[ARMOR-DOCS](https://github.com/JuanenRac/ARMOR-DOCS)** - 姉妹プロジェクト：A.R.M.O.R. セキュリティエコシステムのドキュメントハブ。こちらも独立し、同じ基盤の上にある
* **[JuanenRac](https://github.com/JuanenRac/JuanenRac)** - すべてのエコシステムのプロフィールとステータスダッシュボード

## 📚 ドキュメント

さらに読むには：

* [コントラクト：各実装が守るべきことと既知の欠落](docs/CONTRACTS.md)
* [仕様のフォーマットと変更方法](docs/SPEC_FORMAT.md)
* [移行：各リポジトリの採用方法](docs/MIGRATION.md)
* [プロトコル表：各識別子と実装している側](docs/PROTOCOL_TABLE.md)
* [1本のバスに複数のツールヘッド](docs/MULTINODE.md)
* [このリポジトリの変更履歴](CHANGELOG.md)
* [ライセンス（GPL-3.0-or-later）](LICENSE)
* 質問、アイデア、報告：electrohobby3d@gmail.com

## 🤝 コントリビュートとコミュニティ

* プルリクエストの前に `URTC_CI=1 python tools/ci_validate.py` を実行してください。通過する必要があります。[CONTRIBUTING.md](CONTRIBUTING.md) と[行動規範](CODE_OF_CONDUCT.md)を参照してください。
* README は 8 言語で提供されています。文章の変更は 8 つのファイルすべてで行い、他のリポジトリと共有するセクションは URTC-COMMON の `tools/readme_sections.py` が書き込みます。
* ビルドしただけのものを、ボード上で動いているかのように書かないでください。
* 脆弱性は非公開で報告してください：[SECURITY.md](SECURITY.md)。質問、アイデア、報告：electrohobby3d@gmail.com（[SUPPORT.md](SUPPORT.md)）。

## 👤 作者

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 ライセンス

GPL-3.0-or-later - [LICENSE](LICENSE) を参照してください。
