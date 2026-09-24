# Project_ALICE Constitution (憲章)

> Version: v1.1.0  
> Status: Ratified  
> Scope: Project_ALICE 全モジュール・基盤  

---

## 前文 (Preamble)

Project_ALICE は、音声や会話から知識を抽出し、人々の意思決定と活動を支援するために設計された自律型AIモジュール群である。

本プロジェクトは音声文字起こしから始まり、要約、議事録の生成、ナレッジの横断検索、知識の蓄積・整理・再利用（メモリ）へと進化してきた。

本 Constitution は、Project_ALICE に関わるすべての設計・実装・運用における最上位の規律および不変の原則を定める。何人・いかなるモジュールも本憲章に背いてはならない。

---

## 第1章：プロジェクト原則 (Project Principles)

### 第1条（現実主義と実利用による進化）
Project_ALICE は実際の利用を通じて進化する。設計は現実の具体的なユースケースを起点とし、将来の可能性だけを理由に過度な抽象化や不要な複雑性を持ち込んではならない（KISS / YAGNI 原則の遵守）。

### 第2条（モジュール型自立システム）
Project_ALICE は自立したモジュールの集合体である。各モジュールは独自の依存関係や仮想環境を持ち、単体で開発・テスト・実行可能なものとする。

---

## 第2章：アーキテクチャ原則 (Architecture Principles)

### 第3条（Workspace Driven CLI 連携・疎結合の義務）
1. 中央オーケストレーター（`ALICE_Core`）および各モジュールは、相手方の Python クラスを直接 import してはならない。
2. モジュール間の連携は、**Workspace Driven CLI 方式**（`python cli.py --workspace <path>` 等）およびファイル契約（Contracts）を通じてのみ行う。

### 第4条（1 Job = 1 Workspace）
1. システムが処理する 1 つの要求（Job）に対し、必ず 1 つの独立した Workspace ディレクトリ（`/data/runtime/workspaces/{job_id}/`）を割り当てる。
2. 入力データ、中間成果物、最終成果物、実行ログはすべて当該 Workspace 内に隔離して記録され、他の Job に干渉してはならない。

### 第5条（Source of Truth：源泉データ主義と派生キャッシュの原則）
1. 音声処理モジュール（`ALICE_Transcript`）が生成する `transcript/transcript.json` は、会話の唯一かつ絶対的な正本（Source of Truth）である。
2. 後続の要約・議事録・分析モジュールは、必ずこの正本データを入力として処理を行わなければならない。
3. 検索インデックス（SQLite + FTS5 等）をはじめとするすべての副次データは、Workspace 群から 100% いつでも再構築可能な「派生キャッシュ（Derived Cache）」と位置づけ、正本データと混同してはならない。

### 第6条（単一責任の原則）
各モジュールは明確な単一の責務を持つ。
- `ALICE_Core`: 受付、認証、JobQueue、オーケストレーション、成果物配信、管理Web UI
- `ALICE_Transcript`: 音声認識、話者分離、発話アライメント
- `ALICE_Summary`: 会話理解、構造化分析、論点要約
- `ALICE_Minutes`: 議事録、決定事項・アクションアイテム・議題経緯の厳格抽出
- `ALICE_Search`: 蓄積されたジョブ成果物の全文検索・属性検索、派生インデックス管理
- `ALICE_CoPilot`: 短期・長期記憶の分類、リレーション管理、ナレッジ同期

他モジュールの責務を越境して内部に取り込んではならない。

---

## 第3章：開発と品質 (Development & Quality)

### 第7条（多段階生成による品質担保）
LLM を用いるモジュールは、単一のプロンプトによる一発生成に依存してはならない。必ず「構造化・情報抽出」→「文章化」→「照合・監査・修正」等の段階的処理（Multi-Stage Pipeline）を構築し、ハルシネーションの排除と決定事項の脱落防止を担保しなければならない。

### 第8条（Primary Artifact 契約）
各モジュールは、CoreWorker および Publisher が直接配信・利用可能なプレーンテキストまたは指定形式の Primary Artifact（例: `transcript.txt`, `summary.txt`, `minutes.txt`）を必ず出力する契約を結ぶものとする。

### 第9条（設計決定の記録）
重要なアーキテクチャの変更、パイプラインの導入、またはデータ契約の改定を行う際は、必ず ADR（Architecture Decision Record）を作成し、その背景・決定・影響を記録しなければならない。

---

## 第4章：統治 (Governance)

### 第10条（最上位規範性）
本 Constitution は Project_ALICE の最上位設計憲章である。下位仕様（Standards、Contracts、Interfaces、各モジュールの個別実装）が本憲章と矛盾する場合、本憲章の定めが優先される。
