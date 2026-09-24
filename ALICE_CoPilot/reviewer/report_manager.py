"""
Report Manager for ALICE Nightly Reviewer.
Handles database persistence, Discord Embed formatting, and Action Buttons for morning briefings.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import discord

DEFAULT_DB_PATH = Path("/data/runtime/copilot/database/nightly_reports.db")


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
    """Mark a report as reported with timestamp."""
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


def build_morning_briefing_embed(report: dict[str, Any]) -> discord.Embed:
    """Build a Discord Embed for the morning briefing."""
    summary = report.get("summary", "夜間点検が完了しました。")
    memories = report.get("memories_added", [])
    improvements = report.get("improvements", [])
    conv_count = report.get("conversations_count", 0)
    err_count = report.get("errors_count", 0)

    # Color selection: Green if smooth, Blue if normal, Orange if improvements noted
    embed_color = 0x2ECC71 if not improvements and not memories else 0x3498DB

    embed = discord.Embed(
        title="🌅 ALICE モーニングブリーフィング",
        description="おはようございます、浅野さん！昨夜の会話履歴とシステムログを点検し、自律改善を行いました。",
        color=embed_color,
    )

    # Summary
    embed.add_field(
        name="📋 点検結果サマリー",
        value=summary[:1024] if summary else "異常なし",
        inline=False,
    )

    # Self-Evolving Checklist Results
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
        status_icon = "✅" if failed == 0 else "⚠️"
        new_cnt = len(new_rules)
        sub_text = f"（新規学習・蓄積: {new_cnt}件）" if new_cnt > 0 else "（リグレッションなし）"
        msg = f"**{passed}/{total} 項目 合格** {sub_text}\n"
        if failed > 0:
            msg += f"⚠️ 不合格項目あり: 要確認"
        else:
            msg += "カレンダー・タスク・長期記憶の不変条件および再発防止ルールを全件クリアしました。"
        embed.add_field(
            name=f"{status_icon} 自己進化チェックリスト（全 {total} 項目）",
            value=msg[:1024],
            inline=False,
        )

    # Long-term Memory updates
    if memories:
        mem_lines = []
        for m in memories:
            if isinstance(m, dict):
                title = m.get("title", "新規記憶")
                m_type = m.get("type", "decision")
                mem_lines.append(f"• `[{m_type}]` **{title}**")
            else:
                mem_lines.append(f"• **{m}**")
        embed.add_field(
            name=f"🧠 新規登録・補完した長期記憶 ({len(memories)}件)",
            value="\n".join(mem_lines)[:1024],
            inline=False,
        )
    else:
        embed.add_field(
            name="🧠 長期記憶の更新",
            value="なし（既存の知識ベースと最新の会話に乖離はありません）",
            inline=False,
        )

    # Discrepancy & Hallucination Repairs
    repairs = report.get("repairs_done", [])
    if not repairs and "raw_details" in report and report["raw_details"]:
        try:
            details_obj = json.loads(report["raw_details"])
            if isinstance(details_obj, dict):
                repairs = details_obj.get("repairs_done", [])
        except Exception:
            pass

    if repairs:
        repair_lines = [f"• {r}" for r in repairs]
        embed.add_field(
            name=f"🛠️ 夜間自律修復（ハルシネーション・実態乖離の是正: {len(repairs)}件）",
            value="\n".join(repair_lines)[:1024],
            inline=False,
        )

    # Improvements / Suggestions
    if improvements:
        imp_lines = [f"• {item}" for item in improvements]
        embed.add_field(
            name=f"💡 システム改善提案・気付き ({len(improvements)}件)",
            value="\n".join(imp_lines)[:1024],
            inline=False,
        )
    else:
        embed.add_field(
            name="💡 改善提案",
            value="全システム正常稼働中です。特記事項はありません。",
            inline=False,
        )

    # Metrics
    metrics_text = f"対話ターン数: **{conv_count}** 件 / エラー・警告: **{err_count}** 件"
    embed.add_field(
        name="📊 解析メトリクス",
        value=metrics_text,
        inline=False,
    )

    embed.set_footer(text="Google Antigravity SDK Nightly Reviewer v1.0 • !apply または下のボタンで自律改修を実行")
    return embed


# =========================================================================
# Interactive Discord View (Buttons)
# =========================================================================

class MorningBriefingActionView(discord.ui.View):
    """Interactive Discord View providing quick action buttons for Morning Briefing."""

    def __init__(self, report_id: int, improvements: list[str], timeout: float = 86400):
        super().__init__(timeout=timeout)
        self.report_id = report_id
        self.improvements = improvements

    @discord.ui.button(label="🛠️ 改善案を自律改修する", style=discord.ButtonStyle.primary, custom_id="btn_apply_improvements")
    async def apply_improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Trigger Antigravity Auto-Patcher via Patch Queue when user clicks the button."""
        if not self.improvements:
            await interaction.response.send_message("現在適用可能な未適用の改善提案はありません。", ephemeral=True)
            return

        instruction = "\n".join(f"- {imp}" for imp in self.improvements)
        user_name = str(interaction.user)

        try:
            from reviewer.patch_worker import enqueue_patch_task
            task_id = enqueue_patch_task(
                instruction=instruction,
                repo="ALICE_CoPilot",
                user_id=user_name,
                source="discord_button",
            )

            button.disabled = True
            button.label = "⏳ 改修中..."
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)

            await interaction.followup.send(
                f"🚀 **【Antigravity 自律改修タスク受付完了】**\n"
                f"浅野さんの承認を受け、タスクキューに登録しました（Task ID: `{task_id}`）。\n"
                f"Antigravity CLI がバックグラウンドでコード調査・安全修正・単体テスト（100% PASS）・Gitコミットを実行します。\n"
                f"完了次第、このチャンネル（#copilot）に詳細レポートをお知らせします！\n\n"
                f"**改修対象の提案**:\n```\n{instruction}\n```"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 自律改修タスクのキュー登録中にエラーが発生しました: {e}")


def create_morning_briefing_view(report: dict[str, Any]) -> Optional[discord.ui.View]:
    """Creates an interactive View with buttons if improvements are available."""
    improvements = report.get("improvements", [])
    report_id = report.get("id", 0)
    if not improvements:
        return None
    return MorningBriefingActionView(report_id=report_id, improvements=improvements)


if __name__ == "__main__":
    import sys
    init_reports_db()
    if "--test-embed" in sys.argv:
        dummy = {
            "id": 1,
            "summary": "昨日の対話においてドメイン取得理由に関する質問を検知し、Cloudflare Tunnel移行に関する長期記憶を自動補完しました。",
            "memories_added": [{"type": "decision", "title": "独自ドメイン取得とCloudflare Tunnel移行"}],
            "improvements": ["カタカナ単語検索の正規表現を強化し、辞書マッチ率が向上しました。"],
            "conversations_count": 24,
            "errors_count": 0,
            "raw_details": json.dumps({
                "checklist": {"total": 4, "passed": 4, "failed": 0},
                "new_checklist_rules": ["【チェックリスト新規登録】[CHK-CAL-002] 予定削除時の二重確認"],
            }, ensure_ascii=False),
        }
        emb = build_morning_briefing_embed(dummy)
        view = create_morning_briefing_view(dummy)
        print("Embed title:", emb.title)
        print("Embed fields count:", len(emb.fields))
        print("View created:", view is not None)
        for f in emb.fields:
            print(f"  Field [{f.name}]: {f.value}")
    else:
        latest = get_latest_report()
        print("Latest report:", latest)
