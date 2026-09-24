# Word-Level Speaker Alignment Specification

## 1. 目的

Whisper による単語単位のタイムスタンプ（Word Timestamps）と、Pyannote による話者分離区間（Diarization Segments）を統合し、発話者情報付きの正確な会話文章（Utterance）を再構築する。

低品質な音声（ノイズ・遠隔マイク・小声）に対しても、微小なタイムラグや無音区間による誤判定・話者巻き込みを起こさず、堅牢に話者分離・発話構築を行う。

---

## 2. 処理パイプライン

```text
[Input Audio] (*.wav, *.mp3, *.m4a)
     │
     ▼
[0. Audio Preprocessing]
・ハイパスフィルタ (80Hz以下の低周波・空調ノイズ除去)
・動的音量均一化 (dynaudnorm による距離・小声の均一化)
     │
     ├───────────────────────────────────────┐
     ▼                                       ▼
Whisper Engine                          Pyannote Engine
(Silero VAD / 幻覚抑制)                  (話者分離)
  └─ Word Timestamps (word, start, end)   └─ Speaker Segments (speaker, start, end)
           │                                       │
           └───────────────────┬───────────────────┘
                               ▼
                   [1. Speaker Assignment]
                   ・単語単位の重複時間最大値（Max Overlap）を割り当て
                   ・重複ゼロ時は近傍吸着（TOLERANCE_MARGIN: 0.35s）
                               │
                               ▼
                   [2. UNKNOWN Interpolation]
                   ・同一話者で挟まれた微小ギャップのサンドイッチ補間
                   ・境界付近の近傍補間
                   ・0.25秒以下の孤立した話者フリップノイズ平滑化
                               │
                               ▼
                   [3. Utterance Builder]
                   ・単語レベルの話者交代地点で必ず分割
                   ・同一話者内：ポーズ（1.0s）、句読点＋ポーズ（0.5s）、最大発話長（25s）で分割
                   ・英数字間スペース維持・日本語自然結合
                               │
                               ▼
                   [4. Text Normalizer]
                   ・日本語畳語（ここまで、いろいろ、それぞれ等）の保護
                   ・4文字以上の同一フレーズ即時反復除去（Whisper幻覚対策）
                   ・偶然一致（1〜3文字）による語尾切断防止
                   ・空発話セグメントの除外
                               │
                               ▼
                      Structured Transcript
                      ├── transcript.json (Source of Truth)
                      └── transcript.txt  ([HH:MM:SS - HH:MM:SS] SPEAKER: text)
```

---

## 3. 主要関数・アルゴリズム仕様

### `assign_speakers(words, speaker_segments, tolerance_margin=0.35)`
- 各単語の `[start, end]` 時間と、Pyannote の各話者セグメントの交差（Intersection）時間を計算し、最も重なりが大きい話者 ID（`SPEAKER_00`, `SPEAKER_01` 等）を付与する。
- 重なりが 0 の単語については、`TOLERANCE_MARGIN`（0.35秒）以内の直近セグメントの話者へ近傍吸着する。
- 許容範囲外のみ `UNKNOWN` とする。
- **禁止事項**: ループ内での直前話者の先行代入や、最初に見つかった話者の無条件適用。

### `interpolate_unknown(assigned_words, max_gap=1.5)`
- **サンドイッチ補間**: 前後が同一話者で挟まれた UNKNOWN 区間をその話者で補間する。
- **境界補間**: 発話開始直後・終了直後の UNKNOWN を近接話者へ補間する。
- **デグリッチ平滑化**: 前後と異なる話者の極小単語（0.25秒以下の1トークン誤検出ノイズ）を前後の支配的セグメントへ平滑化する。
- **注意点**: 前後で話者が異なる場合や長い UNKNOWN 区間は無条件補間を行わず慎重に扱う。

### `build_utterances(assigned_words, pause_threshold=1.0, max_duration=25.0)`
- 単語単位に分割されたトークンを自然な発話単位（Utterance）へと組み立てる。
- **話者切替**: 話者が変わった地点で必ず分割する（Whisperセグメント全体への一括話者適用は絶対禁止）。
- **ポーズ時間判定**: 同一話者でも `pause_threshold`（1.0秒）以上の無音で分割する。
- **文境界判定**: 句読点（`。`、`？`、`！`）の後に一定のポーズ（0.5秒）がある場合は自然な文章区切りとして分割する。
- **長大化ガード**: 1発話が `max_duration`（25秒）を超えないよう分割する。

### `TextNormalizer`
- 日本語の 1〜3 文字の一致は正当な語の一部であるため、短い substring 重複除去は行わない。
- 4文字以上の同一フレーズ即時反復および主要フィラー重複のみを除去対象とする。
- 「ここまで」「いろいろ」「それぞれ」「だんだん」「少々」等の自然な日本語畳語を完全保護する。