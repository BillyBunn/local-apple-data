from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
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
MESSAGES_HELPER_TIMEOUT = 5.0
CHAT_HANDLE_PREFIX = "messages:chat"
MESSAGE_ATTACHMENT_HANDLE_PREFIX = "messages:attachment"


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


def _export_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": True,
        "attachment_content_returned": False,
        "attachment_content_exported": True,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
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
        "privacy": _export_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": [],
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


def _messages_attachment_degraded_result(
    exc: StoreUnavailableError,
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
        "warnings": [_warning("messages_store_unavailable", str(exc))],
    }


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
