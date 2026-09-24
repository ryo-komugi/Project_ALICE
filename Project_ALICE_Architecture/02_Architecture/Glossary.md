# Project_ALICE Glossary (用語集)

> Version: v1.1.0  
> Status: Ratified  
> Scope: Project_ALICE 全体  

本ドキュメントは、Project_ALICE 全体で共通して使用される用語・概念の公式定義を定めます。

---

## 1. コア概念 (Core Concepts)

### Project (プロジェクト)
Project_ALICE 全体を指す最上位の概念。複数の自立した Module と中央の Core から構成される。

### Module (モジュール)
Project_ALICE 内で独立して開発・運用・リリースされる機能単位。独自の仮想環境と CLI を持ち、疎結合に動作する。
- **実装済み**: `ALICE_Core`, `ALICE_Transcript`, `ALICE_Summary`, `ALICE_Minutes`, `ALICE_Search`, `ALICE_CoPilot`

### Core (コア / ALICE_Core)
外部クライアント（LINE 等）からの要求受付、Job ライフサイクル、非同期 JobQueue、各モジュールの順次 Subprocess 実行、成果物配信、Admin Web UI を一元管理するオーケストレーター。

### Job (ジョブ)
ユーザーから受け取った 1 つの処理要求の単位。一意な `job_id`（例: `job_YYYYMMDD_HHMMSS`）を持ち、1つの独立した Workspace に紐づく。

### Workspace (ワークスペース)
1 つの Job 専用に割り当てられる隔離された作業ディレクトリ（`/data/runtime/workspaces/{job_id}/`）。入力音声、各モジュールの中間・最終成果物、実行ログが集約される。

### Workflow (ワークフロー)
1 つの Job を完了するために順次実行されるモジュールのパイプライン定義（例: `["transcript"]`、`["transcript", "summary"]`）。

---

## 2. データ・成果物概念 (Data & Artifact Concepts)

### Source of Truth (源泉データ / 一次正本)
会話内容の唯一の構造化正本データである `transcript/transcript.json`。後続の要約や議事録モジュールはすべてこれを入力契約として処理を行う。また広義には、各 Workspace 内に永続化された成果物テキスト群そのものを指す。

### Primary Artifact (プライマリアーティファクト)
各モジュールが正常終了時に必ず生成することを契約した、CoreWorker / Publisher 向けの配信成果物（例: `transcript.txt`, `summary.txt`, `minutes.txt`）。

### Intermediate Artifact (中間成果物)
多段階生成の各ステージ間で受け渡される構造化データ（例: Summary の `analysis.json`, `draft_summary.md`、Minutes の `analysis.json`）。再実行や監査に利用される。

### Derived Cache (派生キャッシュ / 二次インデックス)
正本データ（Workspace）から生成される検索用インデックス（`ALICE_Search` の SQLite + FTS5 等）。消失・破損しても Workspace 群から 100% いつでも完全再構築が可能な副次データを指す。

### Contract (契約)
モジュール間で授受されるデータスキーマ（JSON Schema 等）やファイル配置の合意定義。モジュールの内部実装ではなく入出力仕様を規定する。

---

## 3. 生成・アーキテクチャ手法 (Methods & Architecture)

### Workspace Driven CLI
モジュール間の依存を排除し、すべて CLI 引数（`python cli.py --workspace <path>` 等）と Workspace ディレクトリ内のファイル授受によって連携するアーキテクチャ方式。

### Multi-Stage Synthesis (多段階生成)
LLM によるハルシネーションや情報の脱落を防ぐため、プロンプトを「情報抽出・構造化」→「文章化」→「原文照合・監査」などの複数フェーズに分割して実行する手法。

### Success Boundary (成否分離境界)
Job 本体の成否判定と、派生処理（検索インデックス更新等）の成否を明確に分離する設計境界。成果物の生成と配信が完了した時点で Job は 100% 成功とみなされ、その後の派生処理の失敗によって Job が巻き添えで失敗になることを防止する。

### FTS5 Trigram
SQLite FTS5 において 3 文字単位の n-gram 転置インデックスを生成するトークナイザー。形態素解析器（MeCab 等）の外部依存なしに、日本語・英数字が混在する文章の高速全文検索を実現する。

### Dynamic Context Sizing (動的コンテキスト長調整)
入力文字数に応じて、LLM（Ollama）のコンテキスト窓長（`num_ctx`）を 32k〜64k の間で動的にスケーリングし、長尺面談の文脈切り捨てを防ぐ技術。
