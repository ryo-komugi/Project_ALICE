"""
Unit tests for ALICE_Core alert_notifier.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.alert_notifier import send_discord_alert, send_system_alert
from models.job import Job, JobStatus


@pytest.fixture
def sample_job():
    job = Job(
        job_id="job_test_alert_001",
        user_id="user_test_123",
        input_file=Path("/tmp/test_workspace/input/meeting.mp3"),
        workspace_dir=Path("/tmp/test_workspace"),
        workflow=["transcript", "summary"],
        status=JobStatus.FAILED,
        current_step="transcript",
        error_message="Process exited with exit code 42",
        error_detail={
            "failed_step": "transcript",
            "error_type": "MODULE_EXECUTION_ERROR",
            "exit_code": 42,
            "message": "Process exited with exit code 42 (OOM)",
            "log_file": "/tmp/test.log",
        },
        input_metadata={"original_filename": "meeting_recording.mp3"},
    )
    return job


def test_send_discord_alert_skipped_when_no_webhook(sample_job):
    with patch("core.alert_notifier.config") as mock_config:
        mock_config.DISCORD_ALERT_WEBHOOK_URL = ""
        res = send_discord_alert(sample_job, error_type="TEST_ERROR", message="test message")
        assert res is False


def test_send_discord_alert_success(sample_job):
    fake_url = "https://discord.com/api/webhooks/mock_test_url"
    with patch("core.alert_notifier.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        res = send_discord_alert(
            sample_job,
            error_type="STEP_FAILED",
            message="OOM detected during transcript",
            level="ERROR",
            webhook_url=fake_url,
        )

        assert res is True
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert args[0] == fake_url
        payload = kwargs["json"]
        embed = payload["embeds"][0]
        assert "[ERROR] STEP_FAILED" in embed["title"]
        assert embed["color"] == 0xE74C3C

        field_names = [f["name"] for f in embed["fields"]]
        assert "Job ID" in field_names
        assert "対象ファイル" in field_names
        assert "失敗ステップ" in field_names
        assert "エラー詳細" in field_names

        # Verify no noisy emojis
        for emoji in ["⚠️", "🔍", "❌", "🚨", "📄", "📅"]:
            assert emoji not in embed["title"]
            for f in embed["fields"]:
                assert emoji not in f["name"]
                assert emoji not in f["value"]


def test_send_discord_alert_handles_request_exception(sample_job):
    fake_url = "https://discord.com/api/webhooks/mock_test_url"
    with patch("core.alert_notifier.requests.post", side_effect=Exception("Network Timeout")):
        res = send_discord_alert(
            sample_job,
            error_type="TIMEOUT_TEST",
            message="Should handle safely",
            webhook_url=fake_url,
        )
        assert res is False


def test_send_system_alert():
    fake_url = "https://discord.com/api/webhooks/mock_test_url"
    with patch("core.alert_notifier.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        res = send_system_alert(
            title="サーバー再起動復旧",
            message="1件の中断ジョブを安全にクローズしました",
            level="WARN",
            webhook_url=fake_url,
        )
        assert res is True
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        embed = payload["embeds"][0]
        assert "[WARN] サーバー再起動復旧" in embed["title"]
        assert embed["color"] == 0xF39C12
