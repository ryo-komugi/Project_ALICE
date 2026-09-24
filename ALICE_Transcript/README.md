# ALICE_Transcript

> Project_ALICE 用のオフライン音声文字起こし & 話者分離モジュール

---

## 1. 概要

ALICE_Transcript は、音声ファイルを **Whisper による高精度文字起こし** と **Pyannote による話者分離（Diarization）**、および **ワードレベル話者アライメント** を組み合わせて処理し、話者ごとの発言ログ（タイムスタンプ付き）を生成する独立モジュールです。

生成される `transcript.json` は、後続の要約（Summary）や議事録（Minute）モジュールが利用する **Project_ALICE の源泉データ（Source of Truth）** として機能します。

---

## 2. アーキテクチャと連携方式 (Workspace Driven CLI)

ALICE_Transcript は、**Workspace Driven CLI / Subprocess 方式** で上位の `ALICE_Core` と疎結合に連携します。

```text
ALICE_Core Worker ──(Subprocess)──> cli.py --workspace <path>
                                        │
                                        ▼
                             TranscriptPipeline
                                 1. Pyannote (話者分離)
                                 2. Whisper (音声認識)
                                 3. Alignment (話者照合)
                                 4. Normalization (重複除去・正規化)
                                 5. Exporter (成果物書き出し)
                                        │
                                        └──> <workspace>/transcript/ (json, txt, metadata)
```

---

## 3. CLI 実行契約

```bash
/home/takuya/Project_ALICE/myenv/whisper_env/bin/python /home/takuya/Project_ALICE/ALICE_Transcript/cli.py --workspace /data/runtime/workspaces/{job_id}
```

| 項目 | 仕様 |
| :--- | :--- |
| **入力引数** | `--workspace <workspace_dir>` (必須) |
| **入力ファイル** | `<workspace_dir>/input/` 配下の音声ファイル (`.mp3`, `.m4a`, `.wav`) |
| **出力ディレクトリ**| `<workspace_dir>/transcript/` |
| **生成成果物** | 1. `transcript.json` : 話者・時間・発言の構造化データ (源泉データ)<br>2. `transcript.txt` : 人間可読テキスト<br>3. `metadata.json` : 実行時間・モデル情報 |
| **終了コード** | 正常完了: `0` / 異常終了: `1` 以上（標準エラー出力にエラー詳細） |

---

## 4. ディレクトリ構成

```text
ALICE_Transcript/
├── cli.py                  # CLI エントリーポイント (引数解析と Pipeline 起動)
├── config.py               # モデル名・共通パス等のモジュール設定
├── core/
│   ├── pipeline.py         # TranscriptPipeline (処理フロー統括)
│   ├── job.py              # 実行時コンテキストデータモデル
│   ├── job_status.py       # Job ステータス Enum
│   ├── exporter.py         # transcript.json / txt / metadata.json 出力
│   ├── text_normalizer.py  # 重複削除・テキスト正規化
│   ├── logger.py           # モジュールロガー (/data/runtime/logs/transcript.log)
│   └── utils.py            # 音声変換 (WAV) ・時間フォーマット・時間重なり計算
├── engines/
│   ├── whisper_engine.py   # faster-whisper 音声認識ラッパー
│   ├── pyannote_engine.py  # Pyannote 話者分離ラッパー
│   └── alignment_engine.py # ワードレベル話者アライメント
├── scripts/
│   └── run_pyannote.py     # Pyannote 仮想環境 (pyannote_env) 実行用スクリプト
└── Documents/              # 関連ドキュメント
```

---

## 5. 将来構想 (Current Scope 外)

* 音声認識・話者分離エンジンの精度チューニング
* クラスタリング・並列処理の最適化
* メタデータ拡張
