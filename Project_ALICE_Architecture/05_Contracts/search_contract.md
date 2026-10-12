# ALICE_Search Data & Artifact Contract

> Version: v1.1.0  
> Status: Ratified  

本ドキュメントは、`ALICE_Search` と他モジュール（`ALICE_Core`, `ALICE_CoPilot` 等）間で交わされる入出力データ契約、検索結果 JSON スキーマ、およびインデックス対象成果物規約を定義します。

---

## 1. 検索結果出力契約 (JSON Schema)

`ALICE_Search` の検索クエリ実行時（`--query <text>`）に標準出力へ出力される JSON 形式です。

### 1.1 JSON スキーマ定義
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SearchResult",
  "type": "object",
  "required": ["total", "query", "hits"],
  "properties": {
    "total": {
      "type": "integer",
      "description": "ヒット件数"
    },
    "query": {
      "type": "string",
      "description": "実行された検索クエリ"
    },
    "filters": {
      "type": "object",
      "properties": {
        "user_id": { "type": ["string", "null"] },
        "module": {
          "type": ["array", "null"],
          "items": { "type": "string" }
        },
        "from_date": { "type": ["string", "null"] },
        "to_date": { "type": ["string", "null"] }
      }
    },
    "hits": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "job_id",
          "module",
          "artifact_name",
          "artifact_rel_path",
          "workspace_dir",
          "artifact_abs_path",
          "snippet",
          "rank_score"
        ],
        "properties": {
          "job_id": { "type": "string" },
          "user_id": { "type": ["string", "null"] },
          "module": { "type": "string", "enum": ["summary", "transcript", "minutes"] },
          "artifact_name": { "type": "string" },
          "artifact_rel_path": { "type": "string" },
          "workspace_dir": { "type": "string" },
          "artifact_abs_path": { "type": "string" },
          "snippet": { "type": "string" },
          "rank_score": { "type": "number" },
          "created_at": { "type": ["string", "null"] },
          "metadata": {
            "type": "object",
            "properties": {
              "status": { "type": "string" },
              "original_filename": { "type": "string" },
              "workflow": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

### 1.2 出力例
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
        "workflow": "["transcript", "summary"]"
      }
    }
  ]
}
```

---

## 2. インデックス対象成果物規約

`--index-job <workspace_dir>` および `--reindex` 実行時に走査・格納されるファイル規約です。

| 相対パス | モジュール種別 | インデックス対象 | 理由 |
| :--- | :--- | :---: | :--- |
| `summary/summary.txt` | `summary` | **対象** | LINE配信用の要約テキスト（最重要成果物） |
| `summary/summary.md` | `summary` | **対象** | 完全版 Markdown 要約 |
| `summary/commentary.txt` | `summary` | **対象** | 面談講評プレーンテキスト（所見レポート） |
| `summary/commentary.md` | `summary` | **対象** | 面談講評 Markdown（所見レポート） |
| `transcript/transcript.txt` | `transcript` | **対象** | 全文文字起こしプレーンテキスト |
| `minutes/minutes.txt` | `minutes` | **対象** | 議事録テキスト |
| `minutes/minutes.md` | `minutes` | **対象** | 議事録 Markdown |
| `transcript/transcript.json` | - | **対象外** | 一次正本だが、構文トークン混入による検索ノイズ防止のため除外 |
| `summary/analysis.json` | - | **対象外** | 中間成果物（ノイズ防止） |
| `logs/*.log` | - | **対象外** | 実行ログ（ノイズ防止） |
| `input/*` | - | **対象外** | 音声バイナリデータ |

---

## 3. インデックス同期契約 (Core → Search)

`ALICE_Core` の `CoreWorker` は、Job が `COMPLETED` となり、Primary Artifact が生成された後に以下の契約に基づいてインデックス更新を行います。

- **実行コマンド**: `python cli.py --index-job <workspace_dir>`
- **終了コード契約**:
  - `0`: 正常終了（インデックス作成/更新完了）
  - `1`: 異常終了（引数不正、Workspace パス不正、パースエラー等）
- **例外分離**: 終了コードが `1` の場合でも、`CoreWorker` は警告ログ（warning/error）を記録するのみとし、Job 自体の成否判定に一切影響を与えない。
