from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.adapters.messages import get_message_chat, search_message_chats


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
