# ALICE_Summary Contract Specification

## 1. 入力契約 (Input Contract)

- **必須入力ファイル**: `<workspace>/transcript/transcript.json`
- スキーマ: `transcript_contract.md` に準拠した構造化正本 JSON。

---

## 2. 出力契約成果物一覧 (Output Contract)

`ALICE_Summary` は、正常完了時に `<workspace>/summary/` 配下に以下の成果物を生成する。

| ファイル名 | 区分 | 形式 | 役割・説明 |
| :--- | :--- | :--- | :--- |
| `summary.txt` | **Primary Artifact** | PlainText | **CoreWorker / Publisher が配信に用いる完成版テキスト** |
| `summary.md` | Core Document | Markdown | 見出し・箇条書きが施された完成版要約ドキュメント |
| `commentary.txt` | Optional Primary | PlainText | 面談・1on1時の所見コメントテキスト（Commentator有効時） |
| `commentary.md` | Optional Document | Markdown | 面談・1on1時の所見コメントMarkdown（Commentator有効時） |
| `analysis.json` | Intermediate | JSON | Stage 1 で抽出された会話構造化データ |
| `draft_summary.md` | Intermediate | Markdown | Stage 2 で文章化されたドラフト要約 |
| `consistency_report.md` | Audit Report | Markdown | Stage 3 による原文照合・7項目監査判定レポート |
| `metadata.json` | Auxiliary | JSON | 適用モデル、処理時間、トークン数、コンテキスト長等 |

---

## 3. `analysis.json` 主要構造 (Pydantic Model 準拠)

```json
{
  "theme": "会話の全体目的とテーマ",
  "speakers": [
    { "id": "SPEAKER_00", "estimated_role": "進行役・課長" },
    { "id": "SPEAKER_01", "estimated_role": "報告者・担当" }
  ],
  "agenda_items": [
    {
      "topic": "新機能のリリーススケジュール",
      "facts": ["テストで2件のバグが発見された"],
      "opinions": ["今週中のリリースは延期すべき"],
      "decisions": ["リリース日を来週火曜日に延期する"]
    }
  ],
  "action_items": [
    {
      "task": "バグ修正とリグレッションテスト",
      "assignee": "SPEAKER_01",
      "due": "今週金曜まで"
    }
  ],
  "unresolved_items": ["本番環境へのデプロイ手順確認"]
}
```
