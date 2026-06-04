from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_REMINDERS_DIR = (
    Path.home()
    / "Library/Group Containers/group.com.apple.reminders/Container_v1/Stores"
)

REMINDERS_TABLES = ["ZREMCDREMINDER", "ZREMCDBASELIST"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
EVENTKIT_HELPER = Path(__file__).resolve().parents[3] / "scripts/eventkit_helper.swift"
EVENTKIT_TIMEOUT_SECONDS = 10.0
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_PREVIEW_TITLE_CHARS = 512
MAX_PREVIEW_LIST_CHARS = 512
DEFAULT_EVENTKIT_SCAN_LIMIT = 10000
EVENTKIT_REMINDER_HANDLE_PREFIX = "reminders:reminder:eventkit"
PLAN_OPERATIONS = {"create", "complete", "update_due_date"}
APPROVAL_TOKEN_PREFIX = "reminders-apply:v1:"
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


def _apple_timestamp(moment: datetime) -> float:
    return (moment.astimezone(UTC) - APPLE_EPOCH).total_seconds()


def _store_paths(store_dir: Path) -> list[Path]:
    if not store_dir.exists() or not store_dir.is_dir():
        raise StoreUnavailableError("Reminders store directory unavailable.")
    paths = sorted(store_dir.glob("*.sqlite"))
    if not paths:
        raise StoreUnavailableError("No Reminders SQLite stores found.")
    return paths


def _check_schema(connection) -> str:
    require_columns(
        connection,
        "ZREMCDREMINDER",
        {
            "Z_PK",
            "ZTITLE",
            "ZNOTES",
            "ZDUEDATE",
            "ZDISPLAYDATEDATE",
            "ZCOMPLETED",
            "ZFLAGGED",
            "ZPRIORITY",
            "ZMARKEDFORDELETION",
            "ZLIST",
        },
    )
    require_columns(connection, "ZREMCDBASELIST", {"Z_PK", "ZNAME"})
    return schema_fingerprint(connection, REMINDERS_TABLES)


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "reminders",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "empty_query",
                "message": "Reminders metadata search requires a non-empty title query.",
            }
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "reminders",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "broad_query",
                "message": "Reminders metadata search requires at least two letters or digits.",
            }
        ],
    }


def _store_ref(store_name: str) -> str:
    digest = hashlib.sha256(store_name.encode("utf-8")).hexdigest()[:12]
    return f"reminders-store:{digest}"


def check_reminders_schema(*, store_dir: Path = DEFAULT_REMINDERS_DIR) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    stores: list[dict[str, Any]] = []
    try:
        paths = _store_paths(store_dir)
    except StoreUnavailableError as exc:
        return {
            "status": "degraded",
            "source": "reminders",
            "stores": [],
            "warnings": [{"code": "reminders_store_unavailable", "message": str(exc)}],
        }

    for path in paths:
        try:
            with connect_readonly(path) as connection:
                fingerprint = _check_schema(connection)
            stores.append(
                {
                    "store_ref": _store_ref(path.name),
                    "status": "ok",
                    "schema_fingerprint": fingerprint,
                    "tables_checked": REMINDERS_TABLES,
                }
            )
        except StoreUnavailableError as exc:
            warnings.append(
                {
                    "code": "reminders_schema_unavailable",
                    "message": f"{_store_ref(path.name)}: {exc}",
                }
            )
            stores.append(
                {
                    "store_ref": _store_ref(path.name),
                    "status": "degraded",
                    "schema_fingerprint": None,
                    "tables_checked": REMINDERS_TABLES,
                }
            )

    return {
        "status": "ok" if not warnings else "degraded",
        "source": "reminders",
        "stores": stores,
        "warnings": warnings,
    }


def _row_to_metadata(row, store_name: str) -> dict[str, Any]:
    store_ref = _store_ref(store_name)
    return {
        "handle": make_opaque_handle("reminders:reminder", store_name, row["reminder_id"]),
        "store_ref": store_ref,
        "title": row["title"],
        "list_name": row["list_name"],
        "due_date": row["due_date"],
        "display_date": row["display_date"],
        "completed": bool(row["completed"]) if row["completed"] is not None else None,
        "flagged": bool(row["flagged"]) if row["flagged"] is not None else None,
        "priority": row["priority"],
        "notes_present": bool(row["notes_present"]),
    }


def _query_store(path: Path, sql: str, params: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
    with connect_readonly(path) as connection:
        _check_schema(connection)
        rows = connection.execute(sql, params).fetchmany(limit)
    return [_row_to_metadata(row, path.name) for row in rows]


def search_reminders_metadata(
    query: str,
    *,
    store_dir: Path = DEFAULT_REMINDERS_DIR,
    limit: int = 50,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    try:
        paths = _store_paths(store_dir)
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [{"code": "reminders_store_unavailable", "message": str(exc)}],
        }

    sql = """
        SELECT
            r.Z_PK AS reminder_id,
            r.ZTITLE AS title,
            l.ZNAME AS list_name,
            r.ZDUEDATE AS due_date,
            r.ZDISPLAYDATEDATE AS display_date,
            r.ZCOMPLETED AS completed,
            r.ZFLAGGED AS flagged,
            r.ZPRIORITY AS priority,
            CASE WHEN r.ZNOTES IS NULL OR r.ZNOTES = '' THEN 0 ELSE 1 END AS notes_present
        FROM ZREMCDREMINDER r
        LEFT JOIN ZREMCDBASELIST l ON r.ZLIST = l.Z_PK
        WHERE COALESCE(r.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(r.ZCOMPLETED, 0) = 0
          AND r.ZTITLE LIKE ? ESCAPE '\\'
        ORDER BY COALESCE(r.ZDUEDATE, r.ZDISPLAYDATEDATE, r.ZCREATIONDATE, 0) ASC
        LIMIT ?
    """
    for path in paths:
        remaining = bounded_limit - len(results)
        if remaining <= 0:
            break
        try:
            results.extend(
                _query_store(path, sql, (like_contains_pattern(query), remaining), remaining)
            )
        except StoreUnavailableError as exc:
            warnings.append(
                {
                    "code": "reminders_store_query_failed",
                    "message": f"{_store_ref(path.name)}: {exc}",
                }
            )

    return {
        "schema_version": 1,
        "status": "ok" if not warnings else "degraded",
        "source": "reminders",
        "privacy": _privacy(),
        "query": {"scope": "title", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def due_reminders_metadata(
    *,
    store_dir: Path = DEFAULT_REMINDERS_DIR,
    days: int = 14,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    bounded_days = max(0, min(days, 31))
    bounded_limit = max(1, min(limit, 50))
    now = now or datetime.now(UTC)
    start = _apple_timestamp(now - timedelta(days=1))
    end = _apple_timestamp(now + timedelta(days=bounded_days))
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    try:
        paths = _store_paths(store_dir)
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [{"code": "reminders_store_unavailable", "message": str(exc)}],
        }

    sql = """
        SELECT
            r.Z_PK AS reminder_id,
            r.ZTITLE AS title,
            l.ZNAME AS list_name,
            r.ZDUEDATE AS due_date,
            r.ZDISPLAYDATEDATE AS display_date,
            r.ZCOMPLETED AS completed,
            r.ZFLAGGED AS flagged,
            r.ZPRIORITY AS priority,
            CASE WHEN r.ZNOTES IS NULL OR r.ZNOTES = '' THEN 0 ELSE 1 END AS notes_present
        FROM ZREMCDREMINDER r
        LEFT JOIN ZREMCDBASELIST l ON r.ZLIST = l.Z_PK
        WHERE COALESCE(r.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(r.ZCOMPLETED, 0) = 0
          AND r.ZDUEDATE IS NOT NULL
          AND r.ZDUEDATE >= ?
          AND r.ZDUEDATE <= ?
        ORDER BY r.ZDUEDATE ASC
        LIMIT ?
    """
    for path in paths:
        remaining = bounded_limit - len(results)
        if remaining <= 0:
            break
        try:
            results.extend(_query_store(path, sql, (start, end, remaining), remaining))
        except StoreUnavailableError as exc:
            warnings.append(
                {
                    "code": "reminders_store_query_failed",
                    "message": f"{_store_ref(path.name)}: {exc}",
                }
            )

    results.sort(key=lambda item: item["due_date"] if item["due_date"] is not None else 0)
    return {
        "schema_version": 1,
        "status": "ok" if not warnings else "degraded",
        "source": "reminders",
        "privacy": _privacy(),
        "query": {"scope": "due", "days": bounded_days, "limit": bounded_limit},
        "results": results[:bounded_limit],
        "result_count": min(len(results), bounded_limit),
        "warnings": warnings,
    }


def search_reminders_eventkit(
    query: str,
    *,
    limit: int = 20,
    include_completed: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _eventkit_reminders_response(
        query=query,
        limit=bounded_limit,
        include_completed=include_completed,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return _eventkit_degraded_result(response, content=False)

    results = [_eventkit_reminder_metadata(reminder) for reminder in response.get("reminders", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "eventkit_title",
            "limit": bounded_limit,
            "include_completed": include_completed,
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def get_reminder_content(
    handle: str,
    *,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    include_completed: bool = True,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, EVENTKIT_REMINDER_HANDLE_PREFIX):
        return _invalid_eventkit_handle_result()

    response = _eventkit_reminders_response(
        query="",
        limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
        include_completed=include_completed,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return _eventkit_degraded_result(response, content=True)

    reminder_id = _resolve_eventkit_reminder_id(handle, response.get("reminders", []))
    if reminder_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = eventkit_runner or _run_eventkit_helper
    try:
        detail = runner(
            {"command": "reminder_by_id", "reminder_id": reminder_id},
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "reminders",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [
                _warning(
                    "eventkit_read_error",
                    "Reminder content could not be read safely.",
                )
            ],
        }

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _eventkit_degraded_result(detail, content=True)

    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "reminders",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [
                _warning(
                    "eventkit_read_error",
                    "Reminder content could not be read safely.",
                )
            ],
        }

    result = _eventkit_reminder_metadata(reminder)
    notes_text, notes_truncated = _bounded_text(str(reminder.get("notes") or ""), max_chars)
    result.update(
        {
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
                "Reminder notes were truncated to the requested limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def plan_reminder_change(
    operation: str,
    *,
    title: str = "",
    list_name: str = "",
    due_date: str = "",
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_completed: bool | str | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create, complete, or update_due_date.",
            )
        )
        return _preview_error(warnings)

    normalized_title, title_warning = _bounded_preview_value(
        title,
        field="title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=normalized_operation == "create",
    )
    if title_warning is not None:
        warnings.append(title_warning)

    normalized_list, list_warning = _bounded_preview_value(
        list_name,
        field="list_name",
        max_chars=MAX_PREVIEW_LIST_CHARS,
        required=normalized_operation == "create",
    )
    if list_warning is not None:
        warnings.append(list_warning)

    normalized_notes, notes_warning = _bounded_preview_value(
        notes,
        field="notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if notes_warning is not None:
        warnings.append(notes_warning)

    normalized_expected_title, expected_title_warning = _bounded_preview_value(
        expected_title,
        field="expected_title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=normalized_operation in {"complete", "update_due_date"},
    )
    if expected_title_warning is not None:
        warnings.append(expected_title_warning)

    normalized_due_date, due_date_warning = _normalize_due_date(
        due_date,
        required=normalized_operation == "update_due_date",
    )
    if due_date_warning is not None:
        warnings.append(due_date_warning)

    normalized_completed, completed_warning = _normalize_expected_completed(expected_completed)
    if completed_warning is not None:
        warnings.append(completed_warning)

    normalized_handle = handle.strip()
    if normalized_operation in {"complete", "update_due_date"} and not is_opaque_handle(
        normalized_handle,
        EVENTKIT_REMINDER_HANDLE_PREFIX,
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected reminders:reminder:eventkit:v1 opaque handle from EventKit search output.",
            )
        )
    if normalized_operation == "create" and normalized_handle:
        warnings.append(
            _warning(
                "unexpected_handle",
                "Create reminder planning requires a target list, not a reminder handle.",
            )
        )

    if warnings:
        return _preview_error(warnings)

    target: dict[str, Any]
    proposed: dict[str, Any]
    if normalized_operation == "create":
        target = {"list_name": normalized_list}
        proposed = {
            "title": normalized_title,
            "due_date": normalized_due_date,
            "notes_text": normalized_notes,
            "notes_chars": len(normalized_notes),
            "notes_present": bool(normalized_notes),
        }
    elif normalized_operation == "complete":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed if normalized_completed is not None else False,
        }
        proposed = {
            "completed": True,
            "due_date": None,
            "notes_present": None,
        }
    else:
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
        }
        proposed = {
            "completed": normalized_completed,
            "due_date": normalized_due_date,
            "notes_present": None,
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
        "source": "reminders",
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


def apply_reminder_change(
    operation: str,
    *,
    title: str = "",
    list_name: str = "",
    due_date: str = "",
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_completed: bool | str | None = None,
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    plan = plan_reminder_change(
        operation,
        title=title,
        list_name=list_name,
        due_date=due_date,
        notes=notes,
        handle=handle,
        expected_title=expected_title,
        expected_completed=expected_completed,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Reminder apply requires a valid plan preview.")],
            plan=plan,
        )

    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Reminder apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Reminder apply approval token did not match the plan.")],
            plan=plan,
        )

    normalized_operation = str(preview["operation"])
    runner = eventkit_runner or _run_eventkit_helper
    helper_payload = _apply_helper_payload(preview)
    if normalized_operation in {"complete", "update_due_date"}:
        response = _eventkit_reminders_response(
            query="",
            limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
            include_completed=True,
            eventkit_runner=eventkit_runner,
        )
        if response.get("status") != "ok":
            return _apply_unavailable(response, plan=plan)
        reminder_id = _resolve_eventkit_reminder_id(
            str(preview["target"]["handle"]),
            response.get("reminders", []),
        )
        if reminder_id is None:
            return _apply_error(
                [_warning("target_not_found", "Reminder target was not found through EventKit.")],
                plan=plan,
            )
        helper_payload["reminder_id"] = reminder_id

    try:
        applied = runner(helper_payload, EVENTKIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("eventkit_timeout", "Reminder apply timed out through the local EventKit helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("eventkit_unavailable", "Reminder apply is unavailable through the local EventKit helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("eventkit_apply_failed", "Reminder change could not be applied safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

    reminder = applied.get("reminder")
    if not isinstance(reminder, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Reminder apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )

    read_back = _eventkit_reminder_metadata(reminder)
    warnings = _safe_warnings(applied)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": normalized_operation,
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _eventkit_reminders_response(
    *,
    query: str,
    limit: int,
    include_completed: bool,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "reminders",
                "query": query,
                "limit": max(1, min(limit, DEFAULT_EVENTKIT_SCAN_LIMIT)),
                "include_completed": include_completed,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminders access timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminders access is unavailable through the local EventKit helper.",
                )
            ],
        }


def _run_eventkit_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(EVENTKIT_HELPER)],
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


def _eventkit_reminder_metadata(reminder: dict[str, Any]) -> dict[str, Any]:
    reminder_id = str(reminder.get("reminder_id") or "")
    return {
        "handle": make_opaque_handle(EVENTKIT_REMINDER_HANDLE_PREFIX, reminder_id),
        "title": reminder.get("title"),
        "list_name": reminder.get("list_name"),
        "due_date": reminder.get("due_date") or None,
        "start_date": reminder.get("start_date") or None,
        "completed": bool(reminder.get("completed")),
        "priority": reminder.get("priority"),
        "notes_present": bool(reminder.get("notes_present")),
        "url_present": bool(reminder.get("url_present")),
        "alarms_count": reminder.get("alarms_count"),
    }


def _resolve_eventkit_reminder_id(handle: str, reminders: Any) -> str | None:
    if not isinstance(reminders, list):
        return None
    for reminder in reminders:
        if not isinstance(reminder, dict):
            continue
        reminder_id = str(reminder.get("reminder_id") or "")
        if reminder_id and opaque_handle_matches(
            handle,
            EVENTKIT_REMINDER_HANDLE_PREFIX,
            reminder_id,
        ):
            return reminder_id
    return None


def _preview_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "reminders",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": False,
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
    return {
        "schema_version": 1,
        "status": status,
        "source": "reminders",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": authorization_status,
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_unavailable(response: dict[str, Any], *, plan: dict[str, Any]) -> dict[str, Any]:
    return _apply_error(
        _safe_warnings(response)
        or [_warning("reminders_access_unavailable", "Reminders apply is unavailable.")],
        plan=plan,
        status="degraded",
        authorization_status=response.get("authorization_status"),
    )


def _invalid_eventkit_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "reminders",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected reminders:reminder:eventkit:v1 opaque handle from EventKit search output.",
            )
        ],
    }


def _eventkit_degraded_result(response: dict[str, Any], *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "reminders",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": _safe_warnings(response),
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


def _normalize_due_date(
    value: str,
    *,
    required: bool,
) -> tuple[str | None, dict[str, str] | None]:
    stripped = value.strip()
    if not stripped:
        if required:
            return None, _warning("missing_required_field", "Missing required field: due_date.")
        return None, None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
        return stripped, None
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None, _warning(
            "invalid_due_date",
            "Due date must be YYYY-MM-DD or ISO 8601 with a timezone.",
        )
    if parsed.tzinfo is None:
        return None, _warning(
            "invalid_due_date",
            "Due date timestamps must include a timezone.",
        )
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"), None


def _normalize_expected_completed(
    value: bool | str | None,
) -> tuple[bool | None, dict[str, str] | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return value, None
    lowered = value.strip().casefold()
    if lowered == "true":
        return True, None
    if lowered == "false":
        return False, None
    return None, _warning(
        "invalid_expected_completed",
        "Expected completed state must be true or false.",
    )


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"reminders-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _apply_helper_payload(preview: dict[str, Any]) -> dict[str, Any]:
    operation = str(preview["operation"])
    target = preview["target"]
    proposed = preview["proposed"]
    payload: dict[str, Any] = {
        "command": "reminder_apply_change",
        "operation": operation,
    }
    if operation == "create":
        payload.update(
            {
                "title": proposed["title"],
                "list_name": target["list_name"],
                "due_date": proposed["due_date"] or "",
                "notes": proposed["notes_text"],
            }
        )
    elif operation == "complete":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "completed": True,
            }
        )
    else:
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "due_date": proposed["due_date"],
            }
        )
    return payload


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= bounded_chars:
        return normalized, False
    return normalized[:bounded_chars], True
