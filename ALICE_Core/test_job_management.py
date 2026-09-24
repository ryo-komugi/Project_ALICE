import sys
import os
import time
import shutil
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path("/home/takuya/Project_ALICE")
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from core.workspace_manager import WorkspaceManager
from core.job_queue import JobQueue
from core.worker import CoreWorker
from models.job import Job, JobStatus, StepStatus
from publisher.publisher import Publisher

# テスト実行時は常駐サービス(uvicorn)との alice.log 競合を避けるため basicConfig を使用
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# テスト用の作業ディレクトリ
TEST_BASE_DIR = Path("/tmp/alice_test_workspaces")
SAMPLE_AUDIO = Path("/data/tmp/for_transcript_test/sps-smp.mp3")


def setup_clean_env():
    if TEST_BASE_DIR.exists():
        shutil.rmtree(TEST_BASE_DIR)
    TEST_BASE_DIR.mkdir(parents=True, exist_ok=True)


def test_1_job_creation_and_input_tracking():
    print("\n==========================================")
    print("Test 1: Input Metadata Tracking & Initialization")
    print("==========================================")
    setup_clean_env()
    wm = WorkspaceManager(base_dir=TEST_BASE_DIR)

    # 1. 音声ファイルで Workspace 作成
    original_name = "custom_meeting_recording.mp3"
    job = wm.create_workspace(
        user_id="user_test_001",
        src_file=SAMPLE_AUDIO,
        workflow=["transcript", "summary"],
        original_filename=original_name,
    )

    print(f"[Test 1] Job created: {job.job_id}")
    assert job.status == JobStatus.CREATED
    assert job.workflow == ["transcript", "summary"]
    assert job.current_step is None

    # 「何を受け取り」の検証
    assert job.input_metadata["original_name"] == original_name
    assert job.input_metadata["size_bytes"] == SAMPLE_AUDIO.stat().st_size
    assert "received_at" in job.input_metadata
    assert (job.workspace_dir / "input" / original_name).exists()
    assert (job.workspace_dir / "job.json").exists()

    # job.json の永続化確認
    with open(job.workspace_dir / "job.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["job_id"] == job.job_id
    assert data["input_metadata"]["original_name"] == original_name

    print(">>> Test 1 PASSED!")


def test_2_sequential_workflow_and_progress_tracking():
    print("\n==========================================")
    print("Test 2: Workflow Progress, Step History & Artifact Contract Tracking")
    print("==========================================")
    setup_clean_env()
    wm = WorkspaceManager(base_dir=TEST_BASE_DIR)
    queue = JobQueue()

    # モック用の軽量 Runner を準備（GPU/LLMを呼ばずにArtifact Contract通りの出力を生成）
    dummy_cli_dir = TEST_BASE_DIR / "mock_scripts"
    dummy_cli_dir.mkdir(parents=True, exist_ok=True)

    trans_cli = dummy_cli_dir / "mock_transcript_cli.py"
    trans_cli.write_text(
        """import sys, argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--workspace", required=True)
args = p.parse_args()
ws = Path(args.workspace)
(ws / "transcript" / "transcript.txt").write_text("Hello transcript text")
(ws / "transcript" / "transcript.json").write_text(json.dumps([{"text": "Hello"}]))
(ws / "transcript" / "metadata.json").write_text(json.dumps({"engine": "mock"}))
print("Transcript finished successfully")
"""
    )

    summary_cli = dummy_cli_dir / "mock_summary_cli.py"
    summary_cli.write_text(
        """import sys, argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--workspace", required=True)
args = p.parse_args()
ws = Path(args.workspace)
(ws / "summary" / "summary.txt").write_text("Summary text content")
(ws / "summary" / "summary.md").write_text("# Summary Markdown")
(ws / "summary" / "analysis.json").write_text(json.dumps({"key_points": ["Point 1"]}))
(ws / "summary" / "metadata.json").write_text(json.dumps({"model": "mock"}))
print("Summary finished successfully")
"""
    )

    mock_runners = {
        "transcript": {
            "python_bin": sys.executable,
            "cli_path": str(trans_cli),
            "artifact_dir": "transcript",
            "primary_artifact": "transcript.txt",
            "contract_artifacts": ["transcript.json", "transcript.txt", "metadata.json"],
        },
        "summary": {
            "python_bin": sys.executable,
            "cli_path": str(summary_cli),
            "artifact_dir": "summary",
            "primary_artifact": "summary.txt",
            "contract_artifacts": ["summary.md", "summary.txt", "analysis.json", "metadata.json"],
        },
    }

    mock_pub = Publisher()
    mock_line_pub = MagicMock()
    mock_pub.line_publisher = mock_line_pub

    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_pub,
        module_runners=mock_runners,
    )

    job = wm.create_workspace(
        user_id="user_test_002",
        src_file=SAMPLE_AUDIO,
        workflow=["transcript", "summary"],
        original_filename="sample_meeting.mp3",
    )

    # 実行
    success = worker.process_job(job)
    assert success is True
    assert job.status == JobStatus.COMPLETED
    assert job.current_step is None
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at

    # 「現在どこまで進み」ステップ履歴の検証
    assert len(job.step_history) == 2
    step1, step2 = job.step_history[0], job.step_history[1]

    assert step1["step"] == "transcript"
    assert step1["status"] == StepStatus.COMPLETED.value
    assert step1["exit_code"] == 0
    assert step1["elapsed_sec"] is not None
    assert "transcript.txt" in step1["artifacts"]

    assert step2["step"] == "summary"
    assert step2["status"] == StepStatus.COMPLETED.value
    assert step2["exit_code"] == 0
    assert step2["elapsed_sec"] is not None
    assert "summary.txt" in step2["artifacts"]

    # 「どの成果物が生成されたのか」の検証（Artifact Contract）
    artifact_names = [a["name"] for a in job.artifacts]
    print(f"[Test 2] Collected artifacts: {artifact_names}")
    expected_names = [
        "transcript.json", "transcript.txt", "metadata.json",
        "summary.md", "summary.txt", "analysis.json"
    ]
    for name in expected_names:
        assert name in artifact_names, f"Expected {name} in job.artifacts"

    # プライマリアーティファクトのフラグ確認
    primaries = [a["name"] for a in job.artifacts if a["is_primary"]]
    assert "transcript.txt" in primaries
    assert "summary.txt" in primaries

    # 【重要要件】実データ本文が job.json に格納されていないことの検証
    with open(job.workspace_dir / "job.json", "r", encoding="utf-8") as f:
        job_json_content = f.read()
    assert "Hello transcript text" not in job_json_content, "Transcript body must NOT be stored in job.json"
    assert "Summary text content" not in job_json_content, "Summary body must NOT be stored in job.json"
    assert "# Summary Markdown" not in job_json_content, "Summary markdown must NOT be stored in job.json"

    # Publisher 配信の検証（最終ステップ summary の primary_artifact が配信されたか）
    assert mock_line_pub.publish.called
    pub_args = mock_line_pub.publish.call_args[0]
    assert "summary_summary.txt" in pub_args[0]

    print(">>> Test 2 PASSED!")


def test_3_step_failure_and_error_structure():
    print("\n==========================================")
    print("Test 3: Step Failure, Structured Error & SKIPPED Step Handling")
    print("==========================================")
    setup_clean_env()
    wm = WorkspaceManager(base_dir=TEST_BASE_DIR)
    dummy_cli_dir = TEST_BASE_DIR / "mock_scripts"
    dummy_cli_dir.mkdir(parents=True, exist_ok=True)

    # ステップ1で異常終了する CLI
    fail_cli = dummy_cli_dir / "mock_fail_cli.py"
    fail_cli.write_text(
        """import sys
print("Simulating internal engine crash: Out of memory", file=sys.stderr)
sys.exit(42)
"""
    )

    mock_runners = {
        "transcript": {
            "python_bin": sys.executable,
            "cli_path": str(fail_cli),
            "artifact_dir": "transcript",
            "primary_artifact": "transcript.txt",
            "contract_artifacts": ["transcript.txt"],
        },
        "summary": {
            "python_bin": sys.executable,
            "cli_path": "/dummy.py",
            "artifact_dir": "summary",
            "primary_artifact": "summary.txt",
            "contract_artifacts": ["summary.txt"],
        },
    }

    mock_pub = Publisher()
    mock_line_pub = MagicMock()
    mock_pub.line_publisher = mock_line_pub
    mock_sender = MagicMock()

    worker = CoreWorker(
        job_queue=JobQueue(),
        workspace_manager=wm,
        publisher=mock_pub,
        module_runners=mock_runners,
        sender=mock_sender,
    )

    job = wm.create_workspace(
        user_id="user_test_003",
        src_file=SAMPLE_AUDIO,
        workflow=["transcript", "summary"],
    )

    success = worker.process_job(job)
    assert success is False
    assert job.status == JobStatus.FAILED
    assert job.current_step is None

    # 既存互換サマリー
    assert "Step 'transcript' failed" in job.error_message

    # 「成功したのか失敗したのか（構造化エラー詳細）」の検証
    assert job.error_detail is not None
    assert job.error_detail["failed_step"] == "transcript"
    assert job.error_detail["error_type"] == "MODULE_EXECUTION_ERROR"
    assert job.error_detail["exit_code"] == 42
    assert "logs/transcript.log" in job.error_detail["log_file"]

    # ステップ履歴の検証: transcript は FAILED、後続 summary は SKIPPED
    assert len(job.step_history) == 2
    assert job.step_history[0]["status"] == StepStatus.FAILED.value
    assert job.step_history[0]["exit_code"] == 42
    assert job.step_history[1]["status"] == StepStatus.SKIPPED.value

    # Publisher は呼ばれず、Sender でエラー通知されたこと
    assert not mock_line_pub.publish.called
    assert mock_sender.push_text.called

    print(">>> Test 3 PASSED!")


def test_4_workspace_history_and_restoration():
    print("\n==========================================")
    print("Test 4: Post-Execution Traceability & WorkspaceManager Query APIs")
    print("==========================================")
    setup_clean_env()
    wm = WorkspaceManager(base_dir=TEST_BASE_DIR)

    # 3つの Job を作成
    job1 = wm.create_workspace("user_A", SAMPLE_AUDIO, ["transcript"], "audio1.mp3")
    time.sleep(0.01)
    job2 = wm.create_workspace("user_B", SAMPLE_AUDIO, ["transcript", "summary"], "audio2.mp3")
    time.sleep(0.01)
    job3 = wm.create_workspace("user_A", SAMPLE_AUDIO, ["transcript"], "audio3.mp3")

    # 1. load_job の検証
    restored1 = wm.load_job(job1.workspace_dir)
    assert restored1.job_id == job1.job_id
    assert restored1.user_id == "user_A"
    assert restored1.input_metadata["original_name"] == "audio1.mp3"
    assert restored1.workflow == ["transcript"]

    # 2. get_job の検証
    got_job2 = wm.get_job(job2.job_id)
    assert got_job2 is not None
    assert got_job2.job_id == job2.job_id
    assert got_job2.workflow == ["transcript", "summary"]

    assert wm.get_job("non_existent_job_id") is None

    # 3. list_jobs の検証 (最新順)
    all_jobs = wm.list_jobs(limit=10)
    assert len(all_jobs) == 3
    assert all_jobs[0].job_id == job3.job_id
    assert all_jobs[1].job_id == job2.job_id
    assert all_jobs[2].job_id == job1.job_id

    # ユーザーフィルタ
    user_a_jobs = wm.list_jobs(user_id="user_A")
    assert len(user_a_jobs) == 2
    assert all(j.user_id == "user_A" for j in user_a_jobs)

    print(">>> Test 4 PASSED!")


def test_5_startup_recovery_for_interrupted_jobs():
    print("\n==========================================")
    print("Test 5: Startup Recovery for Interrupted Jobs (Crash/Restart Resilience)")
    print("==========================================")
    setup_clean_env()
    wm = WorkspaceManager(base_dir=TEST_BASE_DIR)
    queue = JobQueue()

    # 1. 完了済みジョブ (COMPLETED)
    job_completed = wm.create_workspace("user_rec_1", SAMPLE_AUDIO, ["transcript"], "completed.mp3")
    job_completed.status = JobStatus.COMPLETED
    wm.save_job_json(job_completed)

    # 2. 中断された実行中ジョブ (RUNNING)
    job_running = wm.create_workspace("user_rec_2", SAMPLE_AUDIO, ["transcript", "summary"], "running.mp3")
    job_running.status = JobStatus.RUNNING
    job_running.current_step = "transcript"
    wm.save_job_json(job_running)

    # 3. 待機中にサーバー停止したジョブ (QUEUED)
    job_queued = wm.create_workspace("user_rec_3", SAMPLE_AUDIO, ["summary"], "queued.mp3")
    job_queued.status = JobStatus.QUEUED
    wm.save_job_json(job_queued)

    # リカバリ実行
    aborted, requeued = wm.recover_interrupted_jobs(queue)

    assert aborted == 1
    assert requeued == 1

    # 検証: job_running が FAILED (RESTART_ABORTED) に更新されたか
    reloaded_running = wm.load_job(job_running.workspace_dir)
    assert reloaded_running.status == JobStatus.FAILED
    assert "RESTART_ABORTED" in reloaded_running.error_message
    assert reloaded_running.error_detail["error_type"] == "SERVER_RESTART_ABORTED"
    assert reloaded_running.error_detail["failed_step"] == "transcript"

    # 検証: job_queued が queue に再投入されたか
    assert queue.size() == 1
    requeued_job = queue.pop(block=False)
    assert requeued_job.job_id == job_queued.job_id

    # 検証: job_completed は COMPLETED のまま影響を受けないか
    reloaded_completed = wm.load_job(job_completed.workspace_dir)
    assert reloaded_completed.status == JobStatus.COMPLETED

    print(">>> Test 5 PASSED!")


def main():
    test_1_job_creation_and_input_tracking()
    test_2_sequential_workflow_and_progress_tracking()
    test_3_step_failure_and_error_structure()
    test_4_workspace_history_and_restoration()
    test_5_startup_recovery_for_interrupted_jobs()
    print("\n==========================================")
    print("=== ALL JOB MANAGEMENT TESTS PASSED! =====")
    print("==========================================")


if __name__ == "__main__":
    main()
