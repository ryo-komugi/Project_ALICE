"""
Assistant (Secretary) Service for ALICE WebUI & CoPilot.
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

    # 1. ユーザー発言の保存
    now_utc = datetime.now(timezone.utc).isoformat()
    save_message(
        timestamp=now_utc,
        channel_id=session_id,
        user_id="web_user",
        role="user",
        content=prompt,
    )

    yield {"type": "status", "message": "コンテキストを確認中..."}

    # 2. 短期会話履歴 & 長期記憶の読み込み
    recent_db_messages = get_recent_messages(channel_id=session_id, limit=10)
    memory_context_str = None

    # 高速バイパス: 日常会話・挨拶・カレンダー/タスク操作なら長期記憶検索判定をスキップ (0.000s)
    action_or_routine = any(kw in prompt for kw in [
        "こんにちは", "おはよう", "こんばんは", "おやすみ", "ありがとう", "どうも", "テスト",
        "予定", "スケジュール", "カレンダー", "タスク", "todo", "動静", "ミーティング", "mtg",
        "登録", "追加", "入れて", "入れといて", "削除", "消して", "変更", "ずらして", "更新",
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

    # メッセージリストの構築
    current_messages = []
    base_sys = get_assistant_system_prompt()
    if memory_context_str:
        base_sys += f"\n\n【ALICEの長期記憶コンテキスト】\n{memory_context_str}"

    current_messages.append({"role": "system", "content": base_sys})

    # 会話履歴を追加
    for role, content in recent_db_messages:
        # 直前の発言は今処理しているpromptなので二重追加に注意
        current_messages.append({"role": role, "content": content})

    # 3. Intent Detection
    create_keywords = ["登録", "追加", "入れて", "入れといて", "入れておいて", "作成", "作って", "セットして", "設定して", "予定入れ", "タスク入れ"]
    move_keywords = ["移動", "ずらして", "変更", "更新", "繰り下げ", "繰り上げ", "延期", "時間変更", "日程変更", "日時の変更"]
    delete_keywords = ["削除", "消して", "取り消し", "キャンセル", "なくして", "消去"]
    task_keywords = ["タスク", "todo", "ToDo", "マイタスク", "業務タスク", "締め切り", "締切", "提〆", "回答〆", "展〆", "動静表", "面談"]
    calendar_keywords = ["カレンダー", "予定", "スケジュール", "動静", "人員動静", "ミーティング", "MTG", "mtg", "出張", "休暇", "全休", "PM休"]
    past_keywords = ["過去", "先週", "先月", "昨日", "おととい", "以前", "前", "昔"]

    is_create = any(kw in prompt for kw in create_keywords)
    is_move = any(kw in prompt for kw in move_keywords)
    is_delete = any(kw in prompt for kw in delete_keywords)
    is_action_query = is_create or is_move or is_delete

    is_task_query = any(kw in prompt for kw in task_keywords)
    is_cal_query = any(kw in prompt for kw in calendar_keywords)
    is_past_query = any(kw in prompt for kw in past_keywords)

    # 新規登録・移動・変更・削除時は初手からツール呼び出しを誘導し、無駄な確認返答ターンを防止
    if is_create and current_messages and current_messages[-1].get("role") == "user":
        if is_task_query and not is_cal_query:
            tool_hint = "ユーザーはタスク（Google Tasks）の登録を求めています。必ず「create_todo_task」ツールのみを直ちに呼び出してください。カレンダーへの二重登録は管理が破綻するため絶対に禁止です。"
        elif is_cal_query and not is_task_query:
            tool_hint = "ユーザーはカレンダー予定の登録を求めています。必ず「create_calendar_event」ツールを直ちに呼び出してください。終日の場合はall_day=trueを指定してください。"
        else:
            tool_hint = "テキスト返答のみで済ませず、必ず「create_calendar_event」または「create_todo_task」ツールを直ちに呼び出してください。"

        current_messages[-1]["content"] += (
            f"\n\n【システム補足：ツール必須呼び出し】\n"
            f"現在日時は {datetime.now().strftime('%Y年%m月%d日 %H:%M')} (JST) です。\n"
            f"{tool_hint}"
        )
    elif (is_move or is_delete) and current_messages and current_messages[-1].get("role") == "user":
        if is_task_query and not is_cal_query:
            act_name = "update_todo_task" if is_move else "complete_todo_task"
            tool_hint = f"ユーザーはタスク（Google Tasks）の変更・完了を求めています。必ず「{act_name}」ツールを直ちに呼び出してください。"
        elif is_cal_query and not is_task_query:
            act_name = "update_calendar_event" if is_move else "delete_calendar_event"
            tool_hint = f"ユーザーはカレンダー予定の変更・削除を求めています。必ず「{act_name}」ツールを直ちに呼び出してください。終日の場合はall_day=trueを指定してください。"
        else:
            tool_hint = "対象がカレンダー予定の場合は「update_calendar_event」「delete_calendar_event」、タスクの場合は「update_todo_task」「complete_todo_task」を直ちに呼び出してください。"

        current_messages[-1]["content"] += (
            f"\n\n【システム補足：ツール必須呼び出し】\n"
            f"現在日時は {datetime.now().strftime('%Y年%m月%d日 %H:%M')} (JST) です。\n"
            f"{tool_hint}"
        )

    guard_triggered = False
    executed_action_tools: list[str] = []

    yield {"type": "status", "message": "思考・ツール実行中..."}

    final_content = ""
    for turn in range(max_turns):
        # ツール呼び出しが必要なコンテキストか判定
        # アクション（登録/変更/削除）時はアクション完了までTOOLS_SCHEMAを維持
        # 照会系は初手またはガード発動時にTOOLS_SCHEMAを提供
        need_tools = (
            (is_action_query and not executed_action_tools)
            or (turn == 0 and (is_task_query or is_cal_query or any(k in prompt for k in ("検索", "会議", "仕様", "メモリ", "負荷")) or "vram" in prompt.lower()))
            or (guard_triggered and not executed_action_tools)
        )
        tools_param = TOOLS_SCHEMA if need_tools else None

        # ツール呼び出しを判定・実行するターンは同期待機で全tool_callsを完全取得し、結果生成ターンでリアルタイムストリーミング
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
                if turn == 0 and not guard_triggered and is_create:
                    guard_triggered = True
                    yield {"type": "status", "message": "【自動登録ガード】ツール実行準備中..."}
                    if is_task_query and not is_cal_query:
                        guard_target = "必ず「create_todo_task」ツールのみを自律呼び出しして登録を実行してください。カレンダーへの登録は行わないでください。"
                    elif is_cal_query and not is_task_query:
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
                if turn == 0 and not guard_triggered and (is_move or is_delete):
                    guard_triggered = True
                    yield {"type": "status", "message": "【自動照会ガード】変更対象を検索中..."}

                    provided_data = {}
                    action_tools_guidance = []

                    check_is_task = is_task_query or not is_cal_query
                    check_is_cal = is_cal_query or not is_task_query

                    if check_is_task:
                        task_res = await execute_tool("get_todo_tasks", {"status": "all"})
                        yield {"type": "tool_result", "name": "get_todo_tasks", "result": task_res}
                        provided_data["tasks"] = task_res
                        if is_move:
                            action_tools_guidance.append("タスク（Google Tasks）の期限や件名を変更する場合は「update_todo_task」")
                        if is_delete:
                            action_tools_guidance.append("タスク（Google Tasks）を完了・消去する場合は「complete_todo_task」")

                    if check_is_cal:
                        cal_args = {}
                        name_match = re.search(r"([一-龥]{2,4})さん", prompt)
                        if name_match:
                            cal_args["query"] = name_match.group(1)
                        elif is_past_query:
                            cal_args["time_min"] = "past"

                        cal_res = await execute_tool("get_calendar_events", cal_args)
                        yield {"type": "tool_result", "name": "get_calendar_events", "result": cal_res}
                        provided_data["calendar_events"] = cal_res
                        if is_move:
                            action_tools_guidance.append("カレンダー予定の日時や終日フラグ等を変更する場合は「update_calendar_event」")
                        if is_delete:
                            action_tools_guidance.append("カレンダー予定を削除する場合は「delete_calendar_event」")

                    tools_guide_str = "、または".join(action_tools_guidance)
                    current_messages.append({
                        "role": "user",
                        "content": (
                            f"【最重要システム指示：操作ツールの自律実行】\n"
                            f"ユーザーは予定またはタスクの変更・移動・削除を求めています（『{prompt}』）。\n"
                            f"現在日時は {datetime.now().strftime('%Y年%m月%d日 %H:%M')} (JST) です。\n"
                            f"以下に最新のAPIから直接取得した実データを提供します。\n"
                            f"対象アイテム（タスクまたはカレンダー予定）を特定し、直ちに適切なツール（{tools_guide_str}）を実行してください。\n"
                            f"「終日」の指定がある場合は、カレンダー予定なら all_day=true を指定してください。\n"
                            f"ツールを実行せずに文章だけで『変更しました』『更新しました』と嘘の報告をすることは厳禁です。\n\n"
                            f"{json.dumps(provided_data, ensure_ascii=False, indent=2)}"
                        ),
                    })
                    continue

                # 3. 照会ガード：初回ターンでタスク・カレンダー照会をスキップした場合の介入
                if turn == 0 and not guard_triggered and (is_task_query or is_cal_query):
                    guard_triggered = True
                    yield {"type": "status", "message": "【自動照会ガード】実データを取得中..."}

                    simulated_calls = []
                    guard_tool_msgs = []

                    if is_task_query:
                        # 過去・完了タスクの明示指定がない限り未完了タスク(needsAction)に絞る
                        task_status = "all" if (is_past_query or any(k in prompt for k in ("完了", "過去", "履歴", "終わった"))) else "needsAction"
                        task_args = {"status": task_status}
                        tasks_res = await execute_tool("get_todo_tasks", task_args)
                        yield {"type": "tool_result", "name": "get_todo_tasks", "result": tasks_res}
                        simulated_calls.append({"id": "call_guard_tasks", "function": {"name": "get_todo_tasks", "arguments": task_args}})
                        guard_tool_msgs.append({
                            "role": "tool",
                            "tool_call_id": "call_guard_tasks",
                            "name": "get_todo_tasks",
                            "content": json.dumps(tasks_res, ensure_ascii=False),
                        })

                    if is_cal_query:
                        if is_past_query:
                            cal_args = {"time_min": "past"}
                        elif any(k in prompt for k in ("今日", "本日")):
                            cal_args = {"days_ahead": 1}
                        else:
                            cal_match = re.search(r"(\d{1,2})[/月](\d{1,2})", prompt)
                            if cal_match:
                                m_int, d_int = int(cal_match.group(1)), int(cal_match.group(2))
                                y_int = datetime.now().year
                                cal_args = {
                                    "time_min": f"{y_int:04d}-{m_int:02d}-{d_int:02d} 00:00",
                                    "time_max": f"{y_int:04d}-{m_int:02d}-{d_int:02d} 23:59",
                                }
                            else:
                                cal_args = {"days_ahead": 7}

                        cal_res = await execute_tool("get_calendar_events", cal_args)
                        yield {"type": "tool_result", "name": "get_calendar_events", "result": cal_res}
                        simulated_calls.append({"id": "call_guard_cal", "function": {"name": "get_calendar_events", "arguments": cal_args}})
                        guard_tool_msgs.append({
                            "role": "tool",
                            "tool_call_id": "call_guard_cal",
                            "name": "get_calendar_events",
                            "content": json.dumps(cal_res, ensure_ascii=False),
                        })

                    current_messages.append({
                        "role": "assistant",
                        "content": "Google カレンダーおよびGoogle Tasksの実データを照会します。",
                        "tool_calls": simulated_calls,
                    })
                    for gtm in guard_tool_msgs:
                        current_messages.append(gtm)
                    continue

                # 4. アクション指示なのにアクションツールが一度も実行されていない場合の検証ガード
                if is_action_query:
                    content_raw = assistant_msg.get("content", "")
                    claim_words = [
                        "登録いたしました", "登録しました", "変更いたしました", "変更しました",
                        "移動いたしました", "移動しました", "削除いたしました", "削除しました",
                        "更新いたしました", "更新しました", "入れました", "登録を実行いたします",
                        "登録します", "追加します", "追加いたしました", "追加しました",
                        "作成します", "作成いたしました", "設定します", "設定いたしました",
                        "処理を行っております", "登録を待機しております", "待機しております"
                    ]
                    is_hallucinating_action = any(cw in content_raw for cw in claim_words)
                    if (is_hallucinating_action or turn < max_turns - 2) and turn < max_turns - 1:
                        yield {"type": "status", "message": "【検証ガード】ツールの実行を強制中..."}
                        current_messages.append(assistant_msg)
                        current_messages.append({
                            "role": "user",
                            "content": (
                                "【重大エラー：操作ツールが未実行です】\n"
                                "ユーザーから指示された予定またはタスクの操作ツール（create_calendar_event / create_todo_task / update_calendar_event / update_todo_task / delete_calendar_event / complete_todo_task）が実行されていません。\n"
                                "ツールを呼び出さずに文章だけで『登録します』『完了しました』等の回答をすることは絶対に許されません。直ちに該当ツールを自律呼び出ししてください。"
                            ),
                        })
                        continue

                    # アクション指示なのに最後までツールが呼ばれなかった場合のフェイルセーフ
                    if not executed_action_tools and any(cw in content_raw for cw in claim_words):
                        content_raw = "申し訳ありません。ご指示いただいた登録処理の自律ツール呼び出しを実行できませんでした。お手数ですが、もう一度ご指示いただくか内容をご確認ください。"

                    final_content = clean_llm_response(content_raw)
                    yield {"type": "delta", "content": final_content}
                    break

                # 5. 一般応答
                content_raw = assistant_msg.get("content", "")
                final_content = clean_llm_response(content_raw)
                yield {"type": "delta", "content": final_content}
                break

        else:
            # リアルタイム・トークンストリーミング (ChatGPT / Gemini 風)
            tool_calls = None
            accumulated_delta = []
            yielded_thinking_status = False

            payload = {
                "model": config.OLLAMA_MODEL,
                "messages": current_messages,
                "stream": True,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"num_ctx": config.OLLAMA_CONTEXT},
            }
            if tools_param:
                payload["tools"] = tools_param

            timeout = aiohttp.ClientTimeout(total=300, sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(config.OLLAMA_URL, json=payload) as resp:
                    resp.raise_for_status()
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            chunk_data = json.loads(line)
                        except Exception:
                            continue

                        msg_chunk = chunk_data.get("message", {})
                        if msg_chunk.get("tool_calls"):
                            if tool_calls is None:
                                tool_calls = []
                                assistant_msg = {"role": "assistant", "content": "".join(accumulated_delta), "tool_calls": []}
                            for tc in msg_chunk.get("tool_calls"):
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

        # ツール呼び出しが発生した場合
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
            if m.get("role") == "assistant" and m.get("content"):
                final_content = clean_llm_response(m.get("content", ""))
                break
        if not final_content:
            final_content = "処理が完了しました。"

    # 4. アシスタント発言の保存
    save_message(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel_id=session_id,
        user_id=None,
        role="assistant",
        content=final_content,
    )

    yield {"type": "done", "full_content": final_content}

    # バックグラウンド記憶統合
    asyncio.create_task(_async_consolidate())


async def _async_consolidate():
    try:
        results = await asyncio.to_thread(consolidate_pending_messages)
        if results:
            await asyncio.to_thread(sync_obsidian, clean=True)
    except Exception as e:
        print(f"[Assistant Background Consolidate Error] {e}")
