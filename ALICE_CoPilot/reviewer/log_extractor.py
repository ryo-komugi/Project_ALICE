"""
Log & Conversation Extractor for Nightly Review.
Fetches past 24h of conversations and system logs for analysis.
"""
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("/data/runtime/copilot/database/conversations.db")
DEFAULT_LOG_PATH = Path("/data/runtime/logs/copilot.log")


def extract_conversations(
    hours: int = 24,
    db_path: Path | str = DEFAULT_DB_PATH,
    max_messages: int = 100,
) -> list[dict[str, Any]]:
    """Extract conversation messages from SQLite for the past N hours."""
    path = Path(db_path)
    if not path.exists():
        return []

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_iso = since.isoformat()

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, timestamp, channel_id, user_id, role, content
            FROM messages
            WHERE timestamp >= ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (since_iso, max_messages),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def extract_system_errors(
    hours: int = 24,
    log_path: Path | str = DEFAULT_LOG_PATH,
    max_lines: int = 150,
) -> list[str]:
    """Extract error/warning log snippets from copilot.log."""
    path = Path(log_path)
    if not path.exists():
        return []

    try:
        # Read the tail of the log file (up to ~500KB)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Log read error: {e}"]

    # We want to capture ERROR, Traceback, Exception, or [WARNING]
    error_patterns = [
        re.compile(r"ERROR", re.IGNORECASE),
        re.compile(r"Traceback \(most recent call last\):"),
        re.compile(r"Exception:"),
        re.compile(r"\[OLLAMA ERROR\]"),
    ]

    matched_lines: list[str] = []
    capture_traceback = 0

    # Scan the last 1000 lines
    for line in lines[-1000:]:
        line_clean = line.strip()
        if not line_clean:
            continue

        if any(p.search(line_clean) for p in error_patterns):
            matched_lines.append(line_clean)
            if "Traceback" in line_clean:
                capture_traceback = 5
        elif capture_traceback > 0:
            matched_lines.append(line_clean)
            capture_traceback -= 1

    return matched_lines[-max_lines:]


def format_conversations_for_prompt(conversations: list[dict[str, Any]]) -> str:
    """Format extracted messages into a clean dialog transcript for LLM review."""
    if not conversations:
        return "（過去24時間以内の会話ログはありません）"

    formatted_turns: list[str] = []
    for msg in conversations:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        # Truncate extremely verbose messages (like prompt dumps) to keep review focused
        if len(content) > 600:
            content = content[:600] + "... [省略]"
        ts = msg.get("timestamp", "")
        # Shorten timestamp to HH:MM if possible
        try:
            ts_dt = datetime.fromisoformat(ts)
            ts_short = ts_dt.strftime("%m/%d %H:%M")
        except Exception:
            ts_short = ts[:16]

        speaker = "浅野さん (User)" if role == "user" else "ALICE (Assistant)"
        formatted_turns.append(f"[{ts_short}] {speaker}:\n{content}")

    return "\n\n".join(formatted_turns)


def build_review_context(hours: int = 24) -> dict[str, Any]:
    """Build the comprehensive context payload for the reviewer agent."""
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(hours=hours)

    convs = extract_conversations(hours=hours)
    errors = extract_system_errors(hours=hours)
    conv_text = format_conversations_for_prompt(convs)

    return {
        "period_start": start_utc.isoformat(),
        "period_end": now_utc.isoformat(),
        "conversations": convs,
        "conversations_count": len(convs),
        "errors": errors,
        "errors_count": len(errors),
        "transcript_text": conv_text,
        "errors_text": "\n".join(errors) if errors else "（エラーや例外ログは検出されませんでした）",
    }


if __name__ == "__main__":
    ctx = build_review_context(24)
    print(f"Context Period: {ctx['period_start']} -> {ctx['period_end']}")
    print(f"Conversations: {ctx['conversations_count']} messages")
    print(f"Errors: {ctx['errors_count']} lines")
    print("--- Sample Transcript ---")
    print(ctx["transcript_text"][:400])