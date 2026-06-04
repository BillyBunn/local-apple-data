from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.handles import make_int_handle
from local_apple_data.adapters.mail import (
    check_mail_schema,
    discover_mail_db_path,
    get_mail_metadata,
    mail_db_relative_path,
    search_mail_metadata,
)


def _make_mail_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE subjects (
                ROWID INTEGER PRIMARY KEY,
                subject TEXT NOT NULL
            );
            CREATE TABLE mailboxes (
                ROWID INTEGER PRIMARY KEY,
                url TEXT NOT NULL
            );
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
            INSERT INTO subjects (ROWID, subject) VALUES
              (1, 'Project Alpha update'),
              (2, 'Unrelated notice'),
              (3, 'Deleted Alpha update');
            INSERT INTO mailboxes (ROWID, url) VALUES
              (1, 'local://synthetic/INBOX');
            INSERT INTO messages
              (ROWID, subject, mailbox, date_received, date_sent, read, flagged, deleted, size)
              VALUES
              (10, 1, 1, 1000, 900, 1, 0, 0, 123),
              (11, 2, 1, 1001, 901, 0, 0, 0, 456),
              (12, 3, 1, 1002, 902, 0, 0, 1, 789);
            """
        )


def _write_emlx(
    mail_root: Path,
    rowid: int,
    mailbox: str = "Synthetic.mbox/INBOX.mbox",
) -> None:
    mime_bytes = (
        b"Subject: Synthetic availability\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Synthetic body is not read by search.\r\n"
    )
    path = mail_root / mailbox / "Messages" / f"{rowid}.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes)


def test_search_mail_metadata_returns_capped_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)

    result = search_mail_metadata("Alpha", db_path=db_path, limit=100)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["limit"] == 50
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("mail:message:v2:")
    assert result["results"][0]["handle"] != "mail:message:10"
    assert result["results"][0]["subject"] == "Project Alpha update"
    assert result["results"][0]["mailbox_name"] == "INBOX"
    assert result["results"][0]["mailbox_ref"].startswith("mailbox:")
    assert "synthetic" not in result["results"][0]["mailbox_ref"]
    assert result["results"][0]["content_status"] == "unavailable"


def test_search_mail_metadata_reports_content_status_without_reading_body(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _make_mail_db(db_path)
    _write_emlx(mail_root, 10)

    result = search_mail_metadata("Alpha", db_path=db_path)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["results"][0]["content_status"] == "available"


def test_search_mail_metadata_marks_duplicate_content_files_unavailable(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _make_mail_db(db_path)
    _write_emlx(mail_root, 10, "One.mbox/INBOX.mbox")
    _write_emlx(mail_root, 10, "Two.mbox/INBOX.mbox")

    result = search_mail_metadata("Alpha", db_path=db_path)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["results"][0]["content_status"] == "unavailable"


def test_discover_mail_db_path_uses_highest_existing_mail_version(tmp_path: Path) -> None:
    old_path = tmp_path / "Library/Mail/V10/MailData/Envelope Index"
    new_path = tmp_path / "Library/Mail/V12/MailData/Envelope Index"
    _make_mail_db(old_path)
    _make_mail_db(new_path)

    assert discover_mail_db_path(home=tmp_path) == new_path
    assert mail_db_relative_path(home=tmp_path) == Path(
        "Library/Mail/V12/MailData/Envelope Index"
    )


def test_get_mail_metadata_by_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)
    handle = search_mail_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_mail_metadata(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["subject"] == "Project Alpha update"
    assert result["result"]["read"] is True
    assert "mailbox" not in result["result"]


def test_search_mail_metadata_rejects_empty_query(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)

    result = search_mail_metadata("   ", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "empty_query"


def test_search_mail_metadata_rejects_low_quality_query(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)

    result = search_mail_metadata("%", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "broad_query"


def test_get_mail_metadata_does_not_return_deleted_message(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)
    handle = make_int_handle("mail:message", 12)

    result = get_mail_metadata(handle, db_path=db_path)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_mail_metadata_rejects_guessable_legacy_id(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)

    result = get_mail_metadata("mail:message:10", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_mail_metadata_rejects_bad_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _make_mail_db(db_path)

    result = get_mail_metadata("bad:10", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_mail_schema_warning_does_not_expose_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite"

    result = check_mail_schema(db_path=missing_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "mail_schema_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]
