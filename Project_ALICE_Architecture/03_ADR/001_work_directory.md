# ADR-001 Workspace Driven CLI & 1 Job = 1 Workspace の採択

## ステータス
採用 (Accepted)

## 背景
初期の構想では、モジュール間で共有ストレージ（OneDrive 等）を利用するか、あるいは Python のインプロセス import によるモジュール結合が検討されていた。

しかし以下の重大な課題が判明した：
1. **依存環境の衝突 (Dependency Hell)**:
   - `ALICE_Transcript` は PyTorch、CUDA、faster-whisper、pyannote.audio など特定のバイナリや古い依存を必要とする。
   - `ALICE_Summary` や `ALICE_Minutes` は Ollama API クライアント、新しい Pydantic、別バージョンのライブラリを好む。
   - これらを単一の Python 環境に同居させると依存解決が困難になり、VRAM 枯渇やプロセスクラッシュ時の巻き添えが発生する。
2. **並行処理とデータの競合**:
   - 複数の Job を処理する際、一時ファイルや共有ディレクトリの書き込み衝突（Race Condition）が発生する。

## 決定
1. **1 Job = 1 Workspace 原則の確立**:
   - すべての処理要求ごとに `/data/runtime/workspaces/{job_id}/` を一意に生成し、入力原本・モジュール別成果物・実行ログをそこに隔離する。
2. **Workspace Driven CLI 連携方式の採択**:
   - モジュール間は Python import を行わず、CoreWorker から Subprocess として `python cli.py --workspace <path>` を呼び出す。
   - 各モジュールはそれぞれ専用の Python 仮想環境（`whisper_env`, `core_env` 等）で実行する。

## 影響
- **メリット**:
  - モジュール間の完全な疎結合化（独立したデプロイ・テスト・リファクタリングが可能）。
  - Job ごとのトレーサビリティとログの完全な隔離。
  - プロセス終了時に OS レベルでメモリや VRAM が確実に解放される。
- **デメリット**:
  - プロセス起動オーバーヘッド（1秒未満）が存在するが、音声処理や LLM 推論時間に比べれば無視できるレベル。
