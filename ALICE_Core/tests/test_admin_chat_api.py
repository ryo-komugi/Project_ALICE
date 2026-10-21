"""
Tests for Admin Chat API endpoints and Cockpit HTML.
"""
import pytest
import re
from portal.admin import get_admin_dashboard


@pytest.mark.anyio
async def test_admin_dashboard_html_excludes_line_elements():
    """Verify admin cockpit HTML excludes LINE service badges and text elements."""
    response = await get_admin_dashboard()
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert 'id="svc-line"' not in html
    assert 'LINE Gateway' not in html
    assert 'LINE User ID' not in html
    assert 'LINE友だち' not in html
    assert 'LINE_ADMIN_USER' not in html
    assert not re.search(r'\bLINE\b', html)

from portal.chat_proxy import get_chat_status, get_chat_history, clear_chat_history, ChatClearRequest


@pytest.mark.anyio
async def test_admin_dashboard_html_excludes_users_tab():
    """Verify admin cockpit HTML excludes User Directory elements."""
    response = await get_admin_dashboard()
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert 'id="tab-users"' not in html
    assert 'id="nav-users"' not in html
    assert 'id="mob-users"' not in html
    assert 'User Directory' not in html


@pytest.mark.anyio
async def test_admin_dashboard_html_excludes_chat_tab():
    """Verify admin cockpit HTML excludes personal AI Console elements."""
    response = await get_admin_dashboard()
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert 'id="tab-chat"' not in html
    assert 'id="nav-chat"' not in html
    assert 'id="mob-chat"' not in html
    assert 'id="voice-chat-modal"' not in html
    assert 'AI Console' not in html


@pytest.mark.anyio
async def test_chat_status_endpoint():
    """Verify get_chat_status returns valid Ollama and Antigravity structure."""
    resp = await get_chat_status()
    # If resp is JSONResponse or dict
    if hasattr(resp, "body"):
        import json
        data = json.loads(resp.body.decode("utf-8"))
    else:
        data = resp

    assert "ollama" in data
    assert "antigravity" in data
    assert isinstance(data["ollama"]["model"], str) and len(data["ollama"]["model"]) > 0
    assert "model" in data["antigravity"]
    # Model should be non-empty (either local gemma4:12b or cloud model)
    ag_model = data["antigravity"].get("selected_model") or data["antigravity"].get("model")
    assert bool(ag_model)


@pytest.mark.anyio
async def test_chat_history_endpoint():
    """Verify get_chat_history handles assistant and copilot modes."""
    resp_assistant = await get_chat_history(mode="assistant", limit=10)
    if hasattr(resp_assistant, "body"):
        import json
        data_a = json.loads(resp_assistant.body.decode("utf-8"))
    else:
        data_a = resp_assistant
    assert data_a["session_id"] == "web_assistant"

    resp_copilot = await get_chat_history(mode="copilot", limit=10)
    if hasattr(resp_copilot, "body"):
        import json
        data_c = json.loads(resp_copilot.body.decode("utf-8"))
    else:
        data_c = resp_copilot
    assert data_c["session_id"] == "web_copilot"
