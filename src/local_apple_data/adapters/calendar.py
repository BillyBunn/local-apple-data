from __future__ import annotations

import json
import subprocess
import hashlib
from datetime import UTC, datetime
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
MAX_PREVIEW_TITLE_CHARS = 512
MAX_PREVIEW_CALENDAR_CHARS = 512
MAX_LOCATION_CHARS = 1000
EVENTKIT_TIMEOUT_SECONDS = 10.0
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTKIT_HELPER = PROJECT_ROOT / "scripts/eventkit_helper.swift"
PLAN_OPERATIONS = {"create"}
APPROVAL_TOKEN_PREFIX = "calendar-apply:v1:"
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


def _preview_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
    }


def _mutation_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "mutation",
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


def plan_calendar_change(
    operation: str,
    *,
    title: str = "",
    calendar_title: str = "",
    start_date: str = "",
    end_date: str = "",
    location: str = "",
    notes: str = "",
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create."))
        return _preview_error(warnings)

    normalized_title, title_warning = _bounded_preview_value(
        title,
        field="title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=True,
    )
    if title_warning is not None:
        warnings.append(title_warning)

    normalized_calendar, calendar_warning = _bounded_preview_value(
        calendar_title,
        field="calendar_title",
        max_chars=MAX_PREVIEW_CALENDAR_CHARS,
        required=True,
    )
    if calendar_warning is not None:
        warnings.append(calendar_warning)

    normalized_location, location_warning = _bounded_preview_value(
        location,
        field="location",
        max_chars=MAX_LOCATION_CHARS,
        required=False,
    )
    if location_warning is not None:
        warnings.append(location_warning)

    normalized_notes, notes_warning = _bounded_preview_value(
        notes,
        field="notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if notes_warning is not None:
        warnings.append(notes_warning)

    normalized_start, start_warning = _normalize_event_datetime(start_date, field="start_date")
    if start_warning is not None:
        warnings.append(start_warning)

    normalized_end, end_warning = _normalize_event_datetime(end_date, field="end_date")
    if end_warning is not None:
        warnings.append(end_warning)

    if normalized_start and normalized_end:
        start_dt = datetime.fromisoformat(normalized_start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(normalized_end.replace("Z", "+00:00"))
        if end_dt <= start_dt:
            warnings.append(
                _warning("invalid_time_range", "Calendar event end_date must be after start_date.")
            )

    if warnings:
        return _preview_error(warnings)

    target = {"calendar_title": normalized_calendar}
    proposed = {
        "title": normalized_title,
        "start_date": normalized_start,
        "end_date": normalized_end,
        "all_day": False,
        "location": normalized_location,
        "location_present": bool(normalized_location),
        "notes_text": normalized_notes,
        "notes_chars": len(normalized_notes),
        "notes_present": bool(normalized_notes),
        "attendees_count": 0,
        "alarms_count": 0,
        "url_present": False,
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def apply_calendar_change(
    operation: str,
    *,
    title: str = "",
    calendar_title: str = "",
    start_date: str = "",
    end_date: str = "",
    location: str = "",
    notes: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    plan = plan_calendar_change(
        operation,
        title=title,
        calendar_title=calendar_title,
        start_date=start_date,
        end_date=end_date,
        location=location,
        notes=notes,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Calendar apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Calendar apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Calendar apply approval token did not match the plan.")],
            plan=plan,
        )

    runner = eventkit_runner or _run_eventkit_helper
    try:
        applied = runner(_apply_helper_payload(preview), EVENTKIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("eventkit_timeout", "Calendar apply timed out through the local EventKit helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("eventkit_unavailable", "Calendar apply is unavailable through the local EventKit helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("eventkit_apply_failed", "Calendar event could not be created safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

    event = applied.get("event")
    if not isinstance(event, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Calendar apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": str(preview["operation"]),
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": _event_metadata(event),
        "result_count": 1,
        "warnings": _safe_warnings(applied),
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


def _preview_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "calendar",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None,
    status: str = "error",
    mutation_applied: bool = False,
    authorization_status: Any = None,
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "calendar",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


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


def _bounded_preview_value(
    value: str,
    *,
    field: str,
    max_chars: int,
    required: bool,
) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    if required and not normalized:
        return "", _warning("missing_required_field", f"Missing required field: {field}.")
    if len(normalized) > max_chars:
        return "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    return normalized, None


def _normalize_event_datetime(
    value: str,
    *,
    field: str,
) -> tuple[str | None, dict[str, str] | None]:
    stripped = value.strip()
    if not stripped:
        return None, _warning("missing_required_field", f"Missing required field: {field}.")
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None, _warning(
            "invalid_datetime",
            f"{field} must be an ISO 8601 timestamp with a timezone.",
        )
    if parsed.tzinfo is None:
        return None, _warning(
            "invalid_datetime",
            f"{field} must include a timezone.",
        )
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"), None


def _apply_helper_payload(preview: dict[str, Any]) -> dict[str, Any]:
    proposed = preview["proposed"]
    target = preview["target"]
    return {
        "command": "calendar_apply_change",
        "operation": preview["operation"],
        "title": proposed["title"],
        "calendar_title": target["calendar_title"],
        "start_date": proposed["start_date"],
        "end_date": proposed["end_date"],
        "location": proposed["location"],
        "notes": proposed["notes_text"],
    }


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"calendar-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
