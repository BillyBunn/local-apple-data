from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import shutil
import sqlite3
import subprocess
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


DEFAULT_NOTES_DB = (
    Path.home()
    / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
)
DEFAULT_NOTES_CONTAINER = Path.home() / "Library/Group Containers/group.com.apple.notes"
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
NOTES_APPLESCRIPT_TIMEOUT_SECONDS = 10.0
MAX_PREVIEW_TITLE_CHARS = 256
MAX_CREATE_BODY_CHARS = 12000
MAX_BODY_PREVIEW_CHARS = 240
DEFAULT_ATTACHMENTS_LIMIT = 20
ATTACHMENT_HANDLE_PREFIX = "notes:attachment"
PLAN_OPERATIONS = {"create", "append_text"}
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


def _export_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": True,
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

    full_text = _html_to_text(html)
    content_text, truncated, total_chars, next_offset = _bounded_text(
        full_text,
        bounded_chars,
        offset=bounded_offset,
    )
    result.update(
        {
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
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_warning("notes_store_unavailable", str(exc))],
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
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "notes",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [_warning("notes_store_unavailable", str(exc))],
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
        "privacy": _export_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def plan_notes_change(
    operation: str,
    *,
    title: str = "",
    handle: str = "",
    body_text: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create or append_text."))

    normalized_title = ""
    normalized_handle = handle.strip()
    normalized_expected_sha = ""
    if normalized_operation == "create":
        normalized_title, title_warning = _normalize_create_title(title)
        if title_warning is not None:
            warnings.append(title_warning)
        if normalized_handle or expected_current_sha256.strip():
            warnings.append(
                _warning(
                    "unexpected_append_target",
                    "Notes create planning requires a title, not a note handle or current-content hash.",
                )
            )
    elif normalized_operation == "append_text":
        if title.strip():
            warnings.append(
                _warning(
                    "unexpected_title",
                    "Notes append-text planning requires a note handle, not a new title.",
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

    normalized_body, body_warning = (
        _normalize_append_body(body_text)
        if normalized_operation == "append_text"
        else _normalize_create_body(body_text)
    )
    if body_warning is not None:
        warnings.append(body_warning)

    if warnings:
        return _plan_error(warnings)

    body_hash = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    body_preview, body_preview_truncated, _, _ = _bounded_text(
        normalized_body,
        MAX_BODY_PREVIEW_CHARS,
    )
    if normalized_operation == "create":
        target = {"account": "default", "folder": "default"}
        proposed = {
            "kind": "note",
            "format": "plaintext",
            "title": normalized_title,
            "body_chars": len(normalized_body),
            "body_preview_text": body_preview,
            "body_preview_chars": len(body_preview),
            "body_preview_truncated": body_preview_truncated,
        }
    else:
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
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": _fingerprint_proposed(normalized_operation, proposed, body_hash),
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
    body_text: str = "",
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
        body_text=body_text,
        expected_current_sha256=expected_current_sha256,
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

    if normalized_operation == "append_text":
        return _apply_notes_append(
            preview,
            db_path=db_path,
            script_runner=runner,
            body_text=body_text,
            approval_fingerprint=fingerprint,
        )

    normalized_title, _ = _normalize_create_title(title)
    normalized_body, _ = _normalize_create_body(body_text)

    already_applied = _find_matching_note_content(
        normalized_title,
        normalized_body,
        db_path=db_path,
        script_runner=runner,
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
            _notes_create_script(normalized_title, normalized_body),
            NOTES_APPLESCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Notes create timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except NotesAutomationError:
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
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "notes",
        "privacy": _mutation_privacy(content_inspected=True),
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


def _normalize_append_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = _normalize_text(value)
    if not normalized:
        return "", _warning("missing_body", "Notes append-text requires non-empty body text.")
    if len(normalized) > MAX_CREATE_BODY_CHARS:
        return (
            normalized[:MAX_CREATE_BODY_CHARS],
            _warning("body_too_long", "Notes append body exceeded the maximum length."),
        )
    return normalized, None


def _normalize_sha256(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: expected_current_sha256.")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        return "", _warning("invalid_expected_sha256", "expected_current_sha256 must be a 64-character SHA-256 hex digest.")
    return normalized, None


def _fingerprint_proposed(operation: str, proposed: dict[str, Any], body_hash: str) -> dict[str, Any]:
    if operation == "create":
        return {
            **proposed,
            "body_sha256": body_hash,
        }
    return {
        **proposed,
        "append_body_sha256": body_hash,
    }


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
    except StoreUnavailableError as exc:
        return _apply_error(
            [_warning("notes_store_unavailable", str(exc))],
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
    except NotesAutomationError:
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

    normalized_body, body_warning = _normalize_append_body(body_text)
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
    except NotesAutomationError:
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


def _find_matching_note_content(
    title: str,
    body_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
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


def _read_back_created_note(
    created_id: str,
    title: str,
    body_text: str,
    *,
    db_path: Path,
    script_runner: ScriptRunner,
) -> dict[str, Any] | None:
    note_id = _note_id_from_automation_output(created_id)
    if note_id is not None:
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
    )


def _note_id_from_automation_output(value: str) -> int | None:
    match = re.search(r"\bICNote/p([0-9]+)\b", value)
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


def _notes_create_script(title: str, body_text: str) -> str:
    title_ref = _applescript_string(title)
    body_ref = _applescript_string(_notes_create_body_html(title, body_text))
    return f"""
set noteTitle to {title_ref}
set noteBody to {body_ref}
tell application "Notes"
    set createdNote to make new note with properties {{name:noteTitle, body:noteBody}}
    return id of createdNote
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


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append({"code": code, "message": message})
    return safe


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


def _automation_warning_from_output(output: str) -> dict[str, str] | None:
    normalized = output.strip()
    if not normalized.startswith(AUTOMATION_ERROR_PREFIX):
        return None
    code = normalized.removeprefix(AUTOMATION_ERROR_PREFIX)
    if code == "password_protected_note":
        return _warning("password_protected_note", "Notes append is blocked for password-protected notes.")
    if code == "shared_note":
        return _warning("shared_note_mutation_blocked", "Notes append is blocked for shared notes.")
    if code == "current_content_changed":
        return _warning("current_content_changed", "Notes target content changed before append could be applied.")
    return _warning("automation_refused", "Notes automation refused the append operation.")


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
