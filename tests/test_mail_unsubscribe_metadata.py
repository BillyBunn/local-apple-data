from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.adapters.mail import (
    get_mail_unsubscribe_metadata,
    search_mail_metadata,
)
from local_apple_data.cli import main
from local_apple_data.mcp_server import (
    mail_get_unsubscribe_metadata as mcp_mail_get_unsubscribe_metadata,
)
from local_apple_data.redacted_log import log_result


def _mail_store(tmp_path: Path) -> tuple[Path, Path, str]:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
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
            INSERT INTO subjects VALUES (1, 'Synthetic newsletter');
            INSERT INTO mailboxes VALUES (1, 'local://synthetic/INBOX');
            INSERT INTO messages VALUES (10, 1, 1, 10, 9, 0, 0, 0, 12);
            """
        )
    handle = search_mail_metadata("newsletter", db_path=db_path)["results"][0]["handle"]
    return db_path, mail_root, handle


def _write_emlx(mail_root: Path, mime_text: str, *, partial: bool = False) -> None:
    mime_bytes = mime_text.encode("utf-8")
    suffix = ".partial.emlx" if partial else ".emlx"
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages" / f"10{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes + b"\n")


def test_exact_unsubscribe_metadata_returns_only_allowlisted_header_detail(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    _write_emlx(
        mail_root,
        "Subject: MIME subject is not returned\r\n"
        "From: private-sender@example.test\r\n"
        "X-Private-Header: private-header-value\r\n"
        "List-Unsubscribe: <mailto:leave@example.test?subject=remove>, "
        "<HTTPS://unsubscribe.example.test/u?token=synthetic>, "
        "<https://unsubscribe.example.test/u?token=synthetic>, "
        "<http://unsubscribe.example.test/manual>, "
        "<ftp://unsafe.example.test/remove>, "
        "<https://unsafe.example.test/%0d%0aheader>, "
        "<https://[malformed.example.test/remove>\r\n"
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"
        "List-Help: <https://help.example.test/list>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Private body text must never be returned.\r\n",
    )

    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert payload["status"] == "ok"
    assert payload["privacy"] == {
        "content_inspected": False,
        "header_inspected": True,
        "message_body_inspected": False,
        "endpoint_urls_returned": True,
        "raw_headers_returned": False,
        "unrelated_headers_returned": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "exact_header_detail",
    }
    result = payload["result"]
    assert result["handle"] == handle
    assert result["subject"] == "Synthetic newsletter"
    assert result["account_ref"].startswith("account:")
    assert result["mailbox_ref"].startswith("mailbox:")
    assert result["rfc8058_one_click_header"] is True
    assert result["one_click_available"] is True
    assert [item["scheme"] for item in result["unsubscribe_endpoints"]] == [
        "mailto",
        "https",
        "http",
    ]
    assert result["unsubscribe_endpoints"][0]["manual_required"] is True
    assert result["unsubscribe_endpoints"][1]["classification"] == "one_click"
    assert result["unsubscribe_endpoints"][1]["request_method"] == "POST"
    assert result["unsubscribe_endpoints"][2]["manual_required"] is True
    assert result["help_endpoints"][0]["action"] == "help"
    assert result["help_endpoints"][0]["one_click"] is False
    assert result["help_endpoints"][0]["manual_required"] is True
    assert result["unsubscribe_endpoints"][1]["request_content_type"] == (
        "application/x-www-form-urlencoded"
    )
    assert result["unsubscribe_endpoints"][1]["request_body"] == (
        "List-Unsubscribe=One-Click"
    )
    assert result["rejected_endpoint_count"] == 3
    assert result["body_links_requested"] is False
    assert result["body_links_inspected"] is False
    assert result["body_unsubscribe_endpoints"] == []
    assert payload["warnings"][0]["code"] == "unsafe_list_endpoint_omitted"
    encoded = json.dumps(payload, sort_keys=True)
    assert "private-sender" not in encoded
    assert "private-header-value" not in encoded
    assert "Private body text" not in encoded
    assert "ftp://" not in encoded
    assert "%0d%0a" not in encoded.casefold()


def test_one_click_requires_exact_post_value_and_https(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    _write_emlx(
        mail_root,
        "List-Unsubscribe: <http://unsubscribe.example.test/remove>, "
        "<mailto:leave@example.test>\r\n"
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click; extra=true\r\n"
        "\r\nbody\r\n",
    )

    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert payload["status"] == "ok"
    assert payload["result"]["rfc8058_one_click_header"] is False
    assert payload["result"]["one_click_available"] is False
    assert all(item["manual_required"] for item in payload["result"]["unsubscribe_endpoints"])
    assert {warning["code"] for warning in payload["warnings"]} == {
        "invalid_list_unsubscribe_post"
    }


def test_list_help_is_never_classified_as_one_click(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    _write_emlx(
        mail_root,
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"
        "List-Help: <https://help.example.test/remove>\r\n"
        "\r\nbody\r\n",
    )

    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert payload["result"]["unsubscribe_endpoints"] == []
    assert payload["result"]["help_endpoints"][0]["action"] == "help"
    assert payload["result"]["help_endpoints"][0]["one_click"] is False
    assert payload["result"]["help_endpoints"][0]["manual_required"] is True
    assert payload["result"]["one_click_available"] is False
    assert payload["warnings"][0]["code"] == "one_click_endpoint_unavailable"


def test_opt_in_body_links_return_only_conservative_manual_endpoints(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    _write_emlx(
        mail_root,
        "Content-Type: text/html; charset=utf-8\r\n\r\n"
        "<html><body>"
        '<a href="https://news.example.test/article">Read more</a>'
        '<a href="https://news.example.test/unsubscribe-explicit">Unsubscribe</a>'
        '<a href="https://news.example.test/unsubscribe?id=synthetic">Click here</a>'
        '<a href="https://news.example.test/email_optout?id=synthetic">Continue</a>'
        '<p>To stop receiving these messages, '
        '<a href="https://news.example.test/leave-adjacent">click here</a></p>'
        "<p>Unsubscribe "
        + ("x" * 151)
        + '<a href="https://news.example.test/too-far">click here</a></p>'
        '<a href="https://news.example.test/manage/preferences?unsubscribe=1">Click here</a>'
        '<a href="https://news.example.test/login/unsubscribe">Click here</a>'
        '<a href="https://news.example.test/resubscribe?unsubscribe=1">Click here</a>'
        '<a href="https://news.example.test/manage">Unsubscribe from this list</a>'
        '<a href="javascript:alert(1)">Unsubscribe</a>'
        '<a href="https://unsafe.example.test/%0aheader">Unsubscribe</a>'
        "<script><a href=\"https://hidden.example.test/unsubscribe\">Unsubscribe</a></script>"
        "</body></html>",
    )

    default_payload = get_mail_unsubscribe_metadata(
        handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    assert default_payload["privacy"]["message_body_inspected"] is False
    assert default_payload["result"]["body_links_requested"] is False
    assert default_payload["result"]["body_unsubscribe_endpoints"] == []
    assert "unsubscribe-explicit" not in json.dumps(default_payload, sort_keys=True)

    payload = get_mail_unsubscribe_metadata(
        handle,
        db_path=db_path,
        mail_root=mail_root,
        include_body_links=True,
    )

    assert payload["status"] == "ok"
    assert payload["privacy"]["content_inspected"] is True
    assert payload["privacy"]["message_body_inspected"] is True
    assert payload["result"]["body_links_requested"] is True
    assert payload["result"]["body_links_inspected"] is True
    endpoints = payload["result"]["body_unsubscribe_endpoints"]
    assert [endpoint["url"] for endpoint in endpoints] == [
        "https://news.example.test/unsubscribe-explicit",
        "https://news.example.test/unsubscribe?id=synthetic",
        "https://news.example.test/email_optout?id=synthetic",
        "https://news.example.test/leave-adjacent",
        "https://news.example.test/manage",
    ]
    assert all(endpoint["classification"] == "body_link" for endpoint in endpoints)
    assert [endpoint["match_reason"] for endpoint in endpoints] == [
        "explicit_unsubscribe_text",
        "unsubscribe_url",
        "unsubscribe_url",
        "adjacent_unsubscribe_phrase",
        "explicit_unsubscribe_text",
    ]
    assert all(endpoint["manual_required"] is True for endpoint in endpoints)
    assert all(endpoint["one_click"] is False for endpoint in endpoints)
    assert all(endpoint["request_body"] is None for endpoint in endpoints)
    encoded = json.dumps(payload, sort_keys=True)
    assert "Read more" not in encoded
    assert "Click here" not in encoded
    assert "stop receiving these messages" not in encoded
    assert "article" not in encoded
    assert "too-far" not in encoded
    assert "manage/preferences" not in encoded
    assert "login/unsubscribe" not in encoded
    assert "resubscribe" not in encoded
    assert "hidden.example" not in encoded
    assert "javascript:" not in encoded
    assert "%0a" not in encoded.casefold()


def test_body_links_deduplicate_preserve_order_and_cap_at_five(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    anchors = "".join(
        f'<a href="https://news.example.test/leave-{index}">Unsubscribe</a>'
        for index in range(7)
    )
    anchors += '<a href="https://news.example.test/leave-0">Unsubscribe again</a>'
    _write_emlx(
        mail_root,
        "Content-Type: text/html; charset=utf-8\r\n\r\n" + anchors,
    )

    payload = get_mail_unsubscribe_metadata(
        handle,
        db_path=db_path,
        mail_root=mail_root,
        include_body_links=True,
    )

    assert [
        endpoint["url"] for endpoint in payload["result"]["body_unsubscribe_endpoints"]
    ] == [f"https://news.example.test/leave-{index}" for index in range(5)]
    assert {
        endpoint["match_reason"]
        for endpoint in payload["result"]["body_unsubscribe_endpoints"]
    } == {"explicit_unsubscribe_text"}


def test_unsubscribe_metadata_rejects_non_exact_handles(tmp_path: Path) -> None:
    db_path, mail_root, _handle = _mail_store(tmp_path)
    for unsafe in (
        "10",
        "mail:message:10",
        "mail:message:v1:abcdef0123456789abcdef0123456789",
        "mailbox:raw",
        str(mail_root / "Synthetic.mbox/INBOX.mbox/Messages/10.emlx"),
    ):
        payload = get_mail_unsubscribe_metadata(
            unsafe,
            db_path=db_path,
            mail_root=mail_root,
        )
        assert payload["status"] == "error"
        assert payload["warnings"][0]["code"] == "invalid_handle"
        assert payload["privacy"]["header_inspected"] is False


def test_unsubscribe_metadata_fails_closed_without_unique_local_file(tmp_path: Path) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)

    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert payload["status"] == "metadata_unavailable"
    assert payload["result"]["handle"] == handle
    assert payload["privacy"]["header_inspected"] is False
    assert payload["warnings"][0]["code"] == "unsubscribe_metadata_unavailable"


def test_unsubscribe_metadata_fails_closed_without_bounded_header_terminator(
    tmp_path: Path,
) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    mime_bytes = (
        b"Subject: Unterminated synthetic header\r\n"
        b"List-Unsubscribe: <https://unsubscribe.example.test/u>\r\n"
    )
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages/10.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes)

    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert payload["status"] == "metadata_unavailable"
    assert payload["privacy"]["header_inspected"] is False
    assert payload["warnings"][0]["code"] == "unsubscribe_metadata_read_error"
    assert "unsubscribe_endpoints" not in payload["result"]


def test_cli_unsubscribe_metadata_uses_exact_synthetic_handle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    _write_emlx(
        mail_root,
        "List-Unsubscribe: <https://unsubscribe.example.test/u>\r\n"
        "List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"
        "Content-Type: text/html; charset=utf-8\r\n\r\n"
        '<a href="https://unsubscribe.example.test/body">Unsubscribe</a>',
    )
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    exit_code = main(
        [
            "mail",
            "unsubscribe-metadata",
            "--json",
            "--handle",
            handle,
            "--include-body-links",
            "--db",
            str(db_path),
            "--mail-root",
            str(mail_root),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["result"]["one_click_available"] is True
    assert payload["result"]["body_links_inspected"] is True
    assert payload["result"]["body_unsubscribe_endpoints"][0]["classification"] == (
        "body_link"
    )


def test_mcp_unsubscribe_metadata_forwards_body_link_opt_in(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(handle: str, *, include_body_links: bool = False):
        captured.update(handle=handle, include_body_links=include_body_links)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"output_tier": "exact_header_detail"},
            "result": None,
            "result_count": 0,
            "warnings": [],
        }

    monkeypatch.setattr(
        "local_apple_data.mcp_server.get_mail_unsubscribe_metadata",
        fake_get,
    )

    payload = mcp_mail_get_unsubscribe_metadata("mail:message:v2:synthetic", True)

    assert payload["status"] == "ok"
    assert captured == {
        "handle": "mail:message:v2:synthetic",
        "include_body_links": True,
    }


def test_unsubscribe_metadata_log_excludes_handle_subject_and_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root, handle = _mail_store(tmp_path)
    endpoint = "https://unsubscribe.example.test/private-token"
    _write_emlx(mail_root, f"List-Unsubscribe: <{endpoint}>\r\n\r\nbody\r\n")
    payload = get_mail_unsubscribe_metadata(handle, db_path=db_path, mail_root=mail_root)
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    log_result("mail.unsubscribe_metadata", payload)

    logged = (tmp_path / "logs/events.jsonl").read_text(encoding="utf-8")
    assert handle not in logged
    assert "Synthetic newsletter" not in logged
    assert endpoint not in logged
    assert "private-token" not in logged
