# ALICE_Summary

> Project_ALICE 用の高度会話理解・段階的要約（Summary）モジュール

---

## 1. 概要

ALICE_Summary は、前段の `ALICE_Transcript` が生成した会話ログ（`transcript/transcript.json`）を入力として受け取り、ローカル LLM（Ollama: `gemma4:12b` 推奨、フォールバック: `qwen3:14b`）を用いて会話の背景・論点・話者認識を理解・構造化したうえで、人間が短時間で全体像を把握できる高品質な要約ドキュメントを生成する独立モジュールです。

単なるテキスト短縮ではなく、**「文字起こし → 会話理解・構造化（Stage 1: `analysis.json`） → ドラフト文章化（Stage 2: `draft_summary.md`） → 原文照合・7項目監査＆精密修正（Stage 3: `summary.md` / `summary.txt` / `consistency_report.md`）」** の 3 段階生成方式（Three-Stage Synthesis）を採用しています。

また、会議・面談の長さに応じてコンテキスト長を自動調整する**動的コンテキスト長スケーリング（Dynamic Context Sizing: 32k〜64k）**を搭載し、120分クラスの長尺面談であっても会話後半の切り捨てをゼロにして完全読解します。

さらに、本番バックグラウンド運用に耐えうる高信頼性機能として、**Ollama API タイムアウト・エクスポネンシャルバックオフ自動リトライ**、**セカンダリモデル（qwen3:14b等）への自動フェイルオーバー**、および**破損中間成果物の自動検知・再生成（Robust Resume）**を完備しています。

---

## 2. 責任境界とモジュール連携

* **ALICE_Core との関係**:
  * Core からの直接 import は一切行わず、CLI（`python cli.py --workspace <path>`）経由で Subprocess 実行されます。
  * Core の `MODULE_RUNNERS["summary"]` における primary artifact である `summary/summary.txt`（および `summary.md`）を確実に生成します。
* **ALICE_Transcript との関係**:
  * Transcript モジュールへの直接 import・コード依存は一切行いません。
  * Workspace 内に配置された `transcript/transcript.json`（契約ファイル・源泉データ）を唯一の入力として読み込みます。
  * Transcript の speaker label 自体は書き換えません。発言内容・敬語・指導関係から役割を意味的に推定します。
* **所有領域**:
  * Workspace 内の `<workspace>/summary/` のみ所有・書き込みを行います。

---

## 3. CLI 実行契約

### 実行コマンド

```bash
/home/takuya/Project_ALICE/myenv/core_env/bin/python /home/takuya/Project_ALICE/ALICE_Summary/cli.py --workspace /data/runtime/workspaces/{job_id} [--model gemma4:12b] [--stage2-only] [--stage3-only] [--skip-stage3] [--force-all]
```

### 引数仕様
* `--workspace <path>` (必須): 対象 Job の Workspace ディレクトリパス
* `--model <name>` (任意): 使用する Ollama モデル名（デフォルト: `gemma4:12b`）
* `--stage2-only` (任意): 既存の `analysis.json` を使用し、Stage 2 以降を再実行する
* `--stage3-only` (任意): 既存の `draft_summary.md` を使用し、Stage 3（整合性チェック）のみを再実行する
* `--skip-stage3` (任意): Stage 3 をスキップし、Stage 2 のドラフトを最終成果物とする
* `--force-stage1` / `--force-all` (任意): 既存の中間成果物を無視して最初から全再実行する

### 入出力契約
* **入力ファイル**: `<workspace_dir>/transcript/transcript.json`（必須）
  * スキーマ: `[{"start": float, "end": float, "speaker": str, "text": str}]`
* **出力ディレクトリ**: `<workspace_dir>/summary/`
* **生成成果物**:
  1. `analysis.json`: Stage 1 で構造化された会話分析データ（目的、話者役割、論点、事実・認識・指摘、合意点、根本課題）
  2. `draft_summary.md`: Stage 2 で生成されたドラフト要約 Markdown
  3. `summary.md`: Stage 3 で原文照合・監査・修正を施した完成版要約 Markdown
  4. `summary.txt`: Markdown 記法に依存せずそのまま読めるプレーンテキスト版要約
  5. `consistency_report.md`: Stage 3 による7項目基準（ハルシネーション排除・話者混同防止・評価と事実の分離等）の監査判定レポート
  6. `metadata.json`: 実行モデル、各 Stage の所要時間、トークン数、適用コンテキスト長などの運用・評価メトリクス
* **終了コード**:
  * 正常完了: `0`
  * 異常終了: `1` 以上（標準エラー出力およびログにエラー詳細）

---

## 4. ディレクトリ構成

```text
ALICE_Summary/
├── cli.py                    # Core 連携 CLI Adapter (--workspace 対応)
├── config.py                 # 設定管理（モデル, Ollama URL, num_ctx, keep_alive等）
├── prompts/                  # 外部化プロンプトテンプレート
│   ├── stage1_analysis.txt     # Stage 1 会話理解・構造化プロンプト
│   ├── stage2_composition.txt  # Stage 2 人間向け要約文章化プロンプト
│   └── stage3_consistency.txt  # Stage 3 原文照合・整合性チェックプロンプト
├── core/
│   ├── __init__.py
│   ├── models.py             # analysis.json データモデル (Pydantic)
│   ├── workspace_io.py       # Workspace 入出力 (transcript, analysis, summary, metadata)
│   ├── ollama_client.py      # Ollama API クライアント (/api/chat, JSON抽出)
│   ├── analyzer.py           # Stage 1 会話構造化エンジン
│   ├── composer.py           # Stage 2 文章化エンジン
│   └── checker.py            # Stage 3 整合性チェッカー＆リファイナー
├── README.md                 # 本ドキュメント
├── test_unit.py              # 単体テストスイート
└── test_summary.py           # 実データ E2E / CLI 統合テストスイート
```

