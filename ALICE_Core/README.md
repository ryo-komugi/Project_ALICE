# ALICE_Core

> Project_ALICE の中核オーケストレーション & 外部インターフェース基盤

---

## 1. 概要

ALICE_Core は、LINE Bot などの外部クライアントからの要求受付、Job / Workspace のライフサイクル管理、非同期 JobQueue、および各 AI モジュール（Transcript, Summary 等）を順次実行する `CoreWorker` と成果物配信（Publisher）を担う中核コンポーネントです。

---

## 2. アーキテクチャと連携方式

### 基本原則

* **疎結合アーキテクチャ**:
  * Core は各モジュール内部の Python クラスを直接 import せず、**Workspace Driven CLI / Subprocess 方式** で連携します。
  * `1 Job = 1 Workspace`（`<ALICE_DATA_DIR>/runtime/workspaces/{job_id}/`）のライフサイクルを Core が完全に管理します。
* **単一責任原則**:
  * Core はオーケストレーション（受付・キュー・プロセス管理・配信）に専念し、音声認識や LLM 推論などの AI 処理ロジックは各独立モジュール（`ALICE_Transcript`, `ALICE_Summary` 等）に委譲します。
* **Source of Truth（源泉データ）**:
  * `transcript/transcript.json` を会話の構造化正本データとし、後続モジュールはこれを参照して処理を行います。

---

## 3. 処理フロー

```text
LINE (ユーザー音声・要求)
    │
    ▼
1. MessageHandler (要求受付 & Workflow 決定)
    │
    ▼
2. WorkspaceManager (Job 生成 & Workspace 初期化)
    │
    ▼
3. JobQueue (非同期キューイング)
    │
    ▼
4. CoreWorker (Job 取得 & 順次 Subprocess 実行)
    │
    ├── Step 1: ALICE_Transcript (cli.py --workspace <path>)
    │            └──> <workspace>/transcript/ (transcript.json / txt)
    │
    ├── Step 2: ALICE_Summary (cli.py --workspace <path>)  ※要約要求時
    │            └──> <workspace>/summary/ (summary.md)
    │
    ▼
5. Publisher (LinePublisher: 最終成果物を LINE へ配信)
    │
    ▼
Job COMPLETED / FAILED
```

---

## 4. 現行の Workflow 仕様

LINE からの要求に応じて、以下の直列 Workflow が自動的に割り当てられます。

| ユーザー要求 | 生成される `Job.workflow` | 実行されるモジュール | 最終配信成果物 |
| :--- | :--- | :--- | :--- |
| **文字起こし** | `["transcript"]` | `ALICE_Transcript` | `transcript.txt` |
| **要約** | `["transcript", "summary"]` | `ALICE_Transcript` → `ALICE_Summary` | `summary.txt` (内部で `summary.md` も保持) |

* **Artifact Contract**:
  * モジュール CLI のプロセス終了コードが `0` かつ、契約された成果物ファイル（`primary_artifact`）が Workspace 内に存在することで成否を判定します。
* **配信タイミング**:
  * 途中のステップ完了時には配信せず、**Workflow 全体の最終ステップ完了後に 1 回のみ** LINE へ成果物を Push 配信します。

---

## 5. 実行時ディレクトリ構成

ALICE の永続データは `ALICE_DATA_DIR` を単一のルートとして保存します。省略時は `{PROJECT_ROOT}/data/`、相対パスは `PROJECT_ROOT` から解決します。Core、Search、CoPilot で同じ `ALICE_DATA_DIR` を設定してください。

```text
<ALICE_DATA_DIR>/
├── runtime/
│   ├── workspaces/{job_id}/    # Job Workspace
│   ├── logs/                   # Core / CoPilot 運用ログ
│   ├── core/
│   │   ├── inbox/              # 受信一時ファイル
│   │   ├── share/              # LINE 配信・静的公開領域 (/share)
│   │   ├── archive/
│   │   ├── system_settings.json
│   │   └── last_global_ip.txt
│   ├── search/                 # 検索インデックス
│   ├── copilot/                # CoPilot DB・実行状態
│   ├── calendar/               # Calendar / Tasks 認証ファイル
│   └── patch_queue/
└── memory/                     # CoPilot 長期記憶・Obsidian・HANDOFF
```

## 6. 本番起動

Project_ALICE ルートで `./start_alice_core.sh` を実行します。スクリプトは `myenv/core_env` の Python で Core を起動し、`ALICE_Core/.env` を読み込むため `ALICE_Core` を作業ディレクトリにします。起動前に GPU ロックファイルへアクセスできるかを、実際の起動ユーザーで確認します。失敗時は UID/GID と対象パスを表示して起動を中止します。

既定では `127.0.0.1:8000` で待ち受けます。起動時に `./start_alice_core.sh --ip 127.0.0.1 --port 8001` のように指定すると接続先を変更できます。`--ip` と `--port` は任意の順序で指定でき、片方だけの指定も可能です。引数を省略した値は `ALICE_CORE_HOST` と `ALICE_CORE_PORT` 環境変数から取得し、それらも未設定なら既定値を使います。systemd から使う場合は、`ExecStart` にこのスクリプトの絶対パスと必要な引数を指定し、意図したサービスユーザーで実行してください。スクリプトは `sudo` による権限変更を行いません。

### 現行版と Rabbit Hole 版の共存

| インスタンス | 公開 URL | 待受 | データ領域 |
| :--- | :--- | :--- | :--- |
| 現行 ALICE | `https://project-alice.net` | `127.0.0.1:8000` | 現行版専用 `ALICE_DATA_DIR` |
| Rabbit Hole ALICE | `https://rabbit-hole.project-alice.net/noel` | `127.0.0.1:8001` | Rabbit Hole 版専用 `ALICE_DATA_DIR` |

Cloudflare Tunnel は既存のリモート管理 Tunnel を使用します。`rabbit-hole.project-alice.net` は既存の `project-alice.net` Zone に追加するサブドメインです。Cloudflare Zero Trust の **Networks → Tunnels → 既存 Tunnel → Routes → Add a route → Published application** で以下を登録します。

| 項目 | 値 |
| :--- | :--- |
| Domain | `project-alice.net` |
| Subdomain | `rabbit-hole` |
| Path | `^/(home|noel)(/.*)?$` |
| Service URL | `http://127.0.0.1:8001` |

Path は `/home`・`/noel` とそれぞれの配下に一致させ、別インスタンスの `/admin` や `/share` 等をこの公開アプリルートから除外します。Cloudflare は Path を除去・書き換えずに転送するため、Rabbit Hole Core は要求パスをそのまま受け取ります。公開アプリルート作成時に DNS レコードも Tunnel 向けに登録されます。Cloudflare Access アプリケーションは作成せず、Noel は匿名利用の方針です。

Rabbit Hole 版は別のコード checkout / systemd service で起動し、たとえば `ALICE_DATA_DIR=/data/alice/rabbit-hole` と `ALICE_GPU_LOCK_FILE=/tmp/alice_gpu.lock` を設定します。GPU ロックだけは現行版と共有し、同時に GPU 処理を走らせないようにします。`ALICE_ENABLE_IP_MONITOR=false` とし、IP 監視・Discord通知の二重起動を防ぎます。ブラウザー Job の成果物は LINE に送らず、Noel API から取得します。手動起動例:

```bash
ALICE_DATA_DIR=/data/alice/rabbit-hole \
ALICE_GPU_LOCK_FILE=/tmp/alice_gpu.lock \
ALICE_ENABLE_IP_MONITOR=false \
./start_alice_core.sh --ip 127.0.0.1 --port 8001
```

ポートは loopback に bind し、IP / ポートを直接公開しません。Cloudflare Access はこの一般利用 URL に適用せず、HTTPS とアップロード検証は Noel API 側で強制します。

---

## 7. Job Management & 追跡仕様 (ALICE v1.0)

ALICE v1.0 では、1件のJobに関する完全なトレーサビリティ（追跡可能性）を保証します。

### 追跡項目
1. **何を受け取ったか (`input_metadata`)**:
   - 受信元ファイル名 (`original_name`)、バイトサイズ (`size_bytes`)、受付日時 (`received_at`)、入力原本パス (`input_file`)
2. **どのWorkflowを実行したか (`workflow`)**:
   - 実行パイプライン（例: `["transcript"]`, `["transcript", "summary"]`）
3. **現在どこまで進んだか (`current_step`, `step_history`)**:
   - 現在実行中モジュール名 (`current_step`)
   - ステップ単位の実行履歴 (`step_history`): ステップ名、状態 (`StepStatus`: PENDING / RUNNING / COMPLETED / FAILED / SKIPPED)、開始時刻、完了時刻、経過秒数 (`elapsed_sec`)、終了コード (`exit_code`)
4. **成功したのか失敗したのか (`status`, `error_detail`)**:
   - 全体ステータス (`JobStatus`: CREATED / QUEUED / RUNNING / COMPLETED / FAILED)
   - 失敗時の構造化詳細 (`error_detail`): 失敗ステップ名 (`failed_step`)、エラー分類 (`error_type`)、終了コード (`exit_code`)、メッセージ、ログファイルパス (`log_file`)、発生時刻
5. **どの成果物が生成されたのか (`artifacts`)**:
   - 各モジュールの **Artifact Contract** に基づいて生成された成果物参照リスト。
   - 成果物名 (`name`)、Workspace内相対パス (`path`)、生成モジュール名 (`module`)、主成果物フラグ (`is_primary`)、ファイルサイズ (`size_bytes`)、生成日時 (`created_at`)
   - **※ Transcript本文やSummary本文などの実データそのものは `job.json` に埋め込まず、ファイル参照メタデータのみを保持します。**

### Source of Truth と WorkspaceManager API
データベース（RDBMS/NoSQL）を追加せず、Workspace 自体を Source of Truth とします。
- `workspace_manager.save_job_json(job)`: アトミック置換保存（tmp -> rename）でデータ整合性を保証。
- `workspace_manager.load_job(workspace_dir)`: 指定 Workspace から Job を完全復元。
- `workspace_manager.get_job(job_id)`: `job_id` から該当 Job を取得。
- `workspace_manager.list_jobs(limit=50, user_id=None)`: 全 Workspace を走査し、作成日時降順で過去の Job 一覧を取得。

---

## 8. ディレクトリ構成

```text
ALICE_Core/
├── auth/                   # ユーザー認証・招待コード管理
├── core/
│   ├── container.py        # DI コンテナ
│   ├── job_queue.py        # FIFO JobQueue (メモリキュー)
│   ├── logger.py           # Core ロガー (<ALICE_DATA_DIR>/runtime/logs/alice.log)
│   ├── session.py          # ユーザー対話セッションモデル
│   ├── session_manager.py  # セッション状態管理
│   ├── worker.py           # CoreWorker (MODULE_RUNNERS 定義 & 順次実行)
│   └── workspace_manager.py# 1 Job = 1 Workspace 管理 (追跡・ロード・一覧API)
├── database/               # ユーザー情報 SQLite
├── line/                   # LINE ハンドラー & メッセージ送信
├── models/
│   └── job.py              # Core 共通 Job モデル (ライフサイクル・進捗・成果物追跡対応)
├── publisher/              # 成果物配信 (LinePublisher)
├── repository/             # DB リポジトリ
├── config.py               # Core 設定
└── main.py                 # FastAPI エントリーポイント
```

---

## 9. 将来構想 (Current Scope 外)

以下は今後のフェーズで段階的に検討・拡張される項目であり、現行バージョンでは未実装・予約領域として扱われます。

* 後続モジュール（`ALICE_Minutes`, `ALICE_Insight`, `ALICE_Search` 等）の追加接続
* Job / Queue の DB 永続化（SQLite / Redis / Celery 等）
* Module 通信の HTTP / gRPC 化
* Publisher の他サービス拡張（Discord, Slack, Obsidian 等）

## 10. Browser API

Rabbit-Hole のホーム画面は `/home` で提供します。`ALICE_Navigators/` 直下の各ナビゲーターディレクトリにある `navigator.json` を読み取り、利用可能な案内先をカード表示します。登録には `name`、`description`、`path` を設定し、任意で同一オリジンの `image` パスを指定します。現在のNoelは `/noel` へ遷移します。ホーム画面は `/admin` と同じ起動スプラッシュの後、森のラビットホールをくぐる短い演出を表示し、演出はスキップできます。`/home` と `/noel` の画面、API、静的ファイルはHTTPS必須です。TLS終端をCloudflare Tunnel等に任せる場合は、Coreが信頼するプロキシから `X-Forwarded-Proto: https` を転送してください。ローカルでCore自身にTLS終端させる場合は、起動時に `--ssl-keyfile` と `--ssl-certfile` を両方指定します。例: `./start_alice_core.sh --ip 127.0.0.1 --port 8001 --ssl-keyfile /path/to/key.pem --ssl-certfile /path/to/cert.pem`。

| Method / Path | 内容 |
| :--- | :--- |
| `GET /home` | Rabbit-Hole ホーム画面を返す。 |
| `GET /home/api/navigators` | `ALICE_Navigators/` 内の有効な `navigator.json` を一覧で返す。 |

Noel のブラウザー画面は `https://rabbit-hole.project-alice.net/noel`（ソース: `ALICE_Navigators/Noel/`）で提供し、画像は同じ Rabbit Hole Core インスタンスから配信します。Noel は文字起こし専用UIとして `/noel/api` 配下の匿名 API を使用し、`/admin` の管理者認証から分離しています。HTTPS 必須で、Cookie は HttpOnly / Secure / SameSite=Strict の host-only 設定です。セッションは Job の分離用で、本人確認には使いません。

| Method / Path | 内容 |
| :--- | :--- |
| `GET /noel/api/session` | ブラウザーセッション用 Cookie を発行し、対応する `user_id` を返す。 |
| `POST /noel/api/transcribe` | multipart/form-data の `audio` を受け付け、`["transcript"]` のみを実行する文字起こし Job を登録する。MP3 / M4A / WAV、100 MiB 以下、音声 2 時間以下。ffprobe で実データを検証する。 |
| `GET /noel/api/jobs/{job_id}` | セッション所有 Job の状態と進捗 (`progress.stage`, `progress.percent`) を返す。他セッションの Job は 404。 |
| `GET /noel/api/jobs/{job_id}/live-transcript` | Whisper が生成した途中の文字起こしテキストを返す。未生成の場合は 204。 |
| `GET /noel/api/jobs/{job_id}/transcript` | 所有 Job の Whisper 文字起こし結果 (`transcript/transcript.txt`) を返す。未生成の場合は 409。 |
| `POST /noel/api/minutes` | 議事録生成用の既存 API。`["transcript", "summary", "minutes"]` を実行する。別 Navigator から利用するため維持する。 |
| `GET /noel/api/jobs/{job_id}/minutes` | 議事録生成 Job の議事録を返す。未生成の場合は 409。 |

Job の `user_id` は署名済みセッション Cookie から導出し、Cookie 値そのものは応答に含めません。各取得時に所有者を照合します。1 セッション 1 件、Noel 全体で実行中・待機中合計 2 件、送信元 IP あたり 15 分で 5 回までに制限します。Uvicorn が信頼する proxy header 送信元は既定で loopback のみです。Cloudflared は同一ホストから loopback に接続させ、Cloudflare 側も Noel のホスト名を Tunnel 経由だけで公開してください。異なる接続元では `ALICE_CORE_TRUSTED_PROXY_IPS` を設定します。
