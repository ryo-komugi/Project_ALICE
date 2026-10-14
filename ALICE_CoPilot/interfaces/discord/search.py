"""
Discord Search Handler and Embed Formatter for ALICE_CoPilot.
Provides Discord integration for ALICE_Search CLI.
"""
import logging
from typing import Any
import discord

import config
from search_handler import clean_html_snippet, execute_search

logger = logging.getLogger("ALICE_CoPilot.Discord.Search")


def build_search_embed(result: dict[str, Any], query: str) -> discord.Embed:
    """Build a clean, readable Discord Embed from search results without noisy emojis."""
    error = result.get("error")
    if error:
        embed = discord.Embed(
            title=f"検索エラー: {query}",
            description=f"検索の実行中にエラーが発生しました。\n`{error}`",
            color=0xE74C3C,
        )
        embed.set_footer(text="ALICE Knowledge & Search")
        return embed

    total = result.get("total", 0)
    hits = result.get("hits", [])

    if total == 0 or not hits:
        embed = discord.Embed(
            title=f"検索結果: {query}",
            description="該当する過去の会話・要約は見つかりませんでした。\n検索条件を変更してお試しください。",
            color=0x7F8C8D,
        )
        embed.set_footer(text="ALICE Knowledge & Search")
        return embed

    display_count = min(len(hits), 5)
    embed = discord.Embed(
        title=f"検索結果: {query}",
        description=f"一致件数: {total} 件 (上位 {display_count} 件を表示)",
        color=0x2980B9,
    )

    displayed_count = 0
    for hit in hits:
        job_id = hit.get("job_id", "unknown")
        meta = hit.get("metadata", {})
        original_filename = meta.get("original_filename") or job_id
        module = hit.get("module", "unknown")
        created_at_raw = hit.get("created_at", "")
        created_str = created_at_raw[:16].replace("T", " ") if created_at_raw else "日時不明"

        raw_snippet = hit.get("snippet", "")
        clean_snippet = clean_html_snippet(raw_snippet)
        if len(clean_snippet) > 250:
            clean_snippet = clean_snippet[:247] + "..."

        quoted_snippet = "\n".join(f"> {line}" for line in clean_snippet.splitlines())

        field_title = f"{original_filename} [{module.upper()}]"
        field_value = (
            f"日時: `{created_str}` | Job: `{job_id}`\n"
            f"{quoted_snippet}"
        )

        embed.add_field(name=field_title, value=field_value, inline=False)
        displayed_count += 1
        if displayed_count >= 5:
            break

    embed.set_footer(text="ALICE Knowledge & Search | #search")
    return embed


def is_search_request(message: discord.Message) -> tuple[bool, str]:
    """Check if message is a search request."""
    content = getattr(message, "content", "").strip()
    if not content:
        return False, ""

    channel = getattr(message, "channel", None)
    channel_name = getattr(channel, "name", "")

    if channel_name == "search":
        author = getattr(message, "author", None)
        if getattr(author, "bot", False):
            return False, ""
        return True, content

    prefixes = ("!search ", "!s ", "検索: ", "検索 ")
    for p in prefixes:
        if content.startswith(p):
            query = content[len(p):].strip()
            return True, query

    return False, ""


async def handle_search_message(message: discord.Message) -> bool:
    """Handle message if it's a search request."""
    is_search, query = is_search_request(message)
    if not is_search:
        return False

    if not query:
        await message.channel.send("検索キーワードを指定してください。(例: `面談`, `!search 予算`)")
        return True

    try:
        target_user_id = getattr(config, "OWNER_CORE_USER_ID", "") or None
        if hasattr(message.channel, "typing"):
            async with message.channel.typing():
                result = await execute_search(query=query, limit=5, user_id=target_user_id)
        else:
            result = await execute_search(query=query, limit=5, user_id=target_user_id)
        embed = build_search_embed(result=result, query=query)
        await message.channel.send(embed=embed)
    except Exception as e:
        logger.error(f"[SearchHandler] Failed to handle search message: {e}")
        await message.channel.send(f"検索中にエラーが発生しました: {e}")

    return True
