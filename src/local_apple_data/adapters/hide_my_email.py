from __future__ import annotations

from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .mail import discover_mail_db_path
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_LIMIT = 20
MAX_LIMIT = 50
HANDLE_PREFIX = "hide_my_email:alias"
MAIL_TABLES = ["addresses", "messages", "recipients"]
PRIVATE_RELAY_DOMAIN = "privaterelay.appleid.com"
ICLOUD_DOMAIN = "icloud.com"
BLOCKED_BROAD_QUERIES = {
    "icloud",
    "icloudcom",
    "privaterelay",
    "privaterelayappleidcom",
    "appleid",
    "appleidcom",
    "hide",
    "hidemyemail",
    "email",
    "mail",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _detail_privacy(*, alias_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
        "alias_returned": alias_returned,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _mail_store_unavailable_warning() -> dict[str, str]:
    return _warning(
        "mail_store_unavailable",
        "Mail local store is unavailable or unreadable.",
    )


def _check_schema(connection) -> str:
    require_columns(connection, "addresses", {"ROWID", "address", "comment"})
    require_columns(
        connection,
        "messages",
        {"ROWID", "sender", "date_received", "date_sent", "deleted"},
    )
    require_columns(connection, "recipients", {"ROWID", "message", "address", "type"})
    return schema_fingerprint(connection, MAIL_TABLES)


def _resolve_db_path(db_path: Path | None) -> Path:
    return db_path if db_path is not None else discover_mail_db_path()


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "hide_my_email",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Hide My Email alias search requires a specific non-empty alias substring.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "hide_my_email",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Hide My Email alias search requires a specific alias substring, not a domain or generic term.",
            )
        ],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=4)


def search_hide_my_email_aliases(
    query: str,
    *,
    db_path: Path | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    a.ROWID AS address_id,
                    a.address AS address
                FROM addresses a
                WHERE COALESCE(a.address, '') LIKE ? ESCAPE '\\'
                ORDER BY a.ROWID DESC
                LIMIT ?
                """,
                (like_contains_pattern(query), bounded_limit * 20),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                candidate = _classify_alias(row["address"])
                if candidate is None:
                    continue
                results.append(_alias_metadata(connection, row, fingerprint, candidate))
                if len(results) >= bounded_limit:
                    break
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "hide_my_email",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "local_mail_address_alias_inference", "limit": bounded_limit},
        "authoritative_inventory": False,
        "results": results,
        "result_count": len(results),
        "warnings": [],
    }


def get_hide_my_email_alias(
    handle: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, HANDLE_PREFIX):
        return _invalid_handle_result()

    try:
        with connect_readonly(_resolve_db_path(db_path)) as connection:
            fingerprint = _check_schema(connection)
            row = _resolve_alias_row(connection, fingerprint, handle)
            if row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "hide_my_email",
                    "schema_fingerprint": fingerprint,
                    "privacy": _detail_privacy(alias_returned=False),
                    "result": None,
                    "warnings": [],
                }
            candidate = _classify_alias(row["address"])
            if candidate is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "hide_my_email",
                    "schema_fingerprint": fingerprint,
                    "privacy": _detail_privacy(alias_returned=False),
                    "result": None,
                    "warnings": [],
                }
            result = _alias_metadata(connection, row, fingerprint, candidate)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    result["alias"] = _normalize_address(row["address"])
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "hide_my_email",
        "schema_fingerprint": fingerprint,
        "privacy": _detail_privacy(alias_returned=True),
        "authoritative_inventory": False,
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def _resolve_alias_row(connection, fingerprint: str, handle: str):
    rows = connection.execute(
        """
        SELECT
            a.ROWID AS address_id,
            a.address AS address
        FROM addresses a
        WHERE COALESCE(a.address, '') != ''
        """
    ).fetchall()
    for row in rows:
        alias = _normalize_address(row["address"])
        if opaque_handle_matches(handle, HANDLE_PREFIX, fingerprint, row["address_id"], alias):
            return row
    return None


def _alias_metadata(
    connection,
    row,
    fingerprint: str,
    candidate: dict[str, str],
) -> dict[str, Any]:
    alias = _normalize_address(row["address"])
    address_id = int(row["address_id"])
    counts = _alias_counts(connection, address_id)
    return {
        "handle": make_opaque_handle(HANDLE_PREFIX, fingerprint, address_id, alias),
        "alias_preview": _mask_alias(alias),
        "domain": candidate["domain"],
        "inference_kind": candidate["inference_kind"],
        "confidence": candidate["confidence"],
        "sender_count": counts["sender_count"],
        "recipient_count": counts["recipient_count"],
        "message_count": counts["message_count"],
        "last_seen_date": counts["last_seen_date"],
        "authoritative_inventory": False,
        "provenance": "local_mail_address_metadata",
    }


def _alias_counts(connection, address_id: int) -> dict[str, Any]:
    sender_count = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM messages m
            WHERE m.sender = ?
              AND COALESCE(m.deleted, 0) = 0
            """,
            (address_id,),
        ).fetchone()["count"]
        or 0
    )
    recipient_count = int(
        connection.execute(
            """
            SELECT COUNT(DISTINCT r.message) AS count
            FROM recipients r
            LEFT JOIN messages m ON m.ROWID = r.message
            WHERE r.address = ?
              AND COALESCE(m.deleted, 0) = 0
            """,
            (address_id,),
        ).fetchone()["count"]
        or 0
    )
    message_rows = connection.execute(
        """
        SELECT DISTINCT message_id
        FROM (
            SELECT m.ROWID AS message_id
            FROM messages m
            WHERE m.sender = ?
              AND COALESCE(m.deleted, 0) = 0
            UNION
            SELECT r.message AS message_id
            FROM recipients r
            LEFT JOIN messages m ON m.ROWID = r.message
            WHERE r.address = ?
              AND COALESCE(m.deleted, 0) = 0
        )
        WHERE message_id IS NOT NULL
        """,
        (address_id, address_id),
    ).fetchall()
    message_ids = [int(row["message_id"]) for row in message_rows]
    last_seen_date = None
    if message_ids:
        placeholders = ",".join("?" for _ in message_ids)
        last_seen_row = connection.execute(
            f"""
            SELECT MAX(COALESCE(date_received, date_sent, 0)) AS last_seen
            FROM messages
            WHERE ROWID IN ({placeholders})
            """,
            message_ids,
        ).fetchone()
        last_seen_date = last_seen_row["last_seen"] if last_seen_row else None
    return {
        "sender_count": sender_count,
        "recipient_count": recipient_count,
        "message_count": len(message_ids),
        "last_seen_date": last_seen_date,
    }


def _classify_alias(value: Any) -> dict[str, str] | None:
    alias = _normalize_address(value)
    if "@" not in alias:
        return None
    local, domain = alias.rsplit("@", 1)
    if not local or not domain:
        return None
    if domain == PRIVATE_RELAY_DOMAIN:
        return {
            "domain": domain,
            "inference_kind": "sign_in_with_apple_private_relay",
            "confidence": "high",
        }
    if domain == ICLOUD_DOMAIN and _looks_like_hide_my_email_local_part(local):
        return {
            "domain": domain,
            "inference_kind": "possible_hide_my_email_icloud_alias",
            "confidence": "medium",
        }
    return None


def _looks_like_hide_my_email_local_part(local: str) -> bool:
    if len(local) < 8:
        return False
    has_separator = any(character in local for character in ("_", "-", "."))
    has_digit = any(character.isdigit() for character in local)
    has_letter = any(character.isalpha() for character in local)
    return has_separator and has_digit and has_letter


def _normalize_address(value: Any) -> str:
    return str(value or "").strip().lower()


def _mask_alias(alias: str) -> str:
    if "@" not in alias:
        return "***"
    local, domain = alias.rsplit("@", 1)
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[:2]}***@{domain}"


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "hide_my_email",
        "privacy": _detail_privacy(alias_returned=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected hide_my_email:alias:v1 opaque handle from search output.",
            )
        ],
    }


def _store_degraded_result(_exc: StoreUnavailableError, *, detail: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "hide_my_email",
        "privacy": _detail_privacy(alias_returned=False) if detail else _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [_mail_store_unavailable_warning()],
    }
