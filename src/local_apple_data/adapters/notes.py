from __future__ import annotations

import hashlib
import html as html_lib
import json
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
MAX_PREVIEW_TITLE_CHARS = 256
MAX_CREATE_BODY_CHARS = 12000
MAX_BODY_PREVIEW_CHARS = 240
PLAN_OPERATIONS = {"create"}
APPROVAL_TOKEN_PREFIX = "notes-apply:v1:"

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


def plan_notes_change(
    operation: str,
    *,
    title: str = "",
    body_text: str = "",
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create."))

    normalized_title, title_warning = _normalize_create_title(title)
    if title_warning is not None:
        warnings.append(title_warning)
    normalized_body, body_warning = _normalize_create_body(body_text)
    if body_warning is not None:
        warnings.append(body_warning)

    if warnings:
        return _plan_error(warnings)

    body_hash = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    body_preview, body_preview_truncated, _, _ = _bounded_text(
        normalized_body,
        MAX_BODY_PREVIEW_CHARS,
    )
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
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": {
            **proposed,
            "body_sha256": body_hash,
        },
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
    body_text: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path = DEFAULT_NOTES_DB,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_notes_change(operation, title=title, body_text=body_text)
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

    normalized_title, _ = _normalize_create_title(title)
    normalized_body, _ = _normalize_create_body(body_text)
    runner = script_runner or _run_osascript

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
