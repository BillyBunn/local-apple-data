from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.cli import main
from local_apple_data.adapters.mail import search_mail_metadata


def _mail_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject TEXT NOT NULL);
            CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY, url TEXT NOT NULL);
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                subject INTEGER NOT NULL,
                mailbox INTEGER NOT NULL,
                date_received INTEGER,
                date_sent INTEGER,
                read INTEGER NOT NULL DEFAULT 0,
                flagged INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO subjects VALUES (1, 'Synthetic planning mail');
            INSERT INTO mailboxes VALUES (1, 'local://synthetic/INBOX');
            INSERT INTO messages VALUES (7, 1, 1, 10, 9, 0, 0, 0, 12);
            """
        )


def _write_emlx(mail_root: Path, rowid: int, mime_text: str) -> None:
    mime_bytes = mime_text.encode("utf-8")
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages" / f"{rowid}.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes)


def _notes_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZICCLOUDSYNCINGOBJECT (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE1 VARCHAR,
                ZTITLE VARCHAR,
                ZSNIPPET VARCHAR,
                ZCREATIONDATE1 TIMESTAMP,
                ZMODIFICATIONDATE1 TIMESTAMP,
                ZISPASSWORDPROTECTED INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZNOTEDATA INTEGER
            );
            CREATE TABLE Z_METADATA (Z_UUID VARCHAR);
            INSERT INTO Z_METADATA VALUES ('11111111-2222-3333-4444-555555555555');
            INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES
              (8, 'Synthetic planning note', 'Fallback', 'Synthetic only', 10, 20, 0, 0, 1);
            """
        )


def _icloud_root(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "Packets").mkdir()
    (path / "synthetic-packet.md").write_text("Synthetic iCloud content.", encoding="utf-8")


def test_cli_mail_search_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "mail.sqlite"
    _mail_db(db_path)

    exit_code = main(
        ["mail", "search", "--json", "--query", "planning", "--db", str(db_path)]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "mail"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("mail:message:v2:")
    assert parsed["results"][0]["content_status"] == "unavailable"


def test_cli_mail_content_uses_synthetic_db_and_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _mail_db(db_path)
    _write_emlx(
        mail_root,
        7,
        "Subject: Synthetic planning mail\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic CLI content.\r\n",
    )
    handle = search_mail_metadata("planning", db_path=db_path)["results"][0]["handle"]

    exit_code = main(
        [
            "mail",
            "content",
            "--json",
            "--handle",
            handle,
            "--max-chars",
            "4000",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "mail"
    assert parsed["status"] == "ok"
    assert parsed["result"]["content_text"] == "Synthetic CLI content."


def test_cli_notes_search_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)

    exit_code = main(
        ["notes", "search", "--json", "--query", "planning", "--db", str(db_path)]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "notes"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("notes:note:v2:")


def test_cli_notes_content_uses_exact_handle(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)

    def fake_get_notes_content(handle: str, **kwargs):
        assert handle.startswith("notes:note:v2:")
        assert kwargs["max_chars"] == 120
        assert kwargs["offset"] == 10
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {
                "content_inspected": True,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "content",
            },
            "result": {
                "handle": handle,
                "content_text": "Synthetic note content.",
                "content_chars": 23,
                "content_offset": 10,
                "content_total_chars": 23,
                "next_offset": None,
                "truncated": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    search_exit_code = main(
        [
            "notes",
            "search",
            "--json",
            "--query",
            "planning",
            "--db",
            str(db_path),
        ]
    )
    assert search_exit_code == 0
    parsed_search = json.loads(capsys.readouterr().out)
    monkeypatch.setattr("local_apple_data.cli.get_notes_content", fake_get_notes_content)

    exit_code = main(
        [
            "notes",
            "content",
            "--json",
            "--handle",
            parsed_search["results"][0]["handle"],
            "--max-chars",
            "120",
            "--offset",
            "10",
            "--db",
            str(db_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "notes"
    assert parsed["status"] == "ok"
    assert parsed["result"]["content_text"] == "Synthetic note content."


def test_cli_notes_plan_and_apply_create(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic planned note",
            "--body-text",
            "Synthetic note body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["title"] == "Synthetic planned note"
        assert kwargs["body_text"] == "Synthetic note body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"title": "Synthetic planned note"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_notes_change", fake_apply_notes_change)

    apply_exit_code = main(
        [
            "notes",
            "apply",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic planned note",
            "--body-text",
            "Synthetic note body.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True


def test_cli_icloud_drive_content_uses_exact_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    search_exit_code = main(
        [
            "icloud-drive",
                "search",
                "--json",
                "--query",
                "synthetic-packet",
                "--root",
                str(root),
            ]
    )
    assert search_exit_code == 0
    parsed_search = json.loads(capsys.readouterr().out)

    exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            parsed_search["results"][0]["handle"],
            "--max-chars",
            "4000",
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "icloud_drive"
    assert parsed["status"] == "ok"
    assert parsed["result"]["content_text"] == "Synthetic iCloud content."


def test_cli_icloud_drive_plan_and_apply_create_text(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    search_exit_code = main(
        [
            "icloud-drive",
            "search",
            "--json",
            "--query",
            "Packets",
            "--root",
            str(root),
        ]
    )
    assert search_exit_code == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "create-text",
            "--parent-handle",
            parent_handle,
            "--filename",
            "new-note.md",
            "--content-text",
            "Synthetic CLI iCloud text.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    apply_exit_code = main(
        [
            "icloud-drive",
            "apply",
            "--json",
            "--operation",
            "create-text",
            "--parent-handle",
            parent_handle,
            "--filename",
            "new-note.md",
            "--content-text",
            "Synthetic CLI iCloud text.",
            "--approval-token",
            token,
            "--confirm-apply",
            "--root",
            str(root),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["name"] == "new-note.md"
    assert (root / "Packets" / "new-note.md").read_text(encoding="utf-8") == (
        "Synthetic CLI iCloud text."
    )


def test_cli_calendar_search_and_get_use_exact_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    handle = "calendar:event:v1:0123456789abcdef0123456789abcdef"

    def fake_search_calendar_events(query: str, **kwargs):
        assert query == "planning"
        assert kwargs["limit"] == 5
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "metadata",
            },
            "results": [{"handle": handle, "title": "Synthetic calendar event"}],
            "result_count": 1,
            "warnings": [],
        }

    def fake_get_calendar_event(calendar_handle: str, **kwargs):
        assert calendar_handle == handle
        assert kwargs["max_chars"] == 120
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {
                "content_inspected": True,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "content",
            },
            "result": {
                "handle": calendar_handle,
                "title": "Synthetic calendar event",
                "notes_text": "Synthetic event notes.",
                "notes_chars": 22,
                "notes_truncated": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.search_calendar_events",
        fake_search_calendar_events,
    )
    monkeypatch.setattr("local_apple_data.cli.get_calendar_event", fake_get_calendar_event)

    search_exit_code = main(
        ["calendar", "search", "--json", "--query", "planning", "--limit", "5"]
    )
    assert search_exit_code == 0
    parsed_search = json.loads(capsys.readouterr().out)
    assert parsed_search["results"][0]["handle"] == handle

    exit_code = main(
        [
            "calendar",
            "get",
            "--json",
            "--handle",
            handle,
            "--max-chars",
            "120",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "calendar"
    assert parsed["status"] == "ok"
    assert parsed["result"]["notes_text"] == "Synthetic event notes."


def test_cli_calendar_plan_and_apply_create(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic planned event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--notes",
            "Synthetic event notes.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["title"] == "Synthetic planned event"
        assert kwargs["calendar_title"] == "Synthetic Calendar"
        assert kwargs["start_date"] == "2026-06-04T17:00:00Z"
        assert kwargs["end_date"] == "2026-06-04T18:00:00Z"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "create",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "Synthetic planned event"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.apply_calendar_change",
        fake_apply_calendar_change,
    )

    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic planned event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--notes",
            "Synthetic event notes.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True


def test_cli_contacts_plan_and_apply_create(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "create",
            "--contact-type",
            "person",
            "--given-name",
            "Synthetic",
            "--family-name",
            "Created",
            "--organization-name",
            "Example Org",
            "--job-title",
            "Tester",
            "--email",
            "work=synthetic@example.invalid",
            "--phone",
            "mobile=+1 555 0101",
            "--url",
            "work=https://example.invalid/contact",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "contacts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_contact_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["contact_type"] == "person"
        assert kwargs["given_name"] == "Synthetic"
        assert kwargs["family_name"] == "Created"
        assert kwargs["organization_name"] == "Example Org"
        assert kwargs["job_title"] == "Tester"
        assert kwargs["email_addresses"] == [
            {"label": "work", "value": "synthetic@example.invalid"}
        ]
        assert kwargs["phone_numbers"] == [{"label": "mobile", "value": "+1 555 0101"}]
        assert kwargs["url_addresses"] == [
            {"label": "work", "value": "https://example.invalid/contact"}
        ]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "create",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"given_name": "Synthetic", "family_name": "Created"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.apply_contact_change",
        fake_apply_contact_change,
    )

    apply_exit_code = main(
        [
            "contacts",
            "apply",
            "--json",
            "--operation",
            "create",
            "--contact-type",
            "person",
            "--given-name",
            "Synthetic",
            "--family-name",
            "Created",
            "--organization-name",
            "Example Org",
            "--job-title",
            "Tester",
            "--email",
            "work=synthetic@example.invalid",
            "--phone",
            "mobile=+1 555 0101",
            "--url",
            "work=https://example.invalid/contact",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True
