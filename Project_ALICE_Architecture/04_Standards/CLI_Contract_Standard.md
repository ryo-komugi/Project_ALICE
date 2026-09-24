# Project_ALICE CLI Contract Standard (CLI実行契約規約)

> Version: v1.0.0  
> Status: Standard  

本規約は、`ALICE_Core` から各機能モジュール（Transcript, Summary, Minutes 等）を Subprocess 実行する際のインターフェース規約および終了判定基準を定めます。

---

## 1. 共通引数規約

すべてのモジュール CLI（`cli.py`）は、以下の必須引数をサポートしなければならない。

```bash
python cli.py --workspace <workspace_directory_path>
```

| 引数名 | 必須/任意 | 説明 |
| :--- | :--- | :--- |
| `--workspace` | **必須** | 対象 Job の Workspace 絶対パス（例: `/data/runtime/workspaces/{job_id}`） |
| `--model` | 任意 | 使用する LLM モデル名の明示指定（Summary, Minutes） |
| `--log-level` | 任意 | ログ出力レベル（`DEBUG`, `INFO`, `WARNING`, `ERROR`） |

---

## 2. 終了コード (Exit Code) 規約

モジュールプロセスの終了コードは以下を厳守しなければならない。

| 終了コード | 状態 | 動作 |
| :--- | :--- | :--- |
| `0` | **正常完了 (Success)** | 契約された成果物ファイルが所定位置に生成されていること。 |
| `1` 以上 | **異常終了 (Failure)** | エラー詳細を標準エラー出力（stderr）および Workspace ログへ出力して終了。 |

---

## 3. 成功判定規約 (Completion Validation)

`ALICE_Core` の `CoreWorker` は、以下の **2 つの条件が同時に満たされた場合のみ**、モジュールの実行を成功と判定する。

1. サブプロセスの終了コード（`returncode`）が `0` であること。
2. 当該モジュールの **Primary Artifact**（例: `<ws>/summary/summary.txt`）がファイルシステム上に存在し、ファイルサイズが 0 より大きいこと。

いずれか一方でも満たされない場合、Job は `FAILED` とみなされ、後続ステップの実行は中断される。
