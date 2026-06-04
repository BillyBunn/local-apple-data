from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.cli import main


def _make_messages_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT, display_name TEXT, service_name TEXT);
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date INTEGER,
                is_from_me INTEGER,
                handle_id INTEGER,
                service TEXT,
                attributedBody BLOB
            );
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
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
            CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
            INSERT INTO chat VALUES (1, 'chat-guid-1', 'Synthetic CLI Chat', 'iMessage');
            INSERT INTO handle VALUES (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES (10, 'Synthetic CLI message', 802310400, 0, 7, 'iMessage', NULL);
            INSERT INTO chat_message_join VALUES (1, 10);
            INSERT INTO attachment VALUES
              (20, 'attachment-guid-1', 802310300, 802310350,
               'Attachments/aa/bb/cli-packet.pdf', 'com.adobe.pdf',
               'application/pdf', 0, 0, NULL, 'cli-packet.pdf', 7, 0);
            INSERT INTO message_attachment_join VALUES (10, 20);
            """
        )


def test_cli_messages_search_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)

    exit_code = main(
        [
            "messages",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "messages"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("messages:chat:v1:")
    assert "+15550100" not in str(parsed)
    assert "Synthetic CLI message" not in str(parsed)


def test_cli_messages_get_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    search_exit = main(
        [
            "messages",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
        ]
    )
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "messages",
            "get",
            "--json",
            "--handle",
            handle,
            "--max-messages",
            "5",
            "--max-chars",
            "4000",
            "--db",
            str(db_path),
        ]
    )

    assert search_exit == 0
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["messages"][0]["text"] == "Synthetic CLI message"
    assert "+15550100" not in str(parsed)


def test_cli_messages_attachments_and_export_use_exact_handles(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    messages_root = tmp_path / "Messages"
    _make_messages_db(db_path)
    source = messages_root / "Attachments/aa/bb/cli-packet.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"CLIPDF!")
    search_exit = main(
        [
            "messages",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
        ]
    )
    chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    attachments_exit = main(
        [
            "messages",
            "attachments",
            "--json",
            "--handle",
            chat_handle,
            "--db",
            str(db_path),
            "--messages-root",
            str(messages_root),
        ]
    )
    attachment_payload = json.loads(capsys.readouterr().out)
    attachment_handle = attachment_payload["results"][0]["handle"]
    export_exit = main(
        [
            "messages",
            "export-attachment",
            "--json",
            "--chat-handle",
            chat_handle,
            "--handle",
            attachment_handle,
            "--output-dir",
            str(tmp_path / "exports"),
            "--filename",
            "../cli packet.pdf",
            "--db",
            str(db_path),
            "--messages-root",
            str(messages_root),
        ]
    )

    assert search_exit == 0
    assert attachments_exit == 0
    assert export_exit == 0
    assert attachment_payload["status"] == "ok"
    assert attachment_payload["results"][0]["filename"] == "cli-packet.pdf"
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["exported_filename"] == "cli-packet.pdf"
    assert Path(parsed["result"]["exported_path"]).read_bytes() == b"CLIPDF!"
    assert str(messages_root) not in str(parsed)
