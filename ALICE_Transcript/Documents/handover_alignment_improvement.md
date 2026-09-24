# ALICE_Transcript アライメント処理・精度改善 申し送り

## 1. 対応状況

ALICE_Transcriptのアライメント処理および低品質音声への対応改善が完了した。

以下の検証に合格している。

- 単体テスト：12項目すべてPASS
- 実音声によるEnd-to-Endパイプライン：正常完了
- transcript.json出力：正常
- transcript.txt出力：Contract規格に適合
- metadata.json：COMPLETEDを記録
- ALICE_Summary単体テスト：4項目すべてPASS
- ALICE_Minutes単体テスト：2項目すべてPASS

現時点では、今回の改修を完了済みの実装として扱うこと。

---

## 2. 今回の主な改修内容

### AlignmentEngine

- Whisperセグメント単位で先頭単語の話者を一括適用する処理を廃止
- 単語単位の話者情報をもとに発話を再構築
- Pyannoteセグメントとの重複時間最大値による話者判定に変更
- 近傍吸着を導入
  - TOLERANCE_MARGIN：0.35秒
- UNKNOWN補間を実装
  - 同一話者に挟まれた微小ギャップ
  - 発話境界付近
  - 0.25秒以下の孤立した話者フリップ
- 発話分割条件を実装
  - 話者切替
  - ポーズ1.0秒以上
  - 句読点＋ポーズ0.5秒以上
  - 最大発話長25秒

### TextNormalizer

- 日本語畳語を破壊する短いsubstring除去を廃止
- 4文字以上の同一フレーズ反復のみ除去
- フィラー重複を安全に除去
- 1〜3文字の偶然一致による文末切断を廃止
- クレンジング後の空発話を除外

### 音声前処理・Whisper

- ffmpegによるハイパスフィルタを導入
  - highpass=f=80
- 音量均一化を導入
  - dynaudnorm
- Whisper設定を変更
  - vad_filter=True
  - condition_on_previous_text=False
  - initial_promptに会議開始文を設定

### 出力処理

- metadata.jsonのステータス記録を修正
- export_debugのパス参照を修正
- transcript.txtの出力形式をContract規格に統一

---

## 3. 今後変更する際の注意点

### 3.1 話者割り当て処理

以下の旧仕様に戻してはいけない。

- Whisperセグメント全体への一括話者適用
- 最初に見つかったPyannote話者の無条件適用
- 重複判定前の直前話者の先行伝播

話者判定は、単語単位の時間情報とPyannoteセグメントとの重複を基準とすること。

### 3.2 UNKNOWN補間

UNKNOWNを無条件に前後話者へ割り当てないこと。

特に、前後で話者が異なる場合や、長いUNKNOWN区間については、誤った話者割り当てにつながるため慎重に扱うこと。

### 3.3 TextNormalizer

日本語では1〜3文字の一致が正当な語の一部である可能性が高い。

以下のような短い語を破壊してはいけない。

- ここまで
- いろいろ
- それぞれ
- だんだん
- 少々

重複除去の閾値を変更する場合は、必ず日本語畳語の回帰テストを実行すること。

### 3.4 Whisper VAD・音声前処理

VADや音声正規化は、ノイズ除去に有効である一方、短い相槌や小声の発話を欠落させる可能性がある。

設定変更時は、以下を確認すること。

- 短い相槌が残るか
- 小声の発話が残るか
- 発話開始・終了時刻が不自然に変化しないか
- ノイズ区間の幻覚・反復が抑制されているか

### 3.5 Jobステータス

`COMPLETED`は、必須成果物が正常に生成されたことと整合する必要がある。

今後ExporterやPublisherの処理順を変更する場合は、metadata.jsonのステータスと実際の成果物状態が矛盾しないようにすること。

---

## 4. Contract維持

下流モジュールとのインターフェースとして、以下を維持すること。

### transcript.json

各発話に少なくとも以下の情報を保持する。

- start
- end
- speaker
- text

### transcript.txt

以下の形式を維持する。

```text
[HH:MM:SS - HH:MM:SS] SPEAKER: text
```
