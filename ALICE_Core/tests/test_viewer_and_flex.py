import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import HTTPException

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from gateway.flex.download import DownloadFlex
from publisher.line_publisher import LinePublisher
from portal.viewer import view_document
import config


def test_download_flex():
    print("=== Testing DownloadFlex 2-Button Generation ===")
    flex_gen = DownloadFlex()

    # 1. 新方式: view_url と download_url を指定
    flex = flex_gen.create(
        title="要約が完了しました",
        filename="summary_20260907.md",
        download_url="https://example.com/download/summary_20260907.md",
        view_url="https://example.com/view/summary_20260907.md"
    )

    footer = flex["contents"]["footer"]
    buttons = footer["contents"]
    assert len(buttons) == 2, f"Expected 2 buttons, got {len(buttons)}"
    
    # 1つ目: Webで開く
    btn_view = buttons[0]
    assert btn_view["action"]["label"] == "📖 Webで開く"
    assert btn_view["action"]["uri"] == "https://example.com/view/summary_20260907.md"
    assert btn_view["style"] == "primary"

    # 2つ目: ファイルを保存
    btn_dl = buttons[1]
    assert btn_dl["action"]["label"] == "📥 ファイルを保存"
    assert btn_dl["action"]["uri"] == "https://example.com/download/summary_20260907.md"
    assert btn_dl["style"] == "secondary"

    print("[✓] 2-Button Flex Message generated correctly!")

    # 2. 後方互換性テスト (url=... のみ指定された場合)
    legacy_flex = flex_gen.create(
        title="旧形式テスト",
        filename="old.txt",
        url="https://example.com/legacy/old.txt"
    )
    legacy_buttons = legacy_flex["contents"]["footer"]["contents"]
    assert legacy_buttons[0]["action"]["uri"] == "https://example.com/legacy/old.txt"
    assert legacy_buttons[1]["action"]["uri"] == "https://example.com/legacy/old.txt"
    print("[✓] Backward compatibility for legacy url parameter verified!")


def test_line_publisher_integration():
    print("\n=== Testing LinePublisher with View & Download URLs ===")
    tmp_dir = Path(tempfile.mkdtemp())
    test_file = tmp_dir / "meeting_notes.md"
    test_file.write_text("# 会議議事録\n\n- 決定事項1: 承認\n- 決定事項2: 継続検討", encoding="utf-8")

    try:
        publisher = LinePublisher()
        mock_flex = MagicMock()
        mock_sender = MagicMock()
        publisher.download_flex = mock_flex
        publisher.sender = mock_sender

        publisher.publish(str(test_file), user_id="U_test123", module_name="summary")

        assert mock_flex.create.called
        kwargs = mock_flex.create.call_args[1]
        assert kwargs["title"] == "要約が完了しました"
        assert kwargs["filename"] == "meeting_notes.md"
        assert "/download/meeting_notes.md" in kwargs["download_url"]
        assert "/view/meeting_notes.md" in kwargs["view_url"]
        assert mock_sender.push_flex.called
        print("[✓] LinePublisher passes both view_url and download_url correctly!")
    finally:
        shutil.rmtree(tmp_dir)
        target = Path(config.DIR_SHARE) / "meeting_notes.md"
        if target.exists():
            target.unlink()


def test_viewer_endpoint():
    print("\n=== Testing Viewer Endpoint (/view/{filename}) ===")

    # config.DIR_SHARE にテスト用ファイルを配置
    share_dir = Path(config.DIR_SHARE)
    share_dir.mkdir(parents=True, exist_ok=True)
    test_filename = "test_viewer_sample.md"
    test_path = share_dir / test_filename

    md_content = """# プロジェクトALICE要約結果

これは**自動生成**されたテスト要約です。

## 主なアジェンダ
- 第一議題: 予算計画
- 第二議題: スケジュール調整

| 項目 | 担当 | 期限 |
|---|---|---|
| A | 田中 | 9/10 |
| B | 鈴木 | 9/15 |

> 重要: 次回ミーティングは来週火曜日です。
"""
    test_path.write_text(md_content, encoding="utf-8")

    try:
        # 1. 正常系: HTMLの取得
        response = view_document(test_filename)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        html_text = response.body.decode("utf-8")

        # MarkdownがHTMLに正しくレンダリングされているか確認
        assert "<h1" in html_text and "プロジェクトALICE要約結果" in html_text
        assert "<strong>自動生成</strong>" in html_text
        assert "<ul" in html_text and "第一議題: 予算計画" in html_text
        assert "<table" in html_text
        assert "<blockquote" in html_text
        # コピー機能とダウンロードボタンが含まれているか確認
        assert "copyContent()" in html_text
        assert f"/download/{test_filename}" in html_text
        print("[✓] Viewer renders Markdown to beautiful HTML with UI controls correctly!")

        # 2. 異常系: 存在しないファイル (404)
        try:
            view_document("non_existent_file_9999.md")
            assert False, "Should have raised 404"
        except HTTPException as e:
            assert e.status_code == 404
            print("[✓] 404 returned for missing file!")

        # 3. セキュリティ: パストラバーサル試行 (400)
        try:
            view_document("../../etc/passwd")
            assert False, "Should have raised 400"
        except HTTPException as e:
            assert e.status_code == 400
            print("[✓] Path traversal successfully blocked!")

        # 4. ペアファイルによるタブナビゲーションのテスト
        comm_filename = "test_viewer_sample_comm.md"
        comm_path = share_dir / comm_filename
        comm_path.write_text("# 解説・講評レポート\n\nテスト講評です。", encoding="utf-8")

        # summary_summary と summary_commentary のペアを作成してテスト
        pair_sum = share_dir / "job_test_summary_summary.txt"
        pair_com = share_dir / "job_test_summary_commentary.txt"
        pair_sum.write_text("# 要約本文", encoding="utf-8")
        pair_com.write_text("# 講評本文", encoding="utf-8")

        try:
            resp_sum = view_document("job_test_summary_summary.txt")
            html_sum = resp_sum.body.decode("utf-8")
            assert "class=\"tab-bar\"" in html_sum
            assert "📝 要約レポート" in html_sum
            assert "💡 解説・講評レポート" in html_sum
            assert "class=\"tab-btn active\">📝 要約レポート" in html_sum

            resp_com = view_document("job_test_summary_commentary.txt")
            html_com = resp_com.body.decode("utf-8")
            assert "class=\"tab-bar\"" in html_com
            assert "class=\"tab-btn active\">💡 解説・講評レポート" in html_com
            print("[✓] Viewer tab navigation correctly rendered between Summary and Commentary pairs!")
        finally:
            if pair_sum.exists(): pair_sum.unlink()
            if pair_com.exists(): pair_com.unlink()
            if comm_path.exists(): comm_path.unlink()

    finally:
        if test_path.exists():
            test_path.unlink()


def test_line_publisher_with_commentary():
    print("\n=== Testing LinePublisher with Commentary Extra Files ===")
    tmp_dir = Path(tempfile.mkdtemp())
    sum_file = tmp_dir / "job_123_summary_summary.txt"
    comm_file = tmp_dir / "job_123_summary_commentary.txt"
    sum_file.write_text("要約本文", encoding="utf-8")
    comm_file.write_text("講評本文", encoding="utf-8")

    try:
        publisher = LinePublisher()
        mock_flex = MagicMock()
        mock_sender = MagicMock()
        publisher.download_flex = mock_flex
        publisher.sender = mock_sender

        publisher.publish(
            str(sum_file),
            user_id="U_test123",
            module_name="summary",
            extra_files={"commentary": str(comm_file)}
        )

        assert mock_flex.create_carousel.called
        carousel_items = mock_flex.create_carousel.call_args[0][0]
        assert len(carousel_items) == 2
        assert carousel_items[0]["title"] == "要約が完了しました"
        assert carousel_items[1]["title"] == "解説・講評レポート"
        assert mock_sender.push_flex.called
        print("[✓] LinePublisher correctly generated Carousel Flex for Summary + Commentary!")
    finally:
        shutil.rmtree(tmp_dir)
        for f in ["job_123_summary_summary.txt", "job_123_summary_commentary.txt"]:
            p = Path(config.DIR_SHARE) / f
            if p.exists():
                p.unlink()


def test_line_publisher_with_minutes_and_summary():
    print("\n=== Testing LinePublisher with Minutes + Summary + Commentary ===")
    tmp_dir = Path(tempfile.mkdtemp())
    min_file = tmp_dir / "job_456_minutes_minutes.md"
    sum_file = tmp_dir / "job_456_summary_summary.txt"
    comm_file = tmp_dir / "job_456_summary_commentary.txt"
    min_file.write_text("# 議事録本文", encoding="utf-8")
    sum_file.write_text("要約本文", encoding="utf-8")
    comm_file.write_text("講評本文", encoding="utf-8")

    try:
        publisher = LinePublisher()
        mock_flex = MagicMock()
        mock_sender = MagicMock()
        publisher.download_flex = mock_flex
        publisher.sender = mock_sender

        publisher.publish(
            str(min_file),
            user_id="U_test456",
            module_name="minutes",
            extra_files={"summary": str(sum_file), "commentary": str(comm_file)}
        )

        assert mock_flex.create_carousel.called
        carousel_items = mock_flex.create_carousel.call_args[0][0]
        alt_text = mock_flex.create_carousel.call_args[1].get("alt_text")
        assert len(carousel_items) == 3
        assert carousel_items[0]["title"] == "議事録作成が完了しました"
        assert carousel_items[1]["title"] == "要約レポート"
        assert carousel_items[2]["title"] == "解説・講評レポート"
        assert alt_text == "議事録・要約レポートが届きました"
        assert mock_sender.push_flex.called
        print("[✓] LinePublisher correctly generated 3-item Carousel Flex for Minutes + Summary + Commentary!")
    finally:
        shutil.rmtree(tmp_dir)
        for f in ["job_456_minutes_minutes.md", "job_456_summary_summary.txt", "job_456_summary_commentary.txt"]:
            p = Path(config.DIR_SHARE) / f
            if p.exists():
                p.unlink()


def test_viewer_endpoint_3tabs():
    print("\n=== Testing Viewer Endpoint 3-Tab Navigation ===")
    share_dir = Path(config.DIR_SHARE)
    share_dir.mkdir(parents=True, exist_ok=True)

    sum_file = share_dir / "job_999_summary_summary.txt"
    comm_file = share_dir / "job_999_summary_commentary.txt"
    min_file = share_dir / "job_999_minutes_minutes.md"

    sum_file.write_text("# 要約本文", encoding="utf-8")
    comm_file.write_text("# 講評本文", encoding="utf-8")
    min_file.write_text("# 議事録本文", encoding="utf-8")

    try:
        resp_min = view_document("job_999_minutes_minutes.md")
        html_min = resp_min.body.decode("utf-8")
        assert "class=\"tab-bar\"" in html_min
        assert "📝 要約レポート" in html_min
        assert "💡 解説・講評レポート" in html_min
        assert "📋 議事録" in html_min
        assert "class=\"tab-btn active\">📋 議事録" in html_min

        resp_sum = view_document("job_999_summary_summary.txt")
        html_sum = resp_sum.body.decode("utf-8")
        assert "class=\"tab-btn active\">📝 要約レポート" in html_sum

        print("[✓] Viewer 3-tab navigation correctly rendered across Minutes, Summary, and Commentary!")
    finally:
        if sum_file.exists(): sum_file.unlink()
        if comm_file.exists(): comm_file.unlink()
        if min_file.exists(): min_file.unlink()


if __name__ == "__main__":
    test_download_flex()
    test_line_publisher_integration()
    test_line_publisher_with_commentary()
    test_line_publisher_with_minutes_and_summary()
    test_viewer_endpoint()
    test_viewer_endpoint_3tabs()
    print("\n🎉 ALL NEW TESTS PASSED!")
