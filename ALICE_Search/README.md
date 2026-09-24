# ALICE_Search (v1.0)

ALICE 過去成果物（Summary / Transcript 等）の全文検索・属性検索・追跡を行う独立モジュール。

---

## 1. 基本方針・設計原則

1. **Workspace = Source of Truth (源泉データ主義)**:
   * すべてのジョブメタデータ・成果物（`summary.txt`, `transcript.txt`, `transcript.json` 等）の正本は各 Workspace（`/data/runtime/workspaces/{job_id}/`）に存在します。
2. **SQLite + FTS5 は再構築可能な派生キャッシュ**:
   * データベース（`/data/runtime/search/alice_index.db`）が消失・破損しても、いつでも Workspace 群から `--reindex` で 100% 復旧可能です。
3. **Core と Search の疎結合（Workspace Driven CLI）**:
   * `ALICE_Core` と `ALICE_Search` は直接 Python import で依存せず、CLI（Subprocess）を介して連携します。
4. **Job 成否と Search Index 更新成否の完全分離**:
   * Job が COMPLETED になった後に派生インデックスを更新します。
   * インデックス更新で万が一エラーが発生しても、Job 本体のステータスは絶対に FAILED に戻りません（ログ記録のみ）。
5. **検索結果から正本 Artifact への確実な到達性**:
   * 検索結果（JSON）には必ず `job_id`, `workspace_dir`, `artifact_abs_path` が含まれ、正本ファイルおよび `transcript.json` へ直接アクセスできます。

---

## 2. CLI インターフェース仕様 (`cli.py`)

検索実行オプションは `--query` に統一されています。

### (1) 全文検索・属性検索の実行
```bash
# 基本検索 (キーワード検索)
python cli.py --query "来期予算" --limit 5

# ユーザーIDやモジュールで絞り込み (Metadata Filter との組み合わせ)
python cli.py --query "システム移行" --user "U794535d58fb802ac996f4a86ce119ad2" --module "summary"

# キーワードなしのジョブ一覧・履歴確認
python cli.py --query "" --user "user_001" --limit 10
```

#### 検索結果出力例 (標準出力 JSON)
```json
{
  "total": 1,
  "query": "司法判断",
  "filters": {
    "module": ["summary"]
  },
  "hits": [
    {
      "job_id": "job_20260911_211704_test_line_summary",
      "user_id": "U794535d58fb802ac996f4a86ce119ad2",
      "module": "summary",
      "artifact_name": "summary.txt",
      "artifact_rel_path": "summary/summary.txt",
      "workspace_dir": "/data/runtime/workspaces/job_20260911_211704_test_line_summary",
      "artifact_abs_path": "/data/runtime/workspaces/job_20260911_211704_test_line_summary/summary/summary.txt",
      "snippet": "...目撃した特定の<b>司法判断</b>（贈賄・収賄に関す...",
      "rank_score": -1.413e-6,
      "created_at": "2026-09-11T21:17:04.252723",
      "metadata": {
        "status": "COMPLETED",
        "original_filename": "test_line_summary.mp3",
        "workflow": "[\"transcript\", \"summary\"]"
      }
    }
  ]
}
```

### (2) 単一 Workspace のインデックス登録 / 更新
```bash
python cli.py --index-job /data/runtime/workspaces/job_20260911_211704_test_line_summary
```
* 終了コード: 成功時 `0`、失敗時 `1`

### (3) 全体再インデックス (Rebuild)
```bash
python cli.py --reindex
```
* すべての Workspace を走査し、DB を 0 から完全再構築します。

---

## 3. 全文検索（FTS5 trigram）と仕様補正

* **3文字以上のクエリ**:
  * SQLite FTS5 の trigram 転置インデックスによる高速 MATCH 検索と BM25 ランキングスコア計算を実行。
* **1〜2文字の短いクエリ**:
  * trigram は仕様上 3文字未満の n-gram を持たないため、FTS5 trigram 仮想テーブル上の高速インデックススキャン `content LIKE '%...%'` を自動使用。
  * スニペットと `<b>...</b>` ハイライトを自動補完し、短縮語（「AI」「予算」「円」等）の検索漏れを防止。
* **検索対象 Artifact**:
  * `summary/summary.txt`, `summary/summary.md`
  * `transcript/transcript.txt`
  * 将来の `minutes/minutes.txt`, `minutes/minutes.md`
  * ※ `transcript.json` は発話構造化データ（一次正本）として維持し、構文トークンによるノイズ防止のため全文検索インデックスからは除外。検索結果の `workspace_dir` から必要に応じて参照可能。
  * ※ `*.log` や一時ファイルは検索対象外。

---

## 4. ディレクトリ構成

```text
ALICE_Search/
├── cli.py               # CLI エントリーポイント (--query, --index-job, --reindex)
├── config.py            # DB パス、対象成果物定義
├── core/
│   ├── __init__.py
│   ├── schema.py        # SQLite スキーマ (jobs_metadata & artifacts_fts trigram)
│   ├── indexer.py       # Workspace 読み込み・インデックス登録・全再構築
│   └── searcher.py      # Full Text Query + Metadata Filter ハイブリッド検索
├── models/
│   ├── __init__.py
│   ├── query.py         # SearchQuery モデル
│   └── result.py        # SearchHit, SearchResult モデル
├── tests/
│   ├── test_fts_trigram.py # 2文字検索、日本語、英数字、固有名詞、BM25等の網羅テスト
│   └── test_search_e2e.py  # CLI, 正本参照, 再構築, エラー分離テスト
└── README.md
```
