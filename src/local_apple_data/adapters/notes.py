from __future__ import annotations

import re
import sqlite3
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from ..handles import int_handle_matches, is_int_handle, make_int_handle
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_NOTES_DB = (
    Path.home()
    / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
NOTES_APPLESCRIPT_TIMEOUT_SECONDS = 10.0

NOTES_TABLES = ["ZICCLOUDSYNCINGOBJECT"]
ScriptRunner = Callable[[str, float], str]


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
    require_columns(
        connection,
        "ZICCLOUDSYNCINGOBJECT",
        {
            "Z_PK",
            "ZTITLE1",
            "ZTITLE",
            "ZSNIPPET",
            "ZCREATIONDATE1",
            "ZMODIFICATIONDATE1",
            "ZISPASSWORDPROTECTED",
            "ZMARKEDFORDELETION",
            "ZNOTEDATA",
        },
    )
    return schema_fingerprint(connection, NOTES_TABLES)


def check_notes_schema(*, db_path: Path = DEFAULT_NOTES_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError as exc:
        return {
            "status": "degraded",
            "source": "notes",
            "schema_fingerprint": None,
            "tables_checked": NOTES_TABLES,
            "warnings": [{"code": "notes_schema_unavailable", "message": str(exc)}],
        }
    return {
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "tables_checked": NOTES_TABLES,
        "warnings": [],
    }


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "empty_query",
                "message": "Notes metadata search requires a non-empty title or snippet query.",
            }
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "broad_query",
                "message": "Notes metadata search requires at least two letters or digits.",
            }
        ],
    }


def _row_to_metadata(row) -> dict[str, Any]:
    return {
        "handle": make_int_handle("notes:note", int(row["note_id"])),
        "title": row["title"],
        "fallback_title": row["fallback_title"],
        "snippet": row["snippet"],
        "creation_date": row["creation_date"],
        "modification_date": row["modification_date"],
        "password_protected": bool(row["password_protected"])
        if row["password_protected"] is not None
        else None,
        "marked_for_deletion": bool(row["marked_for_deletion"])
        if row["marked_for_deletion"] is not None
        else None,
    }


def search_notes_metadata(
    query: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    limit: int = 20,
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
                    Z_PK AS note_id,
                    ZTITLE1 AS title,
                    ZTITLE AS fallback_title,
                    ZSNIPPET AS snippet,
                    ZCREATIONDATE1 AS creation_date,
                    ZMODIFICATIONDATE1 AS modification_date,
                    ZISPASSWORDPROTECTED AS password_protected,
                    ZMARKEDFORDELETION AS marked_for_deletion
                FROM ZICCLOUDSYNCINGOBJECT
                WHERE ZNOTEDATA IS NOT NULL
                  AND COALESCE(ZMARKEDFORDELETION, 0) = 0
                  AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
                  AND (
                    ZTITLE1 LIKE ? ESCAPE '\\'
                    OR ZTITLE LIKE ? ESCAPE '\\'
                    OR ZSNIPPET LIKE ? ESCAPE '\\'
                  )
                ORDER BY COALESCE(ZMODIFICATIONDATE1, ZCREATIONDATE1, 0) DESC
                LIMIT ?
                """,
                (
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    bounded_limit,
                ),
            ).fetchall()
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [{"code": "notes_store_unavailable", "message": str(exc)}],
        }

    results = [_row_to_metadata(row) for row in rows]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "title_or_snippet", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_notes_metadata(handle: str, *, db_path: Path = DEFAULT_NOTES_DB) -> dict[str, Any]:
    if not is_int_handle(handle, "notes:note"):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "notes",
            "privacy": _privacy(),
            "result": None,
            "warnings": [
                {
                    "code": "invalid_handle",
                    "message": "Expected notes:note opaque handle from search output.",
                }
            ],
        }

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = connection.execute(
                """
                SELECT
                    Z_PK AS note_id,
                    ZTITLE1 AS title,
                    ZTITLE AS fallback_title,
                    ZSNIPPET AS snippet,
                    ZCREATIONDATE1 AS creation_date,
                    ZMODIFICATIONDATE1 AS modification_date,
                    ZISPASSWORDPROTECTED AS password_protected,
                    ZMARKEDFORDELETION AS marked_for_deletion
                FROM ZICCLOUDSYNCINGOBJECT
                WHERE Z_PK = ?
                  AND ZNOTEDATA IS NOT NULL
                  AND COALESCE(ZMARKEDFORDELETION, 0) = 0
                  AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
                LIMIT 1
                """,
                (note_id,),
            ).fetchone()
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "result": None,
            "warnings": [{"code": "notes_store_unavailable", "message": str(exc)}],
        }

    warnings = []
    result = _row_to_metadata(row) if row else None
    if result and result["password_protected"]:
        warnings.append(
            {
                "code": "password_protected_note",
                "message": "Metadata only; content retrieval is blocked for locked notes.",
            }
        )

    return {
        "schema_version": 1,
        "status": "ok" if row else "not_found",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": result,
        "warnings": warnings,
    }


def get_notes_content(
    handle: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    offset: int = 0,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    if not is_int_handle(handle, "notes:note"):
        return _invalid_content_handle_result()

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    bounded_offset = max(0, offset)
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(content_inspected=False),
                    "result": None,
                    "warnings": [],
                }
            row = _select_notes_row(connection, note_id)
            store_uuid = _notes_store_uuid(connection)
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_warning("notes_store_unavailable", str(exc))],
        }

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "notes",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }

    result = _row_to_content_metadata(row)
    if not store_uuid:
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "notes",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": result,
            "warnings": [
                _warning(
                    "content_unavailable",
                    "Notes content could not be resolved from the local store mapping.",
                )
            ],
        }

    runner = script_runner or _run_osascript
    try:
        html = runner(
            _notes_body_script(store_uuid, int(row["note_id"])),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "notes",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": result,
            "warnings": [
                _warning(
                    "automation_timeout",
                    "Notes content retrieval timed out through local automation.",
                )
            ],
        }
    except NotesAutomationError:
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "notes",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": result,
            "warnings": [
                _warning("read_error", "Notes content could not be read safely.")
            ],
        }

    content_text, truncated, total_chars, next_offset = _bounded_text(
        _html_to_text(html),
        bounded_chars,
        offset=bounded_offset,
    )
    result.update(
        {
            "content_text": content_text,
            "content_chars": len(content_text),
            "content_offset": bounded_offset,
            "content_total_chars": total_chars,
            "next_offset": next_offset,
            "truncated": truncated,
        }
    )
    warnings = []
    if truncated:
        warnings.append(
            _warning("content_truncated", "Notes content was truncated to the requested limit.")
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def _resolve_notes_handle_note_id(connection, handle: str) -> int | None:
    rows = connection.execute(
        """
        SELECT Z_PK AS note_id
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZNOTEDATA IS NOT NULL
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
        """
    ).fetchall()
    for row in rows:
        note_id = int(row["note_id"])
        if int_handle_matches(handle, "notes:note", note_id):
            return note_id
    return None


def _row_to_content_metadata(row) -> dict[str, Any]:
    metadata = _row_to_metadata(row)
    metadata.update(
        {
            "content_text": "",
            "content_chars": 0,
            "content_offset": 0,
            "content_total_chars": 0,
            "next_offset": None,
            "truncated": False,
        }
    )
    return metadata


def _invalid_content_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected notes:note:v2 opaque handle from search output.",
            )
        ],
    }


def _select_notes_row(connection, note_id: int):
    return connection.execute(
        """
        SELECT
            Z_PK AS note_id,
            ZTITLE1 AS title,
            ZTITLE AS fallback_title,
            ZSNIPPET AS snippet,
            ZCREATIONDATE1 AS creation_date,
            ZMODIFICATIONDATE1 AS modification_date,
            ZISPASSWORDPROTECTED AS password_protected,
            ZMARKEDFORDELETION AS marked_for_deletion
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE Z_PK = ?
          AND ZNOTEDATA IS NOT NULL
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
        LIMIT 1
        """,
        (note_id,),
    ).fetchone()


def _notes_store_uuid(connection) -> str | None:
    try:
        row = connection.execute("SELECT Z_UUID FROM Z_METADATA LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    value = row[0]
    if isinstance(value, str) and re.fullmatch(r"[A-Fa-f0-9-]{16,64}", value):
        return value
    return None


def _notes_body_script(store_uuid: str, note_id: int) -> str:
    note_ref = _applescript_string(f"x-coredata://{store_uuid}/ICNote/p{note_id}")
    return f"""
set targetId to {note_ref}
tell application "Notes"
    set targetNote to note id targetId
    return body of targetNote
end tell
"""


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class NotesAutomationError(RuntimeError):
    pass


def _run_osascript(script: str, timeout: float) -> str:
    completed = subprocess.run(
        ["osascript"],
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise NotesAutomationError()
    return completed.stdout


def _bounded_text(
    text: str,
    max_chars: int,
    *,
    offset: int = 0,
) -> tuple[str, bool, int, int | None]:
    normalized = _normalize_text(text)
    total_chars = len(normalized)
    bounded_offset = max(0, offset)
    if bounded_offset >= total_chars:
        return "", False, total_chars, None
    end = min(total_chars, bounded_offset + max_chars)
    content = normalized[bounded_offset:end]
    next_offset = end if end < total_chars else None
    return content, next_offset is not None, total_chars, next_offset


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


class _HTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    return re.sub(r"\n{2,}", "\n", _normalize_text(parser.text()))
