"""
Development CoPilot Service for Project_ALICE.
Handles engineering questions, codebase inspection, git history, test runs,
and memory synchronization using Google Antigravity SDK and Ollama.
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import requests
import aiohttp
import config
from google.antigravity import Agent, LocalOpenAIAgentConfig
from memory.short_term import save_message, get_recent_messages

PROJECT_ROOT = config.PROJECT_ROOT
COPILOT_DIR = PROJECT_ROOT / "ALICE_CoPilot"
CORE_DIR = PROJECT_ROOT / "ALICE_Core"
COPILOT_PYTHON = PROJECT_ROOT / "myenv/copilot_env/bin/python3"
CORE_PYTHON = PROJECT_ROOT / "myenv/core_env/bin/python3"

# Real-time state tracking for status badge API
ANTIGRAVITY_STATE: dict[str, Any] = {
    "active": False,
    "current_tool": "",
    "model": config.OLLAMA_MODEL,
    "last_run": None,
}


def get_copilot_system_prompt() -> str:
    now_str = datetime.now().strftime("%Y年%m月%d日 (%a) %H:%M")

    # 1. 直近のモーニングブリーフィング改善提案の取得
    briefing_context = ""
    try:
        from reviewer.report_manager import get_latest_report
        latest_rep = get_latest_report()
        if latest_rep and latest_rep.get("improvements"):
            imps = "\n".join(f"  • {item}" for item in latest_rep["improvements"])
            rep_date = latest_rep.get("created_at", "本日")
            briefing_context = (
                f"\n\n【直近のモーニングブリーフィング改善提案 ({rep_date})】\n"
                f"{imps}\n"
                "※ ユーザーから「今朝の提案」「改善案」等について質問された場合は、上記内容を踏まえて背景・課題・改修方針を分かりやすく解説してください。"
            )
    except Exception:
        pass

    # 2. 最新 HANDOFF.md のステータス取得
    handoff_context = ""
    try:
        handoff_path = PROJECT_ROOT / "HANDOFF.md"
        if handoff_path.exists():
            with open(handoff_path, "r", encoding="utf-8") as f:
                h_lines = f.readlines()
            status_lines = []
            capture = False
            for line in h_lines:
                if "## 2. Latest Status" in line or "## 5. 次に実施すべきタスク" in line:
                    capture = True
                elif capture and line.startswith("## ") and not ("Latest Status" in line or "次に実施すべきタスク" in line):
                    capture = False
                if capture:
                    status_lines.append(line)
            if status_lines:
                handoff_context = "\n\n【システム現在地 & 次のToDo (HANDOFF.md抜粋)】\n" + "".join(status_lines[:30]).strip()
    except Exception:
        pass

    return (
        f"現在日時: {now_str} (JST)\n"
        "あなたはProject_ALICEの開発・エンジニアリング専属AI相棒「CoPilot」です。\n"
        "Python (FastAPI, aiohttp, discord.py), Linux (Ubuntu/Tailscale), 機械学習モデル (Whisper, PyAnnote, Ollama), "
        "およびセキュアなシステムアーキテクチャに精通しています。\n"
        "簡潔・論理的で、開発者の思考を加速させる技術的アドバイスを提供してください。"
        f"{briefing_context}"
        f"{handoff_context}"
    )


# =====================================================================
# Antigravity Tools for Interactive Dev CoPilot
# =====================================================================
_event_queue: asyncio.Queue | None = None


def _notify_step(tool_name: str, status: str, detail: Any = None):
    ANTIGRAVITY_STATE["active"] = (status == "running")
    ANTIGRAVITY_STATE["current_tool"] = tool_name if status == "running" else ""
    if _event_queue is not None:
        try:
            _event_queue.put_nowait({
                "type": "antigravity_step",
                "tool": tool_name,
                "status": status,
                "detail": detail,
            })
        except Exception:
            pass


def search_codebase(query: str, repo: str = "ALICE_CoPilot") -> str:
    """Searches the codebase for a given pattern or keyword.

    Args:
        query: The string to search for in source files.
        repo: Repository name ('ALICE_CoPilot', 'ALICE_Core', 'ALICE_Search', 'ALICE_Minutes', 'ALICE_Summary', 'ALICE_Transcript').
    """
    _notify_step("search_codebase", "running", {"query": query, "repo": repo})
    search_path = PROJECT_ROOT / repo if repo else COPILOT_DIR
    if not search_path.exists():
        search_path = COPILOT_DIR

    cmd = [
        "grep",
        "-rn",
        "--exclude-dir=.git",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.pytest_cache",
        "--exclude-dir=.mypy_cache",
        query,
        str(search_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = res.stdout.strip().splitlines()
        result = "\n".join(lines[:25]) + (f"\n...他 {len(lines) - 25} 件" if len(lines) > 25 else "") if lines else f"'{query}' に一致するコードはありません。"
        _notify_step("search_codebase", "completed", {"matches": len(lines)})
        return result
    except Exception as e:
        _notify_step("search_codebase", "error", str(e))
        return f"コード検索エラー: {e}"


def search_git_history(query: str = "", repo: str = "ALICE_CoPilot", max_count: int = 5) -> str:
    """Searches git commit history for recent commits or specific commit messages.

    Args:
        query: Optional filter string for commit messages.
        repo: Repository name ('ALICE_CoPilot', 'ALICE_Core', etc.).
        max_count: Number of commits to inspect.
    """
    _notify_step("search_git_history", "running", {"query": query, "repo": repo})
    repo_path = PROJECT_ROOT / repo if repo else COPILOT_DIR
    if not repo_path.exists():
        repo_path = COPILOT_DIR

    cmd = ["git", "log", f"-n{max_count}", "--oneline"]
    if query:
        cmd.append(f"--grep={query}")

    try:
        res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=10)
        out = res.stdout.strip()
        result = out if out else f"コミット履歴に '{query}' に一致する記録はありません。"
        _notify_step("search_git_history", "completed", {"found": bool(out)})
        return result
    except Exception as e:
        _notify_step("search_git_history", "error", str(e))
        return f"Git履歴検索エラー: {e}"


def run_unit_tests(target: str = "copilot") -> str:
    """Runs automated unit tests.

    Args:
        target: 'copilot' to test ALICE_CoPilot, or 'core' to test ALICE_Core.
    """
    _notify_step("run_unit_tests", "running", {"target": target})
    if target == "core":
        cmd = [str(CORE_PYTHON), "-m", "pytest", "test_admin_auth.py", "-q"]
        cwd = str(CORE_DIR)
    else:
        cmd = [str(COPILOT_PYTHON), "-m", "pytest", "tests/test_tools.py", "-q"]
        cwd = str(COPILOT_DIR)

    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        output = res.stdout.strip() or res.stderr.strip()
        _notify_step("run_unit_tests", "completed", {"exit_code": res.returncode})
        return output
    except Exception as e:
        _notify_step("run_unit_tests", "error", str(e))
        return f"テスト実行例外: {e}"


def read_project_file(file_path: str, max_lines: int = 100) -> str:
    """Reads lines from a project source code file.

    Args:
        file_path: Relative path from Project_ALICE root (e.g. 'ALICE_Core/core/admin.py').
        max_lines: Max number of lines to read.
    """
    _notify_step("read_project_file", "running", {"file_path": file_path})
    target = PROJECT_ROOT / file_path
    if not target.exists() or not target.is_file():
        _notify_step("read_project_file", "error", "File not found")
        return f"ファイルが見つかりません: {file_path}"

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
        content = "".join(lines)
        _notify_step("read_project_file", "completed", {"lines_read": len(lines)})
        return content
    except Exception as e:
        _notify_step("read_project_file", "error", str(e))
        return f"ファイル読み込みエラー: {e}"


def search_project_memory(query: str) -> str:
    """Searches ALICE's long-term engineering memory and design decisions.

    Args:
        query: Search term for decisions or architecture specs.
    """
    _notify_step("search_project_memory", "running", {"query": query})
    try:
        from memory.memory_search import search_memories
        results = search_memories(query)
        if not results:
            _notify_step("search_project_memory", "completed", {"count": 0})
            return f"長期記憶に '{query}' に関する記録はありません。"

        items = []
        for r in results[:5]:
            items.append(f"- [{r.get('type')}] {r.get('title')}: {r.get('content', '')[:100]}...")
        _notify_step("search_project_memory", "completed", {"count": len(items)})
        return "記憶検索結果:\n" + "\n".join(items)
    except Exception as e:
        _notify_step("search_project_memory", "error", str(e))
        return f"記憶検索エラー: {e}"


# =====================================================================
# Main CoPilot Streaming Workflow (Hybrid)
# =====================================================================
async def stream_copilot(prompt: str, session_id: str = "web_copilot") -> AsyncGenerator[dict, None]:
    """
    Executes development CoPilot workflow with Hybrid dispatch (Ollama or Antigravity SDK).
    """
    global _event_queue
    prompt = prompt.strip()
    if not prompt:
        yield {"type": "done", "full_content": "開発に関するご質問や指示を入力してください。"}
        return

    # 1. ユーザー発言の保存
    now_utc = datetime.now(timezone.utc).isoformat()
    save_message(
        timestamp=now_utc,
        channel_id=session_id,
        user_id="web_dev_user",
        role="user",
        content=prompt,
    )

    # 2. 常時Antigravity自律駆動エージェント実行（Ollama切り替えを撤廃しAntigravity一本化）
    from services.antigravity_manager import load_antigravity_settings, increment_quota_usage
    ag_settings = load_antigravity_settings()
    selected_model = ag_settings.get("selected_model", "Gemini 3.8 Flash (High)")

    yield {"type": "status", "message": f"🤖 Antigravity ({selected_model}) 自律エージェントが思考中..."}
    _event_queue = asyncio.Queue()
    ANTIGRAVITY_STATE["active"] = True
    ANTIGRAVITY_STATE["last_run"] = datetime.now(timezone.utc).isoformat()
    increment_quota_usage(cost_weight=2)

    agent_config = LocalOpenAIAgentConfig(
        model=config.OLLAMA_MODEL,
        base_url="http://localhost:11434/v1",
        system_instructions=(
            f"あなたはProject_ALICEの専属自律開発エンジニア「CoPilot」です（モデルプロファイル: {selected_model}）。\n"
            f"{get_copilot_system_prompt()}\n"
            "必要に応じて提供されたツール（コード検索、Git履歴確認、ファイル読み込み、ユニットテスト実行、長期記憶検索）を自律的に活用し、論理的かつ的確な回答を提供してください。"
        ),
        tools=[
            search_codebase,
            search_git_history,
            run_unit_tests,
            read_project_file,
            search_project_memory,
        ],
    )

    async def _run_antigravity():
        try:
            async with Agent(config=agent_config) as agent:
                resp = await agent.chat(prompt)
                ans = await resp.text()
                return ans
        except Exception as ex:
            return f"Antigravity実行中にエラーが発生しました: {ex}"
        finally:
            ANTIGRAVITY_STATE["active"] = False
            ANTIGRAVITY_STATE["current_tool"] = ""

    task = asyncio.create_task(_run_antigravity())

    while not task.done():
        try:
            event = await asyncio.wait_for(_event_queue.get(), timeout=0.2)
            yield event
        except asyncio.TimeoutError:
            continue

    while not _event_queue.empty():
        yield _event_queue.get_nowait()

    final_content = await task
    _event_queue = None
    if final_content:
        yield {"type": "delta", "content": final_content}

    # 3. アシスタント発言の保存
    save_message(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel_id=session_id,
        user_id=None,
        role="assistant",
        content=final_content,
    )

    yield {"type": "done", "full_content": final_content}
