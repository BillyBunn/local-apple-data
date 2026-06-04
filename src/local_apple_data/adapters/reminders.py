from __future__ import annotations

import hashlib
import json
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
DEFAULT_EVENTKIT_SCAN_LIMIT = 10000
EVENTKIT_REMINDER_HANDLE_PREFIX = "reminders:reminder:eventkit"
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


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= bounded_chars:
        return normalized, False
    return normalized[:bounded_chars], True
