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
minutes/minutes.docx  (アップロードされたDOCXフォームがある場合)
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
| `minutes.docx` | アップロードされたDOCXフォームの記入済み成果物（任意） | Word DOCX |

 DOCXフォームは `input/minutes_form.docx` として同じWorkspaceに渡します。記入したい場所に `[会議テーマ]`、`[出席者]`、`[議題]`、`[決定事項]`、`[アクションアイテム]` などのタグを置いてください。生成した議事録本文を入れる場所には `[本文]`（または `[議事録本文]`）が必須です。別表など2つ目の記入場所へ本文を続ける場合は `[本文(継続)]` を置くと、本文を段落の切れ目でおおむね半分に分けて記入します。本文欄には生成済みMarkdown議事録をプレーンテキスト化して使用します。アクションアイテム専用タグがある場合は該当節を、件名・日時・参加者のタグがある場合はMarkdownの第1項から該当する行を機械的に除き、日時欄は `[日時]` 等のタグにも転記します。目的・背景は本文に残します。本文をLLMで再要約・再構成しません。既定タグは構造化データから埋め、独自タグのみ構造化分析と生成済み議事録を参照してLLMが抽出し、該当情報がなければ空欄にします。詳しい協議要旨や主な意見は `[補足事項]`（別名 `[詳細なやり取り]`、`[協議経緯]`、`[議論の経緯]`）に出力できます。フォームにアクションアイテム専用タグがある場合は、本文欄からアクションアイテム節を除いて重複を防ぎます。専用タグがない場合は本文欄に残します。長い内容を入れる行はページ間で分割できるようにし、短い見出し行の設定は維持します。タグの位置だけを書き換え、空欄セルや見出しから場所を推測しません。文書の段落・表レイアウトを保つため、実際の書き込みは `python-docx` で行います。Core の `Docs/requirements_core_env.txt` を反映し、Core Python環境に依存パッケージを導入してください。

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
