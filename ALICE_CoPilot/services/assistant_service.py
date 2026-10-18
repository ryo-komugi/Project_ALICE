"""
Assistant Service for ALICE WebUI & CoPilot.
Handles intelligent assistant workflows: Meeting Search, System Metrics,
and Memory QA with Tool Calling.
"""
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import requests
import config
from tools import TOOLS_SCHEMA, execute_tool
from services.action_guard import detect_intent, build_system_hint
from memory.short_term import save_message, get_recent_messages
from memory.memory_router import should_use_memory
from memory.memory_context import build_memory_context, format_memory_context
from memory.memory_consolidator import consolidate_pending_messages
from memory.obsidian_export import sync_obsidian
from services.antigravity_manager import increment_quota_usage
from services.prompts import get_copilot_system_prompt

logger = logging.getLogger("ALICE_CoPilot.Assistant")


def clean_llm_response(text: str) -> str:
    """Removes model reasoning token artifacts like 'thought\\n<channel|>' or '<thought>...'."""
    if not text:
        return ""
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^(?:\s*thought\s*)?(?:<channel\|>|<thought>)+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*thought\s*\n+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<channel\|>", "", cleaned)
    return cleaned.strip()


def get_assistant_system_prompt() -> str:
    return get_copilot_system_prompt(persona="知的アシスタント・相棒「ALICE」")


def call_ollama(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": {
            "num_ctx": config.OLLAMA_CONTEXT,
        },
    }
    if tools is not None:
        payload["tools"] = tools

    response = requests.post(
        config.OLLAMA_URL,
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


async def stream_assistant(prompt: str, session_id: str = "web_assistant", max_turns: int = 4) -> AsyncGenerator[dict, None]:
    """
    Executes assistant workflow and yields SSE event dictionaries.
    Yields:
      - {"type": "status", "message": str}
      - {"type": "tool_call", "name": str, "args": dict}
      - {"type": "tool_result", "name": str, "result": any}
      - {"type": "delta", "content": str}
      - {"type": "done", "full_content": str}
    """
    prompt = prompt.strip()
    if not prompt:
        yield {"type": "done", "full_content": "メッセージを入力してください。"}
        return

    now_utc = datetime.now(timezone.utc).isoformat()
    save_message(
        timestamp=now_utc,
        channel_id=session_id,
        user_id="web_user",
        role="user",
        content=prompt,
    )

    yield {"type": "status", "message": "コンテキストを確認中..."}

    recent_db_messages = get_recent_messages(channel_id=session_id, limit=10)
    memory_context_str = None

    # Determine if long-term memory lookup is relevant
    has_explicit_memory_kw = any(kw in prompt for kw in ["仕様", "設計", "なぜ", "理由", "方針", "決定", "経緯", "ALICE", "記憶", "過去"])

    if has_explicit_memory_kw or should_use_memory(prompt):
        yield {"type": "status", "message": "長期記憶を検索中..."}
        try:
            from memory.memory_search import search_memories
            raw_memories = await asyncio.to_thread(search_memories, prompt)
            if raw_memories:
                matched_context = await asyncio.to_thread(build_memory_context, raw_memories, query=prompt)
                if matched_context:
                    memory_context_str = format_memory_context(matched_context)
        except Exception as e:
            logger.error(f"[Assistant Memory Context Error] {e}")

    current_messages = []
    base_sys = get_assistant_system_prompt()
    if memory_context_str:
        base_sys += f"\n\n【ALICEの長期記憶コンテキスト】\n{memory_context_str}"

    current_messages.append({"role": "system", "content": base_sys})

    for role, content in recent_db_messages:
        current_messages.append({"role": role, "content": content})

    intent = detect_intent(prompt)
    initial_hint = build_system_hint(intent)
    if initial_hint and current_messages and current_messages[-1].get("role") == "user":
        current_messages[-1]["content"] += f"\n\n{initial_hint}"

    yield {"type": "status", "message": "思考・ツール実行中..."}

    final_content = ""
    for turn in range(max_turns):
        data = await asyncio.to_thread(call_ollama, current_messages, TOOLS_SCHEMA)
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")
        increment_quota_usage(cost_weight=1)

        if not tool_calls:
            raw_content = assistant_msg.get("content", "")
            final_content = clean_llm_response(raw_content)
            break

        # Tool calling requested by model
        current_messages.append(assistant_msg)
        for tc in tool_calls:
            fn_info = tc.get("function", {})
            fn_name = fn_info.get("name", "")
            raw_args = fn_info.get("arguments", {})

            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args or {}

            yield {"type": "tool_call", "name": fn_name, "args": args}
            yield {"type": "status", "message": f"ツール「{fn_name}」を実行中..."}

            tool_res = await execute_tool(fn_name, args)
            yield {"type": "tool_result", "name": fn_name, "result": tool_res}

            current_messages.append({
                "role": "tool",
                "name": fn_name,
                "content": json.dumps(tool_res, ensure_ascii=False) if not isinstance(tool_res, str) else tool_res,
            })

    if not final_content:
        # Generate final response from current messages
        data = await asyncio.to_thread(call_ollama, current_messages)
        final_content = clean_llm_response(data.get("message", {}).get("content", ""))

    # Save assistant response to DB
    now_utc = datetime.now(timezone.utc).isoformat()
    save_message(
        timestamp=now_utc,
        channel_id=session_id,
        user_id="alice",
        role="assistant",
        content=final_content,
    )

    # Yield completion
    yield {"type": "delta", "content": final_content}
    yield {"type": "done", "full_content": final_content}

    # Asynchronous memory consolidation trigger
    asyncio.create_task(asyncio.to_thread(consolidate_pending_messages))
