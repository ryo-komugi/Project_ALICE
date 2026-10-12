# ALICE_Core

> Project_ALICE の中核オーケストレーション & 外部インターフェース基盤

---

## 1. 概要

ALICE_Core は、LINE Bot などの外部クライアントからの要求受付、Job / Workspace のライフサイクル管理、非同期 JobQueue、および各 AI モジュール（Transcript, Summary 等）を順次実行する `CoreWorker` と成果物配信（Publisher）を担う中核コンポーネントです。

---

## 2. アーキテクチャと連携方式

### 基本原則

* **疎結合アーキテクチャ**:
  * Core は各モジュール内部の Python クラスを直接 import せず、**Workspace Driven CLI / Subprocess 方式** で連携します。
  * `1 Job = 1 Workspace`（`/data/runtime/workspaces/{job_id}/`）のライフサイクルを Core が完全に管理します。
* **単一責任原則**:
  * Core はオーケストレーション（受付・キュー・プロセス管理・配信）に専念し、音声認識や LLM 推論などの AI 処理ロジックは各独立モジュール（`ALICE_Transcript`, `ALICE_Summary` 等）に委譲します。
* **Source of Truth（源泉データ）**:
  * `transcript/transcript.json` を会話の構造化正本データとし、後続モジュールはこれを参照して処理を行います。

---

## 3. 処理フロー

```text
LINE (ユーザー音声・要求)
    │
    ▼
1. MessageHandler (要求受付 & Workflow 決定)
    │
    ▼
2. WorkspaceManager (Job 生成 & Workspace 初期化)
    │
    ▼
3. JobQueue (非同期キューイング)
    │
    ▼
4. CoreWorker (Job 取得 & 順次 Subprocess 実行)
    │
    ├── Step 1: ALICE_Transcript (cli.py --workspace <path>)
    │            └──> <workspace>/transcript/ (transcript.json / txt)
    │
    ├── Step 2: ALICE_Summary (cli.py --workspace <path>)  ※要約要求時
    │            └──> <workspace>/summary/ (summary.md)
    │
    ▼
5. Publisher (LinePublisher: 最終成果物を LINE へ配信)
    │
    ▼
Job COMPLETED / FAILED
```

---

## 4. 現行の Workflow 仕様

LINE からの要求に応じて、以下の直列 Workflow が自動的に割り当てられます。

| ユーザー要求 | 生成される `Job.workflow` | 実行されるモジュール | 最終配信成果物 |
| :--- | :--- | :--- | :--- |
| **文字起こし** | `["transcript"]` | `ALICE_Transcript` | `transcript.txt` |
| **要約** | `["transcript", "summary"]` | `ALICE_Transcript` → `ALICE_Summary` | `summary.txt` (内部で `summary.md` も保持) |

* **Artifact Contract**:
  * モジュール CLI のプロセス終了コードが `0` かつ、契約された成果物ファイル（`primary_artifact`）が Workspace 内に存在することで成否を判定します。
* **配信タイミング**:
  * 途中のステップ完了時には配信せず、**Workflow 全体の最終ステップ完了後に 1 回のみ** LINE へ成果物を Push 配信します。

---

## 5. `/data/runtime` ディレクトリ構成

```text
/data/runtime/
├── copilot/                    # [CoPilot 専用]
│   └── database/               # conversations.db
├── core/                       # [Core 専用 (外部IF・配信領域)]
│   ├── inbox/                  # LINE 受信一時ファイル
│   └── share/                  # LINE 配信・静的公開領域 (/share)
├── logs/                       # 【全Module共通システムログ領域】
│   ├── alice.log               # ALICE_Core ログ
│   ├── transcript.log          # ALICE_Transcript スタンドアロンログ
│   └── archive/                # ローテーション過去ログ (alice_*.log, transcript_*.log)
├── transcript/                 # [Transcript スタンドアロン専用領域]
│   ├── staging/
│   ├── input/
│   ├── work/
│   └── output/
└── workspaces/                 # [Project_ALICE 共通 Job Workspace]
    └── {job_id}/
        ├── job.json            # Job の完全なライフサイクル・進捗・成果物参照 (Source of Truth)
        ├── input/              # 入力音声原本
        ├── transcript/         # Transcript 成果物 (transcript.json, transcript.txt, metadata.json)
        ├── summary/            # Summary 成果物 (summary.md, summary.txt, analysis.json, metadata.json)
        ├── minutes/            # (将来予約領域)
        └── logs/               # Job 固有の実行ログ (transcript.log, summary.log)
```

---

## 6. Job Management & 追跡仕様 (ALICE v1.0)

ALICE v1.0 では、1件のJobに関する完全なトレーサビリティ（追跡可能性）を保証します。

### 追跡項目
1. **何を受け取ったか (`input_metadata`)**:
   - 受信元ファイル名 (`original_name`)、バイトサイズ (`size_bytes`)、受付日時 (`received_at`)、入力原本パス (`input_file`)
2. **どのWorkflowを実行したか (`workflow`)**:
   - 実行パイプライン（例: `["transcript"]`, `["transcript", "summary"]`）
3. **現在どこまで進んだか (`current_step`, `step_history`)**:
   - 現在実行中モジュール名 (`current_step`)
   - ステップ単位の実行履歴 (`step_history`): ステップ名、状態 (`StepStatus`: PENDING / RUNNING / COMPLETED / FAILED / SKIPPED)、開始時刻、完了時刻、経過秒数 (`elapsed_sec`)、終了コード (`exit_code`)
4. **成功したのか失敗したのか (`status`, `error_detail`)**:
   - 全体ステータス (`JobStatus`: CREATED / QUEUED / RUNNING / COMPLETED / FAILED)
   - 失敗時の構造化詳細 (`error_detail`): 失敗ステップ名 (`failed_step`)、エラー分類 (`error_type`)、終了コード (`exit_code`)、メッセージ、ログファイルパス (`log_file`)、発生時刻
5. **どの成果物が生成されたのか (`artifacts`)**:
   - 各モジュールの **Artifact Contract** に基づいて生成された成果物参照リスト。
   - 成果物名 (`name`)、Workspace内相対パス (`path`)、生成モジュール名 (`module`)、主成果物フラグ (`is_primary`)、ファイルサイズ (`size_bytes`)、生成日時 (`created_at`)
   - **※ Transcript本文やSummary本文などの実データそのものは `job.json` に埋め込まず、ファイル参照メタデータのみを保持します。**

### Source of Truth と WorkspaceManager API
データベース（RDBMS/NoSQL）を追加せず、Workspace 自体を Source of Truth とします。
- `workspace_manager.save_job_json(job)`: アトミック置換保存（tmp -> rename）でデータ整合性を保証。
- `workspace_manager.load_job(workspace_dir)`: 指定 Workspace から Job を完全復元。
- `workspace_manager.get_job(job_id)`: `job_id` から該当 Job を取得。
- `workspace_manager.list_jobs(limit=50, user_id=None)`: 全 Workspace を走査し、作成日時降順で過去の Job 一覧を取得。

---

## 7. ディレクトリ構成

```text
ALICE_Core/
├── auth/                   # ユーザー認証・招待コード管理
├── core/
│   ├── container.py        # DI コンテナ
│   ├── job_queue.py        # FIFO JobQueue (メモリキュー)
│   ├── logger.py           # Core ロガー (/data/runtime/logs/alice.log)
│   ├── session.py          # ユーザー対話セッションモデル
│   ├── session_manager.py  # セッション状態管理
│   ├── worker.py           # CoreWorker (MODULE_RUNNERS 定義 & 順次実行)
│   └── workspace_manager.py# 1 Job = 1 Workspace 管理 (追跡・ロード・一覧API)
├── database/               # ユーザー情報 SQLite
├── line/                   # LINE ハンドラー & メッセージ送信
├── models/
│   └── job.py              # Core 共通 Job モデル (ライフサイクル・進捗・成果物追跡対応)
├── publisher/              # 成果物配信 (LinePublisher)
├── repository/             # DB リポジトリ
├── config.py               # Core 設定
└── main.py                 # FastAPI エントリーポイント
```

---

## 8. 将来構想 (Current Scope 外)

以下は今後のフェーズで段階的に検討・拡張される項目であり、現行バージョンでは未実装・予約領域として扱われます。

* 後続モジュール（`ALICE_Minutes`, `ALICE_Insight`, `ALICE_Search` 等）の追加接続
* Job / Queue の DB 永続化（SQLite / Redis / Celery 等）
* Module 通信の HTTP / gRPC 化
* Publisher の他サービス拡張（Discord, Slack, Obsidian 等）
