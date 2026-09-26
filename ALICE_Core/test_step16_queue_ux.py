import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from line.message_handler import MessageHandler
from repository.user_repository import UserRepository
from models.job import Job, JobStatus
from core.container import job_queue, core_worker

initialize_logger()
REAL_USER_ID = "U794535d58fb802ac996f4a86ce119ad2"


def test_queue_and_ux_features():
    core_worker.stop()
    print("\n==========================================")
    print("Test: LINE Queue & UX Integration Test")
    print("==========================================")

    user_repo = UserRepository()
    user = user_repo.find(REAL_USER_ID)
    assert user is not None, "Real user should exist in repository"

    handler = MessageHandler()
    replies = []
    switches = []

    handler.sender.reply_text = lambda token, msg: replies.append((token, msg))
    handler.richmenu.switch = lambda uid, menu: switches.append((uid, menu))

    def send_text(text, token="tok"):
        event = {
            "replyToken": token,
            "type": "message",
            "source": {"userId": REAL_USER_ID},
            "message": {"type": "text", "text": text}
        }
        handler.handle(event)

    # 1. IDLE状態での「Queue」押下テスト (実行中なし / 待機中なし)
    send_text("Queue", "tok_q1")
    assert len(replies) > 0
    reply = replies[-1][1]
    assert "【キュー状況】" in reply
    assert "〇 実行中" in reply
    assert "：なし" in reply
    assert "〇 待機中" in reply
    print("[1] 'Queue' command with empty queue verified.")

    # 2. 実行中・待機中Jobのモック設定
    dummy_running_job = Job(
        job_id="job_running_001",
        user_id=REAL_USER_ID,
        input_file=Path("/tmp/sample_meeting.mp4"),
        workspace_dir=Path("/tmp/workspace_001"),
    )
    dummy_running_job.status = JobStatus.RUNNING
    core_worker.current_job = dummy_running_job

    dummy_queued_job = Job(
        job_id="job_queued_002",
        user_id=REAL_USER_ID,
        input_file=Path("/tmp/discussion_audio.m4a"),
        workspace_dir=Path("/tmp/workspace_002"),
    )
    job_queue.push(dummy_queued_job)

    # 3. 「Queue」押下テスト (実行中あり / 待機中あり)
    send_text("キュー", "tok_q2")
    reply = replies[-1][1]
    assert "【キュー状況】" in reply
    assert "sample_meeting.mp4" in reply
    assert "discussion_audio.m4a" in reply
    print("[2] 'Queue' command with active running & queued jobs verified.")

    # 4. 「ヘルプ」の「Queue」説明追加検証
    send_text("ヘルプ", "tok_help")
    reply = replies[-1][1]
    assert "■ Queue:" in reply
    assert "現在の処理待ち件数や待機状況を確認できます" in reply
    print("[3] 'ヘルプ' updated text verified.")

    # 5. 「送信方法」の返答動作検証
    send_text("送信方法", "tok_send")
    reply = replies[-1][1]
    assert "【音声ファイルの送信方法】" in reply
    print("[4] '送信方法' command verified.")

    # 後処理クリーンアップ
    core_worker.current_job = None
    job_queue.pop(block=False)  # pop dummy_queued_job

    print("\n>>> ALL QUEUE & UX INTEGRATION TESTS PASSED!")


if __name__ == "__main__":
    test_queue_and_ux_features()
