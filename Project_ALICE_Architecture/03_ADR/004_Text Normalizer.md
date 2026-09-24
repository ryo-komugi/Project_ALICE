# ADR-004 Text Normalizer

## Status

Accepted

---

## Context

ALICE_TranscriptはSentence Builderにより、
話者付きTranscriptを生成できるようになった。

しかしWhisperの認識結果には、
文章の意味を変えない範囲で補正可能な表記ゆれや
重複が含まれる。

これらをTranscript生成ロジックへ組み込むと、
Alignmentの責務が肥大化し保守性が低下する。

---

## Decision

Text Normalizerを独立したPipelineとして導入する。

Pipelineは以下とする。

Whisper
↓
Pyannote
↓
Alignment
↓
Sentence Builder
↓
Text Normalizer
↓
Exporter

---

## Responsibility

Text Normalizerは、

- 表記ゆれ補正
- URL補正
- 空白補正
- 重複文字除去
- 記号整理

など、

**意味を変更しない文字列正規化のみ**を担当する。

---

## Non Responsibility

以下はText Normalizerでは行わない。

- 誤認識の推測補正
- 固有名詞の推測
- 文法修正
- 要約
- LLMによる自然文生成

これらは将来のALICE_Minutesまたは
ALICE_Summaryが担当する。

---

## Consequences

Alignment Engineは

- Speaker Assignment
- Sentence Builder

のみを担当する。

Text Normalizerは独立して成長できるため、
新しい正規化ルールを追加しても
Alignmentへ影響しない。