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


DEFAULT_FREEFORM_DB = (
    Path.home() / "Library/Group Containers/group.com.apple.freeform/Boards/boards.db"
)
FREEFORM_TABLES = [
    "boards",
    "boards_metadata",
    "board_items",
    "asset_references",
    "assets",
    "folders",
]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
BOARD_HANDLE_PREFIX = "freeform:board"
FOLDER_HANDLE_PREFIX = "freeform:folder"
BLOCKED_BROAD_FOLDER_QUERIES = {
    "all",
    "board",
    "boards",
    "folder",
    "folders",
    "freeform",
    "icloud",
    "library",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
        "board_content_returned": False,
        "asset_content_returned": False,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check_schema(connection) -> str:
    require_columns(
        connection,
        "boards",
        {
            "board_identifier",
            "parent_identifier",
            "data",
            "last_activity_time",
            "tombstoned",
            "unsynced_changes",
            "hide_from_recently_deleted",
            "capsule_data",
            "ck_mergeable_record_value",
        },
    )
    require_columns(
        connection,
        "boards_metadata",
        {
            "board_identifier",
            "crdt_data",
            "is_favorite",
            "enable_collaborator_cursors",
            "view_state_data",
            "unsynced_changes",
        },
    )
    require_columns(
        connection,
        "board_items",
        {
            "item_uuid",
            "board_identifier",
            "item_type",
            "common_data",
            "specific_data",
            "tombstoned",
            "unsynced_changes",
        },
    )
    require_columns(
        connection,
        "asset_references",
        {
            "referrer_identifier",
            "board_identifier",
            "referrer_asset_name",
            "asset_uuid",
            "referrer_type",
            "unsynced_changes",
        },
    )
    require_columns(
        connection,
        "assets",
        {
            "asset_uuid",
            "extension",
            "tombstone_date",
        },
    )
    require_columns(
        connection,
        "folders",
        {
            "identifier",
            "data",
            "parent_identifier",
            "title",
            "last_activity_time",
            "tombstone",
            "hide_from_recently_deleted",
            "owner_name",
            "unsynced_changes",
        },
    )
    return schema_fingerprint(connection, FREEFORM_TABLES)


def check_freeform_schema(*, db_path: Path = DEFAULT_FREEFORM_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "freeform",
            "schema_fingerprint": None,
            "tables_checked": FREEFORM_TABLES,
            "warnings": [
                _warning(
                    "freeform_schema_unavailable",
                    "Apple Freeform local schema could not be checked.",
                )
            ],
        }

    return {
        "status": "ok",
        "source": "freeform",
        "schema_fingerprint": fingerprint,
        "tables_checked": FREEFORM_TABLES,
        "warnings": [],
    }


def list_freeform_boards(
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_boards(connection, limit=bounded_limit)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "recent_board_metadata", "limit": bounded_limit},
        "results": [_board_metadata(row, fingerprint) for row in rows],
        "result_count": len(rows),
        "warnings": [],
    }


def get_freeform_board(
    handle: str,
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, BOARD_HANDLE_PREFIX):
        return _invalid_handle_result("board", detail=True)

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_boards(connection, limit=None)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    for row in rows:
        if opaque_handle_matches(handle, BOARD_HANDLE_PREFIX, fingerprint, _board_key(row)):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "freeform",
                "schema_fingerprint": fingerprint,
                "privacy": _privacy(),
                "result": _board_metadata(row, fingerprint),
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "freeform",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def search_freeform_folders(
    query: str,
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_folder_query_result()
    if not _is_specific_folder_query(query):
        return _broad_folder_query_result()

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    hex(f.identifier) AS folder_id,
                    hex(f.parent_identifier) AS parent_id,
                    f.title AS title,
                    f.last_activity_time AS last_activity_time,
                    f.tombstone AS tombstoned,
                    f.hide_from_recently_deleted AS hide_from_recently_deleted,
                    f.unsynced_changes AS unsynced_changes,
                    (
                        SELECT COUNT(*)
                        FROM boards b
                        WHERE b.parent_identifier = f.identifier
                          AND COALESCE(b.tombstoned, 0) = 0
                          AND COALESCE(b.hide_from_recently_deleted, 0) = 0
                    ) AS board_count
                FROM folders f
                WHERE COALESCE(f.tombstone, 0) = 0
                  AND COALESCE(f.hide_from_recently_deleted, 0) = 0
                  AND COALESCE(f.title, '') LIKE ? ESCAPE '\\'
                ORDER BY COALESCE(f.last_activity_time, 0) DESC,
                         COALESCE(f.title, '') ASC
                LIMIT ?
                """,
                (like_contains_pattern(query), bounded_limit),
            ).fetchall()
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "folder_title", "limit": bounded_limit},
        "results": [_folder_metadata(row, fingerprint) for row in rows],
        "result_count": len(rows),
        "warnings": [],
    }


def get_freeform_folder(
    handle: str,
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_handle_result("folder", detail=True)

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_folders(connection)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    for row in rows:
        if opaque_handle_matches(handle, FOLDER_HANDLE_PREFIX, fingerprint, _folder_key(row)):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "freeform",
                "schema_fingerprint": fingerprint,
                "privacy": _privacy(),
                "result": _folder_metadata(row, fingerprint),
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "freeform",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def list_freeform_folder_boards(
    handle: str,
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_handle_result(
            "folder",
            detail=False,
            source="freeform_folder_boards",
        )

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            folders = _select_folders(connection)
            selected_folder = None
            for folder in folders:
                if opaque_handle_matches(
                    handle, FOLDER_HANDLE_PREFIX, fingerprint, _folder_key(folder)
                ):
                    selected_folder = folder
                    break
            if selected_folder is None:
                return _not_found_folder_boards_result(fingerprint)
            rows = _select_boards(
                connection,
                limit=bounded_limit,
                parent_id_hex=_folder_key(selected_folder),
            )
    except StoreUnavailableError as exc:
        return _store_degraded_result(
            exc,
            detail=False,
            source="freeform_folder_boards",
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform_folder_boards",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "selected_folder_boards", "limit": bounded_limit},
        "folder": _folder_metadata(selected_folder, fingerprint),
        "results": [_board_metadata(row, fingerprint) for row in rows],
        "result_count": len(rows),
        "warnings": [],
    }


def list_freeform_child_folders(
    handle: str,
    *,
    db_path: Path = DEFAULT_FREEFORM_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_handle_result(
            "folder",
            detail=False,
            source="freeform_child_folders",
        )

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            folders = _select_folders(connection)
            selected_folder = None
            for folder in folders:
                if opaque_handle_matches(
                    handle, FOLDER_HANDLE_PREFIX, fingerprint, _folder_key(folder)
                ):
                    selected_folder = folder
                    break
            if selected_folder is None:
                return _not_found_child_folders_result(fingerprint)
            rows = _select_folders(
                connection,
                limit=bounded_limit,
                parent_id_hex=_folder_key(selected_folder),
            )
    except StoreUnavailableError as exc:
        return _store_degraded_result(
            exc,
            detail=False,
            source="freeform_child_folders",
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform_child_folders",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "selected_child_folders", "limit": bounded_limit},
        "folder": _folder_metadata(selected_folder, fingerprint),
        "results": [_folder_metadata(row, fingerprint) for row in rows],
        "result_count": len(rows),
        "warnings": [],
    }


def _select_boards(
    connection,
    *,
    limit: int | None,
    parent_id_hex: str | None = None,
) -> list[Any]:
    limit_clause = "" if limit is None else "LIMIT ?"
    parent_clause = "" if parent_id_hex is None else "AND hex(b.parent_identifier) = ?"
    params: tuple[Any, ...]
    if parent_id_hex is None:
        params = () if limit is None else (limit,)
    else:
        params = (parent_id_hex,) if limit is None else (parent_id_hex, limit)
    return connection.execute(
        f"""
        SELECT
            hex(b.board_identifier) AS board_id,
            hex(b.parent_identifier) AS parent_id,
            b.last_activity_time AS last_activity_time,
            b.tombstoned AS tombstoned,
            b.hide_from_recently_deleted AS hide_from_recently_deleted,
            b.unsynced_changes AS board_unsynced_changes,
            COALESCE(m.is_favorite, 0) AS is_favorite,
            COALESCE(m.enable_collaborator_cursors, 0) AS enable_collaborator_cursors,
            COALESCE(m.unsynced_changes, 0) AS metadata_unsynced_changes,
            (
                SELECT COUNT(*)
                FROM board_items bi
                WHERE bi.board_identifier = b.board_identifier
                  AND COALESCE(bi.tombstoned, 0) = 0
            ) AS item_count,
            (
                SELECT COUNT(DISTINCT ar.asset_uuid)
                FROM asset_references ar
                LEFT JOIN assets a ON a.asset_uuid = ar.asset_uuid
                WHERE ar.board_identifier = b.board_identifier
                  AND COALESCE(a.tombstone_date, 0) <= 0
            ) AS asset_reference_count
        FROM boards b
        LEFT JOIN boards_metadata m ON m.board_identifier = b.board_identifier
        WHERE COALESCE(b.tombstoned, 0) = 0
          AND COALESCE(b.hide_from_recently_deleted, 0) = 0
          {parent_clause}
        ORDER BY COALESCE(b.last_activity_time, 0) DESC
        {limit_clause}
        """,
        params,
    ).fetchall()


def _select_folders(
    connection,
    *,
    limit: int | None = None,
    parent_id_hex: str | None = None,
) -> list[Any]:
    limit_clause = "" if limit is None else "LIMIT ?"
    parent_clause = "" if parent_id_hex is None else "AND hex(f.parent_identifier) = ?"
    params: tuple[Any, ...]
    if parent_id_hex is None:
        params = () if limit is None else (limit,)
    else:
        params = (parent_id_hex,) if limit is None else (parent_id_hex, limit)
    return connection.execute(
        f"""
        SELECT
            hex(f.identifier) AS folder_id,
            hex(f.parent_identifier) AS parent_id,
            f.title AS title,
            f.last_activity_time AS last_activity_time,
            f.tombstone AS tombstoned,
            f.hide_from_recently_deleted AS hide_from_recently_deleted,
            f.unsynced_changes AS unsynced_changes,
            (
                SELECT COUNT(*)
                FROM boards b
                WHERE b.parent_identifier = f.identifier
                  AND COALESCE(b.tombstoned, 0) = 0
                  AND COALESCE(b.hide_from_recently_deleted, 0) = 0
            ) AS board_count
        FROM folders f
        WHERE COALESCE(f.tombstone, 0) = 0
          AND COALESCE(f.hide_from_recently_deleted, 0) = 0
          {parent_clause}
        ORDER BY COALESCE(f.last_activity_time, 0) DESC,
                 COALESCE(f.title, '') ASC
        {limit_clause}
        """,
        params,
    ).fetchall()


def _board_metadata(row: Any, fingerprint: str) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(BOARD_HANDLE_PREFIX, fingerprint, _board_key(row)),
        "title_status": "unavailable_without_blob_decode",
        "board_title_returned": False,
        "last_activity_at": _apple_timestamp(row["last_activity_time"]),
        "is_favorite": bool(row["is_favorite"]),
        "enable_collaborator_cursors": bool(row["enable_collaborator_cursors"]),
        "item_count": _safe_int(row["item_count"]) or 0,
        "asset_reference_count": _safe_int(row["asset_reference_count"]) or 0,
        "has_assets": (_safe_int(row["asset_reference_count"]) or 0) > 0,
        "is_deleted": bool(row["tombstoned"]),
        "hidden_from_recently_deleted": bool(row["hide_from_recently_deleted"]),
        "unsynced_changes": bool(row["board_unsynced_changes"])
        or bool(row["metadata_unsynced_changes"]),
        "board_items_returned": False,
        "board_content_returned": False,
        "asset_content_returned": False,
        "raw_identifier_returned": False,
    }


def _folder_metadata(row: Any, fingerprint: str) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(FOLDER_HANDLE_PREFIX, fingerprint, _folder_key(row)),
        "title": _bounded_text(row["title"], 300),
        "last_activity_at": _apple_timestamp(row["last_activity_time"]),
        "board_count": _safe_int(row["board_count"]) or 0,
        "is_deleted": bool(row["tombstoned"]),
        "hidden_from_recently_deleted": bool(row["hide_from_recently_deleted"]),
        "unsynced_changes": bool(row["unsynced_changes"]),
        "folder_blob_returned": False,
        "raw_identifier_returned": False,
    }


def _board_key(row: Any) -> str:
    return str(row["board_id"])


def _folder_key(row: Any) -> str:
    return str(row["folder_id"])


def _empty_folder_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "freeform",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Apple Freeform folder search requires a non-empty folder title query.",
            )
        ],
    }


def _broad_folder_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "freeform",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Apple Freeform folder search requires a specific folder title term.",
            )
        ],
    }


def _invalid_handle_result(
    kind: str,
    *,
    detail: bool,
    source: str = "freeform",
) -> dict[str, Any]:
    expected = f"{'freeform:board' if kind == 'board' else 'freeform:folder'}:v1"
    return {
        "schema_version": 1,
        "status": "error",
        "source": source,
        "privacy": _privacy(),
        "result": None if detail else None,
        "results": [] if not detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "invalid_handle",
                f"Expected {expected} opaque handle from Freeform output.",
            )
        ],
    }


def _store_degraded_result(
    _exc: StoreUnavailableError,
    *,
    detail: bool,
    source: str = "freeform",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": source,
        "privacy": _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "freeform_store_unavailable",
                "Apple Freeform local store is missing, unreadable, locked, or incompatible.",
            )
        ],
    }


def _not_found_folder_boards_result(fingerprint: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "freeform_folder_boards",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "folder": None,
        "results": [],
        "result_count": 0,
        "warnings": [],
    }


def _not_found_child_folders_result(fingerprint: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "freeform_child_folders",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "folder": None,
        "results": [],
        "result_count": 0,
        "warnings": [],
    }


def _is_specific_folder_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_FOLDER_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def _apple_timestamp(value: Any) -> str | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return (APPLE_EPOCH + timedelta(seconds=seconds)).isoformat()


def _bounded_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
