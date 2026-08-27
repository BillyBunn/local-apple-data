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


def _add_second_messages_chat(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            INSERT INTO chat VALUES (2, 'chat-guid-2', 'Synthetic Other CLI Chat', 'iMessage');
            INSERT INTO handle VALUES (8, '+15550200', 'iMessage');
            INSERT INTO chat_handle_join VALUES (2, 8);
            INSERT INTO message VALUES (20, 'Other CLI message', 802310800, 0, 8, 'iMessage', NULL);
            INSERT INTO chat_message_join VALUES (2, 20);
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
            "Synthetic CLI",
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
            "Synthetic CLI",
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


def test_cli_messages_participants_and_participant_use_exact_handles(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
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
    chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    participants_exit = main(
        [
            "messages",
            "participants",
            "--json",
            "--handle",
            chat_handle,
            "--db",
            str(db_path),
        ]
    )
    participants_payload = json.loads(capsys.readouterr().out)
    participant_handle = participants_payload["results"][0]["handle"]
    participant_exit = main(
        [
            "messages",
            "participant",
            "--json",
            "--chat-handle",
            chat_handle,
            "--handle",
            participant_handle,
            "--db",
            str(db_path),
        ]
    )

    assert search_exit == 0
    assert participants_exit == 0
    assert participant_exit == 0
    assert participants_payload["status"] == "ok"
    assert "id_preview" not in participants_payload["results"][0]
    assert "participant_id" not in participants_payload["results"][0]
    assert "+15550100" not in str(participants_payload)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["participant_id"] == "+15550100"
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "+15550100" not in log_text
    assert chat_handle not in log_text
    assert participant_handle not in log_text
    assert "messages:participant:v1:" not in log_text
    assert "Expected messages:participant" not in log_text


def test_cli_messages_participant_rejects_cross_chat_participant_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    _add_second_messages_chat(db_path)
    main(
        [
            "messages",
            "search",
            "--json",
            "--query",
            "Synthetic CLI",
            "--db",
            str(db_path),
        ]
    )
    chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    main(
        [
            "messages",
            "search",
            "--json",
            "--query",
            "Other",
            "--db",
            str(db_path),
        ]
    )
    other_chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    main(
        [
            "messages",
            "participants",
            "--json",
            "--handle",
            chat_handle,
            "--db",
            str(db_path),
        ]
    )
    participant_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "messages",
            "participant",
            "--json",
            "--chat-handle",
            other_chat_handle,
            "--handle",
            participant_handle,
            "--db",
            str(db_path),
        ]
    )

    parsed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert parsed["status"] == "not_found"
    assert parsed["privacy"]["participant_id_returned"] is False
    assert parsed["result"] is None
    assert "+15550100" not in str(parsed)
    assert "+15550200" not in str(parsed)


def test_cli_messages_plan_and_apply_refusal_use_synthetic_db(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
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
    chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    plan_exit = main(
        [
            "messages",
            "plan",
            "--json",
            "--operation",
            "send-text",
            "--handle",
            chat_handle,
            "--body-text",
            "Synthetic CLI outbound",
            "--db",
            str(db_path),
        ]
    )
    plan_payload = json.loads(capsys.readouterr().out)
    token = "messages-apply:v1:" + plan_payload["preview"]["approval"]["approval_fingerprint"]
    apply_exit = main(
        [
            "messages",
            "apply",
            "--json",
            "--operation",
            "send-text",
            "--handle",
            chat_handle,
            "--body-text",
            "Synthetic CLI outbound",
            "--approval-token",
            token,
            "--db",
            str(db_path),
        ]
    )

    assert search_exit == 0
    assert plan_exit == 0
    assert apply_exit == 0
    assert plan_payload["status"] == "ok"
    assert plan_payload["preview"]["target"]["handle"] == chat_handle
    assert "chat-guid-1" not in str(plan_payload)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["warnings"][0]["code"] == "missing_apply_confirmation"


def test_cli_messages_plan_and_apply_send_file_refusal_use_synthetic_db(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    source = tmp_path / "cli-outbound.pdf"
    source.write_bytes(b"CLIPDF!")
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
    chat_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    plan_exit = main(
        [
            "messages",
            "plan",
            "--json",
            "--operation",
            "send-file",
            "--handle",
            chat_handle,
            "--file-path",
            str(source),
            "--db",
            str(db_path),
        ]
    )
    plan_payload = json.loads(capsys.readouterr().out)
    token = "messages-apply:v1:" + plan_payload["preview"]["approval"]["approval_fingerprint"]
    apply_exit = main(
        [
            "messages",
            "apply",
            "--json",
            "--operation",
            "send-file",
            "--handle",
            chat_handle,
            "--file-path",
            str(source),
            "--approval-token",
            token,
            "--db",
            str(db_path),
        ]
    )

    assert search_exit == 0
    assert plan_exit == 0
    assert apply_exit == 0
    assert plan_payload["status"] == "ok"
    assert plan_payload["preview"]["operation"] == "send_file"
    assert plan_payload["preview"]["proposed"]["filename"] == "cli-outbound.pdf"
    assert str(source) not in str(plan_payload)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["warnings"][0]["code"] == "missing_apply_confirmation"
