# Project_ALICE Architecture

## 1. What is this?

本リポジトリは **Project_ALICE** のアーキテクチャドキュメント群です。

Project_ALICE は、音声認識・話者分離・LLM要約・議事録作成・知識検索・長期記憶を統合した、自立分散型のモジュール型 AI アシスタント基盤です。以下のモジュールで構成されています。

| モジュール | スコープ | 環境 |
| :--- | :--- | :--- |
| `ALICE_Core` | Gateway / Hub / Portal（3層モジュラーモノリス）、JobQueue、WorkspaceManager、LINE連携、Admin WebUI | `core_env` |
| `ALICE_Transcript` | 音声文字起こし（`large-v3-turbo`）、話者分離（Pyannote）、アライメント、正規化 | `whisper_env` |
| `ALICE_Summary` | 3段階要約パイプライン（分析→ドラフト→照合）、タイムライン分析、面談所見生成 | `core_env` |
| `ALICE_Minutes` | 2段階議事録パイプライン（v0.2.0）、LLMスピーカー統合、テンプレート別整形 | `core_env` |
| `ALICE_Search` | SQLite + FTS5 trigram 全文検索、属性検索、講評検索、派生キャッシュ管理 | `core_env` |
| `ALICE_CoPilot` | 短期/長期記憶管理、Obsidian同期、Discord検索連携、Antigravity自律パッチワーカー、アーキテクチャ監査 | `copilot_env` |

---

## 2. ドキュメント構造

```
Project_ALICE_Architecture/
│
├── 01_Governance/                 # プロジェクト憲章・ゴール・マイルストーン
│   ├── Constitution.md            # アーキテクチャ憲章 (10 ヶ条)
│   ├── Architecture_Principles.md # 設計原則詳細
│   └── Milestones_v1.0.md         # v1.0 ゴール定義・マイルストーン・機能マトリクス
│
├── 02_Architecture/               # システム設計・概念・モジュール詳細
│   ├── Overview.md                # システム全体像・Hub/Gateway/Portal 3層・オーケストレーション・成否境界・Zero Trust
│   ├── Workspace_Structure.md     # 1 Job = 1 Workspace (/data/runtime/workspaces/{job_id}/) 仕様・クリーンアップ規約
│   ├── Transcript.md              # ALICE_Transcript 内部パイプライン設計 (large-v3-turbo, Defragmented)
│   ├── Summary.md                 # ALICE_Summary 3段階合成パイプライン設計 (タイムライン分析, 所見生成)
│   ├── Minutes.md                 # ALICE_Minutes v0.2.0 ハイブリッドパイプライン (LLMスピーカー統合, テンプレート)
│   ├── Search.md                  # ALICE_Search 全文検索・講評検索・属性検索・派生キャッシュ設計
│   ├── CoPilot.md                 # ALICE_CoPilot メモリ管理・Obsidian同期・Antigravity自律改善設計
│   ├── Alignment.md               # ワードレベル話者アライメント設計
│   └── Glossary.md                # 共通用語集（Authority Glossary）
│
├── 03_ADR/                        # Architecture Decision Records (設計決定記録)
│   ├── 001_work_directory.md      # Workspace Driven CLI / 1 Job 1 Workspace の採択
│   ├── 02_transcript_json.md      # transcript.json の正本データスキーマ採択
│   ├── 003_utterance_builder.md   # Utterance Builder の導入
│   ├── 004_Text Normalizer.md     # 独立 Text Normalizer の導入
│   ├── 005_three_stage_summary.md # 3段階要約合成（Three-Stage Synthesis）の採択
│   ├── 006_two_stage_minutes.md   # 2段階議事録生成パイプラインの採択
│   ├── 007_knowledge_search_sqlite_fts5.md # SQLite FTS5 trigram 検索基盤の採択
│   ├── 008_cloudflare_zero_trust_auth.md   # 管理UIにおける自前MFA撤去とCloudflare Zero Trust採択
│   └── 009_core_three_layer_architecture.md    # ALICE_Core の Hub/Gateway/Portal 3層モジュラーモノリス構造採択
│
├── 04_Standards/                  # 開発・運用標準規約
│   ├── Directory_Standard.md      # /data/runtime 配下のディレクトリ命名・配置規約
│   ├── CLI_Contract_Standard.md   # モジュール CLI 実行契約（引数・終了コード・成果物規約）
│   └── Logging_Guideline.md       # システム共通・Job別ロギング規約
│
├── 05_Contracts/                  # モジュール間データ契約・成果物スキーマ
│   ├── job_json_schema.md         # job.json スキーマ定義
│   ├── transcript_contract.md     # transcript.json / transcript.txt データ契約
│   ├── summary_contract.md        # analysis.json / summary.md / summary.txt データ契約
│   ├── minutes_contract.md        # analysis.json / minutes.md / minutes.txt データ契約
│   └── search_contract.md         # 検索結果 JSON スキーマ / インデックス対象契約
│
├── 06_Interfaces/                 # 外部公開・モジュール呼び出しインターフェース
│   └── CLI_Specification.md       # 各モジュールの CLI コマンド仕様書
│
└── 99_notes/                      # 設計ドラフト・ディスカッションメモ
    └── Project_ALICE_Constitution_v0.1_20260702_Draft.txt
```

---

## 4. Core Design Philosophy

Project_ALICE のアーキテクチャは以下の基本理念に基づいています。

1. **モジュール疎結合（Decoupled by Workspace CLI）**:
   モジュール間の Python クラス import による密結合を排除し、すべて CLI（`python cli.py --workspace <path>` 等）と Workspace 内のファイル成果物を介して連携します。
2. **1 Job = 1 Workspace**:
   Job ごとに専用のディレクトリを割り当て、入力から中間ファイル・最終成果物・実行ログまでを完結して保持します。
3. **Source of Truth（源泉データ主義）と派生キャッシュ（Derived Cache）**:
   `ALICE_Transcript` が生成する `transcript/transcript.json` および Workspace 内の成果物テキストを唯一の正本とします。検索インデックス（SQLite + FTS5）等の副次データはいつでも Workspace 群から 100% 再構築可能な「派生キャッシュ」として扱います。
4. **Job 成否と検索 Index 更新の完全分離（成否境界）**:
   ユーザーへの価値提供（成果物生成および LINE 配信）の完了をもって Job 自体は 100% COMPLETED と確定し、後続の検索インデックス更新エラーによって Job を失敗扱いに巻き込まない構造的耐障害性を保証します。
5. **多段階生成パイプライン（Multi-Stage Synthesis）**:
   LLM による直接の一発生成を避け、「構造化分析」→「文章化」→「照合・監査」という段階的アプローチをとることで、ハルシネーションや情報の脱落を防止します。
6. **Primary Artifact 契約**:
   各モジュールは完了時に規約された Primary Artifact（プレーンテキスト版成果物等）を出力し、Core の Publisher がこれを外部ユーザーへ配信します。

---

## 5. Goals & Milestones (Roadmap)

Project_ALICE は、音声認識・要約・議事録・検索・記憶同期を統合したパーソナル AI アシスタント基盤として **ALICE v1.0** を正式リリース（2026-09-13）し、現在は実利用に基づく機能拡張フェーズ（v1.1〜v1.4）を展開しています。

詳細な達成基準、マイルストーン、および運用ルールは **[01_Governance/Milestones_v1.0.md](01_Governance/Milestones_v1.0.md)** を参照してください。

### 5.1 マイルストーン進捗サマリー

| Milestone | 概要 | 状態 |
| :--- | :--- | :---: |
| **M1: コア基盤 & 音声認識パイプライン** | `ALICE_Core` (JobQueue, WorkspaceManager, LINE), `ALICE_Transcript` (Whisper, Pyannote, Alignment) | **完了** |
| **M2: 多段階LLM生成エンジン** | `ALICE_Summary` (3-Stage要約, 動的コンテキスト), `ALICE_Minutes` (2-Stage議事録) | **完了** |
| **M3: ナレッジ検索基盤 & 派生キャッシュ** | `ALICE_Search` (SQLite+FTS5 trigram, BM25, 成否境界, 非ブロッキング連携) | **完了** |
| **M4: 知識オフロード・メモリ同期・対話** | `ALICE_CoPilot` (短期/長期記憶分類, Obsidian自動同期, Discord Search連携) | **完了** |
| **M5: 運用管理Web UI & キューUX** | Admin Web UI (PWA, キュー可視化, サイバーワンダーランド起動画面, LINE Flex配信) | **完了** |
| **M6: v1.0 正式リリース・結合テスト** | 全系統 E2E 結合検証, ドキュメント完全同期, 障害リカバリ確認, リリース確定 | **完了 (2026-09-13)** |
| **v1.1: 記憶・管理コックピット基礎** | 記憶オーナー分離, CoPilot 3大能力, User Directory, Reject制御, HANDOFF | **完了 (2026-09-14)** |
| **v1.2: J.A.R.V.I.S. 行動結合 & ゼロトラスト** | Google カレンダー/Tasks, Tool Guard, Cloudflare Zero Trust (ADR-008), 夜間自律点検 | **完了 (2026-09-20)** |
| **v1.3: コアアーキテクチャ整流 & 自律改善** | Hub/Gateway/Portal 3層分解, バースト受信, SLA/リトライ, Antigravity自律パッチワーカー, アーキテクチャ監査, Minutes v0.2.0 | **開発中 (2026-09-27)** |
| **v1.4: J.A.R.V.I.S. Voice（声の相棒）** | 自宅工房モード（常駐マイク＆TTS口頭応答）／外出モバイルモード（PWAリアルタイム音声） | **設計・検証中** |
| **v1.5: 専用モバイルアプリ & 統合拡張** | Flutter モバイルアプリ (Foreground録音/閲覧), 話者名前マッピング, ドキュメント投入 | **構想フェーズ** |

### 5.2 継続的拡張とマイルストーン更新方針 (Dynamic Milestone Governance)
開発過程で「これを入れたい」「あの機能も追加でほしい」といった新たな要求やアイデアが発生した場合は、**随時相談・合意形成** を行い、アーキテクチャ憲章（モジュール疎結合、1 Job 1 Workspace等）との適合性を確認した上で、柔軟にマイルストーンへ組み込みます。
