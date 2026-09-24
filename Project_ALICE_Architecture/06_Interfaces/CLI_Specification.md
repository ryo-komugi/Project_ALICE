# Project_ALICE CLI Interface Specification

> Version: v1.2.0  
> Status: Ratified  

本仕様書は、`ALICE_Core` および運用オペレーターが各モジュールを CLI から実行する際のコマンドラインインターフェース（CLI Interface）仕様を定義します。

---

## 1. モジュール実行環境一覧

| モジュール | 専用 Python 仮想環境パス | CLI スクリプトパス |
| :--- | :--- | :--- |
| **ALICE_Transcript** | `/home/takuya/Project_ALICE/myenv/whisper_env/bin/python` | `/home/takuya/Project_ALICE/ALICE_Transcript/cli.py` |
| **ALICE_Summary** | `/home/takuya/Project_ALICE/myenv/core_env/bin/python` | `/home/takuya/Project_ALICE/ALICE_Summary/cli.py` |
| **ALICE_Minutes** | `/home/takuya/Project_ALICE/myenv/core_env/bin/python` | `/home/takuya/Project_ALICE/ALICE_Minutes/cli.py` |
| **ALICE_Search** | `/home/takuya/Project_ALICE/myenv/core_env/bin/python` | `/home/takuya/Project_ALICE/ALICE_Search/cli.py` |
| **ALICE_CoPilot** | `/home/takuya/Project_ALICE/myenv/core_env/bin/python` | `/home/takuya/Project_ALICE/ALICE_CoPilot/main.py` |

---

## 2. モジュール別 CLI 仕様

### 2.1 ALICE_Transcript CLI

```bash
/home/takuya/Project_ALICE/myenv/whisper_env/bin/python /home/takuya/Project_ALICE/ALICE_Transcript/cli.py --workspace <workspace_dir>
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/input/` 配下の音声（`.wav`, `.mp3`, `.m4a` 等）を自動探索して処理する。
- `--model <name>` (任意): Whisper モデル名（デフォルト: `large-v3-turbo`）。

---

### 2.2 ALICE_Summary CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Summary/cli.py --workspace <workspace_dir> [OPTIONS]
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/transcript/transcript.json` を入力とする。
- `--model <name>` (任意): 使用する Ollama モデル名（デフォルト: `gemma4:12b`）。
- `--stage2-only` (任意): 既存の `analysis.json` を使用し、Stage 2 以降を再実行。
- `--stage3-only` (任意): 既存の `draft_summary.md` を使用し、Stage 3（整合性チェック）のみ再実行。
- `--skip-stage3` (任意): Stage 3 の原文照合監査をスキップし、Stage 2 ドラフトを完成版とする。
- `--force-all` (任意): 既存の中間成果物を無視して Stage 1 から完全再生成。

---

### 2.3 ALICE_Minutes CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Minutes/cli.py --workspace <workspace_dir> [OPTIONS]
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/transcript/transcript.json` を入力とする。
- `--model <name>` (任意): 使用する Ollama モデル名（デフォルト: `qwen3:14b` または `gemma4:12b`）。
- `--stage2-only` (任意): 既存の `analysis.json` を使用し、Stage 2（議事録文章化）のみ再実行。
- `--force-stage1` (任意): 既存の中間成果物を上書きして最初から実行。

---

### 2.4 ALICE_Search CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Search/cli.py [OPTIONS]
```

#### モード別引数仕様

#### (1) 全文・属性検索モード (`--query`)
蓄積された成果物からキーワードおよびメタデータ条件で検索を実行し、結果を標準出力に JSON で出力します。
- `--query <text>` (**必須**): 検索キーワード（空文字列 `""` を指定した場合はメタデータ条件による一覧取得）。複数単語のスペース区切り検索に対応。
- `--user <user_id>` (任意): 特定ユーザー ID で絞り込み。カンマ区切りで複数指定可能（例: `--user "user_A,user_B"`）。
- `--module <name>` (任意): モジュール種別（`summary`, `transcript`, `minutes`）で絞り込み。
- `--from-date <YYYY-MM-DD>` (任意): 指定日以降のジョブに絞り込み。
- `--to-date <YYYY-MM-DD>` (任意): 指定日以前のジョブに絞り込み。
- `--limit <int>` (任意): 取得最大件数（デフォルト: `10`）。

#### (2) 単一 Workspace インデックス登録・更新モード (`--index-job`)
CoreWorker から Job 完了時に呼び出され、当該 Workspace の成果物をインデックスに反映します。
- `--index-job <path>`: 対象 Workspace の絶対パス。
- 終了コード: 成功時 `0`、失敗時 `1`。

#### (3) 全体再インデックスモード (`--reindex`)
全 Workspace ディレクトリを走査し、検索データベース（`alice_index.db`）を 0 から完全再構築します。
- `--reindex`: オプション指定のみで実行。
- 終了コード: 成功時 `0`、失敗時 `1`。

---

### 2.5 ALICE_CoPilot CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_CoPilot/main.py [OPTIONS]
```

#### 引数
- `--discord`: Discord Bot を起動してメッセージ待受を開始（`#search` による `ALICE_Search` 連携機能を含む）。
- `--sync-obsidian`: メモリ原本から Obsidian バウルトへの同期を手動実行（起動時にも自動実行）。
- `--search <query>`: 蓄積された長期メモリ（決定・アイデア・ナレッジ）のキーワード検索を実行。
