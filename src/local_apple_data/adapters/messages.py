from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_MESSAGES_DB = Path.home() / "Library/Messages/chat.db"
MESSAGES_TABLES = ["chat", "message", "chat_message_join", "chat_handle_join", "handle"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
DEFAULT_MESSAGES_LIMIT = 25
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MESSAGE_TEXT_CHARS = 2000
CHAT_HANDLE_PREFIX = "messages:chat"


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


def _check_schema(connection) -> str:
    require_columns(connection, "chat", {"ROWID", "guid", "display_name", "service_name"})
    require_columns(
        connection,
        "message",
        {"ROWID", "text", "date", "is_from_me", "handle_id", "service"},
    )
    require_columns(connection, "chat_message_join", {"chat_id", "message_id"})
    require_columns(connection, "chat_handle_join", {"chat_id", "handle_id"})
    require_columns(connection, "handle", {"ROWID", "id", "service"})
    return schema_fingerprint(connection, MESSAGES_TABLES)


def check_messages_schema(*, db_path: Path = DEFAULT_MESSAGES_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "messages",
            "schema_fingerprint": None,
            "tables_checked": MESSAGES_TABLES,
            "warnings": [
                {
                    "code": "messages_schema_unavailable",
                    "message": "Messages local schema could not be checked.",
                }
            ],
        }
    return {
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "tables_checked": MESSAGES_TABLES,
        "warnings": [],
    }


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Messages chat search requires a non-empty chat display-name query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Messages chat search requires at least two letters or digits.",
            )
        ],
    }


def search_message_chats(
    query: str,
    *,
    db_path: Path = DEFAULT_MESSAGES_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    c.ROWID AS chat_id,
                    COALESCE(c.display_name, '') AS display_name,
                    c.service_name AS service_name,
                    COUNT(DISTINCT chj.handle_id) AS participants_count,
                    COUNT(DISTINCT m.ROWID) AS message_count,
                    MAX(m.date) AS last_message_date
                FROM chat c
                LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
                LEFT JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
                LEFT JOIN message m ON m.ROWID = cmj.message_id
                WHERE COALESCE(c.display_name, '') LIKE ? ESCAPE '\\'
                GROUP BY c.ROWID
                ORDER BY COALESCE(MAX(m.date), 0) DESC
                LIMIT ?
                """,
                (like_contains_pattern(query), bounded_limit),
            ).fetchall()
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "chat_display_name", "limit": bounded_limit},
        "results": [_chat_metadata(row, fingerprint) for row in rows],
        "result_count": len(rows),
        "warnings": [],
    }


def get_message_chat(
    handle: str,
    *,
    db_path: Path = DEFAULT_MESSAGES_DB,
    max_messages: int = DEFAULT_MESSAGES_LIMIT,
    max_chars: int = DEFAULT_CONTENT_CHARS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CHAT_HANDLE_PREFIX):
        return _invalid_handle_result()

    bounded_messages = max(1, min(max_messages, 100))
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            chat_id = _resolve_chat_id(connection, fingerprint, handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(content_inspected=False),
                    "result": None,
                    "warnings": [],
                }
            chat_row = _select_chat(connection, chat_id)
            message_rows = _select_messages(connection, chat_id, bounded_messages)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=True)

    result = _chat_metadata(chat_row, fingerprint)
    messages, transcript_chars, truncated = _message_payloads(message_rows, bounded_chars)
    result.update(
        {
            "messages": messages,
            "messages_returned": len(messages),
            "max_messages": bounded_messages,
            "transcript_chars": transcript_chars,
            "transcript_truncated": truncated,
        }
    )
    warnings = []
    if truncated:
        warnings.append(
            _warning(
                "content_truncated",
                "Messages transcript was truncated to the requested limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def _select_chat(connection, chat_id: int):
    row = connection.execute(
        """
        SELECT
            c.ROWID AS chat_id,
            COALESCE(c.display_name, '') AS display_name,
            c.service_name AS service_name,
            COUNT(DISTINCT chj.handle_id) AS participants_count,
            COUNT(DISTINCT m.ROWID) AS message_count,
            MAX(m.date) AS last_message_date
        FROM chat c
        LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
        LEFT JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        LEFT JOIN message m ON m.ROWID = cmj.message_id
        WHERE c.ROWID = ?
        GROUP BY c.ROWID
        LIMIT 1
        """,
        (chat_id,),
    ).fetchone()
    if row is None:
        raise StoreUnavailableError("Messages chat could not be selected.")
    return row


def _select_messages(connection, chat_id: int, limit: int):
    rows = connection.execute(
        """
        SELECT
            m.ROWID AS message_id,
            m.text AS text,
            m.date AS message_date,
            m.is_from_me AS is_from_me,
            m.service AS service
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ?
          AND m.text IS NOT NULL
          AND m.text != ''
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()
    return list(reversed(rows))


def _resolve_chat_id(connection, fingerprint: str, handle: str) -> int | None:
    rows = connection.execute("SELECT ROWID AS chat_id FROM chat").fetchall()
    for row in rows:
        chat_id = int(row["chat_id"])
        if opaque_handle_matches(handle, CHAT_HANDLE_PREFIX, fingerprint, chat_id):
            return chat_id
    return None


def _chat_metadata(row, fingerprint: str) -> dict[str, Any]:
    chat_id = int(row["chat_id"])
    return {
        "handle": make_opaque_handle(CHAT_HANDLE_PREFIX, fingerprint, chat_id),
        "display_name": _bounded_string(row["display_name"], 500),
        "service_name": _bounded_string(row["service_name"], 50),
        "participants_count": int(row["participants_count"] or 0),
        "message_count": int(row["message_count"] or 0),
        "last_message_date": _message_date(row["last_message_date"]),
    }


def _message_payloads(rows: list[Any], max_chars: int) -> tuple[list[dict[str, Any]], int, bool]:
    messages: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for row in rows:
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        text = _bounded_string(row["text"], min(MESSAGE_TEXT_CHARS, remaining))
        original = _bounded_string(row["text"], MESSAGE_TEXT_CHARS)
        if len(original) > len(text):
            truncated = True
        used += len(text)
        messages.append(
            {
                "date": _message_date(row["message_date"]),
                "direction": "sent" if bool(row["is_from_me"]) else "received",
                "service": _bounded_string(row["service"], 50),
                "text": text,
                "text_chars": len(text),
                "text_truncated": len(original) > len(text),
            }
        )
    return messages, used, truncated


def _message_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    seconds = raw / 1_000_000_000 if abs(raw) > 10_000_000_000 else raw
    try:
        return (APPLE_EPOCH + timedelta(seconds=seconds)).isoformat()
    except OverflowError:
        return None


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected messages:chat:v1 opaque handle from search output.",
            )
        ],
    }


def _store_degraded_result(exc: StoreUnavailableError, *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "messages",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": [_warning("messages_store_unavailable", str(exc))],
    }


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text[: max(1, min(max_chars, MAX_CONTENT_CHARS))]
