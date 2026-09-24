import os
import json
import requests
import config

OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL


SYSTEM_PROMPT = """
あなたはALICE_CoPilotの記憶検索ルーターです。

ユーザーの質問を見て、長期記憶を検索する必要があるか判断してください。

長期記憶を検索すべき例:
- 過去に決めたことを尋ねている
- 過去の会話や出来事について尋ねている
- Project_ALICEの過去の仕様や設計について尋ねている
- ユーザーが以前伝えた情報について尋ねている
- 「前に」「以前」「覚えている」「決めた」など、過去の情報を参照する質問

長期記憶を検索する必要がない例:
- 一般的な知識についての質問
- 単純な雑談
- 現在の時刻や計算
- 一般的なプログラミング質問
- 新しい話題についての質問

必ずJSONだけを返してください。

形式:

{
  "use_memory": true
}

または

{
  "use_memory": false
}
"""


def should_use_memory(question: str) -> bool:
    # 1. 高速バイパス: 明らかな日常会話・挨拶・カレンダー/タスク操作ならLLM呼び出しをスキップ
    q_lower = question.lower()
    obvious_skip_keywords = [
        "こんにちは", "おはよう", "こんばんは", "おやすみ", "ありがとう", "どうも", "テスト",
        "予定", "スケジュール", "カレンダー", "タスク", "todo", "動静", "ミーティング", "mtg",
        "登録", "追加", "入れて", "入れといて", "削除", "消して", "変更", "ずらして", "更新",
        "何時", "天気", "今何時", "今日何日", "計算", "明日の予定", "今日の予定"
    ]
    # メモリ検索関連の明示的キーワード
    memory_keywords = ["前", "以前", "昔", "仕様", "設計", "なぜ", "理由", "覚えて", "方針", "決定", "経緯", "ALICE", "記憶", "過去"]
    has_memory_kw = any(kw in question for kw in memory_keywords)

    if not has_memory_kw and any(kw in question for kw in obvious_skip_keywords):
        return False

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {
                "num_ctx": config.OLLAMA_CONTEXT,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    data = response.json()
    result = json.loads(data["message"]["content"])

    return bool(result.get("use_memory", False))