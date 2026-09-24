"""
Google Calendar integration tools for ALICE_CoPilot.
Supports multi-calendar cross-search and event creation across Personal, Work, and Team Rosters.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import config

logger = logging.getLogger("ALICE_CoPilot.Tools.Calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
JST = timezone(timedelta(hours=9))

KNOWN_CALENDARS = {
    "個人予定": "t.a5128128@gmail.com",
    "仕事": "cd87ab4227322cdfcd3d315a0f2c71895af921b60cc6c1d1a96af30d9b7b9a45@group.calendar.google.com",
    "人員動静": "f682f5ff98f491674b4e42cb19b608e5e7aa1f345b825334e9a8a3595dde9e5c@group.calendar.google.com",
}


_cached_creds: Any = None


def _get_auth_headers() -> dict[str, str]:
    """Obtain Bearer token header from service account credentials with caching."""
    global _cached_creds
    cred_path = getattr(
        config,
        "GOOGLE_CALENDAR_CREDENTIALS_PATH",
        Path("/data/runtime/calendar/credentials.json"),
    )
    if not cred_path.exists():
        raise FileNotFoundError(f"Google Calendar credentials not found at {cred_path}")

    if _cached_creds is None:
        _cached_creds = service_account.Credentials.from_service_account_file(
            str(cred_path), scopes=SCOPES
        )

    if not _cached_creds.valid or getattr(_cached_creds, "expired", False):
        try:
            _cached_creds.refresh(Request())
        except Exception:
            _cached_creds = service_account.Credentials.from_service_account_file(
                str(cred_path), scopes=SCOPES
            )
            _cached_creds.refresh(Request())

    return {
        "Authorization": f"Bearer {_cached_creds.token}",
        "Content-Type": "application/json",
    }


def _get_all_calendars(headers: dict[str, str]) -> dict[str, str]:
    """Get mapping of calendar summary/name -> calendarId."""
    cals = dict(KNOWN_CALENDARS)
    try:
        url = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                summary = item.get("summary")
                cid = item.get("id")
                if summary and cid:
                    cals[summary] = cid
    except Exception as e:
        logger.debug(f"[Calendar] Failed to fetch calendarList: {e}")
    return cals


def _parse_datetime_str(dt_str: str) -> datetime:
    """Parse various datetime string formats into JST-aware datetime."""
    dt_str = dt_str.strip()
    now_year = datetime.now(JST).year

    # Normalize trailing Z to UTC offset for fromisoformat compatibility
    iso_candidate = dt_str
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)
        return dt
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m-%d %H:%M",
        "%m/%d %H:%M",
        "%m-%d",
        "%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=now_year)
            return dt.replace(tzinfo=JST)
        except ValueError:
            continue

    raise ValueError(f"Could not parse datetime string: '{dt_str}'")


def get_calendar_events(
    calendar_name: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    days_ahead: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """
    Get scheduled events across all user Google Calendars (Personal, Work, Team Roster, etc.).
    If calendar_name is omitted, seamlessly aggregates and sorts events across ALL calendars.
    Supports broad past/future search when query is provided or when searching past events.

    Args:
        calendar_name: Optional target calendar name (e.g. '個人予定', '仕事', '人員動静'). If omitted, searches ALL calendars.
        time_min: Start time (ISO or YYYY-MM-DD HH:MM). If 'past' or 'all', does not restrict past. Defaults to today only when no query/time_max.
        time_max: End time (ISO or YYYY-MM-DD HH:MM). Defaults to days_ahead from time_min.
        days_ahead: Number of days to look ahead (defaults to 30 for forward schedule checks).
        query: Optional keyword filter for summary/description. When query is set, searches all past & future unless explicit time limits are passed.

    Returns:
        dict: Total events count and formatted event list with calendar names.
    """
    try:
        now_jst = datetime.now(JST)

        params_base: dict[str, Any] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        }

        if query and query.strip():
            params_base["q"] = query.strip()

        # Handle time boundaries
        dt_start: datetime | None = None
        dt_end: datetime | None = None

        # 1. Start boundary (time_min)
        if time_min and str(time_min).lower() not in ("all", "past", "any", "none"):
            dt_start = _parse_datetime_str(str(time_min))
            params_base["timeMin"] = dt_start.isoformat()
        elif not query and not time_max:
            # Forward-looking schedule check: default to start of today
            dt_start = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
            params_base["timeMin"] = dt_start.isoformat()

        # 2. End boundary (time_max / days_ahead)
        if time_max and str(time_max).lower() not in ("all", "future", "any", "none"):
            dt_end = _parse_datetime_str(str(time_max))
            params_base["timeMax"] = dt_end.isoformat()
        elif days_ahead is not None:
            base_dt = dt_start if dt_start else now_jst
            dt_end = base_dt + timedelta(days=days_ahead)
            params_base["timeMax"] = dt_end.isoformat()
        elif not query and not time_min:
            # General schedule check without query: default to +30 days
            dt_end = (dt_start if dt_start else now_jst) + timedelta(days=30)
            params_base["timeMax"] = dt_end.isoformat()

        headers = _get_auth_headers()
        all_cals = _get_all_calendars(headers)

        target_cals: dict[str, str] = {}
        if calendar_name:
            for cname, cid in all_cals.items():
                if calendar_name in cname or cname in calendar_name:
                    target_cals[cname] = cid
            if not target_cals:
                target_cals = all_cals
        else:
            target_cals = all_cals

        all_events = []
        for cname, cid in target_cals.items():
            params = dict(params_base)
            url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events"
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"[Calendar] Failed to fetch events from {cname}: {resp.text}")
                continue

            items = resp.json().get("items", [])
            for item in items:
                start_info = item.get("start", {})
                end_info = item.get("end", {})

                if "dateTime" in start_info:
                    start_str = start_info["dateTime"][:16].replace("T", " ")
                    raw_start = start_info["dateTime"]
                    all_day = False
                else:
                    start_str = start_info.get("date", "")
                    raw_start = start_info.get("date", "")
                    all_day = True

                if "dateTime" in end_info:
                    end_str = end_info["dateTime"][:16].replace("T", " ")
                else:
                    end_str = end_info.get("date", "")

                all_events.append({
                    "id": item.get("id"),
                    "calendar": cname,
                    "summary": item.get("summary", "(タイトルなし)"),
                    "start": start_str,
                    "end": end_str,
                    "all_day": all_day,
                    "location": item.get("location", ""),
                    "description": item.get("description", ""),
                    "_sort_key": raw_start,
                })

        # Sort combined events by start time
        all_events.sort(key=lambda x: x["_sort_key"])
        for ev in all_events:
            ev.pop("_sort_key", None)

        return {
            "total": len(all_events),
            "period": {
                "from": dt_start.strftime("%Y-%m-%d %H:%M") if dt_start else "指定なし（全過去）",
                "to": dt_end.strftime("%Y-%m-%d %H:%M") if dt_end else "指定なし（未来無制限）",
            },
            "searched_calendars": list(target_cals.keys()),
            "events": all_events,
        }
    except Exception as e:
        logger.error(f"[get_calendar_events] Exception: {e}", exc_info=True)
        return {"error": str(e)}


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str | None = None,
    duration_minutes: int = 60,
    calendar_name: str = "個人予定",
    description: str = "",
    location: str = "",
    all_day: bool = False,
) -> dict[str, Any]:
    """
    Create a new event in user's Google Calendar.

    Args:
        summary: Event title / summary (required)
        start_time: Start datetime (e.g. '2026-09-20 14:00' or '2026-09-20' or ISO)
        end_time: End datetime (optional). If omitted, start_time + duration_minutes.
        duration_minutes: Duration in minutes if end_time not given (default 60).
        calendar_name: Name of the calendar to register into (default '個人予定', or '仕事', '人員動静').
        description: Event description/memo.
        location: Event location.
        all_day: Set to True for all-day events (e.g. vacation, all-day business trip, holidays).

    Returns:
        dict: Result with created event info or error.
    """
    try:
        now_jst = datetime.now(JST)
        dt_start = _parse_datetime_str(start_time)
        if dt_start.year < now_jst.year:
            dt_start = dt_start.replace(year=now_jst.year)

        text_check = f"{summary} {description}".lower()
        is_all_day = (
            all_day
            or "終日" in summary
            or "終日" in description
            or (len(start_time.strip()) == 10 and "-" in start_time and ":" not in start_time)
        )

        headers = _get_auth_headers()
        all_cals = _get_all_calendars(headers)

        cal_id = all_cals.get(calendar_name)
        if not cal_id:
            # Fuzzy match
            for cname, cid in all_cals.items():
                if calendar_name in cname or cname in calendar_name:
                    cal_id = cid
                    calendar_name = cname
                    break
        if not cal_id:
            cal_id = KNOWN_CALENDARS.get("個人予定", "t.a5128128@gmail.com")
            calendar_name = "個人予定"

        if is_all_day:
            start_date_str = dt_start.strftime("%Y-%m-%d")
            if end_time:
                dt_end = _parse_datetime_str(end_time)
                if dt_end.year < now_jst.year:
                    dt_end = dt_end.replace(year=now_jst.year)
                end_date_str = (dt_end + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                end_date_str = (dt_start + timedelta(days=1)).strftime("%Y-%m-%d")

            body = {
                "summary": summary.strip(),
                "start": {"date": start_date_str},
                "end": {"date": end_date_str},
            }
            start_disp = f"{start_date_str} (終日)"
            end_disp = "終日"
        else:
            if end_time:
                dt_end = _parse_datetime_str(end_time)
                if dt_end.year < now_jst.year:
                    dt_end = dt_end.replace(year=now_jst.year)
            else:
                dt_end = dt_start + timedelta(minutes=duration_minutes)

            body = {
                "summary": summary.strip(),
                "start": {"dateTime": dt_start.isoformat()},
                "end": {"dateTime": dt_end.isoformat()},
            }
            start_disp = dt_start.strftime("%Y-%m-%d %H:%M")
            end_disp = dt_end.strftime("%H:%M")

        if description:
            body["description"] = description.strip()
        if location:
            body["location"] = location.strip()

        # Handle notification / alarm suppression
        if is_all_day or any(kw in text_check for kw in ("通知不要", "アラーム不要", "通知なし", "アラームなし", "通知は不要", "アラームは不要", "通知無し")):
            body["reminders"] = {"useDefault": False, "overrides": []}

        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
        resp = requests.post(url, headers=headers, json=body, timeout=10)

        if resp.status_code not in (200, 201):
            logger.error(f"[create_calendar_event] API error: {resp.status_code} {resp.text}")
            return {"error": f"Failed to create event (status {resp.status_code}): {resp.text}"}

        res_data = resp.json()

        return {
            "status": "success",
            "message": f"カレンダー「{calendar_name}」に予定「{summary}」（{start_disp}）を登録しました。",
            "event": {
                "id": res_data.get("id"),
                "calendar": calendar_name,
                "summary": res_data.get("summary"),
                "start": start_disp,
                "end": end_disp,
                "all_day": is_all_day,
                "htmlLink": res_data.get("htmlLink"),
            },
        }
    except Exception as e:
        logger.error(f"[create_calendar_event] Exception: {e}", exc_info=True)
        return {"error": str(e)}


def _is_fuzzy_summary_match(query: str, summary: str) -> bool:
    """Check if query matches an event summary fuzzily or by keyword tokens."""
    q = query.strip().lower()
    s = summary.strip().lower()
    if not q or not s:
        return False
    if q in s or s in q:
        return True
    cleaned_q = q.replace("さん", " ").replace("の", " ").replace("予定", " ").replace("【", " ").replace("】", " ")
    tokens = [t.strip() for t in cleaned_q.split() if len(t.strip()) >= 2]
    if tokens and any(t in s for t in tokens):
        return True
    return False


def delete_calendar_event(
    event_id: str,
    calendar_name: str | None = None,
) -> dict[str, Any]:
    """
    Delete a scheduled event from Google Calendar.

    Args:
        event_id: Google Calendar event ID (e.g. 'jqgo6ka2598qpdhd2ud0eafsms') or exact event title if ID unknown.
        calendar_name: Optional target calendar name (e.g. '個人予定', '仕事', '人員動静').
                      If omitted, automatically searches across all known calendars.

    Returns:
        dict: Success confirmation or error details.
    """
    try:
        headers = _get_auth_headers()
        all_cals = _get_all_calendars(headers)

        target_cals = {}
        if calendar_name:
            for cname, cid in all_cals.items():
                if calendar_name in cname or cname in calendar_name:
                    target_cals[cname] = cid
                    break
        if not target_cals:
            target_cals = all_cals

        # 1. Direct attempt with event_id
        for cname, cid in target_cals.items():
            url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events/{event_id}"
            resp = requests.delete(url, headers=headers, timeout=10)
            if resp.status_code in (200, 204):
                logger.info(f"[delete_calendar_event] Successfully deleted event {event_id} from {cname}")
                return {
                    "status": "success",
                    "message": f"カレンダー「{cname}」から予定（ID: {event_id}）を削除しました。",
                    "event_id": event_id,
                    "calendar": cname,
                }

        # 2. If direct deletion gave 404, check if event_id is actually a summary title or fuzzy keyword
        found_events = []
        for cname, cid in target_cals.items():
            list_url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events"
            list_resp = requests.get(list_url, headers=headers, params={"maxResults": 50, "singleEvents": "true", "q": event_id.strip()}, timeout=10)
            if list_resp.status_code == 200:
                items = list_resp.json().get("items", [])
                for item in items:
                    item_summary = item.get("summary", "")
                    if item.get("id") == event_id or _is_fuzzy_summary_match(event_id, item_summary):
                        found_events.append((cname, cid, item))

        if len(found_events) == 1:
            cname, cid, item = found_events[0]
            real_id = item.get("id")
            del_url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events/{real_id}"
            del_resp = requests.delete(del_url, headers=headers, timeout=10)
            if del_resp.status_code in (200, 204):
                summary = item.get("summary", "")
                logger.info(f"[delete_calendar_event] Deleted event '{summary}' ({real_id}) from {cname}")
                return {
                    "status": "success",
                    "message": f"カレンダー「{cname}」から予定「{summary}」（ID: {real_id}）を削除しました。",
                    "event_id": real_id,
                    "calendar": cname,
                }

        if len(found_events) > 1:
            candidates = [f"[{cn}] {it.get('summary')} (ID: {it.get('id')})" for cn, _, it in found_events]
            return {
                "error": "複数の該当予定が見つかりました。削除対象を1つに特定するためIDを指定してください。",
                "candidates": candidates,
            }

        return {
            "error": f"指定された予定（IDまたはキーワード: '{event_id}'）が見つかりませんでした。",
        }
    except Exception as e:
        logger.error(f"[delete_calendar_event] Exception: {e}", exc_info=True)
        return {"error": str(e)}


def update_calendar_event(
    event_id: str,
    summary: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    calendar_name: str | None = None,
    description: str | None = None,
    location: str | None = None,
    all_day: bool | None = None,
) -> dict[str, Any]:
    """
    Update an existing event in Google Calendar.
    Supports updating by event_id or by event title / keyword fallback.

    Args:
        event_id: Google Calendar event ID or title to update.
        summary: New event title.
        start_time: New start time (e.g. '2026-09-20 15:00' or '2026-09-20').
        end_time: New end time.
        calendar_name: Target calendar name ('個人予定', '仕事', '人員動静').
        description: New description.
        location: New location.
        all_day: Set to True for all-day event, or False for timed event.

    Returns:
        dict: Updated event details or error.
    """
    try:
        headers = _get_auth_headers()
        all_cals = _get_all_calendars(headers)

        target_cals = {}
        if calendar_name:
            for cname, cid in all_cals.items():
                if calendar_name in cname or cname in calendar_name:
                    target_cals[cname] = cid
                    break
        if not target_cals:
            target_cals = all_cals

        patch_body: dict[str, Any] = {}
        if summary is not None:
            patch_body["summary"] = summary.strip()
        if description is not None:
            patch_body["description"] = description.strip()
        if location is not None:
            patch_body["location"] = location.strip()

        check_text = f"{event_id} {summary or ''} {description or ''}"
        target_all_day = all_day
        if target_all_day is None:
            if "終日" in check_text:
                target_all_day = True
            elif start_time and len(start_time.strip()) == 10 and ":" not in start_time:
                target_all_day = True

        if target_all_day is True:
            if start_time is not None:
                dt_start = _parse_datetime_str(start_time)
                start_date_str = dt_start.strftime("%Y-%m-%d")
                if end_time is not None:
                    dt_end = _parse_datetime_str(end_time)
                    end_date_str = (dt_end + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    end_date_str = (dt_start + timedelta(days=1)).strftime("%Y-%m-%d")
                patch_body["start"] = {"date": start_date_str, "dateTime": None}
                patch_body["end"] = {"date": end_date_str, "dateTime": None}
        elif target_all_day is False:
            if start_time is not None:
                dt_start = _parse_datetime_str(start_time)
                patch_body["start"] = {"dateTime": dt_start.isoformat(), "date": None}
            if end_time is not None:
                dt_end = _parse_datetime_str(end_time)
                patch_body["end"] = {"dateTime": dt_end.isoformat(), "date": None}
        else:
            if start_time is not None:
                dt_start = _parse_datetime_str(start_time)
                patch_body["start"] = {"dateTime": dt_start.isoformat()}
            if end_time is not None:
                dt_end = _parse_datetime_str(end_time)
                patch_body["end"] = {"dateTime": dt_end.isoformat()}

        if target_all_day is True or any(kw in check_text for kw in ("通知不要", "アラーム不要", "通知なし", "アラームなし", "通知は不要", "アラームは不要", "通知無し")):
            patch_body["reminders"] = {"useDefault": False, "overrides": []}

        # 1. Direct attempt with event_id
        for cname, cid in target_cals.items():
            ev_url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events/{event_id}"
            if "start" not in patch_body and target_all_day is True:
                try:
                    get_resp = requests.get(ev_url, headers=headers, timeout=10)
                    if get_resp.status_code == 200:
                        ev_item = get_resp.json()
                        cur_st = ev_item.get("start", {}).get("dateTime") or ev_item.get("start", {}).get("date") or ""
                        if cur_st:
                            dt_cur = _parse_datetime_str(cur_st[:10])
                            s_date = dt_cur.strftime("%Y-%m-%d")
                            e_date = (dt_cur + timedelta(days=1)).strftime("%Y-%m-%d")
                            patch_body["start"] = {"date": s_date, "dateTime": None}
                            patch_body["end"] = {"date": e_date, "dateTime": None}
                except Exception:
                    pass

            resp = requests.patch(ev_url, headers=headers, json=patch_body, timeout=10)
            if resp.status_code == 200:
                res_data = resp.json()
                logger.info(f"[update_calendar_event] Successfully updated event {event_id} in {cname}")
                return {
                    "status": "success",
                    "message": f"カレンダー「{cname}」の予定「{res_data.get('summary')}」（ID: {event_id}）を更新しました。",
                    "event": {
                        "id": res_data.get("id"),
                        "calendar": cname,
                        "summary": res_data.get("summary"),
                        "start": res_data.get("start", {}).get("dateTime") or res_data.get("start", {}).get("date"),
                        "end": res_data.get("end", {}).get("dateTime") or res_data.get("end", {}).get("date"),
                        "all_day": "date" in res_data.get("start", {}),
                    },
                }

        # 2. Fallback: Search by title / keyword across calendars
        found_events = []
        for cname, cid in target_cals.items():
            list_url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events"
            list_resp = requests.get(list_url, headers=headers, params={"maxResults": 50, "singleEvents": "true", "q": event_id.strip()}, timeout=10)
            if list_resp.status_code == 200:
                items = list_resp.json().get("items", [])
                for item in items:
                    item_summary = item.get("summary", "")
                    if item.get("id") == event_id or _is_fuzzy_summary_match(event_id, item_summary):
                        found_events.append((cname, cid, item))

        if len(found_events) == 1:
            cname, cid, item = found_events[0]
            real_id = item.get("id")
            if "start" not in patch_body and target_all_day is True:
                cur_st = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date") or ""
                if cur_st:
                    dt_cur = _parse_datetime_str(cur_st[:10])
                    s_date = dt_cur.strftime("%Y-%m-%d")
                    e_date = (dt_cur + timedelta(days=1)).strftime("%Y-%m-%d")
                    patch_body["start"] = {"date": s_date, "dateTime": None}
                    patch_body["end"] = {"date": e_date, "dateTime": None}

            patch_url = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events/{real_id}"
            resp = requests.patch(patch_url, headers=headers, json=patch_body, timeout=10)
            if resp.status_code == 200:
                res_data = resp.json()
                logger.info(f"[update_calendar_event] Successfully updated event '{res_data.get('summary')}' ({real_id}) in {cname}")
                return {
                    "status": "success",
                    "message": f"カレンダー「{cname}」の予定「{res_data.get('summary')}」（ID: {real_id}）を更新しました。",
                    "event": {
                        "id": res_data.get("id"),
                        "calendar": cname,
                        "summary": res_data.get("summary"),
                        "start": res_data.get("start", {}).get("dateTime") or res_data.get("start", {}).get("date"),
                        "end": res_data.get("end", {}).get("dateTime") or res_data.get("end", {}).get("date"),
                        "all_day": "date" in res_data.get("start", {}),
                    },
                }

        if len(found_events) > 1:
            candidates = [f"[{cn}] {it.get('summary')} (ID: {it.get('id')})" for cn, _, it in found_events]
            return {
                "error": "複数の該当予定が見つかりました。更新対象を1つに特定するためIDを指定してください。",
                "candidates": candidates,
            }

        return {
            "error": f"指定された予定（IDまたはキーワード: '{event_id}'）の更新に失敗しました。予定が見つからないか権限がありません。",
        }
    except Exception as e:
        logger.error(f"[update_calendar_event] Exception: {e}", exc_info=True)
        return {"error": str(e)}

