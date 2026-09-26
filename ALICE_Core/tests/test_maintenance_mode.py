import pytest
from unittest.mock import MagicMock, patch
from core.system_settings import (
    get_system_settings,
    update_system_settings,
    is_maintenance_active,
    get_maintenance_message,
    is_admin_bypass_allowed,
    DEFAULT_SETTINGS,
)


def test_system_settings_lifecycle():
    """Verify system_settings load, update, and persist."""
    # Reset to default
    update_system_settings({
        "maintenance_mode": False,
        "maintenance_message": "テスト用メンテメッセージ",
        "admin_bypass": True,
    })

    assert is_maintenance_active() is False
    assert is_admin_bypass_allowed() is True
    assert get_maintenance_message() == "テスト用メンテメッセージ"

    # Turn ON
    update_system_settings({"maintenance_mode": True})
    assert is_maintenance_active() is True

    # Turn OFF
    update_system_settings({"maintenance_mode": False})
    assert is_maintenance_active() is False


@pytest.mark.anyio
async def test_admin_maintenance_api():
    """Verify admin API endpoints for maintenance mode."""
    from portal.admin import get_metrics, get_maintenance_api, update_maintenance_api
    from fastapi import Request

    # 1. Metrics includes maintenance
    metrics = await get_metrics()
    assert "maintenance" in metrics
    assert "active" in metrics["maintenance"]
    assert "message" in metrics["maintenance"]

    # 2. Get maintenance settings
    settings = await get_maintenance_api()
    assert "maintenance_mode" in settings
    assert "maintenance_message" in settings

    # 3. Update maintenance settings via mock request
    from unittest.mock import AsyncMock
    mock_req = MagicMock(spec=Request)
    mock_req.json = AsyncMock(return_value={
        "maintenance_mode": True,
        "maintenance_message": "現在緊急メンテナンス中です。",
        "admin_bypass": False,
    })

    resp = await update_maintenance_api(mock_req)
    assert resp["status"] == "ok"
    assert resp["settings"]["maintenance_mode"] is True
    assert resp["settings"]["maintenance_message"] == "現在緊急メンテナンス中です。"
    assert resp["settings"]["admin_bypass"] is False

    # Cleanup: restore to OFF
    update_system_settings({
        "maintenance_mode": False,
        "maintenance_message": DEFAULT_SETTINGS["maintenance_message"],
        "admin_bypass": True,
    })


def test_line_message_handler_maintenance_guard():
    """Verify MessageHandler blocks guest/users when maintenance is active."""
    from gateway.handlers.message import MessageHandler

    handler = MessageHandler()
    mock_sender = MagicMock()
    handler.sender = mock_sender

    # 1. Maintenance OFF: normal flow
    update_system_settings({"maintenance_mode": False})
    event = {
        "source": {"userId": "guest_user_123"},
        "replyToken": "token_123",
        "message": {"type": "text", "text": "こんにちは"}
    }

    with patch.object(handler.repository, "find", return_value=None):
        handler.handle(event)
        # Not found user in normal mode gives "ユーザー情報が見つかりません"
        mock_sender.reply_text.assert_called_with("token_123", "ユーザー情報が見つかりません。\n一度友だち追加し直してください。")

    # 2. Maintenance ON: intercepts BEFORE anything else!
    update_system_settings({
        "maintenance_mode": True,
        "maintenance_message": "只今メンテナンス中です。",
        "admin_bypass": True,
    })

    mock_sender.reset_mock()
    handler.handle(event)

    # Must reply with maintenance message and stop immediately
    mock_sender.reply_text.assert_called_once_with("token_123", "只今メンテナンス中です。")

    # 3. Admin user bypass
    with patch("config.LINE_ADMIN_USER", "admin_line_id"):
        admin_event = {
            "source": {"userId": "admin_line_id"},
            "replyToken": "token_admin",
            "message": {"type": "text", "text": "テスト"}
        }
        mock_sender.reset_mock()
        with patch.object(handler.repository, "find", return_value=None):
            handler.handle(admin_event)
            # Admin passed the maintenance guard and reached repository.find!
            mock_sender.reply_text.assert_called_with("token_admin", "ユーザー情報が見つかりません。\n一度友だち追加し直してください。")

    # Cleanup
    update_system_settings({"maintenance_mode": False})
