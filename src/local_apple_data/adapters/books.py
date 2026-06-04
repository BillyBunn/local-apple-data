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


DEFAULT_BOOKS_DOCUMENTS_DIR = Path.home() / "Library/Containers/com.apple.iBooksX/Data/Documents"
DEFAULT_BOOKS_LIBRARY_DB = (
    DEFAULT_BOOKS_DOCUMENTS_DIR / "BKLibrary/BKLibrary-1-091020131601.sqlite"
)
DEFAULT_BOOKS_ANNOTATIONS_DB = (
    DEFAULT_BOOKS_DOCUMENTS_DIR / "AEAnnotation/AEAnnotation_v10312011_1727_local.sqlite"
)
BOOKS_TABLES = ["ZBKLIBRARYASSET", "ZAEANNOTATION"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
BOOK_HANDLE_PREFIX = "books:book"
ANNOTATION_HANDLE_PREFIX = "books:annotation"
BLOCKED_BROAD_QUERIES = {
    "all",
    "annotation",
    "annotations",
    "author",
    "authors",
    "book",
    "books",
    "highlight",
    "highlights",
    "library",
    "note",
    "notes",
    "pdf",
    "reading",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _content_privacy(*, annotation_text_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": annotation_text_returned,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
        "annotation_text_returned": annotation_text_returned,
        "book_text_returned": False,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check_library_schema(connection) -> str:
    require_columns(
        connection,
        "ZBKLIBRARYASSET",
        {
            "Z_PK",
            "ZASSETID",
            "ZASSETGUID",
            "ZSTOREID",
            "ZTITLE",
            "ZAUTHOR",
            "ZGENRE",
            "ZKIND",
            "ZCONTENTTYPE",
            "ZISFINISHED",
            "ZREADINGPROGRESS",
            "ZLASTOPENDATE",
            "ZPATH",
        },
    )
    return schema_fingerprint(connection, ["ZBKLIBRARYASSET"])


def _check_annotations_schema(connection) -> str:
    require_columns(
        connection,
        "ZAEANNOTATION",
        {
            "Z_PK",
            "ZANNOTATIONASSETID",
            "ZANNOTATIONDELETED",
            "ZANNOTATIONTYPE",
            "ZANNOTATIONSTYLE",
            "ZANNOTATIONCREATIONDATE",
            "ZANNOTATIONMODIFICATIONDATE",
            "ZANNOTATIONNOTE",
            "ZANNOTATIONREPRESENTATIVETEXT",
            "ZANNOTATIONSELECTEDTEXT",
            "ZANNOTATIONUUID",
        },
    )
    return schema_fingerprint(connection, ["ZAEANNOTATION"])


def check_books_schema(
    *,
    library_db_path: Path = DEFAULT_BOOKS_LIBRARY_DB,
    annotations_db_path: Path = DEFAULT_BOOKS_ANNOTATIONS_DB,
) -> dict[str, Any]:
    try:
        with connect_readonly(library_db_path) as library:
            library_fingerprint = _check_library_schema(library)
        with connect_readonly(annotations_db_path) as annotations:
            annotations_fingerprint = _check_annotations_schema(annotations)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "books",
            "schema_fingerprint": None,
            "tables_checked": BOOKS_TABLES,
            "warnings": [
                _warning(
                    "books_schema_unavailable",
                    "Apple Books local schema could not be checked.",
                )
            ],
        }

    return {
        "status": "ok",
        "source": "books",
        "schema_fingerprint": _combined_fingerprint(
            library_fingerprint,
            annotations_fingerprint,
        ),
        "tables_checked": BOOKS_TABLES,
        "warnings": [],
    }


def search_books(
    query: str,
    *,
    library_db_path: Path = DEFAULT_BOOKS_LIBRARY_DB,
    annotations_db_path: Path = DEFAULT_BOOKS_ANNOTATIONS_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(library_db_path) as library:
            library_fingerprint = _check_library_schema(library)
            rows = library.execute(
                """
                SELECT
                    Z_PK AS book_id,
                    ZASSETID AS asset_id,
                    ZASSETGUID AS asset_guid,
                    ZSTOREID AS store_id,
                    ZTITLE AS title,
                    ZAUTHOR AS author,
                    ZGENRE AS genre,
                    ZKIND AS kind,
                    ZCONTENTTYPE AS content_type,
                    ZISFINISHED AS is_finished,
                    ZREADINGPROGRESS AS reading_progress,
                    ZLASTOPENDATE AS last_opened_at,
                    ZPATH AS asset_path
                FROM ZBKLIBRARYASSET
                WHERE COALESCE(ZTITLE, '') LIKE ? ESCAPE '\\'
                   OR COALESCE(ZAUTHOR, '') LIKE ? ESCAPE '\\'
                   OR COALESCE(ZGENRE, '') LIKE ? ESCAPE '\\'
                ORDER BY COALESCE(ZLASTOPENDATE, 0) DESC, COALESCE(ZTITLE, '') ASC
                LIMIT ?
                """,
                (
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    bounded_limit,
                ),
            ).fetchall()
        annotation_counts, annotations_fingerprint = _annotation_counts(
            annotations_db_path,
            [_asset_identifier(row) for row in rows],
        )
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=False)

    fingerprint = _combined_fingerprint(library_fingerprint, annotations_fingerprint)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "books",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "book_title_author_or_genre", "limit": bounded_limit},
        "results": [
            _book_metadata(row, fingerprint, annotation_counts=annotation_counts)
            for row in rows
        ],
        "result_count": len(rows),
        "warnings": [],
    }


def get_book(
    handle: str,
    *,
    library_db_path: Path = DEFAULT_BOOKS_LIBRARY_DB,
    annotations_db_path: Path = DEFAULT_BOOKS_ANNOTATIONS_DB,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, BOOK_HANDLE_PREFIX):
        return _invalid_book_handle_result(detail=True)

    try:
        with connect_readonly(library_db_path) as library:
            library_fingerprint = _check_library_schema(library)
            rows = _select_books(library)
        annotation_counts, annotations_fingerprint = _annotation_counts(
            annotations_db_path,
            [_asset_identifier(row) for row in rows],
        )
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    fingerprint = _combined_fingerprint(library_fingerprint, annotations_fingerprint)
    for row in rows:
        if opaque_handle_matches(handle, BOOK_HANDLE_PREFIX, fingerprint, _book_key(row)):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "books",
                "schema_fingerprint": fingerprint,
                "privacy": _privacy(),
                "result": _book_metadata(row, fingerprint, annotation_counts=annotation_counts),
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "books",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def list_book_annotations(
    handle: str,
    *,
    library_db_path: Path = DEFAULT_BOOKS_LIBRARY_DB,
    annotations_db_path: Path = DEFAULT_BOOKS_ANNOTATIONS_DB,
    limit: int = DEFAULT_LIMIT,
    max_chars: int = DEFAULT_CONTENT_CHARS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, BOOK_HANDLE_PREFIX):
        return _invalid_book_handle_result(detail=True, annotations=True)

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        with connect_readonly(library_db_path) as library:
            library_fingerprint = _check_library_schema(library)
            book_rows = _select_books(library)
        with connect_readonly(annotations_db_path) as annotations:
            annotations_fingerprint = _check_annotations_schema(annotations)
            fingerprint = _combined_fingerprint(library_fingerprint, annotations_fingerprint)
            book_row = _resolve_book_row(book_rows, fingerprint, handle)
            if book_row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "books",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(annotation_text_returned=False),
                    "result": None,
                    "warnings": [],
                }
            asset_identifier = _asset_identifier(book_row)
            rows = _select_annotations(
                annotations,
                asset_identifier=asset_identifier,
                limit=bounded_limit,
            )
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True, annotations=True)

    returned: list[dict[str, Any]] = []
    remaining = bounded_chars
    truncated = False
    for row in rows:
        annotation = _annotation_metadata(row, fingerprint)
        selected_text = _clean_text(row["selected_text"])
        note_text = _clean_text(row["note_text"])
        selected_text, selected_truncated, remaining = _consume_text(selected_text, remaining)
        note_text, note_truncated, remaining = _consume_text(note_text, remaining)
        annotation.update(
            {
                "selected_text": selected_text,
                "note_text": note_text,
                "selected_text_chars": len(selected_text),
                "note_text_chars": len(note_text),
                "truncated": selected_truncated or note_truncated,
            }
        )
        truncated = truncated or annotation["truncated"]
        returned.append(annotation)
        if remaining <= 0:
            truncated = truncated or len(returned) < len(rows)
            break

    warnings = []
    if truncated:
        warnings.append(_warning("content_truncated", "Annotation text was truncated."))

    result = _book_metadata(book_row, fingerprint, annotation_counts=None)
    result.update(
        {
            "annotations": returned,
            "annotations_returned": len(returned),
            "annotation_text_chars": sum(
                annotation["selected_text_chars"] + annotation["note_text_chars"]
                for annotation in returned
            ),
            "annotation_text_truncated": truncated,
            "book_text_returned": False,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "books",
        "schema_fingerprint": fingerprint,
        "privacy": _content_privacy(annotation_text_returned=True),
        "result": result,
        "result_count": len(returned),
        "warnings": warnings,
    }


def _select_books(connection) -> list[Any]:
    return connection.execute(
        """
        SELECT
            Z_PK AS book_id,
            ZASSETID AS asset_id,
            ZASSETGUID AS asset_guid,
            ZSTOREID AS store_id,
            ZTITLE AS title,
            ZAUTHOR AS author,
            ZGENRE AS genre,
            ZKIND AS kind,
            ZCONTENTTYPE AS content_type,
            ZISFINISHED AS is_finished,
            ZREADINGPROGRESS AS reading_progress,
            ZLASTOPENDATE AS last_opened_at,
            ZPATH AS asset_path
        FROM ZBKLIBRARYASSET
        ORDER BY COALESCE(ZLASTOPENDATE, 0) DESC, COALESCE(ZTITLE, '') ASC
        """
    ).fetchall()


def _select_annotations(connection, *, asset_identifier: str, limit: int) -> list[Any]:
    if not asset_identifier:
        return []
    return connection.execute(
        """
        SELECT
            Z_PK AS annotation_id,
            ZANNOTATIONUUID AS annotation_uuid,
            ZANNOTATIONTYPE AS annotation_type,
            ZANNOTATIONSTYLE AS annotation_style,
            ZANNOTATIONCREATIONDATE AS created_at,
            ZANNOTATIONMODIFICATIONDATE AS modified_at,
            ZANNOTATIONREPRESENTATIVETEXT AS representative_text,
            ZANNOTATIONSELECTEDTEXT AS selected_text,
            ZANNOTATIONNOTE AS note_text
        FROM ZAEANNOTATION
        WHERE COALESCE(ZANNOTATIONDELETED, 0) = 0
          AND ZANNOTATIONASSETID = ?
        ORDER BY COALESCE(ZANNOTATIONMODIFICATIONDATE, ZANNOTATIONCREATIONDATE, 0) DESC
        LIMIT ?
        """,
        (asset_identifier, limit),
    ).fetchall()


def _annotation_counts(db_path: Path, asset_identifiers: list[str]) -> tuple[dict[str, int], str]:
    identifiers = [identifier for identifier in asset_identifiers if identifier]
    if not identifiers:
        with connect_readonly(db_path) as connection:
            return {}, _check_annotations_schema(connection)
    with connect_readonly(db_path) as connection:
        fingerprint = _check_annotations_schema(connection)
        placeholders = ",".join("?" for _ in identifiers)
        rows = connection.execute(
            f"""
            SELECT ZANNOTATIONASSETID AS asset_identifier, COUNT(*) AS annotation_count
            FROM ZAEANNOTATION
            WHERE COALESCE(ZANNOTATIONDELETED, 0) = 0
              AND ZANNOTATIONASSETID IN ({placeholders})
            GROUP BY ZANNOTATIONASSETID
            """,
            identifiers,
        ).fetchall()
    return {str(row["asset_identifier"]): int(row["annotation_count"] or 0) for row in rows}, fingerprint


def _resolve_book_row(rows: list[Any], fingerprint: str, handle: str) -> Any | None:
    for row in rows:
        if opaque_handle_matches(handle, BOOK_HANDLE_PREFIX, fingerprint, _book_key(row)):
            return row
    return None


def _book_metadata(
    row: Any,
    fingerprint: str,
    *,
    annotation_counts: dict[str, int] | None,
) -> dict[str, Any]:
    asset_identifier = _asset_identifier(row)
    result = {
        "handle": make_opaque_handle(BOOK_HANDLE_PREFIX, fingerprint, _book_key(row)),
        "title": _bounded_text(row["title"] or "Untitled", 300),
        "author": _bounded_text(row["author"] or "", 300),
        "genre": _bounded_text(row["genre"] or "", 120),
        "kind": _bounded_text(row["kind"] or "", 80),
        "content_type": _safe_int(row["content_type"]),
        "is_finished": bool(row["is_finished"]) if row["is_finished"] is not None else False,
        "reading_progress": _safe_float(row["reading_progress"]),
        "last_opened_at": _apple_timestamp(row["last_opened_at"]),
        "download_status": "downloaded" if bool(row["asset_path"]) else "unknown",
        "book_text_returned": False,
        "raw_identifier_returned": False,
    }
    if annotation_counts is not None:
        result["annotation_count"] = annotation_counts.get(asset_identifier, 0)
    return result


def _annotation_metadata(row: Any, fingerprint: str) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(
            ANNOTATION_HANDLE_PREFIX,
            fingerprint,
            _annotation_key(row),
        ),
        "annotation_type": _safe_int(row["annotation_type"]),
        "annotation_style": _safe_int(row["annotation_style"]),
        "created_at": _apple_timestamp(row["created_at"]),
        "modified_at": _apple_timestamp(row["modified_at"]),
        "representative_text_present": bool(_clean_text(row["representative_text"])),
        "annotation_text_returned": True,
        "raw_identifier_returned": False,
    }


def _book_key(row: Any) -> str:
    for column in ("asset_id", "asset_guid", "store_id"):
        value = _clean_text(row[column])
        if value:
            return f"{column}:{value}"
    return f"pk:{row['book_id']}"


def _asset_identifier(row: Any) -> str:
    return _clean_text(row["asset_id"]) or _clean_text(row["asset_guid"]) or _clean_text(row["store_id"])


def _annotation_key(row: Any) -> str:
    uuid = _clean_text(row["annotation_uuid"])
    return f"uuid:{uuid}" if uuid else f"pk:{row['annotation_id']}"


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "books",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Apple Books search requires a non-empty title, author, or genre query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "books",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Apple Books search requires a specific title, author, or genre term.",
            )
        ],
    }


def _invalid_book_handle_result(*, detail: bool, annotations: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "books",
        "privacy": _content_privacy(annotation_text_returned=False) if annotations else _privacy(),
        "result": None if detail else None,
        "results": [] if not detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected books:book:v1 opaque handle from search output.",
            )
        ],
    }


def _store_degraded_result(
    _exc: StoreUnavailableError,
    *,
    detail: bool,
    annotations: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "books",
        "privacy": _content_privacy(annotation_text_returned=False) if annotations else _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "books_store_unavailable",
                "Apple Books local stores are missing, unreadable, or incompatible.",
            )
        ],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def _combined_fingerprint(library_fingerprint: str, annotations_fingerprint: str) -> str:
    return f"{library_fingerprint}-{annotations_fingerprint}"


def _apple_timestamp(value: Any) -> str | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return (APPLE_EPOCH + timedelta(seconds=seconds)).isoformat()


def _consume_text(value: str, remaining: int) -> tuple[str, bool, int]:
    if not value or remaining <= 0:
        return "", bool(value), 0
    if len(value) <= remaining:
        return value, False, remaining - len(value)
    return value[:remaining], True, 0


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bounded_text(value: Any, limit: int) -> str:
    text = _clean_text(value)
    return text[:limit]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
