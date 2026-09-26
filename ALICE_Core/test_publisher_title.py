import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = PROJECT_ROOT / "ALICE_Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from publisher.publisher import Publisher
from publisher.line_publisher import LinePublisher


def test_publisher_titles():
    print("=== Testing Publisher Title Switching ===")
    
    tmp_dir = Path(tempfile.mkdtemp())
    dummy_file = tmp_dir / "test_artifact.txt"
    dummy_file.write_text("dummy content")

    try:
        # LinePublisher をモック
        line_pub = LinePublisher()
        mock_flex = MagicMock()
        mock_sender = MagicMock()
        line_pub.download_flex = mock_flex
        line_pub.sender = mock_sender
        
        # 1. Transcript の場合
        line_pub.publish(str(dummy_file), "user123", module_name="transcript")
        args, kwargs = mock_flex.create.call_args
        title = kwargs.get("title")
        assert title == "文字起こしが完了しました", f"Unexpected title: {title}"
        print("[1] Transcript title verified: '文字起こしが完了しました'")

        # 2. Summary の場合
        line_pub.publish(str(dummy_file), "user123", module_name="summary")
        args, kwargs = mock_flex.create.call_args
        title = kwargs.get("title")
        assert title == "要約が完了しました", f"Unexpected title: {title}"
        print("[2] Summary title verified: '要約が完了しました'")

        # 3. Publisher 経由の伝達
        pub = Publisher()
        mock_inner_line = MagicMock()
        pub.line_publisher = mock_inner_line
        pub.publish(str(dummy_file), "user123", module_name="summary")
        assert mock_inner_line.publish.call_args[1].get("module_name") == "summary"
        print("[3] Publisher delegation verified: module_name passed correctly")

        print("\n>>> ALL PUBLISHER TITLE TESTS PASSED!")
    finally:
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    test_publisher_titles()
