from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
    table_columns,
)
from .warning_safety import safe_warning_payloads


DEFAULT_MESSAGES_DB = Path.home() / "Library/Messages/chat.db"
DEFAULT_MESSAGES_ROOT = Path.home() / "Library/Messages"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MESSAGES_HELPER = PROJECT_ROOT / "scripts/messages_helper.swift"
MESSAGES_TABLES = ["chat", "message", "chat_message_join", "chat_handle_join", "handle"]
MESSAGES_ATTACHMENT_TABLES = [*MESSAGES_TABLES, "attachment", "message_attachment_join"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
DEFAULT_MESSAGES_LIMIT = 25
DEFAULT_ATTACHMENTS_LIMIT = 20
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MESSAGE_TEXT_CHARS = 2000
MAX_SEND_TEXT_CHARS = 12000
MAX_SEND_PREVIEW_CHARS = 240
MAX_SEND_FILE_BYTES = 100 * 1024 * 1024
MESSAGES_HELPER_TIMEOUT = 5.0
MESSAGES_APPLESCRIPT_TIMEOUT_SECONDS = 10.0
MESSAGES_SEND_READ_BACK_TIMEOUT_SECONDS = 8.0
MESSAGES_SEND_READ_BACK_INTERVAL_SECONDS = 0.4
CHAT_HANDLE_PREFIX = "messages:chat"
MESSAGE_ATTACHMENT_HANDLE_PREFIX = "messages:attachment"
MESSAGE_PARTICIPANT_HANDLE_PREFIX = "messages:participant"
PLAN_OPERATIONS = {"send_text", "send_file"}
APPROVAL_TOKEN_PREFIX = "messages-apply:v1:"
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


def _attachment_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "attachment_content_returned": False,
        "attachment_content_exported": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _participant_privacy(*, participant_id_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "participant_id_returned": participant_id_returned,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "detail" if participant_id_returned else "metadata",
    }


def _export_privacy(*, attachment_content_exported: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": True,
        "attachment_content_returned": False,
        "attachment_content_exported": attachment_content_exported,
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


def _messages_store_unavailable_warning() -> dict[str, str]:
    return _warning(
        "messages_store_unavailable",
        "Messages local store is unavailable or unreadable.",
    )


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


def _check_attachment_schema(connection) -> str:
    _check_schema(connection)
    require_columns(
        connection,
        "attachment",
        {
            "ROWID",
            "filename",
            "transfer_name",
            "mime_type",
            "uti",
            "total_bytes",
            "created_date",
            "start_date",
        },
    )
    require_columns(connection, "message_attachment_join", {"message_id", "attachment_id"})
    return schema_fingerprint(connection, MESSAGES_ATTACHMENT_TABLES)


def check_messages_schema(*, db_path: Path = DEFAULT_MESSAGES_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_attachment_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "messages",
            "schema_fingerprint": None,
            "tables_checked": MESSAGES_ATTACHMENT_TABLES,
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
        "tables_checked": MESSAGES_ATTACHMENT_TABLES,
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
    messages, transcript_chars, truncated, payload_warnings = _message_payloads(
        message_rows,
        bounded_chars,
    )
    result.update(
        {
            "messages": messages,
            "messages_returned": len(messages),
            "max_messages": bounded_messages,
            "transcript_chars": transcript_chars,
            "transcript_truncated": truncated,
        }
    )
    warnings = [*payload_warnings]
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


def list_message_attachments(
    handle: str,
    *,
    db_path: Path | None = None,
    messages_root: Path | None = None,
    limit: int = DEFAULT_ATTACHMENTS_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CHAT_HANDLE_PREFIX):
        return _invalid_attachment_chat_handle_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path or DEFAULT_MESSAGES_DB) as connection:
            chat_fingerprint = _check_schema(connection)
            attachment_fingerprint = _check_attachment_schema(connection)
            chat_id = _resolve_chat_id(connection, chat_fingerprint, handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "schema_fingerprint": attachment_fingerprint,
                    "privacy": _attachment_privacy(content_inspected=False),
                    "results": [],
                    "result_count": 0,
                    "warnings": [],
                }
            rows = _select_attachment_rows(connection, chat_id, bounded_limit)
    except StoreUnavailableError as exc:
        return _messages_attachment_degraded_result(exc)

    root = messages_root or DEFAULT_MESSAGES_ROOT
    results = [
        _message_attachment_metadata(
            row,
            attachment_fingerprint=attachment_fingerprint,
            chat_fingerprint=chat_fingerprint,
            chat_id=chat_id,
            messages_root=root,
        )
        for row in rows
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": attachment_fingerprint,
        "privacy": _attachment_privacy(content_inspected=False),
        "query": {"scope": "chat_attachments", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def list_message_participants(
    handle: str,
    *,
    db_path: Path | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CHAT_HANDLE_PREFIX):
        return _invalid_participant_chat_handle_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path or DEFAULT_MESSAGES_DB) as connection:
            fingerprint = _check_schema(connection)
            chat_id = _resolve_chat_id(connection, fingerprint, handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "schema_fingerprint": fingerprint,
                    "privacy": _participant_privacy(participant_id_returned=False),
                    "results": [],
                    "result_count": 0,
                    "warnings": [],
                }
            rows = _select_participants(connection, chat_id, bounded_limit)
    except StoreUnavailableError as exc:
        return _messages_participant_degraded_result(exc)

    results = [
        _message_participant_metadata(
            row,
            fingerprint=fingerprint,
            chat_id=chat_id,
            include_identifier=False,
        )
        for row in rows
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "privacy": _participant_privacy(participant_id_returned=False),
        "query": {"scope": "chat_participants", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_message_participant(
    chat_handle: str,
    participant_handle: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(chat_handle, CHAT_HANDLE_PREFIX):
        return _invalid_participant_chat_handle_result(detail=True)
    if not is_opaque_handle(participant_handle, MESSAGE_PARTICIPANT_HANDLE_PREFIX):
        return _invalid_participant_handle_result()

    try:
        with connect_readonly(db_path or DEFAULT_MESSAGES_DB) as connection:
            fingerprint = _check_schema(connection)
            chat_id = _resolve_chat_id(connection, fingerprint, chat_handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "schema_fingerprint": fingerprint,
                    "privacy": _participant_privacy(participant_id_returned=False),
                    "result": None,
                    "warnings": [],
                }
            row = _find_participant_row(
                _select_participants(connection, chat_id, None),
                fingerprint=fingerprint,
                chat_id=chat_id,
                participant_handle=participant_handle,
            )
    except StoreUnavailableError as exc:
        return _messages_participant_degraded_result(exc, detail=True)

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "messages",
            "schema_fingerprint": fingerprint,
            "privacy": _participant_privacy(participant_id_returned=False),
            "result": None,
            "warnings": [],
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "privacy": _participant_privacy(participant_id_returned=True),
        "result": _message_participant_metadata(
            row,
            fingerprint=fingerprint,
            chat_id=chat_id,
            include_identifier=True,
        ),
        "result_count": 1,
        "warnings": [],
    }


def export_message_attachment(
    chat_handle: str,
    attachment_handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    db_path: Path | None = None,
    messages_root: Path | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(chat_handle, CHAT_HANDLE_PREFIX):
        return _invalid_attachment_chat_handle_result(export=True)
    if not is_opaque_handle(attachment_handle, MESSAGE_ATTACHMENT_HANDLE_PREFIX):
        return _invalid_attachment_export_handle_result()

    try:
        with connect_readonly(db_path or DEFAULT_MESSAGES_DB) as connection:
            chat_fingerprint = _check_schema(connection)
            attachment_fingerprint = _check_attachment_schema(connection)
            chat_id = _resolve_chat_id(connection, chat_fingerprint, chat_handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "schema_fingerprint": attachment_fingerprint,
                    "privacy": _export_privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = _find_attachment_row(
                _select_attachment_rows(connection, chat_id, None),
                fingerprint=attachment_fingerprint,
                chat_id=chat_id,
                attachment_handle=attachment_handle,
            )
    except StoreUnavailableError as exc:
        return _messages_attachment_degraded_result(exc, export=True)

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "messages",
            "schema_fingerprint": attachment_fingerprint,
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    root = messages_root or DEFAULT_MESSAGES_ROOT
    result = _message_attachment_metadata(
        row,
        attachment_fingerprint=attachment_fingerprint,
        chat_fingerprint=chat_fingerprint,
        chat_id=chat_id,
        messages_root=root,
    )
    result.update(
        {
            "attachment_content_returned": False,
            "attachment_content_exported": False,
            "exported_path": "",
            "exported_filename": "",
            "exported_bytes": 0,
        }
    )
    source = _resolve_attachment_file(row["filename"], root)
    if source is None:
        return _message_attachment_export_unavailable_result(
            result,
            attachment_fingerprint,
            "messages_attachment_unavailable",
        )

    target_dir = output_dir.expanduser()
    if target_dir.exists() and not target_dir.is_dir():
        return _message_attachment_export_unavailable_result(
            result,
            attachment_fingerprint,
            "invalid_output_dir",
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_output_path(
            target_dir,
            _message_attachment_export_filename(filename, result),
        )
        shutil.copyfile(source, target)
    except OSError:
        return _message_attachment_export_unavailable_result(
            result,
            attachment_fingerprint,
            "messages_attachment_export_failed",
        )

    result.update(
        {
            "attachment_content_exported": True,
            "exported_path": str(target),
            "exported_filename": target.name,
            "exported_bytes": target.stat().st_size,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "messages",
        "schema_fingerprint": attachment_fingerprint,
        "privacy": _export_privacy(attachment_content_exported=True),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def plan_messages_change(
    operation: str,
    *,
    handle: str = "",
    body_text: str = "",
    file_path: str = "",
    db_path: Path | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation send_text or send_file."))
    if not is_opaque_handle(handle, CHAT_HANDLE_PREFIX):
        warnings.append(_warning("invalid_handle", "Messages send planning requires a messages:chat:v1 handle."))
    normalized_body = ""
    file_info: dict[str, Any] | None = None
    if normalized_operation == "send_text":
        normalized_body, body_warning = _normalize_send_body(body_text)
        if body_warning is not None:
            warnings.append(body_warning)
    elif normalized_operation == "send_file":
        file_info, file_warning = _resolve_send_file(file_path)
        if file_warning is not None:
            warnings.append(file_warning)
    if warnings:
        return _plan_error(warnings)

    try:
        with connect_readonly(db_path or DEFAULT_MESSAGES_DB) as connection:
            fingerprint = _check_schema(connection)
            chat_id = _resolve_chat_id(connection, fingerprint, handle)
            if chat_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "messages",
                    "privacy": _preview_privacy(),
                    "mode": "plan",
                    "mutation_applied": False,
                    "apply_available": False,
                    "preview": None,
                    "warnings": [],
                }
            chat_state = _select_chat_send_state(connection, chat_id)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=False, preview=True)

    if not _bounded_string(chat_state["guid"], 500):
        return _plan_error([_warning("messages_chat_not_sendable", "Selected Messages chat is missing a sendable chat id.")])

    target = {
        "handle": make_opaque_handle(CHAT_HANDLE_PREFIX, fingerprint, int(chat_state["chat_id"])),
        "display_name": _bounded_string(chat_state["display_name"], 500),
        "service_name": _bounded_string(chat_state["service_name"], 50),
        "participants_count": int(chat_state["participants_count"] or 0),
        "message_count": int(chat_state["message_count"] or 0),
        "last_message_date": _message_date(chat_state["last_message_date"]),
        "last_message_rowid": _nonnegative_int(chat_state["last_message_rowid"]),
    }
    if normalized_operation == "send_text":
        body_preview, body_preview_truncated = _bounded_text(
            normalized_body,
            MAX_SEND_PREVIEW_CHARS,
        )
        proposed = {
            "kind": "messages_send_text",
            "format": "plaintext",
            "body_chars": len(normalized_body),
            "body_preview_text": body_preview,
            "body_preview_chars": len(body_preview),
            "body_preview_truncated": body_preview_truncated,
            "attachments_permitted": False,
            "direct_recipient_send_permitted": False,
        }
        proposed_fingerprint: dict[str, Any] = {
            **proposed,
            "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
        }
    else:
        assert file_info is not None
        proposed = {
            "kind": "messages_send_file",
            "filename": file_info["filename"],
            "file_size": file_info["file_size"],
            "mime_type": file_info["mime_type"],
            "attachment_type": file_info["attachment_type"],
            "file_content_returned": False,
            "file_path_returned": False,
            "direct_recipient_send_permitted": False,
            "body_text_permitted": False,
        }
        proposed_fingerprint = {
            **proposed,
            "file_identity": file_info["identity"],
        }
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": proposed_fingerprint,
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
        "source": "messages",
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


def apply_messages_change(
    operation: str,
    *,
    handle: str = "",
    body_text: str = "",
    file_path: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    script_runner: ScriptRunner | None = None,
    read_back_timeout: float = MESSAGES_SEND_READ_BACK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    plan = plan_messages_change(
        operation,
        handle=handle,
        body_text=body_text,
        file_path=file_path,
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
            [_warning("missing_apply_confirmation", "Messages apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Messages apply approval token did not match the plan.")],
            plan=plan,
        )

    normalized_operation = operation.strip().replace("-", "_")
    is_text_send = normalized_operation == "send_text"
    normalized_body = ""
    file_info: dict[str, Any] | None = None
    if is_text_send:
        normalized_body, _ = _normalize_send_body(body_text)
    else:
        file_info, _ = _resolve_send_file(file_path)
        if file_info is None:
            return _apply_error([_warning("send_file_unavailable", "Messages send_file path is unavailable.")], plan=plan)
    resolved_db_path = db_path or DEFAULT_MESSAGES_DB
    try:
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            chat_id = _resolve_chat_id(connection, fingerprint, handle)
            if chat_id is None:
                return _apply_error([_warning("invalid_handle", "Selected Messages chat no longer exists.")], plan=plan)
            chat_state = _select_chat_send_state(connection, chat_id)
            before_rowid = _nonnegative_int(chat_state["last_message_rowid"]) or 0
            chat_guid = _bounded_string(chat_state["guid"], 500)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=False, mutation=True)

    if not chat_guid:
        return _apply_error(
            [_warning("messages_chat_not_sendable", "Selected Messages chat is missing a sendable chat id.")],
            plan=plan,
        )

    runner = script_runner or _run_osascript
    try:
        if is_text_send:
            script = _messages_send_text_script(chat_guid=chat_guid, body_text=normalized_body)
        else:
            assert file_info is not None
            script = _messages_send_file_script(chat_guid=chat_guid, file_path=file_info["resolved_path"])
        runner(script, MESSAGES_APPLESCRIPT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Messages send timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MessagesAutomationError):
        return _apply_error(
            [_warning("write_error", "Messages send could not be completed safely.")],
            plan=plan,
        )

    if is_text_send:
        read_back = _wait_for_matching_sent_message(
            chat_id,
            normalized_body,
            after_rowid=before_rowid,
            db_path=resolved_db_path,
            timeout=read_back_timeout,
        )
    else:
        assert file_info is not None
        read_back = _wait_for_matching_sent_file(
            chat_id,
            file_info,
            after_rowid=before_rowid,
            db_path=resolved_db_path,
            timeout=read_back_timeout,
        )
    if read_back is None:
        ghost = _messages_ghost_row_detected(
            after_rowid=before_rowid,
            db_path=resolved_db_path,
        )
        warning = (
            _warning("messages_send_ghost_row", "Messages automation produced an unjoined empty outgoing row.")
            if ghost
            else _warning("read_back_unavailable", "Messages send was attempted but local read-back did not confirm it.")
        )
        return _apply_error([warning], plan=plan, status="partial", mutation_applied=True)

    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
    )


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


def _select_chat_send_state(connection, chat_id: int):
    row = connection.execute(
        """
        SELECT
            c.ROWID AS chat_id,
            c.guid AS guid,
            COALESCE(c.display_name, '') AS display_name,
            c.service_name AS service_name,
            COUNT(DISTINCT chj.handle_id) AS participants_count,
            COUNT(DISTINCT m.ROWID) AS message_count,
            MAX(m.date) AS last_message_date,
            MAX(m.ROWID) AS last_message_rowid
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
    message_columns = table_columns(connection, "message")
    attributed_body_expr = "m.attributedBody" if "attributedBody" in message_columns else "NULL"
    rows = connection.execute(
        f"""
        SELECT
            m.ROWID AS message_id,
            m.text AS text,
            {attributed_body_expr} AS attributed_body,
            m.date AS message_date,
            m.is_from_me AS is_from_me,
            m.service AS service
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ?
          AND (
            (m.text IS NOT NULL AND m.text != '')
            OR ({attributed_body_expr} IS NOT NULL AND length({attributed_body_expr}) > 0)
          )
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()
    return list(reversed(rows))


def _select_participants(connection, chat_id: int, limit: int | None):
    limit_clause = "" if limit is None else "LIMIT ?"
    params: tuple[int, ...] = (chat_id,) if limit is None else (chat_id, limit)
    return connection.execute(
        f"""
        SELECT
            h.ROWID AS participant_id,
            h.id AS participant_identifier,
            h.service AS participant_service,
            COUNT(DISTINCT cmj.message_id) AS message_count,
            MAX(m.date) AS last_message_date
        FROM chat_handle_join chj
        JOIN handle h ON h.ROWID = chj.handle_id
        LEFT JOIN message m ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj
          ON cmj.message_id = m.ROWID
         AND cmj.chat_id = chj.chat_id
        WHERE chj.chat_id = ?
        GROUP BY h.ROWID
        ORDER BY COALESCE(MAX(m.date), 0) DESC, h.ROWID ASC
        {limit_clause}
        """,
        params,
    ).fetchall()


def _select_new_outgoing_messages(connection, chat_id: int, after_rowid: int):
    message_columns = table_columns(connection, "message")
    attributed_body_expr = "m.attributedBody" if "attributedBody" in message_columns else "NULL"
    return connection.execute(
        f"""
        SELECT
            m.ROWID AS message_id,
            m.text AS text,
            {attributed_body_expr} AS attributed_body,
            m.date AS message_date,
            m.is_from_me AS is_from_me,
            m.service AS service
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ?
          AND m.ROWID > ?
          AND COALESCE(m.is_from_me, 0) = 1
        ORDER BY m.ROWID DESC
        LIMIT 20
        """,
        (chat_id, after_rowid),
    ).fetchall()


def _select_new_outgoing_attachments(connection, chat_id: int, after_rowid: int):
    attachment_columns = table_columns(connection, "attachment")
    is_sticker_expr = "a.is_sticker" if "is_sticker" in attachment_columns else "0"
    return connection.execute(
        f"""
        SELECT
            m.ROWID AS message_id,
            m.date AS message_date,
            m.is_from_me AS is_from_me,
            m.service AS service,
            a.ROWID AS attachment_id,
            a.filename AS filename,
            a.transfer_name AS transfer_name,
            a.mime_type AS mime_type,
            a.uti AS uti,
            a.total_bytes AS total_bytes,
            a.created_date AS created_date,
            a.start_date AS start_date,
            {is_sticker_expr} AS is_sticker
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN message_attachment_join maj ON maj.message_id = m.ROWID
        JOIN attachment a ON a.ROWID = maj.attachment_id
        WHERE cmj.chat_id = ?
          AND m.ROWID > ?
          AND COALESCE(m.is_from_me, 0) = 1
        ORDER BY m.ROWID DESC, a.ROWID DESC
        LIMIT 20
        """,
        (chat_id, after_rowid),
    ).fetchall()


def _select_attachment_rows(connection, chat_id: int, limit: int | None):
    attachment_columns = table_columns(connection, "attachment")
    is_sticker_expr = "a.is_sticker" if "is_sticker" in attachment_columns else "0"
    limit_clause = "" if limit is None else "LIMIT ?"
    params: tuple[int, ...] = (chat_id,) if limit is None else (chat_id, limit)
    return connection.execute(
        f"""
        SELECT
            a.ROWID AS attachment_id,
            a.filename AS filename,
            a.transfer_name AS transfer_name,
            a.mime_type AS mime_type,
            a.uti AS uti,
            a.total_bytes AS total_bytes,
            a.created_date AS created_date,
            a.start_date AS start_date,
            {is_sticker_expr} AS is_sticker,
            m.date AS message_date,
            m.is_from_me AS is_from_me,
            m.service AS service
        FROM chat_message_join cmj
        JOIN message_attachment_join maj ON maj.message_id = cmj.message_id
        JOIN attachment a ON a.ROWID = maj.attachment_id
        JOIN message m ON m.ROWID = cmj.message_id
        WHERE cmj.chat_id = ?
        ORDER BY COALESCE(m.date, a.created_date, a.start_date, 0) DESC, a.ROWID DESC
        {limit_clause}
        """,
        params,
    ).fetchall()


def _find_attachment_row(
    rows: list[Any],
    *,
    fingerprint: str,
    chat_id: int,
    attachment_handle: str,
):
    for row in rows:
        identity = _message_attachment_identity(row)
        if opaque_handle_matches(
            attachment_handle,
            MESSAGE_ATTACHMENT_HANDLE_PREFIX,
            fingerprint,
            chat_id,
            int(row["attachment_id"]),
            identity["filename"],
            identity["mime_type"],
            identity["file_size"],
        ):
            return row
    return None


def _find_participant_row(
    rows: list[Any],
    *,
    fingerprint: str,
    chat_id: int,
    participant_handle: str,
):
    for row in rows:
        if opaque_handle_matches(
            participant_handle,
            MESSAGE_PARTICIPANT_HANDLE_PREFIX,
            fingerprint,
            chat_id,
            int(row["participant_id"]),
            _normalize_participant_identifier(row["participant_identifier"]),
            _bounded_string(row["participant_service"], 50),
        ):
            return row
    return None


def _resolve_chat_id(connection, fingerprint: str, handle: str) -> int | None:
    rows = connection.execute("SELECT ROWID AS chat_id FROM chat").fetchall()
    for row in rows:
        chat_id = int(row["chat_id"])
        if opaque_handle_matches(handle, CHAT_HANDLE_PREFIX, fingerprint, chat_id):
            return chat_id
    return None


def _wait_for_matching_sent_message(
    chat_id: int,
    body_text: str,
    *,
    after_rowid: int,
    db_path: Path,
    timeout: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        match = _find_matching_sent_message(
            chat_id,
            body_text,
            after_rowid=after_rowid,
            db_path=db_path,
        )
        if match is not None or time.monotonic() >= deadline:
            return match
        time.sleep(MESSAGES_SEND_READ_BACK_INTERVAL_SECONDS)


def _find_matching_sent_message(
    chat_id: int,
    body_text: str,
    *,
    after_rowid: int,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            rows = _select_new_outgoing_messages(connection, chat_id, after_rowid)
    except StoreUnavailableError:
        return None

    decoded, _ = _decode_attributed_body_texts(rows)
    expected = _normalize_for_compare(body_text)
    for row in rows:
        text = _bounded_string(row["text"], MAX_SEND_TEXT_CHARS)
        text_source = "text"
        if not text:
            text = decoded.get(int(row["message_id"]), "")
            text_source = "attributed_body" if text else "unavailable"
        if _normalize_for_compare(text) != expected:
            continue
        return {
            "chat_handle_confirmed": True,
            "message_date": _message_date(row["message_date"]),
            "direction": "sent",
            "service": _bounded_string(row["service"], 50),
            "text_source": text_source,
            "body_chars": len(text),
            "body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    return None


def _wait_for_matching_sent_file(
    chat_id: int,
    file_info: dict[str, Any],
    *,
    after_rowid: int,
    db_path: Path,
    timeout: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        match = _find_matching_sent_file(
            chat_id,
            file_info,
            after_rowid=after_rowid,
            db_path=db_path,
        )
        if match is not None or time.monotonic() >= deadline:
            return match
        time.sleep(MESSAGES_SEND_READ_BACK_INTERVAL_SECONDS)


def _find_matching_sent_file(
    chat_id: int,
    file_info: dict[str, Any],
    *,
    after_rowid: int,
    db_path: Path,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(db_path) as connection:
            _check_attachment_schema(connection)
            rows = _select_new_outgoing_attachments(connection, chat_id, after_rowid)
    except StoreUnavailableError:
        return None

    expected_name = str(file_info["filename"])
    expected_size = int(file_info["file_size"])
    for row in rows:
        identity = _message_attachment_identity(row)
        if identity["filename"] != expected_name:
            continue
        row_size = identity["file_size"]
        if row_size is not None and int(row_size) != expected_size:
            continue
        return {
            "chat_handle_confirmed": True,
            "message_date": _message_date(row["message_date"]),
            "direction": "sent",
            "service": _bounded_string(row["service"], 50),
            "attachment_filename": identity["filename"],
            "attachment_type": _message_attachment_type(identity["mime_type"], identity["filename"]),
            "mime_type": identity["mime_type"],
            "file_size": row_size,
            "attachment_content_returned": False,
            "attachment_content_exported": False,
            "file_path_returned": False,
        }
    return None


def _messages_ghost_row_detected(*, after_rowid: int, db_path: Path) -> bool:
    try:
        with connect_readonly(db_path) as connection:
            rows = connection.execute(
                """
                SELECT m.ROWID AS message_id
                FROM message m
                LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                WHERE m.ROWID > ?
                  AND COALESCE(m.is_from_me, 0) = 1
                  AND cmj.chat_id IS NULL
                  AND (m.text IS NULL OR m.text = '')
                LIMIT 1
                """,
                (after_rowid,),
            ).fetchall()
    except StoreUnavailableError:
        return False
    return bool(rows)


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


def _message_participant_metadata(
    row,
    *,
    fingerprint: str,
    chat_id: int,
    include_identifier: bool,
) -> dict[str, Any]:
    identifier = _normalize_participant_identifier(row["participant_identifier"])
    service = _bounded_string(row["participant_service"], 50)
    result: dict[str, Any] = {
        "handle": make_opaque_handle(
            MESSAGE_PARTICIPANT_HANDLE_PREFIX,
            fingerprint,
            chat_id,
            int(row["participant_id"]),
            identifier,
            service,
        ),
        "service": service,
        "message_count": int(row["message_count"] or 0),
        "last_message_date": _message_date(row["last_message_date"]),
        "participant_id_returned": False,
    }
    if include_identifier:
        result["participant_id"] = _bounded_string(identifier, 500)
        result["participant_id_returned"] = True
    return result


def _normalize_participant_identifier(value: Any) -> str:
    return str(value or "").strip()


def _message_payloads(
    rows: list[Any],
    max_chars: int,
) -> tuple[list[dict[str, Any]], int, bool, list[dict[str, str]]]:
    messages: list[dict[str, Any]] = []
    used = 0
    truncated = False
    decoded, decode_warning = _decode_attributed_body_texts(rows)
    for row in rows:
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        text_source = "text"
        original = _bounded_string(row["text"], MESSAGE_TEXT_CHARS)
        if not original:
            original = decoded.get(int(row["message_id"]), "")
            text_source = "attributed_body" if original else "unavailable"
        if not original:
            continue
        text = _bounded_string(original, min(MESSAGE_TEXT_CHARS, remaining))
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
                "text_source": text_source,
            }
        )
    warnings = [decode_warning] if decode_warning is not None else []
    return messages, used, truncated, warnings


def _decode_attributed_body_texts(rows: list[Any]) -> tuple[dict[int, str], dict[str, str] | None]:
    items: list[dict[str, str]] = []
    for row in rows:
        if _bounded_string(row["text"], MESSAGE_TEXT_CHARS):
            continue
        blob = row["attributed_body"]
        if blob is None:
            continue
        raw = bytes(blob)
        if not raw:
            continue
        items.append(
            {
                "id": str(int(row["message_id"])),
                "base64": base64.b64encode(raw).decode("ascii"),
            }
        )
    if not items:
        return {}, None

    try:
        return _decode_attributed_body_batch(items), None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        decoded: dict[int, str] = {}
        for item in items:
            try:
                decoded.update(_decode_attributed_body_batch([item]))
            except (OSError, subprocess.TimeoutExpired, ValueError):
                continue
        return decoded, _warning(
            "messages_attributed_body_unavailable",
            "One or more Messages attributedBody values could not be decoded safely.",
        )


def _decode_attributed_body_batch(items: list[dict[str, str]]) -> dict[int, str]:
    payload = _run_messages_helper(
        {
            "items": items,
            "maxChars": MESSAGE_TEXT_CHARS,
            "mode": "decode_attributed_bodies",
        },
        timeout=MESSAGES_HELPER_TIMEOUT,
    )

    decoded: dict[int, str] = {}
    for result in payload.get("results", []):
        if not isinstance(result, dict):
            continue
        if result.get("status") != "ok":
            continue
        try:
            message_id = int(result.get("id"))
        except (TypeError, ValueError):
            continue
        text = _bounded_string(result.get("text"), MESSAGE_TEXT_CHARS)
        if text:
            decoded[message_id] = text
    return decoded


def _run_messages_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(MESSAGES_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Messages helper failed.")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict) or parsed.get("status") != "ok":
        raise ValueError("Messages helper returned invalid JSON.")
    return parsed


def _message_attachment_metadata(
    row,
    *,
    attachment_fingerprint: str,
    chat_fingerprint: str,
    chat_id: int,
    messages_root: Path,
) -> dict[str, Any]:
    identity = _message_attachment_identity(row)
    source = _resolve_attachment_file(row["filename"], messages_root)
    file_size = identity["file_size"]
    if file_size is None and source is not None:
        try:
            file_size = source.stat().st_size
        except OSError:
            file_size = None
    return {
        "handle": make_opaque_handle(
            MESSAGE_ATTACHMENT_HANDLE_PREFIX,
            attachment_fingerprint,
            chat_id,
            int(row["attachment_id"]),
            identity["filename"],
            identity["mime_type"],
            identity["file_size"],
        ),
        "chat_handle": make_opaque_handle(CHAT_HANDLE_PREFIX, chat_fingerprint, chat_id),
        "filename": identity["filename"],
        "mime_type": identity["mime_type"],
        "uti": identity["uti"],
        "file_size": file_size,
        "created_date": _message_date(row["created_date"]),
        "start_date": _message_date(row["start_date"]),
        "message_date": _message_date(row["message_date"]),
        "direction": "sent" if bool(row["is_from_me"]) else "received",
        "service": _bounded_string(row["service"], 50),
        "is_sticker": bool(row["is_sticker"]),
        "attachment_type": _message_attachment_type(identity["mime_type"], identity["filename"]),
        "media_status": "available" if source is not None else "unavailable",
        "remote_status": "local_or_unknown" if source is not None else "not_local_or_purged",
        "attachment_content_returned": False,
        "attachment_content_exported": False,
    }


def _message_attachment_identity(row) -> dict[str, Any]:
    filename = _attachment_display_filename(row["transfer_name"], row["filename"])
    return {
        "filename": filename,
        "mime_type": _bounded_string(row["mime_type"], 300) or "application/octet-stream",
        "uti": _bounded_string(row["uti"], 300),
        "file_size": _nonnegative_int(row["total_bytes"]),
    }


def _attachment_display_filename(transfer_name: Any, filename: Any) -> str:
    for candidate in (transfer_name, filename):
        text = _bounded_string(candidate, 1000).strip()
        if not text:
            continue
        name = Path(text.replace("\\", "/")).name
        if name:
            return _bounded_string(name, 500)
    return ""


def _resolve_attachment_file(filename: Any, messages_root: Path) -> Path | None:
    text = _bounded_string(filename, 2000).strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme == "file":
        text = unquote(parsed.path)
    elif parsed.scheme:
        return None
    else:
        text = unquote(text)

    root = messages_root.expanduser().resolve(strict=False)
    raw_path = Path(text.replace("\\", "/")).expanduser()
    candidates: list[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(root / raw_path)
        parts = raw_path.parts
        if "Attachments" in parts:
            index = parts.index("Attachments")
            candidates.append(root / Path(*parts[index:]))

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _message_attachment_type(mime_type: Any, filename: Any) -> str:
    content_type = _bounded_string(mime_type, 300).lower()
    suffix = Path(_bounded_string(filename, 300)).suffix.lower()
    if content_type.startswith("image/") or suffix in {
        ".gif",
        ".heic",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }:
        return "image"
    if content_type.startswith("video/") or suffix in {".m4v", ".mov", ".mp4"}:
        return "video"
    if content_type.startswith("audio/") or suffix in {
        ".aif",
        ".aiff",
        ".m4a",
        ".mp3",
        ".wav",
    }:
        return "audio"
    if content_type in {
        "application/pdf",
        "application/msword",
        "application/rtf",
        "text/plain",
    } or suffix in {".doc", ".docx", ".pdf", ".rtf", ".txt"}:
        return "document"
    return "other"


def _message_attachment_export_filename(value: str | None, metadata: dict[str, Any]) -> str:
    fallback = str(metadata.get("filename") or "").strip()
    if not fallback:
        fallback = f"message-attachment{_message_attachment_extension(metadata)}"
    candidate = _bounded_string(value, 200).strip() if value else fallback
    name = Path(candidate.replace("\\", "/")).name
    suffix = Path(name).suffix or Path(fallback).suffix or _message_attachment_extension(metadata)
    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    if not safe_stem:
        safe_stem = "message-attachment"
    return f"{safe_stem[:120]}{suffix.lower()}"


def _message_attachment_extension(metadata: dict[str, Any]) -> str:
    filename_suffix = Path(str(metadata.get("filename") or "")).suffix
    if filename_suffix:
        return filename_suffix.lower()
    content_type = str(metadata.get("mime_type") or "").lower()
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
        "image/heic": ".heic",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "text/plain": ".txt",
    }.get(content_type, ".bin")


def _unique_output_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 1000):
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    raise OSError("could not allocate unique output path")


def _bounded_text(value: str, limit: int) -> tuple[str, bool]:
    bounded = value[:limit]
    return bounded, len(value) > len(bounded)


def _normalize_send_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", normalized).strip()
    if not normalized:
        return "", _warning("missing_body_text", "Messages send requires non-empty body_text.")
    if len(normalized) > MAX_SEND_TEXT_CHARS:
        return "", _warning("body_too_long", "Messages send body_text exceeded the maximum length.")
    return normalized, None


def _resolve_send_file(value: str) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    raw = str(value).strip()
    if not raw:
        return None, _warning("missing_file_path", "Messages send_file requires a local file path.")
    try:
        resolved = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None, _warning("send_file_unavailable", "Messages send_file path is unavailable.")
    try:
        stat = resolved.stat()
    except OSError:
        return None, _warning("send_file_unavailable", "Messages send_file path is unavailable.")
    if not resolved.is_file():
        return None, _warning("send_file_not_file", "Messages send_file path must point to a regular file.")
    if stat.st_size <= 0:
        return None, _warning("send_file_empty", "Messages send_file path must point to a non-empty file.")
    if stat.st_size > MAX_SEND_FILE_BYTES:
        return None, _warning("send_file_too_large", "Messages send_file exceeded the maximum file size.")
    filename = _bounded_string(resolved.name, 500).strip()
    if not filename:
        return None, _warning("send_file_unavailable", "Messages send_file path is unavailable.")
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    identity = {
        "resolved_path": str(resolved),
        "file_size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "inode": int(getattr(stat, "st_ino", 0)),
        "device": int(getattr(stat, "st_dev", 0)),
    }
    return {
        "resolved_path": str(resolved),
        "filename": filename,
        "file_size": int(stat.st_size),
        "mime_type": _bounded_string(mime_type, 300),
        "attachment_type": _message_attachment_type(mime_type, filename),
        "identity": identity,
    }, None


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\r\n", "\n").replace("\r", "\n")).strip()


def _nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer >= 0 else None


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


def _invalid_attachment_chat_handle_result(*, export: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _export_privacy() if export else _attachment_privacy(content_inspected=False),
        "result": None if export else None,
        "results": [] if not export else None,
        "result_count": 0 if not export else None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected messages:chat:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_participant_chat_handle_result(*, detail: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _participant_privacy(participant_id_returned=False),
        "result": None if detail else None,
        "results": [] if not detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected messages:chat:v1 opaque handle from search output.",
            )
        ],
    }


def _plan_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
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
        "source": "messages",
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
        "source": "messages",
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


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        payload,
        _warning,
        fallback_message="Messages warning detail was redacted.",
    )


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"messages-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _messages_send_text_script(*, chat_guid: str, body_text: str) -> str:
    return "\n".join(
        [
            f"set messageText to {_applescript_string(body_text)}",
            f"set chatIdentifier to {_applescript_string(chat_guid)}",
            'tell application "Messages"',
            "    set targetChat to chat id chatIdentifier",
            "    send messageText to targetChat",
            "end tell",
        ]
    ) + "\n"


def _messages_send_file_script(*, chat_guid: str, file_path: str) -> str:
    return "\n".join(
        [
            f"set attachmentPath to {_applescript_string(file_path)}",
            "set attachmentFile to POSIX file attachmentPath",
            f"set chatIdentifier to {_applescript_string(chat_guid)}",
            'tell application "Messages"',
            "    set targetChat to chat id chatIdentifier",
            "    send attachmentFile to targetChat",
            "end tell",
        ]
    ) + "\n"


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class MessagesAutomationError(RuntimeError):
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
        raise MessagesAutomationError() from None
    if completed.returncode != 0:
        raise MessagesAutomationError()
    return completed.stdout


def _invalid_attachment_export_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected messages:attachment:v1 opaque handle from Messages attachment list output.",
            )
        ],
    }


def _invalid_participant_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "messages",
        "privacy": _participant_privacy(participant_id_returned=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected messages:participant:v1 opaque handle from participant list output.",
            )
        ],
    }


def _store_degraded_result(
    _exc: StoreUnavailableError,
    *,
    content: bool,
    preview: bool = False,
    mutation: bool = False,
) -> dict[str, Any]:
    if mutation:
        privacy = _mutation_privacy(content_inspected=False)
    elif preview:
        privacy = _preview_privacy()
    else:
        privacy = _content_privacy(content_inspected=False) if content else _privacy()
    result = {
        "schema_version": 1,
        "status": "degraded",
        "source": "messages",
        "privacy": privacy,
        "result": None,
        "warnings": [_messages_store_unavailable_warning()],
    }
    if mutation:
        result.update({"mode": "apply", "mutation_applied": False})
    elif preview:
        result.update(
            {
                "mode": "plan",
                "mutation_applied": False,
                "apply_available": False,
                "preview": None,
            }
        )
    elif not content:
        result.update({"results": [], "result_count": 0})
    return result


def _messages_attachment_degraded_result(
    _exc: StoreUnavailableError,
    *,
    export: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "messages",
        "privacy": _export_privacy() if export else _attachment_privacy(content_inspected=False),
        "results": [] if not export else None,
        "result": None,
        "result_count": 0 if not export else None,
        "warnings": [_messages_store_unavailable_warning()],
    }


def _messages_participant_degraded_result(
    _exc: StoreUnavailableError,
    *,
    detail: bool = False,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "status": "degraded",
        "source": "messages",
        "schema_fingerprint": None,
        "privacy": _participant_privacy(participant_id_returned=False),
        "warnings": [_messages_store_unavailable_warning()],
    }
    if detail:
        return {**base, "result": None}
    return {**base, "results": [], "result_count": 0}


def _message_attachment_export_unavailable_result(
    result: dict[str, Any] | None,
    fingerprint: str,
    code: str,
) -> dict[str, Any]:
    messages = {
        "invalid_output_dir": "Messages attachment export output path was not a directory.",
        "messages_attachment_export_failed": "Messages attachment could not be exported safely.",
        "messages_attachment_unavailable": "Messages attachment bytes are not locally available for export.",
    }
    return {
        "schema_version": 1,
        "status": "attachment_unavailable"
        if code == "messages_attachment_unavailable"
        else "error",
        "source": "messages",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(),
        "result": result,
        "warnings": [
            _warning(code, messages.get(code, "Messages attachment export was unavailable."))
        ],
    }


def _nonnegative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text).strip()
    return text[: max(1, min(max_chars, MAX_CONTENT_CHARS))]
