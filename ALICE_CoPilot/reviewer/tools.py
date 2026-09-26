"""
Tools for the Antigravity Nightly Reviewer Agent.
Equips the agent with capabilities to search code, inspect Git history,
search existing memories, add new memories, run tests, and record the final report.
Includes Self-Evolving Checklist tools for regression prevention.
"""
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Optional

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent)))
COPILOT_DIR = PROJECT_ROOT / "ALICE_CoPilot"
CORE_DIR = PROJECT_ROOT / "ALICE_Core"
PYTHON_BIN = PROJECT_ROOT / "myenv" / "copilot_env" / "bin" / "python3"

# State storage populated during the agent run
REVIEW_STATE: dict[str, Any] = {
    "summary": "",
    "memories_added": [],
    "improvements": [],
    "repairs_done": [],
    "checklist_summary": None,
    "new_checklist_rules": [],
    "recorded": False,
}


def reset_review_state() -> None:
    """Reset the in-memory review state for a new run."""
    REVIEW_STATE["summary"] = ""
    REVIEW_STATE["memories_added"] = []
    REVIEW_STATE["improvements"] = []
    REVIEW_STATE["repairs_done"] = []
    REVIEW_STATE["checklist_summary"] = None
    REVIEW_STATE["new_checklist_rules"] = []
    REVIEW_STATE["recorded"] = False


def search_codebase(query: str, target_dir: str = "ALICE_CoPilot") -> str:
    """Searches the codebase for a given pattern or keyword.

    Args:
        query: The string to search for in source files.
        target_dir: The repository directory to search ('ALICE_CoPilot' or 'ALICE_Core').
    """
    search_path = PROJECT_ROOT / target_dir if target_dir else COPILOT_DIR
    if not search_path.exists():
        search_path = COPILOT_DIR

    cmd = [
        "grep",
        "-rn",
        "--exclude-dir=.git",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.pytest_cache",
        query,
        str(search_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = res.stdout.strip().splitlines()
        if not lines:
            return f"検索結果: '{query}' に一致するコードは見つかりませんでした。"
        preview = lines[:20]
        return "\n".join(preview) + (f"\n...他 {len(lines) - 20} 件" if len(lines) > 20 else "")
    except Exception as e:
        return f"コード検索エラー: {e}"


def search_git_history(query: str = "", repo: str = "ALICE_CoPilot", max_count: int = 5) -> str:
    """Searches git commit history for recent commits or specific commit messages.

    Args:
        query: Optional string to filter commit messages. If empty, returns latest commits.
        repo: Repository name ('ALICE_CoPilot' or 'ALICE_Core').
        max_count: Maximum number of commits to return.
    """
    repo_path = PROJECT_ROOT / repo if repo else COPILOT_DIR
    if not repo_path.exists():
        repo_path = COPILOT_DIR

    cmd = ["git", "log", f"-n{max_count}", "--oneline"]
    if query:
        cmd.append(f"--grep={query}")

    try:
        res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=10)
        out = res.stdout.strip()
        return out if out else f"コミット履歴に '{query}' に一致する記録はありませんでした。"
    except Exception as e:
        return f"Git履歴検索エラー: {e}"


def search_existing_memories(query: str) -> str:
    """Searches existing long-term memories to see what ALICE already remembers.

    Args:
        query: The keyword or concept to search for in long-term memory.
    """
    try:
        from memory.memory_search import search_memories
        results = search_memories(query)
        if not results:
            return f"長期記憶検索: '{query}' に一致する記憶はありません。"
        lines = []
        for r in results[:5]:
            title = r.get("title", "")
            m_type = r.get("type", "")
            m_id = r.get("id", "")
            lines.append(f"- [{m_type}] {title} (ID: {m_id})")
        return "既存の長期記憶:\n" + "\n".join(lines)
    except Exception as e:
        return f"長期記憶検索エラー: {e}"


def add_longterm_memory(memory_type: str, title: str, content: str) -> str:
    """Adds a new confirmed memory to ALICE's long-term memory and syncs to Obsidian.

    Args:
        memory_type: Category of memory ('decision', 'knowledge', 'project', 'idea', 'context').
        title: Short, descriptive title of the memory.
        content: Detailed explanation of the fact, decision, or rationale.
    """
    cmd = [
        str(PYTHON_BIN),
        str(COPILOT_DIR / "memory" / "cli.py"),
        "create",
        "--type", memory_type,
        "--title", title,
        "--content", content,
    ]
    try:
        res = subprocess.run(cmd, cwd=str(COPILOT_DIR), capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            REVIEW_STATE["memories_added"].append({"type": memory_type, "title": title})
            return f"長期記憶に登録完了: [{memory_type}] {title}"
        else:
            return f"長期記憶登録失敗: {res.stderr.strip()}"
    except Exception as e:
        return f"長期記憶登録例外: {e}"


def run_copilot_unit_tests() -> str:
    """Runs the unit tests of ALICE_CoPilot to verify system integrity.
    Useful to verify whether code modifications or refactoring broke anything.
    """
    cmd = [
        str(PYTHON_BIN),
        "-m", "pytest",
        "tests/test_tools.py",
        "tests/test_tasks_tools.py",
        "tests/test_calendar_tools.py",
        "-q",
    ]
    try:
        res = subprocess.run(cmd, cwd=str(COPILOT_DIR), capture_output=True, text=True, timeout=30)
        out = (res.stdout + "\n" + res.stderr).strip()
        passed = res.returncode == 0
        status_str = "全テスト通過 (PASS)" if passed else "テスト失敗 (FAIL)"
        return f"{status_str}:\n{out[:500]}"
    except Exception as e:
        return f"テスト実行エラー: {e}"


def check_calendar_state(query: str = "", time_min: str = "", time_max: str = "", calendar_name: str = "") -> str:
    """Checks the real state of Google Calendar to verify if events were actually registered, updated, or deleted.

    Args:
        query: Search keyword (e.g. '古橋', '休暇', '工数').
        time_min: Start time (e.g. '2026-09-15').
        time_max: End time (e.g. '2026-09-22').
        calendar_name: Target calendar ('個人予定', '仕事', '人員動静').
    """
    try:
        from tools.calendar_tools import get_calendar_events
        res = get_calendar_events(
            calendar_name=calendar_name or None,
            query=query or None,
            time_min=time_min or None,
            time_max=time_max or None,
        )
        events = res.get("events", [])
        if not events:
            return "カレンダー実データ: 条件に一致する予定はありません。"
        lines = [f"カレンダー実データ（全 {len(events)} 件）:"]
        for ev in events:
            lines.append(f"- [{ev.get('calendar')}] id={ev.get('id')} | {ev.get('summary')} ({ev.get('start')} ~ {ev.get('end')})")
        return "\n".join(lines)
    except Exception as e:
        return f"カレンダー照会エラー: {e}"


def check_task_state(query: str = "", list_name: str = "", status: str = "all") -> str:
    """Checks the real state of Google Tasks to verify if tasks were actually added, completed, or deleted.

    Args:
        query: Task keyword to search for.
        list_name: Task list ('業務タスク' or 'マイタスク').
        status: 'all', 'needsAction', or 'completed'.
    """
    try:
        from tools.tasks_tools import get_todo_tasks
        res = get_todo_tasks(query=query or None, list_name=list_name or None, status=status)
        total = res.get("total", 0)
        lists = res.get("lists", {})
        lines = [f"Google Tasks実データ（全 {total} 件）:"]
        for lname, tasks in lists.items():
            lines.append(f"【{lname}】({len(tasks)}件):")
            for t in tasks:
                st = "完了" if t.get("status") == "completed" else "未完了"
                lines.append(f"  - [{st}] {t.get('title')} (期日: {t.get('due') or 'なし'}, ID: {t.get('id')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Tasks照会エラー: {e}"


def repair_calendar_state(action: str, event_id: str, calendar_name: str | None = None, summary: str | None = None) -> str:
    """Autonomously repairs discrepancies in Google Calendar (e.g. deleting hallucinated/duplicate events).

    Args:
        action: 'delete' to remove duplicate/unwanted event, or 'update' to fix title/details.
        event_id: The event ID to delete or modify.
        calendar_name: Target calendar name ('個人予定', '仕事', '人員動静').
        summary: If action is 'update', the corrected summary title.
    """
    try:
        if action == "delete":
            from tools.calendar_tools import delete_calendar_event
            res = delete_calendar_event(event_id=event_id, calendar_name=calendar_name)
            if res.get("status") == "success":
                msg = f"【自律修復】カレンダー「{res.get('calendar')}」から予定（ID: {event_id}）を削除修復しました。"
                REVIEW_STATE["repairs_done"].append(msg)
                return msg
            return f"削除修復失敗: {res.get('error')}"
        elif action == "update":
            from tools.calendar_tools import update_calendar_event
            res = update_calendar_event(event_id=event_id, summary=summary, calendar_name=calendar_name)
            if res.get("status") == "success":
                msg = f"【自律修復】カレンダー「{res.get('calendar')}」の予定（ID: {event_id}）を「{summary}」に更新修復しました。"
                REVIEW_STATE["repairs_done"].append(msg)
                return msg
            return f"更新修復失敗: {res.get('error')}"
        else:
            return f"未知の修復アクション: {action}"
    except Exception as e:
        return f"自律修復例外: {e}"


def repair_tasks_state(
    action: str,
    title: str = "",
    due_date: str = "",
    list_name: str = "業務タスク",
    task_id: str = "",
    notes: str = "",
) -> str:
    """Autonomously repairs discrepancies in Google Tasks (e.g. creating missing tasks that were falsely reported as added, or completing finished tasks).

    Args:
        action: 'create' to add a missing task, 'complete' to mark a task done, or 'update' to modify details.
        title: Title of the task to create or update.
        due_date: Due date in 'YYYY-MM-DD' format (optional).
        list_name: Target task list ('業務タスク' or 'マイタスク'). Defaults to '業務タスク'.
        task_id: Task ID to complete or update.
        notes: Optional notes/description for the task.
    """
    try:
        if action == "create":
            if not title:
                return "タスク作成修復エラー: タイトルが指定されていません。"
            from tools.tasks_tools import create_todo_task
            res = create_todo_task(
                title=title,
                due_date=due_date or None,
                list_name=list_name or "業務タスク",
                notes=notes or None,
            )
            if res.get("status") == "success":
                msg = f"【自律修復】Google Tasks「{list_name}」に未登録だったタスク『{title}』（期限: {due_date or 'なし'}）を自律登録しました。"
                REVIEW_STATE["repairs_done"].append(msg)
                return msg
            return f"タスク作成修復失敗: {res.get('error') or res.get('message')}"

        elif action == "complete":
            if not task_id and not title:
                return "タスク完了修復エラー: タスクIDまたはタイトルが指定されていません。"
            from tools.tasks_tools import complete_todo_task
            res = complete_todo_task(
                task_title_or_id=task_id or title,
                list_name=list_name or None,
            )
            if res.get("status") == "success":
                msg = f"【自律修復】Google Tasks「{list_name}」のタスク『{title or task_id}』を完了済みに修復しました。"
                REVIEW_STATE["repairs_done"].append(msg)
                return msg
            return f"タスク完了修復失敗: {res.get('error') or res.get('message')}"

        elif action == "update":
            if not task_id and not title:
                return "タスク更新修復エラー: タスクIDまたはタイトルが指定されていません。"
            from tools.tasks_tools import update_todo_task
            res = update_todo_task(
                task_title_or_id=task_id or title,
                new_title=title or None,
                due_date=due_date or None,
                notes=notes or None,
                list_name=list_name or None,
            )
            if res.get("status") == "success":
                msg = f"【自律修復】Google Tasks「{list_name}」のタスク『{title or task_id}』の情報を更新修復しました。"
                REVIEW_STATE["repairs_done"].append(msg)
                return msg
            return f"タスク更新修復失敗: {res.get('error') or res.get('message')}"

        else:
            return f"未知のタスク修復アクション: {action}"
    except Exception as e:
        return f"タスク自律修復例外: {e}"


# =========================================================================
# Self-Evolving Checklist Tools
# =========================================================================

def run_self_evolving_checklist(rule_ids_csv: str = "") -> str:
    """Runs the self-evolving checklist to verify all persistent invariant and regression prevention rules.

    Args:
        rule_ids_csv: Optional comma-separated rule IDs (e.g. 'CHK-CAL-001,CHK-TSK-001'). If empty, runs all active rules.
    """
    try:
        from reviewer.checklist import run_checklist
        r_ids = [x.strip() for x in rule_ids_csv.split(",") if x.strip()] if rule_ids_csv else None
        res = run_checklist(rule_ids=r_ids)
        REVIEW_STATE["checklist_summary"] = res

        lines = [f"【自己進化チェックリスト実行結果】: {res.get('summary_text')} (実行: {res.get('total')}件)"]
        for r in res.get("results", []):
            icon = "✅" if r["status"] == "PASS" else "❌"
            lines.append(f"{icon} [{r['rule_id']}] {r['title']}: {r['detail']}")
        return "\n".join(lines)
    except Exception as e:
        return f"チェックリスト実行例外: {e}"


def add_checklist_rule(
    category: str,
    title: str,
    description: str,
    check_type: str,
    learned_from: str,
) -> str:
    """Registers a new permanent checklist rule learned from an incident or user correction.
    Use this whenever you repair a discrepancy, hallucination, or user complaint (e.g. '消えてない', '残ってる')
    to ensure it never regresses in future nightly reviews.

    Args:
        category: 'calendar', 'tasks', 'memory', 'system', or 'user_rule'.
        title: Short descriptive name of the check rule.
        description: The expected invariant condition that must hold true.
        check_type: 'calendar_integrity', 'tasks_integrity', 'memory_conflicts', 'unit_tests', or 'custom'.
        learned_from: Context or user correction that motivated this rule.
    """
    try:
        from reviewer.checklist import add_checklist_rule as add_rule
        rule = add_rule(
            category=category,
            title=title,
            description=description,
            check_type=check_type,
            learned_from=learned_from,
        )
        msg = f"【チェックリスト新規登録】[{rule['rule_id']}] {title}（学習元: {learned_from}）"
        REVIEW_STATE["new_checklist_rules"].append(msg)
        return f"チェックリストに新ルールを登録・永続化しました: {rule['rule_id']} - {title}"
    except Exception as e:
        return f"チェックリスト登録例外: {e}"


def get_checklist_status() -> str:
    """Retrieves all registered checklist rules and their latest pass/fail status."""
    try:
        from reviewer.checklist import get_checklist_status as get_status
        rules = get_status()
        if not rules:
            return "登録されているチェックリストルールはありません。"
        lines = [f"登録済みチェックリストルール（全 {len(rules)} 件）:"]
        for r in rules:
            status_icon = "✅" if r.get("last_status") == "PASS" else ("❌" if r.get("last_status") == "FAIL" else "⚪")
            lines.append(
                f"- {status_icon} [{r['rule_id']}] {r['title']} ({r['category']}) - 状態: {r.get('last_status', 'UNTESTED')}\n"
                f"    条件: {r['description']}\n"
                f"    学習元: {r.get('learned_from', 'なし')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"チェックリスト照会例外: {e}"


def record_review_result(summary: str, improvements: list[str], repairs: list[str] | None = None) -> str:
    """Records the final structured review findings to be included in the morning briefing.

    Args:
        summary: Clear Japanese overview of what was reviewed and any actions taken.
        improvements: List of proposals, suggestions, or insights for the user.
        repairs: Optional list of repairs executed during the review.
    """
    REVIEW_STATE["summary"] = summary
    REVIEW_STATE["improvements"] = improvements
    if repairs:
        REVIEW_STATE["repairs_done"].extend(repairs)
    REVIEW_STATE["recorded"] = True
    return "夜間レビュー結果を正常に記録しました。"
