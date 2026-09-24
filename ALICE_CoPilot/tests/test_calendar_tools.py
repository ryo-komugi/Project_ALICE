"""
Unit tests for Google Calendar integration tools.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from tools import TOOLS_SCHEMA, execute_tool
from tools.calendar_tools import (
    _parse_datetime_str,
    get_calendar_events,
    create_calendar_event,
    delete_calendar_event,
    update_calendar_event,
    JST,
)


def test_calendar_tools_in_schema():
    tool_names = {t["function"]["name"] for t in TOOLS_SCHEMA}
    assert "get_calendar_events" in tool_names
    assert "create_calendar_event" in tool_names
    assert "delete_calendar_event" in tool_names
    assert "update_calendar_event" in tool_names


def test_parse_datetime_str():
    now_year = datetime.now(JST).year

    # ISO with tz
    dt1 = _parse_datetime_str("2026-09-13T15:00:00+09:00")
    assert dt1.year == 2026
    assert dt1.hour == 15

    # String without year (should infer current year)
    dt2 = _parse_datetime_str("10-05 14:00")
    assert dt2.year == now_year
    assert dt2.month == 10
    assert dt2.day == 5
    assert dt2.hour == 14

    # String with past year (should preserve specified year)
    dt3 = _parse_datetime_str("2023-11-20 10:30")
    assert dt3.year == 2023
    assert dt3.month == 11
    assert dt3.day == 20


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"テストカレンダー": "test_cid"})
@patch("requests.get")
def test_get_calendar_events_mock(mock_get, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "ev_1",
                "summary": "定例ミーティング",
                "start": {"dateTime": "2026-09-20T10:00:00+09:00"},
                "end": {"dateTime": "2026-09-20T11:00:00+09:00"},
                "location": "Zoom",
                "description": "週次進捗確認",
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = get_calendar_events(time_min="2026-09-20 00:00", days_ahead=1)
    assert res["total"] == 1
    assert len(res["events"]) == 1
    ev = res["events"][0]
    assert ev["summary"] == "定例ミーティング"
    assert ev["start"] == "2026-09-20 10:00"
    assert ev["end"] == "2026-09-20 11:00"
    assert ev["location"] == "Zoom"


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"個人予定": "test_cid"})
@patch("requests.post")
def test_create_calendar_event_mock(mock_post, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "created_ev_123",
        "summary": "新タスクMTG",
        "htmlLink": "https://calendar.google.com/event?eid=xxx",
    }
    mock_post.return_value = mock_resp

    res = create_calendar_event(
        summary="新タスクMTG",
        start_time="2026-09-25 14:00",
        duration_minutes=30,
        description="アジェンダ検討",
    )
    assert res["status"] == "success"
    assert "新タスクMTG" in res["message"]
    assert res["event"]["id"] == "created_ev_123"


def test_parse_datetime_str_with_z():
    dt_z = _parse_datetime_str("2026-09-15T00:00:00Z")
    assert dt_z.year == 2026
    assert dt_z.month == 9
    assert dt_z.day == 15
    assert dt_z.hour == 9  # 00:00 UTC == 09:00 JST


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"人員動静": "roster_cid"})
@patch("requests.delete")
def test_delete_calendar_event_mock(mock_del, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_del.return_value = mock_resp

    res = delete_calendar_event(event_id="ev_to_delete_999", calendar_name="人員動静")
    assert res["status"] == "success"
    assert "ev_to_delete_999" in res["message"]
    assert res["event_id"] == "ev_to_delete_999"


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"仕事": "work_cid"})
@patch("requests.patch")
def test_update_calendar_event_mock(mock_patch, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "ev_to_update_888",
        "summary": "【変更後】全体定例",
        "start": {"dateTime": "2026-09-21T14:00:00+09:00"},
        "end": {"dateTime": "2026-09-21T15:00:00+09:00"},
    }
    mock_patch.return_value = mock_resp

    res = update_calendar_event(
        event_id="ev_to_update_888",
        summary="【変更後】全体定例",
        start_time="2026-09-21 14:00",
        calendar_name="仕事",
    )
    assert res["status"] == "success"
    assert "【変更後】全体定例" in res["message"]
    assert res["event"]["id"] == "ev_to_update_888"


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"人員動静": "roster_cid"})
@patch("requests.get")
def test_get_calendar_events_query_past_unrestricted(mock_get, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "past_ev_秋澤",
                "summary": "【出張】秋澤s",
                "start": {"dateTime": "2026-09-10T13:30:00+09:00"},
                "end": {"dateTime": "2026-09-10T15:30:00+09:00"},
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = get_calendar_events(query="秋澤")
    assert res["total"] == 1
    assert res["events"][0]["summary"] == "【出張】秋澤s"
    assert res["period"]["from"] == "指定なし（全過去）"
    assert res["period"]["to"] == "指定なし（未来無制限）"

    # Verify query parameter was sent and timeMin was not artificially constrained
    call_args = mock_get.call_args[1]
    params = call_args.get("params", {})
    assert params.get("q") == "秋澤"
    assert "timeMin" not in params
    assert "timeMax" not in params


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"人員動静": "roster_cid"})
@patch("requests.get")
@patch("requests.patch")
def test_update_calendar_event_fallback_title(mock_patch, mock_get, mock_cals, mock_auth):
    # 1. Direct patch fails with 404
    direct_fail = MagicMock()
    direct_fail.status_code = 404
    # 2. Fallback patch succeeds with 200
    patch_success = MagicMock()
    patch_success.status_code = 200
    patch_success.json.return_value = {
        "id": "real_id_999",
        "summary": "【出張】秋澤s",
        "start": {"dateTime": "2026-09-17T13:30:00+09:00"},
        "end": {"dateTime": "2026-09-17T15:30:00+09:00"},
    }
    mock_patch.side_effect = [direct_fail, patch_success]

    # Search list returns the event matching title
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.json.return_value = {
        "items": [
            {
                "id": "real_id_999",
                "summary": "【出張】秋澤s",
            }
        ]
    }
    mock_get.return_value = list_resp

    res = update_calendar_event(
        event_id="秋澤さんの出張予定",
        start_time="2026-09-17 13:30",
        end_time="2026-09-17 15:30",
    )
    assert res["status"] == "success"
    assert res["event"]["id"] == "real_id_999"
    assert "real_id_999" in res["message"]


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"人員動静": "roster_cid"})
@patch("requests.post")
def test_create_calendar_event_all_day_mock(mock_post, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "new_all_day_123",
        "summary": "【休暇】新川s",
        "start": {"date": "2026-09-28"},
        "end": {"date": "2026-09-29"},
    }
    mock_post.return_value = mock_resp

    res = create_calendar_event(
        summary="【休暇】新川s",
        start_time="2026-09-28",
        calendar_name="人員動静",
        all_day=True,
    )
    assert res["status"] == "success"
    assert res["event"]["all_day"] is True
    post_body = mock_post.call_args[1]["json"]
    assert post_body["start"] == {"date": "2026-09-28"}
    assert post_body["end"] == {"date": "2026-09-29"}
    assert post_body["reminders"] == {"useDefault": False, "overrides": []}


@patch("tools.calendar_tools._get_auth_headers", return_value={"Authorization": "Bearer fake"})
@patch("tools.calendar_tools._get_all_calendars", return_value={"人員動静": "roster_cid"})
@patch("requests.patch")
def test_update_calendar_event_all_day_mock(mock_patch, mock_cals, mock_auth):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "ev_allday_456",
        "summary": "【休暇】新川s",
        "start": {"date": "2026-09-28"},
        "end": {"date": "2026-09-29"},
    }
    mock_patch.return_value = mock_resp

    res = update_calendar_event(
        event_id="ev_allday_456",
        start_time="2026-09-28",
        all_day=True,
        calendar_name="人員動静",
    )
    assert res["status"] == "success"
    assert res["event"]["all_day"] is True
    patch_body = mock_patch.call_args[1]["json"]
    assert patch_body["start"] == {"date": "2026-09-28", "dateTime": None}
    assert patch_body["end"] == {"date": "2026-09-29", "dateTime": None}



