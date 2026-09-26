import sys
from pathlib import Path
import pytest

COPILOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COPILOT_DIR))

def test_tasks_token_health():
    from tools.tasks_tools import check_tasks_token_health
    res = check_tasks_token_health()
    assert res["status"] == "healthy"
    assert res["healthy"] is True

def test_repair_tasks_state_dry_run():
    from reviewer.tools import repair_tasks_state, REVIEW_STATE, reset_review_state
    reset_review_state()
    
    # Test invalid action
    res_inv = repair_tasks_state(action="invalid_action")
    assert "未知のタスク修復アクション" in res_inv
    
    # Test missing title on create
    res_no_title = repair_tasks_state(action="create", title="")
    assert "タイトルが指定されていません" in res_no_title
    
    # Test real get_todo_tasks integration via check_task_state
    from reviewer.tools import check_task_state
    task_res = check_task_state(query="江口", list_name="業務タスク")
    assert "江口さん症状確認" in task_res
    print("All tasks & reviewer tests passed!")

if __name__ == "__main__":
    test_tasks_token_health()
    test_repair_tasks_state_dry_run()
    print("SUCCESS: Custom tests passed!")
