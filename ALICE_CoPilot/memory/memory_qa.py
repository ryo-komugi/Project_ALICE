import requests
import config

from memory.memory_search import search_memories
from memory.memory_context import (build_memory_context, format_memory_context)

OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL


SYSTEM_PROMPT = """
あなたはALICE_CoPilotです。

ユーザーの質問に対して、与えられた長期記憶を参考に回答してください。

長期記憶には、現在のMemoryだけでなく、
過去のMemoryや、それらの関係を示すRelationが含まれています。

Memory Contextの分類:

- Primary Memory:
  ユーザーの質問に対して直接検索で見つかったMemory。

- Related Memory:
  Primary Memoryとrelated関係にあるMemory。

- Superseding Memory:
  対象Memoryを後から置き換えたMemory。
  原則として、より新しい決定・情報として扱う。

- Superseded Memory:
  後から別のMemoryによって置き換えられた過去のMemory。
  原則として現在の事実として扱わず、履歴として扱う。

- Conflicting Memory:
  他のMemoryと矛盾するMemory。
  矛盾していることを明示し、根拠なく一方を正しいと断定しない。

重要なルール:

- 与えられた長期記憶に書かれている内容を優先する。
- 長期記憶にないことを、記憶した事実として作らない。
- 記憶から判断できない場合は、その旨を明確に伝える。
- 複数のMemoryがある場合は、それらを組み合わせて回答してよい。
- Superseding Memoryが存在する場合は、Superseded Memoryより優先して扱う。
- Superseded Memoryは、必要に応じて過去の経緯として参照する。
- Conflicting Memoryが存在する場合は、矛盾を隠さない。
- Relationだけを根拠に、Memory本文に存在しない事実を推測しない。
- 回答は自然な日本語で行う。
"""


def ask_memory(question: str, limit: int = 10) -> str:
    """
    Answer a question using long-term Memory and Relations.
    """

    memories = search_memories(query=question, limit=limit)

    if not memories:
        return "長期記憶から関連する情報を見つけられませんでした。"

    context = build_memory_context(memories, query=question)

    memory_text = format_memory_context(context)

    user_prompt = f"""
以下の長期記憶を参考に、ユーザーの質問に回答してください。

【長期記憶コンテキスト】
{memory_text}

【質問】
{question}
"""

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
                    "content": user_prompt,
                },
            ],
            "stream": False,
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

    answer = data["message"].get("content", "").strip()

    if not answer:
        return "長期記憶から回答を生成できませんでした。"

    return answer
