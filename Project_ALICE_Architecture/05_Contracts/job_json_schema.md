# Job JSON Schema & Lifecycle Contract

## 1. 概要

`job.json` は、各 Workspace のルート（`<workspace>/job.json`）に配置され、Job の実行状態、対象ユーザー、実行ワークフロー、エラー情報を一元管理するメタデータファイルです。

---

## 2. スキーマ定義

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "JobMetadata",
  "type": "object",
  "required": [
    "job_id",
    "user_id",
    "status",
    "workflow",
    "input_file",
    "workspace_dir",
    "created_at",
    "updated_at"
  ],
  "properties": {
    "job_id": {
      "type": "string",
      "description": "一意なジョブ識別子 (例: job_20260905_120000)"
    },
    "user_id": {
      "type": "string",
      "description": "要求元ユーザーの外部識別子 (LINE User ID等)"
    },
    "status": {
      "type": "string",
      "enum": ["CREATED", "QUEUED", "RUNNING", "COMPLETED", "FAILED"],
      "description": "現在のジョブ実行ステータス"
    },
    "workflow": {
      "type": "array",
      "items": { "type": "string" },
      "description": "実行するモジュール順序 (例: ['transcript', 'summary'])"
    },
    "input_file": {
      "type": "string",
      "description": "入力原本ファイルの絶対パス"
    },
    "workspace_dir": {
      "type": "string",
      "description": "Job Workspace の絶対パス"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ジョブ生成日時 (ISO 8601)"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "description": "最終状態更新日時 (ISO 8601)"
    },
    "error_message": {
      "type": ["string", "null"],
      "description": "FAILED 時のエラーメッセージ詳細"
    }
  }
}
```

---

## 3. ステータス遷移図

```text
[CREATED] ──(キュー投入)──> [QUEUED] ──(Worker取得)──> [RUNNING]
                                                          │
                                         ┌────────────────┴────────────────┐
                                         ▼                                 ▼
                                   [COMPLETED]                          [FAILED]
                                (全成果物生成・配信成功)           (プロセス異常/ファイル未生成)
```
