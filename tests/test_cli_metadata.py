from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from local_apple_data.cli import main
from local_apple_data.adapters.mail import search_mail_metadata
from local_apple_data.handles import make_int_handle, make_opaque_handle


@pytest.fixture(autouse=True)
def _allow_synthetic_icloud_drive_root(monkeypatch):
    monkeypatch.setenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", "1")


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
              VALUES (7, 14, 'Synthetic Account', 'Synthetic Account', 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZMARKEDFORDELETION)
              VALUES
              (9, 15, 'Synthetic CLI Folder', 7, 0, 30, 0),
              (10, 15, 'Synthetic Archive', 7, 0, 31, 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES
              (8, 12, 'Synthetic planning note', 'Fallback', 'Synthetic only', 10, 20, 0, 0, 9, 1);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE1, ZTITLE, ZMARKEDFORDELETION, ZNOTE, ZFILENAME,
               ZFILESIZE, ZTYPEUTI, ZCREATIONDATE, ZMODIFICATIONDATE, ZIDENTIFIER,
               ZMERGEABLEDATA1)
              VALUES
              (18, NULL, NULL, 0, 8, 'cli-packet.pdf', 8, 'com.adobe.pdf', 11, 21,
               'CLI-ATTACHMENT-UUID', X'434C492D424C4F42');
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


def test_cli_photos_plan_accepts_update_flags(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "preview": {"operation": operation},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_photo_change", fake_plan)

    exit_code = main(
        [
            "photos",
            "plan",
            "--json",
            "--operation",
            "update-flags",
            "--handle",
            "photos:asset:v1:opaque",
            "--favorite",
            "true",
            "--expected-favorite",
            "false",
            "--expected-hidden",
            "false",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "update-flags"
    assert captured["handle"] == "photos:asset:v1:opaque"
    assert captured["favorite"] is True
    assert captured["hidden"] is None
    assert captured["expected_favorite"] is False
    assert captured["expected_hidden"] is False


def test_cli_photos_plan_accepts_delete(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "preview": {"operation": operation},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_photo_change", fake_plan)

    exit_code = main(
        [
            "photos",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            "photos:asset:v1:opaque",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "delete"
    assert captured["handle"] == "photos:asset:v1:opaque"


def test_cli_photos_plan_accepts_album_membership(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "preview": {"operation": operation},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_photo_change", fake_plan)

    exit_code = main(
        [
            "photos",
            "plan",
            "--json",
            "--operation",
            "add-to-album",
            "--handle",
            "photos:asset:v1:opaque",
            "--album-handle",
            "photos:album:v1:opaque",
            "--expected-in-album",
            "false",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "add-to-album"
    assert captured["handle"] == "photos:asset:v1:opaque"
    assert captured["album_handle"] == "photos:album:v1:opaque"
    assert captured["expected_in_album"] is False


def test_cli_photos_albums_and_album(monkeypatch, capsys) -> None:
    def fake_search_albums(query: str, **kwargs: object) -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "query": {"scope": "album_title", "query": query, **kwargs},
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    def fake_get_album(handle: str, **kwargs: object) -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "result": {"handle": handle, **kwargs},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_photo_albums", fake_search_albums)
    monkeypatch.setattr("local_apple_data.cli.get_photo_album", fake_get_album)

    exit_code = main(["photos", "albums", "--json", "--query", "Trips", "--limit", "2"])
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["query"]["query"] == "Trips"
    assert parsed["query"]["limit"] == 2

    exit_code = main(["photos", "album", "--json", "--handle", "photos:album:v1:opaque"])
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["handle"] == "photos:album:v1:opaque"


def test_cli_photos_request_access(monkeypatch, capsys) -> None:
    def fake_request_photos_full_access() -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "metadata",
            },
            "authorization_status": "authorized",
            "request_result": "granted",
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.request_photos_full_access",
        fake_request_photos_full_access,
    )

    exit_code = main(["photos", "request-access", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "photos"
    assert parsed["status"] == "ok"
    assert parsed["authorization_status"] == "authorized"
    assert parsed["request_result"] == "granted"


def test_cli_contacts_request_access(monkeypatch, capsys) -> None:
    def fake_request_contacts_access() -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "metadata",
            },
            "authorization_status": "authorized",
            "request_result": "granted",
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.request_contacts_access",
        fake_request_contacts_access,
    )

    exit_code = main(["contacts", "request-access", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "contacts"
    assert parsed["status"] == "ok"
    assert parsed["authorization_status"] == "authorized"
    assert parsed["request_result"] == "granted"


def test_cli_mail_content_uses_synthetic_db_and_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "DetachedMailRoot"
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


def test_cli_mail_fts_build_and_search_use_synthetic_paths(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    index_path = tmp_path / "private-mail-fts.sqlite"
    _mail_db(db_path)
    _write_emlx(
        mail_root,
        7,
        "From: CLI Billing <billing@example.invalid>\r\n"
        "Subject: Synthetic planning mail\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic CLI FTS subscription token.\r\n",
    )

    build_exit = main(
        [
            "mail",
            "fts-build",
            "--json",
            "--after",
            "0",
            "--before",
            "20",
            "--confirm-index",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
            "--index",
            str(index_path),
        ]
    )
    build = json.loads(capsys.readouterr().out)
    search_exit = main(
        [
            "mail",
            "fts-search",
            "--json",
            "--query",
            "subscription",
            "--scope",
            "body",
            "--after",
            "0",
            "--before",
            "20",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
            "--index",
            str(index_path),
        ]
    )
    search = json.loads(capsys.readouterr().out)

    assert build_exit == 0
    assert search_exit == 0
    assert build["status"] == "ok"
    assert build["result"]["index_path_returned"] is False
    assert search["status"] == "ok"
    assert search["result_count"] == 1
    assert search["results"][0]["matched_scope"] == "body"
    assert str(index_path) not in json.dumps(build, sort_keys=True)
    assert str(index_path) not in json.dumps(search, sort_keys=True)


def test_cli_mail_fts_build_rejects_reset_with_cursor(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    index_path = tmp_path / "private-mail-fts.sqlite"
    _mail_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (2, "Synthetic second planning mail"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (8, 2, 1, 9, 8, 0, 0, 0, 12),
        )
    for rowid in (7, 8):
        _write_emlx(
            mail_root,
            rowid,
            "Subject: Synthetic planning mail\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic CLI reset cursor token.\r\n",
        )

    first_exit = main(
        [
            "mail",
            "fts-build",
            "--json",
            "--after",
            "0",
            "--before",
            "20",
            "--limit",
            "1",
            "--confirm-index",
            "--reset",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
            "--index",
            str(index_path),
        ]
    )
    first = json.loads(capsys.readouterr().out)
    second_exit = main(
        [
            "mail",
            "fts-build",
            "--json",
            "--after",
            "0",
            "--before",
            "20",
            "--limit",
            "1",
            "--cursor",
            first["next_cursor"],
            "--confirm-index",
            "--reset",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
            "--index",
            str(index_path),
        ]
    )
    second = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert first["status"] == "ok"
    assert first["next_cursor"] == "1"
    assert second_exit == 0
    assert second["status"] == "error"
    assert second["warnings"][0]["code"] == "invalid_reset_cursor"


def test_cli_mail_content_offset_pages_synthetic_body(
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
        "abcdefghijklmnopqrstuvwxyz\r\n",
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
            "8",
            "--offset",
            "8",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["content_text"] == "ijklmnop"
    assert parsed["result"]["next_offset"] == 16


def test_cli_mail_body_and_attachment_search_use_date_bounds(
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
        "MIME-Version: 1.0\r\n"
        "From: Billing <billing@example.invalid>\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "CLI-only renewal body for payer@example.invalid.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        'Content-Disposition: attachment; filename="cli-note.txt"\r\n'
        "\r\n"
        "CLI attachment contenttoken for payer@example.invalid.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="cli-renewal.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "Q0xJLU1BSUw=\r\n"
        "--BOUNDARY--\r\n",
    )

    body_exit = main(
        [
            "mail",
            "body-search",
            "--json",
            "--query",
            "renewal",
            "--after",
            "0",
            "--before",
            "20",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert body_exit == 0
    body_result = json.loads(capsys.readouterr().out)
    assert body_result["status"] == "ok"
    assert body_result["results"][0]["matched_scope"] == "body"
    assert "p***@example.invalid" in body_result["results"][0]["snippet"]

    attachment_exit = main(
        [
            "mail",
            "attachment-search",
            "--json",
            "--query",
            "renewal",
            "--after",
            "0",
            "--before",
            "20",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert attachment_exit == 0
    attachment_result = json.loads(capsys.readouterr().out)
    assert attachment_result["status"] == "ok"
    assert attachment_result["results"][0]["attachment"]["filename"] == "cli-renewal.pdf"

    attachment_content_exit = main(
        [
            "mail",
            "attachment-search",
            "--json",
            "--query",
            "contenttoken",
            "--after",
            "0",
            "--before",
            "20",
            "--include-content",
            "--max-snippet-chars",
            "80",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert attachment_content_exit == 0
    attachment_content = json.loads(capsys.readouterr().out)
    assert attachment_content["status"] == "ok"
    assert attachment_content["results"][0]["matched_scope"] == "attachment_content"
    assert attachment_content["results"][0]["attachment"]["filename"] == "cli-note.txt"
    assert "p***@example.invalid" in attachment_content["results"][0]["snippet"]

    advanced_exit = main(
        [
            "mail",
            "advanced-search",
            "--json",
            "--query",
            "billing",
            "--scope",
            "from",
            "--after",
            "0",
            "--before",
            "20",
            "--has-attachments",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert advanced_exit == 0
    advanced_result = json.loads(capsys.readouterr().out)
    assert advanced_result["status"] == "ok"
    assert advanced_result["results"][0]["matched_scopes"] == ["from"]
    assert advanced_result["results"][0]["from"]["previews"] == ["b***@example.invalid"]


def test_cli_mail_attachments_and_export_use_exact_handles(
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
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic CLI body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="cli-packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "Q0xJLU1BSUw=\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("planning", db_path=db_path)["results"][0]["handle"]

    list_exit_code = main(
        [
            "mail",
            "attachments",
            "--json",
            "--handle",
            message_handle,
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert list_exit_code == 0
    listed = json.loads(capsys.readouterr().out)
    attachment_handle = listed["results"][0]["handle"]
    assert attachment_handle.startswith("mail:attachment:v1:")

    export_exit_code = main(
        [
            "mail",
            "export-attachment",
            "--json",
            "--message-handle",
            message_handle,
            "--handle",
            attachment_handle,
            "--output-dir",
            str(tmp_path / "exports"),
            "--filename",
            "../review packet.pdf",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert export_exit_code == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["status"] == "ok"
    assert exported["result"]["exported_filename"] == "review-packet.pdf"
    assert exported["result"]["exported_bytes"] == 8
    assert Path(exported["result"]["exported_path"]).read_bytes() == b"CLI-MAIL"
    assert str(mail_root) not in json.dumps(exported)


def test_cli_mail_plan_and_apply_create_draft(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--cc",
            "copy@example.invalid",
            "--subject",
            "Synthetic planned draft",
            "--body-text",
            "Synthetic draft body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "create-draft"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["cc"] == ["copy@example.invalid"]
        assert kwargs["bcc"] == []
        assert kwargs["subject"] == "Synthetic planned draft"
        assert kwargs["body_text"] == "Synthetic draft body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"subject": "Synthetic planned draft"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--cc",
            "copy@example.invalid",
            "--subject",
            "Synthetic planned draft",
            "--body-text",
            "Synthetic draft body.",
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


def test_cli_mail_sender_handle_forwards_to_plan_and_apply(monkeypatch, capsys) -> None:
    sender_handle = make_opaque_handle("mail:sender", "synthetic-account\x00synthetic-sender")
    calls: list[str] = []

    def fake_plan_mail_change(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "create-draft"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["cc"] == []
        assert kwargs["bcc"] == []
        assert kwargs["subject"] == "Synthetic sender CLI draft"
        assert kwargs["body_text"] == "Synthetic body."
        assert kwargs["sender_handle"] == sender_handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {"approval": {"approval_fingerprint": "synthetic-mail-sender"}},
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "create-draft"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["cc"] == []
        assert kwargs["bcc"] == []
        assert kwargs["subject"] == "Synthetic sender CLI draft"
        assert kwargs["body_text"] == "Synthetic body."
        assert kwargs["sender_handle"] == sender_handle
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-mail-sender"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"sender_selection_confirmed": True},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic sender CLI draft",
            "--body-text",
            "Synthetic body.",
            "--sender-handle",
            sender_handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ok"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic sender CLI draft",
            "--body-text",
            "Synthetic body.",
            "--sender-handle",
            sender_handle,
            "--approval-token",
            "mail-apply:v1:synthetic-mail-sender",
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "ok"
    assert applied["read_back"]["sender_selection_confirmed"] is True
    assert calls == ["plan", "apply"]


def test_cli_mail_signature_handle_forwards_to_plan_and_apply(monkeypatch, capsys) -> None:
    signature_handle = make_opaque_handle("mail:signature", "Synthetic Signature")
    calls: list[str] = []

    def fake_plan_mail_change(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "send-message"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["subject"] == "Synthetic signature CLI send"
        assert kwargs["body_text"] == "Synthetic body."
        assert kwargs["signature_handle"] == signature_handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {"approval": {"approval_fingerprint": "synthetic-mail-signature"}},
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "send-message"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["subject"] == "Synthetic signature CLI send"
        assert kwargs["body_text"] == "Synthetic body."
        assert kwargs["signature_handle"] == signature_handle
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-mail-signature"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"signature_selection_confirmed": True},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic signature CLI send",
            "--body-text",
            "Synthetic body.",
            "--signature-handle",
            signature_handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ok"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic signature CLI send",
            "--body-text",
            "Synthetic body.",
            "--signature-handle",
            signature_handle,
            "--approval-token",
            "mail-apply:v1:synthetic-mail-signature",
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "ok"
    assert applied["read_back"]["signature_selection_confirmed"] is True
    assert calls == ["plan", "apply"]


def test_cli_mail_template_handle_forwards_to_plan_and_apply(monkeypatch, capsys) -> None:
    template_handle = make_opaque_handle("mail:template", "synthetic-template")
    calls: list[str] = []

    def fake_plan_mail_change(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "send-message"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["template_handle"] == template_handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {"approval": {"approval_fingerprint": "synthetic-mail-template"}},
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "send-message"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["template_handle"] == template_handle
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-mail-template"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"template_selection_confirmed": True},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--template-handle",
            template_handle,
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--template-handle",
            template_handle,
            "--approval-token",
            "mail-apply:v1:synthetic-mail-template",
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "ok"
    assert applied["read_back"]["template_selection_confirmed"] is True
    assert calls == ["plan", "apply"]


def test_cli_mail_plan_search_triage_forwards_exact_inputs(monkeypatch, capsys, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    db_path = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    index_path = tmp_path / "mail-fts.sqlite"

    def fake_plan_mail_search_triage(operation: str, query: str, **kwargs):
        captured["operation"] = operation
        captured["query"] = query
        captured["kwargs"] = kwargs
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "preview": {"query_result_selection": {"selected_result_count": 2}},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_search_triage", fake_plan_mail_search_triage)

    exit_code = main(
        [
            "mail",
            "plan-search-triage",
            "--json",
            "--operation",
            "mark-read",
            "--query",
            "subscription",
            "--scope",
            "body",
            "--after",
            "2026-01-01",
            "--before",
            "2026-06-01",
            "--cursor",
            "20",
            "--limit",
            "2",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
            "--index",
            str(index_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert captured["operation"] == "mark-read"
    assert captured["query"] == "subscription"
    kwargs = captured["kwargs"]
    assert kwargs["search_source"] == "fts"
    assert kwargs["scopes"] == ["body"]
    assert kwargs["after"] == "2026-01-01"
    assert kwargs["before"] == "2026-06-01"
    assert kwargs["cursor"] == "20"
    assert kwargs["limit"] == 2
    assert kwargs["db_path"] == db_path
    assert kwargs["mail_root"] == mail_root
    assert kwargs["index_path"] == index_path


def test_cli_mailbox_plan_and_apply_forward_exact_inputs(monkeypatch, capsys) -> None:
    calls: list[str] = []
    mailbox_handle = make_opaque_handle("mail:mailbox", "synthetic", "LAD-TEST-old")

    def fake_plan_mailbox_change(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "rename-mailbox"
        assert kwargs["mailbox_handle"] == mailbox_handle
        assert kwargs["new_mailbox_name"] == "LAD-TEST-new"
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply_mailbox_change(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "rename-mailbox"
        assert kwargs["mailbox_handle"] == mailbox_handle
        assert kwargs["new_mailbox_name"] == "LAD-TEST-new"
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-mailbox"
        assert kwargs["confirm_apply"] is True
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.plan_mail_mailbox_change", fake_plan_mailbox_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_mailbox_change", fake_apply_mailbox_change)

    plan_exit = main(
        [
            "mail",
            "plan-mailbox",
            "--json",
            "--operation",
            "rename-mailbox",
            "--mailbox-handle",
            mailbox_handle,
            "--new-mailbox-name",
            "LAD-TEST-new",
        ]
    )
    assert plan_exit == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    apply_exit = main(
        [
            "mail",
            "apply-mailbox",
            "--json",
            "--operation",
            "rename-mailbox",
            "--mailbox-handle",
            mailbox_handle,
            "--new-mailbox-name",
            "LAD-TEST-new",
            "--approval-token",
            "mail-apply:v1:synthetic-mailbox",
            "--confirm-apply",
        ]
    )
    assert apply_exit == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert calls == ["plan", "apply"]


def test_cli_cleanup_plan_and_apply_forward_exact_inputs(monkeypatch, capsys) -> None:
    calls: list[str] = []
    message_handle = make_int_handle("mail:message", 30)

    def fake_plan_cleanup(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "permanent-delete-message"
        assert kwargs["message_handle"] == message_handle
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply_cleanup(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "permanent-delete-message"
        assert kwargs["message_handle"] == message_handle
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-cleanup"
        assert kwargs["confirm_apply"] is True
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.plan_mail_cleanup", fake_plan_cleanup)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_cleanup", fake_apply_cleanup)

    plan_exit = main(
        [
            "mail",
            "plan-cleanup",
            "--json",
            "--operation",
            "permanent-delete-message",
            "--message-handle",
            message_handle,
        ]
    )
    assert plan_exit == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    apply_exit = main(
        [
            "mail",
            "apply-cleanup",
            "--json",
            "--operation",
            "permanent-delete-message",
            "--message-handle",
            message_handle,
            "--approval-token",
            "mail-apply:v1:synthetic-cleanup",
            "--confirm-apply",
        ]
    )
    assert apply_exit == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert calls == ["plan", "apply"]


def test_cli_mail_attachment_paths_forward_to_plan_and_apply(monkeypatch, capsys, tmp_path: Path) -> None:
    attachment_path = str(tmp_path / "packet.pdf")
    calls: list[str] = []

    def fake_plan_mail_change(operation: str, **kwargs):
        calls.append("plan")
        assert operation == "create-draft"
        assert kwargs["attachment_paths"] == [attachment_path]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {"approval": {"approval_fingerprint": "synthetic-mail-attachment"}},
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        calls.append("apply")
        assert operation == "create-draft"
        assert kwargs["attachment_paths"] == [attachment_path]
        assert kwargs["approval_token"] == "mail-apply:v1:synthetic-mail-attachment"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"attachment_count": 1, "attachment_paths_returned": False},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic attachment CLI draft",
            "--body-text",
            "Synthetic body.",
            "--attachment-path",
            attachment_path,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ok"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "create-draft",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic attachment CLI draft",
            "--body-text",
            "Synthetic body.",
            "--attachment-path",
            attachment_path,
            "--approval-token",
            "mail-apply:v1:synthetic-mail-attachment",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert calls == ["plan", "apply"]


def test_cli_contacts_plan_and_apply_update(monkeypatch, capsys) -> None:
    handle = "contacts:contact:v1:abc"
    current_sha = "a" * 64

    def fake_plan_contact_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["given_name"] == "Renamed"
        assert kwargs["family_name"] is None
        assert kwargs["email_addresses"] is None
        assert kwargs["phone_numbers"] is None
        assert kwargs["url_addresses"] is None
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle, "expected_current_sha256": current_sha},
                "proposed": {"given_name": "Renamed"},
                "approval": {"approval_fingerprint": "fp"},
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_contact_change",
        fake_plan_contact_change,
    )

    plan_exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--given-name",
            "Renamed",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "contacts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_contact_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["given_name"] == "Renamed"
        assert kwargs["family_name"] is None
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"given_name": "Renamed", "family_name": "Contact"},
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
            "update",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--given-name",
            "Renamed",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "update"


def test_cli_contacts_plan_and_apply_delete(monkeypatch, capsys) -> None:
    handle = "contacts:contact:v1:abc"
    current_sha = "b" * 64

    def fake_plan_contact_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["given_name"] is None
        assert kwargs["family_name"] is None
        assert kwargs["email_addresses"] is None
        assert kwargs["phone_numbers"] is None
        assert kwargs["url_addresses"] is None
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "delete",
                "target": {"handle": handle, "expected_current_sha256": current_sha},
                "proposed": {"effect": "delete_exact_contact"},
                "approval": {"approval_fingerprint": "fp-delete"},
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_contact_change",
        fake_plan_contact_change,
    )

    plan_exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "contacts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_contact_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["given_name"] is None
        assert kwargs["family_name"] is None
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"deleted": True, "verified_absent": True},
            "result_count": 0,
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
            "delete",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "delete"
    assert parsed["result_count"] == 0


def test_cli_mail_plan_and_apply_send_message(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic outbound",
            "--body-text",
            "Synthetic outbound body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "send_message"
    assert plan["preview"]["proposed"]["send_permitted"] is True
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "send-message"
        assert kwargs["to"] == ["synthetic@example.invalid"]
        assert kwargs["subject"] == "Synthetic outbound"
        assert kwargs["body_text"] == "Synthetic outbound body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "subject": "Synthetic outbound",
                "sent_copy_confirmed": True,
                "body_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "send-message",
            "--to",
            "synthetic@example.invalid",
            "--subject",
            "Synthetic outbound",
            "--body-text",
            "Synthetic outbound body.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["body_returned"] is False


def test_cli_mail_plan_and_apply_reply_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v1:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "reply-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["body_text"] == "Synthetic reply body."
        assert kwargs["to"] == []
        assert kwargs["cc"] == []
        assert kwargs["bcc"] == []
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "reply_message",
                "proposed": {
                    "kind": "mail_reply",
                    "reply_mode": "sender_only",
                    "irreversible_external_send": True,
                    "body_returned": False,
                },
                "approval": {"approval_fingerprint": "reply-fingerprint"},
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "reply-message",
            "--message-handle",
            handle,
            "--body-text",
            "Synthetic reply body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "reply_message"
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "reply-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["body_text"] == "Synthetic reply body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "reply_copy_confirmed": True,
                "sent_copy_confirmed": True,
                "body_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "reply-message",
            "--message-handle",
            handle,
            "--body-text",
            "Synthetic reply body.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["reply_copy_confirmed"] is True
    assert parsed["read_back"]["body_returned"] is False


def test_cli_mail_plan_and_apply_bulk_triage_repeated_handles(monkeypatch, capsys) -> None:
    first = "mail:message:v2:first"
    second = "mail:message:v2:second"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "mark-read"
        assert kwargs["message_handle"] == first
        assert kwargs["message_handles"] == [second]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "mark_read",
                "proposed": {"kind": "mail_bulk_triage", "message_count": 2},
                "approval": {"approval_fingerprint": "bulk-fingerprint"},
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "mark-read",
            "--message-handle",
            first,
            "--message-handle",
            second,
        ]
    )

    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["kind"] == "mail_bulk_triage"
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "mark-read"
        assert kwargs["message_handle"] == first
        assert kwargs["message_handles"] == [second]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"kind": "mail_bulk_triage", "applied_count": 2},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)
    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "mark-read",
            "--message-handle",
            first,
            "--message-handle",
            second,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["kind"] == "mail_bulk_triage"


def test_cli_mail_plan_and_apply_reply_all_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v1:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "reply-all-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["body_text"] == "Synthetic reply-all body."
        assert kwargs["to"] == []
        assert kwargs["cc"] == []
        assert kwargs["bcc"] == []
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "reply_all_message",
                "proposed": {
                    "kind": "mail_reply",
                    "reply_mode": "reply_all",
                    "irreversible_external_send": True,
                    "body_returned": False,
                },
                "approval": {"approval_fingerprint": "reply-all-fingerprint"},
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "reply-all-message",
            "--message-handle",
            handle,
            "--body-text",
            "Synthetic reply-all body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "reply_all_message"
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "reply-all-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["body_text"] == "Synthetic reply-all body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "reply_copy_confirmed": True,
                "reply_mode": "reply_all",
                "sent_copy_confirmed": True,
                "body_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "reply-all-message",
            "--message-handle",
            handle,
            "--body-text",
            "Synthetic reply-all body.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["reply_copy_confirmed"] is True
    assert parsed["read_back"]["reply_mode"] == "reply_all"
    assert parsed["read_back"]["body_returned"] is False


def test_cli_mail_plan_and_apply_forward_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "forward-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["to"] == ["synthetic-forward@example.invalid"]
        assert kwargs["body_text"] == "Synthetic forward note."
        assert kwargs["subject"] == ""
        assert kwargs["include_source_attachments"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "forward_message",
                "proposed": {
                    "kind": "mail_forward",
                    "irreversible_external_send": True,
                    "source_attachments_permitted": True,
                    "source_non_text_parts_permitted": True,
                    "source_non_body_parts_permitted": True,
                    "body_returned": False,
                },
                "approval": {"approval_fingerprint": "forward-fingerprint"},
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "forward-message",
            "--message-handle",
            handle,
            "--to",
            "synthetic-forward@example.invalid",
            "--body-text",
            "Synthetic forward note.",
            "--include-source-attachments",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "forward_message"
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "forward-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["to"] == ["synthetic-forward@example.invalid"]
        assert kwargs["body_text"] == "Synthetic forward note."
        assert kwargs["include_source_attachments"] is True
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "forward_copy_confirmed": True,
                "sent_copy_confirmed": True,
                "source_attachments_permitted": True,
                "source_non_text_parts_permitted": True,
                "source_non_body_parts_permitted": True,
                "body_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "forward-message",
            "--message-handle",
            handle,
            "--to",
            "synthetic-forward@example.invalid",
            "--body-text",
            "Synthetic forward note.",
            "--approval-token",
            token,
            "--confirm-apply",
            "--include-source-attachments",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["forward_copy_confirmed"] is True
    assert parsed["read_back"]["source_attachments_permitted"] is True
    assert parsed["read_back"]["source_non_text_parts_permitted"] is True
    assert parsed["read_back"]["source_non_body_parts_permitted"] is True
    assert parsed["read_back"]["body_returned"] is False


def test_cli_mail_plan_and_apply_mark_read(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "mark-read"
        assert kwargs["message_handle"] == handle
        assert kwargs["subject"] == ""
        assert kwargs["body_text"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "mark_read",
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "mark-read"
        assert kwargs["message_handle"] == handle
        assert kwargs["approval_token"] == "mail-apply:v1:abc123"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "read": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "mark-read",
            "--message-handle",
            handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "mark_read"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "mark-read",
            "--message-handle",
            handle,
            "--approval-token",
            "mail-apply:v1:abc123",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["read"] is True


def test_cli_mail_plan_and_apply_flag_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "flag-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["subject"] == ""
        assert kwargs["body_text"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "flag_message",
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "flag-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["approval_token"] == "mail-apply:v1:abc123"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "flagged": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "flag-message",
            "--message-handle",
            handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "flag_message"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "flag-message",
            "--message-handle",
            handle,
            "--approval-token",
            "mail-apply:v1:abc123",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["flagged"] is True


def test_cli_mail_plan_and_apply_archive_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "archive-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["subject"] == ""
        assert kwargs["body_text"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "archive_message",
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "archive-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["approval_token"] == "mail-apply:v1:abc123"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "mailbox_ref": "mailbox:archive"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "archive-message",
            "--message-handle",
            handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "archive_message"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "archive-message",
            "--message-handle",
            handle,
            "--approval-token",
            "mail-apply:v1:abc123",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["mailbox_ref"] == "mailbox:archive"


def test_cli_mail_plan_and_apply_trash_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "trash-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["subject"] == ""
        assert kwargs["body_text"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "trash_message",
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "trash-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["approval_token"] == "mail-apply:v1:abc123"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "mailbox_ref": "mailbox:trash"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "trash-message",
            "--message-handle",
            handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "trash_message"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "trash-message",
            "--message-handle",
            handle,
            "--approval-token",
            "mail-apply:v1:abc123",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["mailbox_ref"] == "mailbox:trash"


def test_cli_mail_mailboxes_and_mailbox_use_exact_handles(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "mail.sqlite"
    _mail_db(db_path)

    exit_code = main(["mail", "mailboxes", "--json", "--query", "INBOX", "--db", str(db_path)])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "mail"
    assert parsed["result_count"] == 1
    handle = parsed["results"][0]["handle"]
    assert handle.startswith("mail:mailbox:v1:")

    get_exit_code = main(["mail", "mailbox", "--json", "--handle", handle, "--db", str(db_path)])
    assert get_exit_code == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["status"] == "ok"
    assert detail["result"]["handle"] == handle

    search_exit_code = main(
        [
            "mail",
            "search",
            "--json",
            "--query",
            "planning",
            "--mailbox-handle",
            handle,
            "--db",
            str(db_path),
        ]
    )
    assert search_exit_code == 0
    search = json.loads(capsys.readouterr().out)
    assert search["status"] == "ok"
    assert search["query"]["mailbox_filter"] == "exact_handle"
    assert search["result_count"] == 1

    messages_exit_code = main(
        [
            "mail",
            "mailbox-messages",
            "--json",
            "--handle",
            handle,
            "--after",
            "0",
            "--before",
            "20",
            "--db",
            str(db_path),
        ]
    )
    assert messages_exit_code == 0
    messages = json.loads(capsys.readouterr().out)
    assert messages["status"] == "ok"
    assert messages["query"]["scope"] == "selected_mailbox_messages"
    assert messages["content_returned"] is False
    assert messages["result_count"] == 1


def test_cli_mail_plan_and_apply_move_message(monkeypatch, capsys) -> None:
    handle = "mail:message:v2:synthetic"
    target_handle = "mail:mailbox:v1:synthetic"

    def fake_plan_mail_change(operation: str, **kwargs):
        assert operation == "move-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["target_mailbox_handle"] == target_handle
        assert kwargs["subject"] == ""
        assert kwargs["body_text"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "move_message",
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_mail_change(operation: str, **kwargs):
        assert operation == "move-message"
        assert kwargs["message_handle"] == handle
        assert kwargs["target_mailbox_handle"] == target_handle
        assert kwargs["approval_token"] == "mail-apply:v1:abc123"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "mailbox_ref": "mailbox:projects"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_mail_change", fake_plan_mail_change)
    monkeypatch.setattr("local_apple_data.cli.apply_mail_change", fake_apply_mail_change)

    plan_exit_code = main(
        [
            "mail",
            "plan",
            "--json",
            "--operation",
            "move-message",
            "--message-handle",
            handle,
            "--target-mailbox-handle",
            target_handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "move_message"

    apply_exit_code = main(
        [
            "mail",
            "apply",
            "--json",
            "--operation",
            "move-message",
            "--message-handle",
            handle,
            "--target-mailbox-handle",
            target_handle,
            "--approval-token",
            "mail-apply:v1:abc123",
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["mailbox_ref"] == "mailbox:projects"


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


def test_cli_notes_folders_and_folder_use_exact_handles(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)

    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folders = json.loads(capsys.readouterr().out)
    assert folders["status"] == "ok"
    assert folders["result_count"] == 1
    folder_handle = folders["results"][0]["handle"]
    assert folder_handle.startswith("notes:folder:v1:")
    assert folders["results"][0]["folder_content_returned"] is False

    folder_exit_code = main(
        ["notes", "folder", "--json", "--handle", folder_handle, "--db", str(db_path)]
    )
    assert folder_exit_code == 0
    folder = json.loads(capsys.readouterr().out)
    assert folder["status"] == "ok"
    assert folder["result"]["handle"] == folder_handle
    assert folder["result"]["title"] == "Synthetic CLI Folder"


def test_cli_notes_folder_items_uses_exact_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (11, 15, 'Synthetic CLI Child Folder', 7, 9, 0, 32, NULL, 0)
            """
        )

    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI Folder", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    items_exit_code = main(
        [
            "notes",
            "folder-items",
            "--json",
            "--handle",
            folder_handle,
            "--limit",
            "10",
            "--db",
            str(db_path),
        ]
    )

    assert items_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["folder"]["handle"] == folder_handle
    assert parsed["result_count"] == 1
    assert parsed["child_folder_count"] == 1
    assert parsed["results"][0]["title"] == "Synthetic planning note"
    assert parsed["child_folders"][0]["title"] == "Synthetic CLI Child Folder"
    assert parsed["folder_content_returned"] is False
    assert parsed["note_content_returned"] is False


def test_cli_notes_folder_tree_uses_exact_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (11, 15, 'Synthetic CLI Child Folder', 7, 9, 0, 32, NULL, 0)
            """
        )

    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI Folder", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    tree_exit_code = main(
        [
            "notes",
            "folder-tree",
            "--json",
            "--handle",
            folder_handle,
            "--depth",
            "2",
            "--limit",
            "10",
            "--db",
            str(db_path),
        ]
    )

    assert tree_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["folder"]["handle"] == folder_handle
    assert parsed["query"]["recursive"] is True
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["title"] == "Synthetic CLI Child Folder"
    assert parsed["results"][0]["parent_handle"] == folder_handle
    assert parsed["folder_content_returned"] is False
    assert parsed["note_content_returned"] is False


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


def test_cli_notes_attachments_and_export_use_exact_handles(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    notes_container = tmp_path / "notes-container"
    output_dir = tmp_path / "exports"
    _notes_db(db_path)
    media_path = (
        notes_container
        / "Accounts"
        / "LocalAccount"
        / "Media"
        / "CLI-ATTACHMENT-UUID"
        / "Files"
        / "cli-packet.pdf"
    )
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"CLI-MEDIA")

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

    attachments_exit_code = main(
        [
            "notes",
            "attachments",
            "--json",
            "--handle",
            parsed_search["results"][0]["handle"],
            "--db",
            str(db_path),
            "--notes-container",
            str(notes_container),
        ]
    )
    assert attachments_exit_code == 0
    attachments = json.loads(capsys.readouterr().out)
    assert attachments["status"] == "ok"
    assert attachments["result_count"] == 1
    assert attachments["results"][0]["handle"].startswith("notes:attachment:v1:")

    export_exit_code = main(
        [
            "notes",
            "export-attachment",
            "--json",
            "--handle",
            attachments["results"][0]["handle"],
            "--output-dir",
            str(output_dir),
            "--filename",
            "../review packet.pdf",
            "--db",
            str(db_path),
            "--notes-container",
            str(notes_container),
        ]
    )
    assert export_exit_code == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["status"] == "ok"
    assert exported["result"]["exported_filename"] == "review-packet.pdf"
    assert Path(exported["result"]["exported_path"]).read_bytes() == b"CLI-MEDIA"
    assert str(media_path) not in str(exported)


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


def test_cli_notes_plan_rejects_icloud_drive_only_operations(capsys) -> None:
    for operation in ("trash-text", "rename-text", "copy-text", "move-text"):
        with pytest.raises(SystemExit) as exc_info:
            main(["notes", "plan", "--json", "--operation", operation])

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "invalid choice" in captured.err


def test_cli_notes_plan_and_apply_create_with_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic folder planned note",
            "--folder-handle",
            folder_handle,
            "--body-text",
            "Synthetic note body.",
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    assert plan["preview"]["target"]["folder_handle"] == folder_handle

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["title"] == "Synthetic folder planned note"
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["body_text"] == "Synthetic note body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"title": "Synthetic folder planned note"},
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
            "Synthetic folder planned note",
            "--folder-handle",
            folder_handle,
            "--body-text",
            "Synthetic note body.",
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_plan_and_apply_create_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "create-folder",
            "--title",
            "Synthetic child folder",
            "--folder-handle",
            parent_handle,
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    assert plan["preview"]["operation"] == "create_folder"
    assert plan["preview"]["target"]["parent_folder_handle"] == parent_handle

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "create-folder"
        assert kwargs["title"] == "Synthetic child folder"
        assert kwargs["folder_handle"] == parent_handle
        assert kwargs["body_text"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "title": "Synthetic child folder",
                "parent_folder_handle": parent_handle,
                "parent_folder_confirmed": True,
                "folder_content_returned": False,
            },
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
            "create-folder",
            "--title",
            "Synthetic child folder",
            "--folder-handle",
            parent_handle,
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["read_back"]["parent_folder_confirmed"] is True


def test_cli_notes_plan_and_apply_rename_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "CLI", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "rename-folder",
            "--title",
            "CLI Renamed Folder",
            "--folder-handle",
            folder_handle,
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    expected_sha = plan["preview"]["target"]["expected_current_sha256"]
    assert plan["preview"]["operation"] == "rename_folder"
    assert plan["preview"]["target"]["folder_handle"] == folder_handle

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "rename-folder"
        assert kwargs["title"] == "CLI Renamed Folder"
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["expected_current_sha256"] == expected_sha
        assert kwargs["body_text"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "title": "CLI Renamed Folder",
                "folder_handle": folder_handle,
                "renamed": True,
                "folder_content_returned": False,
            },
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
            "rename-folder",
            "--title",
            "CLI Renamed Folder",
            "--folder-handle",
            folder_handle,
            "--expected-current-sha256",
            expected_sha,
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["read_back"]["renamed"] is True


def test_cli_notes_plan_and_apply_delete_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (11, 15, 'Synthetic CLI Child Folder', 7, 9, 0, 32, NULL, 0)
            """
        )
    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "Child", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "delete-folder",
            "--folder-handle",
            folder_handle,
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    expected_sha = plan["preview"]["target"]["expected_current_sha256"]
    assert plan["preview"]["operation"] == "delete_folder"
    assert plan["preview"]["target"]["folder_handle"] == folder_handle

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "delete-folder"
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["expected_current_sha256"] == expected_sha
        assert kwargs["title"] == ""
        assert kwargs["body_text"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "folder_handle": folder_handle,
                "deleted": True,
                "verified_absent": True,
                "folder_content_returned": False,
            },
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
            "delete-folder",
            "--folder-handle",
            folder_handle,
            "--expected-current-sha256",
            expected_sha,
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["read_back"]["verified_absent"] is True


def test_cli_notes_plan_and_apply_move_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES (11, 15, 'Synthetic CLI Child Folder', 7, 9, 0, 32, NULL, 0)
            """
        )
    folders_exit_code = main(
        ["notes", "folders", "--json", "--query", "Child", "--db", str(db_path)]
    )
    assert folders_exit_code == 0
    folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    targets_exit_code = main(
        ["notes", "folders", "--json", "--query", "Archive", "--db", str(db_path)]
    )
    assert targets_exit_code == 0
    target_folder_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    expected_sha = hashlib.sha256("Synthetic CLI Child Folder".encode("utf-8")).hexdigest()
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "move-folder",
            "--folder-handle",
            folder_handle,
            "--target-folder-handle",
            target_folder_handle,
            "--expected-current-sha256",
            expected_sha,
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    assert plan["preview"]["operation"] == "move_folder"
    assert plan["preview"]["target"]["folder_handle"] == folder_handle
    assert plan["preview"]["target"]["target_folder_handle"] == target_folder_handle

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "move-folder"
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["target_folder_handle"] == target_folder_handle
        assert kwargs["expected_current_sha256"] == expected_sha
        assert kwargs["title"] == ""
        assert kwargs["body_text"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "folder_handle": folder_handle,
                "target_folder_handle": target_folder_handle,
                "moved": True,
                "target_folder_confirmed": True,
                "folder_content_returned": False,
            },
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
            "move-folder",
            "--folder-handle",
            folder_handle,
            "--target-folder-handle",
            target_folder_handle,
            "--expected-current-sha256",
            expected_sha,
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["read_back"]["target_folder_confirmed"] is True


def test_cli_notes_plan_and_apply_append(monkeypatch, capsys) -> None:
    handle = make_int_handle("notes:note", 20)
    current_sha = hashlib.sha256("Current note body".encode("utf-8")).hexdigest()
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "append-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-text",
            "Appended note body.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "append-text"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["body_text"] == "Appended note body."
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"content_text": "Current note body\nAppended note body."},
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
            "append-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-text",
            "Appended note body.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_plan_and_apply_replace(monkeypatch, capsys) -> None:
    handle = make_int_handle("notes:note", 20)
    current_sha = hashlib.sha256("Current note body".encode("utf-8")).hexdigest()
    replacement_text = "Replacement note body."
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "replace-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-text",
            replacement_text,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "replace-text"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["body_text"] == replacement_text
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"content_text": replacement_text},
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
            "replace-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-text",
            replacement_text,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_content_forwards_html_format(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    handle = make_int_handle("notes:note", 20)

    def fake_get_notes_content(handle_arg: str, **kwargs):
        assert kwargs["content_format"] == "html"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "content"},
            "result": {
                "handle": handle_arg,
                "content_format": "html",
                "content_text": "Rich body",
                "content_html": "<p>Rich body</p>",
                "content_html_truncated": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.get_notes_content", fake_get_notes_content)
    exit_code = main(
        ["notes", "content", "--json", "--handle", handle, "--content-format", "html"]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["content_format"] == "html"
    assert parsed["result"]["content_html"] == "<p>Rich body</p>"


def test_cli_notes_plan_and_apply_create_html(monkeypatch, capsys) -> None:
    body_html = "<h1>Rich note</h1><p>Rich body.</p>"
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "create-html",
            "--title",
            "Rich note",
            "--body-html",
            body_html,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["format"] == "rich_text_create"
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "create-html"
        assert kwargs["title"] == "Rich note"
        assert kwargs["body_html"] == body_html
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"content_text": "Rich note\nRich body."},
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
            "create-html",
            "--title",
            "Rich note",
            "--body-html",
            body_html,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_plan_and_apply_replace_html(monkeypatch, capsys) -> None:
    handle = make_int_handle("notes:note", 20)
    current_sha = hashlib.sha256("Current note body".encode("utf-8")).hexdigest()
    body_html = "<h1>Title</h1><p>Replaced rich body.</p>"
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "replace-html",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-html",
            body_html,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["format"] == "rich_text_replace"
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "replace-html"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["body_html"] == body_html
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"content_text": "Title\nReplaced rich body."},
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
            "replace-html",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--body-html",
            body_html,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_plan_and_apply_delete(monkeypatch, capsys) -> None:
    handle = make_int_handle("notes:note", 20)
    current_sha = hashlib.sha256("Current note body".encode("utf-8")).hexdigest()
    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["body_text"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"handle": handle, "deleted": True, "verified_absent": True},
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
            "delete",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"


def test_cli_notes_plan_and_apply_move_to_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "notes.sqlite"
    _notes_db(db_path)
    handle = make_int_handle("notes:note", 8)
    folder_handle = make_opaque_handle(
        "notes:folder",
        "b333f468e636ca89",
        10,
        7,
    )
    current_sha = hashlib.sha256("Current note body".encode("utf-8")).hexdigest()

    def fake_plan_notes_change(operation: str, **kwargs):
        assert operation == "move-to-folder"
        assert kwargs["handle"] == handle
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["db_path"] == db_path
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "move_to_folder",
                "target": {
                    "handle": handle,
                    "folder_handle": folder_handle,
                    "expected_current_sha256": current_sha,
                },
                "approval": {"approval_fingerprint": "movefingerprint"},
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_notes_change", fake_plan_notes_change)

    plan_exit_code = main(
        [
            "notes",
            "plan",
            "--json",
            "--operation",
            "move-to-folder",
            "--handle",
            handle,
            "--folder-handle",
            folder_handle,
            "--expected-current-sha256",
            current_sha,
            "--db",
            str(db_path),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_notes_change(operation: str, **kwargs):
        assert operation == "move-to-folder"
        assert kwargs["handle"] == handle
        assert kwargs["folder_handle"] == folder_handle
        assert kwargs["expected_current_sha256"] == current_sha
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "notes",
            "privacy": {"content_inspected": True, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {
                "handle": handle,
                "target_folder_handle": folder_handle,
                "target_folder_confirmed": True,
                "body_returned": False,
            },
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
            "move-to-folder",
            "--handle",
            handle,
            "--folder-handle",
            folder_handle,
            "--expected-current-sha256",
            current_sha,
            "--approval-token",
            token,
            "--confirm-apply",
            "--db",
            str(db_path),
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["read_back"]["body_returned"] is False


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


def test_cli_icloud_drive_root_returns_selected_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    exit_code = main(["icloud-drive", "root", "--json", "--root", str(root)])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "icloud_drive"
    assert parsed["status"] == "ok"
    assert parsed["result"]["kind"] == "directory"
    assert parsed["result"]["depth"] == 0
    assert parsed["result"]["is_root"] is True
    assert str(root) not in json.dumps(parsed)


def test_cli_icloud_drive_export_uses_exact_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    output_dir = tmp_path / "exports"

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
            "export",
            "--json",
            "--handle",
            parsed_search["results"][0]["handle"],
            "--output-dir",
            str(output_dir),
            "--filename",
            "../exported packet.md",
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "icloud_drive"
    assert parsed["status"] == "ok"
    assert parsed["result"]["exported_filename"] == "exported-packet.md"
    assert Path(parsed["result"]["exported_path"]).read_text(encoding="utf-8") == (
        "Synthetic iCloud content."
    )
    assert str(root) not in json.dumps(parsed)


def test_cli_icloud_drive_list_uses_exact_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Packets" / "Nested").mkdir()
    (root / "Packets" / "Nested" / "nested.md").write_text("Nested", encoding="utf-8")
    (root / "Packets" / ".hidden.md").write_text("Hidden", encoding="utf-8")
    (root / "Packets" / "Bundle.app").mkdir()

    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "icloud-drive",
            "list",
            "--json",
            "--handle",
            handle,
            "--limit",
            "10",
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "icloud_drive"
    assert parsed["status"] == "ok"
    assert parsed["query"]["recursive"] is False
    assert {item["name"] for item in parsed["results"]} == {"Nested"}
    raw = json.dumps(parsed)
    assert "nested.md" not in raw
    assert "Hidden" not in raw
    assert "Bundle.app" not in raw
    assert str(root) not in raw


def test_cli_icloud_drive_tree_uses_exact_folder_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Packets" / "Nested").mkdir()
    (root / "Packets" / "Nested" / "nested.md").write_text("Nested", encoding="utf-8")
    (root / "Packets" / "Nested" / "Deep").mkdir()
    (root / "Packets" / "Nested" / "Deep" / "deep.md").write_text("Deep", encoding="utf-8")
    (root / "Packets" / ".hidden.md").write_text("Hidden", encoding="utf-8")
    (root / "Packets" / "Bundle.app").mkdir()

    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "icloud-drive",
            "tree",
            "--json",
            "--handle",
            handle,
            "--depth",
            "2",
            "--limit",
            "10",
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "icloud_drive"
    assert parsed["status"] == "ok"
    assert parsed["query"]["recursive"] is True
    assert parsed["query"]["max_depth"] == 2
    names = {item["name"] for item in parsed["results"]}
    assert names == {"Deep", "Nested", "nested.md"}
    raw = json.dumps(parsed)
    assert "deep.md" not in raw
    assert "Hidden" not in raw
    assert "Bundle.app" not in raw
    assert str(root) not in raw


def test_cli_icloud_drive_search_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert (
        main(
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
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "search"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0


def test_cli_icloud_drive_root_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert main(["icloud-drive", "root", "--json", "--root", str(root)]) == 0
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["status"] == "error"
    assert parsed["mode"] == "root"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0


def test_cli_icloud_drive_get_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert main(["icloud-drive", "get", "--json", "--handle", handle, "--root", str(root)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "get"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0


def test_cli_icloud_drive_list_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert main(["icloud-drive", "list", "--json", "--handle", handle, "--root", str(root)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "list"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0


def test_cli_icloud_drive_tree_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert main(["icloud-drive", "tree", "--json", "--handle", handle, "--root", str(root)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "tree"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0


def test_cli_icloud_drive_content_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert main(["icloud-drive", "content", "--json", "--handle", handle, "--root", str(root)]) == 0
    raw = capsys.readouterr().out
    parsed = json.loads(raw)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "content"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0
    assert "Synthetic iCloud content." not in raw


def test_cli_icloud_drive_export_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    output_dir = tmp_path / "exports"
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert (
        main(
            [
                "icloud-drive",
                "export",
                "--json",
                "--handle",
                handle,
                "--output-dir",
                str(output_dir),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    raw = capsys.readouterr().out
    parsed = json.loads(raw)
    assert parsed["status"] == "error"
    assert parsed["mode"] == "export"
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert parsed["result_count"] == 0
    assert not output_dir.exists()


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
            "--root",
            str(root),
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


def test_cli_icloud_drive_apply_rejects_root_override_without_test_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    monkeypatch.setenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", "1")
    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "create-text",
                "--parent-handle",
                parent_handle,
                "--filename",
                "blocked-root-write.txt",
                "--content-text",
                "Synthetic blocked content.",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    monkeypatch.delenv("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT", raising=False)

    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "create-text",
                "--parent-handle",
                parent_handle,
                "--filename",
                "blocked-root-write.txt",
                "--content-text",
                "Synthetic blocked content.",
                "--approval-token",
                token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["mutation_applied"] is False
    assert parsed["warnings"][0]["code"] == "unsupported_test_root"
    assert not (root / "Packets" / "blocked-root-write.txt").exists()


def test_cli_icloud_drive_plan_and_apply_create_folder(
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
            "create-folder",
            "--parent-handle",
            parent_handle,
            "--folder-name",
            "CLI Folder",
            "--root",
            str(root),
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
            "create-folder",
            "--parent-handle",
            parent_handle,
            "--folder-name",
            "CLI Folder",
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
    assert parsed["operation"] == "create_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["name"] == "CLI Folder"
    assert parsed["read_back"]["kind"] == "directory"
    assert "content_sha256" not in parsed["read_back"]
    assert (root / "Packets" / "CLI Folder").is_dir()


def test_cli_icloud_drive_plan_and_apply_create_folder_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    assert (
        main(
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
        == 0
    )
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "create-folder-path",
                "--parent-handle",
                parent_handle,
                "--folder-component",
                "Client",
                "--folder-component",
                "Drafts",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "create-folder-path",
                "--parent-handle",
                parent_handle,
                "--folder-component",
                "Client",
                "--folder-component",
                "Drafts",
                "--approval-token",
                token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )

    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "create_folder_path"
    assert parsed["read_back"]["name"] == "Drafts"
    assert parsed["read_back"]["component_count"] == 2
    assert (root / "Packets" / "Client" / "Drafts").is_dir()


def test_cli_icloud_drive_create_folder_path_rejects_expected_sha(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)

    assert main(["icloud-drive", "search", "--json", "--query", "Packets", "--root", str(root)]) == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "create-folder-path",
                "--parent-handle",
                parent_handle,
                "--folder-component",
                "Client",
                "--expected-current-sha256",
                "a" * 64,
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["warnings"][0]["code"] == "unexpected_expected_current_sha256"


def test_cli_icloud_drive_create_folder_rejects_conflicting_name_aliases(
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
            "create-folder",
            "--parent-handle",
            parent_handle,
            "--filename",
            "CLI Folder",
            "--folder-name",
            "Other Folder",
        ]
    )

    assert plan_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "error"
    assert parsed["warning"] == "conflicting_folder_name"


def test_cli_icloud_drive_plan_and_apply_rename_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Non Empty CLI Folder").mkdir()
    (root / "Non Empty CLI Folder" / "child.txt").write_text("rename child", encoding="utf-8")

    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Non Empty CLI Folder",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    item = json.loads(capsys.readouterr().out)["results"][0]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "rename-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Renamed CLI Folder",
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
            "rename-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Renamed CLI Folder",
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
    assert parsed["operation"] == "rename_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["name"] == "Renamed CLI Folder"
    assert parsed["read_back"]["kind"] == "directory"
    assert parsed["read_back"]["renamed"] is True
    assert parsed["read_back"]["empty_folder_confirmed"] is False
    assert parsed["read_back"]["non_empty_allowed"] is True
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in parsed["read_back"]
    assert not (root / "Non Empty CLI Folder").exists()
    assert (root / "Renamed CLI Folder" / "child.txt").read_text(encoding="utf-8") == "rename child"
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        item["handle"],
        item["metadata_sha256"],
        token,
        "Non Empty CLI Folder",
        "Renamed CLI Folder",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_and_apply_trash_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    cli_trash_folder = root / "Non Empty CLI Trash Folder"
    cli_trash_folder.mkdir()
    (cli_trash_folder / "child.txt").write_text("child", encoding="utf-8")

    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Non Empty CLI Trash Folder",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    item = json.loads(capsys.readouterr().out)["results"][0]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "trash-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--root",
            str(root),
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
            "trash-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
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
    assert parsed["operation"] == "trash_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["kind"] == "directory"
    assert parsed["read_back"]["original_present"] is False
    assert parsed["read_back"]["non_empty_allowed"] is True
    assert parsed["read_back"]["trashed"] is True
    assert parsed["read_back"]["empty_folder_confirmed"] is False
    assert parsed["read_back"]["non_empty_allowed"] is True
    assert parsed["read_back"]["trash_path_returned"] is False
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    trash_entries = list((root / ".Trash").iterdir())
    assert not cli_trash_folder.exists()
    assert len(trash_entries) == 1
    assert (trash_entries[0] / "child.txt").read_text(encoding="utf-8") == "child"
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        item["handle"],
        item["metadata_sha256"],
        token,
        "Non Empty CLI Trash Folder",
        "child.txt",
        "child",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_and_apply_delete_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Non Empty CLI Delete Folder").mkdir()
    (root / "Non Empty CLI Delete Folder" / "child.txt").write_text(
        "delete child",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Non Empty CLI Delete Folder",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    item = json.loads(capsys.readouterr().out)["results"][0]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "delete-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--root",
            str(root),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["empty_folder_required"] is False
    assert plan["preview"]["proposed"]["non_empty_allowed"] is True
    assert plan["preview"]["proposed"]["recursive_delete"] == "bounded_private_tree"
    assert plan["preview"]["proposed"]["source_tree_binding"] == "private"
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    apply_exit_code = main(
        [
            "icloud-drive",
            "apply",
            "--json",
            "--operation",
            "delete-folder",
            "--handle",
            item["handle"],
            "--expected-current-sha256",
            item["metadata_sha256"],
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
    assert parsed["operation"] == "delete_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["kind"] == "directory"
    assert parsed["read_back"]["original_present"] is False
    assert parsed["read_back"]["verified_absent"] is True
    assert parsed["read_back"]["permanently_deleted"] is True
    assert parsed["read_back"]["empty_folder_confirmed"] is False
    assert parsed["read_back"]["non_empty_allowed"] is True
    assert parsed["read_back"]["staging_path_returned"] is False
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    response_text = json.dumps(parsed)
    assert "child.txt" not in response_text
    assert "delete child" not in response_text
    assert not (root / "Non Empty CLI Delete Folder").exists()
    assert not (root / ".Trash").exists()
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        item["handle"],
        item["metadata_sha256"],
        token,
        "Non Empty CLI Delete Folder",
        "child.txt",
        "delete child",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_and_apply_move_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Non Empty CLI Move Folder").mkdir()
    (root / "Non Empty CLI Move Folder" / "child.txt").write_text("move child", encoding="utf-8")

    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Non Empty CLI Move Folder",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    item = json.loads(capsys.readouterr().out)["results"][0]
    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Archive",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "move-folder",
            "--handle",
            item["handle"],
            "--parent-handle",
            parent_handle,
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Moved CLI Folder",
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
            "move-folder",
            "--handle",
            item["handle"],
            "--parent-handle",
            parent_handle,
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Moved CLI Folder",
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
    assert parsed["operation"] == "move_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["kind"] == "directory"
    assert parsed["read_back"]["source_present"] is False
    assert parsed["read_back"]["target_present"] is True
    assert parsed["read_back"]["moved"] is True
    assert parsed["read_back"]["empty_folder_confirmed"] is False
    assert parsed["read_back"]["non_empty_allowed"] is True
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    assert not (root / "Non Empty CLI Move Folder").exists()
    assert (root / "Archive" / "Moved CLI Folder" / "child.txt").read_text(encoding="utf-8") == "move child"
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        item["handle"],
        parent_handle,
        item["metadata_sha256"],
        token,
        "Empty CLI Move Folder",
        "Moved CLI Folder",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_and_apply_copy_folder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Empty CLI Copy Folder").mkdir()

    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Empty CLI Copy Folder",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    item = json.loads(capsys.readouterr().out)["results"][0]
    assert (
        main(
            [
                "icloud-drive",
                "search",
                "--json",
                "--query",
                "Archive",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "copy-folder",
            "--handle",
            item["handle"],
            "--parent-handle",
            parent_handle,
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Copied CLI Folder",
            "--root",
            str(root),
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
            "copy-folder",
            "--handle",
            item["handle"],
            "--parent-handle",
            parent_handle,
            "--expected-current-sha256",
            item["metadata_sha256"],
            "--folder-name",
            "Copied CLI Folder",
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
    assert parsed["operation"] == "copy_folder"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["kind"] == "directory"
    assert parsed["read_back"]["source_present"] is True
    assert parsed["read_back"]["target_present"] is True
    assert parsed["read_back"]["copied"] is True
    assert parsed["read_back"]["empty_folder_confirmed"] is True
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    assert (root / "Empty CLI Copy Folder").is_dir()
    assert (root / "Archive" / "Copied CLI Folder").is_dir()
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        item["handle"],
        parent_handle,
        item["metadata_sha256"],
        token,
        "Empty CLI Copy Folder",
        "Copied CLI Folder",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_text_operations_still_require_content_text(
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
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    content_exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            handle,
            "--root",
            str(root),
        ]
    )
    assert content_exit_code == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    parent_search_exit_code = main(
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
    assert parent_search_exit_code == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    cases = [
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
        ],
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "append-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
        ],
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "replace-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
        ],
    ]

    for argv in cases:
        assert main(argv) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["status"] == "error"
        assert parsed["warnings"][0]["code"] == "missing_required_field"


def test_cli_icloud_drive_plan_and_apply_append_text(
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
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    content_exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            handle,
            "--root",
            str(root),
        ]
    )
    assert content_exit_code == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "append-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--content-text",
            "\nSynthetic CLI append.",
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
            "append-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--content-text",
            "\nSynthetic CLI append.",
            "--approval-token",
            token,
            "--confirm-apply",
            "--root",
            str(root),
        ]
    )

    expected = "Synthetic iCloud content.\nSynthetic CLI append."
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "append_text"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["content_sha256"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert (root / "synthetic-packet.md").read_text(encoding="utf-8") == expected


def test_cli_icloud_drive_plan_and_apply_replace_text(
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
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    content_exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            handle,
            "--root",
            str(root),
        ]
    )
    assert content_exit_code == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    replacement = "Synthetic CLI replacement.\n"
    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "replace-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--content-text",
            replacement,
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
            "replace-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--content-text",
            replacement,
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
    assert parsed["operation"] == "replace_text"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["content_sha256"] == hashlib.sha256(replacement.encode("utf-8")).hexdigest()
    assert (root / "synthetic-packet.md").read_text(encoding="utf-8") == replacement
    assert "content_text" not in parsed["read_back"]


def test_cli_icloud_drive_plan_and_apply_trash_text(
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
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    content_exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            handle,
            "--root",
            str(root),
        ]
    )
    assert content_exit_code == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "trash-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--root",
            str(root),
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
            "trash-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
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
    assert parsed["operation"] == "trash_text"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["original_present"] is False
    assert parsed["read_back"]["trashed"] is True
    assert parsed["read_back"]["trash_path_returned"] is False
    assert "content_text" not in parsed["read_back"]
    assert not (root / "synthetic-packet.md").exists()
    assert len(list((root / ".Trash").iterdir())) == 1


def test_cli_icloud_drive_plan_and_apply_delete_text(
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
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    content_exit_code = main(
        [
            "icloud-drive",
            "content",
            "--json",
            "--handle",
            handle,
            "--root",
            str(root),
        ]
    )
    assert content_exit_code == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    plan_exit_code = main(
        [
            "icloud-drive",
            "plan",
            "--json",
            "--operation",
            "delete-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
            "--root",
            str(root),
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "delete_text"
    assert plan["preview"]["proposed"]["permanent_delete"] is True
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    apply_exit_code = main(
        [
            "icloud-drive",
            "apply",
            "--json",
            "--operation",
            "delete-text",
            "--handle",
            handle,
            "--expected-current-sha256",
            current_sha,
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
    assert parsed["operation"] == "delete_text"
    assert parsed["mutation_applied"] is True
    assert parsed["read_back"]["original_present"] is False
    assert parsed["read_back"]["verified_absent"] is True
    assert parsed["read_back"]["permanently_deleted"] is True
    assert parsed["read_back"]["trash_path_returned"] is False
    assert parsed["read_back"]["staging_path_returned"] is False
    assert parsed["read_back"]["content_text_returned"] is False
    assert parsed["read_back"]["content_hash_returned"] is False
    assert "content_text" not in parsed["read_back"]
    assert "content_sha256" not in parsed["read_back"]
    assert not (root / "synthetic-packet.md").exists()
    assert not (root / ".Trash").exists()
    assert not (root / ".local-apple-data-delete-staging").exists()

    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        handle,
        current_sha,
        token,
        "Synthetic iCloud content.",
        "synthetic-packet.md",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_plan_delete_text_rejects_unsupported_without_approval(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    target = root / "image.bin"
    target.write_bytes(b"\x00\x01")

    assert main(["icloud-drive", "search", "--json", "--query", "image", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "delete-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["status"] == "error"
    assert parsed["preview"] is None
    assert parsed["apply_available"] is False
    assert parsed["warnings"][0]["code"] == "unsupported_file_type"
    assert "approval" not in parsed


def test_cli_icloud_drive_delete_text_rejects_same_content_stale_token(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    target = root / "synthetic-packet.md"
    original_text = "Synthetic iCloud content."

    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    current_sha = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "delete-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--root",
                str(root),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    target.unlink()
    target.write_text(original_text, encoding="utf-8")

    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "delete-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--approval-token",
                token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["status"] == "error"
    assert parsed["mutation_applied"] is False
    assert parsed["privacy"]["content_inspected"] is False
    assert parsed["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_text(encoding="utf-8") == original_text
    assert not (root / ".Trash").exists()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_cli_icloud_drive_plan_and_apply_rename_copy_move_text(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Archive").mkdir()

    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet.md", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    assert main(["icloud-drive", "content", "--json", "--handle", handle, "--root", str(root)]) == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "copy-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "synthetic-packet-copy.md",
            ]
        )
        == 0
    )
    copy_plan = json.loads(capsys.readouterr().out)
    copy_token = "icloud-drive-apply:v1:" + copy_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "copy-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "synthetic-packet-copy.md",
                "--approval-token",
                copy_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    copy_result = json.loads(capsys.readouterr().out)
    assert copy_result["status"] == "ok"
    assert copy_result["operation"] == "copy_text"
    assert copy_result["read_back"]["source_present"] is True
    assert (root / "synthetic-packet.md").exists()
    assert (root / "synthetic-packet-copy.md").exists()

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "rename-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "synthetic-renamed.md",
            ]
        )
        == 0
    )
    rename_plan = json.loads(capsys.readouterr().out)
    rename_token = "icloud-drive-apply:v1:" + rename_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "rename-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "synthetic-renamed.md",
                "--approval-token",
                rename_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    rename_result = json.loads(capsys.readouterr().out)
    assert rename_result["status"] == "ok"
    assert rename_result["operation"] == "rename_text"
    assert rename_result["read_back"]["source_present"] is False
    assert not (root / "synthetic-packet.md").exists()
    assert (root / "synthetic-renamed.md").exists()

    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet-copy.md", "--root", str(root)]) == 0
    copy_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    assert main(["icloud-drive", "search", "--json", "--query", "Archive", "--root", str(root)]) == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "move-text",
                "--handle",
                copy_handle,
                "--parent-handle",
                parent_handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "moved-copy.md",
            ]
        )
        == 0
    )
    move_plan = json.loads(capsys.readouterr().out)
    move_token = "icloud-drive-apply:v1:" + move_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "move-text",
                "--handle",
                copy_handle,
                "--parent-handle",
                parent_handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "moved-copy.md",
                "--approval-token",
                move_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    move_result = json.loads(capsys.readouterr().out)
    assert move_result["status"] == "ok"
    assert move_result["operation"] == "move_text"
    assert move_result["read_back"]["source_present"] is False
    assert not (root / "synthetic-packet-copy.md").exists()
    assert (root / "Archive" / "moved-copy.md").exists()
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        handle,
        copy_handle,
        parent_handle,
        current_sha,
        copy_token,
        rename_token,
        move_token,
        "Synthetic iCloud content.",
        "synthetic-packet.md",
        "synthetic-renamed.md",
        str(root),
    ):
        assert forbidden not in log_text


def test_cli_icloud_drive_rename_copy_move_tokens_bind_exact_plan(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    assert main(["icloud-drive", "search", "--json", "--query", "synthetic-packet.md", "--root", str(root)]) == 0
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]
    assert main(["icloud-drive", "content", "--json", "--handle", handle, "--root", str(root)]) == 0
    current_sha = json.loads(capsys.readouterr().out)["result"]["content_sha256"]
    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "copy-text",
                "--handle",
                handle,
                "--expected-current-sha256",
                current_sha,
                "--filename",
                "synthetic-copy.md",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    drift_attempts = [
        ("rename-text", current_sha, "synthetic-copy.md"),
        ("copy-text", "0" * 64, "synthetic-copy.md"),
        ("copy-text", current_sha, "synthetic-other.md"),
    ]
    for operation, expected_sha, filename in drift_attempts:
        assert (
            main(
                [
                    "icloud-drive",
                    "apply",
                    "--json",
                    "--operation",
                    operation,
                    "--handle",
                    handle,
                    "--expected-current-sha256",
                    expected_sha,
                    "--filename",
                    filename,
                    "--approval-token",
                    token,
                    "--confirm-apply",
                    "--root",
                    str(root),
                ]
            )
            == 0
        )
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "invalid_approval_token"

    assert (root / "synthetic-packet.md").exists()
    assert not (root / "synthetic-copy.md").exists()
    assert not (root / "synthetic-other.md").exists()


def test_cli_icloud_drive_plan_and_apply_rename_copy_move_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    _icloud_root(root)
    (root / "Archive").mkdir()
    (root / "rename.bin").write_bytes(b"\x00\x01")
    (root / "copy.bin").write_bytes(b"\x02\x03")
    (root / "move.bin").write_bytes(b"\x04\x05")
    (root / "replace.bin").write_bytes(b"\x08\x09old")
    (root / "trash.bin").write_bytes(b"\x0c\x0dtrash")
    (root / "delete-file.bin").write_bytes(b"\x0e\x0fdelete-file")
    import_source = tmp_path / "import-source.bin"
    import_payload = b"\x06\x07import"
    import_source.write_bytes(import_payload)
    replace_source = tmp_path / "replace-source.bin"
    replace_payload = b"\x0a\x0breplace"
    replace_source.write_bytes(replace_payload)

    assert main(["icloud-drive", "search", "--json", "--query", "rename.bin", "--root", str(root)]) == 0
    rename_item = json.loads(capsys.readouterr().out)["results"][0]
    assert main(["icloud-drive", "search", "--json", "--query", "copy.bin", "--root", str(root)]) == 0
    copy_item = json.loads(capsys.readouterr().out)["results"][0]
    assert main(["icloud-drive", "search", "--json", "--query", "move.bin", "--root", str(root)]) == 0
    move_item = json.loads(capsys.readouterr().out)["results"][0]
    assert main(["icloud-drive", "search", "--json", "--query", "replace.bin", "--root", str(root)]) == 0
    replace_item = json.loads(capsys.readouterr().out)["results"][0]
    assert main(["icloud-drive", "search", "--json", "--query", "trash.bin", "--root", str(root)]) == 0
    trash_item = json.loads(capsys.readouterr().out)["results"][0]
    assert (
        main(["icloud-drive", "search", "--json", "--query", "delete-file.bin", "--root", str(root)])
        == 0
    )
    delete_file_item = json.loads(capsys.readouterr().out)["results"][0]
    assert main(["icloud-drive", "search", "--json", "--query", "Archive", "--root", str(root)]) == 0
    parent_handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "rename-file",
                "--handle",
                rename_item["handle"],
                "--expected-current-sha256",
                rename_item["metadata_sha256"],
                "--filename",
                "renamed.bin",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    rename_plan = json.loads(capsys.readouterr().out)
    rename_token = "icloud-drive-apply:v1:" + rename_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "rename-file",
                "--handle",
                rename_item["handle"],
                "--expected-current-sha256",
                rename_item["metadata_sha256"],
                "--filename",
                "renamed.bin",
                "--approval-token",
                rename_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    rename_result = json.loads(capsys.readouterr().out)
    assert rename_result["status"] == "ok"
    assert rename_result["operation"] == "rename_file"
    assert rename_result["read_back"]["source_present"] is False
    assert rename_result["read_back"]["target_present"] is True
    assert rename_result["read_back"]["content_text_returned"] is False
    assert rename_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in rename_result["read_back"]
    assert not (root / "rename.bin").exists()
    assert (root / "renamed.bin").read_bytes() == b"\x00\x01"

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "copy-file",
                "--handle",
                copy_item["handle"],
                "--expected-current-sha256",
                copy_item["metadata_sha256"],
                "--filename",
                "copy-out.bin",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    copy_plan = json.loads(capsys.readouterr().out)
    copy_token = "icloud-drive-apply:v1:" + copy_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "copy-file",
                "--handle",
                copy_item["handle"],
                "--expected-current-sha256",
                copy_item["metadata_sha256"],
                "--filename",
                "copy-out.bin",
                "--approval-token",
                copy_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    copy_result = json.loads(capsys.readouterr().out)
    assert copy_result["status"] == "ok"
    assert copy_result["operation"] == "copy_file"
    assert copy_result["read_back"]["source_present"] is True
    assert copy_result["read_back"]["target_present"] is True
    assert copy_result["read_back"]["content_text_returned"] is False
    assert copy_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in copy_result["read_back"]
    assert (root / "copy.bin").read_bytes() == b"\x02\x03"
    assert (root / "copy-out.bin").read_bytes() == b"\x02\x03"

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "move-file",
                "--handle",
                move_item["handle"],
                "--parent-handle",
                parent_handle,
                "--expected-current-sha256",
                move_item["metadata_sha256"],
                "--filename",
                "moved.bin",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    move_plan = json.loads(capsys.readouterr().out)
    move_token = "icloud-drive-apply:v1:" + move_plan["preview"]["approval"]["approval_fingerprint"]
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "move-file",
                "--handle",
                move_item["handle"],
                "--parent-handle",
                parent_handle,
                "--expected-current-sha256",
                move_item["metadata_sha256"],
                "--filename",
                "moved.bin",
                "--approval-token",
                move_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    move_result = json.loads(capsys.readouterr().out)
    assert move_result["status"] == "ok"
    assert move_result["operation"] == "move_file"
    assert move_result["read_back"]["source_present"] is False
    assert move_result["read_back"]["target_present"] is True
    assert move_result["read_back"]["content_text_returned"] is False
    assert move_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in move_result["read_back"]
    assert not (root / "move.bin").exists()
    assert (root / "Archive" / "moved.bin").read_bytes() == b"\x04\x05"

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "import-file",
                "--parent-handle",
                parent_handle,
                "--source-file",
                str(import_source),
                "--filename",
                "imported.bin",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    import_plan = json.loads(capsys.readouterr().out)
    import_token = "icloud-drive-apply:v1:" + import_plan["preview"]["approval"]["approval_fingerprint"]
    assert import_plan["status"] == "ok"
    assert import_plan["preview"]["operation"] == "import_file"
    assert import_plan["preview"]["proposed"]["source_filename"] == "import-source.bin"
    assert import_plan["preview"]["proposed"]["source_size_bytes"] == len(import_payload)
    assert import_plan["preview"]["proposed"]["source_path_returned"] is False
    assert import_plan["preview"]["proposed"]["source_hash_returned"] is False
    assert str(import_source) not in json.dumps(import_plan)
    assert "source_content_sha256" not in json.dumps(import_plan)
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "import-file",
                "--parent-handle",
                parent_handle,
                "--source-file",
                str(import_source),
                "--filename",
                "imported.bin",
                "--approval-token",
                import_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    import_result = json.loads(capsys.readouterr().out)
    assert import_result["status"] == "ok"
    assert import_result["operation"] == "import_file"
    assert import_result["read_back"]["target_present"] is True
    assert import_result["read_back"]["imported"] is True
    assert import_result["read_back"]["source_path_returned"] is False
    assert import_result["read_back"]["source_hash_returned"] is False
    assert import_result["read_back"]["content_text_returned"] is False
    assert import_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in import_result["read_back"]
    assert str(import_source) not in json.dumps(import_result)
    assert (root / "Archive" / "imported.bin").read_bytes() == import_payload
    assert import_source.read_bytes() == import_payload

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "replace-file",
                "--handle",
                replace_item["handle"],
                "--source-file",
                str(replace_source),
                "--expected-current-sha256",
                replace_item["metadata_sha256"],
                "--root",
                str(root),
            ]
        )
        == 0
    )
    replace_plan = json.loads(capsys.readouterr().out)
    replace_token = "icloud-drive-apply:v1:" + replace_plan["preview"]["approval"]["approval_fingerprint"]
    assert replace_plan["status"] == "ok"
    assert replace_plan["preview"]["operation"] == "replace_file"
    assert replace_plan["preview"]["proposed"]["replace_from_source_filename"] == "replace-source.bin"
    assert replace_plan["preview"]["proposed"]["source_path_returned"] is False
    assert replace_plan["preview"]["proposed"]["source_hash_returned"] is False
    assert str(replace_source) not in json.dumps(replace_plan)
    assert "source_content_sha256" not in json.dumps(replace_plan)
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "replace-file",
                "--handle",
                replace_item["handle"],
                "--source-file",
                str(replace_source),
                "--expected-current-sha256",
                replace_item["metadata_sha256"],
                "--approval-token",
                replace_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    replace_result = json.loads(capsys.readouterr().out)
    assert replace_result["status"] == "ok"
    assert replace_result["operation"] == "replace_file"
    assert replace_result["read_back"]["target_present"] is True
    assert replace_result["read_back"]["replaced"] is True
    assert replace_result["read_back"]["source_path_returned"] is False
    assert replace_result["read_back"]["source_hash_returned"] is False
    assert replace_result["read_back"]["content_text_returned"] is False
    assert replace_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in replace_result["read_back"]
    assert str(replace_source) not in json.dumps(replace_result)
    assert (root / "replace.bin").read_bytes() == replace_payload
    assert replace_source.read_bytes() == replace_payload

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "trash-file",
                "--handle",
                trash_item["handle"],
                "--expected-current-sha256",
                trash_item["metadata_sha256"],
                "--root",
                str(root),
            ]
        )
        == 0
    )
    trash_plan = json.loads(capsys.readouterr().out)
    trash_token = "icloud-drive-apply:v1:" + trash_plan["preview"]["approval"]["approval_fingerprint"]
    assert trash_plan["status"] == "ok"
    assert trash_plan["preview"]["operation"] == "trash_file"
    assert trash_plan["preview"]["proposed"]["content_type"] == "regular_file"
    assert trash_plan["preview"]["proposed"]["move_to_trash"] is True
    assert trash_plan["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "trash-file",
                "--handle",
                trash_item["handle"],
                "--expected-current-sha256",
                trash_item["metadata_sha256"],
                "--approval-token",
                trash_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    trash_result = json.loads(capsys.readouterr().out)
    assert trash_result["status"] == "ok"
    assert trash_result["operation"] == "trash_file"
    assert trash_result["read_back"]["trashed"] is True
    assert trash_result["read_back"]["original_present"] is False
    assert trash_result["read_back"]["trash_path_returned"] is False
    assert trash_result["read_back"]["content_text_returned"] is False
    assert trash_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in trash_result["read_back"]
    assert not (root / "trash.bin").exists()
    trashed_files = [path for path in (root / ".Trash").iterdir() if path.is_file()]
    assert len(trashed_files) == 1
    assert trashed_files[0].read_bytes() == b"\x0c\x0dtrash"

    assert (
        main(
            [
                "icloud-drive",
                "plan",
                "--json",
                "--operation",
                "delete-file",
                "--handle",
                delete_file_item["handle"],
                "--expected-current-sha256",
                delete_file_item["metadata_sha256"],
                "--root",
                str(root),
            ]
        )
        == 0
    )
    delete_file_plan = json.loads(capsys.readouterr().out)
    delete_file_token = (
        "icloud-drive-apply:v1:"
        + delete_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    assert delete_file_plan["status"] == "ok"
    assert delete_file_plan["preview"]["operation"] == "delete_file"
    assert delete_file_plan["preview"]["proposed"]["content_type"] == "regular_file"
    assert delete_file_plan["preview"]["proposed"]["permanent_delete"] is True
    assert delete_file_plan["preview"]["proposed"]["recoverable_trash"] == "blocked"
    assert delete_file_plan["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert (
        main(
            [
                "icloud-drive",
                "apply",
                "--json",
                "--operation",
                "delete-file",
                "--handle",
                delete_file_item["handle"],
                "--expected-current-sha256",
                delete_file_item["metadata_sha256"],
                "--approval-token",
                delete_file_token,
                "--confirm-apply",
                "--root",
                str(root),
            ]
        )
        == 0
    )
    delete_file_result = json.loads(capsys.readouterr().out)
    assert delete_file_result["status"] == "ok"
    assert delete_file_result["operation"] == "delete_file"
    assert delete_file_result["read_back"]["permanently_deleted"] is True
    assert delete_file_result["read_back"]["verified_absent"] is True
    assert delete_file_result["read_back"]["original_present"] is False
    assert delete_file_result["read_back"]["trash_path_returned"] is False
    assert delete_file_result["read_back"]["staging_path_returned"] is False
    assert delete_file_result["read_back"]["content_text_returned"] is False
    assert delete_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in delete_file_result["read_back"]
    assert not (root / "delete-file.bin").exists()
    assert not (root / ".local-apple-data-delete-staging").exists()

    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        rename_item["handle"],
        copy_item["handle"],
        move_item["handle"],
        replace_item["handle"],
        trash_item["handle"],
        delete_file_item["handle"],
        parent_handle,
        rename_item["metadata_sha256"],
        copy_item["metadata_sha256"],
        move_item["metadata_sha256"],
        replace_item["metadata_sha256"],
        trash_item["metadata_sha256"],
        delete_file_item["metadata_sha256"],
        rename_token,
        copy_token,
        move_token,
        import_token,
        replace_token,
        trash_token,
        delete_file_token,
        "rename.bin",
        "copy.bin",
        "move.bin",
        "replace.bin",
        "trash.bin",
        "delete-file.bin",
        str(import_source),
        str(replace_source),
        str(root),
    ):
        assert forbidden not in log_text


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


def test_cli_calendar_calendars_and_calendar_use_exact_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    handle = make_opaque_handle("calendar:calendar", "calendar-2")

    def fake_search_calendar_calendars(query: str = "", **kwargs):
        assert query == "Focus"
        assert kwargs["limit"] == 5
        assert kwargs["include_default"] is True
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
            "results": [
                {
                    "handle": handle,
                    "title": "Synthetic Focus",
                    "is_default_calendar": False,
                    "allows_content_modifications": True,
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    def fake_get_calendar_calendar(calendar_handle: str):
        assert calendar_handle == handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "content",
            },
            "result": {
                "handle": calendar_handle,
                "title": "Synthetic Focus",
                "is_default_calendar": False,
                "allows_content_modifications": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.search_calendar_calendars",
        fake_search_calendar_calendars,
    )
    monkeypatch.setattr(
        "local_apple_data.cli.get_calendar_calendar",
        fake_get_calendar_calendar,
    )

    search_exit_code = main(
        [
            "calendar",
            "calendars",
            "--json",
            "--query",
            "Focus",
            "--include-default",
            "--limit",
            "5",
        ]
    )
    assert search_exit_code == 0
    parsed_search = json.loads(capsys.readouterr().out)
    assert parsed_search["results"][0]["handle"] == handle

    get_exit_code = main(["calendar", "calendar", "--json", "--handle", handle])

    assert get_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "calendar"
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic Focus"


def test_cli_calendar_events_forwards_exact_calendar_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    handle = make_opaque_handle("calendar:calendar", "calendar-2")

    def fake_list_calendar_events_for_calendar(calendar_handle: str, **kwargs):
        assert calendar_handle == handle
        assert kwargs == {
            "start_date": "2026-06-01T00:00:00Z",
            "end_date": "2026-07-01T00:00:00Z",
            "limit": 5,
        }
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
            "query": {
                "scope": "selected_calendar_events",
                "calendar_handle": calendar_handle,
                "start_date": kwargs["start_date"],
                "end_date": kwargs["end_date"],
                "limit": kwargs["limit"],
            },
            "calendar": {"handle": calendar_handle, "title": "Synthetic Focus"},
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.list_calendar_events_for_calendar",
        fake_list_calendar_events_for_calendar,
    )

    exit_code = main(
        [
            "calendar",
            "events",
            "--json",
            "--handle",
            handle,
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-07-01T00:00:00Z",
            "--limit",
            "5",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["query"]["calendar_handle"] == handle
    assert parsed["query"]["scope"] == "selected_calendar_events"


def test_cli_calendar_request_access(monkeypatch, capsys) -> None:
    def fake_request_calendar_full_access():
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
            "authorization_status": "full_access",
            "request_result": "granted",
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.request_calendar_full_access",
        fake_request_calendar_full_access,
    )

    exit_code = main(["calendar", "request-access", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "calendar"
    assert parsed["status"] == "ok"
    assert parsed["authorization_status"] == "full_access"
    assert parsed["request_result"] == "granted"


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
            "--time-zone",
            "America/Los_Angeles",
            "--availability",
            "free",
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
        assert kwargs["time_zone"] == "America/Los_Angeles"
        assert kwargs["all_day"] is False
        assert kwargs["availability"] == "free"
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
            "--time-zone",
            "America/Los_Angeles",
            "--availability",
            "free",
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


def test_cli_calendar_plan_and_apply_update_availability(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-availability",
            "busy",
            "--title",
            "Synthetic updated free event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--availability",
            "free",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["availability_name"] == "busy"
    assert plan["preview"]["proposed"]["availability_name"] == "free"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["expected_availability"] == "busy"
        assert kwargs["availability"] == "free"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "Synthetic updated free event"},
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-availability",
            "busy",
            "--title",
            "Synthetic updated free event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--availability",
            "free",
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


def test_cli_calendar_plan_and_apply_target_calendar_handles(monkeypatch, capsys) -> None:
    calendar_handle = make_opaque_handle("calendar:calendar", "calendar-2")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic handle event",
            "--calendar-handle",
            calendar_handle,
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["calendar_handle"] == calendar_handle
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["calendar_handle"] == calendar_handle
        assert kwargs["target_calendar_handle"] == ""
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
            "read_back": {"title": "Synthetic handle event"},
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
            "Synthetic handle event",
            "--calendar-handle",
            calendar_handle,
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"


def test_cli_calendar_plan_and_apply_use_default_calendar(monkeypatch, capsys) -> None:
    token = "calendar-apply:v1:synthetic-default-calendar-token"
    calendar_handle = "calendar:calendar:v1:synthetic-default"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["calendar_title"] == ""
        assert kwargs["calendar_handle"] == ""
        assert kwargs["use_default_calendar"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "target": {
                    "target_mode": "calendar_handle",
                    "calendar_title": "",
                    "calendar_handle": calendar_handle,
                },
                "default_calendar_resolution": {
                    "use_default_calendar": True,
                    "calendar_title": "Synthetic Calendar",
                    "calendar_handle": calendar_handle,
                    "default_calendar_verified": True,
                },
                "approval": {
                    "approval_fingerprint": "synthetic-default-calendar-token",
                },
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["calendar_title"] == ""
        assert kwargs["calendar_handle"] == calendar_handle
        assert "use_default_calendar" not in kwargs
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
            "read_back": {
                "title": "Synthetic default-calendar event",
                "target_calendar_verified": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )
    monkeypatch.setattr(
        "local_apple_data.cli.apply_calendar_change",
        fake_apply_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic default-calendar event",
            "--use-default-calendar",
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["target_mode"] == "calendar_handle"
    assert plan["preview"]["default_calendar_resolution"]["use_default_calendar"] is True

    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic default-calendar event",
            "--calendar-handle",
            calendar_handle,
            "--start-date",
            "2026-06-04T17:00:00Z",
            "--end-date",
            "2026-06-04T18:00:00Z",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"


def test_cli_calendar_plan_and_apply_calendar_management(monkeypatch, capsys) -> None:
    source_handle = "calendar:calendar:v1:sourcehandle0000000000000000000"
    calendar_handle = "calendar:calendar:v1:targethandle0000000000000000000"
    token = "calendar-apply:v1:synthetic-calendar-token"

    def fake_plan_calendar_calendar_change(operation: str, **kwargs):
        assert operation == "create-calendar"
        assert kwargs["source_calendar_handle"] == source_handle
        assert kwargs["calendar_handle"] == ""
        assert kwargs["calendar_title"] == "LAD-TEST-new"
        assert kwargs["new_calendar_title"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "create_calendar",
                "approval": {"approval_fingerprint": "synthetic-calendar-token"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_calendar_calendar_change(operation: str, **kwargs):
        assert operation == "rename-calendar"
        assert kwargs["source_calendar_handle"] == ""
        assert kwargs["calendar_handle"] == calendar_handle
        assert kwargs["calendar_title"] == ""
        assert kwargs["new_calendar_title"] == "LAD-TEST-new"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "rename_calendar",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "LAD-TEST-new"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_calendar_change",
        fake_plan_calendar_calendar_change,
    )
    monkeypatch.setattr(
        "local_apple_data.cli.apply_calendar_calendar_change",
        fake_apply_calendar_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan-calendar",
            "--json",
            "--operation",
            "create-calendar",
            "--source-calendar-handle",
            source_handle,
            "--calendar-title",
            "LAD-TEST-new",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "create_calendar"

    apply_exit_code = main(
        [
            "calendar",
            "apply-calendar",
            "--json",
            "--operation",
            "rename-calendar",
            "--calendar-handle",
            calendar_handle,
            "--new-calendar-title",
            "LAD-TEST-new",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "rename_calendar"


def test_cli_calendar_plan_and_apply_calendar_delete(monkeypatch, capsys) -> None:
    calendar_handle = "calendar:calendar:v1:targethandle0000000000000000000"
    token = "calendar-apply:v1:synthetic-calendar-token"

    def fake_plan_calendar_calendar_change(operation: str, **kwargs):
        assert operation == "delete-calendar"
        assert kwargs["source_calendar_handle"] == ""
        assert kwargs["calendar_handle"] == calendar_handle
        assert kwargs["calendar_title"] == ""
        assert kwargs["new_calendar_title"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "delete_calendar",
                "approval": {"approval_fingerprint": "synthetic-calendar-token"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply_calendar_calendar_change(operation: str, **kwargs):
        assert operation == "delete-calendar"
        assert kwargs["source_calendar_handle"] == ""
        assert kwargs["calendar_handle"] == calendar_handle
        assert kwargs["calendar_title"] == ""
        assert kwargs["new_calendar_title"] == ""
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete_calendar",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"calendar_absent_verified": True},
            "result_count": 0,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_calendar_change",
        fake_plan_calendar_calendar_change,
    )
    monkeypatch.setattr(
        "local_apple_data.cli.apply_calendar_calendar_change",
        fake_apply_calendar_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan-calendar",
            "--json",
            "--operation",
            "delete-calendar",
            "--calendar-handle",
            calendar_handle,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["operation"] == "delete_calendar"

    apply_exit_code = main(
        [
            "calendar",
            "apply-calendar",
            "--json",
            "--operation",
            "delete-calendar",
            "--calendar-handle",
            calendar_handle,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "delete_calendar"


def test_cli_calendar_plan_and_apply_create_all_day(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic all day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T00:00:00Z",
            "--end-date",
            "2026-06-06T00:00:00Z",
            "--all-day",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["all_day"] is True
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["all_day"] is True
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
            "read_back": {"title": "Synthetic all day event", "all_day": True},
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
            "Synthetic all day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T00:00:00Z",
            "--end-date",
            "2026-06-06T00:00:00Z",
            "--all-day",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["all_day"] is True


def test_cli_calendar_plan_and_apply_create_date_only(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic date-only event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05",
            "--end-date",
            "2026-06-06",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["all_day"] is True
    assert plan["preview"]["proposed"]["date_only_input"] is True
    assert plan["preview"]["proposed"]["start_date"] == "2026-06-05"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["start_date"] == "2026-06-05"
        assert kwargs["end_date"] == "2026-06-06"
        assert kwargs["all_day"] is False
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
            "read_back": {
                "title": "Synthetic date-only event",
                "start_date": "2026-06-05",
                "end_date": "2026-06-06",
                "all_day": True,
            },
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
            "Synthetic date-only event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05",
            "--end-date",
            "2026-06-06",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["all_day"] is True


def test_cli_calendar_plan_and_apply_alarm_offsets(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic alarmed event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes",
            "0,-10",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    handle = make_opaque_handle("calendar:event", "event-alarm-1")
    delete_plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic alarmed event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05T17:00:00Z",
            "--expected-end-date",
            "2026-06-05T18:00:00Z",
            "--expected-alarm-offsets-minutes",
            "0,-10",
        ]
    )
    assert delete_plan_exit_code == 0
    delete_plan = json.loads(capsys.readouterr().out)
    assert delete_plan["preview"]["target"]["expected_state"]["alarm_offsets_minutes"] == [
        -10,
        0,
    ]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["alarm_offsets_minutes"] == [0, -10]
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
            "read_back": {"title": "Synthetic alarmed event", "alarm_offsets_minutes": [-10, 0]},
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
            "Synthetic alarmed event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes",
            "0,-10",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["alarm_offsets_minutes"] == [-10, 0]


def test_cli_calendar_plan_and_apply_absolute_alarm_dates(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic absolute alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["alarm_absolute_dates"] == [
        "2026-06-05T16:45:00Z"
    ]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    handle = make_opaque_handle("calendar:event", "event-absolute-alarm-1")
    delete_plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic absolute alarm event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05T17:00:00Z",
            "--expected-end-date",
            "2026-06-05T18:00:00Z",
            "--expected-alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
        ]
    )
    assert delete_plan_exit_code == 0
    delete_plan = json.loads(capsys.readouterr().out)
    assert delete_plan["preview"]["target"]["expected_state"][
        "alarm_absolute_dates"
    ] == ["2026-06-05T16:45:00Z"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
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
            "read_back": {
                "title": "Synthetic absolute alarm event",
                "alarm_absolute_dates": ["2026-06-05T16:45:00Z"],
            },
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
            "Synthetic absolute alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]


def test_cli_calendar_plan_and_apply_audio_alarm_sound(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic audio alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes=-10",
            "--alarm-sound-name",
            "Glass",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["alarm_sound_name"] == "Glass"
    assert plan["preview"]["proposed"]["alarm_action"] == "audio"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    handle = make_opaque_handle("calendar:event", "event-audio-alarm-1")
    delete_plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic audio alarm event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05T17:00:00Z",
            "--expected-end-date",
            "2026-06-05T18:00:00Z",
            "--expected-alarm-offsets-minutes=-10",
            "--expected-alarm-sound-name",
            "Glass",
        ]
    )
    assert delete_plan_exit_code == 0
    delete_plan = json.loads(capsys.readouterr().out)
    assert delete_plan["preview"]["target"]["expected_state"]["alarm_sound_name"] == "Glass"

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["alarm_offsets_minutes"] == [-10]
        assert kwargs["alarm_sound_name"] == "Glass"
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
            "read_back": {
                "title": "Synthetic audio alarm event",
                "alarm_offsets_minutes": [-10],
                "alarm_sound_name": "Glass",
                "alarm_sound_name_verified": True,
            },
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
            "Synthetic audio alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes=-10",
            "--alarm-sound-name",
            "Glass",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["alarm_sound_name_verified"] is True


def test_cli_calendar_plan_and_apply_email_alarm_hash(monkeypatch, capsys) -> None:
    expected_sha = hashlib.sha256(b"notify@example.invalid").hexdigest()
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic email alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes=-10",
            "--alarm-email-address",
            "Notify@Example.Invalid",
        ]
    )
    assert plan_exit_code == 0
    plan_stdout = capsys.readouterr().out
    assert "Notify@Example.Invalid" not in plan_stdout
    assert "notify@example.invalid" not in plan_stdout
    plan = json.loads(plan_stdout)
    assert plan["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert plan["preview"]["proposed"]["alarm_action"] == "email"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    handle = make_opaque_handle("calendar:event", "event-email-alarm-1")
    delete_plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic email alarm event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05T17:00:00Z",
            "--expected-end-date",
            "2026-06-05T18:00:00Z",
            "--expected-alarm-offsets-minutes=-10",
            "--expected-alarm-email-address-sha256",
            expected_sha,
        ]
    )
    assert delete_plan_exit_code == 0
    delete_plan = json.loads(capsys.readouterr().out)
    assert (
        delete_plan["preview"]["target"]["expected_state"]["alarm_email_address_sha256"]
        == expected_sha
    )

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["alarm_offsets_minutes"] == [-10]
        assert kwargs["alarm_email_address"] == "Notify@Example.Invalid"
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
            "read_back": {
                "title": "Synthetic email alarm event",
                "alarm_offsets_minutes": [-10],
                "alarm_email_address_sha256": expected_sha,
                "alarm_email_address_sha256_verified": True,
            },
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
            "Synthetic email alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-offsets-minutes=-10",
            "--alarm-email-address",
            "Notify@Example.Invalid",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    apply_stdout = capsys.readouterr().out
    assert "Notify@Example.Invalid" not in apply_stdout
    assert "notify@example.invalid" not in apply_stdout
    parsed = json.loads(apply_stdout)
    assert parsed["read_back"]["alarm_email_address_sha256_verified"] is True


def test_cli_calendar_plan_and_apply_geofence_alarm(monkeypatch, capsys) -> None:
    location_json = json.dumps(
        {
            "title": "Synthetic Gate",
            "latitude": 37.33182,
            "longitude": -122.03118,
            "radius_meters": 75,
        }
    )
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic geofence alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-proximity",
            "enter",
            "--alarm-structured-location",
            location_json,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["alarm_action"] == "geofence"
    assert plan["preview"]["proposed"]["alarm_proximity"] == "enter"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    handle = make_opaque_handle("calendar:event", "event-geofence-alarm-1")
    delete_plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic geofence alarm event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05T17:00:00Z",
            "--expected-end-date",
            "2026-06-05T18:00:00Z",
            "--expected-alarm-proximity",
            "enter",
            "--expected-alarm-structured-location",
            location_json,
        ]
    )
    assert delete_plan_exit_code == 0
    delete_plan = json.loads(capsys.readouterr().out)
    assert delete_plan["preview"]["target"]["expected_state"]["alarm_proximity"] == "enter"

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["alarm_proximity"] == "enter"
        assert kwargs["alarm_structured_location"]["title"] == "Synthetic Gate"
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
            "read_back": {
                "title": "Synthetic geofence alarm event",
                "alarm_proximity": "enter",
                "alarm_geofence_verified": True,
            },
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
            "Synthetic geofence alarm event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--alarm-proximity",
            "enter",
            "--alarm-structured-location",
            location_json,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["alarm_geofence_verified"] is True


def test_cli_calendar_plan_and_apply_recurrence(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "2",
            "--recurrence-count",
            "4",
            "--recurrence-month-days",
            "1,15,-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 2,
        "count": 4,
        "recurrence_present": True,
        "month_days": [-1, 1, 15],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "monthly"
        assert kwargs["recurrence_interval"] == 2
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_month_days"] == [1, 15, -1]
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
            "read_back": {
                "title": "Synthetic recurring event",
                "recurrence": {
                    "frequency": "monthly",
                    "interval": 2,
                    "count": 4,
                    "recurrence_present": True,
                    "month_days": [-1, 1, 15],
                },
            },
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
            "Synthetic recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "2",
            "--recurrence-count",
            "4",
            "--recurrence-month-days",
            "1,15,-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"]["count"] == 4


def test_cli_calendar_plan_and_apply_monthly_weekday_recurrence(
    monkeypatch, capsys
) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic monthly weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "monday,friday",
            "--recurrence-set-positions",
            "-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
        "set_positions": [-1],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "monthly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_weekdays"] == ["monday", "friday"]
        assert kwargs["recurrence_set_positions"] == [-1]
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
            "read_back": {
                "title": "Synthetic monthly weekday event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic monthly weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "monday,friday",
            "--recurrence-set-positions",
            "-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"]["weekdays"] == ["monday", "friday"]
    assert parsed["read_back"]["recurrence"]["set_positions"] == [-1]


def test_cli_calendar_plan_and_apply_monthly_nth_weekday_recurrence(
    monkeypatch, capsys
) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic nth weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-month-weekdays",
            "tuesday:3,friday:-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "tuesday", "week_number": 3},
        ],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "monthly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_month_weekdays"] == [
            {"weekday": "tuesday", "week_number": 3},
            {"weekday": "friday", "week_number": -1},
        ]
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
            "read_back": {
                "title": "Synthetic nth weekday event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic nth weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-month-weekdays",
            "tuesday:3,friday:-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_recurrence_end_date(monkeypatch, capsys) -> None:
    recurrence_end_date = "2026-08-01T17:00:00Z"
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic end-date recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-end-date",
            recurrence_end_date,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    expected_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": recurrence_end_date,
        "recurrence_present": True,
    }
    assert plan["preview"]["proposed"]["recurrence"] == expected_recurrence
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "weekly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] is None
        assert kwargs["recurrence_end_date"] == recurrence_end_date
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
            "read_back": {
                "title": "Synthetic end-date recurring event",
                "recurrence": expected_recurrence,
            },
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
            "Synthetic end-date recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-end-date",
            recurrence_end_date,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == expected_recurrence


def test_cli_calendar_plan_and_apply_unbounded_recurrence(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic unbounded recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-unbounded",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    expected_recurrence = {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert plan["preview"]["proposed"]["recurrence"] == expected_recurrence
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "weekly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] is None
        assert kwargs["recurrence_end_date"] == ""
        assert kwargs["recurrence_unbounded"] is True
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
            "read_back": {
                "title": "Synthetic unbounded recurring event",
                "recurrence": expected_recurrence,
            },
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
            "Synthetic unbounded recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-unbounded",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == expected_recurrence


def test_cli_calendar_plan_and_apply_update_monthly_nth_weekday_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated nth weekday event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-month-weekdays",
            "tuesday:3,friday:-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert plan["preview"]["proposed"]["recurrence"]["month_weekdays"] == [
        {"weekday": "friday", "week_number": -1},
        {"weekday": "tuesday", "week_number": 3},
    ]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "monthly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_month_weekdays"] == [
            {"weekday": "tuesday", "week_number": 3},
            {"weekday": "friday", "week_number": -1},
        ]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated nth weekday event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated nth weekday event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "monthly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-month-weekdays",
            "tuesday:3,friday:-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_yearly_month_recurrence(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic yearly month event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
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
            "read_back": {
                "title": "Synthetic yearly month event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic yearly month event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_yearly_month_day_recurrence(
    monkeypatch, capsys
) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic yearly month day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-days",
            "15,1,-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_days": [-1, 1, 15],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
        assert kwargs["recurrence_year_month_days"] == [15, 1, -1]
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
            "read_back": {
                "title": "Synthetic yearly month day event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic yearly month day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-days",
            "15,1,-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_yearly_month_nth_weekday_recurrence(
    monkeypatch, capsys
) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic yearly month nth weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-weekdays",
            "monday:2,friday:-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "monday", "week_number": 2},
        ],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
        assert kwargs["recurrence_year_month_weekdays"] == [
            {"weekday": "monday", "week_number": 2},
            {"weekday": "friday", "week_number": -1},
        ]
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
            "read_back": {
                "title": "Synthetic yearly month nth weekday event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic yearly month nth weekday event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-weekdays",
            "monday:2,friday:-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_yearly_day_recurrence(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic yearly day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-days",
            "100,1,-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_days": [-1, 1, 100],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_days"] == [100, 1, -1]
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
            "read_back": {
                "title": "Synthetic yearly day event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic yearly day event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-days",
            "100,1,-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_update_yearly_month_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert plan["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated yearly month event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_update_yearly_month_day_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month day event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-days",
            "15,1,-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert plan["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    assert plan["preview"]["proposed"]["recurrence"]["year_month_days"] == [-1, 1, 15]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
        assert kwargs["recurrence_year_month_days"] == [15, 1, -1]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated yearly month day event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month day event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-days",
            "15,1,-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_update_yearly_month_nth_weekday_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month nth weekday event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-weekdays",
            "monday:2,friday:-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert plan["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    assert plan["preview"]["proposed"]["recurrence"]["year_month_weekdays"] == [
        {"weekday": "friday", "week_number": -1},
        {"weekday": "monday", "week_number": 2},
    ]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_year_months"] == [12, 1, 7]
        assert kwargs["recurrence_year_month_weekdays"] == [
            {"weekday": "monday", "week_number": 2},
            {"weekday": "friday", "week_number": -1},
        ]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated yearly month nth weekday event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly month nth weekday event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-year-months",
            "12,1,7",
            "--recurrence-year-month-weekdays",
            "monday:2,friday:-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_update_yearly_week_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly week event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "monday,friday",
            "--recurrence-year-weeks",
            "26,1,-1",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["target"]["expected_state"]["recurrence_present"] is False
    assert plan["preview"]["proposed"]["recurrence"]["weekdays"] == [
        "monday",
        "friday",
    ]
    assert plan["preview"]["proposed"]["recurrence"]["year_weeks"] == [-1, 1, 26]
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "yearly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_weekdays"] == ["monday", "friday"]
        assert kwargs["recurrence_year_weeks"] == [26, 1, -1]
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated yearly week event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated yearly week event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "yearly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "monday,friday",
            "--recurrence-year-weeks",
            "26,1,-1",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == plan["preview"]["proposed"]["recurrence"]


def test_cli_calendar_plan_and_apply_structured_location(monkeypatch, capsys) -> None:
    structured_json = json.dumps(
        {
            "title": "Synthetic Structured Room",
            "latitude": 37.33182,
            "longitude": -122.03118,
            "radius_meters": 25,
        }
    )
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic structured event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--structured-location",
            structured_json,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["structured_location"] == {
        "title": "Synthetic Structured Room",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25.0,
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["structured_location"] == json.loads(structured_json)
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
            "read_back": {
                "title": "Synthetic structured event",
                "structured_location": plan["preview"]["proposed"]["structured_location"],
                "structured_location_verified": True,
            },
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
            "Synthetic structured event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--structured-location",
            structured_json,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["structured_location_verified"] is True


def test_cli_calendar_expected_structured_location_forwards_to_plan(
    monkeypatch, capsys
) -> None:
    expected_structured_json = json.dumps({"title": "Synthetic Structured Room"})

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["expected_structured_location"] == json.loads(
            expected_structured_json
        )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "plan",
            "operation": "delete",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "approval": {"approval_fingerprint": "abc"},
                "target": {"expected_state": {}},
                "proposed": {},
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            "calendar:event:v1:synthetic",
            "--expected-structured-location",
            expected_structured_json,
        ]
    )

    assert plan_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"


def test_cli_calendar_clear_structured_location_forwards_to_plan_and_apply(
    monkeypatch, capsys
) -> None:
    expected_structured_json = json.dumps({"title": "Synthetic Structured Room"})

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_structured_location"] is True
        assert kwargs["expected_structured_location"] == json.loads(
            expected_structured_json
        )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "plan",
            "operation": "update",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "approval": {"approval_fingerprint": "abc"},
                "target": {"expected_state": {}},
                "proposed": {"structured_location_clear_requested": True},
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            "calendar:event:v1:synthetic",
            "--expected-structured-location",
            expected_structured_json,
            "--clear-structured-location",
        ]
    )
    plan = json.loads(capsys.readouterr().out)
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_structured_location"] is True
        assert kwargs["expected_structured_location"] == json.loads(
            expected_structured_json
        )
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "structured_location_present": False,
                "structured_location_cleared_verified": True,
            },
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
            "update",
            "--handle",
            "calendar:event:v1:synthetic",
            "--expected-structured-location",
            expected_structured_json,
            "--clear-structured-location",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert plan_exit_code == 0
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["structured_location_cleared_verified"] is True


def test_cli_calendar_plan_and_apply_weekly_weekday_recurrence(monkeypatch, capsys) -> None:
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic weekday recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "friday,monday",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["recurrence_frequency"] == "weekly"
        assert kwargs["recurrence_interval"] == 1
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_weekdays"] == ["friday", "monday"]
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
            "read_back": {
                "title": "Synthetic weekday recurring event",
                "recurrence": plan["preview"]["proposed"]["recurrence"],
            },
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
            "Synthetic weekday recurring event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "1",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "friday,monday",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"]["weekdays"] == ["monday", "friday"]


def test_cli_calendar_plan_and_apply_update_recurrence(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated recurring event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "2",
            "--recurrence-count",
            "6",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 2,
        "count": 6,
        "recurrence_present": True,
    }
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "weekly"
        assert kwargs["recurrence_interval"] == 2
        assert kwargs["recurrence_count"] == 6
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated recurring event",
                "recurrence": {
                    "frequency": "weekly",
                    "interval": 2,
                    "count": 6,
                    "recurrence_present": True,
                },
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated recurring event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "2",
            "--recurrence-count",
            "6",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"]["count"] == 6


def test_cli_calendar_plan_and_apply_update_unbounded_recurrence(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated unbounded recurring event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "2",
            "--recurrence-unbounded",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    expected_recurrence = {
        "frequency": "weekly",
        "interval": 2,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert plan["preview"]["proposed"]["recurrence"] == expected_recurrence
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_frequency"] == "weekly"
        assert kwargs["recurrence_interval"] == 2
        assert kwargs["recurrence_count"] is None
        assert kwargs["recurrence_end_date"] == ""
        assert kwargs["recurrence_unbounded"] is True
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic updated unbounded recurring event",
                "recurrence": expected_recurrence,
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic updated unbounded recurring event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-interval",
            "2",
            "--recurrence-unbounded",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence"] == expected_recurrence


def test_cli_calendar_plan_and_apply_event_url(monkeypatch, capsys) -> None:
    event_url = "mailto:calendar-link@example.invalid"
    expected_sha = hashlib.sha256(event_url.encode("utf-8")).hexdigest()
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic URL event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--event-url",
            event_url,
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["event_url_requested"] is True
    assert plan["preview"]["proposed"]["event_url_scheme"] == "mailto"
    assert plan["preview"]["proposed"]["event_url_domain"] == ""
    assert plan["preview"]["proposed"]["event_url_safe_sha256"] == expected_sha
    assert event_url not in json.dumps(plan, sort_keys=True)
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "create"
        assert kwargs["event_url"] == event_url
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
            "read_back": {
                "title": "Synthetic URL event",
                "url_present": True,
                "event_url_safe_sha256": expected_sha,
                "event_url_verified": True,
            },
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
            "Synthetic URL event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--event-url",
            event_url,
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["event_url_verified"] is True


def test_cli_calendar_plan_and_apply_clear_event_url(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    expected_sha = hashlib.sha256(
        "https://meet.example.invalid/current?id=42".encode("utf-8")
    ).hexdigest()
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-event-url-present",
            "--expected-event-url-sha256",
            expected_sha,
            "--title",
            "Synthetic cleared URL event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--clear-event-url",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["event_url_clear_requested"] is True
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_event_url"] is True
        assert kwargs["expected_event_url_present"] is True
        assert kwargs["expected_event_url_sha256"] == expected_sha
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic cleared URL event",
                "url_present": False,
                "event_url_cleared_verified": True,
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-event-url-present",
            "--expected-event-url-sha256",
            expected_sha,
            "--title",
            "Synthetic cleared URL event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--clear-event-url",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["event_url_cleared_verified"] is True


def test_cli_calendar_plan_and_apply_clear_recurrence(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1", "2026-06-03T17:00:00.000Z", "2026-06-03T18:00:00.000Z")
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_recurrence"] is True
        assert kwargs["handle"] == handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {"recurrence_clear_requested": True},
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-recurrence",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence_clear_requested"] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_recurrence"] is True
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic planning event",
                "recurrence_present": False,
                "recurrence_cleared_verified": True,
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-recurrence",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence_cleared_verified"] is True


def test_cli_calendar_plan_and_apply_mid_series_clear_recurrence(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_recurrence"] is True
        assert kwargs["recurrence_update_scope"] == "future-events"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_clear_requested": True,
                    "recurrence_update_scope": "future_events",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-recurrence",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "recurrence_update_scope"
    ] == "future_events"

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_recurrence"] is True
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic planning event",
                "recurrence_present": False,
                "recurrence_cleared_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-recurrence",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    assert json.loads(capsys.readouterr().out)["read_back"][
        "previous_occurrence_verified_present"
    ] is True


def test_cli_calendar_plan_and_apply_mid_series_recurrence_replacement(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["clear_recurrence"] is False
        assert kwargs["recurrence_frequency"] == "daily"
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_update_scope"] == "future-events"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "recurrence": {
                        "frequency": "daily",
                        "interval": 1,
                        "count": 4,
                        "recurrence_present": True,
                    },
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-frequency",
            "daily",
            "--recurrence-count",
            "4",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "recurrence_update_scope"
    ] == "future_events"

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_frequency"] == "daily"
        assert kwargs["recurrence_count"] == 4
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "recurrence_replaced_verified": True,
                "future_occurrence_verified_present": True,
                "previous_occurrence_verified_present": True,
                "future_original_slot_verified_replaced_or_absent": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-frequency",
            "daily",
            "--recurrence-count",
            "4",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["recurrence_replaced_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_scalar_update(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["title"] == "Synthetic future series event"
        assert kwargs["location"] == "Future Room"
        assert kwargs["notes"] == "Future series notes."
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_scalar_update_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "",
            "--expected-notes",
            "",
            "--title",
            "Synthetic future series event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Future Room",
            "--notes",
            "Future series notes.",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_scalar_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_scalar_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "",
            "--expected-notes",
            "",
            "--title",
            "Synthetic future series event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Future Room",
            "--notes",
            "Future series notes.",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_scalar_updated_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_reschedule(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_time_zone"] == "America/Los_Angeles"
        assert kwargs["time_zone"] == "America/New_York"
        assert kwargs["start_date"] == "2026-06-03T19:00:00Z"
        assert kwargs["end_date"] == "2026-06-03T20:00:00Z"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_reschedule_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--time-zone",
            "America/New_York",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_reschedule_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_time_zone"] == "America/Los_Angeles"
        assert kwargs["time_zone"] == "America/New_York"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_rescheduled_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent_or_replaced": True,
                "future_original_occurrence_verified_absent_or_replaced": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T19:00:00Z",
            "--end-date",
            "2026-06-03T20:00:00Z",
            "--time-zone",
            "America/New_York",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_rescheduled_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_availability(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_availability"] == "busy"
        assert kwargs["availability"] == "free"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_availability_update_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-availability",
            "busy",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--availability",
            "free",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_availability_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_availability"] == "busy"
        assert kwargs["availability"] == "free"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_availability_updated_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-availability",
            "busy",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--availability",
            "free",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_availability_updated_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_event_url(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"
    event_url = "https://meet.example.invalid/future-series-url"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["event_url"] == event_url
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_event_url_update_requested": True,
                    "event_url_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--event-url",
            event_url,
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_event_url_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["event_url"] == event_url
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_event_url_updated_verified": True,
                "event_url_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--event-url",
            event_url,
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_event_url_updated_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_clear_event_url(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"
    expected_sha = hashlib.sha256(
        "https://meet.example.invalid/current-future-series".encode("utf-8")
    ).hexdigest()

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["clear_event_url"] is True
        assert kwargs["expected_event_url_present"] is True
        assert kwargs["expected_event_url_sha256"] == expected_sha
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_event_url_update_requested": True,
                    "event_url_clear_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-event-url-present",
            "--expected-event-url-sha256",
            expected_sha,
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-event-url",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "event_url_clear_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["clear_event_url"] is True
        assert kwargs["expected_event_url_present"] is True
        assert kwargs["expected_event_url_sha256"] == expected_sha
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_event_url_updated_verified": True,
                "url_present": False,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-event-url-present",
            "--expected-event-url-sha256",
            expected_sha,
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-event-url",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_event_url_updated_verified"] is True
    assert parsed["read_back"]["url_present"] is False


def test_cli_calendar_plan_and_apply_future_series_structured_location(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"
    structured_json = json.dumps(
        {
            "title": "Future Conference Room",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius_meters": 25,
        }
    )

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["structured_location"] == json.loads(structured_json)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_structured_location_update_requested": True,
                    "structured_location_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--structured-location",
            structured_json,
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_structured_location_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["structured_location"] == json.loads(structured_json)
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_structured_location_updated_verified": True,
                "structured_location_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--structured-location",
            structured_json,
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_structured_location_updated_verified"] is True


def test_cli_calendar_plan_and_apply_future_series_clear_structured_location(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"
    expected_structured_json = json.dumps({"title": "Synthetic Current Room"})

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["clear_structured_location"] is True
        assert kwargs["expected_structured_location"] == json.loads(expected_structured_json)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_structured_location_update_requested": True,
                    "structured_location_clear_requested": True,
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-structured-location",
            expected_structured_json,
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-structured-location",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "structured_location_clear_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["clear_structured_location"] is True
        assert kwargs["expected_structured_location"] == json.loads(expected_structured_json)
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_structured_location_updated_verified": True,
                "structured_location_present": False,
                "structured_location_cleared_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-structured-location",
            expected_structured_json,
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--clear-structured-location",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_structured_location_updated_verified"] is True
    assert parsed["read_back"]["structured_location_present"] is False


def test_cli_calendar_plan_and_apply_future_series_display_alarm(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == [-10]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_display_alarm_update_requested": True,
                    "alarm_offsets_minutes": [-10],
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=-10",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_display_alarm_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == [-10]
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_display_alarm_updated_verified": True,
                "alarm_offsets_minutes": [-10],
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=-10",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_display_alarm_updated_verified"] is True
    assert parsed["read_back"]["alarm_offsets_minutes"] == [-10]


def test_cli_calendar_plan_and_apply_future_series_clear_display_alarm(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == []
        assert kwargs["alarm_absolute_dates"] == []
        assert kwargs["expected_alarm_offsets_minutes"] == [-10]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_display_alarm_update_requested": True,
                    "alarm_offsets_minutes": [],
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-alarm-offsets-minutes=-10",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=",
            "--alarm-absolute-dates=",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_display_alarm_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == []
        assert kwargs["alarm_absolute_dates"] == []
        assert kwargs["expected_alarm_offsets_minutes"] == [-10]
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_display_alarm_updated_verified": True,
                "alarm_offsets_minutes": [],
                "alarms_count": 0,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-alarm-offsets-minutes=-10",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=",
            "--alarm-absolute-dates=",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_display_alarm_updated_verified"] is True
    assert parsed["read_back"]["alarm_offsets_minutes"] == []


def test_cli_calendar_plan_and_apply_future_series_action_alarm(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == [-10]
        assert kwargs["alarm_sound_name"] == "Glass"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_action_alarm_update_requested": True,
                    "alarm_offsets_minutes": [-10],
                    "alarm_sound_name": "Glass",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=-10",
            "--alarm-sound-name",
            "Glass",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    plan_parsed = json.loads(capsys.readouterr().out)
    assert plan_parsed["preview"]["proposed"][
        "future_series_action_alarm_update_requested"
    ] is True
    assert "alarm_email_address" not in plan_parsed["preview"]["proposed"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == [-10]
        assert kwargs["alarm_sound_name"] == "Glass"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_action_alarm_updated_verified": True,
                "alarm_offsets_minutes": [-10],
                "alarm_sound_name": "Glass",
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=-10",
            "--alarm-sound-name",
            "Glass",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_action_alarm_updated_verified"] is True
    assert parsed["read_back"]["alarm_sound_name"] == "Glass"
    assert parsed["read_back"]["alarm_offsets_minutes"] == [-10]
    assert "alarm_email_address" not in parsed["read_back"]


def test_cli_calendar_plan_and_apply_future_series_clear_action_alarm(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == []
        assert kwargs["alarm_absolute_dates"] == []
        assert kwargs["alarm_sound_name"] == ""
        assert kwargs["expected_alarm_offsets_minutes"] == [-10]
        assert kwargs["expected_alarm_sound_name"] == "Glass"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_action_alarm_update_requested": True,
                    "alarm_offsets_minutes": [],
                    "alarm_sound_name": "",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-alarm-offsets-minutes=-10",
            "--expected-alarm-sound-name",
            "Glass",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=",
            "--alarm-absolute-dates=",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_action_alarm_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["alarm_offsets_minutes"] == []
        assert kwargs["alarm_absolute_dates"] == []
        assert kwargs["alarm_sound_name"] == ""
        assert kwargs["expected_alarm_offsets_minutes"] == [-10]
        assert kwargs["expected_alarm_sound_name"] == "Glass"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_action_alarm_updated_verified": True,
                "alarm_offsets_minutes": [],
                "alarm_sound_name": "",
                "alarms_count": 0,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-alarm-offsets-minutes=-10",
            "--expected-alarm-sound-name",
            "Glass",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--location",
            "Synthetic Room",
            "--alarm-offsets-minutes=",
            "--alarm-absolute-dates=",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_action_alarm_updated_verified"] is True
    assert parsed["read_back"]["alarm_sound_name"] == ""
    assert parsed["read_back"]["alarm_offsets_minutes"] == []


def test_cli_calendar_plan_and_apply_future_series_all_day(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["start_date"] == "2026-06-03"
        assert kwargs["end_date"] == "2026-06-04"
        assert kwargs["all_day"] is True
        assert kwargs["time_zone"] == ""
        assert kwargs["expected_time_zone"] == "America/Los_Angeles"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_all_day_update_requested": True,
                    "all_day": True,
                    "start_date": "2026-06-03",
                    "end_date": "2026-06-04",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03",
            "--end-date",
            "2026-06-04",
            "--all-day",
            "--location",
            "Synthetic Room",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    plan_parsed = json.loads(capsys.readouterr().out)
    assert plan_parsed["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True
    assert plan_parsed["preview"]["proposed"]["all_day"] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["start_date"] == "2026-06-03"
        assert kwargs["end_date"] == "2026-06-04"
        assert kwargs["all_day"] is True
        assert kwargs["time_zone"] == ""
        assert kwargs["expected_time_zone"] == "America/Los_Angeles"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_all_day_updated_verified": True,
                "all_day": True,
                "start_date": "2026-06-03",
                "end_date": "2026-06-04",
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent_or_replaced": True,
                "future_original_occurrence_verified_absent_or_replaced": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03",
            "--end-date",
            "2026-06-04",
            "--all-day",
            "--location",
            "Synthetic Room",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_all_day_updated_verified"] is True
    assert parsed["read_back"]["all_day"] is True
    assert parsed["read_back"]["start_date"] == "2026-06-03"
    assert parsed["read_back"]["end_date"] == "2026-06-04"


def test_cli_calendar_plan_and_apply_future_series_clear_all_day(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-05",
        "2026-06-06",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_all_day"] is True
        assert kwargs["all_day"] is False
        assert kwargs["start_date"] == "2026-06-05T17:00:00Z"
        assert kwargs["end_date"] == "2026-06-05T18:00:00Z"
        assert kwargs["time_zone"] == "America/Los_Angeles"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_all_day_update_requested": True,
                    "all_day": False,
                    "time_zone": "America/Los_Angeles",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic all day recurring event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05",
            "--expected-end-date",
            "2026-06-06",
            "--expected-all-day",
            "--title",
            "Synthetic all day recurring event",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--time-zone",
            "America/Los_Angeles",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    assert json.loads(capsys.readouterr().out)["preview"]["proposed"][
        "future_series_all_day_update_requested"
    ] is True

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["expected_all_day"] is True
        assert kwargs["all_day"] is False
        assert kwargs["start_date"] == "2026-06-05T17:00:00Z"
        assert kwargs["end_date"] == "2026-06-05T18:00:00Z"
        assert kwargs["time_zone"] == "America/Los_Angeles"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_all_day_updated_verified": True,
                "all_day": False,
                "time_zone": "America/Los_Angeles",
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
                "original_occurrence_verified_absent_or_replaced": True,
                "future_original_occurrence_verified_absent_or_replaced": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic all day recurring event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-05",
            "--expected-end-date",
            "2026-06-06",
            "--expected-all-day",
            "--title",
            "Synthetic all day recurring event",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--time-zone",
            "America/Los_Angeles",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_all_day_updated_verified"] is True
    assert parsed["read_back"]["all_day"] is False
    assert parsed["read_back"]["time_zone"] == "America/Los_Angeles"


def test_cli_calendar_plan_and_apply_future_series_calendar_move(
    monkeypatch, capsys
) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    target_calendar_handle = make_opaque_handle("calendar:calendar", "calendar-2")
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["target_calendar_handle"] == target_calendar_handle
        assert kwargs["time_zone"] == "America/Los_Angeles"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {
                    "recurrence_update_scope": "future_events",
                    "future_series_calendar_move_requested": True,
                    "selected_occurrence_calendar_move_requested": False,
                    "target_calendar_handle": target_calendar_handle,
                    "target_calendar_verified": True,
                    "target_calendar_title": "Synthetic Focus",
                },
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_calendar_change", fake_plan_calendar_change)
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--target-calendar-handle",
            target_calendar_handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--time-zone",
            "America/Los_Angeles",
            "--location",
            "Synthetic Room",
            "--recurrence-update-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    plan_parsed = json.loads(capsys.readouterr().out)
    assert plan_parsed["preview"]["proposed"][
        "future_series_calendar_move_requested"
    ] is True
    assert plan_parsed["preview"]["proposed"][
        "target_calendar_handle"
    ] == target_calendar_handle

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "future-events"
        assert kwargs["recurrence_frequency"] == ""
        assert kwargs["target_calendar_handle"] == target_calendar_handle
        assert kwargs["time_zone"] == "America/Los_Angeles"
        assert kwargs["approval_token"] == token
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "recurrence_update_scope": "future_events",
                "future_series_calendar_move_verified": True,
                "previous_occurrence_calendar_verified": True,
                "calendar_title": "Synthetic Focus",
                "target_calendar_handle": target_calendar_handle,
                "target_calendar_verified": True,
                "selected_occurrence_updated_verified": True,
                "future_occurrence_updated_verified": True,
                "previous_occurrence_verified_present": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_calendar_change", fake_apply_calendar_change)
    apply_exit_code = main(
        [
            "calendar",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--target-calendar-handle",
            target_calendar_handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-location",
            "Synthetic Room",
            "--expected-time-zone",
            "America/Los_Angeles",
            "--title",
            "Synthetic planning event",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--time-zone",
            "America/Los_Angeles",
            "--location",
            "Synthetic Room",
            "--recurrence-update-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )
    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["future_series_calendar_move_verified"] is True
    assert parsed["read_back"]["previous_occurrence_calendar_verified"] is True
    assert parsed["read_back"]["calendar_title"] == "Synthetic Focus"
    assert parsed["read_back"]["target_calendar_verified"] is True


def test_cli_calendar_plan_and_apply_recurring_occurrence_update(monkeypatch, capsys) -> None:
    handle = make_opaque_handle(
        "calendar:event",
        "event-1",
        "2026-06-03T17:00:00.000Z",
        "2026-06-03T18:00:00.000Z",
    )
    token = "calendar-apply:v1:abc123"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "this-event"
        assert kwargs["handle"] == handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update",
                "target": {"handle": handle},
                "proposed": {"recurrence_update_scope": "this_event"},
                "approval": {"approval_fingerprint": "abc123"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic occurrence update",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-update-scope",
            "this-event",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence_update_scope"] == "this_event"

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "update"
        assert kwargs["recurrence_update_scope"] == "this-event"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "title": "Synthetic occurrence update",
                "recurrence_update_scope": "this_event",
                "selected_occurrence_updated_verified": True,
                "adjacent_occurrence_verified_present": True,
            },
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
            "update",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--title",
            "Synthetic occurrence update",
            "--start-date",
            "2026-06-03T17:00:00Z",
            "--end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-update-scope",
            "this-event",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["read_back"]["selected_occurrence_updated_verified"] is True


def test_cli_calendar_event_url_rejects_operation_mismatches(capsys) -> None:
    create_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic URL event",
            "--calendar-title",
            "Synthetic Calendar",
            "--start-date",
            "2026-06-05T17:00:00Z",
            "--end-date",
            "2026-06-05T18:00:00Z",
            "--expected-event-url-present",
            "--expected-event-url-sha256",
            "a" * 64,
        ]
    )
    assert create_exit_code == 0
    create_result = json.loads(capsys.readouterr().out)
    assert create_result["status"] == "error"
    assert create_result["warnings"][0]["code"] == "unsupported_expected_state_for_operation"

    handle = make_opaque_handle("calendar:event", "event-1")
    delete_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--event-url",
            "http://meet.example.invalid/runtime?id=42",
        ]
    )
    assert delete_exit_code == 0
    delete_result = json.loads(capsys.readouterr().out)
    assert delete_result["status"] == "error"
    assert delete_result["warnings"][0]["code"] == "unsupported_event_url_for_operation"


def test_cli_calendar_plan_and_apply_delete(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-all-day",
            "--expected-location",
            "Synthetic Room",
            "--expected-notes",
            "Synthetic event notes.",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["title"] == ""
        assert kwargs["start_date"] == ""
        assert kwargs["end_date"] == ""
        assert kwargs["handle"] == handle
        assert kwargs["expected_title"] == "Synthetic planning event"
        assert kwargs["expected_calendar_title"] == "Synthetic Calendar"
        assert kwargs["expected_all_day"] is True
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"handle": handle, "deleted": True, "verified_absent": True},
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
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--expected-all-day",
            "--expected-location",
            "Synthetic Room",
            "--expected-notes",
            "Synthetic event notes.",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "delete"
    assert parsed["read_back"]["verified_absent"] is True


def test_cli_calendar_plan_and_apply_delete_recurring_occurrence(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "this-event"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation_preview"},
            "mode": "plan",
            "operation": "delete",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "target": {
                    "expected_state": {
                        "recurrence_expected": True,
                    },
                },
                "proposed": {
                    "recurrence_delete_scope": "this_event",
                    "recurrence_present": True,
                },
                "approval": {
                    "approval_fingerprint": "cli-recurring-delete-fingerprint",
                },
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "this-event",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence_delete_scope"] == "this_event"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "this-event"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"handle": handle, "deleted": True, "verified_absent": True},
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
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "this-event",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["verified_absent"] is True


def test_cli_calendar_plan_and_apply_delete_future_recurring_span(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "future-events"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation_preview"},
            "mode": "plan",
            "operation": "delete",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "target": {
                    "expected_state": {
                        "recurrence_expected": True,
                    },
                },
                "proposed": {
                    "recurrence_delete_scope": "future_events",
                    "recurrence_present": True,
                },
                "approval": {
                    "approval_fingerprint": "cli-future-recurring-delete-fingerprint",
                },
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "future-events",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence_delete_scope"] == "future_events"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "future-events"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "handle": handle,
                "deleted": True,
                "verified_absent": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_present": True,
            },
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
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "future-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["future_occurrence_verified_absent"] is True


def test_cli_calendar_plan_and_apply_delete_all_recurring_span(monkeypatch, capsys) -> None:
    handle = make_opaque_handle("calendar:event", "event-1")

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "all-events"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation_preview"},
            "mode": "plan",
            "operation": "delete",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "target": {"expected_state": {"recurrence_expected": True}},
                "proposed": {
                    "recurrence_delete_scope": "all_events",
                    "recurrence_present": True,
                },
                "approval": {
                    "approval_fingerprint": "cli-all-recurring-delete-fingerprint",
                },
            },
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.cli.plan_calendar_change",
        fake_plan_calendar_change,
    )

    plan_exit_code = main(
        [
            "calendar",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "all-events",
        ]
    )
    assert plan_exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["preview"]["proposed"]["recurrence_delete_scope"] == "all_events"
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def fake_apply_calendar_change(operation: str, **kwargs):
        assert operation == "delete"
        assert kwargs["handle"] == handle
        assert kwargs["recurrence_delete_scope"] == "all-events"
        assert kwargs["approval_token"] == token
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "handle": handle,
                "deleted": True,
                "verified_absent": True,
                "future_occurrence_verified_absent": True,
                "previous_occurrence_verified_absent": True,
            },
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
            "delete",
            "--handle",
            handle,
            "--expected-title",
            "Synthetic planning event",
            "--expected-calendar-title",
            "Synthetic Calendar",
            "--expected-start-date",
            "2026-06-03T17:00:00Z",
            "--expected-end-date",
            "2026-06-03T18:00:00Z",
            "--recurrence-delete-scope",
            "all-events",
            "--approval-token",
            token,
            "--confirm-apply",
        ]
    )

    assert apply_exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["read_back"]["future_occurrence_verified_absent"] is True
    assert parsed["read_back"]["previous_occurrence_verified_absent"] is True


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
