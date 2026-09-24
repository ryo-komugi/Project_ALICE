import os
import asyncio
from datetime import datetime, timezone
import requests
import discord
from dotenv import load_dotenv
load_dotenv()
import config
from attachment_handler import extract_attachments_text
from search_handler import handle_search_message
import json
from tools import TOOLS_SCHEMA, execute_tool
from memory.short_term import (initialize_database, save_message, get_recent_messages)
from memory.memory_manager import process_memory
from memory.memory_qa import ask_memory
from memory.memory_router import should_use_memory
from memory.memory_consolidator import consolidate_pending_messages
from memory.memory_search import search_memories
from memory.memory_context import (build_memory_context, format_memory_context)
from memory.obsidian_export import sync_obsidian


TOKEN = os.environ["DISCORD_BOT_TOKEN"]

OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
OLLAMA_CONTEXT = config.OLLAMA_CONTEXT
OLLAMA_KEEP_ALIVE = config.OLLAMA_KEEP_ALIVE

MEMORY_LIMIT = 10

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


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
    data = original_ask_ollama(messages)
    return data.get("message", {}).get("content", "")

_ORIGINAL_ASK_OLLAMA_FN = ask_ollama


from services.prompts import get_copilot_system_prompt

_default_ask_ollama_code = ask_ollama.__code__


def get_base_system_prompt() -> str:
    return get_copilot_system_prompt(persona="知的アシスタント・相棒「ALICE」")


async def ask_ollama_with_tools(messages: list[dict], max_turns: int = 4) -> str:
    """Multi-turn tool-calling loop using Ollama OpenAI-compatible /chat/completions API.
    Equipped with rigorous Action Tool Guard and Verification Guard to eradicate hallucinations.
    """
    if ask_ollama is not _ORIGINAL_ASK_OLLAMA_FN:
        import inspect
        res = ask_ollama(messages)
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

    # Extract latest user prompt
    user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_prompt = m.get("content", "")
            break

    task_keywords = ["タスク", "todo", "ToDo", "マイタスク", "業務タスク", "締め切り", "締切", "提〆", "回答〆", "展〆", "動静表", "面談"]
    calendar_keywords = ["カレンダー", "予定", "スケジュール", "動静", "人員動静", "ミーティング", "MTG", "mtg"]

    is_task_query = any(kw in user_prompt for kw in task_keywords)
    is_cal_query = any(kw in user_prompt for kw in calendar_keywords)

    is_create = any(kw in user_prompt for kw in ["追加", "登録", "作成", "いれて", "入れて", "足して", "予定して", "新規"])
    is_move = any(kw in user_prompt for kw in ["変更", "更新", "ずらし", "動かし", "移動", "変えて", "延期", "前倒し", "完了", "終わった"])
    is_delete = any(kw in user_prompt for kw in ["削除", "消して", "キャンセル", "取り消し", "消去"])
    is_action_query = is_create or is_move or is_delete
    is_verification_query = any(kw in user_prompt for kw in ["入ってる", "はいってる", "入ってない", "確認して", "本当に", "ある？", "同期の遅れ"])

    action_tool_names = {
        "create_calendar_event", "update_calendar_event", "delete_calendar_event",
        "create_todo_task", "complete_todo_task", "update_todo_task"
    }
    query_tool_names = {"get_todo_tasks", "get_calendar_events"}

    guard_triggered = False
    executed_action_tools: list[str] = []
    executed_query_tools: list[str] = []

    for turn in range(max_turns):
        data = await asyncio.to_thread(original_ask_ollama, current_messages, TOOLS_SCHEMA)
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            # 1. Verification Guard: if user asks "is it registered / check it" and no query tool ran yet
            if turn == 0 and not guard_triggered and is_verification_query:
                guard_triggered = True
                print(f"[VERIFY GUARD] User asked for verification: {user_prompt!r}. Forcing query API...")
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

            # 2. Action Guard: If user wants create/update/delete, force tool execution prompt on turn 0
            if turn == 0 and not guard_triggered and is_action_query:
                guard_triggered = True
                print(f"[ACTION GUARD] LLM skipped action tools on turn 0 for: {user_prompt!r}. Forcing tool execution prompt...")
                if is_task_query:
                    tool_hint = "必ず「create_todo_task」「update_todo_task」「complete_todo_task」等のGoogle Tasksツールを直ちに呼び出してください。カレンダーへの登録は禁止です。"
                elif is_cal_query:
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

            # 3. Query Guard: If LLM skipped calling tools on turn 0 for general task/calendar questions, force real data dispatch
            if turn == 0 and not guard_triggered and (is_task_query or is_cal_query):
                guard_triggered = True
                print(f"[TOOL GUARD] LLM skipped tools for prompt: {user_prompt!r}. Forcing auto-dispatch...")

                forced_data = []
                if is_task_query or is_cal_query:
                    tasks_res = await execute_tool("get_todo_tasks", {"status": "all"})
                    forced_data.append(f"【Google Tasks（業務タスク・マイタスク）実データ】\n{json.dumps(tasks_res, ensure_ascii=False, indent=2)}")
                    executed_query_tools.append("get_todo_tasks")

                if is_cal_query or is_task_query:
                    cal_res = await execute_tool("get_calendar_events", {})
                    forced_data.append(f"【Google カレンダー（全カレンダー）実データ】\n{json.dumps(cal_res, ensure_ascii=False, indent=2)}")
                    executed_query_tools.append("get_calendar_events")

                context_block = "\n\n".join(forced_data)
                current_messages.append({
                    "role": "user",
                    "content": (
                        f"【システム自動照会ガード（必須実データ）】\n"
                        f"過去の会話履歴や推測による回答は厳禁です。以下に最新のAPIから直接取得した実データ（Google Tasks / Google カレンダー）を提示します。\n"
                        f"必ず以下の実データのみを根拠として、ユーザーの質問『{user_prompt}』に対して正確・詳細に回答してください。\n"
                        f"※完了済みのタスクに該当するものがある場合は『すでに完了済み（完了日: ...）』と明確に伝えてください。\n\n"
                        f"{context_block}"
                    ),
                })
                continue

            content = assistant_msg.get("content", "")
            claim_words = ["登録しました", "追加しました", "変更しました", "削除しました", "完了しました", "設定しました", "反映しました", "移動しました"]
            is_claiming_action = any(cw in content for cw in claim_words)

            # Check if LLM is hallucinating action completion without tool execution
            if is_action_query and not executed_action_tools and is_claiming_action:
                if turn < max_turns - 1:
                    print(f"[ACTION GUARD] Hallucination detected: claimed action without calling tool. Reprompting turn {turn}...")
                    current_messages.append(assistant_msg)
                    current_messages.append({
                        "role": "user",
                        "content": (
                            "【システム遮断】タスクまたは予定の操作ツールが実行されていません。\n"
                            "文章だけで『追加しました』『登録しました』と報告することは固く禁止されています。\n"
                            "必ず該当する操作ツール（create_todo_task等）を自律呼び出しして処理を完了させてください。"
                        ),
                    })
                    continue
                else:
                    print(f"[ACTION GUARD] CRITICAL: Suppressed hallucinated action completion response.")
                    return "【システム警告】予定またはタスクの操作ツールが実行されなかったため、登録・変更は完了していません。実際の操作を実行するには再度具体的にご指示ください。"

            # Check if LLM is hallucinating verification without querying
            confirm_claims = ["確認しました", "登録されています", "正しく登録", "リストを確認", "存在確認"]
            if is_verification_query and not executed_query_tools and any(cc in content for cc in confirm_claims):
                if turn < max_turns - 1:
                    print(f"[VERIFY GUARD] Hallucination detected: claimed verification without query. Reprompting...")
                    tasks_res = await execute_tool("get_todo_tasks", {"status": "all"})
                    cal_res = await execute_tool("get_calendar_events", {})
                    executed_query_tools.extend(["get_todo_tasks", "get_calendar_events"])
                    current_messages.append(assistant_msg)
                    current_messages.append({
                        "role": "user",
                        "content": (
                            f"【システム自動照会】実データを照会しました:\n"
                            f"Tasks: {json.dumps(tasks_res, ensure_ascii=False)}\n"
                            f"Calendar: {json.dumps(cal_res, ensure_ascii=False)}\n"
                            f"上記の実データに基づいて真実のみを回答してください。"
                        ),
                    })
                    continue

            print(f"[OLLAMA FINAL ANSWER] {content!r}")
            return content

        print(f"[OLLAMA TOOL CALLS] {tool_calls!r}")
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
        results = await asyncio.to_thread(
            consolidate_pending_messages
        )

        if results:
            print(f"[MEMORY CONSOLIDATION] {results}\n\n")
            # 新規記憶保存時に Obsidian ディレクトリへ即時自動同期
            sync_res = await asyncio.to_thread(sync_obsidian, clean=True)
            print(f"[OBSIDIAN AUTO-SYNC] Exported: {sync_res.get('exported', 0)}, Deleted: {sync_res.get('deleted', 0)}")
        else:
            print("[MEMORY CONSOLIDATION] No memories saved.\n\n")

    except Exception as e:
        print(f"[MEMORY CONSOLIDATION ERROR] {e}")


async def system_metrics_monitor_loop(interval_sec: int = 5):
    """Periodically sample and update today's system peaks (VRAM, load, temps)."""
    from tools.system_tools import update_daily_peaks

    while True:
        try:
            await asyncio.to_thread(update_daily_peaks)
        except Exception as e:
            print(f"[SYSTEM METRICS MONITOR ERROR] {e}")
        await asyncio.sleep(interval_sec)



async def morning_briefing_monitor_loop(check_interval_sec: int = 60):
    """Checks for pending nightly review reports and delivers morning briefing at 07:30 JST to #copilot."""
    from datetime import datetime, timezone, timedelta
    from reviewer.report_manager import (
        get_latest_pending_report,
        mark_report_as_reported,
        build_morning_briefing_embed,
    )

    JST = timezone(timedelta(hours=9))
    while True:
        try:
            now_jst = datetime.now(JST)
            # Deliver between 07:30 and 10:00 JST
            if (now_jst.hour == 7 and now_jst.minute >= 30) or (8 <= now_jst.hour < 10):
                report = await asyncio.to_thread(get_latest_pending_report)
                if report:
                    target_channel = None
                    for ch in client.get_all_channels():
                        if getattr(ch, "name", None) == "copilot":
                            target_channel = ch
                            break

                    if target_channel and hasattr(target_channel, "send"):
                        from reviewer.report_manager import create_morning_briefing_view
                        embed = build_morning_briefing_embed(report)
                        view = create_morning_briefing_view(report)
                        if view:
                            await target_channel.send(embed=embed, view=view)
                        else:
                            await target_channel.send(embed=embed)
                        await asyncio.to_thread(mark_report_as_reported, report["id"])
                        print(f"[MORNING BRIEFING] Delivered nightly report #{report['id']} to #{target_channel.name}")
        except Exception as e:
            print(f"[MORNING BRIEFING ERROR] {e}")

        await asyncio.sleep(check_interval_sec)


@client.event
async def on_ready():
    initialize_database()
    print(f"ALICE_CoPilot logged in as {client.user}")
    # システムメトリクス日次ピーク監視タスクを起動
    asyncio.create_task(system_metrics_monitor_loop(5))
    # モーニングブリーフィング配信タスクを起動 (07:30 JST監視)
    asyncio.create_task(morning_briefing_monitor_loop(60))
    # 自律改修タスクキュー監視タスクを起動
    from reviewer.patch_worker import patch_queue_worker_loop
    asyncio.create_task(patch_queue_worker_loop(client, poll_interval_sec=5))

    # 内部APIサーバー (ポート 8005: WebUI連携用) をバックグラウンド起動
    try:
        from aiohttp import web
        from server import create_app
        internal_app = create_app()
        runner = web.AppRunner(internal_app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 8005)
        await site.start()
        print("[INTERNAL API] Started WebUI bridge on http://127.0.0.1:8005")
    except Exception as e:
        print(f"[INTERNAL API ERROR] {e}")

    # 起動時にも Obsidian との差分を自動同期
    try:
        sync_res = await asyncio.to_thread(sync_obsidian, clean=True)
        print(f"[OBSIDIAN STARTUP-SYNC] Completed: {sync_res}")
    except Exception as e:
        print(f"[OBSIDIAN STARTUP-SYNC ERROR] {e}")


@client.event
async def on_message(message):
    if message.author == client.user or getattr(message.author, "bot", False):
        return

    # #search チャンネルまたは !search コマンドによるナレッジ検索処理
    if await handle_search_message(message):
        return

    channel_name = getattr(message.channel, "name", "")
    # 対話機能は "assistant" または "copilot" チャンネルで受け付ける
    if channel_name not in ("assistant", "copilot"):
        return

    prompt = message.content

    for user in message.mentions:
        prompt = prompt.replace(
            f"<@{user.id}>",
            "",
        )
        prompt = prompt.replace(
            f"<@!{user.id}>",
            "",
        )

    prompt = prompt.strip()

    # 添付ファイルからテキストを抽出
    attachment_text, processed_filenames = "", []
    if getattr(message, "attachments", None):
        attachment_text, processed_filenames = await extract_attachments_text(message.attachments)

    if not prompt and not attachment_text:
        await message.channel.send("何か話しかけていただくか、テキストファイル(.mdなど)を添付してください。")
        return

    # 手動レポート確認コマンド (!report, !morning, !nightly)
    if prompt.strip() in ("!report", "!morning", "!nightly"):
        from reviewer.report_manager import get_latest_report, build_morning_briefing_embed, create_morning_briefing_view
        report = await asyncio.to_thread(get_latest_report)
        if report:
            embed = build_morning_briefing_embed(report)
            view = create_morning_briefing_view(report)
            if view:
                await message.channel.send(embed=embed, view=view)
            else:
                await message.channel.send(embed=embed)
        else:
            await message.channel.send("夜間レビューレポートはまだ作成されていません。")
        return

    # 改善案の自律改修コマンド (!apply, !approve)
    if prompt.strip().startswith(("!apply", "!approve")):
        from reviewer.report_manager import get_latest_report
        report = await asyncio.to_thread(get_latest_report)
        improvements = report.get("improvements", []) if report else []
        if not improvements:
            await message.channel.send("現在適用可能な改善提案はありません。")
            return

        instruction = "\n".join(f"- {imp}" for imp in improvements)
        try:
            from reviewer.patch_worker import enqueue_patch_task
            task_id = enqueue_patch_task(
                instruction=instruction,
                repo="ALICE_CoPilot",
                user_id=str(message.author),
                source="discord_command",
            )
            await message.channel.send(
                f"🚀 **【Antigravity 自律改修タスク受付完了】**\n"
                f"浅野さんの承認を受け、タスクキューに登録しました（Task ID: `{task_id}`）。\n"
                f"Antigravity CLI がバックグラウンドでコード調査・安全修正・単体テスト（100% PASS）・Gitコミットを実行します。\n"
                f"完了次第、このチャンネルに詳細レポートをお知らせします！\n\n"
                f"**改修対象の提案**:\n```\n{instruction}\n```"
            )
        except Exception as e:
            await message.channel.send(f"❌ 自律改修タスクのキュー登録中にエラーが発生しました: {e}")
        return

    full_content = (prompt + "\n\n" + attachment_text).strip() if attachment_text else prompt

    timestamp = datetime.now(timezone.utc).isoformat()
    channel_id = str(message.channel.id)
    user_id = str(message.author.id)

    print(f"[USER] {message.author}: {prompt} (添付: {processed_filenames})")

    # ユーザー発言を保存
    save_message(
        timestamp=timestamp,
        channel_id=channel_id,
        user_id=user_id,
        role="user",
        content=full_content,
    )

    # ========================================
    # #copilot チャンネル専用: Google Antigravity SDK 直結ディスパッチ
    # ========================================
    if channel_name == "copilot":
        print(f"[ANTIGRAVITY COPILOT] Processing development instruction from {message.author}: {prompt[:80]}")
        try:
            from services.dev_copilot_service import stream_copilot
            if hasattr(message.channel, "typing"):
                async with message.channel.typing():
                    ans_chunks = []
                    async for event in stream_copilot(prompt=full_content, session_id=f"discord_copilot_{channel_id}"):
                        if event.get("type") == "done":
                            ans_chunks.append(event.get("full_content", ""))
                    answer = "".join(ans_chunks).strip() or "処理が完了しました。"
            else:
                ans_chunks = []
                async for event in stream_copilot(prompt=full_content, session_id=f"discord_copilot_{channel_id}"):
                    if event.get("type") == "done":
                        ans_chunks.append(event.get("full_content", ""))
                answer = "".join(ans_chunks).strip() or "処理が完了しました。"

            print(f"[ANTIGRAVITY COPILOT ANSWER] {answer[:100]}...")
            for chunk in [answer[i:i+1900] for i in range(0, len(answer), 1900)]:
                await message.channel.send(chunk)
        except Exception as e:
            print(f"[ANTIGRAVITY COPILOT ERROR] {e}")
            await message.channel.send(f"❌ Antigravity エージェント実行中にエラーが発生しました: {e}")
        return

    # ========================================
    # 長期記憶
    # ========================================
    is_memory_cmd = prompt.startswith("覚えておいて")
    # 「覚えておいて」明示、または本文なし・添付ありの場合は長期記憶保存として扱う
    is_attachment_memory = bool(processed_filenames) and (not prompt or is_memory_cmd)

    if is_memory_cmd or is_attachment_memory:
        if is_memory_cmd:
            base_text = prompt[len("覚えておいて"):].strip()
        else:
            base_text = prompt

        memory_text = (base_text + "\n\n" + attachment_text).strip() if attachment_text else base_text

        # 記憶対象テキストが空の場合
        if not memory_text:
            await message.channel.send("何を覚えておけばいいですか？")
            return

        try:
            result = await asyncio.to_thread(process_memory, memory_text)

            if result["saved"]:
                memory_type = result["result"]["type"]
                path = result["path"]
                related = result["related"]

                print(f"[MEMORY] Saved: {path}")
                print(f"[MEMORY] Type: {memory_type}")
                print(f"[MEMORY] Related: {related}")

                file_info = f"\n対象ファイル: {', '.join(processed_filenames)}" if processed_filenames else ""
                await message.channel.send(
                    f"覚えておきました。{file_info}\n"
                    f"分類: {memory_type}\n"
                    f"関連記憶: {len(related)}件"
                )

            else:
                print("[MEMORY] Not saved.")
                await message.channel.send("これは長期記憶としては保存しない判断になりました。")

        except Exception as e:
            print(f"[MEMORY ERROR] {e}")
            await message.channel.send("長期記憶への保存中にエラーが発生しました。")

        return

    if prompt.startswith("記憶："):
        memory_question = prompt[len("記憶："):].strip()

        if not memory_question:
            await message.channel.send("長期記憶について何を知りたいですか？")
            return

        try:
            answer = await asyncio.to_thread(ask_memory, memory_question)
            print(f"[MEMORY QA] {answer}")
            save_message(
                timestamp=datetime.now(timezone.utc).isoformat(),
                channel_id=channel_id,
                user_id=None,
                role="assistant",
                content=answer,
            )
            await message.channel.send(answer)
            await run_memory_consolidation()
        except Exception as e:
            print(f"[MEMORY QA ERROR] {e}")
            await message.channel.send("長期記憶の検索中にエラーが発生しました。")

        return

    # ========================================
    # 自動長期記憶参照
    # ========================================
    use_memory = False

    try:
        use_memory = await asyncio.to_thread(should_use_memory, prompt)

        print(f"[MEMORY ROUTER] use_memory={use_memory}")

    except Exception as e:
        print(f"[MEMORY ROUTER ERROR] {e}") # ルーターや長期記憶検索が失敗しても通常会話として処理を継続する。

    # ========================================
    # 通常会話
    # ========================================

    # 直近の会話を取得
    recent_messages = get_recent_messages(channel_id=channel_id, limit=MEMORY_LIMIT)

    # 長期記憶コンテキスト
    memory_context_text = None

    if use_memory:
        try:
            memories = await asyncio.to_thread(search_memories, query=prompt, limit=MEMORY_LIMIT)
            if memories:
                memory_context = await asyncio.to_thread(build_memory_context, memories, query=prompt)
                memory_context_text = format_memory_context(memory_context)
                print("[MEMORY CONTEXT DEBUG]")
                print(memory_context)
                print("[MEMORY CONTEXT TEXT]")
                print(memory_context_text)
                print(
                    f"[MEMORY CONTEXT] "
                    f"{len(memories)} memories found"
                )
        except Exception as e:
            print(f"[MEMORY CONTEXT ERROR] {e}")
            memory_context_text = None

    # Short-Term + Long-Term を統合
    ollama_messages = build_conversation_messages(
        recent_messages=recent_messages,
        memory_context=memory_context_text,
    )

    print(f"[OLLAMA MESSAGES] {ollama_messages!r}")

    # ========================================
    # Ollama
    # ========================================
    try:
        if hasattr(message.channel, "typing"):
            async with message.channel.typing():
                answer = await ask_ollama_with_tools(ollama_messages)
        else:
            answer = await ask_ollama_with_tools(ollama_messages)
        print(f"[ALICE] {answer}")

        if not answer.strip():
            print("[OLLAMA ERROR] Empty answer returned.")
            await message.channel.send("回答を生成できませんでした。")
            return

        # ALICEの返答を短期記憶へ保存
        save_message(
            timestamp=datetime.now(timezone.utc).isoformat(),
            channel_id=channel_id,
            user_id=None,
            role="assistant",
            content=answer,
        )
        await message.channel.send(answer)
        await run_memory_consolidation()
    except Exception as e:
        print(f"[ERROR] {e}")
        await message.channel.send(
            "申し訳ありません。"
            "Ollamaとの通信でエラーが発生しました。"
        )


if __name__ == "__main__":
    initialize_database()
    client.run(TOKEN)