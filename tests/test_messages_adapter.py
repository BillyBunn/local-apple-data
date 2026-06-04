from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.adapters.messages import (
    export_message_attachment,
    get_message_chat,
    list_message_attachments,
    search_message_chats,
)


def _make_messages_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                display_name TEXT,
                service_name TEXT
            );
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date INTEGER,
                is_from_me INTEGER,
                handle_id INTEGER,
                service TEXT
            );
            CREATE TABLE chat_message_join (
                chat_id INTEGER,
                message_id INTEGER
            );
            CREATE TABLE chat_handle_join (
                chat_id INTEGER,
                handle_id INTEGER
            );
            CREATE TABLE handle (
                ROWID INTEGER PRIMARY KEY,
                id TEXT,
                service TEXT
            );
            INSERT INTO chat VALUES
              (1, 'chat-guid-1', 'Synthetic Planning Chat', 'iMessage');
            INSERT INTO handle VALUES
              (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES
              (10, 'First synthetic message', 802310400, 0, 7, 'iMessage'),
              (11, 'Second synthetic reply', 802310500, 1, 0, 'iMessage');
            INSERT INTO chat_message_join VALUES
              (1, 10),
              (1, 11);
            """
        )


def _add_messages_attachment_schema(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE attachment (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                created_date INTEGER,
                start_date INTEGER,
                filename TEXT,
                uti TEXT,
                mime_type TEXT,
                transfer_state INTEGER,
                is_outgoing INTEGER,
                user_info BLOB,
                transfer_name TEXT,
                total_bytes INTEGER,
                is_sticker INTEGER
            );
            CREATE TABLE message_attachment_join (
                message_id INTEGER,
                attachment_id INTEGER
            );
            INSERT INTO attachment VALUES
              (20, 'attachment-guid-1', 802310300, 802310350,
               'Attachments/aa/bb/source-packet.pdf', 'com.adobe.pdf',
               'application/pdf', 0, 0, NULL, 'packet.pdf', 11, 0);
            INSERT INTO message_attachment_join VALUES (10, 20);
            """
        )


def _attachment_store(tmp_path: Path) -> tuple[Path, Path, str]:
    db_path = tmp_path / "chat.db"
    messages_root = tmp_path / "Messages"
    _make_messages_db(db_path)
    _add_messages_attachment_schema(db_path)
    attachment_path = messages_root / "Attachments/aa/bb/source-packet.pdf"
    attachment_path.parent.mkdir(parents=True)
    attachment_path.write_bytes(b"PDF PAYLOAD")
    search = search_message_chats("Planning", db_path=db_path)
    return db_path, messages_root, search["results"][0]["handle"]


def test_search_message_chats_returns_metadata_only(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)

    result = search_message_chats("Planning", db_path=db_path)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "chat_display_name"
    assert result["result_count"] == 1
    chat = result["results"][0]
    assert chat["handle"].startswith("messages:chat:v1:")
    assert chat["display_name"] == "Synthetic Planning Chat"
    assert chat["participants_count"] == 1
    assert "+15550100" not in str(result)
    assert "First synthetic message" not in str(result)
    assert "chat-guid-1" not in str(result)


def test_search_message_chats_rejects_broad_query_without_db(tmp_path: Path) -> None:
    result = search_message_chats("%", db_path=tmp_path / "missing.db")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_get_message_chat_returns_exact_bounded_transcript(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    search = search_message_chats("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_message_chat(handle, db_path=db_path, max_messages=10, max_chars=25)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["messages_returned"] == 2
    assert result["result"]["messages"][0]["direction"] == "received"
    assert result["result"]["messages"][0]["text"] == "First synthetic message"
    assert result["result"]["messages"][1]["text"] == "Se"
    assert result["result"]["transcript_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"
    assert "+15550100" not in str(result)
    assert "chat-guid-1" not in str(result)


def test_get_message_chat_rejects_invalid_handle() -> None:
    result = get_message_chat("messages:chat:1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_message_chats_degrades_without_store(tmp_path: Path) -> None:
    result = search_message_chats("Planning", db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "messages_store_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_list_message_attachments_returns_exact_attachment_handles(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)

    result = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["result_count"] == 1
    attachment = result["results"][0]
    assert attachment["handle"].startswith("messages:attachment:v1:")
    assert attachment["chat_handle"] == chat_handle
    assert attachment["filename"] == "packet.pdf"
    assert attachment["mime_type"] == "application/pdf"
    assert attachment["uti"] == "com.adobe.pdf"
    assert attachment["file_size"] == 11
    assert attachment["media_status"] == "available"
    assert attachment["attachment_type"] == "document"
    assert attachment["direction"] == "received"
    assert str(messages_root) not in str(result)
    assert "+15550100" not in str(result)
    assert "First synthetic message" not in str(result)
    assert "attachment-guid-1" not in str(result)


def test_export_message_attachment_writes_selected_file(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    attachment_handle = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]["handle"]

    result = export_message_attachment(
        chat_handle,
        attachment_handle,
        output_dir=tmp_path / "exports",
        filename="../review packet.pdf",
        db_path=db_path,
        messages_root=messages_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["result"]["attachment_content_exported"] is True
    assert result["result"]["exported_filename"] == "review-packet.pdf"
    assert result["result"]["exported_bytes"] == 11
    assert Path(result["result"]["exported_path"]).read_bytes() == b"PDF PAYLOAD"
    assert str(messages_root) not in str(result)


def test_message_attachment_export_rejects_bad_handles(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    attachment_handle = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]["handle"]

    result = export_message_attachment(
        "messages:chat:1",
        attachment_handle,
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"

    result = export_message_attachment(
        chat_handle,
        "messages:attachment:20",
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_message_attachment_export_reports_unavailable_for_missing_file(
    tmp_path: Path,
) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    (messages_root / "Attachments/aa/bb/source-packet.pdf").unlink()
    attachment = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]

    result = export_message_attachment(
        chat_handle,
        attachment["handle"],
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )

    assert attachment["media_status"] == "unavailable"
    assert result["status"] == "attachment_unavailable"
    assert result["warnings"][0]["code"] == "messages_attachment_unavailable"
    assert not (tmp_path / "exports" / "packet.pdf").exists()
