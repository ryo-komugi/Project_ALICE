import sys
import os
import time
import shutil
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path("/home/takuya/Project_ALICE")
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from core.workspace_manager import WorkspaceManager
from core.job_queue import JobQueue
from core.worker import CoreWorker, MODULE_RUNNERS
from models.job import JobStatus
from publisher.publisher import Publisher

initialize_logger()
SAMPLE_AUDIO = Path("/data/tmp/for_transcript_test/sps-smp.mp3")


def run_e2e_job(workflow: list[str], user_id: str, custom_runners: dict | None = None) -> tuple[any, MagicMock]:
    """Workspace作成 -> JobQueue投入 -> CoreWorker非同期処理 -> 完了待ちの完全なCore内部フローを実行"""
    mock_publisher = Publisher()
    mock_line_publisher = MagicMock()
    mock_publisher.line_publisher = mock_line_publisher

    workspace_mgr = WorkspaceManager()
    queue = JobQueue()
    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=workspace_mgr,
        publisher=mock_publisher,
        module_runners=custom_runners or MODULE_RUNNERS,
    )
    worker.start()

    job = workspace_mgr.create_workspace(user_id=user_id, src_file=SAMPLE_AUDIO, workflow=workflow)
    print(f"\n[E2E] Created Workspace & Job: {job.job_id} (workflow={job.workflow})")
    
    # JobQueue に投入 (Core 本番と同じ非同期キューイング)
    queue.push(job)

    timeout = 300
    t0 = time.time()
    while time.time() - t0 < timeout:
        # job.json から最新状態を読み出す
        job_json_path = job.workspace_dir / "job.json"
        if job_json_path.exists():
            import json
            with open(job_json_path, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                status_str = data.get("status")
                if status_str in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                    job.status = JobStatus(status_str)
                    job.error_message = data.get("error_message")
                    break
        time.sleep(1)

    worker.stop()
    return job, mock_line_publisher


def test_1_e2e_transcript_only():
    print("\n==========================================")
    print("Test 1 (E2E): workflow=['transcript']")
    print("==========================================")
    job, mock_line_publisher = run_e2e_job(workflow=["transcript"], user_id="user_e2e_test1")

    print(f"[Test 1] Final Job Status: {job.status}")
    assert job.status == JobStatus.COMPLETED, f"Job failed: {job.error_message}"

    # Workspace 検証
    ws = job.workspace_dir
    assert (ws / "job.json").exists()
    assert (ws / "input" / f"{SAMPLE_AUDIO.name}.txt").exists()
    assert (ws / "transcript" / "transcript.json").exists()
    assert (ws / "transcript" / "transcript.txt").exists()
    assert (ws / "transcript" / "metadata.json").exists()
    assert (ws / "logs" / "transcript.log").exists()

    # Publisher 検証: 1回だけ transcript.txt が配信される
    assert mock_line_publisher.publish.call_count == 1, f"Expected 1 publish call, got {mock_line_publisher.publish.call_count}"
    published_args = mock_line_publisher.publish.call_args
    published_file = published_args[0][0]
    published_user = published_args[0][1]
    published_module = published_args[1].get("module_name") or (published_args[0][2] if len(published_args[0]) > 2 else None)
    print(f"[Test 1] Published: {published_file} to {published_user} (module={published_module})")
    assert "transcript_transcript.txt" in published_file
    assert published_user == "user_e2e_test1"
    assert published_module == "transcript"
    print(">>> Test 1 (E2E) PASSED!")


def test_2_e2e_transcript_to_summary():
    print("\n==========================================")
    print("Test 2 (E2E): workflow=['transcript', 'summary']")
    print("==========================================")
    job, mock_line_publisher = run_e2e_job(workflow=["transcript", "summary"], user_id="user_e2e_test2")

    print(f"[Test 2] Final Job Status: {job.status}")
    assert job.status == JobStatus.COMPLETED, f"Job failed: {job.error_message}"

    # Workspace 検証
    ws = job.workspace_dir
    assert (ws / "job.json").exists()
    assert (ws / "input" / f"{SAMPLE_AUDIO.name}.txt").exists()
    assert (ws / "transcript" / "transcript.json").exists()
    assert (ws / "transcript" / "transcript.txt").exists()
    assert (ws / "transcript" / "metadata.json").exists()
    assert (ws / "summary" / "summary.txt").exists()
    assert (ws / "summary" / "summary.md").exists()
    assert (ws / "summary" / "analysis.json").exists()
    assert (ws / "summary" / "metadata.json").exists()
    assert (ws / "logs" / "transcript.log").exists()
    assert (ws / "logs" / "summary.log").exists()

    # job.json の workflow 確認
    import json
    with open(ws / "job.json", "r", encoding="utf-8") as jf:
        job_data = json.load(jf)
    assert job_data["workflow"] == ["transcript", "summary"]

    # Publisher 検証: Transcript完了時には配信せず、Summary完了後に 1回だけ summary.txt が配信される
    assert mock_line_publisher.publish.call_count == 1, f"Expected 1 publish call, got {mock_line_publisher.publish.call_count}"
    published_args = mock_line_publisher.publish.call_args
    published_file = published_args[0][0]
    published_user = published_args[0][1]
    published_module = published_args[1].get("module_name") or (published_args[0][2] if len(published_args[0]) > 2 else None)
    print(f"[Test 2] Published: {published_file} to {published_user} (module={published_module})")
    assert "summary_summary.txt" in published_file
    assert published_user == "user_e2e_test2"
    assert published_module == "summary"

    print("\n[Generated summary.txt Content]:")
    with open(ws / "summary" / "summary.txt", "r", encoding="utf-8") as f:
        print(f.read().strip()[:400] + "\n...")

    print(">>> Test 2 (E2E) PASSED!")


def test_3_e2e_unknown_module():
    print("\n==========================================")
    print("Test 3 (E2E): Unknown module via Queue")
    print("==========================================")
    job, mock_line_publisher = run_e2e_job(workflow=["transcript", "unknown_module"], user_id="user_e2e_test3")

    print(f"[Test 3] Final Job Status: {job.status}, Error: {job.error_message}")
    assert job.status == JobStatus.FAILED
    assert "Unknown module 'unknown_module'" in job.error_message
    assert mock_line_publisher.publish.call_count == 0
    print(">>> Test 3 (E2E) PASSED!")


def test_4_e2e_summary_failure():
    print("\n==========================================")
    print("Test 4 (E2E): Summary failure via Queue")
    print("==========================================")
    # Transcript は成功するが Summary CLI が非ゼロで終了する runner 設定
    custom_runners = dict(MODULE_RUNNERS)
    custom_runners["summary"] = {
        "python_bin": "/usr/bin/python3",
        "cli_path": "/non_existent_summary_cli_path_9999.py",
        "artifact_dir": "summary",
        "primary_artifact": "summary.txt",
    }

    job, mock_line_publisher = run_e2e_job(
        workflow=["transcript", "summary"],
        user_id="user_e2e_test4",
        custom_runners=custom_runners,
    )

    print(f"[Test 4] Final Job Status: {job.status}, Error: {job.error_message}")
    assert job.status == JobStatus.FAILED
    assert "Step 'summary' failed" in job.error_message
    # Transcript は完了しているが、Summary が失敗したため Publisher は一度も呼ばれない
    assert mock_line_publisher.publish.call_count == 0
    assert (job.workspace_dir / "transcript" / "transcript.txt").exists()
    assert not (job.workspace_dir / "summary" / "summary.md").exists()
    print(">>> Test 4 (E2E) PASSED!")


def main():
    test_1_e2e_transcript_only()
    test_2_e2e_transcript_to_summary()
    test_3_e2e_unknown_module()
    test_4_e2e_summary_failure()
    print("\n==========================================")
    print("=== ALL STEP 12 E2E TESTS PASSED! ========")
    print("==========================================")


if __name__ == "__main__":
    main()
