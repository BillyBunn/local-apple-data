from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import local_apple_data.adapters.mail as mail_adapter
from local_apple_data.adapters.mail import (
    apply_mail_change,
    build_mail_fts_index,
    create_mail_template,
    delete_mail_template,
    export_mail_attachment,
    get_mail_content,
    get_mail_fts_status,
    get_mail_metadata,
    get_mail_sender,
    get_mail_signature,
    get_mail_template,
    list_mail_attachments,
    plan_mail_change,
    search_mail_advanced,
    search_mail_attachments,
    search_mail_body,
    search_mail_fts,
    search_mail_mailboxes,
    search_mail_metadata,
    search_mail_senders,
    search_mail_signatures,
    search_mail_templates,
)
from local_apple_data.handles import make_int_handle
from local_apple_data.redacted_log import log_result


def _mail_db(path: Path) -> None:
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
            INSERT INTO subjects VALUES
              (1, 'Synthetic content subject'),
              (2, 'Synthetic html subject'),
              (3, 'Synthetic deleted subject');
            INSERT INTO mailboxes VALUES (1, 'local://synthetic/INBOX');
            INSERT INTO messages VALUES
              (10, 1, 1, 10, 9, 0, 0, 0, 12),
              (11, 2, 1, 11, 10, 0, 0, 0, 12),
              (12, 3, 1, 12, 11, 0, 0, 1, 12);
            """
        )


def _write_emlx(mail_root: Path, rowid: int, mime_text: str) -> None:
    mime_bytes = mime_text.encode("utf-8")
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages" / f"{rowid}.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes + b"\n")


def _fts_index_bytes(index_path: Path) -> bytes:
    data = bytearray()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{index_path}{suffix}")
        if candidate.exists():
            data.extend(candidate.read_bytes())
    return bytes(data)


def _insert_draft_message(db_path: Path, *, rowid: int, subject: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
        connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (rowid, "local://synthetic/Drafts"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rowid, rowid, rowid, 20, 20, 0, 0, 0, 12),
        )


def _insert_sent_message(db_path: Path, *, rowid: int, subject: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
        connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (rowid, "local://synthetic/Sent"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rowid, rowid, rowid, 20, 20, 0, 0, 0, 12),
        )


def _insert_mailbox(db_path: Path, *, rowid: int, url: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (rowid, url))


def test_search_mail_metadata_filters_by_exact_mailbox_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _mail_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (2, "local://synthetic/Projects"))
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (4, "Synthetic content subject"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (13, 4, 2, 13, 12, 0, 0, 0, 12),
        )

    mailbox_handle = search_mail_mailboxes("Projects", db_path=db_path)["results"][0]["handle"]
    result = search_mail_metadata(
        "content",
        db_path=db_path,
        mailbox_handle=mailbox_handle,
        limit=10,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["query"]["mailbox_filter"] == "exact_handle"
    assert result["query"]["mailbox_ref"].startswith("mailbox:")
    assert result["results"][0]["mailbox_name"] == "Projects"


def test_search_mail_metadata_rejects_invalid_mailbox_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _mail_db(db_path)

    result = search_mail_metadata(
        "content",
        db_path=db_path,
        mailbox_handle="mailbox:raw",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_mailbox_handle"


def _synthetic_store(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _mail_db(db_path)
    return db_path, mail_root


def test_mail_search_returns_hashed_account_ref_and_no_raw_account_id(tmp_path: Path) -> None:
    # v1.183 attribution: results carry the hashed account_ref (same pseudonymous ref
    # plan flows already expose) and mailbox_path, but never the raw account identifier.
    db_path, _mail_root = _synthetic_store(tmp_path)

    search = search_mail_metadata("content", db_path=db_path)
    handle = search["results"][0]["handle"]
    detail = get_mail_metadata(handle, db_path=db_path)

    assert search["status"] == "ok"
    assert search["results"][0]["account_ref"].startswith("account:")
    assert search["results"][0]["mailbox_path"]
    assert detail["status"] == "ok"
    assert detail["result"]["account_ref"].startswith("account:")
    assert "synthetic" not in json.dumps(search, sort_keys=True)
    assert "synthetic" not in json.dumps(detail, sort_keys=True)


def test_mail_content_parses_synthetic_plain_text_emlx(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic plain body line one.\r\nSynthetic plain body line two.\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "content"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["handle"].startswith("mail:message:v2:")
    assert result["result"]["subject"] == "Synthetic content subject"
    assert result["result"]["content_text"] == (
        "Synthetic plain body line one.\nSynthetic plain body line two."
    )
    assert result["result"]["content_chars"] == len(result["result"]["content_text"])
    assert result["result"]["truncated"] is False


def test_mail_content_html_only_is_deterministic_and_bounded(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        11,
        "Subject: Synthetic html\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        "<html><body><h1>Synthetic HTML</h1><p>First&nbsp;line<br>Second line</p>"
        "<script>hidden text</script></body></html>\r\n",
    )
    handle = search_mail_metadata("html", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root, max_chars=40)

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "Synthetic HTML\nFirst line\nSecond line"
    assert result["result"]["content_chars"] <= 40
    assert result["result"]["truncated"] is False
    assert "hidden text" not in result["result"]["content_text"]


def test_mail_content_rejects_non_v2_message_handles(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    bad_handles = [
        "10",
        "mail:message:10",
        "mail:message:v1:abcdef0123456789abcdef0123456789",
        "mailbox:abcdef012345",
        str(mail_root / "Synthetic.mbox/INBOX.mbox/Messages/10.emlx"),
    ]
    for handle in bad_handles:
        result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)
        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_handle"
        assert result["result"] is None


def test_mail_content_deleted_message_does_not_return_content(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        12,
        "Subject: Synthetic deleted\r\nContent-Type: text/plain\r\n\r\nDeleted synthetic body.\r\n",
    )
    handle = make_int_handle("mail:message", 12)

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_mail_content_truncates_and_warns(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "abcdefghijklmnopqrstuvwxyz\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root, max_chars=8)

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "abcdefgh"
    assert result["result"]["content_chars"] == 8
    assert result["result"]["truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_mail_content_paginates_with_offset(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "abcdefghijklmnopqrstuvwxyz\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(
        handle,
        db_path=db_path,
        mail_root=mail_root,
        max_chars=8,
        offset=8,
    )

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "ijklmnop"
    assert result["result"]["content_offset"] == 8
    assert result["result"]["content_total_chars"] == 26
    assert result["result"]["next_offset"] == 16
    assert result["result"]["truncated"] is True


def test_mail_content_rejects_negative_offset(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    handle = make_int_handle("mail:message", 10)

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root, offset=-1)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_offset"
    assert result["result"] is None


def test_mail_metadata_returns_masked_headers_and_attachment_names(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        "From: Audit Sender <sender@example.invalid>\r\n"
        "To: Receipt Inbox <receipt@example.invalid>\r\n"
        "Cc: Finance <finance@example.invalid>\r\n"
        "Message-ID: <private-message-id@example.invalid>\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic metadata body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_metadata(handle, db_path=db_path, mail_root=mail_root)
    encoded = json.dumps(result, sort_keys=True)

    assert result["status"] == "ok"
    metadata = result["result"]
    assert metadata["header_metadata_status"] == "available"
    assert metadata["from"]["previews"] == ["s***@example.invalid"]
    assert metadata["to"]["previews"] == ["r***@example.invalid"]
    assert metadata["cc"]["previews"] == ["f***@example.invalid"]
    assert metadata["message_id_ref"].startswith("message-id:")
    assert metadata["message_id_returned"] is False
    assert metadata["attachment_metadata_status"] == "available"
    assert metadata["attachment_count"] == 1
    assert metadata["attachment_filenames"] == ["packet.pdf"]
    assert metadata["attachment_content_returned"] is False
    assert metadata["attachment_paths_returned"] is False
    assert "sender@example.invalid" not in encoded
    assert "receipt@example.invalid" not in encoded
    assert "finance@example.invalid" not in encoded
    assert "private-message-id" not in encoded
    assert str(mail_root) not in encoded


def test_mail_metadata_does_not_read_attachment_payload_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        "From: Audit Sender <sender@example.invalid>\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic metadata body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    def fail_payload_read(part) -> bytes:
        raise AssertionError("metadata lookup must not read attachment payload bytes")

    monkeypatch.setattr(mail_adapter, "_attachment_payload_bytes", fail_payload_read)
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_metadata(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    metadata = result["result"]
    assert metadata["attachment_count"] == 1
    assert metadata["attachment_filenames"] == ["packet.pdf"]
    assert metadata["attachment_types"] == ["application/pdf"]


def test_mail_body_search_requires_date_range(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    result = search_mail_body("receipt", db_path=db_path, mail_root=mail_root)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "date_range_required"
    assert result["privacy"]["content_inspected"] is False


def test_mail_body_search_finds_body_only_with_redacted_snippet(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Body-only subscription receipt for payer@example.invalid and RenewalToken42.\r\n",
    )

    result = search_mail_body(
        "RenewalToken42",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        max_snippet_chars=80,
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "content_snippet"
    assert result["privacy"]["content_inspected"] is True
    assert result["result_count"] == 1
    match = result["results"][0]
    assert match["matched_scope"] == "body"
    assert match["handle"].startswith("mail:message:v2:")
    assert "RenewalToken42" in match["snippet"]
    assert "p***@example.invalid" in match["snippet"]
    assert match["content_returned"] is False
    assert match["snippet_chars"] == len(match["snippet"])
    assert "payer@example.invalid" not in encoded
    assert "Body-only subscription receipt for payer" not in encoded


def test_mail_body_search_matches_normalized_whitespace(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Body-only subscription\r\nRenewal\t\tToken42 appears after folded whitespace.\r\n",
    )

    result = search_mail_body(
        "Renewal Token42",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        max_snippet_chars=80,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["matched_scope"] == "body"
    assert "Renewal Token42" in result["results"][0]["snippet"]


def test_mail_attachment_search_finds_global_filename_metadata(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="hsa-receipt.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    result = search_mail_attachments(
        "hsa",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["result_count"] == 1
    match = result["results"][0]
    assert match["matched_scope"] == "attachment_filename"
    assert match["attachment"]["handle"].startswith("mail:attachment:v1:")
    assert match["attachment"]["message_handle"] == match["handle"]
    assert match["attachment"]["filename"] == "hsa-receipt.pdf"
    assert match["attachment"]["content_type"] == "application/pdf"
    assert match["content_returned"] is False
    assert str(mail_root) not in json.dumps(result, sort_keys=True)


def test_mail_attachment_search_reports_mime_metadata_scope(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.bin"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    result = search_mail_attachments(
        "application/pdf",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    match = result["results"][0]
    assert match["matched_scope"] == "attachment_metadata"
    assert match["matched_scopes"] == ["attachment_metadata"]
    assert match["attachment"]["filename"] == "packet.bin"


def test_mail_attachment_search_content_requires_explicit_flag(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        'Content-Disposition: attachment; filename="audit.txt"\r\n'
        "\r\n"
        "Attachment-only reimbursement keyword for alice@example.invalid.\r\n"
        "--BOUNDARY--\r\n",
    )

    metadata_only = search_mail_attachments(
        "reimbursement",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )
    with_content = search_mail_attachments(
        "reimbursement",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
    )

    assert metadata_only["status"] == "ok"
    assert metadata_only["result_count"] == 0
    assert with_content["status"] == "ok"
    assert with_content["privacy"]["attachment_content_returned"] is False
    assert with_content["privacy"]["attachment_content_snippet_returned"] is True
    assert with_content["result_count"] == 1
    match = with_content["results"][0]
    assert match["matched_scope"] == "attachment_content"
    assert match["attachment"]["filename"] == "audit.txt"
    assert match["attachment_text_extractor"] == "text"
    assert "reimbursement keyword" in match["snippet"]
    assert "a***@example.invalid" in match["snippet"]
    assert "alice@example.invalid" not in json.dumps(with_content, sort_keys=True)
    assert str(mail_root) not in json.dumps(with_content, sort_keys=True)


def test_mail_attachment_search_content_redacts_paths_ids_and_phone(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    uuid = "123e4567-e89b-12d3-a456-426614174000"
    sensitive_path = "/Users/synthetic/Private/report.pdf"
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        'Content-Disposition: attachment; filename="audit.txt"\r\n'
        "\r\n"
        f"reimbursement path {sensitive_path} rowid 987654 account_id ABCD-1234 "
        f"{uuid} phone 415-555-1212 sender alice@example.invalid.\r\n"
        "--BOUNDARY--\r\n",
    )

    result = search_mail_attachments(
        "reimbursement",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
    )

    payload = json.dumps(result, sort_keys=True)
    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert "<redacted-path>" in result["results"][0]["snippet"]
    assert "<redacted-id>" in result["results"][0]["snippet"]
    assert "<redacted-phone>" in result["results"][0]["snippet"]
    assert sensitive_path not in payload
    assert "rowid 987654" not in payload
    assert "account_id ABCD-1234" not in payload
    assert uuid not in payload
    assert "415-555-1212" not in payload
    assert "alice@example.invalid" not in payload


def test_mail_attachment_search_content_rejects_declared_oversize_before_decode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "X-Apple-Content-Length: 999999\r\n"
        'Content-Disposition: attachment; filename="huge.txt"\r\n'
        "\r\n"
        "needle should not be decoded.\r\n"
        "--BOUNDARY--\r\n",
    )
    monkeypatch.setattr(mail_adapter, "MAX_MAIL_ATTACHMENT_CONTENT_BYTES", 4)

    def fail_decode(_part):
        raise AssertionError("attachment content search decoded an oversized payload")

    monkeypatch.setattr(mail_adapter, "_attachment_payload_bytes", fail_decode)

    result = search_mail_attachments(
        "needle",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 0


def test_mail_attachment_search_pdf_content_uses_pdf_text_extractor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    monkeypatch.setattr(
        mail_adapter,
        "_pdf_text_from_bytes",
        lambda _data: "embedded deductible packet text",
    )

    result = search_mail_attachments(
        "deductible",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["matched_scope"] == "attachment_content"
    assert result["results"][0]["attachment_text_extractor"] == "pdf_text"
    assert "deductible" in result["results"][0]["snippet"]


def test_mail_attachment_search_pdf_content_can_use_ocr_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="scan.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    monkeypatch.setattr(mail_adapter, "_pdf_text_from_bytes", lambda _data: None)
    monkeypatch.setattr(mail_adapter, "_pdf_ocr_text_from_bytes", lambda _data: "OCR HSA receipt text")

    result = search_mail_attachments(
        "receipt",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
        include_ocr=True,
    )

    assert result["status"] == "ok"
    assert result["query"]["include_ocr"] is True
    assert result["result_count"] == 1
    assert result["results"][0]["matched_scope"] == "attachment_content"
    assert result["results"][0]["attachment_text_extractor"] == "pdf_ocr"
    assert "receipt" in result["results"][0]["snippet"]


def test_mail_attachment_search_pdf_ocr_is_per_search_capped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="first.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="second.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    calls = {"ocr": 0}
    monkeypatch.setattr(mail_adapter, "MAX_MAIL_ATTACHMENT_OCR_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "_pdf_text_from_bytes", lambda _data: None)

    def fake_ocr(_data: bytes) -> str:
        calls["ocr"] += 1
        return "first scanned packet"

    monkeypatch.setattr(mail_adapter, "_pdf_ocr_text_from_bytes", fake_ocr)

    result = search_mail_attachments(
        "second-only-token",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        include_content=True,
        include_ocr=True,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 0
    assert calls["ocr"] == 1
    assert result["query"]["ocr_attempt_count"] == 1
    assert result["query"]["ocr_attempt_limit"] == 1
    assert result["warnings"][0]["code"] == "ocr_attempt_limit_reached"


def test_mail_attachment_search_does_not_read_nonmatching_payload_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain\r\n"
        'Content-Disposition: attachment; filename="ignore.txt"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "SUdOT1JF\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="hsa-receipt.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    def selective_payload_read(part) -> bytes:
        if part.get_filename() == "ignore.txt":
            raise AssertionError("nonmatching attachment payload should not be read")
        return b"PDFDATA"

    monkeypatch.setattr(mail_adapter, "_attachment_payload_bytes", selective_payload_read)

    result = search_mail_attachments(
        "receipt",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["attachment"]["filename"] == "hsa-receipt.pdf"


def test_mail_advanced_subject_only_does_not_parse_message_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    def fail_parse(*args, **kwargs):
        raise AssertionError("subject-only advanced search must not parse message files")

    monkeypatch.setattr(mail_adapter, "_parse_mail_message", fail_parse)

    result = search_mail_advanced(
        "content",
        scopes=["subject"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["result_count"] == 1
    assert result["results"][0]["matched_scopes"] == ["subject"]


def test_mail_advanced_search_iso_date_bounds_match_unix_mail_timestamps(tmp_path: Path) -> None:
    db_path = tmp_path / "mail.sqlite"
    _mail_db(db_path)
    mail_root = tmp_path / "Mail"
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (20, "Your synthetic receipt"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (20, 20, 1, 1782763567, 1782763566, 0, 0, 0, 12),
        )

    result = search_mail_advanced(
        "Your",
        scopes=["subject"],
        after="2026-06-26",
        before="2026-06-30",
        db_path=db_path,
        mail_root=mail_root,
        limit=5,
    )

    assert result["status"] == "ok"
    assert result["query"]["after"] == 1782432000.0
    assert abs(result["query"]["before"] - 1782863999.999) < 0.01
    assert result["result_count"] == 1
    assert result["results"][0]["subject"] == "Your synthetic receipt"


def test_mail_advanced_search_matches_headers_body_and_attachments(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        "From: Billing Team <billing@example.invalid>\r\n"
        "To: Audit Inbox <audit@example.invalid>\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic deductible receipt keyword.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="deductible-packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    from_result = search_mail_advanced(
        "billing",
        scopes=["from"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
    )
    body_result = search_mail_advanced(
        "deductible",
        scopes=["body", "attachment_filename"],
        after=0,
        before=20,
        has_attachments=True,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert from_result["status"] == "ok"
    assert from_result["results"][0]["matched_scopes"] == ["from"]
    assert from_result["results"][0]["from"]["previews"] == ["b***@example.invalid"]
    assert "billing@example.invalid" not in json.dumps(from_result, sort_keys=True)

    assert body_result["status"] == "ok"
    assert body_result["result_count"] == 1
    assert body_result["results"][0]["matched_scopes"] == ["attachment_filename", "body"]
    assert "deductible" in body_result["results"][0]["snippet"]
    assert body_result["results"][0]["attachment_count"] == 1
    assert body_result["results"][0]["attachment_filenames"] == ["deductible-packet.pdf"]


def test_mail_fts_build_requires_date_bound_and_confirmation(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"

    missing_bound = build_mail_fts_index(
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    missing_confirmation = build_mail_fts_index(
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert missing_bound["status"] == "error"
    assert missing_bound["warnings"][0]["code"] == "date_range_required"
    assert missing_confirmation["status"] == "error"
    assert missing_confirmation["warnings"][0]["code"] == "missing_index_confirmation"
    assert not index_path.exists()


def test_mail_fts_build_and_search_body_header_attachment_content(tmp_path: Path) -> None:
    db_path, _default_mail_root = _synthetic_store(tmp_path)
    mail_root = tmp_path / "DetachedMailRoot"
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        "From: Billing Team <billing@example.invalid>\r\n"
        "To: Audit Inbox <audit@example.invalid>\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic FTS body subscription needle for payer@example.invalid.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        'Content-Disposition: attachment; filename="hsa-receipt.txt"\r\n'
        "\r\n"
        "Attachment-only reimbursement needle for alice@example.invalid.\r\n"
        "--BOUNDARY--\r\n",
    )

    build = build_mail_fts_index(
        after=0,
        before=20,
        include_attachments=True,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    body_result = search_mail_fts(
        "subscription needle",
        scopes=["body"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    from_result = search_mail_fts(
        "billing",
        scopes=["from"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    attachment_result = search_mail_fts(
        "reimbursement",
        scopes=["attachment_content"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    encoded = json.dumps(attachment_result, sort_keys=True)

    assert build["status"] == "ok"
    assert build["privacy"]["durable_index_written"] is True
    assert build["result"]["index_path_returned"] is False
    assert build["result"]["messages_indexed"] == 2
    assert build["result"]["body_indexed_count"] == 1
    assert build["result"]["attachment_text_indexed_count"] == 1
    assert index_path.exists()

    assert body_result["status"] == "ok"
    assert body_result["result_count"] == 1
    assert body_result["privacy"]["durable_index_written"] is False
    assert body_result["results"][0]["matched_scope"] == "body"
    assert "subscription needle" in body_result["results"][0]["snippet"]
    assert "payer@example.invalid" not in json.dumps(body_result, sort_keys=True)

    assert from_result["status"] == "ok"
    assert from_result["results"][0]["matched_scope"] == "from"
    assert "billing@example.invalid" not in json.dumps(from_result, sort_keys=True)

    assert attachment_result["status"] == "ok"
    assert attachment_result["result_count"] == 1
    assert attachment_result["results"][0]["matched_scope"] == "attachment_content"
    assert attachment_result["results"][0]["snippet_scope"] == "attachment_content"
    assert attachment_result["results"][0]["attachment_count"] == 1
    assert attachment_result["results"][0]["attachment_filenames"] == ["hsa-receipt.txt"]
    assert attachment_result["results"][0]["attachment_types"] == ["text/plain"]
    assert "reimbursement" in attachment_result["results"][0]["snippet"]
    assert "a***@example.invalid" in attachment_result["results"][0]["snippet"]
    assert "alice@example.invalid" not in encoded
    assert str(index_path) not in encoded


def test_mail_fts_build_paginates_with_cursor(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    with sqlite3.connect(db_path) as connection:
        for rowid, subject, date_value in [
            (20, "FTS build page one", 30),
            (21, "FTS build page two", 29),
            (22, "FTS build page three", 28),
        ]:
            connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rowid, rowid, 1, date_value, date_value, 0, 0, 0, 12),
            )

    first_page = build_mail_fts_index(
        after=25,
        before=31,
        limit=2,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    second_page = build_mail_fts_index(
        after=25,
        before=31,
        cursor=first_page["next_cursor"],
        limit=2,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    search = search_mail_fts(
        "build page",
        scopes=["subject"],
        after=25,
        before=31,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
        limit=10,
    )

    assert first_page["status"] == "ok"
    assert first_page["result"]["messages_indexed"] == 2
    assert first_page["next_cursor"] == "2"
    assert first_page["warnings"][0]["code"] == "mail_fts_build_truncated"
    assert second_page["status"] == "ok"
    assert second_page["result"]["messages_indexed"] == 1
    assert second_page["next_cursor"] == ""
    assert search["status"] == "ok"
    assert search["result_count"] == 3


def test_mail_fts_build_rejects_reset_after_first_page(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    with sqlite3.connect(db_path) as connection:
        for rowid, subject, date_value in [
            (20, "Reset cursor page one", 30),
            (21, "Reset cursor page two", 29),
            (22, "Reset cursor page three", 28),
        ]:
            connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rowid, rowid, 1, date_value, date_value, 0, 0, 0, 12),
            )

    first_page = build_mail_fts_index(
        after=25,
        before=31,
        limit=2,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    invalid_second_page = build_mail_fts_index(
        after=25,
        before=31,
        cursor=first_page["next_cursor"],
        limit=2,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    search = search_mail_fts(
        "Reset cursor page",
        scopes=["subject"],
        after=25,
        before=31,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
        limit=10,
    )

    assert first_page["status"] == "ok"
    assert first_page["next_cursor"] == "2"
    assert invalid_second_page["status"] == "error"
    assert invalid_second_page["warnings"][0]["code"] == "invalid_reset_cursor"
    assert search["status"] == "ok"
    assert search["result_count"] == 2


def test_mail_fts_search_uses_read_only_index_connection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Read-only FTS search needle.\r\n",
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    def fail_writer_schema(_connection):
        raise AssertionError("FTS search must not initialize or write schema")

    monkeypatch.setattr(mail_adapter, "_ensure_mail_fts_schema", fail_writer_schema)
    result = search_mail_fts(
        "needle",
        scopes=["body"],
        after=0,
        before=20,
        db_path=db_path,
        index_path=index_path,
    )

    assert build["status"] == "ok"
    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["privacy"]["durable_index_written"] is False


def test_mail_fts_search_skips_stale_message_content(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "FTS stale-only body needle.\r\n",
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Changed body without the old token.\r\n",
    )

    result = search_mail_fts(
        "stale-only",
        scopes=["body"],
        after=0,
        before=20,
        db_path=db_path,
        index_path=index_path,
    )

    assert build["status"] == "ok"
    assert result["status"] == "ok"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "mail_fts_stale_content"


def test_mail_fts_search_rechecks_current_date_bounds(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "FTS date-drift body needle.\r\n",
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE messages SET date_received = 50, date_sent = 50 WHERE ROWID = 10")

    result = search_mail_fts(
        "date-drift",
        scopes=["body"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert build["status"] == "ok"
    assert result["status"] == "ok"
    assert result["result_count"] == 0


def test_mail_fts_search_paginates_scope_filtered_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (20, "Needle subject one"))
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (21, "Needle subject two"))
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (22, "Body page target"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (20, 20, 1, 30, 30, 0, 0, 0, 12),
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (21, 21, 1, 29, 29, 0, 0, 0, 12),
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (22, 22, 1, 28, 28, 0, 0, 0, 12),
        )
    _write_emlx(
        mail_root,
        22,
        "Subject: Body page target\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Needle body-only result for cursor proof.\r\n",
    )
    monkeypatch.setattr(mail_adapter, "MAX_MAIL_FTS_SEARCH_SCAN_ROWS", 2)
    build = build_mail_fts_index(
        after=0,
        before=40,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    first_page = search_mail_fts(
        "Needle",
        scopes=["body"],
        after=0,
        before=40,
        db_path=db_path,
        index_path=index_path,
        limit=1,
    )
    second_page = search_mail_fts(
        "Needle",
        scopes=["body"],
        after=0,
        before=40,
        cursor=first_page["next_cursor"],
        db_path=db_path,
        index_path=index_path,
        limit=1,
    )

    assert build["status"] == "ok"
    assert first_page["status"] == "ok"
    assert first_page["result_count"] == 0
    assert first_page["next_cursor"] == "2"
    assert second_page["status"] == "ok"
    assert second_page["result_count"] == 1
    assert second_page["results"][0]["matched_scope"] == "body"
    assert "Needle body-only result" in second_page["results"][0]["snippet"]
    assert str(index_path) not in json.dumps(second_page, sort_keys=True)


def test_mail_fts_search_requires_existing_index_and_live_row(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\nContent-Type: text/plain\r\n\r\nFTS disappearing body.\r\n",
    )
    missing = search_mail_fts(
        "disappearing",
        after=0,
        before=20,
        db_path=db_path,
        index_path=index_path,
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = 10")
    stale = search_mail_fts(
        "disappearing",
        after=0,
        before=20,
        db_path=db_path,
        index_path=index_path,
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "mail_fts_index_missing"
    assert build["status"] == "ok"
    assert stale["status"] == "ok"
    assert stale["result_count"] == 0


def test_mail_fts_build_rejects_symlink_and_nonregular_index_paths(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    symlink_target = tmp_path / "target.sqlite"
    symlink_target.write_text("", encoding="utf-8")
    symlink_index = tmp_path / "symlink.sqlite"
    symlink_index.symlink_to(symlink_target)
    directory_index = tmp_path / "directory.sqlite"
    directory_index.mkdir()

    symlink_result = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=symlink_index,
    )
    directory_result = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=directory_index,
    )

    assert symlink_result["status"] == "error"
    assert symlink_result["warnings"][0]["code"] == "mail_fts_unavailable"
    assert directory_result["status"] == "error"
    assert directory_result["warnings"][0]["code"] == "mail_fts_unavailable"


def test_mail_fts_build_rejects_symlink_ancestor_path(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    symlink_parent = tmp_path / "linked-parent"
    symlink_parent.symlink_to(real_parent)

    result = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=symlink_parent / "nested" / "mail-fts.sqlite",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "mail_fts_unavailable"
    assert not (real_parent / "nested").exists()


def test_mail_fts_search_rejects_symlink_ancestor_path(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_index = real_parent / "mail-fts.sqlite"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Symlink ancestor search body.\r\n",
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=real_index,
    )
    symlink_parent = tmp_path / "linked-parent"
    symlink_parent.symlink_to(real_parent)

    result = search_mail_fts(
        "Symlink",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=symlink_parent / "mail-fts.sqlite",
    )

    assert build["status"] == "ok"
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "mail_fts_unavailable"


def test_mail_fts_reset_rejects_symlink_sidecar(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    sidecar_target = tmp_path / "sidecar-target"
    sidecar_target.write_text("do not remove", encoding="utf-8")
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    index_path.with_name(f"{index_path.name}-wal").symlink_to(sidecar_target)

    reset = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert build["status"] == "ok"
    assert reset["status"] == "error"
    assert reset["warnings"][0]["code"] == "mail_fts_unavailable"
    assert sidecar_target.read_text(encoding="utf-8") == "do not remove"


def test_mail_fts_reset_vacuums_removed_content(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    removed_token = b"erasurenoticealpha"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "erasurenoticealpha body text.\r\n",
    )
    first_build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    assert removed_token in index_path.read_bytes()

    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "replacement body text.\r\n",
    )
    second_build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    search = search_mail_fts(
        "erasurenoticealpha",
        scopes=["body"],
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert first_build["status"] == "ok"
    assert second_build["status"] == "ok"
    assert search["status"] == "ok"
    assert search["result_count"] == 0
    assert removed_token not in _fts_index_bytes(index_path)


def test_mail_fts_reset_clears_wal_sidecar_content(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    wal_token = b"walretentionbeta"
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "initial body text.\r\n",
    )
    build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    with sqlite3.connect(index_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute(
            """
            INSERT INTO mail_fts(
                rowid,
                subject,
                from_header,
                to_header,
                cc_header,
                bcc_header,
                body,
                attachment_names,
                attachment_content
            )
            VALUES (?, ?, '', '', '', '', '', '', '')
            """,
            (999, wal_token.decode("ascii")),
        )
        connection.commit()
        assert wal_token in _fts_index_bytes(index_path)

    reset_build = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        reset=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert build["status"] == "ok"
    assert reset_build["status"] == "ok"
    assert wal_token not in _fts_index_bytes(index_path)


def test_mail_fts_build_closes_connection_when_schema_init_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    class FakeConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    fake_connection = FakeConnection()

    def fake_connect(_index_path):
        return fake_connection

    def fail_schema(_connection):
        raise sqlite3.DatabaseError("boom")

    monkeypatch.setattr(mail_adapter, "_connect_mail_fts_index", fake_connect)
    monkeypatch.setattr(mail_adapter, "_ensure_mail_fts_schema", fail_schema)

    result = build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=tmp_path / "mail-fts.sqlite",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "mail_fts_unavailable"
    assert fake_connection.closed is True


def test_mail_content_unavailable_warning_is_path_safe(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "content_unavailable"
    assert str(tmp_path) not in json.dumps(result)


def test_list_mail_attachments_returns_exact_attachment_handles(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = list_mail_attachments(message_handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["result_count"] == 1
    attachment = result["results"][0]
    assert attachment["handle"].startswith("mail:attachment:v1:")
    assert attachment["message_handle"] == message_handle
    assert attachment["filename"] == "packet.pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["file_size"] == 7
    assert attachment["media_status"] == "available"
    assert attachment["attachment_type"] == "document"


def test_export_mail_attachment_writes_selected_mime_part(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="../packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    attachment_handle = list_mail_attachments(
        message_handle,
        db_path=db_path,
        mail_root=mail_root,
    )["results"][0]["handle"]

    result = export_mail_attachment(
        message_handle,
        attachment_handle,
        output_dir=tmp_path / "exports",
        filename="../review packet.pdf",
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["privacy"]["attachment_content_exported"] is True
    assert result["result"]["attachment_content_exported"] is True
    assert result["result"]["exported_filename"] == "review-packet.pdf"
    assert result["result"]["exported_bytes"] == 7
    assert Path(result["result"]["exported_path"]).read_bytes() == b"PDFDATA"
    assert str(mail_root) not in json.dumps(result)


def test_mail_attachment_handle_rejects_same_size_content_drift(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    stale_attachment_handle = list_mail_attachments(
        message_handle,
        db_path=db_path,
        mail_root=mail_root,
    )["results"][0]["handle"]
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "TkVXREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )

    result = export_mail_attachment(
        message_handle,
        stale_attachment_handle,
        output_dir=tmp_path / "exports",
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "not_found"
    assert not (tmp_path / "exports").exists()


def test_mail_attachment_export_rejects_symlink_target_escape(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    attachment_handle = list_mail_attachments(
        message_handle,
        db_path=db_path,
        mail_root=mail_root,
    )["results"][0]["handle"]
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    outside_target = tmp_path / "outside.pdf"
    (output_dir / "packet.pdf").symlink_to(outside_target)

    result = export_mail_attachment(
        message_handle,
        attachment_handle,
        output_dir=output_dir,
        filename="packet.pdf",
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "mail_attachment_export_failed"
    assert not outside_target.exists()


def test_mail_attachment_export_rejects_symlink_output_dir(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="packet.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "UERGREFUQQ==\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    attachment_handle = list_mail_attachments(
        message_handle,
        db_path=db_path,
        mail_root=mail_root,
    )["results"][0]["handle"]
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    output_dir = tmp_path / "exports-link"
    output_dir.symlink_to(real_dir)

    result = export_mail_attachment(
        message_handle,
        attachment_handle,
        output_dir=output_dir,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_output_dir"


def test_mail_attachment_export_rejects_bad_handles(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    result = export_mail_attachment(
        "mail:message:10",
        "mail:attachment:v1:0123456789abcdef0123456789abcdef",
        output_dir=tmp_path / "exports",
        db_path=db_path,
        mail_root=mail_root,
    )
    assert result["status"] == "error"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"

    message_handle = make_int_handle("mail:message", 10)
    result = export_mail_attachment(
        message_handle,
        "mail:attachment:10",
        output_dir=tmp_path / "exports",
        db_path=db_path,
        mail_root=mail_root,
    )
    assert result["status"] == "error"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_mail_attachment_export_reports_unavailable_for_externalized_part(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(
        mail_root,
        10,
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        "\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic body.\r\n"
        "--BOUNDARY\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="remote.pdf"\r\n'
        "X-Apple-Content-Length: 123\r\n"
        "\r\n"
        "\r\n"
        "--BOUNDARY--\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    attachment = list_mail_attachments(
        message_handle,
        db_path=db_path,
        mail_root=mail_root,
    )["results"][0]

    result = export_mail_attachment(
        message_handle,
        attachment["handle"],
        output_dir=tmp_path / "exports",
        db_path=db_path,
        mail_root=mail_root,
    )

    assert attachment["media_status"] == "unavailable"
    assert attachment["file_size"] == 123
    assert result["status"] == "attachment_unavailable"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["result"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "mail_attachment_unavailable"
    assert not (tmp_path / "exports" / "remote.pdf").exists()


def test_mail_content_redacted_log_excludes_sensitive_payload_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    payload = {
        "schema_version": 1,
        "source": "mail",
        "status": "ok",
        "result_count": 1,
        "privacy": {
            "output_tier": "content",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "result": {
            "handle": "mail:message:v2:abcdef0123456789abcdef0123456789",
            "subject": "Synthetic redacted subject",
            "content_text": "Synthetic redacted content",
        },
        "warnings": [{"code": "content_truncated", "message": "Synthetic warning message"}],
    }

    log_result("mail.content", payload)

    text = (tmp_path / "logs/events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "mail.content"
    assert event["privacy"]["output_tier"] == "content"
    assert event["warning_codes"] == ["content_truncated"]
    assert "mail:message:v2:" not in text
    assert "Synthetic redacted subject" not in text
    assert "Synthetic redacted content" not in text
    assert "Synthetic warning message" not in text


def _mail_token(plan: dict) -> str:
    return "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def _sender_rows(*, duplicate: bool = False) -> str:
    rows = [
        "\x1f".join(
            [
                "account-alpha",
                "Alpha Sender",
                "true",
                "Synthetic Alpha",
                "alpha@example.invalid",
            ]
        ),
        "\x1f".join(
            [
                "account-disabled",
                "Disabled Sender",
                "false",
                "Synthetic Disabled",
                "disabled@example.invalid",
            ]
        ),
    ]
    if duplicate:
        rows.append(
            "\x1f".join(
                [
                    "account-beta",
                    "Beta Sender",
                    "true",
                    "Synthetic Beta",
                    "alpha@example.invalid",
                ]
            )
        )
    return "\x1e".join(rows)


def _sender_runner(script: str, timeout: float) -> str:
    assert timeout == 10.0
    assert "email addresses of mailAccount" in script
    return _sender_rows()


def _signature_rows(*, duplicate: bool = False) -> str:
    rows = ["Default Signature", "Project Signature"]
    if duplicate:
        rows.append("Default Signature")
    return "\x1e".join(rows)


def _signature_runner(script: str, timeout: float) -> str:
    assert timeout == 10.0
    assert "repeat with mailSignature in signatures" in script
    assert "content of mailSignature" not in script
    assert "signatureContents" not in script
    return _signature_rows()


def test_mail_sender_search_and_get_return_masked_exact_handles() -> None:
    search = search_mail_senders("alpha", script_runner=_sender_runner)

    assert search["status"] == "ok"
    assert search["result_count"] == 1
    result = search["results"][0]
    assert result["handle"].startswith("mail:sender:v1:")
    assert result["sender_ref"].startswith("sender:")
    assert result["account_ref"].startswith("account:")
    assert result["email_preview"] == "a***@example.invalid"
    assert result["selection_supported"] is True
    assert result["full_email_returned"] is False
    assert result["sender_string_returned"] is False
    assert "alpha@example.invalid" not in json.dumps(search, sort_keys=True)
    assert "account-alpha" not in json.dumps(search, sort_keys=True)

    detail = get_mail_sender(result["handle"], script_runner=_sender_runner)

    assert detail["status"] == "ok"
    assert detail["result"]["handle"] == result["handle"]
    assert detail["result"]["email_preview"] == "a***@example.invalid"
    assert "alpha@example.invalid" not in json.dumps(detail, sort_keys=True)
    assert "account-alpha" not in json.dumps(detail, sort_keys=True)


def test_mail_sender_search_rejects_broad_query() -> None:
    result = search_mail_senders("*", script_runner=_sender_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_mail_sender_search_does_not_match_hidden_email_or_full_name() -> None:
    def hidden_runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "email addresses of mailAccount" in script
        return "\x1f".join(
            [
                "account-private",
                "Visible Account",
                "true",
                "Hidden Person",
                "secret.local@example.invalid",
            ]
        )

    visible = search_mail_senders("visible", script_runner=hidden_runner)
    hidden_local = search_mail_senders("secret.local", script_runner=hidden_runner)
    hidden_full_email = search_mail_senders(
        "secret.local@example.invalid",
        script_runner=hidden_runner,
    )
    hidden_full_name = search_mail_senders("hidden", script_runner=hidden_runner)

    assert visible["status"] == "ok"
    assert visible["result_count"] == 1
    assert hidden_local["status"] == "ok"
    assert hidden_local["result_count"] == 0
    assert hidden_full_email["status"] == "ok"
    assert hidden_full_email["result_count"] == 0
    assert hidden_full_name["status"] == "ok"
    assert hidden_full_name["result_count"] == 0


def test_mail_signature_search_and_get_return_name_without_body() -> None:
    search = search_mail_signatures("default", script_runner=_signature_runner)

    assert search["status"] == "ok"
    assert search["result_count"] == 1
    result = search["results"][0]
    assert result["handle"].startswith("mail:signature:v1:")
    assert result["signature_ref"].startswith("signature:")
    assert result["name"] == "Default Signature"
    assert result["selection_supported"] is True
    assert result["body_returned"] is False
    assert result["content_returned"] is False
    assert "Synthetic signature body" not in json.dumps(search, sort_keys=True)

    detail = get_mail_signature(result["handle"], script_runner=_signature_runner)

    assert detail["status"] == "ok"
    assert detail["result"]["handle"] == result["handle"]
    assert detail["result"]["name"] == "Default Signature"
    assert detail["result"]["body_returned"] is False
    assert detail["result"]["content_returned"] is False
    assert "Synthetic signature body" not in json.dumps(detail, sort_keys=True)


def test_mail_signature_search_rejects_broad_query() -> None:
    result = search_mail_signatures("*", script_runner=_signature_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_plan_mail_change_refuses_duplicate_signature_name() -> None:
    def duplicate_runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "repeat with mailSignature in signatures" in script
        return _signature_rows(duplicate=True)

    signature_handle = search_mail_signatures("default", script_runner=duplicate_runner)["results"][0]["handle"]

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature draft",
        body_text="Synthetic body.",
        signature_handle=signature_handle,
        script_runner=duplicate_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "ambiguous_signature_name"


def test_mail_template_create_search_get_delete_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "mail-templates.json"
    created = create_mail_template(
        "Renewal Reply",
        "Synthetic template body.",
        subject="Synthetic template subject",
        state_path=state_path,
    )

    assert created["status"] == "ok"
    template = created["result"]
    assert template["handle"].startswith("mail:template:v1:")
    assert template["template_ref"].startswith("template:")
    assert template["name"] == "Renewal Reply"
    assert template["subject"] == "Synthetic template subject"
    assert template["body_chars"] == len("Synthetic template body.")
    assert template["body_returned"] is False
    assert "Synthetic template body." not in json.dumps(created, sort_keys=True)

    search = search_mail_templates("renewal", state_path=state_path)
    assert search["status"] == "ok"
    assert search["result_count"] == 1
    assert search["results"][0]["handle"] == template["handle"]
    assert "Synthetic template body." not in json.dumps(search, sort_keys=True)

    detail = get_mail_template(template["handle"], state_path=state_path)
    assert detail["status"] == "ok"
    assert detail["result"]["body_returned"] is False
    assert "Synthetic template body." not in json.dumps(detail, sort_keys=True)

    detail_with_body = get_mail_template(
        template["handle"],
        include_body=True,
        state_path=state_path,
    )
    assert detail_with_body["status"] == "ok"
    assert detail_with_body["result"]["body_text"] == "Synthetic template body."
    assert detail_with_body["result"]["body_returned"] is True

    refused = delete_mail_template(template["handle"], state_path=state_path)
    assert refused["status"] == "error"
    assert refused["warnings"][0]["code"] == "missing_delete_confirmation"

    deleted = delete_mail_template(
        template["handle"],
        confirm_delete=True,
        state_path=state_path,
    )
    assert deleted["status"] == "ok"
    assert deleted["mutation_applied"] is True
    assert search_mail_templates("renewal", state_path=state_path)["result_count"] == 0


def test_mail_template_create_rejects_duplicate_name(tmp_path: Path) -> None:
    state_path = tmp_path / "mail-templates.json"
    first = create_mail_template("Duplicate", "First body.", state_path=state_path)
    second = create_mail_template("duplicate", "Second body.", state_path=state_path)

    assert first["status"] == "ok"
    assert second["status"] == "error"
    assert second["warnings"][0]["code"] == "duplicate_template_name"


def test_plan_mail_change_create_draft_binds_sender_handle() -> None:
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender draft",
        body_text="Synthetic body.",
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["target"]["account"] == "selected_sender"
    assert preview["target"]["sender_ref"].startswith("sender:")
    sender_selection = preview["proposed"]["sender_selection"]
    assert sender_selection["mode"] == "exact_sender_handle"
    assert sender_selection["sender_handle"] == sender_handle
    assert sender_selection["email_preview"] == "a***@example.invalid"
    assert sender_selection["full_email_returned"] is False
    assert preview["proposed"]["retry_safe"] is False
    assert "alpha@example.invalid" not in json.dumps(result, sort_keys=True)
    assert "account-alpha" not in json.dumps(result, sort_keys=True)


def test_plan_mail_change_send_message_binds_sender_handle() -> None:
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]

    result = plan_mail_change(
        "send-message",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender send",
        body_text="Synthetic body.",
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["target"]["account"] == "selected_sender"
    assert preview["target"]["mailbox"] == "outbound_send"
    sender_selection = preview["proposed"]["sender_selection"]
    assert sender_selection["mode"] == "exact_sender_handle"
    assert sender_selection["sender_handle"] == sender_handle
    assert sender_selection["full_email_returned"] is False
    assert "alpha@example.invalid" not in json.dumps(result, sort_keys=True)


def test_plan_mail_change_create_draft_binds_signature_handle_without_body() -> None:
    signature_handle = search_mail_signatures("default", script_runner=_signature_runner)["results"][0]["handle"]

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature draft",
        body_text="Synthetic body.",
        signature_handle=signature_handle,
        script_runner=_signature_runner,
    )

    assert result["status"] == "ok"
    selection = result["preview"]["proposed"]["signature_selection"]
    assert selection["mode"] == "exact_signature_handle"
    assert selection["signature_handle"] == signature_handle
    assert selection["signature_ref"].startswith("signature:")
    assert selection["name"] == "Default Signature"
    assert selection["body_returned"] is False
    assert selection["content_returned"] is False
    assert result["preview"]["proposed"]["retry_safe"] is False
    assert "Synthetic signature body" not in json.dumps(result, sort_keys=True)


def test_plan_mail_change_send_uses_exact_template_body_without_body_return(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "mail-templates.json"
    monkeypatch.setenv("LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE", str(state_path))
    template = create_mail_template(
        "Outbound Template",
        "Synthetic templated outbound body.",
        subject="Synthetic templated outbound",
    )["result"]

    result = plan_mail_change(
        "send-message",
        to=["synthetic@example.invalid"],
        template_handle=template["handle"],
    )

    assert result["status"] == "ok"
    proposed = result["preview"]["proposed"]
    assert proposed["subject"] == "Synthetic templated outbound"
    assert proposed["body_chars"] == len("Synthetic templated outbound body.")
    selection = proposed["template_selection"]
    assert selection["mode"] == "exact_template_handle"
    assert selection["template_handle"] == template["handle"]
    assert selection["template_ref"].startswith("template:")
    assert selection["body_returned"] is False
    assert selection["content_returned"] is False
    assert "Synthetic templated outbound body." not in json.dumps(selection, sort_keys=True)


def test_plan_mail_change_template_rejects_direct_body_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "mail-templates.json"
    monkeypatch.setenv("LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE", str(state_path))
    template = create_mail_template("Override Template", "Stored body.")["result"]

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic subject",
        body_text="Direct body.",
        template_handle=template["handle"],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_body_text_with_template"


def test_plan_mail_change_refuses_duplicate_sender_address() -> None:
    def duplicate_runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "email addresses of mailAccount" in script
        return _sender_rows(duplicate=True)

    sender_handle = search_mail_senders("alpha", script_runner=duplicate_runner)["results"][0]["handle"]

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender draft",
        body_text="Synthetic body.",
        sender_handle=sender_handle,
        script_runner=duplicate_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "ambiguous_sender_address"


def test_apply_mail_change_create_draft_sets_exact_sender_and_reads_back(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender draft",
        body_text="Synthetic sender body.",
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )
    scripts: list[str] = []

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "email addresses of mailAccount" in script:
            return _sender_rows()
        scripts.append(script)
        assert "make new outgoing message" in script
        assert "set draftSender to \"alpha@example.invalid\"" in script
        assert "set sender of draftMessage to draftSender" in script
        assert "save draftMessage" in script
        assert "\nsend " not in script
        _insert_draft_message(db_path, rowid=32, subject="Synthetic sender draft")
        _write_emlx(
            mail_root,
            32,
            "Subject: Synthetic sender draft\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic sender body.\r\n",
        )
        return "Synthetic Alpha <alpha@example.invalid>"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender draft",
        body_text="Synthetic sender body.",
        sender_handle=sender_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert len(scripts) == 1
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sender_ref"].startswith("sender:")
    assert result["read_back"]["sender_selection_confirmed"] is True
    assert result["read_back"]["full_email_returned"] is False
    assert result["read_back"]["sender_string_returned"] is False
    assert "alpha@example.invalid" not in json.dumps(result, sort_keys=True)
    assert "account-alpha" not in json.dumps(result, sort_keys=True)


def test_apply_mail_change_create_draft_sets_exact_signature_and_reads_back(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    signature_handle = search_mail_signatures("default", script_runner=_signature_runner)["results"][0]["handle"]
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature draft",
        body_text="Synthetic signature body.",
        signature_handle=signature_handle,
        script_runner=_signature_runner,
    )
    scripts: list[str] = []

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "repeat with mailSignature in signatures" in script:
            return _signature_rows()
        scripts.append(script)
        assert "make new outgoing message" in script
        assert 'set draftSignatureName to "Default Signature"' in script
        assert "set message signature of draftMessage to signature draftSignatureName" in script
        assert "content of signature" not in script
        assert "save draftMessage" in script
        assert "\nsend " not in script
        _insert_draft_message(db_path, rowid=37, subject="Synthetic signature draft")
        _write_emlx(
            mail_root,
            37,
            "Subject: Synthetic signature draft\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic signature body.\r\n",
        )
        return "id:37\nsignature:Default Signature\nattachment_count:0"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature draft",
        body_text="Synthetic signature body.",
        signature_handle=signature_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert len(scripts) == 1
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["signature_ref"].startswith("signature:")
    assert result["read_back"]["signature_selection_confirmed"] is True
    assert result["read_back"]["signature_body_returned"] is False
    assert result["read_back"]["signature_content_returned"] is False
    assert "Synthetic signature body from Mail settings" not in json.dumps(result, sort_keys=True)


def test_apply_mail_change_create_draft_uses_exact_template_and_reads_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    state_path = tmp_path / "mail-templates.json"
    monkeypatch.setenv("LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE", str(state_path))
    template = create_mail_template(
        "Draft Template",
        "Synthetic templated draft body.",
        subject="Synthetic templated draft",
    )["result"]
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        template_handle=template["handle"],
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "make new outgoing message" in script
        assert "Synthetic templated draft" in script
        assert "Synthetic templated draft body." in script
        assert "save draftMessage" in script
        _insert_draft_message(db_path, rowid=38, subject="Synthetic templated draft")
        _write_emlx(
            mail_root,
            38,
            "Subject: Synthetic templated draft\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic templated draft body.\r\n",
        )
        return "id:38\nattachment_count:0"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        template_handle=template["handle"],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["template_ref"].startswith("template:")
    assert result["read_back"]["template_selection_confirmed"] is True
    assert result["read_back"]["template_body_returned"] is False
    assert result["read_back"]["template_content_returned"] is False
    assert result["read_back"]["handle"].startswith("mail:message:v2:")


def test_apply_mail_change_create_draft_excludes_preexisting_sender_matches(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]
    subject = "Synthetic sender duplicate"
    body = "Synthetic sender duplicate body."
    _insert_draft_message(db_path, rowid=34, subject=subject)
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE messages SET date_received = 99, date_sent = 99 WHERE ROWID = 34")
    _write_emlx(
        mail_root,
        34,
        "Subject: Synthetic sender duplicate\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic sender duplicate body.\r\n",
    )
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "email addresses of mailAccount" in script:
            return _sender_rows()
        _insert_draft_message(db_path, rowid=35, subject=subject)
        _write_emlx(
            mail_root,
            35,
            "Subject: Synthetic sender duplicate\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic sender duplicate body.\r\n",
        )
        return "Synthetic Alpha <alpha@example.invalid>"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["handle"] == make_int_handle("mail:message", 35)
    assert result["read_back"]["sender_selection_confirmed"] is True


def test_apply_mail_change_create_draft_refuses_ambiguous_new_sender_matches(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]
    subject = "Synthetic sender race"
    body = "Synthetic sender race body."
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "email addresses of mailAccount" in script:
            return _sender_rows()
        for rowid in (35, 36):
            _insert_draft_message(db_path, rowid=rowid, subject=subject)
            _write_emlx(
                mail_root,
                rowid,
                "Subject: Synthetic sender race\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                "\r\n"
                "Synthetic sender race body.\r\n",
            )
        return "Synthetic Alpha <alpha@example.invalid>"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "ambiguous_draft_read_back"
    assert "read_back" not in result


def test_apply_mail_change_create_draft_refuses_saturated_sender_read_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]
    subject = "Synthetic sender saturated read-back"
    body = "Synthetic sender saturated body."
    monkeypatch.setattr(mail_adapter, "MAX_MAIL_READ_BACK_CANDIDATES", 3)
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )
    inserted = False

    def runner(script: str, timeout: float) -> str:
        nonlocal inserted
        assert timeout == 10.0
        if "email addresses of mailAccount" in script:
            return _sender_rows()
        if not inserted:
            inserted = True
            for rowid in range(80, 84):
                _insert_draft_message(db_path, rowid=rowid, subject=subject)
                _write_emlx(
                    mail_root,
                    rowid,
                    "Subject: Synthetic sender saturated read-back\r\n"
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    "\r\n"
                    f"Different synthetic sender body {rowid}.\r\n",
                )
        return "Synthetic Alpha <alpha@example.invalid>"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject=subject,
        body_text=body,
        sender_handle=sender_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "ambiguous_draft_read_back"
    assert "read_back" not in result


def test_apply_mail_change_create_draft_requires_sender_read_back(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    sender_handle = search_mail_senders("alpha", script_runner=_sender_runner)["results"][0]["handle"]
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender partial",
        body_text="Synthetic sender body.",
        sender_handle=sender_handle,
        script_runner=_sender_runner,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "email addresses of mailAccount" in script:
            return _sender_rows()
        _insert_draft_message(db_path, rowid=33, subject="Synthetic sender partial")
        _write_emlx(
            mail_root,
            33,
            "Subject: Synthetic sender partial\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic sender body.\r\n",
        )
        return ""

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender partial",
        body_text="Synthetic sender body.",
        sender_handle=sender_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "sender_read_back_unavailable"


def test_plan_mail_change_create_draft_returns_preview_only() -> None:
    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        cc=["copy@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Line one\nLine two",
    )

    assert result["status"] == "ok"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "create_draft"
    assert preview["target"] == {"account": "mail_app_default", "mailbox": "drafts"}
    assert preview["proposed"]["to"] == ["synthetic@example.invalid"]
    assert preview["proposed"]["cc"] == ["copy@example.invalid"]
    assert preview["proposed"]["subject"] == "Synthetic draft subject"
    assert preview["proposed"]["send_permitted"] is False
    assert preview["proposed"]["attachments_permitted"] is False
    assert preview["approval"]["approval_token_format"].startswith("mail-apply:v1:")


def test_plan_mail_change_create_draft_with_local_attachment_returns_bounded_preview(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "create_draft"
    assert preview["proposed"]["attachments_permitted"] is True
    assert preview["proposed"]["attachment_count"] == 1
    assert preview["proposed"]["attachment_total_bytes"] == len(b"PDF OUTBOUND")
    assert preview["proposed"]["attachment_filenames"] == ["packet.pdf"]
    assert preview["proposed"]["attachment_types"] == ["document"]
    assert preview["proposed"]["attachment_content_returned"] is False
    assert preview["proposed"]["attachment_paths_returned"] is False
    assert preview["proposed"]["source_message_attachments_permitted"] is False
    assert preview["proposed"]["retry_safe"] is False
    assert str(source) not in json.dumps(result, sort_keys=True)


def test_plan_mail_change_create_draft_rejects_invalid_attachment_path(tmp_path: Path) -> None:
    empty_source = tmp_path / "empty.txt"
    empty_source.write_bytes(b"")

    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(empty_source)],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "attachment_empty"


def _draft_attachment_warning_code(paths: list[str]) -> str:
    result = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=paths,
    )
    assert result["status"] == "error"
    return result["warnings"][0]["code"]


def test_plan_mail_change_create_draft_rejects_missing_attachment_path() -> None:
    assert _draft_attachment_warning_code([""]) == "missing_attachment_path"
    assert _draft_attachment_warning_code(["/tmp/local-apple-data-missing-attachment.invalid"]) == "attachment_unavailable"


def test_plan_mail_change_create_draft_rejects_directory_attachment(tmp_path: Path) -> None:
    assert _draft_attachment_warning_code([str(tmp_path)]) == "attachment_not_file"


def test_plan_mail_change_create_draft_rejects_symlink_attachment(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("synthetic", encoding="utf-8")
    link = tmp_path / "linked.txt"
    link.symlink_to(target)

    assert _draft_attachment_warning_code([str(link)]) == "symlink_attachment_blocked"


def test_plan_mail_change_create_draft_rejects_duplicate_attachment_path(tmp_path: Path) -> None:
    source = tmp_path / "packet.txt"
    source.write_text("synthetic", encoding="utf-8")

    assert _draft_attachment_warning_code([str(source), str(source)]) == "duplicate_attachment_path"


def test_plan_mail_change_create_draft_rejects_too_many_attachments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(mail_adapter, "MAX_DRAFT_ATTACHMENTS", 1)
    monkeypatch.setattr(
        mail_adapter,
        "_draft_attachment_file_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("too-many attachment rejection must not hash file bytes")
        ),
    )
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    assert _draft_attachment_warning_code([str(first), str(second)]) == "too_many_attachments"


def test_plan_mail_change_create_draft_rejects_per_file_attachment_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(mail_adapter, "MAX_DRAFT_ATTACHMENT_BYTES", 3)
    monkeypatch.setattr(
        mail_adapter,
        "_draft_attachment_file_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("oversize attachment rejection must not hash file bytes")
        ),
    )
    source = tmp_path / "packet.txt"
    source.write_bytes(b"1234")

    assert _draft_attachment_warning_code([str(source)]) == "attachment_too_large"


def test_plan_mail_change_create_draft_rejects_total_attachment_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(mail_adapter, "MAX_DRAFT_ATTACHMENT_TOTAL_BYTES", 5)
    monkeypatch.setattr(
        mail_adapter,
        "_draft_attachment_file_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("total-size attachment rejection must not hash file bytes")
        ),
    )
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"1234")
    second.write_bytes(b"5678")

    assert _draft_attachment_warning_code([str(first), str(second)]) == "attachments_too_large"


def test_plan_mail_change_send_message_accepts_local_attachment(tmp_path: Path) -> None:
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")

    result = plan_mail_change(
        "send-message",
        to=["synthetic@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        attachment_paths=[str(source)],
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["attachments_permitted"] is True
    assert result["preview"]["proposed"]["attachment_send_permitted"] is True
    assert result["preview"]["proposed"]["attachment_count"] == 1
    assert result["preview"]["proposed"]["attachment_paths_returned"] is False


def test_plan_mail_change_requires_to_recipient() -> None:
    result = plan_mail_change(
        "create-draft",
        to=[],
        subject="Synthetic draft subject",
        body_text="Body",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_to"


def test_apply_mail_change_requires_confirmation(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Body",
    )

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Body",
        approval_token=_mail_token(plan),
        confirm_apply=False,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_mail_change_rejects_wrong_approval_token(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Body",
        approval_token="mail-apply:v1:bad",
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_mail_change_creates_draft_and_reads_back(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        cc=["copy@example.invalid"],
        bcc=["blind@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Synthetic draft body.",
    )
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        calls.append(script)
        assert timeout == 10.0
        assert "make new outgoing message" in script
        assert "save draftMessage" in script
        assert "send draftMessage" not in script
        assert "\nsend " not in script
        assert "synthetic@example.invalid" in script
        assert "copy@example.invalid" in script
        assert "blind@example.invalid" in script
        _insert_draft_message(db_path, rowid=30, subject="Synthetic draft subject")
        _write_emlx(
            mail_root,
            30,
            "Subject: Synthetic draft subject\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic draft body.\r\n",
        )
        return "30"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        cc=["copy@example.invalid"],
        bcc=["blind@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Synthetic draft body.",
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert len(calls) == 1
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_name"] == "Drafts"
    assert result["read_back"]["content_text"] == "Synthetic draft body."


def test_apply_mail_change_creates_draft_with_local_attachment_and_reads_back(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "make new attachment with properties {file name:attachmentFile1}" in script
        assert "send draftMessage" not in script
        assert "\nsend " not in script
        assert str(source) not in script
        attachment_path_line = next(
            line for line in script.splitlines() if "set attachmentPath1 to " in line
        )
        automation_path = Path(attachment_path_line.split(' to "', 1)[1].rsplit('"', 1)[0])
        assert automation_path.name == "packet.pdf"
        assert automation_path != source
        assert automation_path.read_bytes() == b"PDF OUTBOUND"
        _insert_draft_message(db_path, rowid=34, subject="Synthetic draft attachment")
        _write_emlx(
            mail_root,
            34,
            "Subject: Synthetic draft attachment\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic draft body.\r\n",
        )
        return "id:34\nattachment_count:1"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["attachment_count"] == 1
    assert result["read_back"]["attachment_filenames"] == ["packet.pdf"]
    assert result["read_back"]["attachment_content_returned"] is False
    assert result["read_back"]["attachment_paths_returned"] is False
    assert result["read_back"]["attachments_confirmed_by_automation"] is True
    assert str(source) not in json.dumps(result, sort_keys=True)


def test_apply_mail_change_sends_message_with_local_attachment_and_reads_back(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    plan = plan_mail_change(
        "send-message",
        to=["synthetic@example.invalid"],
        subject="Synthetic send attachment",
        body_text="Synthetic send body.",
        attachment_paths=[str(source)],
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "send outboundMessage" in script
        assert "save outboundMessage" not in script
        assert "make new attachment with properties {file name:attachmentFile1}" in script
        assert "count of attachments of content of outboundMessage" in script
        assert str(source) not in script
        attachment_path_line = next(
            line for line in script.splitlines() if "set attachmentPath1 to " in line
        )
        automation_path = Path(attachment_path_line.split(' to "', 1)[1].rsplit('"', 1)[0])
        assert automation_path.name == "packet.pdf"
        assert automation_path != source
        assert automation_path.read_bytes() == b"PDF OUTBOUND"
        _insert_sent_message(db_path, rowid=35, subject="Synthetic send attachment")
        _write_emlx(
            mail_root,
            35,
            "Subject: Synthetic send attachment\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic send body.\r\n",
        )
        return "id:35\nattachment_count:1"

    result = apply_mail_change(
        "send-message",
        to=["synthetic@example.invalid"],
        subject="Synthetic send attachment",
        body_text="Synthetic send body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["attachment_count"] == 1
    assert result["read_back"]["attachment_send_permitted"] is True
    assert result["read_back"]["attachment_paths_returned"] is False
    assert str(source) not in json.dumps(result, sort_keys=True)


def test_apply_mail_change_replies_with_local_attachment_and_reads_back(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-reply@example.invalid>\r\n"
        "Subject: Synthetic content subject\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic source body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "reply-message",
        message_handle=message_handle,
        body_text="Synthetic reply body.",
        attachment_paths=[str(source)],
        db_path=db_path,
        mail_root=mail_root,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "reply sourceMessage opening window false reply to all false" in script
        assert "send replyMessage" in script
        assert "make new attachment with properties {file name:attachmentFile1}" in script
        assert "count of attachments of content of replyMessage" in script
        assert str(source) not in script
        _insert_sent_message(db_path, rowid=36, subject="Re: Synthetic content subject")
        _write_emlx(
            mail_root,
            36,
            "Subject: Re: Synthetic content subject\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic reply body.\r\n",
        )
        return "id:36\nattachment_count:1"

    result = apply_mail_change(
        "reply-message",
        message_handle=message_handle,
        body_text="Synthetic reply body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["reply_mode"] == "sender_only"
    assert result["read_back"]["attachment_count"] == 1
    assert result["read_back"]["attachment_send_permitted"] is True


def test_apply_mail_change_reply_all_with_local_attachment_and_reads_back(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-reply-all@example.invalid>\r\n"
        "Subject: Synthetic content subject\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic source body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "reply-all-message",
        message_handle=message_handle,
        body_text="Synthetic reply-all body.",
        attachment_paths=[str(source)],
        db_path=db_path,
        mail_root=mail_root,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "reply sourceMessage opening window false reply to all true" in script
        assert "send replyMessage" in script
        assert "make new attachment with properties {file name:attachmentFile1}" in script
        assert str(source) not in script
        _insert_sent_message(db_path, rowid=37, subject="Re: Synthetic content subject")
        _write_emlx(
            mail_root,
            37,
            "Subject: Re: Synthetic content subject\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic reply-all body.\r\n",
        )
        return "id:37\nattachment_count:1"

    result = apply_mail_change(
        "reply-all-message",
        message_handle=message_handle,
        body_text="Synthetic reply-all body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["reply_mode"] == "reply_all"
    assert result["read_back"]["attachment_count"] == 1
    assert result["read_back"]["attachment_send_permitted"] is True


def test_apply_mail_change_forwards_with_local_attachment_and_reads_back(
    tmp_path: Path,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-forward@example.invalid>\r\n"
        "Subject: Synthetic content subject\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic source body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=message_handle,
        body_text="Synthetic forward note.",
        attachment_paths=[str(source)],
        db_path=db_path,
        mail_root=mail_root,
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "forward sourceMessage opening window false" in script
        assert "send forwardMessage" in script
        assert "make new attachment with properties {file name:attachmentFile1}" in script
        assert "count of attachments of content of forwardMessage" in script
        assert str(source) not in script
        _insert_sent_message(db_path, rowid=38, subject="Fwd: Synthetic content subject")
        _write_emlx(
            mail_root,
            38,
            "Subject: Fwd: Synthetic content subject\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Synthetic forward note.\r\n\r\nSynthetic source body.\r\n",
        )
        return "id:38\nattachment_count:1"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=message_handle,
        body_text="Synthetic forward note.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["forward_copy_confirmed"] is True
    assert result["read_back"]["source_attachments_permitted"] is False
    assert result["read_back"]["attachment_count"] == 1
    assert result["read_back"]["attachment_send_permitted"] is True


def test_apply_mail_change_rejects_same_size_mtime_preserved_attachment_drift(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    original_stat = source.stat()
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )
    source.write_bytes(b"PDF INBOUND!")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("stale attachment token must fail before Mail automation")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_mail_change_rejects_attachment_race_after_token_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    original_stat = source.stat()
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )
    original_prepare = mail_adapter._prepare_draft_attachment_copies

    def racing_prepare(attachments: list[dict], temp_dir: Path) -> list[str]:
        source.write_bytes(b"PDF INBOUND!")
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        return original_prepare(attachments, temp_dir)

    monkeypatch.setattr(mail_adapter, "_prepare_draft_attachment_copies", racing_prepare)

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("racing attachment change must fail before Mail automation")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_attachment_changed"


def test_apply_mail_change_rejects_attachment_change_after_token_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    original_stat = source.stat()
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )
    original_approval_token = mail_adapter._approval_token
    raced = False

    def racing_approval_token(fingerprint: str) -> str:
        nonlocal raced
        token = original_approval_token(fingerprint)
        if not raced:
            raced = True
            source.write_bytes(b"PDF INBOUND!")
            os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        return token

    monkeypatch.setattr(mail_adapter, "_approval_token", racing_approval_token)

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("post-token attachment change must fail before Mail automation")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_attachment_changed"


def test_apply_mail_change_rejects_stale_draft_attachment_identity(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )
    source.write_bytes(b"UPDATED PDF OUTBOUND")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_mail_create_draft_script_attaches_files_without_send(tmp_path: Path) -> None:
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")

    script = mail_adapter._mail_create_draft_script(
        to=["synthetic@example.invalid"],
        cc=[],
        bcc=[],
        subject="Synthetic draft attachment",
        body_text="Synthetic draft body.",
        attachment_paths=[str(source)],
    )
    lowered = script.lower()

    assert "make new outgoing message" in script
    assert "make new attachment with properties {file name:attachmentFile1}" in script
    assert "save draftMessage" in script
    assert "count of attachments of content of draftMessage" in script
    assert "attachment_count:" in script
    assert "attachedCount" not in script
    assert "send draftmessage" not in lowered
    assert "\nsend " not in lowered


def test_apply_mail_change_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Synthetic draft body.",
    )

    def runner(_script: str, _timeout: float) -> str:
        raise OSError("permission denied for /private/local/mail")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft subject",
        body_text="Synthetic draft body.",
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "write_error"
    assert "permission denied" not in str(result)
    assert "/private/local/mail" not in str(result)


def test_apply_mail_change_is_idempotent_for_existing_matching_draft(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_draft_message(db_path, rowid=31, subject="Synthetic existing draft")
    _write_emlx(
        mail_root,
        31,
        "Subject: Synthetic existing draft\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Existing body.\r\n",
    )
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic existing draft",
        body_text="Existing body.",
    )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("idempotent apply should not invoke Mail.app automation")

    result = apply_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic existing draft",
        body_text="Existing body.",
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"


def test_plan_mail_change_move_message_allows_exact_cross_account_mailbox(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_mailbox(db_path, rowid=2, url="local://other-account/Projects")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-move@example.invalid>\r\n"
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic move body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    mailbox_handle = search_mail_mailboxes("Projects", db_path=db_path)["results"][0]["handle"]

    result = plan_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    proposed = result["preview"]["proposed"]
    assert proposed["target_account_relation"] == "cross_account"
    assert proposed["source_account_ref"].startswith("account:")
    assert proposed["target_account_ref"].startswith("account:")
    assert proposed["source_account_ref"] != proposed["target_account_ref"]
    assert "other-account" not in json.dumps(result, sort_keys=True)


def test_plan_mail_change_move_message_refuses_trash_like_target(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_mailbox(db_path, rowid=2, url="local://synthetic/Trash")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-move@example.invalid>\r\n"
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic move body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    mailbox_handle = search_mail_mailboxes("Trash", db_path=db_path)["results"][0]["handle"]

    result = plan_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_target_mailbox"


def test_apply_mail_change_move_message_uses_exact_same_account_mailbox(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_mailbox(db_path, rowid=2, url="local://synthetic/Projects")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-move@example.invalid>\r\n"
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic move body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    mailbox_handle = search_mail_mailboxes("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["target_mailbox_handle"] == mailbox_handle
    assert plan["preview"]["proposed"]["target_mailbox_kind"] == "mailbox"

    scripts: list[str] = []

    def runner(script: str, timeout: float) -> str:
        scripts.append(script)
        assert timeout == 10.0
        assert 'account id "synthetic"' in script
        assert 'mailbox "INBOX"' in script
        assert 'mailbox "Projects"' in script
        assert "message id is \"synthetic-move@example.invalid\"" in script
        assert "move (first item of triageMatches) to targetBox" in script
        assert "\nsend " not in script
        assert "delete " not in script.lower()
        assert "erase " not in script.lower()
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE messages SET mailbox = 2 WHERE ROWID = 10")
        return "ok"

    result = apply_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert len(scripts) == 1
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_mail_change_move_message_uses_exact_cross_account_mailbox(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_mailbox(db_path, rowid=2, url="local://other-account/Projects")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-move@example.invalid>\r\n"
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic move body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    mailbox_handle = search_mail_mailboxes("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["target_account_relation"] == "cross_account"

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert 'mailbox "INBOX" of account id "synthetic"' in script
        assert 'mailbox "Projects" of account id "other-account"' in script
        assert "move (first item of triageMatches) to targetBox" in script
        assert "\nsend " not in script
        assert "delete " not in script.lower()
        assert "erase " not in script.lower()
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE messages SET mailbox = 2 WHERE ROWID = 10")
        return "ok"

    result = apply_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_mail_change_move_message_refuses_stale_target_mailbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _insert_mailbox(db_path, rowid=2, url="local://synthetic/Projects")
    _write_emlx(
        mail_root,
        10,
        "Message-ID: <synthetic-move@example.invalid>\r\n"
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic move body.\r\n",
    )
    message_handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]
    mailbox_handle = search_mail_mailboxes("Projects", db_path=db_path)["results"][0]["handle"]
    plan = plan_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        db_path=db_path,
        mail_root=mail_root,
    )
    assert plan["status"] == "ok"

    original_resolver = mail_adapter._resolve_exact_move_mailbox
    resolve_calls = 0

    def drift_after_preview(connection, target, mailbox_handle):
        nonlocal resolve_calls
        resolved, warning = original_resolver(connection, target, mailbox_handle)
        if warning is not None or resolved is None:
            return resolved, warning
        resolve_calls += 1
        if resolve_calls == 1:
            return resolved, None
        return {**resolved, "mailbox_ref": "mailbox:stale-target"}, None

    monkeypatch.setattr(mail_adapter, "_resolve_exact_move_mailbox", drift_after_preview)

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("stale mailbox target must refuse before Mail.app automation")

    result = apply_mail_change(
        "move-message",
        message_handle=message_handle,
        target_mailbox_handle=mailbox_handle,
        approval_token=_mail_token(plan),
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "stale_mailbox_target"
    assert resolve_calls == 2


# ---- v1.183 discovery performance / partial downloads / index state ----


def _write_partial_emlx(mail_root: Path, rowid: int, mime_text: str) -> None:
    mime_bytes = mime_text.encode("utf-8")
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages" / f"{rowid}.partial.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes + b"\n")


def test_get_mail_content_reads_partial_download_with_warning(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_partial_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic partial body text.\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "Synthetic partial body text."
    assert result["result"]["content_status"] == "partial"
    assert any(w["code"] == "partial_download" for w in result["warnings"])


def test_search_mail_metadata_reports_partial_content_status(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_partial_emlx(mail_root, 10, "Subject: s\r\n\r\nbody\r\n")

    result = search_mail_metadata("content", db_path=db_path)

    statuses = {r["handle"]: r["content_status"] for r in result["results"]}
    assert "partial" in statuses.values()


def test_full_emlx_wins_over_partial_duplicate(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_partial_emlx(mail_root, 10, "Subject: s\r\n\r\npartial body\r\n")
    _write_emlx(
        mail_root,
        10,
        "Subject: Synthetic content\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Synthetic full body.\r\n",
    )
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    assert result["result"]["content_status"] == "available"
    assert result["result"]["content_text"] == "Synthetic full body."
    assert not any(w["code"] == "partial_download" for w in result["warnings"])


def test_search_mail_body_matches_partial_download(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_partial_emlx(
        mail_root,
        10,
        "Subject: s\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "merchant WellnessPay receipt body\r\n",
    )

    result = search_mail_body("WellnessPay", after=0, before=20, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert "WellnessPay" in result["results"][0]["snippet"]


def test_discovery_payloads_include_scan_stats(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(mail_root, 10, "Subject: s\r\n\r\nneedle body\r\n")

    result = search_mail_body("needle", after=0, before=20, db_path=db_path, mail_root=mail_root)

    scan = result["scan"]
    assert scan["scanned"] == 2  # rowids 10 and 11 in range; deleted 12 excluded
    assert scan["range_total"] == 2
    assert scan["stopped_reason"] in {"exhausted", "result_limit"}
    assert scan["elapsed_ms"] >= 0
    assert result["query"]["max_seconds"] == 20.0


def test_scan_time_budget_stops_with_cursor(tmp_path: Path, monkeypatch) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    _write_emlx(mail_root, 10, "Subject: s\r\n\r\nbody ten\r\n")
    _write_emlx(mail_root, 11, "Subject: s\r\n\r\nbody eleven\r\n")

    clock = iter(float(value) for value in range(0, 100000, 1000))
    monkeypatch.setattr(mail_adapter.time, "monotonic", lambda: next(clock))

    result = search_mail_body(
        "body",
        after=0,
        before=20,
        db_path=db_path,
        mail_root=mail_root,
        max_seconds=1,
    )

    assert result["scan"]["stopped_reason"] == "time_budget"
    assert result["scan"]["scanned"] == 1
    assert result["next_cursor"] == "1"
    assert any(w["code"] == "scan_time_budget_reached" for w in result["warnings"])


def test_build_mail_fts_index_checkpoints_and_status_resumes(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    with sqlite3.connect(db_path) as connection:
        for rowid, subject, date_value in [
            (20, "Checkpoint one", 30),
            (21, "Checkpoint two", 29),
            (22, "Checkpoint three", 28),
        ]:
            connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rowid, rowid, 1, date_value, date_value, 0, 0, 0, 12),
            )

    missing = get_mail_fts_status(db_path=db_path, index_path=index_path)
    assert missing["result"]["state"] == "missing"

    first = build_mail_fts_index(
        after=25,
        before=35,
        limit=2,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    assert first["status"] == "ok"
    assert first["result"]["index_state"] == "building"
    assert first["next_cursor"] == "2"
    assert first["scan"]["range_total"] == 3

    building = get_mail_fts_status(db_path=db_path, index_path=index_path)
    assert building["result"]["state"] == "building"
    assert building["result"]["checkpoint_cursor"] == "2"
    assert building["result"]["indexed_docs_total"] == 2
    assert building["result"]["range_total"] == 3

    second = build_mail_fts_index(
        after=25,
        before=35,
        limit=2,
        cursor="2",
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    assert second["status"] == "ok"
    assert second["result"]["index_state"] == "ready"
    assert second["next_cursor"] == ""

    ready = get_mail_fts_status(db_path=db_path, index_path=index_path)
    assert ready["result"]["state"] == "ready"
    assert ready["result"]["checkpoint_cursor"] == ""
    assert ready["result"]["indexed_docs_total"] == 3


def test_search_mail_fts_warns_on_partial_coverage(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    with sqlite3.connect(db_path) as connection:
        for rowid, subject, date_value in [
            (20, "Coverage alpha needle", 30),
            (21, "Coverage beta needle", 29),
        ]:
            connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rowid, rowid, 1, date_value, date_value, 0, 0, 0, 12),
            )
    for rowid in (20, 21):
        _write_emlx(mail_root, rowid, "Subject: s\r\n\r\ncoverage needle body\r\n")

    build_mail_fts_index(
        after=25,
        before=35,
        limit=1,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    result = search_mail_fts(
        "needle",
        after=25,
        before=35,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )

    assert result["status"] == "ok"
    assert result["index_state"]["state"] == "building"
    assert any(w["code"] == "mail_fts_partial_coverage" for w in result["warnings"])


def test_mail_fts_status_reports_stale_fingerprint_rows(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    index_path = tmp_path / "mail-fts.sqlite"
    _write_emlx(mail_root, 10, "Subject: s\r\n\r\nbody\r\n")
    build_mail_fts_index(
        after=0,
        before=20,
        confirm_index=True,
        db_path=db_path,
        mail_root=mail_root,
        index_path=index_path,
    )
    with sqlite3.connect(index_path) as connection:
        connection.execute("UPDATE mail_fts_docs SET schema_fingerprint = 'stale-fingerprint'")

    result = get_mail_fts_status(db_path=db_path, index_path=index_path)

    assert result["result"]["state"] == "stale"
    assert result["result"]["stale_fingerprint_rows"] > 0
