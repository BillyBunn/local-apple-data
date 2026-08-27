from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from ..handles import (
    int_handle_matches,
    is_int_handle,
    is_opaque_handle,
    make_int_handle,
    make_opaque_handle,
    opaque_handle_matches,
)
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)
from .warning_safety import safe_warning_payloads


DEFAULT_NOTES_DB = (
    Path.home()
    / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)
DEFAULT_NOTES_CONTAINER = Path.home() / "Library/Group Containers/group.com.apple.notes"
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_BODY_HTML_CHARS = 24000
NOTES_APPLESCRIPT_TIMEOUT_SECONDS = 10.0
MAX_PREVIEW_TITLE_CHARS = 256
MAX_CREATE_BODY_CHARS = 12000
MAX_BODY_PREVIEW_CHARS = 240
NOTES_CONTENT_FORMATS = {"text", "html"}
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_EXPORT_PAGE_LIMIT = 10
MAX_EXPORT_PAGE_LIMIT = 20
DEFAULT_ATTACHMENTS_LIMIT = 20
ATTACHMENT_HANDLE_PREFIX = "notes:attachment"
FOLDER_HANDLE_PREFIX = "notes:folder"
NOTE_ENTITY_ID = 12
FOLDER_ENTITY_ID = 15
PLAN_OPERATIONS = {
    "create",
    "create_html",
    "create_folder",
    "rename_folder",
    "delete_folder",
    "move_folder",
    "append_text",
    "replace_text",
    "replace_html",
    "move_to_folder",
    "delete",
}
APPROVAL_TOKEN_PREFIX = "notes-apply:v1:"
AUTOMATION_ERROR_PREFIX = "__LOCAL_APPLE_DATA_ERROR__:"

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


def _export_privacy(*, content_exported: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": content_exported,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
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


def _notes_schema_unavailable_warning() -> dict[str, str]:
    return _warning("notes_schema_unavailable", "Notes schema is unavailable or unsupported.")


def _notes_store_unavailable_warning() -> dict[str, str]:
    return _warning("notes_store_unavailable", "Notes local store is unavailable or unreadable.")


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


def _check_attachment_schema(connection) -> str:
    fingerprint = _check_schema(connection)
    require_columns(
        connection,
        "ZICCLOUDSYNCINGOBJECT",
        {
            "Z_PK",
            "ZNOTE",
            "ZFILENAME",
            "ZTITLE",
            "ZFILESIZE",
            "ZTYPEUTI",
            "ZCREATIONDATE",
            "ZMODIFICATIONDATE",
            "ZIDENTIFIER",
            "ZREMOTEFILEURLSTRING",
            "ZMERGEABLEDATA",
            "ZMERGEABLEDATA1",
            "ZMERGEABLEDATA2",
        },
    )
    return fingerprint


def _check_folder_schema(connection) -> str:
    fingerprint = _check_schema(connection)
    require_columns(
        connection,
        "ZICCLOUDSYNCINGOBJECT",
        {
            "Z_ENT",
            "ZACCOUNT8",
            "ZFOLDER",
            "ZFOLDERTYPE",
            "ZFOLDERMODIFICATIONDATE",
            "ZPARENT",
            "ZSMARTFOLDERQUERYJSON",
            "ZTITLE2",
        },
    )
    return fingerprint


def check_notes_schema(*, db_path: Path = DEFAULT_NOTES_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "notes",
            "schema_fingerprint": None,
            "tables_checked": NOTES_TABLES,
            "warnings": [_notes_schema_unavailable_warning()],
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


def _row_to_folder_item_metadata(row) -> dict[str, Any]:
    metadata = _row_to_metadata(row)
    metadata.pop("snippet", None)
    return metadata


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
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_notes_store_unavailable_warning()],
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


def search_notes_folders(
    query: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    limit: int = 20,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "empty_query",
                    "Notes folder search requires a non-empty folder title query.",
                )
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "broad_query",
                    "Notes folder search requires at least two letters or digits.",
                )
            ],
        }

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            rows = _select_folder_rows(
                connection,
                query=like_contains_pattern(query),
                limit=bounded_limit,
            )
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_notes_store_unavailable_warning()],
        }

    results = [_folder_metadata(row, fingerprint) for row in rows]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "folder_title", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_notes_folder(handle: str, *, db_path: Path = DEFAULT_NOTES_DB) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_folder_handle_result()

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, handle)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "result": None,
            "warnings": [_notes_store_unavailable_warning()],
        }

    return {
        "schema_version": 1,
        "status": "ok" if row is not None else "not_found",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": _folder_metadata(row, fingerprint) if row is not None else None,
        "warnings": [],
    }


def list_notes_folder_items(
    handle: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    limit: int = 20,
) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 50))
    empty_payload = {
        "folder": None,
        "results": [],
        "child_folders": [],
        "result_count": 0,
        "child_folder_count": 0,
    }
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        result = _invalid_folder_handle_result()
        result.update(empty_payload)
        return result

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, handle)
            if row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "query": {"scope": "selected_folder_items", "limit": bounded_limit},
                    "warnings": [],
                    **empty_payload,
                }
            folder = _folder_metadata(row, fingerprint)
            if _folder_is_smart(row):
                return {
                    "schema_version": 1,
                    "status": "error",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "query": {"scope": "selected_folder_items", "limit": bounded_limit},
                    "folder": folder,
                    "results": [],
                    "child_folders": [],
                    "result_count": 0,
                    "child_folder_count": 0,
                    "warnings": [
                        _warning(
                            "unsupported_smart_folder",
                            "Notes folder item listing requires an exact normal folder handle.",
                        )
                    ],
                }
            child_rows = _select_child_folder_rows(
                connection,
                parent_folder_id=int(row["folder_id"]),
                limit=bounded_limit,
            )
            note_limit = max(0, bounded_limit - len(child_rows))
            note_rows = (
                _select_note_rows_for_folder(
                    connection,
                    folder_id=int(row["folder_id"]),
                    limit=note_limit,
                )
                if note_limit > 0
                else []
            )
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "query": {"scope": "selected_folder_items", "limit": bounded_limit},
            "warnings": [_notes_store_unavailable_warning()],
            **empty_payload,
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "selected_folder_items", "limit": bounded_limit},
        "folder": folder,
        "results": [_row_to_folder_item_metadata(note) for note in note_rows],
        "child_folders": [_folder_metadata(child, fingerprint) for child in child_rows],
        "result_count": len(note_rows),
        "child_folder_count": len(child_rows),
        "folder_content_returned": False,
        "note_content_returned": False,
        "raw_identifier_returned": False,
        "warnings": [],
    }


def list_notes_folder_tree(
    handle: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    depth: int = 2,
    limit: int = 50,
) -> dict[str, Any]:
    bounded_depth = max(1, min(depth, 3))
    bounded_limit = max(1, min(limit, 50))
    empty_payload = {
        "folder": None,
        "results": [],
        "result_count": 0,
        "folder_content_returned": False,
        "note_content_returned": False,
        "raw_identifier_returned": False,
    }
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        result = _invalid_folder_handle_result()
        result.update(empty_payload)
        return result

    warnings: list[dict[str, str]] = []
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, handle)
            if row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "query": {
                        "scope": "selected_folder_tree",
                        "limit": bounded_limit,
                        "max_depth": bounded_depth,
                        "recursive": True,
                    },
                    "warnings": [],
                    **empty_payload,
                }
            folder = _folder_metadata(row, fingerprint)
            if _folder_is_smart(row):
                return {
                    "schema_version": 1,
                    "status": "error",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "query": {
                        "scope": "selected_folder_tree",
                        "limit": bounded_limit,
                        "max_depth": bounded_depth,
                        "recursive": True,
                    },
                    "warnings": [
                        _warning(
                            "unsupported_smart_folder",
                            "Notes folder tree listing requires an exact normal folder handle.",
                        )
                    ],
                    **{**empty_payload, "folder": folder},
                }
            results, warnings = _notes_folder_tree_nodes(
                connection,
                fingerprint=fingerprint,
                parent_folder_id=int(row["folder_id"]),
                root_handle=handle,
                max_depth=bounded_depth,
                limit=bounded_limit,
            )
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "query": {
                "scope": "selected_folder_tree",
                "limit": bounded_limit,
                "max_depth": bounded_depth,
                "recursive": True,
            },
            "warnings": [_notes_store_unavailable_warning()],
            **empty_payload,
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {
            "scope": "selected_folder_tree",
            "limit": bounded_limit,
            "max_depth": bounded_depth,
            "recursive": True,
        },
        "folder": folder,
        "results": results,
        "result_count": len(results),
        "folder_content_returned": False,
        "note_content_returned": False,
        "raw_identifier_returned": False,
        "warnings": warnings,
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
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "result": None,
            "warnings": [_notes_store_unavailable_warning()],
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
    content_format: str = "text",
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    if not is_int_handle(handle, "notes:note"):
        return _invalid_content_handle_result()

    normalized_format = str(content_format).strip().lower() or "text"
    if normalized_format not in NOTES_CONTENT_FORMATS:
        return _invalid_content_format_result()
    include_html = normalized_format == "html"

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
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_notes_store_unavailable_warning()],
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
    except (OSError, NotesAutomationError):
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

    full_text = _html_to_text(html)
    content_text, truncated, total_chars, next_offset = _bounded_text(
        full_text,
        bounded_chars,
        offset=bounded_offset,
    )
    result.update(
        {
            "content_format": normalized_format,
            "content_text": content_text,
            "content_chars": len(content_text),
            "content_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
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

    if include_html:
        html_body, html_truncated = _bounded_body_html(html, MAX_BODY_HTML_CHARS)
        result.update(
            {
                "content_html": html_body,
                "content_html_chars": len(html_body),
                "content_html_total_chars": len(html),
                "content_html_truncated": html_truncated,
                "content_html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            }
        )
        if html_truncated:
            warnings.append(
                _warning(
                    "content_html_truncated",
                    "Notes rich-text body HTML was truncated to the requested limit.",
                )
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


def export_notes_folder_content(
    folder_handle: str,
    modified_after: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    cursor: int = 0,
    limit: int = DEFAULT_EXPORT_PAGE_LIMIT,
    max_chars_per_note: int = DEFAULT_CONTENT_CHARS,
    confirm_bulk: bool = False,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    """Bounded, paged, date-bounded note-text export for one exact normal folder (v1.182 gate).

    Operator-approved bulk-content read: returns per-note bounded plain text plus a full-text
    content_sha256 for incremental downstream sync. Transient responses only — this repo persists
    nothing. Password-protected and deleted notes are excluded in SQL; smart folders fail closed.
    """
    bounded_limit = max(1, min(limit, MAX_EXPORT_PAGE_LIMIT))
    bounded_chars = max(1, min(max_chars_per_note, MAX_CONTENT_CHARS))
    bounded_cursor = max(0, cursor)
    query_payload = {
        "scope": "folder_content_export",
        "limit": bounded_limit,
        "cursor": bounded_cursor,
        "modified_after": str(modified_after).strip(),
        "max_chars_per_note": bounded_chars,
    }

    def _export_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "notes",
            "privacy": _bulk_content_privacy(content_inspected=False),
            "query": query_payload,
            "folder": None,
            "results": [],
            "result_count": 0,
            "exported_count": 0,
            "skipped_count": 0,
            "next_cursor": None,
            "warnings": warnings,
        }

    if not confirm_bulk:
        return _export_error(
            [
                _warning(
                    "bulk_export_not_confirmed",
                    "Notes folder content export returns multiple note bodies; pass confirm_bulk=true to acknowledge the operator-approved bulk-content read.",
                )
            ]
        )
    if not is_opaque_handle(folder_handle, FOLDER_HANDLE_PREFIX):
        return _export_error(
            [
                _warning(
                    "invalid_folder_handle",
                    "Notes folder content export requires an exact notes:folder:v1: handle from folder metadata output.",
                )
            ]
        )
    modified_after_apple = _parse_modified_after_to_apple_seconds(modified_after)
    if modified_after_apple is None:
        return _export_error(
            [
                _warning(
                    "invalid_modified_after",
                    "Notes folder content export requires a parseable ISO-8601 modified_after date bound.",
                )
            ]
        )

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
            if row is None:
                result = _export_error([])
                result.update({"status": "not_found", "schema_fingerprint": fingerprint})
                return result
            folder = _folder_metadata(row, fingerprint)
            if _folder_is_smart(row):
                result = _export_error(
                    [
                        _warning(
                            "unsupported_smart_folder",
                            "Notes folder content export requires an exact normal folder handle.",
                        )
                    ]
                )
                result.update({"schema_fingerprint": fingerprint, "folder": folder})
                return result
            note_rows = _select_note_rows_for_export(
                connection,
                folder_id=int(row["folder_id"]),
                modified_after_apple=modified_after_apple,
                limit=bounded_limit,
                offset=bounded_cursor,
            )
            store_uuid = _notes_store_uuid(connection)
    except StoreUnavailableError:
        result = _export_error([_notes_store_unavailable_warning()])
        result.update({"status": "degraded"})
        return result

    has_more = len(note_rows) > bounded_limit
    page_rows = note_rows[:bounded_limit]
    if not store_uuid:
        result = _export_error(
            [
                _warning(
                    "content_unavailable",
                    "Notes content could not be resolved from the local store mapping.",
                )
            ]
        )
        result.update(
            {"status": "content_unavailable", "schema_fingerprint": fingerprint, "folder": folder}
        )
        return result

    runner = script_runner or _run_osascript
    results: list[dict[str, Any]] = []
    exported_count = 0
    skipped_count = 0
    truncated_count = 0
    for note_row in page_rows:
        item = _row_to_folder_item_metadata(note_row)
        try:
            html = runner(
                _notes_body_script(store_uuid, int(note_row["note_id"])),
                NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            item.update({"content_status": "skipped", "skip_reason": "automation_timeout"})
            skipped_count += 1
            results.append(item)
            continue
        except (OSError, NotesAutomationError):
            item.update({"content_status": "skipped", "skip_reason": "read_error"})
            skipped_count += 1
            results.append(item)
            continue
        full_text = _html_to_text(html)
        content_text, truncated, total_chars, _next_offset = _bounded_text(full_text, bounded_chars)
        if truncated:
            truncated_count += 1
        item.update(
            {
                "content_status": "ok",
                "content_format": "text",
                "content_text": content_text,
                "content_chars": len(content_text),
                "content_total_chars": total_chars,
                "content_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                "truncated": truncated,
            }
        )
        exported_count += 1
        results.append(item)

    warnings = []
    if truncated_count:
        warnings.append(
            _warning(
                "content_truncated",
                "Some exported notes were truncated to max_chars_per_note; re-read long notes by exact handle for full text.",
            )
        )
    if skipped_count:
        warnings.append(
            _warning(
                "note_content_skipped",
                "Some notes could not be read through local automation this page and were returned as metadata-only skips.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _bulk_content_privacy(content_inspected=exported_count > 0),
        "query": query_payload,
        "folder": folder,
        "results": results,
        "result_count": len(results),
        "exported_count": exported_count,
        "skipped_count": skipped_count,
        "next_cursor": bounded_cursor + len(page_rows) if has_more else None,
        "raw_identifier_returned": False,
        "warnings": warnings,
    }


def _bulk_content_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    payload = _content_privacy(content_inspected=content_inspected)
    payload["bulk_content_returned"] = content_inspected
    return payload


def _parse_modified_after_to_apple_seconds(value: str) -> float | None:
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (parsed - APPLE_EPOCH).total_seconds()


def _select_note_rows_for_export(
    connection,
    *,
    folder_id: int,
    modified_after_apple: float,
    limit: int,
    offset: int,
):
    # limit+1 detects whether another page exists without a COUNT scan; ASC ordering keeps
    # offset pagination stable for a backfill session (edits during pagination may shift a
    # note later — downstream sync dedups by content_sha256, so drift is tolerable).
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
        WHERE ZNOTEDATA IS NOT NULL
          AND ZFOLDER = ?
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
          AND COALESCE(ZMODIFICATIONDATE1, ZCREATIONDATE1, 0) > ?
        ORDER BY COALESCE(ZMODIFICATIONDATE1, ZCREATIONDATE1, 0) ASC, Z_PK ASC
        LIMIT ? OFFSET ?
        """,
        (folder_id, modified_after_apple, limit + 1, offset),
    ).fetchall()


def list_notes_attachments(
    handle: str,
    *,
    db_path: Path = DEFAULT_NOTES_DB,
    notes_container: Path = DEFAULT_NOTES_CONTAINER,
    limit: int = DEFAULT_ATTACHMENTS_LIMIT,
) -> dict[str, Any]:
    if not is_int_handle(handle, "notes:note"):
        return _invalid_attachment_note_handle_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_attachment_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "results": [],
                    "result_count": 0,
                    "warnings": [],
                }
            rows = _select_note_attachment_rows(connection, note_id, limit=bounded_limit)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_notes_store_unavailable_warning()],
        }

    results = [
        _attachment_metadata(row, fingerprint, notes_container=notes_container)
        for row in rows
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "note_attachments", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def export_notes_attachment(
    handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    db_path: Path = DEFAULT_NOTES_DB,
    notes_container: Path = DEFAULT_NOTES_CONTAINER,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, ATTACHMENT_HANDLE_PREFIX):
        return _invalid_attachment_export_handle_result()

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_attachment_schema(connection)
            target = _resolve_attachment_target(connection, fingerprint, handle)
            if target is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "notes",
                    "schema_fingerprint": fingerprint,
                    "privacy": _export_privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = _select_attachment_row(connection, target[0], target[1])
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [_notes_store_unavailable_warning()],
        }

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "notes",
            "schema_fingerprint": fingerprint,
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    result = _attachment_metadata(row, fingerprint, notes_container=notes_container)
    result.update(
        {
            "attachment_content_returned": False,
            "attachment_content_exported": False,
            "exported_path": "",
            "exported_filename": "",
            "exported_bytes": 0,
        }
    )

    target_dir = output_dir.expanduser()
    if target_dir.exists() and not target_dir.is_dir():
        return _attachment_export_unavailable_result(
            result,
            fingerprint,
            "invalid_output_dir",
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_output_path(
            target_dir,
            _attachment_export_filename(filename, row),
        )
        exported_bytes = _copy_attachment_payload(row, target, notes_container=notes_container)
    except OSError:
        return _attachment_export_unavailable_result(
            result,
            fingerprint,
            "notes_attachment_export_failed",
        )

    if exported_bytes is None:
        return _attachment_export_unavailable_result(
            result,
            fingerprint,
            "notes_attachment_unavailable",
        )

    result.update(
        {
            "attachment_content_exported": True,
            "exported_path": str(target),
            "exported_filename": target.name,
            "exported_bytes": exported_bytes,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(content_exported=True),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def plan_notes_change(
    operation: str,
    *,
    title: str = "",
    handle: str = "",
    folder_handle: str = "",
    target_folder_handle: str = "",
    body_text: str = "",
    body_html: str = "",
    expected_current_sha256: str = "",
    db_path: Path = DEFAULT_NOTES_DB,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create, create_html, create_folder, rename_folder, delete_folder, move_folder, append_text, replace_text, replace_html, move_to_folder, or delete.",
            )
        )

    normalized_title = ""
    normalized_handle = handle.strip()
    normalized_folder_handle = folder_handle.strip()
    normalized_target_folder_handle = target_folder_handle.strip()
    normalized_expected_sha = ""
    folder_target: dict[str, Any] | None = None
    move_target: dict[str, Any] | None = None
    if normalized_target_folder_handle and normalized_operation != "move_folder":
        warnings.append(
            _warning(
                "unexpected_target_folder_handle",
                "target_folder_handle is only supported for Notes move-folder planning.",
            )
        )
    if normalized_operation in {
        "create",
        "create_html",
        "create_folder",
        "rename_folder",
        "delete_folder",
        "move_folder",
    }:
        normalized_title, title_warning = _normalize_create_title(title)
        if title_warning is not None and normalized_operation not in {"delete_folder", "move_folder"}:
            warnings.append(title_warning)
        if normalized_operation in {"create", "create_html"} and (
            normalized_handle or expected_current_sha256.strip()
        ):
            warnings.append(
                _warning(
                    "unexpected_append_target",
                    "Notes create planning requires a title, not a note handle or current-content hash.",
                )
            )
        if normalized_operation == "create_folder":
            if normalized_handle or expected_current_sha256.strip():
                warnings.append(
                    _warning(
                        "unexpected_folder_create_target",
                        "Notes create-folder planning requires a parent folder handle and title, not a note handle or current-content hash.",
                    )
                )
            if body_text.strip():
                warnings.append(
                    _warning(
                        "unexpected_body",
                        "Notes create-folder planning requires a folder title, not note body text.",
                    )
                )
            if not is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_folder_handle",
                        "Expected notes:folder:v1 opaque parent folder handle from Notes folder search output.",
                    )
                )
            else:
                folder_target, folder_warning = _resolve_folder_plan_target(
                    normalized_folder_handle,
                    db_path=db_path,
                    operation_label="folder creation",
                )
                if folder_warning is not None:
                    warnings.append(folder_warning)
        elif normalized_operation == "rename_folder":
            if normalized_handle:
                warnings.append(
                    _warning(
                        "unexpected_folder_rename_target",
                        "Notes rename-folder planning requires a folder handle and title, not a note handle.",
                    )
                )
            if body_text.strip():
                warnings.append(
                    _warning(
                        "unexpected_body",
                        "Notes rename-folder planning requires a folder title, not note body text.",
                    )
                )
            if not is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_folder_handle",
                        "Expected notes:folder:v1 opaque folder handle from Notes folder search output.",
                    )
                )
            else:
                folder_target, folder_warning = _resolve_folder_plan_target(
                    normalized_folder_handle,
                    db_path=db_path,
                    operation_label="folder rename",
                )
                if folder_warning is not None:
                    warnings.append(folder_warning)
            if expected_current_sha256.strip():
                normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
                if sha_warning is not None:
                    warnings.append(sha_warning)
        elif normalized_operation == "delete_folder":
            normalized_title = ""
            if normalized_handle:
                warnings.append(
                    _warning(
                        "unexpected_folder_delete_target",
                        "Notes delete-folder planning requires a folder handle, not a note handle.",
                    )
                )
            if title.strip():
                warnings.append(
                    _warning(
                        "unexpected_title",
                        "Notes delete-folder planning requires a folder handle and expected folder-title hash, not a new title.",
                    )
                )
            if body_text.strip():
                warnings.append(
                    _warning(
                        "unexpected_body",
                        "Notes delete-folder planning requires a folder handle and expected folder-title hash, not note body text.",
                    )
                )
            if not is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_folder_handle",
                        "Expected notes:folder:v1 opaque folder handle from Notes folder search output.",
                    )
                )
            else:
                folder_target, folder_warning = _resolve_folder_delete_plan_target(
                    normalized_folder_handle,
                    db_path=db_path,
                )
                if folder_warning is not None:
                    warnings.append(folder_warning)
            if expected_current_sha256.strip():
                normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
                if sha_warning is not None:
                    warnings.append(sha_warning)
        elif normalized_operation == "move_folder":
            normalized_title = ""
            if normalized_handle:
                warnings.append(
                    _warning(
                        "unexpected_folder_move_target",
                        "Notes move-folder planning requires source and destination folder handles, not a note handle.",
                    )
                )
            if title.strip():
                warnings.append(
                    _warning(
                        "unexpected_title",
                        "Notes move-folder planning requires exact folder handles, not a new title.",
                    )
                )
            if body_text.strip():
                warnings.append(
                    _warning(
                        "unexpected_body",
                        "Notes move-folder planning requires exact folder handles and expected folder-title hash, not note body text.",
                    )
                )
            if not is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_folder_handle",
                        "Expected notes:folder:v1 opaque source folder handle from Notes folder search output.",
                    )
                )
            if not is_opaque_handle(normalized_target_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_target_folder_handle",
                        "Expected notes:folder:v1 opaque destination folder handle from Notes folder search output.",
                    )
                )
            if (
                is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX)
                and is_opaque_handle(normalized_target_folder_handle, FOLDER_HANDLE_PREFIX)
            ):
                folder_target, folder_warning = _resolve_folder_move_plan_target(
                    normalized_folder_handle,
                    normalized_target_folder_handle,
                    db_path=db_path,
                )
                if folder_warning is not None:
                    warnings.append(folder_warning)
            normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
            if sha_warning is not None:
                warnings.append(sha_warning)
        elif normalized_folder_handle:
            folder_target, folder_warning = _resolve_folder_plan_target(
                normalized_folder_handle,
                db_path=db_path,
            )
            if folder_warning is not None:
                warnings.append(folder_warning)
    elif normalized_operation in {"append_text", "replace_text", "replace_html", "move_to_folder", "delete"}:
        label = normalized_operation.replace("_", "-")
        if title.strip():
            warnings.append(
                _warning(
                    "unexpected_title",
                    f"Notes {label} planning requires a note handle, not a new title.",
                )
            )
        if normalized_operation == "move_to_folder":
            if not is_opaque_handle(normalized_folder_handle, FOLDER_HANDLE_PREFIX):
                warnings.append(
                    _warning(
                        "invalid_folder_handle",
                        "Expected notes:folder:v1 opaque handle from Notes folder search output.",
                    )
                )
        elif normalized_folder_handle:
            warnings.append(
                _warning(
                    "unexpected_folder_target",
                    f"Notes {label} planning targets an exact note handle, not a folder handle.",
                )
            )
        if normalized_operation in {"move_to_folder", "delete"} and body_text.strip():
            warnings.append(
                _warning(
                    "unexpected_body",
                    f"Notes {label} planning requires a note handle and expected current hash, not replacement body text.",
                )
            )
        if not is_int_handle(normalized_handle, "notes:note"):
            warnings.append(
                _warning(
                    "invalid_handle",
                    "Expected notes:note:v2 opaque handle from search output.",
                )
            )
        normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
        if sha_warning is not None:
            warnings.append(sha_warning)

    normalized_body_html = ""
    if normalized_operation in {"create_html", "replace_html"}:
        if body_text.strip():
            warnings.append(
                _warning(
                    "unexpected_body_text",
                    "Notes rich-text create/replace planning requires body_html, not plain body_text.",
                )
            )
        normalized_body_html, body_warning = _normalize_body_html(
            body_html, operation=normalized_operation
        )
        # Bind and preview against the extracted visible text because Notes.app
        # normalizes stored HTML, so HTML never round-trips exactly.
        normalized_body = _html_to_text(normalized_body_html) if normalized_body_html else ""
    elif normalized_operation in {
        "create_folder",
        "rename_folder",
        "delete_folder",
        "move_folder",
        "move_to_folder",
        "delete",
    }:
        normalized_body = ""
        body_warning = None
        if body_html.strip():
            warnings.append(
                _warning(
                    "unexpected_body_html",
                    "Notes body_html is only supported for rich-text create/replace planning.",
                )
            )
    else:
        if body_html.strip():
            warnings.append(
                _warning(
                    "unexpected_body_html",
                    "Notes body_html is only supported for rich-text create/replace planning.",
                )
            )
        normalized_body, body_warning = (
            _normalize_update_body(body_text, operation=normalized_operation)
            if normalized_operation in {"append_text", "replace_text"}
            else _normalize_create_body(body_text)
        )
    if body_warning is not None:
        warnings.append(body_warning)

    if warnings:
        return _plan_error(warnings)
    if normalized_operation == "rename_folder":
        assert folder_target is not None
        current_title = str(folder_target["folder_title"])
        current_title_sha = _notes_folder_title_sha256(current_title)
        if not normalized_expected_sha:
            if current_title == normalized_title:
                return _plan_error(
                    [_warning("already_named", "Notes folder already has the requested title.")]
                )
            normalized_expected_sha = current_title_sha
        elif current_title_sha != normalized_expected_sha and current_title != normalized_title:
            return _plan_error(
                [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")]
            )
    if normalized_operation == "delete_folder":
        assert folder_target is not None
        current_title = str(folder_target["folder_title"])
        current_title_sha = _notes_folder_title_sha256(current_title)
        if not normalized_expected_sha:
            normalized_expected_sha = current_title_sha
        elif current_title_sha != normalized_expected_sha:
            return _plan_error(
                [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")]
            )
    if normalized_operation == "move_folder":
        assert folder_target is not None
        current_title = str(folder_target["folder_title"])
        current_title_sha = _notes_folder_title_sha256(current_title)
        if current_title_sha != normalized_expected_sha:
            return _plan_error(
                [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")]
            )
    if normalized_operation == "move_to_folder":
        move_target, move_warning = _resolve_move_plan_target(
            normalized_handle,
            normalized_folder_handle,
            db_path=db_path,
        )
        if move_warning is not None:
            return _plan_error([move_warning])
        assert move_target is not None

    body_hash = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    body_preview, body_preview_truncated, _, _ = _bounded_text(
        normalized_body,
        MAX_BODY_PREVIEW_CHARS,
    )
    body_html_hash = (
        hashlib.sha256(normalized_body_html.encode("utf-8")).hexdigest()
        if normalized_body_html
        else ""
    )
    if normalized_operation == "create":
        target = folder_target or {"account": "default", "folder": "default"}
        proposed = {
            "kind": "note",
            "format": "plaintext",
            "title": normalized_title,
            "body_chars": len(normalized_body),
            "body_preview_text": body_preview,
            "body_preview_chars": len(body_preview),
            "body_preview_truncated": body_preview_truncated,
        }
    elif normalized_operation == "create_html":
        target = folder_target or {"account": "default", "folder": "default"}
        proposed = {
            "kind": "note",
            "format": "rich_text_create",
            "title": normalized_title,
            "body_html_chars": len(normalized_body_html),
            "body_html_sanitized": True,
            "body_text_chars": len(normalized_body),
            "body_preview_text": body_preview,
            "body_preview_chars": len(body_preview),
            "body_preview_truncated": body_preview_truncated,
            "read_back": "extracted_text_match",
            "attachment_mutation": "blocked",
        }
    elif normalized_operation == "create_folder":
        assert folder_target is not None
        target = {
            "parent_folder_handle": folder_target["folder_handle"],
            "parent_folder_title": folder_target["folder_title"],
            "parent_folder_kind": folder_target["folder_kind"],
        }
        proposed = {
            "kind": "folder",
            "format": "folder_create",
            "title": normalized_title,
            "parent_folder_title": folder_target["folder_title"],
            "folder_content_returned": False,
            "note_content_returned": False,
            "rename": "blocked",
            "delete": "blocked",
            "bulk": "blocked",
        }
    elif normalized_operation == "rename_folder":
        assert folder_target is not None
        target = {
            "folder_handle": folder_target["folder_handle"],
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "folder",
            "format": "folder_rename",
            "title": normalized_title,
            "folder_content_returned": False,
            "note_content_returned": False,
            "delete": "blocked",
            "move": "blocked",
            "bulk": "blocked",
        }
    elif normalized_operation == "delete_folder":
        assert folder_target is not None
        target = {
            "folder_handle": folder_target["folder_handle"],
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "folder",
            "format": "folder_delete",
            "folder_title": folder_target["folder_title"],
            "delete": "approved_exact_empty_child_folder",
            "empty_folder_required": True,
            "recursive_delete": "blocked",
            "note_delete": "blocked",
            "folder_content_returned": False,
            "note_content_returned": False,
            "bulk": "blocked",
        }
    elif normalized_operation == "move_folder":
        assert folder_target is not None
        target = {
            "folder_handle": folder_target["folder_handle"],
            "target_folder_handle": folder_target["target_folder_handle"],
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "folder",
            "format": "folder_move",
            "folder_title": folder_target["folder_title"],
            "target_folder_title": folder_target["target_folder_title"],
            "move": "approved_exact_empty_child_folder",
            "same_account_required": True,
            "empty_folder_required": True,
            "recursive_move": "blocked",
            "note_move": "blocked",
            "folder_content_returned": False,
            "note_content_returned": False,
            "bulk": "blocked",
        }
    elif normalized_operation == "append_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "note",
            "format": "plaintext_append",
            "append_chars": len(normalized_body),
            "append_preview_text": body_preview,
            "append_preview_chars": len(body_preview),
            "append_preview_truncated": body_preview_truncated,
            "overwrite": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "replace_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "note",
            "format": "plaintext_replace",
            "replacement_chars": len(normalized_body),
            "replacement_preview_text": body_preview,
            "replacement_preview_chars": len(body_preview),
            "replacement_preview_truncated": body_preview_truncated,
            "rich_text": "blocked",
            "attachment_mutation": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "replace_html":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "note",
            "format": "rich_text_replace",
            "replacement_html_chars": len(normalized_body_html),
            "replacement_html_sanitized": True,
            "replacement_text_chars": len(normalized_body),
            "replacement_preview_text": body_preview,
            "replacement_preview_chars": len(body_preview),
            "replacement_preview_truncated": body_preview_truncated,
            "read_back": "extracted_text_match",
            "attachment_mutation": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "move_to_folder":
        assert move_target is not None
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "source_folder_handle": move_target["source_folder_handle"],
            "target_folder_handle": move_target["target_folder_handle"],
        }
        proposed = {
            "kind": "note",
            "format": "note_move",
            "move": "approved_exact_folder",
            "source_folder_title": move_target["source_folder_title"],
            "target_folder_title": move_target["target_folder_title"],
            "same_account_required": True,
            "read_back": "folder_required",
            "body_returned": False,
            "rich_text": "blocked",
            "attachment_mutation": "blocked",
            "bulk": "blocked",
        }
    else:
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "note",
            "format": "note_delete",
            "delete": "approved_exact_handle",
            "read_back": "absence_required",
            "body_returned": False,
            "rich_text": "blocked",
            "attachment_mutation": "blocked",
            "bulk": "blocked",
        }
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": _fingerprint_proposed(
            normalized_operation, proposed, body_hash, body_html_hash=body_html_hash
        ),
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
        "source": "notes",
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


def apply_notes_change(
    operation: str,
    *,
    title: str = "",
    handle: str = "",
    folder_handle: str = "",
    target_folder_handle: str = "",
    body_text: str = "",
    body_html: str = "",
    expected_current_sha256: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path = DEFAULT_NOTES_DB,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_notes_change(
        operation,
        title=title,
        handle=handle,
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        body_text=body_text,
        body_html=body_html,
        expected_current_sha256=expected_current_sha256,
        db_path=db_path,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Notes apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Notes apply approval token did not match the plan.")],
            plan=plan,
        )

    runner = script_runner or _run_osascript
    normalized_operation = str(preview["operation"])

    if normalized_operation == "create_folder":
        return _apply_notes_create_folder(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "rename_folder":
        return _apply_notes_rename_folder(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "delete_folder":
        return _apply_notes_delete_folder(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "move_folder":
        return _apply_notes_move_folder(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "append_text":
        return _apply_notes_append(
            preview,
            db_path=db_path,
            script_runner=runner,
            body_text=body_text,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "replace_text":
        return _apply_notes_replace(
            preview,
            db_path=db_path,
            script_runner=runner,
            body_text=body_text,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "create_html":
        return _apply_notes_create_html(
            preview,
            db_path=db_path,
            script_runner=runner,
            body_html=body_html,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "replace_html":
        return _apply_notes_replace_html(
            preview,
            db_path=db_path,
            script_runner=runner,
            body_html=body_html,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "move_to_folder":
        return _apply_notes_move_to_folder(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )
    if normalized_operation == "delete":
        return _apply_notes_delete(
            preview,
            db_path=db_path,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )

    normalized_title, _ = _normalize_create_title(title)
    normalized_body, _ = _normalize_create_body(body_text)
    folder_id: int | None = None
    folder_reference: str | None = None
    target = preview.get("target") if isinstance(preview, dict) else None
    if isinstance(target, dict) and "folder_handle" in target:
        folder_resolution, folder_warning = _resolve_folder_apply_target(
            str(target.get("folder_handle", "")),
            db_path=db_path,
        )
        if folder_warning is not None:
            return _apply_error([folder_warning], plan=plan)
        folder_id = folder_resolution["folder_id"]
        folder_reference = folder_resolution["folder_reference"]

    already_applied = _find_matching_note_content(
        normalized_title,
        normalized_body,
        db_path=db_path,
        script_runner=runner,
        folder_id=folder_id,
    )
    if already_applied is not None:
        return _apply_success(
            already_applied,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Matching Notes note already exists.")],
        )

    try:
        created_id = runner(
            _notes_create_script(
                normalized_title,
                normalized_body,
                folder_reference=folder_reference,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes create timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes note could not be created safely.")],
            plan=plan,
        )

    read_back = _read_back_created_note(
        created_id,
        normalized_title,
        normalized_body,
        db_path=db_path,
        script_runner=runner,
        folder_id=folder_id,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes create succeeded but read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
    )


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


def _note_id_for_handle(db_path: Path, handle: str) -> int | None:
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            return _resolve_notes_handle_note_id(connection, handle)
    except StoreUnavailableError:
        return None


def _note_folder_matches(db_path: Path, note_id: int, folder_id: int) -> bool:
    try:
        with connect_readonly(db_path) as connection:
            _check_folder_schema(connection)
            row = connection.execute(
                """
                SELECT ZFOLDER AS folder_id
                FROM ZICCLOUDSYNCINGOBJECT
                WHERE Z_PK = ?
                  AND ZNOTEDATA IS NOT NULL
                  AND COALESCE(ZMARKEDFORDELETION, 0) = 0
                  AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
                LIMIT 1
                """,
                (note_id,),
            ).fetchone()
    except StoreUnavailableError:
        return False
    return row is not None and int(row["folder_id"] or 0) == folder_id


def _select_folder_rows(connection, *, query: str | None = None, limit: int | None = None):
    filters = [
        "f.Z_ENT = ?",
        "COALESCE(f.ZMARKEDFORDELETION, 0) = 0",
        "COALESCE(f.ZTITLE2, '') != ''",
    ]
    params: list[Any] = [FOLDER_ENTITY_ID]
    if query is not None:
        filters.append("f.ZTITLE2 LIKE ? ESCAPE '\\'")
        params.append(query)
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ?"
        params.append(limit)
    return connection.execute(
        f"""
        SELECT
            f.Z_PK AS folder_id,
            f.ZTITLE2 AS title,
            f.ZACCOUNT8 AS account_id,
            f.ZPARENT AS parent_id,
            f.ZFOLDERTYPE AS folder_type,
            f.ZFOLDERMODIFICATIONDATE AS modification_date,
            f.ZSMARTFOLDERQUERYJSON AS smart_query_json,
            COUNT(n.Z_PK) AS visible_note_count
        FROM ZICCLOUDSYNCINGOBJECT AS f
        LEFT JOIN ZICCLOUDSYNCINGOBJECT AS n
          ON n.ZFOLDER = f.Z_PK
         AND n.ZNOTEDATA IS NOT NULL
         AND COALESCE(n.ZMARKEDFORDELETION, 0) = 0
         AND COALESCE(n.ZISPASSWORDPROTECTED, 0) = 0
        WHERE {' AND '.join(filters)}
        GROUP BY f.Z_PK
        ORDER BY COALESCE(f.ZFOLDERMODIFICATIONDATE, 0) DESC, f.ZTITLE2 ASC
        {limit_sql}
        """,
        tuple(params),
    ).fetchall()


def _select_child_folder_rows(connection, *, parent_folder_id: int, limit: int):
    return connection.execute(
        """
        SELECT
            f.Z_PK AS folder_id,
            f.ZTITLE2 AS title,
            f.ZACCOUNT8 AS account_id,
            f.ZPARENT AS parent_id,
            f.ZFOLDERTYPE AS folder_type,
            f.ZFOLDERMODIFICATIONDATE AS modification_date,
            f.ZSMARTFOLDERQUERYJSON AS smart_query_json,
            COUNT(n.Z_PK) AS visible_note_count
        FROM ZICCLOUDSYNCINGOBJECT AS f
        LEFT JOIN ZICCLOUDSYNCINGOBJECT AS n
          ON n.ZFOLDER = f.Z_PK
         AND n.ZNOTEDATA IS NOT NULL
         AND COALESCE(n.ZMARKEDFORDELETION, 0) = 0
         AND COALESCE(n.ZISPASSWORDPROTECTED, 0) = 0
        WHERE f.Z_ENT = ?
          AND f.ZPARENT = ?
          AND COALESCE(f.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(f.ZTITLE2, '') != ''
        GROUP BY f.Z_PK
        ORDER BY COALESCE(f.ZFOLDERMODIFICATIONDATE, 0) DESC, f.ZTITLE2 ASC
        LIMIT ?
        """,
        (FOLDER_ENTITY_ID, parent_folder_id, limit),
    ).fetchall()


def _select_note_rows_for_folder(connection, *, folder_id: int, limit: int):
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
        WHERE ZNOTEDATA IS NOT NULL
          AND ZFOLDER = ?
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(ZISPASSWORDPROTECTED, 0) = 0
        ORDER BY COALESCE(ZMODIFICATIONDATE1, ZCREATIONDATE1, 0) DESC
        LIMIT ?
        """,
        (folder_id, limit),
    ).fetchall()


def _notes_folder_tree_nodes(
    connection,
    *,
    fingerprint: str,
    parent_folder_id: int,
    root_handle: str,
    max_depth: int,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    queue: list[tuple[int, int, str]] = [(parent_folder_id, 0, root_handle)]
    seen = {parent_folder_id}
    truncated = False
    cycle_detected = False

    while queue and len(results) < limit:
        folder_id, current_depth, parent_handle = queue.pop(0)
        if current_depth >= max_depth:
            continue
        remaining = limit - len(results)
        child_rows = _select_child_folder_rows(
            connection,
            parent_folder_id=folder_id,
            limit=remaining + 1,
        )
        if len(child_rows) > remaining:
            truncated = True
        for child in child_rows[:remaining]:
            child_id = int(child["folder_id"])
            if child_id in seen:
                cycle_detected = True
                continue
            seen.add(child_id)
            metadata = _folder_metadata(child, fingerprint)
            metadata["parent_handle"] = parent_handle
            metadata["tree_depth"] = current_depth + 1
            results.append(metadata)
            if len(results) >= limit:
                truncated = True
                break
            if current_depth + 1 < max_depth and not _folder_is_smart(child):
                queue.append((child_id, current_depth + 1, str(metadata["handle"])))

    if queue:
        truncated = True
    if truncated:
        warnings.append(
            _warning(
                "result_truncated",
                "Notes folder tree was truncated to the requested limit.",
            )
        )
    if cycle_detected:
        warnings.append(
            _warning(
                "folder_cycle_detected",
                "Notes folder tree stopped at a repeated folder.",
            )
        )
    return results, warnings


def _resolve_notes_folder_handle(connection, fingerprint: str, handle: str):
    rows = _select_folder_rows(connection)
    for row in rows:
        folder_id = int(row["folder_id"])
        account_id = int(row["account_id"] or 0)
        if opaque_handle_matches(
            handle,
            FOLDER_HANDLE_PREFIX,
            fingerprint,
            folder_id,
            account_id,
        ):
            return row
    return None


def _folder_metadata(row, fingerprint: str) -> dict[str, Any]:
    is_smart = _folder_is_smart(row)
    return {
        "handle": make_opaque_handle(
            FOLDER_HANDLE_PREFIX,
            fingerprint,
            int(row["folder_id"]),
            int(row["account_id"] or 0),
        ),
        "title": _bounded_string(row["title"], 300),
        "kind": "smart_folder" if is_smart else "folder",
        "supports_create": not is_smart,
        "visible_note_count": int(row["visible_note_count"] or 0),
        "parent_present": row["parent_id"] is not None,
        "modification_date": row["modification_date"],
        "folder_content_returned": False,
        "raw_identifier_returned": False,
    }


def _folder_plan_target(row, fingerprint: str) -> dict[str, Any]:
    return {
        "folder_handle": _folder_handle_from_row(row, fingerprint),
        "folder_title": _bounded_string(row["title"], 300),
        "folder_kind": "folder",
    }


def _folder_handle_from_row(row, fingerprint: str) -> str:
    return make_opaque_handle(
        FOLDER_HANDLE_PREFIX,
        fingerprint,
        int(row["folder_id"]),
        int(row["account_id"] or 0),
    )


def _folder_is_smart(row) -> bool:
    return bool(_bounded_string(row["smart_query_json"], 100).strip())


def _notes_folder_title_sha256(title: str) -> str:
    return hashlib.sha256(_normalize_text(title).encode("utf-8")).hexdigest()


def _select_note_folder_row(connection, note_id: int):
    return connection.execute(
        """
        SELECT
            n.Z_PK AS note_id,
            n.ZFOLDER AS folder_id,
            f.ZTITLE2 AS folder_title,
            f.ZACCOUNT8 AS account_id,
            f.ZSMARTFOLDERQUERYJSON AS smart_query_json
        FROM ZICCLOUDSYNCINGOBJECT AS n
        LEFT JOIN ZICCLOUDSYNCINGOBJECT AS f
          ON f.Z_PK = n.ZFOLDER
         AND f.Z_ENT = ?
         AND COALESCE(f.ZMARKEDFORDELETION, 0) = 0
        WHERE n.Z_PK = ?
          AND n.ZNOTEDATA IS NOT NULL
          AND COALESCE(n.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(n.ZISPASSWORDPROTECTED, 0) = 0
        LIMIT 1
        """,
        (FOLDER_ENTITY_ID, note_id),
    ).fetchone()


def _select_folder_by_id(connection, folder_id: int):
    return connection.execute(
        """
        SELECT
            f.Z_PK AS folder_id,
            f.ZTITLE2 AS title,
            f.ZACCOUNT8 AS account_id,
            f.ZPARENT AS parent_id,
            f.ZFOLDERTYPE AS folder_type,
            f.ZFOLDERMODIFICATIONDATE AS modification_date,
            f.ZSMARTFOLDERQUERYJSON AS smart_query_json,
            COUNT(n.Z_PK) AS visible_note_count
        FROM ZICCLOUDSYNCINGOBJECT AS f
        LEFT JOIN ZICCLOUDSYNCINGOBJECT AS n
          ON n.ZFOLDER = f.Z_PK
         AND n.ZNOTEDATA IS NOT NULL
         AND COALESCE(n.ZMARKEDFORDELETION, 0) = 0
         AND COALESCE(n.ZISPASSWORDPROTECTED, 0) = 0
        WHERE f.Z_PK = ?
          AND f.Z_ENT = ?
          AND COALESCE(f.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(f.ZTITLE2, '') != ''
        GROUP BY f.Z_PK
        LIMIT 1
        """,
        (folder_id, FOLDER_ENTITY_ID),
    ).fetchone()


def _select_folder_occupancy(connection, folder_id: int) -> dict[str, int]:
    note_row = connection.execute(
        """
        SELECT COUNT(*) AS non_deleted_note_count
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZFOLDER = ?
          AND ZNOTEDATA IS NOT NULL
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
        """,
        (folder_id,),
    ).fetchone()
    folder_row = connection.execute(
        """
        SELECT COUNT(*) AS child_folder_count
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZPARENT = ?
          AND Z_ENT = ?
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(ZTITLE2, '') != ''
        """,
        (folder_id, FOLDER_ENTITY_ID),
    ).fetchone()
    return {
        "non_deleted_note_count": int(note_row["non_deleted_note_count"] if note_row else 0),
        "child_folder_count": int(folder_row["child_folder_count"] if folder_row else 0),
    }


def _select_child_folder_row(
    connection,
    *,
    title: str,
    parent_folder_id: int,
    parent_account_id: int,
):
    return connection.execute(
        """
        SELECT
            f.Z_PK AS folder_id,
            f.ZTITLE2 AS title,
            f.ZACCOUNT8 AS account_id,
            f.ZPARENT AS parent_id,
            f.ZFOLDERTYPE AS folder_type,
            f.ZFOLDERMODIFICATIONDATE AS modification_date,
            f.ZSMARTFOLDERQUERYJSON AS smart_query_json,
            COUNT(n.Z_PK) AS visible_note_count
        FROM ZICCLOUDSYNCINGOBJECT AS f
        LEFT JOIN ZICCLOUDSYNCINGOBJECT AS n
          ON n.ZFOLDER = f.Z_PK
         AND n.ZNOTEDATA IS NOT NULL
         AND COALESCE(n.ZMARKEDFORDELETION, 0) = 0
         AND COALESCE(n.ZISPASSWORDPROTECTED, 0) = 0
        WHERE f.Z_ENT = ?
          AND f.ZTITLE2 = ?
          AND f.ZPARENT = ?
          AND COALESCE(f.ZACCOUNT8, 0) = ?
          AND COALESCE(f.ZMARKEDFORDELETION, 0) = 0
          AND COALESCE(f.ZTITLE2, '') != ''
          AND COALESCE(f.ZSMARTFOLDERQUERYJSON, '') = ''
        GROUP BY f.Z_PK
        ORDER BY COALESCE(f.ZFOLDERMODIFICATIONDATE, 0) DESC, f.Z_PK DESC
        LIMIT 1
        """,
        (FOLDER_ENTITY_ID, title, parent_folder_id, parent_account_id),
    ).fetchone()


def _select_note_attachment_rows(connection, note_id: int, *, limit: int):
    return connection.execute(
        """
        SELECT
            Z_PK AS attachment_id,
            COALESCE(ZFILENAME, ZTITLE) AS filename,
            ZFILESIZE AS file_size,
            ZTYPEUTI AS type_uti,
            ZNOTE AS note_id,
            ZCREATIONDATE AS creation_date,
            ZMODIFICATIONDATE AS modification_date,
            ZIDENTIFIER AS uuid,
            ZREMOTEFILEURLSTRING AS remote_url,
            ZMERGEABLEDATA1 AS mergeable_data1,
            ZMERGEABLEDATA AS mergeable_data,
            ZMERGEABLEDATA2 AS mergeable_data2
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZNOTE = ?
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND (
            ZFILENAME IS NOT NULL
            OR ZTITLE IS NOT NULL
            OR COALESCE(ZFILESIZE, 0) > 0
            OR COALESCE(ZTYPEUTI, '') != ''
          )
          AND ZTITLE1 IS NULL
          AND COALESCE(ZTYPEUTI, '') != ''
        ORDER BY COALESCE(ZMODIFICATIONDATE, ZCREATIONDATE, 0) DESC, Z_PK DESC
        LIMIT ?
        """,
        (note_id, limit),
    ).fetchall()


def _select_attachment_row(connection, note_id: int, attachment_id: int):
    return connection.execute(
        """
        SELECT
            Z_PK AS attachment_id,
            COALESCE(ZFILENAME, ZTITLE) AS filename,
            ZFILESIZE AS file_size,
            ZTYPEUTI AS type_uti,
            ZNOTE AS note_id,
            ZCREATIONDATE AS creation_date,
            ZMODIFICATIONDATE AS modification_date,
            ZIDENTIFIER AS uuid,
            ZREMOTEFILEURLSTRING AS remote_url,
            ZMERGEABLEDATA1 AS mergeable_data1,
            ZMERGEABLEDATA AS mergeable_data,
            ZMERGEABLEDATA2 AS mergeable_data2
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE Z_PK = ?
          AND ZNOTE = ?
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND (
            ZFILENAME IS NOT NULL
            OR ZTITLE IS NOT NULL
            OR COALESCE(ZFILESIZE, 0) > 0
            OR COALESCE(ZTYPEUTI, '') != ''
          )
          AND ZTITLE1 IS NULL
          AND COALESCE(ZTYPEUTI, '') != ''
        LIMIT 1
        """,
        (attachment_id, note_id),
    ).fetchone()


def _resolve_attachment_target(connection, fingerprint: str, handle: str) -> tuple[int, int] | None:
    rows = connection.execute(
        """
        SELECT Z_PK AS attachment_id, ZNOTE AS note_id
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZNOTE IS NOT NULL
          AND COALESCE(ZMARKEDFORDELETION, 0) = 0
          AND (
            ZFILENAME IS NOT NULL
            OR ZTITLE IS NOT NULL
            OR COALESCE(ZFILESIZE, 0) > 0
            OR COALESCE(ZTYPEUTI, '') != ''
          )
          AND ZTITLE1 IS NULL
          AND COALESCE(ZTYPEUTI, '') != ''
        """
    ).fetchall()
    for row in rows:
        note_id = int(row["note_id"])
        attachment_id = int(row["attachment_id"])
        if opaque_handle_matches(
            handle,
            ATTACHMENT_HANDLE_PREFIX,
            fingerprint,
            note_id,
            attachment_id,
        ):
            if _select_notes_row(connection, note_id) is not None:
                return note_id, attachment_id
    return None


def _attachment_metadata(row, fingerprint: str, *, notes_container: Path) -> dict[str, Any]:
    attachment_id = int(row["attachment_id"])
    note_id = int(row["note_id"])
    media_path = _attachment_media_path(row, notes_container=notes_container)
    blob_available = _attachment_blob_bytes(row) is not None
    return {
        "handle": make_opaque_handle(
            ATTACHMENT_HANDLE_PREFIX,
            fingerprint,
            note_id,
            attachment_id,
        ),
        "note_handle": make_int_handle("notes:note", note_id),
        "filename": _bounded_string(row["filename"], 500),
        "file_size": _positive_int(row["file_size"]),
        "type_uti": _bounded_string(row["type_uti"], 300),
        "attachment_type": _attachment_type(row["type_uti"], row["filename"]),
        "creation_date": row["creation_date"],
        "modification_date": row["modification_date"],
        "media_status": "available"
        if media_path is not None and media_path.is_file()
        else "unavailable",
        "blob_status": "available" if blob_available else "unavailable",
        "remote_status": "remote_reference" if row["remote_url"] else "local_or_unknown",
        "attachment_content_returned": False,
        "attachment_content_exported": False,
    }


def _attachment_media_path(row, *, notes_container: Path) -> Path | None:
    accounts_path = notes_container.expanduser() / "Accounts"
    try:
        resolved_accounts = accounts_path.resolve(strict=False)
    except OSError:
        return None
    if not accounts_path.exists():
        return None

    account_folders = [item for item in accounts_path.iterdir() if item.is_dir()]
    uuid = _bounded_string(row["uuid"], 500).strip()
    if uuid:
        for account_folder in account_folders:
            media_dir = account_folder / "Media" / uuid
            candidate = _first_safe_media_file(media_dir, resolved_accounts)
            if candidate is not None:
                return candidate

    filename = Path(_bounded_string(row["filename"], 500)).name
    if filename:
        for account_folder in account_folders:
            media_base = account_folder / "Media"
            if not media_base.exists():
                continue
            for item in media_base.rglob(filename):
                if _is_safe_media_file(item, resolved_accounts):
                    return item
    return None


def _first_safe_media_file(media_dir: Path, resolved_accounts: Path) -> Path | None:
    if not media_dir.exists():
        return None
    for item in media_dir.rglob("*"):
        if item.name.startswith("."):
            continue
        if _is_safe_media_file(item, resolved_accounts):
            return item
    return None


def _is_safe_media_file(path: Path, resolved_accounts: Path) -> bool:
    try:
        if not path.is_file() or path.is_symlink():
            return False
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_accounts)
    except (OSError, ValueError):
        return False
    return True


def _attachment_blob_bytes(row) -> bytes | None:
    for column in ("mergeable_data1", "mergeable_data", "mergeable_data2"):
        value = row[column]
        if isinstance(value, bytes) and value:
            if len(value) >= 2 and value[:2] == b"\x1f\x8b":
                try:
                    import gzip

                    return gzip.decompress(value)
                except OSError:
                    return value
            return value
    return None


def _copy_attachment_payload(row, target: Path, *, notes_container: Path) -> int | None:
    source = _attachment_media_path(row, notes_container=notes_container)
    if source is not None and source.is_file():
        shutil.copy2(source, target)
        return target.stat().st_size

    data = _attachment_blob_bytes(row)
    if not data:
        return None
    target.write_bytes(data)
    return len(data)


def _attachment_export_unavailable_result(
    result: dict[str, Any],
    fingerprint: str,
    warning_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "content_unavailable",
        "source": "notes",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(),
        "result": result,
        "warnings": [
            _warning(
                warning_code,
                "Notes attachment bytes are not locally available for export.",
            )
        ],
    }


def _invalid_attachment_note_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected notes:note:v2 opaque handle from search output.",
            )
        ],
    }


def _invalid_attachment_export_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected notes:attachment:v1 opaque handle from notes attachment list output.",
            )
        ],
    }


def _attachment_type(type_uti: Any, filename: Any) -> str:
    uti = _bounded_string(type_uti, 300).lower()
    suffix = Path(_bounded_string(filename, 300)).suffix.lower()
    if any(value in uti for value in ("jpeg", "png", "tiff", "heic", "gif")) or suffix in {
        ".gif",
        ".heic",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
    }:
        return "image"
    if any(value in uti for value in ("mp4", "mov", "quicktime", "video")) or suffix in {
        ".m4v",
        ".mov",
        ".mp4",
    }:
        return "video"
    if any(value in uti for value in ("mp3", "m4a", "wav", "aiff", "audio")) or suffix in {
        ".aif",
        ".aiff",
        ".m4a",
        ".mp3",
        ".wav",
    }:
        return "audio"
    if any(value in uti for value in ("pdf", "doc", "rtf", "txt", "pages")) or suffix in {
        ".doc",
        ".docx",
        ".pdf",
        ".rtf",
        ".txt",
    }:
        return "document"
    return "other"


def _attachment_export_filename(value: str | None, row) -> str:
    fallback = _bounded_string(row["filename"], 200).strip()
    if not fallback:
        fallback = f"attachment-{int(row['attachment_id'])}{_attachment_extension(row)}"
    candidate = _bounded_string(value, 200).strip() if value else fallback
    name = Path(candidate).name
    suffix = Path(name).suffix or Path(fallback).suffix or _attachment_extension(row)
    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    if not safe_stem:
        safe_stem = f"attachment-{int(row['attachment_id'])}"
    return f"{safe_stem[:120]}{suffix.lower()}"


def _attachment_extension(row) -> str:
    filename_suffix = Path(_bounded_string(row["filename"], 200)).suffix
    if filename_suffix:
        return filename_suffix.lower()
    uti = _bounded_string(row["type_uti"], 300)
    return {
        "com.adobe.pdf": ".pdf",
        "public.jpeg": ".jpg",
        "public.png": ".png",
        "public.tiff": ".tiff",
        "public.heic": ".heic",
        "public.mp4": ".mp4",
        "public.mov": ".mov",
        "public.m4a": ".m4a",
        "public.plain-text": ".txt",
        "public.rtf": ".rtf",
        "com.apple.notes.table": ".table",
        "com.apple.drawing.2": ".drawing",
    }.get(uti, "")


def _unique_output_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError("could not allocate unique export path")


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _row_to_content_metadata(row) -> dict[str, Any]:
    metadata = _row_to_metadata(row)
    metadata.update(
        {
            "content_format": "text",
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


def _invalid_content_format_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_content_format",
                "Notes content_format must be 'text' or 'html'.",
            )
        ],
    }


def _invalid_folder_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected notes:folder:v1 opaque handle from Notes folder search output.",
            )
        ],
    }


def _plan_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "notes",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": False,
        "preview": None,
        "warnings": warnings,
    }


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None = None,
    status: str = "error",
    mutation_applied: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "notes",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "plan": plan.get("preview") if isinstance(plan, dict) else None,
        "result": None,
        "warnings": warnings,
    }


def _apply_success(
    read_back: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    mutation_applied: bool,
    warnings: list[dict[str, str]],
    content_inspected: bool = True,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "privacy": _mutation_privacy(content_inspected=content_inspected),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _normalize_create_title(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = re.sub(r"\s+", " ", _normalize_text(value)).strip()
    if not normalized:
        return "", _warning("missing_title", "Notes create requires a non-empty title.")
    if not has_minimum_query_quality(normalized):
        return "", _warning("broad_title", "Notes create title requires at least two letters or digits.")
    if len(normalized) > MAX_PREVIEW_TITLE_CHARS:
        return (
            normalized[:MAX_PREVIEW_TITLE_CHARS],
            _warning("title_too_long", "Notes create title exceeded the maximum length."),
        )
    return normalized, None


def _normalize_create_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = _normalize_text(value)
    if len(normalized) > MAX_CREATE_BODY_CHARS:
        return (
            normalized[:MAX_CREATE_BODY_CHARS],
            _warning("body_too_long", "Notes create body exceeded the maximum length."),
        )
    return normalized, None


def _normalize_update_body(
    value: str,
    *,
    operation: str,
) -> tuple[str, dict[str, str] | None]:
    normalized = _normalize_text(value)
    if not normalized:
        label = "append-text" if operation == "append_text" else "replace-text"
        return "", _warning("missing_body", f"Notes {label} requires non-empty body text.")
    if len(normalized) > MAX_CREATE_BODY_CHARS:
        label = "append" if operation == "append_text" else "replace"
        return (
            normalized[:MAX_CREATE_BODY_CHARS],
            _warning("body_too_long", f"Notes {label} body exceeded the maximum length."),
        )
    return normalized, None


def _normalize_sha256(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: expected_current_sha256.")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        return "", _warning("invalid_expected_sha256", "expected_current_sha256 must be a 64-character SHA-256 hex digest.")
    return normalized, None


def _fingerprint_proposed(
    operation: str,
    proposed: dict[str, Any],
    body_hash: str,
    *,
    body_html_hash: str = "",
) -> dict[str, Any]:
    if operation == "create":
        return {
            **proposed,
            "body_sha256": body_hash,
        }
    if operation == "create_html":
        return {
            **proposed,
            "body_text_sha256": body_hash,
            "body_html_sha256": body_html_hash,
        }
    if operation == "create_folder":
        return proposed
    if operation == "rename_folder":
        return proposed
    if operation in {"delete_folder", "move_folder"}:
        return proposed
    if operation == "replace_text":
        return {
            **proposed,
            "replacement_body_sha256": body_hash,
        }
    if operation == "replace_html":
        return {
            **proposed,
            "replacement_text_sha256": body_hash,
            "replacement_html_sha256": body_html_hash,
        }
    if operation in {"move_to_folder", "delete"}:
        return proposed
    return {
        **proposed,
        "append_body_sha256": body_hash,
    }


def _resolve_folder_plan_target(
    folder_handle: str,
    *,
    db_path: Path,
    operation_label: str = "create",
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not is_opaque_handle(folder_handle, FOLDER_HANDLE_PREFIX):
        return None, _warning(
            "invalid_folder_handle",
            "Expected notes:folder:v1 opaque handle from Notes folder search output.",
        )
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
    except StoreUnavailableError:
        return None, _notes_store_unavailable_warning()
    if row is None:
        return None, _warning("target_folder_not_found", "Notes target folder was not found.")
    if _folder_is_smart(row):
        return None, _warning(
            "unsupported_smart_folder",
            f"Notes {operation_label} is blocked for smart folders.",
        )
    return _folder_plan_target(row, fingerprint), None


def _resolve_folder_delete_plan_target(
    folder_handle: str,
    *,
    db_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not is_opaque_handle(folder_handle, FOLDER_HANDLE_PREFIX):
        return None, _warning(
            "invalid_folder_handle",
            "Expected notes:folder:v1 opaque handle from Notes folder search output.",
        )
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
            occupancy = (
                _select_folder_occupancy(connection, int(row["folder_id"]))
                if row is not None
                else {"non_deleted_note_count": 0, "child_folder_count": 0}
            )
    except StoreUnavailableError:
        return None, _notes_store_unavailable_warning()
    if row is None:
        return None, _warning("target_folder_not_found", "Notes target folder was not found.")
    warning = _folder_delete_safety_warning(row, occupancy)
    if warning is not None:
        return None, warning
    return _folder_plan_target(row, fingerprint), None


def _resolve_folder_move_plan_target(
    folder_handle: str,
    target_folder_handle: str,
    *,
    db_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            source_row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
            target_row = _resolve_notes_folder_handle(connection, fingerprint, target_folder_handle)
            occupancy = (
                _select_folder_occupancy(connection, int(source_row["folder_id"]))
                if source_row is not None
                else {"non_deleted_note_count": 0, "child_folder_count": 0}
            )
    except StoreUnavailableError:
        return None, _notes_store_unavailable_warning()
    if source_row is None:
        return None, _warning("source_folder_not_found", "Notes source folder was not found.")
    if target_row is None:
        return None, _warning("target_folder_not_found", "Notes target folder was not found.")
    warning = _folder_move_safety_warning(source_row, occupancy)
    if warning is not None:
        return None, warning
    if _folder_is_smart(target_row):
        return None, _warning(
            "unsupported_smart_folder",
            "Notes folder move target is blocked for smart folders.",
        )
    source_account_id = int(source_row["account_id"] or 0)
    target_account_id = int(target_row["account_id"] or 0)
    if source_account_id != target_account_id:
        return None, _warning(
            "cross_account_move_blocked",
            "Notes folder move is limited to folders in the same account.",
        )
    source_folder_id = int(source_row["folder_id"])
    target_folder_id = int(target_row["folder_id"])
    if source_folder_id == target_folder_id or int(source_row["parent_id"] or 0) == target_folder_id:
        return None, _warning(
            "already_in_target_folder",
            "Notes source folder is already in the selected destination folder.",
        )
    return {
        "folder_handle": _folder_handle_from_row(source_row, fingerprint),
        "folder_title": _bounded_string(source_row["title"], 300),
        "folder_kind": "folder",
        "target_folder_handle": _folder_handle_from_row(target_row, fingerprint),
        "target_folder_title": _bounded_string(target_row["title"], 300),
    }, None


def _resolve_folder_apply_target(
    folder_handle: str,
    *,
    db_path: Path,
    operation_label: str = "create",
) -> tuple[dict[str, Any], dict[str, str] | None]:
    if not is_opaque_handle(folder_handle, FOLDER_HANDLE_PREFIX):
        return {}, _warning(
            "invalid_folder_handle",
            "Expected notes:folder:v1 opaque handle from Notes folder search output.",
        )
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
            store_uuid = _notes_store_uuid(connection)
            occupancy = (
                _select_folder_occupancy(connection, int(row["folder_id"]))
                if row is not None
                else {"non_deleted_note_count": 0, "child_folder_count": 0}
            )
    except StoreUnavailableError:
        return {}, _notes_store_unavailable_warning()
    if row is None:
        return {}, _warning("target_folder_not_found", "Notes target folder was not found.")
    if _folder_is_smart(row):
        return {}, _warning(
            "unsupported_smart_folder",
            f"Notes {operation_label} is blocked for smart folders.",
        )
    if not store_uuid:
        return {}, _warning(
            "content_unavailable",
            "Notes target folder could not be resolved from the local store mapping.",
        )
    folder_id = int(row["folder_id"])
    return {
        "folder_id": folder_id,
        "account_id": int(row["account_id"] or 0),
        "parent_id": row["parent_id"],
        "non_deleted_note_count": int(occupancy["non_deleted_note_count"]),
        "child_folder_count": int(occupancy["child_folder_count"]),
        "folder_title": _bounded_string(row["title"], MAX_PREVIEW_TITLE_CHARS),
        "folder_handle": _folder_handle_from_row(row, fingerprint),
        "folder_reference": f"x-coredata://{store_uuid}/ICFolder/p{folder_id}",
    }, None


def _apply_notes_create_folder(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    proposed = preview["proposed"]
    parent_folder_handle = str(target["parent_folder_handle"])
    title = _bounded_string(proposed.get("title"), MAX_PREVIEW_TITLE_CHARS)
    parent_resolution, parent_warning = _resolve_folder_apply_target(
        parent_folder_handle,
        db_path=db_path,
        operation_label="folder creation",
    )
    if parent_warning is not None:
        return _apply_error([parent_warning], plan={"preview": preview})
    parent_folder_id = int(parent_resolution["folder_id"])
    parent_account_id = int(parent_resolution["account_id"])
    parent_reference = str(parent_resolution["folder_reference"])

    already_applied = _find_matching_child_folder(
        title,
        parent_folder_id=parent_folder_id,
        parent_account_id=parent_account_id,
        parent_folder_handle=parent_folder_handle,
        db_path=db_path,
    )
    if already_applied is not None:
        return _apply_success(
            already_applied,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Matching Notes folder already exists.")],
            content_inspected=False,
        )

    try:
        created_id = script_runner(
            _notes_create_folder_script(title, parent_folder_reference=parent_reference),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes folder create timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes folder could not be created safely.")],
            plan={"preview": preview},
        )

    read_back = _read_back_created_folder(
        created_id,
        title,
        parent_folder_id=parent_folder_id,
        parent_account_id=parent_account_id,
        parent_folder_handle=parent_folder_handle,
        db_path=db_path,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes folder create succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if read_back.get("parent_folder_confirmed") is not True:
        return _apply_error(
            [_warning("read_back_mismatch", "Notes folder create read-back did not confirm the selected parent folder.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=False,
    )


def _apply_notes_rename_folder(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    proposed = preview["proposed"]
    folder_handle = str(target["folder_handle"])
    expected_sha = str(target["expected_current_sha256"])
    new_title = _bounded_string(proposed.get("title"), MAX_PREVIEW_TITLE_CHARS)
    folder_resolution, folder_warning = _resolve_folder_apply_target(
        folder_handle,
        db_path=db_path,
        operation_label="folder rename",
    )
    if folder_warning is not None:
        return _apply_error([folder_warning], plan={"preview": preview})

    folder_id = int(folder_resolution["folder_id"])
    current_title = str(folder_resolution["folder_title"])
    current_sha = _notes_folder_title_sha256(current_title)
    folder_reference = str(folder_resolution["folder_reference"])

    if current_title == new_title:
        read_back = _notes_folder_rename_read_back(
            folder_handle,
            folder_id=folder_id,
            new_title=new_title,
            db_path=db_path,
        )
        if read_back is None:
            return _apply_error(
                [_warning("read_back_unavailable", "Notes folder rename was already applied but read-back was unavailable.")],
                plan={"preview": preview},
                status="partial",
            )
        return _apply_success(
            read_back,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Notes folder already has the approved title.")],
            content_inspected=False,
        )

    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")],
            plan={"preview": preview},
        )

    try:
        output = script_runner(
            _notes_rename_folder_script(
                folder_reference,
                expected_title=current_title,
                new_title=new_title,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes folder rename timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes folder could not be renamed safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = _notes_folder_rename_read_back(
        folder_handle,
        folder_id=folder_id,
        new_title=new_title,
        db_path=db_path,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes folder rename succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if read_back.get("renamed") is not True:
        return _apply_error(
            [_warning("read_back_mismatch", "Notes folder rename read-back did not confirm the approved title.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=False,
    )


def _apply_notes_delete_folder(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    folder_handle = str(target["folder_handle"])
    expected_sha = str(target["expected_current_sha256"])
    folder_resolution, folder_warning = _resolve_folder_apply_target(
        folder_handle,
        db_path=db_path,
        operation_label="folder delete",
    )
    if folder_warning is not None:
        return _apply_error([folder_warning], plan={"preview": preview})

    current_title = str(folder_resolution["folder_title"])
    current_sha = _notes_folder_title_sha256(current_title)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")],
            plan={"preview": preview},
        )

    safety_warning = _folder_delete_safety_warning(
        {
            "parent_id": folder_resolution["parent_id"],
            "smart_query_json": "",
        },
        {
            "non_deleted_note_count": int(folder_resolution["non_deleted_note_count"]),
            "child_folder_count": int(folder_resolution["child_folder_count"]),
        },
    )
    if safety_warning is not None:
        return _apply_error([safety_warning], plan={"preview": preview})

    folder_id = int(folder_resolution["folder_id"])
    try:
        output = script_runner(
            _notes_delete_folder_script(
                str(folder_resolution["folder_reference"]),
                expected_title=current_title,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes folder delete timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes folder could not be deleted safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = _notes_folder_delete_read_back(
        folder_handle,
        folder_id=folder_id,
        db_path=db_path,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes folder delete succeeded but absence read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if read_back.get("verified_absent") is not True:
        return _apply_error(
            [_warning("read_back_mismatch", "Notes folder delete read-back still found the selected folder.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=False,
    )


def _apply_notes_move_folder(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    folder_handle = str(target["folder_handle"])
    target_folder_handle = str(target["target_folder_handle"])
    expected_sha = str(target["expected_current_sha256"])
    source_resolution, source_warning = _resolve_folder_apply_target(
        folder_handle,
        db_path=db_path,
        operation_label="folder move",
    )
    if source_warning is not None:
        return _apply_error([source_warning], plan={"preview": preview})
    target_resolution, target_warning = _resolve_folder_apply_target(
        target_folder_handle,
        db_path=db_path,
        operation_label="folder move target",
    )
    if target_warning is not None:
        return _apply_error([target_warning], plan={"preview": preview})

    current_title = str(source_resolution["folder_title"])
    current_sha = _notes_folder_title_sha256(current_title)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_folder_changed", "Notes folder title changed since the approved plan.")],
            plan={"preview": preview},
        )

    safety_warning = _folder_move_safety_warning(
        {
            "parent_id": source_resolution["parent_id"],
            "smart_query_json": "",
        },
        {
            "non_deleted_note_count": int(source_resolution["non_deleted_note_count"]),
            "child_folder_count": int(source_resolution["child_folder_count"]),
        },
    )
    if safety_warning is not None:
        return _apply_error([safety_warning], plan={"preview": preview})
    if int(source_resolution["account_id"]) != int(target_resolution["account_id"]):
        return _apply_error(
            [_warning("cross_account_move_blocked", "Notes folder move is limited to folders in the same account.")],
            plan={"preview": preview},
        )

    folder_id = int(source_resolution["folder_id"])
    target_folder_id = int(target_resolution["folder_id"])
    if folder_id == target_folder_id or int(source_resolution["parent_id"] or 0) == target_folder_id:
        return _apply_error(
            [_warning("already_in_target_folder", "Notes source folder is already in the selected destination folder.")],
            plan={"preview": preview},
        )

    try:
        output = script_runner(
            _notes_move_folder_script(
                str(source_resolution["folder_reference"]),
                str(target_resolution["folder_reference"]),
                expected_title=current_title,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes folder move timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes folder could not be moved safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = _notes_folder_move_read_back(
        folder_handle,
        folder_id=folder_id,
        target_folder_handle=target_folder_handle,
        target_folder_id=target_folder_id,
        db_path=db_path,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes folder move succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if read_back.get("target_folder_confirmed") is not True:
        return _apply_error(
            [_warning("read_back_mismatch", "Notes folder move read-back did not confirm the selected destination folder.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=False,
    )


def _resolve_move_plan_target(
    handle: str,
    folder_handle: str,
    *,
    db_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            source_row = _select_note_folder_row(connection, note_id) if note_id is not None else None
            target_row = _resolve_notes_folder_handle(connection, fingerprint, folder_handle)
    except StoreUnavailableError:
        return None, _notes_store_unavailable_warning()
    if note_id is None or source_row is None:
        return None, _warning("target_note_not_found", "Notes target note was not found.")
    if source_row["folder_id"] is None or source_row["account_id"] is None:
        return None, _warning("source_folder_unavailable", "Notes source folder could not be resolved.")
    if target_row is None:
        return None, _warning("target_folder_not_found", "Notes target folder was not found.")
    if _folder_is_smart(target_row):
        return None, _warning("unsupported_smart_folder", "Notes move is blocked for smart folders.")
    source_account_id = int(source_row["account_id"] or 0)
    target_account_id = int(target_row["account_id"] or 0)
    if source_account_id != target_account_id:
        return None, _warning("cross_account_move_blocked", "Notes move is limited to folders in the same account.")
    source_folder_id = int(source_row["folder_id"] or 0)
    target_folder_id = int(target_row["folder_id"])
    if source_folder_id == target_folder_id:
        return None, _warning("already_in_target_folder", "Notes target note is already in the selected folder.")
    return {
        "source_folder_handle": _folder_handle_from_row(source_row, fingerprint),
        "source_folder_title": _bounded_string(source_row["folder_title"], 300),
        "target_folder_handle": _folder_handle_from_row(target_row, fingerprint),
        "target_folder_title": _bounded_string(target_row["title"], 300),
    }, None


def _apply_notes_append(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    body_text: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    handle = str(target["handle"])
    expected_sha = str(target["expected_current_sha256"])
    note_id = None
    store_uuid = None
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is not None:
                row = _select_notes_row(connection, note_id)
                store_uuid = _notes_store_uuid(connection)
            else:
                row = None
    except StoreUnavailableError:
        return _apply_error(
            [_notes_store_unavailable_warning()],
            plan={"preview": preview},
            status="degraded",
        )

    if note_id is None or row is None:
        return _apply_error(
            [_warning("target_note_not_found", "Notes target note was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if not store_uuid:
        return _apply_error(
            [_warning("content_unavailable", "Notes target could not be resolved from the local store mapping.")],
            plan={"preview": preview},
            status="content_unavailable",
        )

    try:
        current_html = script_runner(
            _notes_body_script(store_uuid, note_id),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes append read timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("read_error", "Notes target content could not be read before append.")],
            plan={"preview": preview},
        )

    current_text = _html_to_text(current_html)
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "Notes target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    normalized_body, body_warning = _normalize_update_body(body_text, operation="append_text")
    if body_warning is not None:
        return _apply_error([body_warning], plan={"preview": preview})

    try:
        output = script_runner(
            _notes_append_script(
                store_uuid,
                note_id,
                current_html,
                _notes_append_body_html(normalized_body),
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes append timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes target could not be appended safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=MAX_CONTENT_CHARS,
        script_runner=script_runner,
    )
    if read_back.get("status") != "ok" or not isinstance(read_back.get("result"), dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Notes append succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    after_text = str(read_back["result"].get("content_text", ""))
    if not after_text.endswith(normalized_body):
        return _apply_error(
            [_warning("read_back_mismatch", "Notes append read-back did not include the approved appended text.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back["result"],
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _apply_notes_move_to_folder(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    handle = str(target["handle"])
    expected_sha = str(target["expected_current_sha256"])
    source_folder_handle = str(target["source_folder_handle"])
    target_folder_handle = str(target["target_folder_handle"])
    note_id = None
    source_row = None
    target_row = None
    store_uuid = None
    fingerprint = ""
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is not None:
                source_row = _select_note_folder_row(connection, note_id)
                store_uuid = _notes_store_uuid(connection)
            target_row = _resolve_notes_folder_handle(connection, fingerprint, target_folder_handle)
    except StoreUnavailableError:
        return _apply_error(
            [_notes_store_unavailable_warning()],
            plan={"preview": preview},
            status="degraded",
        )

    if note_id is None or source_row is None:
        return _apply_error(
            [_warning("target_note_not_found", "Notes target note was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if source_row["folder_id"] is None or source_row["account_id"] is None:
        return _apply_error(
            [_warning("source_folder_unavailable", "Notes source folder could not be resolved.")],
            plan={"preview": preview},
        )
    if target_row is None:
        return _apply_error(
            [_warning("target_folder_not_found", "Notes target folder was not found.")],
            plan={"preview": preview},
        )
    if _folder_is_smart(target_row):
        return _apply_error(
            [_warning("unsupported_smart_folder", "Notes move is blocked for smart folders.")],
            plan={"preview": preview},
        )
    if not store_uuid:
        return _apply_error(
            [_warning("content_unavailable", "Notes target could not be resolved from the local store mapping.")],
            plan={"preview": preview},
            status="content_unavailable",
        )

    current_folder_handle = _folder_handle_from_row(source_row, fingerprint)
    target_folder_id = int(target_row["folder_id"])
    target_folder_reference = f"x-coredata://{store_uuid}/ICFolder/p{target_folder_id}"
    if current_folder_handle != source_folder_handle:
        return _apply_error(
            [_warning("stale_folder_state", "Notes target folder changed since the plan; re-plan before applying.")],
            plan={"preview": preview},
        )
    if int(source_row["account_id"] or 0) != int(target_row["account_id"] or 0):
        return _apply_error(
            [_warning("cross_account_move_blocked", "Notes move is limited to folders in the same account.")],
            plan={"preview": preview},
        )

    try:
        current_html = script_runner(
            _notes_body_script(store_uuid, note_id),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes move read timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("read_error", "Notes target content could not be read before move.")],
            plan={"preview": preview},
        )

    current_text = _html_to_text(current_html)
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "Notes target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    try:
        output = script_runner(
            _notes_move_to_folder_script(
                store_uuid,
                note_id,
                current_html,
                target_folder_reference,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes move timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes target could not be moved safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = _notes_move_read_back(
        handle,
        target_folder_handle=target_folder_handle,
        target_folder_id=target_folder_id,
        source_folder_handle=source_folder_handle,
        db_path=db_path,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes move succeeded but folder read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if read_back.get("target_folder_confirmed") is not True:
        return _apply_error(
            [_warning("read_back_mismatch", "Notes move read-back did not confirm the selected folder.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _apply_notes_replace(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    body_text: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    handle = str(target["handle"])
    expected_sha = str(target["expected_current_sha256"])
    note_id = None
    store_uuid = None
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is not None:
                row = _select_notes_row(connection, note_id)
                store_uuid = _notes_store_uuid(connection)
            else:
                row = None
    except StoreUnavailableError:
        return _apply_error(
            [_notes_store_unavailable_warning()],
            plan={"preview": preview},
            status="degraded",
        )

    if note_id is None or row is None:
        return _apply_error(
            [_warning("target_note_not_found", "Notes target note was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if not store_uuid:
        return _apply_error(
            [_warning("content_unavailable", "Notes target could not be resolved from the local store mapping.")],
            plan={"preview": preview},
            status="content_unavailable",
        )

    try:
        current_html = script_runner(
            _notes_body_script(store_uuid, note_id),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes replace read timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("read_error", "Notes target content could not be read before replace.")],
            plan={"preview": preview},
        )

    current_text = _html_to_text(current_html)
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "Notes target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    normalized_body, body_warning = _normalize_update_body(body_text, operation="replace_text")
    if body_warning is not None:
        return _apply_error([body_warning], plan={"preview": preview})

    try:
        output = script_runner(
            _notes_replace_script(
                store_uuid,
                note_id,
                current_html,
                _notes_replace_body_html(normalized_body),
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes replace timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes target could not be replaced safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=MAX_CONTENT_CHARS,
        script_runner=script_runner,
    )
    if read_back.get("status") != "ok" or not isinstance(read_back.get("result"), dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Notes replace succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    after_text = str(read_back["result"].get("content_text", ""))
    if not _normalized_content_matches(after_text, normalized_body):
        return _apply_error(
            [_warning("read_back_mismatch", "Notes replace read-back did not match the approved replacement text.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back["result"],
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _apply_notes_create_html(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    body_html: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    # Title comes from the approved plan preview to avoid trusting apply-time input drift.
    proposed = preview.get("proposed", {}) if isinstance(preview, dict) else {}
    normalized_title = str(proposed.get("title", ""))
    normalized_body_html, body_warning = _normalize_body_html(body_html, operation="create_html")
    if body_warning is not None:
        return _apply_error([body_warning], plan={"preview": preview})
    expected_text = _html_to_text(normalized_body_html)

    folder_id: int | None = None
    folder_reference: str | None = None
    target = preview.get("target") if isinstance(preview, dict) else None
    if isinstance(target, dict) and "folder_handle" in target:
        folder_resolution, folder_warning = _resolve_folder_apply_target(
            str(target.get("folder_handle", "")),
            db_path=db_path,
        )
        if folder_warning is not None:
            return _apply_error([folder_warning], plan={"preview": preview})
        folder_id = folder_resolution["folder_id"]
        folder_reference = folder_resolution["folder_reference"]

    already_applied = _find_matching_html_note(
        normalized_title,
        expected_text,
        db_path=db_path,
        script_runner=script_runner,
        folder_id=folder_id,
    )
    if already_applied is not None:
        return _apply_success(
            already_applied,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Matching Notes note already exists.")],
        )

    try:
        created_id = script_runner(
            _notes_create_html_script(
                normalized_title,
                normalized_body_html,
                folder_reference=folder_reference,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes rich-text create timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes rich-text note could not be created safely.")],
            plan={"preview": preview},
        )

    read_back = _read_back_created_html_note(
        created_id,
        normalized_title,
        expected_text,
        db_path=db_path,
        script_runner=script_runner,
        folder_id=folder_id,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Notes rich-text create succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if not _normalized_content_matches(read_back.get("content_text", ""), expected_text):
        return _apply_error(
            [_warning("read_back_mismatch", "Notes rich-text create read-back visible text did not match the approved body.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _apply_notes_replace_html(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    body_html: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    handle = str(target["handle"])
    expected_sha = str(target["expected_current_sha256"])
    note_id = None
    store_uuid = None
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is not None:
                row = _select_notes_row(connection, note_id)
                store_uuid = _notes_store_uuid(connection)
            else:
                row = None
    except StoreUnavailableError:
        return _apply_error(
            [_notes_store_unavailable_warning()],
            plan={"preview": preview},
            status="degraded",
        )

    if note_id is None or row is None:
        return _apply_error(
            [_warning("target_note_not_found", "Notes target note was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if not store_uuid:
        return _apply_error(
            [_warning("content_unavailable", "Notes target could not be resolved from the local store mapping.")],
            plan={"preview": preview},
            status="content_unavailable",
        )

    try:
        current_html = script_runner(
            _notes_body_script(store_uuid, note_id),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes rich-text replace read timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("read_error", "Notes target content could not be read before rich-text replace.")],
            plan={"preview": preview},
        )

    # HTML never round-trips exactly through Notes.app, so bind and prove the
    # note's expected/observed VISIBLE TEXT (extracted-plain-text SHA), not HTML.
    current_text = _html_to_text(current_html)
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "Notes target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    normalized_body_html, body_warning = _normalize_body_html(body_html, operation="replace_html")
    if body_warning is not None:
        return _apply_error([body_warning], plan={"preview": preview})
    expected_text = _html_to_text(normalized_body_html)

    try:
        output = script_runner(
            _notes_replace_script(
                store_uuid,
                note_id,
                current_html,
                normalized_body_html,
            ),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes rich-text replace timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes target could not be replaced safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=MAX_CONTENT_CHARS,
        content_format="html",
        script_runner=script_runner,
    )
    if read_back.get("status") != "ok" or not isinstance(read_back.get("result"), dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Notes rich-text replace succeeded but read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    after_text = str(read_back["result"].get("content_text", ""))
    if not _normalized_content_matches(after_text, expected_text):
        return _apply_error(
            [_warning("read_back_mismatch", "Notes rich-text replace read-back visible text did not match the approved body.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    return _apply_success(
        read_back["result"],
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _apply_notes_delete(
    preview: dict[str, Any],
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = preview["target"]
    handle = str(target["handle"])
    expected_sha = str(target["expected_current_sha256"])
    note_id = None
    store_uuid = None
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is not None:
                row = _select_notes_row(connection, note_id)
                store_uuid = _notes_store_uuid(connection)
            else:
                row = None
    except StoreUnavailableError:
        return _apply_error(
            [_notes_store_unavailable_warning()],
            plan={"preview": preview},
            status="degraded",
        )

    if note_id is None or row is None:
        return _apply_error(
            [_warning("target_note_not_found", "Notes target note was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if not store_uuid:
        return _apply_error(
            [_warning("content_unavailable", "Notes target could not be resolved from the local store mapping.")],
            plan={"preview": preview},
            status="content_unavailable",
        )

    try:
        current_html = script_runner(
            _notes_body_script(store_uuid, note_id),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes delete read timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("read_error", "Notes target content could not be read before delete.")],
            plan={"preview": preview},
        )

    current_text = _html_to_text(current_html)
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "Notes target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    try:
        output = script_runner(
            _notes_delete_script(store_uuid, note_id, current_html),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes delete timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, NotesAutomationError):
        return _apply_error(
            [_warning("write_error", "Notes target could not be deleted safely.")],
            plan={"preview": preview},
        )

    automation_warning = _automation_warning_from_output(output)
    if automation_warning is not None:
        return _apply_error([automation_warning], plan={"preview": preview})

    read_back = get_notes_metadata(handle, db_path=db_path)
    if read_back.get("status") == "not_found":
        return _apply_success(
            {"handle": handle, "deleted": True, "verified_absent": True},
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=True,
            warnings=[],
        )
    if read_back.get("status") == "ok":
        return _apply_error(
            [_warning("read_back_mismatch", "Notes delete read-back still found the target note.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    return _apply_error(
        [_warning("read_back_unavailable", "Notes delete succeeded but absence read-back was unavailable.")],
        plan={"preview": preview},
        status="partial",
        mutation_applied=True,
    )


def _find_matching_note_content(
    title: str,
    body_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    folder_id: int | None = None,
) -> dict[str, Any] | None:
    search = search_notes_metadata(title, db_path=db_path, limit=20)
    if search.get("status") != "ok":
        return None
    expected = _expected_created_note_text(title, body_text)
    for item in search.get("results", []):
        if item.get("title") != title:
            continue
        handle = item.get("handle")
        if not isinstance(handle, str):
            continue
        if folder_id is not None:
            note_id = _note_id_for_handle(db_path, handle)
            if note_id is None or not _note_folder_matches(db_path, note_id, folder_id):
                continue
        content = get_notes_content(
            handle,
            db_path=db_path,
            max_chars=MAX_CONTENT_CHARS,
            script_runner=script_runner,
        )
        if content.get("status") != "ok" or not isinstance(content.get("result"), dict):
            continue
        if _normalized_content_matches(content["result"].get("content_text", ""), expected):
            return content["result"]
    return None


def _find_matching_html_note(
    title: str,
    expected_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    folder_id: int | None = None,
) -> dict[str, Any] | None:
    search = search_notes_metadata(title, db_path=db_path, limit=20)
    if search.get("status") != "ok":
        return None
    for item in search.get("results", []):
        if item.get("title") != title:
            continue
        handle = item.get("handle")
        if not isinstance(handle, str):
            continue
        if folder_id is not None:
            note_id = _note_id_for_handle(db_path, handle)
            if note_id is None or not _note_folder_matches(db_path, note_id, folder_id):
                continue
        content = get_notes_content(
            handle,
            db_path=db_path,
            max_chars=MAX_CONTENT_CHARS,
            content_format="html",
            script_runner=script_runner,
        )
        if content.get("status") != "ok" or not isinstance(content.get("result"), dict):
            continue
        if _normalized_content_matches(content["result"].get("content_text", ""), expected_text):
            return content["result"]
    return None


def _read_back_created_html_note(
    created_id: str,
    title: str,
    expected_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    folder_id: int | None = None,
) -> dict[str, Any] | None:
    note_id = _note_id_from_automation_output(created_id)
    if note_id is not None:
        if folder_id is not None and not _note_folder_matches(db_path, note_id, folder_id):
            return _find_matching_html_note(
                title,
                expected_text,
                db_path=db_path,
                script_runner=script_runner,
                folder_id=folder_id,
            )
        content = get_notes_content(
            make_int_handle("notes:note", note_id),
            db_path=db_path,
            max_chars=MAX_CONTENT_CHARS,
            content_format="html",
            script_runner=script_runner,
        )
        if content.get("status") == "ok" and isinstance(content.get("result"), dict):
            return content["result"]
    return _find_matching_html_note(
        title,
        expected_text,
        db_path=db_path,
        script_runner=script_runner,
        folder_id=folder_id,
    )


def _read_back_created_note(
    created_id: str,
    title: str,
    body_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
    folder_id: int | None = None,
) -> dict[str, Any] | None:
    note_id = _note_id_from_automation_output(created_id)
    if note_id is not None:
        if folder_id is not None and not _note_folder_matches(db_path, note_id, folder_id):
            return _find_matching_note_content(
                title,
                body_text,
                db_path=db_path,
                script_runner=script_runner,
                folder_id=folder_id,
            )
        content = get_notes_content(
            make_int_handle("notes:note", note_id),
            db_path=db_path,
            max_chars=MAX_CONTENT_CHARS,
            script_runner=script_runner,
        )
        if content.get("status") == "ok" and isinstance(content.get("result"), dict):
            return content["result"]
    return _find_matching_note_content(
        title,
        body_text,
        db_path=db_path,
        script_runner=script_runner,
        folder_id=folder_id,
    )


def _find_matching_child_folder(
    title: str,
    *,
    parent_folder_id: int,
    parent_account_id: int,
    parent_folder_handle: str,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _select_child_folder_row(
                connection,
                title=title,
                parent_folder_id=parent_folder_id,
                parent_account_id=parent_account_id,
            )
    except StoreUnavailableError:
        return None
    if row is None:
        return None
    return _folder_create_read_back(
        row,
        fingerprint,
        parent_folder_id=parent_folder_id,
        parent_folder_handle=parent_folder_handle,
    )


def _read_back_created_folder(
    created_id: str,
    title: str,
    *,
    parent_folder_id: int,
    parent_account_id: int,
    parent_folder_handle: str,
    db_path: Path,
) -> dict[str, Any] | None:
    folder_id = _folder_id_from_automation_output(created_id)
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _select_folder_by_id(connection, folder_id) if folder_id is not None else None
            if row is not None and not _created_folder_row_has_expected_identity(
                row,
                title=title,
                parent_account_id=parent_account_id,
            ):
                row = None
            if row is None:
                row = _select_child_folder_row(
                    connection,
                    title=title,
                    parent_folder_id=parent_folder_id,
                    parent_account_id=parent_account_id,
                )
    except StoreUnavailableError:
        return None
    if row is None:
        return None
    return _folder_create_read_back(
        row,
        fingerprint,
        parent_folder_id=parent_folder_id,
        parent_folder_handle=parent_folder_handle,
    )


def _created_folder_row_has_expected_identity(
    row,
    *,
    title: str,
    parent_account_id: int,
) -> bool:
    return (
        _bounded_string(row["title"], MAX_PREVIEW_TITLE_CHARS) == title
        and int(row["account_id"] or 0) == parent_account_id
        and not _folder_is_smart(row)
    )


def _folder_create_read_back(
    row,
    fingerprint: str,
    *,
    parent_folder_id: int,
    parent_folder_handle: str,
) -> dict[str, Any]:
    result = _folder_metadata(row, fingerprint)
    result.update(
        {
            "created": True,
            "parent_folder_handle": parent_folder_handle,
            "parent_folder_confirmed": int(row["parent_id"] or 0) == parent_folder_id,
            "note_content_returned": False,
        }
    )
    return result


def _folder_delete_safety_warning(
    row,
    occupancy: dict[str, int],
) -> dict[str, str] | None:
    if _folder_is_smart(row):
        return _warning("unsupported_smart_folder", "Notes folder delete is blocked for smart folders.")
    if row["parent_id"] is None:
        return _warning(
            "root_folder_delete_blocked",
            "Notes folder delete is limited to exact empty child folders.",
        )
    if int(occupancy.get("non_deleted_note_count", 0)) > 0:
        return _warning(
            "folder_not_empty",
            "Notes folder delete is blocked unless the exact folder has no non-deleted notes.",
        )
    if int(occupancy.get("child_folder_count", 0)) > 0:
        return _warning(
            "folder_not_empty",
            "Notes folder delete is blocked unless the exact folder has no child folders.",
        )
    return None


def _folder_move_safety_warning(
    row,
    occupancy: dict[str, int],
) -> dict[str, str] | None:
    if _folder_is_smart(row):
        return _warning("unsupported_smart_folder", "Notes folder move is blocked for smart folders.")
    if row["parent_id"] is None:
        return _warning(
            "root_folder_move_blocked",
            "Notes folder move is limited to exact empty child folders.",
        )
    if int(occupancy.get("non_deleted_note_count", 0)) > 0:
        return _warning(
            "folder_not_empty",
            "Notes folder move is blocked unless the exact source folder has no non-deleted notes.",
        )
    if int(occupancy.get("child_folder_count", 0)) > 0:
        return _warning(
            "folder_not_empty",
            "Notes folder move is blocked unless the exact source folder has no child folders.",
        )
    return None


def _notes_folder_delete_read_back(
    folder_handle: str,
    *,
    folder_id: int,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            _check_folder_schema(connection)
            row = _select_folder_by_id(connection, folder_id)
    except StoreUnavailableError:
        return None
    deleted = row is None
    return {
        "folder_handle": folder_handle,
        "deleted": deleted,
        "verified_absent": deleted,
        "folder_content_returned": False,
        "note_content_returned": False,
    }


def _notes_folder_rename_read_back(
    folder_handle: str,
    *,
    folder_id: int,
    new_title: str,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _select_folder_by_id(connection, folder_id)
    except StoreUnavailableError:
        return None
    if row is None or _folder_is_smart(row):
        return None
    current_handle = _folder_handle_from_row(row, fingerprint)
    result = _folder_metadata(row, fingerprint)
    result.update(
        {
            "folder_handle": folder_handle,
            "current_folder_handle": current_handle,
            "renamed": current_handle == folder_handle
            and _bounded_string(row["title"], MAX_PREVIEW_TITLE_CHARS) == new_title,
            "folder_content_returned": False,
            "note_content_returned": False,
        }
    )
    return result


def _notes_folder_move_read_back(
    folder_handle: str,
    *,
    folder_id: int,
    target_folder_handle: str,
    target_folder_id: int,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            row = _select_folder_by_id(connection, folder_id)
    except StoreUnavailableError:
        return None
    if row is None or _folder_is_smart(row):
        return None
    current_handle = _folder_handle_from_row(row, fingerprint)
    result = _folder_metadata(row, fingerprint)
    result.update(
        {
            "folder_handle": folder_handle,
            "current_folder_handle": current_handle,
            "moved": current_handle == folder_handle
            and int(row["parent_id"] or 0) == target_folder_id,
            "target_folder_handle": target_folder_handle,
            "target_folder_confirmed": int(row["parent_id"] or 0) == target_folder_id,
            "folder_content_returned": False,
            "note_content_returned": False,
        }
    )
    return result


def _notes_move_read_back(
    handle: str,
    *,
    target_folder_handle: str,
    target_folder_id: int,
    source_folder_handle: str,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_folder_schema(connection)
            note_id = _resolve_notes_handle_note_id(connection, handle)
            if note_id is None:
                return None
            row = _select_note_folder_row(connection, note_id)
            metadata_row = _select_notes_row(connection, note_id)
    except StoreUnavailableError:
        return None
    if row is None or metadata_row is None:
        return None
    current_folder_handle = _folder_handle_from_row(row, fingerprint)
    return {
        "handle": handle,
        "title": _bounded_string(metadata_row["title"], MAX_PREVIEW_TITLE_CHARS),
        "moved": current_folder_handle == target_folder_handle,
        "source_folder_handle": source_folder_handle,
        "target_folder_handle": target_folder_handle,
        "current_folder_handle": current_folder_handle,
        "target_folder_confirmed": int(row["folder_id"] or 0) == target_folder_id,
        "body_returned": False,
    }


def _note_id_from_automation_output(value: str) -> int | None:
    match = re.search(r"\bICNote/p([0-9]+)\b", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _folder_id_from_automation_output(value: str) -> int | None:
    match = re.search(r"\bICFolder/p([0-9]+)\b", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _normalized_content_matches(value: Any, expected: str) -> bool:
    if not isinstance(value, str):
        return False
    return _normalize_text(value) == _normalize_text(expected)


def _expected_created_note_text(title: str, body_text: str) -> str:
    if body_text:
        return f"{title}\n{body_text}"
    return title


def _notes_create_script(
    title: str,
    body_text: str,
    *,
    folder_reference: str | None = None,
) -> str:
    title_ref = _applescript_string(title)
    body_ref = _applescript_string(_notes_create_body_html(title, body_text))
    if folder_reference:
        folder_ref = _applescript_string(folder_reference)
        return f"""
set noteTitle to {title_ref}
set noteBody to {body_ref}
set targetFolderId to {folder_ref}
tell application "Notes"
    set targetFolder to folder id targetFolderId
    set createdNote to make new note at targetFolder with properties {{name:noteTitle, body:noteBody}}
    return id of createdNote
end tell
"""
    return f"""
set noteTitle to {title_ref}
set noteBody to {body_ref}
tell application "Notes"
    set createdNote to make new note with properties {{name:noteTitle, body:noteBody}}
    return id of createdNote
end tell
"""


def _notes_create_html_script(
    title: str,
    body_html: str,
    *,
    folder_reference: str | None = None,
) -> str:
    title_ref = _applescript_string(title)
    body_ref = _applescript_string(body_html)
    if folder_reference:
        folder_ref = _applescript_string(folder_reference)
        return f"""
set noteTitle to {title_ref}
set noteBody to {body_ref}
set targetFolderId to {folder_ref}
tell application "Notes"
    set targetFolder to folder id targetFolderId
    set createdNote to make new note at targetFolder with properties {{name:noteTitle, body:noteBody}}
    return id of createdNote
end tell
"""
    return f"""
set noteTitle to {title_ref}
set noteBody to {body_ref}
tell application "Notes"
    set createdNote to make new note with properties {{name:noteTitle, body:noteBody}}
    return id of createdNote
end tell
"""


def _notes_create_folder_script(
    title: str,
    *,
    parent_folder_reference: str,
) -> str:
    title_ref = _applescript_string(title)
    folder_ref = _applescript_string(parent_folder_reference)
    return f"""
set folderTitle to {title_ref}
set parentFolderId to {folder_ref}
tell application "Notes"
    set targetFolder to folder id parentFolderId
    set createdFolder to make new folder at targetFolder with properties {{name:folderTitle}}
    return id of createdFolder
end tell
"""


def _notes_rename_folder_script(
    folder_reference: str,
    *,
    expected_title: str,
    new_title: str,
) -> str:
    folder_ref = _applescript_string(folder_reference)
    expected_ref = _applescript_string(expected_title)
    title_ref = _applescript_string(new_title)
    return f"""
set targetFolderId to {folder_ref}
set expectedTitle to {expected_ref}
set newTitle to {title_ref}
tell application "Notes"
    set targetFolder to folder id targetFolderId
    if name of targetFolder is not expectedTitle then return "{AUTOMATION_ERROR_PREFIX}current_folder_changed"
    set name of targetFolder to newTitle
    return id of targetFolder
end tell
	"""


def _notes_delete_folder_script(
    folder_reference: str,
    *,
    expected_title: str,
) -> str:
    folder_ref = _applescript_string(folder_reference)
    expected_ref = _applescript_string(expected_title)
    return f"""
set targetFolderId to {folder_ref}
set expectedTitle to {expected_ref}
tell application "Notes"
    set targetFolder to folder id targetFolderId
    if name of targetFolder is not expectedTitle then return "{AUTOMATION_ERROR_PREFIX}current_folder_changed"
    if shared of targetFolder is true then return "{AUTOMATION_ERROR_PREFIX}shared_folder"
    if (count of notes of targetFolder) is not 0 then return "{AUTOMATION_ERROR_PREFIX}folder_not_empty"
    if (count of folders of targetFolder) is not 0 then return "{AUTOMATION_ERROR_PREFIX}folder_not_empty"
    delete targetFolder
    return "ok"
end tell
"""


def _notes_move_folder_script(
    folder_reference: str,
    target_folder_reference: str,
    *,
    expected_title: str,
) -> str:
    folder_ref = _applescript_string(folder_reference)
    target_ref = _applescript_string(target_folder_reference)
    expected_ref = _applescript_string(expected_title)
    return f"""
set sourceFolderId to {folder_ref}
set targetFolderId to {target_ref}
set expectedTitle to {expected_ref}
tell application "Notes"
    set sourceFolder to folder id sourceFolderId
    set targetFolder to folder id targetFolderId
    if name of sourceFolder is not expectedTitle then return "{AUTOMATION_ERROR_PREFIX}current_folder_changed"
    if shared of sourceFolder is true then return "{AUTOMATION_ERROR_PREFIX}shared_folder"
    if shared of targetFolder is true then return "{AUTOMATION_ERROR_PREFIX}shared_folder"
    if (count of notes of sourceFolder) is not 0 then return "{AUTOMATION_ERROR_PREFIX}folder_not_empty"
    if (count of folders of sourceFolder) is not 0 then return "{AUTOMATION_ERROR_PREFIX}folder_not_empty"
    move sourceFolder to targetFolder
    return id of sourceFolder
end tell
"""


def _notes_create_body_html(title: str, body_text: str) -> str:
    escaped_title = html_lib.escape(title)
    if not body_text:
        return f"<h1>{escaped_title}</h1>"
    paragraphs = []
    for block in re.split(r"\n{2,}", body_text):
        lines = [html_lib.escape(line) for line in block.split("\n")]
        paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return f"<h1>{escaped_title}</h1>{''.join(paragraphs)}"


def _notes_append_body_html(body_text: str) -> str:
    paragraphs = []
    for block in re.split(r"\n{2,}", body_text):
        lines = [html_lib.escape(line) for line in block.split("\n")]
        paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return "".join(paragraphs)


def _notes_replace_body_html(body_text: str) -> str:
    lines = body_text.split("\n")
    title = html_lib.escape(lines[0])
    remainder = "\n".join(lines[1:]).strip("\n")
    if not remainder:
        return f"<h1>{title}</h1>"
    paragraphs = []
    for block in re.split(r"\n{2,}", remainder):
        block_lines = [html_lib.escape(line) for line in block.split("\n")]
        paragraphs.append(f"<p>{'<br>'.join(block_lines)}</p>")
    return f"<h1>{title}</h1>{''.join(paragraphs)}"


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        payload,
        _warning,
        fallback_message="Notes warning detail was redacted.",
    )


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"notes-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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


def _notes_append_script(
    store_uuid: str,
    note_id: int,
    expected_body_html: str,
    append_body_html: str,
) -> str:
    note_ref = _applescript_string(f"x-coredata://{store_uuid}/ICNote/p{note_id}")
    expected_ref = _applescript_string(expected_body_html)
    append_ref = _applescript_string(append_body_html)
    return f"""
set targetId to {note_ref}
set expectedBody to {expected_ref}
set appendBody to {append_ref}
tell application "Notes"
    set targetNote to note id targetId
    if password protected of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}password_protected_note"
    if shared of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}shared_note"
    if body of targetNote is not expectedBody then return "{AUTOMATION_ERROR_PREFIX}current_content_changed"
    set body of targetNote to expectedBody & appendBody
    return id of targetNote
end tell
"""


def _notes_replace_script(
    store_uuid: str,
    note_id: int,
    expected_body_html: str,
    replacement_body_html: str,
) -> str:
    note_ref = _applescript_string(f"x-coredata://{store_uuid}/ICNote/p{note_id}")
    expected_ref = _applescript_string(expected_body_html)
    replacement_ref = _applescript_string(replacement_body_html)
    return f"""
set targetId to {note_ref}
set expectedBody to {expected_ref}
set replacementBody to {replacement_ref}
tell application "Notes"
    set targetNote to note id targetId
    if password protected of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}password_protected_note"
    if shared of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}shared_note"
    if body of targetNote is not expectedBody then return "{AUTOMATION_ERROR_PREFIX}current_content_changed"
    set body of targetNote to replacementBody
    return id of targetNote
end tell
"""


def _notes_delete_script(
    store_uuid: str,
    note_id: int,
    expected_body_html: str,
) -> str:
    note_ref = _applescript_string(f"x-coredata://{store_uuid}/ICNote/p{note_id}")
    expected_ref = _applescript_string(expected_body_html)
    return f"""
set targetId to {note_ref}
set expectedBody to {expected_ref}
tell application "Notes"
    set targetNote to note id targetId
    if password protected of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}password_protected_note"
    if shared of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}shared_note"
    if body of targetNote is not expectedBody then return "{AUTOMATION_ERROR_PREFIX}current_content_changed"
    delete targetNote
    return "ok"
end tell
"""


def _notes_move_to_folder_script(
    store_uuid: str,
    note_id: int,
    expected_body_html: str,
    target_folder_reference: str,
) -> str:
    note_ref = _applescript_string(f"x-coredata://{store_uuid}/ICNote/p{note_id}")
    folder_ref = _applescript_string(target_folder_reference)
    expected_ref = _applescript_string(expected_body_html)
    return f"""
set targetId to {note_ref}
set targetFolderId to {folder_ref}
set expectedBody to {expected_ref}
tell application "Notes"
    set targetNote to note id targetId
    set targetFolder to folder id targetFolderId
    if password protected of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}password_protected_note"
    if shared of targetNote is true then return "{AUTOMATION_ERROR_PREFIX}shared_note"
    if body of targetNote is not expectedBody then return "{AUTOMATION_ERROR_PREFIX}current_content_changed"
    move targetNote to targetFolder
    return id of targetNote
end tell
"""


def _automation_warning_from_output(output: str) -> dict[str, str] | None:
    normalized = output.strip()
    if not normalized.startswith(AUTOMATION_ERROR_PREFIX):
        return None
    code = normalized.removeprefix(AUTOMATION_ERROR_PREFIX)
    if code == "password_protected_note":
        return _warning("password_protected_note", "Notes mutation is blocked for password-protected notes.")
    if code == "shared_note":
        return _warning("shared_note_mutation_blocked", "Notes mutation is blocked for shared notes.")
    if code == "current_content_changed":
        return _warning("current_content_changed", "Notes target content changed before mutation could be applied.")
    if code == "current_folder_changed":
        return _warning("current_folder_changed", "Notes folder title changed before mutation could be applied.")
    if code == "folder_not_empty":
        return _warning("folder_not_empty", "Notes folder mutation is blocked unless the exact folder is empty.")
    if code == "shared_folder":
        return _warning("shared_folder_mutation_blocked", "Notes folder mutation is blocked for shared folders.")
    return _warning("automation_refused", "Notes automation refused the mutation operation.")


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class NotesAutomationError(RuntimeError):
    pass


def _run_osascript(script: str, timeout: float) -> str:
    try:
        completed = subprocess.run(
            ["osascript"],
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except OSError:
        raise NotesAutomationError() from None
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


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text[: max(1, min(max_chars, MAX_CONTENT_CHARS))]


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


def _bounded_body_html(html: str, max_chars: int) -> tuple[str, bool]:
    text = html if isinstance(html, str) else str(html)
    limit = max(1, min(max_chars, MAX_BODY_HTML_CHARS))
    if len(text) <= limit:
        return text, False
    return text[:limit], True


# Tags whose entire contents must never survive into a stored note body because
# they can carry active or externally fetched content.
_UNSAFE_HTML_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "applet",
    "link",
    "meta",
    "base",
    "form",
    "svg",
    "math",
}
# Attribute name prefixes/values that carry active content.
_UNSAFE_HTML_ATTR_PREFIXES = ("on",)  # event handlers: onclick, onload, ...
_UNSAFE_HTML_URI_ATTRS = {"href", "src", "xlink:href", "action", "formaction", "background"}
_DANGEROUS_HTML_PATTERNS = (
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"</\s*script\b", re.IGNORECASE),
    re.compile(r"\son[a-z0-9_-]+\s*=", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
    re.compile(r"data\s*:", re.IGNORECASE),
)


# C0 control characters other than tab (\t), newline (\n), and carriage return
# (\r), plus the DEL character. A NUL or other C0 byte embedded inside a tag or
# attribute name (e.g. ``<scr\x00ipt>`` or ``on\x00click=``) can slip past the
# element/attribute matching in the sanitizer, so any HTML that contains one is
# treated as unsafe and rejected fail-closed rather than sanitized.
_HTML_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _html_has_control_chars(html: str) -> bool:
    return bool(_HTML_CONTROL_CHARS.search(html))


def _html_contains_active_content(html: str) -> bool:
    if _html_has_control_chars(html):
        return True
    lowered = html
    for pattern in _DANGEROUS_HTML_PATTERNS:
        if pattern.search(lowered):
            return True
    for tag in _UNSAFE_HTML_TAGS:
        if re.search(rf"<\s*{re.escape(tag)}\b", lowered, re.IGNORECASE):
            return True
    return False


class _HTMLSanitizer(HTMLParser):
    """Strip active/unsafe content from note body HTML.

    Removes ``<script>``/``<style>``/etc element contents entirely, drops
    event-handler (``on*``) attributes, and rejects ``javascript:``/``data:``
    URIs on link/media attributes. Preserves visible text and safe formatting
    tags so the note renders the same visible content.
    """

    _VOID_TAGS = {"br", "hr", "img", "wbr", "col"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._suppress_depth = 0
        self._suppress_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in _UNSAFE_HTML_TAGS:
            if lowered not in self._VOID_TAGS:
                self._suppress_depth += 1
                self._suppress_stack.append(lowered)
            return
        if self._suppress_depth:
            return
        self._chunks.append(self._render_start(lowered, attrs, self_closing=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in _UNSAFE_HTML_TAGS:
            return
        if self._suppress_depth:
            return
        self._chunks.append(self._render_start(lowered, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._suppress_stack and self._suppress_stack[-1] == lowered:
            self._suppress_stack.pop()
            self._suppress_depth -= 1
            return
        if lowered in _UNSAFE_HTML_TAGS:
            return
        if self._suppress_depth:
            return
        if lowered in self._VOID_TAGS:
            return
        self._chunks.append(f"</{lowered}>")

    def handle_data(self, data: str) -> None:
        if self._suppress_depth:
            return
        self._chunks.append(html_lib.escape(data, quote=False))

    def _render_start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        self_closing: bool,
    ) -> str:
        safe_attrs: list[str] = []
        for name, value in attrs:
            lowered_name = name.lower()
            if any(lowered_name.startswith(prefix) for prefix in _UNSAFE_HTML_ATTR_PREFIXES):
                continue
            attr_value = value or ""
            if lowered_name in _UNSAFE_HTML_URI_ATTRS and _unsafe_uri(attr_value):
                continue
            escaped = html_lib.escape(attr_value, quote=True)
            safe_attrs.append(f'{lowered_name}="{escaped}"')
        rendered = tag if not safe_attrs else tag + " " + " ".join(safe_attrs)
        if self_closing or tag in self._VOID_TAGS:
            return f"<{rendered}>"
        return f"<{rendered}>"

    def html(self) -> str:
        return "".join(self._chunks)


def _unsafe_uri(value: str) -> bool:
    stripped = value.strip().lower().replace("\t", "").replace("\n", "").replace("\r", "")
    return (
        stripped.startswith("javascript:")
        or stripped.startswith("vbscript:")
        or stripped.startswith("data:")
    )


def _sanitize_body_html(html: str) -> str:
    sanitizer = _HTMLSanitizer()
    sanitizer.feed(html)
    sanitizer.close()
    return sanitizer.html()


def _normalize_body_html(value: Any, *, operation: str) -> tuple[str, dict[str, str] | None]:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        label = "rich-text create" if operation == "create_html" else "rich-text replace"
        return "", _warning("missing_body_html", f"Notes {label} requires non-empty body_html.")
    if len(text) > MAX_BODY_HTML_CHARS:
        label = "rich-text create" if operation == "create_html" else "rich-text replace"
        return (
            "",
            _warning("body_html_too_long", f"Notes {label} body_html exceeded the maximum length."),
        )
    # Reject NUL / C0 control characters before parsing so a control byte embedded
    # in a tag or attribute name (e.g. ``<scr\x00ipt>``) cannot evade the
    # element/attribute matching in the sanitizer. Fail closed.
    if _html_has_control_chars(text):
        return (
            "",
            _warning(
                "unsafe_body_html",
                "Notes rich-text body could not be safely sanitized of active or embedded content.",
            ),
        )
    sanitized = _sanitize_body_html(text)
    if _html_contains_active_content(sanitized):
        return (
            "",
            _warning(
                "unsafe_body_html",
                "Notes rich-text body could not be safely sanitized of active or embedded content.",
            ),
        )
    plain_text = _html_to_text(sanitized)
    if not plain_text.strip():
        label = "rich-text create" if operation == "create_html" else "rich-text replace"
        return (
            "",
            _warning(
                "empty_body_html_text",
                f"Notes {label} body_html has no visible text after sanitization.",
            ),
        )
    return sanitized, None
