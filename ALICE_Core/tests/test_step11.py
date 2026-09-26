import sys
import os
import time
import shutil
from pathlib import Path
from unittest.mock import MagicMock

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from hub.workspace import WorkspaceManager
from hub.queue import JobQueue
from hub.worker import CoreWorker, MODULE_RUNNERS
from models.job import JobStatus
from publisher.publisher import Publisher

initialize_logger()
SAMPLE_AUDIO = Path("/data/tmp/for_transcript_test/sps-smp.mp3")


def test_1_transcript_only():
    print("\n==========================================")
    print("Test 1: workflow=['transcript'] (Backward Compatibility)")
    print("==========================================")
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    workspace_mgr = WorkspaceManager()
    queue = JobQueue()
    worker = CoreWorker(job_queue=queue, workspace_manager=workspace_mgr, publisher=mock_publisher)
    worker.start()

    job = workspace_mgr.create_workspace(user_id="user_test1", src_file=SAMPLE_AUDIO, workflow=["transcript"])
    print(f"[Test 1] Created Job: {job.job_id} (workflow={job.workflow})")
    queue.push(job)

    timeout = 60
    t0 = time.time()
    while time.time() - t0 < timeout:
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            break
        time.sleep(1)

    worker.stop()
    print(f"[Test 1] Final Status: {job.status}")
    assert job.status == JobStatus.COMPLETED, f"Job failed: {job.error_message}"
    assert (job.transcript_dir / "transcript.txt").exists(), "transcript.txt missing"
    assert (job.transcript_dir / "transcript.json").exists(), "transcript.json missing"
    assert mock_line_publisher.publish.called, "Publisher not called"
    
    published_file, published_user = mock_line_publisher.publish.call_args[0]
    print(f"[Test 1] Published file: {published_file}")
    assert "transcript.txt" in published_file
    assert published_user == "user_test1"
    print(">>> Test 1 PASSED!")


def test_2_transcript_to_summary():
    print("\n==========================================")
    print("Test 2: workflow=['transcript', 'summary'] (Sequential Workflow)")
    print("==========================================")
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    workspace_mgr = WorkspaceManager()
    queue = JobQueue()
    worker = CoreWorker(job_queue=queue, workspace_manager=workspace_mgr, publisher=mock_publisher)
    worker.start()

    job = workspace_mgr.create_workspace(user_id="user_test2", src_file=SAMPLE_AUDIO, workflow=["transcript", "summary"])
    print(f"[Test 2] Created Job: {job.job_id} (workflow={job.workflow})")
    queue.push(job)

    timeout = 300
    t0 = time.time()
    while time.time() - t0 < timeout:
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            break
        time.sleep(1)

    worker.stop()
    print(f"[Test 2] Final Status: {job.status}")
    assert job.status == JobStatus.COMPLETED, f"Job failed: {job.error_message}"
    assert (job.transcript_dir / "transcript.json").exists(), "transcript.json missing"
    assert (job.summary_dir / "summary.txt").exists(), "summary.txt missing"
    assert (job.summary_dir / "summary.md").exists(), "summary.md missing"
    assert (job.summary_dir / "metadata.json").exists(), "summary metadata.json missing"
    assert mock_line_publisher.publish.called, "Publisher not called"

    published_args = mock_line_publisher.publish.call_args
    published_file = published_args[0][0]
    published_user = published_args[0][1]
    published_module = published_args[1].get("module_name") or (published_args[0][2] if len(published_args[0]) > 2 else None)
    print(f"[Test 2] Published file: {published_file} (module={published_module})")
    assert "summary.txt" in published_file, f"Expected summary.txt to be published, got {published_file}"
    assert published_user == "user_test2"
    assert published_module == "summary"
    print(">>> Test 2 PASSED!")


def test_3_unknown_module():
    print("\n==========================================")
    print("Test 3: Unknown module in workflow")
    print("==========================================")
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    workspace_mgr = WorkspaceManager()
    queue = JobQueue()
    worker = CoreWorker(job_queue=queue, workspace_manager=workspace_mgr, publisher=mock_publisher)

    job = workspace_mgr.create_workspace(user_id="user_test3", src_file=SAMPLE_AUDIO, workflow=["transcript", "unknown_module"])
    success = worker.process_job(job)

    print(f"[Test 3] Job Status: {job.status}, Error: {job.error_message}")
    assert not success
    assert job.status == JobStatus.FAILED
    assert "Unknown module 'unknown_module'" in job.error_message
    assert not mock_line_publisher.publish.called
    print(">>> Test 3 PASSED!")


def test_4_transcript_failure_stops_summary():
    print("\n==========================================")
    print("Test 4: Transcript failure prevents Summary execution")
    print("==========================================")
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    # Mock failing transcript runner (returns failure immediately)
    bad_runners = dict(MODULE_RUNNERS)
    bad_runners["transcript"] = {
        "python_bin": "/usr/bin/python3",
        "cli_path": "/non_existent_transcript_cli_path_9999.py",
        "artifact_dir": "transcript",
        "primary_artifact": "transcript.txt"
    }

    workspace_mgr = WorkspaceManager()
    queue = JobQueue()
    worker = CoreWorker(job_queue=queue, workspace_manager=workspace_mgr, publisher=mock_publisher, module_runners=bad_runners)

    job = workspace_mgr.create_workspace(user_id="user_test4", src_file=SAMPLE_AUDIO, workflow=["transcript", "summary"])
    success = worker.process_job(job)

    print(f"[Test 4] Job Status: {job.status}, Error: {job.error_message}")
    assert not success
    assert job.status == JobStatus.FAILED
    assert "Step 'transcript' failed" in job.error_message
    assert not (job.summary_dir / "summary.md").exists(), "Summary should not have run"
    assert not mock_line_publisher.publish.called
    print(">>> Test 4 PASSED!")


def test_5_summary_failure_prevents_publish():
    print("\n==========================================")
    print("Test 5: Summary failure prevents publishing")
    print("==========================================")
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    # Create workspace with pre-existing transcript to test summary failure isolated from GPU
    workspace_mgr = WorkspaceManager()
    job = workspace_mgr.create_workspace(user_id="user_test5", src_file=SAMPLE_AUDIO, workflow=["transcript", "summary"])
    
    # Write mock transcript files directly into workspace to isolate from GPU
    (job.transcript_dir / "transcript.json").write_text('{"text": "mock transcript"}', encoding="utf-8")
    (job.transcript_dir / "transcript.txt").write_text("mock transcript", encoding="utf-8")

    # Mock transcript that succeeds via touch, but summary fails
    test_runners = dict(MODULE_RUNNERS)
    test_runners["transcript"] = {
        "python_bin": "/usr/bin/python3",
        "cli_path": str(PROJECT_ROOT / "ALICE_Transcript" / "cli.py"), # or dummy
        "artifact_dir": "transcript",
        "primary_artifact": "transcript.txt"
    }
    test_runners["summary"] = {
        "python_bin": "/usr/bin/python3",
        "cli_path": "/non_existent_summary_cli_path_9999.py", # Fails
        "artifact_dir": "summary",
        "primary_artifact": "summary.txt"
    }

    # Use dummy for transcript to avoid re-running heavy GPU in test 5
    dummy_transcript_runner = {
        "python_bin": "/usr/bin/python3",
        "cli_path": str(PROJECT_ROOT / "ALICE_Core" / "models" / "job.py"), # returns 0 exit
        "artifact_dir": "transcript",
        "primary_artifact": "transcript.txt"
    }
    test_runners["transcript"] = dummy_transcript_runner

    worker = CoreWorker(job_queue=JobQueue(), workspace_manager=workspace_mgr, publisher=mock_publisher, module_runners=test_runners)
    success = worker.process_job(job)

    print(f"[Test 5] Job Status: {job.status}, Error: {job.error_message}")
    assert not success
    assert job.status == JobStatus.FAILED
    assert "Step 'summary' failed" in job.error_message
    assert not mock_line_publisher.publish.called
    print(">>> Test 5 PASSED!")


def main():
    test_1_transcript_only()
    test_2_transcript_to_summary()
    test_3_unknown_module()
    test_4_transcript_failure_stops_summary()
    test_5_summary_failure_prevents_publish()
    print("\n==========================================")
    print("=== ALL STEP 11 TESTS (1 to 5) PASSED! ===")
    print("==========================================")


if __name__ == "__main__":
    main()
