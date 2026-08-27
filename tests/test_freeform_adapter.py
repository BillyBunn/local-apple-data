from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.adapters.freeform import (
    check_freeform_schema,
    get_freeform_board,
    get_freeform_folder,
    list_freeform_child_folders,
    list_freeform_folder_boards,
    list_freeform_boards,
    search_freeform_folders,
)


def _blob(hex_pair: str) -> sqlite3.Binary:
    return sqlite3.Binary(bytes.fromhex(hex_pair * 16))


def _make_freeform_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "boards.db"
    board_id = _blob("11")
    deleted_board_id = _blob("12")
    hidden_board_id = _blob("13")
    folder_id = _blob("22")
    child_folder_id = _blob("55")
    hidden_child_folder_id = _blob("56")
    item_id = _blob("33")
    asset_id = _blob("44")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE boards (
                board_identifier BLOB PRIMARY KEY NOT NULL,
                owner_name TEXT NOT NULL,
                container_uuid BLOB NOT NULL,
                alternate_container_uuid BLOB NOT NULL,
                data BLOB,
                last_activity_time REAL,
                tombstoned INTEGER NOT NULL,
                unsynced_changes UNSIGNED BIG INT DEFAULT 0,
                ckshare_unsynced_changes INTEGER DEFAULT 0,
                sync_data BLOB,
                tombstone_date REAL,
                hide_from_recently_deleted INTEGER NOT NULL,
                ckshare_data BLOB,
                min_required_version UNSIGNED BIG INT DEFAULT 0,
                is_discardable INTEGER NOT NULL,
                min_required_version_for_good_enough_fidelity UNSIGNED BIG INT DEFAULT 0,
                min_required_version_for_full_fidelity UNSIGNED BIG INT DEFAULT 0,
                last_upgraded_version UNSIGNED BIG INT DEFAULT 0,
                last_cloudkit_fetch_version UNSIGNED BIG INT,
                capsule_data BLOB,
                ck_mergeable_record_value BLOB,
                parent_identifier BLOB,
                zone_sync_data BLOB
            );
            CREATE TABLE boards_metadata (
                board_identifier BLOB PRIMARY KEY NOT NULL,
                crdt_data BLOB NOT NULL,
                is_favorite INTEGER NOT NULL,
                enable_collaborator_cursors INTEGER NOT NULL,
                view_state_data BLOB NOT NULL,
                last_open_crashed_version UNSIGNED BIG INT,
                unsynced_changes UNSIGNED BIG INT DEFAULT 0,
                sync_data BLOB,
                min_required_version_for_full_fidelity UNSIGNED BIG INT DEFAULT 0
            );
            CREATE TABLE board_items (
                item_uuid BLOB NOT NULL,
                parent_uuid BLOB,
                board_identifier BLOB NOT NULL,
                item_type INTEGER NOT NULL,
                common_data BLOB,
                specific_data BLOB,
                tombstoned INTEGER NOT NULL,
                unsynced_changes UNSIGNED BIG INT DEFAULT 0,
                sync_data BLOB,
                min_required_version UNSIGNED BIG INT DEFAULT 0,
                object_options UNSIGNED BIG INT DEFAULT 0,
                min_required_version_for_good_enough_fidelity UNSIGNED BIG INT DEFAULT 0,
                min_required_version_for_full_fidelity UNSIGNED BIG INT DEFAULT 0,
                last_cloudkit_fetch_version UNSIGNED BIG INT,
                sub_item_type INTEGER DEFAULT 0,
                capsule_data BLOB,
                ck_mergeable_record_value BLOB,
                PRIMARY KEY (item_uuid, board_identifier)
            );
            CREATE TABLE asset_references (
                referrer_identifier BLOB NOT NULL,
                board_identifier BLOB,
                referrer_asset_name TEXT NOT NULL,
                asset_uuid BLOB NOT NULL,
                referrer_type INTEGER NOT NULL,
                unsynced_changes UNSIGNED BIG INT DEFAULT 0
            );
            CREATE TABLE assets (
                asset_uuid BLOB PRIMARY KEY NOT NULL,
                extension TEXT,
                tombstone_date REAL NOT NULL
            );
            CREATE TABLE folders (
                identifier BLOB PRIMARY KEY NOT NULL,
                data BLOB NOT NULL,
                ckshare_data BLOB,
                parent_identifier BLOB,
                min_required_version UNSIGNED BIG INT DEFAULT 0,
                min_required_version_for_good_enough_fidelity UNSIGNED BIG INT DEFAULT 0,
                min_required_version_for_full_fidelity UNSIGNED BIG INT DEFAULT 0,
                title TEXT,
                last_activity_time REAL,
                tombstone INTEGER NOT NULL DEFAULT 0,
                hide_from_recently_deleted INTEGER NOT NULL DEFAULT 0,
                owner_name TEXT NOT NULL DEFAULT '',
                unsynced_changes UNSIGNED BIG INT DEFAULT 0,
                sync_data BLOB,
                folder_options UNSIGNED BIG INT DEFAULT 0,
                zone_sync_data BLOB
            );
            """
        )
        connection.execute(
            """
            INSERT INTO folders
              (identifier, data, title, last_activity_time, tombstone,
               hide_from_recently_deleted, owner_name, unsynced_changes)
            VALUES (?, X'00', 'Synthetic Planning Folder', 802310300.0, 0, 0, '', 1)
            """,
            (folder_id,),
        )
        connection.execute(
            """
            INSERT INTO folders
              (identifier, data, parent_identifier, title, last_activity_time, tombstone,
               hide_from_recently_deleted, owner_name, unsynced_changes)
            VALUES (?, X'00', ?, 'Synthetic Child Folder', 802310280.0, 0, 0, '', 0)
            """,
            (child_folder_id, folder_id),
        )
        connection.execute(
            """
            INSERT INTO folders
              (identifier, data, parent_identifier, title, last_activity_time, tombstone,
               hide_from_recently_deleted, owner_name, unsynced_changes)
            VALUES (?, X'00', ?, 'Synthetic Hidden Child Folder', 802310270.0, 0, 1, '', 0)
            """,
            (hidden_child_folder_id, folder_id),
        )
        connection.execute(
            """
            INSERT INTO boards
              (board_identifier, owner_name, container_uuid, alternate_container_uuid,
               data, last_activity_time, tombstoned, unsynced_changes,
               hide_from_recently_deleted, is_discardable, capsule_data,
               ck_mergeable_record_value, parent_identifier)
            VALUES (?, '', X'00', X'00', X'53454E5349544956452D424F4152442D424C4F42',
                    802310400.0, 0, 1, 0, 0, X'00', X'00', ?)
            """,
            (board_id, folder_id),
        )
        connection.execute(
            """
            INSERT INTO boards
              (board_identifier, owner_name, container_uuid, alternate_container_uuid,
               data, last_activity_time, tombstoned, unsynced_changes,
               hide_from_recently_deleted, is_discardable, capsule_data,
               ck_mergeable_record_value, parent_identifier)
            VALUES (?, '', X'00', X'00', X'00', 802310200.0, 1, 0, 0, 0, X'00', X'00', ?)
            """,
            (deleted_board_id, folder_id),
        )
        connection.execute(
            """
            INSERT INTO boards
              (board_identifier, owner_name, container_uuid, alternate_container_uuid,
               data, last_activity_time, tombstoned, unsynced_changes,
               hide_from_recently_deleted, is_discardable, capsule_data,
               ck_mergeable_record_value, parent_identifier)
            VALUES (?, '', X'00', X'00', X'00', 802310250.0, 0, 0, 1, 0, X'00', X'00', ?)
            """,
            (hidden_board_id, folder_id),
        )
        connection.execute(
            """
            INSERT INTO boards_metadata
              (board_identifier, crdt_data, is_favorite, enable_collaborator_cursors,
               view_state_data, unsynced_changes)
            VALUES (?, X'53454E5349544956452D43524454', 1, 1, X'00', 0)
            """,
            (board_id,),
        )
        connection.execute(
            """
            INSERT INTO board_items
              (item_uuid, board_identifier, item_type, common_data, specific_data, tombstoned)
            VALUES (?, ?, 2, X'53454E5349544956452D434F4D4D4F4E',
                    X'53454E5349544956452D53504543', 0)
            """,
            (item_id, board_id),
        )
        connection.execute(
            "INSERT INTO assets (asset_uuid, extension, tombstone_date) VALUES (?, 'png', 0)",
            (asset_id,),
        )
        connection.execute(
            """
            INSERT INTO asset_references
              (referrer_identifier, board_identifier, referrer_asset_name, asset_uuid, referrer_type)
            VALUES (?, ?, 'synthetic-asset-name', ?, 1)
            """,
            (item_id, board_id, asset_id),
        )
    return db_path


def test_check_freeform_schema_passes_for_synthetic_store(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = check_freeform_schema(db_path=db_path)

    assert result["status"] == "ok"
    assert result["source"] == "freeform"
    assert "boards" in result["tables_checked"]


def test_list_freeform_boards_returns_metadata_only(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = list_freeform_boards(db_path=db_path)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    board = result["results"][0]
    assert board["handle"].startswith("freeform:board:v1:")
    assert board["title_status"] == "unavailable_without_blob_decode"
    assert board["board_title_returned"] is False
    assert board["board_content_returned"] is False
    assert board["board_items_returned"] is False
    assert board["asset_content_returned"] is False
    assert board["item_count"] == 1
    assert board["asset_reference_count"] == 1
    assert board["is_favorite"] is True
    assert board["raw_identifier_returned"] is False
    assert "11111111111111111111111111111111" not in str(result)
    assert "SENSITIVE-BOARD-BLOB" not in str(result)


def test_get_freeform_board_requires_opaque_handle(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = get_freeform_board("1", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_freeform_board_returns_exact_metadata(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)
    search = list_freeform_boards(db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_freeform_board(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert result["result"]["unsynced_changes"] is True
    assert result["result"]["last_activity_at"] == "2026-06-05T00:00:00+00:00"


def test_search_freeform_folders_rejects_broad_query(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = search_freeform_folders("Freeform", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_search_freeform_folders_returns_title_metadata(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = search_freeform_folders("Planning", db_path=db_path)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    folder = result["results"][0]
    assert folder["handle"].startswith("freeform:folder:v1:")
    assert folder["title"] == "Synthetic Planning Folder"
    assert folder["folder_blob_returned"] is False
    assert folder["raw_identifier_returned"] is False
    assert folder["board_count"] == 1
    assert "22222222222222222222222222222222" not in str(result)


def test_search_freeform_folders_store_degrades_safely_when_missing(tmp_path: Path) -> None:
    result = search_freeform_folders("Planning", db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["source"] == "freeform"
    assert result["warnings"][0]["code"] == "freeform_store_unavailable"


def test_get_freeform_folder_returns_exact_metadata(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)
    search = search_freeform_folders("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_freeform_folder(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert result["result"]["title"] == "Synthetic Planning Folder"
    assert result["result"]["unsynced_changes"] is True


def test_list_freeform_folder_boards_requires_opaque_handle(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = list_freeform_folder_boards("22", db_path=db_path)

    assert result["status"] == "error"
    assert result["source"] == "freeform_folder_boards"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_list_freeform_folder_boards_returns_metadata_only(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)
    search = search_freeform_folders("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = list_freeform_folder_boards(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["source"] == "freeform_folder_boards"
    assert result["folder"]["handle"] == handle
    assert result["folder"]["title"] == "Synthetic Planning Folder"
    assert result["result_count"] == 1
    board = result["results"][0]
    assert board["handle"].startswith("freeform:board:v1:")
    assert board["title_status"] == "unavailable_without_blob_decode"
    assert board["board_title_returned"] is False
    assert board["board_content_returned"] is False
    assert board["board_items_returned"] is False
    assert board["asset_content_returned"] is False
    assert board["item_count"] == 1
    assert board["asset_reference_count"] == 1
    assert board["raw_identifier_returned"] is False
    serialized = str(result)
    assert "11111111111111111111111111111111" not in serialized
    assert "12121212121212121212121212121212" not in serialized
    assert "13131313131313131313131313131313" not in serialized
    assert "22222222222222222222222222222222" not in serialized
    assert "SENSITIVE-BOARD-BLOB" not in serialized


def test_list_freeform_child_folders_requires_opaque_handle(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)

    result = list_freeform_child_folders("22", db_path=db_path)

    assert result["status"] == "error"
    assert result["source"] == "freeform_child_folders"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_list_freeform_child_folders_returns_metadata_only(tmp_path: Path) -> None:
    db_path = _make_freeform_db(tmp_path)
    search = search_freeform_folders("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = list_freeform_child_folders(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["source"] == "freeform_child_folders"
    assert result["folder"]["handle"] == handle
    assert result["result_count"] == 1
    child = result["results"][0]
    assert child["handle"].startswith("freeform:folder:v1:")
    assert child["title"] == "Synthetic Child Folder"
    assert child["board_count"] == 0
    assert child["folder_blob_returned"] is False
    assert child["raw_identifier_returned"] is False
    serialized = str(result)
    assert "22222222222222222222222222222222" not in serialized
    assert "55555555555555555555555555555555" not in serialized
    assert "56565656565656565656565656565656" not in serialized


def test_freeform_store_degrades_safely_when_missing(tmp_path: Path) -> None:
    result = list_freeform_boards(db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["source"] == "freeform"
    assert result["warnings"][0]["code"] == "freeform_store_unavailable"


def test_freeform_folder_boards_store_degrades_with_specific_source(tmp_path: Path) -> None:
    result = list_freeform_folder_boards(
        "freeform:folder:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        db_path=tmp_path / "missing.db",
    )

    assert result["status"] == "degraded"
    assert result["source"] == "freeform_folder_boards"
    assert result["warnings"][0]["code"] == "freeform_store_unavailable"


def test_freeform_child_folders_store_degrades_with_specific_source(tmp_path: Path) -> None:
    result = list_freeform_child_folders(
        "freeform:folder:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        db_path=tmp_path / "missing.db",
    )

    assert result["status"] == "degraded"
    assert result["source"] == "freeform_child_folders"
    assert result["warnings"][0]["code"] == "freeform_store_unavailable"
