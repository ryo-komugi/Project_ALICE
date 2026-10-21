# 【構想・設計引き継ぎ書】Project_ALICE 移管 ＆ Project_CHESHIRE 独立分離計画
**Document ID**: `HANDOFF_CHESHIRE_SPLIT`  
**Last Updated**: 2026-10-20  
**Author / Decision**: Takuya Asano  
**Related Document**: [`../HANDOFF.md`](file:///home/takuya/Project_ALICE/HANDOFF.md)

---

## 1. 背景と目的

1. **個人開発と本番サービスの干渉防止**:
   * 現行の `alice-server` では、ポート 8000（`alice-core.service`）に Cloudflare Tunnel（`project-alice.net`）が直結している。
   * takuya による個人開発・再起動・リファクタリングが外部公開サービス（Rabbit-Hole / Noel 等）を巻き込むリスクがあるため、本番系統を専用ユーザー `product` に完全移管する。
2. **ハードウェア追加なしの「同一マシン内・姉妹システム分割」**:
   * 別物理サーバーを購入・新設するのではなく、現行 `alice-server`（RTX 5060 Ti 16GB, CPU 20コア, RAM 32GB）の潤沢なリソースを活かし、同一マシン内で OS ユーザー・ポート・権限・ドメインを美しく2分割する。
3. **Project_CHESHIRE（チェシャ）の誕生**:
   * 音声処理パイプライン基盤（ALICE）を明け渡し、個人用環境は「自律知性・個人秘書エージェント」に特化した **`Project_CHESHIRE`** として転生・独立進化させる。

---

## 2. システム責務・分離マップ

| 項目 | **Project_ALICE**（本番・共有・移管先） | **Project_CHESHIRE**（個人・自律知性） |
|:---|:---|:---|
| **コンセプト** | 外部向け音声AI処理パイプライン基盤 | takuya専用の自律思考・生活密着パーソナルエージェント |
| **実行ユーザー** | **`product`**（UID 1003、ryo-komugi氏共同管理） | **`takuya`**（UID 1000、chmod 700で完全隔離） |
| **配置ディレクトリ** | `/home/product/Project_ALICE` | `/home/takuya/Project_CHESHIRE` |
| **コア機能** | Core, Transcript, Summary, Minute, Rabbit-Hole, Noel | CoPilot, 自律エージェント, 思考ストック, 家電, 予定 |
| **メインUI / Input** | LINE Messaging API, Webポータル (`/home`, `/noel`) | **Discord Bot**（CHESHIRE専用対話窓口） |
| **管理コックピット** | **ALICE COCKPIT**（個人機能を除去したDashboard / Job Explorer / Logsのみ） | **CHESHIRE COCKPIT**（個人用ダッシュボード・エージェント管理） |
| **待受ポート** | **`8000`**（Cloudflare変更不要） | **`8010`**（CHESHIRE WebUI / API） |
| **Cloudflare ドメイン** | `project-alice.net` / `admin.project-alice.net` | `grin.project-alice.net`（Zero Trust認証でtakuyaのみ） |
| **ランタイムデータ** | **`/data/runtime`**（音声・一時ファイル・ジョブ成果物） | **`/data/runtime_personal`**（エージェントログ・個人一時データ） |
| **長期記憶（Memory）** | **完全排除**（個人情報・Obsidianは一切持たせない） | **`/data/memory`**（Obsidian連携・完全プライベート） |
| **GPUリソース・排他制御** | **完全集約・一元管理**（`acquire_gpu_lock`、Whisper/PyAnnote等のパイプライン排他を全管轄） | **排他制御なし・超省VRAM**（Ollama `gemma4:e4b` のみ常駐、高度推論は外部API/Antigravity委譲） |

---

## 3. 重要アーキテクチャ設計

### ① Job Queue 周りの連携設計（Client-Serverモデル）
* **通常投入**: takuya 自身も普段は Webポータル（Noel: `https://project-alice.net/noel`）から音声をアップロードしてジョブ実行。
* **Discord（CHESHIRE）からの投入**:
  * CHESHIRE が直接モジュール CLI を叩くのではなく、ローカルの **ALICE Core 内部API（`http://127.0.0.1:8000/api/jobs`）** にリクエストを転送する。
  * **メリット**:
    1. ALICE Core の中央キューで整然と順番待ちが行われ、GPUオーバーフローやロック競合が絶対に起きない。
    2. CHESHIRE 側の仮想環境に PyAnnote / Whisper / Torch などの重量級ライブラリを抱える必要がなく、超軽量に保てる。
    3. ジョブ完了時、CHESHIRE が結果を受け取って **Discordに返信し、同時に `/data/memory/obsidian` へ自動ストック** する。

### ② コックピット（WebUI）の分割方針
* **ALICE側**:
  * 個人情報（SwitchBot家電、カレンダー、ブリーフィング、Obsidian検索等）を完全削除。
  * **「GPU/CPUメトリクス（Dashboard）」「ジョブ追跡（Job Explorer）」「システムログ（System Log）」** のみに絞った業務管理画面として提供。
* **CHESHIRE側**:
  * 個人司令塔として転生。エージェント自己診断、対話チャット、スマートホーム、日次ブリーフィング、思考メモ閲覧を集約。

### ③ ストレージパスの分離
* `/data/runtime` $\to$ ALICE本番用（所有者: `product:users`、chmod 775）
* `/data/runtime_personal` $\to$ CHESHIRE用（所有者: `takuya:users`、chmod 770）
* `/data/memory` $\to$ CHESHIRE専用（所有者: `takuya:users`、chmod 700で保護）

### ④ GPU排他制御のALICE一任 ＆ CHESHIREの省VRAM設計
* **GPU排他ロックはALICEに完全集約**:
  * `acquire_gpu_lock()` による排他制御・SLA監視・タイムアウト管理はすべて **ALICE側（`ALICE_Core`）の専任責務** とする。
  * CHESHIRE側はGPU排他制御ロジックを持たず、GPU資源管理から完全に解放される。
* **CHESHIREは当面 `gemma4:e4b` のみで運用**:
  * CHESHIREが使用するローカルLLMは、省フットプリントな **`gemma4:e4b`** のみ常駐させる。
  * 重い分析・コード生成・長文要約などの高度知能はクラウド/外部API（Antigravity CLI / Gemini API）に委託する。
  * これにより、ALICE側がWhisper大型モデル等でGPUをフル稼働させてもVRAM（16GB）に余裕があり、CHESHIRE側がGPUロックを意識せずとも競合・OOMを起こさずに平穏に共存できる。

---

## 4. systemd サービス移管・新設の検討事項

### ① 現行 `alice-core.service` の product 移管
* **現状**: `User=takuya`, `WorkingDirectory=/home/takuya/Project_ALICE/ALICE_Core`
* **移管後（`/etc/systemd/system/alice-core.service`）**:
  * `User=product`
  * `WorkingDirectory=/home/product/Project_ALICE/ALICE_Core`
  * `Environment="PATH=/home/product/Project_ALICE/myenv/core_env/bin"`
  * `ExecStart=/home/product/Project_ALICE/myenv/core_env/bin/uvicorn main:app --host 0.0.0.0 --port 8000`
* **確認・検討項目**:
  * `/home/product/Project_ALICE` のコードベース同期および仮想環境（`myenv`）の配備。
  * `.env` の権限確認（`ALICE_DATA_DIR=/data/runtime` の明記）。
  * GPUロックファイル（`/tmp/alice_gpu.lock`）のマルチユーザー対応パッチ（`e1b07d6`）が確実に反映されていること。

### ② 新設 `cheshire.service`（個人用）
* **新規作成（`/etc/systemd/system/cheshire.service`）**:
  * `User=takuya`
  * `WorkingDirectory=/home/takuya/Project_CHESHIRE`
  * `ExecStart=/home/takuya/Project_CHESHIRE/myenv/bin/python main.py`（Discord Bot ＋ ポート 8010 WebUI）
  * `Restart=always`, `RestartSec=10`

---

## 5. 次回着手時の ToDo チェックリスト

- [ ] **Phase 1: ディレクトリ＆ストレージ準備**
  - [ ] `/data/runtime` および `/data/runtime_personal` の作成とパーミッション設定
  - [ ] `/home/product/Project_ALICE` への最新コードベース配備
- [ ] **Phase 2: ALICE_Core の共有クリーンアップ**
  - [ ] ALICE_Core の `.env` を本番用設定に更新（`ALICE_DATA_DIR=/data/runtime`）
  - [ ] コックピットから個人用コンポーネント（SwitchBot/カレンダー等）を分離
  - [ ] `gpu_lock.py` のマルチユーザー安全パッチ反映
- [ ] **Phase 3: systemd 移管**
  - [ ] `alice-core.service` の実行ユーザーを `product` に切り替え・再起動テスト
  - [ ] ポート 8000（Cloudflare Tunnel `project-alice.net`）の外部疎通確認
- [ ] **Phase 4: Project_CHESHIRE 独立化**
  - [ ] `/home/takuya/Project_CHESHIRE` 立ち上げ（CoPilotと個人機能を移管）
  - [ ] ポート `8010` での CHESHIRE 起動確認
  - [ ] Discord からの Job 投入 $\to$ ALICE Core API（8000番）連携 $\to$ Obsidian自動格納テスト
  - [ ] `cheshire.service` の systemd 登録・自動起動設定
