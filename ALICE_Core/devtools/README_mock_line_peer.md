# ローカル LINE 対向モック

LINE Messaging API と webhook クライアントの最小モックです。実 LINE の認証情報や外部通信なしで Core に署名付きイベントを送り、ファイル受信からジョブワークスペース作成まで確認できます。音声処理モジュール自体は実環境の設定で動くため、処理を最後まで実行する場合は通常のモデル環境が必要です。

## 1. Core の環境設定

`ALICE_Core/.env` に、既存の必須設定に加えてローカル API URL を設定します。`CHANNEL_SECRET` は後のコマンドでも同じ値を使います。

```dotenv
LINE_API_BASE_URL=http://127.0.0.1:8010
LINE_DATA_API_BASE_URL=http://127.0.0.1:8010
PUBLIC_URL=http://127.0.0.1:8000
```

Core の `CHANNEL_ACCESS_TOKEN` はモックでは検証しません。`PROJECT_ROOT` を指定しない場合、Workspace は Project_ALICE ルートの `data/runtime/workspaces/`、Core ログは `data/runtime/logs/` に作成されます。

## 2. 起動

ターミナル 1 で対向 API を起動します。

```bash
python3 ALICE_Core/devtools/mock_line_peer.py serve
```

ターミナル 2 で Core を起動します。

```bash
cd ALICE_Core
../myenv/core_env/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

## 3. イベント送信

ターミナル 3 から、Core と同じ `CHANNEL_SECRET` を指定して順番に送信します。

```bash
python3 ALICE_Core/devtools/mock_line_peer.py --secret 'ここにCHANNEL_SECRET' follow
python3 ALICE_Core/devtools/mock_line_peer.py --secret 'ここにCHANNEL_SECRET' text 'ここにINVITE_CODE'
python3 ALICE_Core/devtools/mock_line_peer.py --secret 'ここにCHANNEL_SECRET' text '文字起こし'
python3 ALICE_Core/devtools/mock_line_peer.py --secret 'ここにCHANNEL_SECRET' file '/path/to/sample.m4a'
```

`--user` は全コマンドで同じ値にしてください（既定値は `U_LOCAL_MOCK_USER`）。別ユーザーを試す場合は別の値を指定します。ファイル送信後は、`<PROJECT_ROOT>/data/runtime/workspaces/` に `job_*` ディレクトリができたことを確認します。

Core の受信確認だけなら `/health` を開けます。モック API は受信した返信・Push・リッチメニュー要求をターミナルに表示し、登録済みのアップロードデータを Core に返します。
