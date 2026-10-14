"""
Discord Bot Message & Event Dispatcher for ALICE_CoPilot.
Handles routing for commands, knowledge search, Antigravity dev mode, long-term memory, and conversation.
"""
import asyncio
from datetime import datetime, timezone
import discord


async def handle_discord_ready(client: discord.Client, context=None):
    """Handles Discord client on_ready event."""
    if context is None:
        import main as context

    context.initialize_database()
    print(f"ALICE_CoPilot logged in as {client.user}")

    # バックグラウンド監視ループ起動
    if hasattr(context, "start_background_tasks"):
        await context.start_background_tasks(client)

    # 内部APIサーバー (ポート 8005: WebUI連携用) をバックグラウンド起動
    if hasattr(context, "start_internal_api_server"):
        asyncio.create_task(context.start_internal_api_server(port=8005))

    # Obsidian差分自動同期
    try:
        sync_res = await asyncio.to_thread(context.sync_obsidian, clean=True)
        print(f"[OBSIDIAN STARTUP-SYNC] Completed: {sync_res}")
    except Exception as e:
        print(f"[OBSIDIAN STARTUP-SYNC ERROR] {e}")


async def handle_discord_message(client: discord.Client, message: discord.Message, context=None):
    """Handles incoming Discord messages with dynamic module context (supports monkeypatching)."""
    if context is None:
        import main as context

    if message.author == client.user or getattr(message.author, "bot", False):
        return

    # #search チャンネルまたは !search コマンドによるナレッジ検索処理
    if await context.handle_search_message(message):
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
        attachment_text, processed_filenames = await context.extract_attachments_text(message.attachments)

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

    # 長期記憶保存（「覚えておいて」）
    is_memory_cmd = prompt.startswith("覚えておいて")
    is_attachment_memory = bool(processed_filenames) and (not prompt or is_memory_cmd)

    if is_memory_cmd or is_attachment_memory:
        base_text = prompt[len("覚えておいて"):].strip() if is_memory_cmd else prompt
        memory_text = (base_text + "\n\n" + attachment_text).strip() if attachment_text else base_text
        if not memory_text:
            await message.channel.send("何を覚えておけばいいですか？")
            return

        try:
            result = await asyncio.to_thread(context.process_memory, memory_text)
            if result["saved"]:
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
    if prompt.startswith("記憶："):
        memory_question = prompt[len("記憶："):].strip()
        if not memory_question:
            await message.channel.send("長期記憶について何を知りたいですか？")
            return

        try:
            answer = await asyncio.to_thread(context.ask_memory, memory_question)
            print(f"[MEMORY QA] {answer}")
            context.save_message(
                timestamp=datetime.now(timezone.utc).isoformat(),
                channel_id=channel_id,
                user_id=None,
                role="assistant",
                content=answer,
            )
            await message.channel.send(answer)
            await context.run_memory_consolidation()
        except Exception as e:
            print(f"[MEMORY QA ERROR] {e}")
            await message.channel.send("長期記憶の検索中にエラーが発生しました。")
        return

    # 自動長期記憶参照
    use_memory = False
    try:
        use_memory = await asyncio.to_thread(context.should_use_memory, prompt)
        print(f"[MEMORY ROUTER] use_memory={use_memory}")
    except Exception as e:
        print(f"[MEMORY ROUTER ERROR] {e}")

    # 通常会話
    limit = getattr(context, "MEMORY_LIMIT", 10)
    recent_messages = context.get_recent_messages(channel_id=channel_id, limit=limit)
    memory_context_text = None

    if use_memory:
        try:
            memories = await asyncio.to_thread(context.search_memories, query=prompt, limit=limit)
            if memories:
                memory_context = await asyncio.to_thread(context.build_memory_context, memories, query=prompt)
                memory_context_text = context.format_memory_context(memory_context)
        except Exception as e:
            print(f"[MEMORY CONTEXT ERROR] {e}")
            memory_context_text = None

    ollama_messages = context.build_conversation_messages(
        recent_messages=recent_messages,
        memory_context=memory_context_text,
    )

    try:
        if hasattr(message.channel, "typing"):
            async with message.channel.typing():
                answer = await context.ask_ollama_with_tools(ollama_messages)
        else:
            answer = await context.ask_ollama_with_tools(ollama_messages)
        print(f"[ALICE] {answer}")

        if not answer.strip():
            print("[OLLAMA ERROR] Empty answer returned.")
            await message.channel.send("回答を生成できませんでした。")
            return

        context.save_message(
            timestamp=datetime.now(timezone.utc).isoformat(),
            channel_id=channel_id,
            user_id=None,
            role="assistant",
            content=answer,
        )
        for chunk in [answer[i:i+1900] for i in range(0, len(answer), 1900)]:
            await message.channel.send(chunk)
        await context.run_memory_consolidation()
    except Exception as e:
        print(f"[ERROR] {e}")
        await message.channel.send("申し訳ありません。Ollamaとの通信でエラーが発生しました。")
