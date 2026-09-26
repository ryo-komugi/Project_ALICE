import sys
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from line.message_handler import MessageHandler
from repository.user_repository import UserRepository

initialize_logger()
REAL_USER_ID = "U794535d58fb802ac996f4a86ce119ad2"


def test_ux_interactions():
    print("\n==========================================")
    print("Test: LINE UX Improvements Verification")
    print("==========================================")
    user_repo = UserRepository()
    user = user_repo.find(REAL_USER_ID)
    assert user is not None

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

    # 1. 送信方法のテスト (IDLE時)
    send_text("送信方法", "tok_send_guide")
    assert "音声ファイルの送信方法" in replies[-1][1], f"Unexpected reply: {replies[-1][1]}"
    print("[1] '送信方法' response verified.")

    # 2. ヘルプのテスト (IDLE時)
    send_text("ヘルプ", "tok_help")
    assert "ALICE の使い方" in replies[-1][1], f"Unexpected reply: {replies[-1][1]}"
    print("[2] 'ヘルプ' response verified.")

    # 3. 議事録のテスト (実装済み受付確認)
    send_text("議事録", "tok_minute")
    assert "議事録ですね" in replies[-1][1], f"Unexpected reply: {replies[-1][1]}"
    assert switches[-1][1] == "UploadMenu"
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Minutes"
    print("[3] '議事録' reception and workflow transition verified.")
    send_text("キャンセル", "tok_cancel")

    # 4. WAIT_FILE(Transcript) -> 「要約」へ切り替え
    send_text("文字起こし", "tok_t1")
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Transcript"
    assert switches[-1][1] == "UploadMenu"
    assert "文字起こしですね" in replies[-1][1]

    # 切り替え
    send_text("要約", "tok_s1")
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Summary"
    assert switches[-1][1] == "UploadMenu"
    assert "要約ですね" in replies[-1][1]
    print("[4] Switch from WAIT_FILE(Transcript) to WAIT_FILE(Summary) verified.")

    # 5. WAIT_FILE(Summary) -> 「文字起こし」へ切り替え
    send_text("文字起こし", "tok_t2")
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE"
    assert session.workflow == "Transcript"
    assert switches[-1][1] == "UploadMenu"
    assert "文字起こしですね" in replies[-1][1]
    print("[5] Switch from WAIT_FILE(Summary) to WAIT_FILE(Transcript) verified.")

    # 6. WAIT_FILE中に「送信方法」を押下
    send_text("送信方法", "tok_send_guide_during_wait")
    assert "音声ファイルの送信方法" in replies[-1][1]
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "WAIT_FILE" # 待機状態を維持
    print("[6] '送信方法' during WAIT_FILE verified (state maintained).")

    # 7. キャンセルの既存動作
    send_text("キャンセル", "tok_cancel")
    session = handler.session_manager.get(REAL_USER_ID)
    assert session.state == "IDLE"
    assert session.workflow is None
    assert switches[-1][1] == "UserMenu"
    assert "受付をキャンセルしました" in replies[-1][1]
    print("[7] 'キャンセル' resets to IDLE verified.")

    print("\n>>> ALL UX INTERACTION TESTS PASSED!")


if __name__ == "__main__":
    test_ux_interactions()
