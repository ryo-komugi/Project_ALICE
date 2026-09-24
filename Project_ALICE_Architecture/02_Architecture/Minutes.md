# ALICE_Minutes Architecture

## 1. 概要

`ALICE_Minutes` は、`ALICE_Transcript` が生成した会話ログ（`transcript/transcript.json`）を入力とし、会議や面談における**「決定事項」「アクションアイテム（TODO・担当・期限）」「議題別審議経緯」「保留・持ち越し事項」**を正確に抽出した議事録（Meeting Minutes）を生成する独立モジュールです。

要約（Summary）が「会話の全体像や論点を把握すること」を主目的とするのに対し、議事録（Minutes）は**「誰が・いつまでに・何をやるか」「何が決まり、何が決まらなかったか」という合意形成と実行管理**に特化しています。

---

## 2. 2段階生成パイプライン (Two-Stage Pipeline)

```text
transcript/transcript.json (Source of Truth)
    │
    ▼
【Stage 1: 議事録構造化エンジン (MinuteAnalyzer)】
    │  ・会話全体の目的、出席者・役割の推定
    │  ・議題ごとの議論要約と決定事項の抽出
    │  ・アクションアイテム（担当者、期限、タスク内容）の厳格抽出
    │  ・未決・保留・持ち越し事項の明確な分離
    │  ・反語・たとえ話・推測発言の誤読防止
    ▼
minutes/analysis.json (中間構造化成果物)
    │
    ▼
【Stage 2: 議事録文章化エンジン (MinuteComposer)】
    │  ・議事録フォーマットによる Markdown 文章化
    │  ・議題別見出し、チェックボックス付き TODO リストの構築
    │  ・ビジネス文書としての体裁整理
    ▼
├── minutes/minutes.md     (議事録 Markdown)
├── minutes/minutes.txt    (LINE配信用テキスト / Primary Artifact)
└── minutes/metadata.json  (処理時間・トークン数等のメトリクス)
```

---

## 3. 主要コンポーネント

| コンポーネント | 役割 | 依存関係 |
| :--- | :--- | :--- |
| `cli.py` | CLI インターフェース（`--workspace`, `--stage2-only` 等） | `core_env` |
| `core.analyzer.MinuteAnalyzer` | Ollama API を呼び出し、構造化データ `MinuteAnalysisResult` を抽出 | `core_env`, Pydantic |
| `core.composer.MinuteComposer` | 構造化データから議事録 Markdown / Text を生成 | `core_env` |
| `core.workspace_io.WorkspaceIO` | `transcript.json` の読込、`minutes/` 配下成果物の保存 | `core_env` |
| `core.ollama_client.OllamaClient` | LLM 通信、JSON モード抽出、VRAM クリーンアップ | `core_env`, Ollama |

---

## 4. 責任境界

- **責務**:
  - 会話正本から決定事項・TODO・審議結果を漏れなく抽出・構造化すること。
  - 議事録 Markdown および Core 配信用の `minutes/minutes.txt` を出力すること。
- **非責務**:
  - 音声データの直接認識。
  - 感想や主観的要約の追加（決定事項と事実の記録に徹する）。
  - 外部メッセージングサービスへの直接配信。
