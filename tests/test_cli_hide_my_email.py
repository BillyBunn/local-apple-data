from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.cli import main


ALIAS = "cli_mask_42" + "@" + "icloud.com"


def _make_mail_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE addresses (
                ROWID INTEGER PRIMARY KEY,
                address TEXT,
                comment TEXT
            );
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                sender INTEGER,
                date_received INTEGER,
                date_sent INTEGER,
                deleted INTEGER
            );
            CREATE TABLE recipients (
                ROWID INTEGER PRIMARY KEY,
                message INTEGER,
                address INTEGER,
                type INTEGER
            );
            INSERT INTO addresses VALUES (1, 'placeholder', '');
            INSERT INTO messages VALUES (10, 1, 1000, 900, 0);
            INSERT INTO recipients VALUES (100, 10, 1, 0);
            """
        )
        connection.execute("UPDATE addresses SET address = ? WHERE ROWID = 1", (ALIAS,))


def test_cli_hide_my_email_search_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)

    exit_code = main(
        [
            "hide-my-email",
            "search",
            "--json",
            "--query",
            "cli_mask",
            "--db",
            str(db_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "hide_my_email"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("hide_my_email:alias:v1:")
    assert parsed["results"][0]["alias_preview"] == "cl***@icloud.com"
    assert parsed["results"][0]["authoritative_inventory"] is False
    assert ALIAS not in str(parsed)


def test_cli_hide_my_email_get_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)
    search_exit = main(
        [
            "hide-my-email",
            "search",
            "--json",
            "--query",
            "cli_mask",
            "--db",
            str(db_path),
        ]
    )
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "hide-my-email",
            "get",
            "--json",
            "--handle",
            handle,
            "--db",
            str(db_path),
        ]
    )

    assert search_exit == 0
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["alias"] == ALIAS
    assert parsed["result"]["authoritative_inventory"] is False
