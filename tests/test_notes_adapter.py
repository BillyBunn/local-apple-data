from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

import local_apple_data.adapters.notes as notes_adapter
from local_apple_data.handles import make_int_handle
from local_apple_data.adapters.notes import (
    _notes_create_folder_script,
    _notes_delete_folder_script,
    _notes_delete_script,
    _notes_move_folder_script,
    _notes_move_to_folder_script,
    _notes_rename_folder_script,
    apply_notes_change,
    check_notes_schema,
    export_notes_attachment,
    get_notes_content,
    get_notes_folder,
    get_notes_metadata,
    list_notes_attachments,
    list_notes_folder_items,
    list_notes_folder_tree,
    plan_notes_change,
    search_notes_folders,
    search_notes_metadata,
)


def _make_notes_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZICCLOUDSYNCINGOBJECT (
                Z_PK INTEGER PRIMARY KEY,
                Z_ENT INTEGER,
                ZTITLE1 VARCHAR,
                ZTITLE VARCHAR,
                ZSNIPPET VARCHAR,
                ZCREATIONDATE1 TIMESTAMP,
                ZMODIFICATIONDATE1 TIMESTAMP,
                ZISPASSWORDPROTECTED INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZFOLDER INTEGER,
                ZNOTEDATA INTEGER,
                ZACCOUNT8 INTEGER,
                ZPARENT INTEGER,
                ZFOLDERTYPE INTEGER,
                ZFOLDERMODIFICATIONDATE TIMESTAMP,
                ZSMARTFOLDERQUERYJSON VARCHAR,
                ZTITLE2 VARCHAR,
                ZNAME VARCHAR,
                ZACCOUNTNAMEFORACCOUNTLISTSORTING VARCHAR,
                ZNOTE INTEGER,
                ZFILENAME VARCHAR,
                ZFILESIZE INTEGER,
                ZTYPEUTI VARCHAR,
                ZCREATIONDATE TIMESTAMP,
                ZMODIFICATIONDATE TIMESTAMP,
                ZIDENTIFIER VARCHAR,
                ZREMOTEFILEURLSTRING VARCHAR,
                ZMERGEABLEDATA BLOB,
                ZMERGEABLEDATA1 BLOB,
                ZMERGEABLEDATA2 BLOB
            );
            CREATE TABLE Z_METADATA (Z_UUID VARCHAR);
            INSERT INTO Z_METADATA VALUES ('11111111-2222-3333-4444-555555555555');
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZNAME, ZACCOUNTNAMEFORACCOUNTLISTSORTING, ZMARKEDFORDELETION)
              VALUES (39, 14, 'Synthetic Account', 'Synthetic Account', 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES
              (40, 15, 'Synthetic Projects', 39, NULL, 0, 400, NULL, 0),
              (41, 15, 'Synthetic Smart Folder', 39, NULL, 0, 401, '{"scope":"all"}', 0),
              (42, 15, 'Synthetic Archive', 39, NULL, 0, 402, NULL, 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES
              (20, 12, 'Project Alpha note', 'Alpha fallback', 'Synthetic snippet', 100, 200, 0, 0, 40, 1),
              (21, 12, 'Locked Alpha note', 'Locked fallback', 'Synthetic locked snippet', 100, 201, 1, 0, 40, 2),
              (22, 12, 'Deleted Alpha note', 'Deleted fallback', 'Synthetic deleted snippet', 100, 202, 0, 1, 40, 3);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE1, ZTITLE, ZMARKEDFORDELETION, ZNOTE, ZFILENAME,
               ZFILESIZE, ZTYPEUTI, ZCREATIONDATE, ZMODIFICATIONDATE, ZIDENTIFIER,
               ZREMOTEFILEURLSTRING, ZMERGEABLEDATA1)
              VALUES
              (130, NULL, NULL, 0, 20, 'packet.pdf', 13, 'com.adobe.pdf', 110, 210,
               'ATTACHMENT-UUID-1', NULL, X'255044462D424C4F42'),
              (131, NULL, NULL, 0, 20, 'remote.pdf', 0, 'com.adobe.pdf', 111, 211,
               'REMOTE-ATTACHMENT', 'https://example.invalid/remote.pdf', NULL),
              (132, NULL, NULL, 1, 20, 'deleted.pdf', 5, 'com.adobe.pdf', 112, 212,
               'DELETED-ATTACHMENT', NULL, X'64656C');
            """
        )


def test_search_notes_metadata_excludes_locked_and_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata("Alpha", db_path=db_path, limit=100)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["limit"] == 50
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("notes:note:v2:")
    assert result["results"][0]["handle"] != "notes:note:20"
    assert result["results"][0]["title"] == "Project Alpha note"


def test_search_notes_metadata_rejects_empty_query(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata(" ", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "empty_query"


def test_search_notes_metadata_rejects_low_quality_query(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata("%", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "broad_query"


def test_search_notes_folders_returns_exact_folder_handles(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_folders("Projects", db_path=db_path, limit=100)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["scope"] == "folder_title"
    assert result["query"]["limit"] == 50
    assert result["result_count"] == 1
    folder = result["results"][0]
    assert folder["handle"].startswith("notes:folder:v1:")
    assert folder["title"] == "Synthetic Projects"
    assert folder["kind"] == "folder"
    assert folder["supports_create"] is True
    assert folder["visible_note_count"] == 1
    assert folder["folder_content_returned"] is False
    assert folder["raw_identifier_returned"] is False


def test_get_notes_folder_by_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = get_notes_folder(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert result["result"]["title"] == "Synthetic Projects"


def test_list_notes_folder_items_returns_direct_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = list_notes_folder_items(handle, db_path=db_path, limit=10)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "selected_folder_items"
    assert result["folder"]["handle"] == handle
    assert result["result_count"] == 1
    assert result["child_folder_count"] == 1
    assert result["results"][0]["handle"].startswith("notes:note:v2:")
    assert result["results"][0]["title"] == "Project Alpha note"
    assert result["child_folders"][0]["handle"].startswith("notes:folder:v1:")
    assert result["child_folders"][0]["title"] == "Synthetic Child"
    assert result["folder_content_returned"] is False
    assert result["note_content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert "content_text" not in result["results"][0]
    assert "snippet" not in result["results"][0]


def test_list_notes_folder_items_caps_combined_direct_items(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = list_notes_folder_items(handle, db_path=db_path, limit=1)

    assert result["status"] == "ok"
    assert result["result_count"] == 0
    assert result["child_folder_count"] == 1


def test_list_notes_folder_items_rejects_invalid_and_smart_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    smart_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    invalid = list_notes_folder_items("notes:folder:41", db_path=db_path)
    smart = list_notes_folder_items(smart_handle, db_path=db_path)

    assert invalid["status"] == "error"
    assert invalid["warnings"][0]["code"] == "invalid_handle"
    assert invalid["result_count"] == 0
    assert invalid["child_folder_count"] == 0
    assert smart["status"] == "error"
    assert smart["warnings"][0]["code"] == "unsupported_smart_folder"
    assert smart["folder"]["kind"] == "smart_folder"
    assert smart["result_count"] == 0
    assert smart["child_folder_count"] == 0


def test_list_notes_folder_tree_returns_bounded_folder_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path, folder_id=43, title="Synthetic Child")
    _insert_empty_child_folder(db_path, folder_id=44, title="Synthetic Grandchild", parent_id=43)
    handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = list_notes_folder_tree(handle, db_path=db_path, depth=2, limit=10)

    assert result["status"] == "ok"
    assert result["query"] == {
        "scope": "selected_folder_tree",
        "limit": 10,
        "max_depth": 2,
        "recursive": True,
    }
    assert result["folder"]["handle"] == handle
    assert result["result_count"] == 2
    assert [item["title"] for item in result["results"]] == [
        "Synthetic Child",
        "Synthetic Grandchild",
    ]
    assert result["results"][0]["parent_handle"] == handle
    assert result["results"][0]["tree_depth"] == 1
    assert result["results"][1]["parent_handle"] == result["results"][0]["handle"]
    assert result["results"][1]["tree_depth"] == 2
    assert result["folder_content_returned"] is False
    assert result["note_content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert "snippet" not in result["results"][0]
    assert "folder_id" not in result["results"][0]


def test_list_notes_folder_tree_caps_depth_and_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path, folder_id=43, title="Synthetic Child")
    _insert_empty_child_folder(db_path, folder_id=44, title="Synthetic Grandchild", parent_id=43)
    handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    shallow = list_notes_folder_tree(handle, db_path=db_path, depth=1, limit=10)
    capped = list_notes_folder_tree(handle, db_path=db_path, depth=5, limit=1)

    assert shallow["status"] == "ok"
    assert shallow["query"]["max_depth"] == 1
    assert shallow["result_count"] == 1
    assert shallow["results"][0]["title"] == "Synthetic Child"
    assert capped["status"] == "ok"
    assert capped["query"]["max_depth"] == 3
    assert capped["query"]["limit"] == 1
    assert capped["result_count"] == 1
    assert capped["warnings"][0]["code"] == "result_truncated"


def test_list_notes_folder_tree_rejects_invalid_and_smart_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    smart_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    invalid = list_notes_folder_tree("notes:folder:41", db_path=db_path)
    smart = list_notes_folder_tree(smart_handle, db_path=db_path)

    assert invalid["status"] == "error"
    assert invalid["warnings"][0]["code"] == "invalid_handle"
    assert invalid["result_count"] == 0
    assert smart["status"] == "error"
    assert smart["warnings"][0]["code"] == "unsupported_smart_folder"
    assert smart["folder"]["kind"] == "smart_folder"
    assert smart["result_count"] == 0


def test_get_notes_folder_rejects_legacy_or_note_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_folder(note_handle, db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_notes_metadata_by_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Project Alpha note"
    assert result["result"]["password_protected"] is False


def test_get_notes_metadata_does_not_return_locked_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 21)

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_notes_metadata_does_not_return_deleted_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 22)

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_notes_metadata_rejects_guessable_legacy_id(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = get_notes_metadata("notes:note:20", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_notes_content_by_handle_strips_html_and_bounds(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    def runner(script: str, timeout: float) -> str:
        assert "x-coredata://" in script
        assert "ICNote/p20" in script
        assert timeout == 10.0
        return "<html><body><h1>Project Alpha note</h1><p>Line one<br>Line two</p></body></html>"

    result = get_notes_content(handle, db_path=db_path, max_chars=4000, script_runner=runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "content"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["content_text"] == "Project Alpha note\nLine one\nLine two"
    assert result["result"]["content_chars"] == len(result["result"]["content_text"])
    assert result["result"]["content_offset"] == 0
    assert result["result"]["content_total_chars"] == len(result["result"]["content_text"])
    assert result["result"]["next_offset"] is None
    assert result["result"]["truncated"] is False


def test_get_notes_content_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    def runner(_script: str, _timeout: float) -> str:
        raise OSError("permission denied for /private/local/notes-content")

    result = get_notes_content(handle, db_path=db_path, script_runner=runner)

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "read_error"
    assert "permission denied" not in str(result)
    assert "/private/local/notes-content" not in str(result)


def test_get_notes_content_truncates(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=8,
        script_runner=lambda _script, _timeout: "<p>abcdefghijklmnop</p>",
    )

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "abcdefgh"
    assert result["result"]["content_sha256"] == hashlib.sha256(
        "abcdefghijklmnop".encode("utf-8")
    ).hexdigest()
    assert result["result"]["content_offset"] == 0
    assert result["result"]["content_total_chars"] == 16
    assert result["result"]["next_offset"] == 8
    assert result["result"]["truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_get_notes_content_supports_offset_for_long_notes(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=5,
        offset=5,
        script_runner=lambda _script, _timeout: "<p>abcdefghijklmnop</p>",
    )

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "fghij"
    assert result["result"]["content_chars"] == 5
    assert result["result"]["content_offset"] == 5
    assert result["result"]["content_total_chars"] == 16
    assert result["result"]["next_offset"] == 10
    assert result["result"]["truncated"] is True


def _make_notes_media_file(root: Path, uuid: str, filename: str, data: bytes) -> Path:
    path = root / "Accounts" / "LocalAccount" / "Media" / uuid / "Files" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_list_notes_attachments_returns_exact_attachment_handles(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    media_root = tmp_path / "notes-container"
    _make_notes_db(db_path)
    _make_notes_media_file(media_root, "ATTACHMENT-UUID-1", "packet.pdf", b"%PDF-MEDIA")
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = list_notes_attachments(handle, db_path=db_path, notes_container=media_root)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["result_count"] == 2
    attachment = result["results"][0]
    assert attachment["handle"].startswith("notes:attachment:v1:")
    assert attachment["note_handle"] == handle
    assert attachment["filename"] == "remote.pdf"
    assert attachment["attachment_content_returned"] is False
    assert result["results"][1]["filename"] == "packet.pdf"
    assert result["results"][1]["attachment_type"] == "document"
    assert result["results"][1]["media_status"] == "available"
    assert result["results"][1]["blob_status"] == "available"


def test_list_notes_attachments_rejects_bad_note_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = list_notes_attachments("notes:note:20", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_export_notes_attachment_copies_media_file(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    media_root = tmp_path / "notes-container"
    output_dir = tmp_path / "exports"
    _make_notes_db(db_path)
    source = _make_notes_media_file(
        media_root,
        "ATTACHMENT-UUID-1",
        "packet.pdf",
        b"%PDF-MEDIA",
    )
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    listing = list_notes_attachments(note_handle, db_path=db_path, notes_container=media_root)
    attachment = next(item for item in listing["results"] if item["filename"] == "packet.pdf")

    result = export_notes_attachment(
        attachment["handle"],
        db_path=db_path,
        notes_container=media_root,
        output_dir=output_dir,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "export"
    assert result["privacy"]["content_exported"] is True
    assert result["result"]["attachment_content_returned"] is False
    assert result["result"]["attachment_content_exported"] is True
    assert result["result"]["exported_filename"] == "packet.pdf"
    exported = Path(result["result"]["exported_path"])
    assert exported.read_bytes() == source.read_bytes()
    assert str(source) not in str(result)


def test_export_notes_attachment_falls_back_to_blob(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    media_root = tmp_path / "notes-container"
    output_dir = tmp_path / "exports"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    listing = list_notes_attachments(note_handle, db_path=db_path, notes_container=media_root)
    attachment = next(item for item in listing["results"] if item["filename"] == "packet.pdf")

    result = export_notes_attachment(
        attachment["handle"],
        db_path=db_path,
        notes_container=media_root,
        output_dir=output_dir,
        filename="../unsafe name.pdf",
    )

    assert result["status"] == "ok"
    assert result["result"]["exported_filename"] == "unsafe-name.pdf"
    assert Path(result["result"]["exported_path"]).read_bytes() == b"%PDF-BLOB"


def test_export_notes_attachment_rejects_bad_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = export_notes_attachment(
        "notes:attachment:30",
        db_path=db_path,
        output_dir=tmp_path,
    )

    assert result["status"] == "error"
    assert result["privacy"]["content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_export_notes_attachment_reports_unavailable_for_remote_only(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    media_root = tmp_path / "notes-container"
    output_dir = tmp_path / "exports"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    listing = list_notes_attachments(note_handle, db_path=db_path, notes_container=media_root)
    attachment = next(item for item in listing["results"] if item["filename"] == "remote.pdf")

    result = export_notes_attachment(
        attachment["handle"],
        db_path=db_path,
        notes_container=media_root,
        output_dir=output_dir,
    )

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_exported"] is False
    assert result["result"]["attachment_content_exported"] is False
    assert result["result"]["remote_status"] == "remote_reference"
    assert result["warnings"][0]["code"] == "notes_attachment_unavailable"


def _notes_token(plan: dict) -> str:
    return "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def _insert_empty_child_folder(
    db_path: Path,
    *,
    folder_id: int = 43,
    title: str = "Synthetic Child",
    parent_id: int = 40,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (?, 15, ?, 39, ?, 0, 403, NULL, 0)
            """,
            (folder_id, title, parent_id),
        )


def test_plan_notes_change_create_returns_preview_only() -> None:
    result = plan_notes_change(
        "create",
        title="Synthetic planning note",
        body_text="Line one\nLine two",
    )

    assert result["status"] == "ok"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "create"
    assert preview["target"] == {"account": "default", "folder": "default"}
    assert preview["proposed"]["title"] == "Synthetic planning note"
    assert preview["proposed"]["body_chars"] == 17
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_create_accepts_exact_folder_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "create",
        title="Synthetic folder note",
        folder_handle=folder_handle,
        body_text="Folder body",
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["target"] == {
        "folder_handle": folder_handle,
        "folder_title": "Synthetic Projects",
        "folder_kind": "folder",
    }
    assert preview["proposed"]["title"] == "Synthetic folder note"


def test_plan_notes_change_create_rejects_smart_folder_target(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "create",
        title="Synthetic folder note",
        folder_handle=folder_handle,
        body_text="Folder body",
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_smart_folder"


def test_plan_notes_change_create_folder_requires_exact_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=folder_handle,
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "create_folder"
    assert preview["target"] == {
        "parent_folder_handle": folder_handle,
        "parent_folder_title": "Synthetic Projects",
        "parent_folder_kind": "folder",
    }
    assert preview["proposed"]["kind"] == "folder"
    assert preview["proposed"]["title"] == "Synthetic Child"
    assert preview["proposed"]["folder_content_returned"] is False
    assert preview["proposed"]["note_content_returned"] is False


def test_plan_notes_change_create_folder_rejects_body_note_target_and_smart_parent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    smart_folder_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    missing_parent = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        db_path=db_path,
    )
    assert missing_parent["status"] == "error"
    assert missing_parent["warnings"][0]["code"] == "invalid_folder_handle"

    unexpected_note_target = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        handle=note_handle,
        expected_current_sha256="a" * 64,
        folder_handle=smart_folder_handle,
        body_text="body is not allowed",
        db_path=db_path,
    )
    codes = {warning["code"] for warning in unexpected_note_target["warnings"]}
    assert "unexpected_folder_create_target" in codes
    assert "unexpected_body" in codes
    assert "unsupported_smart_folder" in codes


def test_plan_notes_change_rename_folder_returns_exact_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "rename_folder"
    assert preview["target"]["folder_handle"] == folder_handle
    assert len(preview["target"]["expected_current_sha256"]) == 64
    assert preview["proposed"]["format"] == "folder_rename"
    assert preview["proposed"]["title"] == "Synthetic Renamed Projects"
    assert preview["proposed"]["folder_content_returned"] is False
    assert preview["proposed"]["note_content_returned"] is False
    assert preview["proposed"]["delete"] == "blocked"
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_rename_folder_rejects_bad_targets(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    smart_folder_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        handle=note_handle,
        folder_handle=smart_folder_handle,
        body_text="body is not allowed",
        db_path=db_path,
    )

    assert result["status"] == "error"
    codes = {warning["code"] for warning in result["warnings"]}
    assert "unexpected_folder_rename_target" in codes
    assert "unexpected_body" in codes
    assert "unsupported_smart_folder" in codes


def test_plan_notes_change_delete_folder_returns_exact_empty_child_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "delete_folder"
    assert preview["target"]["folder_handle"] == folder_handle
    assert len(preview["target"]["expected_current_sha256"]) == 64
    assert preview["proposed"]["format"] == "folder_delete"
    assert preview["proposed"]["folder_title"] == "Synthetic Child"
    assert preview["proposed"]["delete"] == "approved_exact_empty_child_folder"
    assert preview["proposed"]["empty_folder_required"] is True
    assert preview["proposed"]["recursive_delete"] == "blocked"
    assert preview["proposed"]["note_delete"] == "blocked"
    assert preview["proposed"]["folder_content_returned"] is False
    assert preview["proposed"]["note_content_returned"] is False


def test_plan_notes_change_delete_folder_rejects_note_smart_root_and_non_empty_targets(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    note_handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    smart_folder_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]
    root_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    _insert_empty_child_folder(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES (30, 12, 'Synthetic child note', 'Synthetic child note',
                      'Synthetic snippet', 300, 300, 0, 0, 43, 4)
            """
        )
    non_empty_folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]

    bad_target = plan_notes_change(
        "delete-folder",
        title="should not be here",
        handle=note_handle,
        folder_handle=smart_folder_handle,
        body_text="body is not allowed",
        db_path=db_path,
    )
    root_result = plan_notes_change("delete-folder", folder_handle=root_folder_handle, db_path=db_path)
    non_empty_result = plan_notes_change(
        "delete-folder",
        folder_handle=non_empty_folder_handle,
        db_path=db_path,
    )

    assert bad_target["status"] == "error"
    codes = {warning["code"] for warning in bad_target["warnings"]}
    assert "unexpected_folder_delete_target" in codes
    assert "unexpected_title" in codes
    assert "unexpected_body" in codes
    assert "unsupported_smart_folder" in codes
    assert root_result["status"] == "error"
    assert root_result["warnings"][0]["code"] == "root_folder_delete_blocked"
    assert non_empty_result["status"] == "error"
    assert non_empty_result["warnings"][0]["code"] == "folder_not_empty"


def test_plan_notes_change_delete_folder_rejects_child_folders(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path, folder_id=43, title="Synthetic Parent Child")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (44, 15, 'Synthetic Nested Child', 39, 43, 0, 404, NULL, 0)
            """
        )
    folder_handle = search_notes_folders("Parent Child", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "folder_not_empty"


def test_plan_notes_change_move_folder_returns_exact_empty_child_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "move_folder"
    assert preview["target"]["folder_handle"] == folder_handle
    assert preview["target"]["target_folder_handle"] == target_folder_handle
    assert preview["target"]["expected_current_sha256"] == current_sha
    assert preview["proposed"]["format"] == "folder_move"
    assert preview["proposed"]["folder_title"] == "Synthetic Child"
    assert preview["proposed"]["target_folder_title"] == "Synthetic Archive"
    assert preview["proposed"]["move"] == "approved_exact_empty_child_folder"
    assert preview["proposed"]["empty_folder_required"] is True
    assert preview["proposed"]["recursive_move"] == "blocked"
    assert preview["proposed"]["note_move"] == "blocked"
    assert preview["proposed"]["folder_content_returned"] is False
    assert preview["proposed"]["note_content_returned"] is False


def test_plan_notes_change_move_folder_requires_hash_source_and_target() -> None:
    result = plan_notes_change("move-folder")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_folder_handle",
        "invalid_target_folder_handle",
        "missing_required_field",
    }


def test_plan_notes_change_move_folder_rejects_unsafe_targets(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    child_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    smart_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]
    projects_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    archive_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    child_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    smart_sha = hashlib.sha256("Synthetic Smart Folder".encode("utf-8")).hexdigest()
    archive_sha = hashlib.sha256("Synthetic Archive".encode("utf-8")).hexdigest()

    smart_result = plan_notes_change(
        "move-folder",
        folder_handle=smart_handle,
        target_folder_handle=archive_handle,
        expected_current_sha256=smart_sha,
        db_path=db_path,
    )
    root_result = plan_notes_change(
        "move-folder",
        folder_handle=archive_handle,
        target_folder_handle=projects_handle,
        expected_current_sha256=archive_sha,
        db_path=db_path,
    )
    noop_result = plan_notes_change(
        "move-folder",
        folder_handle=child_handle,
        target_folder_handle=projects_handle,
        expected_current_sha256=child_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES (30, 12, 'Synthetic child note', 'Synthetic child note',
                      'Synthetic snippet', 300, 300, 0, 0, 43, 4)
            """
        )
    non_empty_result = plan_notes_change(
        "move-folder",
        folder_handle=child_handle,
        target_folder_handle=archive_handle,
        expected_current_sha256=child_sha,
        db_path=db_path,
    )

    assert smart_result["status"] == "error"
    assert smart_result["warnings"][0]["code"] == "unsupported_smart_folder"
    assert root_result["status"] == "error"
    assert root_result["warnings"][0]["code"] == "root_folder_move_blocked"
    assert noop_result["status"] == "error"
    assert noop_result["warnings"][0]["code"] == "already_in_target_folder"
    assert non_empty_result["status"] == "error"
    assert non_empty_result["warnings"][0]["code"] == "folder_not_empty"


def test_plan_notes_change_move_folder_rejects_target_smart_cross_account_and_stale_hash(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZNAME, ZACCOUNTNAMEFORACCOUNTLISTSORTING, ZMARKEDFORDELETION)
              VALUES (50, 14, 'Synthetic Other Account', 'Synthetic Other Account', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (51, 15, 'Synthetic Other Account Target', 50, NULL, 0, 451, NULL, 0)
            """
        )
    child_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    smart_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]
    other_account_handle = search_notes_folders("Other Account Target", db_path=db_path)["results"][0]["handle"]
    archive_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    child_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()

    smart_target_result = plan_notes_change(
        "move-folder",
        folder_handle=child_handle,
        target_folder_handle=smart_handle,
        expected_current_sha256=child_sha,
        db_path=db_path,
    )
    cross_account_result = plan_notes_change(
        "move-folder",
        folder_handle=child_handle,
        target_folder_handle=other_account_handle,
        expected_current_sha256=child_sha,
        db_path=db_path,
    )
    stale_hash_result = plan_notes_change(
        "move-folder",
        folder_handle=child_handle,
        target_folder_handle=archive_handle,
        expected_current_sha256="0" * 64,
        db_path=db_path,
    )

    assert smart_target_result["status"] == "error"
    assert smart_target_result["warnings"][0]["code"] == "unsupported_smart_folder"
    assert cross_account_result["status"] == "error"
    assert cross_account_result["warnings"][0]["code"] == "cross_account_move_blocked"
    assert stale_hash_result["status"] == "error"
    assert stale_hash_result["warnings"][0]["code"] == "current_folder_changed"


def test_plan_notes_change_append_text_returns_exact_handle_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "append_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["append_chars"] == 13
    assert preview["proposed"]["overwrite"] == "blocked"
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_replace_text_returns_exact_handle_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Project Alpha note\nReplacement body",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "replace_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["format"] == "plaintext_replace"
    assert preview["proposed"]["replacement_chars"] == 35
    assert preview["proposed"]["delete"] == "blocked"
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_delete_returns_exact_handle_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "delete"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["format"] == "note_delete"
    assert preview["proposed"]["delete"] == "approved_exact_handle"
    assert preview["proposed"]["read_back"] == "absence_required"
    assert preview["proposed"]["body_returned"] is False
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_move_to_folder_returns_exact_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "move_to_folder"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_current_sha256"] == current_sha
    assert preview["target"]["target_folder_handle"] == folder_handle
    assert preview["proposed"]["format"] == "note_move"
    assert preview["proposed"]["move"] == "approved_exact_folder"
    assert preview["proposed"]["target_folder_title"] == "Synthetic Archive"
    assert preview["proposed"]["same_account_required"] is True
    assert preview["proposed"]["body_returned"] is False
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_requires_title() -> None:
    result = plan_notes_change("create", title=" ", body_text="Body")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_title"


def test_plan_notes_change_append_text_requires_hash_and_handle() -> None:
    result = plan_notes_change("append-text", body_text="Body")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_handle",
        "missing_required_field",
    }


def test_plan_notes_change_replace_text_requires_hash_and_handle() -> None:
    result = plan_notes_change("replace-text", body_text="Replacement")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_handle",
        "missing_required_field",
    }


def test_plan_notes_change_delete_requires_hash_and_handle() -> None:
    result = plan_notes_change("delete")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_handle",
        "missing_required_field",
    }


def test_plan_notes_change_move_to_folder_requires_hash_note_and_folder() -> None:
    result = plan_notes_change("move-to-folder")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_handle",
        "invalid_folder_handle",
        "missing_required_field",
    }


def test_plan_notes_change_move_to_folder_rejects_smart_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()
    folder_handle = search_notes_folders("Smart", db_path=db_path)["results"][0]["handle"]

    result = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_smart_folder"


def test_plan_notes_change_delete_rejects_body_text(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Delete this.",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_body"


def test_plan_notes_change_move_to_folder_rejects_body_text(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        body_text="No body accepted.",
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_body"


def test_apply_notes_change_requires_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change("create", title="Synthetic create note", body_text="Body")

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Body",
        approval_token=_notes_token(plan),
        confirm_apply=False,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_notes_change_rejects_wrong_approval_token(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Body",
        approval_token="notes-apply:v1:bad",
        confirm_apply=True,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_notes_change_creates_note_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "make new note" in script:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO ZICCLOUDSYNCINGOBJECT
                      (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
                       ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
                      VALUES (30, 'Synthetic create note', 'Synthetic create note',
                              'Created body', 300, 300, 0, 0, 4)
                    """
                )
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p30"
        assert "ICNote/p30" in script
        return "<h1>Synthetic create note</h1><p>Created body</p>"

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["title"] == "Synthetic create note"
    assert result["read_back"]["content_text"] == "Synthetic create note\nCreated body"


def test_apply_notes_change_creates_note_in_exact_folder_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create",
        title="Synthetic folder create note",
        folder_handle=folder_handle,
        body_text="Created body",
        db_path=db_path,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "make new note" in script:
            assert "ICFolder/p40" in script
            assert "account \"" not in script
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO ZICCLOUDSYNCINGOBJECT
                      (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1,
                       ZMODIFICATIONDATE1, ZISPASSWORDPROTECTED, ZMARKEDFORDELETION,
                       ZFOLDER, ZNOTEDATA)
                      VALUES (30, 12, 'Synthetic folder create note',
                              'Synthetic folder create note', 'Created body',
                              300, 300, 0, 0, 40, 4)
                    """
                )
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p30"
        assert "ICNote/p30" in script
        return "<h1>Synthetic folder create note</h1><p>Created body</p>"

    result = apply_notes_change(
        "create",
        title="Synthetic folder create note",
        folder_handle=folder_handle,
        body_text="Created body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["title"] == "Synthetic folder create note"
    assert result["read_back"]["content_text"] == "Synthetic folder create note\nCreated body"


def test_apply_notes_change_creates_child_folder_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "make new folder at targetFolder" in script
        assert "ICFolder/p40" in script
        assert "make new note" not in script
        assert "delete " not in script.lower()
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ZICCLOUDSYNCINGOBJECT
                  (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
                   ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
                  VALUES (43, 15, 'Synthetic Child', 39, 40, 0, 403, NULL, 0)
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43"

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["title"] == "Synthetic Child"
    assert result["read_back"]["handle"].startswith("notes:folder:v1:")
    assert result["read_back"]["parent_folder_handle"] == parent_handle
    assert result["read_back"]["parent_folder_confirmed"] is True
    assert result["read_back"]["folder_content_returned"] is False
    assert result["read_back"]["note_content_returned"] is False
    assert result["read_back"]["raw_identifier_returned"] is False


def test_apply_notes_change_create_folder_rejects_wrong_returned_folder_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ZICCLOUDSYNCINGOBJECT
                  (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
                   ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
                  VALUES (43, 15, 'Wrong Child', 39, 40, 0, 403, NULL, 0)
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43"

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_notes_change_create_folder_rejects_returned_smart_folder_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ZICCLOUDSYNCINGOBJECT
                  (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
                   ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
                  VALUES (43, 15, 'Synthetic Child', 39, 40, 0, 403, '{"scope":"all"}', 0)
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43"

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_notes_change_create_folder_is_idempotent_for_existing_child(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (43, 15, 'Synthetic Child', 39, 40, 0, 403, NULL, 0)
            """
        )
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for an existing child folder")

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["parent_folder_confirmed"] is True


def test_apply_notes_change_create_folder_ignores_existing_smart_child(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (43, 15, 'Synthetic Child', 39, 40, 0, 403, '{"scope":"all"}', 0)
            """
        )
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ZICCLOUDSYNCINGOBJECT
                  (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
                   ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
                  VALUES (44, 15, 'Synthetic Child', 39, 40, 0, 404, NULL, 0)
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p44"

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["parent_folder_confirmed"] is True
    assert result["read_back"]["kind"] == "folder"


def test_apply_notes_change_create_folder_requires_parent_readback(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    parent_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ZICCLOUDSYNCINGOBJECT
                  (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
                   ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
                  VALUES (43, 15, 'Synthetic Child', 39, 42, 0, 403, NULL, 0)
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43"

    result = apply_notes_change(
        "create-folder",
        title="Synthetic Child",
        folder_handle=parent_handle,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_apply_notes_change_renames_folder_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        db_path=db_path,
    )
    expected_sha = plan["preview"]["target"]["expected_current_sha256"]

    def runner(script: str, _timeout: float) -> str:
        assert "set name of targetFolder to newTitle" in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                UPDATE ZICCLOUDSYNCINGOBJECT
                   SET ZTITLE2 = 'Synthetic Renamed Projects',
                       ZFOLDERMODIFICATIONDATE = 405
                 WHERE Z_PK = 40
                """
            )
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p40"

    result = apply_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["title"] == "Synthetic Renamed Projects"
    assert result["read_back"]["folder_handle"] == folder_handle
    assert result["read_back"]["current_folder_handle"] == folder_handle
    assert result["read_back"]["renamed"] is True
    assert result["read_back"]["folder_content_returned"] is False
    assert result["read_back"]["note_content_returned"] is False


def test_apply_notes_change_rename_folder_rejects_stale_title(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE ZICCLOUDSYNCINGOBJECT SET ZTITLE2 = 'Synthetic Other Projects' WHERE Z_PK = 40"
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after folder-title drift")

    result = apply_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_folder_changed"


def test_apply_notes_change_rename_folder_retry_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        db_path=db_path,
    )
    expected_sha = plan["preview"]["target"]["expected_current_sha256"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE ZICCLOUDSYNCINGOBJECT SET ZTITLE2 = 'Synthetic Renamed Projects' WHERE Z_PK = 40"
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for an already renamed folder")

    result = apply_notes_change(
        "rename-folder",
        title="Synthetic Renamed Projects",
        folder_handle=folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["renamed"] is True


def test_apply_notes_change_deletes_empty_child_folder_and_reads_absence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)
    expected_sha = plan["preview"]["target"]["expected_current_sha256"]

    def runner(script: str, _timeout: float) -> str:
        assert "ICFolder/p43" in script
        assert "count of notes of targetFolder" in script
        assert "count of folders of targetFolder" in script
        assert "delete targetFolder" in script
        assert "delete targetNote" not in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE ZICCLOUDSYNCINGOBJECT SET ZMARKEDFORDELETION = 1 WHERE Z_PK = 43"
            )
        return "ok"

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["folder_handle"] == folder_handle
    assert result["read_back"]["deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["folder_content_returned"] is False
    assert result["read_back"]["note_content_returned"] is False


def test_apply_notes_change_delete_folder_rejects_stale_title(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE ZICCLOUDSYNCINGOBJECT SET ZTITLE2 = 'Synthetic Other Child' WHERE Z_PK = 43"
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after folder-title drift")

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_folder_changed"


def test_apply_notes_change_delete_folder_rejects_new_note_before_write(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES (30, 12, 'Synthetic new child note', 'Synthetic new child note',
                      'Synthetic snippet', 300, 300, 0, 0, 43, 4)
            """
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for a non-empty folder")

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "folder_not_empty"


def test_apply_notes_change_delete_folder_rejects_smart_folder_drift(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ZICCLOUDSYNCINGOBJECT
            SET ZSMARTFOLDERQUERYJSON = '{"scope":"changed"}'
            WHERE Z_PK = 43
            """
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after smart-folder drift")

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_smart_folder"


def test_apply_notes_change_delete_folder_rejects_new_child_folder_before_write(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)
    _insert_empty_child_folder(db_path, folder_id=44, title="Synthetic Grandchild")
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZPARENT = 43 WHERE Z_PK = 44")

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for a folder containing a child folder")

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "folder_not_empty"


def test_apply_notes_change_delete_folder_handles_automation_not_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)

    def runner(_script: str, _timeout: float) -> str:
        return notes_adapter.AUTOMATION_ERROR_PREFIX + "folder_not_empty"

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "folder_not_empty"


def test_apply_notes_change_delete_folder_handles_automation_shared_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)

    def runner(_script: str, _timeout: float) -> str:
        return notes_adapter.AUTOMATION_ERROR_PREFIX + "shared_folder"

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_folder_mutation_blocked"


def test_apply_notes_change_delete_folder_reports_unavailable_absence_readback(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)

    def runner(_script: str, _timeout: float) -> str:
        db_path.unlink()
        return "ok"

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_notes_change_delete_folder_requires_absence_readback(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change("delete-folder", folder_handle=folder_handle, db_path=db_path)

    def runner(_script: str, _timeout: float) -> str:
        return "ok"

    result = apply_notes_change(
        "delete-folder",
        folder_handle=folder_handle,
        expected_current_sha256=plan["preview"]["target"]["expected_current_sha256"],
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_apply_notes_change_move_folder_moves_empty_child_and_verifies_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "ICFolder/p43" in script
        assert "ICFolder/p42" in script
        assert "move sourceFolder to targetFolder" in script
        assert "count of notes of sourceFolder" in script
        assert "count of folders of sourceFolder" in script
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZPARENT = 42 WHERE Z_PK = 43")
        return "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43"

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["folder_handle"] == folder_handle
    assert result["read_back"]["target_folder_handle"] == target_folder_handle
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["target_folder_confirmed"] is True
    assert result["read_back"]["folder_content_returned"] is False
    assert result["read_back"]["note_content_returned"] is False


def test_apply_notes_change_move_folder_rejects_stale_title(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZTITLE2 = 'Synthetic Other Child' WHERE Z_PK = 43")

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after folder-title drift")

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_folder_changed"


def test_apply_notes_change_move_folder_rejects_target_drift_before_write(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE ZICCLOUDSYNCINGOBJECT SET ZSMARTFOLDERQUERYJSON = ? WHERE Z_PK = 42",
            ('{"scope":"all"}',),
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after target folder drift")

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_smart_folder"


def test_apply_notes_change_move_folder_rejects_target_account_handle_drift_before_write(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZNAME, ZACCOUNTNAMEFORACCOUNTLISTSORTING, ZMARKEDFORDELETION)
              VALUES (50, 14, 'Synthetic Other Account', 'Synthetic Other Account', 0)
            """
        )
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZACCOUNT8 = 50 WHERE Z_PK = 42")

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after cross-account target drift")

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_folder_not_found"


def test_apply_notes_change_move_folder_rejects_new_note_before_write(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES (30, 12, 'Synthetic new child note', 'Synthetic new child note',
                      'Synthetic snippet', 300, 300, 0, 0, 43, 4)
            """
        )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for a non-empty folder")

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "folder_not_empty"


def test_apply_notes_change_move_folder_fails_closed_after_prior_move(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZPARENT = 42 WHERE Z_PK = 43")

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run after prior folder move")

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_in_target_folder"


def test_apply_notes_change_move_folder_requires_matching_read_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    _insert_empty_child_folder(db_path)
    folder_handle = search_notes_folders("Child", db_path=db_path)["results"][0]["handle"]
    target_folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic Child".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        return "ok"

    result = apply_notes_change(
        "move-folder",
        folder_handle=folder_handle,
        target_folder_handle=target_folder_handle,
        expected_current_sha256=expected_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_apply_notes_change_rejects_stale_folder_handle_before_write(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    folder_handle = search_notes_folders("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_notes_change(
        "create",
        title="Synthetic folder create note",
        folder_handle=folder_handle,
        body_text="Created body",
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZMARKEDFORDELETION = 1 WHERE Z_PK = 40")

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("Notes automation must not run for stale folder handles")

    result = apply_notes_change(
        "create",
        title="Synthetic folder create note",
        folder_handle=folder_handle,
        body_text="Created body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_folder_not_found"


def test_apply_notes_change_is_idempotent_for_matching_existing_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
              VALUES (30, 'Synthetic existing note', 'Synthetic existing note',
                      'Existing body', 300, 300, 0, 0, 4)
            """
        )
    plan = plan_notes_change(
        "create",
        title="Synthetic existing note",
        body_text="Existing body",
    )

    def runner(script: str, _timeout: float) -> str:
        assert "make new note" not in script
        assert "ICNote/p30" in script
        return "<h1>Synthetic existing note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "create",
        title="Synthetic existing note",
        body_text="Existing body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["content_text"] == "Synthetic existing note\nExisting body"


def test_apply_notes_create_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
    )

    def runner(_script: str, _timeout: float) -> str:
        raise OSError("permission denied for /private/local/notes-create")

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "write_error"
    assert "permission denied" not in str(result)
    assert "/private/local/notes-create" not in str(result)


def test_apply_notes_change_appends_text_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, timeout: float) -> str:
        nonlocal body_html
        assert timeout == 10.0
        assert "ICNote/p20" in script
        if "set body of targetNote" in script:
            assert "password protected of targetNote" in script
            assert "shared of targetNote" in script
            body_html = body_html + "<p>Appended line</p>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return body_html

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["content_text"] == "Project Alpha note\nExisting body\nAppended line"


def test_apply_notes_change_append_rejects_stale_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    approved_sha = hashlib.sha256("Different content".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text="Appended line",
    )

    def runner(script: str, _timeout: float) -> str:
        assert "set body of targetNote" not in script
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_apply_notes_append_read_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )

    def runner(_script: str, _timeout: float) -> str:
        raise OSError("permission denied for /private/local/notes-append-read")

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_error"
    assert "permission denied" not in str(result)
    assert "/private/local/notes-append-read" not in str(result)


def test_apply_notes_append_write_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            raise OSError("permission denied for /private/local/notes-append-write")
        return body_html

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "write_error"
    assert "permission denied" not in str(result)
    assert "/private/local/notes-append-write" not in str(result)


def test_apply_notes_change_append_rejects_shared_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            return "__LOCAL_APPLE_DATA_ERROR__:shared_note"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_note_mutation_blocked"


def test_apply_notes_change_replaces_text_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    replacement_text = "Project Alpha note\nReplacement body"
    plan = plan_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, timeout: float) -> str:
        nonlocal body_html
        assert timeout == 10.0
        assert "ICNote/p20" in script
        if "set body of targetNote" in script:
            assert "password protected of targetNote" in script
            assert "shared of targetNote" in script
            assert "replacementBody" in script
            body_html = "<h1>Project Alpha note</h1><p>Replacement body</p>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return body_html

    result = apply_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["content_text"] == replacement_text
    assert result["read_back"]["content_sha256"] == hashlib.sha256(
        replacement_text.encode("utf-8")
    ).hexdigest()


def test_apply_notes_change_replace_rejects_stale_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    approved_sha = hashlib.sha256("Different content".encode("utf-8")).hexdigest()
    replacement_text = "Project Alpha note\nReplacement body"
    plan = plan_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text=replacement_text,
    )

    def runner(script: str, _timeout: float) -> str:
        assert "set body of targetNote" not in script
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text=replacement_text,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_apply_notes_change_replace_rejects_shared_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    replacement_text = "Project Alpha note\nReplacement body"
    plan = plan_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
    )

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            return "__LOCAL_APPLE_DATA_ERROR__:shared_note"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_note_mutation_blocked"


def test_apply_notes_change_replace_requires_matching_read_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    replacement_text = "Project Alpha note\nReplacement body"
    plan = plan_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, _timeout: float) -> str:
        nonlocal body_html
        if "set body of targetNote" in script:
            body_html = "<h1>Project Alpha note</h1><p>Different body</p>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return body_html

    result = apply_notes_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text=replacement_text,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_apply_notes_change_moves_note_and_verifies_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "ICNote/p20" in script
        if "move targetNote to targetFolder" in script:
            assert "ICFolder/p42" in script
            assert "password protected of targetNote" in script
            assert "shared of targetNote" in script
            assert "set body of targetNote" not in script
            with sqlite3.connect(db_path) as connection:
                connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZFOLDER = 42 WHERE Z_PK = 20")
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return body_html

    result = apply_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"] == handle
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["target_folder_handle"] == folder_handle
    assert result["read_back"]["target_folder_confirmed"] is True
    assert result["read_back"]["body_returned"] is False


def test_apply_notes_change_move_to_folder_rejects_stale_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    approved_sha = hashlib.sha256("Different content".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=approved_sha,
        db_path=db_path,
    )

    def runner(script: str, _timeout: float) -> str:
        assert "move targetNote" not in script
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=approved_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_apply_notes_change_move_to_folder_fails_closed_after_prior_move(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE ZICCLOUDSYNCINGOBJECT SET ZFOLDER = 42 WHERE Z_PK = 20")

    def runner(script: str, _timeout: float) -> str:
        raise AssertionError(f"runner should not be called after stale folder state: {script}")

    result = apply_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_in_target_folder"


def test_apply_notes_change_move_to_folder_requires_matching_read_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    folder_handle = search_notes_folders("Archive", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        db_path=db_path,
    )

    def runner(script: str, _timeout: float) -> str:
        if "move targetNote to targetFolder" in script:
            return "ok"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "move-to-folder",
        handle=handle,
        folder_handle=folder_handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_apply_notes_change_deletes_note_and_verifies_absence(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "ICNote/p20" in script
        if "delete targetNote" in script:
            assert "password protected of targetNote" in script
            assert "shared of targetNote" in script
            assert "set body of targetNote" not in script
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    "UPDATE ZICCLOUDSYNCINGOBJECT SET ZMARKEDFORDELETION = 1 WHERE Z_PK = 20"
                )
            return "ok"
        return body_html

    result = apply_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"] == {
        "handle": handle,
        "deleted": True,
        "verified_absent": True,
    }
    assert get_notes_metadata(handle, db_path=db_path)["status"] == "not_found"


def test_apply_notes_change_delete_rejects_stale_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    approved_sha = hashlib.sha256("Different content".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=approved_sha,
    )

    def runner(script: str, _timeout: float) -> str:
        assert "delete targetNote" not in script
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=approved_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_apply_notes_change_delete_rejects_shared_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    def runner(script: str, _timeout: float) -> str:
        if "delete targetNote" in script:
            return "__LOCAL_APPLE_DATA_ERROR__:shared_note"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_note_mutation_blocked"


def test_apply_notes_change_delete_requires_absence_readback(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    def runner(script: str, _timeout: float) -> str:
        if "delete targetNote" in script:
            return "ok"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"


def test_notes_delete_script_deletes_only_exact_target_note() -> None:
    script = _notes_delete_script(
        "11111111-2222-3333-4444-555555555555",
        20,
        "<h1>Project Alpha note</h1><p>Existing body</p>",
    )

    assert "ICNote/p20" in script
    assert "delete targetNote" in script
    assert "password protected of targetNote" in script
    assert "shared of targetNote" in script
    assert "set body of targetNote" not in script
    assert "delete every" not in script.lower()
    assert "delete notes" not in script.lower()


def test_notes_move_to_folder_script_moves_only_exact_target_note() -> None:
    script = _notes_move_to_folder_script(
        "11111111-2222-3333-4444-555555555555",
        20,
        "<h1>Project Alpha note</h1><p>Existing body</p>",
        "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p42",
    )

    assert "ICNote/p20" in script
    assert "ICFolder/p42" in script
    assert "move targetNote to targetFolder" in script
    assert "password protected of targetNote" in script
    assert "shared of targetNote" in script
    assert "set body of targetNote" not in script
    assert "delete targetNote" not in script
    assert "make new note" not in script


def test_notes_move_folder_script_moves_only_exact_empty_source_folder() -> None:
    script = _notes_move_folder_script(
        "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43",
        "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p42",
        expected_title="Synthetic Child",
    )

    assert "ICFolder/p43" in script
    assert "ICFolder/p42" in script
    assert "move sourceFolder to targetFolder" in script
    assert "name of sourceFolder is not expectedTitle" in script
    assert "shared of sourceFolder" in script
    assert "shared of targetFolder" in script
    assert "count of notes of sourceFolder" in script
    assert "count of folders of sourceFolder" in script
    assert "delete sourceFolder" not in script
    assert "make new folder" not in script


def test_notes_create_folder_script_targets_only_exact_parent_folder() -> None:
    script = _notes_create_folder_script(
        "Synthetic Child",
        parent_folder_reference="x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p42",
    )

    assert "ICFolder/p42" in script
    assert "make new folder at targetFolder" in script
    assert "return id of createdFolder" in script
    assert "make new note" not in script
    assert "delete " not in script.lower()
    assert "move " not in script.lower()


def test_notes_rename_folder_script_targets_only_exact_folder() -> None:
    script = _notes_rename_folder_script(
        "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p42",
        expected_title="Synthetic Projects",
        new_title="Synthetic Renamed Projects",
    )

    assert "ICFolder/p42" in script
    assert "name of targetFolder is not expectedTitle" in script
    assert "set name of targetFolder to newTitle" in script
    assert "return id of targetFolder" in script
    assert "make new note" not in script
    assert "make new folder" not in script
    assert "delete " not in script.lower()
    assert "move " not in script.lower()


def test_notes_delete_folder_script_targets_only_exact_empty_folder() -> None:
    script = _notes_delete_folder_script(
        "x-coredata://11111111-2222-3333-4444-555555555555/ICFolder/p43",
        expected_title="Synthetic Child",
    )

    assert "ICFolder/p43" in script
    assert "name of targetFolder is not expectedTitle" in script
    assert "shared of targetFolder" in script
    assert "count of notes of targetFolder" in script
    assert "count of folders of targetFolder" in script
    assert "delete targetFolder" in script
    assert "delete targetNote" not in script
    assert "make new note" not in script
    assert "make new folder" not in script
    assert "move " not in script.lower()


def test_get_notes_content_rejects_bad_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = get_notes_content("notes:note:20", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_notes_content_does_not_return_locked_or_deleted_notes(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    locked = get_notes_content(make_int_handle("notes:note", 21), db_path=db_path)
    deleted = get_notes_content(make_int_handle("notes:note", 22), db_path=db_path)

    assert locked["status"] == "not_found"
    assert locked["result"] is None
    assert deleted["status"] == "not_found"
    assert deleted["result"] is None


def test_get_notes_content_reports_missing_store_uuid(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM Z_METADATA")
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        script_runner=lambda _script, _timeout: "<p>should not run</p>",
    )

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "content_unavailable"


def test_get_notes_content_reports_automation_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    def runner(_script: str, timeout: float) -> str:
        raise subprocess.TimeoutExpired("osascript", timeout)

    result = get_notes_content(handle, db_path=db_path, script_runner=runner)

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "automation_timeout"


def test_notes_schema_warning_does_not_expose_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite"

    result = check_notes_schema(db_path=missing_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "notes_schema_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_notes_schema_warning_uses_generic_message(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    def fail_schema(_connection):
        raise notes_adapter.StoreUnavailableError("schema failed at /private/local/notes.sqlite")

    monkeypatch.setattr(notes_adapter, "_check_schema", fail_schema)

    result = check_notes_schema(db_path=db_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "notes_schema_unavailable",
            "message": "Notes schema is unavailable or unsupported.",
        }
    ]


def test_notes_store_warning_uses_generic_message(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    def fail_schema(_connection):
        raise notes_adapter.StoreUnavailableError("store failed at /private/local/notes.sqlite")

    monkeypatch.setattr(notes_adapter, "_check_schema", fail_schema)

    result = search_notes_metadata("Alpha", db_path=db_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "notes_store_unavailable",
            "message": "Notes local store is unavailable or unreadable.",
        }
    ]


# --- v1.179 rich-text body read + write ---


def test_get_notes_content_html_format_returns_bounded_body_and_text(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    body_html = "<div><h1>Alpha</h1><p>Rich <b>body</b> text.</p></div>"

    result = get_notes_content(
        handle,
        db_path=db_path,
        content_format="html",
        script_runner=lambda _s, _t: body_html,
    )

    assert result["status"] == "ok"
    payload = result["result"]
    assert payload["content_format"] == "html"
    assert payload["content_html"] == body_html
    assert payload["content_html_truncated"] is False
    assert payload["content_html_sha256"]
    assert payload["content_text"] == notes_adapter._html_to_text(body_html)


def test_get_notes_content_text_format_omits_html(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        script_runner=lambda _s, _t: "<p>text</p>",
    )

    assert result["status"] == "ok"
    assert result["result"]["content_format"] == "text"
    assert "content_html" not in result["result"]


def test_get_notes_content_html_truncation_flag(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    monkeypatch.setattr(notes_adapter, "MAX_BODY_HTML_CHARS", 16)
    big_html = "<p>" + ("x" * 200) + "</p>"

    result = get_notes_content(
        handle,
        db_path=db_path,
        content_format="html",
        script_runner=lambda _s, _t: big_html,
    )

    payload = result["result"]
    assert payload["content_html_truncated"] is True
    assert len(payload["content_html"]) == 16
    assert payload["content_html_total_chars"] == len(big_html)
    assert any(w["code"] == "content_html_truncated" for w in result["warnings"])


def test_get_notes_content_rejects_invalid_format(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(handle, db_path=db_path, content_format="markdown")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_content_format"


def test_plan_notes_change_create_html_previews_rich_text(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create_html",
        title="Rich note",
        body_html="<h1>Rich note</h1><p>Rich body.</p>",
        db_path=db_path,
    )
    assert plan["status"] == "ok"
    assert plan["mode"] == "plan"
    assert plan["mutation_applied"] is False
    assert plan["preview"]["proposed"]["format"] == "rich_text_create"
    assert plan["preview"]["proposed"]["body_html_sanitized"] is True


def test_apply_notes_change_create_html_semantic_read_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    title = "Rich created note"
    body_html = "<h1>Rich created note</h1><p>Created <b>rich</b> body.</p>"
    plan = plan_notes_change("create_html", title=title, body_html=body_html, db_path=db_path)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    state = {"html": ""}

    def runner(script: str, _timeout: float) -> str:
        if "make new note" in script:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    "INSERT INTO ZICCLOUDSYNCINGOBJECT "
                    "(Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, "
                    "ZMODIFICATIONDATE1, ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA) "
                    "VALUES (60, 12, ?, ?, 'snip', 300, 300, 0, 0, 9)",
                    (title, title),
                )
            # Notes.app normalizes HTML on save (b -> strong, wrapped in div).
            state["html"] = "<div><h1>Rich created note</h1><p>Created <strong>rich</strong> body.</p></div>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p60"
        return state["html"]

    result = apply_notes_change(
        "create_html",
        title=title,
        body_html=body_html,
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    expected_text = notes_adapter._html_to_text(notes_adapter._sanitize_body_html(body_html))
    assert notes_adapter._normalized_content_matches(
        result["read_back"]["content_text"], expected_text
    )


def test_apply_notes_change_replace_html_binds_extracted_text_sha(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_html = "<h1>Alpha</h1><p>Original body.</p>"
    current_text = notes_adapter._html_to_text(current_html)
    expected_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    body_html = "<h1>Alpha</h1><p>Replaced <i>rich</i> body.</p>"
    plan = plan_notes_change(
        "replace_html",
        handle=handle,
        body_html=body_html,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    state = {"html": current_html}

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            state["html"] = "<div><h1>Alpha</h1><p>Replaced <em>rich</em> body.</p></div>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return state["html"]

    result = apply_notes_change(
        "replace_html",
        handle=handle,
        body_html=body_html,
        expected_current_sha256=expected_sha,
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    expected_text = notes_adapter._html_to_text(notes_adapter._sanitize_body_html(body_html))
    assert notes_adapter._normalized_content_matches(
        result["read_back"]["content_text"], expected_text
    )


def test_apply_notes_change_replace_html_rejects_stale_state(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    stale_sha = hashlib.sha256("stale".encode("utf-8")).hexdigest()
    body_html = "<h1>Alpha</h1><p>New body.</p>"
    plan = plan_notes_change(
        "replace_html",
        handle=handle,
        body_html=body_html,
        expected_current_sha256=stale_sha,
        db_path=db_path,
    )
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            raise AssertionError("stale replace_html must not write")
        return "<h1>Alpha</h1><p>Different current body.</p>"

    result = apply_notes_change(
        "replace_html",
        handle=handle,
        body_html=body_html,
        expected_current_sha256=stale_sha,
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_normalize_body_html_strips_script_and_handlers() -> None:
    sanitized = notes_adapter._sanitize_body_html(
        '<p onclick="evil()">Hi</p><script>alert(1)</script><a href="javascript:x()">link</a>'
    )
    assert "<script" not in sanitized.lower()
    assert "onclick" not in sanitized.lower()
    assert "javascript:" not in sanitized.lower()
    assert "Hi" in sanitized and "link" in sanitized


def test_normalize_body_html_rejects_nul_in_tag_name() -> None:
    body, warning = notes_adapter._normalize_body_html(
        "<scr\x00ipt>alert(1)</script><p>Body</p>", operation="create_html"
    )
    assert body == ""
    assert warning is not None
    assert warning["code"] == "unsafe_body_html"


def test_normalize_body_html_rejects_nul_in_attribute() -> None:
    body, warning = notes_adapter._normalize_body_html(
        '<p on\x00click="evil()">Body</p>', operation="replace_html"
    )
    assert body == ""
    assert warning is not None
    assert warning["code"] == "unsafe_body_html"


def test_normalize_body_html_rejects_other_c0_control_chars() -> None:
    body, warning = notes_adapter._normalize_body_html(
        "<p>Body</p>\x0c<scr\x0cipt>x</script>", operation="create_html"
    )
    assert body == ""
    assert warning is not None
    assert warning["code"] == "unsafe_body_html"


def test_normalize_body_html_allows_tab_and_newline_whitespace() -> None:
    body, warning = notes_adapter._normalize_body_html(
        "<h1>Title</h1>\n<p>Body\twith tab</p>", operation="create_html"
    )
    assert warning is None
    assert "Body" in body


def test_apply_notes_change_create_html_rejects_nul_body(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    title = "Rich NUL note"
    safe_html = "<h1>Rich NUL note</h1><p>Safe body.</p>"
    # Plan against a safe body so a valid approval token exists, then attempt
    # apply with a NUL-laced body_html; apply must re-normalize and reject.
    plan = plan_notes_change("create_html", title=title, body_html=safe_html, db_path=db_path)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, _timeout: float) -> str:
        raise AssertionError("NUL body_html must not reach Notes automation")

    result = apply_notes_change(
        "create_html",
        title=title,
        body_html="<scr\x00ipt>alert(1)</script><p>Rich NUL note</p>",
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsafe_body_html"


def test_plan_notes_change_create_html_rejects_script_only_body(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create_html",
        title="Rich note",
        body_html="<script>alert(1)</script>",
        db_path=db_path,
    )
    assert plan["status"] == "error"
    assert any(
        w["code"] in {"empty_body_html_text", "unsafe_body_html", "missing_body_html"}
        for w in plan["warnings"]
    )


def test_plan_notes_change_create_html_rejects_data_uri_image(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create_html",
        title="Rich note",
        body_html='<p>Body</p><img src="data:text/html;base64,PHNjcmlwdD4=">',
        db_path=db_path,
    )
    # data: URI is stripped from the img src; body still has visible text, so plan succeeds
    # but the stored HTML must not carry the data: URI.
    if plan["status"] == "ok":
        assert "data:" not in str(plan).lower()


def test_plan_notes_change_replace_html_rejects_body_text(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 20)
    sha = hashlib.sha256(b"x").hexdigest()
    plan = plan_notes_change(
        "replace_html",
        handle=handle,
        body_text="plain text",
        body_html="<p>rich</p>",
        expected_current_sha256=sha,
        db_path=db_path,
    )
    assert plan["status"] == "error"
    assert any(w["code"] == "unexpected_body_text" for w in plan["warnings"])


def test_plan_notes_change_plaintext_replace_rejects_body_html(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 20)
    sha = hashlib.sha256(b"x").hexdigest()
    plan = plan_notes_change(
        "replace_text",
        handle=handle,
        body_text="Alpha\nplain replacement",
        body_html="<p>rich</p>",
        expected_current_sha256=sha,
        db_path=db_path,
    )
    assert plan["status"] == "error"
    assert any(w["code"] == "unexpected_body_html" for w in plan["warnings"])


def test_plaintext_replace_unchanged_by_rich_text_addition(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_html = "<h1>Alpha</h1><p>Old body.</p>"
    current_text = notes_adapter._html_to_text(current_html)
    expected_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    replacement_text = "Alpha\nNew plain body."
    plan = plan_notes_change(
        "replace_text",
        handle=handle,
        body_text=replacement_text,
        expected_current_sha256=expected_sha,
        db_path=db_path,
    )
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["format"] == "plaintext_replace"
    assert plan["preview"]["proposed"]["rich_text"] == "blocked"
