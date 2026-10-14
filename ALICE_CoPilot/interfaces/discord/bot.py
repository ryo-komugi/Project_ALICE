"""
Discord Bot Client & Event Dispatcher for ALICE_CoPilot.
Provides optional Discord integration: knowledge search, Antigravity dev mode,
long-term memory, and conversation.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import config
from interfaces.discord.attachments import extract_attachments_text
from interfaces.discord.search import handle_search_message
from interfaces.discord.views import (
    build_morning_briefing_embed,
    create_morning_briefing_view,
)


async def handle_discord_ready(client: discord.Client, context=None):
    """Handles Discord client on_ready event."""
    if context is None:
        import main as context

    if hasattr(context, "initialize_database"):
        context.initialize_database()

    print(f"ALICE_CoPilot logged in as {client.user}")

    # バックグラウンド監視ループ起動
    if hasattr(context, "start_background_tasks"):
        await context.start_background_tasks(client)

    # 内部APIサーバー (ポート 8005) 起動確認
    if hasattr(context, "start_internal_api_server"):
        asyncio.create_task(context.start_internal_api_server(port=8005))

    # Obsidian差分自動同期
    if hasattr(context, "sync_obsidian"):
        try:
            sync_res = await asyncio.to_thread(context.sync_obsidian, clean=True)
            print(f"[OBSIDIAN STARTUP-SYNC] Completed: {sync_res}")
        except Exception as e:
            print(f"[OBSIDIAN STARTUP-SYNC ERROR] {e}")


async def handle_discord_message(client: discord.Client, message: discord.Message, context=None):
    """Handles incoming Discord messages."""
    if context is None:
        import main as context

    bot_user = getattr(client, "user", None)
    if message.author == bot_user or getattr(message.author, "bot", False):
        return

    # #search チャンネルまたは !search コマンドによるナレッジ検索処理
    search_fn = getattr(context, "handle_search_message", handle_search_message)
    if await search_fn(message):
        return

    channel_name = getattr(message.channel, "name", "")
    if channel_name not in ("assistant", "copilot"):
        return

    prompt = message.content
    for user in message.mentions:
        prompt = prompt.replace(f"<@{user.id}>", "")
        prompt = prompt.replace(f"<@!{user.id}>", "")
    prompt = prompt.strip()

    attachment_text, processed_filenames = "", []
    if getattr(message, "attachments", None):
        extract_fn = getattr(context, "extract_attachments_text", extract_attachments_text)
        attachment_text, processed_filenames = await extract_fn(message.attachments)

    if not prompt and not attachment_text:
        await message.channel.send("何か話しかけていただくか、テキストファイル(.mdなど)を添付してください。")
        return

    # 手動レポート確認コマンド (!report, !morning, !nightly)
    if prompt.strip() in ("!report", "!morning", "!nightly"):
        from reviewer.report_manager import get_latest_report
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
        user_name = str(message.author)
        try:
            from reviewer.patch_worker import enqueue_patch_task
            task_id = enqueue_patch_task(
                instruction=instruction,
                repo="ALICE_CoPilot",
                user_id=user_name,
                source="discord_command",
            )
            await message.channel.send(
                f"🚀 **【Antigravity 自律改修タスク受付完了】**\n"
                f"ユーザー（{user_name}）の承認を受け、タスクキューに登録しました（Task ID: `{task_id}`）。\n"
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
    if hasattr(context, "save_message"):
        context.save_message(
            timestamp=timestamp,
            channel_id=channel_id,
            user_id=user_id,
            role="user",
            content=full_content,
        )

    # #copilot チャンネル専用: Google Antigravity SDK 直結ディスパッチ
    if channel_name == "copilot":
        print(f"[ANTIGRAVITY COPILOT] Processing development instruction from {message.author}: {prompt[:80]}")
        try:
            from services.dev_copilot_service import stream_copilot
            ans_chunks = []
            if hasattr(message.channel, "typing"):
                async with message.channel.typing():
                    async for event in stream_copilot(prompt=full_content, session_id=f"discord_copilot_{channel_id}"):
                        if event.get("type") == "done":
                            ans_chunks.append(event.get("full_content", ""))
            else:
                async for event in stream_copilot(prompt=full_content, session_id=f"discord_copilot_{channel_id}"):
                    if event.get("type") == "done":
                        ans_chunks.append(event.get("full_content", ""))
            answer = "".join(ans_chunks).strip() or "処理が完了しました。"

            if hasattr(context, "save_message"):
                context.save_message(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    channel_id=channel_id,
                    user_id="alice",
                    role="assistant",
                    content=answer,
                )

            for chunk in [answer[i:i + 1900] for i in range(0, len(answer), 1900)]:
                await message.channel.send(chunk)
            return
        except Exception as e:
            print(f"[ANTIGRAVITY COPILOT ERROR] {e}")
            await message.channel.send(f"❌ 開発支援エージェントの実行中にエラーが発生しました: {e}")
            return

    # 長期記憶保存（「覚えておいて」）
    is_memory_cmd = prompt.startswith("覚えておいて")
    is_attachment_memory = bool(processed_filenames) and (not prompt or is_memory_cmd)

    if (is_memory_cmd or is_attachment_memory) and hasattr(context, "process_memory"):
        base_text = prompt[len("覚えておいて"):].strip() if is_memory_cmd else prompt
        memory_text = (base_text + "\n\n" + attachment_text).strip() if attachment_text else base_text
        if not memory_text:
            await message.channel.send("何を覚えておけばいいですか？")
            return

        try:
            result = await asyncio.to_thread(context.process_memory, memory_text)
            if result.get("saved"):
                memory_type = result["result"]["type"]
                path = result["path"]
                related = result["related"]
                print(f"[MEMORY] Saved: {path}, Type: {memory_type}, Related: {related}")
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

    # 長期記憶QA（「記憶：」）
    if prompt.startswith("記憶：") and hasattr(context, "ask_memory"):
        memory_question = prompt[len("記憶："):].strip()
        if not memory_question:
            await message.channel.send("長期記憶について何を知りたいですか？")
            return

        try:
            answer = await asyncio.to_thread(context.ask_memory, memory_question)
            if hasattr(context, "save_message"):
                context.save_message(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    channel_id=channel_id,
                    user_id=None,
                    role="assistant",
                    content=answer,
                )
            await message.channel.send(answer)
            if hasattr(context, "run_memory_consolidation"):
                await context.run_memory_consolidation()
        except Exception as e:
            print(f"[MEMORY QA ERROR] {e}")
            await message.channel.send("長期記憶の検索中にエラーが発生しました。")
        return

    # 自動長期記憶参照 & 通常会話
    use_memory = False
    if hasattr(context, "should_use_memory"):
        try:
            use_memory = await asyncio.to_thread(context.should_use_memory, prompt)
        except Exception as e:
            print(f"[MEMORY ROUTER ERROR] {e}")

    limit = getattr(context, "MEMORY_LIMIT", 10)
    recent_messages = context.get_recent_messages(channel_id=channel_id, limit=limit) if hasattr(context, "get_recent_messages") else []
    memory_context_text = None

    if use_memory and hasattr(context, "search_memories"):
        try:
            memories = await asyncio.to_thread(context.search_memories, query=prompt, limit=limit)
            if memories and hasattr(context, "build_memory_context"):
                memory_context = await asyncio.to_thread(context.build_memory_context, memories, query=prompt)
                if hasattr(context, "format_memory_context"):
                    memory_context_text = context.format_memory_context(memory_context)
        except Exception as e:
            print(f"[MEMORY CONTEXT ERROR] {e}")
            memory_context_text = None

    ollama_messages = context.build_conversation_messages(
        recent_messages=recent_messages,
        memory_context=memory_context_text,
    ) if hasattr(context, "build_conversation_messages") else [{"role": "user", "content": prompt}]

    try:
        ask_fn = getattr(context, "ask_ollama_with_tools", getattr(context, "ask_ollama", None))
        if hasattr(message.channel, "typing"):
            async with message.channel.typing():
                answer = await ask_fn(ollama_messages) if asyncio.iscoroutinefunction(ask_fn) else ask_fn(ollama_messages)
        else:
            answer = await ask_fn(ollama_messages) if asyncio.iscoroutinefunction(ask_fn) else ask_fn(ollama_messages)

        if hasattr(context, "save_message"):
            context.save_message(
                timestamp=datetime.now(timezone.utc).isoformat(),
                channel_id=channel_id,
                user_id=None,
                role="assistant",
                content=answer,
            )

        for chunk in [answer[i:i + 1900] for i in range(0, len(answer), 1900)]:
            await message.channel.send(chunk)

        if hasattr(context, "run_memory_consolidation"):
            await context.run_memory_consolidation()

    except Exception as e:
        print(f"[DISCORD ASSISTANT ERROR] {e}")
        await message.channel.send(f"申し訳ありません、応答の生成中にエラーが発生しました: {e}")


def create_discord_client() -> discord.Client:
    """Create and configure Discord client."""
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        await handle_discord_ready(client)

    @client.event
    async def on_message(message: discord.Message):
        await handle_discord_message(client, message)

    return client


async def run_discord_bot(token: str | None = None):
    """Run Discord Bot."""
    bot_token = token or os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("[DISCORD BOT] DISCORD_BOT_TOKEN is not set. Discord bot is disabled.")
        return

    client = create_discord_client()
    print("[DISCORD BOT] Starting Discord bot...")
    await client.start(bot_token)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run_discord_bot())
