# ADR-003 Utterance Builder

## ステータス

採用（Accepted）

## 背景

AlignmentEngineでは、WhisperのWord TimestampとPyannoteの話者情報を統合し、
単語単位の話者割り当て（Speaker Assignment）までは完了している。

しかし、現在の merge_segments() は単純に話者ごとに単語を結合するだけであり、
発話単位（Utterance）の生成には適していない。

また、ALICE_Transcriptの目的は人が読む最終成果物を生成することではない。

ALICE_Transcriptは、ALICE_Minutesへ受け渡すための
構造化されたTranscriptデータを生成することを目的とする。

## 決定

Utterance Builderを導入する。

入力
- assigned_words
- whisper_segments

出力
- transcript.json

Utterance Builderは以下の2段階で処理を行う。

### Phase 1
Whisper SegmentからUtterance Candidateを生成する。

### Phase 2
隣接するCandidateについて、以下の条件を満たす場合に結合する。

- 話者が同一
- 時間差が閾値以内
- （将来）その他の結合条件

Whisper Segmentは文章境界ではなく、
Utterance Candidateを生成するための時間チャンクとして扱う。

## 実装

V0.5.2で実装。
Sentence Builderは
Whisper Segmentを探索範囲として利用し、
assigned_wordsからTranscriptを構築する。

## 影響

merge_segments() は将来的に廃止する。

Utterance BuilderがTranscript生成を担当する。