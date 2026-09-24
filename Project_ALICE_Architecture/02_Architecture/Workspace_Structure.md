# Workspace Structure & Lifecycle Specification

## 1. 概念定義

**Workspace** は、Project_ALICE における 1 つの処理要求（Job）に割り当てられる、完全に隔離されたファイルシステム上の作業領域です。

- **配置先**: `/data/runtime/workspaces/{job_id}/`
- **所有者**: `ALICE_Core` の `WorkspaceManager` が作成・破棄・クリーンアップを統括。
- **アクセス権**: 各モジュールは CLI 起動時に `--workspace /data/runtime/workspaces/{job_id}` を受け取り、自身に割り当てられたサブディレクトリのみを読み書きする。

---

## 2. ディレクトリ構造

```text
/data/runtime/workspaces/{job_id}/
├── job.json                # Job 共通メタデータ・ステータス管理
├── input/                  # 入力原本格納ディレクトリ
│   ├── meeting.m4a         # （処理中: 一時保存された音声バイナリ）
│   └── meeting.m4a.processed # （完了後: 0バイトのプレースホルダー）
├── transcript/             # [ALICE_Transcript 専用成果物領域]
│   ├── transcript.json     # 会話構造化正本（Source of Truth）
│   ├── transcript.txt      # 人間可読テキスト（Primary Artifact）
│   └── metadata.json       # 音声処理メトリクス
├── summary/                # [ALICE_Summary 専用成果物領域]
│   ├── analysis.json       # Stage 1: 会話分析・構造化データ
│   ├── draft_summary.md    # Stage 2: ドラフト要約
│   ├── summary.md          # Stage 3: 完成版要約 Markdown
│   ├── summary.txt         # Stage 3: 完成版テキスト（Primary Artifact）
│   ├── consistency_report.md# Stage 3: 原文照合・整合性監査レポート
│   └── metadata.json       # 要約処理メトリクス
├── minutes/                # [ALICE_Minutes 専用成果物領域]
│   ├── analysis.json       # Stage 1: 議事録構造化データ
│   ├── minutes.md          # Stage 2: 議事録 Markdown
│   ├── minutes.txt         # Stage 2: 完成版テキスト（Primary Artifact）
│   └── metadata.json       # 議事録処理メトリクス
└── logs/                   # Job 実行ログ格納領域
    ├── transcript.log      # Transcript 実行ログ
    ├── summary.log         # Summary 実行ログ
    └── minutes.log         # Minutes 実行ログ
```

---

## 3. Workspace ライフサイクル

```text
[生成] (PENDING)
  │  Core の MessageHandler が要求受付
  │  WorkspaceManager がディレクトリ作成
  │  入力ファイルを input/ へ保存し job.json を初期化
  ▼
[キューイング] (QUEUED)
  │  JobQueue にエンキュー
  ▼
[処理中] (PROCESSING)
  │  CoreWorker がポップして実行開始
  │  Step 1: ALICE_Transcript が input/ を読み transcript/ を出力
  │  Step 2: 後続モジュールが transcript/transcript.json を読み出力
  ▼
[完了検査] (VALIDATING)
  │  プロセス終了コード = 0 かつ Primary Artifact 存在チェック
  ▼
[配信 & 完了] (COMPLETED / FAILED)
  │  Publisher が最終成果物を配信
  │  job.json の status を COMPLETED に更新
  ▼
[クリーンアップ & 派生処理] (CLEANUP & INDEXING)
  │  ・input/ 配下の音声原本バイナリを削除し、<name>.processed プレースホルダーを生成
  │  ・ALICE_Search CLI (--index-job) により検索インデックスを安全に更新
```

---

## 4. モジュール入出力マトリクス

| モジュール | 入力元パス | 出力先パス | 必須入力成果物 | 主な出力成果物 |
| :--- | :--- | :--- | :--- | :--- |
| **ALICE_Transcript** | `<ws>/input/` | `<ws>/transcript/` | 音声ファイル (`.wav`, `.mp3`, `.m4a`) | `transcript.json`, `transcript.txt` |
| **ALICE_Summary** | `<ws>/transcript/` | `<ws>/summary/` | `transcript.json` | `summary.txt`, `summary.md`, `analysis.json` |
| **ALICE_Minutes** | `<ws>/transcript/` | `<ws>/minutes/` | `transcript.json` | `minutes.txt`, `minutes.md`, `analysis.json` |

---

## 5. ストレージ保全と音声原本クリーンアップ規約

音声バイナリファイル（数十MB〜数百MB）を無制限に Workspace 内に保持し続けると、ディスク容量の枯渇を招きます。

1. **Source of Truth（源泉データ）の移行**:
   - 音声認識および話者分離が完了し `transcript/transcript.json` が生成された時点で、以降の全分析・要約処理はテキストデータのみに依存します。
2. **自動クリーンアップの実行**:
   - Job が `COMPLETED` に達した直後、`WorkspaceManager` は `input/` 配下の音声原本を物理削除します。
3. **プレースホルダー（`.processed`）の生成**:
   - 削除の証跡および元ファイル名の記録として、0 バイトの `<original_filename>.processed`（例: `meeting.m4a.processed`）を配置します。
