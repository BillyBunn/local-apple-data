from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from local_apple_data.adapters import calendar as calendar_adapter
from local_apple_data.adapters.calendar import (
    apply_calendar_calendar_change,
    apply_calendar_change,
    check_calendar_authorization,
    get_calendar_calendar,
    get_calendar_event,
    get_calendar_participant,
    list_calendar_events_for_calendar,
    list_calendar_participants,
    plan_calendar_calendar_change,
    plan_calendar_change,
    request_calendar_full_access,
    search_calendar_calendars,
    search_calendar_events,
)
from local_apple_data.handles import make_opaque_handle


def _fake_event_date(value: str, all_day: bool) -> str:
    if all_day:
        return value.split("T", 1)[0]
    return value


def _same_instant(left: str, right: str) -> bool:
    if "T" not in left or "T" not in right:
        return left == right
    return datetime.fromisoformat(left.replace("Z", "+00:00")) == datetime.fromisoformat(
        right.replace("Z", "+00:00")
    )


def _event_url_fields(payload: dict[str, Any]) -> dict[str, Any]:
    event_url = str(payload.get("event_url") or "")
    if not event_url:
        return {"url_present": False}
    return {
        "url_present": True,
        "event_url_safe_sha256": hashlib.sha256(event_url.encode("utf-8")).hexdigest(),
    }


def _structured_location_safe_sha256(payload: dict[str, Any]) -> str:
    geo_present = bool(payload.get("geo_present"))
    parts = [
        f"title={payload.get('title', '')}",
        f"geo_present={'true' if geo_present else 'false'}",
    ]
    if geo_present:
        parts.extend(
            [
                f"latitude={float(payload.get('latitude')):.6f}",
                f"longitude={float(payload.get('longitude')):.6f}",
                f"radius_meters={float(payload.get('radius_meters')):.3f}",
            ]
        )
    else:
        parts.extend(["latitude=", "longitude=", "radius_meters="])
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


ADJACENT_OCCURRENCE_EVENT_URL = "https://meet.example.invalid/adjacent?id=selected-occurrence"
ADJACENT_OCCURRENCE_EVENT_URL_SHA256 = hashlib.sha256(
    ADJACENT_OCCURRENCE_EVENT_URL.encode("utf-8")
).hexdigest()
DEFAULT_EVENT_LOCATION_SHA256 = hashlib.sha256("Synthetic Room".encode("utf-8")).hexdigest()
ADJACENT_OCCURRENCE_LOCATION = "Synthetic Adjacent Room"
ADJACENT_OCCURRENCE_LOCATION_SHA256 = hashlib.sha256(
    ADJACENT_OCCURRENCE_LOCATION.encode("utf-8")
).hexdigest()
ADJACENT_OCCURRENCE_STRUCTURED_LOCATION = {
    "title": ADJACENT_OCCURRENCE_LOCATION,
    "geo_present": False,
}
ADJACENT_OCCURRENCE_STRUCTURED_LOCATION_SHA256 = _structured_location_safe_sha256(
    ADJACENT_OCCURRENCE_STRUCTURED_LOCATION
)
ADJACENT_OCCURRENCE_ALARM_STATE_SHA256 = hashlib.sha256(
    "\n".join(
        [
            "offsets=-10",
            "absolute_dates=",
            "sound_name=",
            "proximity=",
            "structured_location_sha256=",
            "email_address_sha256=",
        ]
    ).encode("utf-8")
).hexdigest()



def _structured_location_fields(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("structured_location_clear_requested"):
        return {
            "location_present": False,
            "structured_location_present": False,
        }
    structured = payload.get("structured_location")
    if isinstance(structured, dict) and structured:
        return {
            "location_present": True,
            "structured_location": structured,
            "structured_location_present": True,
        }
    return {}


def _alarm_sound_fields(payload: dict[str, Any]) -> dict[str, str]:
    sound_name = str(payload.get("alarm_sound_name") or "")
    email_address = str(payload.get("alarm_email_address") or "").strip().lower()
    if email_address:
        return {
            "alarm_sound_name": "",
            "alarm_email_address_sha256": hashlib.sha256(
                email_address.encode("utf-8")
            ).hexdigest(),
            "alarm_action": "email",
        }
    return {
        "alarm_sound_name": sound_name,
        "alarm_action": "audio" if sound_name else "display",
    }


def _alarm_fields(payload: dict[str, Any]) -> dict[str, Any]:
    proximity = str(payload.get("alarm_proximity") or "")
    structured_location = payload.get("alarm_structured_location")
    fields: dict[str, Any] = _alarm_sound_fields(payload)
    if proximity:
        fields.update(
            {
                "alarm_proximity": proximity,
                "alarm_structured_location": structured_location,
                "alarm_action": "geofence",
            }
        )
    return fields


def _alarm_state_fields_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("recurrence_update_scope") == "this_event"
        and not payload.get("selected_occurrence_alarm_update_requested")
    ):
        fields: dict[str, Any] = {
            "alarm_offsets_minutes": payload.get("expected_alarm_offsets_minutes", []),
            "alarm_absolute_dates": payload.get("expected_alarm_absolute_dates", []),
            "alarm_sound_name": payload.get("expected_alarm_sound_name", ""),
            "alarm_action": "audio"
            if payload.get("expected_alarm_sound_name")
            else "display",
        }
        expected_email = str(payload.get("expected_alarm_email_address_sha256") or "")
        if expected_email:
            fields.update(
                {
                    "alarm_sound_name": "",
                    "alarm_email_address_sha256": expected_email,
                    "alarm_action": "email",
                }
            )
        expected_proximity = str(payload.get("expected_alarm_proximity") or "")
        if expected_proximity:
            fields.update(
                {
                    "alarm_offsets_minutes": [],
                    "alarm_absolute_dates": [],
                    "alarm_sound_name": "",
                    "alarm_proximity": expected_proximity,
                    "alarm_structured_location": payload.get(
                        "expected_alarm_structured_location"
                    ),
                    "alarm_action": "geofence",
                }
            )
        return fields
    return {
        "alarm_offsets_minutes": payload.get("alarm_offsets_minutes", []),
        "alarm_absolute_dates": payload.get("alarm_absolute_dates", []),
        **_alarm_fields(payload),
    }


def _alarm_action_changed(payload: dict[str, Any]) -> bool:
    email_address = str(payload.get("alarm_email_address") or "").strip().lower()
    email_sha256 = (
        hashlib.sha256(email_address.encode("utf-8")).hexdigest() if email_address else ""
    )
    return (
        str(payload.get("alarm_sound_name") or "")
        != str(payload.get("expected_alarm_sound_name") or "")
        or email_sha256 != str(payload.get("expected_alarm_email_address_sha256") or "")
        or str(payload.get("alarm_proximity") or "")
        != str(payload.get("expected_alarm_proximity") or "")
        or (payload.get("alarm_structured_location") or None)
        != (payload.get("expected_alarm_structured_location") or None)
    )


def _alarm_count(payload: dict[str, Any]) -> int:
    if payload.get("alarm_proximity"):
        return 1
    return len(payload.get("alarm_offsets_minutes", []) or payload.get("alarm_absolute_dates", []))


def _runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_calendars":
        query = (payload.get("query") or "").lower()
        include_default = bool(payload.get("include_default"))
        include_all = bool(payload.get("include_all"))
        calendars = [
            {
                "calendar_id": "calendar-1",
                "title": "Synthetic Calendar",
                "is_default_calendar": True,
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "source-1",
                "source_type": "local",
                "allowed_entity_types": ["event"],
                "supported_event_availabilities": ["busy", "free"],
            },
            {
                "calendar_id": "calendar-2",
                "title": "Synthetic Focus",
                "is_default_calendar": False,
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "caldav",
                "source_id": "source-2",
                "source_type": "caldav",
                "allowed_entity_types": ["event"],
                "supported_event_availabilities": ["busy", "free", "tentative"],
            },
            {
                "calendar_id": "calendar-test",
                "title": "LAD-TEST-old",
                "is_default_calendar": False,
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "source-1",
                "source_type": "local",
                "allowed_entity_types": ["event"],
                "supported_event_availabilities": ["busy", "free"],
            },
            {
                "calendar_id": "calendar-busy",
                "title": "LAD-TEST-busy",
                "is_default_calendar": False,
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "source-1",
                "source_type": "local",
                "allowed_entity_types": ["event"],
                "supported_event_availabilities": ["busy", "free"],
            },
        ]
        if payload.get("include_safety_counts"):
            for calendar in calendars:
                calendar["event_count_in_safety_window"] = (
                    1 if calendar["calendar_id"] == "calendar-busy" else 0
                )
                calendar["safety_window_start"] = "1900-01-01"
                calendar["safety_window_end"] = "2100-01-01"
        if not include_all:
            calendars = [
                calendar
                for calendar in calendars
                if (query and query in calendar["title"].lower())
                or (include_default and calendar["is_default_calendar"])
            ]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "calendars": calendars[: int(payload.get("limit") or 20)],
            "warnings": [],
        }
    if payload["command"] == "calendar_events_for_calendar":
        assert payload["calendar_id"] == "calendar-2"
        assert payload["start_date"] == "2026-06-01T00:00:00Z"
        assert payload["end_date"] == "2026-07-01T00:00:00Z"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "calendar": {
                "calendar_id": "calendar-2",
                "title": "Synthetic Focus",
                "is_default_calendar": False,
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "caldav",
                "source_id": "source-2",
                "source_type": "caldav",
                "allowed_entity_types": ["event"],
                "supported_event_availabilities": ["busy", "free", "tentative"],
            },
            "events": [
                {
                    "event_id": "event-focus-1",
                    "title": "Synthetic focus event",
                    "calendar_id": "calendar-2",
                    "calendar_title": "Synthetic Focus",
                    "start_date": "2026-06-04T17:00:00.000Z",
                    "end_date": "2026-06-04T18:00:00.000Z",
                    "all_day": False,
                    "availability": 0,
                    "location_present": True,
                    "notes_present": True,
                    "url_present": False,
                    "alarms_count": 1,
                    "attendees_count": 0,
                    "location": "Must not return",
                    "notes": "Must not return",
                    "event_url_safe_sha256": hashlib.sha256(
                        b"https://meet.example.invalid/must-not-return"
                    ).hexdigest(),
                    "structured_location": {
                        "title": "Must not return",
                        "geo_present": True,
                        "latitude": 1.0,
                        "longitude": 2.0,
                        "radius_meters": 3.0,
                    },
                    "structured_location_present": True,
                    "alarm_offsets_minutes": [-10],
                    "alarm_sound_name": "Glass",
                }
            ],
            "truncated": False,
            "warnings": [],
        }
    if payload["command"] == "calendar_events":
        query = payload.get("query") or ""
        events = [
            {
                "event_id": "event-1",
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "America/Los_Angeles",
                "all_day": False,
                "availability": 0,
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [-10],
                "alarm_absolute_dates": [],
                "alarms_count": 0,
                "attendees_count": 2,
            }
        ]
        if payload.get("include_location_proof"):
            for event in events:
                event["location_safe_sha256"] = DEFAULT_EVENT_LOCATION_SHA256
        if payload.get("include_structured_location_proof"):
            for event in events:
                event["structured_location_present"] = False
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
    if payload["command"] == "calendar_event_participants_by_id":
        assert payload["event_id"] == "event-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "event": {
                "event_id": "event-1",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "participants": [
                    {
                        "index": 0,
                        "participant_kind": "attendee",
                        "organizer": False,
                        "name": "Synthetic Invitee",
                        "url": "mailto:invitee@example.invalid",
                        "participant_status": 2,
                        "participant_status_name": "accepted",
                        "participant_role": 1,
                        "participant_role_name": "required",
                        "participant_type": 1,
                        "participant_type_name": "person",
                        "current_user": False,
                    },
                    {
                        "index": 1,
                        "participant_kind": "organizer",
                        "organizer": True,
                        "name": "Synthetic Organizer",
                        "url": "mailto:organizer@example.invalid",
                        "participant_status": 0,
                        "participant_status_name": "unknown",
                        "participant_role": 3,
                        "participant_role_name": "chair",
                        "participant_type": 1,
                        "participant_type_name": "person",
                        "current_user": True,
                    },
                ],
            },
            "warnings": [],
        }
    if payload["command"] == "calendar_event_participants_by_occurrence":
        assert payload["event_id"] == "event-1"
        assert payload["start_date"].startswith("2026-06-03T17:00:00")
        assert payload["end_date"].startswith("2026-06-03T18:00:00")
        return _runner(
            {
                "command": "calendar_event_participants_by_id",
                "event_id": "event-1",
            },
            _timeout,
        )
    if payload["command"] == "calendar_event_by_id":
        assert payload["event_id"] == "event-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "event": {
                "event_id": "event-1",
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "America/Los_Angeles",
                "all_day": False,
                "availability": 0,
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": payload.get("alarm_offsets_minutes", []),
                "alarm_absolute_dates": payload.get("alarm_absolute_dates", []),
                "alarms_count": _alarm_count(payload),
                "attendees_count": 2,
                "location": "Synthetic Room",
                "notes": "Synthetic event notes.",
            },
            "warnings": [],
        }
    if payload["command"] == "calendar_event_by_occurrence":
        assert payload["event_id"] == "event-1"
        assert payload["start_date"].startswith("2026-06-03T17:00:00")
        assert payload["end_date"].startswith("2026-06-03T18:00:00")
        return _runner(
            {
                "command": "calendar_event_by_id",
                "event_id": "event-1",
            },
            _timeout,
        )
    if payload["command"] == "calendar_calendar_apply_change":
        operation = payload["operation"]
        if operation == "create_calendar":
            assert payload["source_calendar_id"] == "calendar-1"
            assert payload["calendar_title"] == "LAD-TEST-new"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "mutation_applied": True,
                "calendar": {
                    "calendar_id": "calendar-created",
                    "title": "LAD-TEST-new",
                    "is_default_calendar": False,
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["event"],
                    "supported_event_availabilities": ["busy", "free"],
                    "event_count_in_safety_window": 0,
                    "safety_window_start": "1900-01-01",
                    "safety_window_end": "2100-01-01",
                },
                "read_back": {
                    "source_calendar_verified": True,
                    "calendar_empty_verified": True,
                },
                "warnings": [],
            }
        if operation == "rename_calendar":
            assert payload["calendar_id"] == "calendar-test"
            assert payload["expected_calendar_title"] == "LAD-TEST-old"
            assert payload["new_calendar_title"] == "LAD-TEST-new"
            assert payload["expected_empty_calendar"] is True
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "mutation_applied": True,
                "calendar": {
                    "calendar_id": "calendar-test",
                    "title": "LAD-TEST-new",
                    "is_default_calendar": False,
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["event"],
                    "supported_event_availabilities": ["busy", "free"],
                    "event_count_in_safety_window": 0,
                    "safety_window_start": "1900-01-01",
                    "safety_window_end": "2100-01-01",
                },
                "read_back": {
                    "calendar_renamed_verified": True,
                    "calendar_empty_verified": True,
                },
                "warnings": [],
            }
        if operation == "delete_calendar":
            assert payload["calendar_id"] == "calendar-test"
            assert payload["expected_calendar_title"] == "LAD-TEST-old"
            assert payload["expected_empty_calendar"] is True
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "mutation_applied": True,
                "calendar": None,
                "read_back": {
                    "calendar_deleted_verified": True,
                    "calendar_absent_verified": True,
                    "calendar_empty_verified": True,
                },
                "warnings": [],
            }
        raise AssertionError(operation)
    if payload["command"] == "calendar_apply_change":
        if payload["operation"] == "delete":
            if payload["expected_title"] != "Synthetic planning event":
                return {
                    "schema_version": 1,
                    "status": "error",
                    "source": "calendar",
                    "authorization_status": "authorized",
                    "warnings": [
                        {
                            "code": "expected_state_mismatch",
                            "message": "Calendar event did not match expected state.",
                        }
                    ],
                }
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "deleted": True,
                "read_back": {
                    "deleted": True,
                    "verified_absent": True,
                },
                "warnings": [],
            }
        if payload["operation"] == "update":
            if payload["expected_title"] != "Synthetic planning event":
                return {
                    "schema_version": 1,
                    "status": "error",
                    "source": "calendar",
                    "authorization_status": "authorized",
                    "event": None,
                    "warnings": [
                        {
                            "code": "expected_state_mismatch",
                            "message": "Calendar event did not match expected state.",
                        }
                    ],
                }
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "event": {
                    "event_id": payload["event_id"],
                    "title": payload["title"],
                    "calendar_id": payload.get("target_calendar_id") or "calendar-1",
                    "calendar_title": (
                        "Synthetic Focus"
                        if payload.get("target_calendar_id") == "calendar-2"
                        else payload["expected_calendar_title"]
                    ),
                    "start_date": _fake_event_date(
                        payload["start_date"],
                        bool(payload.get("all_day")),
                    ),
                    "end_date": _fake_event_date(
                        payload["end_date"],
                        bool(payload.get("all_day")),
                    ),
                    "time_zone": payload.get("time_zone", ""),
                    "all_day": bool(payload.get("all_day")),
                    "availability": int(payload.get("availability", 0)),
                    "availability_name": {
                        0: "busy",
                        1: "free",
                        2: "tentative",
                        3: "unavailable",
                    }[int(payload.get("availability", 0))],
                    "location_present": bool(payload.get("location")),
                    **_structured_location_fields(payload),
                    "notes_present": bool(payload.get("notes")),
                    **_event_url_fields(payload),
                    "alarm_offsets_minutes": payload.get("alarm_offsets_minutes", []),
                    "alarm_absolute_dates": payload.get("alarm_absolute_dates", []),
                    **_alarm_fields(payload),
                    "recurrence": payload.get(
                        "recurrence",
                        {
                            "frequency": "",
                            "interval": 0,
                            "count": 0,
                            "recurrence_present": False,
                        },
                    ),
                    "recurrence_present": bool(
                        payload.get("recurrence", {}).get("recurrence_present", False)
                    ),
                    "alarms_count": _alarm_count(payload),
                    "attendees_count": 0,
                },
                "warnings": [],
            }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
                "event": {
                    "event_id": "created-event-1",
                    "title": payload["title"],
                    "calendar_id": payload.get("calendar_id") or "calendar-1",
                    "calendar_title": (
                        "Synthetic Focus"
                        if payload.get("calendar_id") == "calendar-2"
                        else (
                            "Synthetic Calendar"
                            if payload.get("calendar_id") == "calendar-1"
                            else payload["calendar_title"]
                        )
                    ),
                "start_date": _fake_event_date(
                    payload["start_date"],
                    bool(payload.get("all_day")),
                ),
                "end_date": _fake_event_date(
                    payload["end_date"],
                    bool(payload.get("all_day")),
                ),
                "time_zone": payload.get("time_zone", ""),
                "all_day": bool(payload.get("all_day")),
                "availability": int(payload.get("availability", 0)),
                "availability_name": {
                    0: "busy",
                    1: "free",
                    2: "tentative",
                    3: "unavailable",
                }[int(payload.get("availability", 0))],
                    "location_present": bool(payload.get("location")),
                    **_structured_location_fields(payload),
                    "notes_present": bool(payload.get("notes")),
                **_event_url_fields(payload),
                "alarm_offsets_minutes": payload.get("alarm_offsets_minutes", []),
                "alarm_absolute_dates": payload.get("alarm_absolute_dates", []),
                **_alarm_fields(payload),
                "recurrence": payload.get(
                    "recurrence",
                    {
                        "frequency": "",
                        "interval": 0,
                        "count": 0,
                        "recurrence_present": False,
                    },
                ),
                "recurrence_present": bool(
                    payload.get("recurrence", {}).get("recurrence_present", False)
                ),
                "alarms_count": _alarm_count(payload),
                "attendees_count": 0,
            },
            "warnings": [],
        }
    raise AssertionError(payload)


def _recurring_delete_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        result = _runner(payload, timeout)
        first = result["events"][0]
        recurrence = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        first["recurrence_present"] = True
        first["recurrence"] = recurrence
        adjacent = {
            **first,
            "start_date": "2026-06-10T17:00:00.000Z",
            "end_date": "2026-06-10T18:00:00.000Z",
        }
        result["events"] = [first, adjacent]
        return result
    if payload["command"] in {"calendar_event_by_id", "calendar_event_by_occurrence"}:
        result = _runner(payload, timeout)
        result["event"]["recurrence_present"] = True
        result["event"]["recurrence"] = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        return result
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "delete":
        if payload.get("occurrence_start_date") != "2026-06-03T17:00:00.000Z":
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Calendar occurrence identity did not match expected state.",
                    }
                ],
            }
        if payload.get("recurrence_delete_scope") != "this_event":
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "unsupported_event_state",
                        "message": "Calendar event has unsupported recurrence state.",
                    }
                ],
            }
        if payload.get("expected_recurrence_present") is not True:
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Calendar event did not match expected recurrence state.",
                    }
                ],
            }
        if payload.get("adjacent_occurrence_start_date") != "2026-06-10T17:00:00.000Z":
            return {
                "schema_version": 1,
                "status": "apply_unknown",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "read_back_unavailable",
                        "message": "Calendar occurrence was deleted but sibling preservation proof was unavailable.",
                    }
                ],
            }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {
                "deleted": True,
                "verified_absent": True,
                "selected_occurrence_verified_absent": True,
                "adjacent_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _runner(payload, timeout)


def _recurring_update_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] != "calendar_apply_change":
        result = _recurring_delete_runner(payload, timeout)
        if "events" in result:
            for event in result["events"]:
                event["recurrence_present"] = True
                event["recurrence"] = recurrence
        if "event" in result:
            result["event"]["recurrence_present"] = True
            result["event"]["recurrence"] = recurrence
        return result
    if payload["operation"] == "update":
        assert payload["recurrence_update_scope"] == "this_event"
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == recurrence
        assert payload["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
        assert payload["occurrence_end_date"] == "2026-06-03T18:00:00.000Z"
        assert payload["adjacent_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
        assert payload["adjacent_occurrence_end_date"] == "2026-06-10T18:00:00.000Z"
        if payload["adjacent_occurrence_event_url_present"]:
            assert (
                payload["adjacent_occurrence_event_url_sha256"]
                == ADJACENT_OCCURRENCE_EVENT_URL_SHA256
            )
        else:
            assert payload["adjacent_occurrence_event_url_sha256"] == ""
        if payload["adjacent_occurrence_location_present"]:
            assert payload["adjacent_occurrence_location_sha256"]
        else:
            assert payload["adjacent_occurrence_location_sha256"] == ""
        if payload["adjacent_occurrence_structured_location_present"]:
            assert payload["adjacent_occurrence_structured_location_sha256"]
        else:
            assert payload["adjacent_occurrence_structured_location_sha256"] == ""
        if payload["adjacent_occurrence_alarm_state_present"]:
            assert payload["adjacent_occurrence_alarm_state_sha256"]
        else:
            assert payload["adjacent_occurrence_alarm_state_sha256"] == ""
        if payload.get("structured_location"):
            if payload.get("expected_structured_location"):
                assert payload["expected_structured_location_present"] is True
            else:
                assert payload["expected_structured_location_present"] is False
        if payload.get("structured_location_clear_requested"):
            assert payload["expected_structured_location_present"] is True
            assert payload["expected_structured_location"]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": payload.get("target_calendar_id") or "calendar-1",
                "calendar_title": (
                    "Synthetic Focus"
                    if payload.get("target_calendar_id") == "calendar-2"
                    else payload["expected_calendar_title"]
                ),
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": payload.get("time_zone", ""),
                "all_day": bool(payload.get("all_day", False)),
                "availability": int(payload.get("availability", 0)),
                "availability_name": {
                    0: "busy",
                    1: "free",
                    2: "tentative",
                    3: "unavailable",
                }[int(payload.get("availability", 0))],
                "location_present": bool(payload.get("location")),
                **_structured_location_fields(payload),
                "notes_present": bool(payload.get("notes")),
                **_event_url_fields(payload),
                **_alarm_state_fields_for_payload(payload),
                "recurrence": recurrence,
                "recurrence_present": True,
                "alarms_count": _alarm_count(payload),
                "attendees_count": 0,
            },
            "read_back": {
                "selected_occurrence_updated_verified": True,
                "adjacent_occurrence_verified_present": True,
                "adjacent_occurrence_event_url_verified": True,
                "adjacent_occurrence_location_verified": True,
                "adjacent_occurrence_alarm_verified": True,
                "selected_occurrence_rescheduled_verified": (
                    not _same_instant(payload["start_date"], payload["occurrence_start_date"])
                    or not _same_instant(payload["end_date"], payload["occurrence_end_date"])
                ),
                "original_occurrence_verified_absent": (
                    not _same_instant(payload["start_date"], payload["occurrence_start_date"])
                    or not _same_instant(payload["end_date"], payload["occurrence_end_date"])
                ),
                "selected_occurrence_calendar_move_verified": bool(
                    payload.get("target_calendar_id")
                ),
                "adjacent_occurrence_calendar_verified": True,
                "all_day_verified": bool(payload.get("all_day"))
                != bool(payload.get("expected_all_day"))
                or (
                    bool(payload.get("all_day"))
                    and bool(payload.get("expected_all_day"))
                    and (
                        not _same_instant(payload["start_date"], payload["occurrence_start_date"])
                        or not _same_instant(payload["end_date"], payload["occurrence_end_date"])
                    )
                ),
                "structured_location_verified": bool(payload.get("structured_location")),
                "structured_location_cleared_verified": bool(
                    payload.get("structured_location_clear_requested")
                ),
                "display_alarm_verified": (
                    bool(payload.get("selected_occurrence_alarm_update_requested"))
                    and (
                    payload.get("alarm_offsets_minutes", [])
                    != payload.get("expected_alarm_offsets_minutes", [])
                    or payload.get("alarm_absolute_dates", [])
                    != payload.get("expected_alarm_absolute_dates", [])
                    )
                ),
                "action_alarm_verified": bool(
                    payload.get("selected_occurrence_alarm_update_requested")
                )
                and _alarm_action_changed(payload),
            },
            "warnings": [],
        }
    return _recurring_delete_runner(payload, timeout)


def _recurring_all_day_update_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    event = {
        "event_id": "all-day-recurring-event-1",
        "title": "Synthetic all day recurring event",
        "calendar_id": "calendar-1",
        "calendar_title": "Synthetic Calendar",
        "start_date": "2026-06-05",
        "end_date": "2026-06-06",
        "time_zone": "",
        "all_day": True,
        "availability": 0,
        "availability_name": "busy",
        "location_present": False,
        "structured_location_present": False,
        "notes_present": False,
        "url_present": False,
        "alarm_offsets_minutes": [],
        "alarm_absolute_dates": [],
        "alarms_count": 0,
        "attendees_count": 0,
        "recurrence_present": True,
        "recurrence": recurrence,
    }
    if payload["command"] == "calendar_events":
        future = {
            **event,
            "start_date": "2026-06-12",
            "end_date": "2026-06-13",
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": [event, future],
            "warnings": [],
        }
    if payload["command"] == "calendar_event_by_occurrence":
        assert payload["event_id"] == "all-day-recurring-event-1"
        assert payload["start_date"] in {"2026-06-05", "2026-06-12"}
        assert payload["end_date"] in {"2026-06-06", "2026-06-13"}
        returned = {
            **event,
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": returned,
            "warnings": [],
        }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload["recurrence_update_scope"] == "this_event"
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == recurrence
        assert payload["expected_all_day"] is True
        if payload["all_day"] is False:
            assert payload["time_zone"] == "America/Los_Angeles"
        else:
            assert payload["all_day"] is True
            assert payload["start_date"] == "2026-06-06"
            assert payload["end_date"] == "2026-06-07"
        assert payload["occurrence_start_date"] == "2026-06-05"
        assert payload["occurrence_end_date"] == "2026-06-06"
        assert payload["adjacent_occurrence_start_date"] == "2026-06-12"
        assert payload["adjacent_occurrence_end_date"] == "2026-06-13"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                **event,
                "title": payload["title"],
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": payload.get("time_zone") or "",
                "all_day": payload["all_day"],
                "recurrence": recurrence,
                "recurrence_present": True,
            },
            "read_back": {
                "selected_occurrence_updated_verified": True,
                "adjacent_occurrence_verified_present": True,
                "adjacent_occurrence_event_url_verified": True,
                "adjacent_occurrence_location_verified": True,
                "adjacent_occurrence_alarm_verified": True,
                "selected_occurrence_rescheduled_verified": True,
                "original_occurrence_verified_absent": True,
                "all_day_verified": True,
            },
            "warnings": [],
        }
    return _recurring_update_runner(payload, timeout)


def _recurring_update_adjacent_url_runner(
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    result = _recurring_update_runner(payload, timeout)
    if payload["command"] == "calendar_events":
        for event in result.get("events", []):
            if event.get("start_date") == "2026-06-10T17:00:00.000Z":
                event["url_present"] = True
                event["event_url_safe_sha256"] = ADJACENT_OCCURRENCE_EVENT_URL_SHA256
    return result


def _recurring_update_adjacent_location_runner(
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    result = _recurring_update_runner(payload, timeout)
    if payload["command"] == "calendar_events":
        for event in result.get("events", []):
            if event.get("start_date") == "2026-06-10T17:00:00.000Z":
                event["location_present"] = True
                event["location_safe_sha256"] = ADJACENT_OCCURRENCE_LOCATION_SHA256
                event["structured_location_present"] = True
                event["structured_location_safe_sha256"] = (
                    ADJACENT_OCCURRENCE_STRUCTURED_LOCATION_SHA256
                )
    return result


def _recurring_update_adjacent_alarm_runner(
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    result = _recurring_update_runner(payload, timeout)
    if payload["command"] == "calendar_events":
        for event in result.get("events", []):
            if event.get("start_date") == "2026-06-10T17:00:00.000Z":
                event["alarms_count"] = 1
                event["alarm_state_present"] = True
                event["alarm_state_safe_sha256"] = ADJACENT_OCCURRENCE_ALARM_STATE_SHA256
    return result


def _recurring_future_delete_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        result = _runner(payload, timeout)
        first = result["events"][0]
        recurrence = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        first["recurrence_present"] = True
        first["recurrence"] = recurrence
        previous = {
            **first,
            "start_date": "2026-05-27T17:00:00.000Z",
            "end_date": "2026-05-27T18:00:00.000Z",
        }
        future = {
            **first,
            "start_date": "2026-06-10T17:00:00.000Z",
            "end_date": "2026-06-10T18:00:00.000Z",
        }
        result["events"] = [first, previous, future]
        return result
    if payload["command"] in {"calendar_event_by_id", "calendar_event_by_occurrence"}:
        result = _runner(payload, timeout)
        result["event"]["recurrence_present"] = True
        result["event"]["recurrence"] = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        return result
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "delete":
        if payload.get("recurrence_delete_scope") != "future_events":
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "unsupported_event_state",
                        "message": "Calendar event has unsupported recurrence state.",
                    }
                ],
            }
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            if payload.get(field) != expected:
                return {
                    "schema_version": 1,
                    "status": "apply_unknown",
                    "source": "calendar",
                    "authorization_status": "authorized",
                    "warnings": [
                        {
                            "code": "read_back_unavailable",
                            "message": f"Calendar future delete proof field mismatch: {field}.",
                        }
                    ],
                }
        if payload.get("expected_recurrence_present") is not True:
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Calendar event did not match expected recurrence state.",
                    }
                ],
            }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {
                "deleted": True,
                "verified_absent": True,
                "selected_occurrence_verified_absent": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _runner(payload, timeout)


def _recurring_mid_series_clear_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload["clear_recurrence"] is True
        assert payload["recurrence_update_scope"] == "future_events"
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == recurrence
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": {
                    "frequency": "",
                    "interval": 0,
                    "count": 0,
                    "recurrence_present": False,
                },
                "recurrence_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "recurrence_cleared_verified": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_mid_series_replace_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        requested_recurrence = payload.get("recurrence") or {}
        replacement_recurrence = (
            {
                "frequency": "daily",
                "interval": 1,
                "count": 0,
                "unbounded": True,
                "recurrence_present": True,
            }
            if requested_recurrence.get("unbounded")
            else {
                "frequency": "daily",
                "interval": 1,
                "count": 4,
                "recurrence_present": True,
            }
        )
        assert payload.get("clear_recurrence") is not True
        assert payload["recurrence_update_scope"] == "future_events"
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["recurrence"] == replacement_recurrence
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": replacement_recurrence,
                "recurrence_present": True,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "recurrence_replaced_verified": True,
                "future_occurrence_verified_present": True,
                "previous_occurrence_verified_present": True,
                "future_original_slot_verified_replaced_or_absent": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_scalar_update_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_scalar_update_requested") is True
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["title"] == "Synthetic future series event"
        assert payload["location"] == "Future Room"
        assert payload["notes"] == "Future series notes."
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": "",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": current_recurrence,
                "recurrence_present": True,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "future_series_scalar_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_reschedule_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_reschedule_requested") is True
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        future_slot_collision = payload["start_date"] == "2026-06-10T17:00:00Z"
        assert payload["expected_time_zone"] == "America/Los_Angeles"
        assert payload["time_zone"] == (
            "America/Los_Angeles" if future_slot_collision else "America/New_York"
        )
        if future_slot_collision:
            assert payload["end_date"] == "2026-06-10T18:00:00Z"
        else:
            assert payload["start_date"] == "2026-06-03T19:00:00Z"
            assert payload["end_date"] == "2026-06-03T20:00:00Z"
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": payload["time_zone"],
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": current_recurrence,
                "recurrence_present": True,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "future_series_rescheduled_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                **(
                    {
                        "original_occurrence_verified_absent_or_replaced": True,
                        "future_original_occurrence_verified_absent_or_replaced": True,
                    }
                    if future_slot_collision
                    else {
                        "original_occurrence_verified_absent": True,
                        "future_original_occurrence_verified_absent": True,
                    }
                ),
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_availability_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_availability_update_requested") is True
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload.get("future_series_reschedule_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["expected_availability"] == 0
        assert payload["availability"] == 1
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": "",
                "all_day": False,
                "availability": payload["availability"],
                "availability_name": "free",
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": current_recurrence,
                "recurrence_present": True,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "future_series_availability_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_availability_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_availability_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_availability_updated_verified", None)
    return result


def _recurring_future_series_event_url_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_event_url_update_requested") is True
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload.get("future_series_reschedule_requested") is False
        assert payload.get("future_series_availability_update_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        expected_event_url = "https://meet.example.invalid/current-future-series"
        expected_sha = hashlib.sha256(expected_event_url.encode("utf-8")).hexdigest()
        event_url = "https://meet.example.invalid/new-future-series"
        event_url_sha = hashlib.sha256(event_url.encode("utf-8")).hexdigest()
        clear_requested = payload.get("event_url_clear_requested") is True
        if clear_requested:
            assert payload["expected_event_url_present"] is True
            assert payload["expected_event_url_sha256"] == expected_sha
            assert payload.get("event_url") == ""
        else:
            assert payload["event_url_requested"] is True
            assert payload["event_url"] == event_url
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        event = {
            "event_id": payload["event_id"],
            "title": payload["title"],
            "calendar_id": "calendar-1",
            "calendar_title": "Synthetic Calendar",
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "time_zone": "",
            "all_day": False,
            "availability": 0,
            "availability_name": "busy",
            "location_present": True,
            "notes_present": True,
            "url_present": not clear_requested,
            "alarm_offsets_minutes": [],
            "alarm_absolute_dates": [],
            "recurrence": current_recurrence,
            "recurrence_present": True,
            "alarms_count": 0,
            "attendees_count": 0,
        }
        if not clear_requested:
            event["event_url_safe_sha256"] = event_url_sha
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": event,
            "read_back": {
                "future_series_event_url_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_event_url_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_event_url_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_event_url_updated_verified", None)
    return result


def _recurring_future_series_structured_location_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_structured_location_update_requested") is True
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload.get("future_series_reschedule_requested") is False
        assert payload.get("future_series_availability_update_requested") is False
        assert payload.get("future_series_event_url_update_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        clear_requested = payload.get("structured_location_clear_requested") is True
        if clear_requested:
            assert payload["expected_structured_location_present"] is True
            assert payload["expected_structured_location"] == {
                "title": "Synthetic Current Room",
                "geo_present": False,
            }
            assert payload["location"] == ""
        else:
            assert payload["structured_location"] == {
                "title": "Future Conference Room",
                "geo_present": True,
                "latitude": 37.7749,
                "longitude": -122.4194,
                "radius_meters": 25.0,
            }
            assert payload["location"] == "Future Conference Room"
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        event = {
            "event_id": payload["event_id"],
            "title": payload["title"],
            "calendar_id": "calendar-1",
            "calendar_title": "Synthetic Calendar",
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "time_zone": "",
            "all_day": False,
            "availability": 0,
            "availability_name": "busy",
            "notes_present": True,
            "url_present": False,
            "alarm_offsets_minutes": [],
            "alarm_absolute_dates": [],
            "recurrence": current_recurrence,
            "recurrence_present": True,
            "alarms_count": 0,
            "attendees_count": 0,
        }
        if clear_requested:
            event.update(
                {
                    "location_present": False,
                    "structured_location_present": False,
                }
            )
        else:
            event.update(
                {
                    "location_present": True,
                    "structured_location": payload["structured_location"],
                    "structured_location_present": True,
                }
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": event,
            "read_back": {
                "future_series_structured_location_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_structured_location_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_structured_location_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_structured_location_updated_verified", None)
    return result


def _recurring_future_series_display_alarm_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_display_alarm_update_requested") is True
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload.get("future_series_reschedule_requested") is False
        assert payload.get("future_series_availability_update_requested") is False
        assert payload.get("future_series_event_url_update_requested") is False
        assert payload.get("future_series_structured_location_update_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["alarm_absolute_dates"] == []
        assert payload["expected_alarm_absolute_dates"] == []
        clear_requested = payload["alarm_offsets_minutes"] == []
        if clear_requested:
            assert payload["expected_alarm_offsets_minutes"] == [-10]
        else:
            assert payload["alarm_offsets_minutes"] == [-10]
            assert payload["expected_alarm_offsets_minutes"] == []
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        event = {
            "event_id": payload["event_id"],
            "title": payload["title"],
            "calendar_id": "calendar-1",
            "calendar_title": "Synthetic Calendar",
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "time_zone": "",
            "all_day": False,
            "availability": 0,
            "availability_name": "busy",
            "notes_present": True,
            "url_present": False,
            "location_present": True,
            "structured_location_present": False,
            "alarm_absolute_dates": [],
            "recurrence": current_recurrence,
            "recurrence_present": True,
            "attendees_count": 0,
        }
        if clear_requested:
            event.update(
                {
                    "alarm_offsets_minutes": [],
                    "alarms_count": 0,
                }
            )
        else:
            event.update(
                {
                    "alarm_offsets_minutes": [-10],
                    "alarms_count": 1,
                }
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": event,
            "read_back": {
                "future_series_display_alarm_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_display_alarm_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_display_alarm_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_display_alarm_updated_verified", None)
    return result


def _recurring_future_series_action_alarm_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        assert payload.get("clear_recurrence") is not True
        assert payload.get("future_series_action_alarm_update_requested") is True
        assert payload.get("future_series_display_alarm_update_requested") is False
        assert payload.get("future_series_scalar_update_requested") is False
        assert payload.get("future_series_reschedule_requested") is False
        assert payload.get("future_series_availability_update_requested") is False
        assert payload.get("future_series_event_url_update_requested") is False
        assert payload.get("future_series_structured_location_update_requested") is False
        assert payload["recurrence_update_scope"] == "future_events"
        assert "recurrence" not in payload
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["alarm_absolute_dates"] == []
        assert payload["expected_alarm_absolute_dates"] == []
        assert payload.get("alarm_email_address", "") == ""
        assert payload.get("expected_alarm_email_address_sha256", "") == ""
        assert payload.get("alarm_proximity", "") == ""
        assert payload.get("expected_alarm_proximity", "") == ""
        clear_requested = payload["alarm_sound_name"] == ""
        if clear_requested:
            assert payload["expected_alarm_sound_name"] == "Glass"
            assert payload["expected_alarm_offsets_minutes"] == [-10]
            assert payload["alarm_offsets_minutes"] == []
        else:
            assert payload["alarm_sound_name"] == "Glass"
            assert payload["alarm_offsets_minutes"] == [-10]
            assert payload["expected_alarm_sound_name"] == ""
            assert payload["expected_alarm_offsets_minutes"] == []
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        event = {
            "event_id": payload["event_id"],
            "title": payload["title"],
            "calendar_id": "calendar-1",
            "calendar_title": "Synthetic Calendar",
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "time_zone": "",
            "all_day": False,
            "availability": 0,
            "availability_name": "busy",
            "notes_present": True,
            "url_present": False,
            "location_present": True,
            "structured_location_present": False,
            "alarm_absolute_dates": [],
            "recurrence": current_recurrence,
            "recurrence_present": True,
            "attendees_count": 0,
        }
        if clear_requested:
            event.update(
                {
                    "alarm_offsets_minutes": [],
                    "alarm_sound_name": "",
                    "alarms_count": 0,
                }
            )
        else:
            event.update(
                {
                    "alarm_offsets_minutes": [-10],
                    "alarm_sound_name": "Glass",
                    "alarms_count": 1,
                }
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": event,
            "read_back": {
                "future_series_action_alarm_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_action_alarm_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_action_alarm_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_action_alarm_updated_verified", None)
    return result


def _assert_future_series_all_day_flags(payload: dict[str, Any]) -> None:
    assert payload.get("clear_recurrence") is not True
    assert payload.get("future_series_all_day_update_requested") is True
    assert payload.get("future_series_action_alarm_update_requested") is False
    assert payload.get("future_series_display_alarm_update_requested") is False
    assert payload.get("future_series_scalar_update_requested") is False
    assert payload.get("future_series_reschedule_requested") is False
    assert payload.get("future_series_availability_update_requested") is False
    assert payload.get("future_series_event_url_update_requested") is False
    assert payload.get("future_series_structured_location_update_requested") is False
    assert payload["recurrence_update_scope"] == "future_events"
    assert "recurrence" not in payload
    assert payload["expected_recurrence_present"] is True


def _recurring_future_series_all_day_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        _assert_future_series_all_day_flags(payload)
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["all_day"] is True
        assert payload["expected_all_day"] is False
        assert payload["expected_time_zone"] == "America/Los_Angeles"
        assert payload["start_date"] == "2026-06-03"
        assert payload["end_date"] == "2026-06-04"
        assert payload.get("time_zone", "") == ""
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03",
                "end_date": "2026-06-04",
                "time_zone": "",
                "all_day": True,
                "availability": 0,
                "availability_name": "busy",
                "location_present": True,
                "structured_location_present": False,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "alarms_count": 0,
                "attendees_count": 0,
                "recurrence": current_recurrence,
                "recurrence_present": True,
            },
            "read_back": {
                "future_series_all_day_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent": True,
                "future_original_occurrence_verified_absent": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_all_day_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_all_day_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_all_day_updated_verified", None)
    return result


def _recurring_future_series_all_day_change_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    base_event = {
        "event_id": "all-day-recurring-event-1",
        "title": "Synthetic all day recurring event",
        "calendar_id": "calendar-1",
        "calendar_title": "Synthetic Calendar",
        "start_date": "2026-06-05",
        "end_date": "2026-06-06",
        "time_zone": "",
        "all_day": True,
        "availability": 0,
        "availability_name": "busy",
        "location_present": False,
        "structured_location_present": False,
        "notes_present": False,
        "url_present": False,
        "alarm_offsets_minutes": [],
        "alarm_absolute_dates": [],
        "alarms_count": 0,
        "attendees_count": 0,
        "recurrence_present": True,
        "recurrence": current_recurrence,
    }
    if payload["command"] == "calendar_events":
        previous = {**base_event, "start_date": "2026-05-29", "end_date": "2026-05-30"}
        future = {**base_event, "start_date": "2026-06-12", "end_date": "2026-06-13"}
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": [base_event, previous, future],
            "warnings": [],
        }
    if payload["command"] in {"calendar_event_by_id", "calendar_event_by_occurrence"}:
        returned = {
            **base_event,
            "start_date": payload.get("start_date") or base_event["start_date"],
            "end_date": payload.get("end_date") or base_event["end_date"],
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": returned,
            "warnings": [],
        }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        _assert_future_series_all_day_flags(payload)
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["expected_all_day"] is True
        clear_requested = payload["all_day"] is False
        if clear_requested:
            assert payload["start_date"] == "2026-06-05T17:00:00Z"
            assert payload["end_date"] == "2026-06-05T18:00:00Z"
            assert payload["time_zone"] == "America/Los_Angeles"
        else:
            assert payload["all_day"] is True
            assert payload["start_date"] == "2026-06-06"
            assert payload["end_date"] == "2026-06-07"
            assert payload.get("time_zone", "") == ""
        for field, expected in {
            "occurrence_start_date": "2026-06-05",
            "occurrence_end_date": "2026-06-06",
            "previous_occurrence_start_date": "2026-05-29",
            "previous_occurrence_end_date": "2026-05-30",
            "future_occurrence_start_date": "2026-06-12",
            "future_occurrence_end_date": "2026-06-13",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                **base_event,
                "title": payload["title"],
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": payload.get("time_zone") or "",
                "all_day": payload["all_day"],
            },
            "read_back": {
                "future_series_all_day_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent": True,
                "future_original_occurrence_verified_absent": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_all_day_dst_reschedule_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    # Same-state all-day date-only reschedule whose day shift crosses the
    # 2026-11-01 US DST fall-back boundary (2026-06-05 -> 2026-11-06). The
    # plan/apply/read-back contract must stay date-only end-to-end so the
    # Swift helper derives read-back slots from calendar-day arithmetic;
    # a payload carrying timestamps would make interval math possible.
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        _assert_future_series_all_day_flags(payload)
        assert payload["expected_all_day"] is True
        assert payload["all_day"] is True
        assert payload["start_date"] == "2026-11-06"
        assert payload["end_date"] == "2026-11-07"
        assert payload.get("time_zone", "") == ""
        for field, expected in {
            "expected_start_date": "2026-06-05",
            "expected_end_date": "2026-06-06",
            "occurrence_start_date": "2026-06-05",
            "occurrence_end_date": "2026-06-06",
            "previous_occurrence_start_date": "2026-05-29",
            "previous_occurrence_end_date": "2026-05-30",
            "future_occurrence_start_date": "2026-06-12",
            "future_occurrence_end_date": "2026-06-13",
        }.items():
            assert payload.get(field) == expected
        for field in (
            "start_date",
            "end_date",
            "expected_start_date",
            "expected_end_date",
            "occurrence_start_date",
            "occurrence_end_date",
            "previous_occurrence_start_date",
            "previous_occurrence_end_date",
            "future_occurrence_start_date",
            "future_occurrence_end_date",
        ):
            value = payload[field]
            assert "T" not in value and len(value) == 10, (
                f"all-day DST reschedule payload field {field} must stay date-only"
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-11-06",
                "end_date": "2026-11-07",
                "time_zone": "",
                "all_day": True,
                "availability": 0,
                "availability_name": "busy",
                "location_present": False,
                "structured_location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "alarms_count": 0,
                "attendees_count": 0,
                "recurrence_present": True,
                "recurrence": {
                    "frequency": "weekly",
                    "interval": 1,
                    "count": 6,
                    "recurrence_present": True,
                },
            },
            "read_back": {
                "future_series_all_day_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent": True,
                "future_original_occurrence_verified_absent": True,
            },
            "warnings": [],
        }
    return _recurring_future_series_all_day_change_runner(payload, timeout)


def _assert_future_series_calendar_move_flags(payload: dict[str, Any]) -> None:
    assert payload.get("clear_recurrence") is not True
    assert payload.get("future_series_calendar_move_requested") is True
    assert payload.get("future_series_all_day_update_requested") is False
    assert payload.get("future_series_action_alarm_update_requested") is False
    assert payload.get("future_series_display_alarm_update_requested") is False
    assert payload.get("future_series_scalar_update_requested") is False
    assert payload.get("future_series_reschedule_requested") is False
    assert payload.get("future_series_availability_update_requested") is False
    assert payload.get("future_series_event_url_update_requested") is False
    assert payload.get("future_series_structured_location_update_requested") is False
    assert payload["recurrence_update_scope"] == "future_events"
    assert "recurrence" not in payload
    assert payload["expected_recurrence_present"] is True


def _recurring_future_series_calendar_move_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    current_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        _assert_future_series_calendar_move_flags(payload)
        assert payload["expected_recurrence"] == current_recurrence
        assert payload["target_calendar_id"] == "calendar-2"
        assert payload["title"] == payload["expected_title"]
        assert payload["start_date"] == "2026-06-03T17:00:00Z"
        assert payload["end_date"] == "2026-06-03T18:00:00Z"
        assert payload["time_zone"] == "America/Los_Angeles"
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "previous_occurrence_start_date": "2026-05-27T17:00:00.000Z",
            "previous_occurrence_end_date": "2026-05-27T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            assert payload.get(field) == expected
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": payload["title"],
                "calendar_id": "calendar-2",
                "calendar_title": "Synthetic Focus",
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "time_zone": "America/Los_Angeles",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": True,
                "structured_location_present": False,
                "notes_present": True,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "alarms_count": 0,
                "attendees_count": 0,
                "recurrence": current_recurrence,
                "recurrence_present": True,
            },
            "read_back": {
                "future_series_calendar_move_verified": True,
                "previous_occurrence_calendar_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "warnings": [],
        }
    return _recurring_future_delete_runner(payload, timeout)


def _recurring_future_series_calendar_move_missing_proof_runner(
    payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result = _recurring_future_series_calendar_move_runner(payload, timeout)
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
        result["read_back"].pop("future_series_calendar_move_verified", None)
    return result


def _recurring_all_delete_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        result = _runner(payload, timeout)
        first = result["events"][0]
        recurrence = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        first["recurrence_present"] = True
        first["recurrence"] = recurrence
        future = {
            **first,
            "start_date": "2026-06-10T17:00:00.000Z",
            "end_date": "2026-06-10T18:00:00.000Z",
        }
        result["events"] = [first, future]
        return result
    if payload["command"] in {"calendar_event_by_id", "calendar_event_by_occurrence"}:
        result = _runner(payload, timeout)
        result["event"]["recurrence_present"] = True
        result["event"]["recurrence"] = {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        return result
    if payload["command"] == "calendar_apply_change" and payload["operation"] == "delete":
        if payload.get("recurrence_delete_scope") != "all_events":
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "unsupported_event_state",
                        "message": "Calendar event has unsupported recurrence state.",
                    }
                ],
            }
        for field, expected in {
            "occurrence_start_date": "2026-06-03T17:00:00.000Z",
            "occurrence_end_date": "2026-06-03T18:00:00.000Z",
            "future_occurrence_start_date": "2026-06-10T17:00:00.000Z",
            "future_occurrence_end_date": "2026-06-10T18:00:00.000Z",
        }.items():
            if payload.get(field) != expected:
                return {
                    "schema_version": 1,
                    "status": "apply_unknown",
                    "source": "calendar",
                    "authorization_status": "authorized",
                    "warnings": [
                        {
                            "code": "read_back_unavailable",
                            "message": f"Calendar whole-series delete proof field mismatch: {field}.",
                        }
                    ],
                }
        if payload.get("expected_recurrence_present") is not True:
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Calendar event did not match expected recurrence state.",
                    }
                ],
            }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {
                "deleted": True,
                "verified_absent": True,
                "selected_occurrence_verified_absent": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_absent": True,
            },
            "warnings": [],
        }
    return _runner(payload, timeout)


def _nonrecurring_scoped_delete_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    if (
        payload["command"] == "calendar_apply_change"
        and payload["operation"] == "delete"
        and payload.get("recurrence_delete_scope") == "this_event"
    ):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "calendar",
            "authorization_status": "authorized",
            "warnings": [
                {
                    "code": "expected_state_mismatch",
                    "message": "Calendar event did not match expected recurrence state.",
                }
            ],
        }
    return _runner(payload, timeout)


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
    assert "alarm_offsets_minutes" not in event
    assert "time_zone" not in event
    assert "event-1" not in str(event)
    assert "notes_text" not in event


def test_search_calendar_calendars_returns_metadata_only_and_default() -> None:
    result = search_calendar_calendars(
        "Focus",
        include_default=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["authorization_status"] == "authorized"
    assert result["query"]["scope"] == "calendar_title"
    assert result["result_count"] == 2
    titles = {calendar["title"] for calendar in result["results"]}
    assert titles == {"Synthetic Calendar", "Synthetic Focus"}
    focus = next(calendar for calendar in result["results"] if calendar["title"] == "Synthetic Focus")
    assert focus["handle"].startswith("calendar:calendar:v1:")
    assert focus["allows_content_modifications"] is True
    assert focus["supported_event_availabilities"] == ["busy", "free", "tentative"]
    assert "calendar-2" not in str(result)


def test_search_calendar_calendars_rejects_empty_and_broad_queries() -> None:
    empty = search_calendar_calendars(" ", eventkit_runner=_runner)
    broad = search_calendar_calendars("%", eventkit_runner=_runner)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_get_calendar_calendar_returns_exact_metadata() -> None:
    search = search_calendar_calendars("Focus", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = get_calendar_calendar(handle, eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["result"]["handle"] == handle
    assert result["result"]["title"] == "Synthetic Focus"
    assert "calendar-2" not in str(result)


def test_get_calendar_calendar_rejects_bad_handle() -> None:
    result = get_calendar_calendar("calendar-2", eventkit_runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_list_calendar_events_for_calendar_returns_metadata_only() -> None:
    calendar_handle = search_calendar_calendars("Focus", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = list_calendar_events_for_calendar(
        calendar_handle,
        start_date="2026-06-01T00:00:00Z",
        end_date="2026-07-01T00:00:00Z",
        limit=5,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["authorization_status"] == "authorized"
    assert result["query"]["scope"] == "selected_calendar_events"
    assert result["query"]["calendar_handle"] == calendar_handle
    assert result["calendar"]["handle"] == calendar_handle
    assert result["calendar"]["title"] == "Synthetic Focus"
    assert result["result_count"] == 1
    event = result["results"][0]
    assert event["handle"].startswith("calendar:event:v1:")
    assert event["title"] == "Synthetic focus event"
    assert event["calendar_title"] == "Synthetic Focus"
    assert event["location_present"] is True
    assert event["notes_present"] is True
    assert "location" not in event
    assert "notes" not in event
    assert "notes_text" not in event
    assert "event_url_safe_sha256" not in event
    assert "structured_location" not in event
    assert "structured_location_present" not in event
    assert "alarm_offsets_minutes" not in event
    assert "alarm_sound_name" not in event
    assert "event-focus-1" not in str(result)
    assert "calendar-2" not in str(result)
    assert "Must not return" not in str(result)


def test_list_calendar_events_for_calendar_rejects_bad_handle_and_window() -> None:
    invalid_handle = list_calendar_events_for_calendar(
        "calendar-2",
        start_date="2026-06-01T00:00:00Z",
        end_date="2026-07-01T00:00:00Z",
        eventkit_runner=_runner,
    )
    missing_start = list_calendar_events_for_calendar(
        make_opaque_handle("calendar:calendar", "calendar-2"),
        start_date="",
        end_date="2026-07-01T00:00:00Z",
        eventkit_runner=_runner,
    )
    reversed_window = list_calendar_events_for_calendar(
        make_opaque_handle("calendar:calendar", "calendar-2"),
        start_date="2026-07-01",
        end_date="2026-06-01",
        eventkit_runner=_runner,
    )
    huge_window = list_calendar_events_for_calendar(
        make_opaque_handle("calendar:calendar", "calendar-2"),
        start_date="2026-01-01",
        end_date="2027-12-31",
        eventkit_runner=_runner,
    )
    missing_typed_start = list_calendar_events_for_calendar(
        make_opaque_handle("calendar:calendar", "calendar-2"),
        start_date=None,  # type: ignore[arg-type]
        end_date="2026-07-01T00:00:00Z",
        eventkit_runner=_runner,
    )
    wrong_typed_start = list_calendar_events_for_calendar(
        make_opaque_handle("calendar:calendar", "calendar-2"),
        start_date=123,  # type: ignore[arg-type]
        end_date="2026-07-01T00:00:00Z",
        eventkit_runner=_runner,
    )

    assert invalid_handle["status"] == "error"
    assert invalid_handle["warnings"][0]["code"] == "invalid_handle"
    assert missing_start["warnings"][0]["code"] == "missing_required_field"
    assert reversed_window["warnings"][0]["code"] == "invalid_date_window"
    assert huge_window["warnings"][0]["code"] == "date_window_too_large"
    assert missing_typed_start["warnings"][0]["code"] == "missing_required_field"
    assert wrong_typed_start["warnings"][0]["code"] == "invalid_datetime"


def test_list_calendar_events_for_calendar_caps_helper_overrun() -> None:
    calendar_handle = make_opaque_handle("calendar:calendar", "calendar-2")

    def overrun_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] != "calendar_events_for_calendar":
            return _runner(payload, timeout)
        events = []
        for index in range(60):
            events.append(
                {
                    "event_id": f"raw-event-{index}",
                    "title": f"Synthetic focus event {index}",
                    "calendar_id": "calendar-2",
                    "calendar_title": "Synthetic Focus",
                    "start_date": f"2026-06-{index % 28 + 1:02d}T17:00:00.000Z",
                    "end_date": f"2026-06-{index % 28 + 1:02d}T18:00:00.000Z",
                    "all_day": False,
                    "availability": 0,
                    "location_present": False,
                    "notes_present": False,
                    "url_present": False,
                    "alarms_count": 0,
                    "attendees_count": 0,
                }
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": events,
            "truncated": False,
            "warnings": [],
        }

    result = list_calendar_events_for_calendar(
        calendar_handle,
        start_date="2026-06-01T00:00:00Z",
        end_date="2026-07-01T00:00:00Z",
        limit=5,
        eventkit_runner=overrun_runner,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 5
    assert result["truncated"] is True
    assert result["warnings"][-1]["code"] == "events_truncated"
    assert "raw-event-5" not in str(result)


def test_request_calendar_full_access_uses_eventkit_helper() -> None:
    recorded: dict[str, Any] = {}

    def request_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        recorded["payload"] = payload
        recorded["timeout"] = timeout
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "full_access",
            "request_result": "granted",
            "warnings": [],
        }

    result = request_calendar_full_access(eventkit_runner=request_runner)

    assert recorded["payload"] == {"command": "request_calendar_full_access"}
    assert recorded["timeout"] == 190.0
    assert result["status"] == "ok"
    assert result["authorization_status"] == "full_access"
    assert result["request_result"] == "granted"
    assert result["privacy"]["content_inspected"] is False


def test_request_calendar_full_access_returns_safe_error_on_helper_failure() -> None:
    def failed_runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise ValueError("raw helper path HOME/private/EventKitHelper.app failed")

    result = request_calendar_full_access(eventkit_runner=failed_runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "eventkit_unavailable"
    assert "HOME/private" not in str(result)


def test_request_calendar_full_access_returns_safe_timeout() -> None:
    def timeout_runner(_payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        raise subprocess.TimeoutExpired(["open"], timeout)

    result = request_calendar_full_access(eventkit_runner=timeout_runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "timeout"
    assert result["warnings"][0]["code"] == "calendar_access_request_timeout"


def test_request_calendar_full_access_provisions_before_prompt(monkeypatch) -> None:
    # With a mocked runner the prepare hook must NOT fire (it only runs on the
    # real eventkit_runner=None path), so patch it to fail loudly if invoked.
    monkeypatch.setattr(
        calendar_adapter,
        "_prepare_eventkit_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("prepare fired with a mocked runner")),
    )

    def _runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {"status": "ok", "authorization_status": "full_access", "warnings": []}

    result = request_calendar_full_access(eventkit_runner=_runner)

    assert result["status"] == "ok"


def test_prepare_eventkit_helper_signing_provisions_and_invalidates(monkeypatch) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setattr(
        calendar_adapter,
        "_provision_local_signing_identity",
        lambda: "Local Apple Data Signing",
    )

    def _invalidate(app_root, identity):
        calls["app_root"] = app_root
        calls["identity"] = identity
        return True

    monkeypatch.setattr(
        calendar_adapter._signing, "invalidate_app_if_signing_mismatch", _invalidate
    )

    calendar_adapter._prepare_eventkit_helper_signing()

    assert calls["identity"] == "Local Apple Data Signing"
    assert calls["app_root"] == calendar_adapter._eventkit_helper_app_root()


def test_calendar_read_path_never_provisions(monkeypatch) -> None:
    # Provisioning/prepare must never be reachable from a read path.
    monkeypatch.setattr(
        calendar_adapter,
        "_provision_local_signing_identity",
        lambda: (_ for _ in ()).throw(AssertionError("read path provisioned")),
    )
    monkeypatch.setattr(
        calendar_adapter,
        "_prepare_eventkit_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("read path prepared signing")),
    )

    result = search_calendar_events("meeting", eventkit_runner=_runner)

    assert result["status"] in {"ok", "degraded", "error"}


def test_check_calendar_authorization_is_non_prompting() -> None:
    recorded: dict[str, Any] = {}

    def status_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        recorded["payload"] = payload
        recorded["timeout"] = timeout
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "full_access",
            "warnings": [],
        }

    result = check_calendar_authorization(eventkit_runner=status_runner)

    assert recorded["payload"] == {"command": "calendar_authorization_status"}
    assert recorded["timeout"] == 10.0
    assert result["status"] == "ok"
    assert result["authorization_status"] == "full_access"
    assert result["prompts"] is False
    assert result["prompt_command"] == "local-apple-data calendar request-access --json"


def test_calendar_eventkit_helper_app_declares_calendar_usage_strings() -> None:
    plist = calendar_adapter._eventkit_helper_info_plist()

    assert plist["CFBundleIdentifier"] == calendar_adapter.EVENTKIT_HELPER_BUNDLE_ID
    # The generic default applies only when no operator bundle-id override is set
    # (an override such as a `.env.local`-pinned id legitimately changes this).
    import os as _os

    if not _os.environ.get("LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID"):
        assert plist["CFBundleIdentifier"] == "com.local-apple-data.eventkit-helper"
    assert "NSCalendarsFullAccessUsageDescription" in plist
    assert "NSCalendarsWriteOnlyAccessUsageDescription" in plist
    assert "NSRemindersFullAccessUsageDescription" in plist


def test_calendar_eventkit_helper_app_validation_checks_plist_digest_and_signature(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_root = tmp_path / "EventKitHelper.app"
    contents = app_root / "Contents"
    executable = contents / "MacOS" / "eventkit_helper"
    resources = contents / "Resources"
    resources.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    with (contents / "Info.plist").open("wb") as handle:
        import plistlib

        plistlib.dump(calendar_adapter._eventkit_helper_info_plist(), handle)
    with (resources / "entitlements.plist").open("wb") as handle:
        plistlib.dump(calendar_adapter._eventkit_helper_entitlements(), handle)
    (resources / "source.sha256").write_text("digest")
    monkeypatch.setattr(calendar_adapter.shutil, "which", lambda name: "/usr/bin/true")

    assert calendar_adapter._eventkit_helper_app_valid(app_root, "digest") is True

    (resources / "source.sha256").write_text("stale")

    assert calendar_adapter._eventkit_helper_app_valid(app_root, "digest") is False


def test_calendar_eventkit_helper_runner_hardening_source_guards() -> None:
    source = Path("src/local_apple_data/adapters/calendar.py").read_text(encoding="utf-8")
    signing_source = Path("src/local_apple_data/adapters/_signing.py").read_text(
        encoding="utf-8"
    )

    assert 'os.environ.get("LOCAL_APPLE_DATA_EVENTKIT_HELPER_APP")' not in source
    # Signed with the personal-information entitlements so the TCC prompt is
    # presented; the codesign argv now lives in the shared signing module (both
    # a stable-identity + hardened-runtime branch and an ad-hoc fallback).
    assert '"-s",' in signing_source and '"--deep",' in signing_source
    assert '"--options",' in signing_source and '"runtime",' in signing_source
    assert '"--entitlements"' in signing_source
    assert 'codesign, "--verify", "--deep", "--strict"' in source
    assert 'os.chmod(directory, 0o700)' in source
    assert 'os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600' in source
    assert "completed.returncode != 0 or not output_path.exists()" not in source


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
    assert result["result"]["time_zone"] == "America/Los_Angeles"
    assert result["result"]["location"] == "Synthetic Room"
    assert result["result"]["notes_text"] == "Synthetic event notes."
    assert result["result"]["notes_chars"] == len("Synthetic event notes.")
    assert "event-1" not in str(result)


def test_get_calendar_event_returns_url_hash_proof_without_raw_url() -> None:
    url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(url.encode("utf-8")).hexdigest()

    def url_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] in {"calendar_event_by_id", "calendar_event_by_occurrence"}:
            response["event"] = {
                **response["event"],
                "url_present": True,
                "event_url_safe_sha256": expected_sha,
            }
        return response

    search = search_calendar_events("planning", eventkit_runner=url_runner)
    handle = search["results"][0]["handle"]

    result = get_calendar_event(handle, eventkit_runner=url_runner)

    assert result["status"] == "ok"
    assert result["result"]["url_present"] is True
    assert result["result"]["event_url_safe_sha256"] == expected_sha
    assert url not in str(result)
    assert "event_url" not in result["result"]


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


def test_list_calendar_participants_returns_metadata_handles_without_detail() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = list_calendar_participants(handle, eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["privacy"]["name_returned"] is False
    assert result["privacy"]["url_returned"] is False
    assert result["result_count"] == 2
    first = result["results"][0]
    assert first["handle"].startswith("calendar:participant:v1:")
    assert first["event_handle"] == handle
    assert first["participant_status_name"] == "accepted"
    assert first["participant_role_name"] == "required"
    assert first["participant_type_name"] == "person"
    assert first["name_present"] is True
    assert first["url_present"] is True
    assert "name" not in first
    assert "url" not in first
    assert "invitee@example.invalid" not in str(result)


def test_list_calendar_participants_uses_participant_only_helper() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(dict(payload))
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]

    result = list_calendar_participants(handle, eventkit_runner=recording_runner)

    commands = [call["command"] for call in calls]
    assert result["status"] == "ok"
    assert "calendar_event_participants_by_occurrence" in commands
    assert "calendar_event_by_occurrence" not in commands
    assert "Synthetic event notes" not in str(result)
    assert "Synthetic Room" not in str(result)


def test_get_calendar_participant_returns_exact_selected_detail() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    event_handle = search["results"][0]["handle"]
    participants = list_calendar_participants(event_handle, eventkit_runner=_runner)
    participant_handle = participants["results"][1]["handle"]

    result = get_calendar_participant(
        event_handle,
        participant_handle,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "detail"
    assert result["privacy"]["name_returned"] is True
    assert result["privacy"]["url_returned"] is True
    assert result["result"]["handle"] == participant_handle
    assert result["result"]["participant_kind"] == "organizer"
    assert result["result"]["organizer"] is True
    assert result["result"]["current_user"] is True
    assert result["result"]["name"] == "Synthetic Organizer"
    assert result["result"]["url"] == "mailto:organizer@example.invalid"


def test_list_calendar_participants_resolves_beyond_first_fifty_events() -> None:
    def many_events_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            events = [
                {
                    "event_id": f"event-{index}",
                    "title": "Target planning event" if index == 60 else f"Noise {index}",
                    "calendar_id": "calendar-1",
                    "calendar_title": "Synthetic Calendar",
                    "start_date": f"2026-06-{(index % 28) + 1:02d}T17:00:00.000Z",
                    "end_date": f"2026-06-{(index % 28) + 1:02d}T18:00:00.000Z",
                    "all_day": False,
                    "availability": 0,
                    "location_present": False,
                    "notes_present": False,
                    "url_present": False,
                    "alarms_count": 0,
                    "attendees_count": 1,
                }
                for index in range(1, 61)
            ]
            query = str(payload.get("query") or "").lower()
            if query:
                events = [event for event in events if query in event["title"].lower()]
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "events": events[: int(payload.get("limit") or 20)],
                "warnings": [],
            }
        if payload["command"] == "calendar_event_participants_by_occurrence":
            assert payload["event_id"] == "event-60"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "event": {
                    "event_id": "event-60",
                    "start_date": payload["start_date"],
                    "end_date": payload["end_date"],
                    "participants": [
                        {
                            "index": 0,
                            "participant_kind": "attendee",
                            "organizer": False,
                            "name": "Late Invitee",
                            "url": "mailto:late@example.invalid",
                            "participant_status": 2,
                            "participant_status_name": "accepted",
                            "participant_role": 1,
                            "participant_role_name": "required",
                            "participant_type": 1,
                            "participant_type_name": "person",
                            "current_user": False,
                        }
                    ],
                },
                "warnings": [],
            }
        raise AssertionError(f"unexpected command {payload['command']}")

    search = search_calendar_events("target", eventkit_runner=many_events_runner)
    event_handle = search["results"][0]["handle"]

    result = list_calendar_participants(event_handle, eventkit_runner=many_events_runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("calendar:participant:v1:")


def test_get_calendar_participant_rejects_wrong_event_pair() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    event_handle = search["results"][0]["handle"]
    participants = list_calendar_participants(event_handle, eventkit_runner=_runner)
    participant_handle = participants["results"][0]["handle"]
    wrong_event_handle = make_opaque_handle(
        "calendar:event",
        "event-2",
        "2026-06-04T17:00:00.000Z",
        "2026-06-04T18:00:00.000Z",
    )

    def wrong_event_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "events": [
                    {
                        "event_id": "event-2",
                        "title": "Other event",
                        "calendar_id": "calendar-1",
                        "calendar_title": "Synthetic Calendar",
                        "start_date": "2026-06-04T17:00:00.000Z",
                        "end_date": "2026-06-04T18:00:00.000Z",
                        "all_day": False,
                        "availability": 0,
                        "location_present": False,
                        "notes_present": False,
                        "url_present": False,
                        "alarms_count": 0,
                        "attendees_count": 1,
                    }
                ],
                "warnings": [],
            }
        if payload["command"] == "calendar_event_participants_by_occurrence":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "event": {
                    "event_id": "event-2",
                    "start_date": "2026-06-04T17:00:00.000Z",
                    "end_date": "2026-06-04T18:00:00.000Z",
                    "participants": [
                        {
                            "index": 0,
                            "participant_kind": "attendee",
                            "organizer": False,
                            "name": "Synthetic Invitee",
                            "url": "mailto:invitee@example.invalid",
                            "participant_status": 2,
                            "participant_status_name": "accepted",
                            "participant_role": 1,
                            "participant_role_name": "required",
                            "participant_type": 1,
                            "participant_type_name": "person",
                            "current_user": False,
                        }
                    ],
                },
                "warnings": [],
            }
        raise AssertionError(f"unexpected command {payload['command']}")

    result = get_calendar_participant(
        wrong_event_handle,
        participant_handle,
        eventkit_runner=wrong_event_runner,
    )

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_calendar_participant_rejects_bad_participant_handle() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    event_handle = search["results"][0]["handle"]

    result = get_calendar_participant(
        event_handle,
        "calendar:participant:raw",
        eventkit_runner=_runner,
    )

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


def _calendar_update_plan(handle: str) -> dict[str, Any]:
    return plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )


def _calendar_delete_plan(handle: str) -> dict[str, Any]:
    return plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
    )


def _all_day_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": [
                {
                    "event_id": "all-day-event-1",
                    "title": "Synthetic all day event",
                    "calendar_title": "Synthetic Calendar",
                    "start_date": "2026-06-05",
                    "end_date": "2026-06-06",
                    "all_day": True,
                    "availability": int(payload.get("availability", 0)),
                    "availability_name": {
                        0: "busy",
                        1: "free",
                        2: "tentative",
                        3: "unavailable",
                    }[int(payload.get("availability", 0))],
                    "location_present": False,
                    "notes_present": False,
                    "url_present": False,
                    "alarms_count": 0,
                    "attendees_count": 0,
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "calendar_apply_change":
        if payload["operation"] == "delete":
            assert payload["expected_all_day"] is True
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "deleted": True,
                "read_back": {"deleted": True, "verified_absent": True},
                "warnings": [],
            }
        assert payload["expected_all_day"] is True
        assert payload["all_day"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": "all-day-event-1",
                "title": payload["title"],
                "calendar_title": payload["expected_calendar_title"],
                "start_date": _fake_event_date(payload["start_date"], True),
                "end_date": _fake_event_date(payload["end_date"], True),
                "all_day": True,
                "availability": int(payload.get("availability", 0)),
                "availability_name": {
                    0: "busy",
                    1: "free",
                    2: "tentative",
                    3: "unavailable",
                }[int(payload.get("availability", 0))],
                "location_present": bool(payload.get("location")),
                "notes_present": bool(payload.get("notes")),
                "url_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "warnings": [],
        }
    raise AssertionError(payload)


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


def test_plan_calendar_change_create_all_day_binds_preview() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["all_day"] is True


def test_plan_calendar_change_create_availability_binds_preview_and_token() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="busy",
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["availability"] == 1
    assert base["preview"]["proposed"]["availability_name"] == "free"
    assert base["preview"]["proposed"]["availability_requested"] is True
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_structured_location_binds_preview_and_token() -> None:
    structured = {
        "title": "Synthetic Structured Room",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25,
    }
    changed = {**structured, "radius_meters": 30}
    base = plan_calendar_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        structured_location=structured,
    )
    changed_plan = plan_calendar_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        structured_location=changed,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["location"] == "Synthetic Structured Room"
    assert base["preview"]["proposed"]["structured_location"] == {
        "title": "Synthetic Structured Room",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25.0,
    }
    assert base["preview"]["proposed"]["structured_location_requested"] is True
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed_plan["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_rejects_invalid_structured_location() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        structured_location={"title": "Synthetic", "latitude": 91, "longitude": 0},
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_structured_location"


def test_plan_calendar_change_clear_structured_location_binds_expected_state() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_structured = {"title": "Synthetic Room"}
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={
            **expected_structured,
            "latitude": 37.33182,
            "longitude": -122.03118,
            "radius_meters": 10,
        },
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )

    assert base["status"] == "ok"
    assert base["preview"]["target"]["expected_state"]["structured_location"] == {
        "title": "Synthetic Room",
        "geo_present": False,
    }
    assert base["preview"]["target"]["expected_state"]["structured_location_expected"] is True
    assert base["preview"]["proposed"]["structured_location"] == {}
    assert base["preview"]["proposed"]["structured_location_requested"] is False
    assert base["preview"]["proposed"]["structured_location_clear_requested"] is True
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_clear_structured_location_rejects_unsafe_shapes() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    common = {
        "handle": handle,
        "expected_title": "Synthetic planning event",
        "expected_calendar_title": "Synthetic Calendar",
        "expected_start_date": "2026-06-03T17:00:00Z",
        "expected_end_date": "2026-06-03T18:00:00Z",
        "title": "Synthetic planning event",
        "start_date": "2026-06-03T17:00:00Z",
        "end_date": "2026-06-03T18:00:00Z",
        "clear_structured_location": True,
    }

    missing_expected = plan_calendar_change("update", **common)
    with_location = plan_calendar_change(
        "update",
        **common,
        expected_structured_location={"title": "Synthetic Room"},
        location="Synthetic Room",
    )
    with_structured = plan_calendar_change(
        "update",
        **common,
        expected_structured_location={"title": "Synthetic Room"},
        structured_location={"title": "Synthetic Room"},
    )
    create_result = plan_calendar_change(
        "create",
        title="Synthetic planning event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )

    assert missing_expected["status"] == "error"
    assert missing_expected["warnings"][0]["code"] == "missing_required_field"
    assert with_location["status"] == "error"
    assert with_location["warnings"][0]["code"] == "conflicting_location_fields"
    assert with_structured["status"] == "error"
    assert with_structured["warnings"][0]["code"] == "conflicting_structured_location_fields"
    assert create_result["status"] == "error"
    assert create_result["warnings"][0]["code"] == "unsupported_structured_location_for_operation"


def test_plan_calendar_change_create_event_url_binds_preview_and_token() -> None:
    url = "https://meet.example.invalid/runtime?id=42"
    changed_url = "https://meet.example.invalid/runtime?id=43"
    base = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=url,
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=changed_url,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["event_url_requested"] is True
    assert base["preview"]["proposed"]["event_url_scheme"] == "https"
    assert base["preview"]["proposed"]["event_url_domain"] == "meet.example.invalid"
    assert base["preview"]["proposed"]["event_url_safe_sha256"] == hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()
    assert base["preview"]["proposed"]["url_present"] is True
    assert "event_url" not in base["preview"]["proposed"]
    assert url not in json.dumps(base, sort_keys=True)
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_http_event_url_binds_preview_and_token() -> None:
    url = "http://meet.example.invalid/runtime?id=42"
    result = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=url,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["event_url_requested"] is True
    assert result["preview"]["proposed"]["event_url_scheme"] == "http"
    assert result["preview"]["proposed"]["event_url_domain"] == "meet.example.invalid"
    assert result["preview"]["proposed"]["event_url_safe_sha256"] == hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()
    assert "event_url" not in result["preview"]["proposed"]
    assert url not in json.dumps(result, sort_keys=True)


def test_plan_calendar_change_create_safe_non_http_event_urls() -> None:
    mailto_url = "mailto:calendar-link@example.invalid"
    tel_url = "tel:+15551234567;ext=89"
    mailto = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=mailto_url,
    )
    tel = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=tel_url,
    )

    assert mailto["status"] == "ok"
    assert mailto["preview"]["proposed"]["event_url_scheme"] == "mailto"
    assert mailto["preview"]["proposed"]["event_url_domain"] == ""
    assert mailto["preview"]["proposed"]["event_url_safe_sha256"] == hashlib.sha256(
        mailto_url.encode("utf-8")
    ).hexdigest()
    assert "event_url" not in mailto["preview"]["proposed"]
    assert mailto_url not in json.dumps(mailto, sort_keys=True)
    assert tel["status"] == "ok"
    assert tel["preview"]["proposed"]["event_url_scheme"] == "tel"
    assert tel["preview"]["proposed"]["event_url_domain"] == ""
    assert tel["preview"]["proposed"]["event_url_safe_sha256"] == hashlib.sha256(
        tel_url.encode("utf-8")
    ).hexdigest()
    assert "event_url" not in tel["preview"]["proposed"]
    assert tel_url not in json.dumps(tel, sort_keys=True)


def test_plan_calendar_change_rejects_invalid_event_urls() -> None:
    for bad_url in (
        "ftp://meet.example.invalid/runtime",
        "file:///tmp/runtime.ics",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "mailto:person@example.invalid?subject=secret",
        "mailto:person",
        "tel:",
        "tel:+15551234567?body=secret",
        "tel:+15551234567;phone-context=secret",
        "https://user:secret@meet.example.invalid/runtime",
        "https://user@meet.example.invalid/runtime",
        "https://@meet.example.invalid/runtime",
        "https://[::1",
        "https://[zzzz]/runtime",
        "https://meet.example.invalid:abc/runtime",
        "https://meet.example.invalid:99999/runtime",
        " https://meet.example.invalid/runtime",
        "https://meet.example.invalid/runtime ",
        "https://meet.example.invalid/has space",
        "https://meet.example.invalid/runtime\x00bad",
    ):
        result = plan_calendar_change(
            "create",
            title="Synthetic URL event",
            calendar_title="Synthetic Calendar",
            start_date="2026-06-05T17:00:00Z",
            end_date="2026-06-05T18:00:00Z",
            event_url=bad_url,
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_event_url"


def test_plan_calendar_change_create_rejects_expected_event_url_state() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256="a" * 64,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_expected_state_for_operation"


def test_plan_calendar_change_delete_rejects_event_url_input() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        event_url="https://meet.example.invalid/runtime?id=42",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_event_url_for_operation"


def test_plan_calendar_change_create_date_only_infers_all_day() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["start_date"] == "2026-06-05"
    assert result["preview"]["proposed"]["end_date"] == "2026-06-06"
    assert result["preview"]["proposed"]["all_day"] is True
    assert result["preview"]["proposed"]["date_only_input"] is True


def test_plan_calendar_change_rejects_mixed_date_only_and_timestamp() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic mixed date event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06T18:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "mixed_date_only_datetime"


def test_plan_calendar_change_rejects_time_zone_for_inferred_date_only_all_day() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
        time_zone="America/Los_Angeles",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_time_zone_for_all_day"


def test_plan_calendar_change_create_alarm_offsets_binds_preview() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[0, -10, -10],
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    assert result["preview"]["proposed"]["alarms_count"] == 2


def test_plan_calendar_change_create_absolute_alarms_binds_preview() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic absolute alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_absolute_dates=["2026-06-05T16:45:00Z", "2026-06-05T16:45:00+00:00"],
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["alarm_kind"] == "absolute"
    assert result["preview"]["proposed"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
    assert result["preview"]["proposed"]["alarms_count"] == 1


def test_plan_calendar_change_create_audio_alarm_binds_sound_name() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["alarm_offsets_minutes"] == [-10]
    assert result["preview"]["proposed"]["alarm_sound_name"] == "Glass"
    assert result["preview"]["proposed"]["alarm_action"] == "audio"


def test_plan_calendar_change_create_email_alarm_hashes_without_echo() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="Notify@Example.Invalid",
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="other@example.invalid",
    )

    expected_sha = hashlib.sha256(b"notify@example.invalid").hexdigest()
    serialized = json.dumps(result, sort_keys=True)
    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert result["preview"]["proposed"]["alarm_action"] == "email"
    assert result["preview"]["proposed"]["alarm_kind"] == "email_relative"
    assert "notify@example.invalid" not in serialized
    assert "Notify@Example.Invalid" not in serialized
    assert (
        result["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_geofence_alarm_binds_location() -> None:
    location = {
        "title": "Synthetic Gate",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75,
    }
    result = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
    )

    assert result["status"] == "ok"
    proposed = result["preview"]["proposed"]
    assert proposed["alarm_kind"] == "geofence"
    assert proposed["alarm_action"] == "geofence"
    assert proposed["alarm_proximity"] == "enter"
    assert proposed["alarm_structured_location"] == {
        "title": "Synthetic Gate",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75.0,
    }
    assert proposed["alarms_count"] == 1


def test_plan_calendar_change_geofence_alarm_binds_approval_identity() -> None:
    location = {
        "title": "Synthetic Gate",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75,
    }
    base = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
    )
    changed_proximity = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="leave",
        alarm_structured_location=location,
    )
    changed_radius = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location={**location, "radius_meters": 100},
    )

    assert base["status"] == "ok"
    assert changed_proximity["status"] == "ok"
    assert changed_radius["status"] == "ok"
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed_proximity["preview"]["approval"]["approval_fingerprint"]
    )
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed_radius["preview"]["approval"]["approval_fingerprint"]
    )
    assert base["preview"]["idempotency_key"] != changed_proximity["preview"]["idempotency_key"]
    assert base["preview"]["idempotency_key"] != changed_radius["preview"]["idempotency_key"]


def test_plan_calendar_change_rejects_audio_alarm_without_trigger() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_sound_name="Glass",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_alarm_trigger"


def test_plan_calendar_change_rejects_email_alarm_without_trigger() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_email_address="notify@example.invalid",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_alarm_trigger"


def test_plan_calendar_change_rejects_email_alarm_conflicts() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="notify@example.invalid",
        alarm_sound_name="Glass",
    )
    geofence_result = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="notify@example.invalid",
        alarm_proximity="enter",
        alarm_structured_location={"title": "Synthetic Gate"},
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "conflicting_alarm_fields"
    assert geofence_result["status"] == "error"
    assert geofence_result["warnings"][0]["code"] == "conflicting_alarm_fields"


def test_plan_calendar_change_rejects_invalid_email_alarm_address() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="not an address",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_alarm_email_address"


def test_plan_calendar_change_rejects_expected_email_alarm_without_trigger() -> None:
    result = plan_calendar_change(
        "delete",
        handle=make_opaque_handle("calendar:event", "event-1"),
        expected_title="Synthetic email alarm event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_alarm_email_address_sha256=hashlib.sha256(
            b"notify@example.invalid"
        ).hexdigest(),
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_alarm_trigger"


def test_plan_calendar_change_rejects_geofence_alarm_without_location() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="leave",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_alarm_structured_location"


def test_plan_calendar_change_rejects_geofence_alarm_with_time_alarm() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_proximity="enter",
        alarm_structured_location={"title": "Synthetic Gate"},
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "conflicting_alarm_fields"


def test_plan_calendar_change_create_recurrence_binds_preview_and_token() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=5,
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=6,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence_present"] is True
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_recurrence_end_date_binds_preview_and_token() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date="2026-08-01T17:00:00Z",
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date="2026-09-01T17:00:00Z",
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence_present"] is True
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": "2026-08-01T17:00:00Z",
        "recurrence_present": True,
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_unbounded_recurrence_binds_preview_and_token() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_unbounded=True,
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_unbounded=True,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence_present"] is True
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_all_day_recurrence_end_date_uses_bounded_compare() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic all-day end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_end_date="2026-06-20T00:00:00Z",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["all_day"] is True
    assert result["preview"]["proposed"]["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 0,
        "end_date": "2026-06-20T00:00:00Z",
        "recurrence_present": True,
    }


def test_plan_calendar_change_create_monthly_recurrence_binds_preview() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic monthly recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
    }


def test_plan_calendar_change_create_monthly_recurrence_month_days_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic monthly recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_month_days=[15, 1, -1, 15],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic monthly recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_month_days=[1],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "month_days": [-1, 1, 15],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_monthly_weekday_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["friday", "monday", "2"],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["monday"],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_monthly_nth_weekday_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic monthly nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_month_weekdays=[
            {"weekday": "tuesday", "week_number": 3},
            {"weekday": "friday", "week_number": -1},
            {"weekday": "fri", "week_number": -1},
        ],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic monthly nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_month_weekdays=[{"weekday": "tuesday", "week_number": 3}],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "tuesday", "week_number": 3},
        ],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_yearly_month_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic yearly month event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[12, 1, 7, 1],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic yearly month event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[1],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_yearly_month_day_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[12, 1, 7, 1],
        recurrence_year_month_days=[15, 1, -1, 15],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[12, 1, 7, 1],
        recurrence_year_month_days=[1],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_days": [-1, 1, 15],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_yearly_month_nth_weekday_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[12, 1, 7, 1],
        recurrence_year_month_weekdays=[
            {"weekday": "monday", "week_number": 2},
            {"weekday": "friday", "week_number": -1},
            {"weekday": "fri", "week_number": -1},
        ],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_months=[12, 1, 7, 1],
        recurrence_year_month_weekdays=[{"weekday": "monday", "week_number": 2}],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "monday", "week_number": 2},
        ],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_yearly_day_and_week_recurrence_binds_preview() -> None:
    day_plan = plan_calendar_change(
        "create",
        title="Synthetic yearly day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_days=[100, 1, -1, 100],
    )
    week_plan = plan_calendar_change(
        "create",
        title="Synthetic yearly week event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["monday"],
        recurrence_year_weeks=[26, 1, -1, 26],
    )

    assert day_plan["status"] == "ok"
    assert day_plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "year_days": [-1, 1, 100],
    }
    assert week_plan["status"] == "ok"
    assert week_plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "weekdays": ["monday"],
        "year_weeks": [-1, 1, 26],
    }
    assert (
        day_plan["preview"]["approval"]["approval_fingerprint"]
        != week_plan["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_yearly_week_recurrence_requires_weekdays() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic yearly week event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_year_weeks=[26],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_recurrence"
    assert "requires recurrence_weekdays" in result["warnings"][0]["message"]


def test_plan_calendar_change_create_weekly_recurrence_weekdays_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["friday", "monday", "2"],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["monday"],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_create_set_positions_recurrence_binds_preview() -> None:
    base = plan_calendar_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["monday", "tuesday", "wednesday", "thursday", "friday"],
        recurrence_set_positions=[-1, 1, -1],
    )
    changed = plan_calendar_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_weekdays=["monday", "tuesday", "wednesday", "thursday", "friday"],
        recurrence_set_positions=[1],
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 5,
        "recurrence_present": True,
        "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "set_positions": [-1, 1],
    }
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_rejects_unsupported_recurrence_shapes() -> None:
    cases = [
        {"recurrence_interval": 0},
        {"recurrence_count": 0},
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_end_date": "2026-08-01T17:00:00Z",
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_unbounded": True,
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_end_date": "2026-08-01T17:00:00Z",
            "recurrence_unbounded": True,
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_end_date": "2026-08-01",
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_end_date": "2026-06-05T17:00:00Z",
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_end_date": "2037-06-05T17:00:00Z",
        },
        {"recurrence_frequency": "hourly", "recurrence_interval": 1, "recurrence_count": 5},
        {"recurrence_frequency": "daily", "recurrence_interval": 0, "recurrence_count": 5},
        {"recurrence_frequency": "daily", "recurrence_interval": 5, "recurrence_count": 5},
        {"recurrence_frequency": "daily", "recurrence_interval": 1, "recurrence_count": 1},
        {"recurrence_frequency": "daily", "recurrence_interval": 1, "recurrence_count": 53},
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
        },
        {
            "recurrence_frequency": "weekly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["noday"],
        },
        {
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [1],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [0],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [32],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [-32],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": ["1"],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [True],
        },
        {
            "recurrence_frequency": "weekly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_weekdays": [{"weekday": "noday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": 0}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": 6}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": True}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_month_days": [1],
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
            "recurrence_month_days": [1],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
            "recurrence_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_month_days": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [0],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [32],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [-32],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [True],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": ["1"],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_weekdays": [{"weekday": "noday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_weekdays": [{"weekday": "monday", "week_number": 0}],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [0],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [13],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [True],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": ["1"],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [0],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [367],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [-367],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [True],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_weeks": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_weeks": [0],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_weeks": [54],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_weeks": [-54],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_weeks": [True],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_days": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [1],
            "recurrence_year_month_weekdays": [{"weekday": "monday", "week_number": 1}],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_days": [1],
            "recurrence_year_days": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_months": [1],
            "recurrence_year_month_weekdays": [{"weekday": "monday", "week_number": 1}],
            "recurrence_year_weeks": [1],
        },
        {
            "recurrence_frequency": "yearly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_year_days": [1],
            "recurrence_year_weeks": [1],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
            "recurrence_set_positions": [0],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
            "recurrence_set_positions": [367],
        },
        {
            "recurrence_frequency": "monthly",
            "recurrence_interval": 1,
            "recurrence_count": 5,
            "recurrence_weekdays": ["monday"],
            "recurrence_set_positions": [True],
        },
    ]
    for kwargs in cases:
        result = plan_calendar_change(
            "create",
            title="Synthetic recurring event",
            calendar_title="Synthetic Calendar",
            start_date="2026-06-05T17:00:00Z",
            end_date="2026-06-05T18:00:00Z",
            **kwargs,
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_recurrence"


def test_plan_calendar_change_set_positions_requires_recurrence_selector() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=5,
        recurrence_set_positions=[-1],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_recurrence"
    assert "requires another recurrence selector" in result["warnings"][0]["message"]


def test_plan_calendar_change_update_clear_recurrence_binds_series_proof_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_all_delete_runner)
    handle = search["results"][0]["handle"]
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        eventkit_runner=_recurring_all_delete_runner,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=False,
        eventkit_runner=_recurring_all_delete_runner,
    )

    assert base["status"] == "ok"
    expected = base["preview"]["target"]["expected_state"]
    proposed = base["preview"]["proposed"]
    assert expected["recurrence_expected"] is True
    assert expected["recurrence_present"] is True
    assert expected["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    assert proposed["recurrence_clear_requested"] is True
    assert proposed["recurrence_present"] is False
    assert proposed["recurrence"] == {
        "frequency": "",
        "interval": 0,
        "count": 0,
        "recurrence_present": False,
    }
    assert proposed["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
    assert proposed["first_occurrence_verified"] is True
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_update_mid_series_clear_recurrence_binds_previous_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["recurrence_clear_requested"] is True
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["mid_series_recurrence_clear_requested"] is True
    assert proposed["first_occurrence_verified"] is False
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_mid_series_recurrence_replacement_binds_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    expected = plan["preview"]["target"]["expected_state"]
    proposed = plan["preview"]["proposed"]
    assert expected["recurrence_expected"] is True
    assert expected["recurrence_present"] is True
    assert expected["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["mid_series_recurrence_replace_requested"] is True
    assert proposed["recurrence_clear_requested"] is False
    assert proposed["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
    }
    assert proposed["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_mid_series_unbounded_recurrence_replacement_binds_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_unbounded=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    expected = plan["preview"]["target"]["expected_state"]
    proposed = plan["preview"]["proposed"]
    assert expected["recurrence_expected"] is True
    assert expected["recurrence_present"] is True
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["mid_series_recurrence_replace_requested"] is True
    assert proposed["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_future_series_scalar_binds_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="",
        expected_notes="",
        title="Synthetic future series event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Future Room",
        notes="Future series notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    expected = plan["preview"]["target"]["expected_state"]
    proposed = plan["preview"]["proposed"]
    assert expected["recurrence_expected"] is True
    assert expected["recurrence_present"] is True
    assert expected["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
    }
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["future_series_scalar_update_requested"] is True
    assert proposed["recurrence_clear_requested"] is False
    assert proposed["recurrence_present"] is False
    assert proposed["title"] == "Synthetic future series event"
    assert proposed["location"] == "Future Room"
    assert proposed["notes_text"] == "Future series notes."
    assert proposed["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_future_series_reschedule_binds_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    expected = plan["preview"]["target"]["expected_state"]
    proposed = plan["preview"]["proposed"]
    assert expected["recurrence_expected"] is True
    assert expected["recurrence_present"] is True
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["future_series_reschedule_requested"] is True
    assert proposed["future_series_scalar_update_requested"] is False
    assert proposed["start_date"] == "2026-06-03T19:00:00Z"
    assert proposed["end_date"] == "2026-06-03T20:00:00Z"
    assert proposed["time_zone"] == "America/New_York"
    assert proposed["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_future_series_availability_binds_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert plan["status"] == "ok"
    expected = plan["preview"]["target"]["expected_state"]
    proposed = plan["preview"]["proposed"]
    assert expected["availability"] == 0
    assert proposed["availability"] == 1
    assert proposed["availability_requested"] is True
    assert proposed["recurrence_update_scope"] == "future_events"
    assert proposed["future_series_availability_update_requested"] is True
    assert proposed["future_series_scalar_update_requested"] is False
    assert proposed["future_series_reschedule_requested"] is False
    assert proposed["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert proposed["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert proposed["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"


def test_plan_calendar_change_update_clear_recurrence_rejects_unsafe_shapes() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_all_delete_runner)
    handle = search["results"][0]["handle"]

    create = plan_calendar_change(
        "create",
        title="Synthetic planning event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
    )
    conflict = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_count=4,
        clear_recurrence=True,
        eventkit_runner=_recurring_all_delete_runner,
    )
    scalar = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic renamed event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        eventkit_runner=_recurring_all_delete_runner,
    )
    this_event_scope = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_all_delete_runner,
    )
    future_scope_without_clear = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_all_delete_runner,
    )
    replacement_scalar = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic renamed event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_count=4,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )
    target_calendar_handle = search_calendar_calendars(
        "Focus", eventkit_runner=_recurring_future_delete_runner
    )["results"][0]["handle"]
    replacement_co_mutations = [
        {"target_calendar_handle": target_calendar_handle},
        {"availability": "free"},
        {"event_url": "https://example.test/replacement"},
        {"clear_event_url": True, "expected_event_url_present": False},
        {"clear_structured_location": True},
        {"alarm_offsets_minutes": [5]},
        {"alarm_absolute_dates": ["2026-06-03T16:45:00Z"]},
        {"alarm_sound_name": "Basso"},
    ]
    replacement_co_mutation_results = [
        plan_calendar_change(
            "update",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            title="Synthetic planning event",
            start_date="2026-06-03T17:00:00Z",
            end_date="2026-06-03T18:00:00Z",
            recurrence_frequency="daily",
            recurrence_count=4,
            recurrence_update_scope="future-events",
            eventkit_runner=_recurring_future_delete_runner,
            **extra,
        )
        for extra in replacement_co_mutations
    ]
    future_series_co_mutations = [
        {"target_calendar_handle": target_calendar_handle},
        {"availability": "free", "expected_availability": "busy"},
        {"event_url": "https://example.test/future-series"},
        {"clear_structured_location": True, "expected_structured_location": {"title": "Old Room", "geo_present": False}},
        {"alarm_offsets_minutes": [5]},
        {"alarm_absolute_dates": ["2026-06-03T16:45:00Z"]},
        {"alarm_sound_name": "Basso", "alarm_offsets_minutes": [5]},
    ]
    future_series_co_mutation_results = [
        plan_calendar_change(
            "update",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            expected_location="",
            expected_notes="",
            title="Synthetic future series event",
            start_date=extra.pop("start_date", "2026-06-03T17:00:00Z"),
            end_date=extra.pop("end_date", "2026-06-03T18:00:00Z"),
            location="Future Room",
            notes="Future series notes.",
            recurrence_update_scope="future-events",
            eventkit_runner=_recurring_future_delete_runner,
            **extra,
        )
        for extra in (dict(item) for item in future_series_co_mutations)
    ]
    future_series_reschedule_missing_zone = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="",
        expected_notes="",
        title="Synthetic future series event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        location="Future Room",
        notes="Future series notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    assert create["status"] == "error"
    assert create["warnings"][0]["code"] == "unsupported_recurrence_for_operation"
    assert conflict["status"] == "error"
    assert conflict["warnings"][0]["code"] == "conflicting_recurrence_fields"
    assert scalar["status"] == "error"
    assert scalar["warnings"][0]["code"] == "unsupported_clear_recurrence_shape"
    assert this_event_scope["status"] == "error"
    assert this_event_scope["warnings"][0]["code"] == "unsupported_recurrence_update_scope"
    assert future_scope_without_clear["status"] == "error"
    assert (
        future_scope_without_clear["warnings"][0]["code"]
        == "unsupported_recurrence_update_scope"
    )
    assert replacement_scalar["status"] == "error"
    assert replacement_scalar["warnings"][0]["code"] == "unsupported_recurrence_replacement_shape"
    for result in replacement_co_mutation_results:
        assert result["status"] == "error"
        assert any(
            warning["code"] == "unsupported_recurrence_replacement_shape"
            for warning in result["warnings"]
        )
    for result in future_series_co_mutation_results:
        assert result["status"] == "error"
        assert any(
            warning["code"] == "unsupported_future_series_update_shape"
            for warning in result["warnings"]
        )
    assert future_series_reschedule_missing_zone["status"] == "error"
    assert any(
        warning["code"] == "missing_required_field"
        for warning in future_series_reschedule_missing_zone["warnings"]
    )


def test_plan_calendar_change_update_future_series_availability_rejects_co_mutations() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus", eventkit_runner=_recurring_future_delete_runner
    )["results"][0]["handle"]
    base = {
        "handle": handle,
        "expected_title": "Synthetic planning event",
        "expected_calendar_title": "Synthetic Calendar",
        "expected_start_date": "2026-06-03T17:00:00Z",
        "expected_end_date": "2026-06-03T18:00:00Z",
        "expected_location": "",
        "expected_notes": "",
        "expected_availability": "busy",
        "title": "Synthetic planning event",
        "start_date": "2026-06-03T17:00:00Z",
        "end_date": "2026-06-03T18:00:00Z",
        "location": "",
        "notes": "",
        "availability": "free",
        "recurrence_update_scope": "future-events",
        "eventkit_runner": _recurring_future_delete_runner,
    }
    extras = [
        ({"target_calendar_handle": target_calendar_handle}, "unsupported_future_series_update_shape"),
        ({"title": "Synthetic future series event"}, "unsupported_future_series_update_shape"),
        ({"location": "Future Room"}, "unsupported_future_series_update_shape"),
        ({"notes": "Future series notes."}, "unsupported_future_series_update_shape"),
        ({
            "start_date": "2026-06-03T19:00:00Z",
            "end_date": "2026-06-03T20:00:00Z",
            "expected_time_zone": "America/Los_Angeles",
            "time_zone": "America/New_York",
        }, "unsupported_future_series_update_shape"),
        ({"all_day": True, "expected_all_day": False}, "unsupported_future_series_update_shape"),
        ({"event_url": "https://example.test/future-series"}, "unsupported_future_series_update_shape"),
        ({"clear_event_url": True, "expected_event_url_present": False}, "unsupported_future_series_update_shape"),
        ({"structured_location": {"title": "Future Room", "geo_present": False}}, "unsupported_future_series_update_shape"),
        ({
            "clear_structured_location": True,
            "expected_structured_location": {"title": "Old Room", "geo_present": False},
        }, "unsupported_future_series_update_shape"),
        ({"alarm_offsets_minutes": [5]}, "unsupported_future_series_update_shape"),
        ({"alarm_absolute_dates": ["2026-06-03T16:45:00Z"]}, "unsupported_future_series_update_shape"),
        ({"alarm_sound_name": "Basso", "alarm_offsets_minutes": [5]}, "unsupported_future_series_update_shape"),
        ({"recurrence_frequency": "daily", "recurrence_count": 4}, "unsupported_recurrence_replacement_shape"),
        ({"clear_recurrence": True}, "unsupported_clear_recurrence_shape"),
    ]

    results = [
        (expected_code, plan_calendar_change("update", **{**base, **extra}))
        for extra, expected_code in extras
    ]

    for expected_code, result in results:
        assert result["status"] == "error"
        assert any(
            warning["code"] == expected_code
            for warning in result["warnings"]
        )
        approval = (result.get("preview") or {}).get("approval", {})
        assert "approval_fingerprint" not in approval



def test_plan_calendar_change_rejects_invalid_availability() -> None:
    create = plan_calendar_change(
        "create",
        title="Synthetic invalid availability event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="transparent",
    )
    update = plan_calendar_change(
        "update",
        handle="calendar:event:v1:synthetic",
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        expected_availability="unknown",
    )

    assert create["status"] == "error"
    assert create["warnings"][0]["code"] == "invalid_availability"
    assert update["status"] == "error"
    assert update["warnings"][0]["code"] == "invalid_handle"
    assert update["warnings"][1]["code"] == "invalid_availability"


def test_plan_calendar_change_update_availability_requires_expected_state() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    missing = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="free",
    )
    bound = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="free",
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"
    assert bound["status"] == "ok"
    assert bound["preview"]["target"]["expected_state"]["availability"] == 0
    assert bound["preview"]["target"]["expected_state"]["availability_name"] == "busy"
    assert bound["preview"]["proposed"]["availability"] == 1
    assert bound["preview"]["proposed"]["availability_name"] == "free"


def test_plan_calendar_change_update_recurrence_binds_preview_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=3,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=4,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence_present"] is True
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 3,
        "recurrence_present": True,
    }
    assert base["preview"]["target"]["expected_state"]["recurrence_expected"] is True
    assert base["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_update_unbounded_recurrence_binds_preview_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_unbounded=True,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_unbounded=True,
    )

    assert base["status"] == "ok"
    assert base["preview"]["proposed"]["recurrence_present"] is True
    assert base["preview"]["proposed"]["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert base["preview"]["target"]["expected_state"]["recurrence_expected"] is True
    assert base["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_update_weekly_weekday_recurrence_binds_preview() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic weekday updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=6,
        recurrence_weekdays=["tuesday", "thursday"],
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
        "weekdays": ["tuesday", "thursday"],
    }
    assert result["preview"]["target"]["expected_state"]["recurrence_expected"] is True
    assert result["preview"]["target"]["expected_state"]["recurrence_present"] is False


def test_plan_calendar_change_update_monthly_month_day_recurrence_binds_preview() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic month-day updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=6,
        recurrence_month_days="1,15,-1",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 6,
        "recurrence_present": True,
        "month_days": [-1, 1, 15],
    }
    assert result["preview"]["target"]["expected_state"]["recurrence_expected"] is True
    assert result["preview"]["target"]["expected_state"]["recurrence_present"] is False


def test_plan_calendar_change_update_event_url_binds_expected_state_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    proposed_url = "https://meet.example.invalid/new?id=43"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic updated URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        event_url=proposed_url,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic updated URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        event_url="https://meet.example.invalid/other?id=44",
    )

    assert base["status"] == "ok"
    expected = base["preview"]["target"]["expected_state"]
    assert expected["event_url_present"] is True
    assert expected["event_url_safe_sha256"] == expected_sha
    assert base["preview"]["proposed"]["event_url_requested"] is True
    assert base["preview"]["proposed"]["event_url_safe_sha256"] == hashlib.sha256(
        proposed_url.encode("utf-8")
    ).hexdigest()
    assert "event_url" not in base["preview"]["proposed"]
    assert proposed_url not in json.dumps(base, sort_keys=True)
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_update_clear_event_url_binds_expected_state_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()
    base = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )
    changed = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256="b" * 64,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )

    assert base["status"] == "ok"
    expected = base["preview"]["target"]["expected_state"]
    assert expected["event_url_present"] is True
    assert expected["event_url_safe_sha256"] == expected_sha
    proposed = base["preview"]["proposed"]
    assert proposed["event_url_requested"] is False
    assert proposed["event_url_clear_requested"] is True
    assert proposed["url_present"] is False
    assert "event_url" not in proposed
    assert expected_url not in json.dumps(base, sort_keys=True)
    assert (
        base["preview"]["approval"]["approval_fingerprint"]
        != changed["preview"]["approval"]["approval_fingerprint"]
    )


def test_plan_calendar_change_clear_event_url_rejects_unsafe_shapes() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_sha = hashlib.sha256(
        "https://meet.example.invalid/current?id=42".encode("utf-8")
    ).hexdigest()
    missing_expected = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )
    conflicting = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        event_url="https://meet.example.invalid/new?id=43",
        clear_event_url=True,
    )
    create_clear = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )
    delete_clear = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
    )

    assert missing_expected["status"] == "error"
    assert missing_expected["warnings"][0]["code"] == "missing_required_field"
    assert conflicting["status"] == "error"
    assert conflicting["warnings"][0]["code"] == "conflicting_event_url_fields"
    assert create_clear["status"] == "error"
    assert create_clear["warnings"][0]["code"] == "unsupported_event_url_for_operation"
    assert delete_clear["status"] == "error"
    assert delete_clear["warnings"][0]["code"] == "unsupported_event_url_for_operation"


def test_plan_calendar_change_requires_url_sha_when_expected_url_present() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    missing = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        title="Synthetic updated URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
    )
    orphan_sha = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_sha256="a" * 64,
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"
    assert orphan_sha["status"] == "error"
    assert orphan_sha["warnings"][0]["code"] == "invalid_expected_state"


def test_plan_calendar_change_rejects_non_exact_expected_event_url_sha() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    for expected_sha in ("A" * 64, " " + ("a" * 64), ("a" * 64) + " "):
        result = plan_calendar_change(
            "update",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            expected_event_url_present=True,
            expected_event_url_sha256=expected_sha,
            title="Synthetic updated URL event",
            start_date="2026-06-03T19:00:00Z",
            end_date="2026-06-03T20:00:00Z",
            event_url="https://meet.example.invalid/new?id=43",
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_sha256"


def test_plan_calendar_change_delete_rejects_recurrence() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    delete = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=3,
    )

    assert delete["status"] == "error"
    assert delete["warnings"][0]["code"] == "unsupported_recurrence_for_operation"

    zero_only_update = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_count=0,
    )
    zero_only_delete = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_interval=0,
    )

    assert zero_only_update["status"] == "error"
    assert zero_only_update["warnings"][0]["code"] == "invalid_recurrence"
    assert zero_only_delete["status"] == "error"
    assert zero_only_delete["warnings"][0]["code"] == "unsupported_recurrence_for_operation"


def test_plan_calendar_change_delete_recurring_scope_binds_preview_and_token() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    scoped = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=_recurring_delete_runner,
    )
    unscoped = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
    )
    future_search = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_delete_runner,
    )
    future_handle = future_search["results"][0]["handle"]
    future_scope = plan_calendar_change(
        "delete",
        handle=future_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )
    all_search = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_all_delete_runner,
    )
    all_handle = all_search["results"][0]["handle"]
    all_scope = plan_calendar_change(
        "delete",
        handle=all_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        eventkit_runner=_recurring_all_delete_runner,
    )
    update_scope = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=_recurring_delete_runner,
    )

    assert scoped["status"] == "ok"
    expected_state = scoped["preview"]["target"]["expected_state"]
    assert expected_state["recurrence_expected"] is True
    assert expected_state["recurrence_present"] is True
    assert scoped["preview"]["proposed"]["recurrence_delete_scope"] == "this_event"
    assert scoped["preview"]["proposed"]["recurrence_present"] is True
    assert (
        scoped["preview"]["proposed"]["occurrence_start_date"]
        == "2026-06-03T17:00:00.000Z"
    )
    assert (
        scoped["preview"]["proposed"]["adjacent_occurrence_start_date"]
        == "2026-06-10T17:00:00.000Z"
    )
    assert (
        scoped["preview"]["approval"]["approval_fingerprint"]
        != unscoped["preview"]["approval"]["approval_fingerprint"]
    )
    assert future_scope["status"] == "ok"
    assert future_scope["preview"]["proposed"]["recurrence_delete_scope"] == "future_events"
    assert (
        future_scope["preview"]["proposed"]["previous_occurrence_start_date"]
        == "2026-05-27T17:00:00.000Z"
    )
    assert (
        future_scope["preview"]["proposed"]["future_occurrence_start_date"]
        == "2026-06-10T17:00:00.000Z"
    )
    assert (
        future_scope["preview"]["approval"]["approval_fingerprint"]
        != scoped["preview"]["approval"]["approval_fingerprint"]
    )
    assert all_scope["status"] == "ok"
    assert all_scope["preview"]["proposed"]["recurrence_delete_scope"] == "all_events"
    assert all_scope["preview"]["proposed"]["first_occurrence_verified"] is True
    assert (
        all_scope["preview"]["proposed"]["future_occurrence_start_date"]
        == "2026-06-10T17:00:00.000Z"
    )
    assert (
        all_scope["preview"]["approval"]["approval_fingerprint"]
        != future_scope["preview"]["approval"]["approval_fingerprint"]
    )
    assert update_scope["status"] == "error"
    assert update_scope["warnings"][0]["code"] == "unsupported_recurrence_delete_scope"


def test_plan_calendar_change_rejects_legacy_handle_for_scoped_recurring_delete() -> None:
    legacy_handle = make_opaque_handle("calendar:event", "event-1")

    for scope, runner in {
        "this-event": _recurring_delete_runner,
        "future-events": _recurring_future_delete_runner,
        "all-events": _recurring_all_delete_runner,
    }.items():
        result = plan_calendar_change(
            "delete",
            handle=legacy_handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            recurrence_delete_scope=scope,
            eventkit_runner=runner,
        )

        assert result["status"] == "error"
        assert result["preview"] is None
        assert result["warnings"][0]["code"] == "missing_occurrence_identity"


def test_plan_calendar_change_rejects_mixed_alarm_modes() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic mixed alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "conflicting_alarm_fields"


def test_plan_calendar_change_create_time_zone_binds_preview() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic zoned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["time_zone"] == "America/Los_Angeles"
    assert result["preview"]["proposed"]["time_zone_bound"] is True


def test_get_calendar_calendar_returns_safe_hashes_without_raw_ids() -> None:
    calendars = search_calendar_calendars("Focus", eventkit_runner=_runner)
    handle = calendars["results"][0]["handle"]

    result = get_calendar_calendar(handle, eventkit_runner=_runner)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert result["result"]["calendar_safe_sha256"]
    assert result["result"]["source_safe_sha256"]
    assert "calendar-2" not in str(result)
    assert "source-2" not in str(result)


def test_plan_calendar_calendar_create_binds_source_calendar_handle() -> None:
    source_handle = search_calendar_calendars("Synthetic", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="LAD-TEST-new",
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "create_calendar"
    assert result["preview"]["target"]["source_calendar_handle"] == source_handle
    assert result["preview"]["target"]["source_calendar_safe_sha256"]
    assert result["preview"]["proposed"]["calendar_title"] == "LAD-TEST-new"
    assert result["preview"]["approval"]["approval_token_format"].startswith("calendar-apply:v1:")
    assert "source-1" not in str(result)


def test_plan_calendar_calendar_create_rejects_non_synthetic_title() -> None:
    source_handle = search_calendar_calendars("Synthetic", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="Real Team Calendar",
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "non_synthetic_calendar_title"


def test_plan_calendar_calendar_create_rejects_read_only_source_calendar() -> None:
    source_handle = search_calendar_calendars("Synthetic", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    def read_only_source_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                if calendar["calendar_id"] == "calendar-1":
                    calendar["allows_content_modifications"] = False
                    calendar["is_subscribed"] = True
                    calendar["is_immutable"] = True
                    calendar["source_type"] = "local"
        return response

    result = plan_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="LAD-TEST-new",
        eventkit_runner=read_only_source_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_calendar_source"


def test_apply_calendar_calendar_create_requires_matching_token_and_reads_back() -> None:
    source_handle = search_calendar_calendars("Synthetic", eventkit_runner=_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="LAD-TEST-new",
        eventkit_runner=_runner,
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    invalid = apply_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="LAD-TEST-new",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
        eventkit_runner=_runner,
    )
    result = apply_calendar_calendar_change(
        "create-calendar",
        source_calendar_handle=source_handle,
        calendar_title="LAD-TEST-new",
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert invalid["status"] == "error"
    assert invalid["warnings"][0]["code"] == "invalid_approval_token"
    assert result["status"] == "ok"
    assert result["operation"] == "create_calendar"
    assert result["read_back"]["title"] == "LAD-TEST-new"
    assert result["read_back"]["source_calendar_verified"] is True
    assert result["read_back"]["event_count_in_safety_window"] == 0


def test_plan_calendar_calendar_rename_requires_synthetic_empty_calendar() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_calendar_change(
        "rename-calendar",
        calendar_handle=calendar_handle,
        new_calendar_title="LAD-TEST-new",
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "rename_calendar"
    assert result["preview"]["target"]["calendar_handle"] == calendar_handle
    assert result["preview"]["target"]["calendar_title"] == "LAD-TEST-old"
    assert result["preview"]["target"]["event_count_in_safety_window"] == 0
    assert result["preview"]["proposed"]["new_calendar_title"] == "LAD-TEST-new"
    assert "calendar-test" not in str(result)


def test_apply_calendar_calendar_rename_reads_back_title() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_calendar_change(
        "rename-calendar",
        calendar_handle=calendar_handle,
        new_calendar_title="LAD-TEST-new",
        eventkit_runner=_runner,
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    result = apply_calendar_calendar_change(
        "rename-calendar",
        calendar_handle=calendar_handle,
        new_calendar_title="LAD-TEST-new",
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "rename_calendar"
    assert result["read_back"]["title"] == "LAD-TEST-new"
    assert result["read_back"]["calendar_handle"] == calendar_handle
    assert result["read_back"]["empty_calendar_verified"] is True


def test_apply_calendar_calendar_rename_requires_empty_read_back_proof() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_calendar_change(
        "rename-calendar",
        calendar_handle=calendar_handle,
        new_calendar_title="LAD-TEST-new",
        eventkit_runner=_runner,
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def unsafe_runner(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if (
            payload.get("command") == "calendar_calendar_apply_change"
            and payload.get("operation") == "rename_calendar"
        ):
            result["read_back"]["calendar_empty_verified"] = False
            result["calendar"]["event_count_in_safety_window"] = 1
        return result

    result = apply_calendar_calendar_change(
        "rename-calendar",
        calendar_handle=calendar_handle,
        new_calendar_title="LAD-TEST-new",
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=unsafe_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "calendar_rename_read_back_mismatch"


def test_plan_calendar_calendar_delete_requires_synthetic_empty_calendar() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "delete_calendar"
    assert result["preview"]["target"]["calendar_handle"] == calendar_handle
    assert result["preview"]["target"]["calendar_title"] == "LAD-TEST-old"
    assert result["preview"]["target"]["event_count_in_safety_window"] == 0
    assert result["preview"]["proposed"]["delete_requested"] is True
    assert "calendar-test" not in str(result)


def test_plan_calendar_calendar_delete_refuses_non_empty_calendar() -> None:
    calendar_handle = search_calendar_calendars("busy", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "calendar_not_empty"


def test_plan_calendar_calendar_delete_refuses_mixed_event_reminder_calendar() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    def mixed_entity_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                if calendar["calendar_id"] == "calendar-test":
                    calendar["allowed_entity_types"] = ["event", "reminder"]
        return response

    result = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=mixed_entity_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_calendar_state"


def test_plan_calendar_calendar_delete_refuses_missing_entity_type_proof() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]

    def missing_entity_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                if calendar["calendar_id"] == "calendar-test":
                    calendar.pop("allowed_entity_types", None)
        return response

    result = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=missing_entity_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_calendar_state"


def test_apply_calendar_calendar_delete_reads_back_absence() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=_runner,
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    invalid = apply_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
        eventkit_runner=_runner,
    )
    result = apply_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert invalid["status"] == "error"
    assert invalid["warnings"][0]["code"] == "invalid_approval_token"
    assert result["status"] == "ok"
    assert result["operation"] == "delete_calendar"
    assert result["mutation_applied"] is True
    assert result["result_count"] == 0
    assert result["read_back"]["calendar_handle"] == calendar_handle
    assert result["read_back"]["calendar_deleted_verified"] is True
    assert result["read_back"]["calendar_absent_verified"] is True
    assert result["read_back"]["calendar_empty_verified"] is True


def test_apply_calendar_calendar_delete_requires_absence_proof() -> None:
    calendar_handle = search_calendar_calendars("old", eventkit_runner=_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        eventkit_runner=_runner,
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def unsafe_runner(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if (
            payload.get("command") == "calendar_calendar_apply_change"
            and payload.get("operation") == "delete_calendar"
        ):
            result["read_back"]["calendar_absent_verified"] = False
        return result

    result = apply_calendar_calendar_change(
        "delete-calendar",
        calendar_handle=calendar_handle,
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=unsafe_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "calendar_delete_read_back_mismatch"


def test_plan_calendar_change_create_accepts_exact_calendar_handle() -> None:
    calendars = search_calendar_calendars("Focus", eventkit_runner=_runner)
    handle = calendars["results"][0]["handle"]

    result = plan_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_handle=handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )

    assert result["status"] == "ok"
    assert result["preview"]["target"]["target_mode"] == "calendar_handle"
    assert result["preview"]["target"]["calendar_handle"] == handle
    assert result["preview"]["target"]["calendar_title"] == ""


def test_plan_calendar_change_create_with_default_calendar_binds_exact_target() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    target = result["preview"]["target"]
    assert target["target_mode"] == "calendar_handle"
    assert target["calendar_title"] == ""
    assert target["calendar_handle"].startswith("calendar:calendar:v1:")
    resolution = result["preview"]["default_calendar_resolution"]
    assert resolution["use_default_calendar"] is True
    assert resolution["calendar_title"] == "Synthetic Calendar"
    assert resolution["calendar_handle"] == target["calendar_handle"]
    assert resolution["is_default_calendar"] is True
    assert resolution["default_calendar_verified"] is True
    assert resolution["allows_content_modifications"] is True

    exact_handle_plan = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        calendar_handle=target["calendar_handle"],
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )
    assert exact_handle_plan["preview"]["approval"]["approval_fingerprint"] == result[
        "preview"
    ]["approval"]["approval_fingerprint"]


def test_plan_calendar_change_create_default_calendar_conflicts_with_explicit_target() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        calendar_title="Synthetic Calendar",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "conflicting_target_calendar"


def test_plan_calendar_change_create_default_calendar_requires_writable_target() -> None:
    def non_writable_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                if calendar["is_default_calendar"]:
                    calendar["allows_content_modifications"] = False
        return response

    result = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=non_writable_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "target_calendar_not_writable"


def test_plan_calendar_change_create_default_calendar_requires_single_default() -> None:
    def no_default_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                calendar["is_default_calendar"] = False
        return response

    missing = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=no_default_runner,
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "default_calendar_not_found"

    def ambiguous_default_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            response["calendars"].append(
                {
                    "calendar_id": "calendar-2",
                    "title": "Synthetic Focus",
                    "is_default_calendar": True,
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "caldav",
                    "source_type": "caldav",
                    "supported_event_availabilities": ["busy", "free", "tentative"],
                }
            )
        return response

    ambiguous = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=ambiguous_default_runner,
    )

    assert ambiguous["status"] == "error"
    assert ambiguous["warnings"][0]["code"] == "ambiguous_default_calendar"


def test_plan_calendar_change_create_rejects_conflicting_calendar_targets() -> None:
    calendars = search_calendar_calendars("Focus", eventkit_runner=_runner)
    handle = calendars["results"][0]["handle"]

    result = plan_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_title="Synthetic Calendar",
        calendar_handle=handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "conflicting_target_calendar"


def test_plan_calendar_change_update_binds_target_calendar_handle() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    event_handle = search["results"][0]["handle"]
    calendars = search_calendar_calendars("Focus", eventkit_runner=_runner)
    target_handle = calendars["results"][0]["handle"]

    result = plan_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle=target_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["target_calendar_handle"] == target_handle
    assert result["preview"]["proposed"]["calendar_move_requested"] is True
    assert "calendar-2" not in str(result)


def test_plan_calendar_change_update_rejects_invalid_target_calendar_handle() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    event_handle = search["results"][0]["handle"]

    result = plan_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle="calendar-2",
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_calendar_handle"


def test_plan_calendar_change_rejects_invalid_alarm_offsets() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=["-10"],  # type: ignore[list-item]
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_alarm_offsets"


def test_plan_calendar_change_rejects_invalid_time_zone() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic zoned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="Pacific Standard Time",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_time_zone"


def test_plan_calendar_change_rejects_path_like_time_zones() -> None:
    for bad_zone in ("/etc/passwd", "../../etc/passwd"):
        result = plan_calendar_change(
            "create",
            title="Synthetic zoned event",
            calendar_title="Synthetic Calendar",
            start_date="2026-06-05T17:00:00Z",
            end_date="2026-06-05T18:00:00Z",
            time_zone=bad_zone,
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_time_zone"
        assert bad_zone not in str(result)


def test_plan_calendar_change_rejects_path_like_expected_time_zones_for_update() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    for bad_zone in ("/etc/passwd", "../../etc/passwd"):
        result = plan_calendar_change(
            "update",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            expected_time_zone=bad_zone,
            title="Synthetic updated event",
            start_date="2026-06-03T19:00:00Z",
            end_date="2026-06-03T20:00:00Z",
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_time_zone"
        assert bad_zone not in str(result)


def test_plan_calendar_change_rejects_path_like_expected_time_zones_for_delete() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    for bad_zone in ("/etc/passwd", "../../etc/passwd"):
        result = plan_calendar_change(
            "delete",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            expected_time_zone=bad_zone,
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_time_zone"
        assert bad_zone not in str(result)


def test_plan_calendar_change_rejects_time_zone_for_all_day() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
        time_zone="America/Los_Angeles",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_time_zone_for_all_day"


def test_plan_calendar_change_create_rejects_string_boolean() -> None:
    result = plan_calendar_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day="false",  # type: ignore[arg-type]
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_boolean"


def test_plan_calendar_change_update_requires_exact_handle() -> None:
    result = plan_calendar_change(
        "update",
        handle="event-1",
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_calendar_change_update_returns_expected_state_preview() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = _calendar_update_plan(handle)

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "update"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_state"]["title"] == "Synthetic planning event"
    assert result["preview"]["proposed"]["title"] == "Synthetic updated event"
    assert result["preview"]["approval"]["approval_token_format"].startswith(
        "calendar-apply:v1:"
    )
    assert "event-1" not in str(result)


def test_plan_calendar_change_update_binds_time_zone_expected_state() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
    )

    assert result["status"] == "ok"
    assert result["preview"]["target"]["expected_state"]["time_zone"] == "America/Los_Angeles"
    assert result["preview"]["proposed"]["time_zone"] == "America/New_York"
    assert result["preview"]["proposed"]["time_zone_bound"] is True


def test_plan_calendar_change_delete_requires_exact_handle() -> None:
    result = plan_calendar_change(
        "delete",
        handle="event-1",
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_calendar_change_delete_returns_expected_state_preview() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]

    result = _calendar_delete_plan(handle)

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "delete"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_state"]["title"] == "Synthetic planning event"
    assert result["preview"]["proposed"]["delete"] is True
    assert result["preview"]["approval"]["approval_token_format"].startswith(
        "calendar-apply:v1:"
    )
    assert "event-1" not in str(result)


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


def test_apply_calendar_change_creates_timed_event_with_time_zone() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic zoned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        time_zone="America/Los_Angeles",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic zoned event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        time_zone="America/Los_Angeles",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["time_zone"] == "America/Los_Angeles"
    assert calls[-1]["time_zone"] == "America/Los_Angeles"


def test_apply_calendar_change_creates_event_with_structured_location() -> None:
    calls: list[dict[str, Any]] = []
    structured = {
        "title": "Synthetic Structured Room",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25,
    }

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        structured_location=structured,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T17:00:00Z",
        end_date="2026-06-04T18:00:00Z",
        structured_location=structured,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["structured_location_verified"] is True
    assert result["read_back"]["structured_location"] == {
        "title": "Synthetic Structured Room",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25.0,
    }
    assert calls[-1]["location"] == "Synthetic Structured Room"
    assert calls[-1]["structured_location"] == result["read_back"]["structured_location"]


def test_apply_calendar_change_clears_structured_location_and_reads_back_absence() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["structured_location_present"] is False
    assert result["read_back"]["structured_location_cleared_verified"] is True
    assert calls[-1]["expected_structured_location"] == {
        "title": "Synthetic Room",
        "geo_present": False,
    }
    assert calls[-1]["structured_location_clear_requested"] is True
    assert calls[-1]["structured_location"] == {}
    assert calls[-1]["location"] == ""


def test_apply_calendar_change_clear_structured_location_requires_absence_proof() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
            result["event"]["structured_location_present"] = True
            result["event"]["structured_location"] = {
                "title": "Synthetic Room",
                "geo_present": False,
            }
            result["event"]["location_present"] = True
        return result

    search = search_calendar_events("planning", eventkit_runner=mismatched_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "structured_location_clear_read_back_mismatch"


def test_apply_calendar_change_clear_structured_location_requires_plain_location_absence() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
            result["event"]["structured_location_present"] = False
            result["event"]["location_present"] = True
        return result

    search = search_calendar_events("planning", eventkit_runner=mismatched_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location={"title": "Synthetic Room"},
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "structured_location_clear_read_back_mismatch"


def test_apply_calendar_change_creates_event_with_exact_calendar_handle() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    calendars = search_calendar_calendars("Focus", eventkit_runner=recording_runner)
    calendar_handle = calendars["results"][0]["handle"]
    plan = plan_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["calendar_title"] == "Synthetic Focus"
    assert result["read_back"]["target_calendar_handle"] == calendar_handle
    assert result["read_back"]["target_calendar_verified"] is True
    assert calls[-1]["command"] == "calendar_apply_change"
    assert calls[-1]["calendar_id"] == "calendar-2"
    assert calls[-1]["calendar_title"] == ""
    assert "calendar-2" not in str(result)


def test_apply_calendar_change_creates_event_with_default_calendar_target() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=recording_runner,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        calendar_handle=plan["preview"]["target"]["calendar_handle"],
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["calendar_title"] == "Synthetic Calendar"
    assert result["read_back"]["target_calendar_verified"] is True
    assert result["read_back"]["target_calendar_handle"] == plan["preview"]["target"][
        "calendar_handle"
    ]
    assert calls[-1]["command"] == "calendar_apply_change"
    assert calls[-1]["calendar_id"] == "calendar-1"
    assert calls[-1]["calendar_title"] == ""
    assert "calendar-1" not in str(result)


def test_apply_calendar_change_default_calendar_apply_uses_bound_handle() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        eventkit_runner=_runner,
    )
    calls: list[dict[str, Any]] = []

    def changed_default_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                calendar["is_default_calendar"] = calendar["calendar_id"] == "calendar-2"
        return response

    result = apply_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        calendar_handle=plan["preview"]["target"]["calendar_handle"],
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=changed_default_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["target_calendar_verified"] is True
    assert result["read_back"]["target_calendar_handle"] == plan["preview"]["target"][
        "calendar_handle"
    ]
    assert calls[-1]["command"] == "calendar_apply_change"
    assert calls[-1]["calendar_id"] == "calendar-1"


def test_apply_calendar_change_rejects_default_calendar_apply_without_eventkit() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    result = apply_calendar_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "default_calendar_plan_only"
    assert calls == []


def test_apply_calendar_change_creates_all_day_event_and_reads_back() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
    )

    def create_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            assert payload["all_day"] is True
        return _runner(payload, timeout)

    result = apply_calendar_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=create_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-05"
    assert result["read_back"]["end_date"] == "2026-06-06"


def test_apply_calendar_change_creates_date_only_event_and_binds_all_day() -> None:
    calls: list[dict[str, Any]] = []
    plan = plan_calendar_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
    )

    def create_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    result = apply_calendar_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=create_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-05"
    assert result["read_back"]["end_date"] == "2026-06-06"
    assert calls[-1]["start_date"] == "2026-06-05"
    assert calls[-1]["end_date"] == "2026-06-06"
    assert calls[-1]["all_day"] is True


def test_apply_calendar_change_creates_alarm_offsets_and_reads_back() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[0, -10],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[0, -10],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10, 0]
    assert result["read_back"]["alarms_count"] == 2


def test_apply_calendar_change_creates_absolute_alarm_and_reads_back() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic absolute alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic absolute alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
    assert result["read_back"]["alarms_count"] == 1


def test_apply_calendar_change_creates_audio_alarm_and_reads_back() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert result["read_back"]["alarm_sound_name"] == "Glass"
    assert result["read_back"]["alarm_action"] == "audio"
    assert result["read_back"]["alarm_sound_name_verified"] is True


def test_apply_calendar_change_creates_email_alarm_and_reads_back_without_echo() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="Notify@Example.Invalid",
    )
    expected_sha = hashlib.sha256(b"notify@example.invalid").hexdigest()

    result = apply_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="Notify@Example.Invalid",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert result["read_back"]["alarm_email_address_sha256"] == expected_sha
    assert result["read_back"]["alarm_action"] == "email"
    assert result["read_back"]["alarm_email_address_sha256_verified"] is True
    assert calls[-1]["alarm_email_address"] == "notify@example.invalid"
    serialized = json.dumps(result, sort_keys=True)
    assert "notify@example.invalid" not in serialized
    assert "Notify@Example.Invalid" not in serialized


def test_apply_calendar_change_rejects_unapproved_email_alarm_value() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="notify@example.invalid",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="other@example.invalid",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_creates_geofence_alarm_and_reads_back() -> None:
    location = {
        "title": "Synthetic Gate",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75,
    }
    plan = plan_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_proximity"] == "enter"
    assert result["read_back"]["alarm_action"] == "geofence"
    assert result["read_back"]["alarm_structured_location"] == {
        "title": "Synthetic Gate",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75.0,
    }
    assert result["read_back"]["alarm_geofence_verified"] is True


def test_apply_calendar_change_creates_availability_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["availability"] == 1
    assert result["read_back"]["availability_name"] == "free"
    assert calls[-1]["availability"] == 1


def test_apply_calendar_change_creates_event_url_and_reads_back_hash() -> None:
    calls: list[dict[str, Any]] = []
    event_url = "https://meet.example.invalid/runtime?id=42"
    expected_sha = hashlib.sha256(event_url.encode("utf-8")).hexdigest()

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["url_present"] is True
    assert result["read_back"]["event_url_safe_sha256"] == expected_sha
    assert result["read_back"]["event_url_verified"] is True
    assert "event_url" not in result["read_back"]
    apply_payload = calls[-1]
    assert apply_payload["event_url_requested"] is True
    assert apply_payload["event_url"] == event_url


def test_apply_calendar_change_creates_safe_non_http_event_url() -> None:
    calls: list[dict[str, Any]] = []
    event_url = "mailto:calendar-link@example.invalid"
    expected_sha = hashlib.sha256(event_url.encode("utf-8")).hexdigest()

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["event_url_scheme"] == "mailto"
    assert result["status"] == "ok"
    assert result["read_back"]["url_present"] is True
    assert result["read_back"]["event_url_safe_sha256"] == expected_sha
    assert result["read_back"]["event_url_verified"] is True
    assert "event_url" not in result["read_back"]
    apply_payload = calls[-1]
    assert apply_payload["event_url_requested"] is True
    assert apply_payload["event_url"] == event_url


def test_apply_calendar_change_invalid_token_does_not_echo_event_url() -> None:
    event_url = "https://meet.example.invalid/runtime?id=secret-token"

    result = apply_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
        approval_token="calendar-apply:v1:wrong",
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert "event_url" not in result["preview"]["proposed"]
    assert event_url not in json.dumps(result, sort_keys=True)


def test_apply_calendar_change_flags_event_url_read_back_mismatch() -> None:
    event_url = "https://meet.example.invalid/runtime?id=42"

    def mismatched_url_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            response["event"] = {
                **response["event"],
                "url_present": True,
                "event_url_safe_sha256": "0" * 64,
            }
        return response

    plan = plan_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_url_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "event_url_read_back_mismatch"


def test_apply_calendar_change_flags_availability_read_back_mismatch() -> None:
    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {**response, "event": {**response["event"], "availability": 0}}
        return response

    plan = plan_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "availability_read_back_mismatch"


def test_apply_calendar_change_create_rejects_unsupported_availability_without_mutation() -> None:
    def unsupported_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change" and payload.get("availability") == 3:
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "availability_not_supported",
                        "message": "Calendar target does not support the requested availability value.",
                    }
                ],
            }
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic unavailable event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="unavailable",
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic unavailable event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="unavailable",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=unsupported_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "availability_not_supported"


def test_apply_calendar_change_creates_recurring_event_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=4,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=4,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is True
    assert result["read_back"]["recurrence"] == {
        "frequency": "daily",
        "interval": 2,
        "count": 4,
        "recurrence_present": True,
    }
    assert calls[-1]["recurrence"] == {
        "frequency": "daily",
        "interval": 2,
        "count": 4,
        "recurrence_present": True,
    }


def test_apply_calendar_change_creates_recurrence_end_date_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    recurrence_end_date = "2026-08-01T17:00:00Z"
    plan = plan_calendar_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date=recurrence_end_date,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date=recurrence_end_date,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": recurrence_end_date,
        "recurrence_present": True,
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is True
    assert result["read_back"]["recurrence"] == expected
    assert calls[-1]["recurrence"] == expected


def test_apply_calendar_change_creates_unbounded_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_unbounded=True,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_unbounded=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is True
    assert result["read_back"]["recurrence"] == expected
    assert calls[-1]["recurrence"] == expected


def test_apply_calendar_change_creates_weekly_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "wednesday", "friday"],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_monthly_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "wednesday", "friday"],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_set_positions_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    plan = plan_calendar_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": weekdays,
        "set_positions": [-1],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_monthly_month_day_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic month-day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_days=[1, 15, -1],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic month-day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_days=[1, 15, -1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_days": [-1, 1, 15],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_yearly_recurring_event_and_reads_back() -> None:
    plan = plan_calendar_change(
        "create",
        title="Synthetic yearly recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=3,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic yearly recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=3,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 3,
        "recurrence_present": True,
    }


def test_apply_calendar_change_creates_yearly_month_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic yearly month recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic yearly month recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_yearly_month_day_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_days=[1, 15, -1],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_days=[1, 15, -1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_days": [-1, 1, 15],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_yearly_month_nth_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    recurrence_year_month_weekdays = [
        {"weekday": "monday", "week_number": 2},
        {"weekday": "friday", "week_number": -1},
    ]
    plan = plan_calendar_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "monday", "week_number": 2},
        ],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_yearly_day_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "create",
        title="Synthetic yearly day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_days=[100, 1, -1],
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic yearly day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_days=[100, 1, -1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_days": [-1, 1, 100],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_creates_monthly_nth_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    recurrence_month_weekdays = [
        {"weekday": "tuesday", "week_number": 3},
        {"weekday": "friday", "week_number": -1},
    ]
    plan = plan_calendar_change(
        "create",
        title="Synthetic nth weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
    )

    result = apply_calendar_change(
        "create",
        title="Synthetic nth weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "tuesday", "week_number": 3},
        ],
    }
    assert calls[-1]["recurrence"] == result["read_back"]["recurrence"]


def test_apply_calendar_change_updates_exact_event_and_reads_back() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    plan = _calendar_update_plan(handle)

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "update"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"].startswith("calendar:event:v1:")
    assert result["read_back"]["title"] == "Synthetic updated event"
    assert "Synthetic updated event notes." not in str(result["read_back"])
    assert "event-1" not in str(result)


def test_apply_calendar_change_updates_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "weekly",
        "interval": 2,
        "count": 6,
        "recurrence_present": True,
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_recurrence_end_date_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    recurrence_end_date = "2026-08-01T19:00:00Z"
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated end-date recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_end_date=recurrence_end_date,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated end-date recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_end_date=recurrence_end_date,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "weekly",
        "interval": 2,
        "count": 0,
        "end_date": recurrence_end_date,
        "recurrence_present": True,
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_unbounded_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated unbounded recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_unbounded=True,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated unbounded recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_unbounded=True,
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "weekly",
        "interval": 2,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_monthly_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated monthly weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated monthly weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "wednesday", "friday"],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "wednesday", "friday"],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_set_positions_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated set-position recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated set-position recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": weekdays,
        "set_positions": [-1],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_monthly_nth_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    recurrence_month_weekdays = [
        {"weekday": "tuesday", "week_number": 3},
        {"weekday": "friday", "week_number": -1},
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated nth weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated nth weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "tuesday", "week_number": 3},
        ],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_yearly_month_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_yearly_month_day_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month day event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_days=[1, 15, -1],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month day event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_days=[1, 15, -1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_days": [-1, 1, 15],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_yearly_month_nth_weekday_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    recurrence_year_month_weekdays = [
        {"weekday": "monday", "week_number": 2},
        {"weekday": "friday", "week_number": -1},
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month nth weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month nth weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[1, 7, 12],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "monday", "week_number": 2},
        ],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_updates_yearly_week_recurrence_and_reads_back() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly week recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        recurrence_year_weeks=[26, 1, -1],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly week recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        recurrence_year_weeks=[26, 1, -1],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    expected_recurrence = {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
        "year_weeks": [-1, 1, 26],
    }
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == expected_recurrence
    assert result["read_back"]["recurrence_present"] is True
    assert calls[-1]["recurrence"] == expected_recurrence
    assert calls[-1]["expected_recurrence_present"] is False


def test_apply_calendar_change_update_recurrence_requires_matching_read_back() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and payload["operation"] == "update":
            result["event"]["recurrence"] = {
                "frequency": "weekly",
                "interval": 2,
                "count": 7,
                "recurrence_present": True,
            }
            result["event"]["recurrence_present"] = True
        return result

    search = search_calendar_events("planning", eventkit_runner=mismatched_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "recurrence_read_back_mismatch"


def test_apply_calendar_change_clears_recurrence_with_series_proof() -> None:
    calls: list[dict[str, Any]] = []

    def clear_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        if payload["command"] != "calendar_apply_change":
            return _recurring_all_delete_runner(payload, timeout)
        assert payload["operation"] == "update"
        assert payload["clear_recurrence"] is True
        assert payload["expected_recurrence_present"] is True
        assert payload["expected_recurrence"] == {
            "frequency": "weekly",
            "interval": 1,
            "count": 6,
            "recurrence_present": True,
        }
        assert payload["recurrence"] == {
            "frequency": "",
            "interval": 0,
            "count": 0,
            "recurrence_present": False,
        }
        assert payload["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
        assert payload["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": {
                    "frequency": "",
                    "interval": 0,
                    "count": 0,
                    "recurrence_present": False,
                },
                "recurrence_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "recurrence_cleared_verified": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_absent": True,
            },
            "warnings": [],
        }

    search = search_calendar_events("planning", eventkit_runner=clear_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        eventkit_runner=clear_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=clear_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is False
    assert result["read_back"]["recurrence_cleared_verified"] is True
    assert result["read_back"]["future_occurrence_verified_absent"] is True
    assert result["read_back"]["previous_occurrence_verified_absent"] is True
    assert calls[-1]["clear_recurrence"] is True


def test_apply_calendar_change_clears_mid_series_recurrence_with_previous_proof() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_mid_series_clear_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_mid_series_clear_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_mid_series_clear_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is False
    assert result["read_back"]["recurrence_cleared_verified"] is True
    assert result["read_back"]["future_occurrence_verified_absent"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["recurrence_update_scope"] == "future_events"


def test_apply_calendar_change_replaces_mid_series_recurrence_with_previous_future_proof() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_mid_series_replace_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_mid_series_replace_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_mid_series_replace_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["recurrence_replaced_verified"] is True
    assert result["read_back"]["future_occurrence_verified_present"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert (
        result["read_back"]["future_original_slot_verified_replaced_or_absent"] is True
    )
    assert result["read_back"]["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
    }

    clear_retry = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_mid_series_replace_runner,
    )
    assert clear_retry["status"] == "error"
    assert clear_retry["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_updates_future_series_scalar_fields() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_scalar_update_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="",
        expected_notes="",
        title="Synthetic future series event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Future Room",
        notes="Future series notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_scalar_update_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="",
        expected_notes="",
        title="Synthetic future series event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Future Room",
        notes="Future series notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_scalar_update_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_scalar_updated_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["title"] == "Synthetic future series event"
    assert result["read_back"]["location_present"] is True
    assert result["read_back"]["notes_present"] is True


def test_apply_calendar_change_reschedules_future_series() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_rescheduled_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["original_occurrence_verified_absent"] is True
    assert result["read_back"]["future_original_occurrence_verified_absent"] is True
    assert result["read_back"]["start_date"] == "2026-06-03T19:00:00Z"
    assert result["read_back"]["end_date"] == "2026-06-03T20:00:00Z"
    assert result["read_back"]["time_zone"] == "America/New_York"


def test_apply_calendar_change_reschedules_future_series_into_future_slot() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-10T17:00:00Z",
        end_date="2026-06-10T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-10T17:00:00Z",
        end_date="2026-06-10T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_reschedule_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_rescheduled_verified"] is True
    assert result["read_back"]["original_occurrence_verified_absent"] is False
    assert result["read_back"]["future_original_occurrence_verified_absent"] is False
    assert result["read_back"]["original_occurrence_verified_absent_or_replaced"] is True
    assert (
        result["read_back"]["future_original_occurrence_verified_absent_or_replaced"]
        is True
    )
    assert result["read_back"]["start_date"] == "2026-06-10T17:00:00Z"


def test_apply_calendar_change_updates_future_series_availability() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_availability_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_availability_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_availability_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_availability_updated_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["availability"] == 1
    assert result["read_back"]["availability_name"] == "free"


def test_apply_calendar_change_rejects_missing_future_series_availability_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_availability_missing_proof_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_availability_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_availability_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_apply_calendar_change_updates_future_series_event_url() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )["results"][0]["handle"]
    event_url = "https://meet.example.invalid/new-future-series"
    event_url_sha = hashlib.sha256(event_url.encode("utf-8")).hexdigest()
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=event_url,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["future_series_event_url_update_requested"] is True
    assert plan["preview"]["proposed"]["event_url_safe_sha256"] == event_url_sha

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=event_url,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_event_url_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_event_url_updated_verified"] is True
    assert result["read_back"]["event_url_verified"] is True
    assert result["read_back"]["event_url_safe_sha256"] == event_url_sha
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True


def test_apply_calendar_change_clears_future_series_event_url() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current-future-series"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["future_series_event_url_update_requested"] is True
    assert plan["preview"]["proposed"]["event_url_clear_requested"] is True

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_event_url_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_event_url_updated_verified"] is True
    assert result["read_back"]["event_url_cleared_verified"] is True
    assert result["read_back"]["url_present"] is False


def test_apply_calendar_change_rejects_missing_future_series_event_url_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_event_url_missing_proof_runner,
    )["results"][0]["handle"]
    event_url = "https://meet.example.invalid/new-future-series"
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=event_url,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_event_url_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=event_url,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_event_url_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_event_url_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic changed title",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url="https://meet.example.invalid/new-future-series",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_event_url_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"


def test_apply_calendar_change_updates_future_series_structured_location() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )["results"][0]["handle"]
    structured = {
        "title": "Future Conference Room",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius_meters": 25,
    }
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_structured_location_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_scalar_update_requested"] is False
    assert plan["preview"]["proposed"]["structured_location"] == {
        "title": "Future Conference Room",
        "geo_present": True,
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius_meters": 25.0,
    }

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_structured_location_updated_verified"] is True
    assert result["read_back"]["structured_location_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True


def test_apply_calendar_change_clears_future_series_structured_location() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )["results"][0]["handle"]
    expected_structured = {"title": "Synthetic Current Room"}
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_structured_location_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["structured_location_clear_requested"] is True

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_structured_location_updated_verified"] is True
    assert result["read_back"]["structured_location_cleared_verified"] is True
    assert result["read_back"]["structured_location_present"] is False
    assert result["read_back"]["location_present"] is False


def test_apply_calendar_change_rejects_missing_future_series_structured_location_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_structured_location_missing_proof_runner,
    )["results"][0]["handle"]
    structured = {
        "title": "Future Conference Room",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius_meters": 25,
    }
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_structured_location_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_structured_location_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_structured_location_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic changed title",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location={"title": "Future Conference Room"},
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_structured_location_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"


def test_apply_calendar_change_updates_future_series_display_alarm() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_display_alarm_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_scalar_update_requested"] is False
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == [-10]

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_display_alarm_updated_verified"] is True
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True


def test_apply_calendar_change_clears_future_series_display_alarm() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_display_alarm_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == []

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_display_alarm_updated_verified"] is True
    assert result["read_back"]["alarm_offsets_minutes"] == []
    assert result["read_back"]["alarms_count"] == 0


def test_apply_calendar_change_rejects_missing_future_series_display_alarm_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_display_alarm_missing_proof_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_display_alarm_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_display_alarm_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_display_alarm_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic changed title",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_display_alarm_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"


def test_apply_calendar_change_updates_future_series_action_alarm() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_action_alarm_update_requested"
    ] is True
    assert plan["preview"]["proposed"][
        "future_series_display_alarm_update_requested"
    ] is False
    assert plan["preview"]["proposed"]["future_series_scalar_update_requested"] is False
    assert plan["preview"]["proposed"]["alarm_sound_name"] == "Glass"
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == [-10]
    assert "alarm_email_address" not in plan["preview"]["proposed"]

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_action_alarm_updated_verified"] is True
    assert result["read_back"]["alarm_sound_name"] == "Glass"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert "alarm_email_address" not in result["read_back"]


def test_apply_calendar_change_clears_future_series_action_alarm() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_sound_name="Glass",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_action_alarm_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["alarm_sound_name"] == ""
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == []

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_sound_name="Glass",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[],
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_action_alarm_updated_verified"] is True
    assert result["read_back"]["alarm_sound_name"] == ""
    assert result["read_back"]["alarm_offsets_minutes"] == []
    assert result["read_back"]["alarms_count"] == 0


def test_apply_calendar_change_rejects_missing_future_series_action_alarm_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_action_alarm_missing_proof_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_action_alarm_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_action_alarm_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_action_alarm_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        event_url="https://example.com/synthetic",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"


def test_plan_calendar_change_update_future_series_action_alarm_excludes_title_mutation() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic changed title",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Synthetic Room",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_action_alarm_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"
    assert "action-alarm update cannot co-mutate title or notes" in result["warnings"][0][
        "message"
    ]


def test_apply_calendar_change_updates_future_series_all_day() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_reschedule_requested"] is False
    assert plan["preview"]["proposed"]["future_series_scalar_update_requested"] is False
    assert plan["preview"]["proposed"]["all_day"] is True
    assert plan["preview"]["proposed"]["date_only_input"] is True

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_all_day_updated_verified"] is True
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-03"
    assert result["read_back"]["end_date"] == "2026-06-04"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["original_occurrence_verified_absent_or_replaced"] is True
    assert result["read_back"][
        "future_original_occurrence_verified_absent_or_replaced"
    ] is True


def test_apply_calendar_change_clears_future_series_all_day() -> None:
    handle = search_calendar_events(
        "all day",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
        all_day=False,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_reschedule_requested"] is False
    assert plan["preview"]["proposed"]["all_day"] is False
    assert plan["preview"]["proposed"]["time_zone_bound"] is True

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
        all_day=False,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_all_day_updated_verified"] is True
    assert result["read_back"]["all_day"] is False
    assert result["read_back"]["time_zone"] == "America/Los_Angeles"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True


def test_apply_calendar_change_reschedules_future_series_all_day_date_only() -> None:
    handle = search_calendar_events(
        "all day",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-06",
        end_date="2026-06-07",
        all_day=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_reschedule_requested"] is False
    assert plan["preview"]["proposed"]["all_day"] is True

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-06",
        end_date="2026-06-07",
        all_day=True,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_all_day_updated_verified"] is True
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-06"
    assert result["read_back"]["end_date"] == "2026-06-07"
    assert result["read_back"]["original_occurrence_verified_absent_or_replaced"] is True
    assert result["read_back"][
        "future_original_occurrence_verified_absent_or_replaced"
    ] is True


def test_apply_calendar_change_rejects_missing_future_series_all_day_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_missing_proof_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_all_day_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_all_day_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        event_url="https://example.com/synthetic",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"


def test_plan_calendar_change_update_future_series_all_day_excludes_title_mutation() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic changed title",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"
    assert "all-day update cannot co-mutate title or notes" in result["warnings"][0][
        "message"
    ]


def test_plan_calendar_change_future_series_all_day_requires_date_only() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert "date-only start_date and end_date" in result["warnings"][0]["message"]


def test_plan_calendar_change_future_series_all_day_clear_requires_time_zone() -> None:
    handle = search_calendar_events(
        "all day",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        all_day=False,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert "explicit time_zone" in result["warnings"][0]["message"]


def test_plan_calendar_change_future_series_all_day_flip_excludes_timed_reschedule() -> None:
    handle = search_calendar_events(
        "all day",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
        all_day=False,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_change_runner,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    future_series_flags = [
        proposed["future_series_scalar_update_requested"],
        proposed["future_series_reschedule_requested"],
        proposed["future_series_availability_update_requested"],
        proposed["future_series_event_url_update_requested"],
        proposed["future_series_structured_location_update_requested"],
        proposed["future_series_display_alarm_update_requested"],
        proposed["future_series_action_alarm_update_requested"],
        proposed["future_series_all_day_update_requested"],
    ]
    assert future_series_flags.count(True) == 1
    assert proposed["future_series_all_day_update_requested"] is True
    assert proposed["future_series_reschedule_requested"] is False


def test_plan_calendar_change_future_series_all_day_set_requires_expected_time_zone() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert "expected_time_zone" in result["warnings"][0]["message"]


def test_apply_calendar_change_reschedules_future_series_all_day_across_dst_boundary() -> None:
    handle = search_calendar_events(
        "all day",
        eventkit_runner=_recurring_future_series_all_day_dst_reschedule_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-11-06",
        end_date="2026-11-07",
        all_day=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_all_day_dst_reschedule_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True
    assert plan["preview"]["proposed"]["future_series_reschedule_requested"] is False
    assert plan["preview"]["proposed"]["start_date"] == "2026-11-06"
    assert plan["preview"]["proposed"]["end_date"] == "2026-11-07"
    assert plan["preview"]["proposed"]["date_only_input"] is True
    assert plan["preview"]["target"]["expected_state"]["start_date"] == "2026-06-05"
    assert plan["preview"]["target"]["expected_state"]["end_date"] == "2026-06-06"

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-11-06",
        end_date="2026-11-07",
        all_day=True,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_all_day_dst_reschedule_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["future_series_all_day_updated_verified"] is True
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-11-06"
    assert result["read_back"]["end_date"] == "2026-11-07"
    assert result["read_back"]["original_occurrence_verified_absent_or_replaced"] is True
    assert result["read_back"][
        "future_original_occurrence_verified_absent_or_replaced"
    ] is True


def test_apply_calendar_change_moves_future_series_to_exact_calendar() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _recurring_future_series_calendar_move_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=recording_runner)[
        "results"
    ][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=recording_runner,
    )["results"][0]["handle"]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=recording_runner,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["future_series_calendar_move_requested"] is True
    assert proposed["future_series_scalar_update_requested"] is False
    assert proposed["future_series_reschedule_requested"] is False
    assert proposed["future_series_availability_update_requested"] is False
    assert proposed["future_series_event_url_update_requested"] is False
    assert proposed["future_series_structured_location_update_requested"] is False
    assert proposed["future_series_display_alarm_update_requested"] is False
    assert proposed["future_series_action_alarm_update_requested"] is False
    assert proposed["future_series_all_day_update_requested"] is False
    assert proposed["selected_occurrence_calendar_move_requested"] is False
    assert proposed["target_calendar_handle"] == target_calendar_handle
    assert proposed["target_calendar_verified"] is True
    assert proposed["target_calendar_allows_content_modifications"] is True
    assert proposed["target_calendar_title"] == "Synthetic Focus"

    result = apply_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["future_series_calendar_move_verified"] is True
    assert result["read_back"]["previous_occurrence_calendar_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["future_occurrence_updated_verified"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["calendar_title"] == "Synthetic Focus"
    assert result["read_back"]["target_calendar_handle"] == target_calendar_handle
    assert result["read_back"]["target_calendar_verified"] is True
    apply_payload = [
        call for call in calls if call["command"] == "calendar_apply_change"
    ][-1]
    assert apply_payload["target_calendar_id"] == "calendar-2"
    assert apply_payload["recurrence_update_scope"] == "future_events"


def test_apply_calendar_change_rejects_missing_future_series_calendar_move_proof() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_calendar_move_missing_proof_runner,
    )["results"][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_future_series_calendar_move_missing_proof_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_calendar_move_missing_proof_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_future_series_calendar_move_missing_proof_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "future_series_update_read_back_mismatch"


def test_plan_calendar_change_update_future_series_calendar_move_rejects_co_mutations() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        event_url="https://example.com/synthetic",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"
    assert "target-calendar move cannot co-mutate event URL" in result["warnings"][0][
        "message"
    ]


def test_plan_calendar_change_update_future_series_calendar_move_excludes_title_mutation() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic changed title",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"
    assert "target-calendar move cannot co-mutate title, plain location, or notes" in result[
        "warnings"
    ][0]["message"]


def test_plan_calendar_change_update_future_series_calendar_move_excludes_timed_mutation() -> None:
    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_future_series_update_shape"
    assert "target-calendar move cannot co-mutate timed or availability fields" in result[
        "warnings"
    ][0]["message"]


def test_plan_calendar_change_future_series_calendar_move_scope_routing_regression() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)[
        "results"
    ][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_update_runner,
    )["results"][0]["handle"]

    selected_plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert selected_plan["status"] == "ok"
    selected_proposed = selected_plan["preview"]["proposed"]
    assert selected_proposed["selected_occurrence_calendar_move_requested"] is True
    assert not selected_proposed.get("future_series_calendar_move_requested")

    future_plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        location="Synthetic Room",
        notes="Synthetic event notes.",
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_future_series_calendar_move_runner,
    )

    assert future_plan["status"] == "ok"
    future_proposed = future_plan["preview"]["proposed"]
    assert future_proposed["future_series_calendar_move_requested"] is True
    assert future_proposed["selected_occurrence_calendar_move_requested"] is False
    future_series_shape_flags = [
        future_proposed["future_series_scalar_update_requested"],
        future_proposed["future_series_reschedule_requested"],
        future_proposed["future_series_availability_update_requested"],
        future_proposed["future_series_event_url_update_requested"],
        future_proposed["future_series_structured_location_update_requested"],
        future_proposed["future_series_display_alarm_update_requested"],
        future_proposed["future_series_action_alarm_update_requested"],
        future_proposed["future_series_all_day_update_requested"],
        future_proposed["future_series_calendar_move_requested"],
    ]
    assert future_series_shape_flags.count(True) == 1


def test_apply_calendar_change_replaces_mid_series_recurrence_with_unbounded_rule() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_mid_series_replace_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_unbounded=True,
        recurrence_update_scope="future-events",
        eventkit_runner=_recurring_mid_series_replace_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_unbounded=True,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_mid_series_replace_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_update_scope"] == "future_events"
    assert result["read_back"]["recurrence_replaced_verified"] is True
    assert result["read_back"]["future_occurrence_verified_present"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    assert result["read_back"]["recurrence"] == {
        "frequency": "daily",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }


def test_apply_calendar_change_clears_recurrence_with_end_date_series_proof() -> None:
    calls: list[dict[str, Any]] = []
    recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": "2026-08-01T17:00:00.000Z",
        "recurrence_present": True,
    }

    def clear_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        if payload["command"] != "calendar_apply_change":
            result = _recurring_all_delete_runner(payload, timeout)
            if "events" in result:
                for event in result["events"]:
                    event["recurrence_present"] = True
                    event["recurrence"] = recurrence
            if "event" in result:
                result["event"]["recurrence_present"] = True
                result["event"]["recurrence"] = recurrence
            return result
        assert payload["expected_recurrence"] == recurrence
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "time_zone": "",
                "all_day": False,
                "availability": 0,
                "availability_name": "busy",
                "location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence": {
                    "frequency": "",
                    "interval": 0,
                    "count": 0,
                    "recurrence_present": False,
                },
                "recurrence_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {
                "recurrence_cleared_verified": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_absent": True,
            },
            "warnings": [],
        }

    handle = search_calendar_events("planning", eventkit_runner=clear_runner)["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        eventkit_runner=clear_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=clear_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_present"] is False
    assert calls[-1]["clear_recurrence"] is True


def test_apply_calendar_change_updates_selected_recurring_occurrence_scalars() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic occurrence update",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Updated Room",
        notes="Updated occurrence notes.",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic occurrence update",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        location="Updated Room",
        notes="Updated occurrence notes.",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is True
    assert plan["preview"]["target"]["expected_state"]["recurrence"]["frequency"] == "weekly"
    assert plan["preview"]["proposed"]["recurrence_update_scope"] == "this_event"
    assert plan["preview"]["proposed"]["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_start_date"]
        == "2026-06-10T17:00:00.000Z"
    )
    assert result["status"] == "ok"
    assert result["read_back"]["title"] == "Synthetic occurrence update"
    assert result["read_back"]["location_present"] is True
    assert result["read_back"]["notes_present"] is True
    assert result["read_back"]["recurrence_update_scope"] == "this_event"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True


def test_apply_calendar_change_updates_selected_recurring_occurrence_all_day() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["all_day"] is True
    assert plan["preview"]["proposed"]["all_day_update_requested"] is True
    assert plan["preview"]["proposed"]["date_only_input"] is True
    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-03"
    assert result["read_back"]["end_date"] == "2026-06-04"
    assert result["read_back"]["all_day_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True


def test_apply_calendar_change_clears_selected_recurring_occurrence_all_day() -> None:
    handle = search_calendar_events("all day", eventkit_runner=_recurring_all_day_update_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
        all_day=False,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_all_day_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        time_zone="America/Los_Angeles",
        all_day=False,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_all_day_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["all_day"] is False
    assert plan["preview"]["proposed"]["all_day_update_requested"] is True
    assert plan["preview"]["proposed"]["time_zone_bound"] is True
    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is False
    assert result["read_back"]["time_zone"] == "America/Los_Angeles"
    assert result["read_back"]["all_day_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True


def test_apply_calendar_change_reschedules_selected_recurring_occurrence_all_day_date_only() -> None:
    handle = search_calendar_events("all day", eventkit_runner=_recurring_all_day_update_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-06",
        end_date="2026-06-07",
        all_day=True,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_all_day_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-06",
        end_date="2026-06-07",
        all_day=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_all_day_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["all_day"] is True
    assert plan["preview"]["proposed"]["all_day_update_requested"] is False
    assert plan["preview"]["proposed"]["all_day_date_reschedule_requested"] is True
    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-06"
    assert result["read_back"]["end_date"] == "2026-06-07"
    assert result["read_back"]["all_day_verified"] is True
    assert result["read_back"]["selected_occurrence_rescheduled_verified"] is True
    assert result["read_back"]["original_occurrence_verified_absent"] is True


def test_plan_calendar_change_selected_recurring_occurrence_all_day_requires_date_only() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        all_day=True,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_calendar_change_selected_recurring_occurrence_all_day_set_requires_expected_time_zone() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic recurring notes.",
        title="Synthetic recurring event",
        start_date="2026-06-03",
        end_date="2026-06-04",
        all_day=True,
        location="Synthetic Room",
        notes="Synthetic recurring notes.",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert "expected_time_zone" in result["warnings"][0]["message"]


def test_plan_calendar_change_selected_recurring_occurrence_all_day_clear_requires_time_zone() -> None:
    handle = search_calendar_events("all day", eventkit_runner=_recurring_all_day_update_runner)[
        "results"
    ][0]["handle"]

    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day recurring event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        expected_all_day=True,
        title="Synthetic all day recurring event",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        all_day=False,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_all_day_update_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert "time_zone" in result["warnings"][0]["message"]


def test_apply_calendar_change_reschedules_selected_recurring_occurrence() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["start_date"] == "2026-06-03T19:00:00Z"
    assert plan["preview"]["proposed"]["end_date"] == "2026-06-03T20:00:00Z"
    assert plan["preview"]["proposed"]["time_zone"] == "America/New_York"
    assert result["status"] == "ok"
    assert result["read_back"]["start_date"] == "2026-06-03T19:00:00Z"
    assert result["read_back"]["end_date"] == "2026-06-03T20:00:00Z"
    assert result["read_back"]["time_zone"] == "America/New_York"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["selected_occurrence_rescheduled_verified"] is True
    assert result["read_back"]["original_occurrence_verified_absent"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True


def test_apply_calendar_change_moves_selected_recurring_occurrence_to_exact_calendar() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=recording_runner)["results"][0][
        "handle"
    ]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=recording_runner,
    )["results"][0]["handle"]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=recording_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["target_calendar_handle"] == target_calendar_handle
    assert (
        plan["preview"]["proposed"]["selected_occurrence_calendar_move_requested"] is True
    )
    assert result["status"] == "ok"
    assert result["read_back"]["calendar_title"] == "Synthetic Focus"
    assert result["read_back"]["target_calendar_handle"] == target_calendar_handle
    assert result["read_back"]["target_calendar_verified"] is True
    assert result["read_back"]["selected_occurrence_calendar_move_verified"] is True
    assert result["read_back"]["adjacent_occurrence_calendar_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    apply_payload = [
        call for call in calls if call["command"] == "calendar_apply_change"
    ][-1]
    assert apply_payload["target_calendar_id"] == "calendar-2"
    assert apply_payload["recurrence_update_scope"] == "this_event"


def test_plan_calendar_change_selected_occurrence_calendar_move_resolves_target() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)[
        "results"
    ][0]["handle"]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=_recurring_update_runner,
    )["results"][0]["handle"]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["selected_occurrence_calendar_move_requested"] is True
    assert proposed["target_calendar_handle"] == target_calendar_handle
    assert proposed["target_calendar_verified"] is True
    assert proposed["target_calendar_allows_content_modifications"] is True
    assert proposed["target_calendar_title"] == "Synthetic Focus"


def test_plan_calendar_change_selected_occurrence_calendar_move_rejects_stale_target() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)[
        "results"
    ][0]["handle"]
    stale_target = make_opaque_handle("calendar:calendar", "missing-calendar")

    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=stale_target,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "target_calendar_not_found"
    assert plan["preview"] is None


def test_plan_calendar_change_selected_occurrence_calendar_move_requires_writable_target() -> None:
    def non_writable_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_calendars":
            for calendar in response["calendars"]:
                if calendar["calendar_id"] == "calendar-2":
                    calendar["allows_content_modifications"] = False
        return response

    handle = search_calendar_events("planning", eventkit_runner=non_writable_runner)["results"][0][
        "handle"
    ]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=non_writable_runner,
    )["results"][0]["handle"]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=non_writable_runner,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "target_calendar_not_writable"
    assert plan["preview"] is None


def test_apply_calendar_change_selected_occurrence_calendar_move_requires_adjacent_calendar_proof() -> None:
    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("read_back"):
            response = {
                **response,
                "read_back": {
                    **response["read_back"],
                    "adjacent_occurrence_calendar_verified": False,
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=mismatch_runner)["results"][0][
        "handle"
    ]
    target_calendar_handle = search_calendar_calendars(
        "Focus",
        eventkit_runner=mismatch_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "adjacent_occurrence_calendar_read_back_mismatch"


def test_apply_calendar_change_updates_selected_recurring_occurrence_availability() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["expected_state"]["availability"] == 0
    assert plan["preview"]["proposed"]["availability"] == 1
    assert result["status"] == "ok"
    assert result["read_back"]["availability"] == 1
    assert result["read_back"]["availability_name"] == "free"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    assert "selected_occurrence_rescheduled_verified" not in result["read_back"]


def test_apply_calendar_change_selected_recurring_occurrence_availability_mismatch_fails_unknown() -> None:
    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {
                **response,
                "event": {
                    **response["event"],
                    "availability": 0,
                    "availability_name": "busy",
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=mismatch_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        recurrence_update_scope="this-event",
        eventkit_runner=mismatch_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "availability_read_back_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_availability_support_mask_refusal() -> None:
    def unsupported_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change" and payload.get("availability") == 3:
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "availability_not_supported",
                        "message": "Calendar target does not support the requested availability value.",
                    }
                ],
            }
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=unsupported_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="unavailable",
        recurrence_update_scope="this-event",
        eventkit_runner=unsupported_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="unavailable",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=unsupported_runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "availability_not_supported"


def test_apply_calendar_change_updates_selected_recurring_occurrence_event_url() -> None:
    url = "mailto:selected-occurrence@example.invalid"
    expected_sha = hashlib.sha256(url.encode("utf-8")).hexdigest()
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["event_url_requested"] is True
    assert plan["preview"]["proposed"]["event_url_scheme"] == "mailto"
    assert plan["preview"]["proposed"]["event_url_domain"] == ""
    assert plan["preview"]["proposed"]["event_url_safe_sha256"] == expected_sha
    assert plan["preview"]["proposed"]["adjacent_occurrence_event_url_present"] is False
    assert plan["preview"]["proposed"]["adjacent_occurrence_event_url_safe_sha256"] == ""
    assert "event_url" not in plan["preview"]["proposed"]
    assert result["status"] == "ok"
    assert result["read_back"]["url_present"] is True
    assert result["read_back"]["event_url_safe_sha256"] == expected_sha
    assert result["read_back"]["event_url_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    assert result["read_back"]["adjacent_occurrence_event_url_verified"] is True
    assert "event_url" not in result["read_back"]


def test_apply_calendar_change_clears_selected_recurring_occurrence_event_url() -> None:
    expected_url = "https://meet.example.invalid/current?id=selected-occurrence"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["expected_state"]["event_url_present"] is True
    assert plan["preview"]["target"]["expected_state"]["event_url_safe_sha256"] == expected_sha
    assert plan["preview"]["proposed"]["event_url_clear_requested"] is True
    assert plan["preview"]["proposed"]["adjacent_occurrence_event_url_present"] is False
    assert plan["preview"]["proposed"]["adjacent_occurrence_event_url_safe_sha256"] == ""
    assert result["status"] == "ok"
    assert result["read_back"]["url_present"] is False
    assert result["read_back"]["event_url_cleared_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    assert result["read_back"]["adjacent_occurrence_event_url_verified"] is True


def test_apply_calendar_change_updates_selected_recurring_occurrence_structured_location() -> None:
    structured = {
        "title": "Synthetic Selected Room",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25,
    }
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["recurrence_update_scope"] == "this_event"
    assert plan["preview"]["proposed"]["structured_location_requested"] is True
    assert plan["preview"]["proposed"]["location"] == "Synthetic Selected Room"
    assert plan["preview"]["target"]["expected_state"]["structured_location_present"] is False
    assert plan["preview"]["target"]["expected_state"]["structured_location_present_bound"] is True
    assert plan["preview"]["proposed"]["adjacent_occurrence_location_present"] is True
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_location_safe_sha256"]
        == DEFAULT_EVENT_LOCATION_SHA256
    )
    assert plan["preview"]["proposed"]["adjacent_occurrence_structured_location_present"] is False
    assert plan["preview"]["proposed"]["adjacent_occurrence_structured_location_safe_sha256"] == ""
    assert apply_payload["expected_structured_location_present"] is False
    assert apply_payload["adjacent_occurrence_location_present"] is True
    assert apply_payload["adjacent_occurrence_location_sha256"] == DEFAULT_EVENT_LOCATION_SHA256
    assert result["status"] == "ok"
    assert result["read_back"]["structured_location_verified"] is True
    assert result["read_back"]["structured_location"] == {
        "title": "Synthetic Selected Room",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25.0,
    }
    assert result["read_back"]["location_present"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    assert result["read_back"]["adjacent_occurrence_location_verified"] is True


def test_apply_calendar_change_replaces_selected_recurring_occurrence_structured_location() -> None:
    expected_structured = {"title": "Synthetic Selected Room"}
    structured = {"title": "Synthetic Replacement Room"}
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_adjacent_location_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["expected_state"]["structured_location"] == {
        "title": "Synthetic Selected Room",
        "geo_present": False,
    }
    assert plan["preview"]["target"]["expected_state"]["structured_location_present"] is True
    assert plan["preview"]["target"]["expected_state"]["structured_location_present_bound"] is True
    assert plan["preview"]["proposed"]["structured_location"] == {
        "title": "Synthetic Replacement Room",
        "geo_present": False,
    }
    assert plan["preview"]["proposed"]["adjacent_occurrence_location_present"] is True
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_location_safe_sha256"]
        == ADJACENT_OCCURRENCE_LOCATION_SHA256
    )
    assert plan["preview"]["proposed"]["adjacent_occurrence_structured_location_present"] is True
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_structured_location_safe_sha256"]
        == ADJACENT_OCCURRENCE_STRUCTURED_LOCATION_SHA256
    )
    assert apply_payload["expected_structured_location_present"] is True
    assert (
        apply_payload["adjacent_occurrence_structured_location_sha256"]
        == ADJACENT_OCCURRENCE_STRUCTURED_LOCATION_SHA256
    )
    assert result["status"] == "ok"
    assert result["read_back"]["structured_location_verified"] is True
    assert result["read_back"]["adjacent_occurrence_location_verified"] is True


def test_apply_calendar_change_clears_selected_recurring_occurrence_structured_location() -> None:
    expected_structured = {"title": "Synthetic Selected Room"}
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["expected_state"]["structured_location"] == {
        "title": "Synthetic Selected Room",
        "geo_present": False,
    }
    assert plan["preview"]["target"]["expected_state"]["structured_location_present"] is True
    assert plan["preview"]["target"]["expected_state"]["structured_location_present_bound"] is True
    assert plan["preview"]["proposed"]["structured_location_clear_requested"] is True
    assert apply_payload["expected_structured_location_present"] is True
    assert result["status"] == "ok"
    assert result["read_back"]["structured_location_present"] is False
    assert result["read_back"]["location_present"] is False
    assert result["read_back"]["structured_location_cleared_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True


def test_apply_calendar_change_selected_recurring_occurrence_structured_location_mismatch_fails_unknown() -> None:
    structured = {"title": "Synthetic Selected Room"}

    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {
                **response,
                "event": {
                    **response["event"],
                    "structured_location_present": True,
                    "structured_location": {
                        "title": "Different Room",
                        "geo_present": False,
                    },
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=mismatch_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        eventkit_runner=mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "structured_location_read_back_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_structured_location_clear_mismatch_fails_unknown() -> None:
    expected_structured = {"title": "Synthetic Selected Room"}

    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {
                **response,
                "event": {
                    **response["event"],
                    "location_present": True,
                    "structured_location_present": True,
                    "structured_location": {
                        "title": "Synthetic Selected Room",
                        "geo_present": False,
                    },
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=mismatch_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        recurrence_update_scope="this-event",
        eventkit_runner=mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "structured_location_clear_read_back_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_structured_location_stale_absence_fails_before_apply() -> None:
    structured = {"title": "Synthetic Selected Room"}
    apply_payloads: list[dict[str, Any]] = []

    def stale_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payloads.append(payload)
            if payload.get("expected_structured_location_present") is False:
                return {
                    "schema_version": 1,
                    "status": "error",
                    "source": "calendar",
                    "authorization_status": "authorized",
                    "warnings": [
                        {
                            "code": "expected_state_mismatch",
                            "message": "Calendar event did not match expected structured location state.",
                        }
                    ],
                }
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=stale_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        eventkit_runner=stale_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=stale_runner,
    )

    assert apply_payloads
    assert apply_payloads[-1]["expected_structured_location_present"] is False
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_event_url_mismatch_fails_unknown() -> None:
    url = "https://meet.example.invalid/runtime?id=selected-occurrence"

    def mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {
                **response,
                "event": {
                    **response["event"],
                    "url_present": True,
                    "event_url_safe_sha256": "0" * 64,
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=mismatch_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        eventkit_runner=mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "event_url_read_back_mismatch"


def test_apply_calendar_change_replaces_selected_recurring_occurrence_event_url() -> None:
    current_url = "https://meet.example.invalid/current?id=selected-occurrence"
    current_sha = hashlib.sha256(current_url.encode("utf-8")).hexdigest()
    proposed_url = "https://meet.example.invalid/replacement?id=selected-occurrence"
    proposed_sha = hashlib.sha256(proposed_url.encode("utf-8")).hexdigest()
    apply_payload: dict[str, Any] = {}

    def replacement_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=replacement_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=current_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=proposed_url,
        recurrence_update_scope="this-event",
        eventkit_runner=replacement_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=current_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=proposed_url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=replacement_runner,
    )

    assert result["status"] == "ok"
    assert apply_payload["expected_event_url_present"] is True
    assert apply_payload["expected_event_url_sha256"] == current_sha
    assert result["read_back"]["event_url_safe_sha256"] == proposed_sha
    assert result["read_back"]["event_url_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_event_url_preserves_adjacent_url() -> None:
    url = "https://meet.example.invalid/runtime?id=selected-occurrence-adjacent-url"
    expected_sha = hashlib.sha256(url.encode("utf-8")).hexdigest()
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_adjacent_url_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["event_url_safe_sha256"] == expected_sha
    assert plan["preview"]["proposed"]["adjacent_occurrence_event_url_present"] is True
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_event_url_safe_sha256"]
        == ADJACENT_OCCURRENCE_EVENT_URL_SHA256
    )
    assert apply_payload["adjacent_occurrence_event_url_present"] is True
    assert (
        apply_payload["adjacent_occurrence_event_url_sha256"]
        == ADJACENT_OCCURRENCE_EVENT_URL_SHA256
    )
    assert result["status"] == "ok"
    assert result["read_back"]["event_url_safe_sha256"] == expected_sha
    assert result["read_back"]["event_url_verified"] is True
    assert result["read_back"]["adjacent_occurrence_event_url_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_event_url_refuses_stale_adjacent_url() -> None:
    url = "https://meet.example.invalid/runtime?id=selected-occurrence-stale-adjacent"
    stale_sha = "1" * 64
    apply_payloads: list[dict[str, Any]] = []
    state = {"calendar_events": 0}

    def stale_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            state["calendar_events"] += 1
            result = _recurring_update_runner(payload, timeout)
            adjacent_sha = (
                ADJACENT_OCCURRENCE_EVENT_URL_SHA256
                if state["calendar_events"] == 1
                else stale_sha
            )
            for event in result.get("events", []):
                if event.get("start_date") == "2026-06-10T17:00:00.000Z":
                    event["url_present"] = True
                    event["event_url_safe_sha256"] = adjacent_sha
            return result
        if payload["command"] == "calendar_apply_change":
            apply_payloads.append(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events(
        "planning",
        eventkit_runner=_recurring_update_adjacent_url_runner,
    )["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_adjacent_url_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=False,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=stale_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "stale_occurrence_identity"
    assert apply_payloads == []


def test_apply_calendar_change_selected_recurring_occurrence_event_url_clear_mismatch_fails_unknown() -> None:
    expected_url = "https://meet.example.invalid/current?id=selected-occurrence"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()

    def clear_mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and response.get("event"):
            response = {
                **response,
                "event": {
                    **response["event"],
                    "url_present": True,
                    "event_url_safe_sha256": expected_sha,
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=clear_mismatch_runner)["results"][
        0
    ]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        recurrence_update_scope="this-event",
        eventkit_runner=clear_mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_event_url=True,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=clear_mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "event_url_clear_read_back_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_adjacent_event_url_mismatch_fails_unknown() -> None:
    url = "https://meet.example.invalid/runtime?id=selected-occurrence"

    def adjacent_mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and isinstance(
            response.get("read_back"),
            dict,
        ):
            response = {
                **response,
                "read_back": {
                    **response["read_back"],
                    "adjacent_occurrence_event_url_verified": False,
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=adjacent_mismatch_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        eventkit_runner=adjacent_mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        event_url=url,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=adjacent_mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "adjacent_occurrence_event_url_read_back_mismatch"


def test_apply_calendar_change_selected_recurring_occurrence_adjacent_location_mismatch_fails_unknown() -> None:
    structured = {"title": "Synthetic Selected Room"}

    def adjacent_mismatch_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _recurring_update_adjacent_location_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change" and isinstance(
            response.get("read_back"),
            dict,
        ):
            response = {
                **response,
                "read_back": {
                    **response["read_back"],
                    "adjacent_occurrence_location_verified": False,
                },
            }
        return response

    handle = search_calendar_events("planning", eventkit_runner=adjacent_mismatch_runner)[
        "results"
    ][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        eventkit_runner=adjacent_mismatch_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        structured_location=structured,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=adjacent_mismatch_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "adjacent_occurrence_location_read_back_mismatch"


def test_apply_calendar_change_reschedules_selected_recurring_occurrence_end_only() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:30:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:30:00Z",
        time_zone="America/Los_Angeles",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "ok"
    assert result["read_back"]["start_date"] == "2026-06-03T17:00:00Z"
    assert result["read_back"]["end_date"] == "2026-06-03T18:30:00Z"
    assert result["read_back"]["selected_occurrence_rescheduled_verified"] is True
    assert result["read_back"]["original_occurrence_verified_absent"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True


def test_plan_calendar_change_rejects_selected_recurring_occurrence_reschedule_without_time_zone() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:30:00Z",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert result["preview"] is None


def test_plan_calendar_change_rejects_selected_recurring_occurrence_availability_without_expected_state() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        availability="free",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"
    assert result["preview"] is None


def test_apply_calendar_change_selected_recurring_occurrence_time_zone_only_does_not_claim_absence() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/New_York",
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        time_zone="America/New_York",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "ok"
    assert result["read_back"]["time_zone"] == "America/New_York"
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert "selected_occurrence_rescheduled_verified" not in result["read_back"]
    assert "original_occurrence_verified_absent" not in result["read_back"]


def test_apply_calendar_change_updates_selected_recurring_occurrence_alarm_offsets() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["display_alarm_update_requested"] is True
    assert apply_payload["expected_alarm_offsets_minutes"] == []
    assert apply_payload["alarm_offsets_minutes"] == [-30]
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-30]
    assert result["read_back"]["alarms_count"] == 1
    assert result["read_back"]["display_alarm_verified"] is True
    assert result["read_back"]["selected_occurrence_updated_verified"] is True
    assert result["read_back"]["adjacent_occurrence_location_verified"] is True
    assert result["read_back"]["adjacent_occurrence_alarm_verified"] is True
    assert plan["preview"]["proposed"]["adjacent_occurrence_alarm_state_present"] is False
    assert plan["preview"]["proposed"]["adjacent_occurrence_alarm_state_safe_sha256"] == ""
    assert apply_payload["adjacent_occurrence_alarm_state_present"] is False
    assert apply_payload["adjacent_occurrence_alarm_state_sha256"] == ""


def test_apply_calendar_change_updates_selected_recurring_occurrence_absolute_alarm() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_absolute_dates=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_absolute_dates=["2026-06-03T16:45:00Z"],
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_absolute_dates=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_absolute_dates=["2026-06-03T16:45:00Z"],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert apply_payload["expected_alarm_absolute_dates"] == []
    assert apply_payload["alarm_absolute_dates"] == ["2026-06-03T16:45:00Z"]
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_absolute_dates"] == ["2026-06-03T16:45:00Z"]
    assert result["read_back"]["display_alarm_verified"] is True
    assert result["read_back"]["adjacent_occurrence_alarm_verified"] is True


def test_apply_calendar_change_clears_selected_recurring_occurrence_alarm_offsets() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[],
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert apply_payload["expected_alarm_offsets_minutes"] == [-10]
    assert apply_payload["alarm_offsets_minutes"] == []
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == []
    assert result["read_back"]["alarms_count"] == 0
    assert result["read_back"]["display_alarm_verified"] is True
    assert result["read_back"]["adjacent_occurrence_alarm_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_omitted_alarm_preserves_expected_offsets() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic renamed occurrence",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        title="Synthetic renamed occurrence",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["display_alarm_update_requested"] is False
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == [-10]
    assert apply_payload["expected_alarm_offsets_minutes"] == [-10]
    assert apply_payload["alarm_offsets_minutes"] == [-10]
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert "display_alarm_verified" not in result["read_back"]
    assert result["read_back"]["adjacent_occurrence_alarm_verified"] is True


def test_apply_calendar_change_updates_selected_recurring_occurrence_alarm_preserves_adjacent_alarm_state() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_adjacent_alarm_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert (
        plan["preview"]["proposed"]["adjacent_occurrence_alarm_state_safe_sha256"]
        == ADJACENT_OCCURRENCE_ALARM_STATE_SHA256
    )
    assert plan["preview"]["proposed"]["adjacent_occurrence_alarm_state_present"] is True
    assert apply_payload["adjacent_occurrence_alarm_state_present"] is True
    assert (
        apply_payload["adjacent_occurrence_alarm_state_sha256"]
        == ADJACENT_OCCURRENCE_ALARM_STATE_SHA256
    )
    assert result["status"] == "ok"
    assert result["read_back"]["adjacent_occurrence_alarm_verified"] is True
    assert result["read_back"]["display_alarm_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_adjacent_alarm_read_back_mismatch_is_unknown() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _recurring_update_adjacent_alarm_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            result["read_back"]["adjacent_occurrence_alarm_verified"] = False
        return result

    handle = search_calendar_events("planning", eventkit_runner=mismatched_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        eventkit_runner=mismatched_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[],
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-30],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "adjacent_occurrence_alarm_read_back_mismatch"


def test_apply_calendar_change_updates_selected_recurring_occurrence_audio_alarm() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_sound_name="Glass",
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_sound_name="Glass",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["alarm_action_update_requested"] is True
    assert plan["preview"]["proposed"]["selected_occurrence_alarm_update_requested"] is True
    assert apply_payload["selected_occurrence_alarm_update_requested"] is True
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-15]
    assert result["read_back"]["alarm_sound_name"] == "Glass"
    assert result["read_back"]["alarm_action"] == "audio"
    assert result["read_back"]["alarm_action_verified"] is True


def test_apply_calendar_change_updates_selected_recurring_occurrence_email_alarm_without_echo() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_email_address="agent@example.com",
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_email_address="agent@example.com",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )
    expected_sha = hashlib.sha256(b"agent@example.com").hexdigest()

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert apply_payload["alarm_email_address"] == "agent@example.com"
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_email_address_sha256"] == expected_sha
    assert result["read_back"]["alarm_action"] == "email"
    assert result["read_back"]["alarm_action_verified"] is True
    serialized = json.dumps(result, sort_keys=True)
    assert "agent@example.com" not in serialized


def test_apply_calendar_change_updates_selected_recurring_occurrence_geofence_alarm() -> None:
    apply_payload: dict[str, Any] = {}

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]
    location = {"title": "Synthetic Gate", "geo_present": False}

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert apply_payload["alarm_proximity"] == "enter"
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_proximity"] == "enter"
    assert result["read_back"]["alarm_structured_location"] == location
    assert result["read_back"]["alarm_action"] == "geofence"
    assert result["read_back"]["alarm_action_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_omitted_alarm_preserves_expected_email() -> None:
    apply_payload: dict[str, Any] = {}
    expected_sha = hashlib.sha256(b"agent@example.com").hexdigest()

    def capture_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_apply_change":
            apply_payload.update(payload)
        return _recurring_update_runner(payload, timeout)

    handle = search_calendar_events("planning", eventkit_runner=capture_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_email_address_sha256=expected_sha,
        title="Synthetic renamed occurrence",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
        eventkit_runner=capture_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_email_address_sha256=expected_sha,
        title="Synthetic renamed occurrence",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=capture_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["selected_occurrence_alarm_update_requested"] is False
    assert plan["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert apply_payload["selected_occurrence_alarm_update_requested"] is False
    assert apply_payload["alarm_email_address"] == ""
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_email_address_sha256"] == expected_sha
    assert result["read_back"]["alarm_action"] == "email"
    assert "alarm_action_verified" not in result["read_back"]


def test_apply_calendar_change_selected_recurring_occurrence_clears_audio_action_to_display_alarm() -> None:
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_sound_name="Glass",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-10],
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_sound_name="Glass",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-10],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["alarm_action_update_requested"] is True
    assert plan["preview"]["proposed"]["display_alarm_update_requested"] is False
    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-10]
    assert result["read_back"]["alarm_sound_name"] == ""
    assert result["read_back"]["alarm_action"] == "display"
    assert result["read_back"]["alarm_action_verified"] is True
    assert "display_alarm_verified" not in result["read_back"]


def test_apply_calendar_change_selected_recurring_occurrence_clears_email_action_to_display_alarm() -> None:
    expected_sha = hashlib.sha256(b"agent@example.com").hexdigest()
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_email_address_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-10],
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_offsets_minutes=[-10],
        expected_alarm_email_address_sha256=expected_sha,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-10],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["alarm_action_update_requested"] is True
    assert result["status"] == "ok"
    assert result["read_back"].get("alarm_email_address_sha256", "") == ""
    assert result["read_back"]["alarm_action"] == "display"
    assert result["read_back"]["alarm_action_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_clears_geofence_action() -> None:
    location = {"title": "Synthetic Gate", "geo_present": False}
    handle = search_calendar_events("planning", eventkit_runner=_recurring_update_runner)["results"][0][
        "handle"
    ]

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_proximity="enter",
        expected_alarm_structured_location=location,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[],
        recurrence_update_scope="this-event",
        eventkit_runner=_recurring_update_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_alarm_proximity="enter",
        expected_alarm_structured_location=location,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[],
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_update_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["alarm_action_update_requested"] is True
    assert result["status"] == "ok"
    assert result["read_back"].get("alarm_proximity", "") == ""
    assert result["read_back"].get("alarm_structured_location") is None
    assert result["read_back"]["alarm_action"] == "display"
    assert result["read_back"]["alarm_action_verified"] is True


def test_apply_calendar_change_selected_recurring_occurrence_action_alarm_read_back_mismatch_is_unknown() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _recurring_update_runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            result["read_back"]["action_alarm_verified"] = False
        return result

    handle = search_calendar_events("planning", eventkit_runner=mismatched_runner)["results"][0][
        "handle"
    ]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_sound_name="Glass",
        recurrence_update_scope="this-event",
        eventkit_runner=mismatched_runner,
    )
    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        alarm_offsets_minutes=[-15],
        alarm_sound_name="Glass",
        recurrence_update_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "alarm_action_read_back_mismatch"


def test_apply_calendar_change_clear_recurrence_requires_proof_read_back() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] != "calendar_apply_change":
            return _recurring_all_delete_runner(payload, timeout)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": payload["event_id"],
                "title": "Synthetic planning event",
                "calendar_id": "calendar-1",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "all_day": False,
                "availability": 0,
                "location_present": False,
                "notes_present": False,
                "url_present": False,
                "alarm_offsets_minutes": [],
                "alarm_absolute_dates": [],
                "recurrence_present": True,
                "recurrence": {
                    "frequency": "weekly",
                    "interval": 1,
                    "count": 6,
                    "recurrence_present": True,
                },
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "read_back": {"recurrence_cleared_verified": False},
            "warnings": [],
        }

    search = search_calendar_events("planning", eventkit_runner=mismatched_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        eventkit_runner=mismatched_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "recurrence_clear_read_back_mismatch"


def test_apply_calendar_change_recurrence_replacement_requires_proof_read_back() -> None:
    def mismatched_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] != "calendar_apply_change":
            return _recurring_future_delete_runner(payload, timeout)
        result = _recurring_mid_series_replace_runner(payload, timeout)
        result["read_back"] = {"recurrence_replaced_verified": False}
        return result

    search = search_calendar_events("planning", eventkit_runner=mismatched_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_count=4,
        recurrence_update_scope="future-events",
        eventkit_runner=mismatched_runner,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_count=4,
        recurrence_update_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatched_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "recurrence_replacement_read_back_mismatch"


def test_apply_calendar_change_updates_event_url_with_expected_state() -> None:
    calls: list[dict[str, Any]] = []
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()
    proposed_url = "https://meet.example.invalid/new?id=43"
    proposed_sha = hashlib.sha256(proposed_url.encode("utf-8")).hexdigest()

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic updated URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        event_url=proposed_url,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic updated URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        event_url=proposed_url,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["event_url_safe_sha256"] == proposed_sha
    assert result["read_back"]["event_url_verified"] is True
    apply_payload = calls[-1]
    assert apply_payload["expected_event_url_present"] is True
    assert apply_payload["expected_event_url_sha256"] == expected_sha
    assert apply_payload["event_url_requested"] is True
    assert apply_payload["event_url"] == proposed_url


def test_apply_calendar_change_clears_event_url_with_expected_state() -> None:
    calls: list[dict[str, Any]] = []
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["url_present"] is False
    assert result["read_back"]["event_url_cleared_verified"] is True
    apply_payload = calls[-1]
    assert apply_payload["expected_event_url_present"] is True
    assert apply_payload["expected_event_url_sha256"] == expected_sha
    assert apply_payload["event_url_requested"] is False
    assert apply_payload["event_url_clear_requested"] is True
    assert apply_payload["event_url"] == ""


def test_apply_calendar_change_flags_event_url_clear_read_back_mismatch() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()

    def still_has_url_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            response["event"] = {
                **response["event"],
                "url_present": True,
                "event_url_safe_sha256": expected_sha,
            }
        return response

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=still_has_url_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "event_url_clear_read_back_mismatch"


def test_apply_calendar_change_flags_event_url_clear_missing_absence_proof() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()

    def missing_url_presence_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        response = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            response["event"] = {**response["event"]}
            response["event"].pop("url_present", None)
            response["event"].pop("event_url_safe_sha256", None)
        return response

    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=missing_url_presence_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "event_url_clear_read_back_mismatch"


def test_apply_calendar_change_update_recurrence_preserves_existing_recurrence_refusal() -> None:
    def existing_recurrence_runner(
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        if (
            payload["command"] == "calendar_apply_change"
            and payload["operation"] == "update"
        ):
            assert payload["expected_recurrence_present"] is False
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "event": None,
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Calendar event did not match expected recurrence state.",
                    }
                ],
            }
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=existing_recurrence_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=existing_recurrence_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


def test_apply_calendar_change_updates_timed_event_with_time_zone_binding() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        time_zone="America/New_York",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["time_zone"] == "America/New_York"
    apply_payload = calls[-1]
    assert apply_payload["expected_time_zone"] == "America/Los_Angeles"
    assert apply_payload["time_zone"] == "America/New_York"


def test_apply_calendar_change_updates_availability_with_expected_state() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated free event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="free",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated free event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="free",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["availability"] == 1
    assert result["read_back"]["availability_name"] == "free"
    apply_payload = calls[-1]
    assert apply_payload["expected_availability"] == 0
    assert apply_payload["availability"] == 1


def test_apply_calendar_change_update_move_rejects_unsupported_target_availability_without_mutation() -> None:
    calls: list[dict[str, Any]] = []

    def unsupported_move_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        if (
            payload["command"] == "calendar_apply_change"
            and payload.get("target_calendar_id") == "calendar-2"
            and payload.get("availability") == 3
        ):
            return {
                "schema_version": 1,
                "status": "error",
                "source": "calendar",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "availability_not_supported",
                        "message": "Calendar target does not support the requested availability value.",
                    }
                ],
            }
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=unsupported_move_runner)
    event_handle = search["results"][0]["handle"]
    calendars = search_calendar_calendars("Focus", eventkit_runner=unsupported_move_runner)
    target_calendar_handle = calendars["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic moved unavailable event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="unavailable",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_availability="busy",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic moved unavailable event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        availability="unavailable",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=unsupported_move_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "availability_not_supported"
    apply_payload = calls[-1]
    assert apply_payload["target_calendar_id"] == "calendar-2"
    assert apply_payload["expected_availability"] == 0
    assert apply_payload["availability"] == 3


def test_apply_calendar_change_moves_event_to_exact_calendar_handle() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    event_handle = search["results"][0]["handle"]
    calendars = search_calendar_calendars("Focus", eventkit_runner=recording_runner)
    target_calendar_handle = calendars["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
    )

    result = apply_calendar_change(
        "update",
        handle=event_handle,
        target_calendar_handle=target_calendar_handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        location="Synthetic Updated Room",
        notes="Synthetic updated event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["calendar_title"] == "Synthetic Focus"
    assert result["read_back"]["target_calendar_handle"] == target_calendar_handle
    assert result["read_back"]["target_calendar_verified"] is True
    apply_payload = calls[-1]
    assert apply_payload["command"] == "calendar_apply_change"
    assert apply_payload["event_id"] == "event-1"
    assert apply_payload["target_calendar_id"] == "calendar-2"
    assert "calendar-2" not in str(result)


def test_apply_calendar_change_refuses_target_calendar_read_back_mismatch() -> None:
    calendars = search_calendar_calendars("Focus", eventkit_runner=_runner)
    calendar_handle = calendars["results"][0]["handle"]
    plan = plan_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )

    def mismatching_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        result = _runner(payload, timeout)
        if payload["command"] == "calendar_apply_change":
            result["event"]["calendar_id"] = "calendar-1"
            result["event"]["calendar_title"] = "Synthetic Calendar"
        return result

    result = apply_calendar_change(
        "create",
        title="Synthetic handle-targeted event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=mismatching_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "target_calendar_read_back_mismatch"


def test_apply_calendar_change_updates_all_day_event_and_reads_back() -> None:
    search = search_calendar_events("all day", eventkit_runner=_all_day_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day=True,
        title="Synthetic updated all day event",
        start_date="2026-06-07T00:00:00Z",
        end_date="2026-06-08T00:00:00Z",
        all_day=True,
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day=True,
        title="Synthetic updated all day event",
        start_date="2026-06-07T00:00:00Z",
        end_date="2026-06-08T00:00:00Z",
        all_day=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_all_day_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True


def test_apply_calendar_change_updates_date_only_event_and_binds_expected_all_day() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _all_day_runner(payload, timeout)

    search = search_calendar_events("all day", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        title="Synthetic updated all day event",
        start_date="2026-06-07",
        end_date="2026-06-08",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        title="Synthetic updated all day event",
        start_date="2026-06-07",
        end_date="2026-06-08",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["all_day"] is True
    assert result["read_back"]["start_date"] == "2026-06-07"
    assert result["read_back"]["end_date"] == "2026-06-08"
    apply_payload = calls[-1]
    assert apply_payload["expected_start_date"] == "2026-06-05"
    assert apply_payload["expected_end_date"] == "2026-06-06"
    assert apply_payload["expected_all_day"] is True
    assert apply_payload["start_date"] == "2026-06-07"
    assert apply_payload["end_date"] == "2026-06-08"
    assert apply_payload["all_day"] is True


def test_apply_calendar_change_updates_alarm_offsets_and_binds_expected_state() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[],
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        alarm_offsets_minutes=[-30],
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[],
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        alarm_offsets_minutes=[-30],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["alarm_offsets_minutes"] == [-30]
    assert result["read_back"]["alarms_count"] == 1


def test_plan_calendar_change_update_rejects_string_boolean_flags() -> None:
    search = search_calendar_events("all day", eventkit_runner=_all_day_runner)
    handle = search["results"][0]["handle"]
    result = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day="false",  # type: ignore[arg-type]
        title="Synthetic updated all day event",
        start_date="2026-06-07T00:00:00Z",
        end_date="2026-06-08T00:00:00Z",
        all_day="false",  # type: ignore[arg-type]
    )

    assert result["status"] == "error"
    assert [warning["code"] for warning in result["warnings"]].count("invalid_boolean") == 2


def test_apply_calendar_change_deletes_exact_event_and_reads_back_absence() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = _calendar_delete_plan(handle)

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "delete"
    assert result["mutation_applied"] is True
    assert result["read_back"] == {
        "handle": handle,
        "deleted": True,
        "verified_absent": True,
    }
    delete_payload = [
        call
        for call in calls
        if call["command"] == "calendar_apply_change" and call["operation"] == "delete"
    ][-1]
    assert delete_payload["command"] == "calendar_apply_change"
    assert delete_payload["operation"] == "delete"
    assert delete_payload["event_id"] == "event-1"
    assert delete_payload["expected_title"] == "Synthetic planning event"
    assert "title" not in delete_payload
    assert "start_date" not in delete_payload
    assert "end_date" not in delete_payload
    assert "event-1" not in str(result)


def test_apply_calendar_change_deletes_recurring_occurrence_and_binds_scope() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _recurring_delete_runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=recording_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )
    unscoped_retry = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    delete_payload = calls[-1]
    assert delete_payload["operation"] == "delete"
    assert delete_payload["recurrence_delete_scope"] == "this_event"
    assert delete_payload["expected_recurrence_present"] is True
    assert delete_payload["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert delete_payload["occurrence_end_date"] == "2026-06-03T18:00:00.000Z"
    assert delete_payload["adjacent_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
    assert delete_payload["adjacent_occurrence_end_date"] == "2026-06-10T18:00:00.000Z"
    assert result["read_back"]["selected_occurrence_verified_absent"] is True
    assert result["read_back"]["adjacent_occurrence_verified_present"] is True
    assert unscoped_retry["status"] == "error"
    assert unscoped_retry["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_deletes_end_date_recurring_occurrence_and_binds_scope() -> None:
    calls: list[dict[str, Any]] = []
    recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": "2026-08-01T17:00:00.000Z",
        "recurrence_present": True,
    }

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        result = _recurring_delete_runner(payload, timeout)
        if "events" in result:
            for event in result["events"]:
                event["recurrence_present"] = True
                event["recurrence"] = recurrence
        if "event" in result:
            result["event"]["recurrence_present"] = True
            result["event"]["recurrence"] = recurrence
        return result

    handle = search_calendar_events("planning", eventkit_runner=recording_runner)["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=recording_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    delete_payload = [
        call
        for call in calls
        if call["command"] == "calendar_apply_change" and call["operation"] == "delete"
    ][-1]
    assert result["status"] == "ok"
    assert delete_payload["expected_recurrence"] == recurrence
    assert delete_payload["recurrence_delete_scope"] == "this_event"


def test_apply_calendar_change_deletes_future_recurring_span_and_binds_scope() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _recurring_future_delete_runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="future-events",
        eventkit_runner=recording_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="future-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )
    assert result["status"] == "ok"
    delete_payload = [
        call
        for call in calls
        if call["command"] == "calendar_apply_change" and call["operation"] == "delete"
    ][-1]
    assert delete_payload["operation"] == "delete"
    assert delete_payload["recurrence_delete_scope"] == "future_events"
    assert delete_payload["expected_recurrence_present"] is True
    assert delete_payload["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert delete_payload["occurrence_end_date"] == "2026-06-03T18:00:00.000Z"
    assert delete_payload["previous_occurrence_start_date"] == "2026-05-27T17:00:00.000Z"
    assert delete_payload["previous_occurrence_end_date"] == "2026-05-27T18:00:00.000Z"
    assert delete_payload["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
    assert delete_payload["future_occurrence_end_date"] == "2026-06-10T18:00:00.000Z"
    assert result["read_back"]["selected_occurrence_verified_absent"] is True
    assert result["read_back"]["future_occurrence_verified_absent"] is True
    assert result["read_back"]["previous_occurrence_verified_present"] is True
    this_event_retry = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )
    assert this_event_retry["status"] == "error"
    assert this_event_retry["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_deletes_all_recurring_span_and_binds_scope() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _recurring_all_delete_runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        eventkit_runner=recording_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )
    assert result["status"] == "ok"
    delete_payload = [
        call
        for call in calls
        if call["command"] == "calendar_apply_change" and call["operation"] == "delete"
    ][-1]
    assert delete_payload["operation"] == "delete"
    assert delete_payload["recurrence_delete_scope"] == "all_events"
    assert delete_payload["expected_recurrence_present"] is True
    assert delete_payload["occurrence_start_date"] == "2026-06-03T17:00:00.000Z"
    assert delete_payload["occurrence_end_date"] == "2026-06-03T18:00:00.000Z"
    assert delete_payload["future_occurrence_start_date"] == "2026-06-10T17:00:00.000Z"
    assert delete_payload["future_occurrence_end_date"] == "2026-06-10T18:00:00.000Z"
    assert result["read_back"]["selected_occurrence_verified_absent"] is True
    assert result["read_back"]["future_occurrence_verified_absent"] is True
    assert result["read_back"]["previous_occurrence_verified_absent"] is True
    this_event_retry = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )
    assert this_event_retry["status"] == "error"
    assert this_event_retry["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_calendar_change_rejects_legacy_handle_for_scoped_recurring_delete() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")

    for scope, runner in {
        "this-event": _recurring_delete_runner,
        "future-events": _recurring_future_delete_runner,
        "all-events": _recurring_all_delete_runner,
    }.items():
        result = apply_calendar_change(
            "delete",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            recurrence_delete_scope=scope,
            approval_token="calendar-apply:v1:legacy",
            confirm_apply=True,
            eventkit_runner=runner,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "missing_occurrence_identity"


def test_apply_calendar_change_requires_adjacent_proof_for_scoped_recurring_delete() -> None:
    def runner_without_adjacent(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            result = _recurring_delete_runner(payload, timeout)
            result["events"] = result["events"][:1]
            return result
        return _recurring_delete_runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=runner_without_adjacent)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=_recurring_delete_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=runner_without_adjacent,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "adjacent_occurrence_not_found"


def test_apply_calendar_change_requires_span_proof_for_future_recurring_delete() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_future_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="future-events",
        eventkit_runner=_recurring_future_delete_runner,
    )

    for removed_start, expected_code in {
        "2026-05-27T17:00:00.000Z": "previous_occurrence_not_found",
        "2026-06-10T17:00:00.000Z": "future_occurrence_not_found",
    }.items():

        def runner_without_span_proof(
            payload: dict[str, Any],
            timeout: float,
            *,
            removed_start: str = removed_start,
        ) -> dict[str, Any]:
            if payload["command"] == "calendar_events":
                result = _recurring_future_delete_runner(payload, timeout)
                result["events"] = [
                    event
                    for event in result["events"]
                    if event.get("start_date") != removed_start
                ]
                return result
            return _recurring_future_delete_runner(payload, timeout)

        result = apply_calendar_change(
            "delete",
            handle=handle,
            expected_title="Synthetic planning event",
            expected_calendar_title="Synthetic Calendar",
            expected_start_date="2026-06-03T17:00:00Z",
            expected_end_date="2026-06-03T18:00:00Z",
            recurrence_delete_scope="future-events",
            approval_token=_calendar_token(plan),
            confirm_apply=True,
            eventkit_runner=runner_without_span_proof,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == expected_code


def test_apply_calendar_change_requires_first_and_future_proof_for_all_recurring_delete() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_all_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        eventkit_runner=_recurring_all_delete_runner,
    )

    def runner_with_previous(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            result = _recurring_all_delete_runner(payload, timeout)
            previous = {
                **result["events"][0],
                "start_date": "2026-05-27T17:00:00.000Z",
                "end_date": "2026-05-27T18:00:00.000Z",
            }
            result["events"].append(previous)
            return result
        return _recurring_all_delete_runner(payload, timeout)

    previous_result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=runner_with_previous,
    )
    assert previous_result["status"] == "error"
    assert previous_result["mutation_applied"] is False
    assert previous_result["warnings"][0]["code"] == "previous_occurrence_present"

    def runner_without_future(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            result = _recurring_all_delete_runner(payload, timeout)
            result["events"] = result["events"][:1]
            return result
        return _recurring_all_delete_runner(payload, timeout)

    future_result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="all-events",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=runner_without_future,
    )
    assert future_result["status"] == "error"
    assert future_result["mutation_applied"] is False
    assert future_result["warnings"][0]["code"] == "future_occurrence_not_found"


def test_apply_calendar_change_rejects_unscoped_recurring_delete() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurring_delete_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_event_state"


def test_apply_calendar_change_rejects_scoped_nonrecurring_delete() -> None:
    search = search_calendar_events("planning", eventkit_runner=_recurring_delete_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        eventkit_runner=_recurring_delete_runner,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_nonrecurring_scoped_delete_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


def test_apply_calendar_change_deletes_event_and_binds_expected_event_url() -> None:
    calls: list[dict[str, Any]] = []
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    expected_url = "https://meet.example.invalid/current?id=42"
    expected_sha = hashlib.sha256(expected_url.encode("utf-8")).hexdigest()

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert calls[-1]["expected_event_url_present"] is True
    assert calls[-1]["expected_event_url_sha256"] == expected_sha


def test_apply_calendar_change_deletes_all_day_event_and_binds_expected_flag() -> None:
    search = search_calendar_events("all day", eventkit_runner=_all_day_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day=True,
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day=True,
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_all_day_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["verified_absent"] is True


def test_apply_calendar_change_deletes_date_only_event_and_binds_expected_all_day() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _all_day_runner(payload, timeout)

    search = search_calendar_events("all day", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05",
        expected_end_date="2026-06-06",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["verified_absent"] is True
    delete_payload = calls[-1]
    assert delete_payload["expected_start_date"] == "2026-06-05"
    assert delete_payload["expected_end_date"] == "2026-06-06"
    assert delete_payload["expected_all_day"] is True


def test_apply_calendar_change_deletes_event_and_binds_expected_alarm_offsets() -> None:
    calls: list[dict[str, Any]] = []

    def recording_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(payload)
        return _runner(payload, timeout)

    search = search_calendar_events("planning", eventkit_runner=recording_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        expected_alarm_offsets_minutes=[-10],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=recording_runner,
    )

    assert result["status"] == "ok"
    assert calls[-1]["expected_alarm_offsets_minutes"] == [-10]


def test_apply_calendar_change_deletes_event_and_binds_expected_absolute_alarm() -> None:
    def absolute_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        if payload["command"] == "calendar_events":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "events": [
                    {
                        "event_id": "event-absolute-1",
                        "title": "Synthetic absolute alarm event",
                        "calendar_id": "calendar-1",
                        "calendar_title": "Synthetic Calendar",
                        "start_date": "2026-06-05T17:00:00.000Z",
                        "end_date": "2026-06-05T18:00:00.000Z",
                        "all_day": False,
                        "availability": 0,
                        "location_present": False,
                        "notes_present": False,
                        "url_present": False,
                        "alarm_absolute_dates": ["2026-06-05T16:45:00Z"],
                        "alarms_count": 1,
                        "attendees_count": 0,
                    }
                ],
                "warnings": [],
            }
        if payload["command"] == "calendar_apply_change":
            assert payload["operation"] == "delete"
            assert payload["expected_alarm_offsets_minutes"] == []
            assert payload["expected_alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": "authorized",
                "deleted": True,
                "read_back": {"deleted": True, "verified_absent": True},
                "warnings": [],
            }
        raise AssertionError(payload)

    search = search_calendar_events("absolute", eventkit_runner=absolute_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic absolute alarm event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic absolute alarm event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=absolute_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["verified_absent"] is True


def test_plan_calendar_change_delete_rejects_string_expected_all_day() -> None:
    search = search_calendar_events("all day", eventkit_runner=_all_day_runner)
    handle = search["results"][0]["handle"]
    result = plan_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic all day event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T00:00:00Z",
        expected_end_date="2026-06-06T00:00:00Z",
        expected_all_day="false",  # type: ignore[arg-type]
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_boolean"


def test_eventkit_update_checks_expected_state_before_already_applied() -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts/eventkit_helper.swift"
    source = helper.read_text(encoding="utf-8")
    update_block = source.split('if operation == "update" {', maxsplit=1)[1].split(
        'if operation == "create" {', maxsplit=1
    )[0]
    expected_check = (
        "if !eventMatchesState(event, title: expectedTitle, calendarTitle: "
        "expectedCalendarTitle"
    )
    already_applied_check = (
        "if !recurrenceClearRequested\n"
        "            && !selectedOccurrenceUpdateRequested\n"
        "            && !midSeriesRecurrenceReplaceRequested\n"
        "            && !futureSeriesUpdateRequested\n"
        "            && eventMatchesState(event, title: title, calendarTitle:"
    )
    attendee_alarm_check = "if eventHasUnsupportedAttendeeOrAlarmState(event)"
    expected_recurrence_check = 'if let expectedRecurrencePresent = boolValue(request, "expected_recurrence_present")'
    recurrence_unsupported_check = "if eventIsUnsupportedForBoundedMutation(event)"

    assert "Selected recurring occurrence all-day update requires date-only start_date and end_date." in update_block
    assert "Selected recurring occurrence timed update from all-day requires explicit time_zone." in update_block
    assert "let allDayUpdated = allDay != expectedAllDay" in update_block
    assert "let allDayVerified = allDayUpdated || (allDay && expectedAllDay && selectedRescheduled)" in update_block
    assert '"all_day_verified": allDayVerified' in update_block
    assert update_block.index(attendee_alarm_check) < update_block.index(expected_check)
    assert update_block.index(expected_check) < update_block.index(expected_recurrence_check)
    assert update_block.index(expected_recurrence_check) < update_block.index(
        recurrence_unsupported_check
    )
    assert update_block.index(recurrence_unsupported_check) < update_block.index(
        already_applied_check
    )
    assert 'stringValue(request, "recurrence_update_scope")' in update_block
    assert "selectedOccurrenceUpdateRequested" in update_block
    assert 'recurrenceUpdateScope != "this_event"' in update_block
    assert "if selectedOccurrenceUpdateRequested && (recurrenceClearRequested || recurrenceUpdateRequested)" in update_block
    future_series_block = update_block.split(
        "var futureSeriesUpdateReadBack", maxsplit=1
    )[1].split("} else if selectedOccurrenceUpdateRequested {", maxsplit=1)[0]
    assert "recurrenceMatches(selectedRemaining[0], expectedRecurrence)" in future_series_block
    assert "recurrenceMatches(futureAfterUpdate[0], expectedRecurrence)" in future_series_block
    assert "eventSlotMatches" in future_series_block
    assert "original_occurrence_verified_absent_or_replaced" in future_series_block
    assert "future_original_occurrence_verified_absent_or_replaced" in future_series_block
    assert "else if selectedOccurrenceUpdateRequested" in update_block
    assert "adjacentOccurrenceStartDate" in update_block
    assert "selected_occurrence_updated_verified" in update_block
    assert "selected_occurrence_rescheduled_verified" in update_block
    assert "original_occurrence_verified_absent" in update_block
    assert "let readBackAvailability = proposedAvailability ?? expectedAvailability" in update_block
    assert "let readBackEventURLPresent" in update_block
    assert "availability_read_back_mismatch" in update_block
    assert "event_url_read_back_mismatch" in update_block
    assert "event_url_clear_read_back_mismatch" in update_block
    assert "structured_location_read_back_mismatch" in update_block
    assert "structured_location_clear_read_back_mismatch" in update_block
    assert "structured_location_verified" in update_block
    assert "structured_location_cleared_verified" in update_block
    assert 'boolValue(request, "expected_structured_location_present")' in source
    assert "Calendar event did not match expected structured location state." in update_block
    assert "adjacent_occurrence_event_url_present" in update_block
    assert "adjacent_occurrence_event_url_sha256" in update_block
    assert "adjacent_occurrence_event_url_read_back_mismatch" in update_block
    assert "adjacent_occurrence_event_url_verified" in update_block
    assert "adjacent_occurrence_location_present" in update_block
    assert "adjacent_occurrence_location_sha256" in update_block
    assert "adjacent_occurrence_structured_location_present" in update_block
    assert "adjacent_occurrence_structured_location_sha256" in update_block
    assert "eventLocationProofStateMatches" in update_block
    assert "adjacent_occurrence_location_read_back_mismatch" in update_block
    assert "adjacent_occurrence_location_verified" in update_block
    assert (
        "Selected recurring occurrence update cannot move calendars or change availability."
        not in update_block
    )
    assert (
        "Selected recurring occurrence update cannot set or clear event URLs."
        not in update_block
    )
    assert (
        "Selected recurring occurrence update cannot set or clear structured location."
        not in update_block
    )
    assert (
        "Selected recurring occurrence update is limited to events without existing structured location."
        not in update_block
    )
    assert "Selected recurring occurrence update cannot move calendars." not in update_block
    assert "selected_occurrence_calendar_move_verified" in update_block
    assert "adjacent_occurrence_calendar_verified" in update_block
    assert "adjacent_occurrence_calendar_read_back_mismatch" in update_block
    assert "targetCalendar" in update_block
    assert "selectedReadBackStartDate" in update_block
    assert "originalRemaining" in update_block
    assert "structuredLocationPayloadsEqual" in source
    assert (
        "Selected recurring occurrence update supports only relative or absolute display alarm changes."
        not in update_block
    )
    assert 'boolValue(request, "selected_occurrence_alarm_update_requested")' in update_block
    assert "selectedOccurrenceAlarmUpdateRequested" in update_block
    assert "action_alarm_verified" in update_block
    assert "display_alarm_verified" in update_block
    assert "Selected recurring occurrence update cannot change alarms." not in update_block
    assert "&& !selectedOccurrenceUpdateRequested" in update_block
    assert "&& (!recurrenceUpdateRequested || recurrenceMatches(event, proposedRecurrence))" in update_block
    assert "!recurrenceClearRequested" in update_block
    assert update_block.index(already_applied_check) < update_block.index(
        "applyRecurrence(event, recurrence: proposedRecurrence)"
    )
    assert "event.url = nil" in update_block
    assert "proposedEventURLClearRequested" in update_block
    assert "event_url_clear_requested" in source


def test_eventkit_bounded_calendar_mutation_binds_alarm_offsets() -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts/eventkit_helper.swift"
    source = helper.read_text(encoding="utf-8")
    unsupported_block = source.split("func eventIsUnsupportedForBoundedMutation", maxsplit=1)[
        1
    ].split("func emitCalendarApplyError", maxsplit=1)[0]
    attendee_alarm_block = source.split(
        "func eventHasUnsupportedAttendeeOrAlarmState",
        maxsplit=1,
    )[1].split("func eventIsUnsupportedForBoundedMutation", maxsplit=1)[0]
    recurrence_block = source.split("func eventHasRecurrence", maxsplit=1)[1].split(
        "func eventHasUnsupportedAttendeeOrAlarmState",
        maxsplit=1,
    )[0]

    assert "event.recurrenceRules?.isEmpty == false" in recurrence_block
    assert "eventHasRecurrence(event)" in unsupported_block
    assert "eventHasUnsupportedAttendeeOrAlarmState(event)" in unsupported_block
    assert "event.alarms?.isEmpty == false" not in attendee_alarm_block
    assert "state.offsets == nil" in attendee_alarm_block
    assert "state.absoluteDates == nil" in attendee_alarm_block
    assert "state.soundName == nil" in attendee_alarm_block
    assert "state.proximity == nil" in attendee_alarm_block
    assert "state.emailAddressSHA256 == nil" in attendee_alarm_block
    assert "alarm.absoluteDate" in source
    assert "alarm.structuredLocation != nil" in source
    assert "alarm.proximity != .none" in source
    assert "func alarmProximityName" in source
    assert "func alarmProximityValue" in source
    assert "alarm.proximity = alarmProximity" in source
    assert "alarm.structuredLocation = makeStructuredLocation" in source
    assert "alarm.type == .email" in source
    assert "alarm.type == .procedure" in source
    assert "alarm.relativeOffset != 0" in source
    assert "func isValidAlarmSoundName" in source
    assert "var sawDisplayAlarm = false" in source
    assert "var sawAudioAlarm = false" in source
    assert "if sawDisplayAlarm || sawAudioAlarm || !currentSoundName.isEmpty || !isValidAlarmEmailAddress(currentEmailAddress)" in source
    assert "if sawDisplayAlarm || sawEmailAlarm || !isValidAlarmSoundName(currentSoundName)" in source
    assert "if sawAudioAlarm || sawEmailAlarm || !currentSoundName.isEmpty" in source
    assert "alarm.soundName = soundName" in source
    assert "alarm.emailAddress = emailAddress" in source
    assert "currentAlarmOffsetsMinutes == expectedAlarmOffsetsMinutes" in source
    assert "currentAlarmAbsoluteDates == expectedAlarmAbsoluteDates" in source
    assert "currentAlarmSoundName == expectedAlarmSoundName" in source
    assert "currentAlarmEmailAddressSHA256 == expectedAlarmEmailAddressSHA256" in source
    assert "currentAlarmProximity == expectedAlarmProximity" in source
    assert "structuredLocationPayloadMatches(state.structuredLocation" in source
    assert 'dateStringArrayValue(request, "expected_alarm_absolute_dates")' in source
    assert 'alarmSoundNameValue(request, "expected_alarm_sound_name")' in source
    assert 'alarmEmailAddressValue(request, "alarm_email_address")' in source
    assert 'stringValue(request, "expected_alarm_email_address_sha256")' in source
    assert 'alarmProximityValue(request, "expected_alarm_proximity")' in source
    assert 'structuredLocationRequest(request, "expected_alarm_structured_location")' in source
    delete_block = source.split('if operation == "delete" {', maxsplit=1)[1].split(
        'let title = stringValue(request, "title")',
        maxsplit=1,
    )[0]
    assert delete_block.index("if eventHasUnsupportedAttendeeOrAlarmState(event)") < delete_block.index(
        "if eventHasRecurrence(event)"
    )
    assert delete_block.index("if eventHasRecurrence(event)") < delete_block.index(
        "try store.remove(event, span:"
    )
    assert 'stringValue(request, "recurrence_delete_scope")' in delete_block
    assert 'stringValue(request, "occurrence_start_date")' in delete_block
    assert 'stringValue(request, "occurrence_end_date")' in delete_block
    assert "occurrenceCandidates(" in delete_block
    assert 'boolValue(request, "expected_recurrence_present")' in delete_block
    assert 'recurrenceRequest(request, key: "expected_recurrence")' in delete_block
    assert "recurrenceMatches(event, expectedRecurrence)" in delete_block
    assert 'recurrenceDeleteScope == "this_event"' in delete_block
    assert 'recurrenceDeleteScope == "future_events"' in delete_block
    assert 'recurrenceDeleteScope != "all_events"' in delete_block
    assert 'stringValue(request, "previous_occurrence_start_date")' in delete_block
    assert 'stringValue(request, "future_occurrence_start_date")' in delete_block
    assert "relativeOccurrenceCandidates(" in delete_block
    assert "previous_occurrence_present" in delete_block
    assert "previous_occurrence_verified_absent" in delete_block
    assert "unsupported_recurrence_delete_scope" in delete_block
    assert "applyAlarms(event, offsets: proposedAlarmOffsetsMinutes, absoluteDates: proposedAlarmAbsoluteDates, soundName: proposedAlarmSoundName, emailAddress: proposedAlarmEmailAddress, proximity: proposedAlarmProximity, structuredLocation: proposedAlarmStructuredLocation)" in source
    assert "includeTimeZone: Bool = false" in source
    assert 'payload["time_zone"] = eventTimeZoneIdentifier(event)' in source
    assert "event.timeZone = proposedTimeZone" in source
    assert 'stringValue(request, "expected_time_zone")' in source
    assert "eventTimeZoneIdentifier(event) == expectedTimeZone" in source
    assert "EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)" in source
    assert 'let unbounded = boolValue(recurrence, "unbounded") ?? false' in source
    assert "let end: EKRecurrenceEnd?" in source
    assert "end = nil" in source
    assert 'payload["unbounded"] = true' in source
    assert '((current["unbounded"] as? Bool) ?? false)' in source
    assert "EKRecurrenceDayOfWeek" in source
    assert "daysOfTheWeek: weekdays" in source
    assert "recurrenceMonthDaysPayload" in source
    assert "monthDayArrayValue" in source
    assert "daysOfTheMonth: monthDays.map" in source
    assert '"month_days"' in source
    assert "recurrenceMonthWeekdaysPayload" in source
    assert "monthWeekdayArrayValue" in source
    assert "EKRecurrenceDayOfWeek(weekDay, weekNumber: weekNumber)" in source
    assert "daysOfTheWeek: monthWeekdays" in source
    assert '"month_weekdays"' in source
    assert "recurrenceYearMonthsPayload" in source
    assert "yearMonthArrayValue" in source
    assert "monthsOfTheYear: yearMonths.map" in source
    assert '"year_months"' in source
    assert '"year_month_days"' in source
    assert "daysOfTheMonth: yearMonthDays.isEmpty ? nil : yearMonthDays.map" in source
    assert '"year_month_weekdays"' in source
    assert "!yearMonthDays.isEmpty && !yearMonthWeekdays.isEmpty" in source
    assert "guard yearMonthDays.isEmpty || yearMonthWeekdayValues.isEmpty" in source
    assert "yearMonthWeekdayValues" in source
    assert "daysOfTheWeek: yearMonthWeekdays.isEmpty ? nil : yearMonthWeekdays" in source
    assert "recurrenceYearDaysPayload" in source
    assert "yearDayArrayValue" in source
    assert "daysOfTheYear: yearDays.map" in source
    assert '"year_days"' in source
    assert "recurrenceYearWeeksPayload" in source
    assert "yearWeekArrayValue" in source
    assert "weeksOfTheYear: yearWeeks.map" in source
    assert "yearlyWeekWithWeekdays" in source
    assert '"year_weeks"' in source
    assert "func isBooleanNumber" in source
    monthly_read_back_block = source.split(
        "} else if rule.frequency == .monthly {", maxsplit=1
    )[1].split(
        "} else if rule.frequency == .yearly && !yearMonths.isEmpty {", maxsplit=1
    )[0]
    monthly_apply_block = source.split(
        "if !weekdays.isEmpty && frequency == .monthly {", maxsplit=1
    )[1].split("if !monthDays.isEmpty && frequency == .monthly {", maxsplit=1)[0]
    assert "let rawWeekdayRules = rule.daysOfTheWeek ?? []" in monthly_read_back_block
    assert "if !monthDays.isEmpty && !rawWeekdayRules.isEmpty" in monthly_read_back_block
    assert monthly_read_back_block.index(
        "rawWeekdayRules.allSatisfy({ $0.weekNumber == 0 })"
    ) < monthly_read_back_block.index("recurrenceWeekdaysPayload(rule)")
    assert monthly_read_back_block.index(
        "rawWeekdayRules.allSatisfy({ $0.weekNumber != 0 })"
    ) < monthly_read_back_block.index("recurrenceMonthWeekdaysPayload(rule)")
    assert "daysOfTheWeek: weekdays" in monthly_apply_block
    assert "daysOfTheMonth: nil" in monthly_apply_block
    assert "monthsOfTheYear: nil" in monthly_apply_block
    assert "weeksOfTheYear: nil" in monthly_apply_block
    assert "daysOfTheYear: nil" in monthly_apply_block
    int_array_block = source.split("func intArrayValue", maxsplit=1)[1].split(
        "func monthDayArrayValue", maxsplit=1
    )[0]
    month_day_block = source.split("func monthDayArrayValue", maxsplit=1)[1].split(
        "func monthWeekdayArrayValue", maxsplit=1
    )[0]
    month_weekday_block = source.split("func monthWeekdayArrayValue", maxsplit=1)[1].split(
        "func monthWeekdayComparisonKeys", maxsplit=1
    )[0]
    year_month_block = source.split("func yearMonthArrayValue", maxsplit=1)[1].split(
        "func signedRecurrenceIntArrayValue", maxsplit=1
    )[0]
    signed_recurrence_block = source.split(
        "func signedRecurrenceIntArrayValue", maxsplit=1
    )[1].split("func yearDayArrayValue", maxsplit=1)[0]
    assert int_array_block.index("if isBooleanNumber(item)") < int_array_block.index(
        "if let intItem = item as? Int"
    )
    assert month_day_block.index("if isBooleanNumber(item)") < month_day_block.index(
        "if let value = item as? Int"
    )
    assert month_weekday_block.index(
        "if isBooleanNumber(weekNumberValue)"
    ) < month_weekday_block.index("if let intValue = weekNumberValue as? Int")
    assert year_month_block.index("if isBooleanNumber(item)") < year_month_block.index(
        "if let intValue = item as? Int"
    )
    assert signed_recurrence_block.index(
        "if isBooleanNumber(item)"
    ) < signed_recurrence_block.index("if let value = item as? Int")
    assert "structuredLocationRequest" in source
    assert "value is Bool" in source
    assert "latitude < -90 || latitude > 90" in source
    assert "longitude < -180 || longitude > 180" in source
    assert "radius < 0 || radius > 100000" in source
    assert "EKRecurrenceEnd(occurrenceCount: count)" in source
    assert "EKRecurrenceEnd(end: endDate)" in source
    assert 'stringValue(recurrence, "end_date")' in source
    assert '"end_date"' in source
    assert "event.recurrenceRules = [" in source
    assert "recurrenceRequest(request)" in source
    assert "recurrenceWeekdaysPayload" in source
    assert "recurrenceUpdateRequested" in source
    assert "recurrenceMatches(event, proposedRecurrence)" in source
    assert "applyRecurrence(event, recurrence: proposedRecurrence)" in source
    assert "unsupported_recurrence_for_operation" in source
    assert "Calendar recurrence is not supported for delete operations." in source
    assert "Calendar recurrence is currently supported only for create operations." not in source
    assert "event.availability = proposedAvailability" in source
    assert "calendar.supportedEventAvailabilities.contains(.free)" in source
    assert 'availabilityRequest(request, "expected_availability", allowNotSupported: true)' in source
    assert "availabilityMatches(event, expectedAvailability)" in source
    assert "try store.remove(event, span:" in source
    assert ".thisEvent" in source
    assert ".futureEvents" in source


def test_eventkit_calendar_target_selection_uses_public_eventkit_apis() -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts/eventkit_helper.swift"
    source = helper.read_text(encoding="utf-8")

    assert 'if command == "request_calendar_full_access" {' in source
    assert 'if command == "request_reminders_full_access" {' in source
    assert 'if command == "calendar_authorization_status" {' in source
    assert "requestFullAccessToEvents" in source
    assert "requestFullAccessToReminders" in source
    # The access-request path runs under a real NSApplication lifecycle (an
    # NSApplicationDelegate + app.run()) so macOS 26 TCC presents its prompt;
    # the legacy requestAccess(to:) is invoked with a runtime entityType.
    assert "store.requestAccess(to: entityType" in source
    assert "entityType: .event" in source
    assert "entityType: .reminder" in source
    assert "RunLoop.current.run" in source
    assert "import AppKit" in source
    assert "EventKitAccessDelegate" in source
    assert "NSApplicationDelegate" in source
    assert "NSApp.activate(ignoringOtherApps: true)" in source
    assert "app.run()" in source
    assert 'commandLineOptionValue("--input-json-file")' in source
    assert 'commandLineOptionValue("--output-json-file")' in source
    assert '"calendar_access_request_timeout"' in source
    assert '"reminders_access_request_timeout"' in source
    assert 'if command == "calendar_calendars" {' in source
    assert "store.defaultCalendarForNewEvents?.calendarIdentifier" in source
    assert "calendar.allowsContentModifications" in source
    assert "event.calendar = targetCalendar" in source
    assert 'stringValue(request, "target_calendar_id")' in source
    assert 'stringValue(request, "calendar_id")' in source
    assert '"calendar_id": event.calendar?.calendarIdentifier ?? ""' in source
    assert "calendarTitleIsAmbiguous(store, expectedCalendarTitle)" in source
    assert '"ambiguous_expected_calendar"' in source


def test_apply_calendar_change_delete_requires_absence_proof() -> None:
    def unknown_delete_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if payload["command"] != "calendar_apply_change":
            return _runner(payload, timeout)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {"deleted": True, "verified_absent": False},
            "warnings": [],
        }

    search = search_calendar_events("planning", eventkit_runner=unknown_delete_runner)
    handle = search["results"][0]["handle"]
    plan = _calendar_delete_plan(handle)

    result = apply_calendar_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_location="Synthetic Room",
        expected_notes="Synthetic event notes.",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=unknown_delete_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_calendar_change_rejects_stale_expected_state() -> None:
    search = search_calendar_events("planning", eventkit_runner=_runner)
    handle = search["results"][0]["handle"]
    plan = plan_calendar_change(
        "update",
        handle=handle,
        expected_title="Stale synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
    )

    result = apply_calendar_change(
        "update",
        handle=handle,
        expected_title="Stale synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        approval_token=_calendar_token(plan),
        confirm_apply=True,
        eventkit_runner=_runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


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
