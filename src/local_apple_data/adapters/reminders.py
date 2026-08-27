from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)
from .calendar import _run_eventkit_helper as _run_eventkit_helper_app
from .calendar import _prepare_eventkit_helper_signing
from .calendar import (
    MAX_RECURRENCE_END_DAYS as _CAL_MAX_RECURRENCE_END_DAYS,
    _empty_recurrence,
    _normalize_recurrence,
)
from .warning_safety import safe_warning_payloads


DEFAULT_REMINDERS_DIR = (
    Path.home()
    / "Library/Group Containers/group.com.apple.reminders/Container_v1/Stores"
)

REMINDERS_TABLES = ["ZREMCDREMINDER", "ZREMCDBASELIST"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
EVENTKIT_TIMEOUT_SECONDS = 10.0
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_PREVIEW_TITLE_CHARS = 512
MAX_PREVIEW_LIST_CHARS = 512
DEFAULT_EVENTKIT_SCAN_LIMIT = 10000
MAX_REMINDER_URL_CHARS = 2048
MAX_REMINDER_ALARMS = 8
MIN_REMINDER_ALARM_OFFSET_MINUTES = -40320
MAX_REMINDER_ALARM_OFFSET_MINUTES = 40320
SAFE_REMINDER_URL_SCHEMES = {"http", "https", "mailto", "tel"}
MAILTO_REMINDER_URL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
TEL_REMINDER_URL_RE = re.compile(r"^\+?[0-9][0-9().-]{1,31}(?:;ext=[0-9]{1,10})?$")
EVENTKIT_REMINDER_HANDLE_PREFIX = "reminders:reminder:eventkit"
EVENTKIT_REMINDER_LIST_HANDLE_PREFIX = "reminders:list:eventkit"
PLAN_OPERATIONS = {
    "create",
    "create_with_start_date",
    "create_with_recurrence",
    "complete",
    "uncomplete",
    "update_due_date",
    "update_start_date",
    "update_recurrence",
    "update_title",
    "update_notes",
    "update_priority",
    "update_url",
    "clear_url",
    "set_absolute_display_alarm",
    "set_relative_display_alarm",
    "set_mixed_display_alarm",
    "clear_display_alarm",
    "move_to_list",
    "delete",
}
CREATE_OPERATIONS = {"create", "create_with_start_date", "create_with_recurrence"}
START_DATE_OPERATIONS = {"create_with_start_date", "update_start_date"}
RECURRENCE_OPERATIONS = {"create_with_recurrence", "update_recurrence"}
LIST_MANAGEMENT_OPERATIONS = {
    "create_list",
    "rename_list",
    "delete_list",
    "delete_list_with_migration",
}
MAX_REMINDER_LIST_MIGRATION_COUNT = 50
EXISTING_REMINDER_OPERATIONS = PLAN_OPERATIONS - CREATE_OPERATIONS
PRIORITY_OPERATIONS = {"update_priority"}
EXPECTED_PRIORITY_OPERATIONS = {"update_priority", "delete"}
EXPECTED_NOTES_SHA_OPERATIONS = {"update_notes", "delete"}
URL_OPERATIONS = {"update_url", "clear_url"}
ALARM_OPERATIONS = {
    "set_absolute_display_alarm",
    "set_relative_display_alarm",
    "set_mixed_display_alarm",
    "clear_display_alarm",
}
ALARM_ABSOLUTE_DATE_OPERATIONS = {"set_absolute_display_alarm", "set_mixed_display_alarm"}
ALARM_OFFSET_OPERATIONS = {"set_relative_display_alarm", "set_mixed_display_alarm"}
LIST_TARGET_OPERATIONS = {"move_to_list"}
APPROVAL_TOKEN_PREFIX = "reminders-apply:v1:"
EventKitRunner = Callable[[dict[str, Any], float], dict[str, Any]]


def _privacy(*, list_items_returned: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
        "reminder_notes_returned": False,
        "raw_identifier_returned": False,
        "reminder_url_returned": False,
        "reminder_alarm_details_returned": False,
        "list_items_returned": list_items_returned,
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


def _reminders_store_unavailable_warning() -> dict[str, str]:
    return _warning(
        "reminders_store_unavailable",
        "Reminders local store is unavailable or unreadable.",
    )


def _reminders_schema_unavailable_warning(store_ref: str) -> dict[str, str]:
    return _warning(
        "reminders_schema_unavailable",
        f"{store_ref}: Reminders schema is unavailable or unsupported.",
    )


def _reminders_store_query_failed_warning(store_ref: str) -> dict[str, str]:
    return _warning(
        "reminders_store_query_failed",
        f"{store_ref}: Reminders local store could not be queried safely.",
    )


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
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "reminders",
            "stores": [],
            "warnings": [_reminders_store_unavailable_warning()],
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
        except StoreUnavailableError:
            warnings.append(_reminders_schema_unavailable_warning(_store_ref(path.name)))
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
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_reminders_store_unavailable_warning()],
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
        except StoreUnavailableError:
            warnings.append(_reminders_store_query_failed_warning(_store_ref(path.name)))

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
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_reminders_store_unavailable_warning()],
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
        except StoreUnavailableError:
            warnings.append(_reminders_store_query_failed_warning(_store_ref(path.name)))

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


def search_reminder_lists(
    query: str,
    *,
    limit: int = 20,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "empty_query",
                    "Reminders list search requires a non-empty list-title query.",
                )
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "broad_query",
                    "Reminders list search requires at least two letters or digits.",
                )
            ],
        }

    bounded_limit = max(1, min(limit, 50))
    response = _eventkit_reminder_lists_response(
        query=query,
        limit=bounded_limit,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return _eventkit_degraded_result(response, content=False)

    results = [_eventkit_reminder_list_metadata(item) for item in response.get("lists", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {"scope": "eventkit_list_title", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def list_reminder_lists(
    *,
    limit: int = 20,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    """Enumerate all Reminders lists as capped metadata, without a title query.

    Read-only. Exists so agents can see every target list (including shared
    ones) before writing anywhere; title-substring search alone cannot prove a
    list does not exist.
    """
    bounded_limit = max(1, min(limit, 50))
    response = _eventkit_reminder_lists_response(
        query="",
        limit=bounded_limit + 1,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return _eventkit_degraded_result(response, content=False)

    items = response.get("lists", [])
    truncated = isinstance(items, list) and len(items) > bounded_limit
    results = [_eventkit_reminder_list_metadata(item) for item in items[:bounded_limit]]
    warnings = _safe_warnings(response)
    if truncated:
        warnings.append(
            _warning(
                "results_truncated",
                "More Reminders lists exist than the requested limit; raise limit (max 50) to see the rest.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {"scope": "eventkit_all_lists", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def get_reminder_list(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, EVENTKIT_REMINDER_LIST_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "privacy": _privacy(),
            "result": None,
            "result_count": 0,
            "warnings": [
                _warning(
                    "invalid_handle",
                    "Expected reminders:list:eventkit:v1 opaque handle from Reminders list search output.",
                )
            ],
        }
    response = _eventkit_reminder_lists_response(
        query="",
        limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return _eventkit_degraded_result(response, content=False)

    list_id = _resolve_eventkit_list_id(handle, response.get("lists", []))
    if list_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders",
            "privacy": _privacy(),
            "authorization_status": response.get("authorization_status"),
            "result": None,
            "result_count": 0,
            "warnings": [],
        }
    selected = next(
        item
        for item in response.get("lists", [])
        if str(item.get("list_id") or "") == list_id
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "result": _eventkit_reminder_list_metadata(selected),
        "result_count": 1,
        "warnings": _safe_warnings(response),
    }


def list_reminder_items(
    handle: str,
    *,
    limit: int = 20,
    include_completed: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, EVENTKIT_REMINDER_LIST_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders_list_items",
            "privacy": _privacy(list_items_returned=False),
            "list": None,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "invalid_handle",
                    "Expected reminders:list:eventkit:v1 opaque handle from Reminders list output.",
                )
            ],
        }

    bounded_limit = max(1, min(limit, 50))
    lists_response = _eventkit_reminder_lists_response(
        query="",
        limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
        include_counts=False,
        eventkit_runner=eventkit_runner,
    )
    if lists_response.get("status") != "ok":
        degraded = _eventkit_degraded_result(lists_response, content=False)
        degraded["source"] = "reminders_list_items"
        degraded["list"] = None
        return degraded

    list_id = _resolve_eventkit_list_id(handle, lists_response.get("lists", []))
    if list_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders_list_items",
            "privacy": _privacy(list_items_returned=False),
            "authorization_status": lists_response.get("authorization_status"),
            "list": None,
            "results": [],
            "result_count": 0,
            "warnings": _safe_warnings(lists_response),
        }

    selected = _find_reminder_list_by_id(lists_response.get("lists", []), list_id)
    response = _eventkit_reminders_for_list_response(
        list_id=list_id,
        limit=bounded_limit,
        include_completed=include_completed,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders_list_items",
            "privacy": _privacy(list_items_returned=False),
            "authorization_status": response.get("authorization_status"),
            "list": None,
            "results": [],
            "result_count": 0,
            "warnings": _safe_warnings(response),
        }
    if response.get("status") != "ok":
        degraded = _eventkit_degraded_result(response, content=False)
        degraded["source"] = "reminders_list_items"
        degraded["list"] = _eventkit_reminder_list_metadata(selected) if selected else None
        return degraded

    list_payload = response.get("list") if isinstance(response.get("list"), dict) else selected
    results = [_eventkit_reminder_metadata(reminder) for reminder in response.get("reminders", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders_list_items",
        "privacy": _privacy(list_items_returned=True),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "selected_list_items",
            "limit": bounded_limit,
            "include_completed": include_completed,
        },
        "list": _eventkit_reminder_list_metadata(list_payload)
        if isinstance(list_payload, dict)
        else None,
        "results": results,
        "result_count": len(results),
        "warnings": [*_safe_warnings(lists_response), *_safe_warnings(response)],
    }


def plan_reminder_list_change(
    operation: str,
    *,
    source_list_handle: str = "",
    list_handle: str = "",
    target_list_handle: str = "",
    list_title: str = "",
    new_list_title: str = "",
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    if normalized_operation not in LIST_MANAGEMENT_OPERATIONS:
        return _preview_error(
            [
                _warning(
                    "invalid_operation",
                    "Expected operation create_list, rename_list, delete_list, or delete_list_with_migration.",
                )
            ]
        )
    if normalized_operation == "create_list":
        return _plan_reminder_list_create(
            source_list_handle=source_list_handle,
            list_title=list_title,
            list_handle=list_handle,
            new_list_title=new_list_title,
            target_list_handle=target_list_handle,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "rename_list":
        return _plan_reminder_list_rename(
            list_handle=list_handle,
            new_list_title=new_list_title,
            source_list_handle=source_list_handle,
            list_title=list_title,
            target_list_handle=target_list_handle,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "delete_list":
        return _plan_reminder_list_delete(
            list_handle=list_handle,
            source_list_handle=source_list_handle,
            list_title=list_title,
            new_list_title=new_list_title,
            target_list_handle=target_list_handle,
            eventkit_runner=eventkit_runner,
        )
    if normalized_operation == "delete_list_with_migration":
        return _plan_reminder_list_delete_with_migration(
            list_handle=list_handle,
            target_list_handle=target_list_handle,
            source_list_handle=source_list_handle,
            list_title=list_title,
            new_list_title=new_list_title,
            eventkit_runner=eventkit_runner,
        )
    raise AssertionError(f"unhandled reminder list operation: {normalized_operation}")


def apply_reminder_list_change(
    operation: str,
    *,
    source_list_handle: str = "",
    list_handle: str = "",
    target_list_handle: str = "",
    list_title: str = "",
    new_list_title: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    plan = plan_reminder_list_change(
        operation,
        source_list_handle=source_list_handle,
        list_handle=list_handle,
        target_list_handle=target_list_handle,
        list_title=list_title,
        new_list_title=new_list_title,
        eventkit_runner=runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Reminder list apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Reminder list apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Reminder list apply approval token did not match the plan.")],
            plan=plan,
        )

    resolve_result = _resolve_reminder_list_for_management_apply(preview, eventkit_runner=runner)
    if resolve_result["status"] != "ok":
        return _apply_error(
            resolve_result["warnings"],
            plan=plan,
            status=resolve_result["status"],
        )

    helper_payload = _reminder_list_apply_helper_payload(preview, resolve_result)
    try:
        applied = runner(helper_payload, EVENTKIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("eventkit_timeout", "Reminder list apply timed out through EventKit.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("eventkit_unavailable", "Reminder list apply is unavailable through EventKit.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("eventkit_apply_failed", "Reminder list apply failed.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            mutation_applied=bool(applied.get("mutation_applied")),
            authorization_status=applied.get("authorization_status"),
        )

    operation_name = str(preview["operation"])
    if operation_name in {"delete_list", "delete_list_with_migration"}:
        helper_read_back = applied.get("read_back")
        if not isinstance(helper_read_back, dict):
            return _apply_error(
                [_warning("read_back_unavailable", "Reminder list delete read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        delete_verified = (
            helper_read_back.get("list_deleted_verified") is True
            and helper_read_back.get("list_absent_verified") is True
        )
        if operation_name == "delete_list":
            delete_verified = (
                delete_verified and helper_read_back.get("list_empty_verified") is True
            )
        else:
            expected_migrated = int(preview["proposed"]["migrated_reminder_count"])
            expected_target_before = int(preview["proposed"]["target_reminder_count"])
            actual_target_before = helper_read_back.get("target_count_before")
            actual_target_after = helper_read_back.get("target_count_after")
            delete_verified = (
                delete_verified
                and helper_read_back.get("list_migrated_verified") is True
                and helper_read_back.get("source_list_empty_verified") is True
                and helper_read_back.get("target_list_verified") is True
                and int(helper_read_back.get("migrated_count") or 0) == expected_migrated
                and actual_target_before == expected_target_before
                and actual_target_after == expected_target_before + expected_migrated
            )
        if not delete_verified:
            return _apply_error(
                [
                    _warning(
                        "list_delete_read_back_mismatch",
                        "Reminder list delete proof did not match the approved state.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back = {
            "list_handle": preview["target"]["list_handle"],
            "list_title": preview["target"]["list_title"],
            "list_empty_verified": True,
            "list_deleted_verified": True,
            "list_absent_verified": True,
        }
        if operation_name == "delete_list_with_migration":
            read_back = {
                "list_handle": preview["target"]["list_handle"],
                "list_title": preview["target"]["list_title"],
                "target_list_handle": preview["proposed"]["target_list_handle"],
                "target_list_title": preview["proposed"]["target_list_title"],
                "migrated_count": int(helper_read_back.get("migrated_count") or 0),
                "target_count_before": int(helper_read_back.get("target_count_before") or 0),
                "target_count_after": int(helper_read_back.get("target_count_after") or 0),
                "source_list_empty_verified": True,
                "target_list_verified": True,
                "list_deleted_verified": True,
                "list_absent_verified": True,
            }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": operation_name,
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": read_back,
            "result_count": 0,
            "warnings": _safe_warnings(applied),
        }

    reminder_list = applied.get("list")
    if not isinstance(reminder_list, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Reminder list apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    read_back = _eventkit_reminder_list_metadata(reminder_list)
    expected_title = (
        preview["proposed"]["list_title"]
        if operation_name == "create_list"
        else preview["proposed"]["new_list_title"]
    )
    if read_back.get("title") != expected_title:
        return _apply_error(
            [_warning("list_title_read_back_mismatch", "Reminder list title read-back did not match the approved value.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if operation_name == "create_list":
        helper_read_back = applied.get("read_back")
        expected_source_sha = str(preview["target"]["source_safe_sha256"])
        if (
            not isinstance(helper_read_back, dict)
            or helper_read_back.get("source_list_verified") is not True
            or helper_read_back.get("list_empty_verified") is not True
            or read_back.get("source_safe_sha256") != expected_source_sha
        ):
            return _apply_error(
                [_warning("list_create_read_back_mismatch", "Reminder list create proof did not match the approved source state.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["source_list_handle"] = preview["target"]["source_list_handle"]
        read_back["source_list_verified"] = True
        read_back["empty_list_verified"] = True
    else:
        helper_read_back = applied.get("read_back")
        if not isinstance(helper_read_back, dict) or helper_read_back.get("list_renamed_verified") is not True:
            return _apply_error(
                [_warning("list_rename_read_back_mismatch", "Reminder list rename proof did not match the approved state.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        if helper_read_back.get("list_empty_verified") is not True:
            return _apply_error(
                [_warning("list_rename_read_back_mismatch", "Reminder list rename empty-list proof failed.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["list_handle"] = preview["target"]["list_handle"]
        read_back["empty_list_verified"] = True

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": operation_name,
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": _safe_warnings(applied),
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
            {"command": "reminder_by_id", "reminder_id": reminder_id, "include_content": True},
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

    result = _eventkit_reminder_metadata(reminder, include_url_proof=True)
    normalized_full_notes = str(reminder.get("notes") or "").replace("\r\n", "\n").replace("\r", "\n")
    notes_text, notes_truncated = _bounded_text(normalized_full_notes, max_chars)
    result.update(
        {
            "notes_text": notes_text,
            "notes_chars": len(notes_text),
            "notes_truncated": notes_truncated,
            "notes_sha256": hashlib.sha256(normalized_full_notes.encode("utf-8")).hexdigest(),
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
    title: str | None = "",
    list_name: str = "",
    due_date: str = "",
    start_date: str = "",
    expected_start_date: str = "",
    notes: str | None = None,
    handle: str = "",
    expected_title: str = "",
    expected_completed: bool | str | None = None,
    expected_list_name: str = "",
    expected_list_handle: str = "",
    target_list_handle: str = "",
    expected_priority: int | str | None = None,
    expected_notes_sha256: str = "",
    priority: int | str | None = None,
    url: str = "",
    expected_url_present: bool | str | None = None,
    expected_url_sha256: str = "",
    alarm_absolute_dates: list[str] | None = None,
    alarm_offsets_minutes: list[int] | None = None,
    expected_alarms_count: int | str | None = None,
    expected_alarms_sha256: str = "",
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    clear_recurrence: bool = False,
    expected_recurrence_present: bool | str | None = None,
    expected_recurrence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create, create_with_start_date, create_with_recurrence, complete, uncomplete, update_due_date, update_start_date, update_recurrence, update_title, update_notes, update_priority, update_url, clear_url, set_absolute_display_alarm, set_relative_display_alarm, set_mixed_display_alarm, clear_display_alarm, move_to_list, or delete.",
            )
        )
        return _preview_error(warnings)

    normalized_title, title_warning = _bounded_preview_value(
        title or "",
        field="title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=normalized_operation in CREATE_OPERATIONS | {"update_title"},
    )
    if title_warning is not None:
        warnings.append(title_warning)

    normalized_list, list_warning = _bounded_preview_value(
        list_name,
        field="list_name",
        max_chars=MAX_PREVIEW_LIST_CHARS,
        required=normalized_operation in CREATE_OPERATIONS,
    )
    if list_warning is not None:
        warnings.append(list_warning)

    notes_was_provided = notes is not None
    normalized_notes, notes_warning = _bounded_preview_value(
        notes or "",
        field="notes",
        max_chars=MAX_CONTENT_CHARS,
        required=False,
    )
    if notes_warning is not None:
        warnings.append(notes_warning)
    if normalized_operation == "update_notes" and not notes_was_provided:
        warnings.append(_warning("missing_required_field", "Missing required field: notes."))

    normalized_expected_title, expected_title_warning = _bounded_preview_value(
        expected_title,
        field="expected_title",
        max_chars=MAX_PREVIEW_TITLE_CHARS,
        required=normalized_operation in EXISTING_REMINDER_OPERATIONS,
    )
    if expected_title_warning is not None:
        warnings.append(expected_title_warning)

    normalized_expected_list_name, expected_list_warning = _bounded_preview_value(
        expected_list_name,
        field="expected_list_name",
        max_chars=MAX_PREVIEW_LIST_CHARS,
        required=normalized_operation in LIST_TARGET_OPERATIONS,
    )
    if expected_list_warning is not None:
        warnings.append(expected_list_warning)

    normalized_due_date, due_date_warning = _normalize_due_date(
        due_date,
        required=normalized_operation == "update_due_date",
    )
    if due_date_warning is not None:
        warnings.append(due_date_warning)

    normalized_start_date, start_date_warning = _normalize_start_date(
        start_date,
        required=normalized_operation == "create_with_start_date",
    )
    if start_date_warning is not None:
        warnings.append(start_date_warning)
    if normalized_operation not in START_DATE_OPERATIONS and normalized_start_date:
        warnings.append(
            _warning(
                "unsupported_start_date_for_operation",
                "Reminder start date input is supported only for create_with_start_date and update_start_date.",
            )
        )

    normalized_expected_start_date, expected_start_date_warning = _normalize_start_date(
        expected_start_date,
        required=False,
    )
    if expected_start_date_warning is not None:
        warnings.append(expected_start_date_warning)
    if normalized_operation != "update_start_date" and normalized_expected_start_date:
        warnings.append(
            _warning(
                "unsupported_expected_start_date_for_operation",
                "Reminder expected_start_date is supported only for update_start_date.",
            )
        )

    normalized_recurrence, recurrence_warning = _normalize_recurrence(
        frequency=recurrence_frequency,
        interval=recurrence_interval,
        count=recurrence_count,
        end_date=recurrence_end_date,
        unbounded=recurrence_unbounded,
        weekdays=recurrence_weekdays,
        month_days=recurrence_month_days,
        month_weekdays=recurrence_month_weekdays,
        year_months=recurrence_year_months,
        year_month_days=recurrence_year_month_days,
        year_month_weekdays=recurrence_year_month_weekdays,
        year_days=recurrence_year_days,
        year_weeks=recurrence_year_weeks,
        set_positions=recurrence_set_positions,
    )
    if recurrence_warning is not None:
        warnings.append(recurrence_warning)
    normalized_recurrence_present = bool(
        normalized_recurrence and normalized_recurrence.get("recurrence_present")
    )
    normalized_clear_recurrence, clear_recurrence_warning = _normalize_bool(
        clear_recurrence,
        field="clear_recurrence",
        required=False,
    )
    if clear_recurrence_warning is not None:
        warnings.append(clear_recurrence_warning)
    if normalized_operation not in RECURRENCE_OPERATIONS and normalized_recurrence_present:
        warnings.append(
            _warning(
                "unsupported_recurrence_for_operation",
                "Reminder recurrence fields are supported only for create_with_recurrence and update_recurrence.",
            )
        )
    if normalized_operation != "update_recurrence" and normalized_clear_recurrence:
        warnings.append(
            _warning(
                "unsupported_clear_recurrence_for_operation",
                "Reminder clear_recurrence is supported only for update_recurrence.",
            )
        )

    normalized_completed, completed_warning = _normalize_expected_completed(expected_completed)
    if completed_warning is not None:
        warnings.append(completed_warning)
    if normalized_operation in {"move_to_list", "delete"} | URL_OPERATIONS | ALARM_OPERATIONS and normalized_completed is None:
        warnings.append(_warning("missing_required_field", "Missing required field: expected_completed."))

    normalized_expected_priority, expected_priority_warning = _normalize_priority(
        expected_priority,
        field="expected_priority",
        required=normalized_operation in EXPECTED_PRIORITY_OPERATIONS,
    )
    if expected_priority_warning is not None:
        warnings.append(expected_priority_warning)

    normalized_priority, priority_warning = _normalize_priority(
        priority,
        field="priority",
        required=normalized_operation in PRIORITY_OPERATIONS,
    )
    if priority_warning is not None:
        warnings.append(priority_warning)

    normalized_url, url_scheme, url_domain, url_sha256, url_warning = _normalize_reminder_url(
        url,
        field="url",
        required=normalized_operation == "update_url",
    )
    if url_warning is not None:
        warnings.append(url_warning)
    if normalized_operation == "clear_url" and normalized_url:
        warnings.append(_warning("unexpected_url", "Reminder clear_url does not accept a replacement URL."))
    if normalized_operation not in URL_OPERATIONS and normalized_url:
        warnings.append(
            _warning(
                "unsupported_url_for_operation",
                "Reminder URL input is supported only for update_url.",
            )
        )

    normalized_expected_url_present, expected_url_present_warning = _normalize_bool(
        expected_url_present,
        field="expected_url_present",
        required=normalized_operation in URL_OPERATIONS,
    )
    if expected_url_present_warning is not None:
        warnings.append(expected_url_present_warning)
    normalized_expected_url_sha, url_sha_warning = _normalize_sha256(
        expected_url_sha256,
        field="expected_url_sha256",
        required=normalized_operation in URL_OPERATIONS
        and normalized_expected_url_present is True,
    )
    if url_sha_warning is not None:
        warnings.append(url_sha_warning)
    if normalized_operation in URL_OPERATIONS:
        if normalized_expected_url_present and not normalized_expected_url_sha:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder expected_url_sha256 is required when expected_url_present=true.",
                )
            )
        if normalized_expected_url_present is False and normalized_expected_url_sha:
            warnings.append(
                _warning(
                    "unexpected_expected_url_sha256",
                    "Reminder expected_url_sha256 requires expected_url_present=true.",
                )
            )
        if normalized_operation == "clear_url" and normalized_expected_url_present is not True:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder clear_url requires expected_url_present=true.",
                )
            )

    normalized_alarm_absolute_dates, alarm_dates_warning = _normalize_alarm_absolute_dates(
        alarm_absolute_dates,
        field="alarm_absolute_dates",
        required=normalized_operation in ALARM_ABSOLUTE_DATE_OPERATIONS,
    )
    if alarm_dates_warning is not None:
        warnings.append(alarm_dates_warning)
    if normalized_operation not in ALARM_ABSOLUTE_DATE_OPERATIONS and normalized_alarm_absolute_dates:
        warnings.append(
            _warning(
                "unsupported_alarm_dates_for_operation",
                "Reminder absolute alarm dates are supported only for set_absolute_display_alarm and set_mixed_display_alarm.",
            )
        )
    if normalized_operation == "clear_display_alarm" and normalized_alarm_absolute_dates:
        warnings.append(
            _warning(
                "unexpected_alarm_absolute_dates",
                "Reminder clear_display_alarm does not accept replacement alarm dates.",
            )
        )
    if normalized_operation == "set_relative_display_alarm" and normalized_alarm_absolute_dates:
        warnings.append(
            _warning(
                "unexpected_alarm_absolute_dates",
                "Reminder set_relative_display_alarm accepts alarm_offsets_minutes, not alarm_absolute_dates.",
            )
        )

    normalized_alarm_offsets, alarm_offsets_warning = _normalize_alarm_offsets(
        alarm_offsets_minutes,
        field="alarm_offsets_minutes",
        required=normalized_operation in ALARM_OFFSET_OPERATIONS,
    )
    if alarm_offsets_warning is not None:
        warnings.append(alarm_offsets_warning)
    if normalized_operation not in ALARM_OFFSET_OPERATIONS and normalized_alarm_offsets:
        warnings.append(
            _warning(
                "unsupported_alarm_offsets_for_operation",
                "Reminder relative alarm offsets are supported only for set_relative_display_alarm and set_mixed_display_alarm.",
            )
        )
    if normalized_operation == "clear_display_alarm" and normalized_alarm_offsets:
        warnings.append(
            _warning(
                "unexpected_alarm_offsets",
                "Reminder clear_display_alarm does not accept replacement alarm offsets.",
            )
        )
    if (
        normalized_operation == "set_mixed_display_alarm"
        and normalized_alarm_offsets
        and normalized_alarm_absolute_dates
        and len(normalized_alarm_offsets) + len(normalized_alarm_absolute_dates) > MAX_REMINDER_ALARMS
    ):
        warnings.append(
            _warning(
                "too_many_alarms",
                f"Reminder set_mixed_display_alarm supports at most {MAX_REMINDER_ALARMS} combined alarm offsets and dates.",
            )
        )

    normalized_expected_alarms_count, expected_alarms_count_warning = _normalize_expected_alarms_count(
        expected_alarms_count,
        required=normalized_operation in ALARM_OPERATIONS,
    )
    if expected_alarms_count_warning is not None:
        warnings.append(expected_alarms_count_warning)
    normalized_expected_alarms_sha, expected_alarms_sha_warning = _normalize_sha256(
        expected_alarms_sha256,
        field="expected_alarms_sha256",
        required=normalized_operation in ALARM_OPERATIONS
        and normalized_expected_alarms_count is not None
        and normalized_expected_alarms_count > 0,
    )
    if expected_alarms_sha_warning is not None:
        warnings.append(expected_alarms_sha_warning)
    if normalized_operation in ALARM_OPERATIONS:
        if normalized_expected_alarms_count is not None and normalized_expected_alarms_count > 0 and not normalized_expected_alarms_sha:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder expected_alarms_sha256 is required when expected_alarms_count is greater than zero.",
                )
            )
        if normalized_expected_alarms_count == 0 and normalized_expected_alarms_sha:
            warnings.append(
                _warning(
                    "unexpected_expected_alarms_sha256",
                    "Reminder expected_alarms_sha256 requires expected_alarms_count greater than zero.",
                )
            )
        if normalized_operation == "clear_display_alarm" and normalized_expected_alarms_count == 0:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder clear_display_alarm requires expected_alarms_count greater than zero.",
                )
            )

    normalized_expected_notes_sha, notes_sha_warning = _normalize_sha256(
        expected_notes_sha256,
        field="expected_notes_sha256",
        required=normalized_operation in EXPECTED_NOTES_SHA_OPERATIONS,
    )
    if notes_sha_warning is not None:
        warnings.append(notes_sha_warning)

    normalized_handle = handle.strip()
    normalized_expected_list_handle = expected_list_handle.strip()
    normalized_target_list_handle = target_list_handle.strip()
    if normalized_operation in EXISTING_REMINDER_OPERATIONS and not is_opaque_handle(
        normalized_handle,
        EVENTKIT_REMINDER_HANDLE_PREFIX,
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected reminders:reminder:eventkit:v1 opaque handle from EventKit search output.",
            )
        )
    if normalized_operation in LIST_TARGET_OPERATIONS and not is_opaque_handle(
        normalized_expected_list_handle,
        EVENTKIT_REMINDER_LIST_HANDLE_PREFIX,
    ):
        warnings.append(
            _warning(
                "invalid_expected_list_handle",
                "Expected current reminders:list:eventkit:v1 opaque handle from Reminders search output.",
            )
        )
    if normalized_operation in LIST_TARGET_OPERATIONS and not is_opaque_handle(
        normalized_target_list_handle,
        EVENTKIT_REMINDER_LIST_HANDLE_PREFIX,
    ):
        warnings.append(
            _warning(
                "invalid_target_handle",
                "Expected reminders:list:eventkit:v1 opaque handle from Reminders list search output.",
            )
        )
    if normalized_operation in CREATE_OPERATIONS and normalized_handle:
        warnings.append(
            _warning(
                "unexpected_handle",
                "Create reminder planning requires a target list, not a reminder handle.",
            )
        )

    normalized_expected_recurrence_present, expected_recurrence_present_warning = _normalize_bool(
        expected_recurrence_present,
        field="expected_recurrence_present",
        required=normalized_operation == "update_recurrence",
    )
    if expected_recurrence_present_warning is not None:
        warnings.append(expected_recurrence_present_warning)
    normalized_expected_recurrence = _empty_recurrence()
    if normalized_operation == "update_recurrence":
        if isinstance(expected_recurrence, dict) and expected_recurrence.get("recurrence_present"):
            _expected_count = expected_recurrence.get("count")
            if isinstance(_expected_count, int) and _expected_count == 0:
                _expected_count = None
            normalized_expected_recurrence, expected_recurrence_warning = _normalize_recurrence(
                frequency=str(expected_recurrence.get("frequency") or ""),
                interval=expected_recurrence.get("interval"),
                count=_expected_count,
                end_date=str(expected_recurrence.get("end_date") or ""),
                unbounded=bool(expected_recurrence.get("unbounded")),
                weekdays=expected_recurrence.get("weekdays"),
                month_days=expected_recurrence.get("month_days"),
                month_weekdays=expected_recurrence.get("month_weekdays"),
                year_months=expected_recurrence.get("year_months"),
                year_month_days=expected_recurrence.get("year_month_days"),
                year_month_weekdays=expected_recurrence.get("year_month_weekdays"),
                year_days=expected_recurrence.get("year_days"),
                year_weeks=expected_recurrence.get("year_weeks"),
                set_positions=expected_recurrence.get("set_positions"),
            )
            if expected_recurrence_warning is not None:
                warnings.append(
                    _warning(
                        "invalid_expected_recurrence",
                        "Reminder expected_recurrence must be a bounded daily, weekly, monthly, or yearly rule.",
                    )
                )
            elif normalized_expected_recurrence_present is False:
                warnings.append(
                    _warning(
                        "conflicting_expected_recurrence",
                        "Reminder expected_recurrence_present=false requires no expected_recurrence shape.",
                    )
                )
        elif normalized_expected_recurrence_present is True:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder update_recurrence requires expected_recurrence when expected_recurrence_present=true.",
                )
            )

    # missing_required_field anchor gates ordered before recurrence shape gates.
    if normalized_operation == "create_with_recurrence":
        if not normalized_recurrence_present:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder create_with_recurrence requires recurrence fields.",
                )
            )
        elif not normalized_due_date:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder recurrence requires a due date anchor.",
                )
            )
    if normalized_operation == "update_recurrence":
        if not normalized_recurrence_present and not normalized_clear_recurrence:
            warnings.append(
                _warning(
                    "missing_required_field",
                    "Reminder update_recurrence requires recurrence fields or clear_recurrence=true.",
                )
            )
        if normalized_recurrence_present and normalized_clear_recurrence:
            warnings.append(
                _warning(
                    "conflicting_recurrence_fields",
                    "Use either recurrence fields or clear_recurrence, not both.",
                )
            )

    start_due_warning = _start_date_not_after_due_warning(
        normalized_start_date,
        normalized_due_date,
    )
    if start_due_warning is not None:
        warnings.append(start_due_warning)

    recurrence_end_warning = _reminder_recurrence_end_date_warning(
        normalized_recurrence if normalized_recurrence_present else None,
        due_date=normalized_due_date,
    )
    if recurrence_end_warning is not None:
        warnings.append(recurrence_end_warning)

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
    elif normalized_operation == "create_with_start_date":
        target = {"list_name": normalized_list}
        proposed = {
            "title": normalized_title,
            "due_date": normalized_due_date,
            "start_date": normalized_start_date,
            "start_date_requested": True,
            "notes_text": normalized_notes,
            "notes_chars": len(normalized_notes),
            "notes_present": bool(normalized_notes),
        }
    elif normalized_operation == "create_with_recurrence":
        target = {"list_name": normalized_list}
        proposed = {
            "title": normalized_title,
            "due_date": normalized_due_date,
            "recurrence": normalized_recurrence,
            "recurrence_present": True,
            "notes_text": normalized_notes,
            "notes_chars": len(normalized_notes),
            "notes_present": bool(normalized_notes),
        }
    elif normalized_operation == "update_start_date":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_start_date": normalized_expected_start_date or "",
        }
        proposed = {
            "start_date_update_requested": True,
            "start_date": normalized_start_date or "",
            "start_date_present": bool(normalized_start_date),
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "update_recurrence":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_recurrence_present": normalized_expected_recurrence_present,
            "expected_recurrence": normalized_expected_recurrence,
        }
        proposed = {
            "recurrence_update_requested": True,
            "recurrence": normalized_recurrence if normalized_recurrence_present else _empty_recurrence(),
            "recurrence_present": normalized_recurrence_present,
            "recurrence_clear_requested": normalized_clear_recurrence,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation in {"complete", "uncomplete"}:
        target_completed = normalized_operation == "complete"
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed if normalized_completed is not None else not target_completed,
        }
        proposed = {
            "completed": target_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "update_due_date":
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
    elif normalized_operation == "update_title":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
        }
        proposed = {
            "title": normalized_title,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "update_notes":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_notes_sha256": normalized_expected_notes_sha,
        }
        proposed = {
            "notes_text": normalized_notes,
            "notes_chars": len(normalized_notes),
            "notes_sha256": hashlib.sha256(normalized_notes.encode("utf-8")).hexdigest(),
            "notes_present": bool(normalized_notes),
            "completed": normalized_completed,
            "due_date": None,
        }
    elif normalized_operation == "update_priority":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_priority": normalized_expected_priority,
        }
        proposed = {
            "priority": normalized_priority,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "update_url":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_url_present": normalized_expected_url_present,
            "expected_url_sha256": normalized_expected_url_sha,
        }
        proposed = {
            "url_requested": True,
            "url_scheme": url_scheme,
            "url_domain": url_domain,
            "url_safe_sha256": url_sha256,
            "url_present": True,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "clear_url":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_url_present": normalized_expected_url_present,
            "expected_url_sha256": normalized_expected_url_sha,
        }
        proposed = {
            "url_clear_requested": True,
            "url_present": False,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "set_absolute_display_alarm":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_alarms_count": normalized_expected_alarms_count,
            "expected_alarms_sha256": normalized_expected_alarms_sha,
        }
        proposed = {
            "alarm_update_requested": True,
            "alarm_kind": "absolute",
            "alarm_action": "display",
            "alarm_absolute_dates": normalized_alarm_absolute_dates,
            "alarms_count": len(normalized_alarm_absolute_dates or []),
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "set_relative_display_alarm":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_alarms_count": normalized_expected_alarms_count,
            "expected_alarms_sha256": normalized_expected_alarms_sha,
        }
        proposed = {
            "alarm_update_requested": True,
            "alarm_kind": "relative",
            "alarm_action": "display",
            "alarm_offsets_minutes": normalized_alarm_offsets,
            "alarms_count": len(normalized_alarm_offsets or []),
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "set_mixed_display_alarm":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_alarms_count": normalized_expected_alarms_count,
            "expected_alarms_sha256": normalized_expected_alarms_sha,
        }
        proposed = {
            "alarm_update_requested": True,
            "alarm_kind": "mixed",
            "alarm_action": "display",
            "alarm_offsets_minutes": normalized_alarm_offsets,
            "alarm_absolute_dates": normalized_alarm_absolute_dates,
            "alarms_count": len(normalized_alarm_offsets or []) + len(normalized_alarm_absolute_dates or []),
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "clear_display_alarm":
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_alarms_count": normalized_expected_alarms_count,
            "expected_alarms_sha256": normalized_expected_alarms_sha,
        }
        proposed = {
            "alarm_clear_requested": True,
            "alarms_count": 0,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    elif normalized_operation == "move_to_list":
        target = {
            "handle": normalized_handle,
            "expected_list_handle": normalized_expected_list_handle,
            "target_list_handle": normalized_target_list_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_list_name": normalized_expected_list_name,
        }
        proposed = {
            "list_change": True,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }
    else:
        target = {
            "handle": normalized_handle,
            "expected_title": normalized_expected_title,
            "expected_completed": normalized_completed,
            "expected_priority": normalized_expected_priority,
            "expected_notes_sha256": normalized_expected_notes_sha,
        }
        proposed = {
            "delete": True,
            "completed": normalized_completed,
            "due_date": None,
            "notes_present": None,
        }

    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": {**proposed, "url": normalized_url}
        if normalized_operation == "update_url"
        else proposed,
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
    title: str | None = "",
    list_name: str = "",
    due_date: str = "",
    start_date: str = "",
    expected_start_date: str = "",
    notes: str | None = None,
    handle: str = "",
    expected_title: str = "",
    expected_completed: bool | str | None = None,
    expected_list_name: str = "",
    expected_list_handle: str = "",
    target_list_handle: str = "",
    expected_priority: int | str | None = None,
    expected_notes_sha256: str = "",
    priority: int | str | None = None,
    url: str = "",
    expected_url_present: bool | str | None = None,
    expected_url_sha256: str = "",
    alarm_absolute_dates: list[str] | None = None,
    alarm_offsets_minutes: list[int] | None = None,
    expected_alarms_count: int | str | None = None,
    expected_alarms_sha256: str = "",
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    clear_recurrence: bool = False,
    expected_recurrence_present: bool | str | None = None,
    expected_recurrence: dict[str, Any] | None = None,
    approval_token: str = "",
    confirm_apply: bool = False,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    plan = plan_reminder_change(
        operation,
        title=title,
        list_name=list_name,
        due_date=due_date,
        start_date=start_date,
        expected_start_date=expected_start_date,
        notes=notes,
        handle=handle,
        expected_title=expected_title,
        expected_completed=expected_completed,
        expected_list_name=expected_list_name,
        expected_list_handle=expected_list_handle,
        target_list_handle=target_list_handle,
        expected_priority=expected_priority,
        expected_notes_sha256=expected_notes_sha256,
        priority=priority,
        url=url,
        expected_url_present=expected_url_present,
        expected_url_sha256=expected_url_sha256,
        alarm_absolute_dates=alarm_absolute_dates,
        alarm_offsets_minutes=alarm_offsets_minutes,
        expected_alarms_count=expected_alarms_count,
        expected_alarms_sha256=expected_alarms_sha256,
        recurrence_frequency=recurrence_frequency,
        recurrence_interval=recurrence_interval,
        recurrence_count=recurrence_count,
        recurrence_end_date=recurrence_end_date,
        recurrence_unbounded=recurrence_unbounded,
        recurrence_weekdays=recurrence_weekdays,
        recurrence_month_days=recurrence_month_days,
        recurrence_month_weekdays=recurrence_month_weekdays,
        recurrence_year_months=recurrence_year_months,
        recurrence_year_month_days=recurrence_year_month_days,
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        recurrence_year_days=recurrence_year_days,
        recurrence_year_weeks=recurrence_year_weeks,
        recurrence_set_positions=recurrence_set_positions,
        clear_recurrence=clear_recurrence,
        expected_recurrence_present=expected_recurrence_present,
        expected_recurrence=expected_recurrence,
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
    move_source_list_is_shared = False
    if normalized_operation == "update_url":
        helper_url, _scheme, _domain, helper_url_sha256, helper_url_warning = _normalize_reminder_url(
            url,
            field="url",
            required=True,
        )
        if helper_url_warning is not None:
            return _apply_error([helper_url_warning], plan=plan)
        if helper_url_sha256 != preview["proposed"].get("url_safe_sha256"):
            return _apply_error(
                [_warning("invalid_plan", "Reminder URL input did not match the approved plan.")],
                plan=plan,
            )
        helper_payload["url"] = helper_url
    if normalized_operation in EXISTING_REMINDER_OPERATIONS:
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
        if normalized_operation in EXPECTED_NOTES_SHA_OPERATIONS:
            current_hash_result = _current_reminder_notes_sha256(
                reminder_id,
                runner=runner,
            )
            if isinstance(current_hash_result, dict):
                return _apply_error(_safe_warnings(current_hash_result), plan=plan)
            expected_sha = str(preview["target"]["expected_notes_sha256"])
            if current_hash_result != expected_sha:
                return _apply_error(
                    [_warning("current_notes_changed", "Reminder notes changed since planning.")],
                    plan=plan,
            )
        if normalized_operation in URL_OPERATIONS:
            current_url_state = _current_reminder_url_state(reminder_id, runner=runner)
            if current_url_state.get("status") != "ok":
                return _apply_error(current_url_state["warnings"], plan=plan)
            expected_present = bool(preview["target"]["expected_url_present"])
            expected_sha = str(preview["target"]["expected_url_sha256"])
            if current_url_state["url_present"] != expected_present:
                return _apply_error(
                    [_warning("expected_state_mismatch", "Reminder URL state changed since planning.")],
                    plan=plan,
                )
            if expected_present and current_url_state["url_safe_sha256"] != expected_sha:
                return _apply_error(
                    [_warning("expected_state_mismatch", "Reminder URL state changed since planning.")],
                    plan=plan,
                )
        if normalized_operation in ALARM_OPERATIONS:
            current_alarm_state = _current_reminder_alarm_state(reminder_id, runner=runner)
            if current_alarm_state.get("status") != "ok":
                return _apply_error(current_alarm_state["warnings"], plan=plan)
            expected_count = int(preview["target"]["expected_alarms_count"])
            expected_sha = str(preview["target"]["expected_alarms_sha256"])
            if current_alarm_state["alarms_count"] != expected_count:
                return _apply_error(
                    [_warning("expected_state_mismatch", "Reminder alarm state changed since planning.")],
                    plan=plan,
                )
            if expected_count > 0 and current_alarm_state["alarms_safe_sha256"] != expected_sha:
                return _apply_error(
                    [_warning("expected_state_mismatch", "Reminder alarm state changed since planning.")],
                    plan=plan,
                )
        if normalized_operation == "update_start_date":
            current_start_state = _current_reminder_start_state(reminder_id, runner=runner)
            if current_start_state.get("status") != "ok":
                return _apply_error(current_start_state["warnings"], plan=plan)
            expected_start = str(preview["target"]["expected_start_date"] or "")
            if not _reminder_dates_match(current_start_state["start_date"], expected_start):
                return _apply_error(
                    [_warning("expected_state_mismatch", "Reminder start date changed since planning.")],
                    plan=plan,
                )
        if normalized_operation == "update_recurrence":
            current_recurrence_state = _current_reminder_recurrence_state(reminder_id, runner=runner)
            if current_recurrence_state.get("status") != "ok":
                return _apply_error(current_recurrence_state["warnings"], plan=plan)
            expected_recurrence_dict = preview["target"]["expected_recurrence"]
            if current_recurrence_state["recurrence"] != expected_recurrence_dict:
                return _apply_error(
                    [_warning("stale_recurrence_state", "Reminder recurrence state no longer matches the approved plan.")],
                    plan=plan,
                )
        helper_payload["reminder_id"] = reminder_id
        if normalized_operation in LIST_TARGET_OPERATIONS:
            list_response = _eventkit_reminder_lists_response(
                query="",
                limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
                eventkit_runner=eventkit_runner,
            )
            if list_response.get("status") != "ok":
                return _apply_unavailable(list_response, plan=plan)
            target_list_handle = str(preview["target"]["target_list_handle"])
            expected_list_handle = str(preview["target"]["expected_list_handle"])
            target_list_items = list_response.get("lists", [])
            expected_list_id = _resolve_eventkit_list_id(
                expected_list_handle,
                target_list_items,
            )
            if expected_list_id is None:
                return _apply_error(
                    [
                        _warning(
                            "expected_list_not_found",
                            "Reminder expected current list was not found through EventKit.",
                        )
                    ],
                    plan=plan,
                )
            target_list_id = _resolve_eventkit_list_id(
                target_list_handle,
                target_list_items,
            )
            if target_list_id is None:
                return _apply_error(
                    [
                        _warning(
                            "target_list_not_found",
                            "Reminder target list was not found through EventKit.",
                        )
                    ],
                    plan=plan,
                )
            target_list_metadata = next(
                (
                    _eventkit_reminder_list_metadata(item)
                    for item in target_list_items
                    if isinstance(item, dict)
                    and str(item.get("list_id") or "") == target_list_id
                ),
                None,
            )
            if target_list_metadata is None:
                return _apply_error(
                    [
                        _warning(
                            "target_list_not_found",
                            "Reminder target list was not found through EventKit.",
                        )
                    ],
                    plan=plan,
                )
            expected_list_item = _find_reminder_list_by_id(target_list_items, expected_list_id)
            move_source_list_is_shared = bool(
                isinstance(expected_list_item, dict) and expected_list_item.get("is_shared")
            )
            helper_payload["target_list_id"] = target_list_id
            helper_payload["target_list_title"] = str(target_list_metadata.get("title") or "")
            helper_payload["expected_list_id"] = expected_list_id

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
        failure_warnings = _safe_warnings(applied) or [
            _warning("eventkit_apply_failed", "Reminder change could not be applied safely.")
        ]
        if normalized_operation in LIST_TARGET_OPERATIONS and move_source_list_is_shared:
            # EventKit refuses to save a reminder out of a shared (sharee-backed)
            # list; the generic failure code left agents guessing at the cause.
            failure_warnings = [
                _warning(
                    "shared_list_move_unsupported",
                    "EventKit does not support moving reminders out of a shared list. "
                    "Fall back to creating the reminder on the target list, then deleting "
                    "the original from the shared list with the guarded delete operation.",
                ),
                *failure_warnings,
            ]
        return _apply_error(
            failure_warnings,
            plan=plan,
            status=str(applied.get("status") or "error"),
            mutation_applied=bool(applied.get("mutation_applied")),
            authorization_status=applied.get("authorization_status"),
        )

    if normalized_operation == "delete":
        read_back_payload = applied.get("read_back")
        read_back = read_back_payload if isinstance(read_back_payload, dict) else {}
        deleted = bool(applied.get("deleted")) or bool(read_back.get("deleted"))
        verified_absent = bool(read_back.get("verified_absent"))
        if not deleted or not verified_absent:
            return _apply_error(
                [_warning("read_back_unavailable", "Reminder delete read-back did not prove target absence.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )

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
            "read_back": {
                "handle": preview["target"]["handle"],
                "deleted": True,
                "verified_absent": True,
            },
            "result_count": 1,
            "warnings": warnings,
        }

    reminder = applied.get("reminder")
    if not isinstance(reminder, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Reminder apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )

    read_back = _eventkit_reminder_metadata(
        reminder,
        include_url_proof=normalized_operation in URL_OPERATIONS,
        include_alarm_proof=normalized_operation in ALARM_OPERATIONS,
        include_alarm_dates=normalized_operation in ALARM_ABSOLUTE_DATE_OPERATIONS,
        include_alarm_offsets=normalized_operation in ALARM_OFFSET_OPERATIONS,
        include_recurrence_proof=normalized_operation in {"create_with_recurrence", "update_recurrence"},
    )
    if normalized_operation in LIST_TARGET_OPERATIONS:
        if applied.get("target_list_verified") is not True:
            return _apply_error(
                [
                    _warning(
                        "read_back_target_mismatch",
                        "Reminder list-move read-back did not prove the approved target list identity.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
        )
        read_back["target_list_verified"] = True
    if normalized_operation == "update_url":
        proposed_sha = str(preview["proposed"]["url_safe_sha256"])
        if read_back.get("url_present") is not True or read_back.get("url_safe_sha256") != proposed_sha:
            return _apply_error(
                [_warning("url_read_back_mismatch", "Reminder URL read-back did not match the approved value.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["url_verified"] = True
    if normalized_operation == "clear_url":
        if read_back.get("url_present") is not False:
            return _apply_error(
                [_warning("url_read_back_mismatch", "Reminder URL clear read-back did not prove absence.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["url_absent_verified"] = True
    if normalized_operation == "set_absolute_display_alarm":
        proposed_dates = preview["proposed"]["alarm_absolute_dates"]
        read_back_dates, read_back_dates_warning = _normalize_alarm_absolute_dates(
            read_back.get("alarm_absolute_dates"),
            field="read_back.alarm_absolute_dates",
            required=True,
        )
        if (
            read_back_dates_warning
            or read_back_dates != proposed_dates
            or read_back.get("alarms_count") != len(proposed_dates)
        ):
            return _apply_error(
                [
                    _warning(
                        "alarm_read_back_mismatch",
                        "Reminder absolute alarm read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["alarm_absolute_dates"] = read_back_dates
        read_back["display_alarm_verified"] = True
    if normalized_operation == "set_relative_display_alarm":
        proposed_offsets = preview["proposed"]["alarm_offsets_minutes"]
        read_back_offsets, read_back_offsets_warning = _normalize_alarm_offsets(
            read_back.get("alarm_offsets_minutes"),
            field="read_back.alarm_offsets_minutes",
            required=True,
        )
        if (
            read_back_offsets_warning
            or read_back_offsets != proposed_offsets
            or read_back.get("alarms_count") != len(proposed_offsets)
        ):
            return _apply_error(
                [
                    _warning(
                        "alarm_read_back_mismatch",
                        "Reminder relative alarm read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["alarm_offsets_minutes"] = read_back_offsets
        read_back["display_alarm_verified"] = True
    if normalized_operation == "set_mixed_display_alarm":
        proposed_offsets = preview["proposed"]["alarm_offsets_minutes"]
        proposed_dates = preview["proposed"]["alarm_absolute_dates"]
        read_back_offsets, read_back_offsets_warning = _normalize_alarm_offsets(
            read_back.get("alarm_offsets_minutes"),
            field="read_back.alarm_offsets_minutes",
            required=True,
        )
        read_back_dates, read_back_dates_warning = _normalize_alarm_absolute_dates(
            read_back.get("alarm_absolute_dates"),
            field="read_back.alarm_absolute_dates",
            required=True,
        )
        if (
            read_back_offsets_warning
            or read_back_dates_warning
            or read_back_offsets != proposed_offsets
            or read_back_dates != proposed_dates
            or read_back.get("alarms_count") != len(proposed_offsets) + len(proposed_dates)
        ):
            return _apply_error(
                [
                    _warning(
                        "alarm_read_back_mismatch",
                        "Reminder mixed alarm read-back did not match the approved value.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["alarm_offsets_minutes"] = read_back_offsets
        read_back["alarm_absolute_dates"] = read_back_dates
        read_back["display_alarm_verified"] = True
    if normalized_operation == "clear_display_alarm":
        if read_back.get("alarms_count") != 0:
            return _apply_error(
                [_warning("alarm_read_back_mismatch", "Reminder alarm clear read-back did not prove absence.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["display_alarm_cleared_verified"] = True
    if normalized_operation == "create_with_start_date":
        proposed_start = preview["proposed"]["start_date"]
        if not _reminder_dates_match(read_back.get("start_date"), proposed_start):
            return _apply_error(
                [_warning("start_date_read_back_mismatch", "Reminder start-date create read-back did not match the approved value.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["start_date_verified"] = True
    if normalized_operation == "update_start_date":
        proposed_start = preview["proposed"]["start_date"]
        if preview["proposed"].get("start_date_present"):
            if not _reminder_dates_match(read_back.get("start_date"), proposed_start):
                return _apply_error(
                    [_warning("start_date_read_back_mismatch", "Reminder start-date read-back did not match the approved value.")],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["start_date_verified"] = True
        else:
            if read_back.get("start_date") not in (None, ""):
                return _apply_error(
                    [_warning("start_date_read_back_mismatch", "Reminder start-date clear read-back did not prove absence.")],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["start_date_absent_verified"] = True
    if normalized_operation == "create_with_recurrence":
        proposed_recurrence = preview["proposed"]["recurrence"]
        if read_back.get("recurrence_present") is not True or read_back.get("recurrence") != proposed_recurrence:
            return _apply_error(
                [_warning("recurrence_read_back_mismatch", "Reminder recurrence create read-back did not match the approved value.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        read_back["recurrence_verified"] = True
    if normalized_operation == "update_recurrence":
        if preview["proposed"].get("recurrence_clear_requested"):
            if read_back.get("recurrence_present") is not False:
                return _apply_error(
                    [_warning("recurrence_read_back_mismatch", "Reminder recurrence clear read-back did not prove absence.")],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["recurrence_cleared_verified"] = True
        else:
            proposed_recurrence = preview["proposed"]["recurrence"]
            if read_back.get("recurrence_present") is not True or read_back.get("recurrence") != proposed_recurrence:
                return _apply_error(
                    [_warning("recurrence_read_back_mismatch", "Reminder recurrence read-back did not match the approved value.")],
                    plan=plan,
                    status="apply_unknown",
                    mutation_applied=True,
                    authorization_status=applied.get("authorization_status"),
                )
            read_back["recurrence_verified"] = True
    warnings = _safe_warnings(applied)
    result = {
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
    if normalized_operation in URL_OPERATIONS:
        result["url_raw_returned"] = False
    if normalized_operation in ALARM_OPERATIONS:
        result["alarm_state_raw_returned"] = False
    return result


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


def _eventkit_reminder_lists_response(
    *,
    query: str,
    limit: int,
    include_counts: bool = False,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "reminder_lists",
                "query": query,
                "limit": max(1, min(limit, DEFAULT_EVENTKIT_SCAN_LIMIT)),
                "include_counts": include_counts,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminders list access timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminders list access is unavailable through the local EventKit helper.",
                )
            ],
        }


def _eventkit_reminders_for_list_response(
    *,
    list_id: str,
    limit: int,
    include_completed: bool,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    runner = eventkit_runner or _run_eventkit_helper
    try:
        return runner(
            {
                "command": "reminders_for_list",
                "list_id": list_id,
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
                    "Selected Reminders list access timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Selected Reminders list access is unavailable through the local EventKit helper.",
                )
            ],
        }


def request_reminders_full_access(
    *,
    eventkit_runner: EventKitRunner | None = None,
) -> dict[str, Any]:
    """Trigger the EventKit Reminders full-access prompt from the stable helper app."""

    runner = eventkit_runner or _run_eventkit_helper
    if eventkit_runner is None:
        # Real request-access path only: provision a stable signing identity and
        # rebuild the helper stably signed so TCC actually presents the prompt.
        _prepare_eventkit_helper_signing()
    try:
        response = runner({"command": "request_reminders_full_access"}, 190.0)
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "timeout",
            "warnings": [
                _warning(
                    "reminders_access_request_timeout",
                    "Reminders access prompt did not complete before timeout.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "unavailable",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminders access request is unavailable through the local EventKit helper.",
                )
            ],
        }
    return {
        "schema_version": 1,
        "status": str(response.get("status") or "degraded"),
        "source": "reminders",
        "privacy": _privacy(),
        "authorization_status": str(response.get("authorization_status") or "unknown"),
        "request_result": str(response.get("request_result") or "unknown"),
        "warnings": _safe_warnings(response),
    }


def _run_eventkit_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    return _run_eventkit_helper_app(payload, timeout)


def _eventkit_reminder_metadata(
    reminder: dict[str, Any],
    *,
    include_url_proof: bool = False,
    include_alarm_proof: bool = False,
    include_alarm_dates: bool = False,
    include_alarm_offsets: bool = False,
    include_recurrence_proof: bool = False,
) -> dict[str, Any]:
    reminder_id = str(reminder.get("reminder_id") or "")
    list_id = str(reminder.get("list_id") or "")
    metadata = {
        "handle": make_opaque_handle(EVENTKIT_REMINDER_HANDLE_PREFIX, reminder_id),
        "list_handle": make_opaque_handle(EVENTKIT_REMINDER_LIST_HANDLE_PREFIX, list_id)
        if list_id
        else None,
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
    if include_url_proof and reminder.get("url_safe_sha256"):
        metadata["url_safe_sha256"] = str(reminder.get("url_safe_sha256") or "")
    if include_alarm_proof and reminder.get("alarms_safe_sha256"):
        metadata["alarms_safe_sha256"] = str(reminder.get("alarms_safe_sha256") or "")
    if include_alarm_dates and "alarm_absolute_dates" in reminder:
        dates = reminder.get("alarm_absolute_dates")
        metadata["alarm_absolute_dates"] = dates if isinstance(dates, list) else []
    if include_alarm_offsets and "alarm_offsets_minutes" in reminder:
        offsets = reminder.get("alarm_offsets_minutes")
        metadata["alarm_offsets_minutes"] = offsets if isinstance(offsets, list) else []
    if include_recurrence_proof:
        metadata["recurrence_present"] = bool(reminder.get("recurrence_present"))
        recurrence = reminder.get("recurrence")
        metadata["recurrence"] = recurrence if isinstance(recurrence, dict) else _empty_recurrence()
    if metadata["list_handle"] is None:
        metadata.pop("list_handle")
    return metadata


def _eventkit_reminder_list_metadata(reminder_list: dict[str, Any]) -> dict[str, Any]:
    list_id = str(reminder_list.get("list_id") or "")
    payload: dict[str, Any] = {
        "handle": make_opaque_handle(EVENTKIT_REMINDER_LIST_HANDLE_PREFIX, list_id),
        "title": reminder_list.get("title"),
        "allows_content_modifications": bool(reminder_list.get("allows_content_modifications", True)),
        "is_subscribed": bool(reminder_list.get("is_subscribed")),
        "is_immutable": bool(reminder_list.get("is_immutable")),
        "calendar_type": reminder_list.get("calendar_type") or "",
        "source_type": reminder_list.get("source_type") or "",
        "allowed_entity_types": reminder_list.get("allowed_entity_types", []),
        # None means the helper could not detect sharing state (older helper
        # payload or EventKit accessors unavailable) — never a false "not shared".
        "is_shared": bool(reminder_list["is_shared"]) if "is_shared" in reminder_list else None,
        "list_safe_sha256": _reminder_list_safe_sha256(reminder_list),
        "source_safe_sha256": _reminder_list_source_safe_sha256(reminder_list),
    }
    if "sharee_count" in reminder_list:
        payload["sharee_count"] = int(reminder_list.get("sharee_count") or 0)
    if "reminder_count" in reminder_list:
        payload["reminder_count"] = int(reminder_list.get("reminder_count") or 0)
    return payload


def _plan_reminder_list_create(
    *,
    source_list_handle: str,
    list_title: str,
    list_handle: str,
    new_list_title: str,
    target_list_handle: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if list_handle.strip() or new_list_title.strip() or target_list_handle.strip():
        return _preview_error(
            [_warning("unexpected_list_field", "Reminder create-list accepts source_list_handle and list_title only.")]
        )
    normalized_title, title_warning = _normalize_reminder_list_title(list_title, field="list_title")
    if title_warning is not None:
        return _preview_error([title_warning])
    source_result = _resolve_reminder_list_for_management(
        source_list_handle,
        eventkit_runner=eventkit_runner,
        include_counts=False,
    )
    if source_result["status"] != "ok":
        return _preview_error(source_result["warnings"])
    source_list = source_result["list"]
    source_warning = _reminder_list_source_warning(source_list)
    if source_warning is not None:
        return _preview_error([source_warning])
    if _reminder_list_title_exists_in_source(
        source_result["lists"],
        source_id=str(source_list.get("source_id") or ""),
        title=normalized_title,
    ):
        return _preview_error(
            [_warning("list_already_exists", "A Reminders list with that title already exists in the selected source.")]
        )
    target = {
        "source_list_handle": source_list_handle.strip(),
        "source_list_title": str(source_list.get("title") or ""),
        "source_safe_sha256": _reminder_list_source_safe_sha256(source_list),
        "source_type": str(source_list.get("source_type") or ""),
    }
    proposed = {
        "list_title": normalized_title,
    }
    return _reminder_list_plan("create_list", target, proposed)


def _plan_reminder_list_rename(
    *,
    list_handle: str,
    new_list_title: str,
    source_list_handle: str,
    list_title: str,
    target_list_handle: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if source_list_handle.strip() or list_title.strip() or target_list_handle.strip():
        return _preview_error(
            [_warning("unexpected_list_field", "Reminder rename-list accepts list_handle and new_list_title only.")]
        )
    normalized_title, title_warning = _normalize_reminder_list_title(new_list_title, field="new_list_title")
    if title_warning is not None:
        return _preview_error([title_warning])
    target_result = _resolve_reminder_list_for_management(
        list_handle,
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if target_result["status"] != "ok":
        return _preview_error(target_result["warnings"])
    reminder_list = target_result["list"]
    safety_warning = _reminder_list_target_warning(reminder_list, require_empty=True)
    if safety_warning is not None:
        return _preview_error([safety_warning])
    if _reminder_list_title_exists_in_source(
        target_result["lists"],
        source_id=str(reminder_list.get("source_id") or ""),
        title=normalized_title,
        excluding_list_id=str(reminder_list.get("list_id") or ""),
    ):
        return _preview_error(
            [_warning("list_already_exists", "A Reminders list with that title already exists in the selected source.")]
        )
    return _reminder_list_plan(
        "rename_list",
        _reminder_list_management_target(list_handle, reminder_list),
        {
            "new_list_title": normalized_title,
        },
    )


def _plan_reminder_list_delete(
    *,
    list_handle: str,
    source_list_handle: str,
    list_title: str,
    new_list_title: str,
    target_list_handle: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if source_list_handle.strip() or list_title.strip() or new_list_title.strip() or target_list_handle.strip():
        return _preview_error(
            [_warning("unexpected_list_field", "Reminder delete-list accepts list_handle only.")]
        )
    target_result = _resolve_reminder_list_for_management(
        list_handle,
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if target_result["status"] != "ok":
        return _preview_error(target_result["warnings"])
    reminder_list = target_result["list"]
    safety_warning = _reminder_list_target_warning(reminder_list, require_empty=True)
    if safety_warning is not None:
        return _preview_error([safety_warning])
    return _reminder_list_plan(
        "delete_list",
        _reminder_list_management_target(list_handle, reminder_list),
        {
            "delete_requested": True,
            "absence_proof_required": True,
        },
    )


def _plan_reminder_list_delete_with_migration(
    *,
    list_handle: str,
    target_list_handle: str,
    source_list_handle: str,
    list_title: str,
    new_list_title: str,
    eventkit_runner: EventKitRunner | None,
) -> dict[str, Any]:
    if source_list_handle.strip() or list_title.strip() or new_list_title.strip():
        return _preview_error(
            [
                _warning(
                    "unexpected_list_field",
                    "Reminder delete-list-with-migration accepts list_handle and target_list_handle only.",
                )
            ]
        )
    source_result = _resolve_reminder_list_for_management(
        list_handle,
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if source_result["status"] != "ok":
        return _preview_error(source_result["warnings"])
    target_result = _resolve_reminder_list_for_management(
        target_list_handle,
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if target_result["status"] != "ok":
        return _preview_error(target_result["warnings"])

    source_list = source_result["list"]
    target_list = target_result["list"]
    if str(source_list.get("list_id") or "") == str(target_list.get("list_id") or ""):
        return _preview_error(
            [
                _warning(
                    "same_list_target",
                    "Reminder list migration requires a different target list.",
                )
            ]
        )
    if str(source_list.get("source_id") or "") != str(target_list.get("source_id") or ""):
        return _preview_error(
            [_warning("cross_source_list_migration_refused", "Reminder list migration refuses cross-source targets.")]
        )
    for reminder_list in (source_list, target_list):
        safety_warning = _reminder_list_target_warning(reminder_list, require_empty=False)
        if safety_warning is not None:
            return _preview_error([safety_warning])
        if "reminder_count" not in reminder_list:
            return _preview_error(
                [
                    _warning(
                        "list_count_unavailable",
                        "Reminder list migration count proof was unavailable.",
                    )
                ]
            )

    source_count = int(source_list.get("reminder_count") or 0)
    target_count = int(target_list.get("reminder_count") or 0)
    if source_count == 0:
        return _preview_error([_warning("list_empty", "Use delete-list for empty Reminders lists.")])
    if source_count > MAX_REMINDER_LIST_MIGRATION_COUNT:
        return _preview_error(
            [
                _warning(
                    "list_migration_too_large",
                    f"Reminder list migration is capped at {MAX_REMINDER_LIST_MIGRATION_COUNT} reminders.",
                )
            ]
        )

    proposed = {
        "target_list_handle": target_list_handle.strip(),
        "target_list_title": str(target_list.get("title") or ""),
        "target_list_safe_sha256": _reminder_list_safe_sha256(target_list),
        "target_source_safe_sha256": _reminder_list_source_safe_sha256(target_list),
        "target_source_type": str(target_list.get("source_type") or ""),
        "target_reminder_count": target_count,
        "migrated_reminder_count": source_count,
        "delete_after_migration": True,
        "absence_proof_required": True,
    }
    return _reminder_list_plan(
        "delete_list_with_migration",
        _reminder_list_management_target(list_handle, source_list),
        proposed,
    )


def _reminder_list_plan(operation: str, target: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    fingerprint_payload = {"operation": operation, "target": target, "proposed": proposed}
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
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


def _reminder_list_apply_helper_payload(
    preview: dict[str, Any],
    resolve_result: dict[str, Any],
) -> dict[str, Any]:
    operation = str(preview["operation"])
    target = preview["target"]
    proposed = preview["proposed"]
    payload: dict[str, Any] = {
        "command": "reminder_list_apply_change",
        "operation": operation,
    }
    if operation == "create_list":
        payload.update(
            {
                "source_list_id": resolve_result["list_id"],
                "list_title": proposed["list_title"],
            }
        )
    elif operation == "delete_list_with_migration":
        payload.update(
            {
                "list_id": resolve_result["list_id"],
                "target_list_id": resolve_result["target_list_id"],
                "expected_list_title": target["list_title"],
                "expected_source_type": target["source_type"],
                "expected_target_list_title": proposed["target_list_title"],
                "expected_target_source_type": proposed["target_source_type"],
                "expected_migration_count": proposed["migrated_reminder_count"],
                "expected_target_count": proposed["target_reminder_count"],
                "migrate_before_delete": True,
            }
        )
    else:
        payload.update(
            {
                "list_id": resolve_result["list_id"],
                "expected_list_title": target["list_title"],
                "expected_source_type": target["source_type"],
                "expected_empty_list": True,
            }
        )
        if operation == "rename_list":
            payload["new_list_title"] = proposed["new_list_title"]
        if operation == "delete_list":
            payload["delete_list"] = True
    return payload


def _resolve_reminder_list_for_management_apply(
    preview: dict[str, Any],
    *,
    eventkit_runner: EventKitRunner,
) -> dict[str, Any]:
    operation = str(preview["operation"])
    target = preview["target"]
    if operation == "delete_list_with_migration":
        return _resolve_reminder_list_migration_apply(
            preview,
            eventkit_runner=eventkit_runner,
        )
    if operation == "create_list":
        handle = str(target["source_list_handle"])
        expected_sha = str(target["source_safe_sha256"])
        include_counts = False
    else:
        handle = str(target["list_handle"])
        expected_sha = str(target["list_safe_sha256"])
        include_counts = True
    resolved = _resolve_reminder_list_for_management(
        handle,
        eventkit_runner=eventkit_runner,
        include_counts=include_counts,
    )
    if resolved["status"] != "ok":
        return resolved
    reminder_list = resolved["list"]
    current_sha = (
        _reminder_list_source_safe_sha256(reminder_list)
        if operation == "create_list"
        else _reminder_list_safe_sha256(reminder_list)
    )
    if current_sha != expected_sha:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_list_changed",
                    "Reminder list target changed since the approved plan; re-plan before applying.",
                )
            ],
        }
    if operation == "create_list":
        source_warning = _reminder_list_source_warning(reminder_list)
        if source_warning is not None:
            return {"status": "error", "warnings": [source_warning]}
    else:
        safety_warning = _reminder_list_target_warning(reminder_list, require_empty=True)
        if safety_warning is not None:
            return {"status": "error", "warnings": [safety_warning]}
    return {
        "status": "ok",
        "list_id": str(reminder_list.get("list_id") or ""),
        "list": reminder_list,
        "warnings": [],
    }


def _resolve_reminder_list_migration_apply(
    preview: dict[str, Any],
    *,
    eventkit_runner: EventKitRunner,
) -> dict[str, Any]:
    target = preview["target"]
    proposed = preview["proposed"]
    source_resolved = _resolve_reminder_list_for_management(
        str(target["list_handle"]),
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if source_resolved["status"] != "ok":
        return source_resolved
    target_resolved = _resolve_reminder_list_for_management(
        str(proposed["target_list_handle"]),
        eventkit_runner=eventkit_runner,
        include_counts=True,
    )
    if target_resolved["status"] != "ok":
        return target_resolved

    source_list = source_resolved["list"]
    target_list = target_resolved["list"]
    if (
        _reminder_list_safe_sha256(source_list) != str(target["list_safe_sha256"])
        or _reminder_list_safe_sha256(target_list) != str(proposed["target_list_safe_sha256"])
    ):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_list_changed",
                    "Reminder list target changed since the approved plan; re-plan before applying.",
                )
            ],
        }
    if str(source_list.get("list_id") or "") == str(target_list.get("list_id") or ""):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "same_list_target",
                    "Reminder list migration requires a different target list.",
                )
            ],
        }
    if str(source_list.get("source_id") or "") != str(target_list.get("source_id") or ""):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "cross_source_list_migration_refused",
                    "Reminder list migration refuses cross-source targets.",
                )
            ],
        }
    for reminder_list in (source_list, target_list):
        safety_warning = _reminder_list_target_warning(reminder_list, require_empty=False)
        if safety_warning is not None:
            return {"status": "error", "warnings": [safety_warning]}
    if int(source_list.get("reminder_count") or 0) != int(proposed["migrated_reminder_count"]):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_list_changed",
                    "Reminder list source count changed since the approved plan; re-plan before applying.",
                )
            ],
        }
    if int(target_list.get("reminder_count") or 0) != int(proposed["target_reminder_count"]):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_list_changed",
                    "Reminder list migration target count changed since the approved plan; re-plan before applying.",
                )
            ],
        }
    return {
        "status": "ok",
        "list_id": str(source_list.get("list_id") or ""),
        "target_list_id": str(target_list.get("list_id") or ""),
        "list": source_list,
        "target_list": target_list,
        "warnings": [],
    }


def _resolve_reminder_list_for_management(
    handle: str,
    *,
    eventkit_runner: EventKitRunner | None,
    include_counts: bool,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, EVENTKIT_REMINDER_LIST_HANDLE_PREFIX):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "invalid_list_handle",
                    "Expected reminders:list:eventkit:v1 opaque handle from Reminders list output.",
                )
            ],
        }
    response = _eventkit_reminder_lists_response(
        query="",
        limit=DEFAULT_EVENTKIT_SCAN_LIMIT,
        include_counts=include_counts,
        eventkit_runner=eventkit_runner,
    )
    if response.get("status") != "ok":
        return {"status": "degraded", "warnings": _safe_warnings(response)}
    list_id = _resolve_eventkit_list_id(normalized_handle, response.get("lists", []))
    selected = _find_reminder_list_by_id(response.get("lists", []), list_id or "")
    if selected is None:
        return {
            "status": "not_found",
            "warnings": [_warning("target_list_not_found", "Reminder list target was not found.")],
        }
    return {
        "status": "ok",
        "list": selected,
        "lists": response.get("lists", []),
        "warnings": _safe_warnings(response),
    }


def _normalize_reminder_list_title(value: str, *, field: str) -> tuple[str, dict[str, str] | None]:
    normalized, warning = _bounded_preview_value(
        value,
        field=field,
        max_chars=MAX_PREVIEW_LIST_CHARS,
        required=True,
    )
    if warning is not None:
        return "", warning
    return normalized, None


def _reminder_list_source_warning(reminder_list: dict[str, Any]) -> dict[str, str] | None:
    source_type = str(reminder_list.get("source_type") or "")
    if source_type in {"subscribed", "birthdays"} or reminder_list.get("is_subscribed") or reminder_list.get("is_immutable"):
        return _warning(
            "unsupported_list_source",
            "Reminder list creation refuses subscribed, birthday, or immutable sources.",
        )
    if not reminder_list.get("allows_content_modifications", True):
        return _warning("target_list_not_writable", "Reminder list source does not allow changes.")
    allowed_types = _reminder_list_allowed_entity_types(reminder_list)
    if allowed_types and allowed_types != ["reminder"]:
        return _warning("unsupported_list_source", "Reminder list creation refuses non-reminder-only calendars.")
    return None


def _reminder_list_target_warning(
    reminder_list: dict[str, Any],
    *,
    require_empty: bool,
) -> dict[str, str] | None:
    title = str(reminder_list.get("title") or "")
    if not title:
        return _warning("unsupported_list_state", "Reminder list management refuses untitled lists.")
    if reminder_list.get("is_subscribed") or reminder_list.get("is_immutable"):
        return _warning("unsupported_list_state", "Reminder list management refuses subscribed or immutable lists.")
    if not reminder_list.get("allows_content_modifications", True):
        return _warning("target_list_not_writable", "Reminder list target does not allow changes.")
    allowed_types = _reminder_list_allowed_entity_types(reminder_list)
    if allowed_types and allowed_types != ["reminder"]:
        return _warning("unsupported_list_state", "Reminder list management refuses non-reminder-only calendars.")
    if require_empty and "reminder_count" not in reminder_list:
        return _warning("list_count_unavailable", "Reminder list empty proof was unavailable.")
    if require_empty and int(reminder_list.get("reminder_count") or 0) != 0:
        return _warning("list_not_empty", "Reminder list management refuses non-empty lists.")
    return None


def _reminder_list_management_target(handle: str, reminder_list: dict[str, Any]) -> dict[str, Any]:
    return {
        "list_handle": handle.strip(),
        "list_title": str(reminder_list.get("title") or ""),
        "list_safe_sha256": _reminder_list_safe_sha256(reminder_list),
        "source_type": str(reminder_list.get("source_type") or ""),
        "source_safe_sha256": _reminder_list_source_safe_sha256(reminder_list),
        "reminder_count": int(reminder_list.get("reminder_count") or 0),
    }


def _reminder_list_title_exists_in_source(
    reminder_lists: Any,
    *,
    source_id: str,
    title: str,
    excluding_list_id: str = "",
) -> bool:
    if not isinstance(reminder_lists, list):
        return False
    for item in reminder_lists:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_id") or "") != source_id:
            continue
        if excluding_list_id and str(item.get("list_id") or "") == excluding_list_id:
            continue
        if str(item.get("title") or "") == title:
            return True
    return False


def _find_reminder_list_by_id(reminder_lists: Any, list_id: str) -> dict[str, Any] | None:
    if not list_id or not isinstance(reminder_lists, list):
        return None
    for item in reminder_lists:
        if isinstance(item, dict) and str(item.get("list_id") or "") == list_id:
            return item
    return None


def _reminder_list_allowed_entity_types(reminder_list: dict[str, Any]) -> list[str]:
    value = reminder_list.get("allowed_entity_types")
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if str(item))


def _reminder_list_safe_sha256(reminder_list: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "list_id": str(reminder_list.get("list_id") or ""),
                "title": str(reminder_list.get("title") or ""),
                "source_id": str(reminder_list.get("source_id") or ""),
                "source_type": str(reminder_list.get("source_type") or ""),
                "allows_content_modifications": bool(reminder_list.get("allows_content_modifications", True)),
                "is_subscribed": bool(reminder_list.get("is_subscribed")),
                "is_immutable": bool(reminder_list.get("is_immutable")),
                "calendar_type": str(reminder_list.get("calendar_type") or ""),
                "allowed_entity_types": _reminder_list_allowed_entity_types(reminder_list),
                "reminder_count": int(reminder_list.get("reminder_count") or 0),
            }
        ).encode("utf-8")
    ).hexdigest()


def _reminder_list_source_safe_sha256(reminder_list: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "source_id": str(reminder_list.get("source_id") or ""),
                "source_type": str(reminder_list.get("source_type") or ""),
            }
        ).encode("utf-8")
    ).hexdigest()


def _current_reminder_notes_sha256(
    reminder_id: str,
    *,
    runner: EventKitRunner,
) -> str | dict[str, Any]:
    try:
        detail = runner(
            {"command": "reminder_by_id", "reminder_id": reminder_id, "include_content": True},
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminder note-state check timed out through the local EventKit helper.",
                )
            ]
        }
    except (OSError, ValueError):
        return {
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminder note-state check is unavailable through the local EventKit helper.",
                )
            ]
        }
    if detail.get("status") == "not_found":
        return {"warnings": [_warning("target_not_found", "Reminder target was not found through EventKit.")]}
    if detail.get("status") != "ok":
        warnings = _safe_warnings(detail) or [
            _warning("eventkit_read_error", "Reminder note-state check could not be read safely.")
        ]
        return {"warnings": warnings}
    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {"warnings": [_warning("eventkit_read_error", "Reminder note-state check could not be read safely.")]}
    normalized_notes = str(reminder.get("notes") or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized_notes.encode("utf-8")).hexdigest()


def _current_reminder_url_state(
    reminder_id: str,
    *,
    runner: EventKitRunner,
) -> dict[str, Any]:
    try:
        detail = runner(
            {
                "command": "reminder_by_id",
                "reminder_id": reminder_id,
                "include_content": False,
                "include_url_proof": True,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminder URL-state check timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminder URL-state check is unavailable through the local EventKit helper.",
                )
            ],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "error",
            "warnings": [_warning("target_not_found", "Reminder target was not found through EventKit.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": "error",
            "warnings": _safe_warnings(detail)
            or [_warning("eventkit_read_error", "Reminder URL-state check could not be read safely.")],
        }
    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {
            "status": "error",
            "warnings": [_warning("eventkit_read_error", "Reminder URL-state check could not be read safely.")],
        }
    return {
        "status": "ok",
        "url_present": bool(reminder.get("url_present")),
        "url_safe_sha256": str(reminder.get("url_safe_sha256") or ""),
        "warnings": [],
    }


def _current_reminder_alarm_state(
    reminder_id: str,
    *,
    runner: EventKitRunner,
) -> dict[str, Any]:
    try:
        detail = runner(
            {
                "command": "reminder_by_id",
                "reminder_id": reminder_id,
                "include_content": False,
                "include_alarm_proof": True,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminder alarm-state check timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminder alarm-state check is unavailable through the local EventKit helper.",
                )
            ],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "error",
            "warnings": [_warning("target_not_found", "Reminder target was not found through EventKit.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": "error",
            "warnings": _safe_warnings(detail)
            or [_warning("eventkit_read_error", "Reminder alarm-state check could not be read safely.")],
        }
    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {
            "status": "error",
            "warnings": [_warning("eventkit_read_error", "Reminder alarm-state check could not be read safely.")],
        }
    return {
        "status": "ok",
        "alarms_count": int(reminder.get("alarms_count") or 0),
        "alarms_safe_sha256": str(reminder.get("alarms_safe_sha256") or ""),
        "warnings": [],
    }


def _reminder_dates_match(current: str | None, expected: str | None) -> bool:
    current_dt = _reminder_date_to_datetime(current or "")
    expected_dt = _reminder_date_to_datetime(expected or "")
    if current_dt is None and expected_dt is None:
        return True
    if current_dt is None or expected_dt is None:
        return False
    return abs((current_dt - expected_dt).total_seconds()) < 1


def _current_reminder_start_state(
    reminder_id: str,
    *,
    runner: EventKitRunner,
) -> dict[str, Any]:
    try:
        detail = runner(
            {
                "command": "reminder_by_id",
                "reminder_id": reminder_id,
                "include_content": False,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminder start-date-state check timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminder start-date-state check is unavailable through the local EventKit helper.",
                )
            ],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "error",
            "warnings": [_warning("target_not_found", "Reminder target was not found through EventKit.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": "error",
            "warnings": _safe_warnings(detail)
            or [_warning("eventkit_read_error", "Reminder start-date-state check could not be read safely.")],
        }
    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {
            "status": "error",
            "warnings": [_warning("eventkit_read_error", "Reminder start-date-state check could not be read safely.")],
        }
    return {
        "status": "ok",
        "start_date": str(reminder.get("start_date") or ""),
        "warnings": [],
    }


def _current_reminder_recurrence_state(
    reminder_id: str,
    *,
    runner: EventKitRunner,
) -> dict[str, Any]:
    try:
        detail = runner(
            {
                "command": "reminder_by_id",
                "reminder_id": reminder_id,
                "include_content": False,
                "include_recurrence_proof": True,
            },
            EVENTKIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_timeout",
                    "Reminder recurrence-state check timed out through the local EventKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "eventkit_unavailable",
                    "Reminder recurrence-state check is unavailable through the local EventKit helper.",
                )
            ],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "error",
            "warnings": [_warning("target_not_found", "Reminder target was not found through EventKit.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": "error",
            "warnings": _safe_warnings(detail)
            or [_warning("eventkit_read_error", "Reminder recurrence-state check could not be read safely.")],
        }
    reminder = detail.get("reminder")
    if not isinstance(reminder, dict):
        return {
            "status": "error",
            "warnings": [_warning("eventkit_read_error", "Reminder recurrence-state check could not be read safely.")],
        }
    recurrence = reminder.get("recurrence")
    return {
        "status": "ok",
        "recurrence_present": bool(reminder.get("recurrence_present")),
        "recurrence": recurrence if isinstance(recurrence, dict) else _empty_recurrence(),
        "warnings": [],
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


def _resolve_eventkit_list_id(handle: str, reminder_lists: Any) -> str | None:
    if not isinstance(reminder_lists, list):
        return None
    for reminder_list in reminder_lists:
        if not isinstance(reminder_list, dict):
            continue
        list_id = str(reminder_list.get("list_id") or "")
        if list_id and opaque_handle_matches(
            handle,
            EVENTKIT_REMINDER_LIST_HANDLE_PREFIX,
            list_id,
        ):
            return list_id
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
    return {
        "schema_version": 1,
        "status": status,
        "source": "reminders",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": authorization_status,
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": None,
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
    return safe_warning_payloads(
        response,
        _warning,
        fallback_message="Reminders warning detail was redacted.",
    )


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


def _normalize_start_date(
    value: str,
    *,
    required: bool,
) -> tuple[str | None, dict[str, str] | None]:
    stripped = value.strip()
    if not stripped:
        if required:
            return None, _warning("missing_required_field", "Missing required field: start_date.")
        return None, None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
        return stripped, None
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None, _warning(
            "invalid_start_date",
            "Start date must be YYYY-MM-DD or ISO 8601 with a timezone.",
        )
    if parsed.tzinfo is None:
        return None, _warning(
            "invalid_start_date",
            "Start date timestamps must include a timezone.",
        )
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"), None


def _reminder_date_to_datetime(value: str) -> datetime | None:
    stripped = value.strip()
    if not stripped:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
        try:
            return datetime.fromisoformat(stripped).replace(tzinfo=UTC)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _start_date_not_after_due_warning(
    start_date: str | None,
    due_date: str | None,
) -> dict[str, str] | None:
    if not start_date or not due_date:
        return None
    start_dt = _reminder_date_to_datetime(start_date)
    due_dt = _reminder_date_to_datetime(due_date)
    if start_dt is None or due_dt is None:
        return None
    if start_dt > due_dt:
        return _warning(
            "invalid_start_date",
            "Reminder start date must be on or before the due date when both are present.",
        )
    return None


def _reminder_recurrence_end_date_warning(
    recurrence: dict[str, Any] | None,
    *,
    due_date: str | None,
) -> dict[str, str] | None:
    if not recurrence or not recurrence.get("recurrence_present"):
        return None
    end_date = str(recurrence.get("end_date") or "")
    if not end_date:
        return None
    if not due_date:
        return None
    anchor_dt = _reminder_date_to_datetime(due_date)
    end_dt = _reminder_date_to_datetime(end_date)
    if anchor_dt is None or end_dt is None:
        return None
    if end_dt <= anchor_dt:
        return _warning(
            "invalid_recurrence",
            "recurrence_end_date must be after the reminder due date anchor.",
        )
    if end_dt > anchor_dt + timedelta(days=_CAL_MAX_RECURRENCE_END_DAYS):
        return _warning(
            "invalid_recurrence",
            f"recurrence_end_date must be within {_CAL_MAX_RECURRENCE_END_DAYS} days of the reminder due date anchor.",
        )
    return None


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


def _normalize_bool(
    value: bool | str | None,
    *,
    field: str,
    required: bool,
) -> tuple[bool | None, dict[str, str] | None]:
    if value is None or value == "":
        if required:
            return None, _warning("missing_required_field", f"Missing required field: {field}.")
        return None, None
    if isinstance(value, bool):
        return value, None
    lowered = value.strip().casefold()
    if lowered == "true":
        return True, None
    if lowered == "false":
        return False, None
    return None, _warning("invalid_bool", f"{field} must be true or false.")


def _normalize_priority(
    value: int | str | None,
    *,
    field: str,
    required: bool,
) -> tuple[int | None, dict[str, str] | None]:
    if value is None or value == "":
        if required:
            return None, _warning("missing_required_field", f"Missing required field: {field}.")
        return None, None
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return None, _warning("invalid_priority", "Reminder priority must be an integer from 0 to 9.")
    if priority < 0 or priority > 9:
        return None, _warning("invalid_priority", "Reminder priority must be an integer from 0 to 9.")
    return priority, None


def _normalize_expected_alarms_count(
    value: int | str | None,
    *,
    required: bool,
) -> tuple[int | None, dict[str, str] | None]:
    if value is None or value == "":
        if required:
            return None, _warning("missing_required_field", "Missing required field: expected_alarms_count.")
        return None, None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None, _warning("invalid_expected_alarms_count", "Reminder expected_alarms_count must be a non-negative integer.")
    if count < 0:
        return None, _warning("invalid_expected_alarms_count", "Reminder expected_alarms_count must be a non-negative integer.")
    return count, None


def _normalize_sha256(
    value: str,
    *,
    field: str,
    required: bool,
) -> tuple[str, dict[str, str] | None]:
    stripped = value.strip().lower()
    if not stripped:
        if required:
            return "", _warning("missing_required_field", f"Missing required field: {field}.")
        return "", None
    if not re.fullmatch(r"[0-9a-f]{64}", stripped):
        return "", _warning("invalid_expected_sha256", f"{field} must be a 64-character SHA-256 hex digest.")
    return stripped, None


def _normalize_alarm_absolute_dates(
    value: list[str] | None,
    *,
    field: str,
    required: bool,
) -> tuple[list[str], dict[str, str] | None]:
    if value is None:
        value = []
    if not isinstance(value, list):
        return [], _warning("invalid_alarm_absolute_dates", f"{field} must be a list of ISO 8601 timestamps with timezones.")
    if required and not value:
        return [], _warning("missing_required_field", f"Missing required field: {field}.")
    if len(value) > MAX_REMINDER_ALARMS:
        return [], _warning("too_many_alarm_absolute_dates", f"{field} supports at most {MAX_REMINDER_ALARMS} timestamps.")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return [], _warning("invalid_alarm_absolute_dates", f"{field} must contain only timestamp strings.")
        token = item.strip()
        if not token:
            return [], _warning("invalid_alarm_absolute_dates", f"{field} must contain only non-empty timestamp strings.")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
            return [], _warning("invalid_alarm_absolute_dates", f"{field} must include date and time with a timezone.")
        try:
            parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
        except ValueError:
            return [], _warning("invalid_alarm_absolute_dates", f"{field} must contain ISO 8601 timestamps with timezones.")
        if parsed.tzinfo is None:
            return [], _warning("invalid_alarm_absolute_dates", f"{field} must contain ISO 8601 timestamps with timezones.")
        normalized.append(parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    return sorted(set(normalized)), None


def _normalize_alarm_offsets(
    value: list[int] | None,
    *,
    field: str,
    required: bool,
) -> tuple[list[int], dict[str, str] | None]:
    if value is None:
        value = []
    if not isinstance(value, list):
        return [], _warning("invalid_alarm_offsets", f"{field} must be a JSON array of integer minute offsets.")
    if required and not value:
        return [], _warning("missing_required_field", f"Missing required field: {field}.")
    if len(value) > MAX_REMINDER_ALARMS:
        return [], _warning("too_many_alarm_offsets", f"{field} supports at most {MAX_REMINDER_ALARMS} offsets.")
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            return [], _warning("invalid_alarm_offsets", f"{field} must contain only integer minute offsets.")
        if item < MIN_REMINDER_ALARM_OFFSET_MINUTES or item > MAX_REMINDER_ALARM_OFFSET_MINUTES:
            return [], _warning(
                "invalid_alarm_offset_range",
                f"{field} offsets must be between {MIN_REMINDER_ALARM_OFFSET_MINUTES} and {MAX_REMINDER_ALARM_OFFSET_MINUTES} minutes.",
            )
        normalized.append(item)
    return sorted(set(normalized)), None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_reminder_url(
    value: str,
    *,
    field: str,
    required: bool,
) -> tuple[str, str, str, str, dict[str, str] | None]:
    normalized = value
    if not normalized:
        if required:
            return "", "", "", "", _warning("missing_required_field", f"Missing required field: {field}.")
        return "", "", "", "", None
    if len(normalized) > MAX_REMINDER_URL_CHARS:
        return "", "", "", "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        return "", "", "", "", _warning("invalid_url", f"{field} must not contain control characters.")
    if any(ord(ch) > 126 for ch in normalized):
        return "", "", "", "", _warning("invalid_url", f"{field} must contain only ASCII URL characters.")
    if any(ch.isspace() for ch in normalized):
        return "", "", "", "", _warning("invalid_url", f"{field} must not contain whitespace.")
    try:
        parsed = urlparse(normalized)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return "", "", "", "", _warning("invalid_url", f"{field} must be an allowed URL.")
    scheme = parsed.scheme.lower()
    if scheme not in SAFE_REMINDER_URL_SCHEMES:
        return "", "", "", "", _warning("invalid_url", f"{field} must use http, https, mailto, or tel.")
    if scheme in {"http", "https"}:
        if not parsed.netloc or not hostname:
            return "", "", "", "", _warning("invalid_url", f"{field} must include a host.")
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            return "", "", "", "", _warning("invalid_url", f"{field} must not include embedded credentials.")
        return normalized, scheme, hostname, _sha256_text(normalized), None
    if scheme == "mailto":
        if parsed.netloc or parsed.params or parsed.query or parsed.fragment:
            return "", "", "", "", _warning("invalid_url", f"{field} mailto URLs must contain only one recipient address.")
        if not MAILTO_REMINDER_URL_RE.fullmatch(parsed.path):
            return "", "", "", "", _warning("invalid_url", f"{field} mailto URL must contain one valid recipient address.")
        return normalized, scheme, "", _sha256_text(normalized), None
    if scheme == "tel":
        if parsed.netloc or parsed.query or parsed.fragment or not parsed.path:
            return "", "", "", "", _warning("invalid_url", f"{field} tel URLs must contain only one dial string.")
        dial_string = parsed.path
        if parsed.params:
            dial_string = f"{dial_string};{parsed.params}"
        if not TEL_REMINDER_URL_RE.fullmatch(dial_string):
            return "", "", "", "", _warning("invalid_url", f"{field} tel URL must contain one bounded dial string.")
        return normalized, scheme, "", _sha256_text(normalized), None
    return "", "", "", "", _warning("invalid_url", f"{field} must be an allowed URL.")


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
    elif operation == "create_with_start_date":
        payload.update(
            {
                "title": proposed["title"],
                "list_name": target["list_name"],
                "due_date": proposed["due_date"] or "",
                "start_date": proposed["start_date"] or "",
                "notes": proposed["notes_text"],
            }
        )
    elif operation == "create_with_recurrence":
        payload.update(
            {
                "title": proposed["title"],
                "list_name": target["list_name"],
                "due_date": proposed["due_date"] or "",
                "notes": proposed["notes_text"],
                "recurrence": proposed["recurrence"],
            }
        )
    elif operation == "update_start_date":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_start_date": target["expected_start_date"] or "",
                "start_date": proposed["start_date"] or "",
            }
        )
    elif operation == "update_recurrence":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_recurrence_present": target["expected_recurrence_present"],
                "expected_recurrence": target["expected_recurrence"],
                "recurrence": proposed["recurrence"],
                "clear_recurrence": bool(proposed.get("recurrence_clear_requested")),
            }
        )
    elif operation in {"complete", "uncomplete"}:
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "completed": proposed["completed"],
            }
        )
    elif operation == "update_due_date":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "due_date": proposed["due_date"],
            }
        )
    elif operation == "update_title":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "title": proposed["title"],
            }
        )
    elif operation == "update_notes":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "notes": proposed["notes_text"],
            }
        )
    elif operation == "update_priority":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_priority": target["expected_priority"],
                "priority": proposed["priority"],
            }
        )
    elif operation in {"update_url", "clear_url"}:
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_url_present": target["expected_url_present"],
                "expected_url_sha256": target["expected_url_sha256"],
            }
        )
    elif operation in ALARM_OPERATIONS:
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_alarms_count": target["expected_alarms_count"],
                "expected_alarms_sha256": target["expected_alarms_sha256"],
            }
        )
        if operation in ALARM_ABSOLUTE_DATE_OPERATIONS:
            payload["alarm_absolute_dates"] = proposed["alarm_absolute_dates"]
        if operation in ALARM_OFFSET_OPERATIONS:
            payload["alarm_offsets_minutes"] = proposed["alarm_offsets_minutes"]
    elif operation == "move_to_list":
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_list_name": target["expected_list_name"],
            }
        )
    else:
        payload.update(
            {
                "expected_title": target["expected_title"],
                "expected_completed": target["expected_completed"],
                "expected_priority": target["expected_priority"],
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
