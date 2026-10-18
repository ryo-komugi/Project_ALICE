"""
Assistant (Secretary) Service for ALICE WebUI & CoPilot (dev).
Handles daily secretary workflows: Google Calendar, Google Tasks, Meeting Search,
System Metrics, and Memory QA with Tool Guard.
"""
import asyncio
import json
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
import aiohttp
import config
from tools import TOOLS_SCHEMA, execute_tool
from services.action_guard import detect_intent, build_system_hint, is_hallucinating_action
from memory.short_term import save_message, get_recent_messages
from memory.memory_router import should_use_memory
from memory.memory_context import build_memory_context, format_memory_context
from memory.memory_consolidator import consolidate_pending_messages
from memory.obsidian_export import sync_obsidian
from services.antigravity_manager import increment_quota_usage


def clean_llm_response(text: str) -> str:
    """Removes model reasoning token artifacts like 'thought\n<channel|>' or '<thought>...'."""
    if not text:
        return ""
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^(?:\s*thought\s*)?(?:<channel\|>|<thought>)+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*thought\s*\n+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<channel\|>", "", cleaned)
    return cleaned.strip()


from services.prompts import get_copilot_system_prompt


def get_assistant_system_prompt() -> str:
    return get_copilot_system_prompt(persona="知的アシスタント・専属秘書「ALICE」")


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

    action_or_routine = any(kw in prompt for kw in [
        "こんにちは", "おはよう", "こんばんは", "おやすみ", "ありがとう", "どうも", "テスト",
        "予定", "スケジュール", "カレンダー", "タスク", "todo", "動静", "ミーティング", "mtg",
        "登録", "追加", "入れて", "入れといて", "削除", "消して", "変更", "ずらして", "更新",
        "完了", "終わった", "済んだ", "完了にして",
        "何時", "天気", "今何時", "今日何日", "計算", "明日の予定", "今日の予定"
    ])
    has_explicit_memory_kw = any(kw in prompt for kw in ["前", "以前", "昔", "仕様", "設計", "なぜ", "理由", "覚えて", "方針", "決定", "経緯", "ALICE", "記憶", "過去"])

    if not action_or_routine or has_explicit_memory_kw:
        if should_use_memory(prompt):
            yield {"type": "status", "message": "長期記憶を検索中..."}
            try:
                from memory.memory_search import search_memories
                raw_memories = await asyncio.to_thread(search_memories, prompt)
                if raw_memories:
                    matched_context = await asyncio.to_thread(build_memory_context, raw_memories, query=prompt)
                    if matched_context:
                        memory_context_str = format_memory_context(matched_context)
            except Exception as e:
                print(f"[Assistant Memory Context Error] {e}")

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

    guard_triggered = False
    executed_action_tools: list[str] = []

    yield {"type": "status", "message": "思考・ツール実行中..."}

    final_content = ""
    for turn in range(max_turns):
        need_tools = (
            (intent.is_action_query and not executed_action_tools)
            or (turn == 0 and (intent.is_task_query or intent.is_cal_query or any(k in prompt for k in ("検索", "会議", "仕様", "メモリ", "負荷")) or "vram" in prompt.lower()))
            or (intent.is_action_query and guard_triggered and not executed_action_tools)
        )
        tools_param = TOOLS_SCHEMA if need_tools else None
        need_sync_verification = bool(tools_param)

        tool_calls = None
        assistant_msg = {}

        if need_sync_verification:
            data = await asyncio.to_thread(call_ollama, current_messages, tools_param)
            assistant_msg = data.get("message", {})
            tool_calls = assistant_msg.get("tool_calls")
            increment_quota_usage(cost_weight=1)

            if not tool_calls:
                # 1. 新規登録ガード
                if turn == 0 and not guard_triggered and intent.is_create:
                    guard_triggered = True
                    yield {"type": "status", "message": "【自動登録ガード】ツール実行準備中..."}
                    if intent.is_task_query and not intent.is_cal_query:
                        guard_target = "必ず「create_todo_task」ツールのみを自律呼び出しして登録を実行してください。カレンダーへの登録は行わないでください。"
                    elif intent.is_cal_query and not intent.is_task_query:
                        guard_target = "必ず「create_calendar_event」ツールを自律呼び出しして登録を実行してください。"
                    else:
                        guard_target = "必ず「create_calendar_event」または「create_todo_task」ツールを自律呼び出しして登録を実行してください。"

                    current_messages.append({
                        "role": "user",
                        "content": (
                            f"【最重要システム指示：新規登録ツール必須実行】\n"
                            f"ユーザーは新規予定またはタスクの登録を求めています（『{prompt}』）。\n"
                            f"現在日時は {datetime.now().strftime('%Y年%m月%d日 %H:%M')} (JST) です。\n"
                            f"{guard_target}\n"
                            f"ツールを呼び出さずに文章だけで『登録いたしました』と嘘をつくことは絶対に許されません。"
                        ),
                    })
                    continue

                # 2. 移動・削除ガード
                if turn == 0 and not guard_triggered and (intent.is_update or intent.is_delete):
                    guard_triggered = True
                    yield {"type": "status", "message": "【自動照会ガード】変更対象を検索中..."}

                    provided_data = {}
                    action_tools_guidance = []

                    check_is_task = intent.is_task_query or not intent.is_cal_query
                    check_is_cal = intent.is_cal_query or not intent.is_task_query

                    if check_is_task:
                        task_res = await execute_tool("get_todo_tasks", {"status": "all"})
                        yield {"type": "tool_result", "name": "get_todo_tasks", "result": task_res}
                        provided_data["tasks"] = task_res
                        if intent.is_update:
                            action_tools_guidance.append("タスクの期限や件名を変更する場合は「update_todo_task」")
                        if intent.is_delete:
                            action_tools_guidance.append("タスクを完了・消去する場合は「complete_todo_task」")

                    if check_is_cal:
                        cal_args = {}
                        if intent.is_past_query:
                            cal_args["time_min"] = "past"

                        cal_res = await execute_tool("get_calendar_events", cal_args)
                        yield {"type": "tool_result", "name": "get_calendar_events", "result": cal_res}
                        provided_data["calendar_events"] = cal_res
                        if intent.is_update:
                            action_tools_guidance.append("カレンダー予定の日時や件名を変更する場合は「update_calendar_event」")
                        if intent.is_delete:
                            action_tools_guidance.append("カレンダー予定を削除する場合は「delete_calendar_event」")

                    tools_guide_str = "、または".join(action_tools_guidance)
                    current_messages.append({
                        "role": "user",
                        "content": (
                            f"【最重要システム指示：操作ツールの自律実行】\n"
                            f"ユーザーは対象の変更または削除を求めています（『{prompt}』）。\n"
                            f"以下に最新の実データを提示します:\n"
                            f"{json.dumps(provided_data, ensure_ascii=False, indent=2)}\n\n"
                            f"上記の実データを確認した上で、{tools_guide_str}を自律呼び出しして処理を完了させてください。\n"
                            f"実際にツールを呼び出さずに文章だけで完了を報告することは固く禁じられています。"
                        ),
                    })
                    continue

                content = assistant_msg.get("content", "")
                if intent.is_action_query and is_hallucinating_action(content, executed_action_tools):
                    if turn < max_turns - 1:
                        yield {"type": "status", "message": "【ガード発動】ツール実行を再要請中..."}
                        current_messages.append(assistant_msg)
                        current_messages.append({
                            "role": "user",
                            "content": (
                                "【システム警告】タスクまたは予定の操作ツールが実行されていません。\n"
                                "文章だけで完了報告をすることは固く禁止されています。\n"
                                "必ず該当する操作ツールを自律呼び出しして処理を完了させてください。"
                            ),
                        })
                        continue
                    else:
                        final_content = "【システム警告】予定またはタスクの操作ツールが実行されなかったため、登録・変更は完了していません。実際の操作を実行するには再度具体的にご指示ください。"
                        break

                final_content = clean_llm_response(content)
                break

        else:
            yield {"type": "status", "message": "回答を生成中..."}
            stream_payload = {
                "model": config.OLLAMA_MODEL,
                "messages": current_messages,
                "stream": True,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {
                    "num_ctx": config.OLLAMA_CONTEXT,
                },
            }
            increment_quota_usage(cost_weight=1)

            accumulated_delta = []
            tool_calls = []
            assistant_msg = {"role": "assistant", "content": "", "tool_calls": []}
            yielded_thinking_status = False

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
                async with session.post(config.OLLAMA_URL, json=stream_payload) as resp:
                    resp.raise_for_status()
                    async for line_bytes in resp.content:
                        line = line_bytes.decode("utf-8").strip()
                        if not line:
                            continue
                        chunk = json.loads(line)
                        msg_chunk = chunk.get("message", {})

                        if msg_chunk.get("tool_calls"):
                            for tc in msg_chunk["tool_calls"]:
                                tool_calls.append(tc)
                                assistant_msg["tool_calls"].append(tc)

                        thinking_delta = msg_chunk.get("thinking", "")
                        if thinking_delta and not yielded_thinking_status:
                            yielded_thinking_status = True
                            yield {"type": "status", "message": "思考・回答を整理中..."}

                        delta = msg_chunk.get("content", "")
                        if delta and not tool_calls:
                            accumulated_delta.append(delta)
                            yield {"type": "delta", "content": delta}

            if not tool_calls:
                final_content = clean_llm_response("".join(accumulated_delta))
                break

        current_messages.append(assistant_msg)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            call_id = tc.get("id", "")

            yield {"type": "tool_call", "name": name, "args": args}
            yield {"type": "status", "message": f"ツール実行中: {name}..."}

            tool_result = await execute_tool(name, args)
            yield {"type": "tool_result", "name": name, "result": tool_result}

            if name in ("create_calendar_event", "update_calendar_event", "delete_calendar_event", "create_todo_task", "complete_todo_task", "update_todo_task"):
                executed_action_tools.append(name)

            tool_msg = {
                "role": "tool",
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
            if call_id:
                tool_msg["tool_call_id"] = call_id
            current_messages.append(tool_msg)

    if not final_content:
        for m in reversed(current_messages):
            if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
                final_content = clean_llm_response(m.get("content", ""))
                break
        if not final_content:
            final_content = "処理が完了しました。"

    save_message(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel_id=session_id,
        user_id=None,
        role="assistant",
        content=final_content,
    )

    yield {"type": "done", "full_content": final_content}

    asyncio.create_task(_async_consolidate())


async def ask_assistant(prompt: str, session_id: str = "assistant", max_turns: int = 4) -> str:
    """Non-streaming helper for assistant workflow."""
    final_text = ""
    async for event in stream_assistant(prompt=prompt, session_id=session_id, max_turns=max_turns):
        if event.get("type") == "done":
            final_text = event.get("full_content", "")
    return final_text or "処理が完了しました。"


async def ask_assistant_messages(messages: list[dict], max_turns: int = 4) -> str:
    """Message-list based compatibility wrapper for legacy tests and callers."""
    latest_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            latest_prompt = m.get("content", "")
            break
    if not latest_prompt:
        return "メッセージを入力してください。"
    return await ask_assistant(prompt=latest_prompt, session_id="test_session", max_turns=max_turns)


async def _async_consolidate():
    try:
        results = await asyncio.to_thread(consolidate_pending_messages)
        if results:
            await asyncio.to_thread(sync_obsidian, clean=True)
    except Exception as e:
        print(f"[Assistant Background Consolidate Error] {e}")
