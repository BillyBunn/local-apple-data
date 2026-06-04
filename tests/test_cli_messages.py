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
                service TEXT
            );
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
            INSERT INTO chat VALUES (1, 'chat-guid-1', 'Synthetic CLI Chat', 'iMessage');
            INSERT INTO handle VALUES (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES (10, 'Synthetic CLI message', 802310400, 0, 7, 'iMessage');
            INSERT INTO chat_message_join VALUES (1, 10);
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
