"""
Unit tests for ALICE Nightly Reviewer.
"""
import json
import sqlite3
from pathlib import Path
import pytest
from reviewer.report_manager import (
    init_reports_db,
    save_report,
    get_latest_pending_report,
    get_latest_report,
    mark_report_as_reported,
    build_morning_briefing_embed,
)
from reviewer.log_extractor import (
    extract_conversations,
    extract_system_errors,
    format_conversations_for_prompt,
    build_review_context,
)
from reviewer.tools import (
    REVIEW_STATE,
    reset_review_state,
    record_review_result,
    search_git_history,
)


@pytest.fixture
def temp_reports_db(tmp_path):
    db_path = tmp_path / "test_reports.db"
    init_reports_db(db_path)
    return db_path


def test_report_manager_lifecycle(temp_reports_db):
    # Initially no reports
    assert get_latest_pending_report(temp_reports_db) is None
    assert get_latest_report(temp_reports_db) is None

    # Save a report
    rep_id = save_report(
        summary="Test review summary",
        memories_added=[{"type": "decision", "title": "Test Decision"}],
        improvements=["Improve performance"],
        conversations_count=10,
        errors_count=1,
        db_path=temp_reports_db,
    )
    assert rep_id == 1

    # Check pending
    pending = get_latest_pending_report(temp_reports_db)
    assert pending is not None
    assert pending["id"] == 1
    assert pending["status"] == "pending"
    assert pending["summary"] == "Test review summary"
    assert len(pending["memories_added"]) == 1
    assert pending["memories_added"][0]["title"] == "Test Decision"
    assert pending["improvements"] == ["Improve performance"]

    # Build Discord Embed
    embed = build_morning_briefing_embed(pending)
    assert embed.title == "🌅 ALICE モーニングブリーフィング"
    assert len(embed.fields) >= 3

    # Mark as reported
    mark_report_as_reported(1, temp_reports_db)
    assert get_latest_pending_report(temp_reports_db) is None

    # Latest report still exists with reported status
    latest = get_latest_report(temp_reports_db)
    assert latest is not None
    assert latest["status"] == "reported"
    assert latest["reported_at"] is not None


def test_format_conversations_for_prompt():
    empty_res = format_conversations_for_prompt([])
    assert "過去24時間以内の会話ログはありません" in empty_res

    sample_msgs = [
        {"role": "user", "content": "テスト質問", "timestamp": "2026-09-15T01:00:00+00:00"},
        {"role": "assistant", "content": "テスト回答", "timestamp": "2026-09-15T01:01:00+00:00"},
    ]
    res = format_conversations_for_prompt(sample_msgs)
    assert "浅野さん (User):" in res
    assert "テスト質問" in res
    assert "ALICE (Assistant):" in res
    assert "テスト回答" in res


def test_reviewer_tools_state():
    reset_review_state()
    assert REVIEW_STATE["recorded"] is False

    res = record_review_result(
        summary="Completed successfully",
        improvements=["Proposal 1", "Proposal 2"],
    )
    assert "正常に記録しました" in res
    assert REVIEW_STATE["recorded"] is True
    assert REVIEW_STATE["summary"] == "Completed successfully"
    assert len(REVIEW_STATE["improvements"]) == 2


def test_git_history_tool():
    out = search_git_history(max_count=3)
    assert out is not None
    assert len(out.splitlines()) >= 1


def test_reviewer_repair_tools_and_embed(temp_reports_db, monkeypatch):
    from unittest.mock import MagicMock
    from reviewer.tools import check_calendar_state, repair_calendar_state

    # Mock get_calendar_events
    monkeypatch.setattr(
        "tools.calendar_tools.get_calendar_events",
        lambda **kwargs: {"total": 1, "events": [{"id": "ev_test_1", "calendar": "人員動静", "summary": "【未・休暇】古橋s", "start": "2026-09-17", "end": "2026-09-18"}]}
    )
    cal_state = check_calendar_state(query="古橋")
    assert "ev_test_1" in cal_state
    assert "【未・休暇】古橋s" in cal_state

    # Mock delete_calendar_event
    monkeypatch.setattr(
        "tools.calendar_tools.delete_calendar_event",
        lambda **kwargs: {"status": "success", "calendar": "人員動静", "event_id": "ev_test_1"}
    )
    reset_review_state()
    repair_res = repair_calendar_state(action="delete", event_id="ev_test_1", calendar_name="人員動静")
    assert "自律修復" in repair_res
    assert len(REVIEW_STATE["repairs_done"]) == 1

    # Embed with repairs_done
    rep_id = save_report(
        summary="自律点検・修復完了",
        raw_details=json.dumps({"raw_text": "ok", "repairs_done": REVIEW_STATE["repairs_done"]}),
        db_path=temp_reports_db,
    )
    pending = get_latest_pending_report(temp_reports_db)
    embed = build_morning_briefing_embed(pending)
    field_names = [f.name for f in embed.fields]
    assert any("夜間自律修復" in name for name in field_names)