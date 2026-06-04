from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.cli import main


def _store(store_dir: Path) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store_dir / "Data-local.sqlite") as connection:
        connection.executescript(
            """
            CREATE TABLE ZREMCDBASELIST (Z_PK INTEGER PRIMARY KEY, ZNAME VARCHAR);
            CREATE TABLE ZREMCDREMINDER (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE VARCHAR,
                ZNOTES VARCHAR,
                ZDUEDATE TIMESTAMP,
                ZDISPLAYDATEDATE TIMESTAMP,
                ZCREATIONDATE TIMESTAMP,
                ZCOMPLETED INTEGER,
                ZFLAGGED INTEGER,
                ZPRIORITY INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZLIST INTEGER
            );
            INSERT INTO ZREMCDBASELIST VALUES (1, 'Synthetic List');
            INSERT INTO ZREMCDREMINDER VALUES
              (33, 'Synthetic CLI reminder', '', 802310400, 802310400, 802300000, 0, 0, 0, 0, 1);
            """
        )


def test_cli_reminders_search_uses_synthetic_store(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    _store(tmp_path)

    exit_code = main(
        [
            "reminders",
            "search",
            "--json",
            "--query",
            "CLI",
            "--store-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("reminders:reminder:v1:")
    assert "Data-local" not in str(parsed["results"][0])


def test_cli_reminders_eventkit_search(monkeypatch, capsys) -> None:
    def fake_search(query: str, *, limit: int, include_completed: bool) -> dict:
        assert query == "CLI"
        assert limit == 7
        assert include_completed is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
                    "title": "Synthetic CLI EventKit reminder",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_reminders_eventkit", fake_search)

    exit_code = main(
        [
            "reminders",
            "eventkit-search",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "7",
            "--include-completed",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("reminders:reminder:eventkit:v1:")


def test_cli_reminders_content(monkeypatch, capsys) -> None:
    def fake_content(handle: str, *, max_chars: int) -> dict:
        assert handle == "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
        assert max_chars == 12
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": True, "output_tier": "content"},
            "result": {
                "handle": handle,
                "title": "Synthetic CLI EventKit reminder",
                "notes_text": "Synthetic no",
                "notes_chars": 12,
                "notes_truncated": True,
            },
            "result_count": 1,
            "warnings": [{"code": "content_truncated", "message": "Synthetic truncation."}],
        }

    monkeypatch.setattr("local_apple_data.cli.get_reminder_content", fake_content)

    exit_code = main(
        [
            "reminders",
            "content",
            "--json",
            "--handle",
            "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
            "--max-chars",
            "12",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["notes_chars"] == 12


def test_cli_reminders_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic CLI planned reminder",
            "--list-name",
            "Synthetic List",
            "--due-date",
            "2026-06-04",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "plan"
    assert parsed["mutation_applied"] is False
    assert parsed["apply_available"] is False
    assert parsed["preview"]["operation"] == "create"
    assert parsed["preview"]["proposed"]["title"] == "Synthetic CLI planned reminder"
