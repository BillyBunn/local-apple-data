from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.adapters.mail import (
    apply_mail_change,
    get_mail_content,
    plan_mail_change,
    search_mail_metadata,
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


def _insert_draft_message(db_path: Path, *, rowid: int, subject: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO subjects VALUES (?, ?)", (rowid, subject))
        connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (rowid, "local://synthetic/Drafts"))
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rowid, rowid, rowid, 20, 20, 0, 0, 0, 12),
        )


def _synthetic_store(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _mail_db(db_path)
    return db_path, mail_root


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


def test_mail_content_unavailable_warning_is_path_safe(tmp_path: Path) -> None:
    db_path, mail_root = _synthetic_store(tmp_path)
    handle = search_mail_metadata("content", db_path=db_path)["results"][0]["handle"]

    result = get_mail_content(handle, db_path=db_path, mail_root=mail_root)

    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "content_unavailable"
    assert str(tmp_path) not in json.dumps(result)


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
