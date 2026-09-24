# ALICE_Transcript Architecture

## 1. 概要

`ALICE_Transcript` は、Project_ALICE におけるオフライン音声文字起こし & 話者分離モジュールです。

高速かつ高精度な最新音声認識エンジン（`faster-whisper` + **`large-v3-turbo`**）と話者分離エンジン（`pyannote.audio`）を独立したパイプラインで実行し、音響前処理、単語レベルのアライメント（`AlignmentEngine`）、発話断片化防止（Defragmented Alignment）、重複除去・正規化（`TextNormalizer`）を経て、全下流モジュールが依存する **Source of Truth（源泉データ）** である `transcript.json` を生成します。

---

## 2. 処理パイプライン

```text
Input Audio (<workspace>/input/*.wav, *.mp3, *.m4a)
    │
    ▼
[Audio Preprocessing & Clean Acoustics]
・動的音量均一化 (dynaudnorm による遠隔マイク・小声の明瞭化)
・ハイパスフィルタ (空調・低周波ノイズの抑制)
    │
    ├────────────────────────────────┐
    ▼                                ▼
Pyannote Engine                  faster-whisper Engine
(pyannote_env)                   (whisper_env: large-v3-turbo)
話者分離 (Diarization)            音声認識 + Word Timestamps
    │                                │
    │ segments (speaker, start, end) │ words (word, start, end)
    └───────────────┬────────────────┘
                    ▼
           Alignment Engine (Defragmented)
           ・単語レベル話者割り当て (Speaker Assignment)
           ・UNKNOWN 話者のサンドイッチ・近傍補間 (Interpolation)
           ・発話断片化防止（同一話者の自然な結合・デグリッチ）
           ・Utterance Builder (発話単位の候補生成・結合)
                    │
                    ▼
           Text Normalizer
           ・日本語畳語の完全保護
           ・反復フレーズ・スタッター除去（Whisper幻覚対策）
           ・記号・空白正規化
                    │
                    ▼
           Exporter
           ├── <workspace>/transcript/transcript.json (Source of Truth)
           ├── <workspace>/transcript/transcript.txt  (Primary Artifact)
           └── <workspace>/transcript/metadata.json   (処理メトリクス)
```

---

## 3. 主要コンポーネント

| コンポーネント | 役割 | 動作環境 / 依存 |
| :--- | :--- | :--- |
| `cli.py` | CLI 引数解析（`--workspace`）、ログ設定、パイプライン実行 | `whisper_env` |
| `core.pipeline.TranscriptPipeline` | 全体実行フロー制御、音響前処理、一時ファイル管理 | `whisper_env` |
| `engines.whisper_engine.WhisperEngine` | faster-whisper（`large-v3-turbo`）による高速認識・Word Timestamp 抽出 | `whisper_env` (CUDA) |
| `engines.pyannote_engine.PyannoteEngine` | pyannote.audio による話者区間分離（Subprocess で `run_pyannote.py` を呼出） | `pyannote_env` (隔離環境) |
| `engines.alignment_engine.AlignmentEngine` | 単語と話者区間のマッチング、断片化防止、Utterance 構築 | `whisper_env` |
| `core.text_normalizer.TextNormalizer` | 意味を変えない範囲でのテキストクレンジング（畳語保護付き） | `whisper_env` |
| `core.exporter.Exporter` | `transcript.json`, `transcript.txt`, `metadata.json` の出力 | `whisper_env` |

---

## 4. 責任境界

- **責務**:
  - 音声原本からの正確・高速なテキスト化と話者区分の紐付け。
  - 発話単位（Utterance）のタイムスタンプ整合性担保および断片化防止。
  - 構造化データ（JSON）と人間可読テキスト（TXT）の生成。
- **非責務**:
  - 文脈に基づいた誤字・固有名詞の推測補正（LLM による補正）。
  - 会話の要約・議事録化。
  - 外部サービスへの配信。
