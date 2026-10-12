# ALICE_CoPilot Architecture

## 1. 概要

`ALICE_CoPilot` は、Project_ALICE におけるオフロードメモリ構築・ナレッジ管理・対話支援・自律改善モジュールです。

ユーザーとの日常対話（Discord 等）や各種テキスト情報・添付ファイル（Markdown 等）から、自動的に**「短期記憶」**と**「長期記憶」**を分類・抽出し、エンティティ間のリレーション（`related`, `supersedes`, `conflicts`）を構築します。

構築されたメモリは起動時および変更時に **Obsidian** のバウルトと自動同期され、AI エージェントやユーザーが文脈や決定履歴を即座に参照できる環境を提供します。また、**`ALICE_Search`** と連携し、過去の音声処理成果物（要約・文字起こし）を Discord 上から即座に検索・引用できるインターフェースを提供します。

さらに、**Google Antigravity SDK** を活用した自律パッチワーカーおよび自己診断機構により、コードベースの健全性を継続的に自律維持します。

---

## 2. アーキテクチャとデータ構造

```text
User / Discord Messages & Attachments
    │
    ▼
【Memory Ingestion & Router】
    │
    ├─────────────────────────────┐
    ▼                             ▼
【Short-term Memory】        【Memory Classifier】
・SQLite (conversations.db)   ・コンテキスト解析
・セッション内会話履歴         ・記憶タイプ判定 (context, project, decision, knowledge, idea)
                                  │
                                  ▼
                             【Memory Consolidator & Relations】
                              ・重複検出 & マージ
                              ・リレーション構築 (related, supersedes, conflicts)
                              ・カタカナ語 NFKC 正規化 & 中黒複合語抽出
                                  │
                                  ▼
                             【Long-term Memory Store】
                              /data/memory/copilot/longterm/
                              ├── Context/
                              ├── Projects/
                              ├── Decisions/
                              ├── Knowledge/
                              └── Ideas/
                                  │
                                  ▼ (Obsidian Exporter / Auto-Sync on Startup)
                             【Obsidian Vault Sync】
                              /data/memory/obsidian/

─────────────────────────────────────────────────────────────
【自律改善サブシステム (reviewer/)】
    │
    ├── Nightly Reviewer (毎晩 03:00 JST)
    │    ・過去24hの対話ログ・システムログを自律点検
    │    ・Antigravity SDK (gemma4:12b) による自律推論・ツール実行
    │    ・知識欠落・未登録仕様の自動検知 & 長期記憶補完
    │
    ├── Auto Patcher (antigravity_autonomous_patch_worker)
    │    ・Antigravity SDK による自律コードパッチ生成 & 適用
    │    ・直列キュー (patch_worker.py) で安全に逐次処理
    │    ・report_manager による結果トラッキング
    │
    └── Architecture Auditor (reviewer/tools.py)
         ・コードベースのレイヤー分離遵守状況を自動点検
         ・Hub / Gateway / Portal の責任境界違反を検出
         ・Discord #copilot へ監査レポートを配信

─────────────────────────────────────────────────────────────
【ALICE_Search 連携インターフェース】
Discord (#search channel / !search command)
    │
    ▼
ALICE_Search CLI (`python cli.py --query "..." --limit 5`)
    │
    ▼
Discord Embed (クリーンな引用レイアウトで過去要約・発話を表示)
```

---

## 3. 主要機能

1. **自動分類 (Memory Classifier)**:
   - 会話や添付文書から、保存すべき記憶タイプを自動判定。
2. **リレーション追跡 (Relation Management)**:
   - メモリ間の関係性（関連 `related`、更新・廃止 `supersedes`、矛盾 `conflicts`）を保持。
3. **Obsidian 自動同期 (Obsidian Auto-Sync)**:
   - システム起動時およびメモリ更新時に、自動的に Obsidian Vault（Markdown 形式）へ最新状態を同期。
4. **過去成果物の横断検索連携 (ALICE_Search Integration)**:
   - Discord の `#search` チャンネルへの投稿、または `!search <query>` コマンドにより、`ALICE_Search` を呼び出して過去の要約・発話・成果物をダイレクトに検索・引用表示。
5. **フルテキストメモリ検索 (Memory Search)**:
   - 蓄積された過去の判断・経緯・アイデアを即座にクエリ可能。カタカナ語の NFKC 正規化・中黒複合語抽出により検索精度を強化。
6. **夜間自律点検 & モーニングブリーフィング (Nightly Reviewer)**:
   - 毎晩 03:00 JST に対話ログ・システムログを自律点検し、長期記憶の自動補完を実施。毎朝 07:30 JST に Discord `#copilot` へモーニングブリーフィングを自動配信。
7. **Antigravity 自律パッチワーカー (Auto Patcher)**:
   - Antigravity CLI を活用した自律コードパッチ生成 & 直列適用機構。コードベースの自己修復を継続的に実行。
8. **自己診断チェックリスト (Self-Diagnosis)**:
   - 単体テストを含む自己診断プログラムにより、CoPilot 自身の健全性を定期検証・復旧。
9. **アーキテクチャ監査 (Architecture Auditor)**:
   - コードベースのレイヤー分離（Hub / Gateway / Portal）の遵守を自動点検し、違反を早期検出。

---

## 4. 責任境界

- **責務**:
  - ユーザーの対話・知識・判断の蓄積・検索・参照支援。
  - Antigravity SDK を活用したコードベースの自律維持・改善。
  - Google カレンダー・Tasks との連携によるスケジュール・タスク管理支援。
- **非責務**:
  - Core の Job 実行・キュー管理。
  - 音声文字起こし・音響前処理。
  - 検索エンジン（ALICE_Search）の内部実装。
