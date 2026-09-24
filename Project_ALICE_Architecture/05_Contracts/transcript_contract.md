# ALICE_Transcript Contract Specification

## 1. 契約成果物一覧

`ALICE_Transcript` は、正常完了時（Exit Code 0）に Workspace 内の `<workspace>/transcript/` 配下に以下の成果物を必ず生成する契約を結ぶ。

| ファイル名 | 契約区分 | 形式 | 役割・説明 |
| :--- | :--- | :--- | :--- |
| `transcript.json` | **Source of Truth** | JSON | 全文のタイムスタンプ・話者付き構造化正本 |
| `transcript.txt` | **Primary Artifact** | PlainText | LINE 配信および人間可読用のプレーンテキスト |
| `metadata.json` | Auxiliary | JSON | 処理時間、認識言語、モデルパラメータ等 |

---

## 2. `transcript.json` スキーマ (Source of Truth)

```json
[
  {
    "start": 0.0,
    "end": 2.45,
    "speaker": "SPEAKER_00",
    "text": "会議を始めます。"
  },
  {
    "start": 2.80,
    "end": 5.12,
    "speaker": "SPEAKER_01",
    "text": "よろしくお願いします。"
  }
]
```

### フィールド仕様
- `start` (`float`): 発話開始秒数（0以上の実数）。
- `end` (`float`): 発話終了秒数（`start` 以上）。
- `speaker` (`string`): 話者ラベル。原則として `SPEAKER_XX` 形式（未特定時は `UNKNOWN`）。
- `text` (`string`): 正規化済みの発話テキスト。

---

## 3. `transcript.txt` フォーマット (Primary Artifact)

```text
[00:00:00 - 00:00:02] SPEAKER_00: 会議を始めます。
[00:00:02 - 00:00:05] SPEAKER_01: よろしくお願いします。
```

- 各行は `[HH:MM:SS - HH:MM:SS] SPEAKER_ID: 発話内容` の形式とする。
