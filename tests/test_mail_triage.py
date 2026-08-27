from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import subprocess
from pathlib import Path

import local_apple_data.adapters.mail as mail_adapter
from local_apple_data.adapters.mail import (
    APPROVAL_TOKEN_PREFIX,
    _mail_create_mailbox_script,
    _mail_delete_mailbox_script,
    _mail_empty_special_mailbox_script,
    _mail_archive_message_script,
    _mail_forward_message_script,
    _mail_permanent_delete_message_script,
    _mail_move_message_script,
    _mail_rename_mailbox_script,
    _mail_reply_message_script,
    _mail_send_message_script,
    _mail_set_flagged_status_script,
    _mail_set_read_status_script,
    _mail_trash_message_script,
    apply_mail_change,
    apply_mail_cleanup,
    apply_mail_mailbox_change,
    apply_mail_triage,
    create_mail_template,
    get_mail_mailbox,
    plan_mail_cleanup,
    plan_mail_change,
    plan_mail_mailbox_change,
    plan_mail_search_triage,
    plan_mail_triage,
    search_mail_mailboxes,
    search_mail_signatures,
)
from local_apple_data.handles import make_int_handle, make_opaque_handle


# An iCloud-style mailbox URL: imap://<account-UUID>/<mailbox>. The resolver pulls account id +
# mailbox name out of this, matching what was verified against live Mail.
MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/iCloud%20test%20mailbox"
MAILBOX_ACCOUNT_ID = "18E15B19-108F-4FD4-AE58-77F4468D00C1"
ARCHIVE_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Archive"
TRASH_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Trash"
JUNK_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Junk"
SENT_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Sent%20Messages"
ALL_MAIL_MAILBOX_URL = "imap://SENDER-ACCOUNT-ID/%5BGmail%5D/All%20Mail"
PROJECTS_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Projects"
SYNTHETIC_MAILBOX_URL = "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/LAD-TEST-old"
OTHER_ACCOUNT_MAILBOX_URL = "imap://SECOND-ACCOUNT-ID/Projects"
UNREAD_ROWID = 10
READ_ROWID = 11
ARCHIVED_ROWID = 12
TRASHED_ROWID = 13
SENT_ROWID = 14
REPLY_ROWID = 15
MOVED_ROWID = 16
FORWARD_ROWID = 17
STALE_FORWARD_ROWID = 18
STALE_REPLY_ROWID = 19
STALE_SEND_ROWID = 20
SYNTHETIC_TRASH_ROWID = 30
SYNTHETIC_TRASH_ROWID_2 = 31
REAL_TRASH_ROWID = 32
UNREAD_MSGID = "unread-001@example.test"
READ_MSGID = "read-001@example.test"
SYNTHETIC_TRASH_MSGID = "lad-test-trash-001@example.test"
SYNTHETIC_TRASH_MSGID_2 = "lad-test-trash-002@example.test"
REAL_TRASH_MSGID = "real-trash-001@example.test"
SENDER_ACCOUNT_ID = "SENDER-ACCOUNT-ID"
SENDER_ADDRESS = "visible-sender@example.invalid"
SENDER_ROWS = f"{SENDER_ACCOUNT_ID}\x1fVisible Sender Account\x1ftrue\x1fVisible Sender\x1f{SENDER_ADDRESS}"
CLEANUP_SENDER_ADDRESS = "cleanup-sender@example.invalid"
CLEANUP_SENDER_ROWS = f"{MAILBOX_ACCOUNT_ID}\x1fCleanup Sender Account\x1ftrue\x1fCleanup Sender\x1f{CLEANUP_SENDER_ADDRESS}"
SIGNATURE_NAME = "LAD Test Signature"
SIGNATURE_ROWS = SIGNATURE_NAME


def _make_mail_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject TEXT NOT NULL);
            CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY, url TEXT NOT NULL);
            CREATE TABLE message_global_data (
                ROWID INTEGER PRIMARY KEY,
                message_id_header TEXT
            );
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                subject INTEGER NOT NULL,
                mailbox INTEGER NOT NULL,
                message_id TEXT,
                global_message_id INTEGER,
                date_received INTEGER,
                date_sent INTEGER,
                read INTEGER NOT NULL DEFAULT 0,
                flagged INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        connection.execute("INSERT INTO subjects (ROWID, subject) VALUES (1, 'Unread'), (2, 'Read')")
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (1, ?)", (MAILBOX_URL,))
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (2, ?)", (ARCHIVE_MAILBOX_URL,))
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (3, ?)", (TRASH_MAILBOX_URL,))
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (6, ?)", (PROJECTS_MAILBOX_URL,))
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (7, ?)", (OTHER_ACCOUNT_MAILBOX_URL,))
        connection.execute(
            "INSERT INTO message_global_data (ROWID, message_id_header) VALUES (?, ?), (?, ?)",
            (UNREAD_ROWID, f"<{UNREAD_MSGID}>", READ_ROWID, READ_MSGID),
        )
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) VALUES (?,1,1,?,?,0)",
            (UNREAD_ROWID, "-3543720719788426468", UNREAD_ROWID),
        )
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) VALUES (?,2,1,?,?,1)",
            (READ_ROWID, "1251", READ_ROWID),
        )


def _write_emlx(path: Path, mime_text: str) -> None:
    mime_bytes = mime_text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes + b"\n")


def _make_mail_files(root: Path) -> None:
    messages = root / "TestAccount" / "Messages"
    _write_emlx(
        messages / f"{UNREAD_ROWID}.emlx",
        f"Message-ID: <{UNREAD_MSGID}>\nSubject: Unread\n\nSynthetic unread body.\n",
    )
    _write_emlx(
        messages / f"{READ_ROWID}.emlx",
        f"Message-ID: <{READ_MSGID}>\nSubject: Read\n\nSynthetic read body.\n",
    )


def _add_synthetic_mailbox(db: Path, *, mailbox_url: str = SYNTHETIC_MAILBOX_URL) -> None:
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (9, ?)", (mailbox_url,))


def _add_cleanup_messages(db: Path, mail_root: Path, *, include_real: bool = False) -> None:
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT OR IGNORE INTO mailboxes (ROWID, url) VALUES (4, ?)", (JUNK_MAILBOX_URL,))
        connection.execute(
            "INSERT INTO subjects (ROWID, subject) VALUES (?, ?)",
            (30, "LAD-TEST-trash-one"),
        )
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, read, flagged) VALUES (?, ?, ?, ?, 1, 0)",
            (SYNTHETIC_TRASH_ROWID, 30, 3, "synthetic-trash-db"),
        )
        connection.execute(
            "INSERT INTO subjects (ROWID, subject) VALUES (?, ?)",
            (31, "LAD-TEST-trash-two"),
        )
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, read, flagged) VALUES (?, ?, ?, ?, 1, 0)",
            (SYNTHETIC_TRASH_ROWID_2, 31, 3, "synthetic-trash-db-2"),
        )
        if include_real:
            connection.execute(
                "INSERT INTO subjects (ROWID, subject) VALUES (?, ?)",
                (32, "Real trash message"),
            )
            connection.execute(
                "INSERT INTO messages (ROWID, subject, mailbox, message_id, read, flagged) VALUES (?, ?, ?, ?, 1, 0)",
                (REAL_TRASH_ROWID, 32, 3, "real-trash-db"),
            )
    messages = mail_root / "TestAccount" / "Messages"
    _write_emlx(
        messages / f"{SYNTHETIC_TRASH_ROWID}.emlx",
        f"Message-ID: <{SYNTHETIC_TRASH_MSGID}>\nSubject: LAD-TEST-trash-one\n\nSynthetic trash body.\n",
    )
    _write_emlx(
        messages / f"{SYNTHETIC_TRASH_ROWID_2}.emlx",
        f"Message-ID: <{SYNTHETIC_TRASH_MSGID_2}>\nSubject: LAD-TEST-trash-two\n\nSynthetic trash body.\n",
    )
    if include_real:
        _write_emlx(
            messages / f"{REAL_TRASH_ROWID}.emlx",
            f"Message-ID: <{REAL_TRASH_MSGID}>\nSubject: Real trash message\n\nReal trash body.\n",
        )


def _handle(rowid: int) -> str:
    return make_int_handle("mail:message", rowid)


def _sender_handle() -> str:
    return make_opaque_handle("mail:sender", f"{SENDER_ACCOUNT_ID}\0{SENDER_ADDRESS}")


def _cleanup_sender_handle() -> str:
    return make_opaque_handle("mail:sender", f"{MAILBOX_ACCOUNT_ID}\0{CLEANUP_SENDER_ADDRESS}")


def _fail_if_called(script: str, timeout: float) -> str:
    raise AssertionError("Mail automation must not run")


def _sender_search_runner(script: str, timeout: float) -> str:
    assert timeout == 10.0
    assert "repeat with mailAccount in accounts" in script
    return SENDER_ROWS


def _cleanup_sender_search_runner(script: str, timeout: float) -> str:
    assert timeout == 10.0
    assert "repeat with mailAccount in accounts" in script
    return CLEANUP_SENDER_ROWS


def _sender_dispatch_runner(base_runner):
    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _sender_search_runner(script, timeout)
        return base_runner(script, timeout)

    return runner


def _signature_handle() -> str:
    return make_opaque_handle("mail:signature", SIGNATURE_NAME)


def _signature_search_runner(script: str, timeout: float) -> str:
    assert timeout == 10.0
    assert "repeat with mailSignature in signatures" in script
    assert "content of mailSignature" not in script
    return SIGNATURE_ROWS


def _signature_dispatch_runner(base_runner):
    def runner(script: str, timeout: float) -> str:
        if "repeat with mailSignature in signatures" in script:
            return _signature_search_runner(script, timeout)
        return base_runner(script, timeout)

    return runner


def _assert_forward_error_does_not_echo_body(result: dict) -> None:
    serialized = json.dumps(result, sort_keys=True)
    assert "body_preview_text" not in serialized
    assert "Synthetic forward note." not in serialized
    assert "Synthetic unread body" not in serialized
    assert result["plan"]["proposed"]["body_preview_returned"] is False


def _flipping_runner(db_path: Path, rowid: int, expected_message_id: str, target_read: bool):
    """Mocked Mail.app automation: mimic the real read-flag flip so read-back can confirm."""

    def runner(script: str, timeout: float) -> str:
        assert "read status" in script
        assert expected_message_id in script
        assert "-3543720719788426468" not in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET read = ? WHERE ROWID = ?",
                (1 if target_read else 0, rowid),
            )
        return "ok"

    return runner


def _flagging_runner(db_path: Path, rowid: int, expected_message_id: str, target_flagged: bool):
    """Mocked Mail.app automation: mimic the real flagged-status flip so read-back can confirm."""

    def runner(script: str, timeout: float) -> str:
        assert "flagged status" in script
        assert expected_message_id in script
        assert "-3543720719788426468" not in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET flagged = ? WHERE ROWID = ?",
                (1 if target_flagged else 0, rowid),
            )
        return "ok"

    return runner


def _move_runner(db_path: Path, rowid: int, expected_message_id: str, target_mailbox_id: int = 6):
    """Mocked Mail.app automation: mimic an exact mailbox move so read-back can confirm."""

    def runner(script: str, timeout: float) -> str:
        assert "move (first item of triageMatches) to targetBox" in script
        assert expected_message_id in script
        assert "-3543720719788426468" not in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET mailbox = ? WHERE ROWID = ?",
                (target_mailbox_id, rowid),
            )
        return "ok"

    return runner


def _archive_runner(db_path: Path, rowid: int, expected_message_id: str):
    """Mocked Mail.app automation: mimic moving one exact message to Archive for read-back."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "move (first item of triageMatches) to archiveBox" in script
        assert "mailbox \"Archive\"" in script
        assert expected_message_id in script
        assert "-3543720719788426468" not in script
        lowered = script.lower()
        for forbidden in ("send ", "delete", "erase", "empty", "trash", "remove"):
            assert forbidden not in lowered
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET mailbox = 2 WHERE ROWID = ?",
                (rowid,),
            )
        return "ok"

    return runner


def _trash_runner(db_path: Path, rowid: int, expected_message_id: str):
    """Mocked Mail.app automation: mimic moving one exact message to Trash for read-back."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "move (first item of triageMatches) to trashBox" in script
        assert "mailbox \"Trash\"" in script
        assert expected_message_id in script
        assert "-3543720719788426468" not in script
        lowered = script.lower()
        for forbidden in ("send ", "delete", "erase", "empty", "remove"):
            assert forbidden not in lowered
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET mailbox = 3 WHERE ROWID = ?",
                (rowid,),
            )
        return "ok"

    return runner


def _send_runner(db_path: Path, mail_root: Path):
    """Mocked Mail.app automation: mimic a sent copy appearing in the local Sent mailbox."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "make new outgoing message" in script
        assert "send outboundMessage" in script
        assert "save " not in script.lower()
        assert "synthetic-recipient@example.invalid" in script
        assert "Synthetic outbound" in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO subjects (ROWID, subject) VALUES (4, 'Synthetic outbound')"
            )
            connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (4, ?)", (SENT_MAILBOX_URL,))
            connection.execute(
                """
                INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
                VALUES (?, 4, 4, ?, 1)
                """,
                (SENT_ROWID, "synthetic-sent-id"),
            )
        _write_emlx(
            mail_root / "SentAccount" / "Messages" / f"{SENT_ROWID}.emlx",
            "Message-ID: <synthetic-sent-id@example.test>\n"
            "Subject: Synthetic outbound\n\n"
            "Synthetic outbound body.\n",
        )
        if SENDER_ADDRESS in script:
            assert "set sender of outboundMessage to outboundSender" in script
            return f"synthetic-outbound-id\nsender:{SENDER_ADDRESS}\nattachment_count:0"
        if SIGNATURE_NAME in script:
            assert "set message signature of outboundMessage to signature outboundSignatureName" in script
            assert "content of signature" not in script
            return f"synthetic-outbound-id\nsignature:{SIGNATURE_NAME}\nattachment_count:0"
        return "synthetic-outbound-id"

    return runner


def _send_all_mail_runner(db_path: Path, mail_root: Path):
    """Mocked Mail.app automation: mimic Gmail surfacing a sent copy in All Mail."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "make new outgoing message" in script
        assert "send outboundMessage" in script
        assert "synthetic-recipient@example.invalid" in script
        assert "Synthetic outbound" in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO subjects (ROWID, subject) VALUES (4, 'Synthetic outbound')"
            )
            connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (4, ?)", (ALL_MAIL_MAILBOX_URL,))
            connection.execute(
                """
                INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
                VALUES (?, 4, 4, ?, 1)
                """,
                (SENT_ROWID, "synthetic-gmail-all-mail-id"),
            )
        _write_emlx(
            mail_root / "SentAccount" / "Messages" / f"{SENT_ROWID}.emlx",
            "Message-ID: <synthetic-gmail-all-mail-id@example.test>\n"
            "Subject: Synthetic outbound\n\n"
            "> Synthetic outbound body.\n",
        )
        if SENDER_ADDRESS in script:
            assert "set sender of outboundMessage to outboundSender" in script
            return f"synthetic-outbound-id\nsender:{SENDER_ADDRESS}\nattachment_count:0"
        return "synthetic-outbound-id"

    return runner


def _reply_runner(db_path: Path, mail_root: Path, *, reply_to_all: bool = False):
    """Mocked Mail.app automation: mimic a reply copy appearing in the local Sent mailbox."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        reply_all_flag = "true" if reply_to_all else "false"
        assert f"reply sourceMessage opening window false reply to all {reply_all_flag}" in script
        assert "send replyMessage" in script
        assert "set content of replyMessage to replyBody" in script
        assert UNREAD_MSGID in script
        lowered = script.lower()
        for forbidden in ("make new to recipient", "save ", "move ", "delete", "erase", "empty"):
            assert forbidden not in lowered
        with sqlite3.connect(db_path) as connection:
            connection.execute("INSERT INTO subjects (ROWID, subject) VALUES (5, 'Re: Unread')")
            connection.execute("INSERT INTO mailboxes (ROWID, url) VALUES (5, ?)", (SENT_MAILBOX_URL,))
            connection.execute(
                """
                INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
                VALUES (?, 5, 5, ?, 1)
                """,
                (REPLY_ROWID, "synthetic-reply-id"),
            )
        _write_emlx(
            mail_root / "SentAccount" / "Messages" / f"{REPLY_ROWID}.emlx",
            "Message-ID: <synthetic-reply-id@example.test>\n"
            "Subject: Re: Unread\n\n"
            "Synthetic reply body.\n",
        )
        if SENDER_ADDRESS in script:
            assert "set sender of replyMessage to replySender" in script
            return f"synthetic-reply-id\nsender:{SENDER_ADDRESS}\nattachment_count:0"
        if SIGNATURE_NAME in script:
            assert "set message signature of replyMessage to signature replySignatureName" in script
            assert "content of signature" not in script
            return f"synthetic-reply-id\nsignature:{SIGNATURE_NAME}\nattachment_count:0"
        return "synthetic-reply-id"

    return runner


def _write_forward_sent_copy(
    db_path: Path,
    mail_root: Path,
    *,
    rowid: int,
    body_text: str = "Synthetic forward note.\n\nForwarded source body.",
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO subjects (ROWID, subject) VALUES (6, 'Fwd: Unread')")
        connection.execute("INSERT OR IGNORE INTO mailboxes (ROWID, url) VALUES (8, ?)", (SENT_MAILBOX_URL,))
        connection.execute(
            """
            INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
            VALUES (?, 6, 8, ?, 1)
            """,
            (rowid, f"synthetic-forward-id-{rowid}"),
        )
    _write_emlx(
        mail_root / "SentAccount" / "Messages" / f"{rowid}.emlx",
        f"Message-ID: <synthetic-forward-id-{rowid}@example.test>\n"
        "Subject: Fwd: Unread\n\n"
        f"{body_text}\n",
    )


def _write_reply_sent_copy(
    db_path: Path,
    mail_root: Path,
    *,
    rowid: int,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO subjects (ROWID, subject) VALUES (8, 'Re: Unread')")
        connection.execute("INSERT OR IGNORE INTO mailboxes (ROWID, url) VALUES (9, ?)", (SENT_MAILBOX_URL,))
        connection.execute(
            """
            INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
            VALUES (?, 8, 9, ?, 1)
            """,
            (rowid, f"synthetic-stale-reply-id-{rowid}"),
        )
    _write_emlx(
        mail_root / "SentAccount" / "Messages" / f"{rowid}.emlx",
        f"Message-ID: <synthetic-stale-reply-id-{rowid}@example.test>\n"
        "Subject: Re: Unread\n\n"
        "Synthetic reply body.\n",
    )


def _write_send_sent_copy(
    db_path: Path,
    mail_root: Path,
    *,
    rowid: int,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO subjects (ROWID, subject) VALUES (9, 'Synthetic outbound')")
        connection.execute("INSERT OR IGNORE INTO mailboxes (ROWID, url) VALUES (10, ?)", (SENT_MAILBOX_URL,))
        connection.execute(
            """
            INSERT INTO messages (ROWID, subject, mailbox, message_id, read)
            VALUES (?, 9, 10, ?, 1)
            """,
            (rowid, f"synthetic-stale-send-id-{rowid}"),
        )
    _write_emlx(
        mail_root / "SentAccount" / "Messages" / f"{rowid}.emlx",
        f"Message-ID: <synthetic-stale-send-id-{rowid}@example.test>\n"
        "Subject: Synthetic outbound\n\n"
        "Synthetic outbound body.\n",
    )


def _forward_runner(db_path: Path, mail_root: Path):
    """Mocked Mail.app automation: mimic a forward copy appearing in the local Sent mailbox."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "forward sourceMessage opening window false" in script
        assert "send forwardMessage" in script
        assert "set content of forwardMessage to forwardBody" in script
        assert "make new to recipient" in script
        assert 'address:"synthetic-forward@example.invalid"' in script
        assert UNREAD_MSGID in script
        lowered = script.lower()
        for forbidden in ("make new outgoing message", "reply ", "save ", "move ", "delete", "erase", "empty"):
            assert forbidden not in lowered
        _write_forward_sent_copy(db_path, mail_root, rowid=FORWARD_ROWID)
        if SENDER_ADDRESS in script:
            assert "set sender of forwardMessage to forwardSender" in script
            return f"synthetic-forward-id\nsender:{SENDER_ADDRESS}\nattachment_count:0"
        if SIGNATURE_NAME in script:
            assert "set message signature of forwardMessage to signature forwardSignatureName" in script
            assert "content of signature" not in script
            return f"synthetic-forward-id\nsignature:{SIGNATURE_NAME}\nattachment_count:0"
        return "synthetic-forward-id"

    return runner


def _source_attachment_forward_runner(
    db_path: Path,
    mail_root: Path,
    *,
    expected_count: int = 1,
    expected_message_id: str = UNREAD_MSGID,
):
    """Mocked Mail.app automation for a forward that preserves source attachments."""

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "forward sourceMessage opening window false" in script
        assert f"if savedAttachmentCount is not {expected_count}" in script
        assert "send forwardMessage" in script
        assert expected_message_id in script
        _write_forward_sent_copy(db_path, mail_root, rowid=FORWARD_ROWID)
        return f"synthetic-forward-id\nattachment_count:{expected_count}"

    return runner


def _write_attachment_source(mail_root: Path, rowid: int) -> None:
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{rowid}.emlx",
        "Message-ID: <attachment-source@example.test>\n"
        "Subject: Unread\n"
        "MIME-Version: 1.0\n"
        "Content-Type: multipart/mixed; boundary=\"BOUNDARY\"\n"
        "\n"
        "--BOUNDARY\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Body with attachment.\n"
        "--BOUNDARY\n"
        "Content-Type: text/plain; name=\"synthetic.txt\"\n"
        "Content-Disposition: attachment; filename=\"synthetic.txt\"\n"
        "\n"
        "attachment bytes\n"
        "--BOUNDARY--\n",
    )


def _write_many_attachment_source(mail_root: Path, rowid: int, *, count: int) -> None:
    parts = []
    for index in range(count):
        parts.append(
            "--BOUNDARY\n"
            "Content-Type: text/plain; charset=utf-8\n"
            f"Content-Disposition: attachment; filename=\"synthetic-{index}.txt\"\n"
            "\n"
            f"attachment {index}\n"
        )
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{rowid}.emlx",
        "Message-ID: <many-attachment-source@example.test>\n"
        "Subject: Unread\n"
        "MIME-Version: 1.0\n"
        "Content-Type: multipart/mixed; boundary=\"BOUNDARY\"\n"
        "\n"
        "--BOUNDARY\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Body with many attachments.\n"
        + "".join(parts)
        + "--BOUNDARY--\n",
    )


def _write_inline_image_source(mail_root: Path, rowid: int) -> None:
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{rowid}.emlx",
        "Message-ID: <inline-image-source@example.test>\n"
        "Subject: Unread\n"
        "MIME-Version: 1.0\n"
        "Content-Type: multipart/related; boundary=\"BOUNDARY\"\n"
        "\n"
        "--BOUNDARY\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        "<html><body><img src=\"cid:synthetic-image\"></body></html>\n"
        "--BOUNDARY\n"
        "Content-Type: image/png\n"
        "Content-ID: <synthetic-image>\n"
        "Content-Transfer-Encoding: base64\n"
        "\n"
        "iVBORw0KGgo=\n"
        "--BOUNDARY--\n",
    )


def _write_non_text_part_source(mail_root: Path, rowid: int, *, part_headers: str) -> None:
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{rowid}.emlx",
        "Message-ID: <non-text-part-source@example.test>\n"
        "Subject: Unread\n"
        "MIME-Version: 1.0\n"
        "Content-Type: multipart/mixed; boundary=\"BOUNDARY\"\n"
        "\n"
        "--BOUNDARY\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Body with non-text part.\n"
        "--BOUNDARY\n"
        f"{part_headers}"
        "\n"
        "AAECAwQ=\n"
        "--BOUNDARY--\n",
    )


def test_plan_send_message_returns_irreversible_send_preview() -> None:
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )

    assert plan["status"] == "ok"
    assert plan["privacy"]["content_inspected"] is True
    preview = plan["preview"]
    assert preview["operation"] == "send_message"
    assert preview["target"] == {"account": "mail_app_default", "mailbox": "outbound_send"}
    assert preview["proposed"]["kind"] == "mail_send"
    assert preview["proposed"]["send_permitted"] is True
    assert preview["proposed"]["irreversible_external_send"] is True
    assert preview["proposed"]["retry_safe"] is False
    assert preview["proposed"]["attachments_permitted"] is False


def test_plan_send_message_accepts_exact_sender_handle_without_full_email() -> None:
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        sender_handle=_sender_handle(),
        script_runner=_sender_search_runner,
    )

    assert plan["status"] == "ok"
    preview = plan["preview"]
    assert preview["target"]["account"] == "selected_sender"
    assert preview["target"]["mailbox"] == "outbound_send"
    assert preview["proposed"]["sender_selection"]["mode"] == "exact_sender_handle"
    assert preview["proposed"]["sender_selection"]["sender_selected"] is True
    assert preview["proposed"]["sender_selection"]["sender_handle"] == _sender_handle()
    assert preview["proposed"]["sender_selection"]["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(plan, sort_keys=True)


def test_plan_send_message_accepts_exact_signature_handle_without_body() -> None:
    signature_handle = search_mail_signatures("LAD", script_runner=_signature_search_runner)["results"][0]["handle"]
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        signature_handle=signature_handle,
        script_runner=_signature_search_runner,
    )

    assert plan["status"] == "ok"
    selection = plan["preview"]["proposed"]["signature_selection"]
    assert selection["mode"] == "exact_signature_handle"
    assert selection["signature_selected"] is True
    assert selection["signature_handle"] == signature_handle
    assert selection["body_returned"] is False
    assert selection["content_returned"] is False


def test_plan_forward_message_returns_exact_source_preview(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "ok"
    preview = plan["preview"]
    assert preview["operation"] == "forward_message"
    assert preview["target"]["message_handle"] == _handle(UNREAD_ROWID)
    assert preview["proposed"]["kind"] == "mail_forward"
    assert preview["proposed"]["subject"] == "Fwd: Unread"
    assert preview["proposed"]["source_body_included"] is True
    assert preview["proposed"]["source_attachments_permitted"] is False
    assert preview["proposed"]["source_non_text_parts_permitted"] is False
    assert preview["proposed"]["source_non_body_parts_permitted"] is False
    assert preview["proposed"]["source_attachment_count"] == 0
    assert preview["proposed"]["recipient_inputs_permitted"] is True
    assert preview["proposed"]["subject_input_permitted"] is False
    assert preview["proposed"]["irreversible_external_send"] is True
    assert preview["proposed"]["retry_safe"] is False
    assert preview["proposed"]["attachments_permitted"] is False
    assert preview["source_attachment_state"]
    assert preview["source_content_state"]


def test_plan_forward_message_accepts_exact_sender_handle_without_full_email(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        sender_handle=_sender_handle(),
        db_path=db,
        script_runner=_sender_search_runner,
    )

    assert plan["status"] == "ok"
    selection = plan["preview"]["proposed"]["sender_selection"]
    assert selection["mode"] == "exact_sender_handle"
    assert selection["sender_selected"] is True
    assert selection["sender_handle"] == _sender_handle()
    assert selection["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(plan, sort_keys=True)


def test_plan_forward_message_accepts_exact_signature_handle_without_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    signature_handle = search_mail_signatures("LAD", script_runner=_signature_search_runner)["results"][0]["handle"]

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        signature_handle=signature_handle,
        db_path=db,
        script_runner=_signature_search_runner,
    )

    assert plan["status"] == "ok"
    selection = plan["preview"]["proposed"]["signature_selection"]
    assert selection["mode"] == "exact_signature_handle"
    assert selection["signature_selected"] is True
    assert selection["signature_handle"] == signature_handle
    assert selection["body_returned"] is False
    assert selection["content_returned"] is False


def test_plan_forward_message_can_include_source_attachments_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_attachment_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        db_path=db,
    )

    assert plan["status"] == "ok"
    preview = plan["preview"]
    assert preview["proposed"]["source_attachments_permitted"] is True
    assert preview["proposed"]["source_non_text_parts_permitted"] is True
    assert preview["proposed"]["source_non_body_parts_permitted"] is True
    assert preview["proposed"]["source_attachment_count"] == 1
    assert preview["proposed"]["source_attachment_like_part_count"] == 1
    assert preview["proposed"]["source_declared_attachment_count"] == 1
    assert preview["proposed"]["source_non_body_part_count"] == 0
    assert preview["proposed"]["source_attachment_forwarding_requested"] is True
    assert preview["proposed"]["source_forward_verification"] == "mail_attachment_count_pre_send"
    dumped = json.dumps(plan, sort_keys=True)
    assert "attachment bytes" not in dumped
    assert "synthetic.txt" not in dumped


def test_plan_forward_message_can_include_inline_non_body_part_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_inline_image_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        db_path=db,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["source_attachment_count"] == 1
    assert proposed["source_attachment_like_part_count"] == 1
    assert proposed["source_declared_attachment_count"] == 0
    assert proposed["source_non_body_part_count"] == 1
    assert proposed["source_non_body_parts_permitted"] is True
    dumped = json.dumps(plan, sort_keys=True)
    assert "synthetic-image" not in dumped
    assert "iVBORw0" not in dumped


def test_plan_forward_message_source_parts_are_not_limited_by_public_attachment_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_many_attachment_source(mail_root, UNREAD_ROWID, count=55)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        db_path=db,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["source_attachment_count"] == 55
    assert proposed["source_attachment_like_part_count"] == 55
    assert proposed["source_declared_attachment_count"] == 55
    assert proposed["source_non_body_part_count"] == 0
    assert "synthetic-54.txt" not in json.dumps(plan, sort_keys=True)


def test_plan_reply_message_returns_exact_source_sender_only_preview(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "reply-message",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply body.",
        db_path=db,
    )

    assert plan["status"] == "ok"
    preview = plan["preview"]
    assert preview["operation"] == "reply_message"
    assert preview["target"]["message_handle"] == _handle(UNREAD_ROWID)
    assert preview["proposed"]["kind"] == "mail_reply"
    assert preview["proposed"]["reply_mode"] == "sender_only"
    assert preview["proposed"]["reply_all_permitted"] is False
    assert preview["proposed"]["recipient_inputs_permitted"] is False
    assert preview["proposed"]["subject"] == "Re: Unread"
    assert preview["proposed"]["irreversible_external_send"] is True
    assert preview["proposed"]["retry_safe"] is False
    assert preview["proposed"]["attachments_permitted"] is False


def test_plan_reply_message_accepts_exact_sender_handle_without_full_email(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "reply-message",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply body.",
        sender_handle=_sender_handle(),
        db_path=db,
        script_runner=_sender_search_runner,
    )

    assert plan["status"] == "ok"
    selection = plan["preview"]["proposed"]["sender_selection"]
    assert selection["mode"] == "exact_sender_handle"
    assert selection["sender_selected"] is True
    assert selection["sender_handle"] == _sender_handle()
    assert selection["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(plan, sort_keys=True)


def test_plan_reply_message_accepts_exact_signature_handle_without_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    signature_handle = search_mail_signatures("LAD", script_runner=_signature_search_runner)["results"][0]["handle"]

    plan = plan_mail_change(
        "reply-message",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply body.",
        signature_handle=signature_handle,
        db_path=db,
        script_runner=_signature_search_runner,
    )

    assert plan["status"] == "ok"
    selection = plan["preview"]["proposed"]["signature_selection"]
    assert selection["mode"] == "exact_signature_handle"
    assert selection["signature_selected"] is True
    assert selection["signature_handle"] == signature_handle
    assert selection["body_returned"] is False
    assert selection["content_returned"] is False


def test_plan_reply_all_message_returns_exact_source_reply_all_preview(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "reply-all-message",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply-all body.",
        db_path=db,
    )

    assert plan["status"] == "ok"
    preview = plan["preview"]
    assert preview["operation"] == "reply_all_message"
    assert preview["target"]["message_handle"] == _handle(UNREAD_ROWID)
    assert preview["proposed"]["kind"] == "mail_reply"
    assert preview["proposed"]["reply_mode"] == "reply_all"
    assert preview["proposed"]["reply_all_permitted"] is True
    assert preview["proposed"]["recipient_inputs_permitted"] is False
    assert preview["proposed"]["subject"] == "Re: Unread"
    assert preview["proposed"]["irreversible_external_send"] is True
    assert preview["proposed"]["retry_safe"] is False
    assert preview["proposed"]["attachments_permitted"] is False


def test_public_mail_apply_dispatches_reply_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_reply_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["source_message_handle"] == handle
    assert result["read_back"]["reply_mode"] == "sender_only"
    assert result["read_back"]["body_returned"] is False


def test_public_mail_apply_dispatches_reply_message_with_sender_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        sender_handle=_sender_handle(),
        db_path=db,
        script_runner=_sender_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        sender_handle=_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_sender_dispatch_runner(_reply_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["sender_selection_confirmed"] is True
    assert result["read_back"]["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(result, sort_keys=True)


def test_public_mail_apply_dispatches_reply_message_with_signature_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        signature_handle=_signature_handle(),
        db_path=db,
        script_runner=_signature_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        signature_handle=_signature_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_signature_dispatch_runner(_reply_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["signature_selection_confirmed"] is True
    assert result["read_back"]["signature_body_returned"] is False
    assert result["read_back"]["signature_content_returned"] is False


def test_public_mail_apply_dispatches_reply_all_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-all-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-all-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_reply_runner(db, mail_root, reply_to_all=True),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["source_message_handle"] == handle
    assert result["read_back"]["reply_mode"] == "reply_all"
    assert result["read_back"]["body_returned"] is False


def test_reply_all_script_sets_exact_sender_when_requested() -> None:
    script = _mail_reply_message_script(
        account_id="ACCOUNT-ID",
        mailbox_name="Inbox",
        message_id=UNREAD_MSGID,
        body_text="Synthetic reply body.",
        sender=SENDER_ADDRESS,
        reply_to_all=True,
    )

    assert f"set replySender to \"{SENDER_ADDRESS}\"" in script
    assert "reply sourceMessage opening window false reply to all true" in script
    assert "set sender of replyMessage to replySender" in script
    assert "send replyMessage" in script


def test_reply_all_script_sets_exact_signature_when_requested() -> None:
    script = _mail_reply_message_script(
        account_id="ACCOUNT-ID",
        mailbox_name="Inbox",
        message_id=UNREAD_MSGID,
        body_text="Synthetic reply body.",
        signature_name=SIGNATURE_NAME,
        reply_to_all=True,
    )

    assert f"set replySignatureName to \"{SIGNATURE_NAME}\"" in script
    assert "reply sourceMessage opening window false reply to all true" in script
    assert "set message signature of replyMessage to signature replySignatureName" in script
    assert "content of signature" not in script
    assert "send replyMessage" in script


def test_public_mail_apply_dispatches_forward_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_forward_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["forward_copy_confirmed"] is True
    assert result["read_back"]["source_message_handle"] == handle
    assert result["read_back"]["forward_mode"] == "exact_source_message"
    assert result["read_back"]["source_body_included"] is True
    assert result["read_back"]["source_attachments_permitted"] is False
    assert result["read_back"]["source_non_text_parts_permitted"] is False
    assert result["read_back"]["source_non_body_parts_permitted"] is False
    assert result["read_back"]["source_content_state"] == plan["preview"]["source_content_state"]
    assert result["read_back"]["body_returned"] is False
    assert result["read_back"]["prepended_body_sha256"] == hashlib.sha256(
        "Synthetic forward note.".encode("utf-8")
    ).hexdigest()
    dumped = json.dumps(result, sort_keys=True)
    assert "Synthetic forward note." not in dumped
    assert "Synthetic unread body." not in dumped


def test_public_mail_apply_dispatches_forward_message_with_sender_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        sender_handle=_sender_handle(),
        db_path=db,
        script_runner=_sender_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        sender_handle=_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_sender_dispatch_runner(_forward_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["forward_copy_confirmed"] is True
    assert result["read_back"]["sender_selection_confirmed"] is True
    assert result["read_back"]["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(result, sort_keys=True)


def test_public_mail_apply_dispatches_forward_message_with_signature_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        signature_handle=_signature_handle(),
        db_path=db,
        script_runner=_signature_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        signature_handle=_signature_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_signature_dispatch_runner(_forward_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["forward_copy_confirmed"] is True
    assert result["read_back"]["signature_selection_confirmed"] is True
    assert result["read_back"]["signature_body_returned"] is False
    assert result["read_back"]["signature_content_returned"] is False


def test_public_mail_apply_dispatches_source_attachment_forward_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_attachment_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_source_attachment_forward_runner(
            db,
            mail_root,
            expected_count=1,
            expected_message_id="attachment-source@example.test",
        ),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["source_attachments_permitted"] is True
    assert result["read_back"]["source_non_text_parts_permitted"] is True
    assert result["read_back"]["source_non_body_parts_permitted"] is True
    assert result["read_back"]["source_attachment_count"] == 1
    assert result["read_back"]["source_attachment_like_part_count"] == 1
    assert result["read_back"]["source_declared_attachment_count"] == 1
    assert result["read_back"]["source_non_body_part_count"] == 0
    assert result["read_back"]["forwarded_attachment_count"] == 1
    assert result["read_back"]["source_forward_verification"] == "mail_attachment_count_pre_send"
    assert result["read_back"]["body_returned"] is False
    dumped = json.dumps(result, sort_keys=True)
    assert "attachment bytes" not in dumped
    assert "Synthetic forward note." not in dumped


def test_public_mail_apply_dispatches_inline_non_body_forward_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_inline_image_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_source_attachment_forward_runner(
            db,
            mail_root,
            expected_count=1,
            expected_message_id="inline-image-source@example.test",
        ),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["source_attachment_count"] == 1
    assert result["read_back"]["source_declared_attachment_count"] == 0
    assert result["read_back"]["source_non_body_part_count"] == 1
    assert result["read_back"]["forwarded_attachment_count"] == 1
    dumped = json.dumps(result, sort_keys=True)
    assert "synthetic-image" not in dumped


def test_apply_forward_message_is_partial_when_sent_readback_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_DELAY_SECONDS", 0)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-forward-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"
    dumped = json.dumps(result, sort_keys=True)
    assert "Synthetic forward note." not in dumped
    assert result["plan"]["proposed"]["body_preview_returned"] is False
    assert "body_preview_text" not in result["plan"]["proposed"]


def test_apply_forward_message_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=False,
        db_path=db,
        mail_root=mail_root,
        script_runner=_fail_if_called,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_forward_message_rejects_invalid_token(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=f"{APPROVAL_TOKEN_PREFIX}wrong",
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_fail_if_called,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    _assert_forward_error_does_not_echo_body(result)


def test_apply_forward_message_rejects_stale_source_state_after_token_check(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    real_fingerprint = mail_adapter._triage_state_fingerprint
    calls = {"count": 0}

    def drifting_fingerprint(target):
        calls["count"] += 1
        if calls["count"] >= 2:
            return "drifted-source-state"
        return real_fingerprint(target)

    monkeypatch.setattr(mail_adapter, "_triage_state_fingerprint", drifting_fingerprint)

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_forward_runner(db, mail_root),
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "stale_message_state"
    _assert_forward_error_does_not_echo_body(result)


def test_apply_forward_message_ignores_stale_matching_sent_copy(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_forward_sent_copy(db, mail_root, rowid=STALE_FORWARD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-forward-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_forward_message_rejects_ambiguous_new_sent_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def runner(script: str, timeout: float) -> str:
        assert "forward sourceMessage opening window false" in script
        _write_forward_sent_copy(db, mail_root, rowid=FORWARD_ROWID)
        _write_forward_sent_copy(db, mail_root, rowid=FORWARD_ROWID + 100)
        return "synthetic-forward-id"

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "ambiguous_forward_read_back"
    _assert_forward_error_does_not_echo_body(result)


def test_apply_forward_message_rejects_stale_source_content_state(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    real_source_content_state = mail_adapter._forward_source_content_state
    calls = {"count": 0}

    def drifting_source_content_state(target, *, mail_root):
        calls["count"] += 1
        state, warning = real_source_content_state(target, mail_root=mail_root)
        if calls["count"] >= 2:
            return {**state, "safe_sha256": "drifted-source-content-state"}, warning
        return state, warning

    monkeypatch.setattr(mail_adapter, "_forward_source_content_state", drifting_source_content_state)

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_fail_if_called,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "stale_source_content_state"
    _assert_forward_error_does_not_echo_body(result)


def test_apply_reply_message_is_partial_when_sent_readback_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_DELAY_SECONDS", 0)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-reply-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_reply_message_ignores_stale_matching_sent_copy(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_reply_sent_copy(db, mail_root, rowid=STALE_REPLY_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_DELAY_SECONDS", 0)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-reply-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_reply_message_confirms_new_sent_copy_when_stale_copy_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_reply_sent_copy(db, mail_root, rowid=STALE_REPLY_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "reply-message",
        message_handle=handle,
        body_text="Synthetic reply body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_reply_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["reply_copy_confirmed"] is True
    assert result["read_back"]["handle"] != _handle(STALE_REPLY_ROWID)


def test_plan_forward_message_rejects_subject_missing_recipient_and_missing_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        subject="Synthetic override",
        message_handle=_handle(UNREAD_ROWID),
        body_text="",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert {warning["code"] for warning in plan["warnings"]} >= {
        "unexpected_subject",
        "missing_to",
        "missing_body_text",
    }


def test_plan_forward_message_rejects_invalid_handle_malformed_recipient_and_overlong_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    invalid_handle = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle="mail:message:v1:raw-rowid",
        body_text="Synthetic forward note.",
        db_path=db,
    )
    bad_inputs = plan_mail_change(
        "forward-message",
        to=["not-an-address"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="x" * (mail_adapter.MAX_DRAFT_BODY_CHARS + 1),
        db_path=db,
    )

    assert invalid_handle["status"] == "error"
    assert invalid_handle["warnings"][0]["code"] == "invalid_message_handle"
    assert bad_inputs["status"] == "error"
    assert {warning["code"] for warning in bad_inputs["warnings"]} >= {
        "invalid_to_recipient",
        "missing_to",
        "body_too_long",
    }


def test_plan_forward_message_rejects_source_attachments(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_attachment_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert plan["privacy"]["content_inspected"] is True
    assert plan["warnings"][0]["code"] == "source_has_attachments"


def test_plan_mail_rejects_source_attachment_flag_outside_forward() -> None:
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        include_source_attachments=True,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "unexpected_include_source_attachments"


def test_plan_forward_message_rejects_inline_non_text_mime_parts(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_inline_image_source(mail_root, UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert plan["privacy"]["content_inspected"] is True
    assert plan["warnings"][0]["code"] == "source_has_attachments"


def test_plan_forward_message_rejects_non_text_mime_part_without_content_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_non_text_part_source(
        mail_root,
        UNREAD_ROWID,
        part_headers="Content-Type: application/pdf\nContent-Transfer-Encoding: base64\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "source_has_attachments"


def test_plan_forward_message_rejects_inline_non_text_disposition_without_filename(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_non_text_part_source(
        mail_root,
        UNREAD_ROWID,
        part_headers=(
            "Content-Type: application/octet-stream\n"
            "Content-Disposition: inline\n"
            "Content-Transfer-Encoding: base64\n"
        ),
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "source_has_attachments"


def test_plan_forward_message_rejects_calendar_mime_part_without_filename(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_non_text_part_source(
        mail_root,
        UNREAD_ROWID,
        part_headers="Content-Type: text/calendar; charset=utf-8\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic forward note.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "source_has_attachments"


def test_plan_reply_message_rejects_direct_recipients_and_subject(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "reply-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic override",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply body.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert {warning["code"] for warning in plan["warnings"]} >= {
        "unexpected_recipient_inputs",
            "unexpected_subject",
    }


def test_plan_reply_all_message_rejects_direct_recipients_and_subject(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "reply-all-message",
        cc=["synthetic-recipient@example.invalid"],
        subject="Synthetic override",
        message_handle=_handle(UNREAD_ROWID),
        body_text="Synthetic reply body.",
        db_path=db,
    )

    assert plan["status"] == "error"
    assert {warning["code"] for warning in plan["warnings"]} >= {
        "unexpected_recipient_inputs",
        "unexpected_subject",
    }


def test_apply_forward_message_rejects_stale_attachment_state(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    real_attachment_state = mail_adapter._forward_attachment_state
    calls = {"count": 0}

    def drifting_attachment_state(message_handle, *, db_path, mail_root, include_source_attachments=False):
        calls["count"] += 1
        state, warning = real_attachment_state(
            message_handle,
            db_path=db_path,
            mail_root=mail_root,
            include_source_attachments=include_source_attachments,
        )
        if calls["count"] >= 2:
            return {**state, "safe_sha256": "drifted-source-attachment-state"}, warning
        return state, warning

    monkeypatch.setattr(mail_adapter, "_forward_attachment_state", drifting_attachment_state)

    result = apply_mail_change(
        "forward-message",
        to=["synthetic-forward@example.invalid"],
        message_handle=handle,
        body_text="Synthetic forward note.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_fail_if_called,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "stale_source_attachment_state"
    _assert_forward_error_does_not_echo_body(result)


def test_public_mail_apply_dispatches_send_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_send_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["body_returned"] is False
    assert result["read_back"]["content_chars"] == len("Synthetic outbound body.")
    assert result["read_back"]["content_sha256"] == hashlib.sha256(
        "Synthetic outbound body.".encode("utf-8")
    ).hexdigest()


def test_public_mail_apply_dispatches_send_message_with_sender_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        sender_handle=_sender_handle(),
        script_runner=_sender_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        sender_handle=_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_sender_dispatch_runner(_send_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["sender_selection_confirmed"] is True
    assert result["read_back"]["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(result, sort_keys=True)


def test_public_mail_apply_send_read_back_accepts_gmail_all_mail_with_sender_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        sender_handle=_sender_handle(),
        script_runner=_sender_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        sender_handle=_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_sender_dispatch_runner(_send_all_mail_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["mailbox_name"] == "All Mail"
    assert result["read_back"]["sender_selection_confirmed"] is True
    assert result["read_back"]["full_email_returned"] is False
    assert SENDER_ADDRESS not in json.dumps(result, sort_keys=True)


def test_find_matching_sent_content_retries_after_local_index_lag(monkeypatch) -> None:
    calls = []
    sleeps = []

    def fake_find_matching_sent_content(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return None
        return {"handle": "mail:message:v2:synthetic", "mailbox_name": "Sent Messages"}

    monkeypatch.setattr(mail_adapter, "_find_matching_sent_content", fake_find_matching_sent_content)
    monkeypatch.setattr(mail_adapter.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = mail_adapter._find_matching_sent_content_with_retry(
        "Synthetic outbound",
        "Synthetic outbound body.",
        db_path=Path("/tmp/nonexistent-mail.sqlite"),
        mail_root=Path("/tmp/nonexistent-mail-root"),
        excluded_handles=set(),
        attempts=3,
        retry_delay_seconds=0.01,
    )

    assert result == {"handle": "mail:message:v2:synthetic", "mailbox_name": "Sent Messages"}
    assert len(calls) == 2
    assert sleeps == [0.01]


def test_sent_read_back_matcher_accepts_mail_quote_prefixes() -> None:
    assert mail_adapter._is_sent_read_back_mailbox("Sent Messages") is True
    assert mail_adapter._is_sent_read_back_mailbox("[Gmail]/All Mail") is True
    assert mail_adapter._is_sent_read_back_mailbox("Inbox") is False
    assert mail_adapter._normalized_sent_content_matches(
        "> LAD-TEST-subject\n> Synthetic outbound body.",
        "LAD-TEST-subject\nSynthetic outbound body.",
    )
    assert mail_adapter._normalized_sent_content_startswith(
        "> Synthetic forward note.\n> forwarded body",
        "Synthetic forward note.",
    )


def test_public_mail_apply_dispatches_send_message_with_signature_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        signature_handle=_signature_handle(),
        script_runner=_signature_search_runner,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        signature_handle=_signature_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_signature_dispatch_runner(_send_runner(db, mail_root)),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["signature_selection_confirmed"] is True
    assert result["read_back"]["signature_body_returned"] is False
    assert result["read_back"]["signature_content_returned"] is False


def test_public_mail_apply_dispatches_send_message_with_template_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    template_state = tmp_path / "mail-templates.json"
    monkeypatch.setenv("LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE", str(template_state))
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    template = create_mail_template(
        "Outbound",
        "Synthetic outbound body.",
        subject="Synthetic outbound",
    )["result"]
    assert "body_sha256" not in template
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        template_handle=template["handle"],
    )
    assert "body_sha256" not in plan["preview"]["proposed"]["template_selection"]
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        template_handle=template["handle"],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_send_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["template_selection_confirmed"] is True
    assert result["read_back"]["template_body_returned"] is False
    assert result["read_back"]["template_content_returned"] is False
    assert "body_sha256" not in json.dumps(result["read_back"], sort_keys=True)


def test_apply_send_message_is_partial_when_sent_readback_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_DELAY_SECONDS", 0)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-outbound-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_send_message_ignores_stale_matching_sent_copy(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_send_sent_copy(db, mail_root, rowid=STALE_SEND_ROWID)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_ATTEMPTS", 1)
    monkeypatch.setattr(mail_adapter, "MAIL_SENT_READ_BACK_DELAY_SECONDS", 0)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "synthetic-outbound-id",
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_send_message_confirms_new_sent_copy_when_stale_copy_exists(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_send_sent_copy(db, mail_root, rowid=STALE_SEND_ROWID)
    plan = plan_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    result = apply_mail_change(
        "send-message",
        to=["synthetic-recipient@example.invalid"],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=_send_runner(db, mail_root),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["sent_copy_confirmed"] is True
    assert result["read_back"]["handle"] != _handle(STALE_SEND_ROWID)


def test_mail_send_message_script_sends_without_saving_or_mutating_mailboxes() -> None:
    script = _mail_send_message_script(
        to=["synthetic-recipient@example.invalid"],
        cc=[],
        bcc=[],
        subject="Synthetic outbound",
        body_text="Synthetic outbound body.",
    )

    assert "send outboundMessage" in script
    assert "make new to recipient" in script
    assert "save " not in script.lower()
    assert "move " not in script.lower()
    assert "delete" not in script.lower()
    assert "empty" not in script.lower()
    assert "erase" not in script.lower()


def test_mail_reply_message_script_uses_exact_source_without_direct_recipients_or_save() -> None:
    script = _mail_reply_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="unread-001@example.test",
        body_text="Synthetic reply body.",
    )

    assert "messages of sourceBox whose message id is \"unread-001@example.test\"" in script
    assert "reply sourceMessage opening window false reply to all false" in script
    assert "set content of replyMessage to replyBody" in script
    assert "send replyMessage" in script
    lowered = script.lower()
    for forbidden in ("make new to recipient", "make new outgoing message", "save ", "move ", "delete", "erase", "empty"):
        assert forbidden not in lowered


def test_mail_reply_all_message_script_uses_public_reply_all_without_direct_recipients_or_save() -> None:
    script = _mail_reply_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="unread-001@example.test",
        body_text="Synthetic reply-all body.",
        reply_to_all=True,
    )

    assert "messages of sourceBox whose message id is \"unread-001@example.test\"" in script
    assert "reply sourceMessage opening window false reply to all true" in script
    assert "set content of replyMessage to replyBody" in script
    assert "send replyMessage" in script
    lowered = script.lower()
    for forbidden in ("make new to recipient", "make new outgoing message", "save ", "move ", "delete", "erase", "empty"):
        assert forbidden not in lowered


def test_mail_forward_message_script_uses_exact_source_recipients_and_no_attachment_mutation() -> None:
    script = _mail_forward_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="unread-001@example.test",
        to=["synthetic-forward@example.invalid"],
        cc=["synthetic-cc@example.invalid"],
        bcc=["synthetic-bcc@example.invalid"],
        subject="Fwd: Unread",
        body_text="Synthetic forward note.",
    )

    assert "messages of sourceBox whose message id is \"unread-001@example.test\"" in script
    assert "forward sourceMessage opening window false" in script
    assert "make new to recipient" in script
    assert "make new cc recipient" in script
    assert "make new bcc recipient" in script
    assert 'address:"synthetic-forward@example.invalid"' in script
    assert 'address:"synthetic-cc@example.invalid"' in script
    assert 'address:"synthetic-bcc@example.invalid"' in script
    assert "set subject of forwardMessage to forwardSubject" in script
    assert "set content of forwardMessage to forwardBody" in script
    assert "if savedAttachmentCount is not 0" in script
    assert "send forwardMessage" in script
    lowered = script.lower()
    for forbidden in ("make new outgoing message", "reply ", "save ", "move ", "delete", "erase", "empty"):
        assert forbidden not in lowered


def test_mail_forward_message_script_counts_source_attachments() -> None:
    script = _mail_forward_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="unread-001@example.test",
        to=["synthetic-forward@example.invalid"],
        cc=[],
        bcc=[],
        subject="Fwd: Unread",
        body_text="Synthetic forward note.",
        expected_source_part_count=2,
    )

    assert "forward sourceMessage opening window false" in script
    assert "if savedAttachmentCount is not 2" in script
    assert "attachment_count:" in script


def test_exact_source_scripts_support_nested_mailbox_paths() -> None:
    read_script = _mail_set_read_status_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="Parent/Inbox",
        message_id="unread-001@example.test",
        target_read=True,
    )
    flag_script = _mail_set_flagged_status_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="Parent/Inbox",
        message_id="unread-001@example.test",
        target_flagged=True,
    )
    reply_script = _mail_reply_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="Parent/Inbox",
        message_id="unread-001@example.test",
        body_text="Synthetic reply body.",
    )
    forward_script = _mail_forward_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="Parent/Inbox",
        message_id="unread-001@example.test",
        to=["synthetic-forward@example.invalid"],
        cc=[],
        bcc=[],
        subject="Fwd: Unread",
        body_text="Synthetic forward note.",
    )

    for script in (read_script, flag_script, reply_script, forward_script):
        assert 'mailbox "Inbox" of mailbox "Parent" of account id' in script
        assert 'mailbox "Parent/Inbox" of account id' not in script


def test_plan_mark_read_on_unread_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["operation"] == "mark_read"
    assert proposed["current_read"] is False
    assert proposed["target_read"] is True
    assert proposed["current_flagged"] is False
    assert proposed["already_satisfied"] is False
    assert plan["preview"]["approval"]["approval_fingerprint"]


def test_plan_flag_message_on_unflagged_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("flag_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["operation"] == "flag_message"
    assert proposed["current_read"] is False
    assert proposed["current_flagged"] is False
    assert proposed["target_flagged"] is True
    assert proposed["already_satisfied"] is False
    assert plan["preview"]["approval"]["approval_fingerprint"]


def test_plan_archive_message_on_exact_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("archive_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["operation"] == "archive_message"
    assert proposed["current_read"] is False
    assert proposed["current_flagged"] is False
    assert proposed["target_mailbox_kind"] == "archive"
    assert proposed["target_mailbox_ref"].startswith("mailbox:")
    assert proposed["target_mailbox_ref"] != proposed["mailbox_ref"]
    assert proposed["already_satisfied"] is False


def test_plan_trash_message_on_exact_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["operation"] == "trash_message"
    assert proposed["target_mailbox_kind"] == "trash"
    assert proposed["target_mailbox_ref"].startswith("mailbox:")
    assert proposed["target_mailbox_ref"] != proposed["mailbox_ref"]
    assert proposed["already_satisfied"] is False


def test_search_and_get_mail_mailboxes_return_exact_handles(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)

    result = search_mail_mailboxes("Projects", db_path=db)

    assert result["status"] == "ok"
    assert result["result_count"] == 2
    mailbox = result["results"][0]
    assert mailbox["handle"].startswith("mail:mailbox:v1:")
    assert mailbox["mailbox_name"] == "Projects"
    assert mailbox["mailbox_path"] == "Projects"
    assert mailbox["account_ref"].startswith("account:")
    assert mailbox["supports_move_target"] is True
    assert mailbox["raw_identifier_returned"] is False
    assert mailbox["account_identifier_returned"] is False

    detail = get_mail_mailbox(mailbox["handle"], db_path=db)
    assert detail["status"] == "ok"
    assert detail["result"]["handle"] == mailbox["handle"]


def test_get_mail_mailbox_rejects_message_handle(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)

    result = get_mail_mailbox(_handle(UNREAD_ROWID), db_path=db)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_mailbox_handle"


def test_plan_move_message_on_exact_message_and_mailbox(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][0]["handle"]

    plan = plan_mail_triage(
        "move_message",
        message_handle=_handle(UNREAD_ROWID),
        target_mailbox_handle=target_handle,
        db_path=db,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["operation"] == "move_message"
    assert proposed["target_mailbox_kind"] == "mailbox"
    assert proposed["target_mailbox_handle"] == target_handle
    assert proposed["target_mailbox_ref"].startswith("mailbox:")
    assert proposed["target_account_relation"] == "same_account"
    assert proposed["source_account_ref"].startswith("account:")
    assert proposed["target_account_ref"] == proposed["source_account_ref"]
    assert proposed["already_satisfied"] is False


def test_plan_move_message_requires_target_mailbox_handle(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("move_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    assert any(w["code"] == "missing_target_mailbox_handle" for w in plan["warnings"])


def test_plan_move_message_accepts_cross_account_exact_target(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][1]["handle"]

    plan = plan_mail_triage(
        "move_message",
        message_handle=_handle(UNREAD_ROWID),
        target_mailbox_handle=target_handle,
        db_path=db,
    )

    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["target_mailbox_handle"] == target_handle
    assert proposed["target_account_relation"] == "cross_account"
    assert proposed["source_account_ref"].startswith("account:")
    assert proposed["target_account_ref"].startswith("account:")
    assert proposed["target_account_ref"] != proposed["source_account_ref"]
    serialized = json.dumps(plan, sort_keys=True)
    assert "SECOND-ACCOUNT-ID" not in serialized


def test_plan_move_message_rejects_trash_target(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Trash", db_path=db)["results"][0]["handle"]

    plan = plan_mail_triage(
        "move_message",
        message_handle=_handle(UNREAD_ROWID),
        target_mailbox_handle=target_handle,
        db_path=db,
    )

    assert plan["status"] == "error"
    assert any(w["code"] == "unsupported_target_mailbox" for w in plan["warnings"])


def test_plan_move_message_rejects_junk_bulk_and_trash_subfolders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (8, ?)",
            ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Junk%20E-mail",),
        )
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (9, ?)",
            ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Bulk%20Mail",),
        )
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (10, ?)",
            ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Spam/Review",),
        )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    for query in ("Junk", "Bulk", "Review"):
        target_handle = search_mail_mailboxes(query, db_path=db)["results"][0]["handle"]
        plan = plan_mail_triage(
            "move_message",
            message_handle=_handle(UNREAD_ROWID),
            target_mailbox_handle=target_handle,
            db_path=db,
        )

        assert plan["status"] == "error"
        assert any(w["code"] == "unsupported_target_mailbox" for w in plan["warnings"])


def test_public_mail_plan_dispatches_mark_unread(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("mark-unread", message_handle=_handle(READ_ROWID), db_path=db)

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "mark_unread"
    assert plan["preview"]["proposed"]["current_read"] is True
    assert plan["preview"]["proposed"]["target_read"] is False


def test_public_mail_plan_accepts_bulk_mark_read(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "mark-read",
        message_handle=_handle(UNREAD_ROWID),
        message_handles=[_handle(READ_ROWID)],
        db_path=db,
    )

    assert plan["status"] == "ok"
    assert plan["result_count"] == 2
    proposed = plan["preview"]["proposed"]
    assert proposed["kind"] == "mail_bulk_triage"
    assert proposed["operation"] == "mark_read"
    assert proposed["message_count"] == 2
    assert proposed["already_satisfied_count"] == 1
    assert proposed["partial_apply_possible"] is True
    assert [item["message_handle"] for item in proposed["messages"]] == [
        _handle(UNREAD_ROWID),
        _handle(READ_ROWID),
    ]
    assert plan["preview"]["approval"]["approval_fingerprint"]


def test_bulk_plan_batches_handle_resolution_and_mail_tree_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(READ_ROWID)]
    handle_resolution_calls = 0
    mail_tree_scan_calls = 0
    real_handle_resolver = mail_adapter._resolve_mail_handle_rowids
    real_mail_tree_scan = mail_adapter._scan_mail_message_files

    def counted_handle_resolver(connection, selected_handles):
        nonlocal handle_resolution_calls
        handle_resolution_calls += 1
        assert selected_handles == handles
        return real_handle_resolver(connection, selected_handles)

    def counted_mail_tree_scan(root, *, only_rowid=None, only_rowids=None):
        nonlocal mail_tree_scan_calls
        mail_tree_scan_calls += 1
        assert root == mail_root
        assert only_rowid is None
        assert only_rowids == {UNREAD_ROWID, READ_ROWID}
        return real_mail_tree_scan(
            root,
            only_rowid=only_rowid,
            only_rowids=only_rowids,
        )

    monkeypatch.setattr(mail_adapter, "_resolve_mail_handle_rowids", counted_handle_resolver)
    monkeypatch.setattr(mail_adapter, "_scan_mail_message_files", counted_mail_tree_scan)

    plan = plan_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        db_path=db,
    )

    assert plan["status"] == "ok"
    assert handle_resolution_calls == 1
    assert mail_tree_scan_calls == 1


def test_bulk_apply_uses_batched_preflight_and_bound_row_readback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(READ_ROWID)]
    plan = plan_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    handle_resolution_calls = 0
    mail_tree_scan_calls = 0
    bound_row_readback_calls = 0
    real_handle_resolver = mail_adapter._resolve_mail_handle_rowids
    real_mail_tree_scan = mail_adapter._scan_mail_message_files
    real_bound_row_readback = mail_adapter._triage_read_back_by_rowid

    def counted_handle_resolver(connection, selected_handles):
        nonlocal handle_resolution_calls
        handle_resolution_calls += 1
        assert selected_handles == handles
        return real_handle_resolver(connection, selected_handles)

    def counted_mail_tree_scan(root, *, only_rowid=None, only_rowids=None):
        nonlocal mail_tree_scan_calls
        mail_tree_scan_calls += 1
        assert only_rowid is None
        assert only_rowids == {UNREAD_ROWID, READ_ROWID}
        return real_mail_tree_scan(
            root,
            only_rowid=only_rowid,
            only_rowids=only_rowids,
        )

    def counted_bound_row_readback(rowid, *, db_path):
        nonlocal bound_row_readback_calls
        bound_row_readback_calls += 1
        assert rowid in {UNREAD_ROWID, READ_ROWID}
        return real_bound_row_readback(rowid, db_path=db_path)

    monkeypatch.setattr(mail_adapter, "_resolve_mail_handle_rowids", counted_handle_resolver)
    monkeypatch.setattr(mail_adapter, "_scan_mail_message_files", counted_mail_tree_scan)
    monkeypatch.setattr(mail_adapter, "_triage_read_back_by_rowid", counted_bound_row_readback)
    monkeypatch.setattr(mail_adapter, "_triage_read_back", _fail_if_called)

    result = apply_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flipping_runner(db, UNREAD_ROWID, UNREAD_MSGID, True),
    )

    assert result["status"] == "ok"
    assert handle_resolution_calls == 2
    assert mail_tree_scan_calls == 2
    assert bound_row_readback_calls == 2


def test_public_mail_plan_search_triage_uses_capped_fts_handles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    def fake_search_mail_fts(query: str, **kwargs):
        assert query == "subscription"
        assert kwargs["after"] == "2026-01-01"
        assert kwargs["limit"] == 2
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "metadata"},
            "results": [
                {"handle": _handle(UNREAD_ROWID), "snippet": "synthetic"},
                {"handle": _handle(READ_ROWID), "snippet": "synthetic"},
            ],
            "result_count": 2,
            "next_cursor": "2",
            "warnings": [],
        }

    monkeypatch.setattr(mail_adapter, "search_mail_fts", fake_search_mail_fts)

    plan = plan_mail_search_triage(
        "mark-read",
        "subscription",
        after="2026-01-01",
        limit=2,
        db_path=db,
        mail_root=mail_root,
    )

    assert plan["status"] == "ok"
    assert plan["result_count"] == 2
    assert plan["preview"]["proposed"]["kind"] == "mail_bulk_triage"
    assert [item["message_handle"] for item in plan["preview"]["proposed"]["messages"]] == [
        _handle(UNREAD_ROWID),
        _handle(READ_ROWID),
    ]
    selection = plan["preview"]["query_result_selection"]
    assert selection["search_source"] == "fts"
    assert selection["selected_result_count"] == 2
    assert selection["next_cursor"] == "2"
    assert selection["raw_query_returned"] is False
    assert plan["preview"]["approval"]["approval_fingerprint"]


def test_public_mail_plan_search_triage_accepts_single_fts_handle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    def fake_search_mail_fts(query: str, **kwargs):
        assert query == "subscription"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": True, "output_tier": "metadata"},
            "results": [{"handle": _handle(UNREAD_ROWID), "snippet": "synthetic"}],
            "result_count": 1,
            "next_cursor": None,
            "warnings": [],
        }

    monkeypatch.setattr(mail_adapter, "search_mail_fts", fake_search_mail_fts)

    plan = plan_mail_search_triage(
        "mark-read",
        "subscription",
        after="2026-01-01",
        db_path=db,
        mail_root=mail_root,
    )

    assert plan["status"] == "ok"
    assert plan["result_count"] == 1
    assert plan["preview"]["proposed"]["kind"] == "mail_triage"
    assert plan["preview"]["proposed"]["message_handle"] == _handle(UNREAD_ROWID)
    selection = plan["preview"]["query_result_selection"]
    assert selection["selected_result_count"] == 1
    assert selection["raw_query_returned"] is False


def test_public_mail_plan_search_triage_rejects_unsupported_source() -> None:
    plan = plan_mail_search_triage(
        "mark-read",
        "subscription",
        search_source="subject",
        after="2026-01-01",
    )

    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "unsupported_search_source"


def test_plan_mailbox_create_requires_synthetic_name() -> None:
    plan = plan_mail_mailbox_change(
        "create-mailbox",
        sender_handle=_sender_handle(),
        mailbox_name="Projects",
        script_runner=_sender_search_runner,
    )

    assert plan["status"] == "error"
    assert any(w["code"] == "non_synthetic_mailbox_name" for w in plan["warnings"])


def test_apply_mailbox_create_uses_exact_sender_account_without_returning_raw_id(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    plan = plan_mail_mailbox_change(
        "create-mailbox",
        sender_handle=_sender_handle(),
        mailbox_name="LAD-TEST-created",
        db_path=db,
        script_runner=_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _sender_search_runner(script, timeout)
        assert "make new mailbox at targetAccount" in script
        assert "LAD-TEST-created" in script
        return "mailbox_name:LAD-TEST-created\nmessage_count:0"

    result = apply_mail_mailbox_change(
        "create-mailbox",
        sender_handle=_sender_handle(),
        mailbox_name="LAD-TEST-created",
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["mailbox_name"] == "LAD-TEST-created"
    assert result["read_back"]["empty_mailbox_confirmed"] is True
    serialized = json.dumps(result, sort_keys=True)
    assert SENDER_ACCOUNT_ID not in serialized


def test_apply_mailbox_rename_and_delete_require_empty_lad_test_mailbox(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    _add_synthetic_mailbox(db)
    handle = search_mail_mailboxes("LAD-TEST-old", db_path=db)["results"][0]["handle"]
    rename_plan = plan_mail_mailbox_change(
        "rename-mailbox",
        mailbox_handle=handle,
        new_mailbox_name="LAD-TEST-new",
        db_path=db,
    )
    rename_token = APPROVAL_TOKEN_PREFIX + rename_plan["preview"]["approval"]["approval_fingerprint"]

    def rename_runner(script: str, timeout: float) -> str:
        assert "set name of sourceBox to newMailboxNameValue" in script
        assert "LAD-TEST-old" in script
        assert "LAD-TEST-new" in script
        with sqlite3.connect(db) as connection:
            connection.execute(
                "UPDATE mailboxes SET url = ? WHERE url = ?",
                ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/LAD-TEST-new", SYNTHETIC_MAILBOX_URL),
            )
        return "mailbox_name:LAD-TEST-new\nmessage_count:0"

    renamed = apply_mail_mailbox_change(
        "rename-mailbox",
        mailbox_handle=handle,
        new_mailbox_name="LAD-TEST-new",
        approval_token=rename_token,
        confirm_apply=True,
        db_path=db,
        script_runner=rename_runner,
    )

    assert renamed["status"] == "ok"
    assert renamed["read_back"]["mailbox_name"] == "LAD-TEST-new"

    new_handle = search_mail_mailboxes("LAD-TEST-new", db_path=db)["results"][0]["handle"]
    delete_plan = plan_mail_mailbox_change("delete-mailbox", mailbox_handle=new_handle, db_path=db)
    delete_token = APPROVAL_TOKEN_PREFIX + delete_plan["preview"]["approval"]["approval_fingerprint"]

    def delete_runner(script: str, timeout: float) -> str:
        assert "delete sourceBox" in script
        assert "LAD-TEST-new" in script
        with sqlite3.connect(db) as connection:
            connection.execute("DELETE FROM mailboxes WHERE url = ?", ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/LAD-TEST-new",))
        return "mailbox_name:LAD-TEST-new\nmessage_count:0\nverified_absent:true"

    deleted = apply_mail_mailbox_change(
        "delete-mailbox",
        mailbox_handle=new_handle,
        approval_token=delete_token,
        confirm_apply=True,
        db_path=db,
        script_runner=delete_runner,
    )

    assert deleted["status"] == "ok"
    assert deleted["read_back"]["verified_absent"] is True


def test_mailbox_management_scripts_use_public_mailbox_verbs() -> None:
    create_script = _mail_create_mailbox_script(account_id=SENDER_ACCOUNT_ID, mailbox_name="LAD-TEST-created")
    rename_script = _mail_rename_mailbox_script(
        account_id=SENDER_ACCOUNT_ID,
        old_mailbox_name="LAD-TEST-created",
        new_mailbox_name="LAD-TEST-renamed",
    )
    delete_script = _mail_delete_mailbox_script(account_id=SENDER_ACCOUNT_ID, mailbox_name="LAD-TEST-renamed")

    assert "make new mailbox at targetAccount" in create_script
    assert "set name of sourceBox" in rename_script
    assert "delete sourceBox" in delete_script
    assert "account id" in create_script


def test_plan_cleanup_refuses_non_synthetic_trash_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root, include_real=True)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(REAL_TRASH_ROWID), db_path=db)

    assert plan["status"] == "error"
    assert any(w["code"] == "non_synthetic_subject" for w in plan["warnings"])


def test_apply_cleanup_permanent_delete_requires_absence_read_back(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID_2,))
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "cleanup_target_not_unique" in script
        assert "set cleanupMessages to messages of cleanupBox" not in script
        assert SYNTHETIC_TRASH_MSGID in script
        assert "delete cleanupMessage" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID,))
        return "deleted_count:1\nverified_absent:true"

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["permanently_deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["warnings"] == []
    assert calls == ["background", "delete"]


def test_apply_cleanup_retries_absence_read_back_after_index_lag(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID_2,))
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS", 2)
    monkeypatch.setattr(mail_adapter, "MAIL_CLEANUP_ABSENCE_READ_BACK_DELAY_SECONDS", 0)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    original_present = mail_adapter._message_present_in_cleanup_mailbox
    read_back_calls = 0

    def delayed_absence(connection, *, target, message_id: str, subject: str, mail_root: Path) -> bool:
        nonlocal read_back_calls
        read_back_calls += 1
        if read_back_calls == 1:
            return True
        return original_present(
            connection,
            target=target,
            message_id=message_id,
            subject=subject,
            mail_root=mail_root,
        )

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            return "background_idle:true"
        assert "cleanup_target_not_unique" in script
        assert "set cleanupMessages to messages of cleanupBox" not in script
        assert SYNTHETIC_TRASH_MSGID in script
        assert "delete cleanupMessage" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID,))
        return "deleted_count:1\nverified_absent:true"

    monkeypatch.setattr(mail_adapter, "_message_present_in_cleanup_mailbox", delayed_absence)
    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert read_back_calls == 2
    assert result["read_back"]["verified_absent"] is True


def test_apply_cleanup_treats_live_original_row_as_still_present_without_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID_2,))
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS", 1)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            return "background_idle:true"
        assert "cleanup_target_not_unique" in script
        assert "set cleanupMessages to messages of cleanupBox" not in script
        assert "delete cleanupMessage" in script
        (mail_root / "TestAccount" / "Messages" / f"{SYNTHETIC_TRASH_ROWID}.emlx").unlink()
        return "deleted_count:1\nverified_absent:true"

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["verified_absent"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["absence_read_back_unavailable"]


def test_apply_cleanup_succeeds_when_same_message_id_remains_outside_cleanup_mailbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID_2,))
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, read, flagged) VALUES (?, ?, ?, ?, 1, 0)",
            (33, 30, 1, "synthetic-trash-duplicate-db"),
        )
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / "33.emlx",
        f"Message-ID: <{SYNTHETIC_TRASH_MSGID}>\nSubject: LAD-TEST-trash-one\n\nSynthetic duplicate body.\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    monkeypatch.setattr(mail_adapter, "MAIL_CLEANUP_ABSENCE_READ_BACK_ATTEMPTS", 1)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            return "background_idle:true"
        assert "cleanup_target_not_unique" in script
        assert "set cleanupMessages to messages of cleanupBox" not in script
        assert SYNTHETIC_TRASH_MSGID in script
        assert "delete cleanupMessage" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID,))
        return "deleted_count:1\nverified_absent:true"

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True


def test_plan_empty_trash_refuses_mixed_real_messages(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root, include_real=True)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )

    assert plan["status"] == "error"
    assert any(w["code"] == "non_synthetic_mailbox_contents" for w in plan["warnings"])


def test_apply_empty_trash_deletes_only_planned_synthetic_messages(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "background_idle:true" in script:
            return "background_idle:true"
        assert "delete cleanupMessage" in script
        assert "LAD-TEST-" in script
        with sqlite3.connect(db) as connection:
            connection.execute(
                "UPDATE messages SET deleted = 1 WHERE ROWID IN (?, ?)",
                (SYNTHETIC_TRASH_ROWID, SYNTHETIC_TRASH_ROWID_2),
            )
        return "deleted_count:2\nverified_absent:true"

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["message_count"] == 2
    assert result["read_back"]["permanently_deleted"] is True


def test_apply_empty_trash_returns_partial_when_public_delete_leaves_messages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "delete cleanupMessage" in script:
            calls.append("delete")
            assert "LAD-TEST-" in script
            assert "cleanup_target_set_changed" in script
            assert SYNTHETIC_TRASH_MSGID in script
            assert SYNTHETIC_TRASH_MSGID_2 in script
            return "deleted_count:2\nverified_absent:false"
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        raise AssertionError(script)

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["read_back"]["message_count"] == 2
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["verified_absent"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["absence_read_back_unavailable"]
    assert calls == ["background", "delete"]


def test_apply_empty_trash_refuses_when_script_side_target_set_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "cleanup_target_set_changed" in script
        assert SYNTHETIC_TRASH_MSGID in script
        assert SYNTHETIC_TRASH_MSGID_2 in script
        raise mail_adapter.MailAutomationError("cleanup_target_set_changed")

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["write_error"]
    assert calls == ["background", "delete"]


def test_apply_empty_trash_refuses_when_script_side_target_state_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "cleanup_target_state_changed" in script
        assert "expectedSubjects" in script
        assert "expectedReadStatuses" in script
        assert "expectedFlaggedStatuses" in script
        raise mail_adapter.MailAutomationError("cleanup_target_state_changed")

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["write_error"]
    assert calls == ["background", "delete"]


def test_apply_empty_trash_refuses_while_mail_background_busy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "delete cleanupMessage" in script:
            calls.append("delete")
            return "deleted_count:2\nverified_absent:false"
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:false"
        calls.append("unexpected")
        raise AssertionError(script)

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "degraded"
    assert result["mutation_applied"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["mail_background_activity_timeout"]
    assert calls == ["background"]


def test_apply_permanent_delete_with_extra_synthetic_messages_uses_exact_delete_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "delete cleanupMessage" in script
        assert SYNTHETIC_TRASH_MSGID in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID,))
        return "deleted_count:1\nverified_absent:true"

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert calls == ["background", "delete"]
    with sqlite3.connect(db) as connection:
        remaining = connection.execute(
            "SELECT deleted FROM messages WHERE ROWID = ?",
            (SYNTHETIC_TRASH_ROWID_2,),
        ).fetchone()
    assert remaining is not None and remaining[0] == 0


def test_apply_permanent_delete_reports_partial_when_extra_synthetic_message_remains(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "delete cleanupMessage" in script
        assert SYNTHETIC_TRASH_MSGID in script
        return "deleted_count:1\nverified_absent:false"

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert [warning["code"] for warning in result["warnings"]] == ["absence_read_back_unavailable"]
    assert calls == ["background", "delete"]


def test_apply_permanent_delete_reports_partial_when_script_errors_after_delete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID_2,))
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "cleanup_target_state_changed" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (SYNTHETIC_TRASH_ROWID,))
        raise mail_adapter.MailAutomationError("mail_error_after_delete")

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert [warning["code"] for warning in result["warnings"]] == ["write_error"]
    assert calls == ["background", "delete"]


def test_apply_permanent_delete_reports_no_mutation_when_osascript_launch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup("permanent-delete-message", message_handle=_handle(SYNTHETIC_TRASH_ROWID), db_path=db)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        raise OSError("osascript unavailable")

    result = apply_mail_cleanup(
        "permanent-delete-message",
        message_handle=_handle(SYNTHETIC_TRASH_ROWID),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["write_error"]
    assert "read_back" not in result
    assert calls == ["background", "delete"]


def test_apply_empty_trash_reports_partial_when_script_times_out_after_delete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _add_cleanup_messages(db, mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    plan = plan_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        db_path=db,
        mail_root=mail_root,
        script_runner=_cleanup_sender_search_runner,
    )
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    calls: list[str] = []

    def runner(script: str, timeout: float) -> str:
        if "repeat with mailAccount in accounts" in script:
            return _cleanup_sender_search_runner(script, timeout)
        if "background_idle:true" in script:
            calls.append("background")
            return "background_idle:true"
        calls.append("delete")
        assert "cleanup_target_state_changed" in script
        with sqlite3.connect(db) as connection:
            connection.execute(
                "UPDATE messages SET deleted = 1 WHERE ROWID IN (?, ?)",
                (SYNTHETIC_TRASH_ROWID, SYNTHETIC_TRASH_ROWID_2),
            )
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=timeout)

    result = apply_mail_cleanup(
        "empty-trash",
        sender_handle=_cleanup_sender_handle(),
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=runner,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["read_back"]["message_count"] == 2
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert [warning["code"] for warning in result["warnings"]] == ["automation_timeout"]
    assert calls == ["background", "delete"]


def test_cleanup_scripts_recheck_synthetic_subjects() -> None:
    delete_script = _mail_permanent_delete_message_script(
        account_id=SENDER_ACCOUNT_ID,
        mailbox_name="Trash",
        target={
            "message_id": SYNTHETIC_TRASH_MSGID,
            "subject": "LAD-TEST-trash-one",
            "read": True,
            "flagged": False,
        },
    )
    empty_script = _mail_empty_special_mailbox_script(
        account_id=SENDER_ACCOUNT_ID,
        mailbox_name="Trash",
        targets=[
            {
                "message_id": SYNTHETIC_TRASH_MSGID,
                "subject": "LAD-TEST-trash-one",
                "read": True,
                "flagged": False,
            },
            {
                "message_id": SYNTHETIC_TRASH_MSGID_2,
                "subject": "LAD-TEST-trash-two",
                "read": True,
                "flagged": False,
            },
        ],
    )

    assert "does not start with \"LAD-TEST-\"" in delete_script
    assert "delete cleanupMessage" in delete_script
    assert "delete cleanupMessage" in empty_script
    assert "delete cleanupMessages" not in empty_script
    assert "cleanup_target_set_changed" in empty_script
    assert "cleanup_target_state_changed" in delete_script
    assert "cleanup_target_state_changed" in empty_script
    assert "LAD-TEST-trash-one" in delete_script
    assert "expectedSubjects" in empty_script
    assert "expectedReadStatuses" in empty_script
    assert "expectedFlaggedStatuses" in empty_script
    assert SYNTHETIC_TRASH_MSGID in empty_script
    assert SYNTHETIC_TRASH_MSGID_2 in empty_script


def test_public_mail_plan_rejects_duplicate_bulk_handle(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change(
        "mark-read",
        message_handle=_handle(UNREAD_ROWID),
        message_handles=[_handle(UNREAD_ROWID)],
        db_path=db,
    )

    assert plan["status"] == "error"
    assert any(w["code"] == "duplicate_message_handle" for w in plan["warnings"])


def test_public_mail_plan_dispatches_unflag_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET flagged = 1 WHERE ROWID = ?", (READ_ROWID,))
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("unflag-message", message_handle=_handle(READ_ROWID), db_path=db)

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "unflag_message"
    assert plan["preview"]["proposed"]["current_flagged"] is True
    assert plan["preview"]["proposed"]["target_flagged"] is False


def test_public_mail_plan_dispatches_archive_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("archive-message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "archive_message"
    assert plan["preview"]["proposed"]["target_mailbox_kind"] == "archive"


def test_public_mail_plan_dispatches_trash_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("trash-message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "trash_message"
    assert plan["preview"]["proposed"]["target_mailbox_kind"] == "trash"


def test_public_mail_plan_dispatches_move_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][0]["handle"]

    plan = plan_mail_change(
        "move-message",
        message_handle=_handle(UNREAD_ROWID),
        target_mailbox_handle=target_handle,
        db_path=db,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "move_message"
    assert plan["preview"]["proposed"]["target_mailbox_handle"] == target_handle


def test_public_mail_apply_dispatches_mark_unread(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(READ_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("mark_unread", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "mark-unread",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flipping_runner(db, READ_ROWID, READ_MSGID, False),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["read"] is False


def test_public_mail_apply_dispatches_bulk_mark_read(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(READ_ROWID)]

    plan = plan_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flipping_runner(db, UNREAD_ROWID, UNREAD_MSGID, True),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["kind"] == "mail_bulk_triage"
    assert result["read_back"]["applied_count"] == 1
    assert result["read_back"]["already_satisfied_count"] == 1
    assert result["read_back"]["failed_count"] == 0
    assert [item["status"] for item in result["read_back"]["results"]] == ["ok", "already_satisfied"]


def test_public_mail_apply_bulk_refuses_stale_preflight_before_mutating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(READ_ROWID)]

    plan = plan_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    original_resolver = mail_adapter._resolve_triage_target
    call_count = 0

    def drift_after_apply_plan(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = original_resolver(*args, **kwargs)
        if call_count == 2:
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE messages SET read = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
        return result

    monkeypatch.setattr(mail_adapter, "_resolve_triage_target", drift_after_apply_plan)

    result = apply_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1]],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_fail_if_called,
    )

    assert call_count == 4
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert any(w["code"] == "stale_message_state" for w in result["warnings"])


def test_public_mail_apply_bulk_reports_partial_after_mid_batch_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    second_rowid = 21
    second_msgid = "bulk-second-001@example.test"
    third_rowid = 22
    third_msgid = "bulk-third-001@example.test"
    with sqlite3.connect(db) as connection:
        connection.executemany(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, read) VALUES (?,1,1,?,0)",
            [
                (second_rowid, "bulk-second-hash"),
                (third_rowid, "bulk-third-hash"),
            ],
        )
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{second_rowid}.emlx",
        f"Message-ID: <{second_msgid}>\nSubject: Bulk second\n\nSynthetic bulk body.\n",
    )
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{third_rowid}.emlx",
        f"Message-ID: <{third_msgid}>\nSubject: Bulk third\n\nSynthetic bulk body.\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(second_rowid), _handle(third_rowid)]

    plan = plan_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1], handles[2]],
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    call_count = 0

    def runner(script: str, timeout: float) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert UNREAD_MSGID in script
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE messages SET read = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
            return "ok"
        assert second_msgid in script
        assert third_msgid not in script
        raise mail_adapter.MailAutomationError()

    result = apply_mail_change(
        "mark-read",
        message_handle=handles[0],
        message_handles=[handles[1], handles[2]],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=runner,
    )

    assert call_count == 2
    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["result_count"] == 3
    assert result["read_back"]["message_count"] == 3
    assert result["read_back"]["applied_count"] == 1
    assert result["read_back"]["failed_count"] == 1
    assert result["read_back"]["not_attempted_count"] == 1
    assert result["read_back"]["results"][1]["warning_code"] == "write_error"
    assert result["read_back"]["results"][2]["status"] == "not_attempted"
    assert result["read_back"]["results"][2]["message_handle"] == handles[2]


def test_public_mail_apply_dispatches_flag_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("flag-message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "flag-message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flagging_runner(db, UNREAD_ROWID, UNREAD_MSGID, True),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["flagged"] is True


def test_public_mail_apply_dispatches_archive_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("archive-message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "archive-message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_archive_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_public_mail_apply_dispatches_trash_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_change("trash-message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "trash-message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_trash_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_public_mail_apply_dispatches_move_message(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][0]["handle"]

    plan = plan_mail_change(
        "move-message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_change(
        "move-message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_move_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_public_mail_plan_rejects_message_handle_for_create_draft() -> None:
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic",
        body_text="Body",
        message_handle=_handle(UNREAD_ROWID),
    )

    assert plan["status"] == "error"
    assert any(w["code"] == "unexpected_message_handle" for w in plan["warnings"])


def test_plan_rejects_invalid_operation(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    plan = plan_mail_triage("delete", message_handle=_handle(UNREAD_ROWID), db_path=db)
    assert plan["status"] == "error"
    assert any(w["code"] == "invalid_operation" for w in plan["warnings"])


def test_plan_archive_message_fails_when_archive_mailbox_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM mailboxes WHERE ROWID = 2")
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("archive_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    assert any(w["code"] == "archive_mailbox_unavailable" for w in plan["warnings"])


def test_plan_trash_message_fails_when_trash_mailbox_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM mailboxes WHERE ROWID = 3")
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    assert any(w["code"] == "trash_mailbox_unavailable" for w in plan["warnings"])


def test_plan_trash_message_fails_when_trash_mailbox_is_ambiguous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (4, ?)",
            ("imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Bin",),
        )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    assert any(w["code"] == "trash_mailbox_ambiguous" for w in plan["warnings"])


def test_plan_trash_message_prefers_provider_trash_over_deleted_messages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM mailboxes WHERE ROWID = 3")
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (?, ?)",
            (3, "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/%5BGmail%5D/Trash"),
        )
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url) VALUES (?, ?)",
            (4, "imap://18E15B19-108F-4FD4-AE58-77F4468D00C1/Deleted%20Messages"),
        )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["target_mailbox_kind"] == "trash"


def test_plan_rejects_invalid_handle(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    plan = plan_mail_triage("mark_read", message_handle="not-a-handle", db_path=db)
    assert plan["status"] == "error"
    assert any(w["code"] == "invalid_message_handle" for w in plan["warnings"])


def test_plan_message_not_found(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    plan = plan_mail_triage("mark_read", message_handle=_handle(999), db_path=db)
    assert plan["status"] == "error"
    assert any(w["code"] == "message_not_found" for w in plan["warnings"])


def test_plan_fails_closed_when_rfc_message_id_file_is_unavailable(tmp_path: Path) -> None:
    db = tmp_path / "mail.sqlite"
    _make_mail_db(db)
    plan = plan_mail_triage("mark_read", message_handle=_handle(UNREAD_ROWID), db_path=db)
    assert plan["status"] == "error"
    assert any(w["code"] == "message_identity_unavailable" for w in plan["warnings"])


def test_apply_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    result = apply_mail_triage(
        "mark_read",
        message_handle=_handle(UNREAD_ROWID),
        approval_token="anything",
        confirm_apply=False,
        db_path=db,
    )
    assert result["mutation_applied"] is False
    assert any(w["code"] == "missing_apply_confirmation" for w in result["warnings"])


def test_apply_rejects_bad_token(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    result = apply_mail_triage(
        "mark_read",
        message_handle=_handle(UNREAD_ROWID),
        approval_token=f"{APPROVAL_TOKEN_PREFIX}wrong",
        confirm_apply=True,
        db_path=db,
    )
    assert result["mutation_applied"] is False
    assert any(w["code"] == "invalid_approval_token" for w in result["warnings"])


def test_apply_fails_closed_when_rfc_message_id_disappears_after_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    handle = _handle(UNREAD_ROWID)
    plan = plan_mail_triage("mark_read", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    original_resolver = mail_adapter._resolve_triage_target
    call_count = 0

    def disappearing_identity(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return original_resolver(*args, **kwargs)
        raise mail_adapter.MailTriageIdentityUnavailable()

    def explode(script: str, timeout: float) -> str:
        raise AssertionError("automation must not run without a fresh message identity")

    monkeypatch.setattr(mail_adapter, "_resolve_triage_target", disappearing_identity)

    result = apply_mail_triage(
        "mark_read",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=explode,
    )

    assert call_count == 2
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert any(w["code"] == "message_identity_unavailable" for w in result["warnings"])


def test_apply_mark_read_success_with_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_triage(
        "mark_read",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flipping_runner(db, UNREAD_ROWID, UNREAD_MSGID, True),
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["read"] is True


def test_apply_flag_message_success_with_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("flag_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_triage(
        "flag_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_flagging_runner(db, UNREAD_ROWID, UNREAD_MSGID, True),
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["flagged"] is True
    assert result["read_back"]["read"] is False


def test_apply_archive_message_success_with_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("archive_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_triage(
        "archive_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_archive_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_trash_message_success_with_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_triage(
        "trash_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_trash_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_move_message_success_with_readback(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][0]["handle"]

    plan = plan_mail_triage(
        "move_message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        db_path=db,
    )
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"
    result = apply_mail_triage(
        "move_message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=_move_runner(db, UNREAD_ROWID, UNREAD_MSGID),
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_move_message_supports_cross_account_exact_target(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    target_handle = search_mail_mailboxes("Projects", db_path=db)["results"][1]["handle"]

    plan = plan_mail_triage(
        "move_message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        db_path=db,
    )
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["target_account_relation"] == "cross_account"
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert 'mailbox "iCloud test mailbox" of account id "18E15B19-108F-4FD4-AE58-77F4468D00C1"' in script
        assert 'mailbox "Projects" of account id "SECOND-ACCOUNT-ID"' in script
        assert "move (first item of triageMatches) to targetBox" in script
        lowered = script.lower()
        for forbidden in ("send ", "delete", "erase", "empty", "trash", "remove"):
            assert forbidden not in lowered
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET mailbox = 7 WHERE ROWID = ?", (UNREAD_ROWID,))
        return "ok"

    result = apply_mail_triage(
        "move_message",
        message_handle=handle,
        target_mailbox_handle=target_handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=runner,
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_archive_message_confirms_readback_after_row_rekey(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{ARCHIVED_ROWID}.emlx",
        f"Message-ID: <{UNREAD_MSGID}>\nSubject: Unread\n\nSynthetic archived body.\n",
    )
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("archive_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def rekeying_runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "move (first item of triageMatches) to archiveBox" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
            connection.execute(
                "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) VALUES (?,1,2,?,?,0)",
                (ARCHIVED_ROWID, "-3543720719788426468", UNREAD_ROWID),
            )
        return "ok"

    result = apply_mail_triage(
        "archive_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=rekeying_runner,
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"] == _handle(ARCHIVED_ROWID)
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_archive_rekey_readback_uses_bounded_message_id_sql_without_mail_tree_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) "
            "VALUES (?, 1, 2, ?, ?, 0)",
            (ARCHIVED_ROWID, "archive-rekey", UNREAD_ROWID),
        )
        # Same RFC identity in another mailbox must not make Archive ambiguous.
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) "
            "VALUES (?, 1, 6, ?, ?, 0)",
            (22, "other-mailbox-copy", UNREAD_ROWID),
        )
        for offset in range(200):
            global_id = 1000 + offset
            rowid = 2000 + offset
            connection.execute(
                "INSERT INTO message_global_data (ROWID, message_id_header) VALUES (?, ?)",
                (global_id, f"<decoy-{offset}@example.test>"),
            )
            connection.execute(
                "INSERT INTO messages "
                "(ROWID, subject, mailbox, message_id, global_message_id, read) "
                "VALUES (?, 1, 2, ?, ?, 0)",
                (rowid, f"decoy-{offset}", global_id),
            )

    monkeypatch.setattr(
        mail_adapter,
        "_find_message_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("re-key read-back must not scan the Mail tree")
        ),
    )

    read_back = mail_adapter._triage_read_back_by_message_id(
        message_id=f"<{UNREAD_MSGID}>",
        target_mailbox_url=ARCHIVE_MAILBOX_URL,
        db_path=db,
        mail_root=mail_root,
    )

    assert read_back is not None
    assert read_back["handle"] == _handle(ARCHIVED_ROWID)
    assert read_back["mailbox_ref"] == mail_adapter._mailbox_metadata(
        ARCHIVE_MAILBOX_URL
    )["mailbox_ref"]
    assert (
        mail_adapter._triage_read_back_by_message_id(
            message_id=UNREAD_MSGID,
            target_mailbox_url=TRASH_MAILBOX_URL,
            db_path=db,
            mail_root=mail_root,
        )
        is None
    )

    source = inspect.getsource(mail_adapter._triage_read_back_by_message_id)
    assert "JOIN message_global_data" in source
    assert "mgd.message_id_header" in source
    assert "LIMIT 2" in source
    assert "_find_message_file" not in source

    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) "
            "VALUES (?, 1, 2, ?, ?, 0)",
            (23, "duplicate-archive-copy", UNREAD_ROWID),
        )
    assert (
        mail_adapter._triage_read_back_by_message_id(
            message_id=UNREAD_MSGID,
            target_mailbox_url=ARCHIVE_MAILBOX_URL,
            db_path=db,
            mail_root=mail_root,
        )
        is None
    )


def test_bulk_archive_rekey_readback_never_scans_target_mailbox_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)
    handles = [_handle(UNREAD_ROWID), _handle(READ_ROWID)]
    plan = plan_mail_change(
        "archive-message",
        message_handle=handles[0],
        message_handles=[handles[1]],
        db_path=db,
        mail_root=mail_root,
    )
    assert plan["status"] == "ok"
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    with sqlite3.connect(db) as connection:
        for offset in range(200):
            global_id = 3000 + offset
            rowid = 4000 + offset
            connection.execute(
                "INSERT INTO message_global_data (ROWID, message_id_header) VALUES (?, ?)",
                (global_id, f"<bulk-decoy-{offset}@example.test>"),
            )
            connection.execute(
                "INSERT INTO messages "
                "(ROWID, subject, mailbox, message_id, global_message_id, read) "
                "VALUES (?, 1, 2, ?, ?, 0)",
                (rowid, f"bulk-decoy-{offset}", global_id),
            )

    real_find_message_file = mail_adapter._find_message_file
    file_lookup_rowids: list[int] = []

    def guarded_find_message_file(root, rowid, *, index=None):
        file_lookup_rowids.append(rowid)
        if rowid not in {UNREAD_ROWID, READ_ROWID}:
            raise AssertionError("bulk read-back scanned a target mailbox message file")
        return real_find_message_file(root, rowid, index=index)

    monkeypatch.setattr(mail_adapter, "_find_message_file", guarded_find_message_file)
    rekeys = [
        (UNREAD_ROWID, ARCHIVED_ROWID, 1, UNREAD_ROWID, 0, UNREAD_MSGID),
        (READ_ROWID, 21, 2, READ_ROWID, 1, READ_MSGID),
    ]

    def rekeying_runner(script: str, timeout: float) -> str:
        source_rowid, target_rowid, subject_id, global_id, read, expected_id = rekeys.pop(0)
        assert timeout == 10.0
        assert expected_id in script
        assert "move (first item of triageMatches) to archiveBox" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (source_rowid,))
            connection.execute(
                "INSERT INTO messages "
                "(ROWID, subject, mailbox, message_id, global_message_id, read) "
                "VALUES (?, ?, 2, ?, ?, ?)",
                (target_rowid, subject_id, f"rekey-{target_rowid}", global_id, read),
            )
        return "ok"

    result = apply_mail_change(
        "archive-message",
        message_handle=handles[0],
        message_handles=[handles[1]],
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        mail_root=mail_root,
        script_runner=rekeying_runner,
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["kind"] == "mail_bulk_triage"
    assert result["read_back"]["applied_count"] == 2
    assert result["read_back"]["failed_count"] == 0
    assert rekeys == []
    assert set(file_lookup_rowids) <= {UNREAD_ROWID, READ_ROWID}


def test_apply_trash_message_confirms_readback_after_row_rekey(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{TRASHED_ROWID}.emlx",
        f"Message-ID: <{UNREAD_MSGID}>\nSubject: Unread\n\nSynthetic trashed body.\n",
    )
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("trash_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def rekeying_runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        assert "move (first item of triageMatches) to trashBox" in script
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
            connection.execute(
                "INSERT INTO messages (ROWID, subject, mailbox, message_id, global_message_id, read) VALUES (?,1,3,?,?,0)",
                (TRASHED_ROWID, "-3543720719788426468", UNREAD_ROWID),
            )
        return "ok"

    result = apply_mail_triage(
        "trash_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=rekeying_runner,
    )

    assert result["status"] == "ok", result
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"] == _handle(TRASHED_ROWID)
    assert result["read_back"]["mailbox_ref"] == plan["preview"]["proposed"]["target_mailbox_ref"]


def test_apply_archive_message_refuses_stale_mailbox_state(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("archive_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    original_resolver = mail_adapter._resolve_triage_target
    call_count = 0

    def drift_after_apply_plan(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = original_resolver(*args, **kwargs)
        if call_count == 1:
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE messages SET read = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
        return result

    monkeypatch.setattr(mail_adapter, "_resolve_triage_target", drift_after_apply_plan)

    def explode(script: str, timeout: float) -> str:
        raise AssertionError("automation must not run for stale message state")

    result = apply_mail_triage(
        "archive_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=explode,
    )

    assert call_count == 2
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert any(w["code"] == "stale_message_state" for w in result["warnings"])


def test_apply_already_satisfied_skips_automation(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    handle = _handle(READ_ROWID)  # already read
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def explode(script: str, timeout: float) -> str:  # must not be called
        raise AssertionError("automation must not run when already satisfied")

    result = apply_mail_triage(
        "mark_read",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=explode,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert any(w["code"] == "already_applied" for w in result["warnings"])


def test_apply_flag_already_satisfied_skips_automation(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _make_mail_files(mail_root)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE messages SET flagged = 1 WHERE ROWID = ?", (UNREAD_ROWID,))
    handle = _handle(UNREAD_ROWID)
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("flag_message", message_handle=handle, db_path=db)
    token = f"{APPROVAL_TOKEN_PREFIX}{plan['preview']['approval']['approval_fingerprint']}"

    def explode(script: str, timeout: float) -> str:
        raise AssertionError("automation must not run when already satisfied")

    result = apply_mail_triage(
        "flag_message",
        message_handle=handle,
        approval_token=token,
        confirm_apply=True,
        db_path=db,
        script_runner=explode,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["read_back"]["flagged"] is True
    assert any(w["code"] == "already_applied" for w in result["warnings"])


def test_message_id_header_helpers_are_bounded_and_fail_closed(tmp_path: Path) -> None:
    emlx = tmp_path / "42.emlx"
    large_body = "x" * (mail_adapter.MAX_TRIAGE_HEADER_BYTES * 2)
    _write_emlx(
        emlx,
        f"Message-ID: <bounded-001@example.test>\nSubject: Synthetic\n\n{large_body}",
    )

    assert mail_adapter._message_id_from_emlx(emlx) == "bounded-001@example.test"
    assert mail_adapter._normalize_message_id_header("  no-brackets@example.test  ") == (
        "no-brackets@example.test"
    )

    missing = tmp_path / "missing.emlx"
    _write_emlx(missing, "Subject: no message id\n\nSynthetic body")
    assert mail_adapter._message_id_from_emlx(missing) is None


def test_read_status_script_never_deletes_or_moves() -> None:
    script = _mail_set_read_status_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="x@example.test",
        target_read=True,
    )
    assert "set read status" in script
    assert "whose message id is" in script
    lowered = script.lower()
    for forbidden in ("delete", "move", "erase", "empty", "trash", "remove"):
        assert forbidden not in lowered, f"triage script must not contain '{forbidden}'"


def test_flagged_status_script_never_deletes_or_moves() -> None:
    script = _mail_set_flagged_status_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        mailbox_name="iCloud test mailbox",
        message_id="x@example.test",
        target_flagged=True,
    )
    assert "set flagged status" in script
    assert "whose message id is" in script
    lowered = script.lower()
    for forbidden in ("delete", "move", "erase", "empty", "trash", "remove"):
        assert forbidden not in lowered, f"triage script must not contain '{forbidden}'"


def test_archive_script_moves_without_permanent_delete_or_send() -> None:
    script = _mail_archive_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        source_mailbox_name="iCloud test mailbox",
        target_mailbox_name="Archive",
        message_id="x@example.test",
    )
    assert "move (first item of triageMatches) to archiveBox" in script
    assert "whose message id is" in script
    lowered = script.lower()
    for forbidden in ("delete", "erase", "empty", "trash", "remove", "send "):
        assert forbidden not in lowered, f"archive script must not contain '{forbidden}'"


def test_trash_script_moves_without_permanent_delete_or_send() -> None:
    script = _mail_trash_message_script(
        account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        source_mailbox_name="iCloud test mailbox",
        target_mailbox_name="Trash",
        message_id="x@example.test",
    )
    assert "move (first item of triageMatches) to trashBox" in script
    assert "whose message id is" in script
    lowered = script.lower()
    for forbidden in ("delete", "erase", "empty", "remove", "send "):
        assert forbidden not in lowered, f"trash script must not contain '{forbidden}'"


def test_move_script_moves_without_permanent_delete_or_send() -> None:
    script = _mail_move_message_script(
        source_account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        target_account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        source_mailbox_name="iCloud test mailbox",
        target_mailbox_name="Projects",
        message_id="x@example.test",
    )
    assert "move (first item of triageMatches) to targetBox" in script
    assert "whose message id is" in script
    lowered = script.lower()
    for forbidden in ("delete", "erase", "empty", "trash", "remove", "send "):
        assert forbidden not in lowered, f"move script must not contain '{forbidden}'"


def test_move_script_supports_nested_mailbox_paths() -> None:
    script = _mail_move_message_script(
        source_account_id="18E15B19-108F-4FD4-AE58-77F4468D00C1",
        target_account_id="SECOND-ACCOUNT-ID",
        source_mailbox_name="Parent/Inbox",
        target_mailbox_name="Clients/Project A",
        message_id="x@example.test",
    )
    assert 'mailbox "Inbox" of mailbox "Parent" of account id "18E15B19-108F-4FD4-AE58-77F4468D00C1"' in script
    assert 'mailbox "Project A" of mailbox "Clients" of account id "SECOND-ACCOUNT-ID"' in script


# ---- v1.183 partial-download identity + granular unavailability reasons ----


def test_plan_resolves_identity_from_partial_download(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{UNREAD_ROWID}.partial.emlx",
        f"Message-ID: <{UNREAD_MSGID}>\nSubject: Unread\n\nSynthetic partial body.\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "ok"


def test_plan_identity_warning_names_missing_file(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    mail_root.mkdir()
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    warning = next(w for w in plan["warnings"] if w["code"] == "message_identity_unavailable")
    assert "no local message file" in warning["message"]


def test_plan_identity_warning_names_missing_rfc_message_id(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "mail.sqlite"
    mail_root = tmp_path / "mail-root"
    _make_mail_db(db)
    _write_emlx(
        mail_root / "TestAccount" / "Messages" / f"{UNREAD_ROWID}.emlx",
        "Subject: Unread without identity\n\nSynthetic body.\n",
    )
    monkeypatch.setattr(mail_adapter, "_mail_content_root", lambda path: mail_root)

    plan = plan_mail_triage("mark_read", message_handle=_handle(UNREAD_ROWID), db_path=db)

    assert plan["status"] == "error"
    warning = next(w for w in plan["warnings"] if w["code"] == "message_identity_unavailable")
    assert "no RFC Message-ID header" in warning["message"]
