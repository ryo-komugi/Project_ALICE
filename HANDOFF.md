# Antigravity Cross-Device Context & Handoff (HANDOFF.md)

> **[AGENT INSTRUCTION / エージェントへの指示]**
> このファイルは、メインPC、モバイルPC、alice-serverの各Antigravity間で作業文脈・タスク進捗・設計決定を引き継ぐための**共有メモリ**です。
> - **作業開始時**: 本ファイルを確認し、直近の作業状況やToDoを把握してから作業に着手してください。
> - **作業完了・区切り時**: 本セッションで完了した作業内容や発生した決定事項、次のToDoを本ファイルの「2. Latest Status & Handoff」に追記・更新してください。

---

## 1. System & Environment Overview

| 項目 | 内容 |
|------|------|
| **Core Project** | `Project_ALICE` (ALICE_Core, LINE連携, 音声処理, メモリ同期等) |
| **Server** | `alice-server` (SSH: `takuya@alice-server`, Repo: `/home/takuya/Project_ALICE`) |
| **GitHub Remote** | `git@github.com:ryo-komugi/Project_ALICE.git` (branch: `main`) |
| **Home Relay Node** | `home-tablet` (SSH: `ssh home-tablet`, Tailscale: `100.72.47.67:8022`) — 自宅LAN常時給電リレー・WoL基点 |
| **Shared Memory (Windows)** | `C:\Users\TA_51\ALICE_Memory` (Syncthing `alice-memory` で常時自動同期) |
| **Shared Memory (Linux)** | `/data/memory` |

**アーキテクチャ方針**:
- **Antigravity内部データ (`~/.gemini/antigravity/`) の直接同期は完全禁止**（バイナリインデックス衝突・DBファイルロック破壊を避けるため）。
- 端末間の文脈・タスク引き継ぎはすべて本ファイル (`HANDOFF.md`) および `ALICE_Memory` を介して行う。

---

## 2. Latest Status & Handoff

- **Last Updated**: 2026-09-25 01:25 (Device: takuya_MainPC/alice-server via Antigravity)
- **Current Milestone**: Phase 3（GitHub管理移行完了・Requirementsファイル名整理・プッシュ完了）
- **Direct Next Action**: リアルタイム音声会話の品質改善（Barge-in / STT / TTS）

---

## 3. System Architecture & Module Status

### 3.1 モジュール稼働状況

| モジュール | 最新コミット | 状態 | 備考 |
|-----------|------------|------|------|
| `ALICE_Core` | `1c4e386` (V0.2.0) | ✅ 稼働中 | Hub/Gateway/Portal 3層構成・タイムアウトSLA & リトライ・systemctl連携 |
| `ALICE_Transcript` | `9cef515` | ✅ 安定 | large-v3、前処理・アライメント最適化済み |
| `ALICE_Summary` | `32179d1` | ✅ 安定 | Pydantic V2、Timeline構造・Commentary生成 |
| `ALICE_Minutes` | `7e09d41` | ✅ 安定 | ハイブリッド連携・4テンプレート・3画面Webビューア |
| `ALICE_Search` | `7b8cd6d` | ✅ 安定 | commentary検索対応・FTS5+LIKEフォールバック |
| `ALICE_CoPilot` | `828eca4` | ✅ 稼働中 | Antigravity CLI常駐タスクキュー・文脈共有 |

### 3.2 サービス構成

| サービス | ポート | 管理 |
|---------|-------|------|
| `alice-core.service` | 8000 | systemctl |
| `alice-copilot.service` | 8005 | systemctl |
| Nightly Reviewer | — | cron 03:00 JST |
| Morning Briefing | — | cron 07:30 JST |

### 3.3 主要設定

| 項目 | 値 |
|-----|---|
| CoPilot LLM | `qwen3.5:9b` (Ollama, keep_alive 24h) |
| Minutes/Summary LLM | `gemma4:12b` (Ollama, think: False) |
| Whisper モデル | `large-v3` |
| バックアップ先 | `/data/backup_alice/*.git` |

---

## 4. 完了した主要マイルストーン

### Phase 1: 基盤構築・安全展開 (〜2026-09-15)
- [x] ALICE_Core 責務分離・モジュラーモノリス（Hub / Gateway / Portal）再編 (`8a0e5a4`)
- [x] Cloudflare Zero Trust 移行・自前認証撤廃・マルチPWA（admin/wol）サブドメイン分離 (`bf4c9cf`)
- [x] Phase 1 仲間内安全展開・管理画面MFA・招待制アクセス制御
- [x] Wake-on-LAN（WoL）遠隔起動PWA (`wol.project-alice.net`) 配備
- [x] 自宅グローバルIP変動検知 & Discord #alerts 通報システム (`73974f5`)
- [x] 端末間引き継ぎ仕組み（HANDOFF.md + Syncthing）の確立

### Phase 2: Google連携・長期記憶・夜間自律改善 (〜2026-09-17)
- [x] Google カレンダー多カレンダー横断検索・自然言語登録・終日イベント対応 (`bca5bb1`)
- [x] Google Tasks 直結・期日フィルタ・ハルシネーション根絶ガード
- [x] 長期記憶検索強化・カタカナ対応・`search_project_memory` ツール追加
- [x] 夜間自律改善システム（Nightly Reviewer）& モーニングブリーフィング配備 (`6c70c05`)
- [x] WebUI AI Console（Assistant / CoPilot 二分）・トークンストリーミング・リアルタイム音声対話 WebUI版

### Phase 2+: コード品質・パイプライン強化 (2026-09-22〜23)
- [x] ALICE_Transcript: large-v3標準化・VRAM解放・音声前処理・アライメント平滑化 (`9cef515`, `347f244`)
- [x] ALICE_Summary: Pydantic V2・タイムライン構造化・Commentary生成・Pipeline分離 (`32179d1`)
- [x] ALICE_Minutes: ハイブリッド議事録・4テンプレート（standard/interview/executive/consultation）・3画面Webビューア (`7e09d41`)
- [x] ALICE_Search: commentary検索対応・conftest整備・FTS5+LIKEフォールバック (`7b8cd6d`)
- [x] ALICE_CoPilot: 自己進化型チェックリスト（CHK-CAL/TSK/MEM/SYS-001）・単体テスト復旧 (`e17b7c5`)
- [x] LLM高速化: `qwen3.5:9b` 移行（約2.5倍高速化）・包括リファクタリング
- [x] LINE音声バースト受信（複数ファイル同時送信対応）(`356d2d4`)
- [x] ゴースト話者問題: 音声前処理（FFmpeg）+ LLM文脈名寄せによる根本解決 (`cf17702`)

---

## 5. 次に実施すべきタスク (Next ToDo)

### 優先度: 高

- [x] **Discord チャンネル分離（`#assistant` 稼働）& `#copilot` への Antigravity 直結＆自律改修パイプライン配備 (2026-09-23)**:
  - `#assistant`: 日常秘書・スケジュール・Tasks・要約検索（Ollama `qwen3.5:9b` 爆速応答）。
  - `#copilot`: 開発・自律保守専属。Ollama を完全バイパスし Google Antigravity SDK (`stream_copilot`) を直結。
  - モーニングブリーフィング Embed に【🛠️ 改善案を自律改修する】インタラクティブボタンおよび `!apply` コマンドを配備。Discord からワンタップで Antigravity (`auto_patcher.py`) が起動し、調査・修正・単体テスト・Gitコミットまで自律完走。
  - 単体テスト（`test_channel_routing.py` 含む計31件）全件 PASS。

- [x] **モーニングブリーフィング改善提案の実行・実装＆長期記憶明文化 (2026-09-23)**:
  - **提案①（依存関係マップ）**: システム全系統・外部連携依存関係マップ（Dependency Graph）を策定し、長期記憶（`/data/memory/copilot/Knowledge/`）に登録・Obsidian 同期完了。
  - **提案②（ワークフローSLA＆リトライ）**: `ALICE_Core`（`config.py`, `hub/worker.py`）にモジュール単体タイムアウトSLA（900秒）および自動リトライ（最大2回・バックオフ5秒）を実装。単体テスト全件PASS、長期記憶登録・Obsidian 同期完了。

- [x] **Antigravity CLI (`agy`) 常駐タスクキュー & 共有コンテキスト自律改修基盤配備 (2026-09-24)**:
  - **追加API課金ゼロ（完全定額）**: サーバー上の Antigravity CLI (`/home/takuya/.gemini/bin/agy`) を活用し、Google クラウド知能（Gemini 3.8 Flash / 2.5 Pro 級）で自律パッチを実行。
  - **即時受付タスクキュー（`patch_worker.py`）**: Discord ボタン / `!apply` 押下後 1 秒で受付完了返答。バックグラウンドで `agy` がコード調査・安全修正・pytest単体テスト（100% PASS）・Gitコミット・HANDOFF 3拠点同期を自律完走し、`#copilot` に完了 Embed を通知。
  - **WebUI CoPilot への文脈共有**: `dev_copilot_service.py` のシステムプロンプトに、今朝のモーニングブリーフィング改善提案（`nightly_reports.db`）と `HANDOFF.md` を動的注入。「今朝の提案について教えて」に即答可能化。
  - **テスト検証**: 単体テスト（`test_patch_worker.py`、`test_channel_routing.py` 含む計230件）全件 PASS。CoPilot サービス稼働中。

- [ ] **リアルタイム音声会話のさらなる品質改善**（WebUI版は基本実装済み、改善余地あり）
  - 現状: Web Speech API（ブラウザ内蔵STT/TTS）による実装完了。
  - 改善候補: faster-whisperによる高精度STT、VOICEVOX等による高品質TTS、Barge-in精度向上。

### 優先度: 中

- [ ] **Phase 3: 平日アイデア温め & 先行リサーチ基盤**
  - Discord から吹き込んだ思いつき → アイデアリスト追記 → Antigravityが自律フィジビリティ調査 → 週末に一気に実装、のサイクル確立。

- [ ] **Phase 3: 自宅工房ハンズフリーモード（案C）**
  - デスク常駐マイク & スピーカーによるウェイクワード「アリス」による完全ハンズフリー対話の検証。

### 優先度: 低（将来）

- [ ] Flutter モバイルアプリ化（Phase 4 以降）
  - 長時間バックグラウンド録音・LINEログイン連携・議事録ビューアー。ニーズ顕在化後に着手。

---

## 6. 重要な設計決定・運用規約 (Key Decisions & Constraints)

1. **モバイル展開方針**: まず LINE 公式アカウントで展開し、ニーズ成熟後に Flutter アプリ化（Phase 4 以降にプール）。
2. **コミットルール**: ユーザーから明示的な指示（「コミットして」等）があるまで `git commit` を行わない。
3. **【最重要エージェント規約】HANDOFF.md の自律更新**: 大きな作業の完了時・セッション終了時には、エージェントが必ず自律的に本ファイルを更新し、3箇所（MainPC / `ALICE_Memory` / `alice-server:/data/memory/`）へ同期すること。
4. **Google Tasks 運用ルール**: 原則「接頭語なし」。`【提〆】`/`【回答〆】`/`【G〆】` は明示された時のみ付与。時刻通知はカレンダーに案内。
5. **Tasks / Calendar 完全分離**: 「タスク」指示 → Google Tasks のみ。「予定/スケジュール/カレンダー」指示 → Google Calendar のみ。二重登録厳禁。
6. **夜間自律改善の自律レベル**: Level 1（長期記憶の自動追加・Obsidian同期 + コード改善提案の提示）。コード自動修正は提案にとどめ、ユーザー承認後に適用。
7. **ユーザーアクセス制御**: 招待コードによる自動承認 + 管理画面からの手動ステータス変更を正式運用とする。Reject ユーザーには「紹介元の管理者まで直接お問い合わせください」と案内（管理者個人LINEを明かさない）。
8. **アーキテクチャ方針（Antigravity同期禁止）**: `~/.gemini/antigravity/` の直接同期は完全禁止。文脈引き継ぎは HANDOFF.md を介する。
