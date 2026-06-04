from __future__ import annotations

import hashlib
import re
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..handles import int_handle_matches, is_int_handle, make_int_handle
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


MAIL_ROOT_RELATIVE = Path("Library/Mail")
DEFAULT_MAIL_RELATIVE = MAIL_ROOT_RELATIVE / "V10/MailData/Envelope Index"
DEFAULT_MAIL_DB = Path.home() / DEFAULT_MAIL_RELATIVE
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000

MAIL_TABLES = ["messages", "subjects", "mailboxes"]


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
    except StoreUnavailableError as exc:
        return {
            "status": "degraded",
            "source": "mail",
            "schema_fingerprint": None,
            "tables_checked": MAIL_TABLES,
            "warnings": [{"code": "mail_schema_unavailable", "message": str(exc)}],
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


def _mailbox_metadata(raw_url: str | None) -> dict[str, str | None]:
    if not raw_url:
        return {"mailbox_name": None, "mailbox_ref": None}

    parsed = urlparse(raw_url)
    path = unquote(parsed.path).strip("/")
    mailbox_name = path.split("/")[-1] if path else "mailbox"
    mailbox_ref = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:12]
    return {"mailbox_name": mailbox_name, "mailbox_ref": f"mailbox:{mailbox_ref}"}


def _row_to_metadata(row, *, content_status: str | None = None) -> dict[str, Any]:
    mailbox = _mailbox_metadata(row["mailbox_url"])
    metadata = {
        "handle": make_int_handle("mail:message", int(row["rowid"])),
        "subject": row["subject"],
        "mailbox_name": mailbox["mailbox_name"],
        "mailbox_ref": mailbox["mailbox_ref"],
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
    limit: int = 20,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        resolved_db_path = _resolve_db_path(db_path)
        with connect_readonly(resolved_db_path) as connection:
            fingerprint = _check_schema(connection)
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
                  AND s.subject LIKE ? ESCAPE '\\'
                ORDER BY COALESCE(m.date_received, m.date_sent, 0) DESC
                LIMIT ?
                """,
                (like_contains_pattern(query), bounded_limit),
            ).fetchall()
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [{"code": "mail_store_unavailable", "message": str(exc)}],
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
        "query": {"scope": "subject", "limit": bounded_limit},
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_mail_metadata(handle: str, *, db_path: Path | None = None) -> dict[str, Any]:
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
        with connect_readonly(_resolve_db_path(db_path)) as connection:
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
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _privacy(),
            "result": None,
            "warnings": [{"code": "mail_store_unavailable", "message": str(exc)}],
        }

    return {
        "schema_version": 1,
        "status": "ok" if row else "not_found",
        "source": "mail",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": _row_to_metadata(row) if row else None,
        "warnings": [],
    }


def get_mail_content(
    handle: str,
    *,
    db_path: Path | None = None,
    mail_root: Path | None = None,
    max_chars: int = DEFAULT_CONTENT_CHARS,
) -> dict[str, Any]:
    if not is_int_handle(handle, "mail:message"):
        return _invalid_content_handle_result()

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
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
    except StoreUnavailableError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "mail",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_warning("mail_store_unavailable", str(exc))],
        }

    root = mail_root or _mail_content_root(resolved_db_path)
    message_path = _find_message_file(root, int(row["rowid"]))
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
                    "Mail content file was not available through the local store mapping.",
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

    content_text, truncated = _bounded_text(text, bounded_chars)
    result = _row_to_content_metadata(row)
    result.update(
        {
            "content_text": content_text,
            "content_chars": len(content_text),
            "truncated": truncated,
        }
    )
    warnings = []
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


def _resolve_mail_handle_rowid(connection, handle: str) -> int | None:
    rows = connection.execute(
        """
        SELECT m.ROWID AS rowid
        FROM messages m
        WHERE COALESCE(m.deleted, 0) = 0
        """
    ).fetchall()
    for row in rows:
        rowid = int(row["rowid"])
        if int_handle_matches(handle, "mail:message", rowid):
            return rowid
    return None


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


def _mail_content_root(db_path: Path) -> Path:
    if db_path.parent.name == "MailData" and db_path.parent.parent.name.startswith("V"):
        return db_path.parent.parent
    return db_path.parent


def _find_message_file(mail_root: Path, rowid: int) -> Path | None:
    matches, completed = _find_message_file_candidates(mail_root, rowid)
    if not completed:
        return None
    return matches[0] if len(matches) == 1 else None


def _message_content_statuses(mail_root: Path, rowids: list[int]) -> dict[int, str]:
    counts = {rowid: 0 for rowid in set(rowids)}
    if not counts:
        return {}
    try:
        for candidate in mail_root.glob("**/Messages/*.emlx"):
            if not candidate.is_file():
                continue
            try:
                rowid = int(candidate.stem)
            except ValueError:
                continue
            if rowid in counts:
                counts[rowid] += 1
    except OSError:
        return {rowid: "unknown" for rowid in counts}
    return {
        rowid: "available" if count == 1 else "unavailable"
        for rowid, count in counts.items()
    }


def _find_message_file_candidates(mail_root: Path, rowid: int) -> tuple[list[Path], bool]:
    matches: list[Path] = []
    try:
        for candidate in mail_root.glob(f"**/Messages/{rowid}.emlx"):
            if candidate.is_file():
                matches.append(candidate)
                if len(matches) > 1:
                    break
    except OSError:
        return [], False
    return matches, True


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
