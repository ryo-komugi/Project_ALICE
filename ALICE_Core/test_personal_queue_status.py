import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from models.job import Job, JobStatus
from core.container import core_worker, job_queue
from line.message_handler import MessageHandler


def test_personal_queue_status():
    print("=== Testing Personal Queue Status (Pattern B) ===")
    handler = MessageHandler()

    user_a = "U_alice_001"
    user_b = "U_bob_002"
    user_c = "U_charlie_003"

    # 1. 完全に空の場合
    core_worker.current_job = None
    while not job_queue.empty():
        job_queue.pop(block=False)

    text_empty = handler.get_queue_status_text(user_a)
    assert "〇 実行中\n    ：なし" in text_empty
    assert "〇 待機中\n    ：なし" in text_empty
    print("[✓] Case 1 (Empty queue) verified.")

    # 2. User A のジョブが実行中、User B のジョブが待機列1番目、User A の2本目が待機列2番目
    job_run_a = Job(
        job_id="job_001",
        user_id=user_a,
        input_file=Path("/tmp/alice_meeting_1.mp4"),
        workspace_dir=Path("/tmp/ws_001"),
        status=JobStatus.RUNNING,
    )
    job_queue_b = Job(
        job_id="job_002",
        user_id=user_b,
        input_file=Path("/tmp/bob_interview.m4a"),
        workspace_dir=Path("/tmp/ws_002"),
        status=JobStatus.QUEUED,
    )
    job_queue_a2 = Job(
        job_id="job_003",
        user_id=user_a,
        input_file=Path("/tmp/alice_meeting_2.mp4"),
        workspace_dir=Path("/tmp/ws_003"),
        status=JobStatus.QUEUED,
    )

    core_worker.current_job = job_run_a
    job_queue.push(job_queue_b)
    job_queue.push(job_queue_a2)

    # --- User A の視点 ---
    text_a = handler.get_queue_status_text(user_a)
    print("\n[User A perspective]:\n" + text_a)
    assert "alice_meeting_1.mp4" in text_a, "User A should see own running job name"
    assert "alice_meeting_2.mp4 (待機 2番目)" in text_a, "User A should see own queued job with position 2"
    assert "bob_interview.m4a" not in text_a, "User A must NEVER see User B's file name"
    print("[✓] Case 2-A (User A with running & queued jobs) verified.")

    # --- User B の視点 ---
    text_b = handler.get_queue_status_text(user_b)
    print("\n[User B perspective]:\n" + text_b)
    assert "他の処理を実行中" in text_b, "User B should see masked running job"
    assert "alice_meeting_1.mp4" not in text_b, "User B must NEVER see User A's running file name"
    assert "bob_interview.m4a (待機 1番目)" in text_b, "User B should see own queued job with position 1"
    assert "alice_meeting_2.mp4" not in text_b, "User B must NEVER see User A's queued file name"
    print("[✓] Case 2-B (User B with queued job while other is running) verified.")

    # --- User C (部外者/第三者) の視点 ---
    text_c = handler.get_queue_status_text(user_c)
    print("\n[User C perspective]:\n" + text_c)
    assert "他の処理を実行中" in text_c, "User C should see masked running job"
    assert "なし (全体で 2件待機中)" in text_c, "User C should see no personal queued jobs, but total queued count"
    assert "alice" not in text_c and "bob" not in text_c, "User C must NEVER see any private file names"
    print("[✓] Case 2-C (User C with no active jobs) verified.")

    # 後処理クリーンアップ
    core_worker.current_job = None
    while not job_queue.empty():
        job_queue.pop(block=False)

    print("\n🎉 ALL PERSONAL QUEUE TESTS PASSED!")


if __name__ == "__main__":
    test_personal_queue_status()
