# Project_ALICE Directory Standard (ディレクトリ配置規約)

> Version: v1.1.0  
> Status: Standard  

本規約は、Project_ALICE システムにおけるランタイム領域（`/data/runtime`）および各モジュール領域のディレクトリ構造・命名規則を定義します。

---

## 1. ランタイム領域 (`/data/runtime`)

すべての動的データ（ジョブ、ワークスペース、ログ、公開ファイル、セッションDB、検索インデックス）は `/data/runtime` 配下に集約し、ソースコードリポジトリ内には一時ファイルやログを書き込んではならない。

```text
/data/runtime/
├── copilot/                    # [ALICE_CoPilot 専用領域]
│   └── database/               # conversations.db
├── core/                       # [ALICE_Core 専用領域]
│   ├── inbox/                  # 外部クライアント受信一時ファイル
│   └── share/                  # 公開配信・静的ファイル領域 (/share)
├── logs/                       # 【システム全体共通ログ領域】
│   ├── alice.log               # ALICE_Core 運用ログ
│   ├── transcript.log          # ALICE_Transcript スタンドアロンログ
│   └── archive/                # ローテーション過去ログ (*.log.YYYY-MM-DD)
├── search/                     # [ALICE_Search 専用領域]
│   └── alice_index.db          # SQLite + FTS5 trigram 派生検索インデックス
└── workspaces/                 # 【Job 共通 Workspace 領域】
    └── {job_id}/               # 1 Job ごとの隔離ディレクトリ
        ├── job.json            # Job 状態・メタデータ
        ├── input/              # 入力原本（処理完了後に削除・プレースホルダー化）
        ├── transcript/         # Transcript 成果物
        ├── summary/            # Summary 成果物
        ├── minutes/            # Minutes 成果物
        └── logs/               # Job 別実行ログ
```

---

## 2. メモリ・ナレッジ領域 (`/data/memory`)

`ALICE_CoPilot` が管理するメモリおよび Obsidian バウルト領域。

```text
/data/memory/
├── copilot/                    # メモリ原本領域
│   ├── shortterm/              # 未確定短期メモリ
│   └── longterm/               # 確定長期メモリ (Context, Decisions, Projects等)
└── obsidian/                   # Obsidian バウルト同期領域
```

---

## 3. 命名規則 (Naming Conventions)

1. **Job ID**: `job_{YYYYMMDD}_{HHMMSS}_{random4}` または日付時刻ベースのユニーク文字列。
2. **モジュール成果物ディレクトリ**: モジュール名の短縮小文字（`transcript`, `summary`, `minutes`）。
3. **Primary Artifact**:
   - 文字起こし: `transcript.txt`
   - 要約: `summary.txt`
   - 議事録: `minutes.txt`
