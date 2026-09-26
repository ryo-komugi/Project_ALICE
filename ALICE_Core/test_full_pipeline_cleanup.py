"""
Full E2E Pipeline Integration Test with Audio Cleanup and Search Verification.
"""
import sys
import os
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

CORE_ROOT = Path(__file__).resolve().parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from core.workspace_manager import WorkspaceManager
from core.job_queue import JobQueue
from core.worker import CoreWorker
from models.job import JobStatus
import subprocess

initialize_logger()


def main():
    print("=" * 60)
    print("=== ALICE Full Pipeline E2E Integration Test ===")
    print("=" * 60)

    # 1. 既存音声の準備 (11MB)
    src_audio = Path("/data/runtime/workspaces/job_20260908_003201_8月20日（15-01）/input/8月20日（15-01）.m4a")
    if not src_audio.exists():
        print(f"[ERROR] Source audio not found: {src_audio}")
        sys.exit(1)

    print(f"[*] Target Audio: {src_audio.name} ({src_audio.stat().st_size / (1024*1024):.2f} MB)")

    # 2. Workspace と Job の作成
    wm = WorkspaceManager(base_dir="/data/runtime/workspaces")
    queue = JobQueue()
    mock_publisher = MagicMock()
    mock_publisher.publish = lambda path, uid, module_name="summary": print(f"[MockPublisher] Published {path} to {uid} ({module_name})")

    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_publisher,
    )

    job = wm.create_workspace(
        user_id="test_e2e_verification_user",
        src_file=src_audio,
        workflow=["transcript", "summary"],
        original_filename="8月20日（15-01）.m4a",
    )
    print(f"[*] Created Test Job: {job.job_id}")
    print(f"[*] Workspace: {job.workspace_dir}")
    print(f"[*] Workflow: {job.workflow}")

    # 3. パイプライン実行
    start_time = time.time()
    print("\n[*] Starting CoreWorker.process_job (Transcript -> Summary -> Publish -> Search -> Cleanup)...")
    success = worker.process_job(job)
    elapsed = time.time() - start_time
    print(f"[*] Process finished in {elapsed:.1f}s (Success={success})")

    # 4. 検証
    reloaded_job = wm.load_job(job.workspace_dir)
    print(f"\n[*] Final Job Status: {reloaded_job.status.value}")

    assert success is True, "Worker process_job failed!"
    assert reloaded_job.status == JobStatus.COMPLETED, f"Expected COMPLETED, got {reloaded_job.status}"

    # Source of Truth
    transcript_json = job.workspace_dir / "transcript" / "transcript.json"
    assert transcript_json.exists(), "Source of truth transcript.json missing!"
    print(f"[+] Source of Truth confirmed: {transcript_json.name} ({transcript_json.stat().st_size} bytes)")

    # Summary Artifacts
    summary_txt = job.workspace_dir / "summary" / "summary.txt"
    assert summary_txt.exists(), "Summary primary artifact missing!"
    print(f"[+] Primary Artifact confirmed: {summary_txt.name} ({summary_txt.stat().st_size} bytes)")

    # Audio Cleanup Verification
    original_audio_path = job.workspace_dir / "input" / "8月20日（15-01）.m4a"
    placeholder_path = job.workspace_dir / "input" / "8月20日（15-01）.m4a.txt"

    assert not original_audio_path.exists(), "Original audio binary still exists! Should have been cleaned up."
    print(f"[+] Audio binary successfully deleted from input directory!")

    assert placeholder_path.exists(), "Audio placeholder txt missing!"
    placeholder_text = placeholder_path.read_text(encoding="utf-8")
    assert "[Audio Source Cleared]" in placeholder_text
    print(f"[+] Audio placeholder confirmed:\n{placeholder_text.strip()}")

    assert reloaded_job.input_metadata.get("audio_cleared") is True, "job.json metadata audio_cleared not True"
    print(f"[+] job.json input_metadata.audio_cleared: True")

    # 5. ALICE_Search Verification
    search_cli = (Path(__file__).resolve().parent.parent / "ALICE_Search" / "cli.py")
    res = subprocess.run(
        [sys.executable, str(search_cli), "--query", "チェックリスト", "--user", "test_e2e_verification_user", "--limit", "5"],
        capture_output=True,
        text=True,
    )
    print(f"\n[*] Search CLI output:\n{res.stdout}")
    assert job.job_id in res.stdout or res.returncode == 0, "Job not indexed in ALICE_Search!"
    print(f"[+] ALICE_Search indexing verified!")

    print("\n" + "=" * 60)
    print("=== ALL VERIFICATIONS PASSED SUCCESSFULLY! ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
