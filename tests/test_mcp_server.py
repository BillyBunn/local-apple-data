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
    calendar_get_event,
    contacts_get,
    hide_my_email_get_alias,
    icloud_drive_get_content,
    icloud_drive_get_metadata,
    mail_get_content,
    mail_get_metadata,
    messages_get_chat,
    notes_get_content,
    notes_get_metadata,
    photos_export_asset,
    photos_get_asset,
    reminders_get_content,
    reminders_plan_change,
    voice_memos_export_audio,
    voice_memos_get_recording,
)


def test_mcp_instructions_preserve_safety_boundaries() -> None:
    assert "metadata-first" in INSTRUCTIONS
    assert "read-only" in INSTRUCTIONS
    assert "Gmail connector" in INSTRUCTIONS
    assert "exact-handle" in INSTRUCTIONS


def test_mcp_tools_use_read_only_annotations() -> None:
    assert READ_ONLY_ANNOTATIONS.readOnlyHint is True
    assert READ_ONLY_ANNOTATIONS.destructiveHint is False
    assert READ_ONLY_ANNOTATIONS.idempotentHint is True
    assert READ_ONLY_ANNOTATIONS.openWorldHint is False


def test_mcp_direct_tool_wrappers_reject_bad_handles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))

    mail_result = mail_get_metadata("bad-handle")
    mail_content_result = mail_get_content("bad-handle")
    messages_result = messages_get_chat("bad-handle")
    hide_my_email_result = hide_my_email_get_alias("bad-handle")
    voice_memos_result = voice_memos_get_recording("bad-handle")
    voice_memos_export_result = voice_memos_export_audio("bad-handle", str(tmp_path / "exports"))
    notes_result = notes_get_metadata("bad-handle")
    notes_content_result = notes_get_content("bad-handle")
    icloud_result = icloud_drive_get_metadata("bad-handle")
    icloud_content_result = icloud_drive_get_content("bad-handle")
    calendar_result = calendar_get_event("bad-handle")
    contact_result = contacts_get("bad-handle")
    photo_result = photos_get_asset("bad-handle")
    photo_export_result = photos_export_asset("bad-handle", str(tmp_path / "exports"))
    reminder_result = reminders_get_content("bad-handle")
    reminder_plan_result = reminders_plan_change(
        "complete",
        handle="bad-handle",
        expected_title="Synthetic reminder",
    )

    assert mail_result["status"] == "error"
    assert mail_content_result["status"] == "error"
    assert mail_content_result["warnings"][0]["code"] == "invalid_handle"
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
    assert icloud_result["status"] == "error"
    assert icloud_result["warnings"][0]["code"] == "invalid_handle"
    assert icloud_content_result["status"] == "error"
    assert icloud_content_result["warnings"][0]["code"] == "invalid_handle"
    assert calendar_result["status"] == "error"
    assert calendar_result["warnings"][0]["code"] == "invalid_handle"
    assert contact_result["status"] == "error"
    assert contact_result["warnings"][0]["code"] == "invalid_handle"
    assert photo_result["status"] == "error"
    assert photo_result["warnings"][0]["code"] == "invalid_handle"
    assert photo_export_result["status"] == "error"
    assert photo_export_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_result["status"] == "error"
    assert reminder_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_plan_result["status"] == "error"
    assert reminder_plan_result["warnings"][0]["code"] == "invalid_handle"


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
                    "icloud_drive_search",
                    "icloud_drive_get_metadata",
                    "icloud_drive_get_content",
                    "calendar_search",
                    "calendar_get_event",
                    "contacts_search",
                    "contacts_get",
                    "photos_search",
                    "photos_get_asset",
                    "photos_export_asset",
                    "reminders_search",
                    "reminders_due",
                    "reminders_eventkit_search",
                    "reminders_get_content",
                    "reminders_plan_change",
                }.issubset(names)
                for tool in tools.tools:
                    if tool.name in names:
                        assert tool.annotations is not None
                        assert tool.annotations.readOnlyHint is True
                        assert tool.annotations.destructiveHint is False
                        assert tool.annotations.idempotentHint is True
                        assert tool.annotations.openWorldHint is False

    asyncio.run(run())
