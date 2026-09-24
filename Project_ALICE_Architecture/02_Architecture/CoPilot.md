# ALICE_CoPilot Architecture

## 1. 概要

`ALICE_CoPilot` は、Project_ALICE におけるオフロードメモリ構築・ナレッジ管理・対話支援モジュールです。

ユーザーとの日常対話（Discord 等）や各種テキスト情報・添付ファイル（Markdown 等）から、自動的に**「短期記憶」**と**「長期記憶」**を分類・抽出し、エンティティ間のリレーション（`related`, `supersedes`, `conflicts`）を構築します。

構築されたメモリは起動時および変更時に **Obsidian** のバウルトと自動同期され、AI エージェントやユーザーが文脈や決定履歴を即座に参照できる環境を提供します。また、**`ALICE_Search`** と連携し、過去の音声処理成果物（要約・文字起こし）を Discord 上から即座に検索・引用できるインターフェースを提供します。

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
   - 蓄積された過去の判断・経緯・アイデアを即座にクエリ可能。
