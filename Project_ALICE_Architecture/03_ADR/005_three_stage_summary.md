# ADR-005 ALICE_Summary における 3段階生成方式 (Three-Stage Synthesis) の採択

## ステータス
採用 (Accepted)

## 背景
長時間の面談・会議音声（60分〜120分超）の文字起こしデータは、数万トークンに達する。
これを単一のプロンプトで「要約してください」と指示して一発生成（One-Shot Generation）させた場合、以下の重大な問題が発生した：
1. **重要な論点・決定事項の脱落**: コンテキスト中間〜後半の情報が無視される「Lost in the Middle」現象。
2. **話者混同とハルシネーション**: 発言者 A の意見を B の発言として要約したり、会話に存在しないもっともらしい推測を事実として記述してしまう。
3. **失敗時の再実行コスト**: 単一ステップの場合、生成途中で失敗した際に最初から全てやり直す必要があり、GPU 負荷・所要時間が膨大化する。

## 決定
`ALICE_Summary` において、3段階生成方式（Three-Stage Synthesis）を採用する。

1. **Stage 1: 会話分析・構造化 (Analyzer)**:
   - 全文から目的、出席者役割、論点、事実・指摘事項、決定事項を抽出し、Pydantic モデルで検証された `analysis.json` を生成。
2. **Stage 2: ドラフト要約文章化 (Composer)**:
   - `analysis.json` に基づき、人間が読みやすい構造化 Markdown 要約 `draft_summary.md` を生成。
3. **Stage 3: 原文照合・監査・修正 (Checker & Refiner)**:
   - `draft_summary.md` と原文 `transcript.json` を照合し、ハルシネーションや話者混同がないか7項目監査を実施。
   - 監査結果に基づき修正を適用した最終版 `summary.md` / `summary.txt` および `consistency_report.md` を出力。

## 影響
- **メリット**:
  - ハルシネーションと話者取り違えの劇的な低減。
  - `--stage2-only` や `--stage3-only` による中間生成物の再利用（Robust Resume）が可能。
- **デメリット**:
  - LLM の推論回数が最大3回となり、総処理時間が増加する。ただしバッチ処理であるため品質の向上が優先される。
