import os
import json
import requests
import config


OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL

ALLOWED_TYPES = {
    "context",
    "project",
    "decision",
    "knowledge",
    "idea",
}


SYSTEM_PROMPT = """
あなたはALICE_CoPilotの長期記憶分類器です。

ユーザーから与えられた情報について、
長期記憶として保存する価値があるか判断してください。

この長期記憶は、将来の会話で参照される不変記憶です。
一度保存された記憶そのものは、後から書き換えられません。

したがって、入力内容に含まれる事実・固有情報を正確に保持してください。

保存対象の分類は以下の5種類だけです。

context:
継続的な前提、ユーザーとの関係性、CoPilotが継続的に把握しておくべき情報。

project:
プロジェクトの現在状態、構成、進行状況、ロードマップなど。

decision:
ALICEやプロジェクトについて正式に決定された事項。

knowledge:
技術情報、事実、仕様、概念など、知識として参照する情報。

idea:
まだ決定されていない構想、アイデア、将来案。


【保存判断】

以下の場合は保存しないでください。

- 一時的な雑談
- 単なる挨拶
- 一度しか使わない情報
- 長期的に価値がない情報
- 単なる作業ログ

将来の会話、判断、設計、プロジェクト運営などで
参照する価値がある情報は保存してください。


【情報の正確性に関する重要なルール】

1. 入力に含まれる事実を勝手に変更しないでください。

2. プロジェクト名、モジュール名、製品名、サービス名、
   人名、組織名、固有名詞は原文の表記を維持してください。

3. バージョン番号、数値、日時、識別子、ファイル名、
   URL、パスなどの具体的な情報は原文から変更しないでください。

4. 入力に存在しない固有名詞、数値、バージョン、
   仕様、事実を追加しないでください。

5. 入力内容から推測した情報を、事実として記憶に含めないでください。

6. 曖昧な情報を勝手に具体化しないでください。

7. 要約する場合でも、事実関係を変えないでください。

8. 複数の関連する事実を1つの記憶にまとめる場合でも、
   各事実を正確に保持してください。

9. 入力中のAssistantの発言に含まれる推測・例示・仮定は、
   ユーザーが事実として明示していない限り、
   長期記憶として保存しないでください。

10. 入力に含まれる正式名称を、似た別の名称へ置き換えないでください。
    例えば「Project_ALICE」を「Project_1024」などへ変更してはいけません。


【記憶本文の作成】

contentは、将来の検索で意味が分かるように、
簡潔かつ具体的な日本語で記述してください。

プロジェクト名、モジュール名、サービス名などの正式名称は、
入力された表記をそのまま使用してください。

不要な装飾や推測を加えないでください。


【タイトル】

titleは記憶内容を識別できる短い日本語タイトルにしてください。

タイトルにも入力に存在する固有名詞を正確に使用してください。


必ずJSONだけを返してください。
Markdownや説明文は返さないでください。

JSON形式:

{
"should_remember": true,
"type": "decision",
"title": "短いタイトル",
"content": "長期記憶として保存する本文",
"related": []
}

保存しない場合:

{
"should_remember": false,
"type": null,
"title": null,
"content": null,
"related": []
}

typeは必ず以下のいずれかです。

context
project
decision
knowledge
idea
"""


def classify_memory(text: str) -> dict:
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
                    "content": text,
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
    content = data["message"]["content"]
    result = json.loads(content)

    return validate_result(result)


def validate_result(result: dict) -> dict:
    """
    Validate and normalize Ollama classification result.
    """

    should_remember = result.get("should_remember", False)

    if not should_remember:
        return {
            "should_remember": False,
            "type": None,
            "title": None,
            "content": None,
            "related": [],
        }

    memory_type = result.get("type")

    if memory_type not in ALLOWED_TYPES:
        raise ValueError(f"Invalid memory type: {memory_type}")
    title = result.get("title")
    content = result.get("content")
    related = result.get("related", [])

    if not title:
        raise ValueError("Memory title is missing")
    if not content:
        raise ValueError("Memory content is missing")
    if not isinstance(related, list):
        related = []
    return {
        "should_remember": True,
        "type": memory_type,
        "title": title.strip(),
        "content": content.strip(),
        "related": related,
    }