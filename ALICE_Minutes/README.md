# ALICE_Minute (ALICE_Minutes)

> Project_ALICE 構造化議事録生成モジュール (v0.2.0)

---

## 1. 概要

ALICE_Minute は、`ALICE_Transcript` が生成した構造化音声文字起こしデータ（`transcript/transcript.json`）を事実の正本とし、`ALICE_Summary` の Stage 1 分析結果（`summary/analysis.json`）を議論構造の見取り図としてハイブリッド連携することで、会議や面談における**「決定事項」「アクションアイテム（TODO）」「議題別の審議経緯」「保留・持ち越し事項」**を高精度に記録した議事録（Meeting Minutes）を生成するモジュールです。

---

## 2. 2段階生成パイプライン (Two-Stage Pipeline)

会話の長大化による決定事項やTODO・期限の脱落を防ぎ、高品質な議事録を生成するため、2段階処理を採用しています。

```text
transcript/transcript.json (事実の正本)
summary/analysis.json       (議論構造の見取り図)
    │
    ▼
【Stage 1: Analyzer】 (MinuteAnalyzer)
    │  ・Summaryの見取り図を骨格として活用
    │  ・会話全体の目的、出席者役割の同定
    │  ・議題ごとの議論要約と決定事項・合意レベルの抽出
    │  ・アクションアイテム（担当者、優先度、期限、タスク）の厳格抽出
    │  ・未決・保留事項の明確な分類
    │  ・反語・たとえ話・仮想事例の誤読・誤帰属防止
    ▼
minutes/analysis.json (構造化中間成果物)
    │
    ▼
【Stage 2: Composer】 (MinuteComposer)
    │  ・指定テンプレート（standard / interview / executive）のMarkdown文章化
    │  ・見出し、優先度ラベル、チェックボックス付きTODOリストの構築
    │  ・Ollama VRAM即時解放 (keep_alive: 0)
    ▼
minutes/minutes.md    (Markdown議事録 / Primary Artifact)
minutes/minutes.txt   (Plain Text議事録)
minutes/metadata.json (実行時間・モデル・トークン情報)
```

---

## 3. CLI インターフェース契約

ALICE_Core との連携は、Workspace を引数とする Subprocess 方式で行われます。

```bash
# 基本実行 (Stage 1 -> Stage 2, デフォルトテンプレート: standard)
python cli.py --workspace /path/to/workspace

# テンプレート指定実行 (standard / interview / executive)
python cli.py --workspace /path/to/workspace --template interview

# Stage 1 をスキップし、既存の analysis.json から議事録のみ再生成
python cli.py --workspace /path/to/workspace --stage2-only --template executive

# 既存の analysis.json があっても強制的に Stage 1 から再実行
python cli.py --workspace /path/to/workspace --force-stage1

# モデルの明示指定
python cli.py --workspace /path/to/workspace --model gemma4:12b
```

---

## 4. 成果物仕様 (`minutes/`)

| ファイル名 | 役割 | 形式 |
| :--- | :--- | :--- |
| `analysis.json` | 会話から抽出された議事録構造化データ | JSON (`MinuteAnalysisResult`) |
| `minutes.md` | **Webビューア用 Primary Artifact** (見出し・表・チェックボックス付き) | Markdown |
| `minutes.txt` | プレーンテキスト議事録 (記号フォーマット付き) | PlainText |
| `metadata.json` | 処理時間、トークン数、決定事項数、使用テンプレート等 | JSON |

---

## 5. ディレクトリ構成

```text
ALICE_Minutes/
├── config.py                 # Minute 設定管理 (gemma4:12b / fallback gemma4:e4b, template)
├── cli.py                    # Core 連携用 CLI アダプタ (--template 対応)
├── version.py                # バージョン定義 (v0.2.0)
├── README.md                 # 仕様ドキュメント
├── .gitignore                # Git 除外設定
├── core/
│   ├── __init__.py
│   ├── models.py             # Pydantic 議事録データモデル
│   ├── workspace_io.py       # Workspace 入出力・Markdown変換・Template読込
│   ├── ollama_client.py      # Ollama /api/chat 通信 & 二重 VRAM 解放
│   ├── analyzer.py           # Stage 1: ハイブリッド議事録構造化エンジン
│   └── composer.py           # Stage 2: マルチテンプレート議事録文章化エンジン
├── prompts/
│   ├── stage1_analysis.md    # Stage 1 構造化プロンプト
│   └── templates/            # Stage 2 テンプレート集
│       ├── standard.md       # 標準会議議事録
│       ├── interview.md      # 面談・1on1議事録
│       └── executive.md      # 役員・経営報告用サマリー
└── test_unit.py              # 単体テストスイート
```
