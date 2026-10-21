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

