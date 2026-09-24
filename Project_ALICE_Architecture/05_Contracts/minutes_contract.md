# ALICE_Minutes Contract Specification

## 1. 入力契約 (Input Contract)

- **必須入力ファイル**: `<workspace>/transcript/transcript.json`
- スキーマ: `transcript_contract.md` に準拠した構造化正本 JSON。

---

## 2. 出力契約成果物一覧 (Output Contract)

`ALICE_Minutes` は、正常完了時に `<workspace>/minutes/` 配下に以下の成果物を生成する。

| ファイル名 | 区分 | 形式 | 役割・説明 |
| :--- | :--- | :--- | :--- |
| `minutes.txt` | **Primary Artifact** | PlainText | **CoreWorker / Publisher が配信に用いる議事録テキスト** |
| `minutes.md` | Core Document | Markdown | 見出し・チェックボックス付き議事録ドキュメント |
| `analysis.json` | Intermediate | JSON | Stage 1 で抽出された決定事項・TODO等の構造化データ |
| `metadata.json` | Auxiliary | JSON | 処理時間、トークン数、抽出決定事項数等 |

---

## 3. `analysis.json` 主要構造 (Pydantic Model 準拠)

```json
{
  "meeting_title": "定例進捗会議",
  "attendees": [
    { "speaker_id": "SPEAKER_00", "role": "ファシリテーター" },
    { "speaker_id": "SPEAKER_01", "role": "開発担当" }
  ],
  "decisions": [
    { "agenda": "API設計方針", "decision": "RESTful APIを採用しJSONで統一" }
  ],
  "action_items": [
    {
      "task": "エンドポイント一覧のドキュメント作成",
      "assignee": "SPEAKER_01",
      "deadline": "2026-09-10"
    }
  ],
  "pending_issues": [
    "認証方式にOAuth2を導入するかどうかは次回検討"
  ]
}
```
