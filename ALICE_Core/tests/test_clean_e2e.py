import sys
import os
import time
import shutil
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from hub.container import core_worker, job_queue, workspace_manager
from gateway.handlers.message import MessageHandler
from repository.user_repository import UserRepository

initialize_logger()

def main():
    print("=== Step 5 LINE E2E Test (Post Legacy Cleanup) ===")
    
    core_worker.start()

    user_repo = UserRepository()
    real_user_id = "U794535d58fb802ac996f4a86ce119ad2"
    user = user_repo.find(real_user_id)
    assert user is not None, f"User {real_user_id} not found"

    handler = MessageHandler()

    # 1. State transition to WAIT_FILE
    text_event = {
        "replyToken": "dummy_reply_token_1",
        "type": "message",
        "source": {"userId": real_user_id},
        "message": {"type": "text", "text": "文字起こし"}
    }
    handler.sender.reply_text = lambda token, msg: print(f"[MockLINE Reply] -> {msg}")
    handler.richmenu.switch = lambda uid, menu: print(f"[MockRichMenu Switch] for {uid} -> {menu}")
    handler.handle(text_event)

    # 2. Receive file and trigger Job
    test_src = Path("/data/tmp/for_transcript_test/sps-smp.mp3")
    sample_filename = "clean_path_e2e.mp3"
    
    def mock_download(msg_id, save_path):
        shutil.copy2(test_src, save_path)

    handler.downloader.download = mock_download

    file_event = {
        "replyToken": "dummy_reply_token_2",
        "type": "message",
        "source": {"userId": real_user_id},
        "message": {
            "type": "file",
            "id": "mock_msg_clean_001",
            "fileName": sample_filename
        }
    }

    handler.handle(file_event)

    # 3. Wait for completion
    timeout = 60
    start_time = time.time()
    completed = False
    target_workspace = None

    while time.time() - start_time < timeout:
        workspaces = list(Path("/data/runtime/workspaces").glob(f"*{sample_filename.split('.')[0]}*"))
        if workspaces:
            latest_ws = max(workspaces, key=lambda p: p.stat().st_mtime)
            job_json = latest_ws / "job.json"
            if job_json.exists():
                import json
                with open(job_json) as jf:
                    data = json.load(jf)
                if data.get("status") == "COMPLETED":
                    completed = True
                    target_workspace = latest_ws
                    print(f"\n[Clean E2E Test] SUCCESS: Job COMPLETED and published to LINE!")
                    break
        time.sleep(1)

    core_worker.stop()

    if not completed:
        print("[Clean E2E Test] FAILED: Job did not complete")
        sys.exit(1)

    # 4. Verify staging directory is completely empty (no legacy leak)
    staging_dir = Path("/data/runtime/transcript/staging")
    staging_files = list(staging_dir.iterdir()) if staging_dir.exists() else []
    print(f"[Verification] Staging directory files count: {len(staging_files)}")
    assert len(staging_files) == 0, f"Staging is not empty: {staging_files}"

    # 5. Verify workspace contents
    assert (target_workspace / "job.json").exists()
    assert (target_workspace / "input" / sample_filename).exists()
    assert (target_workspace / "transcript" / "transcript.json").exists()
    assert (target_workspace / "transcript" / "transcript.txt").exists()
    assert (target_workspace / "transcript" / "metadata.json").exists()
    assert (target_workspace / "logs" / "transcript.log").exists()

    # 6. Verify Job Management Tracking Metadata (ALICE v1.0)
    with open(target_workspace / "job.json", "r", encoding="utf-8") as jf:
        job_data = json.load(jf)
    assert job_data["status"] == "COMPLETED"
    assert job_data["input_metadata"]["original_name"] == sample_filename
    assert job_data["current_step"] is None
    assert len(job_data["step_history"]) >= 1
    assert job_data["step_history"][0]["step"] == "transcript"
    assert job_data["step_history"][0]["status"] == "COMPLETED"
    assert len(job_data["artifacts"]) >= 1
    artifact_names = [a["name"] for a in job_data["artifacts"]]
    assert "transcript.txt" in artifact_names
    assert "transcript.json" in artifact_names

    print("[Verification] Workspace structure, artifacts, and Job tracking metadata verified successfully!")
    sys.exit(0)

if __name__ == "__main__":
    main()
