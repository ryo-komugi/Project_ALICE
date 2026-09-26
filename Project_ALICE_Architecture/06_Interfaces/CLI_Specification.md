# Project_ALICE CLI Specification & Interface Reference

> Version: v1.3.0  
> Status: Ratified  

本ドキュメントは、`ALICE_Core` からサブプロセス起動される各モジュール（`ALICE_Transcript`, `ALICE_Summary`, `ALICE_Minutes`, `ALICE_Search`）および `ALICE_CoPilot` のコマンドライン引数仕様、環境変数、終了コード規約を定義します。

---

## 1. 共通実行規約

### 1.1 Python インタープリタパス契約
各モジュールは隔離された Python 仮想環境で動作します。Core は以下の絶対パスでインタープリタを呼び出します。

| モジュール | Python インタープリタパス | エントリポイント |
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
/home/takuya/Project_ALICE/myenv/whisper_env/bin/python /home/takuya/Project_ALICE/ALICE_Transcript/cli.py --workspace <workspace_dir> [OPTIONS]
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/input/` 配下の音声（`.wav`, `.mp3`, `.m4a` 等）を自動探索して処理する。
- `--model <name>` (任意): Whisper モデル名（デフォルト: `large-v3-turbo`）。
- `--device <cuda|cpu>` (任意): 実行デバイス（デフォルト: `cuda`）。
- `--language <ja|...>` (任意): 文字起こし言語コード（デフォルト: `ja`）。

#### 成果物
- `<workspace>/transcript/transcript.json` (Source of Truth)
- `<workspace>/transcript/transcript.txt` (**Primary Artifact**)
- `<workspace>/transcript/metadata.json`

---

### 2.2 ALICE_Summary CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Summary/cli.py --workspace <workspace_dir> [OPTIONS]
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/transcript/transcript.json` を入力とする。
- `--model <name>` (任意): 使用する Ollama モデル名（デフォルト: `gemma4:12b`）。
- `--stage2-only` (任意): 既存の `analysis.json` を使用し、Stage 2（要約文章化）のみ再実行。
- `--stage3-only` (任意): 既存の `draft_summary.md` を使用し、Stage 3（整合性検査）のみ再実行。
- `--force-stage1` (任意): 既存の中間成果物を上書きして最初から実行。

#### 成果物
- `<workspace>/summary/summary.txt` (**Primary Artifact**)
- `<workspace>/summary/summary.md`
- `<workspace>/summary/commentary.txt` / `commentary.md`（面談タイプ時）
- `<workspace>/summary/analysis.json`
- `<workspace>/summary/draft_summary.md`
- `<workspace>/summary/consistency_report.md`

---

### 2.3 ALICE_Minutes CLI

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Minutes/cli.py --workspace <workspace_dir> [OPTIONS]
```

#### 引数
- `--workspace <path>` (**必須**): Job Workspace の絶対パス。`<path>/transcript/transcript.json` を入力とする。
- `--template {standard,interview,executive,consultation}` (任意): 使用する議事録テンプレート（デフォルト: `standard`）。
- `--model <name>` (任意): 使用する Ollama モデル名（デフォルト: `gemma4:12b`）。
- `--stage2-only` (任意): 既存の `analysis.json` を使用し、Stage 2（議事録文章化）のみ再実行。
- `--force-stage1` (任意): 既存の中間成果物を上書きして最初から実行。

#### 成果物
- `<workspace>/minutes/minutes.txt` (**Primary Artifact**)
- `<workspace>/minutes/minutes.md`
- `<workspace>/minutes/analysis.json`
- `<workspace>/minutes/metadata.json`

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
- `--status <status>` (任意): ジョブステータス（`COMPLETED`, `FAILED` 等）で絞り込み。
- `--limit <int>` (任意): 取得上限件数（デフォルト: 20）。
- `--offset <int>` (任意): ページネーションオフセット（デフォルト: 0）。

#### (2) ジョブインデックス登録・更新モード (`--index-job`)
Core の Job 完了時、Workspace 内のテキスト成果物をインデックスに反映します。
- `--index-job <workspace_dir>` (**必須**): 対象 Workspace の絶対パス。

#### (3) インデックス完全再構築モード (`--reindex`)
全 Workspace ディレクトリを走査し、インデックス DB をゼロから再構築します。
- `--reindex`: 派生キャッシュ DB を再生成するフラグ。
- `--workspaces-dir <dir>` (任意): Workspace 親ディレクトリ（デフォルト: `/data/runtime/workspaces`）。

---

## 3. 終了コード規約

| 終了コード | 意味 | Core側のハンドリング |
| :---: | :--- | :--- |
| `0` | **正常終了 (SUCCESS)** | ワークフローの後続ステップへ進む。Primary Artifact の存在確認へ。 |
| `1` | **一般エラー (ERROR)** | ジョブを `FAILED` として中断。エラーログを記録。 |
| `2` | **引数不正 (USAGE)** | ジョブを `FAILED` として中断。CLI 呼び出し設定の不具合と判定。 |
| `137` | **OOM (Out Of Memory)** | メモリ/VRAM 枯渇。キューを一時停止し、リソース解放後に再試行。 |
