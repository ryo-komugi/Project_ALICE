# Project_ALICE System Architecture Overview

## 1. システム全体像

Project_ALICE は、音声認識・話者分離・LLM要約・議事録作成・知識検索・長期記憶を統合した、自立分散型のモジュール型AIシステムです。

中央のオーケストレーターである **`ALICE_Core`** が外部インターフェース（LINE・Admin Web UI）からの要求受付とジョブ管理を行い、各機能モジュール（**`ALICE_Transcript`**, **`ALICE_Summary`**, **`ALICE_Minutes`**）を **Workspace Driven CLI / Subprocess 方式** で順次駆動します。また、蓄積された成果物の高速横断検索を担う **`ALICE_Search`**、オフロードメモリ基盤・Discord対話支援として **`ALICE_CoPilot`** が連携します。

```text
               +-------------------------------------------------+
               |             Client / User Interface             |
               | (LINE Messaging / Discord Bot / Admin Web PWA)  |
               +------------------------+------------------------+
                                        │
           LINE Webhook / Discord API   │ Cloudflare Zero Trust (Access)
                                        │ [admin.project-alice.net]
                                        v
                            +-----------------------+
                            |      ALICE_Core       |
                            |  - FastAPI Gateway    |
                            |  - MessageHandler     |
                            |  - JobQueue (FIFO)    |
                            |  - CoreWorker         |
                            |  - WorkspaceManager   |
                            |  - LinePublisher      |
                            |  - Admin Dashboard UI |
                            +-----------+-----------+
                                        |
                     Subprocess CLI     |  1 Job = 1 Workspace
                (--workspace <path>)    |  (/data/runtime/workspaces/{job_id}/)
                                        |
       +--------------------------------+--------------------------------+
       |                                |                                |
       v                                v                                v
+--------------+                 +--------------+                 +--------------+
|  ALICE_      |                 |  ALICE_      |                 |  ALICE_      |
|  Transcript  |                 |  Summary     |                 |  Minutes     |
| (whisper_env)|                 |  (core_env)  |                 |  (core_env)  |
+-------+------+                 +-------+------+                 +-------+------+
        |                                |                                |
        | 生成                            | 入力・生成                      | 入力・生成
        v                                v                                v
+--------------------------------------------------------------------------------+
|                           Job Workspace Directory                              |
| - input/       : meeting.m4a (処理後削除 -> meeting.m4a.processed プレースホルダー)|
| - transcript/  : transcript.json (Source of Truth), transcript.txt             |
| - summary/     : analysis.json, draft_summary.md, summary.txt/md               |
| - minutes/     : analysis.json, minutes.txt/md                                 |
| - logs/        : 実行ログ                                                      |
+--------------------------------------------------------------------------------+
        |
        | [Job 成功完了後 / 非ブロッキング派生処理]
        | python cli.py --index-job <workspace_dir>
        v
+----------------------------------------------------+       +-----------------------+
|                    ALICE_Search                    |       |     ALICE_CoPilot     |
| - SQLite + FTS5 trigram 転置インデックス           |<======| - Discord Bot         |
| - 全文検索・属性検索・BM25・LIKE補正               | 検索  | - Short/Long Memory   |
| - 派生キャッシュ (いつでも再構築可能)              | CLI   | - Obsidian Auto-Sync  |
+----------------------------------------------------+       +-----------------------+
```

---

## 2. 実行制御フロー (CoreWorker & JobQueue & Search Indexing)

1. **要求受付 & 認証**:
   - LINE から音声やテキストメッセージを受信（または Admin Web UI からの手動投入）。
   - 管理画面へのアクセスは Cloudflare Zero Trust（Cloudflare Access）境界認証により保護され、アプリ側は `CF-Access` 検証を実施。
   - `MessageHandler` がユーザー状態を認証・検証（User Directory による照合および Reject 遮断）し、ワークフロー種別を判定（例: `["transcript"]`、`["transcript", "summary"]`）。
2. **Workspace 初期化 & ジョブ投入**:
   - `WorkspaceManager` が `/data/runtime/workspaces/{job_id}/` を初期化し、入力音声を `input/` に保存。
   - メタデータ `job.json` を生成し、`JobQueue`（FIFO メモリキュー）へエンキュー。
3. **順次サブプロセス実行 (CoreWorker)**:
   - バックグラウンドスレッド `CoreWorker` がキューから Job を取得。
   - `job.workflow` に定義された順序に従い、各モジュールの CLI を Subprocess 実行：
     - **Step 1: ALICE_Transcript** (`whisper_env` で起動: `large-v3-turbo`)
       → 音声から `transcript/transcript.json` および `transcript/transcript.txt` を生成。
     - **Step 2: ALICE_Summary / ALICE_Minutes** (`core_env` で起動)
       → `transcript/transcript.json` を入力として、要約または議事録を生成。
4. **Primary Artifact 検証 & 配信 (Job成否境界)**:
   - プロセス終了コードが `0` かつ、契約された `primary_artifact`（例: `summary.txt`）が Workspace 内に存在することを確認。
   - ワークフローの最終ステップ完了後、`LinePublisher` が結果をユーザーの LINE へ配信（Flex Message "Pure Card" 形式）。
   - `job.json` のステータスを `COMPLETED`（異常時は `FAILED`）に更新。
   - **※ ここが成否境界であり、ユーザーへの価値提供・Job 自体はここで 100% 成功完了する。**
5. **ストレージ保全 & 派生キャッシュ更新 (Cleanup & Search Indexing)**:
   - `WorkspaceManager` が `input/` 配下の音声原本バイナリを物理削除し、`<name>.processed` プレースホルダーを配置してディスク枯渇を防止。
   - `CoreWorker` は非ブロッキングで `ALICE_Search` CLI（`--index-job <workspace>`）を呼び出し、検索インデックスを更新する。
   - **エラー分離原則**: 万が一インデックス更新でエラーが発生しても、エラーログを記録するのみとし、Job の `COMPLETED` ステータスは絶対に覆さない（インデックスはいつでも `--reindex` で修復可能）。

---

## 3. モジュール間の責任境界

| モジュール | 主な責任 (Responsibility) | 非責任 (Non-Responsibility) |
| :--- | :--- | :--- |
| **ALICE_Core** | 外部通信受付、認可（User Directory 管理・Reject遮断）、Cloudflare Access連携、JobQueue管理、Workspace生成、Subprocess実行、成果物配信、Admin Web UI | 音声認識、話者分離、要約ロジック、検索アルゴリズム、プロンプト処理 |
| **ALICE_Transcript** | 音響前処理、音声のテキスト化（large-v3-turbo）、話者分離（Pyannote）、単語アライメント（断片化防止）、基本テキスト正規化、`transcript.json` 出力 | 会話の意味解釈、誤字推測、要約、議事録作成、検索インデックス管理 |
| **ALICE_Summary** | 会話構造化分析（Stage 1: タイムライン把握）、要約ドラフト生成（Stage 2: 所見生成含む）、原文照合監査（Stage 3）、`summary.txt/md` 出力 | 音声認識、話者分離のやり直し、外部への直接配信、インデックス登録 |
| **ALICE_Minutes** | 決定事項・アクションアイテム・議題経緯の厳格抽出（Stage 1）、議事録整形（Stage 2）、`minutes.txt/md` 出力 | 音声認識、自由形式の要約、外部への直接配信、インデックス登録 |
| **ALICE_Search** | 蓄積された全ジョブの成果物の全文・属性横断検索（複数語・複数ユーザー対応）、SQLite+FTS5 trigram 派生インデックス管理、正本パス解決 | Jobライフサイクル管理、音声・要約の生成、永続正本データの保持 |
| **ALICE_CoPilot** | 日常対話からの知識・記憶抽出、短期/長期記憶管理、エンティティリレーション、Obsidian 同期、カレンダー・タスク連携、Discord 検索インターフェース | Core の Job 実行管理、音声文字起こし、検索エンジンの内部実装 |
