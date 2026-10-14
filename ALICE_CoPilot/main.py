"""
ALICE_CoPilot Main Entrypoint.
Orchestrates Discord Bot client, background worker loops, and WebUI internal API server.
"""
import os
import sys
import asyncio
import json
import requests
from pathlib import Path
import discord
from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

load_dotenv()

import config
from attachment_handler import extract_attachments_text
from search_handler import handle_search_message
from tools import TOOLS_SCHEMA, execute_tool
from services.action_guard import detect_intent, build_system_hint, is_hallucinating_action
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
from interfaces.discord_bot import (
    handle_discord_ready,
    handle_discord_message,
)

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
    """Multi-turn tool-calling loop using Ollama OpenAI-compatible /chat/completions API.
    Equipped with rigorous Action Tool Guard and Verification Guard to eradicate hallucinations.
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

    action_tool_names = {
        "create_calendar_event", "update_calendar_event", "delete_calendar_event",
        "create_todo_task", "complete_todo_task", "update_todo_task"
    }
    query_tool_names = {"get_todo_tasks", "get_calendar_events"}

    guard_triggered = False
    executed_action_tools: list[str] = []
    executed_query_tools: list[str] = []

    active_orig_ask = globals().get("original_ask_ollama", original_ask_ollama)

    for turn in range(max_turns):
        data = await asyncio.to_thread(active_orig_ask, current_messages, TOOLS_SCHEMA)
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            # 1. Verification Guard
            if turn == 0 and not guard_triggered and intent.is_verification_query:
                guard_triggered = True
                forced_data = []
                tasks_res = await execute_tool("get_todo_tasks", {"status": "all"})
                cal_res = await execute_tool("get_calendar_events", {})
                forced_data.append(f"【Google Tasks最新実データ】\n{json.dumps(tasks_res, ensure_ascii=False, indent=2)}")
                forced_data.append(f"【Google カレンダー最新実データ】\n{json.dumps(cal_res, ensure_ascii=False, indent=2)}")
                executed_query_tools.extend(["get_todo_tasks", "get_calendar_events"])
                verify_block = "\n\n".join(forced_data)
                current_messages.append({
                    "role": "user",
                    "content": (
                        f"【システム自動照会ガード（必須実データ）】\n"
                        f"推測や嘘の確認報告は厳禁です。以下に最新のAPIから直接取得した実データを提示します。\n"
                        f"必ず以下の実データに該当するタスク/予定が存在するか確認し、事実のみを回答してください。\n\n"
                        f"{verify_block}"
                    ),
                })
                continue

            # 2. Action Guard
            if turn == 0 and not guard_triggered and intent.is_action_query:
                guard_triggered = True
                if intent.is_task_query:
                    tool_hint = "必ず「create_todo_task」「update_todo_task」「complete_todo_task」等のGoogle Tasksツールを直ちに呼び出してください。カレンダーへの登録は禁止です。"
                elif intent.is_cal_query:
                    tool_hint = "必ず「create_calendar_event」「update_calendar_event」「delete_calendar_event」ツールを直ちに呼び出してください。"
                else:
                    tool_hint = "必ず「create_todo_task」または「create_calendar_event」ツールを直ちに呼び出してください。"

                current_messages.append({
                    "role": "user",
                    "content": (
                        f"【システム・アクション強制ガード】\n"
                        f"{tool_hint}\n"
                        f"ツールの呼び出しを実行せずに文章だけで『登録しました』『完了しました』と嘘の報告をすることは固く禁止されています。直ちに該当ツールを自律呼び出ししてください。"
                    ),
                })
                continue

            # 3. Query Guard
            if turn == 0 and not guard_triggered and (intent.is_task_query or intent.is_cal_query):
                guard_triggered = True
                forced_data = []
                if intent.is_task_query or intent.is_cal_query:
                    tasks_res = await execute_tool("get_todo_tasks", {"status": "all"})
                    forced_data.append(f"【Google Tasks実データ】\n{json.dumps(tasks_res, ensure_ascii=False, indent=2)}")
                    executed_query_tools.append("get_todo_tasks")

                if intent.is_cal_query or intent.is_task_query:
                    cal_res = await execute_tool("get_calendar_events", {})
                    forced_data.append(f"【Google カレンダー実データ】\n{json.dumps(cal_res, ensure_ascii=False, indent=2)}")
                    executed_query_tools.append("get_calendar_events")

                context_block = "\n\n".join(forced_data)
                current_messages.append({
                    "role": "user",
                    "content": (
                        f"【システム自動照会ガード（必須実データ）】\n"
                        f"過去の会話履歴や推測による回答は厳禁です。以下に最新のAPIから直接取得した実データを提示します。\n"
                        f"必ず以下の実データのみを根拠として正確に回答してください。\n\n"
                        f"{context_block}"
                    ),
                })
                continue

            content = assistant_msg.get("content", "")

            # Check if LLM is hallucinating action completion without tool execution
            if intent.is_action_query and is_hallucinating_action(content, executed_action_tools):
                if turn < max_turns - 1:
                    current_messages.append(assistant_msg)
                    current_messages.append({
                        "role": "user",
                        "content": (
                            "【システム遮断】タスクまたは予定の操作ツールが実行されていません。\n"
                            "文章だけで『追加しました』『登録しました』と報告することは固く禁止されています。\n"
                            "必ず該当する操作ツールを自律呼び出しして処理を完了させてください。"
                        ),
                    })
                    continue
                else:
                    return "【システム警告】予定またはタスクの操作ツールが実行されなかったため、登録・変更は完了していません。実際の操作を実行するには再度具体的にご指示ください。"

            return content

        current_messages.append(assistant_msg)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            call_id = tc.get("id", "")

            if name in action_tool_names:
                executed_action_tools.append(name)
            if name in query_tool_names:
                executed_query_tools.append(name)

            tool_result = await execute_tool(name, args)
            tool_msg = {
                "role": "tool",
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
            if call_id:
                tool_msg["tool_call_id"] = call_id
            current_messages.append(tool_msg)

    return current_messages[-1].get("content", "") or "処理が完了しました。"


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


# Discord Client Setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    import sys
    this_mod = sys.modules[__name__]
    await handle_discord_ready(client, context=this_mod)


@client.event
async def on_message(message: discord.Message):
    import sys
    this_mod = sys.modules[__name__]
    await handle_discord_message(client, message, context=this_mod)


if __name__ == "__main__":
    if not TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN environment variable is not set.")
        sys.exit(1)

    initialize_database()
    client.run(TOKEN)
