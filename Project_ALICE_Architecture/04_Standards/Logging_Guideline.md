# Project_ALICE Logging Guideline (ロギング規約)

> Version: v2.0.0  
> Status: Standard  

---

## 1. 目的

ログは「システムの稼働監視」および「Job 処理の時系列追跡と障害解析」を目的とします。
デバッグ用の一時的なプリント出力ではなく、後から処理の流れを完全に再現できるログ出力を徹底します。

---

## 2. ログの二重化構造

Project_ALICE では、以下の 2 系統でログを出力・保持します。

### ① システム全体ログ (`/data/runtime/logs/`)
- `alice.log`: `ALICE_Core` の全体運用ログ（FastAPI アクセス、JobQueue 状況、Worker 全体動作）。
- `transcript.log`: `ALICE_Transcript` のスタンドアロン実行ログ。
- 日次ローテーションを実施し、過去ログは `archive/` へ移動。

### ② Job 個別ログ (`/data/runtime/workspaces/{job_id}/logs/`)
- `transcript.log`: 当該 Job における Whisper / Pyannote / Alignment の実行詳細。
- `summary.log`: 当該 Job における LLM 推論・プロンプトトークン数・ステージ推移。
- `minutes.log`: 当該 Job における議事録抽出・文章化ログ。

これによって、特定の Job で障害が発生した場合、該当 Workspace の `logs/` を確認するだけで原因究明が完結します。

---

## 3. フォーマットとログレベル

### 基本フォーマット
```text
YYYY-MM-DD HH:MM:SS,ms [LEVEL] [Module/Component] Message
```

### ログレベルの基準
| レベル | 用途 | 出力例 |
| :--- | :--- | :--- |
| `INFO` | 通常の処理開始・終了、状態遷移、重要ファイルの保存 | `[CoreWorker] Starting job: job_20260905_120000 with workflow: ['transcript', 'summary']` |
| `WARNING`| 想定内だが注意を要する事象（タイムアウト後の自動リトライ、未知の話者ラベル補間等） | `[Summary] Ollama API timeout. Retrying in 2.0s (attempt 1/3)...` |
| `ERROR` | 処理の失敗、Subprocess 非ゼロ終了、成果物未生成 | `[CoreWorker] Step transcript failed with exit code 1` |
| `EXCEPTION` | スタックトレース付き予期せぬ例外（`logger.exception()` を使用） | `[MessageHandler] Unexpected exception during event dispatch` |

---

## 4. 秘匿情報（マスキング）指針

以下の情報はログへ絶対に出力してはならない。
- LINE Channel Access Token, Channel Secret
- Discord Bot Token, Hugging Face Token (Pyannote)
- 招待コード、個人を特定可能な認証情報
