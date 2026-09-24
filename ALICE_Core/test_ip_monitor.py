"""
Unit tests for Global IP Change Monitor (core.ip_monitor).
Verifies provider fallback, baseline establishment, change detection, and Discord alerting.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.ip_monitor import (
    check_and_notify_ip_change,
    fetch_current_global_ip,
    get_cached_global_ip,
    save_cached_global_ip,
)


def test_fetch_current_global_ip_success():
    """Verify IP is fetched successfully from primary provider."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "180.196.23.177\n"

    with patch("requests.get", return_value=mock_resp):
        ip = fetch_current_global_ip()
        assert ip == "180.196.23.177"


def test_fetch_current_global_ip_fallback():
    """Verify fallback to second provider when first fails."""
    fail_resp = MagicMock()
    fail_resp.status_code = 500

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.text = "203.0.113.10"

    with patch("requests.get", side_effect=[Exception("Network error"), ok_resp]):
        ip = fetch_current_global_ip()
        assert ip == "203.0.113.10"


def test_fetch_current_global_ip_all_fail():
    """Verify None is returned if all providers fail."""
    with patch("requests.get", side_effect=Exception("Timeout")):
        ip = fetch_current_global_ip()
        assert ip is None


def test_baseline_initialization(tmp_path):
    """First run should save baseline without sending an alert."""
    cache_file = tmp_path / "last_ip.txt"

    with patch("core.ip_monitor.fetch_current_global_ip", return_value="180.196.23.177"):
        with patch("core.ip_monitor.send_system_alert") as mock_alert:
            res = check_and_notify_ip_change(cache_file=cache_file)
            assert res["status"] == "initialized"
            assert res["current_ip"] == "180.196.23.177"
            assert res["previous_ip"] is None
            assert res["alert_sent"] is False
            mock_alert.assert_not_called()

            # Verify file was written
            assert cache_file.exists()
            assert cache_file.read_text(encoding="utf-8") == "180.196.23.177"


def test_ip_unchanged(tmp_path):
    """Subsequent checks with the same IP do not trigger alert."""
    cache_file = tmp_path / "last_ip.txt"
    cache_file.write_text("180.196.23.177", encoding="utf-8")

    with patch("core.ip_monitor.fetch_current_global_ip", return_value="180.196.23.177"):
        with patch("core.ip_monitor.send_system_alert") as mock_alert:
            res = check_and_notify_ip_change(cache_file=cache_file)
            assert res["status"] == "unchanged"
            assert res["current_ip"] == "180.196.23.177"
            assert res["alert_sent"] is False
            mock_alert.assert_not_called()


def test_ip_change_triggers_alert(tmp_path):
    """IP change triggers send_system_alert and updates cache file."""
    cache_file = tmp_path / "last_ip.txt"
    cache_file.write_text("180.196.23.177", encoding="utf-8")

    with patch("core.ip_monitor.fetch_current_global_ip", return_value="133.200.50.60"):
        with patch("core.ip_monitor.send_system_alert", return_value=True) as mock_alert:
            res = check_and_notify_ip_change(cache_file=cache_file)
            assert res["status"] == "changed"
            assert res["previous_ip"] == "180.196.23.177"
            assert res["current_ip"] == "133.200.50.60"
            assert res["alert_sent"] is True

            mock_alert.assert_called_once()
            call_kwargs = mock_alert.call_args.kwargs
            assert "旧IP (Previous)" in call_kwargs["extra_fields"]
            assert call_kwargs["extra_fields"]["旧IP (Previous)"] == "180.196.23.177"
            assert call_kwargs["extra_fields"]["新IP (Current)"] == "133.200.50.60"

            # Cache file must be updated to new IP
            assert cache_file.read_text(encoding="utf-8") == "133.200.50.60"
