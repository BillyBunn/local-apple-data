from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_DAYS_BACK = 365
DEFAULT_DAYS_FORWARD = 730
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_EVENTS = 2000
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
EVENTKIT_TIMEOUT_SECONDS = 10.0
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTKIT_HELPER = PROJECT_ROOT / "scripts/eventkit_helper.swift"
EventKitRunner = Callable[[dict[str, Any], float], dict[str, Any]]


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _content_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Calendar search requires a non-empty event title query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Calendar search requires at least two letters or digits.",
            )
        ],
    }


def search_calendar_events(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _calendar_events_response(
        query=query,
        limit=bounded_limit,
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=False)

    results = [_event_metadata(event) for event in response.get("events", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "title",
            "limit": bounded_limit,
            "days_back": _bounded_days(days_back),
            "days_forward": _bounded_days(days_forward),
            "max_scan_events": _bounded_max_scan(max_scan_events),
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def get_calendar_event(
    handle: str,
    *,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    max_scan_events: int = DEFAULT_MAX_SCAN_EVENTS,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, "calendar:event"):
        return _invalid_handle_result()

    response = _calendar_events_response(
        query="",
        limit=50,
        days_back=days_back,
        days_forward=days_forward,
        max_scan_events=max_scan_events,
        eventkit_runner=eventkit_runner,
    )
    if response["status"] != "ok":
        return _helper_degraded_result(response, content=True)

    event_id = _resolve_event_id(handle, response.get("events", []))
    if event_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = eventkit_runner or _run_eventkit_helper
    try:
        detail = runner(
            {"command": "calendar_event_by_id", "event_id": event_id},
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _content_unavailable_result(
            None,
            "eventkit_read_error",
            "Calendar event could not be read safely.",
        )

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _helper_degraded_result(detail, content=True)

    event = detail.get("event")
    if not isinstance(event, dict):
        return _content_unavailable_result(
            None,
            "eventkit_read_error",
            "Calendar event could not be read safely.",
        )

    result = _event_metadata(event)
    notes_text, notes_truncated = _bounded_text(
        str(event.get("notes") or ""),
        max_chars,
    )
    location_text, location_truncated = _bounded_text(
        str(event.get("location") or ""),
        min(max_chars, 1000),
    )
    result.update(
        {
            "location": location_text,
            "location_truncated": location_truncated,
            "notes_text": notes_text,
            "notes_chars": len(notes_text),
            "notes_truncated": notes_truncated,
        }
    )
    warnings = _safe_warnings(response) + _safe_warnings(detail)
    if notes_truncated:
        warnings.append(
            _warning(
                "content_truncated",
                "Calendar event notes were truncated to the requested limit.",
            )
        )
    if location_truncated:
        warnings.append(
            _warning(
                "location_truncated",
                "Calendar event location was truncated to the requested limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def _calendar_events_response(
    *,
    query: str,
    limit: int,
    days_back: int,
    days_forward: int,
    max_scan_events: int,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "calendar_events",
                "query": query,
                "limit": max(1, min(limit, 50)),
                "days_back": _bounded_days(days_back),
                "days_forward": _bounded_days(days_forward),
                "max_events": _bounded_max_scan(max_scan_events),
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Calendar access timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Calendar access is unavailable through the local EventKit helper.",
                )
            ],
        }


def _run_eventkit_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(DEFAULT_EVENTKIT_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("EventKit helper failed.")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("EventKit helper returned invalid JSON.")
    return parsed


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    return {
        "handle": make_opaque_handle("calendar:event", event_id),
        "title": event.get("title"),
        "calendar_title": event.get("calendar_title"),
        "start_date": event.get("start_date"),
        "end_date": event.get("end_date"),
        "all_day": bool(event.get("all_day")),
        "availability": event.get("availability"),
        "location_present": bool(event.get("location_present")),
        "notes_present": bool(event.get("notes_present")),
        "url_present": bool(event.get("url_present")),
        "alarms_count": event.get("alarms_count"),
        "attendees_count": event.get("attendees_count"),
    }


def _resolve_event_id(handle: str, events: Any) -> str | None:
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        if event_id and opaque_handle_matches(handle, "calendar:event", event_id):
            return event_id
    return None


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected calendar:event:v1 opaque handle from search output.",
            )
        ],
    }


def _helper_degraded_result(response: dict[str, Any], *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": _safe_warnings(response),
    }


def _content_unavailable_result(
    result: dict[str, Any] | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "content_unavailable",
        "source": "calendar",
        "privacy": _content_privacy(content_inspected=False),
        "result": result,
        "warnings": [_warning(code, message)],
    }


def _safe_warnings(response: dict[str, Any]) -> list[dict[str, str]]:
    warnings = response.get("warnings")
    if not isinstance(warnings, list):
        return []
    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append(_warning(code, message))
    return safe


def _bounded_days(days: int) -> int:
    return max(0, min(days, 3650))


def _bounded_max_scan(max_scan_events: int) -> int:
    return max(1, min(max_scan_events, 10000))


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= bounded_chars:
        return normalized, False
    return normalized[:bounded_chars], True
