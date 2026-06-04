from __future__ import annotations

import json
from pathlib import Path

from local_apple_data.redacted_log import log_result


def test_log_result_excludes_query_and_result_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "mail",
        "status": "ok",
        "result_count": 1,
        "query": {"scope": "subject", "text": "do not log query"},
        "results": [{"subject": "do not log subject"}],
        "privacy": {
            "output_tier": "metadata",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "warnings": [{"code": "sample_warning", "message": "do not log message"}],
    }

    log_result("mail.search", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "mail.search"
    assert event["warning_codes"] == ["sample_warning"]
    assert "do not log query" not in text
    assert "do not log subject" not in text
    assert "do not log message" not in text


def test_log_result_excludes_mail_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "mail",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "target": {"account": "mail_app_default", "mailbox": "drafts"},
            "proposed": {
                "to": ["do-not-log@example.invalid"],
                "cc": ["copy-do-not-log@example.invalid"],
                "subject": "do not log draft subject",
                "body_preview_text": "do not log draft body",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "mail:message:v2:abcdef0123456789abcdef0123456789",
            "subject": "do not log draft subject",
            "content_text": "do not log draft body",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("mail.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "mail.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do-not-log@example.invalid" not in text
    assert "copy-do-not-log@example.invalid" not in text
    assert "do not log draft subject" not in text
    assert "do not log draft body" not in text
    assert "mail:message:v2:" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_reminder_plan_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "reminders",
        "status": "ok",
        "result_count": 1,
        "mode": "plan",
        "privacy": {
            "output_tier": "preview",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "operation": "create",
            "target": {"list_name": "do not log list"},
            "proposed": {
                "title": "do not log reminder title",
                "notes_text": "do not log reminder notes",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "warnings": [],
    }

    log_result("reminders.plan", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "reminders.plan"
    assert event["privacy"]["output_tier"] == "preview"
    assert "do not log list" not in text
    assert "do not log reminder title" not in text
    assert "do not log reminder notes" not in text
    assert "do-not-log-fingerprint" not in text


def test_log_result_excludes_reminder_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "reminders",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "title": "do not log reminder title",
            "list_name": "do not log list",
            "handle": "do-not-log-handle",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("reminders.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "reminders.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do not log reminder title" not in text
    assert "do not log list" not in text
    assert "do-not-log-handle" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_icloud_drive_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "icloud_drive",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "target": {
                "parent_handle": "do-not-log-parent-handle",
                "filename": "do-not-log-filename.md",
            },
            "proposed": {
                "content_sha256": "do-not-log-content-hash",
                "content_text": "do not log file content",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "do-not-log-created-handle",
            "name": "do-not-log-filename.md",
            "content_sha256": "do-not-log-content-hash",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("icloud-drive.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "icloud-drive.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do-not-log-parent-handle" not in text
    assert "do-not-log-created-handle" not in text
    assert "do-not-log-filename.md" not in text
    assert "do-not-log-content-hash" not in text
    assert "do not log file content" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_calendar_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "calendar",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "target": {"calendar_title": "do not log calendar"},
            "proposed": {
                "title": "do not log event title",
                "location": "do not log location",
                "notes_text": "do not log event notes",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "do-not-log-calendar-handle",
            "title": "do not log event title",
            "calendar_title": "do not log calendar",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("calendar.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "calendar.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do not log event title" not in text
    assert "do not log calendar" not in text
    assert "do not log location" not in text
    assert "do not log event notes" not in text
    assert "do-not-log-calendar-handle" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_contacts_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "contacts",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "proposed": {
                "given_name": "do not log given",
                "family_name": "do not log family",
                "email_addresses": [{"label": "work", "value": "do-not-log@example.invalid"}],
                "phone_numbers": [{"label": "mobile", "value": "do not log phone"}],
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "do-not-log-contact-handle",
            "given_name": "do not log given",
            "family_name": "do not log family",
            "email_addresses": [{"label": "work", "value": "do-not-log@example.invalid"}],
            "phone_numbers": [{"label": "mobile", "value": "do not log phone"}],
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("contacts.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "contacts.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do not log given" not in text
    assert "do not log family" not in text
    assert "do-not-log@example.invalid" not in text
    assert "do not log phone" not in text
    assert "do-not-log-contact-handle" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_notes_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "notes",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "target": {
                "handle": "do-not-log-note-handle",
                "expected_current_sha256": "do-not-log-content-hash",
            },
            "proposed": {
                "title": "do not log note title",
                "body_preview_text": "do not log note body",
                "append_preview_text": "do not log appended note body",
                "append_body_sha256": "do-not-log-append-hash",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "do-not-log-note-handle",
            "title": "do not log note title",
            "content_text": "do not log note body",
            "content_sha256": "do-not-log-content-hash",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("notes.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "notes.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do not log note title" not in text
    assert "do not log note body" not in text
    assert "do not log appended note body" not in text
    assert "do-not-log-note-handle" not in text
    assert "do-not-log-content-hash" not in text
    assert "do-not-log-append-hash" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_photos_plan_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "photos",
        "status": "ok",
        "result_count": 1,
        "mode": "plan",
        "privacy": {
            "output_tier": "preview",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "target": {"library": "system_photo_library"},
            "proposed": {
                "source_filename": "do-not-log-photo.jpg",
                "file_sha256": "do-not-log-file-hash",
                "source_path": "/do/not/log/photo.jpg",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "warnings": [{"code": "synthetic_warning", "message": "do not log warning"}],
    }

    log_result("photos.plan", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "photos.plan"
    assert event["privacy"]["output_tier"] == "preview"
    assert event["warning_codes"] == ["synthetic_warning"]
    assert "do-not-log-photo.jpg" not in text
    assert "do-not-log-file-hash" not in text
    assert "/do/not/log/photo.jpg" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_photos_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "photos",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "preview": {
            "proposed": {
                "source_filename": "do-not-log-photo.jpg",
                "file_sha256": "do-not-log-file-hash",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": "photos:asset:v1:abcdef0123456789abcdef0123456789",
            "primary_filename": "do-not-log-photo.jpg",
            "resources": [{"filename": "do-not-log-photo.jpg"}],
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("photos.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "photos.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "do-not-log-photo.jpg" not in text
    assert "do-not-log-file-hash" not in text
    assert "photos:asset:v1:" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_messages_apply_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "messages",
        "status": "ok",
        "result_count": 1,
        "mode": "apply",
        "privacy": {
            "output_tier": "mutation",
            "content_inspected": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "plan": {
            "target": {
                "handle": "messages:chat:v1:abcdef0123456789abcdef0123456789",
                "display_name": "do not log chat name",
                "last_message_rowid": 123,
            },
            "proposed": {
                "body_preview_text": "do not log message body",
                "body_sha256": "do-not-log-body-hash",
            },
            "approval": {"approval_fingerprint": "do-not-log-fingerprint"},
        },
        "approval": {
            "approval_fingerprint": "do-not-log-fingerprint",
            "approval_token_verified": True,
        },
        "read_back": {
            "chat_handle_confirmed": True,
            "service": "iMessage",
            "body_chars": 24,
            "body_sha256": "do-not-log-body-hash",
        },
        "warnings": [{"code": "already_applied", "message": "do not log warning"}],
    }

    log_result("messages.apply", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "messages.apply"
    assert event["privacy"]["output_tier"] == "mutation"
    assert event["warning_codes"] == ["already_applied"]
    assert "messages:chat:v1:" not in text
    assert "do not log chat name" not in text
    assert "do not log message body" not in text
    assert "do-not-log-body-hash" not in text
    assert "do-not-log-fingerprint" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_notes_attachment_export_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "notes",
        "status": "ok",
        "result_count": 1,
        "privacy": {
            "output_tier": "export",
            "content_inspected": False,
            "content_exported": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "result": {
            "handle": "notes:attachment:v1:abcdef0123456789abcdef0123456789",
            "note_handle": "notes:note:v2:abcdef0123456789abcdef0123456789",
            "filename": "do-not-log-packet.pdf",
            "exported_path": "/do/not/log/exported/do-not-log-packet.pdf",
            "attachment_content_returned": False,
            "attachment_content_exported": True,
        },
        "warnings": [{"code": "synthetic_warning", "message": "do not log warning"}],
    }

    log_result("notes.export_attachment", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "notes.export_attachment"
    assert event["privacy"]["output_tier"] == "export"
    assert event["warning_codes"] == ["synthetic_warning"]
    assert "notes:attachment:v1:" not in text
    assert "notes:note:v2:" not in text
    assert "do-not-log-packet.pdf" not in text
    assert "/do/not/log/exported" not in text
    assert "do not log warning" not in text


def test_log_result_excludes_mail_attachment_export_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "mail",
        "status": "ok",
        "result_count": 1,
        "privacy": {
            "output_tier": "export",
            "content_inspected": True,
            "attachment_content_returned": False,
            "attachment_content_exported": True,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "result": {
            "handle": "mail:attachment:v1:abcdef0123456789abcdef0123456789",
            "message_handle": "mail:message:v2:abcdef0123456789abcdef0123456789",
            "filename": "do-not-log-mail-packet.pdf",
            "exported_path": "/do/not/log/exported/do-not-log-mail-packet.pdf",
            "attachment_content_returned": False,
            "attachment_content_exported": True,
        },
        "warnings": [{"code": "synthetic_warning", "message": "do not log warning"}],
    }

    log_result("mail.export_attachment", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "mail.export_attachment"
    assert event["privacy"]["output_tier"] == "export"
    assert event["warning_codes"] == ["synthetic_warning"]
    assert "mail:attachment:v1:" not in text
    assert "mail:message:v2:" not in text
    assert "do-not-log-mail-packet.pdf" not in text
    assert "/do/not/log/exported" not in text
    assert "do not log warning" not in text
