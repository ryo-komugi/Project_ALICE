# ALICE_Summary 開発マイルストーン総括ドキュメント

本ドキュメントは、音声会話要約エンジン **`ALICE_Summary`** の設計刷新、3ステージ段階的生成アーキテクチャの導入、LINEボット連携、耐障害性向上、会話タイプ別テンプレート適応、およびシステム全体の一気通貫 E2E 結合検証に至る全開発マイルストーンの記録です。

---

## 1. 開発背景とアーキテクチャ刷新

### 従来の課題
従来の単一プロンプトによる一括要約では、以下の重大な課題が発生していました：
1. **事実と評価の混同**: 指導者側の主観的な叱責・警告が、客観的事実として記録されてしまう。
2. **発言者の混同**: 対象者本人の弁明と指導側の指摘が入れ替わってしまう。
3. **ハルシネーション**: 元の文字起こしに存在しない数値や出来事が捏造される。
4. **重要論点の脱落**: 長尺の会話において、後半の結論や合意事項が抜け落ちる。

### 解決策: 3ステージ段階的生成アーキテクチャ
単一モデルに一度に全タスクを任せるのではなく、人間の優秀な編集者と同様の分業プロセスを導入しました。

```
[文字起こしテキスト (transcript.json / txt)]
                     │
                     ▼
  ┌─────────────────────────────────────────┐
  │ Stage 1: Analyzer (会話理解・構造化)    │
  │   - 会話目的・背景の抽出                │
  │   - トピック別論点・事実・発言・合意抽出│
  │   - 話者別スタンス・発言分析            │
  └────────────────────┬────────────────────┘
                       │ analysis.json
                       ▼
  ┌─────────────────────────────────────────┐
  │ Stage 2: Composer (高品質文章化)        │
  │   - 会話タイプ（面談/会議/相談/汎用）自動判別
  │   - 最適化テンプレートによるドラフト生成│
  └────────────────────┬────────────────────┘
                       │ draft_summary.md
                       ▼
  ┌─────────────────────────────────────────┐
  │ Stage 3: ConsistencyChecker (整合性監査)│
  │   - 文字起こし原文との全項目厳格対照    │
  │   - 会話タイプ固有基準による監査・微修正│
  └────────────────────┬────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
  summary.md                      summary.txt
  (Markdown完全版)                (LINE/テキスト版)
```

---

## 2. 開発マイルストーン詳細

### Milestone 0: 段階的生成プロトタイプ & モデルベンチマーク
* **目的**: ローカル LLM（Gemma 4: 12B / Qwen 2.5: 14B）を用いて、ChatGPT-4o に匹敵する要約クオリティが実現可能かを検証。
* **実施内容**:
  - 実録音データ（53分・113分の長尺面談）を用いたモデル比較・コンテキスト長検証。
  - Gemma 4: 12B が事実の抽出精度・ニュアンスの忠実度において突出して優れていることを確認。
  - 動的コンテキスト長（`num_ctx: 32k〜64k`）自動計算ロジックの導入。
* **成果**: 3ステージパイプライン（Analyzer → Composer → ConsistencyChecker）の設計確立。

---

### Milestone 1: LINE ボット要約直接送信連携 (v0.2.0)
* **目的**: 従来の「ダウンロード Flex カード」に加え、LINE トーク画面上で要約内容をそのまま読める UX の提供。
* **実施内容**:
  - `ALICE_Core/publisher/line_publisher.py` を改修。
  - 要約完了時、Flex カード（ファイルダウンロードリンク）の送信直後に、要約本文テキスト（`summary.txt`）をプッシュ送信する仕組みを実装。
  - LINE の 1 メッセージ文字数制限（5,000文字）を考慮し、4,500文字を超える場合は「プレビュー版＋完全版ダウンロード誘導」に自動分割。
* **コミット**:
  - `ALICE_Core`: `896c496` (`feat(line): push full/preview summary text directly to LINE talk`)
* **検証**: `test_step13.py` にて LINE への文字起こし＋要約通知フローの完全合格を確認。

---

### Milestone 2: 耐障害性・堅牢化 (v0.3.0)
* **目的**: ローカル LLM 運用特有の障害（通信瞬断、モデルハング・無限ループ、JSON破損、キャッシュ破損）に対する完全自動リカバリ機能の構築。
* **実施内容**:
  1. **指数バックオフ自動リトライ**:
     - `OllamaClient`: 通信エラー（接続遮断、一時タイムアウト）時に最大 3 回の自動リトライ（待機時間: 2s → 4s → 8s）。
  2. **モデル自動フォールバック**:
     - 指定モデルが存在しない（HTTP 404）または推論不能な場合、代替モデル（`gemma4:12b` → `qwen3:14b`）へ自動切り替え。
  3. **生成ループ完全防止**:
     - Ollama のデフォルト `num_predict=-1` による長尺暴走を防ぐため、各ステージに明示的な上限（Stage 1: 4096, Stage 2: 4096, Stage 3: 6144）と `repeat_penalty: 1.1` を設定。
  4. **堅牢な JSON 修復パーサー**:
     - 思考タグ（`<thought>`）の除去、未エスケープ改行の許容（`strict=False`）、末尾カンマの除去、欠落カッコの自動補完を実装。
  5. **破損中間成果物の自動検知・再生成 (Robust Resume)**:
     - 過去の中断や破損で空ファイルや不正 JSON が残っていても、自動検知して破棄・再生成。
* **コミット**:
  - `ALICE_Summary`: `58c343b` (`fix: prevent generation loop with num_predict and harden json extraction parser`)
  - `ALICE_Summary`: `a34ce9f` (`feat(resilience): implement auto-retry with backoff, model fallback, and robust resume`)
* **検証**: 単体テスト 8 件、実データ E2E テスト 4 件すべて合格。

---

### Milestone 3: 会話タイプ別テンプレート適応 & 監査連動 (v0.4.0)
* **目的**: 「面談」に留まらず、「定例会議」「業務相談・壁打ち」「汎用」など、対話の種類に応じた最適な章立て・用語・整合性監査を実現。
* **実施内容**:
  1. **4種類の会話タイプ別プロンプトテンプレート** (`prompts/templates/`):
     - `stage2_interview.txt`: 面談・評価用（目的、重要発言・認識齟齬・事実と評価の峻別、合意・宿題事項）。
     - `stage2_meeting.txt`: 定例会議用（アジェンダ別討議・意見、決定事項【Decisions】、ネクストアクション【Action Items】）。
     - `stage2_consultation.txt`: 業務相談・壁打ち用（相談課題、検討アイデア、助言・アドバイス、検証方針）。
     - `stage2_general.txt`: 汎用対話用（背景、主要な話題、結論・今後の予定）。
  2. **自動判別エンジン (`Composer.detect_conversation_type`)**:
     - Stage 1 の抽出結果（`metadata`, `conversation_overview`, `speakers_analysis`, `topics`）から総合キーワードスコアリングを行い、最適なテンプレートを自動選定。
  3. **Stage 3 整合性監査への動的連動 (`ConsistencyChecker`)**:
     - 会話タイプに応じた固有チェック項目（会議なら決定事項の厳格性・タスク期限、相談なら相談課題と助言の峻別など）を監査プロンプトに動的注入。
  4. **CLI オプション拡張 (`cli.py`)**:
     - `--type {auto,interview,meeting,consultation,general}` をサポート（デフォルト: `auto`）。
     - `metadata.json` に選定された `"conversation_type"` を記録。
* **コミット**:
  - `ALICE_Summary`: `6a79140` (`feat(templates): add conversation-type templates and auto-detection (Milestone 3)`)
  - `ALICE_Summary`: `4daf4b4` (`feat(checker): integrate conversation-type specific criteria into Stage 3 audit`)
* **検証**: 単体テスト 11 件全 PASS、実面談データ E2E テストにて `interview` が自動判定され正常出力。

---

### Milestone 4: システム全体一気通貫 E2E 結合検証
* **目的**: 本番オーケストレーション（`ALICE_Core` Worker）において、音声ファイル投入から文字起こし・新3ステージ要約・LINE配信までが完全に連携して動作することを検証。
* **実施内容**:
  - `ALICE_Core/test_step13.py` を拡張し、新3ステージパイプラインの成果物（`analysis.json`, `draft_summary.md`, `consistency_report.md`, `summary.md`, `summary.txt`, `metadata.json`）の存在および整合性を検証。
  - 実音声ファイルを投入し、CoreWorker 経由で一気通貫実行。
* **実行結果**:
  ```text
  [CoreWorker] Executing step 'transcript' -> SUCCESS (12.5s)
  [CoreWorker] Executing step 'summary'    -> SUCCESS (126.3s)
    - Stage 1 (Analyzer): 40.28s
    - Stage 2 (Composer: auto -> interview): 38.58s
    - Stage 3 (ConsistencyChecker): 47.39s
  [CoreWorker] Job COMPLETED
  [LinePublisher] Copy & Publish complete
  [Test 2] Summary metadata verified: type=interview, total=126.26s
  >>> Test 2 PASSED!
  ```
* **コミット**:
  - `ALICE_Core`: `7afd11e` (`test(e2e): update test_step13 to assert full 3-stage summary pipeline and metadata`)

---

## 3. マイルストーン達成サマリー表

| マイルストーン | バージョン | 主な機能・対応 | 状態 | 対象リポジトリ / コミット |
| :--- | :---: | :--- | :---: | :--- |
| **Milestone 0** | v0.1.0 | 3ステージ段階的生成方式の確立（Analyzer / Composer / Checker） | **完了** | `ALICE_Summary` |
| **Milestone 1** | v0.2.0 | LINEトーク画面への要約テキスト直接プッシュ送信（4,500字分割・プレビュー） | **完了** | `ALICE_Core` (`896c496`) |
| **Milestone 2** | v0.3.0 | 耐障害性向上（指数バックオフ、モデルフォールバック、生成ループ防止、JSON修復） | **完了** | `ALICE_Summary` (`58c343b`, `a34ce9f`) |
| **Milestone 3** | v0.4.0 | 会話タイプ別テンプレート（面談・会議・相談・汎用）自動判別 & 整合性監査連動 | **完了** | `ALICE_Summary` (`6a79140`, `4daf4b4`) |
| **Milestone 4** | v0.4.1 | システム全体（Core + Transcript + Summary + LINE）一気通貫 E2E 結合検証 | **完了** | `ALICE_Core` (`7afd11e`) |

---

## 4. 成果物およびファイル構成一覧

### ALICE_Summary
- `cli.py`: パイプライン実行 CLI（`--workspace`, `--model`, `--type`, `--skip-stage3`, `--stage3-only` 等）
- `config.py`: 設定定義（リトライ回数、フォールバックモデル、生成トークン上限、温度パラメータ）
- `core/analyzer.py`: Stage 1 構造化抽出エンジン
- `core/composer.py`: Stage 2 会話タイプ自動判別・文章化エンジン
- `core/checker.py`: Stage 3 原文照合・タイプ別整合性監査エンジン
- `core/ollama_client.py`: Ollama API クライアント（リトライ、フォールバック、JSON修復）
- `core/workspace_io.py`: 成果物入出力、動的コンテキスト長計算、テキスト変換
- `prompts/templates/`:
  - `stage2_interview.txt`: 面談用プロンプトテンプレート
  - `stage2_meeting.txt`: 会議用プロンプトテンプレート
  - `stage2_consultation.txt`: 業務相談用プロンプトテンプレート
  - `stage2_general.txt`: 汎用プロンプトテンプレート
- `prompts/stage1_analysis.txt`: Stage 1 構造化抽出プロンプト
- `prompts/stage3_consistency.txt`: Stage 3 整合性監査プロンプト
- `test_unit.py`: 単体テストスイート（11件）
- `test_summary.py`: 実データ E2E テストスイート（4件）

### ALICE_Core
- `core/worker.py`: ジョブキュー監視・直列モジュール実行（Transcript → Summary）
- `publisher/line_publisher.py`: Flexカードダウンロード通知 ＋ 要約テキスト直接プッシュ送信
- `test_step13.py`: LINE受付から音声文字起こし・要約・配信までの一気通貫結合テスト

---

## 5. 生成成果物仕様

各ジョブのワークスペース配下（`/data/runtime/workspaces/<job_id>/summary/`）に出力される成果物：

| ファイル名 | 種別 | 内容・用途 |
| :--- | :--- | :--- |
| `analysis.json` | JSON | Stage 1 成果物。会話の背景・目的、発言者分析、トピック別の論点・事実・発言・合意事項 |
| `draft_summary.md` | Markdown | Stage 2 成果物。会話タイプ別テンプレートに基づいて執筆された初稿要約 |
| `consistency_report.md` | Markdown | Stage 3 成果物。原文文字起こしとドラフト要約の整合性対照・チェック基準判定レポート |
| `summary.md` | Markdown | 最終確定版要約（Stage 3 精密監査・微修正済み） |
| `summary.txt` | Text | LINE 送信およびテキスト閲覧用のプレーンテキスト整形版（記号置換済み） |
| `metadata.json` | JSON | 実行メタデータ（会話タイプ、モデル名、フォールバック有無、ステージ別所要時間・トークン数） |
