"""
Discord Views and Embed formatting for ALICE_CoPilot.
Provides morning briefing embeds and interactive action buttons for autonomous patching.
"""
import json
from typing import Any, Optional
import discord


def build_morning_briefing_embed(report: dict[str, Any]) -> discord.Embed:
    """Build a Discord Embed for the morning briefing."""
    summary = report.get("summary", "夜間点検が完了しました。")
    memories = report.get("memories_added", [])
    improvements = report.get("improvements", [])
    conv_count = report.get("conversations_count", 0)
    err_count = report.get("errors_count", 0)

    embed_color = 0x2ECC71 if not improvements and not memories else 0x3498DB

    embed = discord.Embed(
        title="🌅 ALICE モーニングブリーフィング",
        description="おはようございます！昨夜の対話履歴とシステムログを点検し、自律改善を行いました。",
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
            msg += "⚠️ 不合格項目あり: 要確認"
        else:
            msg += "長期記憶の不変条件および再発防止ルールを全件クリアしました。"
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

    # Discrepancy & Self-Repairs
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

    embed.set_footer(text="Google Antigravity SDK Nightly Reviewer • !apply または下のボタンで自律改修を実行")
    return embed


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
                f"ユーザー（{user_name}）の承認を受け、タスクキューに登録しました（Task ID: `{task_id}`）。\n"
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
