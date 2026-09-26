import sys
from pathlib import Path
import pytest

COPILOT_DIR = Path("/home/takuya/Project_ALICE/ALICE_CoPilot")
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
    task_res = check_task_state(query="新人面談アポ", list_name="業務タスク")
    assert "新人面談アポ" in task_res
    print("All tasks & reviewer tests passed!")

def test_audit_codebase_architecture_tool():
    from reviewer.tools import audit_codebase_architecture
    audit_res = audit_codebase_architecture("ALICE_Core")
    assert "ALICE_Core アーキテクチャ＆レイヤー整合性診断" in audit_res
    assert "Project_ALICE_Architecture" in audit_res or "健全" in audit_res or "モジュール肥大化" in audit_res
    print("audit_codebase_architecture test passed!")

if __name__ == "__main__":
    test_tasks_token_health()
    test_repair_tasks_state_dry_run()
    test_audit_codebase_architecture_tool()
    print("SUCCESS: All custom tests passed!")
