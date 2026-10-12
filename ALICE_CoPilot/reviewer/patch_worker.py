"""
Antigravity CLI (agy) Autonomous Patch Worker & Task Queue for Project_ALICE.
Executes autonomous code modifications using the local agy CLI within existing subscriptions.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

COPILOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(COPILOT_DIR.parent)))
QUEUE_DIR = Path("/data/runtime/patch_queue")
INBOX_DIR = QUEUE_DIR / "inbox"
RUNNING_DIR = QUEUE_DIR / "running"
COMPLETED_DIR = QUEUE_DIR / "completed"
FAILED_DIR = QUEUE_DIR / "failed"
LOGS_DIR = QUEUE_DIR / "logs"

AGY_BIN = Path(os.getenv("AGY_BIN", str(Path.home() / ".gemini" / "bin" / "agy")))
HANDOFF_PATH = PROJECT_ROOT / "HANDOFF.md"
SHARED_MEMORY_HANDOFF = Path("/data/memory/HANDOFF.md")


def init_queue_dirs() -> None:
    """Ensure all required patch queue directories exist."""
    for d in (INBOX_DIR, RUNNING_DIR, COMPLETED_DIR, FAILED_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def enqueue_patch_task(
    instruction: str,
    repo: str = "ALICE_CoPilot",
    user_id: str = "unknown",
    source: str = "discord_button",
) -> str:
    """Enqueues an autonomous patch task into the inbox.

    Returns:
        Generated task ID (e.g. 'patch_20260924_004012_a1b2').
    """
    init_queue_dirs()
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand_suffix = os.urandom(2).hex()
    task_id = f"patch_{timestamp_str}_{rand_suffix}"

    task_data = {
        "task_id": task_id,
        "instruction": instruction,
        "repo": repo,
        "user_id": user_id,
        "source": source,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "status": "queued",
    }

    task_file = INBOX_DIR / f"{task_id}.json"
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)

    logger.info(f"[PATCH WORKER] Enqueued task {task_id} from {source} (user: {user_id})")
    return task_id


def build_patch_prompt(instruction: str, repo: str) -> str:
    """Builds the comprehensive self-contained prompt for Antigravity CLI."""
    return f"""【Project_ALICE 自律改修タスク】
浅野さんから承認されたシステム改善提案です。以下の課題・提案を解決してください:
{instruction}

【対象リポジトリ】: {repo}

【必須プロトコル・完了条件】
1. まず関連コードを調査・確認し、安全にピンポイントな修正を行ってください。
2. 修正後、pytest 単体テストを実行し、全件 PASS することを確認してください。
3. 設計や規約に関する新知見・決定事項が生じた場合は ALICE_Memory（Knowledge）に Markdown として記録してください。
4. HANDOFF.md の「2. Latest Status & Handoff」および「5. 次に実施すべきタスク」を更新してください。
5. 最後に git add および git commit を作成し、backup にプッシュしてください。
"""


def sync_handoff_files() -> bool:
    """Syncs HANDOFF.md from Project_ALICE to /data/memory for Syncthing distribution."""
    try:
        if HANDOFF_PATH.exists():
            shutil.copy2(HANDOFF_PATH, SHARED_MEMORY_HANDOFF)
            logger.info("[PATCH WORKER] Synced HANDOFF.md to /data/memory/HANDOFF.md")
            return True
    except Exception as e:
        logger.error(f"[PATCH WORKER] Failed to sync HANDOFF.md: {e}")
    return False


async def run_agy_subprocess(task_id: str, prompt: str) -> tuple[int, str]:
    """Runs Antigravity CLI in a non-blocking subprocess with real-time log streaming."""
    log_file = LOGS_DIR / f"{task_id}.log"
    cmd = [
        str(AGY_BIN),
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--print-timeout",
        "15m",
    ]

    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"=== Antigravity CLI Task: {task_id} ===\n")
        lf.write(f"Started at: {datetime.now().isoformat()}\n\n")
        lf.flush()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(PROJECT_ROOT),
            stdout=lf,
            stderr=subprocess.STDOUT,
        )
        await proc.wait()
        exit_code = proc.returncode

    with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
        output = lf.read()

    return exit_code, output


async def process_single_task(task_file: Path, discord_client: Any = None) -> bool:
    """Processes a single patch task from inbox to completion or failure."""
    task_id = task_file.stem
    running_file = RUNNING_DIR / task_file.name

    try:
        shutil.move(str(task_file), str(running_file))
    except Exception as e:
        logger.error(f"[PATCH WORKER] Could not move {task_file} to running: {e}")
        return False

    with open(running_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    instruction = task_data.get("instruction", "")
    repo = task_data.get("repo", "ALICE_CoPilot")
    repo_dir = PROJECT_ROOT / repo if (PROJECT_ROOT / repo).exists() else PROJECT_ROOT

    # Record HEAD hash before running agy
    head_before = ""
    try:
        r_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True)
        head_before = r_head.stdout.strip()
    except Exception:
        pass

    prompt = build_patch_prompt(instruction, repo)
    logger.info(f"[PATCH WORKER] Executing Antigravity CLI for {task_id}...")

    t_start = time.time()
    exit_code, log_output = await run_agy_subprocess(task_id, prompt)
    elapsed_sec = round(time.time() - t_start, 1)

    # Check git status and new commit
    head_after = ""
    commit_msg = ""
    commit_diff = ""
    committed = False
    try:
        r_head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True)
        head_after = r_head_after.stdout.strip()
        if head_before and head_after and head_before != head_after:
            committed = True
            r_msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=str(repo_dir), capture_output=True, text=True)
            commit_msg = r_msg.stdout.strip()
            r_diff = subprocess.run(["git", "diff", f"{head_before}..{head_after}", "--stat"], cwd=str(repo_dir), capture_output=True, text=True)
            commit_diff = r_diff.stdout.strip()
    except Exception as e:
        logger.warning(f"[PATCH WORKER] Git status check error: {e}")

    # Sync HANDOFF.md to shared memory if modified
    sync_handoff_files()

    success = (exit_code == 0)
    task_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    task_data["elapsed_sec"] = elapsed_sec
    task_data["exit_code"] = exit_code
    task_data["committed"] = committed
    task_data["commit_hash"] = head_after[:7] if committed else None
    task_data["commit_message"] = commit_msg
    task_data["commit_diff"] = commit_diff
    task_data["status"] = "completed" if success else "failed"

    dest_dir = COMPLETED_DIR if success else FAILED_DIR
    dest_file = dest_dir / task_file.name
    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)

    try:
        running_file.unlink(missing_ok=True)
    except Exception:
        pass

    # Send Discord notification if client available
    if discord_client:
        await notify_discord_completion(discord_client, task_data, log_output)

    logger.info(f"[PATCH WORKER] Task {task_id} finished (status={task_data['status']}, committed={committed}, elapsed={elapsed_sec}s)")
    return success


async def notify_discord_completion(discord_client: Any, task_data: dict[str, Any], log_output: str) -> None:
    """Finds the #copilot channel and sends completion/failure embed."""
    try:
        import discord
        target_channel = None
        for guild in discord_client.guilds:
            for ch in guild.text_channels:
                if ch.name == "copilot":
                    target_channel = ch
                    break
            if target_channel:
                break

        if not target_channel:
            return

        task_id = task_data.get("task_id", "")
        committed = task_data.get("committed", False)
        commit_hash = task_data.get("commit_hash", "")
        commit_msg = task_data.get("commit_message", "")
        diff_stat = task_data.get("commit_diff", "")
        elapsed = task_data.get("elapsed_sec", 0)
        status = task_data.get("status", "unknown")

        if status == "completed":
            embed = discord.Embed(
                title=f"✅ 【Antigravity 自律改修完了】 Task: `{task_id}`",
                description=f"Antigravity CLI による自律調査・コード修正・単体テスト検証・Git コミットが正常に完了しました。（所要時間: {elapsed}s）",
                color=0x2ECC71,
                timestamp=datetime.now(timezone.utc),
            )
            if committed:
                embed.add_field(name="📌 コミット情報", value=f"`[{commit_hash}]` {commit_msg}", inline=False)
                if diff_stat:
                    embed.add_field(name="📊 変更統計", value=f"```\n{diff_stat[:800]}\n```", inline=False)
            embed.add_field(
                name="📝 実行サマリー",
                value=log_output[-800:] if len(log_output) > 800 else (log_output or "正常終了"),
                inline=False,
            )
            embed.set_footer(text="Google Antigravity CLI Autonomous Worker • HANDOFF.md 同期完了")
        else:
            embed = discord.Embed(
                title=f"❌ 【Antigravity 自律改修失敗】 Task: `{task_id}`",
                description=f"Antigravity CLI の実行中にエラーが発生しました。（所要時間: {elapsed}s）",
                color=0xE74C3C,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(
                name="⚠️ エラーログ末尾",
                value=f"```\n{log_output[-800:] if len(log_output) > 800 else (log_output or '不明なエラー')}\n```",
                inline=False,
            )
            embed.set_footer(text="Google Antigravity CLI Autonomous Worker")

        await target_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"[PATCH WORKER] Failed to send Discord notification: {e}")


async def patch_queue_worker_loop(discord_client: Any = None, poll_interval_sec: float = 5.0) -> None:
    """Continuously polls the inbox directory and processes pending patch tasks."""
    init_queue_dirs()
    logger.info(f"[PATCH WORKER] Autonomous Patch Worker loop started (poll interval: {poll_interval_sec}s)")

    while True:
        try:
            task_files = sorted(INBOX_DIR.glob("*.json"))
            for tf in task_files:
                logger.info(f"[PATCH WORKER] Found pending task: {tf.name}")
                await process_single_task(tf, discord_client)
        except Exception as e:
            logger.error(f"[PATCH WORKER] Error in worker loop: {e}", exc_info=True)

        await asyncio.sleep(poll_interval_sec)
