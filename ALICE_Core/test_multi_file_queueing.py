import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

CORE_DIR = Path(__file__).resolve().parent
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import pytest

from core.session_manager import SessionManager
from line.message_handler import MessageHandler
from repository.user_repository import UserRepository
from auth.user import User
from auth.user_status import UserStatus
from models.job import Job, JobStatus


REAL_USER_ID = "U_test_multi_file_user"


@pytest.fixture
def mock_handler(tmp_path, monkeypatch):
    """Set up MessageHandler with mocked dependencies and isolated directories."""
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    ws_dir = tmp_path / "workspaces"
    ws_dir.mkdir(parents=True, exist_ok=True)

    import config
    monkeypatch.setattr(config, "DIR_INBOX", str(inbox_dir))
    monkeypatch.setattr(config, "DIR_WORKSPACES", str(ws_dir))
    
    from core.container import workspace_manager, job_queue
    monkeypatch.setattr(workspace_manager, "base_dir", ws_dir)

    # Empty queue before test
    while not job_queue.empty():
        job_queue.pop(block=False)

    handler = MessageHandler()
    
    def fake_download(message_id, save_path):
        p = Path(save_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake audio data")

    handler.downloader = MagicMock()
    handler.downloader.download.side_effect = fake_download
    handler.sender = MagicMock()
    handler.richmenu = MagicMock()
    
    # Mock user repository to always return a READY user
    test_user = User(
        user_id=REAL_USER_ID,
        display_name="Test Multi User",
        status=UserStatus.READY
    )
    handler.repository = MagicMock()
    handler.repository.find.return_value = test_user
    
    # Isolate session manager
    handler.session_manager = SessionManager(default_burst_seconds=2.0)
    
    yield handler

    # Clean queue after test
    while not job_queue.empty():
        job_queue.pop(block=False)


def test_session_manager_burst_logic():
    """Test SessionManager core burst evaluation."""
    sm = SessionManager(default_burst_seconds=2.0)
    uid = "user_test_sm"
    
    # Initially IDLE -> cannot accept
    assert sm.can_accept_file(uid) is False
    assert sm.is_in_burst(uid) is False
    
    # WAIT_FILE set -> can accept first file
    sm.set_wait_file(uid, "Minutes")
    assert sm.can_accept_file(uid) is True
    assert sm.is_in_burst(uid) is False  # No file received yet
    
    # Record first file -> now in burst
    sm.record_file_received(uid, burst_seconds=2.0)
    session = sm.get(uid)
    assert session.file_count == 1
    assert session.last_file_at is not None
    assert sm.is_in_burst(uid) is True
    assert sm.can_accept_file(uid) is True
    
    # Simulate time passing beyond burst window
    session.last_file_at = datetime.now() - timedelta(seconds=3.0)
    assert sm.is_in_burst(uid) is False
    assert sm.can_accept_file(uid) is False


def test_multi_file_burst_queueing(mock_handler, tmp_path, monkeypatch):
    """Test sending multiple audio files in sequence during burst window."""
    from core.container import job_queue
        
    handler = mock_handler
    user = handler.repository.find(REAL_USER_ID)
    
    # 1. User selects "議事録"
    handler.handle_text(user, REAL_USER_ID, "tok_menu", "議事録")
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Minutes"
    
    # 2. File 1 arrives
    event_file1 = {
        "replyToken": "tok_f1",
        "message": {
            "id": "msg_f1",
            "type": "file",
            "fileName": "meeting_part1.mp4"
        }
    }
    handler.handle_file(user, REAL_USER_ID, "tok_f1", event_file1)
    
    assert job_queue.size() == 1
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.file_count == 1
    assert handler.session_manager.is_in_burst(REAL_USER_ID) is True
    assert "受付けました" in handler.sender.reply_text.call_args[0][1]
    assert "meeting_part1.mp4" in handler.sender.reply_text.call_args[0][1]
    
    # 3. File 2 arrives 0.1s later (burst)
    event_file2 = {
        "replyToken": "tok_f2",
        "message": {
            "id": "msg_f2",
            "type": "file",
            "fileName": "meeting_part2.mp4"
        }
    }
    handler.handle_file(user, REAL_USER_ID, "tok_f2", event_file2)
    
    assert job_queue.size() == 2
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.file_count == 2
    assert "meeting_part2.mp4" in handler.sender.reply_text.call_args[0][1]
    
    # 4. Audio (native LINE voice message) arrives 0.1s later
    event_audio3 = {
        "replyToken": "tok_f3",
        "message": {
            "id": "msg_f3",
            "type": "audio"
        }
    }
    handler.handle_audio(user, REAL_USER_ID, "tok_f3", event_audio3)
    
    assert job_queue.size() == 3
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.file_count == 3
    
    # Verify FIFO queue content and workflows
    job1 = job_queue.pop(block=False)
    job2 = job_queue.pop(block=False)
    job3 = job_queue.pop(block=False)
    
    assert "meeting_part1" in job1.input_file.name
    assert "meeting_part2" in job2.input_file.name
    assert "audio_msg_f3" in job3.input_file.name
    assert job1.workflow == ["transcript", "summary", "minutes"]
    assert job2.workflow == ["transcript", "summary", "minutes"]
    assert job3.workflow == ["transcript", "summary", "minutes"]


def test_idle_state_strictly_rejects_audio(mock_handler):
    """Test audio/file sent in IDLE state is strictly rejected."""
    from core.container import job_queue
        
    handler = mock_handler
    user = handler.repository.find(REAL_USER_ID)
    
    # Session is IDLE
    assert handler.session_manager.get(REAL_USER_ID).state == "IDLE"
    
    event = {
        "replyToken": "tok_err",
        "message": {
            "id": "msg_err",
            "type": "audio"
        }
    }
    handler.handle_audio(user, REAL_USER_ID, "tok_err", event)
    
    # Rejection reply sent
    handler.sender.reply_text.assert_called_once()
    assert "先にリッチメニューから機能を選択してください" in handler.sender.reply_text.call_args[0][1]
    
    # Queue is completely empty
    assert job_queue.empty() is True


def test_audio_rejected_after_burst_expires(mock_handler):
    """Test audio sent after burst window has elapsed is rejected."""
    from core.container import job_queue
    handler = mock_handler
    user = handler.repository.find(REAL_USER_ID)
    
    # 1. Start minutes workflow
    handler.session_manager.set_wait_file(REAL_USER_ID, "Minutes")
    
    # 2. File 1 accepted
    event1 = {
        "replyToken": "tok_1",
        "message": {"id": "m1", "type": "file", "fileName": "f1.mp4"}
    }
    handler.handle_file(user, REAL_USER_ID, "tok_1", event1)
    
    # 3. Simulate burst expiration (> 2.0s)
    session = handler.session_manager.get(REAL_USER_ID)
    session.last_file_at = datetime.now() - timedelta(seconds=5.0)
    
    # 4. File 2 arrives after expiration
    event2 = {
        "replyToken": "tok_2",
        "message": {"id": "m2", "type": "file", "fileName": "f2.mp4"}
    }
    handler.handle_file(user, REAL_USER_ID, "tok_2", event2)
    
    # Verified rejected
    last_reply = handler.sender.reply_text.call_args[0][1]
    assert "先にリッチメニューから機能を選択してください" in last_reply
    # Session reset to IDLE
    assert handler.session_manager.get(REAL_USER_ID).state == "IDLE"


def test_burst_timer_auto_resets_session(mock_handler):
    """Test burst timer automatically resets session to IDLE after timeout."""
    from core.container import job_queue
    handler = mock_handler
    user = handler.repository.find(REAL_USER_ID)
    
    # Use very short burst for fast test
    handler.session_manager.default_burst_seconds = 0.1
    handler.session_manager.set_wait_file(REAL_USER_ID, "Minutes")
    
    event = {
        "replyToken": "tok_auto",
        "message": {"id": "m_auto", "type": "file", "fileName": "auto.mp4"}
    }
    handler.handle_file(user, REAL_USER_ID, "tok_auto", event)
    
    assert handler.session_manager.get(REAL_USER_ID).state == "WAIT_FILE"
    
    # Wait for timer to expire
    time.sleep(0.3)
    
    # Session should now be IDLE
    assert handler.session_manager.get(REAL_USER_ID).state == "IDLE"
    handler.richmenu.switch.assert_called_with(REAL_USER_ID, "UserMenu")


def test_text_after_files_resets_session_to_idle(mock_handler):
    """Test user text after sending files explicitly concludes reception."""
    from core.container import job_queue
    handler = mock_handler
    user = handler.repository.find(REAL_USER_ID)
    
    handler.session_manager.set_wait_file(REAL_USER_ID, "Minutes")
    event = {
        "replyToken": "tok_f",
        "message": {"id": "m_f", "type": "file", "fileName": "test.mp4"}
    }
    handler.handle_file(user, REAL_USER_ID, "tok_f", event)
    
    # User sends "ありがとう"
    handler.handle_text(user, REAL_USER_ID, "tok_thanks", "ありがとう")
    
    assert handler.session_manager.get(REAL_USER_ID).state == "IDLE"
    handler.richmenu.switch.assert_called_with(REAL_USER_ID, "UserMenu")
