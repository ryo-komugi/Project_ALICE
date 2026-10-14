"""
Report Manager for ALICE Nightly Reviewer.
Handles database persistence and clean Markdown formatting for nightly reviews and morning briefings.
Free from Discord dependencies (Discord views/embeds are separated into interfaces/discord/).
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config

DEFAULT_DB_PATH = Path(
    os.getenv(
        "ALICE_REPORTS_DB_PATH",
        str(config.PROJECT_ROOT / "data" / "runtime" / "copilot" / "database" / "nightly_reports.db"),
    )
)


def get_db_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_reports_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Initialize the nightly reports database table."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nightly_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    conversations_count INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    reported_at TEXT,
                    summary TEXT NOT NULL,
                    memories_added TEXT,
                    improvements TEXT,
                    raw_details TEXT
                )
                """
            )
    finally:
        conn.close()


def save_report(
    summary: str,
    memories_added: list[Any] | None = None,
    improvements: list[str] | None = None,
    period_start: str = "",
    period_end: str = "",
    conversations_count: int = 0,
    errors_count: int = 0,
    raw_details: str = "",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Save a newly generated nightly report. Returns report ID."""
    init_reports_db(db_path)
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    if not period_end:
        period_end = now_iso

    memories_json = json.dumps(memories_added or [], ensure_ascii=False)
    improvements_json = json.dumps(improvements or [], ensure_ascii=False)

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO nightly_reports (
                    created_at, period_start, period_end, conversations_count, errors_count,
                    status, summary, memories_added, improvements, raw_details
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    period_start,
                    period_end,
                    conversations_count,
                    errors_count,
                    summary,
                    memories_json,
                    improvements_json,
                    raw_details,
                ),
            )
            return cursor.lastrowid
    finally:
        conn.close()


def get_latest_pending_report(db_path: Path | str = DEFAULT_DB_PATH) -> Optional[dict[str, Any]]:
    """Retrieve the most recent un-reported report."""
    init_reports_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT * FROM nightly_reports
            WHERE status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def get_latest_report(db_path: Path | str = DEFAULT_DB_PATH) -> Optional[dict[str, Any]]:
    """Retrieve the most recent report regardless of status."""
    init_reports_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT * FROM nightly_reports
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def mark_report_as_reported(report_id: int, db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Mark a pending report as reported."""
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            conn.execute(
                """
                UPDATE nightly_reports
                SET status = 'reported', reported_at = ?
                WHERE id = ?
                """,
                (now_iso, report_id),
            )
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    res = dict(row)
    try:
        res["memories_added"] = json.loads(res.get("memories_added") or "[]")
    except Exception:
        res["memories_added"] = []
    try:
        res["improvements"] = json.loads(res.get("improvements") or "[]")
    except Exception:
        res["improvements"] = []
    return res


def format_morning_briefing_markdown(report: dict[str, Any]) -> str:
    """Format report as a clean Markdown text (presentation-agnostic)."""
    summary = report.get("summary", "夜間点検が完了しました。")
    memories = report.get("memories_added", [])
    improvements = report.get("improvements", [])
    conv_count = report.get("conversations_count", 0)
    err_count = report.get("errors_count", 0)

    lines = [
        "# 🌅 ALICE モーニングブリーフィング",
        "昨夜の対話履歴とシステムログを点検し、自律改善を行いました。\n",
        "## 📋 点検結果サマリー",
        summary,
        "",
    ]

    # Checklist
    checklist_info = None
    new_rules = []
    if "raw_details" in report and report["raw_details"]:
        try:
            details_obj = json.loads(report["raw_details"])
            if isinstance(details_obj, dict):
                checklist_info = details_obj.get("checklist")
                new_rules = details_obj.get("new_checklist_rules", [])
        except Exception:
            pass

    if checklist_info:
        total = checklist_info.get("total", 0)
        passed = checklist_info.get("passed", 0)
        failed = checklist_info.get("failed", 0)
        new_cnt = len(new_rules)
        sub_text = f"（新規学習・蓄積: {new_cnt}件）" if new_cnt > 0 else "（リグレッションなし）"
        lines.append(f"## ✅ 自己進化チェックリスト（全 {total} 項目）")
        lines.append(f"- **{passed}/{total} 項目 合格** {sub_text}")
        if failed > 0:
            lines.append(f"- ⚠️ 不合格項目あり: 要確認")
        lines.append("")

    # Memories
    lines.append("## 🧠 長期記憶の更新")
    if memories:
        for m in memories:
            if isinstance(m, dict):
                title = m.get("title", "新規記憶")
                m_type = m.get("type", "decision")
                lines.append(f"- `[{m_type}]` **{title}**")
            else:
                lines.append(f"- **{m}**")
    else:
        lines.append("- なし（既存の知識ベースと最新の対話に乖離はありません）")
    lines.append("")

    # Improvements
    lines.append("## 💡 システム改善提案・気付き")
    if improvements:
        for item in improvements:
            lines.append(f"- {item}")
    else:
        lines.append("- 全システム正常稼働中です。特記事項はありません。")
    lines.append("")

    # Metrics
    lines.append("## 📊 解析メトリクス")
    lines.append(f"- 対話ターン数: **{conv_count}** 件")
    lines.append(f"- エラー・警告: **{err_count}** 件")

    return "\n".join(lines)


# Backwards compatibility / Discord helper forwarding
def build_morning_briefing_embed(report: dict[str, Any]) -> Any:
    """Convenience forwarder for backwards compatibility. Imports from interfaces.discord.views."""
    try:
        from interfaces.discord.views import build_morning_briefing_embed as _builder
        return _builder(report)
    except ImportError:
        return None


def create_morning_briefing_view(report: dict[str, Any]) -> Any:
    """Convenience forwarder for backwards compatibility. Imports from interfaces.discord.views."""
    try:
        from interfaces.discord.views import create_morning_briefing_view as _creator
        return _creator(report)
    except ImportError:
        return None


try:
    from interfaces.discord.views import MorningBriefingActionView
except ImportError:
    class MorningBriefingActionView:
        pass
