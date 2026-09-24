"""
Search tools for ALICE_CoPilot Tool Calling.
Enables CoPilot to autonomously search past meetings, transcripts, summaries, and minutes.
"""
import logging
from typing import Any
import config
from search_handler import execute_search, clean_html_snippet

logger = logging.getLogger("ALICE_CoPilot.Tools.Search")


async def search_past_meetings(query: str, limit: int = 5, module: str | None = None) -> dict[str, Any]:
    """
    Search past meetings, transcripts, summaries, and official minutes by keyword.

    Args:
        query: Keyword to search (e.g. '面談', '伊藤さん', '予算', '進捗')
        limit: Max results to return (default 5)
        module: Optional filter ('summary', 'transcript', 'minutes')

    Returns:
        dict: Formatted search results with snippets and dates.
    """
    if not query or not query.strip():
        return {"total": 0, "message": "検索キーワードが空です。"}

    try:
        # Strictly enforce owner core user id for memory contamination guard
        owner_id = getattr(config, "OWNER_CORE_USER_ID", "U794535d58fb802ac996f4a86ce119ad2")
        result = await execute_search(
            query=query.strip(),
            limit=limit,
            user_id=owner_id,
            module=module,
        )

        hits = result.get("hits", [])
        if not hits:
            return {
                "total": 0,
                "query": query,
                "message": f"「{query}」に関する過去の会議録や要約は見つかりませんでした。",
                "results": [],
            }

        formatted_results = []
        for hit in hits:
            job_id = hit.get("job_id", "unknown")
            meta = hit.get("metadata", {})
            title = meta.get("original_filename") or job_id
            mod = hit.get("module", "unknown")
            created_at = hit.get("created_at", "")
            date_str = created_at[:16].replace("T", " ") if created_at else "日時不明"

            raw_snippet = hit.get("snippet", "")
            snippet = clean_html_snippet(raw_snippet)
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."

            formatted_results.append({
                "title": title,
                "module": mod,
                "date": date_str,
                "job_id": job_id,
                "snippet": snippet,
            })

        return {
            "total": len(formatted_results),
            "query": query,
            "results": formatted_results,
        }
    except Exception as e:
        logger.error(f"[search_past_meetings] Error: {e}")
        return {"total": 0, "error": f"検索中にエラーが発生しました: {e}"}



async def search_project_memory(query: str, limit: int = 5) -> dict[str, Any]:
    """
    Search Project ALICE long-term memory (Decisions, Architecture, Specifications, Background history).
    Use when user asks about project specifications, design decisions, why certain technologies were adopted or abandoned
    (e.g., why domain was acquired, Tailscale Funnel vs Cloudflare Tunnel, MFA specifications, architecture rules).
    """
    if not query or not query.strip():
        return {"total": 0, "message": "検索キーワードが空です。"}

    try:
        import asyncio
        from memory.memory_search import search_memories

        memories = await asyncio.to_thread(search_memories, query=query.strip(), limit=limit)
        if not memories:
            return {
                "total": 0,
                "query": query,
                "message": f"「{query}」に関する長期記憶・設計決定は見つかりませんでした。",
                "results": [],
            }

        formatted = []
        for m in memories:
            content = m.get("content", "")
            lines = [line for line in content.splitlines() if not line.startswith("## Related")]
            body_snippet = "\n".join(lines).strip()
            if len(body_snippet) > 350:
                body_snippet = body_snippet[:347] + "..."

            formatted.append({
                "id": m.get("id"),
                "score": m.get("score"),
                "snippet": body_snippet,
            })

        return {
            "total": len(formatted),
            "query": query,
            "results": formatted,
        }
    except Exception as e:
        logger.error(f"[search_project_memory] Error: {e}")
        return {"total": 0, "error": f"長期記憶検索中にエラーが発生しました: {e}"}
