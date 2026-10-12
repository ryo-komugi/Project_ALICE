import config
"""
Integration tests for ALICE_Minutes pipeline within ALICE_Core.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hub.worker import CoreWorker, MODULE_RUNNERS
from gateway.handlers.message import MessageHandler, WORKFLOW_MAP
from publisher.line_publisher import LinePublisher
from models.job import Job, JobStatus
from hub.workspace import WorkspaceManager
from hub.queue import JobQueue


def test_minutes_runner_registered():
    """Verify MODULE_RUNNERS contains minutes with valid contract."""
    assert "minutes" in MODULE_RUNNERS
    runner = MODULE_RUNNERS["minutes"]
    assert runner["artifact_dir"] == "minutes"
    assert runner["primary_artifact"] == "minutes.md"
    assert "minutes.txt" in runner["contract_artifacts"]
    assert "minutes.md" in runner["contract_artifacts"]
    assert "analysis.json" in runner["contract_artifacts"]


def test_workflow_map_minutes():
    """Verify WORKFLOW_MAP contains Minutes mapping with hybrid summary pipeline."""
    assert "Minutes" in WORKFLOW_MAP
    assert WORKFLOW_MAP["Minutes"] == ["transcript", "summary", "minutes"]


@patch("gateway.handlers.message.UserRepository")
def test_message_handler_minutes_routing(mock_user_repo_cls):
    """Verify MessageHandler routes '議事録' command to WAIT_FILE with Minutes workflow."""
    handler = MessageHandler()
    handler.repository.find = MagicMock(return_value=MagicMock(status="READY"))
    handler.sender.reply_text = MagicMock()
    handler.richmenu.switch = MagicMock()

    user_id = "U_test_minutes_user"
    reply_token = "reply_token_123"

    handler.handle_text(user=MagicMock(), user_id=user_id, reply_token=reply_token, text="議事録")

    session = handler.session_manager.get(user_id)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Minutes"
    handler.sender.reply_text.assert_called_once()
    assert "議事録ですね" in handler.sender.reply_text.call_args[0][1]


def test_line_publisher_minutes(tmp_path, monkeypatch):
    share_dir = tmp_path / 'share'
    share_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, 'DIR_SHARE', str(share_dir))
    """Verify LinePublisher handles minutes with pure Flex Card delivery (Pattern A)."""
    publisher = LinePublisher()
    publisher.sender.push_text = MagicMock()
    publisher.sender.push_flex = MagicMock()

    minutes_file = tmp_path / "test_minutes.txt"
    minutes_file.write_text("■ 決定事項\n・新機能リリースを決定", encoding="utf-8")

    try:
        publisher.publish(str(minutes_file), "user_123", module_name="minutes")

        # Verify push_text is NOT called (Pattern A: pure card notification without dumping text)
        publisher.sender.push_text.assert_not_called()

        # Verify push_flex was called
        publisher.sender.push_flex.assert_called_once()
        flex_payload = publisher.sender.push_flex.call_args[0][1]
        assert "議事録作成が完了しました" in json.dumps(flex_payload, ensure_ascii=False)
    finally:
        share_f = Path(config.DIR_SHARE) / "test_minutes.txt"
        if share_f.exists():
            share_f.unlink()


def test_core_worker_executes_minutes(tmp_path, monkeypatch):
    share_dir = tmp_path / 'share'
    share_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, 'DIR_SHARE', str(share_dir))
    """Verify CoreWorker executes minutes runner and completes job."""
    wm = WorkspaceManager(base_dir=tmp_path / "workspaces")
    queue = JobQueue()

    # Create job
    dummy_input = tmp_path / "meeting.mp3"
    dummy_input.write_bytes(b"dummy audio")

    job = wm.create_workspace(
        user_id="user_minutes_e2e",
        src_file=str(dummy_input),
        workflow=["minutes"],
        original_filename="meeting.mp3",
    )

    # Put mock transcript in workspace
    (job.transcript_dir / "transcript.json").write_text(
        json.dumps({
            "segments": [
                {"start": 0.0, "speaker": "SPEAKER_00", "text": "本日の議題は来期予算についてです。"},
                {"start": 5.0, "speaker": "SPEAKER_01", "text": "承認されました。"}
            ]
        }),
        encoding="utf-8",
    )

    # Mock python script for minutes CLI that produces minutes artifacts
    minutes_cli = tmp_path / "mock_minutes_cli.py"
    minutes_cli.write_text(
        '''import sys, json, os, argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
args, _ = parser.parse_known_args()

ws = Path(args.workspace)
min_dir = ws / "minutes"
min_dir.mkdir(parents=True, exist_ok=True)
(min_dir / "minutes.txt").write_text("■ 議事録\\n・予算承認", encoding="utf-8")
(min_dir / "minutes.md").write_text("# 議事録\\n- 予算承認", encoding="utf-8")
(min_dir / "analysis.json").write_text("{}", encoding="utf-8")
(min_dir / "metadata.json").write_text("{}", encoding="utf-8")
sys.exit(0)
''',
        encoding="utf-8",
    )

    custom_runners = {
        "minutes": {
            "python_bin": "/usr/bin/python3",
            "cli_path": str(minutes_cli),
            "module_cwd": str(tmp_path),
            "artifact_dir": "minutes",
            "primary_artifact": "minutes.md",
            "contract_artifacts": ["minutes.txt", "minutes.md", "analysis.json", "metadata.json"],
        }
    }

    mock_publisher = MagicMock()
    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_publisher,
        module_runners=custom_runners,
    )

    # Run job
    success = worker.process_job(job)
    assert success is True

    reloaded_job = wm.load_job(job.workspace_dir)
    assert reloaded_job.status == JobStatus.COMPLETED
    assert (job.workspace_dir / "minutes" / "minutes.txt").exists()
    assert (job.workspace_dir / "minutes" / "minutes.md").exists()
    mock_publisher.publish.assert_called_once()


def test_publish_result_bundles_summary_and_commentary(tmp_path, monkeypatch):
    share_dir = tmp_path / 'share'
    share_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, 'DIR_SHARE', str(share_dir))
    """Verify _publish_result bundles summary and commentary artifacts when publishing minutes."""
    wm = WorkspaceManager(base_dir=tmp_path / "workspaces")
    queue = JobQueue()

    dummy_input = tmp_path / "meeting2.mp3"
    dummy_input.write_bytes(b"dummy audio")

    job = wm.create_workspace(
        user_id="user_bundle_test",
        src_file=str(dummy_input),
        workflow=["transcript", "summary", "minutes"],
        original_filename="meeting2.mp3",
    )

    # Simulate summary artifacts
    sum_dir = job.workspace_dir / "summary"
    (sum_dir / "summary.md").write_text("# 要約本文", encoding="utf-8")
    (sum_dir / "summary.txt").write_text("■ 要約本文", encoding="utf-8")
    (sum_dir / "commentary.md").write_text("# 解説本文", encoding="utf-8")
    (sum_dir / "commentary.txt").write_text("■ 解説本文", encoding="utf-8")

    # Simulate minutes artifacts
    min_dir = job.workspace_dir / "minutes"
    min_md = min_dir / "minutes.md"
    min_txt = min_dir / "minutes.txt"
    min_md.write_text("# 議事録本文", encoding="utf-8")
    min_txt.write_text("■ 議事録本文", encoding="utf-8")

    mock_publisher = MagicMock()
    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_publisher,
    )

    worker._publish_result(job, min_md, "minutes")

    mock_publisher.publish.assert_called_once()
    publish_args = mock_publisher.publish.call_args[0]
    publish_kwargs = mock_publisher.publish.call_args[1]

    # Primary artifact published
    assert "minutes_minutes.md" in publish_args[0]
    assert publish_kwargs.get("module_name") == "minutes"

    # Extra files bundled
    extra = publish_kwargs.get("extra_files", {})
    assert "summary" in extra
    assert "commentary" in extra
    assert Path(extra["summary"]).exists()
    assert Path(extra["commentary"]).exists()
