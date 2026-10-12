# ALICE_Minutes Architecture

## 1. 概要

`ALICE_Minutes` は、`ALICE_Transcript` が生成した会話ログ（`transcript/transcript.json`）を入力とし、会議や面談における**「決定事項」「アクションアイテム（TODO・担当・期限）」「議題別審議経緯」「保留・持ち越し事項」**を正確に抽出した議事録（Meeting Minutes）を生成する独立モジュールです。

要約（Summary）が「会話の全体像や論点を把握すること」を主目的とするのに対し、議事録（Minutes）は**「誰が・いつまでに・何をやるか」「何が決まり、何が決まらなかったか」という合意形成と実行管理**に特化しています。

---

## 2. ハイブリッド 2段階生成パイプライン（v0.2.0）

```text
transcript/transcript.json (Source of Truth)
    │
    ▼
【Stage 1: 議事録構造化エンジン (MinuteAnalyzer)】
    │  ・会話全体の目的、出席者・役割の推定
    │  ・LLM によるスピーカー統合・重複排除（SPEAKER_00 等の文脈統合）
    │  ・議題ごとの議論要約と決定事項の抽出
    │  ・アクションアイテム（担当者、期限、タスク内容）の厳格抽出
    │  ・未決・保留・持ち越し事項の明確な分離
    │  ・反語・たとえ話・推測発言の誤読防止
    ▼
minutes/analysis.json (中間構造化成果物 / Pydantic V2 バリデーション済み)
    │
    ▼
【Stage 2: 議事録文章化エンジン (MinuteComposer)】
    │  ・会議タイプ別 Markdown テンプレートによる整形:
    │      standard.md  : 一般会議テンプレート（デフォルト）
    │      executive.md : 経営レビュー・意思決定フォーカス
    │      interview.md : 採用・面談形式
    │      consultation.md : 相談・1on1 支援形式
    │  ・議題別見出し、チェックボックス付き TODO リストの構築
    │  ・ビジネス文書としての体裁整理
    │  ・<think> タグ等 LLM 内部推論の自動除去
    ▼
├── minutes/minutes.md     (議事録 Markdown)
├── minutes/minutes.txt    (LINE配信用テキスト / Primary Artifact)
└── minutes/metadata.json  (処理時間・トークン数等のメトリクス)
```

---

## 3. 主要コンポーネント

| コンポーネント | 役割 | 依存関係 |
| :--- | :--- | :--- |
| `cli.py` | CLI インターフェース（`--workspace`, `--stage2-only`, `--template` 等） | `core_env` |
| `core.pipeline.MinutePipeline` | 全体実行フロー制御（Stage 1 → Stage 2 の順次実行・エラーハンドリング・再開管理） | `core_env` |
| `core.analyzer.MinuteAnalyzer` | Ollama API を呼び出し、Pydantic V2 で構造化データ `MinuteAnalysisResult` を抽出 | `core_env`, Pydantic V2 |
| `core.composer.MinuteComposer` | テンプレート別に Markdown / Text を生成 | `core_env` |
| `core.workspace_io.WorkspaceIO` | `transcript.json` の読込、`minutes/` 配下成果物の保存 | `core_env` |
| `core.ollama_client.OllamaClient` | LLM 通信、JSON モード抽出、VRAM クリーンアップ | `core_env`, Ollama |
| `prompts/stage1_analysis.md` | Stage 1 プロンプト（LLMスピーカー統合・重複排除ルール含む） | — |
| `prompts/templates/*.md` | Stage 2 整形テンプレート（standard / executive / interview / consultation） | — |

---

## 4. v0.2.0 主要変更点

1. **LLM スピーカー統合 & 重複排除（Speaker Consolidation）**:
   - Stage 1 プロンプトに明示的なルールを追加。`SPEAKER_00` 等の機械的識別子を文脈から推定・統合し、重複エントリを排除してアクションアイテムの粒度を一意化。
2. **Markdown テンプレート体系の整備**:
   - プロンプトファイルを `.txt` から `.md` 形式に統一。`standard` / `executive` / `interview` / `consultation` の 4 テンプレートを整備し、会議タイプに応じた最適な整形を実現。
3. **MinutePipeline の抽出（クリーンアーキテクチャ）**:
   - `cli.py` に混在していたパイプライン制御ロジックを `core/pipeline.py` の `MinutePipeline` クラスへ分離し、テストカバレッジを大幅に向上。
4. **Pydantic V2 移行**:
   - `core/models.py` の全モデルを Pydantic V2 API に準拠。バリデーションと型安全性を強化。
5. **completion guard（完了ガード）**:
   - 各ステージの出力ファイル存在チェックを強化し、部分的な成果物のみ残るまま終了する誤認識を防止。

---

## 5. 責任境界

- **責務**:
  - 会話正本から決定事項・TODO・審議結果を漏れなく抽出・構造化すること。
  - 議事録 Markdown および Core 配信用の `minutes/minutes.txt` を出力すること。
- **非責務**:
  - 音声データの直接認識。
  - 感想や主観的要約の追加（決定事項と事実の記録に徹する）。
  - 外部メッセージングサービスへの直接配信。
