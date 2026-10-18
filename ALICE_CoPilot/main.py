"""
ALICE_CoPilot Main Entrypoint.
Orchestrates internal API server (port 8005 for WebUI/Core Portal),
background memory sync/workers, and optional Discord Bot client.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

load_dotenv()

import config
from tools import TOOLS_SCHEMA, execute_tool
from services.action_guard import detect_intent, build_system_hint
from memory.short_term import initialize_database, save_message, get_recent_messages
from memory.memory_manager import process_memory
from memory.memory_qa import ask_memory
from memory.memory_router import should_use_memory
from memory.memory_consolidator import consolidate_pending_messages
from memory.memory_search import search_memories
from memory.memory_context import build_memory_context, format_memory_context
from memory.obsidian_export import sync_obsidian
from services.prompts import get_copilot_system_prompt
from server import start_internal_api_server
from services.background_workers import (
    system_metrics_monitor_loop,
    morning_briefing_monitor_loop,
    start_background_tasks,
)

logger = logging.getLogger("ALICE_CoPilot")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
OLLAMA_CONTEXT = config.OLLAMA_CONTEXT
OLLAMA_KEEP_ALIVE = config.OLLAMA_KEEP_ALIVE
MEMORY_LIMIT = 10


def original_ask_ollama(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_ctx": OLLAMA_CONTEXT,
        },
    }
    if tools is not None:
        payload["tools"] = tools

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def ask_ollama(messages: list[dict]) -> str:
    fn = globals().get("original_ask_ollama", original_ask_ollama)
    data = fn(messages)
    return data.get("message", {}).get("content", "")


_ORIGINAL_ASK_OLLAMA_FN = ask_ollama


def get_base_system_prompt() -> str:
    return get_copilot_system_prompt(persona="知的アシスタント・相棒「ALICE」")


async def ask_ollama_with_tools(messages: list[dict], max_turns: int = 4) -> str:
    """Multi-turn tool-calling loop using Ollama API.
    Equipped with intent hints and factual system verification.
    """
    import inspect
    current_ask_ollama = globals().get("ask_ollama", ask_ollama)
    if current_ask_ollama is not _ORIGINAL_ASK_OLLAMA_FN:
        res = current_ask_ollama(messages)
        if inspect.iscoroutine(res):
            return await res
        return res

    current_messages = list(messages)
    has_system = any(m.get("role") == "system" for m in current_messages)
    if not has_system:
        base_sys = get_base_system_prompt()
        current_messages.insert(0, {
            "role": "system",
            "content": base_sys,
        })

    user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_prompt = m.get("content", "")
            break

    intent = detect_intent(user_prompt)
    initial_hint = build_system_hint(intent)
    if initial_hint and current_messages and current_messages[-1].get("role") == "user":
        current_messages[-1]["content"] += f"\n\n{initial_hint}"

    active_orig_ask = globals().get("original_ask_ollama", original_ask_ollama)

    for turn in range(max_turns):
        data = await asyncio.to_thread(active_orig_ask, current_messages, TOOLS_SCHEMA)
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            content = assistant_msg.get("content", "")
            return content.strip()

        # Execute tool calls
        current_messages.append({
            "role": "assistant",
            "content": assistant_msg.get("content", ""),
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            call_id = tc.get("id", "call_1")
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

            tool_res = await execute_tool(fn_name, args)

            current_messages.append({
                "role": "tool",
                "name": fn_name,
                "content": json.dumps(tool_res, ensure_ascii=False) if not isinstance(tool_res, str) else tool_res,
            })

    final_data = await asyncio.to_thread(active_orig_ask, current_messages)
    final_content = final_data.get("message", {}).get("content", "")
    return final_content.strip()


def build_conversation_messages(recent_messages: list[tuple[str, str]], memory_context: str | None = None) -> list[dict]:
    messages = []
    if memory_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "以下はALICE_CoPilotの長期記憶です。\n"
                    "Memoryには現在有効な情報と、過去の情報・矛盾情報が含まれています。\n\n"
                    "【重要なルール】\n"
                    "- Primary Memoryは現在有効な情報として扱ってください。\n"
                    "- Superseded Memoryは過去の情報であり、現在の事実として使用しないでください。\n"
                    "- Conflicting MemoryはPrimary Memoryと矛盾する情報です。\n"
                    "- Conflicting Memoryは現在の事実として採用しないでください。\n"
                    "- 現在の事実を回答する場合は、Primary Memoryを優先してください。\n"
                    "- Primary MemoryとConflicting Memoryが矛盾している場合でも、Conflicting Memoryを根拠に回答を変更しないでください。\n\n"
                    f"{memory_context}"
                ),
            }
        )

    messages.extend(
        {
            "role": role,
            "content": content,
        }
        for role, content in recent_messages
    )
    return messages


async def run_memory_consolidation():
    try:
        results = await asyncio.to_thread(consolidate_pending_messages)
        if results:
            sync_res = await asyncio.to_thread(sync_obsidian, clean=True)
    except Exception as e:
        print(f"[MEMORY CONSOLIDATION ERROR] {e}")


# Optional Discord Bot Forwarding & Compatibility Handlers
def get_discord_client():
    try:
        from interfaces.discord.bot import create_discord_client
        return create_discord_client()
    except (ImportError, Exception):
        return None

client = get_discord_client()

async def on_ready():
    from interfaces.discord.bot import handle_discord_ready
    await handle_discord_ready(client, context=sys.modules[__name__])

async def on_message(message):
    from interfaces.discord.bot import handle_discord_message
    active_client = globals().get("client", client)
    await handle_discord_message(active_client, message, context=sys.modules[__name__])


async def start_main(port: int = 8005):
    """Main async orchestrator."""
    initialize_database()
    print("[ALICE_CoPilot] Database initialized.")

    # Obsidian差分自動同期
    try:
        sync_res = await asyncio.to_thread(sync_obsidian, clean=True)
        print(f"[OBSIDIAN STARTUP-SYNC] Completed: {sync_res}")
    except Exception as e:
        print(f"[OBSIDIAN STARTUP-SYNC ERROR] {e}")

    tasks = []

    # 1. Start internal API server (FastAPI on port 8005)
    api_task = asyncio.create_task(start_internal_api_server(port=port))
    tasks.append(api_task)
    print(f"[ALICE_CoPilot] Internal API Server running on port {port}.")

    # 2. Optional: Discord Bot
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if bot_token:
        try:
            from interfaces.discord.bot import run_discord_bot
            print("[ALICE_CoPilot] DISCORD_BOT_TOKEN detected. Starting Discord Bot...")
            tasks.append(asyncio.create_task(run_discord_bot(bot_token)))
        except Exception as e:
            print(f"[ALICE_CoPilot] Could not start Discord Bot: {e}")
    else:
        print("[ALICE_CoPilot] DISCORD_BOT_TOKEN not set. Running in API-only mode.")

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    try:
        asyncio.run(start_main(port=port))
    except KeyboardInterrupt:
        print("[ALICE_CoPilot] Shutting down.")
