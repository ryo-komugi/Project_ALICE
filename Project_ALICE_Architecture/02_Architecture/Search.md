# ALICE_Search Architecture

## 1. 概要

`ALICE_Search` は、Project_ALICE が過去に処理したすべての会話・要約・ジョブ成果物を対象とする、高速全文検索・属性検索・追跡を行う独立モジュールです。

```text
Workspace Directory 群 (/data/runtime/workspaces/{job_id}/)
  ├── summary/summary.txt, summary.md
  ├── transcript/transcript.txt
  ├── minutes/minutes.txt, minutes.md
  └── job.json
          │
          │ [cli.py --index-job <workspace_dir>]
          ▼
┌──────────────────────────────────────────────────────────┐
│ ALICE_Search Engine                                      │
│                                                          │
│  [Indexer]                                               │
│    ├─ jobs_metadata テーブル (属性・ステータス)          │
│    └─ artifacts_fts 仮想テーブル (FTS5 trigram 転置索引) │
│                                                          │
│  [Searcher]                                              │
│    ├─ 3文字以上: FTS5 MATCH + BM25 ランキング            │
│    ├─ 1〜2文字 : LIKE '%...%' 高速スキャン自動補正       │
│    ├─ 複数単語 : 個別トークン化 ＋ 2文字語ハイブリッド   │
│    ├─ 属性フィルタ: user_id (複数/カンマ区切り可), module │
│    └─ ハイライト・スニペット生成 (<b>...</b>)             │
└──────────────────────────┬───────────────────────────────┘
                           │
                           │ [cli.py --query "..." --user "..."]
                           ▼
                    検索結果 (JSON)
          (job_id, artifact_abs_path, snippet, rank)
```

---

## 2. コア設計原則

1. **Workspace = Source of Truth（源泉データ主義）**:
   - すべてのジョブメタデータおよび成果物（`summary.txt`, `transcript.txt` 等）の正本は各 Workspace（`/data/runtime/workspaces/{job_id}/`）に存在します。
2. **SQLite + FTS5 は再構築可能な派生キャッシュ（Derived Cache）**:
   - データベース（`/data/runtime/search/alice_index.db`）が消失・破損しても、いつでも Workspace 群から `--reindex` により 100% 完全に復旧可能です。
3. **Core と Search の疎結合（Workspace Driven CLI）**:
   - `ALICE_Core` と `ALICE_Search` は Python クラスを直接 import せず、CLI（Subprocess）を介して連携します。
4. **Job 成否と Search Index 更新の完全分離（成否境界）**:
   - Job は成果物生成および LINE 配信が成功した時点で 100% `COMPLETED` と判定されます。
   - その後に行われるインデックス更新が万が一失敗しても、エラーログを記録するのみで、Job の成功ステータスは絶対に覆りません。
5. **正本 Artifact への直接到達性**:
   - 検索結果には必ず `workspace_dir` および `artifact_abs_path` が含まれ、正本テキストおよび構造化正本 `transcript.json` へダイレクトにアクセスできます。

---

## 3. データストア・スキーマ設計

検索データベースは `/data/runtime/search/alice_index.db` に永続化されます。

### 3.1 メタデータテーブル (`jobs_metadata`)
ジョブの属性情報・ステータスを管理し、インデックス更新日時を追跡します。

```sql
CREATE TABLE IF NOT EXISTS jobs_metadata (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    original_filename TEXT,
    workflow TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    workspace_dir TEXT NOT NULL,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs_metadata(created_at);
```

### 3.2 全文検索仮想テーブル (`artifacts_fts`)
成果物テキストの転置インデックスを保持します。日本語・英数字が混在する長文に対応するため、トークナイザーには **FTS5 `trigram`** を採用しています。

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
    job_id UNINDEXED,
    user_id UNINDEXED,
    module,
    artifact_name,
    artifact_rel_path UNINDEXED,
    content,
    tokenize = 'trigram'
);
```

---

## 4. 検索アルゴリズムと仕様補正

### 4.1 3文字以上のクエリ
- SQLite FTS5 の `trigram` 転置インデックスによる高速 `MATCH` 検索を実行。
- SQLite 組み込みの `bm25(artifacts_fts)` を用いて関連度スコアリングを算出しソート。
- `snippet(artifacts_fts, 5, '<b>', '</b>', '...', 32)` により、マッチ周辺の文脈をスニペット化。

### 4.2 1〜2文字の短いクエリに対する自動補正
- **背景**: FTS5 `trigram` は仕様上 3 文字未満の n-gram を生成しないため、単純な `MATCH` では短縮キーワード（「AI」「予算」「円」等）がヒットしません。
- **解決策**: クエリ長が 1〜2 文字の場合、内部で自動的に `content LIKE '%query%'` スキャンへ切り替え、Python 側で `<b>...</b>` ハイライトと前後 32 トークンのスニペットを生成・補完します。これにより、日本語特有の短いキーワードの検索漏れを完全に排除しています。

### 4.3 複数単語クエリの安全なトークン分割とハイブリッド処理
- 検索クエリにスペース区切りの複数単語が含まれる場合、各単語を個別に安全にダブルクォートで括って FTS5 クエリを構築します。
- 複数単語の中に 2文字以下の単語が含まれる場合でも構文エラーを起こさず、FTS5 の trigram トークンと LIKE 判定を適切に組み合わせたフォールバックを実行します。

### 4.4 複数ユーザーID絞り込み
- `--user` オプションにカンマ区切り（例: `--user "user_A,user_B"`）で複数ユーザー ID を指定可能。内部で `user_id IN (...)` 句へ安全に展開されます。

### 4.5 検索対象アーティファクト
ノイズを排除し、検索精度とパフォーマンスを両立するため、対象ファイルを明確に限定しています。
- **対象**:
  - `summary/summary.txt`, `summary/summary.md`
  - `transcript/transcript.txt`
  - `minutes/minutes.txt`, `minutes/minutes.md`
  - `summary/commentary.txt`, `summary/commentary.md`（面談講評・所見レポート）
- **対象外**:
  - `transcript/transcript.json`（構文トークンによるノイズ防止のため除外。検索結果の `workspace_dir` から取得可能）
  - `analysis.json`, 各種ログファイル（`*.log`）、入力音声バイナリ

---

## 5. モジュール間連携と利用シナリオ

1. **ALICE_Core からの自動同期**:
   - `CoreWorker` が Job 完了直後に `python cli.py --index-job <workspace_dir>` を非ブロッキング実行。
2. **ALICE_CoPilot (Discord Bot) からの参照**:
   - Discord の `#search` チャンネルまたは `!search <query>` コマンドから `ALICE_Search` CLI を呼び出し、過去の会話履歴・要約をユーザーへ埋め込み表示。
3. **運用・保守**:
   - 障害時やスキーマ変更時は、`python cli.py --reindex` を 1 コマンド実行するだけで全 Workspace からインデックスを完全再構築。
