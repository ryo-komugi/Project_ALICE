# ADR 009: ALICE_Core の Hub / Gateway / Portal 3層モジュラーモノリス構造の採択

> Status: Accepted  
> Date: 2026-09-23  
> Deciders: Project_ALICE Core Architecture Team  

---

## 1. 背景と課題 (Context)

`ALICE_Core` は、初期設計において `core/` ディレクトリ直下に以下の責務をすべて抱え込んでいた：
1. **外部通信**: LINE Webhook 受信、署名検証、メッセージハンドラー、リッチメニュー管理
2. **ジョブ制御**: FIFO メモリキュー（`JobQueue`）、ワーカー（`CoreWorker`）、`WorkspaceManager`
3. **管理機能**: Admin Dashboard PWA、ユーザー認可、ジョブログ閲覧、成果物プレビュー

この構造には以下の重大な課題が生じていた：
- **コード肥大化とモノリス化**: `core/admin.py` や `core/worker.py` が 1,000 行超に達し、変更の影響範囲が不明瞭化。
- **パッケージの責務重複**: `line/` パッケージと `core/` の間でセッション管理やメッセージハンドラーの二重化やシムコードが残存。
- **機能拡張への摩擦**: バースト複数ファイル受信（WAIT_FILE）、ワークフロー単位の SLA タイムアウト／リトライ制御、管理画面からのオンデマンド再生成（serial queue）といった高度な制御を導入する際、単一レイヤーでは状態競合やテストの複雑化を招くリスクが高まっていた。

---

## 2. 決定事項 (Decision)

`ALICE_Core` を **Gateway / Hub / Portal** の3層に明確に分離されたモジュラーモノリス（Modular Monolith）構造へ再編した。

### 1. 3層の責任境界
- **Gateway Layer (`gateway/`)**:
  - LINE 等の外部メッセージング・Webhook 受信、署名検証（`SignatureVerifier`）
  - 各種ハンドラー（`follow`, `message`, `postback`, `unfollow`）
  - コンテンツダウンロード・送信およびセッション管理（`GatewaySession`）
  - リッチメニュー生成・アップロード
- **Hub Layer (`hub/`)**:
  - ジョブ実行エンジン（`CoreWorker`）、キュー管理（`JobQueue`）
  - ワークスペースライフサイクル統括（`WorkspaceManager`）
  - ワークフロー SLA タイムアウト監視および指数バックオフリトライ制御
- **Portal Layer (`portal/`)**:
  - 管理画面（Admin Dashboard PWA）および Cloudflare Access 認証連携
  - 専用サブルーターへの分割：
    - `admin_jobs.py`: ジョブ一覧・詳細・成果物プレビュー・オンデマンド再生成 API
    - `admin_logs.py`: リアルタイムシステムログ・ジョブログストリーミング
    - `admin_users.py`: ユーザーディレクトリ管理・表示名編集・Reject制御
  - HTML テンプレートの外部化（`portal/templates/`）

### 2. 旧パッケージの統合とシム撤去
- `line/` パッケージは `gateway/` へ完全統合。
- `core/` 直下に残存していた古い互換シムファイルを完全撤去。

### 3. パス解決のポータブル化
- 全パスを `PROJECT_ROOT` からの動的解決に統一し、環境依存を排除。

---

## 3. 影響と評価 (Consequences)

### メリット
- **高凝集・低結合の実現**: 外部通信プロトコル（Gateway）、ジョブ・SLA制御（Hub）、管理UI（Portal）が独立し、相互の変更影響を極小化。
- **テスト容易性の向上**: 各層ごとの独立した単体・結合テスト（`test_worker_resilience.py`, `test_admin_api.py`, `test_multi_file_queueing.py`）がクリーンに記述可能に。
- **自律監査との親和性**: `ALICE_CoPilot` のアーキテクチャ監査ツール（`reviewer/tools.py`）により、Hub / Gateway / Portal のレイヤー分離違反を自動点検できる基盤が完成。

### デメリット / 制約事項
- パッケージ階層が深くなったため、モジュール内での相対インポート規約を遵守する必要がある。
