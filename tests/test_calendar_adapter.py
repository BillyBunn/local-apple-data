from __future__ import annotations

from typing import Any

from local_apple_data.adapters.calendar import (
    apply_calendar_change,
    get_calendar_event,
    plan_calendar_change,
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
    if payload["command"] == "calendar_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": "created-event-1",
                "title": payload["title"],
                "calendar_title": payload["calendar_title"],
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "all_day": False,
                "availability": 0,
                "location_present": bool(payload.get("location")),
                "notes_present": bool(payload.get("notes")),
                "url_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
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


def _calendar_plan() -> dict[str, Any]:
    return plan_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        location="Synthetic Room",
        notes="Synthetic event notes.",
    )


def _calendar_token(plan: dict[str, Any]) -> str:
    return "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def test_plan_calendar_change_create_returns_preview_only() -> None:
    result = _calendar_plan()

    assert result["status"] == "ok"
    assert result["source"] == "calendar"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    assert result["preview"]["idempotency_key"].startswith("calendar-plan:v1:")
    assert result["preview"]["approval"]["approval_token_format"].startswith(
        "calendar-apply:v1:"
    )
    assert result["preview"]["target"]["calendar_title"] == "Synthetic Calendar"
    assert result["preview"]["proposed"]["title"] == "Synthetic planned event"
    assert result["preview"]["proposed"]["start_date"] == "2026-06-04T17:00:00Z"


def test_plan_calendar_change_rejects_invalid_time_range() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T18:00:00Z",
        end_date="2026-06-04T17:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_time_range"


def test_apply_calendar_change_requires_confirmation() -> None:
    plan = _calendar_plan()

    result = apply_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        approval_token=_calendar_token(plan),
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_calendar_change_rejects_wrong_approval_token() -> None:
    result = apply_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_creates_event_and_reads_back() -> None:
    plan = _calendar_plan()

    result = apply_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "mutation"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["handle"].startswith("calendar:event:v1:")
    assert result["read_back"]["title"] == "Synthetic planned event"
    assert result["read_back"]["calendar_title"] == "Synthetic Calendar"


def test_apply_calendar_change_surfaces_eventkit_warning() -> None:
    def failed_runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": None,
            "warnings": [
                {
                    "code": "target_calendar_not_found",
                    "message": "Calendar was not found.",
                }
            ],
        }

    plan = _calendar_plan()
    result = apply_calendar_change(
        "create",
        title="Synthetic planned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=failed_runner,
    )

    assert result["status"] == "not_found"
    assert result["authorization_status"] == "authorized"
    assert result["warnings"][0]["code"] == "target_calendar_not_found"
