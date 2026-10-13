# Project_ALICE Directory Standard (ディレクトリ配置規約)

> Version: v1.1.0  
> Status: Standard  

本規約は、Project_ALICE システムにおけるプロジェクト別ランタイム領域（`{PROJECT_ROOT}/data/runtime`）、共有ランタイム領域（`/data/runtime`）、および各モジュール領域のディレクトリ構造・命名規則を定義します。

---

## 1. プロジェクト別ランタイム領域 (`{PROJECT_ROOT}/data/runtime`)

Job Workspace と ALICE_Core の運用ログは Project_ALICE ルート配下に保存し、ユーザーごとのプロジェクトフォルダで分離します。
基準ディレクトリは `ALICE_DATA_DIR` で設定します（既定値: `{PROJECT_ROOT}/data`）。相対パスは `PROJECT_ROOT` から解決し、Workspace は `<ALICE_DATA_DIR>/runtime/workspaces/`、運用ログは `<ALICE_DATA_DIR>/runtime/logs/` に保存します。

```text
{PROJECT_ROOT}/data/runtime/
├── logs/                       # ALICE_Core / CoPilot 運用ログ
│   ├── alice.log
│   ├── copilot.log
│   └── archive/
└── workspaces/                 # Job Workspace
    └── {job_id}/
```

## 2. 共有ランタイム領域 (`/data/runtime`)

次の既存共有データは `/data/runtime` 配下に維持します。

```text
/data/runtime/
├── copilot/                    # [ALICE_CoPilot 専用領域]
│   └── database/               # conversations.db
├── core/                       # [ALICE_Core 専用領域]
│   ├── inbox/                  # 外部クライアント受信一時ファイル
│   └── share/                  # 公開配信・静的ファイル領域 (/share)
├── search/                     # [ALICE_Search 専用領域]
│   └── alice_index.db          # SQLite + FTS5 trigram 派生検索インデックス
```

---

## 3. メモリ・ナレッジ領域 (`/data/memory`)

`ALICE_CoPilot` が管理するメモリおよび Obsidian バウルト領域。

```text
/data/memory/
├── copilot/                    # メモリ原本領域
│   ├── shortterm/              # 未確定短期メモリ
│   └── longterm/               # 確定長期メモリ (Context, Decisions, Projects等)
└── obsidian/                   # Obsidian バウルト同期領域
```

---

## 4. 命名規則 (Naming Conventions)

1. **Job ID**: `job_{YYYYMMDD}_{HHMMSS}_{random4}` または日付時刻ベースのユニーク文字列。
2. **モジュール成果物ディレクトリ**: モジュール名の短縮小文字（`transcript`, `summary`, `minutes`）。
3. **Primary Artifact**:
   - 文字起こし: `transcript.txt`
   - 要約: `summary.txt`
   - 議事録: `minutes.txt`
