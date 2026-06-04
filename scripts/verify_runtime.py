#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import struct
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from local_apple_data.adapters.calendar import (
    apply_calendar_change,
    get_calendar_event,
    plan_calendar_change,
    search_calendar_events,
)
from local_apple_data.adapters.contacts import (
    apply_contact_change,
    get_contact,
    plan_contact_change,
    search_contacts,
)
from local_apple_data.adapters.icloud_drive import (
    apply_icloud_drive_change,
    get_icloud_drive_content,
    plan_icloud_drive_change,
    search_icloud_drive_metadata,
)
from local_apple_data.adapters.hide_my_email import (
    get_hide_my_email_alias,
    search_hide_my_email_aliases,
)
from local_apple_data.adapters.mail import (
    apply_mail_change,
    get_mail_content,
    get_mail_metadata,
    plan_mail_change,
    search_mail_metadata,
)
from local_apple_data.adapters.messages import get_message_chat, search_message_chats
from local_apple_data.adapters.notes import (
    apply_notes_change,
    get_notes_content,
    plan_notes_change,
    search_notes_metadata,
)
from local_apple_data.adapters.photos import (
    apply_photo_change,
    export_photo_asset,
    get_photo_asset,
    plan_photo_change,
    search_photos,
)
from local_apple_data.adapters.reminders import (
    apply_reminder_change,
    get_reminder_content,
    plan_reminder_change,
    search_reminders_eventkit,
)
from local_apple_data.adapters.voice_memos import (
    export_voice_memo_audio,
    get_voice_memo_recording,
    search_voice_memos,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_mail_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    alias = "runtime_mask_42" + "@" + "icloud.com"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY, address TEXT, comment TEXT);
            CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject TEXT NOT NULL);
            CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY, url TEXT NOT NULL);
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                subject INTEGER NOT NULL,
                mailbox INTEGER NOT NULL,
                sender INTEGER,
                date_received INTEGER,
                date_sent INTEGER,
                read INTEGER NOT NULL DEFAULT 0,
                flagged INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE recipients (
                ROWID INTEGER PRIMARY KEY,
                message INTEGER,
                address INTEGER,
                type INTEGER
            );
            INSERT INTO subjects VALUES (1, 'Synthetic runtime verification mail');
            INSERT INTO mailboxes VALUES (1, 'local://synthetic/INBOX');
            """
        )
        connection.execute("INSERT INTO addresses VALUES (1, ?, '')", (alias,))
        connection.execute("INSERT INTO messages VALUES (42, 1, 1, 1, 10, 9, 0, 0, 0, 12)")
        connection.execute("INSERT INTO recipients VALUES (1, 42, 1, 0)")


def _write_mail_emlx(mail_root: Path, rowid: int, *, subject: str, body: str) -> None:
    mime_text = (
        f"Subject: {subject}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}\r\n"
    )
    mime_bytes = mime_text.encode("utf-8")
    path = mail_root / "Synthetic.mbox/INBOX.mbox/Messages" / f"{rowid}.emlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(mime_bytes)).encode("ascii") + b"\n" + mime_bytes)


def _write_emlx(mail_root: Path, rowid: int) -> None:
    _write_mail_emlx(
        mail_root,
        rowid,
        subject="Synthetic runtime verification mail",
        body="Synthetic runtime content.",
    )


def _make_notes_db(path: Path) -> None:
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
              (84, 'Synthetic runtime verification note', 'Fallback', 'Synthetic only', 10, 20, 0, 0, 1);
            """
        )


def _make_messages_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                display_name TEXT,
                service_name TEXT
            );
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date INTEGER,
                is_from_me INTEGER,
                handle_id INTEGER,
                service TEXT
            );
            CREATE TABLE chat_message_join (
                chat_id INTEGER,
                message_id INTEGER
            );
            CREATE TABLE chat_handle_join (
                chat_id INTEGER,
                handle_id INTEGER
            );
            CREATE TABLE handle (
                ROWID INTEGER PRIMARY KEY,
                id TEXT,
                service TEXT
            );
            INSERT INTO chat VALUES (1, 'runtime-chat-guid', 'Synthetic runtime chat', 'iMessage');
            INSERT INTO handle VALUES (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES
              (10, 'Synthetic runtime message.', 802310400, 0, 7, 'iMessage'),
              (11, 'Synthetic runtime reply.', 802310500, 1, 0, 'iMessage');
            INSERT INTO chat_message_join VALUES
              (1, 10),
              (1, 11);
            """
        )


def _atom(name: str, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + name.encode("ascii") + payload


def _write_voice_memo(path: Path, transcript_text: str) -> None:
    transcript = json.dumps(
        {"attributedString": [transcript_text, {"timeRange": [0, 1.0]}]},
        separators=(",", ":"),
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_atom("moov", _atom("trak", _atom("udta", _atom("tsrp", transcript)))))


def _make_voice_memos_db(path: Path, recordings_dir: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZCLOUDRECORDING (
                Z_PK INTEGER PRIMARY KEY,
                ZCUSTOMLABEL TEXT,
                ZDATE REAL,
                ZDURATION REAL,
                ZPATH TEXT,
                ZUNIQUEID TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ZCLOUDRECORDING
              (Z_PK, ZCUSTOMLABEL, ZDATE, ZDURATION, ZPATH, ZUNIQUEID)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "Synthetic runtime voice memo",
                802310400.0,
                11.0,
                "synthetic-runtime-voice.m4a",
                "synthetic-runtime-voice-uuid",
            ),
        )
    _write_voice_memo(
        recordings_dir / "synthetic-runtime-voice.m4a",
        "Synthetic runtime voice memo transcript.",
    )


def _make_icloud_drive_root(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "Runtime Packets").mkdir()
    (path / "synthetic-runtime-file.md").write_text(
        "Synthetic iCloud runtime content.",
        encoding="utf-8",
    )


def _payload(result: Any) -> dict[str, Any]:
    return json.loads(result.content[0].text)


async def _mcp_smoke(env: dict[str, str]) -> dict[str, Any]:
    server = StdioServerParameters(
        command="./scripts/run_mcp_server.sh",
        args=[],
        env=env,
        cwd=PROJECT_ROOT,
    )
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with stdio_client(server, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                health = await session.call_tool("apple_data_health", {})
                doctor = await session.call_tool("apple_data_doctor", {})
                empty_mail = await session.call_tool("mail_search", {"query": ""})
                wildcard_mail = await session.call_tool("mail_search", {"query": "%"})
                wildcard_messages = await session.call_tool("messages_search", {"query": "%"})
                wildcard_hide_my_email = await session.call_tool(
                    "hide_my_email_search",
                    {"query": "icloud.com"},
                )
                wildcard_voice_memos = await session.call_tool(
                    "voice_memos_search",
                    {"query": "%"},
                )
                wildcard_notes = await session.call_tool("notes_search", {"query": "%"})
                wildcard_icloud = await session.call_tool("icloud_drive_search", {"query": "%"})
                wildcard_calendar = await session.call_tool("calendar_search", {"query": "%"})
                wildcard_contacts = await session.call_tool("contacts_search", {"query": "%"})
                wildcard_photos = await session.call_tool("photos_search", {"query": "%"})
                wildcard_reminders = await session.call_tool("reminders_search", {"query": "%"})
                wildcard_eventkit_reminders = await session.call_tool(
                    "reminders_eventkit_search",
                    {"query": "%"},
                )

    return {
        "tool_count": len(tools.tools),
        "health_status": _payload(health)["status"],
        "doctor_source": _payload(doctor)["source"],
        "doctor_mode": _payload(doctor)["remediation_mode"],
        "empty_mail": _payload(empty_mail)["warnings"][0]["code"],
        "wildcard_mail": _payload(wildcard_mail)["warnings"][0]["code"],
        "wildcard_messages": _payload(wildcard_messages)["warnings"][0]["code"],
        "wildcard_hide_my_email": _payload(wildcard_hide_my_email)["warnings"][0]["code"],
        "wildcard_voice_memos": _payload(wildcard_voice_memos)["warnings"][0]["code"],
        "wildcard_notes": _payload(wildcard_notes)["warnings"][0]["code"],
        "wildcard_icloud": _payload(wildcard_icloud)["warnings"][0]["code"],
        "wildcard_calendar": _payload(wildcard_calendar)["warnings"][0]["code"],
        "wildcard_contacts": _payload(wildcard_contacts)["warnings"][0]["code"],
        "wildcard_photos": _payload(wildcard_photos)["warnings"][0]["code"],
        "wildcard_reminders": _payload(wildcard_reminders)["warnings"][0]["code"],
        "wildcard_eventkit_reminders": _payload(wildcard_eventkit_reminders)["warnings"][0][
            "code"
        ],
    }


def _handle_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "Library/Mail/V99/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99"
    _make_mail_db(db_path)
    _write_emlx(mail_root, 42)
    search = search_mail_metadata("runtime verification", db_path=db_path)
    handle = search["results"][0]["handle"]
    exact = get_mail_metadata(handle, db_path=db_path)
    content = get_mail_content(handle, db_path=db_path, mail_root=mail_root, max_chars=4000)
    legacy = get_mail_metadata("mail:message:42", db_path=db_path)
    legacy_content = get_mail_content("mail:message:42", db_path=db_path, mail_root=mail_root)
    return {
        "opaque_handle": handle.startswith("mail:message:v2:"),
        "search_content_status": search["results"][0]["content_status"],
        "exact_status": exact["status"],
        "content_status": content["status"],
        "content_chars": content["result"]["content_chars"],
        "legacy_content_status": legacy_content["status"],
        "legacy_content_warning": legacy_content["warnings"][0]["code"],
        "legacy_status": legacy["status"],
        "legacy_warning": legacy["warnings"][0]["code"],
    }


def _mail_plan_apply_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "Library/Mail/V99-MailDraft/MailData/Envelope Index"
    mail_root = tmp_path / "Library/Mail/V99-MailDraft"
    _make_mail_db(db_path)
    subject = "Synthetic runtime planned draft"
    body_text = "Synthetic runtime draft body."
    plan = plan_mail_change(
        "create-draft",
        to=["synthetic-runtime@example.invalid"],
        subject=subject,
        body_text=body_text,
    )
    token = "mail-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    missing_confirmation = apply_mail_change(
        "create-draft",
        to=["synthetic-runtime@example.invalid"],
        subject=subject,
        body_text=body_text,
        approval_token=token,
        confirm_apply=False,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=lambda _script, _timeout: "",
    )

    def runner(script: str, _timeout: float) -> str:
        if "send draftMessage" in script or "\nsend " in script:
            raise RuntimeError("Mail draft smoke must not send")
        with sqlite3.connect(db_path) as connection:
            connection.execute("INSERT INTO subjects VALUES (?, ?)", (43, subject))
            connection.execute("INSERT INTO mailboxes VALUES (?, ?)", (43, "local://synthetic/Drafts"))
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (43, 43, 43, 1, 20, 20, 0, 0, 0, 12),
            )
        _write_mail_emlx(mail_root, 43, subject=subject, body=body_text)
        return "43"

    result = apply_mail_change(
        "create-draft",
        to=["synthetic-runtime@example.invalid"],
        subject=subject,
        body_text=body_text,
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        mail_root=mail_root,
        script_runner=runner,
    )
    return {
        "mail_plan_status": plan["status"],
        "mail_plan_mode": plan["mode"],
        "mail_plan_mutation_applied": plan["mutation_applied"],
        "mail_plan_apply_available": plan["apply_available"],
        "mail_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith(
            "mail-plan:v1:"
        ),
        "mail_apply_status": result["status"],
        "mail_apply_mode": result["mode"],
        "mail_apply_mutation_applied": result["mutation_applied"],
        "mail_apply_read_back_subject": result["read_back"]["subject"],
        "mail_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _hide_my_email_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "Library/Mail/V99-HideMyEmail/MailData/Envelope Index"
    _make_mail_db(db_path)
    search = search_hide_my_email_aliases("runtime_mask", db_path=db_path)
    handle = search["results"][0]["handle"]
    detail = get_hide_my_email_alias(handle, db_path=db_path)
    legacy_detail = get_hide_my_email_alias("hide_my_email:alias:1", db_path=db_path)
    return {
        "hide_my_email_opaque_handle": handle.startswith("hide_my_email:alias:v1:"),
        "hide_my_email_search_status": search["status"],
        "hide_my_email_alias_preview": search["results"][0]["alias_preview"],
        "hide_my_email_detail_status": detail["status"],
        "hide_my_email_authoritative_inventory": detail["authoritative_inventory"],
        "hide_my_email_legacy_detail_status": legacy_detail["status"],
        "hide_my_email_legacy_detail_warning": legacy_detail["warnings"][0]["code"],
    }


def _notes_content_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    search = search_notes_metadata("runtime verification", db_path=db_path)
    handle = search["results"][0]["handle"]
    content = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=4000,
        script_runner=lambda _script, _timeout: "<p>Synthetic runtime note content.</p>",
    )
    paged = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=5,
        offset=5,
        script_runner=lambda _script, _timeout: "<p>abcdefghijklmnop</p>",
    )
    legacy_content = get_notes_content("notes:note:84", db_path=db_path)
    return {
        "notes_opaque_handle": handle.startswith("notes:note:v2:"),
        "notes_content_status": content["status"],
        "notes_content_chars": content["result"]["content_chars"],
        "notes_paged_status": paged["status"],
        "notes_paged_next_offset": paged["result"]["next_offset"],
        "notes_legacy_content_status": legacy_content["status"],
        "notes_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _notes_plan_apply_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "notes-plan-apply.sqlite"
    _make_notes_db(db_path)
    title = "Synthetic runtime planned note"
    body_text = "Synthetic runtime note body."
    plan = plan_notes_change("create", title=title, body_text=body_text)
    token = "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    missing_confirmation = apply_notes_change(
        "create",
        title=title,
        body_text=body_text,
        approval_token=token,
        confirm_apply=False,
        db_path=db_path,
        script_runner=lambda _script, _timeout: "",
    )

    def runner(script: str, _timeout: float) -> str:
        if "make new note" in script:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO ZICCLOUDSYNCINGOBJECT
                      (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
                       ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
                      VALUES (85, 'Synthetic runtime planned note', 'Synthetic runtime planned note',
                              'Synthetic runtime note body.', 30, 30, 0, 0, 2)
                    """
                )
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p85"
        return "<h1>Synthetic runtime planned note</h1><p>Synthetic runtime note body.</p>"

    result = apply_notes_change(
        "create",
        title=title,
        body_text=body_text,
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )
    return {
        "notes_plan_status": plan["status"],
        "notes_plan_mode": plan["mode"],
        "notes_plan_mutation_applied": plan["mutation_applied"],
        "notes_plan_apply_available": plan["apply_available"],
        "notes_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith("notes-plan:v1:"),
        "notes_apply_status": result["status"],
        "notes_apply_mode": result["mode"],
        "notes_apply_mutation_applied": result["mutation_applied"],
        "notes_apply_read_back_title": result["read_back"]["title"],
        "notes_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _messages_content_smoke(tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    search = search_message_chats("runtime", db_path=db_path)
    handle = search["results"][0]["handle"]
    content = get_message_chat(handle, db_path=db_path)
    legacy_content = get_message_chat("messages:chat:1", db_path=db_path)
    return {
        "messages_opaque_handle": handle.startswith("messages:chat:v1:"),
        "messages_content_status": content["status"],
        "messages_returned": content["result"]["messages_returned"],
        "messages_transcript_chars": content["result"]["transcript_chars"],
        "messages_legacy_content_status": legacy_content["status"],
        "messages_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _voice_memos_content_smoke(tmp_path: Path) -> dict[str, Any]:
    recordings_dir = tmp_path / "Recordings"
    recordings_dir.mkdir()
    db_path = recordings_dir / "CloudRecordings.db"
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("runtime", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]
    content = get_voice_memo_recording(
        handle,
        db_path=db_path,
        recordings_dir=recordings_dir,
        max_chars=4000,
    )
    export = export_voice_memo_audio(
        handle,
        output_dir=tmp_path / "voice-memo-exports",
        filename="runtime-memo",
        db_path=db_path,
        recordings_dir=recordings_dir,
    )
    legacy_content = get_voice_memo_recording("voice_memos:recording:1", db_path=db_path)
    return {
        "voice_memos_opaque_handle": handle.startswith("voice_memos:recording:v1:"),
        "voice_memos_content_status": content["status"],
        "voice_memos_transcript_status": content["result"]["transcript_status"],
        "voice_memos_transcript_chars": content["result"]["transcript_chars"],
        "voice_memos_audio_content_returned": content["result"]["audio_content_returned"],
        "voice_memos_export_status": export["status"],
        "voice_memos_audio_content_exported": export["result"]["audio_content_exported"],
        "voice_memos_exported_bytes": export["result"]["exported_bytes"],
        "voice_memos_legacy_content_status": legacy_content["status"],
        "voice_memos_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _icloud_drive_content_smoke(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "CloudDocs"
    _make_icloud_drive_root(root)
    search = search_icloud_drive_metadata("synthetic-runtime-file", root=root)
    handle = search["results"][0]["handle"]
    content = get_icloud_drive_content(handle, root=root, max_chars=4000)
    legacy_content = get_icloud_drive_content("icloud:file:synthetic-runtime-file.md", root=root)
    return {
        "icloud_opaque_handle": handle.startswith("icloud:file:v1:"),
        "icloud_content_status": content["status"],
        "icloud_content_chars": content["result"]["content_chars"],
        "icloud_content_sha256_present": bool(content["result"]["content_sha256"]),
        "icloud_legacy_content_status": legacy_content["status"],
        "icloud_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _icloud_drive_plan_apply_smoke(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "CloudDocs"
    if not root.exists():
        _make_icloud_drive_root(root)
    search = search_icloud_drive_metadata("Runtime Packets", root=root)
    parent_handle = search["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="runtime-created-note.md",
        content_text="Synthetic iCloud Drive apply content.",
    )
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="runtime-created-note.md",
        content_text="Synthetic iCloud Drive apply content.",
        approval_token=token,
        confirm_apply=True,
        root=root,
    )
    missing_confirmation = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="runtime-created-note.md",
        content_text="Synthetic iCloud Drive apply content.",
        approval_token=token,
        root=root,
    )
    created_handle = result["read_back"]["handle"]
    created_sha = result["read_back"]["content_sha256"]
    append_plan = plan_icloud_drive_change(
        "append_text",
        handle=created_handle,
        expected_current_sha256=created_sha,
        content_text="\nSynthetic appended runtime content.",
    )
    append_token = "icloud-drive-apply:v1:" + append_plan["preview"]["approval"]["approval_fingerprint"]
    append_result = apply_icloud_drive_change(
        "append_text",
        handle=created_handle,
        expected_current_sha256=created_sha,
        content_text="\nSynthetic appended runtime content.",
        approval_token=append_token,
        confirm_apply=True,
        root=root,
    )
    stale_append = apply_icloud_drive_change(
        "append_text",
        handle=created_handle,
        expected_current_sha256=created_sha,
        content_text="\nSynthetic appended runtime content.",
        approval_token=append_token,
        confirm_apply=True,
        root=root,
    )
    return {
        "icloud_plan_status": plan["status"],
        "icloud_plan_mode": plan["mode"],
        "icloud_plan_mutation_applied": plan["mutation_applied"],
        "icloud_plan_apply_available": plan["apply_available"],
        "icloud_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith(
            "icloud-drive-plan:v1:"
        ),
        "icloud_apply_status": result["status"],
        "icloud_apply_mode": result["mode"],
        "icloud_apply_mutation_applied": result["mutation_applied"],
        "icloud_apply_read_back_name": result["read_back"]["name"],
        "icloud_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
        "icloud_append_plan_status": append_plan["status"],
        "icloud_append_plan_mode": append_plan["mode"],
        "icloud_append_apply_status": append_result["status"],
        "icloud_append_apply_mutation_applied": append_result["mutation_applied"],
        "icloud_append_apply_sha_changed": append_result["read_back"]["content_sha256"] != created_sha,
        "icloud_append_stale_warning": stale_append["warnings"][0]["code"],
    }


def _calendar_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "calendar_events":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "events": [
                {
                    "event_id": "runtime-event-1",
                    "title": "Synthetic runtime calendar event",
                    "calendar_title": "Synthetic Calendar",
                    "start_date": "2026-06-03T17:00:00.000Z",
                    "end_date": "2026-06-03T18:00:00.000Z",
                    "all_day": False,
                    "availability": 0,
                    "location_present": True,
                    "notes_present": True,
                    "url_present": False,
                    "alarms_count": 0,
                    "attendees_count": 0,
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "calendar_event_by_id":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "event": {
                "event_id": "runtime-event-1",
                "title": "Synthetic runtime calendar event",
                "calendar_title": "Synthetic Calendar",
                "start_date": "2026-06-03T17:00:00.000Z",
                "end_date": "2026-06-03T18:00:00.000Z",
                "all_day": False,
                "availability": 0,
                "location_present": True,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
                "location": "Synthetic Room",
                "notes": "Synthetic calendar notes.",
            },
            "warnings": [],
        }
    if payload["command"] == "calendar_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": "authorized",
            "event": {
                "event_id": "runtime-created-calendar-event-1",
                "title": payload["title"],
                "calendar_title": payload["calendar_title"],
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "all_day": False,
                "availability": 0,
                "location_present": bool(payload.get("location")),
                "notes_present": bool(payload.get("notes")),
                "url_present": False,
                "alarms_count": 0,
                "attendees_count": 0,
            },
            "warnings": [],
        }
    raise RuntimeError("unexpected calendar helper command")


def _calendar_content_smoke() -> dict[str, Any]:
    search = search_calendar_events("runtime", eventkit_runner=_calendar_runner)
    handle = search["results"][0]["handle"]
    content = get_calendar_event(handle, eventkit_runner=_calendar_runner)
    legacy_content = get_calendar_event("calendar:event:runtime-event-1")
    return {
        "calendar_opaque_handle": handle.startswith("calendar:event:v1:"),
        "calendar_content_status": content["status"],
        "calendar_notes_chars": content["result"]["notes_chars"],
        "calendar_legacy_content_status": legacy_content["status"],
        "calendar_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _calendar_plan_apply_smoke() -> dict[str, Any]:
    plan = plan_calendar_change(
        "create",
        title="Synthetic runtime planned calendar event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T19:00:00Z",
        end_date="2026-06-04T20:00:00Z",
        location="Synthetic Room",
        notes="Synthetic calendar apply notes.",
    )
    token = "calendar-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    result = apply_calendar_change(
        "create",
        title="Synthetic runtime planned calendar event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T19:00:00Z",
        end_date="2026-06-04T20:00:00Z",
        location="Synthetic Room",
        notes="Synthetic calendar apply notes.",
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=_calendar_runner,
    )
    missing_confirmation = apply_calendar_change(
        "create",
        title="Synthetic runtime planned calendar event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-04T19:00:00Z",
        end_date="2026-06-04T20:00:00Z",
        location="Synthetic Room",
        notes="Synthetic calendar apply notes.",
        approval_token=token,
        eventkit_runner=_calendar_runner,
    )
    return {
        "calendar_plan_status": plan["status"],
        "calendar_plan_mode": plan["mode"],
        "calendar_plan_mutation_applied": plan["mutation_applied"],
        "calendar_plan_apply_available": plan["apply_available"],
        "calendar_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith(
            "calendar-plan:v1:"
        ),
        "calendar_apply_status": result["status"],
        "calendar_apply_mode": result["mode"],
        "calendar_apply_mutation_applied": result["mutation_applied"],
        "calendar_apply_read_back_title": result["read_back"]["title"],
        "calendar_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _contacts_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "contacts":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contacts": [
                {
                    "contact_id": "runtime-contact-1",
                    "display_name": "Synthetic runtime contact",
                    "contact_type": "person",
                    "given_name": "Synthetic",
                    "family_name": "Contact",
                    "nickname": "",
                    "organization_name": "Synthetic Org",
                    "department_name": "Runtime",
                    "job_title": "Verifier",
                    "email_count": 1,
                    "phone_count": 1,
                    "postal_address_count": 0,
                    "url_count": 1,
                    "social_profile_count": 0,
                    "instant_message_count": 0,
                    "relation_count": 0,
                    "dates_count": 0,
                    "birthday_present": False,
                    "image_available": False,
                    "note_status": "requires_entitlement",
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "contact_by_id":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": {
                "contact_id": "runtime-contact-1",
                "display_name": "Synthetic runtime contact",
                "contact_type": "person",
                "given_name": "Synthetic",
                "family_name": "Contact",
                "nickname": "",
                "organization_name": "Synthetic Org",
                "department_name": "Runtime",
                "job_title": "Verifier",
                "email_count": 1,
                "phone_count": 1,
                "postal_address_count": 0,
                "url_count": 1,
                "social_profile_count": 0,
                "instant_message_count": 0,
                "relation_count": 0,
                "dates_count": 0,
                "birthday_present": False,
                "image_available": False,
                "note_status": "requires_entitlement",
                "name_prefix": "",
                "middle_name": "",
                "previous_family_name": "",
                "name_suffix": "",
                "email_addresses": [{"label": "work", "value": "synthetic@example.invalid"}],
                "phone_numbers": [{"label": "mobile", "value": "+1 555 0100"}],
                "postal_addresses": [],
                "url_addresses": [{"label": "work", "value": "https://example.invalid"}],
                "birthday": {},
                "dates": [],
                "social_profiles": [],
                "instant_message_addresses": [],
                "contact_relations": [],
            },
            "warnings": [],
        }
    if payload["command"] == "contacts_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contact": {
                "contact_id": "runtime-created-contact-1",
                "display_name": "Synthetic runtime created contact",
                "contact_type": payload["contact_type"],
                "given_name": payload["given_name"],
                "family_name": payload["family_name"],
                "nickname": payload["nickname"],
                "organization_name": payload["organization_name"],
                "department_name": payload["department_name"],
                "job_title": payload["job_title"],
                "email_count": len(payload["email_addresses"]),
                "phone_count": len(payload["phone_numbers"]),
                "postal_address_count": 0,
                "url_count": len(payload["url_addresses"]),
                "social_profile_count": 0,
                "instant_message_count": 0,
                "relation_count": 0,
                "dates_count": 0,
                "birthday_present": False,
                "image_available": False,
                "note_status": "requires_entitlement",
                "name_prefix": "",
                "middle_name": "",
                "previous_family_name": "",
                "name_suffix": "",
                "email_addresses": payload["email_addresses"],
                "phone_numbers": payload["phone_numbers"],
                "postal_addresses": [],
                "url_addresses": payload["url_addresses"],
                "birthday": {},
                "dates": [],
                "social_profiles": [],
                "instant_message_addresses": [],
                "contact_relations": [],
            },
            "warnings": [],
        }
    raise RuntimeError("unexpected contacts helper command")


def _contacts_content_smoke() -> dict[str, Any]:
    search = search_contacts("runtime", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    content = get_contact(handle, contacts_runner=_contacts_runner)
    legacy_content = get_contact("contacts:contact:runtime-contact-1")
    return {
        "contacts_opaque_handle": handle.startswith("contacts:contact:v1:"),
        "contacts_content_status": content["status"],
        "contacts_email_count": len(content["result"]["email_addresses"]),
        "contacts_note_status": content["result"]["note_status"],
        "contacts_legacy_content_status": legacy_content["status"],
        "contacts_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _contacts_plan_apply_smoke() -> dict[str, Any]:
    plan = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Runtime Created",
        organization_name="Synthetic Org",
        job_title="Verifier",
        email_addresses=[{"label": "work", "value": "synthetic-runtime@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0102"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/runtime"}],
    )
    token = "contacts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    missing_confirmation = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Runtime Created",
        organization_name="Synthetic Org",
        job_title="Verifier",
        email_addresses=[{"label": "work", "value": "synthetic-runtime@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0102"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/runtime"}],
        approval_token=token,
        contacts_runner=_contacts_runner,
    )
    result = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Runtime Created",
        organization_name="Synthetic Org",
        job_title="Verifier",
        email_addresses=[{"label": "work", "value": "synthetic-runtime@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0102"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/runtime"}],
        approval_token=token,
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )
    return {
        "contacts_plan_status": plan["status"],
        "contacts_plan_mode": plan["mode"],
        "contacts_plan_mutation_applied": plan["mutation_applied"],
        "contacts_plan_apply_available": plan["apply_available"],
        "contacts_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith(
            "contacts-plan:v1:"
        ),
        "contacts_apply_status": result["status"],
        "contacts_apply_mode": result["mode"],
        "contacts_apply_mutation_applied": result["mutation_applied"],
        "contacts_apply_read_back_given_name": result["read_back"]["given_name"],
        "contacts_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _photos_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "photos":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "assets": [
                {
                    "asset_id": "runtime-photo-1",
                    "media_type": "image",
                    "media_subtypes": 0,
                    "pixel_width": 4032,
                    "pixel_height": 3024,
                    "duration": 0.0,
                    "favorite": False,
                    "hidden": False,
                    "source_type": 1,
                    "creation_date": "2026-06-04T17:00:00.000Z",
                    "modification_date": "2026-06-04T18:00:00.000Z",
                    "primary_filename": "IMG_RUNTIME.JPG",
                    "resource_count": 1,
                    "asset_content_returned": False,
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "photo_by_id":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "asset": {
                "asset_id": "runtime-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 4032,
                "pixel_height": 3024,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T17:00:00.000Z",
                "modification_date": "2026-06-04T18:00:00.000Z",
                "primary_filename": "IMG_RUNTIME.JPG",
                "resource_count": 1,
                "asset_content_returned": False,
                "resources": [
                    {
                        "filename": "IMG_RUNTIME.JPG",
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    if payload["command"] == "export_photo_by_id":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "asset": {
                "asset_id": "runtime-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 4032,
                "pixel_height": 3024,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T17:00:00.000Z",
                "modification_date": "2026-06-04T18:00:00.000Z",
                "primary_filename": "IMG_RUNTIME.JPG",
                "resource_count": 1,
                "asset_content_returned": False,
                "asset_content_exported": True,
                "exported_path": str(Path(payload["output_dir"]) / "runtime-photo.jpg"),
                "exported_filename": "runtime-photo.jpg",
                "exported_bytes": 4321,
                "resources": [
                    {
                        "filename": "IMG_RUNTIME.JPG",
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    if payload["command"] == "photos_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "asset": {
                "asset_id": "runtime-created-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 1600,
                "pixel_height": 1200,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T19:00:00.000Z",
                "modification_date": "2026-06-04T19:00:00.000Z",
                "primary_filename": payload["expected_filename"],
                "resource_count": 1,
                "asset_content_returned": False,
                "resources": [
                    {
                        "filename": payload["expected_filename"],
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    raise RuntimeError("unexpected photos helper command")


def _photos_content_smoke(tmp_path: Path) -> dict[str, Any]:
    search = search_photos("runtime", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]
    detail = get_photo_asset(handle, photos_runner=_photos_runner)
    export = export_photo_asset(
        handle,
        output_dir=tmp_path / "photo-exports",
        filename="runtime-photo.jpg",
        photos_runner=_photos_runner,
    )
    legacy_detail = get_photo_asset("photos:asset:runtime-photo-1")
    return {
        "photos_opaque_handle": handle.startswith("photos:asset:v1:"),
        "photos_detail_status": detail["status"],
        "photos_resource_count": len(detail["result"]["resources"]),
        "photos_asset_content_returned": detail["result"]["asset_content_returned"],
        "photos_export_status": export["status"],
        "photos_asset_content_exported": export["result"]["asset_content_exported"],
        "photos_exported_bytes": export["result"]["exported_bytes"],
        "photos_legacy_detail_status": legacy_detail["status"],
        "photos_legacy_detail_warning": legacy_detail["warnings"][0]["code"],
    }


def _photos_plan_apply_smoke(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "IMG_RUNTIME_IMPORT.JPG"
    source.write_bytes(b"synthetic runtime photo bytes")
    plan = plan_photo_change("import", source_file=source)
    token = "photos-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    result = apply_photo_change(
        "import",
        source_file=source,
        approval_token=token,
        confirm_apply=True,
        photos_runner=_photos_runner,
    )
    missing_confirmation = apply_photo_change(
        "import",
        source_file=source,
        approval_token=token,
        photos_runner=_photos_runner,
    )
    return {
        "photos_plan_status": plan["status"],
        "photos_plan_mode": plan["mode"],
        "photos_plan_mutation_applied": plan["mutation_applied"],
        "photos_plan_apply_available": plan["apply_available"],
        "photos_plan_idempotency_key": plan["preview"]["idempotency_key"].startswith(
            "photos-plan:v1:"
        ),
        "photos_apply_status": result["status"],
        "photos_apply_mode": result["mode"],
        "photos_apply_mutation_applied": result["mutation_applied"],
        "photos_apply_read_back_filename": result["read_back"]["primary_filename"],
        "photos_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _reminders_runner(payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
    if payload["command"] == "reminders":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminders": [
                {
                    "reminder_id": "runtime-reminder-1",
                    "title": "Synthetic runtime reminder",
                    "list_name": "Synthetic List",
                    "due_date": "2026-06-04T17:00:00.000Z",
                    "start_date": "",
                    "completed": False,
                    "priority": 5,
                    "notes_present": True,
                    "url_present": False,
                    "alarms_count": 1,
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "reminder_by_id":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "notes": "Synthetic reminder notes.",
            },
            "warnings": [],
        }
    if payload["command"] == "reminder_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": payload.get("reminder_id", "runtime-created-reminder-1"),
                "title": payload.get("title") or payload.get("expected_title"),
                "list_name": payload.get("list_name") or "Synthetic List",
                "due_date": payload.get("due_date") or "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": payload.get("operation") == "complete",
                "priority": 5,
                "notes_present": bool(payload.get("notes")),
                "url_present": False,
                "alarms_count": 0,
            },
            "warnings": [],
        }
    raise RuntimeError("unexpected reminders helper command")


def _reminders_content_smoke() -> dict[str, Any]:
    search = search_reminders_eventkit("runtime", eventkit_runner=_reminders_runner)
    handle = search["results"][0]["handle"]
    content = get_reminder_content(handle, eventkit_runner=_reminders_runner)
    legacy_content = get_reminder_content("reminders:reminder:runtime-reminder-1")
    return {
        "reminders_eventkit_opaque_handle": handle.startswith(
            "reminders:reminder:eventkit:v1:"
        ),
        "reminders_content_status": content["status"],
        "reminders_notes_chars": content["result"]["notes_chars"],
        "reminders_legacy_content_status": legacy_content["status"],
        "reminders_legacy_content_warning": legacy_content["warnings"][0]["code"],
    }


def _reminders_plan_smoke() -> dict[str, Any]:
    result = plan_reminder_change(
        "create",
        title="Synthetic runtime planned reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
    )
    return {
        "reminders_plan_status": result["status"],
        "reminders_plan_mode": result["mode"],
        "reminders_plan_mutation_applied": result["mutation_applied"],
        "reminders_plan_apply_available": result["apply_available"],
        "reminders_plan_idempotency_key": result["preview"]["idempotency_key"].startswith(
            "reminders-plan:v1:"
        ),
    }


def _reminders_apply_smoke() -> dict[str, Any]:
    search = search_reminders_eventkit("runtime", eventkit_runner=_reminders_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "complete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
    )
    token = "reminders-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    result = apply_reminder_change(
        "complete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        approval_token=token,
        confirm_apply=True,
        eventkit_runner=_reminders_runner,
    )
    missing_confirmation = apply_reminder_change(
        "complete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        approval_token=token,
        eventkit_runner=_reminders_runner,
    )
    return {
        "reminders_apply_status": result["status"],
        "reminders_apply_mode": result["mode"],
        "reminders_apply_mutation_applied": result["mutation_applied"],
        "reminders_apply_read_back_completed": result["read_back"]["completed"],
        "reminders_apply_missing_confirmation": missing_confirmation["warnings"][0]["code"],
    }


def _assert_summary(summary: dict[str, Any]) -> None:
    expected = {
        "tool_count": 43,
        "doctor_source": "doctor",
        "doctor_mode": "non_mutating",
        "empty_mail": "empty_query",
        "wildcard_mail": "broad_query",
        "wildcard_messages": "broad_query",
        "wildcard_hide_my_email": "broad_query",
        "wildcard_voice_memos": "broad_query",
        "wildcard_notes": "broad_query",
        "wildcard_icloud": "broad_query",
        "wildcard_calendar": "broad_query",
        "wildcard_contacts": "broad_query",
        "wildcard_photos": "broad_query",
        "wildcard_reminders": "broad_query",
        "wildcard_eventkit_reminders": "broad_query",
        "opaque_handle": True,
        "search_content_status": "available",
        "exact_status": "ok",
        "content_status": "ok",
        "content_chars": 26,
        "legacy_content_status": "error",
        "legacy_content_warning": "invalid_handle",
        "legacy_status": "error",
        "legacy_warning": "invalid_handle",
        "mail_plan_status": "ok",
        "mail_plan_mode": "plan",
        "mail_plan_mutation_applied": False,
        "mail_plan_apply_available": True,
        "mail_plan_idempotency_key": True,
        "mail_apply_status": "ok",
        "mail_apply_mode": "apply",
        "mail_apply_mutation_applied": True,
        "mail_apply_read_back_subject": "Synthetic runtime planned draft",
        "mail_apply_missing_confirmation": "missing_apply_confirmation",
        "messages_opaque_handle": True,
        "messages_content_status": "ok",
        "messages_returned": 2,
        "messages_transcript_chars": 50,
        "messages_legacy_content_status": "error",
        "messages_legacy_content_warning": "invalid_handle",
        "hide_my_email_opaque_handle": True,
        "hide_my_email_search_status": "ok",
        "hide_my_email_alias_preview": "ru***@icloud.com",
        "hide_my_email_detail_status": "ok",
        "hide_my_email_authoritative_inventory": False,
        "hide_my_email_legacy_detail_status": "error",
        "hide_my_email_legacy_detail_warning": "invalid_handle",
        "voice_memos_opaque_handle": True,
        "voice_memos_content_status": "ok",
        "voice_memos_transcript_status": "available",
        "voice_memos_transcript_chars": 40,
        "voice_memos_audio_content_returned": False,
        "voice_memos_export_status": "ok",
        "voice_memos_audio_content_exported": True,
        "voice_memos_exported_bytes": 119,
        "voice_memos_legacy_content_status": "error",
        "voice_memos_legacy_content_warning": "invalid_handle",
        "notes_opaque_handle": True,
        "notes_content_status": "ok",
        "notes_content_chars": 31,
        "notes_paged_status": "ok",
        "notes_paged_next_offset": 10,
        "notes_legacy_content_status": "error",
        "notes_legacy_content_warning": "invalid_handle",
        "notes_plan_status": "ok",
        "notes_plan_mode": "plan",
        "notes_plan_mutation_applied": False,
        "notes_plan_apply_available": True,
        "notes_plan_idempotency_key": True,
        "notes_apply_status": "ok",
        "notes_apply_mode": "apply",
        "notes_apply_mutation_applied": True,
        "notes_apply_read_back_title": "Synthetic runtime planned note",
        "notes_apply_missing_confirmation": "missing_apply_confirmation",
        "icloud_opaque_handle": True,
        "icloud_content_status": "ok",
        "icloud_content_chars": 33,
        "icloud_legacy_content_status": "error",
        "icloud_legacy_content_warning": "invalid_handle",
        "icloud_plan_status": "ok",
        "icloud_plan_mode": "plan",
        "icloud_plan_mutation_applied": False,
        "icloud_plan_apply_available": True,
        "icloud_plan_idempotency_key": True,
        "icloud_apply_status": "ok",
        "icloud_apply_mode": "apply",
        "icloud_apply_mutation_applied": True,
        "icloud_apply_read_back_name": "runtime-created-note.md",
        "icloud_apply_missing_confirmation": "missing_apply_confirmation",
        "calendar_opaque_handle": True,
        "calendar_content_status": "ok",
        "calendar_notes_chars": 25,
        "calendar_legacy_content_status": "error",
        "calendar_legacy_content_warning": "invalid_handle",
        "calendar_plan_status": "ok",
        "calendar_plan_mode": "plan",
        "calendar_plan_mutation_applied": False,
        "calendar_plan_apply_available": True,
        "calendar_plan_idempotency_key": True,
        "calendar_apply_status": "ok",
        "calendar_apply_mode": "apply",
        "calendar_apply_mutation_applied": True,
        "calendar_apply_read_back_title": "Synthetic runtime planned calendar event",
        "calendar_apply_missing_confirmation": "missing_apply_confirmation",
        "contacts_opaque_handle": True,
        "contacts_content_status": "ok",
        "contacts_email_count": 1,
        "contacts_note_status": "requires_entitlement",
        "contacts_legacy_content_status": "error",
        "contacts_legacy_content_warning": "invalid_handle",
        "contacts_plan_status": "ok",
        "contacts_plan_mode": "plan",
        "contacts_plan_mutation_applied": False,
        "contacts_plan_apply_available": True,
        "contacts_plan_idempotency_key": True,
        "contacts_apply_status": "ok",
        "contacts_apply_mode": "apply",
        "contacts_apply_mutation_applied": True,
        "contacts_apply_read_back_given_name": "Synthetic",
        "contacts_apply_missing_confirmation": "missing_apply_confirmation",
        "photos_opaque_handle": True,
        "photos_detail_status": "ok",
        "photos_resource_count": 1,
        "photos_asset_content_returned": False,
        "photos_export_status": "ok",
        "photos_asset_content_exported": True,
        "photos_exported_bytes": 4321,
        "photos_legacy_detail_status": "error",
        "photos_legacy_detail_warning": "invalid_handle",
        "photos_plan_status": "ok",
        "photos_plan_mode": "plan",
        "photos_plan_mutation_applied": False,
        "photos_plan_apply_available": True,
        "photos_plan_idempotency_key": True,
        "photos_apply_status": "ok",
        "photos_apply_mode": "apply",
        "photos_apply_mutation_applied": True,
        "photos_apply_read_back_filename": "IMG_RUNTIME_IMPORT.JPG",
        "photos_apply_missing_confirmation": "missing_apply_confirmation",
        "reminders_eventkit_opaque_handle": True,
        "reminders_content_status": "ok",
        "reminders_notes_chars": 25,
        "reminders_legacy_content_status": "error",
        "reminders_legacy_content_warning": "invalid_handle",
        "reminders_plan_status": "ok",
        "reminders_plan_mode": "plan",
        "reminders_plan_mutation_applied": False,
        "reminders_plan_apply_available": True,
        "reminders_plan_idempotency_key": True,
        "reminders_apply_status": "ok",
        "reminders_apply_mode": "apply",
        "reminders_apply_mutation_applied": True,
        "reminders_apply_read_back_completed": True,
        "reminders_apply_missing_confirmation": "missing_apply_confirmation",
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise SystemExit(f"runtime verification failed: {key}={summary.get(key)!r}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env = os.environ.copy()
        env["LOCAL_APPLE_DATA_LOG_DIR"] = str(tmp_path / "logs")
        env["LOCAL_APPLE_DATA_HANDLE_SECRET"] = "synthetic-runtime-verification-secret"
        os.environ.update(
            {
                "LOCAL_APPLE_DATA_LOG_DIR": env["LOCAL_APPLE_DATA_LOG_DIR"],
                "LOCAL_APPLE_DATA_HANDLE_SECRET": env["LOCAL_APPLE_DATA_HANDLE_SECRET"],
            }
        )
        summary = asyncio.run(_mcp_smoke(env))
        summary.update(_handle_smoke(tmp_path))
        summary.update(_mail_plan_apply_smoke(tmp_path))
        summary.update(_messages_content_smoke(tmp_path))
        summary.update(_hide_my_email_smoke(tmp_path))
        summary.update(_voice_memos_content_smoke(tmp_path))
        summary.update(_notes_content_smoke(tmp_path))
        summary.update(_notes_plan_apply_smoke(tmp_path))
        summary.update(_icloud_drive_content_smoke(tmp_path))
        summary.update(_icloud_drive_plan_apply_smoke(tmp_path))
        summary.update(_calendar_content_smoke())
        summary.update(_calendar_plan_apply_smoke())
        summary.update(_contacts_content_smoke())
        summary.update(_contacts_plan_apply_smoke())
        summary.update(_photos_content_smoke(tmp_path))
        summary.update(_photos_plan_apply_smoke(tmp_path))
        summary.update(_reminders_content_smoke())
        summary.update(_reminders_plan_smoke())
        summary.update(_reminders_apply_smoke())

    _assert_summary(summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
