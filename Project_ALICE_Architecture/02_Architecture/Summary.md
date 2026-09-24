# ALICE_Summary Architecture

## 1. 概要

`ALICE_Summary` は、`ALICE_Transcript` が生成した会話ログ（`transcript/transcript.json`）を入力とし、ローカル LLM（Ollama: `gemma4:12b` 推奨、フォールバック: `qwen3:14b`）を用いて、高品質な会話要約ドキュメントを生成するモジュールです。

長時間の面談や会議において、情報の脱落やハルシネーション（事実と異なる記述や話者取り違え）を完全に防止するため、**3段階生成方式（Three-Stage Synthesis）** を採用しています。また、面談タイプに応じたタイムライン構造化分析や所見コメント生成（Commentator）を備えています。

---

## 2. 3段階生成パイプライン (Three-Stage Synthesis)

```text
transcript/transcript.json (Source of Truth)
    │
    ▼
【Stage 1: 会話分析エンジン (Analyzer)】
    │  ・会話の全体目的・テーマの把握
    │  ・発言内容・文脈・敬語関係からの話者役割推定
    │  ・主要な論点、事実・認識・指摘事項の整理
    │  ・タイムライン構造化分析（会話の時系列推移・フェーズ変化の追跡）
    │  ・合意点・決定事項・持ち越し課題の抽出
    ▼
summary/analysis.json (中間構造化成果物)
    │
    ▼
【Stage 2: 文章化エンジン (Composer)】
    │  ・人間が瞬時に理解できる自然な Markdown 構成
    │  ・「エグゼクティブサマリー」「論点別詳細」「決定事項」への文章化
    │  ・面談・1on1 向け所見コメント生成 (Commentator)
    ▼
summary/draft_summary.md (ドラフト要約)
    │
    ▼
【Stage 3: 整合性検査＆リファイン (Checker)】
    │  ・ドラフト要約と原文 transcript.json を照合
    │  ・7項目監査（ハルシネーション排除、話者混同防止、事実と解釈の分離等）
    │  ・指摘箇所の自動修正＆再整形
    ▼
├── summary/summary.md             (完成版 Markdown)
├── summary/summary.txt            (完成版 PlainText / Primary Artifact)
├── summary/consistency_report.md  (監査判定レポート)
└── summary/metadata.json          (トークン数・所要時間等のメトリクス)
```

---

## 3. 主要機能とアーキテクチャ特徴

1. **タイムライン構造化分析 (Timeline Analysis)**:
   - 会話の序盤・中盤・終盤における参加者の心理状態や議論の進展を時系列で把握し、多面的な合意形成の文脈を記録。
2. **面談所見ジェネレーター (Commentator)**:
   - 1on1 や指導面談、採用面接において、指導側・面接官側の客観的評価や次回フォローに向けた所見レポートを自動生成。
3. **動的コンテキスト長スケーリング (Dynamic Context Sizing)**:
   - 入力文字数・トークン数に応じて、Ollama 起動パラメータ `num_ctx` を 32,768 〜 65,536 の範囲で自動調整。
   - 120分クラスの長尺面談であっても、末尾の会話が切り捨てられることなく全体を文脈として保持。
4. **耐障害性とフェイルオーバー (Robust Architecture)**:
   - Ollama API タイムアウト時のエクスポネンシャルバックオフ付き自動リトライ。
   - メインモデル（`gemma4:12b`）が利用不能またはクラッシュした場合、セカンダリモデル（`qwen3:14b`）へ自動切り替え。
5. **中間成果物の再利用 (Robust Resume)**:
   - `--stage2-only` や `--stage3-only` オプションにより、途中の `analysis.json` や `draft_summary.md` が有効であれば、高コストな Stage 1 をスキップして途中から再生成が可能。

---

## 4. 責任境界

- **責務**:
  - `transcript/transcript.json` に記録された事実に基づき、正確で構造化された要約ドキュメントを生成すること。
  - Core 配信用 Primary Artifact である `summary/summary.txt` を確実に出力すること。
- **非責務**:
  - 音声データの直接再解析や話者ラベル自体の書き換え。
  - 外部メッセージングサービスへの直接配信。
