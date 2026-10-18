"""
Background Worker Loops for ALICE_CoPilot.
Handles periodic tasks:
- Daily system peak metrics monitoring
- Nightly review / Morning briefing delivery (07:30 JST)
- Autonomous patch queue worker
"""
import asyncio
from datetime import datetime, timezone, timedelta
import discord


async def system_metrics_monitor_loop(interval_sec: int = 5):
    """Periodically sample and update today's system peaks (VRAM, load, temps)."""
    from tools.system_tools import update_daily_peaks

    while True:
        try:
            await asyncio.to_thread(update_daily_peaks)
        except Exception as e:
            print(f"[SYSTEM METRICS MONITOR ERROR] {e}")
        await asyncio.sleep(interval_sec)


async def morning_briefing_monitor_loop(client: discord.Client, check_interval_sec: int = 60):
    """Checks for pending nightly review reports and delivers morning briefing at 07:30 JST to #copilot."""
    from reviewer.report_manager import (
        get_latest_pending_report,
        mark_report_as_reported,
        build_morning_briefing_embed,
        create_morning_briefing_view,
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


async def start_background_tasks(client: discord.Client):
    """Starts all background monitoring and queue worker tasks."""
    from reviewer.patch_worker import patch_queue_worker_loop

    asyncio.create_task(system_metrics_monitor_loop(5))
    asyncio.create_task(morning_briefing_monitor_loop(client, 60))
    asyncio.create_task(patch_queue_worker_loop(client, poll_interval_sec=5))
    print("[BACKGROUND WORKERS] Started system metrics, morning briefing, and patch worker loops.")
