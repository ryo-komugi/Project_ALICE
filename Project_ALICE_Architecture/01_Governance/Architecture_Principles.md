# Project_ALICE Architecture Principles (設計基本原則)

> Version: v1.0.0  
> Status: Approved  
> Category: Core Principles  

本ドキュメントは、Constitution（憲章）に基づき、Project_ALICE の全モジュールに適用される技術的アーキテクチャ原則を詳細に定義します。

---

## 原則 1: Workspace Driven CLI 連携 (疎結合アーキテクチャ)

### 宣言
**「モジュール間の境界は CLI とファイルシステムによって厳格に分離され、コードレベルの依存を一切持たない」**

### 根拠
- 各 AI モジュール（Transcript: faster-whisper/PyTorch, Summary/Minutes: Ollama/Pydantic, CoPilot: Discord/SQLite）は要求される Python ライブラリや CUDA/C++ 依存環境が大きく異なります。
- 単一の Python プロセスで import し合う密結合設計は、依存衝突（Dependency Hell）やメモリリーク、GPU リソース枯渇（VRAM 不足）を誘発します。
- Subprocess 呼び出し（`python cli.py --workspace <path>`）を採用することで、モジュールごとの独立した仮想環境実行（`whisper_env`, `core_env` 等）とプロセスクリーンアップを保証します。

### ルール
1. `ALICE_Core` は各モジュールの Python モジュールを直接 `import` してはならない。
2. モジュールの実行は必ず CLI コマンドを経由し、対象の Job Workspace パスを `--workspace` 引数で渡す。
3. 処理結果は戻り値ではなく、Workspace 内に生成された成果物ファイルと終了コード（`0`: 成功, `1`以上: 失敗）によって判定する。

---

## 原則 2: 1 Job = 1 Workspace

### 宣言
**「1つの要求処理（Job）は、自己完結した専用の作業ディレクトリ（Workspace）を持ち、すべての入出力をそこに隔離する」**

### 根拠
- 複数のリクエストが同時・非同期に到着した際、共有ディレクトリでの一時ファイル上書きや競合（Race Condition）を防ぎます。
- Job に関連するすべてのデータ（入力原本、各モジュールの成果物、実行ログ）が1つのディレクトリに集約されるため、トレーサビリティ（追跡可能性）と再現性、障害調査が容易になります。

### ルール
1. Job の生成時に、`/data/runtime/workspaces/{job_id}/` が一意に生成される。
2. Workspace 内の基本構造は以下を厳守する：
   - `job.json`: Job メタデータ・ワークフローステータス
   - `input/`: ユーザーから受け取った音声等の入力原本
   - `{module_name}/`: 各モジュール専用の成果物領域（例: `transcript/`, `summary/`, `minutes/`）
   - `logs/`: Job 固有のモジュール別実行ログ
3. 各モジュールは、指定された自身の成果物領域以外を変更してはならない。

---

## 原則 3: Source of Truth (源泉データ主義)

### 宣言
**「会話の唯一の正本は `transcript/transcript.json` であり、すべての下流処理はこの正本を参照する」**

### 根拠
- 音声認識（Whisper）と話者分離（Pyannote）によって生成された「誰が・いつ・何を話したか」のタイムスタンプ付き構造化データが、後続すべての AI 処理の根拠となります。
- 正本が 1 つに定まっていることで、要約（Summary）や議事録（Minutes）が異なる解釈や推測によるハルシネーションを起こした際、原文照合（Stage 3 監査等）による検証・再実行が可能になります。

### ルール
1. `ALICE_Transcript` は発話開始・終了時刻、話者識別子、発話テキストを含む `transcript.json` を出力する。
2. 後続モジュール（`ALICE_Summary`, `ALICE_Minutes` 等）は、直接音声を再解析するのではなく、必ず `transcript.json` を唯一の入力として処理を開始する。
3. 下流モジュールは正本のテキストや話者ラベルを改ざんして保存してはならない。

---

## 原則 4: 多段階生成パイプライン (Multi-Stage Synthesis)

### 宣言
**「LLM による高度な生成タスクは単一プロンプトで行わず、段階的な情報抽出・構造化・文章化・監査を経る」**

### 根拠
- 長時間の会議ログ（数万トークン）を一括でプロンプトに投入して「要約してください」「議事録を作ってください」と指示すると、決定事項の抜け落ち、話者の取り違え、もっともらしい嘘（ハルシネーション）が発生します。
- 人間の知的作業と同様に、「事実と発言の分解（Stage 1）」→「ドラフト作成（Stage 2）」→「原文照合・チェック（Stage 3）」と分割することで、極めて高い品質と決定事項の網羅性を実現します。

### ルール
1. `ALICE_Summary` は **Three-Stage Synthesis**（Stage 1: 会話分析 `analysis.json` → Stage 2: ドラフト文章化 `draft_summary.md` → Stage 3: 原文照合監査 `summary.md` / `summary.txt`）を実装する。
2. `ALICE_Minutes` は **Two-Stage Pipeline**（Stage 1: 議事録構造化抽出 `analysis.json` → Stage 2: 議事録文章化 `minutes.md` / `minutes.txt`）を実装する。
3. 各ステージの中間成果物は Workspace 内に保存し、再実行（Resume）や部分実行（`--stage2-only` 等）を可能とする。

---

## 原則 5: Primary Artifact 契約と Publisher 分離

### 宣言
**「モジュールは Core 配信用の Primary Artifact を約定し、配信チャネルへの送信責務は Publisher が一元管理する」**

### 根拠
- 各モジュールが LINE や Discord などの配信 API を個別に叩くと、認証トークンの分散や配信失敗時のリトライ責務が重複します。
- Core の `Publisher`（`LinePublisher` 等）が最終成果物の配信を一元管理することで、モジュール側は純粋なドキュメント生成に集中できます。また、将来の配信先追加（Slack, メール, クラウドストレージ等）にも Core 側の拡張のみで対応可能になります。

### ルール
1. 各モジュールは、外部ユーザーへ直接届けるプレーンテキスト形式の Primary Artifact（`transcript.txt`, `summary.txt`, `minutes.txt` 等）を出力する。
2. モジュールは外部配信 API（LINE Messaging API 等）を直接呼び出してはならない。
3. CoreWorker は全 Workflow 完了時に、最終ステップの Primary Artifact を Publisher 経由でユーザーへ配信する。
