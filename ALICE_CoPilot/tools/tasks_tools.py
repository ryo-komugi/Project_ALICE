"""
Google Tasks integration tools for ALICE_CoPilot.
Connects directly to user's 'マイタスク' and '業務タスク' lists via Google Tasks API v1.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests

logger = logging.getLogger("ALICE_CoPilot.Tools.Tasks")

TOKEN_PATH = Path("/data/runtime/calendar/token.json")
JST = timezone(timedelta(hours=9))


_cached_tasks_token: str | None = None
_token_expiry_ts: float = 0.0


def _refresh_token_from_file(data: dict) -> str:
    global _cached_tasks_token, _token_expiry_ts
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    refresh_token = data.get("refresh_token")

    logger.info("[Google Tasks] Refreshing access token...")
    token_url = "https://oauth2.googleapis.com/token"
    refresh_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(token_url, data=refresh_data, timeout=10)
    if resp.status_code == 200:
        new_token_data = resp.json()
        new_token = new_token_data["access_token"]
        expires_in = new_token_data.get("expires_in", 3600)
        _cached_tasks_token = new_token
        import time
        _token_expiry_ts = time.time() + float(expires_in) - 60.0
        data["access_token"] = new_token
        data["expires_at"] = _token_expiry_ts
        try:
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[Google Tasks] Failed to save updated token to file: {e}")
        return new_token
    else:
        raise RuntimeError(f"Failed to refresh Google Tasks token: {resp.text}")


def _get_valid_token(force_refresh: bool = False) -> str:
    """Read token and automatically refresh if expired, with memory caching."""
    global _cached_tasks_token, _token_expiry_ts
    import time

    if not force_refresh and _cached_tasks_token and time.time() < _token_expiry_ts:
        return _cached_tasks_token

    if not TOKEN_PATH.exists():
        raise FileNotFoundError(f"OAuth token not found at {TOKEN_PATH}")

    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    access_token = data.get("access_token")
    expires_at = data.get("expires_at", 0)

    if not force_refresh and access_token and time.time() < float(expires_at):
        _cached_tasks_token = access_token
        _token_expiry_ts = float(expires_at)
        return access_token

    return _refresh_token_from_file(data)


def _get_task_lists(headers: dict[str, str]) -> dict[str, str]:
    """Map title -> list_id for all user task lists."""
    url = "https://tasks.googleapis.com/tasks/v1/users/@me/lists"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 401:
        token = _get_valid_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        logger.error(f"[Tasks] Failed to list task lists: {resp.text}")
        return {}

    mapping = {}
    for item in resp.json().get("items", []):
        mapping[item.get("title")] = item.get("id")
    return mapping


def _categorize_task(title: str) -> str:
    """Categorize task by prefix."""
    if "【提〆】" in title or "【提出〆】" in title:
        return "提出期限"
    elif "【回答〆】" in title:
        return "回答期限"
    elif "【展開〆】" in title or "【展〆】" in title:
        return "展開期限"
    elif "【SmartHR】" in title:
        return "手続き"
    return "一般タスク"


def get_todo_tasks(
    list_name: str | None = None,
    status: str = "needsAction",
    due_max: str | None = None,
    due_min: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """
    Get ToDo tasks from user's Google Tasks ('業務タスク' and/or 'マイタスク').

    Args:
        list_name: Specific list ('業務タスク' or 'マイタスク'). If omitted, checks both lists.
        status: 'needsAction' (incomplete only, default), 'completed' (done), or 'all'.
        due_max: Optional filter for tasks due on or before this date (YYYY-MM-DD or ISO).
        due_min: Optional filter for tasks due on or after this date (YYYY-MM-DD or ISO).
        query: Optional keyword filter for task title or notes (case-insensitive substring match).

    Returns:
        dict: Incomplete and completed tasks grouped by list with categorized prefixes.
    """
    try:
        token = _get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        all_lists = _get_task_lists(headers)

        target_lists = {}
        if list_name:
            for t_name, lid in all_lists.items():
                if list_name in t_name or t_name in list_name:
                    target_lists[t_name] = lid
            if not target_lists:
                target_lists = all_lists
        else:
            target_lists = all_lists

        result_by_list: dict[str, list[dict[str, Any]]] = {}
        total_count = 0

        show_completed = status in ("completed", "all")

        for lname, lid in target_lists.items():
            t_url = f"https://tasks.googleapis.com/tasks/v1/lists/{lid}/tasks"
            params: dict[str, Any] = {
                "showCompleted": "true" if show_completed else "false",
                "showHidden": "true" if show_completed else "false",
                "maxResults": 100,
            }
            if due_min:
                params["dueMin"] = f"{due_min[:10]}T00:00:00Z"
            if due_max:
                # Google Tasks API stores dates at midnight UTC and treats dueMax as strictly less than.
                # To include tasks due on due_max date, dueMax must be the start of the next day.
                try:
                    dt_max = datetime.fromisoformat(due_max[:10])
                    next_day = (dt_max + timedelta(days=1)).strftime("%Y-%m-%d")
                    params["dueMax"] = f"{next_day}T00:00:00Z"
                except Exception:
                    params["dueMax"] = f"{due_max[:10]}T23:59:59Z"

            resp = requests.get(t_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                continue

            items = resp.json().get("items", [])
            tasks_formatted = []
            for item in items:
                istatus = item.get("status")
                if status == "needsAction" and istatus != "needsAction":
                    continue
                if status == "completed" and istatus != "completed":
                    continue

                title = item.get("title", "(タイトルなし)")
                notes = item.get("notes", "").strip()

                if query:
                    q_lower = query.strip().lower()
                    if q_lower not in title.lower() and q_lower not in notes.lower():
                        continue

                due = item.get("due")
                due_disp = due[:10] if due else None

                # Exact boundary verification in Python
                if due_min and due_disp and due_disp < due_min[:10]:
                    continue
                if due_max and due_disp and due_disp > due_max[:10]:
                    continue

                category = _categorize_task(title)

                tasks_formatted.append({
                    "id": item.get("id"),
                    "title": title,
                    "category": category,
                    "status": "未完了" if istatus == "needsAction" else "完了済",
                    "due": due_disp,
                    "notes": notes,
                })

            result_by_list[lname] = tasks_formatted
            total_count += len(tasks_formatted)

        return {
            "total": total_count,
            "filter_status": status,
            "lists": result_by_list,
        }
    except Exception as e:
        logger.error(f"[get_todo_tasks] Error: {e}", exc_info=True)
        return {"error": str(e)}


def create_todo_task(
    title: str,
    list_name: str = "業務タスク",
    due_date: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """
    Create a new task in user's Google Tasks ('業務タスク' or 'マイタスク').

    Args:
        title: Task title (e.g. '【提〆】週報', 'サブスク見直し').
        list_name: Target list ('業務タスク' or 'マイタスク', default: '業務タスク').
        due_date: Due date string (YYYY-MM-DD or ISO). Optional.
        notes: Detailed notes or memo.

    Returns:
        dict: Result with created task info.
    """
    try:
        token = _get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        all_lists = _get_task_lists(headers)

        target_lid = None
        matched_lname = list_name
        for t_name, lid in all_lists.items():
            if list_name in t_name or t_name in list_name:
                target_lid = lid
                matched_lname = t_name
                break

        if not target_lid:
            target_lid = all_lists.get("業務タスク") or next(iter(all_lists.values()), None)
            matched_lname = "業務タスク"

        body: dict[str, Any] = {"title": title.strip()}
        if due_date:
            due_str = due_date[:10]
            body["due"] = f"{due_str}T00:00:00.000Z"
        if notes:
            body["notes"] = notes.strip()

        url = f"https://tasks.googleapis.com/tasks/v1/lists/{target_lid}/tasks"
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code not in (200, 201):
            return {"error": f"Failed to create task (status {resp.status_code}): {resp.text}"}

        item = resp.json()
        due_disp = f"（期限: {item.get('due')[:10]}）" if item.get("due") else ""
        return {
            "status": "success",
            "message": f"「{matched_lname}」にタスク『{title}』{due_disp} を登録しました。",
            "task": {
                "id": item.get("id"),
                "list": matched_lname,
                "title": item.get("title"),
                "category": _categorize_task(title),
                "due": item.get("due")[:10] if item.get("due") else None,
            },
        }
    except Exception as e:
        logger.error(f"[create_todo_task] Error: {e}", exc_info=True)
        return {"error": str(e)}


def complete_todo_task(
    task_title_or_id: str,
    list_name: str | None = None,
) -> dict[str, Any]:
    """
    Mark a task as completed in Google Tasks.

    Args:
        task_title_or_id: Title of the task (or task ID) to complete.
        list_name: Target list name if known ('業務タスク' or 'マイタスク').

    Returns:
        dict: Result message.
    """
    try:
        token = _get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        all_lists = _get_task_lists(headers)

        target_lists = {}
        if list_name:
            for t_name, lid in all_lists.items():
                if list_name in t_name or t_name in list_name:
                    target_lists[t_name] = lid
            if not target_lists:
                target_lists = all_lists
        else:
            target_lists = all_lists

        for lname, lid in target_lists.items():
            t_url = f"https://tasks.googleapis.com/tasks/v1/lists/{lid}/tasks"
            resp = requests.get(t_url, headers=headers, params={"showCompleted": "false"}, timeout=10)
            if resp.status_code != 200:
                continue

            items = resp.json().get("items", [])
            for item in items:
                tid = item.get("id")
                ttitle = item.get("title", "")
                if tid == task_title_or_id or task_title_or_id in ttitle or ttitle in task_title_or_id:
                    # Update status to completed
                    patch_url = f"https://tasks.googleapis.com/tasks/v1/lists/{lid}/tasks/{tid}"
                    patch_resp = requests.patch(patch_url, headers=headers, json={"status": "completed"}, timeout=10)
                    if patch_resp.status_code == 200:
                        return {
                            "status": "success",
                            "message": f"「{lname}」のタスク『{ttitle}』を完了済みにマークしました！お疲れ様でした。",
                            "task_id": tid,
                            "title": ttitle,
                        }

        return {"status": "not_found", "message": f"『{task_title_or_id}』に一致する未完了タスクが見つかりませんでした。"}
    except Exception as e:
        logger.error(f"[complete_todo_task] Error: {e}", exc_info=True)
        return {"error": str(e)}


def update_todo_task(
    task_title_or_id: str,
    new_title: str | None = None,
    due_date: str | None = None,
    notes: str | None = None,
    list_name: str | None = None,
) -> dict[str, Any]:
    """
    Update an existing task in Google Tasks (rename title, change due date, update notes).

    Args:
        task_title_or_id: Existing title or ID of the task to update.
        new_title: New title for the task (if changing).
        due_date: New due date string (YYYY-MM-DD). Optional.
        notes: New notes / memo. Optional.
        list_name: Target list name ('業務タスク' or 'マイタスク'). Optional.

    Returns:
        dict: Result with updated task info.
    """
    try:
        token = _get_valid_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        all_lists = _get_task_lists(headers)

        target_lists = {}
        if list_name:
            for t_name, lid in all_lists.items():
                if list_name in t_name or t_name in list_name:
                    target_lists[t_name] = lid
            if not target_lists:
                target_lists = all_lists
        else:
            target_lists = all_lists

        patch_body: dict[str, Any] = {}
        if new_title is not None:
            patch_body["title"] = new_title.strip()
        if due_date is not None:
            due_str = due_date[:10]
            patch_body["due"] = f"{due_str}T00:00:00.000Z"
        if notes is not None:
            patch_body["notes"] = notes.strip()

        if not patch_body:
            return {"status": "error", "message": "更新内容（件名、期限日、メモ）が指定されていません。"}

        for lname, lid in target_lists.items():
            t_url = f"https://tasks.googleapis.com/tasks/v1/lists/{lid}/tasks"
            resp = requests.get(t_url, headers=headers, params={"showCompleted": "false"}, timeout=10)
            if resp.status_code != 200:
                continue

            items = resp.json().get("items", [])
            for item in items:
                tid = item.get("id")
                ttitle = item.get("title", "")
                if tid == task_title_or_id or task_title_or_id in ttitle or ttitle in task_title_or_id:
                    patch_url = f"https://tasks.googleapis.com/tasks/v1/lists/{lid}/tasks/{tid}"
                    patch_resp = requests.patch(patch_url, headers=headers, json=patch_body, timeout=10)
                    if patch_resp.status_code == 200:
                        updated_item = patch_resp.json()
                        final_title = updated_item.get("title", "")
                        return {
                            "status": "success",
                            "message": f"「{lname}」のタスク『{ttitle}』を『{final_title}』に更新しました。",
                            "task": {
                                "id": tid,
                                "list": lname,
                                "title": final_title,
                                "category": _categorize_task(final_title),
                                "due": updated_item.get("due")[:10] if updated_item.get("due") else None,
                                "notes": updated_item.get("notes", ""),
                            },
                        }

        return {"status": "not_found", "message": f"『{task_title_or_id}』に一致する未完了タスクが見つかりませんでした。"}
    except Exception as e:
        logger.error(f"[update_todo_task] Error: {e}", exc_info=True)
        return {"error": str(e)}



def check_tasks_token_health() -> dict[str, Any]:
    """Checks the health and remaining validity of the Google Tasks OAuth token.

    Returns a dict with 'status' ('healthy', 'warning', 'expired', or 'error') and details.
    """
    if not TOKEN_PATH.exists():
        return {
            "status": "error",
            "message": f"OAuth token not found at {TOKEN_PATH}",
            "healthy": False,
        }

    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        has_refresh_token = bool(data.get("refresh_token"))
        if not has_refresh_token:
            return {
                "status": "error",
                "message": "token.json does not contain a refresh_token",
                "healthy": False,
            }

        token = _get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            "https://tasks.googleapis.com/tasks/v1/users/@me/lists",
            headers=headers,
            timeout=5,
        )
        if resp.status_code == 200:
            return {
                "status": "healthy",
                "message": "Google Tasks OAuth token is active and functional.",
                "healthy": True,
            }
        else:
            return {
                "status": "warning",
                "message": f"Google Tasks API returned status {resp.status_code}: {resp.text}",
                "healthy": False,
            }
    except Exception as e:
        return {
            "status": "expired" if "invalid_grant" in str(e) else "error",
            "message": f"Token health check failed: {e}",
            "healthy": False,
        }
