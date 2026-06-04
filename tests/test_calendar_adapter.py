from __future__ import annotations

from typing import Any

from local_apple_data.adapters.calendar import (
    get_calendar_event,
    search_calendar_events,
)


def _runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        query = payload.get("query") or ""
        events = [
            {
                "event_id": "event-1",
                "title": "Synthetic planning event",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "all_day": False,
                "availability": 0,
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "attendees_count": 2,
            }
        ]
        if query:
            events = [event for event in events if query.lower() in event["title"].lower()]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": events,
            "warnings": [],
        }
    if payload["command"] == "calendar_event_by_id":
        assert payload["event_id"] == "event-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "event": {
                "event_id": "event-1",
                "title": "Synthetic planning event",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "all_day": False,
                "availability": 0,
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "attendees_count": 2,
                "location": "Synthetic Room",
                "notes": "Synthetic event notes.",
            },
            "warnings": [],
        }
    raise AssertionError(payload)


def test_search_calendar_events_returns_metadata_only() -> None:
    result = search_calendar_events("planning", eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["authorization_status"] == "authorized"
    assert result["query"]["scope"] == "title"
    assert result["result_count"] == 1
    event = result["results"][0]
    assert event["handle"].startswith("calendar:event:v1:")
    assert event["title"] == "Synthetic planning event"
    assert event["notes_present"] is True
    assert "event-1" not in str(event)
    assert "notes_text" not in event


def test_search_calendar_events_rejects_empty_and_broad_queries() -> None:
    empty = search_calendar_events(" ", eventkit_runner=_runner)
    broad = search_calendar_events("%", eventkit_runner=_runner)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_get_calendar_event_by_handle_returns_exact_details() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = get_calendar_event(handle, eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["title"] == "Synthetic planning event"
    assert result["result"]["location"] == "Synthetic Room"
    assert result["result"]["notes_text"] == "Synthetic event notes."
    assert result["result"]["notes_chars"] == len("Synthetic event notes.")
    assert "event-1" not in str(result)


def test_get_calendar_event_truncates_notes() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = get_calendar_event(handle, max_chars=9, eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["result"]["notes_text"] == "Synthetic"
    assert result["result"]["notes_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_get_calendar_event_rejects_bad_handle() -> None:
    result = get_calendar_event("calendar:event:event-1", eventkit_runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_calendar_degrades_when_eventkit_is_not_authorized() -> None:
    def denied_runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "calendar",
            "authorization_status": "denied",
            "events": [],
            "warnings": [
                {
                    "code": "calendar_access_unavailable",
                    "message": "Calendar access is not authorized for this process.",
                }
            ],
        }

    result = search_calendar_events("planning", eventkit_runner=denied_runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "calendar_access_unavailable"
