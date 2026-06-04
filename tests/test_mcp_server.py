from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from local_apple_data.mcp_server import (
    INSTRUCTIONS,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    calendar_apply_change,
    calendar_get_event,
    calendar_plan_change,
    contacts_apply_change,
    contacts_get,
    contacts_plan_change,
    icloud_drive_apply_change,
    hide_my_email_get_alias,
    icloud_drive_get_content,
    icloud_drive_get_metadata,
    icloud_drive_plan_change,
    mail_apply_change,
    mail_get_content,
    mail_get_metadata,
    mail_plan_change,
    messages_get_chat,
    notes_apply_change,
    notes_get_content,
    notes_get_metadata,
    notes_plan_change,
    photos_export_asset,
    photos_get_asset,
    reminders_apply_change,
    reminders_get_content,
    reminders_plan_change,
    voice_memos_export_audio,
    voice_memos_get_recording,
)


def test_mcp_instructions_preserve_safety_boundaries() -> None:
    assert "metadata-first" in INSTRUCTIONS
    assert "bounded" in INSTRUCTIONS
    assert "Gmail connector" in INSTRUCTIONS
    assert "exact-handle" in INSTRUCTIONS
    assert "approval token" in INSTRUCTIONS


def test_mcp_tools_use_read_only_annotations() -> None:
    assert READ_ONLY_ANNOTATIONS.readOnlyHint is True
    assert READ_ONLY_ANNOTATIONS.destructiveHint is False
    assert READ_ONLY_ANNOTATIONS.idempotentHint is True
    assert READ_ONLY_ANNOTATIONS.openWorldHint is False
    assert WRITE_ANNOTATIONS.readOnlyHint is False
    assert WRITE_ANNOTATIONS.destructiveHint is False
    assert WRITE_ANNOTATIONS.idempotentHint is True
    assert WRITE_ANNOTATIONS.openWorldHint is False


def test_mcp_direct_tool_wrappers_reject_bad_handles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))

    mail_result = mail_get_metadata("bad-handle")
    mail_content_result = mail_get_content("bad-handle")
    mail_plan_result = mail_plan_change(
        "create_draft",
        to=[],
        subject="Synthetic draft",
        body_text="Synthetic body.",
    )
    mail_apply_result = mail_apply_change(
        "create_draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic draft",
        body_text="Synthetic body.",
        approval_token="mail-apply:v1:bad",
        confirm_apply=True,
    )
    messages_result = messages_get_chat("bad-handle")
    hide_my_email_result = hide_my_email_get_alias("bad-handle")
    voice_memos_result = voice_memos_get_recording("bad-handle")
    voice_memos_export_result = voice_memos_export_audio("bad-handle", str(tmp_path / "exports"))
    notes_result = notes_get_metadata("bad-handle")
    notes_content_result = notes_get_content("bad-handle")
    notes_plan_result = notes_plan_change("create", title="", body_text="Synthetic body.")
    notes_apply_result = notes_apply_change(
        "create",
        title="Synthetic note",
        body_text="Synthetic body.",
        approval_token="notes-apply:v1:bad",
        confirm_apply=True,
    )
    icloud_result = icloud_drive_get_metadata("bad-handle")
    icloud_content_result = icloud_drive_get_content("bad-handle")
    icloud_plan_result = icloud_drive_plan_change(
        "create_text",
        parent_handle="bad-handle",
        filename="new-note.md",
        content_text="Synthetic text.",
    )
    icloud_apply_result = icloud_drive_apply_change(
        "create_text",
        parent_handle="bad-handle",
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token="icloud-drive-apply:v1:bad",
        confirm_apply=True,
    )
    calendar_result = calendar_get_event("bad-handle")
    calendar_plan_result = calendar_plan_change(
        "create",
        title="Synthetic event",
        calendar_title="Synthetic Calendar",
        start_date="bad-date",
        end_date="2026-06-04T18:00:00Z",
    )
    calendar_apply_result = calendar_apply_change(
        "create",
        title="Synthetic event",
        calendar_title="Synthetic Calendar",
        start_date="bad-date",
        end_date="2026-06-04T18:00:00Z",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )
    contact_result = contacts_get("bad-handle")
    contacts_plan_result = contacts_plan_change(
        "create",
        contact_type="person",
    )
    contacts_apply_result = contacts_apply_change(
        "create",
        approval_token="contacts-apply:v1:bad",
        contact_type="person",
        confirm_apply=True,
    )
    photo_result = photos_get_asset("bad-handle")
    photo_export_result = photos_export_asset("bad-handle", str(tmp_path / "exports"))
    reminder_result = reminders_get_content("bad-handle")
    reminder_plan_result = reminders_plan_change(
        "complete",
        handle="bad-handle",
        expected_title="Synthetic reminder",
    )
    reminder_apply_result = reminders_apply_change(
        "complete",
        approval_token="reminders-apply:v1:bad",
        confirm_apply=True,
        handle="bad-handle",
        expected_title="Synthetic reminder",
    )

    assert mail_result["status"] == "error"
    assert mail_content_result["status"] == "error"
    assert mail_content_result["warnings"][0]["code"] == "invalid_handle"
    assert mail_plan_result["status"] == "error"
    assert mail_plan_result["warnings"][0]["code"] == "missing_to"
    assert mail_apply_result["status"] == "error"
    assert mail_apply_result["warnings"][0]["code"] == "invalid_approval_token"
    assert messages_result["status"] == "error"
    assert messages_result["warnings"][0]["code"] == "invalid_handle"
    assert hide_my_email_result["status"] == "error"
    assert hide_my_email_result["warnings"][0]["code"] == "invalid_handle"
    assert voice_memos_result["status"] == "error"
    assert voice_memos_result["warnings"][0]["code"] == "invalid_handle"
    assert voice_memos_export_result["status"] == "error"
    assert voice_memos_export_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_result["status"] == "error"
    assert notes_content_result["status"] == "error"
    assert notes_content_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_plan_result["status"] == "error"
    assert notes_plan_result["warnings"][0]["code"] == "missing_title"
    assert notes_apply_result["status"] == "error"
    assert notes_apply_result["warnings"][0]["code"] == "invalid_approval_token"
    assert icloud_result["status"] == "error"
    assert icloud_result["warnings"][0]["code"] == "invalid_handle"
    assert icloud_content_result["status"] == "error"
    assert icloud_content_result["warnings"][0]["code"] == "invalid_handle"
    assert icloud_plan_result["status"] == "error"
    assert icloud_plan_result["warnings"][0]["code"] == "invalid_parent_handle"
    assert icloud_apply_result["status"] == "error"
    assert icloud_apply_result["warnings"][0]["code"] == "invalid_parent_handle"
    assert calendar_result["status"] == "error"
    assert calendar_result["warnings"][0]["code"] == "invalid_handle"
    assert calendar_plan_result["status"] == "error"
    assert calendar_plan_result["warnings"][0]["code"] == "invalid_datetime"
    assert calendar_apply_result["status"] == "error"
    assert calendar_apply_result["warnings"][0]["code"] == "invalid_datetime"
    assert contact_result["status"] == "error"
    assert contact_result["warnings"][0]["code"] == "invalid_handle"
    assert contacts_plan_result["status"] == "error"
    assert contacts_plan_result["warnings"][0]["code"] == "missing_required_field"
    assert contacts_apply_result["status"] == "error"
    assert contacts_apply_result["warnings"][0]["code"] == "missing_required_field"
    assert photo_result["status"] == "error"
    assert photo_result["warnings"][0]["code"] == "invalid_handle"
    assert photo_export_result["status"] == "error"
    assert photo_export_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_result["status"] == "error"
    assert reminder_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_plan_result["status"] == "error"
    assert reminder_plan_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_apply_result["status"] == "error"
    assert reminder_apply_result["warnings"][0]["code"] == "invalid_handle"


def test_mcp_stdio_lists_read_only_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    async def run() -> None:
        env = os.environ.copy()
        env["LOCAL_APPLE_DATA_LOG_DIR"] = str(tmp_path / "logs")
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "local_apple_data.mcp_server"],
            env=env,
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {
                    "apple_data_health",
                    "apple_data_doctor",
                    "mail_search",
                    "mail_get_metadata",
                    "mail_get_content",
                    "mail_plan_change",
                    "mail_apply_change",
                    "messages_search",
                    "messages_get_chat",
                    "hide_my_email_search",
                    "hide_my_email_get_alias",
                    "voice_memos_search",
                    "voice_memos_get_recording",
                    "voice_memos_export_audio",
                    "notes_search",
                    "notes_get_metadata",
                    "notes_get_content",
                    "notes_plan_change",
                    "notes_apply_change",
                    "icloud_drive_search",
                    "icloud_drive_get_metadata",
                    "icloud_drive_get_content",
                    "icloud_drive_plan_change",
                    "icloud_drive_apply_change",
                    "calendar_search",
                    "calendar_get_event",
                    "calendar_plan_change",
                    "calendar_apply_change",
                    "contacts_search",
                    "contacts_get",
                    "contacts_plan_change",
                    "contacts_apply_change",
                    "photos_search",
                    "photos_get_asset",
                    "photos_export_asset",
                    "reminders_search",
                    "reminders_due",
                    "reminders_eventkit_search",
                    "reminders_get_content",
                    "reminders_plan_change",
                    "reminders_apply_change",
                }.issubset(names)
                for tool in tools.tools:
                    if tool.name in names:
                        assert tool.annotations is not None
                        if tool.name in {
                            "reminders_apply_change",
                            "icloud_drive_apply_change",
                            "calendar_apply_change",
                            "contacts_apply_change",
                            "notes_apply_change",
                            "mail_apply_change",
                        }:
                            assert tool.annotations.readOnlyHint is False
                        else:
                            assert tool.annotations.readOnlyHint is True
                        assert tool.annotations.destructiveHint is False
                        assert tool.annotations.idempotentHint is True
                        assert tool.annotations.openWorldHint is False

    asyncio.run(run())
