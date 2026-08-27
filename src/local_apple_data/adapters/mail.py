from __future__ import annotations

import copy
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse

from ..handles import (
    int_handle_matches,
    is_int_handle,
    is_opaque_handle,
    make_int_handle,
    make_opaque_handle,
    opaque_handle_matches,
    resolve_int_handles,
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


MAIL_ROOT_RELATIVE = Path("Library/Mail")
DEFAULT_MAIL_RELATIVE = MAIL_ROOT_RELATIVE / "V10/MailData/Envelope Index"
DEFAULT_MAIL_DB = Path.home() / DEFAULT_MAIL_RELATIVE
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAIL_APPLESCRIPT_TIMEOUT_SECONDS = 10.0
MAX_PREVIEW_SUBJECT_CHARS = 256
MAX_DRAFT_BODY_CHARS = 12000
MAX_DRAFT_BODY_PREVIEW_CHARS = 240
MAX_RECIPIENTS_PER_FIELD = 20
MAX_DRAFT_ATTACHMENTS = 5
MAX_DRAFT_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_DRAFT_ATTACHMENT_TOTAL_BYTES = 25 * 1024 * 1024
DEFAULT_ATTACHMENTS_LIMIT = 20
DEFAULT_MAIL_DISCOVERY_LIMIT = 20
MAX_MAIL_DISCOVERY_LIMIT = 50
# Raised 200 -> 2000 in v1.183: the one-walk message-file index dropped per-row cost
# from ~700ms (full-tree glob) to ~1-3ms, and the max_seconds budget bounds the worst case.
MAX_MAIL_DISCOVERY_SCAN_ROWS = 2000
DEFAULT_MAIL_SCAN_BUDGET_SECONDS = 20.0
MAX_MAIL_SCAN_BUDGET_SECONDS = 120.0
DEFAULT_MAIL_SNIPPET_CHARS = 240
MAX_MAIL_SNIPPET_CHARS = 500
MAX_MAIL_ATTACHMENT_CONTENT_BYTES = 10 * 1024 * 1024
MAX_MAIL_ATTACHMENT_EXTRACTED_CHARS = 200_000
MAIL_ATTACHMENT_TEXT_TIMEOUT_SECONDS = 10.0
MAIL_ATTACHMENT_OCR_TIMEOUT_SECONDS = 60.0
MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS = 5
MAX_MAIL_FTS_BUILD_MESSAGES = 1000
MAX_MAIL_FTS_SEARCH_LIMIT = 50
MAX_MAIL_FTS_SEARCH_SCAN_ROWS = 200
MAX_MAIL_FTS_SNIPPET_CHARS = 500
MAIL_FTS_INDEX_VERSION = 2
MAIL_FTS_INDEX_ENV = "LOCAL_APPLE_DATA_MAIL_FTS_INDEX"
DEFAULT_MAIL_FTS_INDEX = Path.home() / ".local/state/local-apple-data/mail-fts.sqlite"
MAIL_TEMPLATE_STATE_ENV = "LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE"
DEFAULT_MAIL_TEMPLATE_STATE = Path.home() / ".local/state/local-apple-data/mail-templates.json"
SOURCE_FORWARD_VERIFICATION = "mail_attachment_count_pre_send"
ATTACHMENT_HANDLE_PREFIX = "mail:attachment"
MAILBOX_HANDLE_PREFIX = "mail:mailbox"
SENDER_HANDLE_PREFIX = "mail:sender"
SIGNATURE_HANDLE_PREFIX = "mail:signature"
TEMPLATE_HANDLE_PREFIX = "mail:template"
DEFAULT_MAILBOX_LIMIT = 20
DEFAULT_SENDER_LIMIT = 20
DEFAULT_SIGNATURE_LIMIT = 20
DEFAULT_TEMPLATE_LIMIT = 20
MAX_TEMPLATE_NAME_CHARS = 120
SYNTHETIC_MAIL_TEST_PREFIX = "LAD-TEST-"
MAX_SYNTHETIC_MAILBOX_NAME_CHARS = 120
MAX_MAIL_READ_BACK_CANDIDATES = 200
MAIL_SENT_READ_BACK_ATTEMPTS = 15
MAIL_SENT_READ_BACK_DELAY_SECONDS = 2.0
MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS = 10
MAIL_CLEANUP_ABSENCE_READ_BACK_DELAY_SECONDS = 0.3
MAIL_CLEANUP_BACKGROUND_IDLE_ATTEMPTS = 30
MAIL_CLEANUP_BACKGROUND_IDLE_DELAY_SECONDS = 1.0
MAIL_TRIAGE_READ_BACK_ATTEMPTS = 10
MAIL_TRIAGE_READ_BACK_DELAY_SECONDS = 0.2
MAX_TRIAGE_HEADER_BYTES = 64 * 1024
MAX_BULK_TRIAGE_MESSAGES = 20
MAX_BODY_LINK_MIME_BYTES = 10 * 1024 * 1024
MAX_BODY_LINK_ENDPOINTS = 5
MAX_BODY_LINK_VISIBLE_CONTEXT_CHARS = 150
PLAN_OPERATIONS = {
    "create_draft",
    "send_message",
    "reply_message",
    "reply_all_message",
    "forward_message",
    "mark_read",
    "mark_unread",
    "flag_message",
    "unflag_message",
    "archive_message",
    "trash_message",
    "move_message",
}
# v1.32/v1.37/v1.40/v1.41: reversible triage on exact existing messages.
# The RFC Message-ID must be recovered from the selected local .emlx file; the
# Envelope Index message_id column is not sufficient. The generated AppleScript
# either sets `read status` / `flagged status` or moves to the selected
# account-scoped Archive/Trash/exact target mailbox. It never sends,
# permanently deletes, erases, or empties mail. Bulk triage is capped and binds
# every exact handle/current state/target into one approval fingerprint.
TRIAGE_OPERATIONS = {
    "mark_read",
    "mark_unread",
    "flag_message",
    "unflag_message",
    "archive_message",
    "trash_message",
    "move_message",
}
READ_STATUS_OPERATIONS = {"mark_read", "mark_unread"}
FLAG_STATUS_OPERATIONS = {"flag_message", "unflag_message"}
MOVE_OPERATIONS = {"archive_message", "trash_message", "move_message"}
MAILBOX_MANAGEMENT_OPERATIONS = {"create_mailbox", "rename_mailbox", "delete_mailbox"}
MAIL_CLEANUP_OPERATIONS = {"permanent_delete_message", "empty_trash", "empty_junk"}
REPLY_OPERATIONS = {"reply_message", "reply_all_message"}
FORWARD_OPERATIONS = {"forward_message"}
LOCAL_ATTACHMENT_OPERATIONS = {
    "create_draft",
    "send_message",
    "reply_message",
    "reply_all_message",
    "forward_message",
}
SENDER_SELECTION_OPERATIONS = LOCAL_ATTACHMENT_OPERATIONS
SIGNATURE_SELECTION_OPERATIONS = LOCAL_ATTACHMENT_OPERATIONS
CONTENT_OPERATIONS = {"create_draft", "send_message"}
APPROVAL_TOKEN_PREFIX = "mail-apply:v1:"
UNSUPPORTED_MOVE_TARGET_TOKENS = {
    "basura",
    "bin",
    "bulk",
    "corbeille",
    "delete",
    "deleted",
    "eliminados",
    "junk",
    "lixeira",
    "papelera",
    "papierkorb",
    "poubelle",
    "spam",
    "trash",
}

MAIL_TABLES = ["messages", "subjects", "mailboxes"]
ScriptRunner = Callable[[str, float], str]
SUPPORTED_MAIL_SEARCH_SCOPES = {
    "subject",
    "from",
    "to",
    "cc",
    "bcc",
    "body",
    "attachment_filename",
}
MAIL_SEARCH_SCOPE_ORDER = [
    "subject",
    "from",
    "to",
    "cc",
    "bcc",
    "body",
    "attachment_filename",
]
SUPPORTED_MAIL_FTS_SCOPES = {
    *SUPPORTED_MAIL_SEARCH_SCOPES,
    "attachment_content",
}
MAIL_FTS_SCOPE_ORDER = [
    *MAIL_SEARCH_SCOPE_ORDER,
    "attachment_content",
]
_LIST_ENDPOINT_PATTERN = re.compile(r"<([^<>]*)>")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_RFC8058_POST_PATTERN = re.compile(
    r"List-Unsubscribe\s*=\s*One-Click",
    flags=re.IGNORECASE,
)
_BODY_LINK_EXPLICIT_TEXT_PATTERN = re.compile(
    r"(?:\bunsubscrib(?:e|ed|ing)\b|\bopt[\s-]*out\b|\bstop\s+receiving\b)",
    flags=re.IGNORECASE,
)
_BODY_LINK_HREF_PATTERN = re.compile(
    r"(?:unsubscribe|opt[\s_-]*out)",
    flags=re.IGNORECASE,
)
_BODY_LINK_CLICK_HERE_PATTERN = re.compile(r"\bclick\s+here\b", flags=re.IGNORECASE)
_BODY_LINK_DENY_HREF_PATTERN = re.compile(
    r"(?:manage|preferences?|login|log[\s_-]*in|resubscribe)",
    flags=re.IGNORECASE,
)


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


def _unsubscribe_metadata_privacy(
    *,
    header_inspected: bool,
    endpoint_urls_returned: bool = False,
    message_body_inspected: bool = False,
) -> dict[str, bool | str]:
    return {
        "content_inspected": message_body_inspected,
        "header_inspected": header_inspected,
        "message_body_inspected": message_body_inspected,
        "endpoint_urls_returned": endpoint_urls_returned,
        "raw_headers_returned": False,
        "unrelated_headers_returned": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "exact_header_detail",
    }


def _snippet_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content_snippet",
    }


def _attachment_privacy(
    *,
    content_inspected: bool,
    content_snippet_returned: bool = False,
) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "attachment_content_returned": False,
        "attachment_content_snippet_returned": content_snippet_returned,
        "attachment_content_exported": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content_snippet" if content_snippet_returned else "metadata",
    }


def _fts_privacy(
    *,
    content_inspected: bool,
    durable_index_written: bool = False,
    content_snippet_returned: bool = False,
) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "durable_index_written": durable_index_written,
        "durable_personal_content_cache": durable_index_written,
        "content_snippet_returned": content_snippet_returned,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "durable_index" if durable_index_written else "content_snippet",
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


def _preview_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
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


def _mail_schema_unavailable_warning() -> dict[str, str]:
    return _warning("mail_schema_unavailable", "Mail schema is unavailable or unsupported.")


def _mail_store_unavailable_warning() -> dict[str, str]:
    return _warning("mail_store_unavailable", "Mail local store is unavailable or unreadable.")


def _check_schema(connection) -> str:
    require_columns(
        connection,
        "messages",
        {"ROWID", "subject", "mailbox", "date_received", "date_sent", "read", "flagged", "deleted"},
    )
    require_columns(connection, "subjects", {"ROWID", "subject"})
    require_columns(connection, "mailboxes", {"ROWID", "url"})
    return schema_fingerprint(connection, MAIL_TABLES)


def _mail_version_number(path: Path) -> int:
    version = path.parent.parent.name
    if version.startswith("V") and version[1:].isdigit():
        return int(version[1:])
    return -1


def discover_mail_db_path(*, home: Path | None = None) -> Path:
    home = home or Path.home()
    mail_root = home / MAIL_ROOT_RELATIVE
    candidates = sorted(
        (path for path in mail_root.glob("V*/MailData/Envelope Index") if path.is_file()),
        key=lambda path: (_mail_version_number(path), path.as_posix()),
    )
    return candidates[-1] if candidates else home / DEFAULT_MAIL_RELATIVE


def mail_db_relative_path(*, home: Path | None = None) -> Path:
    home = home or Path.home()
    path = discover_mail_db_path(home=home)
    try:
        return path.relative_to(home)
    except ValueError:
        return DEFAULT_MAIL_RELATIVE


def _resolve_db_path(db_path: Path | None) -> Path:
    return db_path if db_path is not None else discover_mail_db_path()


def check_mail_schema(*, db_path: Path | None = None) -> dict[str, Any]:
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "mail",
            "schema_fingerprint": None,
            "tables_checked": MAIL_TABLES,
            "warnings": [_mail_schema_unavailable_warning()],
        }
    return {
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "tables_checked": MAIL_TABLES,
        "warnings": [],
    }


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "empty_query",
                "message": "Mail metadata search requires a non-empty subject query.",
            }
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            {
                "code": "broad_query",
                "message": "Mail metadata search requires at least two letters or digits.",
            }
        ],
    }


def _search_error(
    code: str,
    message: str,
    *,
    privacy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _search_error_payload([_warning(code, message)], privacy=privacy or _privacy())


def _search_error_payload(
    warnings: list[dict[str, str]],
    *,
    privacy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": privacy,
        "results": [],
        "result_count": 0,
        "warnings": warnings,
    }


def _search_store_unavailable_result(*, privacy: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "mail",
        "privacy": privacy,
        "results": [],
        "result_count": 0,
        "warnings": [_mail_store_unavailable_warning()],
    }


def _mail_date_bounds(
    *,
    after: str | int | float | None,
    before: str | int | float | None,
    require_bound: bool,
) -> tuple[dict[str, float], list[dict[str, str]]]:
    bounds: dict[str, float] = {}
    warnings: list[dict[str, str]] = []
    after_value, after_warning = _parse_mail_date_bound(after, label="after", end_of_day=False)
    before_value, before_warning = _parse_mail_date_bound(before, label="before", end_of_day=True)
    if after_warning is not None:
        warnings.append(after_warning)
    if before_warning is not None:
        warnings.append(before_warning)
    if after_value is not None:
        bounds["after"] = after_value
    if before_value is not None:
        bounds["before"] = before_value
    if require_bound and not bounds:
        warnings.append(
            _warning(
                "date_range_required",
                "Mail body and attachment discovery requires an after or before date bound.",
            )
        )
    if after_value is not None and before_value is not None and after_value > before_value:
        warnings.append(
            _warning(
                "invalid_date_range",
                "Mail search after date must be earlier than or equal to before date.",
            )
        )
    return bounds, warnings


def _parse_mail_date_bound(
    value: str | int | float | None,
    *,
    label: str,
    end_of_day: bool,
) -> tuple[float | None, dict[str, str] | None]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    if not text:
        return None, None
    try:
        return float(text), None
    except ValueError:
        pass
    try:
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if date_only and end_of_day:
            parsed = parsed + timedelta(days=1) - timedelta(milliseconds=1)
        return parsed.timestamp(), None
    except ValueError:
        return (
            None,
            _warning(
                "invalid_date_bound",
                f"Mail search {label} must be an ISO date/time or Mail timestamp.",
            ),
        )


def _mail_cursor_offset(cursor: str | int | None) -> tuple[int, dict[str, str] | None]:
    if cursor is None:
        return 0, None
    text = str(cursor).strip()
    if not text:
        return 0, None
    try:
        value = int(text)
    except ValueError:
        return 0, _warning("invalid_cursor", "Mail search cursor must be an opaque pagination token from a prior result.")
    if value < 0:
        return 0, _warning("invalid_cursor", "Mail search cursor must be zero or greater.")
    return value, None


def _select_mail_discovery_rows(
    connection,
    *,
    bounds: dict[str, float],
    cursor_offset: int,
    scan_limit: int,
):
    date_expr = "COALESCE(m.date_received, m.date_sent, 0)"
    conditions = ["COALESCE(m.deleted, 0) = 0"]
    params: list[Any] = []
    if "after" in bounds:
        conditions.append(f"{date_expr} >= ?")
        params.append(bounds["after"])
    if "before" in bounds:
        conditions.append(f"{date_expr} <= ?")
        params.append(bounds["before"])
    params.extend([scan_limit, cursor_offset])
    where_clause = " AND ".join(conditions)
    return connection.execute(
        f"""
        SELECT
            m.ROWID AS rowid,
            s.subject AS subject,
            mb.url AS mailbox_url,
            m.date_received AS date_received,
            m.date_sent AS date_sent,
            m.read AS read,
            m.flagged AS flagged,
            m.deleted AS deleted,
            m.size AS size
        FROM messages m
        LEFT JOIN subjects s ON m.subject = s.ROWID
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE {where_clause}
        ORDER BY {date_expr} DESC, m.ROWID DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def _next_cursor(
    cursor_offset: int,
    scanned_count: int,
    row_count: int,
    result_count: int,
    bounded_limit: int,
    scan_limit: int = MAX_MAIL_DISCOVERY_SCAN_ROWS,
    *,
    stopped_early: bool = False,
) -> str:
    if scanned_count <= 0:
        return ""
    if stopped_early and scanned_count < row_count:
        return str(cursor_offset + scanned_count)
    if result_count >= bounded_limit or row_count >= scan_limit:
        return str(cursor_offset + scanned_count)
    return ""


def _bounded_scan_seconds(max_seconds: float | int | None) -> float:
    try:
        value = float(max_seconds) if max_seconds is not None else DEFAULT_MAIL_SCAN_BUDGET_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_MAIL_SCAN_BUDGET_SECONDS
    if value != value:  # NaN
        return DEFAULT_MAIL_SCAN_BUDGET_SECONDS
    return max(1.0, min(value, MAX_MAIL_SCAN_BUDGET_SECONDS))


def _count_mail_rows_in_bounds(connection, bounds: dict[str, float]) -> int:
    date_expr = "COALESCE(m.date_received, m.date_sent, 0)"
    conditions = ["COALESCE(m.deleted, 0) = 0"]
    params: list[Any] = []
    if "after" in bounds:
        conditions.append(f"{date_expr} >= ?")
        params.append(bounds["after"])
    if "before" in bounds:
        conditions.append(f"{date_expr} <= ?")
        params.append(bounds["before"])
    row = connection.execute(
        f"SELECT COUNT(*) AS total FROM messages m WHERE {' AND '.join(conditions)}",
        params,
    ).fetchone()
    return int(row["total"]) if row is not None else 0


def _scan_stats_block(
    *,
    scanned_count: int,
    range_total: int,
    started_monotonic: float,
    stopped_reason: str,
) -> dict[str, Any]:
    return {
        "scanned": scanned_count,
        "range_total": range_total,
        "elapsed_ms": int((time.monotonic() - started_monotonic) * 1000),
        "stopped_reason": stopped_reason,
    }


def _scan_time_budget_warning() -> dict[str, str]:
    return _warning(
        "scan_time_budget_reached",
        "Mail scan stopped at the max_seconds time budget; continue with next_cursor.",
    )


def _read_message_file_bytes(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> bytes | None:
    message_path = _find_message_file(mail_root, rowid, index=index)
    if message_path is None:
        return None
    try:
        return message_path.read_bytes()
    except OSError:
        return None


def _mail_row_content_text(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> str | None:
    raw = _read_message_file_bytes(mail_root, rowid, index=index)
    if raw is None:
        return None
    try:
        return _extract_text_from_emlx(raw)
    except ValueError:
        return None


def _mail_fts_content_state_sha256(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> str:
    raw = _read_message_file_bytes(mail_root, rowid, index=index)
    if raw is None:
        return ""
    return hashlib.sha256(raw).hexdigest()


def _match_snippet(
    text: str,
    match_index: int,
    match_length: int,
    max_chars: int,
) -> str:
    normalized = _normalize_text(text)
    bounded = max(1, max_chars)
    start = max(0, match_index - max(0, (bounded - match_length) // 2))
    end = min(len(normalized), start + bounded)
    start = max(0, end - bounded)
    return _redact_mail_snippet(normalized[start:end], bounded)


def _mail_body_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_text(text)).strip()


def _redact_mail_snippet(value: str, max_chars: int) -> str:
    def replace_email(match: re.Match[str]) -> str:
        return _mask_email_address(match.group(0))

    redacted = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        replace_email,
        value,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(?<!\w)(?:~|/Users|/private|/var|/tmp|/Volumes|/Library|/System|/Applications)(?:/[^\s,;:'\")\]]+)+",
        "<redacted-path>",
        redacted,
    )
    redacted = re.sub(
        r"\b(?:rowid|row id|message[_ -]?id|account[_ -]?id|account identifier|raw id)\s*[:=#]?\s*[\w.-]{4,}\b",
        "<redacted-id>",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "<redacted-id>",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"\b[0-9a-f]{16,}\b",
        "<redacted-id>",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})(?!\w)",
        "<redacted-phone>",
        redacted,
    )
    return _bounded_string(redacted, max_chars)


def _normalize_mail_search_scopes(
    scopes: list[str] | None,
) -> tuple[list[str], dict[str, str] | None]:
    if not scopes:
        return list(MAIL_SEARCH_SCOPE_ORDER), None
    expanded: list[str] = []
    for scope in scopes:
        expanded.extend(part.strip().lower().replace("-", "_") for part in str(scope).split(","))
    normalized: list[str] = []
    invalid: list[str] = []
    for scope in expanded:
        if not scope:
            continue
        if scope not in SUPPORTED_MAIL_SEARCH_SCOPES:
            invalid.append(scope)
            continue
        if scope not in normalized:
            normalized.append(scope)
    if invalid or not normalized:
        return (
            [],
            _warning(
                "invalid_scope",
                "Advanced Mail search scope must be one of subject, from, to, cc, bcc, body, or attachment_filename.",
            ),
        )
    return [scope for scope in MAIL_SEARCH_SCOPE_ORDER if scope in normalized], None


def _normalize_mail_fts_scopes(
    scopes: list[str] | None,
) -> tuple[list[str], dict[str, str] | None]:
    if not scopes:
        return list(MAIL_FTS_SCOPE_ORDER), None
    expanded: list[str] = []
    for scope in scopes:
        expanded.extend(part.strip().lower().replace("-", "_") for part in str(scope).split(","))
    normalized: list[str] = []
    invalid: list[str] = []
    for scope in expanded:
        if not scope:
            continue
        if scope not in SUPPORTED_MAIL_FTS_SCOPES:
            invalid.append(scope)
            continue
        if scope not in normalized:
            normalized.append(scope)
    if invalid or not normalized:
        return (
            [],
            _warning(
                "invalid_scope",
                "Mail FTS scope must be one of subject, from, to, cc, bcc, body, attachment_filename, or attachment_content.",
            ),
        )
    return [scope for scope in MAIL_FTS_SCOPE_ORDER if scope in normalized], None


def _mail_fts_index_path(index_path: Path | None) -> Path:
    if index_path is not None:
        return index_path.expanduser()
    configured = os.environ.get(MAIL_FTS_INDEX_ENV, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MAIL_FTS_INDEX


def _mail_fts_index_is_default(index_path: Path) -> bool:
    return index_path.expanduser() == DEFAULT_MAIL_FTS_INDEX


def _mail_fts_index_ref(index_path: Path) -> str:
    return f"mail-fts:{hashlib.sha256(str(index_path).encode('utf-8')).hexdigest()[:12]}"


def _mail_fts_index_files(index_path: Path) -> tuple[Path, ...]:
    index_path = index_path.expanduser()
    return (
        index_path,
        index_path.with_name(f"{index_path.name}-wal"),
        index_path.with_name(f"{index_path.name}-shm"),
        index_path.with_name(f"{index_path.name}-journal"),
    )


def _validate_mail_fts_directory_chain(directory: Path) -> None:
    current = directory.expanduser()
    if not current.is_absolute():
        current = Path.cwd() / current
    checked: set[Path] = set()
    while True:
        if current in checked:
            raise OSError("Mail FTS index parent cycle refused")
        checked.add(current)
        if current.is_symlink():
            raise OSError("Mail FTS index parent must not contain symlinks")
        if current.exists() and not current.is_dir():
            raise OSError("Mail FTS index parent must be a real directory")
        if current == current.parent:
            break
        current = current.parent


def _validate_mail_fts_index_target(index_path: Path) -> None:
    if index_path.is_symlink():
        raise OSError("Mail FTS index path must not be a symlink")
    if index_path.exists() and not index_path.is_file():
        raise OSError("Mail FTS index path must be a regular file")
    parent = index_path.parent
    _validate_mail_fts_directory_chain(parent)
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    _validate_mail_fts_directory_chain(parent)
    if not parent.is_dir():
        raise OSError("Mail FTS index parent must be a real directory")


def _validate_existing_mail_fts_index(index_path: Path) -> None:
    if index_path.is_symlink() or not index_path.is_file():
        raise OSError("Mail FTS index path must be a regular file")
    _validate_mail_fts_directory_chain(index_path.parent)


def _remove_mail_fts_index_files(index_path: Path) -> None:
    index_path = index_path.expanduser()
    _validate_mail_fts_index_target(index_path)
    index_files = _mail_fts_index_files(index_path)
    for candidate in index_files:
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
            raise OSError("Mail FTS index sidecar path must be a regular file")
    for candidate in index_files:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _connect_mail_fts_index(index_path: Path) -> sqlite3.Connection:
    index_path = index_path.expanduser()
    _validate_mail_fts_index_target(index_path)
    if _mail_fts_index_is_default(index_path):
        try:
            index_path.parent.chmod(0o700)
        except OSError:
            pass
    connection = sqlite3.connect(index_path)
    if index_path.is_symlink() or (index_path.exists() and not index_path.is_file()):
        connection.close()
        raise OSError("Mail FTS index path must be a regular file")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA secure_delete=ON")
    if _mail_fts_index_is_default(index_path):
        try:
            index_path.chmod(0o600)
        except OSError:
            pass
    return connection


def _connect_mail_fts_index_readonly(index_path: Path) -> sqlite3.Connection:
    index_path = index_path.expanduser()
    _validate_existing_mail_fts_index(index_path)
    uri = f"file:{quote(str(index_path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_mail_fts_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_fts_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_fts_docs (
            doc_rowid INTEGER PRIMARY KEY,
            mail_rowid INTEGER NOT NULL,
            schema_fingerprint TEXT NOT NULL,
            message_handle TEXT NOT NULL,
            subject TEXT,
            mailbox_name TEXT,
            mailbox_ref TEXT,
            date_received REAL,
            date_sent REAL,
            content_state_sha256 TEXT NOT NULL DEFAULT '',
            attachment_count INTEGER NOT NULL DEFAULT 0,
            attachment_names_json TEXT NOT NULL DEFAULT '[]',
            attachment_types_json TEXT NOT NULL DEFAULT '[]',
            indexed_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS mail_fts USING fts5(
            subject,
            from_header,
            to_header,
            cc_header,
            bcc_header,
            body,
            attachment_names,
            attachment_content,
            tokenize='unicode61'
        )
        """
    )
    version_row = connection.execute(
        "SELECT value FROM mail_fts_meta WHERE key = 'schema_version'"
    ).fetchone()
    existing_version = str(version_row["value"]) if version_row is not None else ""
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(mail_fts_docs)").fetchall()
    }
    if "content_state_sha256" not in columns:
        connection.execute(
            "ALTER TABLE mail_fts_docs ADD COLUMN content_state_sha256 TEXT NOT NULL DEFAULT ''"
        )
    if "attachment_types_json" not in columns:
        connection.execute(
            "ALTER TABLE mail_fts_docs ADD COLUMN attachment_types_json TEXT NOT NULL DEFAULT '[]'"
        )
    if existing_version and existing_version != str(MAIL_FTS_INDEX_VERSION):
        _reset_mail_fts_index(connection, vacuum=True)
        return
    connection.execute(
        "INSERT OR REPLACE INTO mail_fts_meta(key, value) VALUES ('schema_version', ?)",
        (str(MAIL_FTS_INDEX_VERSION),),
    )
    connection.commit()


MAIL_FTS_META_BUILD_KEYS = (
    "build_state",
    "built_after",
    "built_before",
    "checkpoint_cursor",
    "last_build_at",
    "envelope_fingerprint",
)


def _set_mail_fts_meta(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    for key, value in values.items():
        connection.execute(
            "INSERT OR REPLACE INTO mail_fts_meta(key, value) VALUES (?, ?)",
            (key, str(value)),
        )


def _get_mail_fts_meta(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM mail_fts_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def _validate_mail_fts_schema(connection: sqlite3.Connection) -> None:
    version_row = connection.execute(
        "SELECT value FROM mail_fts_meta WHERE key = 'schema_version'"
    ).fetchone()
    if version_row is None or str(version_row["value"]) != str(MAIL_FTS_INDEX_VERSION):
        raise sqlite3.DatabaseError("unsupported Mail FTS index schema version")
    connection.execute(
        """
        SELECT
            mail_rowid,
            schema_fingerprint,
            content_state_sha256,
            attachment_count,
            attachment_names_json,
            attachment_types_json
        FROM mail_fts_docs
        LIMIT 0
        """
    )
    connection.execute(
        """
        SELECT
            rowid,
            subject,
            from_header,
            to_header,
            cc_header,
            bcc_header,
            body,
            attachment_names,
            attachment_content
        FROM mail_fts
        LIMIT 0
        """
    )


def _reset_mail_fts_index(connection: sqlite3.Connection, *, vacuum: bool = False) -> None:
    connection.execute("PRAGMA secure_delete=ON")
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    except sqlite3.Error:
        pass
    connection.execute("PRAGMA journal_mode=DELETE").fetchone()
    connection.execute("DROP TABLE IF EXISTS mail_fts")
    connection.execute("DROP TABLE IF EXISTS mail_fts_docs")
    connection.execute("DROP TABLE IF EXISTS mail_fts_meta")
    if vacuum:
        connection.commit()
        connection.execute("VACUUM")
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        except sqlite3.Error:
            pass
    _ensure_mail_fts_schema(connection)


def _mail_fts_header_text(message) -> dict[str, str]:
    if message is None:
        return {"from": "", "to": "", "cc": "", "bcc": ""}
    return {
        "from": _mail_fts_address_text(message.get_all("From", [])),
        "to": _mail_fts_address_text(message.get_all("To", [])),
        "cc": _mail_fts_address_text(message.get_all("Cc", [])),
        "bcc": _mail_fts_address_text(message.get_all("Bcc", [])),
    }


def _mail_fts_address_text(values: list[str]) -> str:
    parts = [str(value) for value in values]
    for name, address in getaddresses(values):
        if name:
            parts.append(name)
        normalized = _normalize_sender_email(address)
        if normalized:
            parts.append(normalized)
    return _mail_body_search_text(" ".join(parts))


def _upsert_mail_fts_row(
    connection: sqlite3.Connection,
    *,
    row,
    fingerprint: str,
    content_state_sha256: str,
    header_text: dict[str, str],
    body_text: str,
    attachment_names: list[str],
    attachment_types: list[str],
    attachment_count: int,
    attachment_text: str,
) -> None:
    rowid = int(row["rowid"])
    metadata = _row_to_metadata(row)
    safe_attachment_names = [
        _bounded_string(name, 200)
        for name in dict.fromkeys(attachment_names)
        if name
    ][:MAX_MAIL_DISCOVERY_LIMIT]
    safe_attachment_types = [
        _bounded_string(name, 200)
        for name in dict.fromkeys(attachment_types)
        if name
    ][:MAX_MAIL_DISCOVERY_LIMIT]
    connection.execute("DELETE FROM mail_fts WHERE rowid = ?", (rowid,))
    connection.execute("DELETE FROM mail_fts_docs WHERE doc_rowid = ?", (rowid,))
    connection.execute(
        """
        INSERT INTO mail_fts_docs(
            doc_rowid,
            mail_rowid,
            schema_fingerprint,
            message_handle,
            subject,
            mailbox_name,
            mailbox_ref,
            date_received,
            date_sent,
            content_state_sha256,
            attachment_count,
            attachment_names_json,
            attachment_types_json,
            indexed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            rowid,
            fingerprint,
            metadata["handle"],
            metadata.get("subject") or "",
            metadata.get("mailbox_name") or "",
            metadata.get("mailbox_ref") or "",
            metadata.get("date_received"),
            metadata.get("date_sent"),
            _bounded_string(content_state_sha256, 128),
            max(0, int(attachment_count)),
            json.dumps(safe_attachment_names, ensure_ascii=True),
            json.dumps(safe_attachment_types, ensure_ascii=True),
            int(datetime.now(tz=timezone.utc).timestamp()),
        ),
    )
    connection.execute(
        """
        INSERT INTO mail_fts(
            rowid,
            subject,
            from_header,
            to_header,
            cc_header,
            bcc_header,
            body,
            attachment_names,
            attachment_content
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            str(metadata.get("subject") or ""),
            header_text.get("from", ""),
            header_text.get("to", ""),
            header_text.get("cc", ""),
            header_text.get("bcc", ""),
            _mail_body_search_text(body_text),
            _mail_body_search_text(" ".join([*safe_attachment_names, *safe_attachment_types])),
            _mail_body_search_text(attachment_text),
        ),
    )


def _mail_fts_match_query(query: str) -> str:
    tokens = re.findall(r"[\w@.+-]+", query, flags=re.UNICODE)
    if not tokens:
        tokens = [query]
    return " AND ".join(f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens[:8])


def _select_mail_fts_rows(
    connection: sqlite3.Connection,
    fts_query: str,
    *,
    bounds: dict[str, float],
    fingerprint: str,
    cursor_offset: int,
    limit: int,
) -> list[sqlite3.Row]:
    date_expr = "COALESCE(d.date_received, d.date_sent, 0)"
    conditions = ["mail_fts MATCH ?", "d.schema_fingerprint = ?"]
    params: list[Any] = [fts_query, fingerprint]
    if "after" in bounds:
        conditions.append(f"{date_expr} >= ?")
        params.append(bounds["after"])
    if "before" in bounds:
        conditions.append(f"{date_expr} <= ?")
        params.append(bounds["before"])
    params.extend([limit, cursor_offset])
    where_clause = " AND ".join(conditions)
    return connection.execute(
        f"""
        SELECT
            f.rowid AS fts_rowid,
            f.subject AS subject_text,
            f.from_header,
            f.to_header,
            f.cc_header,
            f.bcc_header,
            f.body,
            f.attachment_names,
            f.attachment_content,
            d.*
        FROM mail_fts f
        JOIN mail_fts_docs d ON d.doc_rowid = f.rowid
        WHERE {where_clause}
        ORDER BY {date_expr} DESC, d.mail_rowid DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def _mail_row_matches_date_bounds(row, bounds: dict[str, float]) -> bool:
    raw_date = row["date_received"] if row["date_received"] is not None else row["date_sent"]
    try:
        date_value = float(raw_date if raw_date is not None else 0)
    except (TypeError, ValueError):
        date_value = 0.0
    if "after" in bounds and date_value < float(bounds["after"]):
        return False
    if "before" in bounds and date_value > float(bounds["before"]):
        return False
    return True


def _mail_fts_stale_count(connection: sqlite3.Connection, fingerprint: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM mail_fts_docs WHERE schema_fingerprint != ?",
        (fingerprint,),
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def _mail_fts_matched_scopes(
    indexed,
    query: str,
    scopes: list[str],
) -> list[str]:
    columns = {
        "subject": "subject_text",
        "from": "from_header",
        "to": "to_header",
        "cc": "cc_header",
        "bcc": "bcc_header",
        "body": "body",
        "attachment_filename": "attachment_names",
        "attachment_content": "attachment_content",
    }
    matched = [
        scope
        for scope in scopes
        if _mail_fts_column_matches(str(indexed[columns[scope]] or ""), query)
    ]
    return matched


def _mail_fts_column_matches(value: str, query: str) -> bool:
    haystack = _mail_body_search_text(value).casefold()
    needle = _mail_body_search_text(query).casefold()
    if needle and needle in haystack:
        return True
    tokens = [token.casefold() for token in re.findall(r"[\w@.+-]+", query, flags=re.UNICODE)]
    return bool(tokens) and all(token in haystack for token in tokens)


def _mail_fts_result_snippet(
    indexed,
    query: str,
    matched_scopes: list[str],
    max_chars: int,
) -> tuple[str, str]:
    preferred = [
        "body",
        "attachment_content",
        "subject",
        "from",
        "to",
        "cc",
        "bcc",
        "attachment_filename",
    ]
    columns = {
        "subject": "subject_text",
        "from": "from_header",
        "to": "to_header",
        "cc": "cc_header",
        "bcc": "bcc_header",
        "body": "body",
        "attachment_filename": "attachment_names",
        "attachment_content": "attachment_content",
    }
    for scope in preferred:
        if scope not in matched_scopes:
            continue
        value = str(indexed[columns[scope]] or "")
        match_index, match_length = _mail_fts_match_position(value, query)
        if match_index >= 0:
            return scope, _match_snippet(value, match_index, match_length, max_chars)
    return "", ""


def _mail_fts_match_position(value: str, query: str) -> tuple[int, int]:
    normalized = _mail_body_search_text(value)
    folded = normalized.casefold()
    needle = _mail_body_search_text(query).casefold()
    if needle:
        index = folded.find(needle)
        if index >= 0:
            return index, len(needle)
    for token in re.findall(r"[\w@.+-]+", query, flags=re.UNICODE):
        folded_token = token.casefold()
        index = folded.find(folded_token)
        if index >= 0:
            return index, len(folded_token)
    return -1, 0


def _safe_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [_bounded_string(str(item), 200) for item in parsed if item]


def _matched_header_scopes(message, scopes: list[str], query_key: str) -> list[str]:
    matched: list[str] = []
    header_map = {
        "from": "From",
        "to": "To",
        "cc": "Cc",
        "bcc": "Bcc",
    }
    for scope, header in header_map.items():
        if scope not in scopes:
            continue
        raw_values = message.get_all(header, [])
        searchable_parts = [str(value) for value in raw_values]
        searchable_parts.extend(
            address
            for _name, address in getaddresses(raw_values)
            if _normalize_sender_email(address)
        )
        if query_key in " ".join(searchable_parts).casefold():
            matched.append(scope)
    return matched


def _safe_header_search_metadata(message) -> dict[str, Any]:
    return {
        "from": _masked_address_metadata(message.get_all("From", [])),
        "to": _masked_address_metadata(message.get_all("To", [])),
        "cc": _masked_address_metadata(message.get_all("Cc", [])),
        "bcc": _masked_address_metadata(message.get_all("Bcc", [])),
        "message_id_ref": _message_id_ref(_bounded_string(message.get("Message-ID", ""), 300)),
        "message_id_returned": False,
        "full_headers_returned": False,
        "full_email_returned": False,
    }


def _mailbox_metadata(raw_url: str | None) -> dict[str, str | None]:
    if not raw_url:
        return {
            "mailbox_name": None,
            "mailbox_path": None,
            "mailbox_ref": None,
            "account_ref": None,
        }

    parsed = urlparse(raw_url)
    path = unquote(parsed.path).strip("/")
    mailbox_name = path.split("/")[-1] if path else "mailbox"
    mailbox_ref = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:12]
    account_ref = hashlib.sha256(parsed.netloc.encode("utf-8")).hexdigest()[:12] if parsed.netloc else None
    return {
        "mailbox_name": mailbox_name,
        "mailbox_path": path or "mailbox",
        "mailbox_ref": f"mailbox:{mailbox_ref}",
        "account_ref": f"account:{account_ref}" if account_ref else None,
    }


def search_mail_mailboxes(
    query: str,
    *,
    db_path: Path | None = None,
    limit: int = DEFAULT_MAILBOX_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("empty_query", "Mail mailbox search requires a non-empty mailbox query.")
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("broad_query", "Mail mailbox search requires at least two letters or digits.")
            ],
        }

    bounded_limit = max(1, min(limit, 50))
    normalized_query = query.casefold()
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_mailbox_rows(connection)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_mail_store_unavailable_warning()],
        }

    results = []
    for row in rows:
        parsed = _parse_mailbox_url(row["url"])
        if parsed is None:
            continue
        if normalized_query not in parsed["mailbox_name"].casefold():
            continue
        results.append(_mailbox_target_metadata(parsed, fingerprint))
        if len(results) >= bounded_limit:
            break
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "mailbox_name", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_mail_mailbox(handle: str, *, db_path: Path | None = None) -> dict[str, Any]:
    if not is_opaque_handle(handle, MAILBOX_HANDLE_PREFIX):
        return _invalid_mailbox_handle_result()
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
            parsed = _resolve_mailbox_handle(connection, fingerprint, handle)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [_mail_store_unavailable_warning()],
        }

    return {
        "schema_version": 1,
        "status": "ok" if parsed is not None else "not_found",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": _mailbox_target_metadata(parsed, fingerprint) if parsed is not None else None,
        "warnings": [],
    }


def list_mail_mailbox_messages(
    handle: str,
    *,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    db_path: Path | None = None,
    limit: int = DEFAULT_MAIL_DISCOVERY_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, MAILBOX_HANDLE_PREFIX):
        return _search_error(
            "invalid_mailbox_handle",
            "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
        )
    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    if bound_warnings:
        return _search_error_payload(bound_warnings, privacy=_privacy())

    bounded_limit = max(1, min(limit, MAX_MAIL_DISCOVERY_LIMIT))
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            mailbox_target = _resolve_mailbox_handle(connection, fingerprint, handle)
            if mailbox_target is None:
                return _search_error(
                    "invalid_mailbox_handle",
                    "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
                )
            date_expr = "COALESCE(m.date_received, m.date_sent, 0)"
            conditions = ["COALESCE(m.deleted, 0) = 0", "mb.url = ?"]
            params: list[Any] = [mailbox_target["mailbox_url"]]
            if "after" in bounds:
                conditions.append(f"{date_expr} >= ?")
                params.append(bounds["after"])
            if "before" in bounds:
                conditions.append(f"{date_expr} <= ?")
                params.append(bounds["before"])
            params.append(bounded_limit)
            rows = connection.execute(
                f"""
                SELECT
                    m.ROWID AS rowid,
                    s.subject AS subject,
                    mb.url AS mailbox_url,
                    m.date_received AS date_received,
                    m.date_sent AS date_sent,
                    m.read AS read,
                    m.flagged AS flagged,
                    m.deleted AS deleted,
                    m.size AS size
                FROM messages m
                LEFT JOIN subjects s ON m.subject = s.ROWID
                LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
                WHERE {" AND ".join(conditions)}
                ORDER BY {date_expr} DESC, m.ROWID DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_mail_store_unavailable_warning()],
        }

    content_root = _mail_content_root(resolved_db_path)
    content_statuses = _message_content_statuses(
        content_root,
        [int(row["rowid"]) for row in rows],
    )
    results = [
        _row_to_metadata(
            row,
            content_status=content_statuses.get(int(row["rowid"]), "unknown"),
        )
        for row in rows
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {
            "scope": "selected_mailbox_messages",
            "limit": bounded_limit,
            "mailbox_filter": "exact_handle",
            "mailbox_ref": mailbox_target["mailbox_ref"],
            "after": bounds.get("after"),
            "before": bounds.get("before"),
        },
        "mailbox": _mailbox_target_metadata(mailbox_target, fingerprint),
        "results": results,
        "result_count": len(results),
        "content_returned": False,
        "raw_identifier_returned": False,
        "raw_path_returned": False,
        "warnings": [],
    }


def plan_mail_mailbox_change(
    operation: str,
    *,
    sender_handle: str = "",
    mailbox_handle: str = "",
    mailbox_name: str = "",
    new_mailbox_name: str = "",
    db_path: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in MAILBOX_MANAGEMENT_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create_mailbox, rename_mailbox, or delete_mailbox.",
            )
        )

    sender_identity: dict[str, str] | None = None
    sender_metadata: dict[str, Any] | None = None
    parsed_mailbox: dict[str, str] | None = None
    fingerprint = ""
    current_message_count = 0

    if normalized_operation == "create_mailbox":
        if mailbox_handle.strip():
            warnings.append(
                _warning("unexpected_mailbox_handle", "Mail synthetic mailbox creation uses a sender_handle account target.")
            )
        if new_mailbox_name.strip():
            warnings.append(
                _warning("unexpected_new_mailbox_name", "Mail synthetic mailbox creation uses mailbox_name, not new_mailbox_name.")
            )
        normalized_mailbox_name, name_warning = _normalize_synthetic_mailbox_name(mailbox_name)
        if name_warning is not None:
            warnings.append(name_warning)
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            warnings.append(sender_warning)
        if sender_identity is not None and normalized_mailbox_name:
            try:
                with connect_readonly(_resolve_db_path(db_path)) as connection:
                    _check_schema(connection)
                    if _mailbox_name_exists_for_account(
                        connection,
                        account_id=sender_identity["account_id"],
                        mailbox_name=normalized_mailbox_name,
                    ):
                        warnings.append(
                            _warning("mailbox_already_exists", "A Mail mailbox with that synthetic name already exists.")
                        )
            except StoreUnavailableError:
                # Mail.app apply still performs a public-automation existence check.
                pass
    else:
        if sender_handle.strip():
            warnings.append(
                _warning("unexpected_sender_handle", "Mail synthetic mailbox rename/delete uses an exact mailbox handle.")
            )
        if mailbox_name.strip():
            warnings.append(
                _warning("unexpected_mailbox_name", "Mail synthetic mailbox rename/delete derives the current name from the handle.")
            )
        if not is_opaque_handle(mailbox_handle, MAILBOX_HANDLE_PREFIX):
            warnings.append(
                _warning("invalid_mailbox_handle", "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.")
            )
        try:
            with connect_readonly(_resolve_db_path(db_path)) as connection:
                fingerprint = _check_schema(connection)
                parsed_mailbox = _resolve_mailbox_handle(connection, fingerprint, mailbox_handle)
                if parsed_mailbox is None and is_opaque_handle(mailbox_handle, MAILBOX_HANDLE_PREFIX):
                    warnings.append(_warning("mailbox_not_found", "Mail mailbox handle did not resolve to a live mailbox."))
                elif parsed_mailbox is not None:
                    mailbox_warning = _validate_synthetic_mailbox_target(parsed_mailbox)
                    if mailbox_warning is not None:
                        warnings.append(mailbox_warning)
                    current_message_count = _mailbox_message_count(connection, parsed_mailbox["mailbox_url"])
                    if current_message_count != 0:
                        warnings.append(
                            _warning(
                                "mailbox_not_empty",
                                "Mail synthetic mailbox rename/delete requires an empty LAD-TEST-* mailbox.",
                            )
                        )
        except StoreUnavailableError:
            warnings.append(_mail_store_unavailable_warning())

        if normalized_operation == "rename_mailbox":
            normalized_new_mailbox_name, new_name_warning = _normalize_synthetic_mailbox_name(new_mailbox_name)
            if new_name_warning is not None:
                warnings.append(new_name_warning)
            if parsed_mailbox is not None and normalized_new_mailbox_name:
                try:
                    with connect_readonly(_resolve_db_path(db_path)) as connection:
                        _check_schema(connection)
                        if _mailbox_name_exists_for_account(
                            connection,
                            account_id=parsed_mailbox["account_id"],
                            mailbox_name=normalized_new_mailbox_name,
                        ):
                            warnings.append(
                                _warning("mailbox_already_exists", "A Mail mailbox with the new synthetic name already exists.")
                            )
                except StoreUnavailableError:
                    pass
        elif new_mailbox_name.strip():
            warnings.append(
                _warning("unexpected_new_mailbox_name", "Mail synthetic mailbox deletion does not accept new_mailbox_name.")
            )

    if warnings:
        return _plan_error(warnings)

    if normalized_operation == "create_mailbox":
        assert sender_identity is not None
        assert sender_metadata is not None
        normalized_mailbox_name, _ = _normalize_synthetic_mailbox_name(mailbox_name)
        account_ref = sender_metadata["account_ref"]
        proposed = {
            "kind": "mail_mailbox_management",
            "operation": normalized_operation,
            "account_ref": account_ref,
            "mailbox_name": normalized_mailbox_name,
            "synthetic_name_required": SYNTHETIC_MAIL_TEST_PREFIX,
            "expected_message_count": 0,
            "raw_identifier_returned": False,
            "account_identifier_returned": False,
        }
        fingerprint_payload = {
            "operation": normalized_operation,
            "account_ref": account_ref,
            "mailbox_name": normalized_mailbox_name,
        }
    elif normalized_operation == "rename_mailbox":
        assert parsed_mailbox is not None
        normalized_new_mailbox_name, _ = _normalize_synthetic_mailbox_name(new_mailbox_name)
        proposed = {
            "kind": "mail_mailbox_management",
            "operation": normalized_operation,
            "mailbox_handle": mailbox_handle.strip(),
            "mailbox_ref": parsed_mailbox["mailbox_ref"],
            "account_ref": parsed_mailbox["account_ref"],
            "current_mailbox_name": parsed_mailbox["mailbox_name"],
            "new_mailbox_name": normalized_new_mailbox_name,
            "expected_message_count": current_message_count,
            "synthetic_name_required": SYNTHETIC_MAIL_TEST_PREFIX,
            "raw_identifier_returned": False,
            "account_identifier_returned": False,
        }
        fingerprint_payload = {
            "operation": normalized_operation,
            "mailbox_handle": mailbox_handle.strip(),
            "mailbox_ref": parsed_mailbox["mailbox_ref"],
            "new_mailbox_name": normalized_new_mailbox_name,
            "message_count": current_message_count,
            "schema_fingerprint": fingerprint,
        }
    else:
        assert parsed_mailbox is not None
        proposed = {
            "kind": "mail_mailbox_management",
            "operation": normalized_operation,
            "mailbox_handle": mailbox_handle.strip(),
            "mailbox_ref": parsed_mailbox["mailbox_ref"],
            "account_ref": parsed_mailbox["account_ref"],
            "mailbox_name": parsed_mailbox["mailbox_name"],
            "expected_message_count": current_message_count,
            "synthetic_name_required": SYNTHETIC_MAIL_TEST_PREFIX,
            "raw_identifier_returned": False,
            "account_identifier_returned": False,
        }
        fingerprint_payload = {
            "operation": normalized_operation,
            "mailbox_handle": mailbox_handle.strip(),
            "mailbox_ref": parsed_mailbox["mailbox_ref"],
            "message_count": current_message_count,
            "schema_fingerprint": fingerprint,
        }

    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
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


def apply_mail_mailbox_change(
    operation: str,
    *,
    sender_handle: str = "",
    mailbox_handle: str = "",
    mailbox_name: str = "",
    new_mailbox_name: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_mailbox_change(
        operation,
        sender_handle=sender_handle,
        mailbox_handle=mailbox_handle,
        mailbox_name=mailbox_name,
        new_mailbox_name=new_mailbox_name,
        db_path=db_path,
        script_runner=script_runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    fingerprint = str(preview["approval"]["approval_fingerprint"])
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail mailbox apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != _approval_token(fingerprint):
        return _apply_error(
            [_warning("invalid_approval_token", "Mail mailbox apply approval token did not match the plan.")],
            plan=plan,
        )

    operation_name = str(preview["operation"])
    proposed = preview["proposed"]
    runner = script_runner or _run_osascript
    try:
        if operation_name == "create_mailbox":
            sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
                sender_handle,
                script_runner=script_runner,
            )
            if sender_warning is not None:
                return _apply_error([sender_warning], plan=plan)
            assert sender_identity is not None
            assert sender_metadata is not None
            if sender_metadata["account_ref"] != proposed["account_ref"]:
                return _apply_error(
                    [_warning("stale_sender_state", "Mail sender account changed since the plan; re-plan before applying.")],
                    plan=plan,
                )
            output = runner(
                _mail_create_mailbox_script(
                    account_id=sender_identity["account_id"],
                    mailbox_name=str(proposed["mailbox_name"]),
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
            read_back = _mailbox_management_read_back(
                operation_name,
                output,
                mailbox_name=str(proposed["mailbox_name"]),
                account_ref=str(proposed["account_ref"]),
            )
        elif operation_name == "rename_mailbox":
            parsed_mailbox = _resolve_mailbox_for_management_apply(
                mailbox_handle,
                db_path=db_path,
                expected_ref=str(proposed["mailbox_ref"]),
            )
            if isinstance(parsed_mailbox, dict) and parsed_mailbox.get("warning"):
                return _apply_error([parsed_mailbox["warning"]], plan=plan)
            assert isinstance(parsed_mailbox, dict)
            output = runner(
                _mail_rename_mailbox_script(
                    account_id=parsed_mailbox["account_id"],
                    old_mailbox_name=parsed_mailbox["mailbox_name"],
                    new_mailbox_name=str(proposed["new_mailbox_name"]),
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
            read_back = _mailbox_management_read_back(
                operation_name,
                output,
                mailbox_name=str(proposed["new_mailbox_name"]),
                account_ref=parsed_mailbox["account_ref"],
            )
        else:
            parsed_mailbox = _resolve_mailbox_for_management_apply(
                mailbox_handle,
                db_path=db_path,
                expected_ref=str(proposed["mailbox_ref"]),
            )
            if isinstance(parsed_mailbox, dict) and parsed_mailbox.get("warning"):
                return _apply_error([parsed_mailbox["warning"]], plan=plan)
            assert isinstance(parsed_mailbox, dict)
            output = runner(
                _mail_delete_mailbox_script(
                    account_id=parsed_mailbox["account_id"],
                    mailbox_name=parsed_mailbox["mailbox_name"],
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
            read_back = _mailbox_management_read_back(
                operation_name,
                output,
                mailbox_name=parsed_mailbox["mailbox_name"],
                account_ref=parsed_mailbox["account_ref"],
            )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail synthetic mailbox operation timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail synthetic mailbox operation could not be applied safely.")],
            plan=plan,
        )

    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail synthetic mailbox operation applied but read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    return _mail_apply_success(
        read_back,
        preview=preview,
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=False,
    )


def plan_mail_cleanup(
    operation: str,
    *,
    message_handle: str = "",
    sender_handle: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in MAIL_CLEANUP_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation permanent_delete_message, empty_trash, or empty_junk.",
            )
        )
    if normalized_operation == "permanent_delete_message":
        if sender_handle.strip():
            warnings.append(
                _warning("unexpected_sender_handle", "Mail permanent_delete_message uses one exact message handle.")
            )
        if not is_int_handle(message_handle, "mail:message"):
            warnings.append(
                _warning("invalid_message_handle", "Expected mail:message opaque handle from search output.")
            )
        if warnings:
            return _plan_error(warnings, privacy=_preview_privacy(content_inspected=True))
        try:
            resolved_db_path = _resolve_db_path(db_path)
            resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
            with connect_readonly(resolved_db_path) as connection:
                _check_schema(connection)
                target = _resolve_cleanup_message_target(
                    connection,
                    message_handle,
                    mail_root=resolved_mail_root,
                )
        except StoreUnavailableError:
            return _plan_error([_mail_store_unavailable_warning()], privacy=_preview_privacy(content_inspected=True))
        except MailTriageIdentityUnavailable as error:
            return _plan_error(
                [_message_identity_unavailable_plan_warning(error)],
                privacy=_preview_privacy(content_inspected=True),
            )
        except MailCleanupRefused as error:
            return _plan_error([error.warning], privacy=_preview_privacy(content_inspected=True))
        if target is None:
            return _plan_error(
                [_warning("message_not_found", "Mail message handle did not resolve to a live message.")],
                privacy=_preview_privacy(content_inspected=True),
            )
        target_list = [target]
        proposed = {
            "kind": "mail_cleanup",
            "operation": normalized_operation,
            "message_handle": message_handle,
            "message_count": 1,
            "target_mailbox_kind": target["mailbox_kind"],
            "mailbox_ref": target["mailbox_ref"],
            "expected_state": _cleanup_state_fingerprint(target),
            "synthetic_subject_prefix_required": SYNTHETIC_MAIL_TEST_PREFIX,
            "synthetic_subject_prefix_confirmed": True,
            "body_returned": False,
            "content_returned": False,
            "raw_identifier_returned": False,
        }
        fingerprint_payload = {
            "operation": normalized_operation,
            "message_handle": message_handle,
            "expected_state": _cleanup_state_fingerprint(target),
        }
    else:
        if message_handle.strip():
            warnings.append(_warning("unexpected_message_handle", "Mail empty_trash/empty_junk uses an exact sender account handle."))
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            warnings.append(sender_warning)
        if warnings:
            return _plan_error(warnings, privacy=_preview_privacy(content_inspected=True))
        assert sender_identity is not None
        assert sender_metadata is not None
        kind = "trash" if normalized_operation == "empty_trash" else "junk"
        try:
            resolved_db_path = _resolve_db_path(db_path)
            resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
            with connect_readonly(resolved_db_path) as connection:
                _check_schema(connection)
                mailbox_target, mailbox_warning = _resolve_special_mailbox(
                    connection,
                    {"account_id": sender_identity["account_id"], "mailbox_ref": ""},
                    kind=kind,
                )
                if mailbox_warning is not None:
                    return _plan_error([mailbox_warning], privacy=_preview_privacy(content_inspected=True))
                assert mailbox_target is not None
                target_list, target_warning = _cleanup_targets_in_mailbox(
                    connection,
                    mailbox_target,
                    mail_root=resolved_mail_root,
                )
        except StoreUnavailableError:
            return _plan_error([_mail_store_unavailable_warning()], privacy=_preview_privacy(content_inspected=True))
        if target_warning is not None:
            return _plan_error([target_warning], privacy=_preview_privacy(content_inspected=True))
        proposed = {
            "kind": "mail_cleanup",
            "operation": normalized_operation,
            "account_ref": sender_metadata["account_ref"],
            "target_mailbox_kind": kind,
            "target_mailbox_ref": mailbox_target["mailbox_ref"],
            "message_count": len(target_list),
            "message_handles": [target["handle"] for target in target_list],
            "messages": [_cleanup_fingerprint_item(target) for target in target_list],
            "already_satisfied": len(target_list) == 0,
            "synthetic_subject_prefix_required": SYNTHETIC_MAIL_TEST_PREFIX,
            "synthetic_subject_prefix_confirmed": True,
            "body_returned": False,
            "content_returned": False,
            "raw_identifier_returned": False,
            "account_identifier_returned": False,
        }
        fingerprint_payload = {
            "operation": normalized_operation,
            "account_ref": sender_metadata["account_ref"],
            "target_mailbox_ref": mailbox_target["mailbox_ref"],
            "messages": [_cleanup_fingerprint_item(target) for target in target_list],
        }

    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
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


def apply_mail_cleanup(
    operation: str,
    *,
    message_handle: str = "",
    sender_handle: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_cleanup(
        operation,
        message_handle=message_handle,
        sender_handle=sender_handle,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=script_runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan, content_inspected=True)
    preview = plan["preview"]
    fingerprint = str(preview["approval"]["approval_fingerprint"])
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail cleanup apply requires confirm_apply=true.")],
            plan=plan,
            content_inspected=True,
        )
    if approval_token.strip() != _approval_token(fingerprint):
        return _apply_error(
            [_warning("invalid_approval_token", "Mail cleanup apply approval token did not match the plan.")],
            plan=plan,
            content_inspected=True,
        )

    proposed = preview["proposed"]
    operation_name = str(preview["operation"])
    runner = script_runner or _run_osascript
    try:
        resolved_db_path = _resolve_db_path(db_path)
        resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            if operation_name == "permanent_delete_message":
                target = _resolve_cleanup_message_target(
                    connection,
                    message_handle,
                    mail_root=resolved_mail_root,
                )
                targets = [target] if target is not None else []
                if target is None or _cleanup_state_fingerprint(target) != _cleanup_fingerprint_from_plan(proposed):
                    return _apply_error(
                        [_warning("stale_message_state", "Mail cleanup target changed since the plan; re-plan before applying.")],
                        plan=plan,
                        content_inspected=True,
                    )
                script = _mail_permanent_delete_message_script(
                    account_id=target["account_id"],
                    mailbox_name=target["mailbox_name"],
                    target=target,
                )
            else:
                sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
                    sender_handle,
                    script_runner=script_runner,
                )
                if sender_warning is not None:
                    return _apply_error([sender_warning], plan=plan, content_inspected=True)
                assert sender_identity is not None
                assert sender_metadata is not None
                if sender_metadata["account_ref"] != proposed.get("account_ref"):
                    return _apply_error(
                        [_warning("stale_sender_state", "Mail cleanup account changed since the plan; re-plan before applying.")],
                        plan=plan,
                        content_inspected=True,
                    )
                kind = "trash" if operation_name == "empty_trash" else "junk"
                mailbox_target, mailbox_warning = _resolve_special_mailbox(
                    connection,
                    {"account_id": sender_identity["account_id"], "mailbox_ref": ""},
                    kind=kind,
                )
                if mailbox_warning is not None:
                    return _apply_error([mailbox_warning], plan=plan, content_inspected=True)
                assert mailbox_target is not None
                targets, target_warning = _cleanup_targets_in_mailbox(
                    connection,
                    mailbox_target,
                    mail_root=resolved_mail_root,
                )
                if target_warning is not None:
                    return _apply_error([target_warning], plan=plan, content_inspected=True)
                if [_cleanup_fingerprint_item(target) for target in targets] != _cleanup_fingerprints_from_plan(proposed):
                    return _apply_error(
                        [_warning("stale_mailbox_contents", "Mail cleanup mailbox contents changed since the plan; re-plan before applying.")],
                        plan=plan,
                        content_inspected=True,
                    )
                if not targets:
                    return _mail_apply_success(
                        {
                            "kind": "mail_cleanup",
                            "operation": operation_name,
                            "message_count": 0,
                            "already_satisfied": True,
                            "verified_absent": True,
                            "permanently_deleted": False,
                            "body_returned": False,
                            "content_returned": False,
                        },
                        preview=preview,
                        approval_fingerprint=fingerprint,
                        mutation_applied=False,
                        warnings=[_warning("already_applied", "Mail cleanup mailbox was already empty.")],
                        content_inspected=True,
                    )
                script = _mail_empty_special_mailbox_script(
                    account_id=sender_identity["account_id"],
                    mailbox_name=mailbox_target["mailbox_name"],
                    targets=targets,
                )
    except StoreUnavailableError:
        return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded", content_inspected=True)
    except MailTriageIdentityUnavailable:
        return _apply_error(
            [
                _warning(
                    "message_identity_unavailable",
                    "Mail cleanup target identity was no longer available through the local message file.",
                )
            ],
            plan=plan,
            content_inspected=True,
        )
    except MailCleanupRefused as error:
        return _apply_error([error.warning], plan=plan, content_inspected=True)

    pre_delete_idle_output = ""
    try:
        pre_delete_idle_output = runner(
            _mail_wait_for_background_activity_script(),
            (MAIL_CLEANUP_BACKGROUND_IDLE_ATTEMPTS * MAIL_CLEANUP_BACKGROUND_IDLE_DELAY_SECONDS) + 5.0,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("mail_background_activity_timeout", "Mail cleanup refused to mutate while background activity status timed out.")],
            plan=plan,
            status="degraded",
            content_inspected=True,
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("mail_background_activity_unavailable", "Mail cleanup refused to mutate because Mail background activity was unavailable.")],
            plan=plan,
            status="degraded",
            content_inspected=True,
        )
    if _script_key_value_output(pre_delete_idle_output).get("background_idle", "").casefold() != "true":
        return _apply_error(
            [
                _warning(
                    "mail_background_activity_timeout",
                    "Mail cleanup refused to mutate while Mail background activity was still running.",
                )
            ],
            plan=plan,
            status="degraded",
            content_inspected=True,
        )

    try:
        runner(script, MAIL_APPLESCRIPT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        cleanup_absent = _cleanup_targets_absent(
            targets,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
            require_mailbox_empty=operation_name in {"empty_trash", "empty_junk"},
            attempts=MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS,
            retry_delay_seconds=MAIL_CLEANUP_ABSENCE_READ_BACK_DELAY_SECONDS,
        )
        return _apply_error(
            [_warning("automation_timeout", "Mail cleanup timed out through local automation.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
            content_inspected=True,
            read_back=_mail_cleanup_read_back(
                operation_name,
                targets,
                verified_absent=cleanup_absent,
            ),
        )
    except OSError:
        return _apply_error(
            [_warning("write_error", "Mail cleanup could not be applied safely.")],
            plan=plan,
            content_inspected=True,
        )
    except MailAutomationError as error:
        if _mail_cleanup_error_before_delete(error):
            return _apply_error(
                [_warning("write_error", "Mail cleanup could not be applied safely.")],
                plan=plan,
                content_inspected=True,
            )
        cleanup_absent = _cleanup_targets_absent(
            targets,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
            require_mailbox_empty=operation_name in {"empty_trash", "empty_junk"},
            attempts=MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS,
            retry_delay_seconds=MAIL_CLEANUP_ABSENCE_READ_BACK_DELAY_SECONDS,
        )
        return _apply_error(
            [_warning("write_error", "Mail cleanup could not be applied safely.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
            content_inspected=True,
            read_back=_mail_cleanup_read_back(
                operation_name,
                targets,
                verified_absent=cleanup_absent,
            ),
        )

    cleanup_absent = _cleanup_targets_absent(
        targets,
        db_path=resolved_db_path,
        mail_root=resolved_mail_root,
        require_mailbox_empty=operation_name in {"empty_trash", "empty_junk"},
        attempts=MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS,
        retry_delay_seconds=MAIL_CLEANUP_ABSENCE_READ_BACK_DELAY_SECONDS,
    )

    if not cleanup_absent:
        warnings = [
            _warning(
                "absence_read_back_unavailable",
                "Mail cleanup applied but local absence read-back did not confirm every target.",
            )
        ]
        return _apply_error(
            warnings,
            plan=plan,
            status="partial",
            mutation_applied=True,
            content_inspected=True,
            read_back=_mail_cleanup_read_back(operation_name, targets, verified_absent=False),
        )
    return _mail_apply_success(
        {
            "kind": "mail_cleanup",
            "operation": operation_name,
            "message_count": len(targets),
            "verified_absent": True,
            "permanently_deleted": True,
            "synthetic_subject_prefix_confirmed": True,
            "body_returned": False,
            "content_returned": False,
            "raw_identifier_returned": False,
        },
        preview=preview,
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
        content_inspected=True,
    )


def search_mail_senders(
    query: str,
    *,
    limit: int = DEFAULT_SENDER_LIMIT,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("empty_query", "Mail sender search requires a non-empty sender query.")
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("broad_query", "Mail sender search requires at least two letters or digits.")
            ],
        }

    identities, warning = _mail_sender_identities(script_runner=script_runner)
    if warning is not None:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [warning],
        }

    bounded_limit = max(1, min(limit, 50))
    address_counts = _sender_address_counts(identities)
    normalized_query = query.casefold()
    results = []
    for identity in identities:
        searchable = _sender_safe_search_text(identity)
        if normalized_query not in searchable:
            continue
        results.append(_sender_metadata(identity, address_counts))
        if len(results) >= bounded_limit:
            break

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _privacy(),
        "query": {"scope": "mail_sender", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_mail_sender(
    handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    resolved, warning = _resolve_mail_sender_handle(handle, script_runner=script_runner)
    if warning is not None:
        status = "degraded" if warning["code"] == "mail_sender_source_unavailable" else "error"
        return {
            "schema_version": 1,
            "status": status,
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [warning],
        }
    if resolved is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [],
        }
    identity, identities = resolved
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _privacy(),
        "result": _sender_metadata(identity, _sender_address_counts(identities)),
        "warnings": [],
    }


def search_mail_signatures(
    query: str,
    *,
    limit: int = DEFAULT_SIGNATURE_LIMIT,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("empty_query", "Mail signature search requires a non-empty signature query.")
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("broad_query", "Mail signature search requires at least two letters or digits.")
            ],
        }

    signatures, warning = _mail_signature_identities(script_runner=script_runner)
    if warning is not None:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [warning],
        }

    bounded_limit = max(1, min(limit, 50))
    name_counts = _signature_name_counts(signatures)
    normalized_query = query.casefold()
    results = []
    seen: set[str] = set()
    for signature in signatures:
        name_key = signature["name_key"]
        if name_key in seen:
            continue
        if normalized_query not in _signature_safe_search_text(signature):
            continue
        seen.add(name_key)
        results.append(_signature_metadata(signature, name_counts))
        if len(results) >= bounded_limit:
            break

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _privacy(),
        "query": {"scope": "mail_signature_name", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_mail_signature(
    handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    resolved, warning = _resolve_mail_signature_handle(handle, script_runner=script_runner)
    if warning is not None:
        status = "degraded" if warning["code"] == "mail_signature_source_unavailable" else "error"
        return {
            "schema_version": 1,
            "status": status,
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [warning],
        }
    if resolved is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [],
        }
    signature, signatures = resolved
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _privacy(),
        "result": _signature_metadata(signature, _signature_name_counts(signatures)),
        "warnings": [],
    }


def create_mail_template(
    name: str,
    body_text: str,
    *,
    subject: str = "",
    state_path: Path | None = None,
) -> dict[str, Any]:
    normalized_name, name_warning = _normalize_template_name(name)
    normalized_body, body_warning = _normalize_draft_body(body_text)
    normalized_subject, subject_warning = (
        _normalize_draft_subject(subject) if subject.strip() else ("", None)
    )
    warnings = [warning for warning in (name_warning, body_warning, subject_warning) if warning is not None]
    if warnings:
        return _template_error(warnings, content_inspected=True)

    state = _load_mail_template_state(state_path)
    for template in state["templates"]:
        if str(template["name"]).casefold() == normalized_name.casefold():
            return _template_error(
                [_warning("duplicate_template_name", "Mail template names must be unique.")],
                content_inspected=True,
            )

    now = _utc_now_iso()
    template = {
        "id": uuid.uuid4().hex,
        "name": normalized_name,
        "subject": normalized_subject,
        "body_text": normalized_body,
        "created_at": now,
        "updated_at": now,
    }
    state["templates"].append(template)
    _write_mail_template_state(state, state_path)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(content_inspected=True),
        "result": _template_metadata(template),
        "result_count": 1,
        "warnings": [],
    }


def search_mail_templates(
    query: str = "",
    *,
    limit: int = DEFAULT_TEMPLATE_LIMIT,
    state_path: Path | None = None,
) -> dict[str, Any]:
    normalized_query = query.strip().casefold()
    if normalized_query and not has_minimum_query_quality(normalized_query):
        return _template_error(
            [_warning("broad_query", "Mail template search requires at least two letters or digits.")],
            results=True,
        )
    state = _load_mail_template_state(state_path)
    bounded_limit = max(1, min(limit, 50))
    results = []
    for template in state["templates"]:
        searchable = f"{template['name']} {template.get('subject', '')}".casefold()
        if normalized_query and normalized_query not in searchable:
            continue
        results.append(_template_metadata(template))
        if len(results) >= bounded_limit:
            break
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _privacy(),
        "query": {"scope": "mail_template_name_subject", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_mail_template(
    handle: str,
    *,
    include_body: bool = False,
    state_path: Path | None = None,
) -> dict[str, Any]:
    template = _resolve_mail_template_handle(handle, state_path=state_path)
    if template is None:
        return _invalid_template_handle_result()
    result = _template_metadata(template)
    if include_body:
        result = {
            **result,
            "body_text": str(template["body_text"]),
            "body_returned": True,
            "content_returned": True,
        }
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _content_privacy(content_inspected=include_body) if include_body else _privacy(),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def delete_mail_template(
    handle: str,
    *,
    confirm_delete: bool = False,
    state_path: Path | None = None,
) -> dict[str, Any]:
    if not confirm_delete:
        return _template_error(
            [_warning("missing_delete_confirmation", "Mail template delete requires confirm_delete=true.")]
        )
    if not is_opaque_handle(handle, TEMPLATE_HANDLE_PREFIX):
        return _invalid_template_handle_result()
    state = _load_mail_template_state(state_path)
    for index, template in enumerate(state["templates"]):
        if opaque_handle_matches(handle, TEMPLATE_HANDLE_PREFIX, str(template["id"])):
            deleted = state["templates"].pop(index)
            _write_mail_template_state(state, state_path)
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "mail",
                "privacy": _privacy(),
                "mutation_applied": True,
                "read_back": {
                    **_template_metadata(deleted),
                    "deleted": True,
                },
                "result_count": 1,
                "warnings": [],
            }
    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "mail",
        "privacy": _privacy(),
        "mutation_applied": False,
        "read_back": None,
        "result_count": 0,
        "warnings": [],
    }


def _row_to_metadata(row, *, content_status: str | None = None) -> dict[str, Any]:
    mailbox = _mailbox_metadata(row["mailbox_url"])
    metadata = {
        "handle": make_int_handle("mail:message", int(row["rowid"])),
        "subject": row["subject"],
        "mailbox_name": mailbox["mailbox_name"],
        "mailbox_path": mailbox["mailbox_path"],
        "mailbox_ref": mailbox["mailbox_ref"],
        "account_ref": mailbox["account_ref"],
        "date_received": row["date_received"],
        "date_sent": row["date_sent"],
        "read": bool(row["read"]) if row["read"] is not None else None,
        "flagged": bool(row["flagged"]) if row["flagged"] is not None else None,
        "deleted": bool(row["deleted"]) if row["deleted"] is not None else None,
        "size": row["size"] if "size" in row.keys() else None,
    }
    if content_status is not None:
        metadata["content_status"] = content_status
    return metadata


def _row_to_content_metadata(row) -> dict[str, Any]:
    metadata = _row_to_metadata(row)
    metadata.update({"content_text": "", "content_chars": 0, "truncated": False})
    return metadata


def search_mail_metadata(
    query: str,
    *,
    db_path: Path | None = None,
    mailbox_handle: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()
    normalized_mailbox_handle = mailbox_handle.strip()
    if normalized_mailbox_handle and not is_opaque_handle(
        normalized_mailbox_handle,
        MAILBOX_HANDLE_PREFIX,
    ):
        return _search_error(
            "invalid_mailbox_handle",
            "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
        )

    bounded_limit = max(1, min(limit, 50))
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            mailbox_target = None
            if normalized_mailbox_handle:
                mailbox_target = _resolve_mailbox_handle(
                    connection,
                    fingerprint,
                    normalized_mailbox_handle,
                )
                if mailbox_target is None:
                    return _search_error(
                        "invalid_mailbox_handle",
                        "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
                    )
            conditions = [
                "COALESCE(m.deleted, 0) = 0",
                "s.subject LIKE ? ESCAPE '\\'",
            ]
            params: list[Any] = [like_contains_pattern(query)]
            if mailbox_target is not None:
                conditions.append("mb.url = ?")
                params.append(mailbox_target["mailbox_url"])
            params.append(bounded_limit)
            rows = connection.execute(
                f"""
                SELECT
                    m.ROWID AS rowid,
                    s.subject AS subject,
                    mb.url AS mailbox_url,
                    m.date_received AS date_received,
                    m.date_sent AS date_sent,
                    m.read AS read,
                    m.flagged AS flagged,
                    m.deleted AS deleted,
                    m.size AS size
                FROM messages m
                LEFT JOIN subjects s ON m.subject = s.ROWID
                LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
                WHERE {" AND ".join(conditions)}
                ORDER BY COALESCE(m.date_received, m.date_sent, 0) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_mail_store_unavailable_warning()],
        }

    content_root = _mail_content_root(resolved_db_path)
    content_statuses = _message_content_statuses(
        content_root,
        [int(row["rowid"]) for row in rows],
    )
    results = [
        _row_to_metadata(
            row,
            content_status=content_statuses.get(int(row["rowid"]), "unknown"),
        )
        for row in rows
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {
            "scope": "subject",
            "limit": bounded_limit,
            "mailbox_filter": "exact_handle" if normalized_mailbox_handle else "",
            "mailbox_ref": mailbox_target["mailbox_ref"] if mailbox_target else "",
        },
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def search_mail_body(
    query: str,
    *,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    cursor: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    limit: int = DEFAULT_MAIL_DISCOVERY_LIMIT,
    max_snippet_chars: int = DEFAULT_MAIL_SNIPPET_CHARS,
    max_seconds: float | int | None = None,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    normalized_query = query.strip()
    if not normalized_query:
        return _search_error("empty_query", "Mail body search requires a non-empty body query.")
    if not has_minimum_query_quality(normalized_query):
        return _search_error("broad_query", "Mail body search requires at least two letters or digits.")

    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    cursor_offset, cursor_warning = _mail_cursor_offset(cursor)
    warnings = [*bound_warnings]
    if cursor_warning is not None:
        warnings.append(cursor_warning)
    if warnings:
        return _search_error_payload(warnings, privacy=_snippet_privacy(content_inspected=False))

    bounded_limit = max(1, min(limit, MAX_MAIL_DISCOVERY_LIMIT))
    bounded_snippet_chars = max(1, min(max_snippet_chars, MAX_MAIL_SNIPPET_CHARS))
    bounded_seconds = _bounded_scan_seconds(max_seconds)
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            range_total = _count_mail_rows_in_bounds(connection, bounds)
            rows = _select_mail_discovery_rows(
                connection,
                bounds=bounds,
                cursor_offset=cursor_offset,
                scan_limit=MAX_MAIL_DISCOVERY_SCAN_ROWS,
            )
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_snippet_privacy(content_inspected=False))

    root = mail_root or _mail_content_root(resolved_db_path)
    file_index = _scan_mail_message_files(root)
    deadline = started_monotonic + bounded_seconds
    results: list[dict[str, Any]] = []
    scanned_count = 0
    stopped_reason = "exhausted"
    query_key = _mail_body_search_text(normalized_query).casefold()
    for row in rows:
        if scanned_count > 0 and time.monotonic() > deadline:
            stopped_reason = "time_budget"
            break
        scanned_count += 1
        text = _mail_row_content_text(root, int(row["rowid"]), index=file_index)
        if text is None:
            continue
        searchable_text = _mail_body_search_text(text)
        match_index = searchable_text.casefold().find(query_key)
        if match_index < 0:
            continue
        metadata = _row_to_metadata(row, content_status="available")
        snippet = _match_snippet(searchable_text, match_index, len(query_key), bounded_snippet_chars)
        metadata.update(
            {
                "matched_scope": "body",
                "matched_scopes": ["body"],
                "snippet": snippet,
                "snippet_chars": len(snippet),
                "content_returned": False,
            }
        )
        results.append(metadata)
        if len(results) >= bounded_limit:
            stopped_reason = "result_limit"
            break
    if stopped_reason == "exhausted" and len(rows) >= MAX_MAIL_DISCOVERY_SCAN_ROWS:
        stopped_reason = "scan_limit"

    next_cursor = _next_cursor(
        cursor_offset,
        scanned_count,
        len(rows),
        len(results),
        bounded_limit,
        stopped_early=stopped_reason == "time_budget",
    )
    warnings = [_scan_time_budget_warning()] if stopped_reason == "time_budget" else []
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _snippet_privacy(content_inspected=True),
        "query": {
            "scope": "body",
            "limit": bounded_limit,
            "after": bounds.get("after"),
            "before": bounds.get("before"),
            "cursor": cursor or "",
            "max_seconds": bounded_seconds,
        },
        "scan": _scan_stats_block(
            scanned_count=scanned_count,
            range_total=range_total,
            started_monotonic=started_monotonic,
            stopped_reason=stopped_reason,
        ),
        "results": results,
        "result_count": len(results),
        "next_cursor": next_cursor,
        "warnings": warnings,
    }


def search_mail_attachments(
    query: str,
    *,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    cursor: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    limit: int = DEFAULT_MAIL_DISCOVERY_LIMIT,
    include_content: bool = False,
    include_ocr: bool = False,
    max_snippet_chars: int = DEFAULT_MAIL_SNIPPET_CHARS,
    max_seconds: float | int | None = None,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    normalized_query = query.strip()
    if not normalized_query:
        return _search_error("empty_query", "Mail attachment search requires a non-empty filename or MIME query.")
    if not has_minimum_query_quality(normalized_query):
        return _search_error("broad_query", "Mail attachment search requires at least two letters or digits.")

    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    cursor_offset, cursor_warning = _mail_cursor_offset(cursor)
    warnings = [*bound_warnings]
    if cursor_warning is not None:
        warnings.append(cursor_warning)
    if warnings:
        return _search_error_payload(warnings, privacy=_attachment_privacy(content_inspected=False))

    bounded_limit = max(1, min(limit, MAX_MAIL_DISCOVERY_LIMIT))
    bounded_snippet_chars = max(1, min(max_snippet_chars, MAX_MAIL_SNIPPET_CHARS))
    bounded_seconds = _bounded_scan_seconds(max_seconds)
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            range_total = _count_mail_rows_in_bounds(connection, bounds)
            rows = _select_mail_discovery_rows(
                connection,
                bounds=bounds,
                cursor_offset=cursor_offset,
                scan_limit=MAX_MAIL_DISCOVERY_SCAN_ROWS,
            )
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_attachment_privacy(content_inspected=False))

    root = mail_root or _mail_content_root(resolved_db_path)
    file_index = _scan_mail_message_files(root)
    deadline = started_monotonic + bounded_seconds
    results: list[dict[str, Any]] = []
    scanned_count = 0
    stopped_reason = "exhausted"
    query_key = normalized_query.casefold()
    content_query_key = _mail_body_search_text(normalized_query).casefold()
    content_snippet_returned = False
    ocr_attempt_count = 0
    ocr_attempt_limit_reached = False
    for row in rows:
        if scanned_count > 0 and time.monotonic() > deadline:
            stopped_reason = "time_budget"
            break
        scanned_count += 1
        message = _parse_mail_message(root, int(row["rowid"]), index=file_index)
        if message is None:
            continue
        for part_index, part, header_metadata in _mail_attachment_header_parts(
            message,
            limit=MAX_MAIL_DISCOVERY_LIMIT,
        ):
            searchable = " ".join(
                [
                    str(header_metadata.get("filename") or ""),
                    str(header_metadata.get("content_type") or ""),
                    str(header_metadata.get("attachment_type") or ""),
                ]
            ).casefold()
            matched_scope = ""
            snippet = ""
            extractor_status = ""
            if query_key in searchable:
                matched_scope = (
                    "attachment_filename"
                    if query_key in str(header_metadata.get("filename") or "").casefold()
                    else "attachment_metadata"
                )
            elif include_content:
                allow_ocr = include_ocr and ocr_attempt_count < MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS
                extracted_text, extractor_status, ocr_attempted = _attachment_search_text(
                    part,
                    include_ocr=allow_ocr,
                )
                if ocr_attempted:
                    ocr_attempt_count += 1
                elif include_ocr and not allow_ocr and extractor_status == "pdf_text_unavailable":
                    extractor_status = "pdf_ocr_skipped_limit"
                    ocr_attempt_limit_reached = True
                if extracted_text:
                    searchable_text = _mail_body_search_text(extracted_text)
                    match_index = searchable_text.casefold().find(content_query_key)
                    if match_index >= 0:
                        matched_scope = "attachment_content"
                        snippet = _match_snippet(
                            searchable_text,
                            match_index,
                            len(content_query_key),
                            bounded_snippet_chars,
                        )
            if not matched_scope:
                continue
            attachment = _mail_attachment_metadata(
                part,
                fingerprint=fingerprint,
                rowid=int(row["rowid"]),
                part_index=part_index,
            )
            metadata = _row_to_metadata(row, content_status="available")
            metadata.update(
                {
                    "matched_scope": matched_scope,
                    "matched_scopes": [matched_scope],
                    "attachment": attachment,
                    "snippet": snippet,
                    "snippet_chars": len(snippet),
                    "attachment_text_extractor": extractor_status,
                    "attachment_content_snippet_returned": bool(snippet),
                    "content_returned": False,
                    "attachment_content_returned": False,
                }
            )
            content_snippet_returned = content_snippet_returned or bool(snippet)
            results.append(metadata)
            if len(results) >= bounded_limit:
                break
        if len(results) >= bounded_limit:
            stopped_reason = "result_limit"
            break
    if stopped_reason == "exhausted" and len(rows) >= MAX_MAIL_DISCOVERY_SCAN_ROWS:
        stopped_reason = "scan_limit"

    next_cursor = _next_cursor(
        cursor_offset,
        scanned_count,
        len(rows),
        len(results),
        bounded_limit,
        stopped_early=stopped_reason == "time_budget",
    )
    warnings = []
    if stopped_reason == "time_budget":
        warnings.append(_scan_time_budget_warning())
    if ocr_attempt_limit_reached:
        warnings.append(
            _warning(
                "ocr_attempt_limit_reached",
                "Mail attachment OCR search skipped additional PDF OCR candidates after the per-search limit.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _attachment_privacy(
            content_inspected=True,
            content_snippet_returned=content_snippet_returned,
        ),
        "query": {
            "scope": "attachment_filename_or_mime_or_content"
            if include_content
            else "attachment_filename_or_mime",
            "limit": bounded_limit,
            "after": bounds.get("after"),
            "before": bounds.get("before"),
            "cursor": cursor or "",
            "max_seconds": bounded_seconds,
            "include_content": include_content,
            "include_ocr": bool(include_content and include_ocr),
            "ocr_attempt_count": ocr_attempt_count,
            "ocr_attempt_limit": MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS if include_content and include_ocr else 0,
        },
        "scan": _scan_stats_block(
            scanned_count=scanned_count,
            range_total=range_total,
            started_monotonic=started_monotonic,
            stopped_reason=stopped_reason,
        ),
        "results": results,
        "result_count": len(results),
        "next_cursor": next_cursor,
        "warnings": warnings,
    }


def search_mail_advanced(
    query: str,
    *,
    scopes: list[str] | None = None,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    mailbox: str = "",
    has_attachments: bool | None = None,
    cursor: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    limit: int = DEFAULT_MAIL_DISCOVERY_LIMIT,
    max_snippet_chars: int = DEFAULT_MAIL_SNIPPET_CHARS,
    max_seconds: float | int | None = None,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    normalized_query = query.strip()
    if not normalized_query:
        return _search_error("empty_query", "Advanced Mail search requires a non-empty query.")
    if not has_minimum_query_quality(normalized_query):
        return _search_error("broad_query", "Advanced Mail search requires at least two letters or digits.")

    normalized_scopes, scope_warning = _normalize_mail_search_scopes(scopes)
    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    cursor_offset, cursor_warning = _mail_cursor_offset(cursor)
    warnings = [*bound_warnings]
    if scope_warning is not None:
        warnings.append(scope_warning)
    if cursor_warning is not None:
        warnings.append(cursor_warning)
    if warnings:
        return _search_error_payload(warnings, privacy=_snippet_privacy(content_inspected=False))

    bounded_limit = max(1, min(limit, MAX_MAIL_DISCOVERY_LIMIT))
    bounded_snippet_chars = max(1, min(max_snippet_chars, MAX_MAIL_SNIPPET_CHARS))
    bounded_seconds = _bounded_scan_seconds(max_seconds)
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            range_total = _count_mail_rows_in_bounds(connection, bounds)
            rows = _select_mail_discovery_rows(
                connection,
                bounds=bounds,
                cursor_offset=cursor_offset,
                scan_limit=MAX_MAIL_DISCOVERY_SCAN_ROWS,
            )
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_snippet_privacy(content_inspected=False))

    root = mail_root or _mail_content_root(resolved_db_path)
    file_index = _scan_mail_message_files(root)
    deadline = started_monotonic + bounded_seconds
    results: list[dict[str, Any]] = []
    scanned_count = 0
    stopped_reason = "exhausted"
    query_key = _mail_body_search_text(normalized_query).casefold()
    mailbox_key = mailbox.strip().casefold()
    normalized_scope_set = set(normalized_scopes)
    header_scopes = {"from", "to", "cc", "bcc"}
    needs_message = bool(
        normalized_scope_set & header_scopes
        or "attachment_filename" in normalized_scope_set
        or has_attachments is not None
    )
    for row in rows:
        if scanned_count > 0 and time.monotonic() > deadline:
            stopped_reason = "time_budget"
            break
        scanned_count += 1
        row_metadata = _row_to_metadata(row)
        if mailbox_key and mailbox_key not in str(row_metadata.get("mailbox_name") or "").casefold():
            continue
        message = (
            _parse_mail_message(root, int(row["rowid"]), index=file_index)
            if needs_message
            else None
        )
        attachment_metadata: list[dict[str, Any]] = []
        if message is not None and ("attachment_filename" in normalized_scopes or has_attachments is not None):
            attachment_metadata = _mail_attachment_header_metadata_list(
                message,
                limit=MAX_MAIL_DISCOVERY_LIMIT,
            )
        if has_attachments is not None and bool(attachment_metadata) != has_attachments:
            continue

        matched_scopes: list[str] = []
        snippet = ""
        if "subject" in normalized_scopes and query_key in str(row["subject"] or "").casefold():
            matched_scopes.append("subject")
        if message is not None:
            matched_scopes.extend(_matched_header_scopes(message, normalized_scopes, query_key))
            if "attachment_filename" in normalized_scopes:
                if any(
                    query_key
                    in " ".join(
                        [
                            str(attachment.get("filename") or ""),
                            str(attachment.get("content_type") or ""),
                            str(attachment.get("attachment_type") or ""),
                        ]
                    ).casefold()
                    for attachment in attachment_metadata
                ):
                    matched_scopes.append("attachment_filename")
        if "body" in normalized_scopes:
            text = _mail_row_content_text(root, int(row["rowid"]), index=file_index)
            if text is not None:
                searchable_text = _mail_body_search_text(text)
                match_index = searchable_text.casefold().find(query_key)
                if match_index >= 0:
                    matched_scopes.append("body")
                    snippet = _match_snippet(
                        searchable_text,
                        match_index,
                        len(query_key),
                        bounded_snippet_chars,
                    )

        if not matched_scopes:
            continue
        content_status = "available" if message is not None or snippet else "unknown"
        result = _row_to_metadata(row, content_status=content_status)
        result.update(
            {
                "matched_scope": matched_scopes[0],
                "matched_scopes": sorted(set(matched_scopes)),
                "snippet": snippet,
                "snippet_chars": len(snippet),
                "content_returned": False,
            }
        )
        if message is not None:
            result.update(_safe_header_search_metadata(message))
            result["attachment_count"] = len(attachment_metadata)
            result["attachment_filenames"] = [
                _bounded_string(item["filename"], 200)
                for item in attachment_metadata
                if item.get("filename")
            ][:MAX_MAIL_DISCOVERY_LIMIT]
        results.append(result)
        if len(results) >= bounded_limit:
            stopped_reason = "result_limit"
            break
    if stopped_reason == "exhausted" and len(rows) >= MAX_MAIL_DISCOVERY_SCAN_ROWS:
        stopped_reason = "scan_limit"

    next_cursor = _next_cursor(
        cursor_offset,
        scanned_count,
        len(rows),
        len(results),
        bounded_limit,
        stopped_early=stopped_reason == "time_budget",
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _snippet_privacy(content_inspected="body" in normalized_scopes),
        "query": {
            "scope": "advanced",
            "scopes": normalized_scopes,
            "limit": bounded_limit,
            "after": bounds.get("after"),
            "before": bounds.get("before"),
            "mailbox_filter_used": bool(mailbox_key),
            "has_attachments": has_attachments,
            "cursor": cursor or "",
            "max_seconds": bounded_seconds,
        },
        "scan": _scan_stats_block(
            scanned_count=scanned_count,
            range_total=range_total,
            started_monotonic=started_monotonic,
            stopped_reason=stopped_reason,
        ),
        "results": results,
        "result_count": len(results),
        "next_cursor": next_cursor,
        "warnings": [_scan_time_budget_warning()] if stopped_reason == "time_budget" else [],
    }


def build_mail_fts_index(
    *,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    cursor: str = "",
    include_attachments: bool = False,
    include_ocr: bool = False,
    confirm_index: bool = False,
    reset: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    index_path: Path | None = None,
    limit: int = MAX_MAIL_FTS_BUILD_MESSAGES,
    max_seconds: float | int | None = None,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    cursor_offset, cursor_warning = _mail_cursor_offset(cursor)
    warnings = [*bound_warnings]
    if cursor_warning is not None:
        warnings.append(cursor_warning)
    if reset and cursor_offset > 0:
        warnings.append(
            _warning(
                "invalid_reset_cursor",
                "Mail FTS reset is allowed only on the first build page; continue next_cursor builds without reset.",
            )
        )
    if not confirm_index:
        warnings.append(
            _warning(
                "missing_index_confirmation",
                "Mail FTS index build requires confirm_index=true because it writes a local durable content cache.",
            )
        )
    if include_ocr and not include_attachments:
        warnings.append(
            _warning(
                "unexpected_include_ocr",
                "Mail FTS OCR requires include_attachments=true.",
            )
        )
    if warnings:
        return _search_error_payload(warnings, privacy=_fts_privacy(content_inspected=False))

    bounded_limit = max(1, min(limit, MAX_MAIL_FTS_BUILD_MESSAGES))
    bounded_seconds = _bounded_scan_seconds(max_seconds)
    fetch_limit = bounded_limit + 1
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            range_total = _count_mail_rows_in_bounds(connection, bounds)
            fetched_rows = _select_mail_discovery_rows(
                connection,
                bounds=bounds,
                cursor_offset=cursor_offset,
                scan_limit=fetch_limit,
            )
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_fts_privacy(content_inspected=False))

    rows = fetched_rows[:bounded_limit]
    root = mail_root or _mail_content_root(resolved_db_path)
    index = _mail_fts_index_path(index_path)
    fts: sqlite3.Connection | None = None
    try:
        if reset:
            _remove_mail_fts_index_files(index)
        fts = _connect_mail_fts_index(index)
        _ensure_mail_fts_schema(fts)
    except (OSError, sqlite3.Error):
        if fts is not None:
            try:
                fts.close()
            except sqlite3.Error:
                pass
        return _search_error(
            "mail_fts_unavailable",
            "Mail FTS index could not be opened or initialized safely.",
            privacy=_fts_privacy(content_inspected=False),
        )

    file_index = _scan_mail_message_files(root)
    deadline = started_monotonic + bounded_seconds
    stopped_reason = "exhausted"
    indexed_count = 0
    body_indexed_count = 0
    attachment_metadata_count = 0
    attachment_text_indexed_count = 0
    pdf_ocr_attempt_count = 0
    ocr_attempt_limit_reached = False
    try:
        for row in rows:
            if indexed_count > 0 and time.monotonic() > deadline:
                stopped_reason = "time_budget"
                break
            raw = _read_message_file_bytes(root, int(row["rowid"]), index=file_index)
            message = _parse_mail_message_bytes(raw) if raw is not None else None
            content_state_sha256 = hashlib.sha256(raw).hexdigest() if raw is not None else ""
            body_text = ""
            if raw is not None:
                try:
                    body_text = _extract_text_from_emlx(raw) or ""
                except ValueError:
                    body_text = ""
            if body_text:
                body_indexed_count += 1
            header_text = _mail_fts_header_text(message) if message is not None else {}
            attachment_names: list[str] = []
            attachment_types: list[str] = []
            attachment_text_parts: list[str] = []
            row_attachment_count = 0
            if include_attachments and message is not None:
                for _part_index, part, header_metadata in _mail_attachment_header_parts(
                    message,
                    limit=MAX_MAIL_DISCOVERY_LIMIT,
                ):
                    row_attachment_count += 1
                    attachment_metadata_count += 1
                    filename = _bounded_string(str(header_metadata.get("filename") or ""), 200)
                    content_type = _bounded_string(str(header_metadata.get("content_type") or ""), 200)
                    if filename:
                        attachment_names.append(filename)
                    if content_type:
                        attachment_types.append(content_type)
                    allow_ocr = include_ocr and pdf_ocr_attempt_count < MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS
                    extracted_text, _extractor_status, ocr_attempted = _attachment_search_text(
                        part,
                        include_ocr=allow_ocr,
                    )
                    if ocr_attempted:
                        pdf_ocr_attempt_count += 1
                    elif include_ocr and not allow_ocr:
                        ocr_attempt_limit_reached = True
                    if extracted_text:
                        attachment_text_parts.append(extracted_text)
                        attachment_text_indexed_count += 1
            _upsert_mail_fts_row(
                fts,
                row=row,
                fingerprint=fingerprint,
                content_state_sha256=content_state_sha256,
                header_text=header_text,
                body_text=body_text,
                attachment_names=attachment_names,
                attachment_types=attachment_types,
                attachment_count=row_attachment_count,
                attachment_text="\n".join(attachment_text_parts),
            )
            indexed_count += 1
        if stopped_reason == "time_budget":
            next_cursor = str(cursor_offset + indexed_count)
        elif len(fetched_rows) > bounded_limit:
            next_cursor = str(cursor_offset + len(rows))
            stopped_reason = "build_limit"
        else:
            next_cursor = ""
        indexed_docs_row = fts.execute("SELECT COUNT(*) AS total FROM mail_fts_docs").fetchone()
        indexed_docs_total = int(indexed_docs_row["total"]) if indexed_docs_row is not None else 0
        _set_mail_fts_meta(
            fts,
            {
                "build_state": "building" if next_cursor else "ready",
                "built_after": str(bounds.get("after", "")),
                "built_before": str(bounds.get("before", "")),
                "checkpoint_cursor": next_cursor,
                "last_build_at": datetime.now(tz=timezone.utc).isoformat(),
                "envelope_fingerprint": fingerprint,
            },
        )
        fts.commit()
    except (OSError, sqlite3.Error):
        try:
            fts.rollback()
        except sqlite3.Error:
            pass
        return _search_error(
            "mail_fts_write_failed",
            "Mail FTS index write failed safely.",
            privacy=_fts_privacy(content_inspected=True),
        )
    finally:
        try:
            fts.close()
        except sqlite3.Error:
            pass

    warnings = []
    if stopped_reason == "time_budget":
        warnings.append(_scan_time_budget_warning())
    if ocr_attempt_limit_reached:
        warnings.append(
            _warning(
                "ocr_attempt_limit_reached",
                "Mail FTS index skipped additional PDF OCR candidates after the per-build limit.",
            )
        )
    if next_cursor:
        warnings.append(
            _warning(
                "mail_fts_build_truncated",
                "Mail FTS index build stopped at the per-build limit; continue with next_cursor.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _fts_privacy(content_inspected=True, durable_index_written=True),
        "query": {
            "after": bounds.get("after"),
            "before": bounds.get("before"),
            "limit": bounded_limit,
            "cursor": cursor or "",
            "max_seconds": bounded_seconds,
            "include_attachments": include_attachments,
            "include_ocr": bool(include_attachments and include_ocr),
            "reset": reset,
        },
        "scan": _scan_stats_block(
            scanned_count=indexed_count,
            range_total=range_total,
            started_monotonic=started_monotonic,
            stopped_reason=stopped_reason,
        ),
        "result": {
            "index_schema_version": MAIL_FTS_INDEX_VERSION,
            "index_ref": _mail_fts_index_ref(index),
            "index_path_returned": False,
            "index_state": "building" if next_cursor else "ready",
            "indexed_docs_total": indexed_docs_total,
            "messages_seen": len(rows),
            "messages_indexed": indexed_count,
            "body_indexed_count": body_indexed_count,
            "attachment_metadata_count": attachment_metadata_count,
            "attachment_text_indexed_count": attachment_text_indexed_count,
            "pdf_ocr_attempt_count": pdf_ocr_attempt_count,
            "ocr_attempt_limit": MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS if include_attachments and include_ocr else 0,
            "durable_personal_content_cache": True,
        },
        "result_count": indexed_count,
        "next_cursor": next_cursor,
        "warnings": warnings,
    }


def _mail_fts_index_state(
    fts: sqlite3.Connection,
    mail_connection,
    fingerprint: str,
) -> dict[str, Any]:
    """Derive the index coverage state agents need before trusting FTS results.

    States: building (checkpointed build in flight), stale (rows from an older
    Envelope schema fingerprint), partial (marked ready but fewer docs than
    Envelope messages in the built range, or a legacy index with no build
    metadata), ready. "missing" is handled by callers before the index opens.
    """
    meta = _get_mail_fts_meta(fts)
    docs_row = fts.execute("SELECT COUNT(*) AS total FROM mail_fts_docs").fetchone()
    indexed_docs_total = int(docs_row["total"]) if docs_row is not None else 0
    stale_fingerprint_rows = _mail_fts_stale_count(fts, fingerprint)

    bounds: dict[str, float] = {}
    for meta_key, bound_key in (("built_after", "after"), ("built_before", "before")):
        raw_value = meta.get(meta_key, "")
        try:
            bounds[bound_key] = float(raw_value)
        except (TypeError, ValueError):
            continue
    range_total = _count_mail_rows_in_bounds(mail_connection, bounds)

    build_state = meta.get("build_state", "")
    if stale_fingerprint_rows > 0:
        state = "stale"
    elif build_state == "building":
        state = "building"
    elif build_state == "ready":
        state = "partial" if indexed_docs_total < range_total else "ready"
    else:
        # Index predates build-state tracking; coverage is unknown, so treat as partial.
        state = "partial"

    return {
        "state": state,
        "indexed_docs_total": indexed_docs_total,
        "range_total": range_total,
        "built_after": bounds.get("after"),
        "built_before": bounds.get("before"),
        "checkpoint_cursor": meta.get("checkpoint_cursor", ""),
        "last_build_at": meta.get("last_build_at", ""),
        "stale_fingerprint_rows": stale_fingerprint_rows,
    }


def get_mail_fts_status(
    *,
    db_path: Path | None = None,
    index_path: Path | None = None,
) -> dict[str, Any]:
    index = _mail_fts_index_path(index_path)
    base = {
        "schema_version": 1,
        "source": "mail",
        "privacy": _fts_privacy(content_inspected=False),
        "warnings": [],
    }
    if not index.exists():
        return {
            **base,
            "status": "ok",
            "result": {
                "index_schema_version": MAIL_FTS_INDEX_VERSION,
                "index_ref": _mail_fts_index_ref(index),
                "index_path_returned": False,
                "state": "missing",
            },
            "result_count": 0,
        }
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as mail_connection:
            fingerprint = _check_schema(mail_connection)
            fts = _connect_mail_fts_index_readonly(index)
            try:
                _validate_mail_fts_schema(fts)
                state = _mail_fts_index_state(fts, mail_connection, fingerprint)
            finally:
                try:
                    fts.close()
                except sqlite3.Error:
                    pass
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_fts_privacy(content_inspected=False))
    except (OSError, sqlite3.Error):
        return _search_error(
            "mail_fts_unavailable",
            "Mail FTS index could not be inspected safely.",
            privacy=_fts_privacy(content_inspected=False),
        )
    return {
        **base,
        "status": "ok",
        "schema_fingerprint": fingerprint,
        "result": {
            "index_schema_version": MAIL_FTS_INDEX_VERSION,
            "index_ref": _mail_fts_index_ref(index),
            "index_path_returned": False,
            **state,
        },
        "result_count": 1,
    }


def search_mail_fts(
    query: str,
    *,
    scopes: list[str] | None = None,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    cursor: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    index_path: Path | None = None,
    limit: int = DEFAULT_MAIL_DISCOVERY_LIMIT,
    max_snippet_chars: int = DEFAULT_MAIL_SNIPPET_CHARS,
) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        return _search_error("empty_query", "Mail FTS search requires a non-empty query.")
    if not has_minimum_query_quality(normalized_query):
        return _search_error("broad_query", "Mail FTS search requires at least two letters or digits.")

    normalized_scopes, scope_warning = _normalize_mail_fts_scopes(scopes)
    bounds, bound_warnings = _mail_date_bounds(after=after, before=before, require_bound=True)
    cursor_offset, cursor_warning = _mail_cursor_offset(cursor)
    warnings = [*bound_warnings]
    if scope_warning is not None:
        warnings.append(scope_warning)
    if cursor_warning is not None:
        warnings.append(cursor_warning)
    if warnings:
        return _search_error_payload(warnings, privacy=_fts_privacy(content_inspected=False))

    bounded_limit = max(1, min(limit, MAX_MAIL_FTS_SEARCH_LIMIT))
    scan_limit = max(bounded_limit, min(MAX_MAIL_FTS_SEARCH_SCAN_ROWS, bounded_limit * 5))
    bounded_snippet_chars = max(1, min(max_snippet_chars, MAX_MAIL_FTS_SNIPPET_CHARS))
    index = _mail_fts_index_path(index_path)
    if not index.exists():
        return _search_error(
            "mail_fts_index_missing",
            "Mail FTS index is not available; build it before searching.",
            privacy=_fts_privacy(content_inspected=False),
        )
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as mail_connection:
            fingerprint = _check_schema(mail_connection)
            fts = _connect_mail_fts_index_readonly(index)
            _validate_mail_fts_schema(fts)
            rows = _select_mail_fts_rows(
                fts,
                _mail_fts_match_query(normalized_query),
                bounds=bounds,
                fingerprint=fingerprint,
                cursor_offset=cursor_offset,
                limit=scan_limit,
            )
            stale_count = _mail_fts_stale_count(fts, fingerprint)
            index_state = _mail_fts_index_state(fts, mail_connection, fingerprint)
            results: list[dict[str, Any]] = []
            snippet_returned = False
            scanned_count = 0
            stale_content_count = 0
            content_root = mail_root or _mail_content_root(resolved_db_path)
            file_index = _scan_mail_message_files(content_root)
            for indexed in rows:
                scanned_count += 1
                mail_rowid = int(indexed["mail_rowid"])
                current_row = _select_mail_row(mail_connection, mail_rowid)
                if current_row is None:
                    continue
                if not _mail_row_matches_date_bounds(current_row, bounds):
                    continue
                indexed_content_state = str(indexed["content_state_sha256"] or "")
                current_content_state = _mail_fts_content_state_sha256(
                    content_root,
                    mail_rowid,
                    index=file_index,
                )
                if indexed_content_state != current_content_state:
                    stale_content_count += 1
                    continue
                matched_scopes = _mail_fts_matched_scopes(indexed, normalized_query, normalized_scopes)
                if not matched_scopes:
                    continue
                metadata = _row_to_metadata(
                    current_row,
                    content_status="available" if current_content_state else "unavailable",
                )
                snippet_scope, snippet = _mail_fts_result_snippet(
                    indexed,
                    normalized_query,
                    matched_scopes,
                    bounded_snippet_chars,
                )
                snippet_returned = snippet_returned or bool(snippet)
                metadata.update(
                    {
                        "matched_scope": matched_scopes[0],
                        "matched_scopes": matched_scopes,
                        "snippet": snippet,
                        "snippet_scope": snippet_scope,
                        "snippet_chars": len(snippet),
                        "content_returned": False,
                        "attachment_content_returned": False,
                        "fts_index_ref": _mail_fts_index_ref(index),
                        "index_path_returned": False,
                    }
                )
                attachment_names = _safe_json_list(indexed["attachment_names_json"])
                attachment_types = _safe_json_list(indexed["attachment_types_json"])
                attachment_count = int(indexed["attachment_count"] or 0)
                if attachment_count:
                    metadata["attachment_count"] = attachment_count
                if attachment_names:
                    metadata["attachment_filenames"] = attachment_names[:MAX_MAIL_DISCOVERY_LIMIT]
                if attachment_types:
                    metadata["attachment_types"] = attachment_types[:MAX_MAIL_DISCOVERY_LIMIT]
                results.append(metadata)
                if len(results) >= bounded_limit:
                    break
    except StoreUnavailableError:
        return _search_store_unavailable_result(privacy=_fts_privacy(content_inspected=False))
    except (OSError, sqlite3.Error):
        return _search_error(
            "mail_fts_unavailable",
            "Mail FTS index could not be searched safely.",
            privacy=_fts_privacy(content_inspected=False),
        )
    finally:
        try:
            fts.close()  # type: ignore[name-defined]
        except (NameError, sqlite3.Error):
            pass

    next_cursor = _next_cursor(
        cursor_offset,
        scanned_count,
        len(rows),
        len(results),
        bounded_limit,
        scan_limit,
    )
    warnings = []
    if stale_count:
        warnings.append(
            _warning(
                "mail_fts_stale_rows",
                "Mail FTS index contains rows from an older Mail schema fingerprint; rebuild the index.",
            )
        )
    if stale_content_count:
        warnings.append(
            _warning(
                "mail_fts_stale_content",
                "Mail FTS index contains rows whose local message content changed or disappeared; rebuild the index.",
            )
        )
    if index_state["state"] != "ready":
        warnings.append(
            _warning(
                "mail_fts_partial_coverage",
                "Mail FTS index coverage is "
                + index_state["state"]
                + "; zero or few results may reflect missing index coverage, not message absence. "
                + "Check mail_fts_status and resume the build with checkpoint_cursor.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _fts_privacy(
            content_inspected=True,
            durable_index_written=False,
            content_snippet_returned=snippet_returned,
        ),
        "query": {
            "scope": "fts",
            "scopes": normalized_scopes,
            "limit": bounded_limit,
            "after": bounds.get("after"),
            "before": bounds.get("before"),
            "cursor": cursor or "",
            "index_ref": _mail_fts_index_ref(index),
            "index_path_returned": False,
        },
        "index_state": index_state,
        "results": results,
        "result_count": len(results),
        "next_cursor": next_cursor,
        "warnings": warnings,
    }


def get_mail_metadata(
    handle: str,
    *,
    db_path: Path | None = None,
    mail_root: Path | None = None,
) -> dict[str, Any]:
    if not is_int_handle(handle, "mail:message"):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [
                {
                    "code": "invalid_handle",
                    "message": "Expected mail:message opaque handle from search output.",
                }
            ],
        }

    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, handle)
            if rowid is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "mail",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = connection.execute(
                """
                SELECT
                    m.ROWID AS rowid,
                    s.subject AS subject,
                    mb.url AS mailbox_url,
                    m.date_received AS date_received,
                    m.date_sent AS date_sent,
                    m.read AS read,
                    m.flagged AS flagged,
                    m.deleted AS deleted,
                    m.size AS size
                FROM messages m
                LEFT JOIN subjects s ON m.subject = s.ROWID
                LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
                WHERE m.ROWID = ?
                  AND COALESCE(m.deleted, 0) = 0
                LIMIT 1
                """,
                (rowid,),
            ).fetchone()
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [_mail_store_unavailable_warning()],
        }

    result = _row_to_metadata(row) if row else None
    warnings: list[dict[str, str]] = []
    if row and result is not None:
        root = mail_root or _mail_content_root(resolved_db_path)
        file_metadata = _mail_message_file_metadata(root, int(row["rowid"]), fingerprint)
        if file_metadata is None:
            result.update(
                {
                    "header_metadata_status": "unavailable",
                    "attachment_metadata_status": "unavailable",
                    "full_headers_returned": False,
                    "full_email_returned": False,
                    "attachment_content_returned": False,
                    "attachment_paths_returned": False,
                }
            )
            warnings.append(
                _warning(
                    "message_metadata_unavailable",
                    "Mail header and attachment metadata were not available through the local message file.",
                )
            )
        else:
            result.update(file_metadata)

    return {
        "schema_version": 1,
        "status": "ok" if row else "not_found",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": result,
        "warnings": warnings,
    }


def get_mail_content(
    handle: str,
    *,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    offset: int = 0,
) -> dict[str, Any]:
    if not is_int_handle(handle, "mail:message"):
        return _invalid_content_handle_result()

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    if offset < 0:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [
                _warning(
                    "invalid_offset",
                    "Mail content offset must be zero or greater.",
                )
            ],
        }
    bounded_offset = offset
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, handle)
            if rowid is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "mail",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(content_inspected=False),
                    "result": None,
                    "warnings": [],
                }
            row = _select_mail_row(connection, rowid)
            if row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "mail",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(content_inspected=False),
                    "result": None,
                    "warnings": [],
                }
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_mail_store_unavailable_warning()],
        }

    root = mail_root or _mail_content_root(resolved_db_path)
    message_path, file_status = _find_message_file_with_status(root, int(row["rowid"]))
    if message_path is None:
        result = _row_to_content_metadata(row)
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": result,
            "warnings": [
                _warning(
                    "content_unavailable",
                    "No local message file exists for this handle (the message body may not be "
                    "downloaded locally yet); open the message in Mail.app to download it, then retry.",
                )
            ],
        }

    try:
        raw = message_path.read_bytes()
        text = _extract_text_from_emlx(raw)
    except (OSError, ValueError):
        result = _row_to_content_metadata(row)
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=False),
            "result": result,
            "warnings": [_warning("read_error", "Mail content could not be read safely.")],
        }

    if text is None:
        result = _row_to_content_metadata(row)
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _content_privacy(content_inspected=True),
            "result": result,
            "warnings": [
                _warning(
                    "unsupported_message_format",
                    "Mail content format is not supported for plain text extraction.",
                )
            ],
        }

    content_text, truncated, total_chars, next_offset = _bounded_text_page(
        text,
        bounded_chars,
        offset=bounded_offset,
    )
    result = _row_to_content_metadata(row)
    result.update(
        {
            "content_text": content_text,
            "content_chars": len(content_text),
            "content_offset": bounded_offset,
            "content_total_chars": total_chars,
            "next_offset": next_offset,
            "truncated": truncated,
            "content_status": file_status,
        }
    )
    partial_warnings = (
        [
            _warning(
                "partial_download",
                "This message exists locally only as a partial download; text shown is what "
                "Mail has fetched so far and attachments may be missing.",
            )
        ]
        if file_status == "partial"
        else []
    )
    warnings = [*partial_warnings]
    if truncated:
        warnings.append(
            _warning("content_truncated", "Mail content was truncated to the requested limit.")
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def get_mail_unsubscribe_metadata(
    handle: str,
    *,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    include_body_links: bool = False,
) -> dict[str, Any]:
    """Return allowlisted unsubscribe detail for one exact Mail message.

    Headers are the default. Optional body-link inspection examines only HTML
    anchors in the selected MIME body. The body, anchor labels, unrelated
    headers/links, raw account identifiers, and local paths are never returned.
    """
    if not is_int_handle(handle, "mail:message"):
        return _invalid_unsubscribe_metadata_handle_result()

    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, handle)
            row = _select_mail_row(connection, rowid) if rowid is not None else None
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _unsubscribe_metadata_privacy(header_inspected=False),
            "result": None,
            "result_count": 0,
            "warnings": [_mail_store_unavailable_warning()],
        }

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _unsubscribe_metadata_privacy(header_inspected=False),
            "result": None,
            "result_count": 0,
            "warnings": [],
        }

    root = mail_root or _mail_content_root(resolved_db_path)
    message_path, file_status = _find_message_file_with_status(root, int(row["rowid"]))
    identity = _mail_unsubscribe_identity(row)
    if message_path is None:
        return {
            "schema_version": 1,
            "status": "metadata_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _unsubscribe_metadata_privacy(header_inspected=False),
            "result": identity,
            "result_count": 1,
            "warnings": [
                _warning(
                    "unsubscribe_metadata_unavailable",
                    "No unique local Mail message file was available for exact unsubscribe header inspection.",
                )
            ],
        }

    try:
        header_prefix = _emlx_header_prefix(message_path, limit=MAX_TRIAGE_HEADER_BYTES)
        if b"\r\n\r\n" not in header_prefix and b"\n\n" not in header_prefix:
            raise ValueError("bounded Mail header terminator unavailable")
        message = BytesParser(policy=policy.default).parsebytes(
            header_prefix,
            headersonly=True,
        )
    except (LookupError, OSError, TypeError, UnicodeError, ValueError):
        return {
            "schema_version": 1,
            "status": "metadata_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _unsubscribe_metadata_privacy(header_inspected=False),
            "result": identity,
            "result_count": 1,
            "warnings": [
                _warning(
                    "unsubscribe_metadata_read_error",
                    "Mail unsubscribe headers could not be read safely.",
                )
            ],
        }

    unsubscribe_values = message.get_all("List-Unsubscribe", [])
    post_values = message.get_all("List-Unsubscribe-Post", [])
    help_values = message.get_all("List-Help", [])
    post_present = bool(post_values)
    post_valid = any(_is_rfc8058_post_header(value) for value in post_values)
    invalid_post_count = sum(
        1 for value in post_values if not _is_rfc8058_post_header(value)
    )

    unsubscribe_urls, rejected_unsubscribe = _allowlisted_list_header_urls(
        unsubscribe_values
    )
    help_urls, rejected_help = _allowlisted_list_header_urls(help_values)
    unsubscribe_endpoints = [
        _mail_unsubscribe_endpoint(url, one_click_header=post_valid)
        for url in unsubscribe_urls
    ]
    help_endpoints = [_mail_help_endpoint(url) for url in help_urls]
    one_click_available = any(
        endpoint["classification"] == "one_click"
        for endpoint in unsubscribe_endpoints
    )
    body_unsubscribe_endpoints: list[dict[str, Any]] = []
    body_links_inspected = False
    body_link_warnings: list[dict[str, str]] = []
    if include_body_links:
        (
            body_unsubscribe_endpoints,
            body_links_inspected,
            body_link_warnings,
        ) = _mail_body_unsubscribe_endpoints(message_path)

    warnings: list[dict[str, str]] = [*body_link_warnings]
    rejected_count = rejected_unsubscribe + rejected_help
    if rejected_count:
        warnings.append(
            _warning(
                "unsafe_list_endpoint_omitted",
                "One or more malformed, control-bearing, or non-http(s)/mailto list endpoints were omitted.",
            )
        )
    if invalid_post_count:
        warnings.append(
            _warning(
                "invalid_list_unsubscribe_post",
                "List-Unsubscribe-Post was present but did not match the RFC 8058 one-click value.",
            )
        )
    if post_valid and not one_click_available:
        warnings.append(
            _warning(
                "one_click_endpoint_unavailable",
                "RFC 8058 one-click metadata was present, but no allowlisted HTTPS unsubscribe endpoint was available.",
            )
        )
    if file_status == "partial":
        warnings.append(
            _warning(
                "partial_download",
                "This message exists locally only as a partial download; locally available headers"
                + (" and requested body links" if body_links_inspected else "")
                + " were inspected.",
            )
        )

    result = {
        **identity,
        "content_status": file_status,
        "header_presence": {
            "list_unsubscribe": bool(unsubscribe_values),
            "list_unsubscribe_post": post_present,
            "list_help": bool(help_values),
        },
        "rfc8058_one_click_header": post_valid,
        "one_click_available": one_click_available,
        "unsubscribe_endpoints": unsubscribe_endpoints,
        "help_endpoints": help_endpoints,
        "body_links_requested": include_body_links,
        "body_links_inspected": body_links_inspected,
        "body_unsubscribe_endpoints": body_unsubscribe_endpoints,
        "rejected_endpoint_count": rejected_count,
        "message_body_returned": False,
        "raw_headers_returned": False,
        "unrelated_headers_returned": False,
        "local_path_returned": False,
        "raw_account_identifier_returned": False,
    }
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _unsubscribe_metadata_privacy(
            header_inspected=True,
            endpoint_urls_returned=bool(
                unsubscribe_endpoints or help_endpoints or body_unsubscribe_endpoints
            ),
            message_body_inspected=body_links_inspected,
        ),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def list_mail_attachments(
    handle: str,
    *,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    limit: int = DEFAULT_ATTACHMENTS_LIMIT,
) -> dict[str, Any]:
    if not is_int_handle(handle, "mail:message"):
        return _invalid_attachment_message_handle_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, handle)
            if rowid is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "mail",
                    "schema_fingerprint": fingerprint,
                    "privacy": _attachment_privacy(content_inspected=False),
                    "results": [],
                    "result_count": 0,
                    "warnings": [],
                }
            row = _select_mail_row(connection, rowid)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _attachment_privacy(content_inspected=False),
            "results": [],
            "result_count": 0,
            "warnings": [_mail_store_unavailable_warning()],
        }

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _attachment_privacy(content_inspected=False),
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    root = mail_root or _mail_content_root(resolved_db_path)
    message = _parse_message_for_attachment_access(root, int(row["rowid"]))
    if message is None:
        return {
            "schema_version": 1,
            "status": "attachments_unavailable",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _attachment_privacy(content_inspected=False),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "attachments_unavailable",
                    "Mail attachment metadata was not available through the local message file.",
                )
            ],
        }

    results = _mail_attachment_metadata_list(
        message,
        fingerprint=fingerprint,
        rowid=int(row["rowid"]),
        limit=bounded_limit,
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _attachment_privacy(content_inspected=True),
        "query": {"scope": "message_attachments", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def export_mail_attachment(
    message_handle: str,
    attachment_handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    db_path: Path | None = None,
    mail_root: Path | None = None,
) -> dict[str, Any]:
    if not is_int_handle(message_handle, "mail:message"):
        return _invalid_attachment_message_handle_result(export=True)
    if not is_opaque_handle(attachment_handle, ATTACHMENT_HANDLE_PREFIX):
        return _invalid_attachment_export_handle_result()

    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, message_handle)
            if rowid is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "mail",
                    "schema_fingerprint": fingerprint,
                    "privacy": _export_privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = _select_mail_row(connection, rowid)
    except StoreUnavailableError:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [_mail_store_unavailable_warning()],
        }

    if row is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    root = mail_root or _mail_content_root(resolved_db_path)
    message = _parse_message_for_attachment_access(root, int(row["rowid"]))
    if message is None:
        return _mail_attachment_export_unavailable_result(
            None,
            fingerprint,
            "attachments_unavailable",
        )

    target_part = _find_mail_attachment_part(
        message,
        fingerprint=fingerprint,
        rowid=int(row["rowid"]),
        attachment_handle=attachment_handle,
    )
    if target_part is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "mail",
            "schema_fingerprint": fingerprint,
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    part_index, part = target_part
    result = _mail_attachment_metadata(
        part,
        fingerprint=fingerprint,
        rowid=int(row["rowid"]),
        part_index=part_index,
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
    data = _attachment_payload_bytes(part)
    if data is None:
        return _mail_attachment_export_unavailable_result(
            result,
            fingerprint,
            "mail_attachment_unavailable",
        )

    target_dir = output_dir.expanduser()
    if target_dir.is_symlink() or (target_dir.exists() and not target_dir.is_dir()):
        return _mail_attachment_export_unavailable_result(
            result,
            fingerprint,
            "invalid_output_dir",
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if target_dir.is_symlink() or not target_dir.is_dir():
            return _mail_attachment_export_unavailable_result(
                result,
                fingerprint,
                "invalid_output_dir",
            )
        target = _write_unique_export_file(
            target_dir,
            _mail_attachment_export_filename(filename, result),
            data,
        )
    except OSError:
        return _mail_attachment_export_unavailable_result(
            result,
            fingerprint,
            "mail_attachment_export_failed",
        )

    result.update(
        {
            "attachment_content_exported": True,
            "exported_path": str(target),
            "exported_filename": target.name,
            "exported_bytes": len(data),
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(attachment_content_exported=True),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def plan_mail_change(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    message_handles: list[str] | None = None,
    target_mailbox_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
    include_private: bool = False,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    if attachment_paths and normalized_operation not in LOCAL_ATTACHMENT_OPERATIONS:
        return _plan_error(
            [
                _warning(
                    "unexpected_attachment_paths",
                    "Mail local attachments are supported only for draft/send/reply/forward planning.",
                )
            ]
        )
    if target_mailbox_handle.strip() and normalized_operation != "move_message":
        return _plan_error(
            [
                _warning(
                    "unexpected_target_mailbox_handle",
                    "Only Mail move_message planning accepts a target mailbox handle.",
                )
            ]
        )
    if sender_handle.strip() and normalized_operation not in SENDER_SELECTION_OPERATIONS:
        return _plan_error(
            [
                _warning(
                    "unexpected_sender_handle",
                    "Mail sender selection is supported only for draft/send/reply/reply-all/forward planning.",
                )
            ]
        )
    if signature_handle.strip() and normalized_operation not in SIGNATURE_SELECTION_OPERATIONS:
        return _plan_error(
            [
                _warning(
                    "unexpected_signature_handle",
                    "Mail signature selection is supported only for draft/send/reply/reply-all/forward planning.",
                )
            ]
        )
    if template_handle.strip() and normalized_operation not in CONTENT_OPERATIONS | REPLY_OPERATIONS | FORWARD_OPERATIONS:
        return _plan_error(
            [
                _warning(
                    "unexpected_template_handle",
                    "Mail template selection is supported only for draft/send/reply/reply-all/forward planning.",
                )
            ]
        )
    if include_source_attachments and normalized_operation != "forward_message":
        return _plan_error(
            [
                _warning(
                    "unexpected_include_source_attachments",
                    "Mail source attachment forwarding is supported only for forward_message.",
                )
            ]
        )
    if normalized_operation not in TRIAGE_OPERATIONS and _triage_message_handle_inputs("", message_handles):
        return _plan_error(
            [
                _warning(
                    "unexpected_message_handles",
                    "Mail repeated message handles are supported only for exact bulk triage operations.",
                )
            ]
        )
    if normalized_operation in TRIAGE_OPERATIONS:
        triage_handles = _triage_message_handle_inputs(message_handle, message_handles)
        if len(triage_handles) > 1:
            return plan_mail_bulk_triage(
                normalized_operation,
                message_handles=triage_handles,
                target_mailbox_handle=target_mailbox_handle,
                db_path=db_path,
                mail_root=mail_root,
            )
        return plan_mail_triage(
            normalized_operation,
            message_handle=triage_handles[0] if triage_handles else message_handle,
            target_mailbox_handle=target_mailbox_handle,
            db_path=db_path,
            mail_root=mail_root,
        )
    if normalized_operation in REPLY_OPERATIONS:
        return plan_mail_reply(
            normalized_operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            db_path=db_path,
            mail_root=mail_root,
            script_runner=script_runner,
            include_private=include_private,
        )
    if normalized_operation in FORWARD_OPERATIONS:
        return plan_mail_forward(
            normalized_operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            include_source_attachments=include_source_attachments,
            db_path=db_path,
            mail_root=mail_root,
            script_runner=script_runner,
            include_private=include_private,
        )

    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create_draft, send_message, reply_message, reply_all_message, forward_message, mark_read, mark_unread, flag_message, unflag_message, archive_message, trash_message, or move_message.",
            )
        )
    if target_mailbox_handle.strip():
        warnings.append(
            _warning(
                "unexpected_target_mailbox_handle",
                "Mail draft, send, reply, reply-all, and forward operations do not accept a target mailbox handle.",
            )
        )
    if message_handle.strip() or _triage_message_handle_inputs("", message_handles):
        label = "send" if normalized_operation == "send_message" else "draft creation"
        warnings.append(
            _warning(
                "unexpected_message_handle",
                f"Mail {label} requires recipients and content, not a message handle.",
            )
        )

    normalized_to, to_warnings = _normalize_recipients(to or [], field="to")
    normalized_cc, cc_warnings = _normalize_recipients(cc or [], field="cc")
    normalized_bcc, bcc_warnings = _normalize_recipients(bcc or [], field="bcc")
    warnings.extend(to_warnings)
    warnings.extend(cc_warnings)
    warnings.extend(bcc_warnings)
    if not normalized_to:
        label = "send" if normalized_operation == "send_message" else "draft creation"
        warnings.append(_warning("missing_to", f"Mail {label} requires at least one To recipient."))

    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            warnings.append(template_warning)
        if template is not None:
            if body_text.strip():
                warnings.append(
                    _warning(
                        "unexpected_body_text_with_template",
                        "Mail template planning uses the selected template body; direct body_text is not accepted.",
                    )
                )
            if subject.strip() and str(template.get("subject") or "").strip():
                warnings.append(
                    _warning(
                        "unexpected_subject_with_template",
                        "Mail template planning uses the selected template subject when the template has one.",
                    )
                )
    draft_subject_source = str(template.get("subject") or subject) if template is not None else subject
    draft_body_source = str(template["body_text"]) if template is not None else body_text

    normalized_subject, subject_warning = _normalize_draft_subject(draft_subject_source)
    if subject_warning is not None:
        warnings.append(subject_warning)
    normalized_body, body_warning = _normalize_draft_body(draft_body_source)
    if body_warning is not None:
        warnings.append(body_warning)
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        _, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            warnings.append(sender_warning)
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        _, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            warnings.append(signature_warning)
    attachment_infos: list[dict[str, Any]] = []
    if normalized_operation in {"create_draft", "send_message"}:
        attachment_infos, attachment_warnings = _resolve_draft_attachments(attachment_paths or [])
        warnings.extend(attachment_warnings)

    if warnings:
        return _plan_error(warnings)

    body_preview, body_preview_truncated = _bounded_text(
        normalized_body,
        MAX_DRAFT_BODY_PREVIEW_CHARS,
    )
    is_send = normalized_operation == "send_message"
    if sender_metadata is None:
        target = {
            "account": "mail_app_default",
            "mailbox": "outbound_send" if is_send else "drafts",
        }
        sender_selection: dict[str, Any] = {
            "mode": "mail_app_default",
            "sender_selected": False,
        }
    else:
        target = {
            "account": "selected_sender",
            "account_ref": sender_metadata["account_ref"],
            "sender_ref": sender_metadata["sender_ref"],
            "mailbox": "outbound_send" if is_send else "drafts",
        }
        sender_selection = {
            "mode": "exact_sender_handle",
            "sender_selected": True,
            "sender_handle": sender_handle.strip(),
            "sender_ref": sender_metadata["sender_ref"],
            "account_ref": sender_metadata["account_ref"],
            "email_preview": sender_metadata["email_preview"],
            "selection_supported": sender_metadata["selection_supported"],
            "full_email_returned": False,
            "sender_string_returned": False,
        }
    if signature_metadata is None:
        signature_selection: dict[str, Any] = {
            "mode": "signature_cleared",
            "signature_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        signature_selection = {
            "mode": "exact_signature_handle",
            "signature_selected": True,
            "signature_handle": signature_handle.strip(),
            "signature_ref": signature_metadata["signature_ref"],
            "name": signature_metadata["name"],
            "selection_supported": signature_metadata["selection_supported"],
            "body_returned": False,
            "content_returned": False,
        }
    if template_metadata is None:
        template_selection: dict[str, Any] = {
            "mode": "direct_body_text",
            "template_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        template_selection = {
            "mode": "exact_template_handle",
            "template_selected": True,
            "template_handle": template_handle.strip(),
            "template_ref": template_metadata["template_ref"],
            "name": template_metadata["name"],
            "subject": template_metadata["subject"],
            "body_chars": template_metadata["body_chars"],
            "body_returned": False,
            "content_returned": False,
        }
    attachment_preview = _draft_attachment_preview(
        attachment_infos,
        send_permitted=is_send,
    )
    proposed = {
        "kind": "mail_send" if is_send else "mail_draft",
        "format": "plaintext",
        "to": normalized_to,
        "cc": normalized_cc,
        "bcc": normalized_bcc,
        "recipient_count": len(normalized_to) + len(normalized_cc) + len(normalized_bcc),
        "subject": normalized_subject,
        "body_chars": len(normalized_body),
        "body_preview_text": body_preview,
        "body_preview_chars": len(body_preview),
        "body_preview_truncated": body_preview_truncated,
        "send_permitted": is_send,
        "irreversible_external_send": is_send,
        "retry_safe": not is_send and sender_metadata is None and signature_metadata is None and not attachment_infos,
        "attachments_permitted": bool(attachment_infos),
        "source_message_attachments_permitted": False,
        **attachment_preview,
        "sender_selection": sender_selection,
        "signature_selection": signature_selection,
        "template_selection": template_selection,
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
        "proposed": {
            **proposed,
            "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
            "attachment_identities": [info["identity"] for info in attachment_infos],
        },
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    result = {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(content_inspected=True),
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
    if include_private:
        result["_private"] = {"attachment_infos": copy.deepcopy(attachment_infos)}
    return result


def apply_mail_change(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    message_handles: list[str] | None = None,
    target_mailbox_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    if attachment_paths and normalized_operation not in LOCAL_ATTACHMENT_OPERATIONS:
        plan = _plan_error(
            [
                _warning(
                    "unexpected_attachment_paths",
                    "Mail local attachments are supported only for draft/send/reply/forward apply.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if target_mailbox_handle.strip() and normalized_operation != "move_message":
        plan = _plan_error(
            [
                _warning(
                    "unexpected_target_mailbox_handle",
                    "Only Mail move_message apply accepts a target mailbox handle.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if sender_handle.strip() and normalized_operation not in SENDER_SELECTION_OPERATIONS:
        plan = _plan_error(
            [
                _warning(
                    "unexpected_sender_handle",
                    "Mail sender selection is supported only for draft/send/reply/reply-all/forward apply.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if signature_handle.strip() and normalized_operation not in SIGNATURE_SELECTION_OPERATIONS:
        plan = _plan_error(
            [
                _warning(
                    "unexpected_signature_handle",
                    "Mail signature selection is supported only for draft/send/reply/reply-all/forward apply.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if template_handle.strip() and normalized_operation not in CONTENT_OPERATIONS | REPLY_OPERATIONS | FORWARD_OPERATIONS:
        plan = _plan_error(
            [
                _warning(
                    "unexpected_template_handle",
                    "Mail template selection is supported only for draft/send/reply/reply-all/forward apply.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if include_source_attachments and normalized_operation != "forward_message":
        plan = _plan_error(
            [
                _warning(
                    "unexpected_include_source_attachments",
                    "Mail source attachment forwarding is supported only for forward_message.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if normalized_operation not in TRIAGE_OPERATIONS and _triage_message_handle_inputs("", message_handles):
        plan = _plan_error(
            [
                _warning(
                    "unexpected_message_handles",
                    "Mail repeated message handles are supported only for exact bulk triage operations.",
                )
            ]
        )
        return _apply_error(_safe_warnings(plan), plan=plan)
    if normalized_operation in TRIAGE_OPERATIONS:
        triage_handles = _triage_message_handle_inputs(message_handle, message_handles)
        if len(triage_handles) > 1:
            return apply_mail_bulk_triage(
                normalized_operation,
                message_handles=triage_handles,
                target_mailbox_handle=target_mailbox_handle,
                approval_token=approval_token,
                confirm_apply=confirm_apply,
                db_path=db_path,
                mail_root=mail_root,
                script_runner=script_runner,
            )
        return apply_mail_triage(
            normalized_operation,
            message_handle=triage_handles[0] if triage_handles else message_handle,
            target_mailbox_handle=target_mailbox_handle,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
            db_path=db_path,
            mail_root=mail_root,
            script_runner=script_runner,
        )
    if normalized_operation in REPLY_OPERATIONS:
        return apply_mail_reply(
            normalized_operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
            db_path=db_path,
            mail_root=mail_root,
            script_runner=script_runner,
        )
    if normalized_operation in FORWARD_OPERATIONS:
        return apply_mail_forward(
            normalized_operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            include_source_attachments=include_source_attachments,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
            db_path=db_path,
            mail_root=mail_root,
            script_runner=script_runner,
        )

    plan = plan_mail_change(
        operation,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body_text=body_text,
        message_handle=message_handle,
        message_handles=message_handles,
        sender_handle=sender_handle,
        signature_handle=signature_handle,
        template_handle=template_handle,
        attachment_paths=attachment_paths,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=script_runner,
        include_private=True,
    )
    if target_mailbox_handle.strip():
        plan = {
            "schema_version": 1,
            "status": "error",
            "source": "mail",
            "privacy": _preview_privacy(),
            "warnings": [
                _warning(
                    "unexpected_target_mailbox_handle",
                    "Mail draft, send, and reply apply do not accept a target mailbox handle.",
                )
            ],
        }
        return _apply_error(_safe_warnings(plan), plan=plan)
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Mail apply approval token did not match the plan.")],
            plan=plan,
        )

    normalized_to, _ = _normalize_recipients(to or [], field="to")
    normalized_cc, _ = _normalize_recipients(cc or [], field="cc")
    normalized_bcc, _ = _normalize_recipients(bcc or [], field="bcc")
    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            return _apply_error([template_warning], plan=plan)
        planned_template = preview["proposed"].get("template_selection", {})
        if (
            template_metadata is None
            or template_metadata.get("template_ref") != planned_template.get("template_ref")
        ):
            return _apply_error(
                [_warning("stale_template_state", "Mail template changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    draft_subject_source = str(template.get("subject") or subject) if template is not None else subject
    draft_body_source = str(template["body_text"]) if template is not None else body_text
    normalized_subject, _ = _normalize_draft_subject(draft_subject_source)
    normalized_body, _ = _normalize_draft_body(draft_body_source)
    attachment_infos = _approved_draft_attachment_infos(plan)
    if attachment_paths and len(attachment_infos) != int(preview["proposed"].get("attachment_count") or 0):
        return _apply_error(
            [_warning("invalid_plan", "Mail attachment approval metadata was unavailable; re-plan before applying.")],
            plan=plan,
        )
    sender_identity: dict[str, str] | None = None
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            return _apply_error([sender_warning], plan=plan)
        planned_sender = preview["proposed"].get("sender_selection", {})
        if sender_metadata is None or sender_metadata.get("sender_ref") != planned_sender.get("sender_ref"):
            return _apply_error(
                [_warning("stale_sender_state", "Mail sender identity changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    signature_identity: dict[str, str] | None = None
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        signature_identity, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            return _apply_error([signature_warning], plan=plan)
        planned_signature = preview["proposed"].get("signature_selection", {})
        if (
            signature_metadata is None
            or signature_metadata.get("signature_ref") != planned_signature.get("signature_ref")
        ):
            return _apply_error(
                [_warning("stale_signature_state", "Mail signature changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    resolved_db_path = _resolve_db_path(db_path)
    resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
    runner = script_runner or _run_osascript

    if normalized_operation == "send_message":
        return _apply_mail_send(
            preview,
            to=normalized_to,
            cc=normalized_cc,
            bcc=normalized_bcc,
            subject=normalized_subject,
            body_text=normalized_body,
            sender_identity=sender_identity,
            sender_metadata=sender_metadata,
            signature_identity=signature_identity,
            signature_metadata=signature_metadata,
            template_metadata=template_metadata,
            attachment_infos=attachment_infos,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
            script_runner=runner,
            approval_fingerprint=fingerprint,
        )

    preexisting_draft_handles: set[str] | None = None
    already_applied = None
    needs_new_draft_attribution = (
        sender_identity is not None or signature_identity is not None or bool(attachment_infos)
    )
    if not needs_new_draft_attribution:
        already_applied = _find_matching_draft_content(
            normalized_subject,
            normalized_body,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
        )
    else:
        preexisting_draft_handles = _draft_handle_snapshot(
            normalized_subject,
            db_path=resolved_db_path,
        )
        if preexisting_draft_handles is None:
            return _apply_error(
                [_warning("draft_snapshot_unavailable", "Mail draft state could not be snapshotted before sender-selected apply.")],
                plan=plan,
            )
    if already_applied is not None:
        return _apply_success(
            already_applied,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Matching Mail draft already exists.")],
        )

    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-") as attachment_temp_dir:
            automation_attachment_paths = _prepare_draft_attachment_copies(
                attachment_infos,
                Path(attachment_temp_dir),
            )
            automation_output = runner(
                _mail_create_draft_script(
                    to=normalized_to,
                    cc=normalized_cc,
                    bcc=normalized_bcc,
                    subject=normalized_subject,
                    body_text=normalized_body,
                    sender=_sender_value(sender_identity),
                    signature_name=_signature_value(signature_identity),
                    attachment_paths=automation_attachment_paths,
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
    except DraftAttachmentChangedError:
        return _apply_error(
            [_warning("current_attachment_changed", "Mail draft attachment changed after approval; re-plan before applying.")],
            plan=plan,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail draft creation timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail draft could not be created safely.")],
            plan=plan,
        )

    if attachment_infos:
        automation_attachment_count = _extract_attachment_output_count(automation_output)
        if automation_attachment_count != len(attachment_infos):
            return _apply_error(
                [
                    _warning(
                        "attachment_read_back_unavailable",
                        "Mail draft was saved but attachment automation confirmation was unavailable.",
                    )
                ],
                plan=plan,
                status="partial",
                mutation_applied=True,
            )

    if sender_identity is not None and _extract_sender_output_email(automation_output) != sender_identity["email_address"]:
        return _apply_error(
            [_warning("sender_read_back_unavailable", "Mail draft was saved but selected sender read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    if signature_identity is not None and _extract_signature_output_name(automation_output) != signature_identity["name"]:
        return _apply_error(
            [
                _warning(
                    "signature_read_back_unavailable",
                    "Mail draft was saved but selected signature read-back was unavailable.",
                )
            ],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    if needs_new_draft_attribution:
        read_back_matches, read_back_truncated = _find_matching_draft_contents(
            normalized_subject,
            normalized_body,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
            excluded_handles=preexisting_draft_handles,
        )
        if read_back_truncated or len(read_back_matches) > 1:
            return _apply_error(
                [
                    _warning(
                        "ambiguous_draft_read_back",
                        "Mail draft creation succeeded but new matching Draft read-back was not uniquely attributable.",
                    )
                ],
                plan=plan,
                status="partial",
                mutation_applied=True,
            )
        read_back = read_back_matches[0] if read_back_matches else None
    else:
        read_back = _find_matching_draft_content(
            normalized_subject,
            normalized_body,
            db_path=resolved_db_path,
            mail_root=resolved_mail_root,
        )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail draft creation succeeded but read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    if attachment_infos:
        read_back = {
            **read_back,
            **_draft_attachment_read_back(attachment_infos),
        }
    if sender_metadata is not None:
        read_back = {
            **read_back,
            "sender_ref": sender_metadata["sender_ref"],
            "sender_selection_confirmed": True,
            "full_email_returned": False,
            "sender_string_returned": False,
        }
    if signature_metadata is not None:
        read_back = {
            **read_back,
            "signature_ref": signature_metadata["signature_ref"],
            "signature_selection_confirmed": True,
            "signature_body_returned": False,
            "signature_content_returned": False,
        }
    if template_metadata is not None:
        read_back = {
            **read_back,
            "template_ref": template_metadata["template_ref"],
            "template_selection_confirmed": True,
            "template_body_returned": False,
            "template_content_returned": False,
        }
    return _apply_success(
        read_back,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _resolve_mail_handle_rowids(
    connection,
    handles: list[str],
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT m.ROWID AS rowid
        FROM messages m
        WHERE COALESCE(m.deleted, 0) = 0
        """
    )
    return resolve_int_handles(
        handles,
        "mail:message",
        (int(row["rowid"]) for row in rows),
    )


def _resolve_mail_handle_rowid(connection, handle: str) -> int | None:
    return _resolve_mail_handle_rowids(connection, [handle]).get(handle)


class MailTriageIdentityUnavailable(RuntimeError):
    """Raised when a message cannot be addressed safely; `reason` says which
    precondition failed so plan-side warnings can tell the caller what to do."""

    def __init__(self, reason: str = "identity_unavailable") -> None:
        super().__init__(reason)
        self.reason = reason


_MESSAGE_IDENTITY_PLAN_MESSAGES = {
    "message_file_unavailable": (
        "Mail message RFC identity was not available: no local message file exists for this "
        "handle (the message may not be downloaded locally); open it in Mail.app to download "
        "it, then retry."
    ),
    "rfc_message_id_missing": (
        "Mail message RFC identity was not available: the local message file has no RFC "
        "Message-ID header, so Mail cannot be addressed safely for this operation; compose a "
        "fresh message instead of replying in-thread."
    ),
}


def _message_identity_unavailable_plan_warning(
    error: MailTriageIdentityUnavailable,
) -> dict[str, str]:
    return _warning(
        "message_identity_unavailable",
        _MESSAGE_IDENTITY_PLAN_MESSAGES.get(
            error.reason,
            "Mail message RFC identity was not available through the local message file.",
        ),
    )


class MailCleanupRefused(RuntimeError):
    def __init__(self, warning: dict[str, str]) -> None:
        super().__init__(warning["code"])
        self.warning = warning


def _resolve_triage_target(
    connection,
    handle: str,
    *,
    mail_root: Path | None = None,
    resolved_rowid: int | None = None,
    message_file_index: dict[int, dict[str, list[Path]]] | None = None,
) -> dict[str, Any] | None:
    """Resolve a mail:message handle to the fields needed to address + verify a status triage.

    Production wiring for Mail status triage uses this message-addressing bridge. Real-Mail
    validation (2026-06-12) established that the status mutation scoped to
    `account id "<UUID>"` + mailbox + RFC Message-ID) is proven against live Mail and is reversible.
    It also proved the Envelope Index ``messages.message_id`` column is an INTEGER hash, not the RFC
    Message-ID string AppleScript addresses by, and AppleScript's integer ``id of message`` does not
    equal the Envelope Index ROWID. This resolver therefore ignores the DB `message_id` value and
    recovers the RFC Message-ID from the selected local ``.emlx`` file. If the file/header is not
    available, it fails closed with ``MailTriageIdentityUnavailable``.

    Reads the current read/flagged state and mailbox identity straight from the Envelope Index. The mailbox
    URL is ``imap://<account-UUID>/<mailbox-path>``; the UUID is the Mail account id that AppleScript
    addresses by (`account id "<UUID>"`, confirmed against live Mail). Returns None for an unknown or
    deleted handle, or when identity fields are missing.
    """
    rowid = resolved_rowid
    if rowid is None:
        rowid = _resolve_mail_handle_rowid(connection, handle)
    elif not int_handle_matches(handle, "mail:message", rowid):
        return None
    if rowid is None:
        return None
    row = connection.execute(
        """
        SELECT
            m.ROWID AS rowid,
            s.subject AS subject,
            m.read AS read,
            m.flagged AS flagged,
            mb.url AS mailbox_url
        FROM messages m
        LEFT JOIN subjects s ON m.subject = s.ROWID
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE m.ROWID = ? AND COALESCE(m.deleted, 0) = 0
        LIMIT 1
        """,
        (rowid,),
    ).fetchone()
    if row is None or not row["mailbox_url"]:
        return None
    parsed_mailbox = _parse_mailbox_url(row["mailbox_url"])
    if parsed_mailbox is None:
        return None
    if mail_root is None:
        raise MailTriageIdentityUnavailable("mail_root_unavailable")
    message_path = _find_message_file(mail_root, rowid, index=message_file_index)
    if message_path is None:
        raise MailTriageIdentityUnavailable("message_file_unavailable")
    message_id = _message_id_from_emlx(message_path)
    if not message_id:
        raise MailTriageIdentityUnavailable("rfc_message_id_missing")
    mailbox = _mailbox_metadata(row["mailbox_url"])
    return {
        "handle": handle,
        "rowid": int(row["rowid"]),
        "subject": _bounded_string(row["subject"], MAX_PREVIEW_SUBJECT_CHARS),
        "message_id": message_id,
        "read": bool(row["read"]) if row["read"] is not None else False,
        "flagged": bool(row["flagged"]) if row["flagged"] is not None else False,
        "account_id": parsed_mailbox["account_id"],
        "account_ref": mailbox["account_ref"],
        "mailbox_name": parsed_mailbox["mailbox_name"],
        "mailbox_url": parsed_mailbox["mailbox_url"],
        "mailbox_ref": mailbox["mailbox_ref"],
    }


def _resolve_bulk_triage_targets(
    connection,
    handles: list[str],
    *,
    mail_root: Path,
) -> dict[str, dict[str, Any]] | None:
    """Resolve a bounded exact-handle batch with one row scan and one Mail-tree walk."""

    rowids = _resolve_mail_handle_rowids(connection, handles)
    if len(rowids) != len(handles):
        return None
    message_file_index = _scan_mail_message_files(
        mail_root,
        only_rowids=set(rowids.values()),
    )
    if message_file_index is None:
        raise MailTriageIdentityUnavailable("message_file_unavailable")

    targets: dict[str, dict[str, Any]] = {}
    for handle in handles:
        target = _resolve_triage_target(
            connection,
            handle,
            mail_root=mail_root,
            resolved_rowid=rowids[handle],
            message_file_index=message_file_index,
        )
        if target is None:
            return None
        targets[handle] = target
    return targets


def _parse_mailbox_url(value: Any) -> dict[str, str] | None:
    mailbox_url = str(value or "")
    parsed = urlparse(mailbox_url)
    account_id = parsed.netloc
    mailbox_name = unquote(parsed.path).strip("/")
    if not account_id or not mailbox_name:
        return None
    mailbox = _mailbox_metadata(mailbox_url)
    mailbox_ref = mailbox.get("mailbox_ref")
    if not mailbox_ref:
        return None
    return {
        "account_id": account_id,
        "account_ref": mailbox["account_ref"],
        "mailbox_name": mailbox_name,
        "mailbox_url": mailbox_url,
        "mailbox_ref": str(mailbox_ref),
    }


def _select_mailbox_rows(connection):
    return connection.execute(
        """
        SELECT ROWID AS mailbox_id, url
        FROM mailboxes
        WHERE url IS NOT NULL
        ORDER BY url ASC
        """
    ).fetchall()


def _mailbox_handle_from_parsed(parsed: dict[str, str], fingerprint: str) -> str:
    return make_opaque_handle(
        MAILBOX_HANDLE_PREFIX,
        fingerprint,
        parsed["mailbox_url"],
    )


def _mailbox_target_metadata(parsed: dict[str, str], fingerprint: str) -> dict[str, Any]:
    path_parts = [part for part in parsed["mailbox_name"].split("/") if part]
    return {
        "handle": _mailbox_handle_from_parsed(parsed, fingerprint),
        "mailbox_name": _bounded_string(path_parts[-1] if path_parts else parsed["mailbox_name"], 300),
        "mailbox_path": _bounded_string(parsed["mailbox_name"], 600),
        "mailbox_ref": parsed["mailbox_ref"],
        "account_ref": parsed["account_ref"],
        "supports_move_target": _mailbox_supports_arbitrary_move_target(parsed),
        "raw_identifier_returned": False,
        "account_identifier_returned": False,
    }


def _resolve_mailbox_handle(connection, fingerprint: str, handle: str) -> dict[str, str] | None:
    for row in _select_mailbox_rows(connection):
        parsed = _parse_mailbox_url(row["url"])
        if parsed is None:
            continue
        if opaque_handle_matches(handle, MAILBOX_HANDLE_PREFIX, fingerprint, parsed["mailbox_url"]):
            return parsed
    return None


def _mailbox_supports_arbitrary_move_target(parsed: dict[str, str]) -> bool:
    path_segments = [segment for segment in parsed["mailbox_name"].strip("/").split("/") if segment]
    for segment in path_segments:
        normalized = re.sub(r"[^a-z0-9]+", " ", segment.lower()).strip()
        tokens = set(normalized.split())
        if tokens & UNSUPPORTED_MOVE_TARGET_TOKENS:
            return False
    return True


def _invalid_mailbox_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_mailbox_handle",
                "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
            )
        ],
    }


def _normalize_synthetic_mailbox_name(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if not normalized:
        return "", _warning("missing_mailbox_name", "Mail synthetic mailbox operations require a mailbox name.")
    if len(normalized) > MAX_SYNTHETIC_MAILBOX_NAME_CHARS:
        return "", _warning("mailbox_name_too_long", "Mail synthetic mailbox name is too long.")
    if not normalized.startswith(SYNTHETIC_MAIL_TEST_PREFIX):
        return "", _warning("non_synthetic_mailbox_name", "Mail synthetic mailbox names must start with LAD-TEST-.")
    if "/" in normalized or ":" in normalized or "\\" in normalized or any(ord(char) < 32 for char in normalized):
        return "", _warning("invalid_mailbox_name", "Mail synthetic mailbox name cannot contain path separators or controls.")
    if not has_minimum_query_quality(normalized):
        return "", _warning("broad_mailbox_name", "Mail synthetic mailbox name requires at least two letters or digits.")
    return normalized, None


def _validate_synthetic_mailbox_target(parsed: dict[str, str]) -> dict[str, str] | None:
    mailbox_name = parsed.get("mailbox_name", "")
    if "/" in mailbox_name:
        return _warning("nested_mailbox_not_supported", "Mail synthetic mailbox management is limited to top-level LAD-TEST-* mailboxes.")
    _normalized, warning = _normalize_synthetic_mailbox_name(mailbox_name)
    return warning


def _mailbox_name_exists_for_account(connection, *, account_id: str, mailbox_name: str) -> bool:
    for row in _select_mailbox_rows(connection):
        parsed = _parse_mailbox_url(row["url"])
        if parsed is None:
            continue
        if parsed["account_id"] == account_id and parsed["mailbox_name"] == mailbox_name:
            return True
    return False


def _mailbox_message_count(connection, mailbox_url: str) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS message_count
        FROM messages m
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE mb.url = ?
          AND COALESCE(m.deleted, 0) = 0
        """,
        (mailbox_url,),
    ).fetchone()
    return int(row["message_count"]) if row is not None else 0


def _resolve_mailbox_for_management_apply(
    handle: str,
    *,
    db_path: Path | None,
    expected_ref: str,
) -> dict[str, Any]:
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
            parsed = _resolve_mailbox_handle(connection, fingerprint, handle)
            if parsed is None:
                return {"warning": _warning("mailbox_not_found", "Mail mailbox handle no longer resolves to a live mailbox.")}
            warning = _validate_synthetic_mailbox_target(parsed)
            if warning is not None:
                return {"warning": warning}
            if parsed["mailbox_ref"] != expected_ref:
                return {"warning": _warning("stale_mailbox_state", "Mail mailbox identity changed since the plan; re-plan before applying.")}
            if _mailbox_message_count(connection, parsed["mailbox_url"]) != 0:
                return {
                    "warning": _warning(
                        "mailbox_not_empty",
                        "Mail synthetic mailbox apply requires the LAD-TEST-* mailbox to still be empty.",
                    )
                }
            return parsed
    except StoreUnavailableError:
        return {"warning": _mail_store_unavailable_warning()}


def _mail_create_mailbox_script(*, account_id: str, mailbox_name: str) -> str:
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set targetAccount to account id {_applescript_string(account_id)}",
            f"    set mailboxNameValue to {_applescript_string(mailbox_name)}",
            "    set existingMatches to (mailboxes of targetAccount whose name is mailboxNameValue)",
            '    if (count of existingMatches) is not 0 then error "mailbox_already_exists"',
            "    make new mailbox at targetAccount with properties {name:mailboxNameValue}",
            "    set createdMatches to (mailboxes of targetAccount whose name is mailboxNameValue)",
            '    if (count of createdMatches) is not 1 then error "mailbox_read_back_not_unique"',
            "    set messageCountValue to count of messages of (first item of createdMatches)",
            '    return "mailbox_name:" & mailboxNameValue & linefeed & "message_count:" & (messageCountValue as text)',
            "end tell",
        ]
    ) + "\n"


def _mail_rename_mailbox_script(*, account_id: str, old_mailbox_name: str, new_mailbox_name: str) -> str:
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=old_mailbox_name)}",
            f"    set targetAccount to account id {_applescript_string(account_id)}",
            f"    set newMailboxNameValue to {_applescript_string(new_mailbox_name)}",
            '    if (count of messages of sourceBox) is not 0 then error "mailbox_not_empty"',
            "    set existingMatches to (mailboxes of targetAccount whose name is newMailboxNameValue)",
            '    if (count of existingMatches) is not 0 then error "mailbox_already_exists"',
            "    set name of sourceBox to newMailboxNameValue",
            "    set renamedMatches to (mailboxes of targetAccount whose name is newMailboxNameValue)",
            '    if (count of renamedMatches) is not 1 then error "mailbox_read_back_not_unique"',
            "    set messageCountValue to count of messages of (first item of renamedMatches)",
            '    return "mailbox_name:" & newMailboxNameValue & linefeed & "message_count:" & (messageCountValue as text)',
            "end tell",
        ]
    ) + "\n"


def _mail_delete_mailbox_script(*, account_id: str, mailbox_name: str) -> str:
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set targetAccount to account id {_applescript_string(account_id)}",
            f"    set mailboxNameValue to {_applescript_string(mailbox_name)}",
            f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
            '    if (count of messages of sourceBox) is not 0 then error "mailbox_not_empty"',
            "    delete sourceBox",
            "    delay 0.2",
            "    set remainingMatches to (mailboxes of targetAccount whose name is mailboxNameValue)",
            '    if (count of remainingMatches) is not 0 then error "mailbox_absence_not_confirmed"',
            '    return "mailbox_name:" & mailboxNameValue & linefeed & "message_count:0" & linefeed & "verified_absent:true"',
            "end tell",
        ]
    ) + "\n"


def _mailbox_management_read_back(
    operation: str,
    output: str,
    *,
    mailbox_name: str,
    account_ref: str,
) -> dict[str, Any] | None:
    values = _script_key_value_output(output)
    count_text = values.get("message_count", "")
    try:
        message_count = int(count_text)
    except ValueError:
        return None
    if values.get("mailbox_name") != mailbox_name:
        return None
    if operation in {"create_mailbox", "rename_mailbox"} and message_count != 0:
        return None
    verified_absent = values.get("verified_absent") == "true"
    if operation == "delete_mailbox" and not verified_absent:
        return None
    return {
        "kind": "mail_mailbox_management",
        "operation": operation,
        "account_ref": account_ref,
        "mailbox_name": mailbox_name,
        "message_count": message_count,
        "empty_mailbox_confirmed": message_count == 0,
        "verified_absent": verified_absent if operation == "delete_mailbox" else False,
        "synthetic_name_confirmed": mailbox_name.startswith(SYNTHETIC_MAIL_TEST_PREFIX),
        "raw_identifier_returned": False,
        "account_identifier_returned": False,
    }


def _mail_sender_identities(
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    runner = script_runner or _run_osascript
    try:
        output = runner(_mail_sender_identity_script(), MAIL_APPLESCRIPT_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError, MailAutomationError):
        return [], _warning(
            "mail_sender_source_unavailable",
            "Mail sender account metadata was unavailable through public Mail.app automation.",
        )
    return _parse_mail_sender_identity_rows(output), None


def _mail_sender_identity_script() -> str:
    return "\n".join(
        [
            "set fieldSep to ASCII character 31",
            "set rowSep to ASCII character 30",
            "set senderRows to {}",
            'tell application "Mail"',
            "    repeat with mailAccount in accounts",
            '        set accountIdentifier to ""',
            "        try",
            "            set accountIdentifier to id of mailAccount as text",
            "        end try",
            '        set accountNameValue to ""',
            "        try",
            "            set accountNameValue to name of mailAccount as text",
            "        end try",
            "        set enabledValue to false",
            "        try",
            "            set enabledValue to enabled of mailAccount as boolean",
            "        end try",
            '        set fullNameValue to ""',
            "        try",
            "            set fullNameValue to full name of mailAccount as text",
            "        end try",
            "        set addressList to {}",
            "        try",
            "            set addressList to email addresses of mailAccount",
            "        end try",
            "        repeat with senderAddress in addressList",
            "            set addressText to senderAddress as text",
            '            if accountIdentifier is not "" and addressText is not "" then',
            "                set end of senderRows to accountIdentifier & fieldSep & accountNameValue & fieldSep & (enabledValue as text) & fieldSep & fullNameValue & fieldSep & addressText",
            "            end if",
            "        end repeat",
            "    end repeat",
            "end tell",
            "set AppleScript's text item delimiters to rowSep",
            "set outputText to senderRows as text",
            "set AppleScript's text item delimiters to \"\"",
            "return outputText",
        ]
    ) + "\n"


def _parse_mail_sender_identity_rows(output: str) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in output.split("\x1e"):
        parts = row.split("\x1f")
        if len(parts) != 5:
            continue
        account_id, account_name, enabled_text, full_name, email_address = [
            part.strip() for part in parts
        ]
        normalized_email = _normalize_sender_email(email_address)
        if not account_id or not normalized_email or enabled_text.casefold() != "true":
            continue
        key = (account_id, normalized_email)
        if key in seen:
            continue
        seen.add(key)
        identities.append(
            {
                "account_id": account_id,
                "account_name": account_name,
                "full_name": full_name,
                "email_address": normalized_email,
                "address_key": normalized_email.casefold(),
            }
        )
    return identities


def _normalize_sender_email(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value).strip())
    if not normalized or not _valid_email_address(normalized):
        return ""
    return normalized


def _sender_identity_key(identity: dict[str, str]) -> str:
    return f"{identity['account_id']}\0{identity['address_key']}"


def _sender_handle(identity: dict[str, str]) -> str:
    return make_opaque_handle(SENDER_HANDLE_PREFIX, _sender_identity_key(identity))


def _sender_address_counts(identities: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for identity in identities:
        counts[identity["address_key"]] = counts.get(identity["address_key"], 0) + 1
    return counts


def _sender_metadata(
    identity: dict[str, str],
    address_counts: dict[str, int],
) -> dict[str, Any]:
    address_key = identity["address_key"]
    return {
        "handle": _sender_handle(identity),
        "sender_ref": f"sender:{hashlib.sha256(_sender_identity_key(identity).encode('utf-8')).hexdigest()[:12]}",
        "account_ref": f"account:{hashlib.sha256(identity['account_id'].encode('utf-8')).hexdigest()[:12]}",
        "account_label": _mask_email_text(_bounded_string(identity["account_name"], 300)),
        "email_preview": _mask_email_address(identity["email_address"]),
        "selection_supported": address_counts.get(address_key, 0) == 1,
        "raw_identifier_returned": False,
        "account_identifier_returned": False,
        "full_email_returned": False,
        "sender_string_returned": False,
    }


def _sender_safe_search_text(identity: dict[str, str]) -> str:
    return " ".join(
        [
            _mask_email_text(_bounded_string(identity["account_name"], 300)),
            _mask_email_address(identity["email_address"]),
        ]
    ).casefold()


def _resolve_mail_sender_handle(
    handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[tuple[dict[str, str], list[dict[str, str]]] | None, dict[str, str] | None]:
    if not is_opaque_handle(handle, SENDER_HANDLE_PREFIX):
        return None, _warning(
            "invalid_sender_handle",
            "Expected mail:sender:v1 opaque handle from Mail sender search output.",
        )
    identities, warning = _mail_sender_identities(script_runner=script_runner)
    if warning is not None:
        return None, warning
    for identity in identities:
        if opaque_handle_matches(handle, SENDER_HANDLE_PREFIX, _sender_identity_key(identity)):
            return (identity, identities), None
    return None, None


def _resolve_mail_sender_for_plan(
    sender_handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[dict[str, str] | None, dict[str, Any] | None, dict[str, str] | None]:
    handle = sender_handle.strip()
    if not handle:
        return None, None, None
    resolved, warning = _resolve_mail_sender_handle(handle, script_runner=script_runner)
    if warning is not None:
        return None, None, warning
    if resolved is None:
        return None, None, _warning(
            "sender_not_found",
            "Mail sender handle did not resolve to a current configured sender.",
        )
    identity, identities = resolved
    address_counts = _sender_address_counts(identities)
    if address_counts.get(identity["address_key"], 0) != 1:
        return None, None, _warning(
            "ambiguous_sender_address",
            "Mail public automation can select sender text but cannot force one account when multiple accounts share the same sender address.",
        )
    metadata = _sender_metadata(identity, address_counts)
    return identity, metadata, None


def _sender_value(identity: dict[str, str] | None) -> str:
    if identity is None:
        return ""
    return identity["email_address"]


def _mail_signature_identities(
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    runner = script_runner or _run_osascript
    try:
        output = runner(_mail_signature_identity_script(), MAIL_APPLESCRIPT_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError, MailAutomationError):
        return [], _warning(
            "mail_signature_source_unavailable",
            "Mail signature metadata was unavailable through public Mail.app automation.",
        )
    return _parse_mail_signature_identity_rows(output), None


def _mail_signature_identity_script() -> str:
    return "\n".join(
        [
            "set rowSep to ASCII character 30",
            "set signatureRows to {}",
            'tell application "Mail"',
            "    repeat with mailSignature in signatures",
            '        set signatureNameValue to ""',
            "        try",
            "            set signatureNameValue to name of mailSignature as text",
            "        end try",
            '        if signatureNameValue is not "" then',
            "            set end of signatureRows to signatureNameValue",
            "        end if",
            "    end repeat",
            "end tell",
            "set AppleScript's text item delimiters to rowSep",
            "set outputText to signatureRows as text",
            "set AppleScript's text item delimiters to \"\"",
            "return outputText",
        ]
    ) + "\n"


def _parse_mail_signature_identity_rows(output: str) -> list[dict[str, str]]:
    signatures: list[dict[str, str]] = []
    for row in output.split("\x1e"):
        name = re.sub(r"\s+", " ", row).strip()
        if not name:
            continue
        signatures.append(
            {
                "name": name,
                "name_key": name,
            }
        )
    return signatures


def _signature_identity_key(signature: dict[str, str]) -> str:
    return signature["name_key"]


def _signature_handle(signature: dict[str, str]) -> str:
    return make_opaque_handle(SIGNATURE_HANDLE_PREFIX, _signature_identity_key(signature))


def _signature_ref(signature: dict[str, str]) -> str:
    return f"signature:{hashlib.sha256(_signature_identity_key(signature).encode('utf-8')).hexdigest()[:12]}"


def _signature_name_counts(signatures: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signature in signatures:
        counts[signature["name_key"]] = counts.get(signature["name_key"], 0) + 1
    return counts


def _signature_metadata(
    signature: dict[str, str],
    name_counts: dict[str, int],
) -> dict[str, Any]:
    name_key = signature["name_key"]
    return {
        "handle": _signature_handle(signature),
        "signature_ref": _signature_ref(signature),
        "name": _bounded_string(signature["name"], 300),
        "selection_supported": name_counts.get(name_key, 0) == 1,
        "body_returned": False,
        "content_returned": False,
        "raw_identifier_returned": False,
    }


def _signature_safe_search_text(signature: dict[str, str]) -> str:
    return _bounded_string(signature["name"], 300).casefold()


def _resolve_mail_signature_handle(
    handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[tuple[dict[str, str], list[dict[str, str]]] | None, dict[str, str] | None]:
    if not is_opaque_handle(handle, SIGNATURE_HANDLE_PREFIX):
        return None, _warning(
            "invalid_signature_handle",
            "Expected mail:signature:v1 opaque handle from Mail signature search output.",
        )
    signatures, warning = _mail_signature_identities(script_runner=script_runner)
    if warning is not None:
        return None, warning
    for signature in signatures:
        if opaque_handle_matches(handle, SIGNATURE_HANDLE_PREFIX, _signature_identity_key(signature)):
            return (signature, signatures), None
    return None, None


def _resolve_mail_signature_for_plan(
    signature_handle: str,
    *,
    script_runner: ScriptRunner | None = None,
) -> tuple[dict[str, str] | None, dict[str, Any] | None, dict[str, str] | None]:
    handle = signature_handle.strip()
    if not handle:
        return None, None, None
    resolved, warning = _resolve_mail_signature_handle(handle, script_runner=script_runner)
    if warning is not None:
        return None, None, warning
    if resolved is None:
        return None, None, _warning(
            "signature_not_found",
            "Mail signature handle did not resolve to a current configured signature.",
        )
    signature, signatures = resolved
    name_counts = _signature_name_counts(signatures)
    if name_counts.get(signature["name_key"], 0) != 1:
        return None, None, _warning(
            "ambiguous_signature_name",
            "Mail public automation selects signatures by name; duplicate signature names are not safe to select.",
        )
    metadata = _signature_metadata(signature, name_counts)
    return signature, metadata, None


def _signature_value(identity: dict[str, str] | None) -> str:
    if identity is None:
        return ""
    return identity["name"]


def _mail_template_state_path(state_path: Path | None = None) -> Path:
    if state_path is not None:
        return state_path.expanduser()
    configured = os.environ.get(MAIL_TEMPLATE_STATE_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_MAIL_TEMPLATE_STATE


def _empty_mail_template_state() -> dict[str, Any]:
    return {"schema_version": 1, "templates": []}


def _load_mail_template_state(state_path: Path | None = None) -> dict[str, Any]:
    path = _mail_template_state_path(state_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_mail_template_state()
    except (OSError, json.JSONDecodeError):
        return _empty_mail_template_state()
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return _empty_mail_template_state()
    templates = payload.get("templates")
    if not isinstance(templates, list):
        return _empty_mail_template_state()
    cleaned = []
    for item in templates:
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        body_text = str(item.get("body_text") or "")
        if not template_id or not name or not body_text:
            continue
        cleaned.append(
            {
                "id": template_id,
                "name": _bounded_string(name, MAX_TEMPLATE_NAME_CHARS),
                "subject": _bounded_string(str(item.get("subject") or ""), MAX_PREVIEW_SUBJECT_CHARS),
                "body_text": _bounded_string(body_text, MAX_DRAFT_BODY_CHARS),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            }
        )
    return {"schema_version": 1, "templates": cleaned}


def _write_mail_template_state(state: dict[str, Any], state_path: Path | None = None) -> None:
    path = _mail_template_state_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json(state) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
    temp_path.chmod(0o600)
    temp_path.replace(path)


def _normalize_template_name(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if not normalized:
        return "", _warning("missing_template_name", "Mail template name is required.")
    if len(normalized) > MAX_TEMPLATE_NAME_CHARS:
        return "", _warning("template_name_too_long", "Mail template name is too long.")
    return normalized, None


def _template_handle(template: dict[str, Any]) -> str:
    return make_opaque_handle(TEMPLATE_HANDLE_PREFIX, str(template["id"]))


def _template_ref(template: dict[str, Any]) -> str:
    return f"template:{hashlib.sha256(str(template['id']).encode('utf-8')).hexdigest()[:12]}"


def _template_metadata(template: dict[str, Any]) -> dict[str, Any]:
    body_text = str(template["body_text"])
    return {
        "handle": _template_handle(template),
        "template_ref": _template_ref(template),
        "name": _bounded_string(str(template["name"]), MAX_TEMPLATE_NAME_CHARS),
        "subject": _bounded_string(str(template.get("subject") or ""), MAX_PREVIEW_SUBJECT_CHARS),
        "body_chars": len(body_text),
        "created_at": str(template.get("created_at") or ""),
        "updated_at": str(template.get("updated_at") or ""),
        "body_returned": False,
        "content_returned": False,
        "raw_identifier_returned": False,
    }


def _resolve_mail_template_handle(
    handle: str,
    *,
    state_path: Path | None = None,
) -> dict[str, Any] | None:
    if not is_opaque_handle(handle, TEMPLATE_HANDLE_PREFIX):
        return None
    state = _load_mail_template_state(state_path)
    for template in state["templates"]:
        if opaque_handle_matches(handle, TEMPLATE_HANDLE_PREFIX, str(template["id"])):
            return template
    return None


def _resolve_mail_template_for_plan(
    template_handle: str,
    *,
    state_path: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, str] | None]:
    handle = template_handle.strip()
    if not handle:
        return None, None, None
    if not is_opaque_handle(handle, TEMPLATE_HANDLE_PREFIX):
        return None, None, _warning(
            "invalid_template_handle",
            "Expected mail:template:v1 opaque handle from Mail template search output.",
        )
    template = _resolve_mail_template_handle(handle, state_path=state_path)
    if template is None:
        return None, None, _warning(
            "template_not_found",
            "Mail template handle did not resolve to a plugin-managed template.",
        )
    return template, _template_metadata(template), None


def _template_error(
    warnings: list[dict[str, str]],
    *,
    content_inspected: bool = False,
    results: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _preview_privacy(content_inspected=content_inspected),
        "warnings": warnings,
    }
    if results:
        payload.update({"results": [], "result_count": 0})
    else:
        payload.update({"result": None, "result_count": 0})
    return payload


def _invalid_template_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _privacy(),
        "result": None,
        "result_count": 0,
        "warnings": [
            _warning(
                "invalid_template_handle",
                "Expected mail:template:v1 opaque handle from Mail template search output.",
            )
        ],
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_sender_output_email(output: str) -> str:
    text = str(output).strip()
    bracket_match = re.search(r"<([^<>@\s]+@[^<>@\s]+)>", text)
    if bracket_match:
        return _normalize_sender_email(bracket_match.group(1))
    direct = _normalize_sender_email(text)
    if direct:
        return direct
    email_match = EMAIL_TEXT_PATTERN.search(text)
    return _normalize_sender_email(email_match.group(0)) if email_match else ""


def _extract_signature_output_name(output: str) -> str:
    for line in str(output).splitlines():
        if line.startswith("signature:"):
            return line.removeprefix("signature:").strip()
    return ""


def _script_key_value_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in str(output).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        values[key.strip()] = value.strip()
    return values


def _mask_email_address(value: str) -> str:
    value = str(value).strip()
    if "@" not in value:
        return "<masked>"
    local, domain = value.rsplit("@", 1)
    if not local or not domain:
        return "<masked>"
    prefix = local[:1]
    return f"{prefix}***@{domain}"


EMAIL_TEXT_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+")


def _mask_email_text(value: str) -> str:
    return EMAIL_TEXT_PATTERN.sub(lambda match: _mask_email_address(match.group(0)), value)


def _special_mailbox_rank(kind: str, mailbox_name: str) -> int | None:
    last_segment = mailbox_name.strip("/").split("/")[-1]
    normalized = re.sub(r"[^a-z0-9]+", " ", last_segment.lower()).strip()
    if kind == "archive":
        if normalized in {"archive", "archives"}:
            return 0
        if normalized == "all mail":
            return 1
    if kind == "trash":
        if normalized in {"trash", "bin"}:
            return 0
        if normalized in {"deleted messages", "deleted items"}:
            return 1
    if kind == "junk":
        if normalized in {"junk", "junk mail", "junk e mail", "spam", "bulk mail"}:
            return 0
    return None


def _resolve_special_mailbox(
    connection,
    target: dict[str, Any],
    *,
    kind: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    rows = connection.execute(
        """
        SELECT ROWID AS mailbox_id, url
        FROM mailboxes
        WHERE url IS NOT NULL
        """
    ).fetchall()
    candidates: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        parsed = _parse_mailbox_url(row["url"])
        if parsed is None or parsed["account_id"] != target["account_id"]:
            continue
        rank = _special_mailbox_rank(kind, parsed["mailbox_name"])
        if rank is None:
            continue
        parsed = {
            **parsed,
            "mailbox_kind": kind,
        }
        if parsed["mailbox_ref"] == target["mailbox_ref"]:
            return parsed, None
        candidates.append((rank, parsed))

    if not candidates:
        return None, _warning(
            f"{kind}_mailbox_unavailable",
            f"Mail {kind} mailbox was not available for the selected message account.",
        )
    candidates.sort(key=lambda item: (item[0], item[1]["mailbox_name"]))
    best_rank = candidates[0][0]
    best = [candidate for rank, candidate in candidates if rank == best_rank]
    if len(best) != 1:
        return None, _warning(
            f"{kind}_mailbox_ambiguous",
            f"Mail {kind} mailbox resolution was ambiguous for the selected message account.",
        )
    return best[0], None


def _resolve_archive_mailbox(connection, target: dict[str, Any]) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    return _resolve_special_mailbox(connection, target, kind="archive")


def _resolve_trash_mailbox(connection, target: dict[str, Any]) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    return _resolve_special_mailbox(connection, target, kind="trash")


def _resolve_exact_move_mailbox(
    connection,
    target: dict[str, Any],
    mailbox_handle: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    fingerprint = _check_schema(connection)
    parsed = _resolve_mailbox_handle(connection, fingerprint, mailbox_handle)
    if parsed is None:
        return None, _warning(
            "target_mailbox_not_found",
            "Mail target mailbox handle did not resolve to a live mailbox.",
        )
    if not _mailbox_supports_arbitrary_move_target(parsed):
        return None, _warning(
            "unsupported_target_mailbox",
            "Mail move_message refuses Trash, Junk, or spam-class target mailboxes; use a dedicated approved operation.",
        )
    account_relation = "same_account" if parsed["account_id"] == target["account_id"] else "cross_account"
    return {**parsed, "mailbox_kind": "mailbox", "account_relation": account_relation}, None


def _message_id_from_emlx(path: Path) -> str | None:
    try:
        raw = _emlx_header_prefix(path, limit=MAX_TRIAGE_HEADER_BYTES)
    except OSError:
        return None
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            raw,
            headersonly=True,
        )
    except (LookupError, TypeError, UnicodeError, ValueError):
        return None
    return _normalize_message_id_header(message.get("Message-ID"))


def _emlx_header_prefix(path: Path, *, limit: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit)
    first_line, separator, remainder = raw.partition(b"\n")
    mime_prefix = remainder if separator and first_line.strip().isdigit() else raw
    for delimiter in (b"\r\n\r\n", b"\n\n"):
        header, found, _body_prefix = mime_prefix.partition(delimiter)
        if found:
            return header + found
    return mime_prefix


def _normalize_message_id_header(value: Any) -> str | None:
    text = _bounded_string(value, 500)
    if not text:
        return None
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text or None


def _triage_state_fingerprint(target: dict[str, Any]) -> str:
    """Bind the message's stable identity + mutable status state so apply refuses on drift."""
    payload = {
        "message_id": target["message_id"],
        "mailbox_ref": target["mailbox_ref"],
        "read": bool(target["read"]),
        "flagged": bool(target["flagged"]),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _mail_set_read_status_script(
    *,
    account_id: str,
    mailbox_name: str,
    message_id: str,
    target_read: bool,
) -> str:
    """AppleScript that flips exactly one message's read flag. Never moves or deletes anything.

    Scopes to the message's own `account id` + mailbox and matches the globally-unique Message-ID;
    errors out unless exactly one message matches, so a triage can never touch the wrong message.
    """
    flag = "true" if target_read else "false"
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set triageBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
            f"    set triageMatches to (messages of triageBox whose message id is {_applescript_string(message_id)})",
            '    if (count of triageMatches) is not 1 then error "triage_target_not_unique"',
            f"    set read status of (first item of triageMatches) to {flag}",
            '    return "ok"',
            "end tell",
        ]
    ) + "\n"


def _mail_set_flagged_status_script(
    *,
    account_id: str,
    mailbox_name: str,
    message_id: str,
    target_flagged: bool,
) -> str:
    """AppleScript that flips exactly one message's flag. Never moves or deletes anything."""
    flag = "true" if target_flagged else "false"
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set triageBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
            f"    set triageMatches to (messages of triageBox whose message id is {_applescript_string(message_id)})",
            '    if (count of triageMatches) is not 1 then error "triage_target_not_unique"',
            f"    set flagged status of (first item of triageMatches) to {flag}",
            '    return "ok"',
            "end tell",
        ]
    ) + "\n"


def _mailbox_script_spec(*, account_id: str, mailbox_name: str) -> str:
    parts = [part for part in mailbox_name.split("/") if part]
    if not parts:
        parts = [mailbox_name]
    spec = f"account id {_applescript_string(account_id)}"
    for part in parts:
        spec = f"mailbox {_applescript_string(part)} of {spec}"
    return spec


def _mail_archive_message_script(
    *,
    account_id: str,
    source_mailbox_name: str,
    target_mailbox_name: str,
    message_id: str,
) -> str:
    """AppleScript that moves exactly one message to Archive. Never sends or permanently deletes."""

    return "\n".join(
        [
            'tell application "Mail"',
            f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=source_mailbox_name)}",
            f"    set archiveBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=target_mailbox_name)}",
            f"    set triageMatches to (messages of sourceBox whose message id is {_applescript_string(message_id)})",
            '    if (count of triageMatches) is not 1 then error "triage_target_not_unique"',
            "    move (first item of triageMatches) to archiveBox",
            '    return "ok"',
            "end tell",
        ]
    ) + "\n"


def _mail_trash_message_script(
    *,
    account_id: str,
    source_mailbox_name: str,
    target_mailbox_name: str,
    message_id: str,
) -> str:
    """AppleScript that moves exactly one message to Trash. Never permanently deletes."""

    return "\n".join(
        [
            'tell application "Mail"',
            f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=source_mailbox_name)}",
            f"    set trashBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=target_mailbox_name)}",
            f"    set triageMatches to (messages of sourceBox whose message id is {_applescript_string(message_id)})",
            '    if (count of triageMatches) is not 1 then error "triage_target_not_unique"',
            "    move (first item of triageMatches) to trashBox",
            '    return "ok"',
            "end tell",
        ]
    ) + "\n"


def _mail_move_message_script(
    *,
    source_account_id: str,
    target_account_id: str,
    source_mailbox_name: str,
    target_mailbox_name: str,
    message_id: str,
) -> str:
    """AppleScript that moves exactly one message to an exact selected mailbox."""

    return "\n".join(
        [
            'tell application "Mail"',
            f"    set sourceBox to {_mailbox_script_spec(account_id=source_account_id, mailbox_name=source_mailbox_name)}",
            f"    set targetBox to {_mailbox_script_spec(account_id=target_account_id, mailbox_name=target_mailbox_name)}",
            f"    set triageMatches to (messages of sourceBox whose message id is {_applescript_string(message_id)})",
            '    if (count of triageMatches) is not 1 then error "triage_target_not_unique"',
            "    move (first item of triageMatches) to targetBox",
            '    return "ok"',
            "end tell",
        ]
    ) + "\n"


def _triage_read_back_from_connection(connection, rowid: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            m.ROWID AS rowid,
            mb.url AS mailbox_url,
            m.read AS read,
            m.flagged AS flagged
        FROM messages m
        JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE m.ROWID = ?
          AND COALESCE(m.deleted, 0) = 0
        LIMIT 1
        """,
        (rowid,),
    ).fetchone()
    if row is None or row["read"] is None or row["flagged"] is None:
        return None
    mailbox = _mailbox_metadata(row["mailbox_url"])
    return {
        "handle": make_int_handle("mail:message", int(row["rowid"])),
        "read": bool(row["read"]),
        "flagged": bool(row["flagged"]),
        "mailbox_ref": mailbox["mailbox_ref"],
    }


def _triage_read_back_by_rowid(
    rowid: int,
    *,
    db_path: Path | None,
) -> dict[str, Any] | None:
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            _check_schema(connection)
            return _triage_read_back_from_connection(connection, rowid)
    except (StoreUnavailableError, sqlite3.Error):
        return None


def _triage_read_back(handle: str, *, db_path: Path | None) -> dict[str, Any] | None:
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, handle)
            if rowid is None:
                return None
            return _triage_read_back_from_connection(connection, rowid)
    except (StoreUnavailableError, sqlite3.Error):
        return None


def _triage_read_back_by_message_id(
    *,
    message_id: str,
    target_mailbox_url: str,
    db_path: Path | None,
    mail_root: Path,
) -> dict[str, Any] | None:
    """Read back one moved row by stored RFC Message-ID in the exact target mailbox."""

    normalized_message_id = _normalize_message_id_header(message_id)
    if not normalized_message_id:
        return None
    bracketed_message_id = f"<{normalized_message_id}>"

    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    m.ROWID AS rowid,
                    s.subject AS subject,
                    mb.url AS mailbox_url,
                    m.date_received AS date_received,
                    m.date_sent AS date_sent,
                    m.read AS read,
                    m.flagged AS flagged,
                    m.deleted AS deleted,
                    m.size AS size
                FROM messages m
                LEFT JOIN subjects s ON m.subject = s.ROWID
                JOIN mailboxes mb ON m.mailbox = mb.ROWID
                JOIN message_global_data mgd ON m.global_message_id = mgd.ROWID
                WHERE mb.url = ?
                  AND COALESCE(m.deleted, 0) = 0
                  AND (mgd.message_id_header = ? OR mgd.message_id_header = ?)
                ORDER BY m.ROWID ASC
                LIMIT 2
                """,
                (
                    target_mailbox_url,
                    normalized_message_id,
                    bracketed_message_id,
                ),
            ).fetchall()
    except (StoreUnavailableError, sqlite3.Error):
        return None

    if len(rows) != 1:
        return None
    metadata = _row_to_metadata(rows[0])
    return {
        "handle": metadata.get("handle"),
        "read": bool(metadata.get("read")),
        "flagged": bool(metadata.get("flagged")),
        "mailbox_ref": metadata.get("mailbox_ref"),
    }


def _cleanup_mailbox_kind(mailbox_name: str) -> str | None:
    if _special_mailbox_rank("trash", mailbox_name) is not None:
        return "trash"
    if _special_mailbox_rank("junk", mailbox_name) is not None:
        return "junk"
    return None


def _resolve_cleanup_message_target(
    connection,
    handle: str,
    *,
    mail_root: Path,
) -> dict[str, Any] | None:
    target = _resolve_triage_target(connection, handle, mail_root=mail_root)
    if target is None:
        return None
    mailbox_kind = _cleanup_mailbox_kind(str(target["mailbox_name"]))
    if mailbox_kind not in {"trash", "junk"}:
        raise MailCleanupRefused(
            _warning(
                "cleanup_target_not_trash_or_junk",
                "Mail permanent delete is limited to synthetic messages already in Trash or Junk.",
            )
        )
    if not str(target.get("subject") or "").startswith(SYNTHETIC_MAIL_TEST_PREFIX):
        raise MailCleanupRefused(
            _warning(
                "non_synthetic_subject",
                "Mail permanent delete requires a selected message subject starting with LAD-TEST-.",
            )
        )
    return {**target, "mailbox_kind": mailbox_kind}


def _cleanup_targets_in_mailbox(
    connection,
    mailbox_target: dict[str, str],
    *,
    mail_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    rows = connection.execute(
        """
        SELECT
            m.ROWID AS rowid,
            s.subject AS subject,
            m.read AS read,
            m.flagged AS flagged
        FROM messages m
        LEFT JOIN subjects s ON m.subject = s.ROWID
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE mb.url = ?
          AND COALESCE(m.deleted, 0) = 0
        ORDER BY m.ROWID ASC
        """,
        (mailbox_target["mailbox_url"],),
    ).fetchall()
    targets: list[dict[str, Any]] = []
    for row in rows:
        subject = _bounded_string(row["subject"], MAX_PREVIEW_SUBJECT_CHARS)
        if not subject.startswith(SYNTHETIC_MAIL_TEST_PREFIX):
            return [], _warning(
                "non_synthetic_mailbox_contents",
                "Mail empty Trash/Junk refuses when any target mailbox message subject does not start with LAD-TEST-.",
            )
        message_path = _find_message_file(mail_root, int(row["rowid"]))
        if message_path is None:
            return [], _warning(
                "message_identity_unavailable",
                "Mail cleanup target RFC identity was not available through the local message file.",
            )
        message_id = _message_id_from_emlx(message_path)
        if not message_id:
            return [], _warning(
                "message_identity_unavailable",
                "Mail cleanup target RFC identity was not available through the local message file.",
            )
        targets.append(
            {
                "handle": make_int_handle("mail:message", int(row["rowid"])),
                "rowid": int(row["rowid"]),
                "subject": subject,
                "message_id": message_id,
                "read": bool(row["read"]) if row["read"] is not None else False,
                "flagged": bool(row["flagged"]) if row["flagged"] is not None else False,
                "account_id": mailbox_target["account_id"],
                "account_ref": mailbox_target["account_ref"],
                "mailbox_name": mailbox_target["mailbox_name"],
                "mailbox_url": mailbox_target["mailbox_url"],
                "mailbox_ref": mailbox_target["mailbox_ref"],
                "mailbox_kind": mailbox_target["mailbox_kind"],
            }
        )
    return targets, None


def _cleanup_state_fingerprint(target: dict[str, Any]) -> str:
    payload = {
        "message_id": target["message_id"],
        "mailbox_ref": target["mailbox_ref"],
        "subject_sha256": hashlib.sha256(str(target["subject"]).encode("utf-8")).hexdigest(),
        "read": bool(target["read"]),
        "flagged": bool(target["flagged"]),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _cleanup_fingerprint_item(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_handle": target["handle"],
        "expected_state": _cleanup_state_fingerprint(target),
    }


def _cleanup_fingerprint_from_plan(proposed: dict[str, Any]) -> str:
    return str(proposed.get("expected_state") or "")


def _cleanup_fingerprints_from_plan(proposed: dict[str, Any]) -> list[dict[str, Any]]:
    value = proposed.get("message_handles")
    if not isinstance(value, list):
        return []
    states = proposed.get("messages")
    if isinstance(states, list):
        return [item for item in states if isinstance(item, dict)]
    return []


def _mail_cleanup_read_back(
    operation_name: str,
    targets: list[dict[str, Any]],
    *,
    verified_absent: bool,
) -> dict[str, Any]:
    return {
        "kind": "mail_cleanup",
        "operation": operation_name,
        "message_count": len(targets),
        "verified_absent": verified_absent,
        "permanently_deleted": verified_absent,
        "synthetic_subject_prefix_confirmed": True,
        "body_returned": False,
        "content_returned": False,
        "raw_identifier_returned": False,
    }


def _mail_cleanup_error_before_delete(error: MailAutomationError) -> bool:
    text = str(error)
    return any(
        code in text
        for code in (
            "cleanup_target_not_unique",
            "cleanup_target_set_changed",
            "cleanup_target_state_changed",
            "non_synthetic_subject",
        )
    )


def _cleanup_targets_absent(
    targets: list[dict[str, Any]],
    *,
    db_path: Path,
    mail_root: Path,
    require_mailbox_empty: bool = False,
    attempts: int = 1,
    retry_delay_seconds: float = 0.0,
) -> bool:
    bounded_attempts = max(1, attempts)
    for attempt in range(bounded_attempts):
        try:
            with connect_readonly(db_path) as connection:
                _check_schema(connection)
                all_absent = True
                if require_mailbox_empty and targets and not _cleanup_mailbox_empty(connection, targets[0]):
                    all_absent = False
                for target in targets:
                    if _message_present_in_cleanup_mailbox(
                        connection,
                        target=target,
                        message_id=str(target["message_id"]),
                        subject=str(target.get("subject") or ""),
                        mail_root=mail_root,
                    ):
                        all_absent = False
                        break
        except StoreUnavailableError:
            all_absent = False
        if all_absent:
            return True
        if attempt + 1 < bounded_attempts and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)
    return False


def _cleanup_mailbox_empty(connection, target: dict[str, Any]) -> bool:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM messages m
            LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
            WHERE COALESCE(m.deleted, 0) = 0
              AND mb.url = ?
            LIMIT 1
            """,
            (target["mailbox_url"],),
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is None


def _message_present_in_cleanup_mailbox(
    connection,
    *,
    target: dict[str, Any],
    message_id: str,
    subject: str,
    mail_root: Path,
) -> bool:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM messages m
            LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
            WHERE m.ROWID = ?
              AND COALESCE(m.deleted, 0) = 0
              AND mb.url = ?
            LIMIT 1
            """,
            (int(target["rowid"]), target["mailbox_url"]),
        ).fetchone()
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        row = None
    if row is not None:
        return True
    normalized_message_id = _normalize_message_id_header(message_id)
    if normalized_message_id and _message_global_data_header_present(
        connection,
        normalized_message_id,
        mailbox_url=str(target["mailbox_url"]),
    ):
        return True
    rows = connection.execute(
        """
        SELECT m.ROWID AS rowid
        FROM messages m
        LEFT JOIN subjects s ON m.subject = s.ROWID
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE COALESCE(m.deleted, 0) = 0
          AND mb.url = ?
          AND s.subject = ?
        """,
        (target["mailbox_url"], subject),
    ).fetchall()
    for row in rows:
        message_path = _find_message_file(mail_root, int(row["rowid"]))
        if message_path is None:
            continue
        if _message_id_from_emlx(message_path) == normalized_message_id:
            return True
    return False


def _message_global_data_header_present(connection, message_id: str, *, mailbox_url: str = "") -> bool:
    bracketed = f"<{message_id}>"
    mailbox_filter = "AND mb.url = ?" if mailbox_url else ""
    parameters: tuple[str, ...] = (message_id, bracketed, mailbox_url) if mailbox_url else (message_id, bracketed)
    try:
        row = connection.execute(
            f"""
            SELECT 1
            FROM messages m
            LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
            LEFT JOIN message_global_data mgd ON m.global_message_id = mgd.ROWID
            WHERE COALESCE(m.deleted, 0) = 0
              AND (mgd.message_id_header = ? OR mgd.message_id_header = ?)
              {mailbox_filter}
            LIMIT 1
            """,
            parameters,
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _mail_wait_for_background_activity_script() -> str:
    return "\n".join(
        [
            'tell application "Mail"',
            f"    repeat with attemptIndex from 1 to {MAIL_CLEANUP_BACKGROUND_IDLE_ATTEMPTS}",
            "        try",
            '            if background activity count is 0 then return "background_idle:true"',
            "        end try",
            f"        delay {MAIL_CLEANUP_BACKGROUND_IDLE_DELAY_SECONDS}",
            "    end repeat",
            '    return "background_idle:false"',
            "end tell",
        ]
    ) + "\n"


def _mail_permanent_delete_message_script(
    *,
    account_id: str,
    mailbox_name: str,
    target: dict[str, Any],
) -> str:
    message_id = str(target["message_id"])
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set cleanupBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
            f"    set cleanupMatches to (messages of cleanupBox whose message id is {_applescript_string(message_id)})",
            '    if (count of cleanupMatches) is not 1 then error "cleanup_target_not_unique"',
            "    set cleanupMessage to first item of cleanupMatches",
            f"    if subject of cleanupMessage does not start with {_applescript_string(SYNTHETIC_MAIL_TEST_PREFIX)} then error \"non_synthetic_subject\"",
            *_mail_cleanup_target_state_guard_lines("cleanupMessage", target, indent="    "),
            "    delete cleanupMessage",
            "    delay 0.2",
            f"    set remainingMatches to (messages of cleanupBox whose message id is {_applescript_string(message_id)})",
            '    return "deleted_count:1" & linefeed & "verified_absent:" & (((count of remainingMatches) is 0) as text)',
            "end tell",
        ]
    ) + "\n"


def _mail_empty_special_mailbox_script(*, account_id: str, mailbox_name: str, targets: list[dict[str, Any]]) -> str:
    message_ids = [str(target["message_id"]) for target in targets]
    message_id_list = "{" + ", ".join(_applescript_string(message_id) for message_id in message_ids) + "}"
    subject_list = "{" + ", ".join(_applescript_string(str(target.get("subject") or "")) for target in targets) + "}"
    read_list = "{" + ", ".join("true" if bool(target.get("read")) else "false" for target in targets) + "}"
    flagged_list = "{" + ", ".join("true" if bool(target.get("flagged")) else "false" for target in targets) + "}"
    return "\n".join(
        [
            'tell application "Mail"',
            f"    set cleanupBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
            "    set cleanupMessages to messages of cleanupBox",
            "    set cleanupCount to count of cleanupMessages",
            f"    if cleanupCount is not {len(message_ids)} then error \"cleanup_target_set_changed\"",
            f"    set expectedMessageIds to {message_id_list}",
            f"    set expectedSubjects to {subject_list}",
            f"    set expectedReadStatuses to {read_list}",
            f"    set expectedFlaggedStatuses to {flagged_list}",
            "    set cleanupTargets to {}",
            "    set cleanupIndex to 1",
            "    repeat with expectedMessageId in expectedMessageIds",
            "        set cleanupMatches to (messages of cleanupBox whose message id is (expectedMessageId as text))",
            "        if (count of cleanupMatches) is not 1 then error \"cleanup_target_set_changed\"",
            "        set cleanupMessage to first item of cleanupMatches",
            f"        if subject of cleanupMessage does not start with {_applescript_string(SYNTHETIC_MAIL_TEST_PREFIX)} then error \"non_synthetic_subject\"",
            "        if subject of cleanupMessage is not (item cleanupIndex of expectedSubjects) then error \"cleanup_target_state_changed\"",
            "        if read status of cleanupMessage is not (item cleanupIndex of expectedReadStatuses) then error \"cleanup_target_state_changed\"",
            "        if flagged status of cleanupMessage is not (item cleanupIndex of expectedFlaggedStatuses) then error \"cleanup_target_state_changed\"",
            "        set end of cleanupTargets to cleanupMessage",
            "        set cleanupIndex to cleanupIndex + 1",
            "    end repeat",
            "    repeat with cleanupMessage in cleanupTargets",
            "        delete cleanupMessage",
            "    end repeat",
            "    delay 0.2",
            '    return "deleted_count:" & (cleanupCount as text) & linefeed & "verified_absent:" & (((count of messages of cleanupBox) is 0) as text)',
            "end tell",
        ]
    ) + "\n"


def _mail_cleanup_target_state_guard_lines(
    message_reference: str,
    target: dict[str, Any],
    *,
    indent: str,
) -> list[str]:
    expected_subject = _applescript_string(str(target.get("subject") or ""))
    expected_read = "true" if bool(target.get("read")) else "false"
    expected_flagged = "true" if bool(target.get("flagged")) else "false"
    return [
        f"{indent}if subject of {message_reference} is not {expected_subject} then error \"cleanup_target_state_changed\"",
        f"{indent}if read status of {message_reference} is not {expected_read} then error \"cleanup_target_state_changed\"",
        f"{indent}if flagged status of {message_reference} is not {expected_flagged} then error \"cleanup_target_state_changed\"",
    ]


def _triage_message_handle_inputs(
    message_handle: str = "",
    message_handles: list[str] | None = None,
) -> list[str]:
    handles: list[str] = []
    single = str(message_handle or "").strip()
    if single:
        handles.append(single)
    for value in message_handles or []:
        handle = str(value or "").strip()
        if handle:
            handles.append(handle)
    return handles


def _normalize_bulk_triage_handles(handles: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    normalized = [str(handle or "").strip() for handle in handles if str(handle or "").strip()]
    if len(normalized) < 2:
        warnings.append(
            _warning(
                "missing_message_handles",
                "Mail bulk triage requires at least two exact mail:message handles.",
            )
        )
    if len(normalized) > MAX_BULK_TRIAGE_MESSAGES:
        warnings.append(
            _warning(
                "too_many_message_handles",
                f"Mail bulk triage is capped at {MAX_BULK_TRIAGE_MESSAGES} exact messages.",
            )
        )
    seen: set[str] = set()
    for handle in normalized:
        if handle in seen:
            warnings.append(
                _warning(
                    "duplicate_message_handle",
                    "Mail bulk triage requires each exact message handle at most once.",
                )
            )
            break
        seen.add(handle)
        if not is_int_handle(handle, "mail:message"):
            warnings.append(
                _warning("invalid_message_handle", "Expected mail:message opaque handles from search output.")
            )
            break
    return normalized, warnings


def _triage_move_target(
    connection,
    operation: str,
    target: dict[str, Any],
    target_mailbox_handle: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    if operation == "archive_message":
        return _resolve_archive_mailbox(connection, target)
    if operation == "trash_message":
        return _resolve_trash_mailbox(connection, target)
    return _resolve_exact_move_mailbox(connection, target, target_mailbox_handle)


def _bulk_triage_preview_item(
    operation: str,
    *,
    message_handle: str,
    target: dict[str, Any],
    move_target: dict[str, str] | None = None,
    target_mailbox_handle: str = "",
) -> dict[str, Any]:
    target_read = operation == "mark_read"
    target_flagged = operation == "flag_message"
    item: dict[str, Any] = {
        "message_handle": message_handle,
        "mailbox_ref": target["mailbox_ref"],
        "current_read": target["read"],
        "current_flagged": target["flagged"],
        "expected_state": _triage_state_fingerprint(target),
    }
    if operation in READ_STATUS_OPERATIONS:
        item["target_read"] = target_read
        item["already_satisfied"] = target["read"] == target_read
    elif operation in MOVE_OPERATIONS:
        assert move_target is not None
        item["target_mailbox_kind"] = move_target["mailbox_kind"]
        item["target_mailbox_ref"] = move_target["mailbox_ref"]
        if operation == "move_message":
            item["target_mailbox_handle"] = target_mailbox_handle
            item["target_account_relation"] = move_target["account_relation"]
            item["source_account_ref"] = target["account_ref"]
            item["target_account_ref"] = move_target["account_ref"]
        item["already_satisfied"] = target["mailbox_ref"] == move_target["mailbox_ref"]
    else:
        item["target_flagged"] = target_flagged
        item["already_satisfied"] = target["flagged"] == target_flagged
    return item


def _bulk_triage_fingerprint_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "message_handle": item["message_handle"],
        "expected_state": item["expected_state"],
    }
    if "target_read" in item:
        payload["target_read"] = item["target_read"]
    if "target_flagged" in item:
        payload["target_flagged"] = item["target_flagged"]
    if "target_mailbox_ref" in item:
        payload["target_mailbox_ref"] = item["target_mailbox_ref"]
        payload["target_mailbox_kind"] = item["target_mailbox_kind"]
    if "target_mailbox_handle" in item:
        payload["target_mailbox_handle"] = item["target_mailbox_handle"]
        payload["target_account_relation"] = item["target_account_relation"]
    return payload


def plan_mail_bulk_triage(
    operation: str,
    *,
    message_handles: list[str],
    target_mailbox_handle: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    normalized_handles, warnings = _normalize_bulk_triage_handles(message_handles)
    if normalized_operation not in TRIAGE_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation mark_read, mark_unread, flag_message, unflag_message, archive_message, trash_message, or move_message.",
            )
        )
    normalized_target_mailbox_handle = target_mailbox_handle.strip()
    if normalized_operation == "move_message" and not normalized_target_mailbox_handle:
        warnings.append(
            _warning(
                "missing_target_mailbox_handle",
                "Mail move_message requires a target mail:mailbox:v1 handle from mailbox search output.",
            )
        )
    if normalized_operation != "move_message" and normalized_target_mailbox_handle:
        warnings.append(
            _warning(
                "unexpected_target_mailbox_handle",
                "Only Mail move_message accepts a target mailbox handle.",
            )
        )
    if normalized_target_mailbox_handle and not is_opaque_handle(normalized_target_mailbox_handle, MAILBOX_HANDLE_PREFIX):
        warnings.append(
            _warning(
                "invalid_target_mailbox_handle",
                "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
            )
        )
    if warnings:
        return _plan_error(warnings)

    try:
        resolved_db_path = _resolve_db_path(db_path)
        resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
        items: list[dict[str, Any]] = []
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            targets = _resolve_bulk_triage_targets(
                connection,
                normalized_handles,
                mail_root=resolved_mail_root,
            )
            if targets is None:
                return _plan_error(
                    [_warning("message_not_found", "Mail message handle did not resolve to a live message.")]
                )
            for handle in normalized_handles:
                target = targets[handle]
                move_target: dict[str, str] | None = None
                if normalized_operation in MOVE_OPERATIONS:
                    move_target, move_warning = _triage_move_target(
                        connection,
                        normalized_operation,
                        target,
                        normalized_target_mailbox_handle,
                    )
                    if move_warning is not None:
                        return _plan_error([move_warning])
                items.append(
                    _bulk_triage_preview_item(
                        normalized_operation,
                        message_handle=handle,
                        target=target,
                        move_target=move_target,
                        target_mailbox_handle=normalized_target_mailbox_handle,
                    )
                )
    except StoreUnavailableError:
        return _plan_error([_mail_store_unavailable_warning()])
    except MailTriageIdentityUnavailable as error:
        return _plan_error([_message_identity_unavailable_plan_warning(error)])

    proposed = {
        "kind": "mail_bulk_triage",
        "operation": normalized_operation,
        "message_count": len(items),
        "message_handles": normalized_handles,
        "messages": items,
        "already_satisfied_count": sum(1 for item in items if item["already_satisfied"]),
        "partial_apply_possible": True,
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "bulk": True,
        "messages": [_bulk_triage_fingerprint_item(item) for item in items],
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
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
        "result_count": len(items),
        "warnings": [],
    }


def _bulk_triage_read_back(
    operation: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "mail_bulk_triage",
        "operation": operation,
        "message_count": len(results),
        "applied_count": sum(1 for item in results if item.get("mutation_applied") is True),
        "already_satisfied_count": sum(1 for item in results if item.get("status") == "already_satisfied"),
        "failed_count": sum(1 for item in results if item.get("status") == "error"),
        "not_attempted_count": sum(1 for item in results if item.get("status") == "not_attempted"),
        "results": results,
        "body_returned": False,
        "raw_identifier_returned": False,
    }


def _bulk_triage_apply_result(
    *,
    status: str,
    preview: dict[str, Any],
    fingerprint: str,
    mutation_applied: bool,
    results: list[dict[str, Any]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "mail",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": _bulk_triage_read_back(str(preview["operation"]), results),
        "result_count": len(results),
        "warnings": warnings,
    }


def _bulk_triage_unattempted_results(
    items: list[dict[str, Any]],
    *,
    completed_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "message_handle": str(item["message_handle"]),
            "status": "not_attempted",
            "mutation_applied": False,
            "warning_code": "not_attempted_after_prior_failure",
        }
        for item in items[completed_count:]
    ]


def _triage_script_for_target(
    operation: str,
    target: dict[str, Any],
    move_target: dict[str, str] | None,
    item: dict[str, Any],
) -> str:
    if operation in READ_STATUS_OPERATIONS:
        return _mail_set_read_status_script(
            account_id=target["account_id"],
            mailbox_name=target["mailbox_name"],
            message_id=target["message_id"],
            target_read=bool(item["target_read"]),
        )
    if operation in MOVE_OPERATIONS:
        assert move_target is not None
        if operation == "archive_message":
            return _mail_archive_message_script(
                account_id=target["account_id"],
                source_mailbox_name=target["mailbox_name"],
                target_mailbox_name=move_target["mailbox_name"],
                message_id=target["message_id"],
            )
        if operation == "trash_message":
            return _mail_trash_message_script(
                account_id=target["account_id"],
                source_mailbox_name=target["mailbox_name"],
                target_mailbox_name=move_target["mailbox_name"],
                message_id=target["message_id"],
            )
        return _mail_move_message_script(
            source_account_id=target["account_id"],
            target_account_id=move_target["account_id"],
            source_mailbox_name=target["mailbox_name"],
            target_mailbox_name=move_target["mailbox_name"],
            message_id=target["message_id"],
        )
    return _mail_set_flagged_status_script(
        account_id=target["account_id"],
        mailbox_name=target["mailbox_name"],
        message_id=target["message_id"],
        target_flagged=bool(item["target_flagged"]),
    )


def _bulk_triage_confirmation(
    operation: str,
    *,
    item: dict[str, Any],
    target: dict[str, Any],
    move_target: dict[str, str] | None,
    db_path: Path | None,
    mail_root: Path,
) -> dict[str, Any] | None:
    for attempt in range(MAIL_TRIAGE_READ_BACK_ATTEMPTS):
        read_back = _triage_read_back_by_rowid(int(target["rowid"]), db_path=db_path)
        if operation in MOVE_OPERATIONS and (
            read_back is None or read_back.get("mailbox_ref") != item.get("target_mailbox_ref")
        ):
            assert move_target is not None
            read_back = _triage_read_back_by_message_id(
                message_id=target["message_id"],
                target_mailbox_url=move_target["mailbox_url"],
                db_path=db_path,
                mail_root=mail_root,
            )
        if operation in READ_STATUS_OPERATIONS:
            confirmed = read_back is not None and read_back.get("read") == item.get("target_read")
        elif operation in MOVE_OPERATIONS:
            confirmed = read_back is not None and read_back.get("mailbox_ref") == item.get("target_mailbox_ref")
        else:
            confirmed = read_back is not None and read_back.get("flagged") == item.get("target_flagged")
        if confirmed:
            return read_back
        if attempt + 1 < MAIL_TRIAGE_READ_BACK_ATTEMPTS:
            time.sleep(MAIL_TRIAGE_READ_BACK_DELAY_SECONDS)
    return None


def apply_mail_bulk_triage(
    operation: str,
    *,
    message_handles: list[str],
    target_mailbox_handle: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_bulk_triage(
        operation,
        message_handles=message_handles,
        target_mailbox_handle=target_mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Mail apply approval token did not match the plan.")],
            plan=plan,
        )

    normalized_operation = str(preview["operation"])
    proposed = preview["proposed"]
    items = list(proposed["messages"])
    resolved: dict[str, tuple[dict[str, Any], dict[str, str] | None]] = {}
    try:
        resolved_db_path = _resolve_db_path(db_path)
        resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            targets = _resolve_bulk_triage_targets(
                connection,
                [str(item["message_handle"]) for item in items],
                mail_root=resolved_mail_root,
            )
            if targets is None:
                return _apply_error(
                    [_warning("message_not_found", "Mail message handle no longer resolves to a live message.")],
                    plan=plan,
                )
            for item in items:
                handle = str(item["message_handle"])
                target = targets[handle]
                if _triage_state_fingerprint(target) != item["expected_state"]:
                    return _apply_error(
                        [_warning("stale_message_state", "Mail message changed since the plan; re-plan before applying.")],
                        plan=plan,
                    )
                move_target: dict[str, str] | None = None
                if normalized_operation in MOVE_OPERATIONS:
                    move_target, move_warning = _triage_move_target(
                        connection,
                        normalized_operation,
                        target,
                        str(item.get("target_mailbox_handle") or target_mailbox_handle),
                    )
                    if move_warning is not None:
                        return _apply_error([move_warning], plan=plan)
                    assert move_target is not None
                    if move_target["mailbox_ref"] != item.get("target_mailbox_ref"):
                        return _apply_error(
                            [
                                _warning(
                                    "stale_mailbox_target",
                                    "Mail target mailbox changed since the plan; re-plan before applying.",
                                )
                            ],
                            plan=plan,
                        )
                resolved[handle] = (target, move_target)
    except StoreUnavailableError:
        return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded")
    except MailTriageIdentityUnavailable:
        return _apply_error(
            [
                _warning(
                    "message_identity_unavailable",
                    "Mail message RFC identity was no longer available through the local message file.",
                )
            ],
            plan=plan,
        )

    runner = script_runner or _run_osascript
    results: list[dict[str, Any]] = []
    mutation_applied = False
    for item in items:
        handle = str(item["message_handle"])
        target, move_target = resolved[handle]
        if item.get("already_satisfied"):
            read_back = _bulk_triage_confirmation(
                normalized_operation,
                item=item,
                target=target,
                move_target=move_target,
                db_path=db_path,
                mail_root=resolved_mail_root,
            ) or _triage_read_back(handle, db_path=db_path)
            results.append(
                {
                    "message_handle": handle,
                    "status": "already_satisfied",
                    "mutation_applied": False,
                    "read_back": read_back,
                }
            )
            continue
        script = _triage_script_for_target(normalized_operation, target, move_target, item)
        try:
            runner(script, MAIL_APPLESCRIPT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "message_handle": handle,
                    "status": "error",
                    "mutation_applied": False,
                    "warning_code": "automation_timeout",
                }
            )
            results.extend(_bulk_triage_unattempted_results(items, completed_count=len(results)))
            return _bulk_triage_apply_result(
                status="partial" if mutation_applied else "degraded",
                preview=preview,
                fingerprint=fingerprint,
                mutation_applied=mutation_applied,
                results=results,
                warnings=[_warning("automation_timeout", "Mail bulk triage timed out through local automation.")],
            )
        except (OSError, MailAutomationError):
            results.append(
                {
                    "message_handle": handle,
                    "status": "error",
                    "mutation_applied": False,
                    "warning_code": "write_error",
                }
            )
            results.extend(_bulk_triage_unattempted_results(items, completed_count=len(results)))
            return _bulk_triage_apply_result(
                status="partial" if mutation_applied else "error",
                preview=preview,
                fingerprint=fingerprint,
                mutation_applied=mutation_applied,
                results=results,
                warnings=[_warning("write_error", "Mail bulk triage could not update every selected message safely.")],
            )
        mutation_applied = True
        read_back = _bulk_triage_confirmation(
            normalized_operation,
            item=item,
            target=target,
            move_target=move_target,
            db_path=db_path,
            mail_root=resolved_mail_root,
        )
        if read_back is None:
            results.append(
                {
                    "message_handle": handle,
                    "status": "error",
                    "mutation_applied": True,
                    "warning_code": "read_back_unavailable",
                }
            )
            results.extend(_bulk_triage_unattempted_results(items, completed_count=len(results)))
            return _bulk_triage_apply_result(
                status="partial",
                preview=preview,
                fingerprint=fingerprint,
                mutation_applied=True,
                results=results,
                warnings=[
                    _warning(
                        "read_back_unavailable",
                        "Mail bulk triage applied to at least one message but read-back did not confirm every new state.",
                    )
                ],
            )
        results.append(
            {
                "message_handle": handle,
                "status": "ok",
                "mutation_applied": True,
                "read_back": read_back,
            }
        )

    warnings = []
    if not mutation_applied:
        warnings.append(_warning("already_applied", "Mail messages were already in the requested state."))
    return _bulk_triage_apply_result(
        status="ok",
        preview=preview,
        fingerprint=fingerprint,
        mutation_applied=mutation_applied,
        results=results,
        warnings=warnings,
    )


def plan_mail_search_triage(
    operation: str,
    query: str,
    *,
    search_source: str = "fts",
    scopes: list[str] | None = None,
    after: str | int | float | None = None,
    before: str | int | float | None = None,
    cursor: str = "",
    limit: int = MAX_BULK_TRIAGE_MESSAGES,
    target_mailbox_handle: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
    index_path: Path | None = None,
) -> dict[str, Any]:
    normalized_source = search_source.strip().replace("-", "_").casefold() or "fts"
    bounded_limit = max(1, min(limit, MAX_BULK_TRIAGE_MESSAGES))
    if normalized_source != "fts":
        return _plan_error(
            [
                _warning(
                    "unsupported_search_source",
                    "Mail query-result triage currently supports only durable FTS search results.",
                )
            ]
        )
    search_result = search_mail_fts(
        query,
        scopes=scopes,
        after=after,
        before=before,
        cursor=cursor,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
        limit=bounded_limit,
        max_snippet_chars=DEFAULT_MAIL_SNIPPET_CHARS,
    )
    if search_result.get("status") != "ok":
        return _plan_error(_safe_warnings(search_result), privacy=search_result.get("privacy"))
    handles = [
        str(result.get("handle") or "")
        for result in search_result.get("results", [])
        if is_int_handle(str(result.get("handle") or ""), "mail:message")
    ]
    if not handles:
        return _plan_error(
            [_warning("no_query_results", "Mail query-result triage found no exact message handles to plan.")]
        )
    if len(handles) == 1:
        plan = plan_mail_triage(
            operation,
            message_handle=handles[0],
            target_mailbox_handle=target_mailbox_handle,
            db_path=db_path,
            mail_root=mail_root,
        )
    else:
        plan = plan_mail_bulk_triage(
            operation,
            message_handles=handles,
            target_mailbox_handle=target_mailbox_handle,
            db_path=db_path,
            mail_root=mail_root,
        )
    if plan.get("status") != "ok":
        return plan
    plan = copy.deepcopy(plan)
    plan["preview"]["query_result_selection"] = {
        "search_source": normalized_source,
        "query_ref": f"query:{hashlib.sha256(query.strip().encode('utf-8')).hexdigest()[:12]}",
        "scopes": list(scopes or []),
        "after": str(after) if after is not None else None,
        "before": str(before) if before is not None else None,
        "cursor": cursor,
        "selected_result_count": len(handles),
        "search_result_count": int(search_result.get("result_count") or 0),
        "next_cursor": search_result.get("next_cursor"),
        "body_returned": False,
        "content_returned": False,
        "raw_query_returned": False,
    }
    plan["result_count"] = len(handles)
    return plan


def plan_mail_triage(
    operation: str,
    *,
    message_handle: str = "",
    target_mailbox_handle: str = "",
    db_path: Path | None = None,
    mail_root: Path | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in TRIAGE_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation mark_read, mark_unread, flag_message, unflag_message, archive_message, trash_message, or move_message.",
            )
        )
    if not is_int_handle(message_handle, "mail:message"):
        warnings.append(
            _warning("invalid_message_handle", "Expected mail:message opaque handle from search output.")
        )
    normalized_target_mailbox_handle = target_mailbox_handle.strip()
    if normalized_operation == "move_message" and not normalized_target_mailbox_handle:
        warnings.append(
            _warning(
                "missing_target_mailbox_handle",
                "Mail move_message requires a target mail:mailbox:v1 handle from mailbox search output.",
            )
        )
    if normalized_operation != "move_message" and normalized_target_mailbox_handle:
        warnings.append(
            _warning(
                "unexpected_target_mailbox_handle",
                "Only Mail move_message accepts a target mailbox handle.",
            )
        )
    if normalized_target_mailbox_handle and not is_opaque_handle(normalized_target_mailbox_handle, MAILBOX_HANDLE_PREFIX):
        warnings.append(
            _warning(
                "invalid_target_mailbox_handle",
                "Expected mail:mailbox:v1 opaque handle from Mail mailbox search output.",
            )
        )
    if warnings:
        return _plan_error(warnings)

    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=mail_root or _mail_content_root(resolved_db_path),
            )
    except StoreUnavailableError:
        return _plan_error([_mail_store_unavailable_warning()])
    except MailTriageIdentityUnavailable as error:
        return _plan_error([_message_identity_unavailable_plan_warning(error)])
    if target is None:
        return _plan_error(
            [_warning("message_not_found", "Mail message handle did not resolve to a live message.")]
        )

    move_target: dict[str, str] | None = None
    if normalized_operation in MOVE_OPERATIONS:
        try:
            with connect_readonly(_resolve_db_path(db_path)) as connection:
                _check_schema(connection)
                if normalized_operation == "archive_message":
                    move_target, move_warning = _resolve_archive_mailbox(connection, target)
                elif normalized_operation == "trash_message":
                    move_target, move_warning = _resolve_trash_mailbox(connection, target)
                else:
                    move_target, move_warning = _resolve_exact_move_mailbox(
                        connection,
                        target,
                        normalized_target_mailbox_handle,
                    )
        except StoreUnavailableError:
            return _plan_error([_mail_store_unavailable_warning()])
        if move_warning is not None:
            return _plan_error([move_warning])

    is_read_operation = normalized_operation in READ_STATUS_OPERATIONS
    is_move_operation = normalized_operation in MOVE_OPERATIONS
    target_read = normalized_operation == "mark_read"
    target_flagged = normalized_operation == "flag_message"
    expected_state = _triage_state_fingerprint(target)
    proposed = {
        "kind": "mail_triage",
        "operation": normalized_operation,
        "message_handle": message_handle,
        "mailbox_ref": target["mailbox_ref"],
        "current_read": target["read"],
        "current_flagged": target["flagged"],
    }
    if is_read_operation:
        proposed["target_read"] = target_read
        proposed["already_satisfied"] = target["read"] == target_read
    elif is_move_operation:
        assert move_target is not None
        proposed["target_mailbox_kind"] = move_target["mailbox_kind"]
        if normalized_operation == "move_message":
            proposed["target_mailbox_handle"] = normalized_target_mailbox_handle
            proposed["target_account_relation"] = move_target["account_relation"]
            proposed["source_account_ref"] = target["account_ref"]
            proposed["target_account_ref"] = move_target["account_ref"]
        proposed["target_mailbox_ref"] = move_target["mailbox_ref"]
        proposed["already_satisfied"] = target["mailbox_ref"] == move_target["mailbox_ref"]
    else:
        proposed["target_flagged"] = target_flagged
        proposed["already_satisfied"] = target["flagged"] == target_flagged
    fingerprint_payload = {
        "operation": normalized_operation,
        "message_handle": message_handle,
        "expected_state": expected_state,
    }
    if is_read_operation:
        fingerprint_payload["target_read"] = target_read
    elif is_move_operation:
        assert move_target is not None
        fingerprint_payload["target_mailbox_ref"] = move_target["mailbox_ref"]
        fingerprint_payload["target_mailbox_kind"] = move_target["mailbox_kind"]
        if normalized_operation == "move_message":
            fingerprint_payload["target_mailbox_handle"] = normalized_target_mailbox_handle
            fingerprint_payload["target_account_relation"] = move_target["account_relation"]
    else:
        fingerprint_payload["target_flagged"] = target_flagged
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "proposed": proposed,
            "expected_state": expected_state,
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


def apply_mail_triage(
    operation: str,
    *,
    message_handle: str = "",
    target_mailbox_handle: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_triage(
        operation,
        message_handle=message_handle,
        target_mailbox_handle=target_mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Mail apply approval token did not match the plan.")],
            plan=plan,
        )

    proposed = preview["proposed"]
    is_read_operation = str(proposed["operation"]) in READ_STATUS_OPERATIONS
    is_move_operation = str(proposed["operation"]) in MOVE_OPERATIONS
    target_read = bool(proposed.get("target_read"))
    target_flagged = bool(proposed.get("target_flagged"))
    if proposed.get("already_satisfied"):
        read_back = _triage_read_back(message_handle, db_path=db_path)
        if is_read_operation:
            fallback = {"handle": message_handle, "read": target_read}
        elif is_move_operation:
            fallback = {
                "handle": message_handle,
                "mailbox_ref": proposed.get("target_mailbox_ref"),
            }
        else:
            fallback = {
                "handle": message_handle,
                "flagged": target_flagged,
            }
        return _apply_success(
            read_back or fallback,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=fingerprint,
            mutation_applied=False,
            warnings=[_warning("already_applied", "Mail message already in the requested state.")],
        )

    # Re-resolve at apply time and refuse if the message drifted since the plan.
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=mail_root or _mail_content_root(resolved_db_path),
            )
    except StoreUnavailableError:
        return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded")
    except MailTriageIdentityUnavailable:
        return _apply_error(
            [
                _warning(
                    "message_identity_unavailable",
                    "Mail message RFC identity was no longer available through the local message file.",
                )
            ],
            plan=plan,
        )
    if target is None:
        return _apply_error(
            [_warning("message_not_found", "Mail message handle no longer resolves to a live message.")],
            plan=plan,
        )
    if _triage_state_fingerprint(target) != preview["expected_state"]:
        return _apply_error(
            [_warning("stale_message_state", "Mail message changed since the plan; re-plan before applying.")],
            plan=plan,
        )
    move_target: dict[str, str] | None = None
    if is_move_operation:
        try:
            with connect_readonly(resolved_db_path) as connection:
                _check_schema(connection)
                if str(proposed["operation"]) == "archive_message":
                    move_target, move_warning = _resolve_archive_mailbox(connection, target)
                elif str(proposed["operation"]) == "trash_message":
                    move_target, move_warning = _resolve_trash_mailbox(connection, target)
                else:
                    move_target, move_warning = _resolve_exact_move_mailbox(
                        connection,
                        target,
                        str(proposed.get("target_mailbox_handle", "")),
                    )
        except StoreUnavailableError:
            return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded")
        if move_warning is not None:
            return _apply_error([move_warning], plan=plan)
        if move_target["mailbox_ref"] != proposed.get("target_mailbox_ref"):
            return _apply_error(
                [_warning("stale_mailbox_target", "Mail target mailbox changed since the plan; re-plan before applying.")],
                plan=plan,
            )

    runner = script_runner or _run_osascript
    try:
        if is_read_operation:
            script = _mail_set_read_status_script(
                account_id=target["account_id"],
                mailbox_name=target["mailbox_name"],
                message_id=target["message_id"],
                target_read=target_read,
            )
        elif is_move_operation:
            assert move_target is not None
            if str(proposed["operation"]) == "archive_message":
                script = _mail_archive_message_script(
                    account_id=target["account_id"],
                    source_mailbox_name=target["mailbox_name"],
                    target_mailbox_name=move_target["mailbox_name"],
                    message_id=target["message_id"],
                )
            elif str(proposed["operation"]) == "trash_message":
                script = _mail_trash_message_script(
                    account_id=target["account_id"],
                    source_mailbox_name=target["mailbox_name"],
                    target_mailbox_name=move_target["mailbox_name"],
                    message_id=target["message_id"],
                )
            else:
                script = _mail_move_message_script(
                    source_account_id=target["account_id"],
                    target_account_id=move_target["account_id"],
                    source_mailbox_name=target["mailbox_name"],
                    target_mailbox_name=move_target["mailbox_name"],
                    message_id=target["message_id"],
                )
        else:
            script = _mail_set_flagged_status_script(
                account_id=target["account_id"],
                mailbox_name=target["mailbox_name"],
                message_id=target["message_id"],
                target_flagged=target_flagged,
            )
        runner(script, MAIL_APPLESCRIPT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail triage timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail message state could not be updated safely.")],
            plan=plan,
        )

    read_back = _triage_read_back(message_handle, db_path=db_path)
    if (
        is_move_operation
        and (read_back is None or read_back.get("mailbox_ref") != proposed.get("target_mailbox_ref"))
    ):
        assert move_target is not None
        read_back = _triage_read_back_by_message_id(
            message_id=target["message_id"],
            target_mailbox_url=move_target["mailbox_url"],
            db_path=db_path,
            mail_root=mail_root or _mail_content_root(resolved_db_path),
        )
    if is_read_operation:
        confirmed = read_back is not None and read_back.get("read") == target_read
    elif is_move_operation:
        confirmed = read_back is not None and read_back.get("mailbox_ref") == proposed.get("target_mailbox_ref")
    else:
        confirmed = read_back is not None and read_back.get("flagged") == target_flagged
    if not confirmed:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail triage applied but read-back did not confirm the new state.")],
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


def plan_mail_reply(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
    include_private: bool = False,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in REPLY_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation reply_message or reply_all_message."))
    if not is_int_handle(message_handle, "mail:message"):
        warnings.append(_warning("invalid_message_handle", "Expected mail:message opaque handle from search output."))
    if any(to or []) or any(cc or []) or any(bcc or []):
        warnings.append(
            _warning(
                "unexpected_recipient_inputs",
                "Mail reply derives recipients from the exact source message; direct recipients are not accepted.",
            )
        )
    if subject.strip():
        warnings.append(
            _warning(
                "unexpected_subject",
                "Mail reply derives its subject from the exact source message; direct subject input is not accepted.",
            )
        )
    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            warnings.append(template_warning)
        if template is not None and body_text.strip():
            warnings.append(
                _warning(
                    "unexpected_body_text_with_template",
                    "Mail template planning uses the selected template body; direct body_text is not accepted.",
                )
            )
    reply_body_source = str(template["body_text"]) if template is not None else body_text
    normalized_body, body_warning = _normalize_reply_body(reply_body_source)
    if body_warning is not None:
        warnings.append(body_warning)
    attachment_infos, attachment_warnings = _resolve_draft_attachments(attachment_paths or [])
    warnings.extend(attachment_warnings)
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        _, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            warnings.append(sender_warning)
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        _, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            warnings.append(signature_warning)
    if warnings:
        return _plan_error(warnings)

    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=mail_root or _mail_content_root(resolved_db_path),
            )
    except StoreUnavailableError:
        return _plan_error([_mail_store_unavailable_warning()])
    except MailTriageIdentityUnavailable as error:
        return _plan_error([_message_identity_unavailable_plan_warning(error)])
    if target is None:
        return _plan_error([_warning("message_not_found", "Mail message handle did not resolve to a live message.")])

    source_state = _triage_state_fingerprint(target)
    reply_subject = _reply_subject(target["subject"])
    reply_all = normalized_operation == "reply_all_message"
    reply_mode = "reply_all" if reply_all else "sender_only"
    body_preview, body_preview_truncated = _bounded_text(normalized_body, MAX_DRAFT_BODY_PREVIEW_CHARS)
    attachment_preview = _draft_attachment_preview(
        attachment_infos,
        send_permitted=True,
    )
    if sender_metadata is None:
        sender_selection: dict[str, Any] = {
            "mode": "mail_app_default",
            "sender_selected": False,
        }
    else:
        sender_selection = {
            "mode": "exact_sender_handle",
            "sender_selected": True,
            "sender_handle": sender_handle.strip(),
            "sender_ref": sender_metadata["sender_ref"],
            "account_ref": sender_metadata["account_ref"],
            "email_preview": sender_metadata["email_preview"],
            "selection_supported": sender_metadata["selection_supported"],
            "full_email_returned": False,
            "sender_string_returned": False,
        }
    if signature_metadata is None:
        signature_selection: dict[str, Any] = {
            "mode": "signature_cleared",
            "signature_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        signature_selection = {
            "mode": "exact_signature_handle",
            "signature_selected": True,
            "signature_handle": signature_handle.strip(),
            "signature_ref": signature_metadata["signature_ref"],
            "name": signature_metadata["name"],
            "selection_supported": signature_metadata["selection_supported"],
            "body_returned": False,
            "content_returned": False,
        }
    if template_metadata is None:
        template_selection: dict[str, Any] = {
            "mode": "direct_body_text",
            "template_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        template_selection = {
            "mode": "exact_template_handle",
            "template_selected": True,
            "template_handle": template_handle.strip(),
            "template_ref": template_metadata["template_ref"],
            "name": template_metadata["name"],
            "subject_used": False,
            "body_chars": template_metadata["body_chars"],
            "body_returned": False,
            "content_returned": False,
        }
    proposed = {
        "kind": "mail_reply",
        "format": "plaintext",
        "source_message_handle": message_handle,
        "source_mailbox_ref": target["mailbox_ref"],
        "reply_mode": reply_mode,
        "reply_all_permitted": reply_all,
        "forward_permitted": False,
        "recipient_inputs_permitted": False,
        "subject_input_permitted": False,
        "subject": reply_subject,
        "body_chars": len(normalized_body),
        "body_preview_text": body_preview,
        "body_preview_chars": len(body_preview),
        "body_preview_truncated": body_preview_truncated,
        "send_permitted": True,
        "irreversible_external_send": True,
        "retry_safe": False,
        "attachments_permitted": bool(attachment_infos),
        **attachment_preview,
        "sender_selection": sender_selection,
        "signature_selection": signature_selection,
        "template_selection": template_selection,
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "source_message_handle": message_handle,
        "source_state": source_state,
        "proposed": {
            **proposed,
            "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
            "attachment_identities": [info["identity"] for info in attachment_infos],
        },
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    result = {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": {
                "message_handle": message_handle,
                "mailbox_ref": target["mailbox_ref"],
            },
            "proposed": proposed,
            "source_state": source_state,
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
    if include_private:
        result["_private"] = {"attachment_infos": copy.deepcopy(attachment_infos)}
    return result


def apply_mail_reply(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_reply(
        operation,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body_text=body_text,
        message_handle=message_handle,
        sender_handle=sender_handle,
        signature_handle=signature_handle,
        template_handle=template_handle,
        attachment_paths=attachment_paths,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=script_runner,
        include_private=True,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Mail apply approval token did not match the plan.")],
            plan=plan,
        )

    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            return _apply_error([template_warning], plan=plan)
        planned_template = preview["proposed"].get("template_selection", {})
        if (
            template_metadata is None
            or template_metadata.get("template_ref") != planned_template.get("template_ref")
        ):
            return _apply_error(
                [_warning("stale_template_state", "Mail template changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    reply_body_source = str(template["body_text"]) if template is not None else body_text
    normalized_body, _ = _normalize_reply_body(reply_body_source)
    attachment_infos = _approved_draft_attachment_infos(plan)
    if attachment_paths and len(attachment_infos) != int(preview["proposed"].get("attachment_count") or 0):
        return _apply_error(
            [_warning("invalid_plan", "Mail reply attachment approval metadata was unavailable; re-plan before applying.")],
            plan=plan,
        )
    sender_identity: dict[str, str] | None = None
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            return _apply_error([sender_warning], plan=plan)
        planned_sender = preview["proposed"].get("sender_selection", {})
        if sender_metadata is None or sender_metadata.get("sender_ref") != planned_sender.get("sender_ref"):
            return _apply_error(
                [_warning("stale_sender_state", "Mail sender identity changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    signature_identity: dict[str, str] | None = None
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        signature_identity, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            return _apply_error([signature_warning], plan=plan)
        planned_signature = preview["proposed"].get("signature_selection", {})
        if (
            signature_metadata is None
            or signature_metadata.get("signature_ref") != planned_signature.get("signature_ref")
        ):
            return _apply_error(
                [_warning("stale_signature_state", "Mail signature changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    resolved_db_path = _resolve_db_path(db_path)
    resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
    try:
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=resolved_mail_root,
            )
    except StoreUnavailableError:
        return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded")
    except MailTriageIdentityUnavailable:
        return _apply_error(
            [
                _warning(
                    "message_identity_unavailable",
                    "Mail message RFC identity was no longer available through the local message file.",
                )
            ],
            plan=plan,
        )
    if target is None:
        return _apply_error(
            [_warning("message_not_found", "Mail message handle no longer resolves to a live message.")],
            plan=plan,
        )
    if _triage_state_fingerprint(target) != preview["source_state"]:
        return _apply_error(
            [_warning("stale_message_state", "Mail message changed since the plan; re-plan before applying.")],
            plan=plan,
        )

    reply_subject = _reply_subject(target["subject"])
    sent_handles_before = _sent_handle_snapshot(
        reply_subject,
        db_path=resolved_db_path,
    )
    runner = script_runner or _run_osascript
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-") as attachment_temp_dir:
            automation_attachment_paths = _prepare_draft_attachment_copies(
                attachment_infos,
                Path(attachment_temp_dir),
            )
            automation_output = runner(
                _mail_reply_message_script(
                    account_id=target["account_id"],
                    mailbox_name=target["mailbox_name"],
                    message_id=target["message_id"],
                    body_text=normalized_body,
                    sender=_sender_value(sender_identity),
                    signature_name=_signature_value(signature_identity),
                    reply_to_all=str(preview["proposed"].get("reply_mode")) == "reply_all",
                    attachment_paths=automation_attachment_paths,
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
    except DraftAttachmentChangedError:
        return _apply_error(
            [_warning("current_attachment_changed", "Mail reply attachment changed after approval; re-plan before applying.")],
            plan=plan,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail reply timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail reply could not be sent safely.")],
            plan=plan,
        )

    if attachment_infos:
        automation_attachment_count = _extract_attachment_output_count(automation_output)
        if automation_attachment_count != len(attachment_infos):
            return _apply_error(
                [
                    _warning(
                        "attachment_read_back_unavailable",
                        "Mail reply was accepted but attachment automation confirmation was unavailable.",
                    )
                ],
                plan=plan,
                status="partial",
                mutation_applied=True,
            )
    if sender_identity is not None and _extract_sender_output_email(automation_output) != sender_identity["email_address"]:
        return _apply_error(
            [_warning("sender_read_back_unavailable", "Mail reply was sent but selected sender read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    if signature_identity is not None and _extract_signature_output_name(automation_output) != signature_identity["name"]:
        return _apply_error(
            [
                _warning(
                    "signature_read_back_unavailable",
                    "Mail reply was sent but selected signature read-back was unavailable.",
                )
            ],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    read_back = _find_matching_sent_content_with_retry(
        reply_subject,
        normalized_body,
        db_path=resolved_db_path,
        mail_root=resolved_mail_root,
        excluded_handles=sent_handles_before,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail reply was accepted but local Sent read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    proof = _mail_sent_read_back_proof(read_back, normalized_body)
    proof.update(
        {
            "reply_copy_confirmed": True,
            "source_message_handle": message_handle,
            "reply_mode": str(preview["proposed"].get("reply_mode", "sender_only")),
        }
    )
    if attachment_infos:
        proof.update(_draft_attachment_read_back(attachment_infos, send_permitted=True))
    if sender_metadata is not None:
        proof.update(
            {
                "sender_ref": sender_metadata["sender_ref"],
                "sender_selection_confirmed": True,
                "full_email_returned": False,
                "sender_string_returned": False,
            }
        )
    if signature_metadata is not None:
        proof.update(
            {
                "signature_ref": signature_metadata["signature_ref"],
                "signature_selection_confirmed": True,
                "signature_body_returned": False,
                "signature_content_returned": False,
            }
        )
    if template_metadata is not None:
        proof.update(
            {
                "template_ref": template_metadata["template_ref"],
                "template_selection_confirmed": True,
                "template_body_returned": False,
                "template_content_returned": False,
            }
        )
    return _apply_success(
        proof,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def plan_mail_forward(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
    include_private: bool = False,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in FORWARD_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation forward_message."))
    if not is_int_handle(message_handle, "mail:message"):
        warnings.append(_warning("invalid_message_handle", "Expected mail:message opaque handle from search output."))
    if subject.strip():
        warnings.append(
            _warning(
                "unexpected_subject",
                "Mail forward derives its subject from the exact source message; direct subject input is not accepted.",
            )
        )
    normalized_to, to_warnings = _normalize_recipients(to or [], field="to")
    normalized_cc, cc_warnings = _normalize_recipients(cc or [], field="cc")
    normalized_bcc, bcc_warnings = _normalize_recipients(bcc or [], field="bcc")
    warnings.extend(to_warnings)
    warnings.extend(cc_warnings)
    warnings.extend(bcc_warnings)
    if not normalized_to:
        warnings.append(_warning("missing_to", "Mail forward requires at least one To recipient."))
    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            warnings.append(template_warning)
        if template is not None and body_text.strip():
            warnings.append(
                _warning(
                    "unexpected_body_text_with_template",
                    "Mail template planning uses the selected template body; direct body_text is not accepted.",
                )
            )
    forward_body_source = str(template["body_text"]) if template is not None else body_text
    normalized_body, body_warning = _normalize_forward_body(forward_body_source)
    if body_warning is not None:
        warnings.append(body_warning)
    attachment_infos, attachment_warnings = _resolve_draft_attachments(attachment_paths or [])
    warnings.extend(attachment_warnings)
    sender_identity: dict[str, str] | None = None
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            warnings.append(sender_warning)
    signature_identity: dict[str, str] | None = None
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        signature_identity, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            warnings.append(signature_warning)
    if warnings:
        return _plan_error(warnings)

    try:
        resolved_db_path = _resolve_db_path(db_path)
        resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=resolved_mail_root,
            )
    except StoreUnavailableError:
        return _plan_error([_mail_store_unavailable_warning()])
    except MailTriageIdentityUnavailable as error:
        return _plan_error([_message_identity_unavailable_plan_warning(error)])
    if target is None:
        return _plan_error([_warning("message_not_found", "Mail message handle did not resolve to a live message.")])

    attachment_state, attachment_warning = _forward_attachment_state(
        message_handle,
        db_path=resolved_db_path,
        mail_root=resolved_mail_root,
        include_source_attachments=include_source_attachments,
    )
    forward_preview_privacy = _preview_privacy(content_inspected=True)
    if attachment_warning is not None:
        return _plan_error([attachment_warning], privacy=forward_preview_privacy)
    source_content_state, source_content_warning = _forward_source_content_state(target, mail_root=resolved_mail_root)
    if source_content_warning is not None:
        return _plan_error([source_content_warning], privacy=forward_preview_privacy)

    source_state = _triage_state_fingerprint(target)
    forward_subject = _forward_subject(target["subject"])
    body_preview, body_preview_truncated = _bounded_text(normalized_body, MAX_DRAFT_BODY_PREVIEW_CHARS)
    attachment_preview = _draft_attachment_preview(
        attachment_infos,
        send_permitted=True,
    )
    if sender_metadata is None:
        sender_selection: dict[str, Any] = {
            "mode": "mail_app_default",
            "sender_selected": False,
        }
    else:
        sender_selection = {
            "mode": "exact_sender_handle",
            "sender_selected": True,
            "sender_handle": sender_handle.strip(),
            "sender_ref": sender_metadata["sender_ref"],
            "account_ref": sender_metadata["account_ref"],
            "email_preview": sender_metadata["email_preview"],
            "selection_supported": sender_metadata["selection_supported"],
            "full_email_returned": False,
            "sender_string_returned": False,
        }
    if signature_metadata is None:
        signature_selection: dict[str, Any] = {
            "mode": "signature_cleared",
            "signature_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        signature_selection = {
            "mode": "exact_signature_handle",
            "signature_selected": True,
            "signature_handle": signature_handle.strip(),
            "signature_ref": signature_metadata["signature_ref"],
            "name": signature_metadata["name"],
            "selection_supported": signature_metadata["selection_supported"],
            "body_returned": False,
            "content_returned": False,
        }
    if template_metadata is None:
        template_selection: dict[str, Any] = {
            "mode": "direct_body_text",
            "template_selected": False,
            "body_returned": False,
            "content_returned": False,
        }
    else:
        template_selection = {
            "mode": "exact_template_handle",
            "template_selected": True,
            "template_handle": template_handle.strip(),
            "template_ref": template_metadata["template_ref"],
            "name": template_metadata["name"],
            "subject_used": False,
            "body_chars": template_metadata["body_chars"],
            "body_returned": False,
            "content_returned": False,
        }
    proposed = {
        "kind": "mail_forward",
        "format": "plaintext",
        "source_message_handle": message_handle,
        "source_mailbox_ref": target["mailbox_ref"],
        "forward_mode": "exact_source_message",
        "source_body_included": True,
        "source_attachments_permitted": include_source_attachments,
        "source_non_text_parts_permitted": include_source_attachments,
        "source_non_body_parts_permitted": include_source_attachments,
        "source_attachment_count": attachment_state["attachment_count"],
        "source_attachment_like_part_count": attachment_state["source_part_count"],
        "source_declared_attachment_count": attachment_state["declared_attachment_count"],
        "source_non_body_part_count": attachment_state["non_body_part_count"],
        "source_attachment_forwarding_requested": include_source_attachments,
        "source_forward_verification": SOURCE_FORWARD_VERIFICATION,
        "recipient_inputs_permitted": True,
        "subject_input_permitted": False,
        "subject": forward_subject,
        "to": normalized_to,
        "cc": normalized_cc,
        "bcc": normalized_bcc,
        "recipient_count": len(normalized_to) + len(normalized_cc) + len(normalized_bcc),
        "body_role": "prepend_text",
        "body_chars": len(normalized_body),
        "body_preview_text": body_preview,
        "body_preview_chars": len(body_preview),
        "body_preview_truncated": body_preview_truncated,
        "send_permitted": True,
        "irreversible_external_send": True,
        "retry_safe": False,
        "attachments_permitted": bool(attachment_infos),
        **attachment_preview,
        "sender_selection": sender_selection,
        "signature_selection": signature_selection,
        "template_selection": template_selection,
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "source_message_handle": message_handle,
        "source_state": source_state,
        "source_attachment_state": attachment_state["safe_sha256"],
        "source_content_state": source_content_state["safe_sha256"],
        "proposed": {
            **proposed,
            "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
            "attachment_identities": [info["identity"] for info in attachment_infos],
        },
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint({**fingerprint_payload, "idempotency_key": idempotency_key})
    result = {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": forward_preview_privacy,
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": {
                "message_handle": message_handle,
                "mailbox_ref": target["mailbox_ref"],
            },
            "proposed": proposed,
            "source_state": source_state,
            "source_attachment_state": attachment_state["safe_sha256"],
            "source_content_state": source_content_state["safe_sha256"],
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
    if include_private:
        result["_private"] = {"attachment_infos": copy.deepcopy(attachment_infos)}
    return result


def apply_mail_forward(
    operation: str,
    *,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
    approval_token: str = "",
    confirm_apply: bool = False,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    script_runner: ScriptRunner | None = None,
) -> dict[str, Any]:
    plan = plan_mail_forward(
        operation,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body_text=body_text,
        message_handle=message_handle,
        sender_handle=sender_handle,
        signature_handle=signature_handle,
        template_handle=template_handle,
        attachment_paths=attachment_paths,
        include_source_attachments=include_source_attachments,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=script_runner,
        include_private=True,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Mail apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Mail apply approval token did not match the plan.")],
            plan=plan,
        )

    normalized_to, _ = _normalize_recipients(to or [], field="to")
    normalized_cc, _ = _normalize_recipients(cc or [], field="cc")
    normalized_bcc, _ = _normalize_recipients(bcc or [], field="bcc")
    template: dict[str, Any] | None = None
    template_metadata: dict[str, Any] | None = None
    if template_handle.strip():
        template, template_metadata, template_warning = _resolve_mail_template_for_plan(template_handle)
        if template_warning is not None:
            return _apply_error([template_warning], plan=plan)
        planned_template = preview["proposed"].get("template_selection", {})
        if (
            template_metadata is None
            or template_metadata.get("template_ref") != planned_template.get("template_ref")
        ):
            return _apply_error(
                [_warning("stale_template_state", "Mail template changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    forward_body_source = str(template["body_text"]) if template is not None else body_text
    normalized_body, _ = _normalize_forward_body(forward_body_source)
    attachment_infos = _approved_draft_attachment_infos(plan)
    if attachment_paths and len(attachment_infos) != int(preview["proposed"].get("attachment_count") or 0):
        return _apply_error(
            [_warning("invalid_plan", "Mail forward attachment approval metadata was unavailable; re-plan before applying.")],
            plan=plan,
        )
    sender_identity: dict[str, str] | None = None
    sender_metadata: dict[str, Any] | None = None
    if sender_handle.strip():
        sender_identity, sender_metadata, sender_warning = _resolve_mail_sender_for_plan(
            sender_handle,
            script_runner=script_runner,
        )
        if sender_warning is not None:
            return _apply_error([sender_warning], plan=plan)
        planned_sender = preview["proposed"].get("sender_selection", {})
        if sender_metadata is None or sender_metadata.get("sender_ref") != planned_sender.get("sender_ref"):
            return _apply_error(
                [_warning("stale_sender_state", "Mail sender identity changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    signature_identity: dict[str, str] | None = None
    signature_metadata: dict[str, Any] | None = None
    if signature_handle.strip():
        signature_identity, signature_metadata, signature_warning = _resolve_mail_signature_for_plan(
            signature_handle,
            script_runner=script_runner,
        )
        if signature_warning is not None:
            return _apply_error([signature_warning], plan=plan)
        planned_signature = preview["proposed"].get("signature_selection", {})
        if (
            signature_metadata is None
            or signature_metadata.get("signature_ref") != planned_signature.get("signature_ref")
        ):
            return _apply_error(
                [_warning("stale_signature_state", "Mail signature changed since the plan; re-plan before applying.")],
                plan=plan,
            )
    resolved_db_path = _resolve_db_path(db_path)
    resolved_mail_root = mail_root or _mail_content_root(resolved_db_path)
    try:
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            target = _resolve_triage_target(
                connection,
                message_handle,
                mail_root=resolved_mail_root,
            )
    except StoreUnavailableError:
        return _apply_error([_mail_store_unavailable_warning()], plan=plan, status="degraded")
    except MailTriageIdentityUnavailable:
        return _apply_error(
            [
                _warning(
                    "message_identity_unavailable",
                    "Mail message RFC identity was no longer available through the local message file.",
                )
            ],
            plan=plan,
        )
    if target is None:
        return _apply_error(
            [_warning("message_not_found", "Mail message handle no longer resolves to a live message.")],
            plan=plan,
        )
    if _triage_state_fingerprint(target) != preview["source_state"]:
        return _apply_error(
            [_warning("stale_message_state", "Mail message changed since the plan; re-plan before applying.")],
            plan=plan,
        )
    attachment_state, attachment_warning = _forward_attachment_state(
        message_handle,
        db_path=resolved_db_path,
        mail_root=resolved_mail_root,
        include_source_attachments=include_source_attachments,
    )
    if attachment_warning is not None:
        return _apply_error([attachment_warning], plan=plan)
    if attachment_state["safe_sha256"] != preview["source_attachment_state"]:
        return _apply_error(
            [
                _warning(
                    "stale_source_attachment_state",
                    "Mail source attachment/non-body-part state changed since the plan; re-plan before applying.",
                )
            ],
            plan=plan,
        )
    source_content_state, source_content_warning = _forward_source_content_state(target, mail_root=resolved_mail_root)
    if source_content_warning is not None:
        return _apply_error([source_content_warning], plan=plan)
    if source_content_state["safe_sha256"] != preview["source_content_state"]:
        return _apply_error(
            [_warning("stale_source_content_state", "Mail source content changed since the plan; re-plan before applying.")],
            plan=plan,
        )

    forward_subject = _forward_subject(target["subject"])
    source_part_count = int(preview["proposed"].get("source_attachment_like_part_count") or 0)
    sent_handles_before = _sent_handle_snapshot(
        forward_subject,
        db_path=resolved_db_path,
    )
    runner = script_runner or _run_osascript
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-") as attachment_temp_dir:
            automation_attachment_paths = _prepare_draft_attachment_copies(
                attachment_infos,
                Path(attachment_temp_dir),
            )
            automation_output = runner(
                _mail_forward_message_script(
                    account_id=target["account_id"],
                    mailbox_name=target["mailbox_name"],
                    message_id=target["message_id"],
                    to=normalized_to,
                    cc=normalized_cc,
                    bcc=normalized_bcc,
                    subject=forward_subject,
                    body_text=normalized_body,
                    sender=_sender_value(sender_identity),
                    signature_name=_signature_value(signature_identity),
                    attachment_paths=automation_attachment_paths,
                    expected_source_part_count=source_part_count,
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
    except DraftAttachmentChangedError:
        return _apply_error(
            [_warning("current_attachment_changed", "Mail forward attachment changed after approval; re-plan before applying.")],
            plan=plan,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail forward timed out through local automation.")],
            plan=plan,
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail forward could not be sent safely.")],
            plan=plan,
        )

    expected_automation_attachment_count = len(attachment_infos) + source_part_count
    if expected_automation_attachment_count:
        automation_attachment_count = _extract_attachment_output_count(automation_output)
        if automation_attachment_count != expected_automation_attachment_count:
            return _apply_error(
                [
                    _warning(
                        "attachment_read_back_unavailable",
                        "Mail forward was accepted but attachment automation confirmation was unavailable.",
                    )
                ],
                plan=plan,
                status="partial",
                mutation_applied=True,
            )
    if sender_identity is not None and _extract_sender_output_email(automation_output) != sender_identity["email_address"]:
        return _apply_error(
            [_warning("sender_read_back_unavailable", "Mail forward was sent but selected sender read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    if signature_identity is not None and _extract_signature_output_name(automation_output) != signature_identity["name"]:
        return _apply_error(
            [
                _warning(
                    "signature_read_back_unavailable",
                    "Mail forward was sent but selected signature read-back was unavailable.",
                )
            ],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )

    read_back_matches = _find_matching_forward_sent_contents_with_retry(
        forward_subject,
        normalized_body,
        db_path=resolved_db_path,
        mail_root=resolved_mail_root,
        excluded_handles=sent_handles_before,
    )
    if not read_back_matches:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail forward was accepted but local Sent read-back was unavailable.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    if len(read_back_matches) > 1:
        return _apply_error(
            [
                _warning(
                    "ambiguous_forward_read_back",
                    "Mail forward was accepted but new matching Sent read-back was not uniquely attributable.",
                )
            ],
            plan=plan,
            status="partial",
            mutation_applied=True,
        )
    read_back = read_back_matches[0]

    proof = _mail_forward_read_back_proof(read_back, normalized_body)
    proof.update(
        {
            "forward_copy_confirmed": True,
            "source_message_handle": message_handle,
            "forward_mode": "exact_source_message",
            "source_body_included": True,
            "source_attachments_permitted": include_source_attachments,
            "source_non_text_parts_permitted": include_source_attachments,
            "source_non_body_parts_permitted": include_source_attachments,
            "source_attachment_count": source_part_count,
            "source_attachment_like_part_count": source_part_count,
            "source_declared_attachment_count": preview["proposed"].get("source_declared_attachment_count"),
            "source_non_body_part_count": preview["proposed"].get("source_non_body_part_count"),
            "forwarded_attachment_count": expected_automation_attachment_count,
            "source_forward_verification": SOURCE_FORWARD_VERIFICATION,
            "source_content_state": preview["source_content_state"],
        }
    )
    if attachment_infos:
        proof.update(_draft_attachment_read_back(attachment_infos, send_permitted=True))
    if sender_metadata is not None:
        proof.update(
            {
                "sender_ref": sender_metadata["sender_ref"],
                "sender_selection_confirmed": True,
                "full_email_returned": False,
                "sender_string_returned": False,
            }
        )
    if signature_metadata is not None:
        proof.update(
            {
                "signature_ref": signature_metadata["signature_ref"],
                "signature_selection_confirmed": True,
                "signature_body_returned": False,
                "signature_content_returned": False,
            }
        )
    if template_metadata is not None:
        proof.update(
            {
                "template_ref": template_metadata["template_ref"],
                "template_selection_confirmed": True,
                "template_body_returned": False,
                "template_content_returned": False,
            }
        )
    return _apply_success(
        proof,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _invalid_content_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected mail:message:v2 opaque handle from search output.",
            )
        ],
    }


def _invalid_unsubscribe_metadata_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _unsubscribe_metadata_privacy(header_inspected=False),
        "result": None,
        "result_count": 0,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected mail:message:v2 opaque handle from search output.",
            )
        ],
    }


def _mail_unsubscribe_identity(row) -> dict[str, Any]:
    metadata = _row_to_metadata(row)
    return {
        "handle": metadata["handle"],
        "subject": metadata["subject"],
        "account_ref": metadata["account_ref"],
        "mailbox_ref": metadata["mailbox_ref"],
    }


def _is_rfc8058_post_header(value: Any) -> bool:
    text = str(value).strip()
    if not text or _CONTROL_CHARACTER_PATTERN.search(text):
        return False
    return _RFC8058_POST_PATTERN.fullmatch(text) is not None


def _allowlisted_list_header_urls(values: list[Any]) -> tuple[list[str], int]:
    endpoints: list[str] = []
    rejected = 0
    for value in values:
        text = str(value)
        candidates = _LIST_ENDPOINT_PATTERN.findall(text)
        if not candidates:
            rejected += 1
            continue
        for candidate in candidates:
            normalized = _normalize_list_endpoint(candidate)
            if normalized is None:
                rejected += 1
                continue
            if normalized not in endpoints:
                endpoints.append(normalized)
    return endpoints, rejected


def _normalize_list_endpoint(value: str) -> str | None:
    endpoint = value.strip()
    if not endpoint or _CONTROL_CHARACTER_PATTERN.search(endpoint):
        return None
    try:
        decoded = unquote(endpoint)
    except (UnicodeError, ValueError):
        return None
    if _CONTROL_CHARACTER_PATTERN.search(decoded) or any(character.isspace() for character in endpoint):
        return None

    if "\\" in endpoint:
        return None
    try:
        parsed = urlparse(endpoint)
        scheme = parsed.scheme.casefold()
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    if scheme not in {"http", "https", "mailto"}:
        return None
    if scheme in {"http", "https"}:
        if not parsed.netloc or not hostname or username or password:
            return None
        _ = port
    elif parsed.netloc or not parsed.path or parsed.fragment:
        return None
    return scheme + endpoint[len(parsed.scheme) :]


class _BodyUnsubscribeHTMLParser(HTMLParser):
    _HIDDEN_TAGS = {"head", "noscript", "script", "style", "template", "title"}
    _SEPARATOR_TAGS = {
        "br",
        "div",
        "footer",
        "li",
        "p",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.endpoints: list[dict[str, Any]] = []
        self._hidden_depth = 0
        self._visible_tail = ""
        self._active_anchor: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._HIDDEN_TAGS:
            self._hidden_depth += 1
            return
        if self._hidden_depth:
            return
        if normalized_tag in self._SEPARATOR_TAGS:
            if self._active_anchor is not None:
                self._active_anchor["text"].append(" ")
            else:
                self._append_visible(" ")
        if normalized_tag != "a" or self._active_anchor is not None:
            return
        href = next(
            (
                value
                for name, value in attrs
                if name.casefold() == "href" and isinstance(value, str)
            ),
            None,
        )
        self._active_anchor = {
            "href": href,
            "text": [],
            "preceding": self._visible_tail[-MAX_BODY_LINK_VISIBLE_CONTEXT_CHARS:],
        }

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._HIDDEN_TAGS:
            self._hidden_depth = max(0, self._hidden_depth - 1)
            return
        if self._hidden_depth:
            return
        if normalized_tag == "a" and self._active_anchor is not None:
            self._finish_anchor()
        if normalized_tag in self._SEPARATOR_TAGS:
            if self._active_anchor is not None:
                self._active_anchor["text"].append(" ")
            else:
                self._append_visible(" ")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        visible = _normalize_body_link_visible_text(data)
        if not visible:
            return
        if self._active_anchor is not None:
            self._active_anchor["text"].append(visible)
        else:
            self._append_visible(visible)

    def finish(self) -> None:
        if self._active_anchor is not None:
            self._finish_anchor()

    def _append_visible(self, value: str) -> None:
        combined = f"{self._visible_tail} {value}".strip()
        self._visible_tail = combined[-MAX_BODY_LINK_VISIBLE_CONTEXT_CHARS:]

    def _finish_anchor(self) -> None:
        anchor = self._active_anchor
        self._active_anchor = None
        if anchor is None or len(self.endpoints) >= MAX_BODY_LINK_ENDPOINTS:
            return
        href = anchor.get("href")
        if not isinstance(href, str):
            return
        visible_text = _normalize_body_link_visible_text("".join(anchor["text"]))
        preceding = _normalize_body_link_visible_text(anchor["preceding"])
        endpoint = _qualifying_body_unsubscribe_endpoint(
            href,
            visible_text=visible_text,
            preceding_visible_text=preceding,
        )
        if endpoint is None:
            return
        if all(existing["url"] != endpoint["url"] for existing in self.endpoints):
            self.endpoints.append(endpoint)


def _normalize_body_link_visible_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _qualifying_body_unsubscribe_endpoint(
    href: str,
    *,
    visible_text: str,
    preceding_visible_text: str,
) -> dict[str, Any] | None:
    url = _normalize_list_endpoint(href)
    if url is None:
        return None
    explicit_text = _BODY_LINK_EXPLICIT_TEXT_PATTERN.search(visible_text) is not None
    parsed = urlparse(url)
    href_path_query = unquote(f"{parsed.path}?{parsed.query}")
    if _CONTROL_CHARACTER_PATTERN.search(href_path_query):
        return None
    denied_href = _BODY_LINK_DENY_HREF_PATTERN.search(href_path_query) is not None
    href_matches = _BODY_LINK_HREF_PATTERN.search(href_path_query) is not None
    adjacent_matches = (
        _BODY_LINK_CLICK_HERE_PATTERN.search(visible_text) is not None
        and _BODY_LINK_EXPLICIT_TEXT_PATTERN.search(preceding_visible_text) is not None
    )
    if not explicit_text and denied_href:
        return None
    if not (explicit_text or href_matches or adjacent_matches):
        return None
    match_reason = (
        "explicit_unsubscribe_text"
        if explicit_text
        else "unsubscribe_url"
        if href_matches
        else "adjacent_unsubscribe_phrase"
    )
    return _mail_body_unsubscribe_endpoint(url, match_reason=match_reason)


def _mail_body_unsubscribe_endpoint(
    url: str,
    *,
    match_reason: str,
) -> dict[str, Any]:
    scheme = urlparse(url).scheme.casefold()
    return {
        "url": url,
        "scheme": scheme,
        "action": "unsubscribe",
        "classification": "body_link",
        "match_reason": match_reason,
        "request_method": "GET" if scheme in {"http", "https"} else "mailto",
        "request_content_type": None,
        "request_body": None,
        "one_click": False,
        "manual_required": True,
    }


def _mail_body_unsubscribe_endpoints(
    message_path: Path,
) -> tuple[list[dict[str, Any]], bool, list[dict[str, str]]]:
    try:
        if message_path.stat().st_size > MAX_BODY_LINK_MIME_BYTES:
            return [], False, [
                _warning(
                    "body_link_inspection_too_large",
                    "Selected Mail MIME content exceeded the bounded body-link inspection limit.",
                )
            ]
        raw = message_path.read_bytes()
        message = BytesParser(policy=policy.default).parsebytes(_mime_bytes_from_emlx(raw))
    except (LookupError, OSError, TypeError, UnicodeError, ValueError):
        return [], False, [
            _warning(
                "body_link_inspection_failed",
                "Selected Mail body links could not be inspected safely.",
            )
        ]

    endpoints: list[dict[str, Any]] = []
    try:
        for part in message.walk():
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() != "text/html":
                continue
            content = part.get_content()
            if not isinstance(content, str):
                continue
            parser = _BodyUnsubscribeHTMLParser()
            parser.feed(content)
            parser.close()
            parser.finish()
            for endpoint in parser.endpoints:
                if all(existing["url"] != endpoint["url"] for existing in endpoints):
                    endpoints.append(endpoint)
                    if len(endpoints) >= MAX_BODY_LINK_ENDPOINTS:
                        return endpoints, True, []
    except (LookupError, TypeError, UnicodeError, ValueError):
        return [], False, [
            _warning(
                "body_link_inspection_failed",
                "Selected Mail body links could not be inspected safely.",
            )
        ]
    return endpoints, True, []


def _mail_unsubscribe_endpoint(url: str, *, one_click_header: bool) -> dict[str, Any]:
    scheme = urlparse(url).scheme.casefold()
    one_click = one_click_header and scheme == "https"
    return {
        "url": url,
        "scheme": scheme,
        "action": "unsubscribe",
        "classification": "one_click" if one_click else "manual_required",
        "request_method": "POST" if one_click else ("GET" if scheme in {"http", "https"} else "mailto"),
        "request_content_type": "application/x-www-form-urlencoded" if one_click else None,
        "request_body": "List-Unsubscribe=One-Click" if one_click else None,
        "one_click": one_click,
        "manual_required": not one_click,
    }


def _mail_help_endpoint(url: str) -> dict[str, Any]:
    scheme = urlparse(url).scheme.casefold()
    return {
        "url": url,
        "scheme": scheme,
        "action": "help",
        "classification": "manual_required",
        "request_method": "GET" if scheme in {"http", "https"} else "mailto",
        "one_click": False,
        "manual_required": True,
    }


def _select_mail_row(connection, rowid: int):
    return connection.execute(
        """
        SELECT
            m.ROWID AS rowid,
            s.subject AS subject,
            mb.url AS mailbox_url,
            m.date_received AS date_received,
            m.date_sent AS date_sent,
            m.read AS read,
            m.flagged AS flagged,
            m.deleted AS deleted,
            m.size AS size
        FROM messages m
        LEFT JOIN subjects s ON m.subject = s.ROWID
        LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
        WHERE m.ROWID = ?
          AND COALESCE(m.deleted, 0) = 0
        LIMIT 1
        """,
        (rowid,),
    ).fetchone()


def _invalid_attachment_message_handle_result(*, export: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _export_privacy() if export else _attachment_privacy(content_inspected=False),
        "result": None if export else None,
        "results": [] if not export else None,
        "result_count": 0,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected mail:message:v2 opaque handle from search output.",
            )
        ],
    }


def _invalid_attachment_export_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected mail:attachment:v1 opaque handle from mail attachment list output.",
            )
        ],
    }


def _parse_mail_message_bytes(raw: bytes):
    try:
        mime_bytes = _mime_bytes_from_emlx(raw)
        return BytesParser(policy=policy.default).parsebytes(mime_bytes)
    except (OSError, ValueError):
        return None


def _parse_mail_message(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
):
    raw = _read_message_file_bytes(mail_root, rowid, index=index)
    if raw is None:
        return None
    return _parse_mail_message_bytes(raw)


def _mail_message_file_metadata(
    mail_root: Path,
    rowid: int,
    fingerprint: str,
) -> dict[str, Any] | None:
    message = _parse_mail_message(mail_root, rowid)
    if message is None:
        return None
    attachment_metadata = _mail_attachment_header_metadata_list(
        message,
        limit=MAX_MAIL_DISCOVERY_LIMIT,
    )
    message_id = _bounded_string(message.get("Message-ID", ""), 300)
    return {
        "header_metadata_status": "available",
        "from": _masked_address_metadata(message.get_all("From", [])),
        "to": _masked_address_metadata(message.get_all("To", [])),
        "cc": _masked_address_metadata(message.get_all("Cc", [])),
        "bcc": _masked_address_metadata(message.get_all("Bcc", [])),
        "message_id_ref": _message_id_ref(message_id),
        "message_id_returned": False,
        "full_headers_returned": False,
        "full_email_returned": False,
        "attachment_metadata_status": "available",
        "attachment_count": len(attachment_metadata),
        "attachment_filenames": [
            _bounded_string(item["filename"], 200)
            for item in attachment_metadata
            if item.get("filename")
        ][:MAX_MAIL_DISCOVERY_LIMIT],
        "attachment_types": [
            _bounded_string(item["content_type"], 200)
            for item in attachment_metadata
            if item.get("content_type")
        ][:MAX_MAIL_DISCOVERY_LIMIT],
        "attachment_content_returned": False,
        "attachment_paths_returned": False,
    }


def _masked_address_metadata(values: list[str]) -> dict[str, Any]:
    addresses = []
    for _name, address in getaddresses(values):
        normalized = _normalize_sender_email(address)
        if normalized:
            addresses.append(normalized)
    previews = [_mask_email_address(address) for address in addresses[:10]]
    return {
        "count": len(addresses),
        "previews": previews,
        "truncated": len(addresses) > len(previews),
        "full_email_returned": False,
    }


def _message_id_ref(message_id: str) -> str:
    normalized = _bounded_string(message_id, 500)
    if not normalized:
        return ""
    return f"message-id:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12]}"


def _parse_message_for_attachment_access(mail_root: Path, rowid: int):
    return _parse_mail_message(mail_root, rowid)


def _mail_attachment_metadata_list(
    message,
    *,
    fingerprint: str,
    rowid: int,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for part_index, part, _header_metadata in _mail_attachment_header_parts(message, limit=limit):
        results.append(
            _mail_attachment_metadata(
                part,
                fingerprint=fingerprint,
                rowid=rowid,
                part_index=part_index,
            )
        )
    return results


def _mail_attachment_header_parts(
    message,
    *,
    limit: int,
) -> list[tuple[int, Any, dict[str, Any]]]:
    results: list[tuple[int, Any, dict[str, Any]]] = []
    for part_index, part in enumerate(message.walk()):
        if part.is_multipart() or not _is_attachment_part(part):
            continue
        results.append((part_index, part, _mail_attachment_header_metadata(part)))
        if len(results) >= limit:
            break
    return results


def _mail_attachment_header_metadata_list(
    message,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        header_metadata
        for _part_index, _part, header_metadata in _mail_attachment_header_parts(
            message,
            limit=limit,
        )
    ]


def _find_mail_attachment_part(
    message,
    *,
    fingerprint: str,
    rowid: int,
    attachment_handle: str,
):
    for part_index, part in enumerate(message.walk()):
        if part.is_multipart() or not _is_attachment_part(part):
            continue
        metadata = _mail_attachment_identity_metadata(part)
        if opaque_handle_matches(
            attachment_handle,
            ATTACHMENT_HANDLE_PREFIX,
            fingerprint,
            rowid,
            part_index,
            metadata["filename"],
            metadata["content_type"],
            metadata["file_size"],
            metadata["content_sha256"],
        ):
            return part_index, part
    return None


def _mail_attachment_metadata(
    part,
    *,
    fingerprint: str,
    rowid: int,
    part_index: int,
) -> dict[str, Any]:
    metadata = _mail_attachment_identity_metadata(part)
    return {
        "handle": make_opaque_handle(
            ATTACHMENT_HANDLE_PREFIX,
            fingerprint,
            rowid,
            part_index,
            metadata["filename"],
            metadata["content_type"],
            metadata["file_size"],
            metadata["content_sha256"],
        ),
        "message_handle": make_int_handle("mail:message", rowid),
        "filename": metadata["filename"],
        "content_type": metadata["content_type"],
        "content_disposition": metadata["content_disposition"],
        "file_size": metadata["file_size"],
        "part_index": part_index,
        "attachment_type": _mail_attachment_type(
            metadata["content_type"],
            metadata["filename"],
        ),
        "media_status": metadata["media_status"],
        "remote_status": "local_or_unknown",
        "attachment_content_returned": False,
        "attachment_content_exported": False,
    }


def _mail_attachment_identity_metadata(part) -> dict[str, Any]:
    header = _mail_attachment_header_metadata(part)
    data = _attachment_payload_bytes(part)
    return {
        "filename": header["filename"],
        "content_type": header["content_type"],
        "content_disposition": header["content_disposition"],
        "file_size": len(data) if data is not None else _declared_attachment_size(part),
        "content_sha256": hashlib.sha256(data).hexdigest() if data is not None else "",
        "media_status": "available" if data is not None else "unavailable",
    }


def _mail_attachment_header_metadata(part) -> dict[str, Any]:
    filename = _mail_attachment_filename(part)
    content_type = _bounded_string(part.get_content_type(), 300) or "application/octet-stream"
    disposition = _bounded_string(part.get_content_disposition(), 50) or "attachment"
    return {
        "filename": filename,
        "content_type": content_type,
        "content_disposition": disposition,
        "attachment_type": _mail_attachment_type(content_type, filename),
    }


def _is_attachment_part(part) -> bool:
    disposition = part.get_content_disposition()
    if disposition == "attachment":
        return True
    filename = part.get_filename()
    if filename and disposition in {None, "inline"}:
        return True
    if disposition not in {None, "inline"}:
        return False
    content_type = (part.get_content_type() or "").casefold()
    if content_type in {"text/plain", "text/html"}:
        return False
    if part.get("Content-ID") or disposition == "inline":
        return True
    return bool(content_type)


def _mail_attachment_filename(part) -> str:
    filename = part.get_filename() or ""
    safe_name = Path(str(filename).replace("\\", "/")).name
    return _bounded_string(safe_name, 500)


def _attachment_payload_bytes(part) -> bytes | None:
    try:
        data = part.get_payload(decode=True)
    except (LookupError, UnicodeError, ValueError):
        return None
    if data is None:
        payload = part.get_payload()
        if isinstance(payload, bytes):
            data = payload
        elif isinstance(payload, str):
            charset = part.get_content_charset() or "utf-8"
            try:
                data = payload.encode(charset, errors="replace")
            except LookupError:
                data = payload.encode("utf-8", errors="replace")
    if data is None:
        return None
    if not data and (_declared_attachment_size(part) or 0) > 0:
        return None
    return data


def _attachment_search_payload_warning(part) -> str | None:
    declared_size = _declared_attachment_size(part)
    if declared_size is not None and declared_size > MAX_MAIL_ATTACHMENT_CONTENT_BYTES:
        return "attachment_too_large"
    try:
        payload = part.get_payload()
    except (LookupError, UnicodeError, ValueError):
        return "payload_unavailable"
    if isinstance(payload, list):
        return "payload_unavailable"
    raw_length = len(payload) if isinstance(payload, (bytes, str)) else 0
    transfer_encoding = str(part.get("Content-Transfer-Encoding") or "").strip().casefold()
    if transfer_encoding == "base64":
        compact_length = sum(1 for char in payload if not str(char).isspace()) if isinstance(payload, str) else raw_length
        if (compact_length * 3) // 4 > MAX_MAIL_ATTACHMENT_CONTENT_BYTES:
            return "attachment_too_large"
    elif raw_length > MAX_MAIL_ATTACHMENT_CONTENT_BYTES:
        return "attachment_too_large"
    return None


def _attachment_search_text(part, *, include_ocr: bool) -> tuple[str | None, str, bool]:
    preflight_warning = _attachment_search_payload_warning(part)
    if preflight_warning is not None:
        return None, preflight_warning, False
    data = _attachment_payload_bytes(part)
    if data is None:
        return None, "payload_unavailable", False
    if len(data) > MAX_MAIL_ATTACHMENT_CONTENT_BYTES:
        return None, "attachment_too_large", False

    content_type = (part.get_content_type() or "").casefold()
    filename = _mail_attachment_filename(part)
    suffix = Path(filename).suffix.casefold()
    if content_type == "text/html" or suffix in {".html", ".htm"}:
        charset = part.get_content_charset() or "utf-8"
        try:
            html = data.decode(charset, errors="replace")
        except LookupError:
            html = data.decode("utf-8", errors="replace")
        return _bounded_extracted_text(_html_to_text(html)), "html", False
    if content_type.startswith("text/") or suffix in {".txt", ".csv", ".json", ".xml", ".ics"}:
        charset = part.get_content_charset() or "utf-8"
        try:
            return _bounded_extracted_text(data.decode(charset, errors="replace")), "text", False
        except LookupError:
            return _bounded_extracted_text(data.decode("utf-8", errors="replace")), "text", False
    if content_type == "application/pdf" or suffix == ".pdf":
        pdf_text = _pdf_text_from_bytes(data)
        if pdf_text:
            return _bounded_extracted_text(pdf_text), "pdf_text", False
        if include_ocr:
            ocr_text = _pdf_ocr_text_from_bytes(data)
            if ocr_text:
                return _bounded_extracted_text(ocr_text), "pdf_ocr", True
            return None, "pdf_ocr_unavailable", True
        return None, "pdf_text_unavailable", False
    return None, "unsupported_attachment_type", False


def _bounded_extracted_text(text: str) -> str:
    return _normalize_text(text)[:MAX_MAIL_ATTACHMENT_EXTRACTED_CHARS]


def _pdf_text_from_bytes(data: bytes) -> str | None:
    tool = shutil.which("pdftotext")
    if not tool:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-pdf-") as tmp:
            input_path = Path(tmp) / "attachment.pdf"
            input_path.write_bytes(data)
            completed = subprocess.run(
                [tool, "-enc", "UTF-8", "-q", str(input_path), "-"],
                check=False,
                capture_output=True,
                timeout=MAIL_ATTACHMENT_TEXT_TIMEOUT_SECONDS,
            )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


def _pdf_ocr_text_from_bytes(data: bytes) -> str | None:
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-ocr-") as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "attachment.pdf"
            output_path = tmp_path / "ocr.pdf"
            sidecar_path = tmp_path / "ocr.txt"
            input_path.write_bytes(data)
            completed = subprocess.run(
                [
                    ocrmypdf,
                    "--quiet",
                    "--skip-text",
                    "--sidecar",
                    str(sidecar_path),
                    str(input_path),
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                timeout=MAIL_ATTACHMENT_OCR_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or not sidecar_path.exists():
                return None
            return sidecar_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _declared_attachment_size(part) -> int | None:
    for key, value in part.items():
        if key.lower() in {"x-apple-content-length", "size"}:
            try:
                size = int(str(value).strip())
            except ValueError:
                continue
            if size >= 0:
                return size
    return None


def _mail_attachment_type(content_type: Any, filename: Any) -> str:
    mime_type = _bounded_string(content_type, 300).lower()
    suffix = Path(_bounded_string(filename, 300)).suffix.lower()
    if mime_type.startswith("image/") or suffix in {
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
    if mime_type.startswith("video/") or suffix in {".m4v", ".mov", ".mp4"}:
        return "video"
    if mime_type.startswith("audio/") or suffix in {
        ".aif",
        ".aiff",
        ".m4a",
        ".mp3",
        ".wav",
    }:
        return "audio"
    if mime_type in {
        "application/pdf",
        "application/msword",
        "application/rtf",
        "text/plain",
    } or suffix in {".doc", ".docx", ".pdf", ".rtf", ".txt"}:
        return "document"
    return "other"


def _resolve_draft_attachments(values: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    raw_values = [str(value).strip() for value in values if str(value).strip()]
    warnings: list[dict[str, str]] = []
    if len(raw_values) != len(values):
        warnings.append(_warning("missing_attachment_path", "Mail attachment paths must be non-empty."))
    if len(raw_values) > MAX_DRAFT_ATTACHMENTS:
        warnings.append(_warning("too_many_attachments", "Mail attachment count exceeded the maximum."))
    if warnings:
        return [], warnings

    candidates: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    total_bytes = 0
    for raw in raw_values:
        original = Path(raw).expanduser()
        try:
            if original.is_symlink():
                warnings.append(_warning("symlink_attachment_blocked", "Mail attachment path cannot be a symlink."))
                continue
            resolved = original.resolve(strict=True)
        except (OSError, RuntimeError):
            warnings.append(_warning("attachment_unavailable", "Mail attachment path is unavailable."))
            continue
        resolved_key = str(resolved)
        if resolved_key in seen_paths:
            warnings.append(_warning("duplicate_attachment_path", "Mail attachment paths must be unique."))
            continue
        try:
            file_stat = _draft_attachment_file_stat(resolved)
        except IsADirectoryError:
            warnings.append(_warning("attachment_not_file", "Mail attachment path must point to a regular file."))
            continue
        except OSError:
            warnings.append(_warning("attachment_unavailable", "Mail attachment path is unavailable."))
            continue
        if file_stat.st_size <= 0:
            warnings.append(_warning("attachment_empty", "Mail attachment path must point to a non-empty file."))
            continue
        if file_stat.st_size > MAX_DRAFT_ATTACHMENT_BYTES:
            warnings.append(_warning("attachment_too_large", "Mail attachment exceeded the per-file size limit."))
            continue
        prospective_total = total_bytes + int(file_stat.st_size)
        if prospective_total > MAX_DRAFT_ATTACHMENT_TOTAL_BYTES:
            warnings.append(_warning("attachments_too_large", "Mail attachment total size exceeded the limit."))
            return [], warnings
        total_bytes = prospective_total
        filename = _bounded_string(resolved.name, 500).strip()
        if not filename:
            warnings.append(_warning("attachment_unavailable", "Mail attachment filename is unavailable."))
            continue
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        candidates.append(
            {
                "resolved": resolved,
                "resolved_path": resolved_key,
                "filename": filename,
                "file_size": int(file_stat.st_size),
                "content_type": _bounded_string(mime_type, 300),
                "attachment_type": _mail_attachment_type(mime_type, filename),
            }
        )
        seen_paths.add(resolved_key)

    if warnings:
        return [], warnings

    attachments: list[dict[str, Any]] = []
    for candidate in candidates:
        resolved = candidate["resolved"]
        try:
            file_stat, content_sha256 = _draft_attachment_file_state(
                resolved,
                expected_size=int(candidate["file_size"]),
            )
        except IsADirectoryError:
            warnings.append(_warning("attachment_not_file", "Mail attachment path must point to a regular file."))
            continue
        except OSError:
            warnings.append(_warning("attachment_unavailable", "Mail attachment path is unavailable."))
            continue
        attachments.append(
            {
                "resolved_path": candidate["resolved_path"],
                "filename": candidate["filename"],
                "file_size": int(file_stat.st_size),
                "content_type": candidate["content_type"],
                "attachment_type": candidate["attachment_type"],
                "content_sha256": content_sha256,
                "identity": {
                    "resolved_path": candidate["resolved_path"],
                    "file_size": int(file_stat.st_size),
                    "mtime_ns": int(file_stat.st_mtime_ns),
                    "inode": int(getattr(file_stat, "st_ino", 0)),
                    "device": int(getattr(file_stat, "st_dev", 0)),
                    "content_sha256": content_sha256,
                },
            }
        )
    if warnings:
        return [], warnings
    return attachments, []


def _approved_draft_attachment_infos(plan: dict[str, Any]) -> list[dict[str, Any]]:
    private = plan.get("_private") if isinstance(plan, dict) else None
    if not isinstance(private, dict):
        return []
    attachments = private.get("attachment_infos")
    if not isinstance(attachments, list):
        return []
    return copy.deepcopy([item for item in attachments if isinstance(item, dict)])


def _draft_attachment_file_stat(path: Path) -> os.stat_result:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise IsADirectoryError(str(path))
        return file_stat
    finally:
        os.close(fd)


def _draft_attachment_file_state(path: Path, *, expected_size: int | None = None) -> tuple[os.stat_result, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise IsADirectoryError(str(path))
        if expected_size is not None and int(file_stat.st_size) != expected_size:
            raise OSError("attachment file changed during validation")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb") as source:
            fd = -1
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return file_stat, digest.hexdigest()
    finally:
        if fd >= 0:
            os.close(fd)


def _prepare_draft_attachment_copies(
    attachments: list[dict[str, Any]],
    temp_dir: Path,
) -> list[str]:
    prepared: list[str] = []
    for index, info in enumerate(attachments, start=1):
        source_path = Path(str(info["resolved_path"]))
        target_dir = temp_dir / f"attachment-{index}"
        target_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        target_path = target_dir / str(info["filename"])
        _copy_validated_draft_attachment(source_path, target_path, info)
        prepared.append(str(target_path))
    return prepared


def _copy_validated_draft_attachment(source_path: Path, target_path: Path, info: dict[str, Any]) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    source_fd = -1
    target_fd = -1
    try:
        source_fd = os.open(source_path, flags)
        source_stat = os.fstat(source_fd)
        expected = info["identity"]
        if (
            not stat.S_ISREG(source_stat.st_mode)
            or int(source_stat.st_size) != int(expected["file_size"])
            or int(source_stat.st_mtime_ns) != int(expected["mtime_ns"])
            or int(getattr(source_stat, "st_ino", 0)) != int(expected["inode"])
            or int(getattr(source_stat, "st_dev", 0)) != int(expected["device"])
        ):
            raise DraftAttachmentChangedError()
        target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            target_flags |= os.O_NOFOLLOW
        target_fd = os.open(target_path, target_flags, 0o600)
        digest = hashlib.sha256()
        with os.fdopen(source_fd, "rb") as source, os.fdopen(target_fd, "wb") as target:
            source_fd = -1
            target_fd = -1
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != str(info["content_sha256"]):
            try:
                target_path.unlink()
            except OSError:
                pass
            raise DraftAttachmentChangedError()
    except OSError as exc:
        raise DraftAttachmentChangedError() from exc
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if target_fd >= 0:
            os.close(target_fd)


def _draft_attachment_preview(
    attachments: list[dict[str, Any]],
    *,
    send_permitted: bool = False,
) -> dict[str, Any]:
    return {
        "attachment_count": len(attachments),
        "attachment_total_bytes": sum(int(info["file_size"]) for info in attachments),
        "attachment_filenames": [info["filename"] for info in attachments],
        "attachment_types": [info["attachment_type"] for info in attachments],
        "attachment_content_returned": False,
        "attachment_paths_returned": False,
        "attachment_send_permitted": bool(send_permitted),
    }


def _draft_attachment_read_back(
    attachments: list[dict[str, Any]],
    *,
    send_permitted: bool = False,
) -> dict[str, Any]:
    return {
        **_draft_attachment_preview(attachments, send_permitted=send_permitted),
        "attachments_confirmed_by_automation": True,
    }


def _extract_attachment_output_count(output: str) -> int | None:
    match = re.search(r"attachment_count:(\d+)", str(output))
    return int(match.group(1)) if match else None


def _mail_attachment_export_filename(value: str | None, metadata: dict[str, Any]) -> str:
    fallback = str(metadata.get("filename") or "").strip()
    if not fallback:
        fallback = f"attachment-{metadata.get('part_index', 'mail')}{_mail_attachment_extension(metadata)}"
    candidate = _bounded_string(value, 200).strip() if value else fallback
    name = Path(candidate.replace("\\", "/")).name
    suffix = Path(name).suffix or Path(fallback).suffix or _mail_attachment_extension(metadata)
    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    if not safe_stem:
        safe_stem = f"attachment-{metadata.get('part_index', 'mail')}"
    return f"{safe_stem[:120]}{suffix.lower()}"


def _mail_attachment_extension(metadata: dict[str, Any]) -> str:
    filename_suffix = Path(str(metadata.get("filename") or "")).suffix
    if filename_suffix:
        return filename_suffix.lower()
    content_type = str(metadata.get("content_type") or "").lower()
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


def _write_unique_export_file(directory: Path, filename: str, data: bytes) -> Path:
    first_candidate = directory / filename
    stem = first_candidate.stem
    suffix = first_candidate.suffix
    for index in range(1, 1000):
        candidate = first_candidate if index == 1 else directory / f"{stem}-{index - 1}{suffix}"
        if candidate.is_symlink():
            raise OSError("unsafe symlink export target")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(candidate, flags, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            return candidate
        except FileExistsError:
            continue
    raise OSError("could not allocate unique output path")


def _mail_attachment_export_unavailable_result(
    result: dict[str, Any] | None,
    fingerprint: str,
    code: str,
) -> dict[str, Any]:
    messages = {
        "attachments_unavailable": "Mail attachment metadata was not available through the local message file.",
        "invalid_output_dir": "Mail attachment export output path was not a directory.",
        "mail_attachment_export_failed": "Mail attachment could not be exported safely.",
        "mail_attachment_unavailable": "Mail attachment bytes are not locally available for export.",
    }
    return {
        "schema_version": 1,
        "status": "attachment_unavailable" if code == "mail_attachment_unavailable" else "error",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(),
        "result": result,
        "warnings": [_warning(code, messages.get(code, "Mail attachment export was unavailable."))],
    }


def _bounded_string(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text).strip()
    return text[:limit]


def _plan_error(warnings: list[dict[str, str]], *, privacy: dict[str, bool | str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "mail",
        "privacy": privacy or _preview_privacy(),
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
    content_inspected: bool = False,
    read_back: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_privacy = plan.get("privacy") if isinstance(plan, dict) else None
    plan_content_inspected = bool(plan_privacy.get("content_inspected")) if isinstance(plan_privacy, dict) else False
    result = {
        "schema_version": 1,
        "status": status,
        "source": "mail",
        "privacy": _mutation_privacy(content_inspected=content_inspected or plan_content_inspected),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "plan": _apply_safe_plan_preview(plan.get("preview")) if isinstance(plan, dict) else None,
        "result": None,
        "warnings": warnings,
    }
    if read_back is not None:
        result["read_back"] = read_back
        result["result_count"] = 1
    return result


def _apply_safe_plan_preview(preview: Any) -> Any:
    if not isinstance(preview, dict):
        return preview
    safe_preview = copy.deepcopy(preview)
    proposed = safe_preview.get("proposed")
    if isinstance(proposed, dict):
        proposed.pop("body_preview_text", None)
        proposed["body_preview_returned"] = False
    return safe_preview


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
        "source": "mail",
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


def _mail_apply_success(
    read_back: dict[str, Any],
    *,
    preview: dict[str, Any],
    approval_fingerprint: str,
    mutation_applied: bool,
    warnings: list[dict[str, str]],
    content_inspected: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "mail",
        "privacy": _mutation_privacy(content_inspected=content_inspected),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _normalize_draft_subject(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = re.sub(r"\s+", " ", _normalize_text(value)).strip()
    if not normalized:
        return "", _warning("missing_subject", "Mail draft creation requires a non-empty subject.")
    if not has_minimum_query_quality(normalized):
        return "", _warning("broad_subject", "Mail draft subject requires at least two letters or digits.")
    if len(normalized) > MAX_PREVIEW_SUBJECT_CHARS:
        return (
            normalized[:MAX_PREVIEW_SUBJECT_CHARS],
            _warning("subject_too_long", "Mail draft subject exceeded the maximum length."),
        )
    return normalized, None


def _normalize_draft_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = _normalize_text(value)
    if len(normalized) > MAX_DRAFT_BODY_CHARS:
        return (
            normalized[:MAX_DRAFT_BODY_CHARS],
            _warning("body_too_long", "Mail draft body exceeded the maximum length."),
        )
    return normalized, None


def _normalize_reply_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized, warning = _normalize_draft_body(value)
    if warning is not None:
        return normalized, warning
    if not normalized.strip():
        return "", _warning("missing_body_text", "Mail reply requires non-empty body_text.")
    return normalized, None


def _normalize_forward_body(value: str) -> tuple[str, dict[str, str] | None]:
    normalized, warning = _normalize_draft_body(value)
    if warning is not None:
        return normalized, warning
    if not normalized.strip():
        return "", _warning("missing_body_text", "Mail forward requires non-empty body_text.")
    return normalized, None


def _reply_subject(value: str) -> str:
    normalized = re.sub(r"\s+", " ", _normalize_text(value)).strip()
    if not normalized:
        return "Re: (no subject)"
    if re.match(r"^(re|aw|sv):", normalized, flags=re.IGNORECASE):
        return normalized[:MAX_PREVIEW_SUBJECT_CHARS]
    return f"Re: {normalized}"[:MAX_PREVIEW_SUBJECT_CHARS]


def _forward_subject(value: str) -> str:
    normalized = re.sub(r"\s+", " ", _normalize_text(value)).strip()
    if not normalized:
        return "Fwd: (no subject)"
    if re.match(r"^(fwd|fw):", normalized, flags=re.IGNORECASE):
        return normalized[:MAX_PREVIEW_SUBJECT_CHARS]
    return f"Fwd: {normalized}"[:MAX_PREVIEW_SUBJECT_CHARS]


def _normalize_recipients(
    values: list[str],
    *,
    field: str,
) -> tuple[list[str], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    normalized: list[str] = []
    seen: set[str] = set()
    if len(values) > MAX_RECIPIENTS_PER_FIELD:
        warnings.append(
            _warning(
                f"too_many_{field}_recipients",
                "Mail draft recipient lists are capped.",
            )
        )
        values = values[:MAX_RECIPIENTS_PER_FIELD]
    for value in values:
        candidate = re.sub(r"\s+", "", str(value).strip())
        if not candidate:
            continue
        if not _valid_email_address(candidate):
            warnings.append(
                _warning(
                    f"invalid_{field}_recipient",
                    "Mail draft recipients must be plain email addresses.",
                )
            )
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        normalized.append(candidate)
        seen.add(key)
    return normalized, warnings


def _valid_email_address(value: str) -> bool:
    if len(value) > 254 or any(character.isspace() for character in value):
        return False
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
            value,
        )
    )


def _find_matching_draft_content(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
) -> dict[str, Any] | None:
    return _find_matching_mailbox_content(
        subject,
        body_text,
        db_path=db_path,
        mail_root=mail_root,
        mailbox_predicate=_is_draft_mailbox,
        excluded_handles=excluded_handles,
    )


def _find_matching_draft_contents(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    return _find_matching_mailbox_contents(
        subject,
        body_text,
        db_path=db_path,
        mail_root=mail_root,
        mailbox_predicate=_is_draft_mailbox,
        excluded_handles=excluded_handles,
        candidate_limit=MAX_MAIL_READ_BACK_CANDIDATES,
        match_limit=2,
    )


def _find_matching_sent_content(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
) -> dict[str, Any] | None:
    if excluded_handles is None:
        return None
    return _find_matching_mailbox_content(
        subject,
        body_text,
        db_path=db_path,
        mail_root=mail_root,
        mailbox_predicate=_is_sent_read_back_mailbox,
        excluded_handles=excluded_handles,
        content_matcher=_normalized_sent_content_matches,
    )


def _find_matching_sent_content_with_retry(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
    attempts: int | None = None,
    retry_delay_seconds: float | None = None,
) -> dict[str, Any] | None:
    bounded_attempts = max(1, attempts if attempts is not None else MAIL_SENT_READ_BACK_ATTEMPTS)
    delay = (
        retry_delay_seconds
        if retry_delay_seconds is not None
        else MAIL_SENT_READ_BACK_DELAY_SECONDS
    )
    for attempt in range(bounded_attempts):
        read_back = _find_matching_sent_content(
            subject,
            body_text,
            db_path=db_path,
            mail_root=mail_root,
            excluded_handles=excluded_handles,
        )
        if read_back is not None:
            return read_back
        if attempt < bounded_attempts - 1 and delay > 0:
            time.sleep(delay)
    return None


def _find_matching_forward_sent_contents(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
) -> list[dict[str, Any]]:
    if excluded_handles is None:
        return []
    search = search_mail_metadata(subject, db_path=db_path, limit=MAX_MAIL_READ_BACK_CANDIDATES)
    if search.get("status") != "ok":
        return []
    matches: list[dict[str, Any]] = []
    for item in search.get("results", []):
        if item.get("subject") != subject or not _is_sent_read_back_mailbox(item.get("mailbox_name")):
            continue
        handle = item.get("handle")
        if not isinstance(handle, str):
            continue
        if handle in excluded_handles:
            continue
        content = get_mail_content(
            handle,
            db_path=db_path,
            mail_root=mail_root,
            max_chars=MAX_CONTENT_CHARS,
        )
        if content.get("status") != "ok" or not isinstance(content.get("result"), dict):
            continue
        if _normalized_sent_content_startswith(content["result"].get("content_text", ""), body_text):
            matches.append(content["result"])
            if len(matches) >= 2:
                break
    return matches


def _find_matching_forward_sent_contents_with_retry(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    excluded_handles: set[str] | None = None,
    attempts: int | None = None,
    retry_delay_seconds: float | None = None,
) -> list[dict[str, Any]]:
    bounded_attempts = max(1, attempts if attempts is not None else MAIL_SENT_READ_BACK_ATTEMPTS)
    delay = (
        retry_delay_seconds
        if retry_delay_seconds is not None
        else MAIL_SENT_READ_BACK_DELAY_SECONDS
    )
    for attempt in range(bounded_attempts):
        matches = _find_matching_forward_sent_contents(
            subject,
            body_text,
            db_path=db_path,
            mail_root=mail_root,
            excluded_handles=excluded_handles,
        )
        if matches:
            return matches
        if attempt < bounded_attempts - 1 and delay > 0:
            time.sleep(delay)
    return []


def _sent_handle_snapshot(
    subject: str,
    *,
    db_path: Path,
) -> set[str] | None:
    search = search_mail_metadata(subject, db_path=db_path, limit=50)
    if search.get("status") != "ok":
        return None
    handles: set[str] = set()
    for item in search.get("results", []):
        if item.get("subject") != subject or not _is_sent_read_back_mailbox(item.get("mailbox_name")):
            continue
        handle = item.get("handle")
        if isinstance(handle, str):
            handles.add(handle)
    return handles


def _draft_handle_snapshot(
    subject: str,
    *,
    db_path: Path,
) -> set[str] | None:
    search = search_mail_metadata(subject, db_path=db_path, limit=50)
    if search.get("status") != "ok":
        return None
    handles: set[str] = set()
    for item in search.get("results", []):
        if item.get("subject") != subject or not _is_draft_mailbox(item.get("mailbox_name")):
            continue
        handle = item.get("handle")
        if isinstance(handle, str):
            handles.add(handle)
    return handles


def _find_matching_mailbox_content(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    mailbox_predicate: Callable[[Any], bool],
    excluded_handles: set[str] | None = None,
    content_matcher: Callable[[Any, str], bool] | None = None,
) -> dict[str, Any] | None:
    matches, _truncated = _find_matching_mailbox_contents(
        subject,
        body_text,
        db_path=db_path,
        mail_root=mail_root,
        mailbox_predicate=mailbox_predicate,
        excluded_handles=excluded_handles,
        candidate_limit=50,
        match_limit=1,
        content_matcher=content_matcher,
    )
    return matches[0] if matches else None


def _find_matching_mailbox_contents(
    subject: str,
    body_text: str,
    *,
    db_path: Path,
    mail_root: Path,
    mailbox_predicate: Callable[[Any], bool],
    excluded_handles: set[str] | None = None,
    candidate_limit: int,
    match_limit: int | None = None,
    content_matcher: Callable[[Any, str], bool] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    candidates, truncated = _exact_subject_mail_candidates(subject, db_path=db_path, limit=candidate_limit)
    if candidates is None:
        return [], False
    match_content = content_matcher or _normalized_content_matches
    excluded_handles = excluded_handles or set()
    matches: list[dict[str, Any]] = []
    for item in candidates:
        if item.get("subject") != subject or not mailbox_predicate(item.get("mailbox_name")):
            continue
        handle = item.get("handle")
        if not isinstance(handle, str):
            continue
        if handle in excluded_handles:
            continue
        content = get_mail_content(
            handle,
            db_path=db_path,
            mail_root=mail_root,
            max_chars=MAX_CONTENT_CHARS,
        )
        if content.get("status") != "ok" or not isinstance(content.get("result"), dict):
            continue
        if match_content(content["result"].get("content_text", ""), body_text):
            matches.append(content["result"])
            if match_limit is not None and len(matches) >= match_limit:
                break
    return matches, truncated


def _exact_subject_mail_candidates(
    subject: str,
    *,
    db_path: Path,
    limit: int,
) -> tuple[list[dict[str, Any]], bool] | tuple[None, bool]:
    bounded_limit = max(1, limit)
    try:
        with connect_readonly(db_path) as connection:
            _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    m.ROWID AS rowid,
                    s.subject AS subject,
                    mb.url AS mailbox_url,
                    m.date_received AS date_received,
                    m.date_sent AS date_sent,
                    m.read AS read,
                    m.flagged AS flagged,
                    m.deleted AS deleted,
                    m.size AS size
                FROM messages m
                LEFT JOIN subjects s ON m.subject = s.ROWID
                LEFT JOIN mailboxes mb ON m.mailbox = mb.ROWID
                WHERE COALESCE(m.deleted, 0) = 0
                  AND s.subject = ?
                ORDER BY COALESCE(m.date_received, m.date_sent, 0) DESC
                LIMIT ?
                """,
                (subject, bounded_limit + 1),
            ).fetchall()
    except StoreUnavailableError:
        return None, False
    truncated = len(rows) > bounded_limit
    candidates = [
        _row_to_metadata(row, content_status="unknown")
        for row in rows[:bounded_limit]
        if row["subject"] is not None
    ]
    return candidates, truncated


def _is_draft_mailbox(value: Any) -> bool:
    return isinstance(value, str) and "draft" in value.casefold()


def _is_sent_mailbox(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.casefold()
    return "sent" in normalized


def _is_sent_read_back_mailbox(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.casefold().replace("-", " ").replace("_", " ").split())
    last_segment = normalized.rsplit("/", 1)[-1].strip()
    return _is_sent_mailbox(value) or last_segment in {"all mail", "allmail"}


def _mail_sent_read_back_proof(content_result: dict[str, Any], body_text: str) -> dict[str, Any]:
    return {
        "handle": content_result.get("handle"),
        "subject": content_result.get("subject"),
        "mailbox_ref": content_result.get("mailbox_ref"),
        "mailbox_name": content_result.get("mailbox_name"),
        "sent_copy_confirmed": True,
        "content_sha256": hashlib.sha256(_normalize_text(body_text).encode("utf-8")).hexdigest(),
        "content_chars": len(_normalize_text(body_text)),
        "body_returned": False,
    }


def _mail_forward_read_back_proof(content_result: dict[str, Any], body_text: str) -> dict[str, Any]:
    normalized_body = _normalize_text(body_text)
    return {
        "handle": content_result.get("handle"),
        "subject": content_result.get("subject"),
        "mailbox_ref": content_result.get("mailbox_ref"),
        "mailbox_name": content_result.get("mailbox_name"),
        "sent_copy_confirmed": True,
        "prepended_body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
        "prepended_body_chars": len(normalized_body),
        "body_returned": False,
    }


def _normalized_content_matches(value: Any, expected: str) -> bool:
    if not isinstance(value, str):
        return False
    return _normalize_text(value) == _normalize_text(expected)


def _normalized_content_startswith(value: Any, expected_prefix: str) -> bool:
    if not isinstance(value, str):
        return False
    return _normalize_text(value).startswith(_normalize_text(expected_prefix))


def _normalized_sent_content_matches(value: Any, expected: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized_value = _normalize_text(value)
    normalized_expected = _normalize_text(expected)
    return (
        normalized_value == normalized_expected
        or _strip_mail_quote_prefixes(normalized_value) == normalized_expected
    )


def _normalized_sent_content_startswith(value: Any, expected_prefix: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized_value = _normalize_text(value)
    normalized_expected = _normalize_text(expected_prefix)
    return normalized_value.startswith(normalized_expected) or _strip_mail_quote_prefixes(
        normalized_value
    ).startswith(normalized_expected)


def _strip_mail_quote_prefixes(value: str) -> str:
    lines = []
    for line in _normalize_text(value).splitlines():
        stripped = line.lstrip()
        if stripped.startswith("> "):
            lines.append(stripped[2:])
        elif stripped == ">":
            lines.append("")
        elif stripped.startswith(">"):
            lines.append(stripped[1:])
        else:
            lines.append(line)
    return _normalize_text("\n".join(lines))


def _forward_attachment_state(
    message_handle: str,
    *,
    db_path: Path,
    mail_root: Path,
    include_source_attachments: bool = False,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            _check_schema(connection)
            rowid = _resolve_mail_handle_rowid(connection, message_handle)
    except StoreUnavailableError:
        return {}, _warning(
            "source_attachment_state_unavailable",
            "Mail source attachment/non-body-part state was unavailable; forward_message cannot prove source attachments and non-body MIME parts are absent.",
        )
    if rowid is None:
        return {}, _warning(
            "source_attachment_state_unavailable",
            "Mail source attachment/non-body-part state was unavailable; forward_message cannot prove source attachments and non-body MIME parts are absent.",
        )
    message = _parse_message_for_attachment_access(mail_root, int(rowid))
    if message is None:
        return {}, _warning(
            "source_attachment_state_unavailable",
            "Mail source attachment/non-body-part state was unavailable; forward_message cannot prove source attachments and non-body MIME parts are absent.",
        )
    source_parts = _source_forward_part_metadata_list(message)
    source_part_count = len(source_parts)
    if source_part_count and not include_source_attachments:
        return {}, _warning(
            "source_has_attachments",
            "Mail forward_message refuses source messages with attachments or non-body MIME parts unless include_source_attachments is explicit.",
        )
    declared_attachment_count = sum(1 for item in source_parts if item["source_part_kind"] == "attachment")
    non_body_part_count = sum(1 for item in source_parts if item["source_part_kind"] == "non_body")
    payload = {
        "attachment_count": source_part_count,
        "source_part_count": source_part_count,
        "declared_attachment_count": declared_attachment_count,
        "non_body_part_count": non_body_part_count,
        "attachment_gate": "source_parts_forwarded_by_mail"
        if include_source_attachments
        else "no_source_attachments_or_non_body_parts",
        "source_forward_verification": SOURCE_FORWARD_VERIFICATION,
        "source_parts": source_parts if include_source_attachments else [],
    }
    return {
        **payload,
        "safe_sha256": hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
    }, None


def _source_forward_part_metadata_list(message) -> list[dict[str, Any]]:
    source_parts: list[dict[str, Any]] = []
    for part_index, part in enumerate(message.walk()):
        if part.is_multipart() or not _is_attachment_part(part):
            continue
        filename = _mail_attachment_filename(part)
        content_type = _bounded_string(part.get_content_type(), 300) or "application/octet-stream"
        raw_disposition = _bounded_string(part.get_content_disposition(), 50)
        source_part_kind = "attachment" if raw_disposition == "attachment" or bool(filename) else "non_body"
        source_parts.append(
            {
                "filename": filename,
                "content_type": content_type,
                "content_disposition": raw_disposition,
                "declared_file_size": _declared_attachment_size(part),
                "part_index": part_index,
                "attachment_type": _mail_attachment_type(content_type, filename),
                "source_part_kind": source_part_kind,
                "has_filename": bool(filename),
                "has_content_id": bool(part.get("Content-ID")),
            }
        )
    return source_parts


def _forward_source_content_state(
    target: dict[str, Any],
    *,
    mail_root: Path,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    message_path = _find_message_file(mail_root, int(target["rowid"]))
    if message_path is None:
        return {}, _warning(
            "source_content_state_unavailable",
            "Mail source content state was unavailable; forward_message cannot bind the source content.",
        )
    try:
        raw = message_path.read_bytes()
    except OSError:
        return {}, _warning(
            "source_content_state_unavailable",
            "Mail source content state was unavailable; forward_message cannot bind the source content.",
        )
    payload = {
        "emlx_sha256": hashlib.sha256(raw).hexdigest(),
        "message_id": target["message_id"],
    }
    return {
        "safe_sha256": hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
    }, None


def _apply_mail_send(
    preview: dict[str, Any],
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    sender_identity: dict[str, str] | None,
    sender_metadata: dict[str, Any] | None,
    signature_identity: dict[str, str] | None,
    signature_metadata: dict[str, Any] | None,
    template_metadata: dict[str, Any] | None,
    attachment_infos: list[dict[str, Any]],
    db_path: Path,
    mail_root: Path,
    script_runner: ScriptRunner,
    approval_fingerprint: str,
) -> dict[str, Any]:
    sent_handles_before = _sent_handle_snapshot(subject, db_path=db_path)
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-mail-") as attachment_temp_dir:
            automation_attachment_paths = _prepare_draft_attachment_copies(
                attachment_infos,
                Path(attachment_temp_dir),
            )
            automation_output = script_runner(
                _mail_send_message_script(
                    to=to,
                    cc=cc,
                    bcc=bcc,
                    subject=subject,
                    body_text=body_text,
                    sender=_sender_value(sender_identity),
                    signature_name=_signature_value(signature_identity),
                    attachment_paths=automation_attachment_paths,
                ),
                MAIL_APPLESCRIPT_TIMEOUT_SECONDS,
            )
    except DraftAttachmentChangedError:
        return _apply_error(
            [_warning("current_attachment_changed", "Mail send attachment changed after approval; re-plan before applying.")],
            plan={"preview": preview},
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("automation_timeout", "Mail send timed out through local automation.")],
            plan={"preview": preview},
            status="degraded",
        )
    except (OSError, MailAutomationError):
        return _apply_error(
            [_warning("write_error", "Mail message could not be sent safely.")],
            plan={"preview": preview},
        )

    if attachment_infos:
        automation_attachment_count = _extract_attachment_output_count(automation_output)
        if automation_attachment_count != len(attachment_infos):
            return _apply_error(
                [
                    _warning(
                        "attachment_read_back_unavailable",
                        "Mail send was accepted but attachment automation confirmation was unavailable.",
                    )
                ],
                plan={"preview": preview},
                status="partial",
                mutation_applied=True,
            )
    if sender_identity is not None and _extract_sender_output_email(automation_output) != sender_identity["email_address"]:
        return _apply_error(
            [_warning("sender_read_back_unavailable", "Mail send was accepted but selected sender read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )
    if signature_identity is not None and _extract_signature_output_name(automation_output) != signature_identity["name"]:
        return _apply_error(
            [
                _warning(
                    "signature_read_back_unavailable",
                    "Mail send was accepted but selected signature read-back was unavailable.",
                )
            ],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    read_back = _find_matching_sent_content_with_retry(
        subject,
        body_text,
        db_path=db_path,
        mail_root=mail_root,
        excluded_handles=sent_handles_before,
    )
    if read_back is None:
        return _apply_error(
            [_warning("read_back_unavailable", "Mail send was accepted but local Sent read-back was unavailable.")],
            plan={"preview": preview},
            status="partial",
            mutation_applied=True,
        )

    proof = _mail_sent_read_back_proof(read_back, body_text)
    if attachment_infos:
        proof.update(_draft_attachment_read_back(attachment_infos, send_permitted=True))
    if sender_metadata is not None:
        proof.update(
            {
                "sender_ref": sender_metadata["sender_ref"],
                "sender_selection_confirmed": True,
                "full_email_returned": False,
                "sender_string_returned": False,
            }
        )
    if signature_metadata is not None:
        proof.update(
            {
                "signature_ref": signature_metadata["signature_ref"],
                "signature_selection_confirmed": True,
                "signature_body_returned": False,
                "signature_content_returned": False,
            }
        )
    if template_metadata is not None:
        proof.update(
            {
                "template_ref": template_metadata["template_ref"],
                "template_selection_confirmed": True,
                "template_body_returned": False,
                "template_content_returned": False,
            }
        )
    return _apply_success(
        proof,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        warnings=[],
    )


def _mail_create_draft_script(
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    sender: str = "",
    signature_name: str = "",
    attachment_paths: list[str] | None = None,
) -> str:
    lines = [
        f"set draftSubject to {_applescript_string(subject)}",
        f"set draftBody to {_applescript_string(body_text)}",
        f"set draftSender to {_applescript_string(sender)}",
        f"set draftSignatureName to {_applescript_string(signature_name)}",
        'tell application "Mail"',
        "    set draftMessage to make new outgoing message with properties {subject:draftSubject, content:draftBody, visible:false}",
        "    set message signature of draftMessage to missing value",
        '    if draftSignatureName is not "" then set message signature of draftMessage to signature draftSignatureName',
        '    if draftSender is not "" then set sender of draftMessage to draftSender',
        "    tell draftMessage",
    ]
    lines.extend(_recipient_script_lines("to", to))
    lines.extend(_recipient_script_lines("cc", cc))
    lines.extend(_recipient_script_lines("bcc", bcc))
    for index, path in enumerate(attachment_paths or [], start=1):
        lines.extend(
            [
                f"        set attachmentPath{index} to {_applescript_string(path)}",
                f"        set attachmentFile{index} to POSIX file attachmentPath{index}",
                f"        make new attachment with properties {{file name:attachmentFile{index}}} at after the last paragraph",
            ]
        )
    lines.extend(
        [
            "    end tell",
            "    save draftMessage",
            "    set savedAttachmentCount to count of attachments of content of draftMessage",
            '    set resultText to "id:" & ((id of draftMessage) as text) & linefeed',
            '    if draftSender is not "" then set resultText to resultText & "sender:" & (sender of draftMessage) & linefeed',
            '    if draftSignatureName is not "" then set resultText to resultText & "signature:" & (name of message signature of draftMessage) & linefeed',
            '    set resultText to resultText & "attachment_count:" & (savedAttachmentCount as text)',
            "    return resultText",
            "end tell",
        ]
    )
    return "\n".join(lines) + "\n"


def _mail_send_message_script(
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    sender: str = "",
    signature_name: str = "",
    attachment_paths: list[str] | None = None,
) -> str:
    attachment_count = len(attachment_paths or [])
    lines = [
        f"set outboundSubject to {_applescript_string(subject)}",
        f"set outboundBody to {_applescript_string(body_text)}",
        f"set outboundSender to {_applescript_string(sender)}",
        f"set outboundSignatureName to {_applescript_string(signature_name)}",
        'tell application "Mail"',
        "    set outboundMessage to make new outgoing message with properties {subject:outboundSubject, content:outboundBody, visible:false}",
        "    set message signature of outboundMessage to missing value",
        '    if outboundSignatureName is not "" then set message signature of outboundMessage to signature outboundSignatureName',
        '    if outboundSender is not "" then set sender of outboundMessage to outboundSender',
        "    tell outboundMessage",
    ]
    lines.extend(_recipient_script_lines("to", to))
    lines.extend(_recipient_script_lines("cc", cc))
    lines.extend(_recipient_script_lines("bcc", bcc))
    lines.extend(_attachment_script_lines(attachment_paths or []))
    lines.extend(
        [
            "    end tell",
            "    set savedAttachmentCount to count of attachments of content of outboundMessage",
            f"    if savedAttachmentCount is not {attachment_count} then error \"attachment_count_mismatch\"",
            '    set resultText to "id:" & ((id of outboundMessage) as text) & linefeed',
            '    if outboundSender is not "" then set resultText to resultText & "sender:" & (sender of outboundMessage) & linefeed',
            '    if outboundSignatureName is not "" then set resultText to resultText & "signature:" & (name of message signature of outboundMessage) & linefeed',
            '    set resultText to resultText & "attachment_count:" & (savedAttachmentCount as text)',
            "    send outboundMessage",
            "    return resultText",
            "end tell",
        ]
    )
    return "\n".join(lines) + "\n"


def _mail_reply_message_script(
    *,
    account_id: str,
    mailbox_name: str,
    message_id: str,
    body_text: str,
    sender: str = "",
    signature_name: str = "",
    reply_to_all: bool = False,
    attachment_paths: list[str] | None = None,
) -> str:
    reply_all_flag = "true" if reply_to_all else "false"
    attachment_count = len(attachment_paths or [])
    lines = [
        f"set replyBody to {_applescript_string(body_text)}",
        f"set replySender to {_applescript_string(sender)}",
        f"set replySignatureName to {_applescript_string(signature_name)}",
        'tell application "Mail"',
        f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
        f"    set replyMatches to (messages of sourceBox whose message id is {_applescript_string(message_id)})",
        '    if (count of replyMatches) is not 1 then error "reply_target_not_unique"',
        "    set sourceMessage to first item of replyMatches",
        f"    set replyMessage to reply sourceMessage opening window false reply to all {reply_all_flag}",
        "    set message signature of replyMessage to missing value",
        '    if replySignatureName is not "" then set message signature of replyMessage to signature replySignatureName',
        '    if replySender is not "" then set sender of replyMessage to replySender',
        "    set content of replyMessage to replyBody",
        "    tell replyMessage",
    ]
    lines.extend(_attachment_script_lines(attachment_paths or []))
    lines.extend(
        [
            "    end tell",
            "    set savedAttachmentCount to count of attachments of content of replyMessage",
            f"    if savedAttachmentCount is not {attachment_count} then error \"attachment_count_mismatch\"",
            '    set resultText to "id:" & ((id of replyMessage) as text) & linefeed',
            '    if replySender is not "" then set resultText to resultText & "sender:" & (sender of replyMessage) & linefeed',
            '    if replySignatureName is not "" then set resultText to resultText & "signature:" & (name of message signature of replyMessage) & linefeed',
            '    set resultText to resultText & "attachment_count:" & (savedAttachmentCount as text)',
            "    send replyMessage",
            "    return resultText",
            "end tell",
        ]
    )
    return "\n".join(lines) + "\n"


def _mail_forward_message_script(
    *,
    account_id: str,
    mailbox_name: str,
    message_id: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    sender: str = "",
    signature_name: str = "",
    attachment_paths: list[str] | None = None,
    expected_source_part_count: int = 0,
) -> str:
    attachment_count = len(attachment_paths or []) + expected_source_part_count
    lines = [
        f"set forwardSubject to {_applescript_string(subject)}",
        f"set forwardBody to {_applescript_string(body_text)}",
        f"set forwardSender to {_applescript_string(sender)}",
        f"set forwardSignatureName to {_applescript_string(signature_name)}",
        'tell application "Mail"',
        f"    set sourceBox to {_mailbox_script_spec(account_id=account_id, mailbox_name=mailbox_name)}",
        f"    set forwardMatches to (messages of sourceBox whose message id is {_applescript_string(message_id)})",
        '    if (count of forwardMatches) is not 1 then error "forward_target_not_unique"',
        "    set sourceMessage to first item of forwardMatches",
        "    set forwardMessage to forward sourceMessage opening window false",
        "    set message signature of forwardMessage to missing value",
        '    if forwardSignatureName is not "" then set message signature of forwardMessage to signature forwardSignatureName',
        '    if forwardSender is not "" then set sender of forwardMessage to forwardSender',
        "    set subject of forwardMessage to forwardSubject",
        "    set content of forwardMessage to forwardBody & return & return & (content of forwardMessage)",
        "    tell forwardMessage",
    ]
    lines.extend(_recipient_script_lines("to", to))
    lines.extend(_recipient_script_lines("cc", cc))
    lines.extend(_recipient_script_lines("bcc", bcc))
    lines.extend(_attachment_script_lines(attachment_paths or []))
    lines.extend(
        [
            "    end tell",
            "    set savedAttachmentCount to count of attachments of content of forwardMessage",
            f"    if savedAttachmentCount is not {attachment_count} then error \"attachment_count_mismatch\"",
            '    set resultText to "id:" & ((id of forwardMessage) as text) & linefeed',
            '    if forwardSender is not "" then set resultText to resultText & "sender:" & (sender of forwardMessage) & linefeed',
            '    if forwardSignatureName is not "" then set resultText to resultText & "signature:" & (name of message signature of forwardMessage) & linefeed',
            '    set resultText to resultText & "attachment_count:" & (savedAttachmentCount as text)',
            "    send forwardMessage",
            "    return resultText",
            "end tell",
        ]
    )
    return "\n".join(lines) + "\n"


def _recipient_script_lines(field: str, recipients: list[str]) -> list[str]:
    if field == "to":
        class_name = "to recipient"
        collection_name = "to recipients"
    elif field == "cc":
        class_name = "cc recipient"
        collection_name = "cc recipients"
    else:
        class_name = "bcc recipient"
        collection_name = "bcc recipients"
    return [
        f"        make new {class_name} at end of {collection_name} with properties {{address:{_applescript_string(recipient)}}}"
        for recipient in recipients
    ]


def _attachment_script_lines(attachment_paths: list[str]) -> list[str]:
    lines: list[str] = []
    for index, path in enumerate(attachment_paths, start=1):
        lines.extend(
            [
                f"        set attachmentPath{index} to {_applescript_string(path)}",
                f"        set attachmentFile{index} to POSIX file attachmentPath{index}",
                f"        make new attachment with properties {{file name:attachmentFile{index}}} at after the last paragraph",
            ]
        )
    return lines


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        payload,
        _warning,
        fallback_message="Mail warning detail was redacted.",
    )


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"mail-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class MailAutomationError(RuntimeError):
    pass


class DraftAttachmentChangedError(RuntimeError):
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
        raise MailAutomationError() from None
    if completed.returncode != 0:
        raise MailAutomationError((completed.stderr or "")[:1000])
    return completed.stdout


def _mail_content_root(db_path: Path) -> Path:
    if db_path.parent.name == "MailData" and db_path.parent.parent.name.startswith("V"):
        return db_path.parent.parent
    return db_path.parent


def _message_file_rowid(filename: str) -> tuple[int, bool] | None:
    if not filename.endswith(".emlx"):
        return None
    stem = filename[: -len(".emlx")]
    partial = stem.endswith(".partial")
    if partial:
        stem = stem[: -len(".partial")]
    if not stem.isdigit():
        return None
    return int(stem), partial


def _scan_mail_message_files(
    mail_root: Path,
    *,
    only_rowid: int | None = None,
    only_rowids: set[int] | None = None,
) -> dict[int, dict[str, list[Path]]] | None:
    """One os.walk pass over the Mail tree mapping rowid -> full/partial .emlx candidates.

    Replaces the per-message ``glob("**/Messages/{rowid}.emlx")`` pattern that made every
    scan-shaped Mail operation pay a full-tree walk per row (measured ~700ms/row on a
    ~500k-entry live store vs ~1.7s for this single pass). Candidate lists are capped at
    2 entries because callers only distinguish exactly-one from anything-else.
    """
    selected_rowids = set(only_rowids) if only_rowids is not None else None
    if only_rowid is not None:
        if selected_rowids is None:
            selected_rowids = {only_rowid}
        else:
            selected_rowids.add(only_rowid)
    index: dict[int, dict[str, list[Path]]] = {}
    try:
        for dirpath, _dirnames, filenames in os.walk(mail_root):
            if os.path.basename(dirpath) != "Messages":
                continue
            for filename in filenames:
                parsed = _message_file_rowid(filename)
                if parsed is None:
                    continue
                rowid, partial = parsed
                if selected_rowids is not None and rowid not in selected_rowids:
                    continue
                entry = index.setdefault(rowid, {"full": [], "partial": []})
                bucket = entry["partial" if partial else "full"]
                if len(bucket) < 2:
                    bucket.append(Path(dirpath) / filename)
    except OSError:
        return None
    return index


def _select_message_file_candidate(
    entry: dict[str, list[Path]] | None,
) -> tuple[Path | None, str]:
    """Pick the usable message file for one rowid: exactly one full match wins,
    else exactly one partial match (status "partial"), else unavailable."""
    if entry is None:
        return None, "unavailable"
    full = entry["full"]
    partial = entry["partial"]
    if len(full) == 1:
        return full[0], "available"
    if not full and len(partial) == 1:
        return partial[0], "partial"
    return None, "unavailable"


def _find_message_file_with_status(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> tuple[Path | None, str]:
    if index is None:
        index = _scan_mail_message_files(mail_root, only_rowid=rowid)
        if index is None:
            return None, "unknown"
    return _select_message_file_candidate(index.get(rowid))


def _find_message_file(
    mail_root: Path,
    rowid: int,
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> Path | None:
    path, _status = _find_message_file_with_status(mail_root, rowid, index=index)
    return path


def _message_content_statuses(
    mail_root: Path,
    rowids: list[int],
    *,
    index: dict[int, dict[str, list[Path]]] | None = None,
) -> dict[int, str]:
    unique_rowids = set(rowids)
    if not unique_rowids:
        return {}
    if index is None:
        index = _scan_mail_message_files(mail_root)
    if index is None:
        return {rowid: "unknown" for rowid in unique_rowids}
    return {
        rowid: _select_message_file_candidate(index.get(rowid))[1]
        for rowid in unique_rowids
    }


def _mime_bytes_from_emlx(raw: bytes) -> bytes:
    first_line, separator, remainder = raw.partition(b"\n")
    if separator and first_line.strip().isdigit():
        length = int(first_line.strip())
        if 0 <= length <= len(remainder):
            return remainder[:length]
    return raw


def _extract_text_from_emlx(raw: bytes) -> str | None:
    mime_bytes = _mime_bytes_from_emlx(raw)
    message = BytesParser(policy=policy.default).parsebytes(mime_bytes)
    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        try:
            content = part.get_content()
        except (LookupError, UnicodeError, ValueError):
            continue
        if not isinstance(content, str):
            continue
        if content_type == "text/plain":
            plain_parts.append(content)
        elif content_type == "text/html":
            html_parts.append(_html_to_text(content))

    text = "\n\n".join(part.strip() for part in plain_parts if part.strip())
    if text:
        return _normalize_text(text)

    html_text = "\n\n".join(part.strip() for part in html_parts if part.strip())
    if html_text:
        return _normalize_text(html_text)
    return None


def _bounded_text(text: str, max_chars: int) -> tuple[str, bool]:
    normalized = _normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized, False
    return normalized[:max_chars], True


def _bounded_text_page(
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
