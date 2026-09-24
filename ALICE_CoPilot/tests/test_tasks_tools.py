"""
Unit tests for Google Tasks integration tools.
"""
from unittest.mock import MagicMock, patch
import pytest

from tools import TOOLS_SCHEMA
from tools.tasks_tools import (
    _categorize_task,
    get_todo_tasks,
    create_todo_task,
    complete_todo_task,
    update_todo_task,
)


def test_tasks_tools_in_schema():
    tool_names = {t["function"]["name"] for t in TOOLS_SCHEMA}
    assert "get_todo_tasks" in tool_names
    assert "create_todo_task" in tool_names
    assert "complete_todo_task" in tool_names
    assert "update_todo_task" in tool_names


def test_categorize_task():
    assert _categorize_task("【提〆】動静表") == "提出期限"
    assert _categorize_task("【回答〆】駅伝アンケート") == "回答期限"
    assert _categorize_task("【展開〆】仕様書レビュー") == "展開期限"
    assert _categorize_task("【SmartHR】年末調整") == "手続き"
    assert _categorize_task("本を買う") == "一般タスク"


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"業務タスク": "list_work_id", "マイタスク": "list_my_id"})
@patch("requests.get")
def test_get_todo_tasks_mock(mock_get, mock_lists, mock_token):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "t1",
                "title": "【提〆】動静表提出",
                "status": "needsAction",
                "due": "2026-09-15T00:00:00.000Z",
                "notes": "17時まで",
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = get_todo_tasks(list_name="業務タスク")
    assert res["total"] == 1
    assert "業務タスク" in res["lists"]
    t = res["lists"]["業務タスク"][0]
    assert t["title"] == "【提〆】動静表提出"
    assert t["category"] == "提出期限"
    assert t["due"] == "2026-09-15"


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"業務タスク": "list_work_id"})
@patch("requests.get")
def test_get_todo_tasks_query_filter(mock_get, mock_lists, mock_token):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "t1",
                "title": "【提〆】動静表",
                "status": "completed",
                "due": "2026-09-15T00:00:00.000Z",
                "notes": "",
            },
            {
                "id": "t2",
                "title": "新人面談アポ",
                "status": "needsAction",
                "due": "2026-09-17T00:00:00.000Z",
                "notes": "",
            },
        ]
    }
    mock_get.return_value = mock_resp

    # Query matches "動静表" with status="all"
    res_match = get_todo_tasks(list_name="業務タスク", status="all", query="動静表")
    assert res_match["total"] == 1
    assert res_match["lists"]["業務タスク"][0]["title"] == "【提〆】動静表"
    assert res_match["lists"]["業務タスク"][0]["status"] == "完了済"

    # Query does not match
    res_nomatch = get_todo_tasks(list_name="業務タスク", status="all", query="存在しないタスク")
    assert res_nomatch["total"] == 0


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"業務タスク": "list_work_id"})
@patch("requests.post")
def test_create_todo_task_mock(mock_post, mock_lists, mock_token):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "t_new_123",
        "title": "【提〆】月報作成",
        "status": "needsAction",
        "due": "2026-09-30T00:00:00.000Z",
    }
    mock_post.return_value = mock_resp

    res = create_todo_task(
        title="【提〆】月報作成",
        list_name="業務タスク",
        due_date="2026-09-30",
        notes="下書き作成",
    )
    assert res["status"] == "success"
    assert res["task"]["id"] == "t_new_123"
    assert res["task"]["category"] == "提出期限"


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"マイタスク": "list_my_id"})
@patch("requests.patch")
@patch("requests.get")
def test_complete_todo_task_mock(mock_get, mock_patch, mock_lists, mock_token):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "items": [
            {"id": "t_done_1", "title": "牛乳を買う", "status": "needsAction"}
        ]
    }
    mock_get.return_value = mock_get_resp

    mock_patch_resp = MagicMock()
    mock_patch_resp.status_code = 200
    mock_patch_resp.json.return_value = {
        "id": "t_done_1",
        "title": "牛乳を買う",
        "status": "completed",
    }
    mock_patch.return_value = mock_patch_resp

    res = complete_todo_task(task_title_or_id="牛乳を買う", list_name="マイタスク")
    assert res["status"] == "success"
    assert "完了済みにマークしました" in res["message"]
    assert res["task_id"] == "t_done_1"


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"業務タスク": "list_work_id"})
@patch("requests.patch")
@patch("requests.get")
def test_update_todo_task_mock(mock_get, mock_patch, mock_lists, mock_token):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "items": [
            {"id": "t_work_1", "title": "【提〆】新人面談アポ通知 17:30", "status": "needsAction"}
        ]
    }
    mock_get.return_value = mock_get_resp

    mock_patch_resp = MagicMock()
    mock_patch_resp.status_code = 200
    mock_patch_resp.json.return_value = {
        "id": "t_work_1",
        "title": "新人面談アポ",
        "due": "2026-09-17T00:00:00.000Z",
        "notes": "時計台会議室",
    }
    mock_patch.return_value = mock_patch_resp

    res = update_todo_task(
        task_title_or_id="新人面談アポ",
        new_title="新人面談アポ",
        due_date="2026-09-17",
        notes="時計台会議室",
        list_name="業務タスク",
    )
    assert res["status"] == "success"
    assert "更新しました" in res["message"]
    assert res["task"]["title"] == "新人面談アポ"
    assert res["task"]["category"] == "一般タスク"
    assert res["task"]["due"] == "2026-09-17"


@patch("tools.tasks_tools._get_valid_token", return_value="fake_token")
@patch("tools.tasks_tools._get_task_lists", return_value={"業務タスク": "list_work_id"})
@patch("requests.get")
def test_get_todo_tasks_due_max_param(mock_get, mock_lists, mock_token):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "t1",
                "title": "今日のタスク",
                "status": "needsAction",
                "due": "2026-09-18T00:00:00.000Z",
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = get_todo_tasks(due_max="2026-09-18")
    assert res["total"] == 1
    # Verify dueMax parameter passed to Google Tasks API is next day 00:00:00Z
    call_args = mock_get.call_args
    assert call_args[1]["params"]["dueMax"] == "2026-09-19T00:00:00Z"


