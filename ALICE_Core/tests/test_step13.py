import sys
import os
import time
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from hub.container import core_worker, job_queue, workspace_manager
from gateway.handlers.message import MessageHandler
from repository.user_repository import UserRepository
from models.job import JobStatus

initialize_logger()
SAMPLE_AUDIO = Path("/data/tmp/for_transcript_test/sps-smp.mp3")
REAL_USER_ID = "U794535d58fb802ac996f4a86ce119ad2"


def test_1_line_transcript_flow():
    print("\n==========================================")
    print("Test 1: LINE '文字起こし' -> workflow=['transcript']")
    print("==========================================")
    core_worker.start()

    user_repo = UserRepository()
    user = user_repo.find(REAL_USER_ID)
    assert user is not None

    handler = MessageHandler()
    mock_replies = []
    handler.sender.reply_text = lambda token, msg: mock_replies.append(msg)
    handler.richmenu.switch = lambda uid, menu: None

    # 1. 送信: 「文字起こし」
    event_text = {
        "replyToken": "token_trans_1",
        "type": "message",
        "source": {"userId": REAL_USER_ID},
        "message": {"type": "text", "text": "文字起こし"}
    }
    handler.handle(event_text)
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Transcript"

    # 2. 送信: 音声ファイル
    sample_filename = "test_line_transcript.mp3"
    handler.downloader.download = lambda mid, save_path: shutil.copy2(SAMPLE_AUDIO, save_path)

    event_file = {
        "replyToken": "token_trans_2",
        "type": "message",
        "source": {"userId": REAL_USER_ID},
        "message": {"type": "file", "id": "msg_trans_001", "fileName": sample_filename}
    }
    handler.handle(event_file)

    # 3. 処理完了待ち
    timeout = 90
    t0 = time.time()
    target_job_data = None
    target_ws = None

    while time.time() - t0 < timeout:
        workspaces = list(Path("/data/runtime/workspaces").glob(f"*{sample_filename.split('.')[0]}*"))
        if workspaces:
            latest_ws = max(workspaces, key=lambda p: p.stat().st_mtime)
            job_json = latest_ws / "job.json"
            if job_json.exists():
                try:
                    with open(job_json, "r", encoding="utf-8") as jf:
                        content = jf.read().strip()
                        if content:
                            data = json.loads(content)
                            if data.get("status") in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                                target_job_data = data
                                target_ws = latest_ws
                                break
                except Exception:
                    pass
        time.sleep(1)

    core_worker.stop()

    assert target_job_data is not None, "Job did not finish"
    assert target_job_data["status"] == "COMPLETED"
    assert target_job_data["workflow"] == ["transcript"]
    assert (target_ws / "transcript" / "transcript.txt").exists()
    assert (target_ws / "transcript" / "transcript.json").exists()
    assert not (target_ws / "summary" / "summary.md").exists(), "Summary should not run for transcript workflow"
    print(f"[Test 1] Job workflow in job.json: {target_job_data['workflow']}")
    print(">>> Test 1 PASSED!")


def test_2_line_summary_flow():
    print("\n==========================================")
    print("Test 2: LINE '要約' -> workflow=['transcript', 'summary']")
    print("==========================================")
    core_worker.start()

    user_repo = UserRepository()
    user = user_repo.find(REAL_USER_ID)
    assert user is not None

    handler = MessageHandler()
    mock_replies = []
    handler.sender.reply_text = lambda token, msg: mock_replies.append(msg)
    handler.richmenu.switch = lambda uid, menu: None

    # 1. 送信: 「要約」
    event_text = {
        "replyToken": "token_sum_1",
        "type": "message",
        "source": {"userId": REAL_USER_ID},
        "message": {"type": "text", "text": "要約"}
    }
    handler.handle(event_text)
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Summary"

    # 2. 送信: 音声ファイル
    sample_filename = "test_line_summary.mp3"
    handler.downloader.download = lambda mid, save_path: shutil.copy2(SAMPLE_AUDIO, save_path)

    event_file = {
        "replyToken": "token_sum_2",
        "type": "message",
        "source": {"userId": REAL_USER_ID},
        "message": {"type": "file", "id": "msg_sum_001", "fileName": sample_filename}
    }
    handler.handle(event_file)

    # 3. 処理完了待ち
    timeout = 360
    t0 = time.time()
    target_job_data = None
    target_ws = None

    while time.time() - t0 < timeout:
        workspaces = list(Path("/data/runtime/workspaces").glob(f"*{sample_filename.split('.')[0]}*"))
        if workspaces:
            latest_ws = max(workspaces, key=lambda p: p.stat().st_mtime)
            job_json = latest_ws / "job.json"
            if job_json.exists():
                try:
                    with open(job_json, "r", encoding="utf-8") as jf:
                        content = jf.read().strip()
                        if content:
                            data = json.loads(content)
                            if data.get("status") in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                                target_job_data = data
                                target_ws = latest_ws
                                break
                except Exception:
                    pass
        time.sleep(1)

    core_worker.stop()

    assert target_job_data is not None, "Job did not finish"
    assert target_job_data["status"] == "COMPLETED"
    assert target_job_data["workflow"] == ["transcript", "summary"]
    assert (target_ws / "transcript" / "transcript.json").exists()
    assert (target_ws / "summary" / "analysis.json").exists(), "analysis.json must exist"
    assert (target_ws / "summary" / "draft_summary.md").exists(), "draft_summary.md must exist"
    assert (target_ws / "summary" / "consistency_report.md").exists(), "consistency_report.md must exist"
    assert (target_ws / "summary" / "summary.md").exists(), "summary.md must exist"
    assert (target_ws / "summary" / "summary.txt").exists(), "summary.txt must exist"
    assert (target_ws / "summary" / "metadata.json").exists(), "metadata.json must exist"

    with open(target_ws / "summary" / "metadata.json", "r", encoding="utf-8") as mf:
        s_meta = json.load(mf)
        assert s_meta.get("stage3_executed") is True
        assert "conversation_type" in s_meta
        print(f"[Test 2] Summary metadata verified: type={s_meta.get('conversation_type')}, times={s_meta.get('execution_time_sec')}")

    print(f"[Test 2] Job workflow in job.json: {target_job_data['workflow']}")
    print(">>> Test 2 PASSED!")


def main():
    if "--summary-only" in sys.argv:
        test_2_line_summary_flow()
        print("\n==========================================")
        print("=== STEP 13 SUMMARY TEST PASSED! =========")
        print("==========================================")
        return

    test_1_line_transcript_flow()
    test_2_line_summary_flow()
    print("\n==========================================")
    print("=== ALL STEP 13 LINE TESTS PASSED! =======")
    print("==========================================")


if __name__ == "__main__":
    main()
