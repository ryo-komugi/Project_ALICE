# ALICE_CoPilot

## Version & Status

| Item   | Value        |
|--------|--------------|
| Version | v0.1.0      |
| Status | Development |
| Python | 3.10        |
| Platform | Ubuntu 26.04 LTS |
| License | MIT         |

## Overview

ALICE_CoPilot は、Project ALICE 用のオフロードメモリ構築・管理エンジンです。

会話や情報から **短期記憶** と **長期記憶** を自動分類し、エンティティ間の **リレーション** を構築します。構築したメモリは **Obsidian** と同期され、エージェントが知識を検索・参照できる環境を提供します。

## Core Features

- **自動分類** – `memory_classifier` が入力を记忆タイプ（context, project, decision, knowledge, idea）に振り分ける

## Setup

### 必要な環境変数

`.env`ファイルに以下の変数を定義します。

| 変数 | 必須 | デフォルト値 | 説明 |
|------|------|--------------|------|
| `DISCORD_BOT_TOKEN` | Yes | - | Discordボット認証トークン |
| `ALICE_COPILOT_MEMORY_ROOT` | No | `/data/memory/copilot` | メモリファイルのルートディレクトリ |
| `OBSIDIAN_ROOT` | No | `/data/memory/obsidian` | Obsidianのバウルトルート |

### .env の例

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
ALICE_COPILOT_MEMORY_ROOT=/data/memory/copilot
OBSIDIAN_ROOT=/data/memory/obsidian
```

### Ollamaの実行確認

```bash
curl http://localhost:11434/api/generate -X POST -H "Content-Type: application/json" -d '{"model":"gemma4:12b","prompt":"test"}'
```

### インストール前提

- Python 3.10+
- Ollamaサービス（ローカル実行）
- Discord Bot Token（botが動作する場合のみ）

## Core Features

- **自動分類** – `memory_classifier` が入力を記憶タイプ（context, project, decision, knowledge, idea）に振り分ける
- **重複検出** – 既存メモリと比較し、同一内容を自動マージ
- **リレーション管理** – `related`, `supersedes`, `conflicts` の 3 種類の関係を保持
- **フルテキスト検索** – `memory_search` でキーワード検索が可能
- **Obsidian エクスポート / 同期** – `obsidian_export` でソースメモリを Obsidian バウルトに反映
- **バッチ取り込み** – JSON ファイルから一括でメモリを作成
- **短期記憶** – `short_term` が SQLite でメッセージ履歴を管理
- **統合・圧縮** – `memory_consolidator` が重複メモリをまとめる
- **主語関係推定** – `memory_subject` が自然言語を解析
- **記憶ルーター** – `memory_router` が質問に記憶検索が必要か判定
- **記憶抽出** – `memory_extractor` が会話から記憶候補を抽出
- **CLI / Python API** – 両方から操作可能
- **メンテナンス** – 孤立リレーションの検出・削除、Markdown からリレーションへの移行

## Architecture

```
/data/memory/copilot/
├── shortterm/        # 短期記憶（未確定メモリ）
├── longterm/         # 確定済み長期記憶
│   ├── Context/
│   ├── Projects/
│   ├── Decisions/
│   ├── Knowledge/
│   ├── Ideas/
│   └── Archive/      # アーカイブ済みメモリ
└── Relations/        # リレーション JSON
```

主要モジュール:

| モジュール | 役割 |
|------------|------|
| `memory_classifier.py` | 入力テキストを分析し、記憶タイプを判定 |
| `memory_manager.py` | 記憶の作成・重複チェック・リレーション評価を統合 |
| `memory_search.py` | キーワード検索機能 |
| `memory_relation.py` | リレーションの分析・作成・再評価 |
| `memory_consolidator.py` | 記憶の統合・圧縮処理 |

| `obsidian_export.py` | Obsidian バウルトへのエクスポートと同期 |
| `memory_qa.py` | QA 機能（問い合わせ回答） |
| `memory_router.py` | 記憶検索の必要性を判定（`should_use_memory`） |
| `memory_extractor.py` | 会話から記憶候補を抽出（`extract_memories`） |
| `memory_context.py` | QA 用コンテキスト構築（`build_memory_context`, `format_memory_context`） |
| `short_term.py` | 短期メモリ（SQLite） |
| `memory_cleanup.py` | 孤立リレーション検出、レポート生成 |
| `long_term.py` | 記憶・リレーション永続化（`create_memory`, `create_relation`, `find_memory_by_id`） |
| `main.py` | Discord ボットエントリポイント |
| `cli.py` | コマンドラインインターフェース |
| `config.py` | 共通設定定数 |

## Configuration

設定は `config.py` で定義されています。環境変数で上書き可能です。

| 定数 | デフォルト値 | 説明 |
|------|--------------|------|
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | LLM サーバ URL |
| `OLLAMA_MODEL` | `gemma4:12b` | 使用モデル名 |
| `OLLAMA_CONTEXT` | `32768` | コンテキストウィンドウサイズ |
| `ALICE_COPILOT_MEMORY_ROOT` | `/data/memory/copilot` | 記憶ルートディレクトリ |
| `MEMORY_ROOT` | `ALICE_COPILOT_MEMORY_ROOT` | 記憶ルートディレクトリ (alias) |
| `ARCHIVE_ROOT` | `MEMORY_ROOT / "Archive"` | アーカイブディレクトリ |
| `RELATIONS_ROOT` | `MEMORY_ROOT / "Relations"` | リレーションファイルディレクトリ |
| `DB_PATH` | `/data/runtime/copilot/database/conversations.db` | 会話データベースパス |
| `OBSIDIAN_ROOT` | `/data/memory/obsidian` | Obsidian バウルトのルート |

## Entrypoint

### Discordボットとして実行

```bash
python main.py
```

**動作要件:**
- `.env` に `DISCORD_BOT_TOKEN` を設定
- DiscordサーバーにBot招待
- 「copilot」という名前のチャンネル内のメッセージのみに反応
- ユーザーからのメンション（`<@USERID>`、`<@!USERID>`）は自動除去

**ユーザー発言例:**
- `覚えておいて ニュースを覚えさせておいて` → 記憶保存
- `記憶：先月の決定内容は何ですか？` → QA実行
- 通常の会話 → 記憶検索が必要な場合のみ回答

### Python APIとして実行

すべてのモジュールは `import` 可能です。

```python
from memory.memory_manager import process_memory
from memory.memory_qa import ask_memory
from memory.memory_search import search_memories
from memory.memory_router import should_use_memory
from memory.memory_context import build_memory_context, format_memory_context
from memory.long_term import create_memory, create_relation, load_relations
from memory.short_term import initialize_database, save_message, get_recent_messages
from memory.cli import main as cli_main
```

## Data Models

### メモリファイルのフォーマット（Markdown）

**構造:**
```markdown
# {タイトル}

{コンテンツ}
```

**ID形式:**
`{YYYYMMDD_HHMMSS_microseconds}_{ランダム文字数}_{サニタイズされたタイトル}.md`

**例:**
```
/data/memory/copilot/decision/20260813_230926_749497_9af9_supersedesテストの実施方法.md
```

**ディレクトリ構造:**
```
{MEMORY_ROOT}/
├── Context/
│   └── {timestamp}_{suffix}_{title}.md
├── Projects/
├── Decisions/
├── Knowledge/
├── Ideas/
├── Conversations/
└── Archive/
    └── {timestamp}_{suffix}_{title}.md
```

### リレーションファイルのフォーマット（JSON）

**構造:**
```json
{
  "id": "YYYYMMDD_HHMMSS_microseconds_randomsuffix",
  "from": "{memory_id}",
  "relation": "{related|supersedes|conflicts}",
  "to": "{memory_id}",
  "created_at": "2026-08-13T23:09:26.123456+09:00"
}
```

**例:**
```json
{
  "id": "20260813_230926_749497_9af9",
  "from": "20260813_220000_123456_ABCD",
  "relation": "supersedes",
  "to": "20260813_230926_749497_9af9_supersedesテストの実施方法",
  "created_at": "2026-08-13T23:09:26.123456+09:00"
}
```

### データベーススキーマ（SQLite）

**テーブル: messages**
| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER (主キー, 自動採番) | メッセージの並び順ID |
| timestamp | TEXT | ISOフォーマットの日時 |
| channel_id | TEXT | DiscordチャンネルID |
| user_id | TEXT | DiscordユーザーID（botのメッセージの場合はNULL） |
| role | TEXT | 'user' または 'assistant' |
| content | TEXT | メッセージ内容（日本語推奨） |

### ファイル命名規則

**メモリファイル:**
- パターン：`{タイムスタンプ}_{ランダムサフィックス}_{サニタイズされたタイトル}.md`
- タイムスタンプフォーマット：`YYYYMMDD_HHMMSS_MICROSECONDS`
- ランダムサフィックス：4文字の16進数

**リレーションファイル:**
- パターン：`{タイムスタンプ}.json`
- コンテンツ：`{"id": "...", "from": "...", "relation": "...", "to": "...", "created_at": "..."}`

## CLI Usage

CLI は `python -m memory.cli` で実行します。

### 記憶の追加

```bash
python -m memory.cli add --type project --title "MyProject" --content "プロジェクトの概要" \
  --related ABC123 --supersedes DEF456 --conflicts GHI789 --json
```

- `--related`, `--supersedes`, `--conflicts` でリレーションを指定できます。
- `--json` で JSON 出力が可能です。

### バッチ取り込み

```bash
python -m memory.cli ingest --file batch.json
```

### 検索

```bash
python -m memory.cli search "プロジェクト" --limit 10
```

### Obsidian エクスポート

```bash
python -m memory.cli export-obsidian
```

### Obsidian 同期（ドライラン付き）

```bash
python -m memory.cli sync-obsidian --dry-run
python -m memory.cli sync-obsidian --clean
```

### リレーションの移行

```bash
python -m memory.cli migrate-related --dry-run
```

### メンテナンス

```bash
python -m memory.cli cleanup --check-orphans
python -m memory.cli cleanup --clean-orphans -y
```

### CLIコマンドの完全なオプション

#### 記憶の追加（add）

```bash
python -m memory.cli add \
  --type {context|project|decision|knowledge|idea} \
  --title "<タイトル>" \
  --content "<コンテンツ>" \
  [--related "<メモリID>" ...] \
  [--supersedes "<メモリID>" ...] \
  [--conflicts "<メモリID>" ...] \
  [--json]
```

- `--type`: メモリタイプ（context, project, decision, knowledge, idea）
- `--title`, `--content`: メモリのタイトルと本文
- `--related`, `--supersedes`, `--conflicts`: リレーションを指定
- `--json`: JSON形式で結果を出力
- すべてのリレーションターゲットIDが存在している必要があります。

#### バッチ取り込み（ingest）

```bash
python -m memory.cli ingest --file batch.json [--skip-validation] [--yes]
```

- `--file`: JSONファイルのパス
- JSONフォーマット：
  ```json
  [
    {"type": "project", "title": "タイトル", "content": "内容", "related": ["ID1"], ...},
    ...
  ]
  ```
- `--yes`: 確認をスキップします。

#### 検索（search）

```bash
python -m memory.cli search "<クエリ>" [--limit <数>] [--json]
```

- `--limit`: 返す結果の最大数（デフォルト: 10）
- `--json`: JSON形式で結果を出力

#### リレーションの移行（migrate-related）

```bash
python -m memory.cli migrate-related [--dry-run] [--force] [--skip-markdown]
```

- `--dry-run`: 実際に書き込みません
- `--force`: MarkdownからJSONへの変換を強制します
- `--skip-markdown`: 既存の`## Related [[...]]`リンクをスキップします

#### Obsidian エクスポート（export-obsidian）

```bash
python -m memory.cli export-obsidian [--dry-run]
```

- `--dry-run`: 実際に書き込みません
- ソースメモリからObsidianバウルトへの完全なエクスポートを行います

#### Obsidian 同期（sync-obsidian）

```bash
python -m memory.cli sync-obsidian [--dry-run] [--clean] [--force]
```

- `--dry-run`: 同期内容を表示のみ（書き込みなし）
- `--clean`: 健全でないファイルを削除します
- `--force`: すべてのファイルを強制的に上書きします

#### メンテナンス（cleanup）

```bash
python -m memory.cli cleanup --check-orphans [--yes]
python -m memory.cli cleanup --clean-orphans [-y|--yes]
python -m memory.cli cleanup --archive [--dry-run] [--yes]
```

- `--check-orphans`: 孤立リレーションを検出
- `--clean-orphans`: 孤立リレーションを削除（-y または --yes で確認）
- `--archive`: 重複メモリをアーカイブ（dry-run 可能）

## Python API

```python
from memory.memory_manager import process_memory
from memory.memory_search import search_memories
from memory.obsidian_export import export_memory, sync_obsidian
from memory.long_term import create_memory, create_relation, find_memory_by_id

# 記憶の作成
result = process_memory("新しい情報をここに記述します。")

# 検索
results = search_memories(query="プロジェクト", limit=10)

# Obsidian にエクスポート
export_memory(Path("/data/memory/copilot/longterm/Projects/MyProject.md"))

# 同期（dry-run）
sync_obsidian(dry_run=True)
```

## Obsidian Integration

`obsidian_export.py` はソース記憶を常に優先し、Obsidian バウルトと同期します。

- **エクスポート** – `export_memory` / `export_all_memories` が Obsidian に Markdown を書き出す
- **同期** – `sync_obsidian` で差分を検出し、欠落ファイルを検出・削除可能
- **リンク形式** – リレーションは `[[MemoryID]]` の Obsidian ウィキリンクで出力される
- **管理対象ディレクトリ** – `Context`, `Projects`, `Decisions`, `Knowledge`, `Ideas`, `Conversations`, `Archive` のみが同期対象

## Maintenance

- **孤立リレーション検出** – `--check-orphans` で使用されていないリレーションを一覧表示
- **孤立リレーション削除** – `--clean-orphans` で安全に削除
- **Markdown 移行** – `migrate-related` で既存の `## Related [[...]]` リンクを Relation JSON に移行
- **レポート生成** – `memory_cleanup.generate_report` で全メモリの重複分析
- **正準記憶選択** – `memory_cleanup.select_canonical_memory` で重複グループの代表を選択

## Memory Lifecycle

### メモリの作成からアーカイブへの移行フロー

```
会話 → 短期記憶（SQLite） → 記憶抽出（LLM） → 分類判定（LLM） → 重複チェック → 長期記憶作成 → リレーション評価 → Supersededチェーン更新 → アーカイブ
```

### Supersededチェーンの仕組み

メモリは不変設計で、新しい情報が古い情報を置き換える場合、`supersedes`リレーションでチェーンを維持します。

**チェーンの例:**
```
記憶A --supersedes--> 記憶B --supersedes--> 記憶C
   （古い）          （中間）          （現在）
```

**動作:**
- 現在参照すべきメモリは最も新しい（記憶C）
- 記憶Bは履歴として保持
- 記憶Aは過去の履歴として保持
- `find_superseding_memories(memory_id)` で置き換えた記憶を検索
- `find_superseded_memories(memory_id)` で置き換えられた記憶を検索

### メモリのカテゴリ

| カテゴリ | ディレクトリ名 | 用途 |
|----------|----------------|------|
| context | `Context` | ユーザーとの関係性、継続的なコンテキスト |
| project | `Projects` | プロジェクトの状態、進捗、仕様 |
| decision | `Decisions` | 正式に決定された事項 |
| knowledge | `Knowledge` | 事実、仕様、概念 |
| idea | `Ideas` | まだ決定されていない構想やアイデア |
| archive | `Archive` | アーカイブ済みメモリ（superseded等） |
| conversation | `Conversations` | 会話履歴（インポートのみ） |

## Module Usage Patterns

### 推奨なインポート順序

**コアモジュール:**
```python
from memory.memory_manager import process_memory
from memory.memory_search import search_memories
from memory.memory_context import build_memory_context, format_memory_context
```

**QA機能:**
```python
from memory.memory_qa import ask_memory
from memory.memory_router import should_use_memory
```

**長期記憶操作:**
```python
from memory.long_term import (
    create_memory,
    create_relation,
    load_relations,
    find_memory_by_id,
    find_superseded_memories,
    find_superseding_memories,
    find_conflicting_memories,
)
```

**短期記憶管理:**
```python
from memory.short_term import (
    initialize_database,
    save_message,
    get_recent_messages,
)
```

**ツールモジュール:**
```python
from memory.memory_subject import extract_memory_subject, filter_memories_by_subject
from memory.obsidian_export import export_memory, export_all_memories, sync_obsidian
from memory.memory_cleanup import find_orphan_relations, execute_clean_orphans
```

### モジュール間の連携パターン

**メモリ処理ワークフロー:**
```python
from memory.memory_manager import process_memory
from memory.memory_context import build_memory_context, format_memory_context
from memory.memory_qa import ask_memory

# 1. メモリを作成
result = process_memory("新しい情報")

# 2. QAコンテキストを構築
if result["saved"]:
    context = build_memory_context(
        [result["memory_id"]],
        query="問い合わせ内容"
    )
    memory_text = format_memory_context(context)

    # 3. QAを実行
    answer = ask_memory("問い合わせ内容")
```

**リレーション分析パターン:**
```python
from memory.memory_relation import (
    find_memory_candidates,
    analyze_memory_relations,
    reevaluate_relations_for_memory
)
from memory.long_term import create_relation

# 1. 候補の検索
candidates = find_memory_candidates(
    title="タイトル",
    content="コンテンツ"
)

# 2. リレーション分析
relations = analyze_memory_relations(
    title="タイトル",
    content="コンテンツ",
    candidates=candidates
)

# 3. リレーションの作成
for relation in relations:
    create_relation(
        from_memory_id=新メモリID,
        relation=relation["relation"],
        to_memory_id=relation["memory_id"]
    )
```

### Supersededチェーンを用いた現在のメモリ取得

```python
from memory.long_term import (
    find_memory_by_id,
    find_superseding_memories,
    find_conflicted_memories
)

# 記憶IDを取得
memory_id = "20260813_220000_123456_ABCD"

# 直接取得
current_memory = find_memory_by_id(memory_id)

# 置き換えたメモリを検索（古い記憶）
superseded_by = find_superseding_memories(memory_id)

# 置き換えられたメモリを検索（新しい記憶）
superseded = find_superseded_memories(memory_id)

# 矛盾しているメモリを検索
conflicts = find_conflicted_memories(memory_id)
```

## Roadmap

### v0.1

- コアメモリ機能・CLI の実装

### v0.2

- QA 機能の強化
- より高度な自動統合
- テストカバレッジの向上

## Tests

### テストの構造

```
tests/
├── conftest.py                 # テストフィクスチャー
├── test_memory_manager.py      # Managerワークフローテスト
├── test_memory_search.py       # 検索機能テスト
├── test_memory_qa.py           # QA機能テスト
├── test_memory_subject.py      # Subject抽出テスト
├── test_memory_context.py      # Context構築テスト
├── test_memory_conversation.py # 会話処理テスト
├── test_memory_consolidator.py # 統合テスト
├── test_memory_lifecycle.py    # ライフサイクル管理テスト
├── test_memory_obsidian_export.py # Obsidian同期テスト
├── test_memory_relation.py     # リレーション分析テスト
├── test_memory_cli.py          # CLIインターフェーステスト
└── test_memory_candidates.py   # 候補検索テスト

tests/integration/
├── test_memory_classification_ollama.py  # 実Ollama分類
├── test_memory_router_ollama.py         # Router精度
├── test_memory_relation_ollama.py        # リレーション分析
└── test_memory_lifecycle_ollama.py       # 完全ライフサイクル
```

### テストの実行方法

**全テストの実行:**
```bash
pytest tests/ -v
```

**ユニットテストのみ:**
```bash
pytest tests/test_memory_*.py -v
```

**統合テストのみ:**
```bash
pytest tests/integration/ -m integration -v
```

**カバレッジの確認:**
```bash
pytest tests/ --cov=memory --cov-report=html
```

**前提条件:**
- pytest がインストールされていること
- Integrationテストを実行する場合、Ollamaサービスがローカルで稼働していること

### テストの動作

**ユニットテスト:**
- Ollama APIやSQLiteをモック
- リモートサービスに依存しない

**統合テスト:**
- `@pytest.mark.integration` マーカーを使用
- 実際のOllama APIを呼び出し
- メモリの完全なライフサイクルを検証

## Dependencies and Requirements

### Pythonバージョン

- Python 3.10+
- 型ヒントが使用されています
- Pythonの現代的な機能（リスト内包、型ユニオン等）を利用

### 必要なパッケージ（インポートより推測）

- **requests**: Ollama APIへのHTTPリクエスト
- **discord.py**: Discordボット機能
- **python-dotenv**: `.env`からの環境変数読み込み
- **pytest**: テストフレームワーク

### 外部サービス

**Ollama**
- URL: `http://localhost:11434/api/chat`
- モデル: `gemma4:12b`
- コンテキストウィンドウ: `32768` トークン
- **使用箇所**: 分類、抽出、ルーティング、QA、リレーション分析、重複検出

**Ollamaの動作確認:**
```bash
curl http://localhost:11434/api/generate -X POST -H "Content-Type: application/json" -d '{"model":"gemma4:12b","prompt":"test","stream":false}'
```

### Discord統合

- **Discord.py**: ボット機能のライブラリ
- **Discord Bot Token**: 環境変数 `DISCORD_BOT_TOKEN` で指定
- チャンネル名: 「copilot」名前のチャンネルのみに反応

### ファイルシステム要件

- **SQLite**: 短期記憶（Python標準ライブラリ）
- **Pathlib**: ファイルパス操作（Python標準ライブラリ）
- POSIX互換ファイルシステム（Linux推奨）
- UTF-8エンコーディングの強制使用

### 依存関係の管理

パッケージを追加する場合、`pyproject.toml`を更新してください。

### アーキテクチャの前提

1. **不変設計**: 記憶やリレーションは作成後は決して変更されません
2. **アトミック性**: ファイル書き込みは一時ファイル＋renameで行われます
3. **決定論性**: クリティカルな決定（分類、リレーション分析）にはLLMを使用せず、ルールで判断されます
4. **分離された懸念**: 短期記憶 vs 長期記憶 vs コンテキスト vs QA vs CLI

**エラー処理とフォールバック:**
- メモリ操作が失敗しても会話が止まりません
- Ollamaが使用できない場合は、適切なフォールバック動作が実装されています
- 特定の関数では最小限のエラーハンドリングのみで、グレースフルデグレードが行われます

## License

MIT License
