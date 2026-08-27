from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import local_apple_data.mcp_server as mcp_server
from local_apple_data.adapters.icloud_drive import (
    _directory_identity_sha256 as adapter_directory_identity_sha256,
)
from local_apple_data.adapters.icloud_drive import (
    apply_icloud_drive_change as adapter_apply_icloud_drive_change,
)
from local_apple_data.adapters.icloud_drive import (
    plan_icloud_drive_change as adapter_plan_icloud_drive_change,
)
from local_apple_data.adapters.icloud_drive import (
    search_icloud_drive_metadata as adapter_search_icloud_drive_metadata,
)
from local_apple_data.adapters.messages import (
    get_message_participant as adapter_get_message_participant,
)
from local_apple_data.adapters.messages import (
    list_message_participants as adapter_list_message_participants,
)
from local_apple_data.adapters.messages import (
    search_message_chats as adapter_search_message_chats,
)
from local_apple_data.mcp_server import (
    CLIENT_INSTRUCTION_BUDGET_CHARS,
    mcp,
    DESTRUCTIVE_WRITE_ANNOTATIONS,
    INSTRUCTIONS,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    apple_data_doctor,
    apple_data_health,
    calendar_apply_calendar_change,
    calendar_apply_change,
    calendar_get_calendar,
    calendar_get_event,
    calendar_get_participant,
    calendar_list_calendar_events,
    calendar_list_participants,
    calendar_plan_calendar_change,
    calendar_plan_change,
    calendar_search_calendars,
    contacts_apply_change,
    contacts_search,
    contacts_count,
    contacts_export_archive,
    contacts_get,
    contacts_get_container,
    contacts_get_group,
    contacts_list_container_members,
    contacts_list_group_members,
    contacts_plan_change,
    contacts_search_containers,
    contacts_search_groups,
    freeform_get_board,
    freeform_get_folder,
    freeform_list_child_folders,
    freeform_list_folder_boards,
    icloud_drive_apply_change,
    icloud_drive_export_file,
    hide_my_email_get_alias,
    icloud_drive_get_content,
    icloud_drive_get_metadata,
    icloud_drive_get_root,
    icloud_drive_list_folder,
    icloud_drive_list_tree,
    icloud_drive_plan_change,
    mail_apply_change,
    mail_apply_cleanup,
    mail_apply_mailbox_change,
    mail_build_fts_index,
    mail_create_template,
    mail_delete_template,
    mail_export_attachment,
    mail_get_content,
    mail_get_mailbox,
    mail_get_metadata,
    mail_get_unsubscribe_metadata,
    mail_get_sender,
    mail_get_signature,
    mail_get_template,
    mail_list_attachments,
    mail_list_mailbox_messages,
    mail_plan_change,
    mail_plan_cleanup,
    mail_plan_mailbox_change,
    mail_plan_search_triage,
    mail_search,
    mail_search_advanced,
    mail_search_attachments,
    mail_search_body,
    mail_search_fts,
    mail_search_mailboxes,
    mail_search_senders,
    mail_search_signatures,
    mail_search_templates,
    messages_export_attachment,
    messages_get_chat,
    messages_get_participant,
    messages_list_attachments,
    messages_list_participants,
    messages_plan_change,
    messages_apply_change,
    music_get_playlist,
    music_get_track,
    music_list_playlist_tracks,
    notes_apply_change,
    notes_export_attachment,
    notes_get_content,
    notes_get_folder,
    notes_get_metadata,
    notes_list_attachments,
    notes_list_folder_items,
    notes_list_folder_tree,
    notes_plan_change,
    photos_export_asset,
    photos_apply_change,
    photos_get_asset,
    photos_list_album_assets,
    photos_plan_change,
    podcasts_get_episode,
    podcasts_get_show,
    podcasts_list_episodes,
    reminders_apply_list_change,
    reminders_apply_change,
    reminders_get_content,
    reminders_get_list,
    reminders_list_items,
    reminders_list_lists,
    reminders_plan_list_change,
    reminders_plan_change,
    reminders_search_lists,
    safari_get_folder,
    safari_get_item,
    safari_list_folder_items,
    shortcuts_apply_run,
    shortcuts_get_item,
    shortcuts_list_folder_items,
    shortcuts_plan_run,
    tv_get_item,
    tv_get_playlist,
    tv_list_playlist_items,
    voice_memos_export_audio,
    voice_memos_get_recording,
)
from local_apple_data.handles import make_int_handle, make_opaque_handle


def _content_sha(text: str) -> str:
    import hashlib

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
                service TEXT,
                attributedBody BLOB
            );
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
            INSERT INTO chat VALUES
              (1, 'mcp-chat-guid-1', 'Synthetic MCP Chat', 'iMessage');
            INSERT INTO handle VALUES (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES
              (10, 'Synthetic MCP message', 802310400, 0, 7, 'iMessage', NULL);
            INSERT INTO chat_message_join VALUES (1, 10);
            """
        )


def test_mcp_instructions_preserve_safety_boundaries() -> None:
    assert "metadata-first" in INSTRUCTIONS
    assert "bounded" in INSTRUCTIONS
    assert "Gmail connector" in INSTRUCTIONS
    assert "exact-handle" in INSTRUCTIONS
    assert "attachment export" in INSTRUCTIONS
    assert "approval token" in INSTRUCTIONS
    assert "Outbound Mail may use bounded caller-selected local attachments" in INSTRUCTIONS
    assert "output returns no paths or bytes" in INSTRUCTIONS
    assert "optional local attachments" in (mail_plan_change.__doc__ or "")
    assert "accepted for draft/send/reply/reply-all/forward" in (mail_apply_change.__doc__ or "")


# Clients may truncate the server instructions string, and the model has no way to
# recover what was dropped. That is how the mutation gating rule went unread for its
# entire life while sitting last in the string. These tests turn a silent loss into a
# failing build. The budget lives in src next to the string it governs.
APPLY_SURFACE_SENTENCE_START = "The only apply-capable mutation surfaces are "


def test_mutation_gating_rule_survives_client_truncation() -> None:
    delivered = INSTRUCTIONS[:CLIENT_INSTRUCTION_BUDGET_CHARS]
    assert "approval token" in delivered
    assert "explicit confirmation" in delivered
    # The rule must lead, not merely appear: a model that stops reading early still gets it.
    assert delivered.index("approval token") < 200


def test_instruction_body_before_apply_enumeration_survives_truncation() -> None:
    enumeration_start = INSTRUCTIONS.index(APPLY_SURFACE_SENTENCE_START)
    # Everything before the apply-surface enumeration is behavioural guidance that is not
    # recoverable from tools/list: the Gmail/IMAP routing prohibition, metadata-first,
    # no-broad-dumps, exact-handle discipline, date bounds, and the attachment rules.
    # The enumeration itself is required verbatim in this file by
    # scripts/audit_mutation_gates.py and is redundant with tools/list, so it is the only
    # part that may fall beyond the cut. If this fails, shorten the body rather than
    # raising the budget -- the budget exists because clients cut, not because we chose to.
    assert enumeration_start <= CLIENT_INSTRUCTION_BUDGET_CHARS, (
        f"instruction body is {enumeration_start} chars; only the first "
        f"{CLIENT_INSTRUCTION_BUDGET_CHARS} are guaranteed to reach a model"
    )
    for clause in (
        "Do not use Gmail connector paths",
        "metadata-first",
        "Do not request broad dumps",
        "exact-handle",
        "require date bounds",
        "attachment export",
    ):
        assert clause in INSTRUCTIONS[:CLIENT_INSTRUCTION_BUDGET_CHARS]


def test_served_instructions_match_the_reviewed_constant() -> None:
    # The tests above assert on the constant; this one asserts the server actually hands
    # that constant to FastMCP, so a future edit cannot pass the budget tests while
    # serving something else.
    assert mcp.instructions == INSTRUCTIONS


def test_mcp_tools_use_read_only_annotations() -> None:
    assert READ_ONLY_ANNOTATIONS.readOnlyHint is True
    assert READ_ONLY_ANNOTATIONS.destructiveHint is False
    assert READ_ONLY_ANNOTATIONS.idempotentHint is True
    assert READ_ONLY_ANNOTATIONS.openWorldHint is False
    assert WRITE_ANNOTATIONS.readOnlyHint is False
    assert WRITE_ANNOTATIONS.destructiveHint is False
    assert WRITE_ANNOTATIONS.idempotentHint is True
    assert WRITE_ANNOTATIONS.openWorldHint is False
    assert DESTRUCTIVE_WRITE_ANNOTATIONS.readOnlyHint is False
    assert DESTRUCTIVE_WRITE_ANNOTATIONS.destructiveHint is True
    assert DESTRUCTIVE_WRITE_ANNOTATIONS.idempotentHint is False
    assert DESTRUCTIVE_WRITE_ANNOTATIONS.openWorldHint is False


def test_mcp_messages_participant_wrappers_preserve_exact_detail_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    chat = adapter_search_message_chats("MCP", db_path=db_path)["results"][0]

    def list_with_db(handle: str, limit: int = 20) -> dict:
        return adapter_list_message_participants(handle, db_path=db_path, limit=limit)

    def get_with_db(chat_handle: str, participant_handle: str) -> dict:
        return adapter_get_message_participant(
            chat_handle,
            participant_handle,
            db_path=db_path,
        )

    monkeypatch.setattr(mcp_server, "list_message_participants", list_with_db)
    monkeypatch.setattr(mcp_server, "get_message_participant", get_with_db)

    listing = messages_list_participants(chat["handle"])
    participant = listing["results"][0]
    detail = messages_get_participant(chat["handle"], participant["handle"])
    invalid = messages_get_participant(
        chat["handle"],
        "messages:participant:v1:bad",
    )

    assert listing["status"] == "ok"
    assert participant["handle"].startswith("messages:participant:v1:")
    assert "id_preview" not in participant
    assert "participant_id" not in participant
    assert "identifier" not in str(participant)
    assert "+15550100" not in str(listing)
    assert detail["status"] == "ok"
    assert detail["result"]["participant_id"] == "+15550100"
    assert invalid["status"] == "error"
    assert invalid["warnings"][0]["code"] == "invalid_handle"
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "+15550100" not in log_text
    assert "messages:participant:v1:" not in log_text


def test_mcp_calendar_all_day_plan_and_apply_bind_flags_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic all day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T00:00:00Z",
        end_date="2026-06-06T00:00:00Z",
        all_day=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["all_day"] is True
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["all_day"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_alarm_offsets_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[0, -10],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic alarmed event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[0, -10],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_absolute_alarms_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic absolute alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic absolute alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["alarm_kind"] == "absolute"
    assert plan_result["preview"]["proposed"]["alarm_absolute_dates"] == [
        "2026-06-05T16:45:00Z"
    ]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["alarm_absolute_dates"] == [
        "2026-06-05T16:45:00Z"
    ]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_audio_alarm_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic audio alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_sound_name="Glass",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["alarm_sound_name"] == "Glass"
    assert plan_result["preview"]["proposed"]["alarm_action"] == "audio"
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["alarm_sound_name"] == "Glass"
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_email_alarm_plan_and_apply_hash_without_eventkit() -> None:
    expected_sha = hashlib.sha256(b"notify@example.invalid").hexdigest()
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="Notify@Example.Invalid",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic email alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_offsets_minutes=[-10],
        alarm_email_address="Notify@Example.Invalid",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert plan_result["preview"]["proposed"]["alarm_action"] == "email"
    assert "notify@example.invalid" not in json.dumps(plan_result, sort_keys=True)
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["alarm_email_address_sha256"] == expected_sha
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_geofence_alarm_plan_and_apply_bind_without_eventkit() -> None:
    location = {
        "title": "Synthetic Gate",
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 75,
    }
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic geofence alarm event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        alarm_proximity="enter",
        alarm_structured_location=location,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["alarm_kind"] == "geofence"
    assert plan_result["preview"]["proposed"]["alarm_action"] == "geofence"
    assert plan_result["preview"]["proposed"]["alarm_proximity"] == "enter"
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["alarm_proximity"] == "enter"
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=2,
        recurrence_count=3,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=2,
        recurrence_count=3,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 2,
        "count": 3,
        "recurrence_present": True,
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence_present"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_recurrence_end_date_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date="2026-08-01T17:00:00Z",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic end-date recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_end_date="2026-08-01T17:00:00Z",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "end_date": "2026-08-01T17:00:00Z",
        "recurrence_present": True,
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_unbounded_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_unbounded=True,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic unbounded recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=1,
        recurrence_unbounded=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 1,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_month_day_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic month-day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_days=[1, 15, -1],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic month-day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_days=[1, 15, -1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_days": [-1, 1, 15],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic monthly weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": ["monday", "friday"],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_set_positions_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic set-position recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=weekdays,
        recurrence_set_positions=[-1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "weekdays": weekdays,
        "set_positions": [-1],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_monthly_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    recurrence_month_weekdays = [
        {"weekday": "tuesday", "week_number": 3},
        {"weekday": "friday", "week_number": -1},
    ]
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic nth weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic nth weekday recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "monthly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "month_weekdays": [
            {"weekday": "friday", "week_number": -1},
            {"weekday": "tuesday", "week_number": 3},
        ],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_monthly_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    recurrence_month_weekdays = [
        {"weekday": "tuesday", "week_number": 3},
        {"weekday": "friday", "week_number": -1},
    ]
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated nth weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated nth weekday recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_month_weekdays=recurrence_month_weekdays,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["month_weekdays"] == [
        {"weekday": "friday", "week_number": -1},
        {"weekday": "tuesday", "week_number": 3},
    ]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_yearly_month_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic yearly month recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic yearly month recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_yearly_month_day_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_days=[15, 1, -1],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic yearly month day event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_days=[15, 1, -1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_months": [1, 7, 12],
        "year_month_days": [-1, 1, 15],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_yearly_month_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    recurrence_year_month_weekdays = [
        {"weekday": "monday", "week_number": 2},
        {"weekday": "friday", "week_number": -1},
    ]
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic yearly month nth weekday event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
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
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_yearly_day_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic yearly day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_days=[100, 1, -1],
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic yearly day recurring event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_days=[100, 1, -1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "yearly",
        "interval": 1,
        "count": 4,
        "recurrence_present": True,
        "year_days": [-1, 1, 100],
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_yearly_month_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_monthly_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated monthly weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated monthly weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="monthly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["weekdays"] == [
        "monday",
        "friday",
    ]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_yearly_month_day_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month day event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_days=[15, 1, -1],
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month day event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_days=[15, 1, -1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    assert plan_result["preview"]["proposed"]["recurrence"]["year_month_days"] == [
        -1,
        1,
        15,
    ]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_yearly_month_nth_weekday_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    recurrence_year_month_weekdays = [
        {"weekday": "monday", "week_number": 2},
        {"weekday": "friday", "week_number": -1},
    ]
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month nth weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly month nth weekday event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_year_months=[12, 1, 7],
        recurrence_year_month_weekdays=recurrence_year_month_weekdays,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["year_months"] == [1, 7, 12]
    assert plan_result["preview"]["proposed"]["recurrence"]["year_month_weekdays"] == [
        {"weekday": "friday", "week_number": -1},
        {"weekday": "monday", "week_number": 2},
    ]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_yearly_week_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly week recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        recurrence_year_weeks=[26, 1, -1],
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated yearly week recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="yearly",
        recurrence_interval=1,
        recurrence_count=4,
        recurrence_weekdays=["monday", "friday"],
        recurrence_year_weeks=[26, 1, -1],
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"][
        "recurrence_present"
    ] is False
    assert plan_result["preview"]["proposed"]["recurrence"]["weekdays"] == [
        "monday",
        "friday",
    ]
    assert plan_result["preview"]["proposed"]["recurrence"]["year_weeks"] == [-1, 1, 26]
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_structured_location_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        structured_location={
            "title": "Synthetic Structured Room",
            "latitude": 37.33182,
            "longitude": -122.03118,
            "radius_meters": 25,
        },
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic structured event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        structured_location={
            "title": "Synthetic Structured Room",
            "latitude": 37.33182,
            "longitude": -122.03118,
            "radius_meters": 25,
        },
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["structured_location"] == {
        "title": "Synthetic Structured Room",
        "geo_present": True,
        "latitude": 37.33182,
        "longitude": -122.03118,
        "radius_meters": 25.0,
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["structured_location"] == plan_result[
        "preview"
    ]["proposed"]["structured_location"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_clear_structured_location_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    expected_structured_location = {"title": "Synthetic Room"}
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured_location,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_structured_location=expected_structured_location,
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_structured_location=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["target"]["expected_state"]["structured_location"] == {
        "title": "Synthetic Room",
        "geo_present": False,
    }
    assert plan_result["preview"]["proposed"]["structured_location_clear_requested"] is True
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["structured_location_clear_requested"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_count=6,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 2,
        "count": 6,
        "recurrence_present": True,
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence_present"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_unbounded_recurrence_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated unbounded recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_unbounded=True,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic updated unbounded recurring event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        recurrence_frequency="weekly",
        recurrence_interval=2,
        recurrence_unbounded=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["recurrence"] == {
        "frequency": "weekly",
        "interval": 2,
        "count": 0,
        "unbounded": True,
        "recurrence_present": True,
    }
    assert plan_result["preview"]["target"]["expected_state"]["recurrence_expected"] is True
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["recurrence"] == plan_result["preview"][
        "proposed"
    ]["recurrence"]
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_update_recurring_occurrence_fails_closed_without_identity() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic occurrence update",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic occurrence update",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_update_scope="this-event",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "error"
    assert plan_result["preview"] is None
    assert plan_result["mutation_applied"] is False
    assert plan_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"] is None
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }


def test_mcp_calendar_clear_recurrence_fails_closed_without_occurrence_identity() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "error"
    assert plan_result["preview"] is None
    assert plan_result["mutation_applied"] is False
    assert plan_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"] is None
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }


def test_mcp_calendar_mid_series_clear_recurrence_fails_closed_without_identity() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        clear_recurrence=True,
        recurrence_update_scope="future-events",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "error"
    assert plan_result["preview"] is None
    assert plan_result["mutation_applied"] is False
    assert plan_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"] is None
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }


def test_mcp_calendar_mid_series_recurrence_replacement_fails_closed_without_identity() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_count=4,
        recurrence_update_scope="future-events",
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        title="Synthetic planning event",
        start_date="2026-06-03T17:00:00Z",
        end_date="2026-06-03T18:00:00Z",
        recurrence_frequency="daily",
        recurrence_count=4,
        recurrence_update_scope="future-events",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "error"
    assert plan_result["preview"] is None
    assert plan_result["mutation_applied"] is False
    assert plan_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"] is None
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }


def test_mcp_calendar_delete_recurring_occurrence_fails_closed_without_occurrence_identity() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    plan_result = calendar_plan_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
    )
    apply_result = calendar_apply_change(
        "delete",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        recurrence_delete_scope="this-event",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "error"
    assert plan_result["preview"] is None
    assert plan_result["mutation_applied"] is False
    assert plan_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }
    assert apply_result["status"] == "error"
    assert apply_result["preview"] is None
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] in {
        "calendar_access_unavailable",
        "missing_occurrence_identity",
        "target_not_found",
    }


def test_mcp_calendar_event_url_plan_and_apply_bind_without_eventkit() -> None:
    event_url = "tel:+15551234567"
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        event_url=event_url,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["event_url_requested"] is True
    assert plan_result["preview"]["proposed"]["event_url_scheme"] == "tel"
    assert plan_result["preview"]["proposed"]["event_url_domain"] == ""
    assert event_url not in str(plan_result)
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["event_url_requested"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_clear_event_url_plan_and_apply_bind_without_eventkit() -> None:
    handle = make_opaque_handle("calendar:event", "event-1")
    expected_sha = hashlib.sha256(
        "https://meet.example.invalid/current?id=42".encode("utf-8")
    ).hexdigest()
    plan_result = calendar_plan_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
    )
    apply_result = calendar_apply_change(
        "update",
        handle=handle,
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256=expected_sha,
        title="Synthetic cleared URL event",
        start_date="2026-06-03T19:00:00Z",
        end_date="2026-06-03T20:00:00Z",
        clear_event_url=True,
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["event_url_clear_requested"] is True
    assert plan_result["preview"]["proposed"]["event_url_requested"] is False
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["event_url_clear_requested"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_event_url_rejects_operation_mismatches() -> None:
    create_result = calendar_plan_change(
        "create",
        title="Synthetic URL event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        expected_event_url_present=True,
        expected_event_url_sha256="a" * 64,
    )
    delete_result = calendar_plan_change(
        "delete",
        handle="calendar:event:v1:example",
        expected_title="Synthetic planning event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-03T17:00:00Z",
        expected_end_date="2026-06-03T18:00:00Z",
        event_url="http://meet.example.invalid/runtime?id=42",
    )

    assert create_result["status"] == "error"
    assert create_result["warnings"][0]["code"] == "unsupported_expected_state_for_operation"
    assert delete_result["status"] == "error"
    assert delete_result["warnings"][0]["code"] == "unsupported_event_url_for_operation"


def test_mcp_calendar_availability_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic free event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        availability="free",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["availability"] == 1
    assert plan_result["preview"]["proposed"]["availability_name"] == "free"
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["availability_requested"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_date_only_plan_and_apply_bind_without_eventkit() -> None:
    plan_result = calendar_plan_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic date-only event",
        calendar_title="Synthetic Calendar",
        start_date="2026-06-05",
        end_date="2026-06-06",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert plan_result["preview"]["proposed"]["all_day"] is True
    assert plan_result["preview"]["proposed"]["date_only_input"] is True
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["all_day"] is True
    assert apply_result["preview"]["proposed"]["date_only_input"] is True
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_default_calendar_flag_forwards_to_adapter(monkeypatch) -> None:
    token = "calendar-apply:v1:synthetic-default-calendar-token"
    calendar_handle = "calendar:calendar:v1:synthetic-default"

    def fake_plan_calendar_change(operation: str, **kwargs):
        assert operation == "create"
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
            "read_back": {"target_calendar_verified": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_calendar_change", fake_plan_calendar_change)
    monkeypatch.setattr(mcp_server, "apply_calendar_change", fake_apply_calendar_change)

    plan_result = calendar_plan_change(
        "create",
        title="Synthetic default-calendar event",
        use_default_calendar=True,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )
    apply_result = calendar_apply_change(
        "create",
        title="Synthetic default-calendar event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
        approval_token=token,
        confirm_apply=True,
    )

    assert plan_result["preview"]["target"]["target_mode"] == "calendar_handle"
    assert plan_result["preview"]["default_calendar_resolution"]["use_default_calendar"] is True
    assert apply_result["read_back"]["target_calendar_verified"] is True


def test_mcp_calendar_target_calendar_handles_bind_without_eventkit() -> None:
    calendar_handle = make_opaque_handle("calendar:calendar", "calendar-2")
    event_handle = make_opaque_handle("calendar:event", "event-1")
    empty_search = calendar_search_calendars()
    invalid_detail = calendar_get_calendar("bad-handle")
    create_plan = calendar_plan_change(
        "create",
        title="Synthetic handle event",
        calendar_handle=calendar_handle,
        start_date="2026-06-05T17:00:00Z",
        end_date="2026-06-05T18:00:00Z",
    )
    update_plan = calendar_plan_change(
        "update",
        handle=event_handle,
        target_calendar_handle=calendar_handle,
        expected_title="Synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic moved event",
        start_date="2026-06-05T19:00:00Z",
        end_date="2026-06-05T20:00:00Z",
        time_zone="America/New_York",
    )
    apply_result = calendar_apply_change(
        "update",
        handle=event_handle,
        target_calendar_handle=calendar_handle,
        expected_title="Synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic moved event",
        start_date="2026-06-05T19:00:00Z",
        end_date="2026-06-05T20:00:00Z",
        time_zone="America/New_York",
        approval_token="calendar-apply:v1:bad",
        confirm_apply=True,
    )

    assert empty_search["status"] == "error"
    assert empty_search["warnings"][0]["code"] == "empty_query"
    assert invalid_detail["status"] == "error"
    assert invalid_detail["warnings"][0]["code"] == "invalid_handle"
    assert create_plan["status"] == "ok"
    assert create_plan["preview"]["target"]["calendar_handle"] == calendar_handle
    assert update_plan["status"] == "ok"
    assert update_plan["preview"]["proposed"]["target_calendar_handle"] == calendar_handle
    assert update_plan["preview"]["proposed"]["calendar_move_requested"] is True
    assert update_plan["preview"]["target"]["expected_state"]["time_zone"] == "America/Los_Angeles"
    assert update_plan["preview"]["proposed"]["time_zone"] == "America/New_York"
    assert apply_result["status"] == "error"
    assert apply_result["preview"]["proposed"]["target_calendar_handle"] == calendar_handle
    assert apply_result["preview"]["proposed"]["time_zone"] == "America/New_York"
    assert apply_result["warnings"][0]["code"] == "invalid_approval_token"


def test_mcp_calendar_target_calendar_success_wrappers_forward_exact_inputs(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    calendar_handle = make_opaque_handle("calendar:calendar", "calendar-2")
    event_handle = make_opaque_handle("calendar:event", "event-1")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_search(query: str, *, limit: int = 20, include_default: bool = False) -> dict:
        calls.append(("search", {"query": query, "limit": limit, "include_default": include_default}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"output_tier": "metadata"},
            "results": [{"handle": calendar_handle, "title": "Synthetic Focus"}],
            "result_count": 1,
            "warnings": [],
        }

    def fake_get(handle: str) -> dict:
        calls.append(("get", {"handle": handle}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"output_tier": "metadata"},
            "result": {"handle": handle, "title": "Synthetic Focus"},
            "result_count": 1,
            "warnings": [],
        }

    def fake_events(handle: str, *, start_date: str, end_date: str, limit: int = 20) -> dict:
        calls.append(
            (
                "events",
                {
                    "handle": handle,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                },
            )
        )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "privacy": {"output_tier": "metadata"},
            "query": {
                "scope": "selected_calendar_events",
                "calendar_handle": handle,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
            "calendar": {"handle": handle, "title": "Synthetic Focus"},
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    def fake_plan(operation: str, **kwargs: object) -> dict:
        calls.append(("plan", {"operation": operation, **kwargs}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "mode": "plan",
            "preview": {
                "operation": operation,
                "proposed": {"target_calendar_handle": kwargs.get("target_calendar_handle")},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs: object) -> dict:
        calls.append(("apply", {"operation": operation, **kwargs}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "mode": "apply",
            "read_back": {
                "handle": event_handle,
                "calendar_title": "Synthetic Focus",
                "target_calendar_handle": kwargs.get("target_calendar_handle"),
                "target_calendar_verified": True,
            },
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "search_calendar_calendars", fake_search)
    monkeypatch.setattr(mcp_server, "get_calendar_calendar", fake_get)
    monkeypatch.setattr(mcp_server, "list_calendar_events_for_calendar", fake_events)
    monkeypatch.setattr(mcp_server, "plan_calendar_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_calendar_change", fake_apply)

    search_result = calendar_search_calendars("Focus", limit=5, include_default=True)
    detail_result = calendar_get_calendar(calendar_handle)
    events_result = calendar_list_calendar_events(
        calendar_handle,
        "2026-06-01T00:00:00Z",
        "2026-07-01T00:00:00Z",
        limit=5,
    )
    plan_result = calendar_plan_change(
        "update",
        handle=event_handle,
        target_calendar_handle=calendar_handle,
        expected_title="Synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic moved event",
        start_date="2026-06-05T19:00:00Z",
        end_date="2026-06-05T20:00:00Z",
        time_zone="America/New_York",
    )
    apply_result = calendar_apply_change(
        "update",
        approval_token="calendar-apply:v1:test",
        handle=event_handle,
        target_calendar_handle=calendar_handle,
        expected_title="Synthetic event",
        expected_calendar_title="Synthetic Calendar",
        expected_start_date="2026-06-05T17:00:00Z",
        expected_end_date="2026-06-05T18:00:00Z",
        expected_time_zone="America/Los_Angeles",
        title="Synthetic moved event",
        start_date="2026-06-05T19:00:00Z",
        end_date="2026-06-05T20:00:00Z",
        time_zone="America/New_York",
        confirm_apply=True,
    )

    assert search_result["status"] == "ok"
    assert detail_result["status"] == "ok"
    assert events_result["status"] == "ok"
    assert events_result["query"]["calendar_handle"] == calendar_handle
    assert plan_result["status"] == "ok"
    assert apply_result["status"] == "ok"
    assert apply_result["read_back"]["target_calendar_handle"] == calendar_handle
    assert apply_result["read_back"]["target_calendar_verified"] is True
    assert calls[0] == ("search", {"query": "Focus", "limit": 5, "include_default": True})
    assert calls[1] == ("get", {"handle": calendar_handle})
    assert calls[2] == (
        "events",
        {
            "handle": calendar_handle,
            "start_date": "2026-06-01T00:00:00Z",
            "end_date": "2026-07-01T00:00:00Z",
            "limit": 5,
        },
    )
    assert calls[3][0] == "plan"
    assert calls[3][1]["target_calendar_handle"] == calendar_handle
    assert calls[3][1]["expected_time_zone"] == "America/Los_Angeles"
    assert calls[3][1]["time_zone"] == "America/New_York"
    assert calls[4][0] == "apply"
    assert calls[4][1]["approval_token"] == "calendar-apply:v1:test"
    assert calls[4][1]["confirm_apply"] is True
    assert calls[4][1]["target_calendar_handle"] == calendar_handle
    assert calls[4][1]["expected_time_zone"] == "America/Los_Angeles"
    assert calls[4][1]["time_zone"] == "America/New_York"


def test_mcp_calendar_calendar_management_wrappers_forward_exact_inputs(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    source_calendar_handle = make_opaque_handle("calendar:calendar", "calendar-1")
    target_calendar_handle = make_opaque_handle("calendar:calendar", "calendar-test")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_plan(operation: str, **kwargs: object) -> dict:
        calls.append(("plan", {"operation": operation, **kwargs}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "mode": "plan",
            "preview": {"operation": operation},
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs: object) -> dict:
        calls.append(("apply", {"operation": operation, **kwargs}))
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "mode": "apply",
            "operation": operation,
            "read_back": {"source_calendar_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_calendar_calendar_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_calendar_calendar_change", fake_apply)

    plan_result = calendar_plan_calendar_change(
        "create-calendar",
        source_calendar_handle=source_calendar_handle,
        calendar_title="LAD-TEST-mcp",
    )
    apply_result = calendar_apply_calendar_change(
        "create-calendar",
        approval_token="calendar-apply:v1:test",
        source_calendar_handle=source_calendar_handle,
        calendar_title="LAD-TEST-mcp",
        confirm_apply=True,
    )
    delete_plan_result = calendar_plan_calendar_change(
        "delete-calendar",
        calendar_handle=target_calendar_handle,
    )
    delete_apply_result = calendar_apply_calendar_change(
        "delete-calendar",
        approval_token="calendar-apply:v1:delete",
        calendar_handle=target_calendar_handle,
        confirm_apply=True,
    )

    assert plan_result["status"] == "ok"
    assert apply_result["status"] == "ok"
    assert delete_plan_result["status"] == "ok"
    assert delete_apply_result["status"] == "ok"
    assert calls[0][0] == "plan"
    assert calls[0][1]["operation"] == "create-calendar"
    assert calls[0][1]["source_calendar_handle"] == source_calendar_handle
    assert calls[0][1]["calendar_title"] == "LAD-TEST-mcp"
    assert calls[1][0] == "apply"
    assert calls[1][1]["approval_token"] == "calendar-apply:v1:test"
    assert calls[1][1]["source_calendar_handle"] == source_calendar_handle
    assert calls[1][1]["calendar_title"] == "LAD-TEST-mcp"
    assert calls[1][1]["confirm_apply"] is True
    assert calls[2][0] == "plan"
    assert calls[2][1]["operation"] == "delete-calendar"
    assert calls[2][1]["calendar_handle"] == target_calendar_handle
    assert calls[3][0] == "apply"
    assert calls[3][1]["operation"] == "delete-calendar"
    assert calls[3][1]["approval_token"] == "calendar-apply:v1:delete"
    assert calls[3][1]["calendar_handle"] == target_calendar_handle
    assert calls[3][1]["confirm_apply"] is True


def test_mcp_icloud_drive_plan_create_folder_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    (root / "Packets").mkdir(parents=True)
    parent = adapter_search_icloud_drive_metadata("Packets", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "create_folder",
        parent_handle=parent["handle"],
        filename="MCP Folder",
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "create_folder"
    assert result["preview"]["target"]["expected_parent_identity_sha256"] == adapter_directory_identity_sha256(root / "Packets", root)
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["content"] == "blocked"


def test_mcp_icloud_drive_plan_create_folder_path_components(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    (root / "Packets").mkdir(parents=True)
    parent = adapter_search_icloud_drive_metadata("Packets", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "create_folder_path",
        parent_handle=parent["handle"],
        folder_components=["Client", "Drafts"],
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "create_folder_path"
    assert result["preview"]["target"]["expected_parent_identity_sha256"] == adapter_directory_identity_sha256(root / "Packets", root)
    assert result["preview"]["target"]["folder_components"] == ["Client", "Drafts"]
    assert result["preview"]["proposed"]["component_count"] == 2
    assert result["preview"]["proposed"]["content"] == "blocked"


def test_mcp_icloud_drive_plan_create_folder_path_rejects_expected_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    (root / "Packets").mkdir(parents=True)
    parent = adapter_search_icloud_drive_metadata("Packets", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "create_folder_path",
        parent_handle=parent["handle"],
        folder_components=["Client", "Drafts"],
        expected_current_sha256="a" * 64,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_expected_current_sha256"


def test_mcp_icloud_drive_apply_create_folder_path_components(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    (root / "Packets").mkdir(parents=True)
    parent = adapter_search_icloud_drive_metadata("Packets", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    def apply_with_root(operation: str, **kwargs):
        return adapter_apply_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)
    monkeypatch.setattr(mcp_server, "apply_icloud_drive_change", apply_with_root)

    plan = icloud_drive_plan_change(
        "create_folder_path",
        parent_handle=parent["handle"],
        folder_components=["Client", "Drafts"],
    )
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    result = icloud_drive_apply_change(
        "create_folder_path",
        parent_handle=parent["handle"],
        folder_components=["Client", "Drafts"],
        approval_token=token,
        confirm_apply=True,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["component_count"] == 2
    assert result["read_back"]["final_folder_verified"] is True
    assert (root / "Packets" / "Client" / "Drafts").is_dir()


def test_mcp_icloud_drive_export_file_forwards_output_args(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_export(handle: str, **kwargs: object) -> dict:
        captured["handle"] = handle
        captured.update(kwargs)
        return {"schema_version": 1, "status": "ok", "source": "icloud_drive", "warnings": []}

    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mcp_server, "export_icloud_drive_file", fake_export)

    result = icloud_drive_export_file(
        "icloud:file:v1:selected",
        output_dir=str(tmp_path / "exports"),
        filename="../packet.pdf",
        max_bytes=1234,
    )

    assert result["status"] == "ok"
    assert captured["handle"] == "icloud:file:v1:selected"
    assert captured["output_dir"] == tmp_path / "exports"
    assert captured["filename"] == "../packet.pdf"
    assert captured["max_bytes"] == 1234


def test_mcp_icloud_drive_list_folder_forwards_exact_handle(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_list(handle: str, **kwargs: object) -> dict:
        captured["handle"] = handle
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "icloud_drive",
            "warnings": [],
        }

    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mcp_server, "list_icloud_drive_folder", fake_list)

    result = icloud_drive_list_folder("icloud:file:v1:selected", limit=7)

    assert result["status"] == "ok"
    assert captured == {"handle": "icloud:file:v1:selected", "limit": 7}


def test_mcp_icloud_drive_get_root_forwards_without_content(monkeypatch, tmp_path: Path) -> None:
    called = {"value": False}

    def fake_root() -> dict:
        called["value"] = True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "icloud_drive",
            "privacy": {"content_inspected": False},
            "result": {"handle": "icloud:file:v1:root", "kind": "directory", "is_root": True},
            "warnings": [],
        }

    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mcp_server, "get_icloud_drive_root_metadata", fake_root)

    result = icloud_drive_get_root()

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["result"]["is_root"] is True
    assert called["value"] is True


def test_mcp_icloud_drive_list_tree_forwards_exact_handle(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_tree(handle: str, **kwargs: object) -> dict:
        captured["handle"] = handle
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "icloud_drive",
            "warnings": [],
        }

    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mcp_server, "list_icloud_drive_folder_tree", fake_tree)

    result = icloud_drive_list_tree("icloud:file:v1:selected", depth=3, limit=17)

    assert result["status"] == "ok"
    assert captured == {"handle": "icloud:file:v1:selected", "depth": 3, "limit": 17}


def test_mcp_icloud_drive_plan_trash_text_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/review-packet.md")
    current_sha = "a" * 64

    result = icloud_drive_plan_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "trash_text"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["proposed"]["move_to_trash"] is True
    assert result["preview"]["proposed"]["permanent_delete"] == "blocked"


def test_mcp_icloud_drive_plan_delete_text_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    (root / "Packets").mkdir(parents=True)
    (root / "Packets" / "review-packet.md").write_text("MCP delete text.\n", encoding="utf-8")
    handle = make_opaque_handle("icloud:file", "Packets/review-packet.md")
    current_sha = "a" * 64

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "delete_text"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["proposed"]["permanent_delete"] is True
    assert result["preview"]["proposed"]["trash_fallback"] == "blocked"
    assert result["preview"]["proposed"]["folder_delete"] == "blocked"
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_plan_delete_text_rejects_unsupported_without_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    root.mkdir()
    target = root / "image.bin"
    target.write_bytes(b"\x00\x01")
    handle = make_opaque_handle("icloud:file", "image.bin")
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    assert result["status"] == "error"
    assert result["preview"] is None
    assert result["apply_available"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert "approval" not in result


def test_mcp_icloud_drive_plan_rename_copy_move_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/review-packet.md")
    parent_handle = make_opaque_handle("icloud:file", "Archive")
    current_sha = "a" * 64

    rename = icloud_drive_plan_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    copy = icloud_drive_plan_change(
        "copy_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )
    move = icloud_drive_plan_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
    )

    assert rename["status"] == "ok"
    assert rename["preview"]["operation"] == "rename_text"
    assert rename["preview"]["proposed"]["content_return"] == "blocked"
    assert copy["status"] == "ok"
    assert copy["preview"]["operation"] == "copy_text"
    assert copy["preview"]["proposed"]["source_mutation"] == "blocked"
    assert move["status"] == "ok"
    assert move["preview"]["operation"] == "move_text"
    assert move["preview"]["proposed"]["move_to_parent"] == "exact_handle"


def test_mcp_icloud_drive_plan_rename_copy_move_file_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/image.bin")
    parent_handle = make_opaque_handle("icloud:file", "Archive")
    current_metadata_sha = "d" * 64

    rename = icloud_drive_plan_change(
        "rename_file",
        handle=handle,
        expected_current_sha256=current_metadata_sha,
        filename="image-renamed.bin",
    )
    copy = icloud_drive_plan_change(
        "copy_file",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_metadata_sha,
        filename="image-copy.bin",
    )
    move = icloud_drive_plan_change(
        "move_file",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_metadata_sha,
    )

    assert rename["status"] == "ok"
    assert rename["preview"]["operation"] == "rename_file"
    assert rename["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert copy["status"] == "ok"
    assert copy["preview"]["operation"] == "copy_file"
    assert copy["preview"]["proposed"]["source_mutation"] == "blocked"
    assert move["status"] == "ok"
    assert move["preview"]["operation"] == "move_file"
    assert move["preview"]["proposed"]["move_to_parent"] == "exact_handle"


def test_mcp_icloud_drive_plan_rename_folder_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/Empty Folder")
    current_metadata_sha = "b" * 64

    result = icloud_drive_plan_change(
        "rename_folder",
        handle=handle,
        expected_current_sha256=current_metadata_sha,
        filename="Renamed Folder",
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "rename_folder"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["empty_folder_required"] is False
    assert result["preview"]["proposed"]["non_empty_allowed"] is True
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_plan_trash_folder_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/Empty Folder")
    current_metadata_sha = "b" * 64

    result = icloud_drive_plan_change(
        "trash_folder",
        handle=handle,
        expected_current_sha256=current_metadata_sha,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "trash_folder"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["move_to_trash"] is True
    assert result["preview"]["proposed"]["empty_folder_required"] is False
    assert result["preview"]["proposed"]["non_empty_allowed"] is True
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_plan_delete_folder_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    root.mkdir()
    (root / "Empty Folder").mkdir()
    item = adapter_search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "delete_folder"
    assert result["preview"]["target"]["handle"] == item["handle"]
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["permanent_delete"] is True
    assert result["preview"]["proposed"]["empty_folder_required"] is False
    assert result["preview"]["proposed"]["non_empty_allowed"] is True
    assert result["preview"]["proposed"]["recursive_delete"] == "bounded_private_tree"
    assert result["preview"]["proposed"]["source_tree_binding"] == "private"
    assert result["preview"]["proposed"]["trash_fallback"] == "blocked"
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_plan_move_folder_without_content_text() -> None:
    handle = make_opaque_handle("icloud:file", "Packets/Empty Folder")
    parent_handle = make_opaque_handle("icloud:file", "Archive")
    current_metadata_sha = "b" * 64

    result = icloud_drive_plan_change(
        "move_folder",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_metadata_sha,
        filename="Moved Folder",
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "move_folder"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["parent_handle"] == parent_handle
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["move_to_parent"] == "exact_handle"
    assert result["preview"]["proposed"]["empty_folder_required"] is False
    assert result["preview"]["proposed"]["non_empty_allowed"] is True
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_plan_copy_folder_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    root.mkdir()
    (root / "Archive").mkdir()
    (root / "Empty Folder").mkdir()
    item = adapter_search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    parent_handle = make_opaque_handle("icloud:file", "Archive")

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)

    result = icloud_drive_plan_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "copy_folder"
    assert result["preview"]["target"]["handle"] == item["handle"]
    assert result["preview"]["target"]["parent_handle"] == parent_handle
    assert result["preview"]["proposed"]["kind"] == "directory"
    assert result["preview"]["proposed"]["copy_to_parent"] == "exact_handle"
    assert result["preview"]["proposed"]["empty_folder_required"] is False
    assert result["preview"]["proposed"]["non_empty_allowed"] is True
    assert result["preview"]["proposed"]["source_mutation"] == "blocked"
    assert result["preview"]["proposed"]["content_return"] == "blocked"


def test_mcp_icloud_drive_apply_rename_copy_move_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    root.mkdir()
    (root / "Archive").mkdir()
    (root / "Empty Folder").mkdir()
    (root / "Empty Folder" / "child.txt").write_text("rename child", encoding="utf-8")
    (root / "Trash Folder").mkdir()
    (root / "Trash Folder" / "child.txt").write_text("trash child", encoding="utf-8")
    (root / "Delete Folder").mkdir()
    (root / "Delete Folder" / "child.txt").write_text("delete child", encoding="utf-8")
    (root / "Move Folder").mkdir()
    (root / "Move Folder" / "child.txt").write_text("move child", encoding="utf-8")
    (root / "Copy Folder").mkdir()
    (root / "review.md").write_text("MCP synthetic text.\n", encoding="utf-8")
    (root / "delete.md").write_text("MCP delete synthetic text.\n", encoding="utf-8")
    (root / "image-rename.bin").write_bytes(b"\x00\x01")
    (root / "image-copy.bin").write_bytes(b"\x02\x03")
    (root / "image-move.bin").write_bytes(b"\x04\x05")
    (root / "image-replace.bin").write_bytes(b"\x08\x09old")
    (root / "image-trash.bin").write_bytes(b"\x0c\x0dmcp-trash")
    (root / "image-delete.bin").write_bytes(b"\x0e\x0fmcp-delete")
    import_source = tmp_path / "mcp-import-source.bin"
    import_payload = b"\x06\x07mcp-import"
    import_source.write_bytes(import_payload)
    replace_source = tmp_path / "mcp-replace-source.bin"
    replace_payload = b"\x0a\x0bmcp-replace"
    replace_source.write_bytes(replace_payload)
    handle = make_opaque_handle("icloud:file", "review.md")
    delete_handle = make_opaque_handle("icloud:file", "delete.md")
    parent_handle = make_opaque_handle("icloud:file", "Archive")
    current_sha = _content_sha("MCP synthetic text.\n")
    delete_sha = _content_sha("MCP delete synthetic text.\n")
    folder_item = adapter_search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    trash_folder_item = adapter_search_icloud_drive_metadata("Trash Folder", root=root)["results"][0]
    delete_folder_item = adapter_search_icloud_drive_metadata("Delete Folder", root=root)["results"][0]
    move_folder_item = adapter_search_icloud_drive_metadata("Move Folder", root=root)["results"][0]
    copy_folder_item = adapter_search_icloud_drive_metadata("Copy Folder", root=root)["results"][0]
    rename_file_item = adapter_search_icloud_drive_metadata("image-rename", root=root)["results"][0]
    copy_file_item = adapter_search_icloud_drive_metadata("image-copy", root=root)["results"][0]
    move_file_item = adapter_search_icloud_drive_metadata("image-move", root=root)["results"][0]
    replace_file_item = adapter_search_icloud_drive_metadata("image-replace", root=root)["results"][0]
    trash_file_item = adapter_search_icloud_drive_metadata("image-trash", root=root)["results"][0]
    delete_file_item = adapter_search_icloud_drive_metadata("image-delete", root=root)["results"][0]

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    def apply_with_root(operation: str, **kwargs):
        return adapter_apply_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)
    monkeypatch.setattr(mcp_server, "apply_icloud_drive_change", apply_with_root)

    copy_plan = icloud_drive_plan_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )
    copy_token = "icloud-drive-apply:v1:" + copy_plan["preview"]["approval"]["approval_fingerprint"]
    copy_result = icloud_drive_apply_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=copy_token,
        confirm_apply=True,
    )
    copy_handle = make_opaque_handle("icloud:file", "review-copy.md")

    rename_plan = icloud_drive_plan_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    rename_token = "icloud-drive-apply:v1:" + rename_plan["preview"]["approval"]["approval_fingerprint"]
    rename_result = icloud_drive_apply_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=rename_token,
        confirm_apply=True,
    )

    move_plan = icloud_drive_plan_change(
        "move_text",
        handle=copy_handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="moved-copy.md",
    )
    move_token = "icloud-drive-apply:v1:" + move_plan["preview"]["approval"]["approval_fingerprint"]
    move_result = icloud_drive_apply_change(
        "move_text",
        handle=copy_handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="moved-copy.md",
        approval_token=move_token,
        confirm_apply=True,
    )

    delete_plan = icloud_drive_plan_change(
        "delete_text",
        handle=delete_handle,
        expected_current_sha256=delete_sha,
    )
    delete_token = "icloud-drive-apply:v1:" + delete_plan["preview"]["approval"]["approval_fingerprint"]
    delete_result = icloud_drive_apply_change(
        "delete_text",
        handle=delete_handle,
        expected_current_sha256=delete_sha,
        approval_token=delete_token,
        confirm_apply=True,
    )

    folder_plan = icloud_drive_plan_change(
        "rename_folder",
        handle=folder_item["handle"],
        expected_current_sha256=folder_item["metadata_sha256"],
        filename="Renamed Folder",
    )
    folder_token = (
        "icloud-drive-apply:v1:"
        + folder_plan["preview"]["approval"]["approval_fingerprint"]
    )
    folder_result = icloud_drive_apply_change(
        "rename_folder",
        handle=folder_item["handle"],
        expected_current_sha256=folder_item["metadata_sha256"],
        filename="Renamed Folder",
        approval_token=folder_token,
        confirm_apply=True,
    )
    trash_folder_plan = icloud_drive_plan_change(
        "trash_folder",
        handle=trash_folder_item["handle"],
        expected_current_sha256=trash_folder_item["metadata_sha256"],
    )
    trash_folder_token = (
        "icloud-drive-apply:v1:"
        + trash_folder_plan["preview"]["approval"]["approval_fingerprint"]
    )
    trash_folder_result = icloud_drive_apply_change(
        "trash_folder",
        handle=trash_folder_item["handle"],
        expected_current_sha256=trash_folder_item["metadata_sha256"],
        approval_token=trash_folder_token,
        confirm_apply=True,
    )
    delete_folder_plan = icloud_drive_plan_change(
        "delete_folder",
        handle=delete_folder_item["handle"],
        expected_current_sha256=delete_folder_item["metadata_sha256"],
    )
    assert delete_folder_plan["preview"]["proposed"]["empty_folder_required"] is False
    assert delete_folder_plan["preview"]["proposed"]["non_empty_allowed"] is True
    assert delete_folder_plan["preview"]["proposed"]["recursive_delete"] == "bounded_private_tree"
    assert delete_folder_plan["preview"]["proposed"]["source_tree_binding"] == "private"
    delete_folder_token = (
        "icloud-drive-apply:v1:"
        + delete_folder_plan["preview"]["approval"]["approval_fingerprint"]
    )
    delete_folder_result = icloud_drive_apply_change(
        "delete_folder",
        handle=delete_folder_item["handle"],
        expected_current_sha256=delete_folder_item["metadata_sha256"],
        approval_token=delete_folder_token,
        confirm_apply=True,
    )
    move_folder_plan = icloud_drive_plan_change(
        "move_folder",
        handle=move_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=move_folder_item["metadata_sha256"],
        filename="Moved Folder",
    )
    move_folder_token = (
        "icloud-drive-apply:v1:"
        + move_folder_plan["preview"]["approval"]["approval_fingerprint"]
    )
    move_folder_result = icloud_drive_apply_change(
        "move_folder",
        handle=move_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=move_folder_item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=move_folder_token,
        confirm_apply=True,
    )
    copy_folder_plan = icloud_drive_plan_change(
        "copy_folder",
        handle=copy_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=copy_folder_item["metadata_sha256"],
        filename="Copied Folder",
    )
    copy_folder_token = (
        "icloud-drive-apply:v1:"
        + copy_folder_plan["preview"]["approval"]["approval_fingerprint"]
    )
    copy_folder_result = icloud_drive_apply_change(
        "copy_folder",
        handle=copy_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=copy_folder_item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=copy_folder_token,
        confirm_apply=True,
    )
    rename_file_plan = icloud_drive_plan_change(
        "rename_file",
        handle=rename_file_item["handle"],
        expected_current_sha256=rename_file_item["metadata_sha256"],
        filename="image-renamed.bin",
    )
    rename_file_token = (
        "icloud-drive-apply:v1:"
        + rename_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    rename_file_result = icloud_drive_apply_change(
        "rename_file",
        handle=rename_file_item["handle"],
        expected_current_sha256=rename_file_item["metadata_sha256"],
        filename="image-renamed.bin",
        approval_token=rename_file_token,
        confirm_apply=True,
    )
    copy_file_plan = icloud_drive_plan_change(
        "copy_file",
        handle=copy_file_item["handle"],
        expected_current_sha256=copy_file_item["metadata_sha256"],
        filename="image-copied.bin",
    )
    copy_file_token = (
        "icloud-drive-apply:v1:"
        + copy_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    copy_file_result = icloud_drive_apply_change(
        "copy_file",
        handle=copy_file_item["handle"],
        expected_current_sha256=copy_file_item["metadata_sha256"],
        filename="image-copied.bin",
        approval_token=copy_file_token,
        confirm_apply=True,
    )
    move_file_plan = icloud_drive_plan_change(
        "move_file",
        handle=move_file_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=move_file_item["metadata_sha256"],
        filename="image-moved.bin",
    )
    move_file_token = (
        "icloud-drive-apply:v1:"
        + move_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    move_file_result = icloud_drive_apply_change(
        "move_file",
        handle=move_file_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=move_file_item["metadata_sha256"],
        filename="image-moved.bin",
        approval_token=move_file_token,
        confirm_apply=True,
    )
    import_file_plan = icloud_drive_plan_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=str(import_source),
        filename="image-imported.bin",
    )
    import_file_token = (
        "icloud-drive-apply:v1:"
        + import_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    import_file_result = icloud_drive_apply_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=str(import_source),
        filename="image-imported.bin",
        approval_token=import_file_token,
        confirm_apply=True,
    )
    replace_file_plan = icloud_drive_plan_change(
        "replace_file",
        handle=replace_file_item["handle"],
        expected_current_sha256=replace_file_item["metadata_sha256"],
        source_file=str(replace_source),
    )
    replace_file_token = (
        "icloud-drive-apply:v1:"
        + replace_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    replace_file_result = icloud_drive_apply_change(
        "replace_file",
        handle=replace_file_item["handle"],
        expected_current_sha256=replace_file_item["metadata_sha256"],
        source_file=str(replace_source),
        approval_token=replace_file_token,
        confirm_apply=True,
    )
    trash_file_plan = icloud_drive_plan_change(
        "trash_file",
        handle=trash_file_item["handle"],
        expected_current_sha256=trash_file_item["metadata_sha256"],
    )
    trash_file_token = (
        "icloud-drive-apply:v1:"
        + trash_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    trash_file_result = icloud_drive_apply_change(
        "trash_file",
        handle=trash_file_item["handle"],
        expected_current_sha256=trash_file_item["metadata_sha256"],
        approval_token=trash_file_token,
        confirm_apply=True,
    )
    delete_file_plan = icloud_drive_plan_change(
        "delete_file",
        handle=delete_file_item["handle"],
        expected_current_sha256=delete_file_item["metadata_sha256"],
    )
    delete_file_token = (
        "icloud-drive-apply:v1:"
        + delete_file_plan["preview"]["approval"]["approval_fingerprint"]
    )
    delete_file_result = icloud_drive_apply_change(
        "delete_file",
        handle=delete_file_item["handle"],
        expected_current_sha256=delete_file_item["metadata_sha256"],
        approval_token=delete_file_token,
        confirm_apply=True,
    )

    assert copy_result["status"] == "ok"
    assert copy_result["read_back"]["copied"] is True
    assert copy_result["read_back"]["source_present"] is True
    assert copy_result["read_back"]["content_text_returned"] is False
    assert rename_result["status"] == "ok"
    assert rename_result["read_back"]["renamed"] is True
    assert rename_result["read_back"]["source_present"] is False
    assert rename_result["read_back"]["content_text_returned"] is False
    assert move_result["status"] == "ok"
    assert move_result["read_back"]["moved"] is True
    assert move_result["read_back"]["source_present"] is False
    assert move_result["read_back"]["content_text_returned"] is False
    assert delete_result["status"] == "ok"
    assert delete_result["read_back"]["permanently_deleted"] is True
    assert delete_result["read_back"]["verified_absent"] is True
    assert delete_result["read_back"]["original_present"] is False
    assert delete_result["read_back"]["trash_path_returned"] is False
    assert delete_result["read_back"]["staging_path_returned"] is False
    assert delete_result["read_back"]["content_text_returned"] is False
    assert delete_result["read_back"]["content_hash_returned"] is False
    assert folder_result["status"] == "ok"
    assert folder_result["read_back"]["renamed"] is True
    assert folder_result["read_back"]["source_present"] is False
    assert folder_result["read_back"]["target_present"] is True
    assert folder_result["read_back"]["content_text_returned"] is False
    assert folder_result["read_back"]["content_hash_returned"] is False
    assert folder_result["read_back"]["empty_folder_confirmed"] is False
    assert folder_result["read_back"]["non_empty_allowed"] is True
    assert (root / "Renamed Folder" / "child.txt").read_text(encoding="utf-8") == "rename child"
    assert trash_folder_result["status"] == "ok"
    assert trash_folder_result["read_back"]["trashed"] is True
    assert trash_folder_result["read_back"]["original_present"] is False
    assert trash_folder_result["read_back"]["content_text_returned"] is False
    assert trash_folder_result["read_back"]["content_hash_returned"] is False
    assert trash_folder_result["read_back"]["empty_folder_confirmed"] is False
    assert trash_folder_result["read_back"]["non_empty_allowed"] is True
    trash_entries = list((root / ".Trash").iterdir())
    assert any(
        entry.is_dir()
        and (entry / "child.txt").exists()
        and (entry / "child.txt").read_text(encoding="utf-8") == "trash child"
        for entry in trash_entries
    )
    assert delete_folder_result["status"] == "ok"
    assert delete_folder_result["read_back"]["permanently_deleted"] is True
    assert delete_folder_result["read_back"]["verified_absent"] is True
    assert delete_folder_result["read_back"]["original_present"] is False
    assert delete_folder_result["read_back"]["content_text_returned"] is False
    assert delete_folder_result["read_back"]["content_hash_returned"] is False
    assert delete_folder_result["read_back"]["staging_path_returned"] is False
    assert delete_folder_result["read_back"]["empty_folder_confirmed"] is False
    assert delete_folder_result["read_back"]["non_empty_allowed"] is True
    delete_folder_response = json.dumps(delete_folder_result)
    assert "child.txt" not in delete_folder_response
    assert "delete child" not in delete_folder_response
    assert move_folder_result["status"] == "ok"
    assert move_folder_result["read_back"]["moved"] is True
    assert move_folder_result["read_back"]["source_present"] is False
    assert move_folder_result["read_back"]["target_present"] is True
    assert move_folder_result["read_back"]["content_text_returned"] is False
    assert move_folder_result["read_back"]["content_hash_returned"] is False
    assert move_folder_result["read_back"]["empty_folder_confirmed"] is False
    assert move_folder_result["read_back"]["non_empty_allowed"] is True
    assert (root / "Archive" / "Moved Folder" / "child.txt").read_text(encoding="utf-8") == "move child"
    assert copy_folder_result["status"] == "ok"
    assert copy_folder_result["read_back"]["copied"] is True
    assert copy_folder_result["read_back"]["source_present"] is True
    assert copy_folder_result["read_back"]["target_present"] is True
    assert copy_folder_result["read_back"]["content_text_returned"] is False
    assert copy_folder_result["read_back"]["content_hash_returned"] is False
    assert copy_folder_result["read_back"]["empty_folder_confirmed"] is True
    assert rename_file_result["status"] == "ok"
    assert rename_file_result["read_back"]["renamed"] is True
    assert rename_file_result["read_back"]["source_present"] is False
    assert rename_file_result["read_back"]["target_present"] is True
    assert rename_file_result["read_back"]["content_text_returned"] is False
    assert rename_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in rename_file_result["read_back"]
    assert copy_file_result["status"] == "ok"
    assert copy_file_result["read_back"]["copied"] is True
    assert copy_file_result["read_back"]["source_present"] is True
    assert copy_file_result["read_back"]["target_present"] is True
    assert copy_file_result["read_back"]["content_text_returned"] is False
    assert copy_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in copy_file_result["read_back"]
    assert move_file_result["status"] == "ok"
    assert move_file_result["read_back"]["moved"] is True
    assert move_file_result["read_back"]["source_present"] is False
    assert move_file_result["read_back"]["target_present"] is True
    assert move_file_result["read_back"]["content_text_returned"] is False
    assert move_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in move_file_result["read_back"]
    assert import_file_plan["status"] == "ok"
    assert import_file_plan["preview"]["operation"] == "import_file"
    assert import_file_plan["preview"]["proposed"]["source_filename"] == "mcp-import-source.bin"
    assert import_file_plan["preview"]["proposed"]["source_size_bytes"] == len(import_payload)
    assert import_file_plan["preview"]["proposed"]["source_path_returned"] is False
    assert import_file_plan["preview"]["proposed"]["source_hash_returned"] is False
    assert str(import_source) not in json.dumps(import_file_plan)
    assert "source_content_sha256" not in json.dumps(import_file_plan)
    assert import_file_result["status"] == "ok"
    assert import_file_result["read_back"]["imported"] is True
    assert import_file_result["read_back"]["target_present"] is True
    assert import_file_result["read_back"]["source_path_returned"] is False
    assert import_file_result["read_back"]["source_hash_returned"] is False
    assert import_file_result["read_back"]["content_text_returned"] is False
    assert import_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in import_file_result["read_back"]
    assert str(import_source) not in json.dumps(import_file_result)
    assert replace_file_plan["status"] == "ok"
    assert replace_file_plan["preview"]["operation"] == "replace_file"
    assert replace_file_plan["preview"]["proposed"]["replace_from_source_filename"] == "mcp-replace-source.bin"
    assert replace_file_plan["preview"]["proposed"]["source_size_bytes"] == len(replace_payload)
    assert replace_file_plan["preview"]["proposed"]["source_path_returned"] is False
    assert replace_file_plan["preview"]["proposed"]["source_hash_returned"] is False
    assert str(replace_source) not in json.dumps(replace_file_plan)
    assert "source_content_sha256" not in json.dumps(replace_file_plan)
    assert replace_file_result["status"] == "ok"
    assert replace_file_result["read_back"]["replaced"] is True
    assert replace_file_result["read_back"]["target_present"] is True
    assert replace_file_result["read_back"]["source_path_returned"] is False
    assert replace_file_result["read_back"]["source_hash_returned"] is False
    assert replace_file_result["read_back"]["content_text_returned"] is False
    assert replace_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in replace_file_result["read_back"]
    assert str(replace_source) not in json.dumps(replace_file_result)
    assert trash_file_plan["status"] == "ok"
    assert trash_file_plan["preview"]["operation"] == "trash_file"
    assert trash_file_plan["preview"]["proposed"]["content_type"] == "regular_file"
    assert trash_file_plan["preview"]["proposed"]["move_to_trash"] is True
    assert trash_file_plan["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert trash_file_result["status"] == "ok"
    assert trash_file_result["read_back"]["trashed"] is True
    assert trash_file_result["read_back"]["original_present"] is False
    assert trash_file_result["read_back"]["trash_path_returned"] is False
    assert trash_file_result["read_back"]["content_text_returned"] is False
    assert trash_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in trash_file_result["read_back"]
    assert delete_file_plan["status"] == "ok"
    assert delete_file_plan["preview"]["operation"] == "delete_file"
    assert delete_file_plan["preview"]["proposed"]["content_type"] == "regular_file"
    assert delete_file_plan["preview"]["proposed"]["permanent_delete"] is True
    assert delete_file_plan["preview"]["proposed"]["recoverable_trash"] == "blocked"
    assert delete_file_plan["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert delete_file_result["status"] == "ok"
    assert delete_file_result["read_back"]["permanently_deleted"] is True
    assert delete_file_result["read_back"]["verified_absent"] is True
    assert delete_file_result["read_back"]["original_present"] is False
    assert delete_file_result["read_back"]["trash_path_returned"] is False
    assert delete_file_result["read_back"]["staging_path_returned"] is False
    assert delete_file_result["read_back"]["content_text_returned"] is False
    assert delete_file_result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in delete_file_result["read_back"]
    assert (root / "review-renamed.md").exists()
    assert (root / "Archive" / "moved-copy.md").exists()
    assert not (root / "delete.md").exists()
    assert (root / "image-renamed.bin").read_bytes() == b"\x00\x01"
    assert (root / "image-copy.bin").read_bytes() == b"\x02\x03"
    assert (root / "image-copied.bin").read_bytes() == b"\x02\x03"
    assert (root / "Archive" / "image-moved.bin").read_bytes() == b"\x04\x05"
    assert (root / "Archive" / "image-imported.bin").read_bytes() == import_payload
    assert import_source.read_bytes() == import_payload
    assert (root / "image-replace.bin").read_bytes() == replace_payload
    assert replace_source.read_bytes() == replace_payload
    assert not (root / "image-trash.bin").exists()
    assert not (root / "image-delete.bin").exists()
    assert not (root / ".local-apple-data-delete-staging").exists()
    assert (root / "Renamed Folder").is_dir()
    assert not (root / "Trash Folder").exists()
    assert not (root / "Delete Folder").exists()
    assert (root / "Archive" / "Moved Folder").is_dir()
    assert (root / "Copy Folder").is_dir()
    assert (root / "Archive" / "Copied Folder").is_dir()
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        handle,
        copy_handle,
        delete_handle,
        parent_handle,
        folder_item["handle"],
        folder_item["metadata_sha256"],
        trash_folder_item["handle"],
        trash_folder_item["metadata_sha256"],
        delete_folder_item["handle"],
        delete_folder_item["metadata_sha256"],
        move_folder_item["handle"],
        move_folder_item["metadata_sha256"],
        copy_folder_item["handle"],
        copy_folder_item["metadata_sha256"],
        rename_file_item["handle"],
        rename_file_item["metadata_sha256"],
        copy_file_item["handle"],
        copy_file_item["metadata_sha256"],
        move_file_item["handle"],
        move_file_item["metadata_sha256"],
        trash_file_item["handle"],
        trash_file_item["metadata_sha256"],
        delete_file_item["handle"],
        delete_file_item["metadata_sha256"],
        current_sha,
        delete_sha,
        copy_token,
        rename_token,
        move_token,
        delete_token,
        folder_token,
        trash_folder_token,
        delete_folder_token,
        move_folder_token,
        copy_folder_token,
        rename_file_token,
        copy_file_token,
        move_file_token,
        import_file_token,
        trash_file_token,
        delete_file_token,
        "MCP synthetic text.",
        "MCP delete synthetic text.",
        "Empty Folder",
        "Renamed Folder",
        "Trash Folder",
        "image-delete.bin",
        "Delete Folder",
        "Move Folder",
        "Moved Folder",
        "Copy Folder",
        "Copied Folder",
        "review.md",
        "review-renamed.md",
        "moved-copy.md",
        "delete.md",
        "image-rename.bin",
        "image-renamed.bin",
        "image-copy.bin",
        "image-copied.bin",
        "image-move.bin",
        "image-moved.bin",
        "image-trash.bin",
        "mcp-import-source.bin",
        "image-imported.bin",
        str(import_source),
        str(root),
    ):
        assert forbidden not in log_text


def test_mcp_icloud_drive_delete_text_rejects_same_content_stale_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    root.mkdir()
    target = root / "delete.md"
    original_text = "MCP stale delete synthetic text.\n"
    target.write_text(original_text, encoding="utf-8")
    handle = make_opaque_handle("icloud:file", "delete.md")
    current_sha = _content_sha(original_text)

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    def apply_with_root(operation: str, **kwargs):
        return adapter_apply_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)
    monkeypatch.setattr(mcp_server, "apply_icloud_drive_change", apply_with_root)

    plan = icloud_drive_plan_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    target.unlink()
    target.write_text(original_text, encoding="utf-8")

    result = icloud_drive_apply_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=token,
        confirm_apply=True,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_text(encoding="utf-8") == original_text
    assert not (root / ".Trash").exists()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_mcp_icloud_drive_apply_copy_folder_without_content_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    root = tmp_path / "CloudDocs"
    root.mkdir()
    (root / "Archive").mkdir()
    (root / "Copy Folder").mkdir()
    copy_folder_item = adapter_search_icloud_drive_metadata("Copy Folder", root=root)["results"][0]
    parent_handle = make_opaque_handle("icloud:file", "Archive")

    def plan_with_root(operation: str, **kwargs):
        return adapter_plan_icloud_drive_change(operation, root=root, **kwargs)

    def apply_with_root(operation: str, **kwargs):
        return adapter_apply_icloud_drive_change(operation, root=root, **kwargs)

    monkeypatch.setattr(mcp_server, "plan_icloud_drive_change", plan_with_root)
    monkeypatch.setattr(mcp_server, "apply_icloud_drive_change", apply_with_root)

    plan = icloud_drive_plan_change(
        "copy_folder",
        handle=copy_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=copy_folder_item["metadata_sha256"],
        filename="Copied Folder",
    )
    token = "icloud-drive-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    result = icloud_drive_apply_change(
        "copy_folder",
        handle=copy_folder_item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=copy_folder_item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=token,
        confirm_apply=True,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["copied"] is True
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert result["read_back"]["empty_folder_confirmed"] is True
    assert (root / "Copy Folder").is_dir()
    assert (root / "Archive" / "Copied Folder").is_dir()
    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    for forbidden in (
        copy_folder_item["handle"],
        copy_folder_item["metadata_sha256"],
        parent_handle,
        token,
        "Copy Folder",
        "Copied Folder",
        str(root),
    ):
        assert forbidden not in log_text


def test_mcp_readiness_tools_redact_unexpected_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fail_health():
        raise OSError(f"permission denied for {tmp_path / 'Library/Mail'}")

    def fail_doctor():
        raise RuntimeError(f"doctor failed at {tmp_path / 'Library/Notes'}")

    monkeypatch.setattr("local_apple_data.mcp_server.build_health", fail_health)
    monkeypatch.setattr("local_apple_data.mcp_server.build_doctor", fail_doctor)

    health_result = apple_data_health()
    doctor_result = apple_data_doctor()

    assert health_result["status"] == "error"
    assert health_result["source"] == "apple_data_health"
    assert health_result["warnings"] == [
        {"code": "mcp_tool_error", "message": "MCP tool failed safely: OSError"}
    ]
    assert doctor_result["status"] == "error"
    assert doctor_result["source"] == "apple_data_doctor"
    assert doctor_result["warnings"] == [
        {"code": "mcp_tool_error", "message": "MCP tool failed safely: RuntimeError"}
    ]
    assert "permission denied" not in str(health_result)
    assert "doctor failed" not in str(doctor_result)
    assert str(tmp_path) not in str(health_result)
    assert str(tmp_path) not in str(doctor_result)


def test_mcp_mail_tools_redact_unexpected_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fail(*args, **kwargs):
        raise RuntimeError(f"mail transport failure at {tmp_path / 'Library/Mail'}")

    cases = [
        ("search_mail_metadata", "mail_search", lambda: mail_search("receipt")),
        (
            "search_mail_body",
            "mail_search_body",
            lambda: mail_search_body("receipt", after="2026-06-26"),
        ),
        (
            "search_mail_attachments",
            "mail_search_attachments",
            lambda: mail_search_attachments("receipt", after="2026-06-26"),
        ),
        (
            "search_mail_advanced",
            "mail_search_advanced",
            lambda: mail_search_advanced("receipt", scopes=["subject"], after="2026-06-26"),
        ),
        (
            "build_mail_fts_index",
            "mail_build_fts_index",
            lambda: mail_build_fts_index(after="2026-06-26", confirm_index=True),
        ),
        (
            "search_mail_fts",
            "mail_search_fts",
            lambda: mail_search_fts("receipt", after="2026-06-26"),
        ),
        ("get_mail_metadata", "mail_get_metadata", lambda: mail_get_metadata("bad")),
        ("search_mail_mailboxes", "mail_search_mailboxes", lambda: mail_search_mailboxes("Inbox")),
        ("get_mail_mailbox", "mail_get_mailbox", lambda: mail_get_mailbox("bad")),
        ("search_mail_senders", "mail_search_senders", lambda: mail_search_senders("sender")),
        ("get_mail_sender", "mail_get_sender", lambda: mail_get_sender("bad")),
        (
            "search_mail_signatures",
            "mail_search_signatures",
            lambda: mail_search_signatures("signature"),
        ),
        ("get_mail_signature", "mail_get_signature", lambda: mail_get_signature("bad")),
        (
            "create_mail_template",
            "mail_create_template",
            lambda: mail_create_template("name", "body"),
        ),
        ("search_mail_templates", "mail_search_templates", lambda: mail_search_templates("name")),
        ("get_mail_template", "mail_get_template", lambda: mail_get_template("bad")),
        ("delete_mail_template", "mail_delete_template", lambda: mail_delete_template("bad")),
        ("get_mail_content", "mail_get_content", lambda: mail_get_content("bad")),
        (
            "get_mail_unsubscribe_metadata",
            "mail_get_unsubscribe_metadata",
            lambda: mail_get_unsubscribe_metadata("bad"),
        ),
        ("list_mail_attachments", "mail_list_attachments", lambda: mail_list_attachments("bad")),
        (
            "export_mail_attachment",
            "mail_export_attachment",
            lambda: mail_export_attachment("bad", "bad", str(tmp_path / "exports")),
        ),
        ("plan_mail_change", "mail_plan_change", lambda: mail_plan_change("create_draft")),
        (
            "apply_mail_change",
            "mail_apply_change",
            lambda: mail_apply_change("create_draft", approval_token="mail-apply:v1:bad"),
        ),
        (
            "plan_mail_search_triage",
            "mail_plan_search_triage",
            lambda: mail_plan_search_triage("mark_read", "receipt"),
        ),
        (
            "plan_mail_mailbox_change",
            "mail_plan_mailbox_change",
            lambda: mail_plan_mailbox_change("create_mailbox"),
        ),
        (
            "apply_mail_mailbox_change",
            "mail_apply_mailbox_change",
            lambda: mail_apply_mailbox_change(
                "create_mailbox",
                approval_token="mail-mailbox-apply:v1:bad",
            ),
        ),
        ("plan_mail_cleanup", "mail_plan_cleanup", lambda: mail_plan_cleanup("empty_trash")),
        (
            "apply_mail_cleanup",
            "mail_apply_cleanup",
            lambda: mail_apply_cleanup("empty_trash", approval_token="mail-cleanup-apply:v1:bad"),
        ),
    ]

    for adapter_name, command, call in cases:
        monkeypatch.setattr(f"local_apple_data.mcp_server.{adapter_name}", fail)
        result = call()
        assert result["status"] == "error", command
        assert result["source"] == command
        assert result["warnings"] == [
            {"code": "mcp_tool_error", "message": "MCP tool failed safely: RuntimeError"}
        ]
        assert "mail transport failure" not in str(result)
        assert str(tmp_path) not in str(result)

    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "mail transport failure" not in log_text
    assert str(tmp_path) not in log_text


def test_mcp_contacts_tools_redact_unexpected_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fail(*args, **kwargs):
        raise RuntimeError(f"contacts transport failure at {tmp_path / 'Library/Application Support/AddressBook'}")

    cases = [
        ("search_contacts", "contacts_search", lambda: contacts_search("Synthetic")),
        ("get_contact", "contacts_get", lambda: contacts_get("bad")),
        ("search_contact_groups", "contacts_search_groups", lambda: contacts_search_groups("Group")),
        ("get_contact_group", "contacts_get_group", lambda: contacts_get_group("bad")),
        (
            "search_contact_containers",
            "contacts_search_containers",
            lambda: contacts_search_containers("iCloud"),
        ),
        ("get_contact_container", "contacts_get_container", lambda: contacts_get_container("bad")),
        (
            "list_contact_container_members",
            "contacts_list_container_members",
            lambda: contacts_list_container_members("bad"),
        ),
        ("count_contacts", "contacts_count", lambda: contacts_count(max_contacts=1)),
        (
            "export_contacts_archive",
            "contacts_export_archive",
            lambda: contacts_export_archive(str(tmp_path / "exports")),
        ),
        ("plan_contact_change", "contacts_plan_change", lambda: contacts_plan_change("create_contact")),
        (
            "apply_contact_change",
            "contacts_apply_change",
            lambda: contacts_apply_change("create_contact", approval_token="contacts-apply:v1:bad"),
        ),
    ]

    for adapter_name, command, call in cases:
        monkeypatch.setattr(f"local_apple_data.mcp_server.{adapter_name}", fail)
        result = call()
        assert result["status"] == "error", command
        assert result["source"] == command
        assert result["warnings"] == [
            {"code": "mcp_tool_error", "message": "MCP tool failed safely: RuntimeError"}
        ]
        assert "contacts transport failure" not in str(result)
        assert str(tmp_path) not in str(result)

    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "contacts transport failure" not in log_text
    assert str(tmp_path) not in log_text


def test_mcp_stdio_mail_error_keeps_contacts_available(tmp_path: Path) -> None:
    runner = tmp_path / "mcp_fault_runner.py"
    runner.write_text(
        """
from local_apple_data import mcp_server

def fail_mail_advanced(*args, **kwargs):
    raise RuntimeError("mail adapter exploded at /private/tmp/Envelope Index")

def fake_count_contacts(*, max_contacts=50000):
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "result_count": 1,
        "result": {"live_count": 1, "count_complete": True},
        "warnings": [],
    }

mcp_server.search_mail_advanced = fail_mail_advanced
mcp_server.count_contacts = fake_count_contacts
mcp_server.main()
""".lstrip(),
        encoding="utf-8",
    )

    async def run() -> tuple[dict[str, object], dict[str, object]]:
        env = os.environ.copy()
        env["LOCAL_APPLE_DATA_LOG_DIR"] = str(tmp_path / "logs")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(runner)],
            env=env,
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mail_result = await session.call_tool(
                    "mail_search_advanced",
                    {
                        "query": "Your",
                        "scopes": ["subject"],
                        "after": "2026-06-26",
                        "before": "2026-06-30",
                        "limit": 1,
                    },
                )
                contacts_result = await session.call_tool("contacts_count", {"max_contacts": 1})
        return (
            json.loads(mail_result.content[0].text),
            json.loads(contacts_result.content[0].text),
        )

    mail_payload, contacts_payload = asyncio.run(run())

    assert mail_payload["status"] == "error"
    assert mail_payload["source"] == "mail_search_advanced"
    assert mail_payload["warnings"] == [
        {"code": "mcp_tool_error", "message": "MCP tool failed safely: RuntimeError"}
    ]
    assert "mail adapter exploded" not in str(mail_payload)
    assert "/private/tmp" not in str(mail_payload)
    assert contacts_payload["status"] == "ok"
    assert contacts_payload["source"] == "contacts"
    assert contacts_payload["result_count"] == 1

    log_text = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "mail adapter exploded" not in log_text
    assert "/private/tmp" not in log_text


def test_mcp_mail_attachment_search_forwards_content_flags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return {"status": "ok", "results": []}

    monkeypatch.setattr("local_apple_data.mcp_server.search_mail_attachments", fake_search)

    result = mail_search_attachments(
        "receipt",
        after="0",
        before="20",
        include_content=True,
        include_ocr=True,
        max_snippet_chars=77,
    )

    assert result["status"] == "ok"
    assert captured["query"] == "receipt"
    assert captured["kwargs"] == {
        "after": "0",
        "before": "20",
        "cursor": "",
        "limit": 20,
        "include_content": True,
        "include_ocr": True,
        "max_snippet_chars": 77,
        "max_seconds": 20,
    }


def test_mcp_mail_fts_wrappers_forward_bounds_and_flags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_build(**kwargs):
        captured["build"] = kwargs
        return {"status": "ok", "result": {"messages_indexed": 1}}

    def fake_search(query: str, **kwargs):
        captured["query"] = query
        captured["search"] = kwargs
        return {"status": "ok", "results": []}

    monkeypatch.setattr("local_apple_data.mcp_server.build_mail_fts_index", fake_build)
    monkeypatch.setattr("local_apple_data.mcp_server.search_mail_fts", fake_search)

    build_result = mail_build_fts_index(
        after="0",
        before="20",
        cursor="2",
        limit=42,
        include_attachments=True,
        include_ocr=True,
        confirm_index=True,
        reset=False,
    )
    search_result = mail_search_fts(
        "receipt",
        scopes=["body", "attachment_content"],
        after="0",
        before="20",
        cursor="10",
        limit=5,
        max_snippet_chars=77,
    )

    assert build_result["status"] == "ok"
    assert search_result["status"] == "ok"
    assert captured["build"] == {
        "after": "0",
        "before": "20",
        "cursor": "2",
        "limit": 42,
        "include_attachments": True,
        "include_ocr": True,
        "confirm_index": True,
        "reset": False,
        "max_seconds": 20,
    }
    assert captured["query"] == "receipt"
    assert captured["search"] == {
        "scopes": ["body", "attachment_content"],
        "after": "0",
        "before": "20",
        "cursor": "10",
        "limit": 5,
        "max_snippet_chars": 77,
    }


def test_mcp_mail_search_forwards_exact_mailbox_handle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_search_mail_metadata(query: str, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "query": {
                "scope": "subject",
                "limit": kwargs["limit"],
                "mailbox_filter": "exact_handle",
                "mailbox_ref": "mailbox-ref",
            },
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "search_mail_metadata", fake_search_mail_metadata)

    result = mail_search(
        "planning",
        limit=7,
        mailbox_handle="mail:mailbox:v1:synthetic",
    )

    assert result["status"] == "ok"
    assert captured == {
        "query": "planning",
        "limit": 7,
        "mailbox_handle": "mail:mailbox:v1:synthetic",
    }


def test_mcp_mail_list_mailbox_messages_forwards_exact_handle_and_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_list_mailbox_messages(handle: str, **kwargs):
        captured["handle"] = handle
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "mail",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "query": {
                "scope": "selected_mailbox_messages",
                "limit": kwargs["limit"],
                "mailbox_filter": "exact_handle",
            },
            "results": [],
            "result_count": 0,
            "content_returned": False,
            "raw_identifier_returned": False,
            "raw_path_returned": False,
            "warnings": [],
        }

    monkeypatch.setattr(
        mcp_server,
        "list_mail_mailbox_messages",
        fake_list_mailbox_messages,
    )

    result = mail_list_mailbox_messages(
        "mail:mailbox:v1:synthetic",
        after="0",
        before="20",
        limit=7,
    )

    assert result["status"] == "ok"
    assert captured == {
        "handle": "mail:mailbox:v1:synthetic",
        "after": "0",
        "before": "20",
        "limit": 7,
    }


def test_mcp_direct_tool_wrappers_reject_bad_handles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))

    mail_result = mail_get_metadata("bad-handle")
    mail_mailbox_result = mail_get_mailbox("bad-handle")
    mail_mailbox_search_result = mail_search_mailboxes("*")
    mail_sender_result = mail_get_sender("bad-handle")
    mail_sender_search_result = mail_search_senders("*")
    mail_signature_result = mail_get_signature("bad-handle")
    mail_signature_search_result = mail_search_signatures("*")
    mail_template_result = mail_get_template("bad-handle")
    mail_template_search_result = mail_search_templates("*")
    mail_body_search_result = mail_search_body("renewal")
    mail_attachment_search_result = mail_search_attachments("receipt")
    mail_advanced_search_result = mail_search_advanced("billing", scopes=["from"])
    mail_fts_build_result = mail_build_fts_index(confirm_index=True)
    mail_fts_search_result = mail_search_fts("renewal")
    mail_content_result = mail_get_content("bad-handle")
    mail_unsubscribe_metadata_result = mail_get_unsubscribe_metadata("bad-handle")
    mail_attachments_result = mail_list_attachments("bad-handle")
    mail_export_result = mail_export_attachment(
        "bad-handle",
        "bad-attachment",
        str(tmp_path / "exports"),
    )
    mail_plan_result = mail_plan_change(
        "create_draft",
        to=[],
        subject="Synthetic draft",
        body_text="Synthetic body.",
    )
    mail_triage_plan_result = mail_plan_change(
        "mark_read",
        message_handle="bad-handle",
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
    messages_attachments_result = messages_list_attachments("bad-handle")
    messages_participants_result = messages_list_participants("bad-handle")
    messages_participant_result = messages_get_participant("bad-handle", "bad-participant")
    messages_export_result = messages_export_attachment(
        "bad-handle",
        "bad-attachment",
        str(tmp_path / "exports"),
    )
    messages_plan_result = messages_plan_change(
        "send_text",
        handle="bad-handle",
        body_text="Synthetic body.",
    )
    messages_file_plan_result = messages_plan_change(
        "send_file",
        handle="bad-handle",
        file_path=str(tmp_path / "missing.pdf"),
    )
    messages_apply_result = messages_apply_change(
        "send_text",
        handle="bad-handle",
        body_text="Synthetic body.",
        approval_token="messages-apply:v1:bad",
        confirm_apply=True,
    )
    hide_my_email_result = hide_my_email_get_alias("bad-handle")
    voice_memos_result = voice_memos_get_recording("bad-handle")
    voice_memos_export_result = voice_memos_export_audio("bad-handle", str(tmp_path / "exports"))
    safari_result = safari_get_item("bad-handle")
    safari_folder_result = safari_get_folder("bad-handle")
    safari_folder_items_result = safari_list_folder_items("bad-handle")
    shortcuts_result = shortcuts_get_item("bad-handle")
    shortcuts_folder_items_result = shortcuts_list_folder_items("bad-handle")
    podcasts_show_result = podcasts_get_show("bad-handle")
    podcasts_episodes_result = podcasts_list_episodes("bad-handle")
    podcasts_episode_result = podcasts_get_episode("bad-handle")
    music_track_result = music_get_track("bad-handle")
    music_playlist_result = music_get_playlist("bad-handle")
    music_playlist_tracks_result = music_list_playlist_tracks("bad-handle")
    tv_item_result = tv_get_item("bad-handle")
    tv_playlist_result = tv_get_playlist("bad-handle")
    tv_playlist_items_result = tv_list_playlist_items("bad-handle")
    freeform_board_result = freeform_get_board("bad-handle")
    freeform_folder_result = freeform_get_folder("bad-handle")
    freeform_folder_boards_result = freeform_list_folder_boards("bad-handle")
    freeform_child_folders_result = freeform_list_child_folders("bad-handle")
    notes_result = notes_get_metadata("bad-handle")
    notes_folder_result = notes_get_folder("bad-handle")
    notes_folder_items_result = notes_list_folder_items("bad-handle")
    notes_folder_tree_result = notes_list_folder_tree("bad-handle")
    notes_content_result = notes_get_content("bad-handle")
    notes_attachments_result = notes_list_attachments("bad-handle")
    notes_export_result = notes_export_attachment("bad-handle", str(tmp_path / "exports"))
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
    calendar_participants_result = calendar_list_participants("bad-handle")
    calendar_participant_result = calendar_get_participant("bad-handle", "bad-handle")
    calendar_target_result = calendar_get_calendar("bad-handle")
    calendar_target_events_result = calendar_list_calendar_events(
        "bad-handle",
        "2026-06-01T00:00:00Z",
        "2026-07-01T00:00:00Z",
    )
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
    photo_album_assets_result = photos_list_album_assets("bad-handle")
    photo_export_result = photos_export_asset("bad-handle", str(tmp_path / "exports"))
    photos_plan_result = photos_plan_change("import", source_file="")
    photos_apply_result = photos_apply_change(
        "import",
        source_file="",
        approval_token="photos-apply:v1:bad",
        confirm_apply=True,
    )
    reminder_result = reminders_get_content("bad-handle")
    reminder_list_result = reminders_get_list("bad-handle")
    reminder_list_items_result = reminders_list_items("bad-handle")
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
    assert mail_mailbox_result["status"] == "error"
    assert mail_mailbox_result["warnings"][0]["code"] == "invalid_mailbox_handle"
    assert mail_mailbox_search_result["status"] == "error"
    assert mail_mailbox_search_result["warnings"][0]["code"] == "broad_query"
    assert mail_sender_result["status"] == "error"
    assert mail_sender_result["warnings"][0]["code"] == "invalid_sender_handle"
    assert mail_sender_search_result["status"] == "error"
    assert mail_sender_search_result["warnings"][0]["code"] == "broad_query"
    assert mail_signature_result["status"] == "error"
    assert mail_signature_result["warnings"][0]["code"] == "invalid_signature_handle"
    assert mail_signature_search_result["status"] == "error"
    assert mail_signature_search_result["warnings"][0]["code"] == "broad_query"
    assert mail_template_result["status"] == "error"
    assert mail_template_result["warnings"][0]["code"] == "invalid_template_handle"
    assert mail_template_search_result["status"] == "error"
    assert mail_template_search_result["warnings"][0]["code"] == "broad_query"
    assert mail_body_search_result["status"] == "error"
    assert mail_body_search_result["warnings"][0]["code"] == "date_range_required"
    assert mail_attachment_search_result["status"] == "error"
    assert mail_attachment_search_result["warnings"][0]["code"] == "date_range_required"
    assert mail_advanced_search_result["status"] == "error"
    assert mail_advanced_search_result["warnings"][0]["code"] == "date_range_required"
    assert mail_fts_build_result["status"] == "error"
    assert mail_fts_build_result["warnings"][0]["code"] == "date_range_required"
    assert mail_fts_search_result["status"] == "error"
    assert mail_fts_search_result["warnings"][0]["code"] == "date_range_required"
    assert mail_content_result["status"] == "error"
    assert mail_content_result["warnings"][0]["code"] == "invalid_handle"
    assert mail_unsubscribe_metadata_result["status"] == "error"
    assert mail_unsubscribe_metadata_result["warnings"][0]["code"] == "invalid_handle"
    assert mail_attachments_result["status"] == "error"
    assert mail_attachments_result["warnings"][0]["code"] == "invalid_handle"
    assert mail_export_result["status"] == "error"
    assert mail_export_result["warnings"][0]["code"] == "invalid_handle"
    assert mail_plan_result["status"] == "error"
    assert mail_plan_result["warnings"][0]["code"] == "missing_to"
    assert mail_triage_plan_result["status"] == "error"
    assert mail_triage_plan_result["warnings"][0]["code"] == "invalid_message_handle"
    assert mail_apply_result["status"] == "error"
    assert mail_apply_result["warnings"][0]["code"] == "invalid_approval_token"
    assert messages_result["status"] == "error"
    assert messages_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_attachments_result["status"] == "error"
    assert messages_attachments_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_participants_result["status"] == "error"
    assert messages_participants_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_participant_result["status"] == "error"
    assert messages_participant_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_export_result["status"] == "error"
    assert messages_export_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_plan_result["status"] == "error"
    assert messages_plan_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_file_plan_result["status"] == "error"
    assert messages_file_plan_result["warnings"][0]["code"] == "invalid_handle"
    assert messages_apply_result["status"] == "error"
    assert messages_apply_result["warnings"][0]["code"] == "invalid_handle"
    assert hide_my_email_result["status"] == "error"
    assert hide_my_email_result["warnings"][0]["code"] == "invalid_handle"
    assert voice_memos_result["status"] == "error"
    assert voice_memos_result["warnings"][0]["code"] == "invalid_handle"
    assert voice_memos_export_result["status"] == "error"
    assert voice_memos_export_result["warnings"][0]["code"] == "invalid_handle"
    assert safari_result["status"] == "error"
    assert safari_result["warnings"][0]["code"] == "invalid_handle"
    assert safari_folder_result["status"] == "error"
    assert safari_folder_result["warnings"][0]["code"] == "invalid_handle"
    assert safari_folder_items_result["status"] == "error"
    assert safari_folder_items_result["warnings"][0]["code"] == "invalid_handle"
    assert shortcuts_result["status"] == "error"
    assert shortcuts_result["warnings"][0]["code"] == "invalid_handle"
    assert shortcuts_folder_items_result["status"] == "error"
    assert shortcuts_folder_items_result["warnings"][0]["code"] == "invalid_handle"
    assert podcasts_show_result["status"] == "error"
    assert podcasts_show_result["warnings"][0]["code"] == "invalid_handle"
    assert podcasts_episodes_result["status"] == "error"
    assert podcasts_episodes_result["warnings"][0]["code"] == "invalid_handle"
    assert podcasts_episode_result["status"] == "error"
    assert podcasts_episode_result["warnings"][0]["code"] == "invalid_handle"
    assert music_track_result["status"] == "error"
    assert music_track_result["warnings"][0]["code"] == "invalid_handle"
    assert music_playlist_result["status"] == "error"
    assert music_playlist_result["warnings"][0]["code"] == "invalid_handle"
    assert music_playlist_tracks_result["status"] == "error"
    assert music_playlist_tracks_result["warnings"][0]["code"] == "invalid_handle"
    assert tv_item_result["status"] == "error"
    assert tv_item_result["warnings"][0]["code"] == "invalid_handle"
    assert tv_playlist_result["status"] == "error"
    assert tv_playlist_result["warnings"][0]["code"] == "invalid_handle"
    assert tv_playlist_items_result["status"] == "error"
    assert tv_playlist_items_result["warnings"][0]["code"] == "invalid_handle"
    assert freeform_board_result["status"] == "error"
    assert freeform_board_result["warnings"][0]["code"] == "invalid_handle"
    assert freeform_folder_result["status"] == "error"
    assert freeform_folder_result["warnings"][0]["code"] == "invalid_handle"
    assert freeform_folder_boards_result["status"] == "error"
    assert freeform_folder_boards_result["source"] == "freeform_folder_boards"
    assert freeform_folder_boards_result["warnings"][0]["code"] == "invalid_handle"
    assert freeform_child_folders_result["status"] == "error"
    assert freeform_child_folders_result["source"] == "freeform_child_folders"
    assert freeform_child_folders_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_result["status"] == "error"
    assert notes_folder_result["status"] == "error"
    assert notes_folder_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_folder_items_result["status"] == "error"
    assert notes_folder_items_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_folder_items_result["result_count"] == 0
    assert notes_folder_tree_result["status"] == "error"
    assert notes_folder_tree_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_folder_tree_result["result_count"] == 0
    assert notes_content_result["status"] == "error"
    assert notes_content_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_attachments_result["status"] == "error"
    assert notes_attachments_result["warnings"][0]["code"] == "invalid_handle"
    assert notes_export_result["status"] == "error"
    assert notes_export_result["warnings"][0]["code"] == "invalid_handle"
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
    assert calendar_participants_result["status"] == "error"
    assert calendar_participants_result["warnings"][0]["code"] == "invalid_handle"
    assert calendar_participant_result["status"] == "error"
    assert calendar_participant_result["warnings"][0]["code"] == "invalid_handle"
    assert calendar_target_result["status"] == "error"
    assert calendar_target_result["warnings"][0]["code"] == "invalid_handle"
    assert calendar_target_events_result["status"] == "error"
    assert calendar_target_events_result["warnings"][0]["code"] == "invalid_handle"
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
    assert photo_album_assets_result["status"] == "error"
    assert photo_album_assets_result["warnings"][0]["code"] == "invalid_album_handle"
    assert photo_export_result["status"] == "error"
    assert photo_export_result["warnings"][0]["code"] == "invalid_handle"
    assert photos_plan_result["status"] == "error"
    assert photos_plan_result["warnings"][0]["code"] == "missing_source_file"
    assert photos_apply_result["status"] == "error"
    assert photos_apply_result["warnings"][0]["code"] == "missing_source_file"
    assert reminder_result["status"] == "error"
    assert reminder_list_result["status"] == "error"
    assert reminder_list_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_list_items_result["status"] == "error"
    assert reminder_list_items_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_list_items_result["result_count"] == 0
    assert reminder_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_plan_result["status"] == "error"
    assert reminder_plan_result["warnings"][0]["code"] == "invalid_handle"
    assert reminder_apply_result["status"] == "error"
    assert reminder_apply_result["warnings"][0]["code"] == "invalid_handle"


def test_mcp_photos_plan_change_accepts_update_flags(monkeypatch) -> None:
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

    monkeypatch.setattr("local_apple_data.mcp_server.plan_photo_change", fake_plan)

    result = photos_plan_change(
        "update_flags",
        handle="photos:asset:v1:opaque",
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
    )

    assert result["status"] == "ok"
    assert captured["operation"] == "update_flags"
    assert captured["handle"] == "photos:asset:v1:opaque"
    assert captured["favorite"] is True
    assert captured["hidden"] is None
    assert captured["expected_favorite"] is False
    assert captured["expected_hidden"] is False


def test_mcp_photos_plan_change_accepts_delete(monkeypatch) -> None:
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

    monkeypatch.setattr("local_apple_data.mcp_server.plan_photo_change", fake_plan)

    result = photos_plan_change(
        "delete",
        handle="photos:asset:v1:opaque",
    )

    assert result["status"] == "ok"
    assert captured["operation"] == "delete"
    assert captured["handle"] == "photos:asset:v1:opaque"


def test_mcp_photos_plan_change_accepts_album_membership(monkeypatch) -> None:
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

    monkeypatch.setattr("local_apple_data.mcp_server.plan_photo_change", fake_plan)

    result = photos_plan_change(
        "add_to_album",
        handle="photos:asset:v1:opaque",
        album_handle="photos:album:v1:opaque",
        expected_in_album=False,
    )

    assert result["status"] == "ok"
    assert captured["operation"] == "add_to_album"
    assert captured["handle"] == "photos:asset:v1:opaque"
    assert captured["album_handle"] == "photos:album:v1:opaque"
    assert captured["expected_in_album"] is False


def test_mcp_photos_plan_change_accepts_album_management(monkeypatch) -> None:
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

    monkeypatch.setattr("local_apple_data.mcp_server.plan_photo_change", fake_plan)

    result = photos_plan_change(
        "rename_album",
        album_handle="photos:album:v1:opaque",
        new_album_title="LAD-TEST-Renamed",
    )

    assert result["status"] == "ok"
    assert captured["operation"] == "rename_album"
    assert captured["album_handle"] == "photos:album:v1:opaque"
    assert captured["new_album_title"] == "LAD-TEST-Renamed"


def test_mcp_reminders_list_move_wrappers_preserve_exact_gate(monkeypatch) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    current_list_handle = make_opaque_handle("reminders:list:eventkit", "synthetic-list-1")
    list_handle = make_opaque_handle("reminders:list:eventkit", "synthetic-list-2")
    calls: list[str] = []

    def fake_search_lists(query: str, *, limit: int = 20) -> dict:
        calls.append("search_lists")
        assert query == "Target"
        assert limit == 3
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [{"handle": list_handle, "title": "Synthetic Target List"}],
            "result_count": 1,
            "warnings": [],
        }

    def fake_get_list(handle: str) -> dict:
        calls.append("get_list")
        assert handle == list_handle
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "result": {"handle": handle, "title": "Synthetic Target List"},
            "result_count": 1,
            "warnings": [],
        }

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "move_to_list"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_list_handle"] == current_list_handle
        assert kwargs["target_list_handle"] == list_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_list_name"] == "Inbox"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "move_to_list",
                "approval": {"approval_fingerprint": "synthetic"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "move_to_list"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_list_handle"] == current_list_handle
        assert kwargs["target_list_handle"] == list_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_list_name"] == "Inbox"
        assert kwargs["approval_token"] == "reminders-apply:v1:synthetic"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "move_to_list",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "list_name": "Synthetic Target List",
                "target_list_verified": True,
            },
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "search_reminder_lists", fake_search_lists)
    monkeypatch.setattr(mcp_server, "get_reminder_list", fake_get_list)
    monkeypatch.setattr(mcp_server, "plan_reminder_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_change", fake_apply)

    listing = reminders_search_lists("Target", limit=3)
    detail = reminders_get_list(list_handle)
    plan = reminders_plan_change(
        "move_to_list",
        handle=reminder_handle,
        expected_list_handle=current_list_handle,
        target_list_handle=list_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_list_name="Inbox",
    )
    applied = reminders_apply_change(
        "move_to_list",
        handle=reminder_handle,
        expected_list_handle=current_list_handle,
        target_list_handle=list_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_list_name="Inbox",
        approval_token="reminders-apply:v1:synthetic",
        confirm_apply=True,
    )

    assert listing["results"][0]["handle"] == list_handle
    assert "synthetic-list-2" not in str(listing)
    assert detail["result"]["title"] == "Synthetic Target List"
    assert plan["preview"]["operation"] == "move_to_list"
    assert applied["read_back"]["list_name"] == "Synthetic Target List"
    assert applied["read_back"]["target_list_verified"] is True
    assert calls == ["search_lists", "get_list", "plan", "apply"]


def test_mcp_reminders_list_items_wrapper_is_read_only(monkeypatch) -> None:
    list_handle = make_opaque_handle("reminders:list:eventkit", "synthetic-list-2")
    captured: dict[str, object] = {}

    def fake_list_items(
        handle: str,
        *,
        limit: int,
        include_completed: bool,
    ) -> dict:
        captured["handle"] = handle
        captured["limit"] = limit
        captured["include_completed"] = include_completed
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders_list_items",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "list": {"handle": handle, "title": "Synthetic Target List"},
            "results": [
                {
                    "handle": make_opaque_handle(
                        "reminders:reminder:eventkit",
                        "synthetic-reminder-1",
                    ),
                    "title": "Synthetic selected-list reminder",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "list_reminder_items", fake_list_items)

    result = reminders_list_items(list_handle, limit=4, include_completed=True)

    assert result["status"] == "ok"
    assert result["source"] == "reminders_list_items"
    assert result["result_count"] == 1
    assert captured == {
        "handle": list_handle,
        "limit": 4,
        "include_completed": True,
    }


def test_mcp_reminders_list_lists_wrapper_is_read_only(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_list_lists(*, limit: int) -> dict:
        captured["limit"] = limit
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": make_opaque_handle(
                        "reminders:list:eventkit",
                        "synthetic-list-1",
                    ),
                    "title": "Synthetic List",
                    "is_shared": True,
                    "sharee_count": 1,
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "list_reminder_lists", fake_list_lists)

    result = reminders_list_lists(limit=7)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["is_shared"] is True
    assert captured == {"limit": 7}


def test_mcp_reminders_url_wrappers_preserve_exact_gate(monkeypatch) -> None:
    reminder_handle = make_opaque_handle("reminders:reminder:eventkit", "runtime-reminder-1")
    url = "tel:+15550101010"
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "update_url"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_url_present"] == "false"
        assert kwargs["expected_url_sha256"] == ""
        assert kwargs["url"] == url
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "update_url",
                "proposed": {"url_safe_sha256": "a" * 64},
                "approval": {"approval_fingerprint": "synthetic"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "update_url"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_url_present"] == "false"
        assert kwargs["expected_url_sha256"] == ""
        assert kwargs["url"] == url
        assert kwargs["approval_token"] == "reminders-apply:v1:synthetic"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update_url",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"url_present": True, "url_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_change", fake_apply)

    plan = reminders_plan_change(
        "update_url",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_url_present="false",
        url=url,
    )
    applied = reminders_apply_change(
        "update_url",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_url_present="false",
        url=url,
        approval_token="reminders-apply:v1:synthetic",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "update_url"
    assert applied["read_back"]["url_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_reminders_clear_url_wrappers_preserve_exact_gate(monkeypatch) -> None:
    reminder_handle = make_opaque_handle("reminders:reminder:eventkit", "runtime-reminder-1")
    current_hash = "b" * 64
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "clear_url"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_url_present"] == "true"
        assert kwargs["expected_url_sha256"] == current_hash
        assert kwargs["url"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "clear_url",
                "proposed": {"url_clear_requested": True},
                "approval": {"approval_fingerprint": "synthetic"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "clear_url"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_url_present"] == "true"
        assert kwargs["expected_url_sha256"] == current_hash
        assert kwargs["url"] == ""
        assert kwargs["approval_token"] == "reminders-apply:v1:synthetic"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "clear_url",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"url_present": False, "url_absent_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_change", fake_apply)

    plan = reminders_plan_change(
        "clear_url",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_url_present="true",
        expected_url_sha256=current_hash,
    )
    applied = reminders_apply_change(
        "clear_url",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_url_present="true",
        expected_url_sha256=current_hash,
        approval_token="reminders-apply:v1:synthetic",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "clear_url"
    assert applied["read_back"]["url_absent_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_reminders_absolute_display_alarm_wrappers_preserve_exact_gate(monkeypatch) -> None:
    reminder_handle = make_opaque_handle("reminders:reminder:eventkit", "runtime-reminder-1")
    current_hash = "c" * 64
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "set_absolute_display_alarm"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_alarms_count"] == 0
        assert kwargs["expected_alarms_sha256"] == ""
        assert kwargs["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
        assert kwargs["alarm_offsets_minutes"] is None
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "set_absolute_display_alarm",
                "proposed": {"alarm_absolute_dates": ["2026-06-05T16:45:00Z"]},
                "approval": {"approval_fingerprint": "synthetic"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "clear_display_alarm"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_alarms_count"] == 1
        assert kwargs["expected_alarms_sha256"] == current_hash
        assert kwargs["alarm_absolute_dates"] is None
        assert kwargs["alarm_offsets_minutes"] is None
        assert kwargs["approval_token"] == "reminders-apply:v1:synthetic"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "clear_display_alarm",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"alarms_count": 0, "display_alarm_cleared_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_change", fake_apply)

    plan = reminders_plan_change(
        "set_absolute_display_alarm",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    applied = reminders_apply_change(
        "clear_display_alarm",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_alarms_count=1,
        expected_alarms_sha256=current_hash,
        approval_token="reminders-apply:v1:synthetic",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "set_absolute_display_alarm"
    assert applied["read_back"]["display_alarm_cleared_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_reminders_relative_display_alarm_wrappers_preserve_exact_gate(monkeypatch) -> None:
    reminder_handle = make_opaque_handle("reminders:reminder:eventkit", "runtime-reminder-1")
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "set_relative_display_alarm"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_alarms_count"] == 0
        assert kwargs["expected_alarms_sha256"] == ""
        assert kwargs["alarm_absolute_dates"] is None
        assert kwargs["alarm_offsets_minutes"] == [-30, 0]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "set_relative_display_alarm",
                "proposed": {"alarm_offsets_minutes": [-30, 0]},
                "approval": {"approval_fingerprint": "synthetic"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "set_relative_display_alarm"
        assert kwargs["handle"] == reminder_handle
        assert kwargs["expected_title"] == "Synthetic reminder"
        assert kwargs["expected_completed"] == "false"
        assert kwargs["expected_alarms_count"] == 0
        assert kwargs["expected_alarms_sha256"] == ""
        assert kwargs["alarm_absolute_dates"] is None
        assert kwargs["alarm_offsets_minutes"] == [-30, 0]
        assert kwargs["approval_token"] == "reminders-apply:v1:synthetic"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "set_relative_display_alarm",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"alarm_offsets_minutes": [-30, 0], "display_alarm_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_change", fake_apply)

    plan = reminders_plan_change(
        "set_relative_display_alarm",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_alarms_count=0,
        alarm_offsets_minutes=[-30, 0],
    )
    applied = reminders_apply_change(
        "set_relative_display_alarm",
        handle=reminder_handle,
        expected_title="Synthetic reminder",
        expected_completed="false",
        expected_alarms_count=0,
        alarm_offsets_minutes=[-30, 0],
        approval_token="reminders-apply:v1:synthetic",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "set_relative_display_alarm"
    assert applied["read_back"]["display_alarm_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_reminders_list_management_wrappers_preserve_gate(monkeypatch) -> None:
    source_handle = make_opaque_handle("reminders:list:eventkit", "synthetic-list-1")
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "create_list"
        assert kwargs["source_list_handle"] == source_handle
        assert kwargs["list_handle"] == ""
        assert kwargs["target_list_handle"] == ""
        assert kwargs["list_title"] == "Project MCP"
        assert kwargs["new_list_title"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "create_list",
                "approval": {"approval_fingerprint": "exact-list"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "create_list"
        assert kwargs["source_list_handle"] == source_handle
        assert kwargs["list_handle"] == ""
        assert kwargs["target_list_handle"] == ""
        assert kwargs["list_title"] == "Project MCP"
        assert kwargs["new_list_title"] == ""
        assert kwargs["approval_token"] == "reminders-apply:v1:exact-list"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "create_list",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "Project MCP", "source_list_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_list_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_list_change", fake_apply)

    plan = reminders_plan_list_change(
        "create_list",
        source_list_handle=source_handle,
        list_title="Project MCP",
    )
    applied = reminders_apply_list_change(
        "create_list",
        source_list_handle=source_handle,
        list_title="Project MCP",
        approval_token="reminders-apply:v1:exact-list",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "create_list"
    assert applied["read_back"]["source_list_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_reminders_list_migration_wrappers_preserve_target_gate(monkeypatch) -> None:
    source_handle = make_opaque_handle("reminders:list:eventkit", "source-list")
    target_handle = make_opaque_handle("reminders:list:eventkit", "target-list")
    calls: list[str] = []

    def fake_plan(operation: str, **kwargs) -> dict:
        calls.append("plan")
        assert operation == "delete_list_with_migration"
        assert kwargs["source_list_handle"] == ""
        assert kwargs["list_handle"] == source_handle
        assert kwargs["target_list_handle"] == target_handle
        assert kwargs["list_title"] == ""
        assert kwargs["new_list_title"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "delete_list_with_migration",
                "approval": {"approval_fingerprint": "migrate-delete"},
            },
            "warnings": [],
        }

    def fake_apply(operation: str, **kwargs) -> dict:
        calls.append("apply")
        assert operation == "delete_list_with_migration"
        assert kwargs["source_list_handle"] == ""
        assert kwargs["list_handle"] == source_handle
        assert kwargs["target_list_handle"] == target_handle
        assert kwargs["list_title"] == ""
        assert kwargs["new_list_title"] == ""
        assert kwargs["approval_token"] == "reminders-apply:v1:migrate-delete"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete_list_with_migration",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"list_absent_verified": True, "target_list_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "plan_reminder_list_change", fake_plan)
    monkeypatch.setattr(mcp_server, "apply_reminder_list_change", fake_apply)

    plan = reminders_plan_list_change(
        "delete_list_with_migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
    )
    applied = reminders_apply_list_change(
        "delete_list_with_migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        approval_token="reminders-apply:v1:migrate-delete",
        confirm_apply=True,
    )

    assert plan["preview"]["operation"] == "delete_list_with_migration"
    assert applied["read_back"]["target_list_verified"] is True
    assert calls == ["plan", "apply"]


def test_mcp_mail_forward_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "forward-message",
        message_handle="mail:message:v2:fixture",
        to=["synthetic-forward@example.invalid"],
        body_text="Synthetic forward note.",
        include_source_attachments=True,
    )
    mail_apply_change(
        "forward-message",
        approval_token="mail-apply:v1:abc",
        message_handle="mail:message:v2:fixture",
        to=["synthetic-forward@example.invalid"],
        body_text="Synthetic forward note.",
        include_source_attachments=True,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "forward-message"
    assert apply_operation == "forward-message"
    assert plan_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert plan_kwargs["to"] == ["synthetic-forward@example.invalid"]
    assert plan_kwargs["body_text"] == "Synthetic forward note."
    assert plan_kwargs["include_source_attachments"] is True
    assert apply_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert apply_kwargs["to"] == ["synthetic-forward@example.invalid"]
    assert apply_kwargs["body_text"] == "Synthetic forward note."
    assert apply_kwargs["include_source_attachments"] is True
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_sender_handle_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    sender_handle = make_opaque_handle("mail:sender", "synthetic-account\x00synthetic-sender")
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender MCP draft",
        body_text="Synthetic body.",
        sender_handle=sender_handle,
    )
    mail_apply_change(
        "create-draft",
        approval_token="mail-apply:v1:abc",
        to=["synthetic@example.invalid"],
        subject="Synthetic sender MCP draft",
        body_text="Synthetic body.",
        sender_handle=sender_handle,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "create-draft"
    assert apply_operation == "create-draft"
    assert plan_kwargs["sender_handle"] == sender_handle
    assert apply_kwargs["sender_handle"] == sender_handle
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_signature_handle_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    signature_handle = make_opaque_handle("mail:signature", "synthetic-signature")
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "send-message",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature MCP send",
        body_text="Synthetic body.",
        signature_handle=signature_handle,
    )
    mail_apply_change(
        "send-message",
        approval_token="mail-apply:v1:abc",
        to=["synthetic@example.invalid"],
        subject="Synthetic signature MCP send",
        body_text="Synthetic body.",
        signature_handle=signature_handle,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "send-message"
    assert apply_operation == "send-message"
    assert plan_kwargs["signature_handle"] == signature_handle
    assert apply_kwargs["signature_handle"] == signature_handle
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_template_handle_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    template_handle = make_opaque_handle("mail:template", "synthetic-template")
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "send-message",
        to=["synthetic@example.invalid"],
        template_handle=template_handle,
    )
    mail_apply_change(
        "send-message",
        approval_token="mail-apply:v1:abc",
        to=["synthetic@example.invalid"],
        template_handle=template_handle,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "send-message"
    assert apply_operation == "send-message"
    assert plan_kwargs["template_handle"] == template_handle
    assert apply_kwargs["template_handle"] == template_handle
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_plan_search_triage_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, str, dict]] = {}

    def fake_plan(operation: str, query: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, query, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_search_triage", fake_plan)

    mail_plan_search_triage(
        "mark-read",
        "subscription",
        scopes=["body"],
        after="2026-01-01",
        before="2026-06-01",
        cursor="20",
        limit=2,
    )

    operation, query, kwargs = captured["plan"]
    assert operation == "mark-read"
    assert query == "subscription"
    assert kwargs["search_source"] == "fts"
    assert kwargs["scopes"] == ["body"]
    assert kwargs["after"] == "2026-01-01"
    assert kwargs["before"] == "2026-06-01"
    assert kwargs["cursor"] == "20"
    assert kwargs["limit"] == 2


def test_mcp_mailbox_plan_and_apply_forward_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    mailbox_handle = make_opaque_handle("mail:mailbox", "synthetic", "LAD-TEST-old")
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_mailbox_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_mailbox_change", fake_apply)

    mail_plan_mailbox_change(
        "rename-mailbox",
        mailbox_handle=mailbox_handle,
        new_mailbox_name="LAD-TEST-new",
    )
    mail_apply_mailbox_change(
        "rename-mailbox",
        approval_token="mail-apply:v1:abc",
        mailbox_handle=mailbox_handle,
        new_mailbox_name="LAD-TEST-new",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "rename-mailbox"
    assert apply_operation == "rename-mailbox"
    assert plan_kwargs["mailbox_handle"] == mailbox_handle
    assert plan_kwargs["new_mailbox_name"] == "LAD-TEST-new"
    assert apply_kwargs["mailbox_handle"] == mailbox_handle
    assert apply_kwargs["new_mailbox_name"] == "LAD-TEST-new"
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_cleanup_plan_and_apply_forward_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    message_handle = make_int_handle("mail:message", 30)
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_cleanup", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_cleanup", fake_apply)

    mail_plan_cleanup("permanent-delete-message", message_handle=message_handle)
    mail_apply_cleanup(
        "permanent-delete-message",
        approval_token="mail-apply:v1:abc",
        message_handle=message_handle,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "permanent-delete-message"
    assert apply_operation == "permanent-delete-message"
    assert plan_kwargs["message_handle"] == message_handle
    assert apply_kwargs["message_handle"] == message_handle
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_attachment_paths_forward_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    attachment_path = str(tmp_path / "packet.pdf")
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "create-draft",
        to=["synthetic@example.invalid"],
        subject="Synthetic attachment MCP draft",
        body_text="Synthetic body.",
        attachment_paths=[attachment_path],
    )
    mail_apply_change(
        "create-draft",
        approval_token="mail-apply:v1:abc",
        to=["synthetic@example.invalid"],
        subject="Synthetic attachment MCP draft",
        body_text="Synthetic body.",
        attachment_paths=[attachment_path],
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "create-draft"
    assert apply_operation == "create-draft"
    assert plan_kwargs["attachment_paths"] == [attachment_path]
    assert apply_kwargs["attachment_paths"] == [attachment_path]
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_reply_all_forwards_exact_inputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "reply-all-message",
        message_handle="mail:message:v2:fixture",
        body_text="Synthetic reply-all body.",
    )
    mail_apply_change(
        "reply-all-message",
        approval_token="mail-apply:v1:abc",
        message_handle="mail:message:v2:fixture",
        body_text="Synthetic reply-all body.",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "reply-all-message"
    assert apply_operation == "reply-all-message"
    assert plan_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert plan_kwargs["body_text"] == "Synthetic reply-all body."
    assert apply_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert apply_kwargs["body_text"] == "Synthetic reply-all body."
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_mail_move_forwards_exact_target_mailbox(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "mail", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_mail_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_mail_change", fake_apply)

    mail_plan_change(
        "move-message",
        message_handle="mail:message:v2:fixture",
        target_mailbox_handle="mail:mailbox:v1:target",
    )
    mail_apply_change(
        "move-message",
        approval_token="mail-apply:v1:abc",
        message_handle="mail:message:v2:fixture",
        target_mailbox_handle="mail:mailbox:v1:target",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "move-message"
    assert apply_operation == "move-message"
    assert plan_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert plan_kwargs["target_mailbox_handle"] == "mail:mailbox:v1:target"
    assert apply_kwargs["message_handle"] == "mail:message:v2:fixture"
    assert apply_kwargs["target_mailbox_handle"] == "mail:mailbox:v1:target"
    assert apply_kwargs["approval_token"] == "mail-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_notes_create_folder_forwards_exact_parent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_notes_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_notes_change", fake_apply)

    notes_plan_change(
        "create-folder",
        title="Synthetic child folder",
        folder_handle="notes:folder:v1:fixture",
    )
    notes_apply_change(
        "create-folder",
        title="Synthetic child folder",
        folder_handle="notes:folder:v1:fixture",
        approval_token="notes-apply:v1:abc",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "create-folder"
    assert apply_operation == "create-folder"
    assert plan_kwargs["title"] == "Synthetic child folder"
    assert plan_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert plan_kwargs["body_text"] == ""
    assert apply_kwargs["title"] == "Synthetic child folder"
    assert apply_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert apply_kwargs["approval_token"] == "notes-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_notes_get_content_forwards_html_format(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_get(handle: str, **kwargs: object) -> dict:
        captured["handle"] = handle
        captured["kwargs"] = kwargs
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.get_notes_content", fake_get)
    notes_get_content("notes:note:v2:fixture", content_format="html")
    assert captured["handle"] == "notes:note:v2:fixture"
    assert captured["kwargs"]["content_format"] == "html"


def test_mcp_notes_rich_text_create_replace_forward_body_html(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_notes_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_notes_change", fake_apply)

    notes_plan_change("create_html", title="Rich", body_html="<p>Rich body</p>")
    notes_apply_change(
        "replace_html",
        handle="notes:note:v2:fixture",
        body_html="<p>Replaced</p>",
        expected_current_sha256="a" * 64,
        approval_token="notes-apply:v1:abc",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "create_html"
    assert plan_kwargs["body_html"] == "<p>Rich body</p>"
    assert apply_operation == "replace_html"
    assert apply_kwargs["body_html"] == "<p>Replaced</p>"
    assert apply_kwargs["expected_current_sha256"] == "a" * 64
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_notes_rename_folder_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_notes_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_notes_change", fake_apply)

    notes_plan_change(
        "rename-folder",
        title="Synthetic renamed folder",
        folder_handle="notes:folder:v1:fixture",
        expected_current_sha256="a" * 64,
    )
    notes_apply_change(
        "rename-folder",
        title="Synthetic renamed folder",
        folder_handle="notes:folder:v1:fixture",
        expected_current_sha256="a" * 64,
        approval_token="notes-apply:v1:abc",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "rename-folder"
    assert apply_operation == "rename-folder"
    assert plan_kwargs["title"] == "Synthetic renamed folder"
    assert plan_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert plan_kwargs["expected_current_sha256"] == "a" * 64
    assert plan_kwargs["body_text"] == ""
    assert apply_kwargs["title"] == "Synthetic renamed folder"
    assert apply_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert apply_kwargs["expected_current_sha256"] == "a" * 64
    assert apply_kwargs["approval_token"] == "notes-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_notes_delete_folder_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_notes_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_notes_change", fake_apply)

    notes_plan_change(
        "delete-folder",
        folder_handle="notes:folder:v1:fixture",
        expected_current_sha256="a" * 64,
    )
    notes_apply_change(
        "delete-folder",
        folder_handle="notes:folder:v1:fixture",
        expected_current_sha256="a" * 64,
        approval_token="notes-apply:v1:abc",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "delete-folder"
    assert apply_operation == "delete-folder"
    assert plan_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert plan_kwargs["expected_current_sha256"] == "a" * 64
    assert plan_kwargs["title"] == ""
    assert plan_kwargs["body_text"] == ""
    assert apply_kwargs["folder_handle"] == "notes:folder:v1:fixture"
    assert apply_kwargs["expected_current_sha256"] == "a" * 64
    assert apply_kwargs["title"] == ""
    assert apply_kwargs["body_text"] == ""
    assert apply_kwargs["approval_token"] == "notes-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_notes_list_folder_items_forwards_exact_handle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_list(handle: str, *, limit: int = 20) -> dict:
        captured["handle"] = handle
        captured["limit"] = limit
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.list_notes_folder_items", fake_list)

    result = notes_list_folder_items("notes:folder:v1:selected", limit=7)

    assert result["status"] == "ok"
    assert captured == {"handle": "notes:folder:v1:selected", "limit": 7}


def test_mcp_notes_list_folder_tree_forwards_exact_handle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_list(handle: str, *, depth: int = 2, limit: int = 50) -> dict:
        captured["handle"] = handle
        captured["depth"] = depth
        captured["limit"] = limit
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.list_notes_folder_tree", fake_list)

    result = notes_list_folder_tree("notes:folder:v1:selected", depth=3, limit=9)

    assert result["status"] == "ok"
    assert captured == {"handle": "notes:folder:v1:selected", "depth": 3, "limit": 9}


def test_mcp_notes_move_folder_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "notes", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_notes_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_notes_change", fake_apply)

    notes_plan_change(
        "move-folder",
        folder_handle="notes:folder:v1:source",
        target_folder_handle="notes:folder:v1:target",
        expected_current_sha256="a" * 64,
    )
    notes_apply_change(
        "move-folder",
        folder_handle="notes:folder:v1:source",
        target_folder_handle="notes:folder:v1:target",
        expected_current_sha256="a" * 64,
        approval_token="notes-apply:v1:abc",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "move-folder"
    assert apply_operation == "move-folder"
    assert plan_kwargs["folder_handle"] == "notes:folder:v1:source"
    assert plan_kwargs["target_folder_handle"] == "notes:folder:v1:target"
    assert plan_kwargs["expected_current_sha256"] == "a" * 64
    assert plan_kwargs["title"] == ""
    assert plan_kwargs["body_text"] == ""
    assert apply_kwargs["folder_handle"] == "notes:folder:v1:source"
    assert apply_kwargs["target_folder_handle"] == "notes:folder:v1:target"
    assert apply_kwargs["expected_current_sha256"] == "a" * 64
    assert apply_kwargs["title"] == ""
    assert apply_kwargs["body_text"] == ""
    assert apply_kwargs["approval_token"] == "notes-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_contacts_update_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    contacts_plan_change(
        "update",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="a" * 64,
        given_name="Renamed",
        email_addresses=[{"label": "work", "value": "new@example.invalid"}],
    )
    contacts_apply_change(
        "update",
        approval_token="contacts-apply:v1:abc",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="a" * 64,
        given_name="Renamed",
        email_addresses=[{"label": "work", "value": "new@example.invalid"}],
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "update"
    assert apply_operation == "update"
    assert plan_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert plan_kwargs["expected_current_sha256"] == "a" * 64
    assert plan_kwargs["given_name"] == "Renamed"
    assert plan_kwargs["family_name"] is None
    assert plan_kwargs["email_addresses"] == [{"label": "work", "value": "new@example.invalid"}]
    assert plan_kwargs["phone_numbers"] is None
    assert apply_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert apply_kwargs["expected_current_sha256"] == "a" * 64
    assert apply_kwargs["email_addresses"] == [{"label": "work", "value": "new@example.invalid"}]
    assert apply_kwargs["phone_numbers"] is None
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:abc"
    assert apply_kwargs["confirm_apply"] is True

    contacts_plan_change(
        "delete",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="b" * 64,
    )
    contacts_apply_change(
        "delete",
        approval_token="contacts-apply:v1:def",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="b" * 64,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "delete"
    assert apply_operation == "delete"
    assert plan_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert plan_kwargs["expected_current_sha256"] == "b" * 64
    assert plan_kwargs["given_name"] is None
    assert apply_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert apply_kwargs["expected_current_sha256"] == "b" * 64
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:def"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_contacts_rich_update_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    postal = [{"label": "home", "street": "2 New Way", "city": "Example"}]
    birthday = {"month": 1, "day": 2}
    dates = [{"label": "anniversary", "date": {"month": 3, "day": 4}}]
    social = [{"label": "work", "service": "LinkedIn", "username": "fixture"}]
    ims = [{"label": "home", "service": "Signal", "username": "fixture"}]
    relations = [{"label": "assistant", "name": "Fixture Friend"}]

    contacts_plan_change(
        "update",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="d" * 64,
        postal_addresses=postal,
        birthday=birthday,
        dates=dates,
        social_profiles=social,
        instant_message_addresses=ims,
        contact_relations=relations,
        image_path="/tmp/avatar.png",
    )
    contacts_apply_change(
        "update",
        approval_token="contacts-apply:v1:jkl",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="d" * 64,
        postal_addresses=postal,
        birthday=birthday,
        dates=dates,
        social_profiles=social,
        instant_message_addresses=ims,
        contact_relations=relations,
        image_path="/tmp/avatar.png",
        confirm_apply=True,
    )

    _plan_operation, plan_kwargs = captured["plan"]
    _apply_operation, apply_kwargs = captured["apply"]
    assert plan_kwargs["postal_addresses"] == postal
    assert plan_kwargs["birthday"] == birthday
    assert plan_kwargs["dates"] == dates
    assert plan_kwargs["social_profiles"] == social
    assert plan_kwargs["instant_message_addresses"] == ims
    assert plan_kwargs["contact_relations"] == relations
    assert plan_kwargs["image_path"] == "/tmp/avatar.png"
    assert apply_kwargs["postal_addresses"] == postal
    assert apply_kwargs["birthday"] == birthday
    assert apply_kwargs["dates"] == dates
    assert apply_kwargs["social_profiles"] == social
    assert apply_kwargs["instant_message_addresses"] == ims
    assert apply_kwargs["contact_relations"] == relations
    assert apply_kwargs["image_path"] == "/tmp/avatar.png"
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:jkl"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_contacts_count_and_export_forward_archive_args(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    captured: dict[str, dict] = {}

    def fake_count(**kwargs: object) -> dict:
        captured["count"] = kwargs
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_export(**kwargs: object) -> dict:
        captured["export"] = kwargs
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.count_contacts", fake_count)
    monkeypatch.setattr("local_apple_data.mcp_server.export_contacts_archive", fake_export)

    contacts_count(max_contacts=77)
    contacts_export_archive(
        output_dir=str(tmp_path / "backup"),
        filename_prefix="phase0",
        max_contacts=88,
    )

    assert captured["count"]["max_contacts"] == 77
    assert captured["export"]["output_dir"] == tmp_path / "backup"
    assert captured["export"]["filename_prefix"] == "phase0"
    assert captured["export"]["max_contacts"] == 88


def test_mcp_contacts_append_note_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    contacts_plan_change(
        "append_note",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="c" * 64,
        note_text="\n\nSynthetic context.",
    )
    contacts_apply_change(
        "append_note",
        approval_token="contacts-apply:v1:ghi",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="c" * 64,
        note_text="\n\nSynthetic context.",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "append_note"
    assert apply_operation == "append_note"
    assert plan_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert plan_kwargs["expected_current_sha256"] == "c" * 64
    assert plan_kwargs["note_text"] == "\n\nSynthetic context."
    assert apply_kwargs["handle"] == "contacts:contact:v1:fixture"
    assert apply_kwargs["expected_current_sha256"] == "c" * 64
    assert apply_kwargs["note_text"] == "\n\nSynthetic context."
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:ghi"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_contacts_set_note_forwards_exact_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    contacts_plan_change(
        "merge_note",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="e" * 64,
        note_text="Merged context.",
    )
    contacts_apply_change(
        "merge_note",
        approval_token="contacts-apply:v1:mno",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="e" * 64,
        note_text="Merged context.",
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "merge_note"
    assert apply_operation == "merge_note"
    assert plan_kwargs["note_text"] == "Merged context."
    assert apply_kwargs["note_text"] == "Merged context."
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:mno"
    assert apply_kwargs["confirm_apply"] is True


def test_mcp_contacts_group_tools_and_membership_forward_exact_binding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_groups(query: str, *, limit: int) -> dict:
        captured["groups"] = {"query": query, "limit": limit}
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_group(handle: str) -> dict:
        captured["group"] = handle
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_group_members(handle: str, *, limit: int) -> dict:
        captured["group_members"] = {"handle": handle, "limit": limit}
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_containers(query: str, *, limit: int) -> dict:
        captured["containers"] = {"query": query, "limit": limit}
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_container(handle: str) -> dict:
        captured["container"] = handle
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_container_members(handle: str, *, limit: int) -> dict:
        captured["container_members"] = {"handle": handle, "limit": limit}
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.search_contact_groups", fake_groups)
    monkeypatch.setattr("local_apple_data.mcp_server.get_contact_group", fake_group)
    monkeypatch.setattr("local_apple_data.mcp_server.list_contact_group_members", fake_group_members)
    monkeypatch.setattr("local_apple_data.mcp_server.search_contact_containers", fake_containers)
    monkeypatch.setattr("local_apple_data.mcp_server.get_contact_container", fake_container)
    monkeypatch.setattr("local_apple_data.mcp_server.list_contact_container_members", fake_container_members)
    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    contacts_search_groups("Synthetic", limit=3)
    contacts_get_group("contacts:group:v1:fixture")
    contacts_list_group_members("contacts:group:v1:fixture", limit=4)
    contacts_search_containers("iCloud", limit=2)
    contacts_get_container("contacts:container:v1:fixture")
    contacts_list_container_members("contacts:container:v1:fixture", limit=6)
    contacts_plan_change(
        "add_group_member",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="0" * 64,
        group_handle="contacts:group:v1:fixture",
        expected_group_sha256="1" * 64,
    )
    contacts_apply_change(
        "add_group_member",
        approval_token="contacts-apply:v1:group",
        handle="contacts:contact:v1:fixture",
        expected_current_sha256="0" * 64,
        group_handle="contacts:group:v1:fixture",
        expected_group_sha256="1" * 64,
        confirm_apply=True,
    )

    assert captured["groups"] == {"query": "Synthetic", "limit": 3}
    assert captured["group"] == "contacts:group:v1:fixture"
    assert captured["group_members"] == {"handle": "contacts:group:v1:fixture", "limit": 4}
    assert captured["containers"] == {"query": "iCloud", "limit": 2}
    assert captured["container"] == "contacts:container:v1:fixture"
    assert captured["container_members"] == {"handle": "contacts:container:v1:fixture", "limit": 6}
    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "add_group_member"
    assert apply_operation == "add_group_member"
    assert plan_kwargs["group_handle"] == "contacts:group:v1:fixture"
    assert plan_kwargs["expected_group_sha256"] == "1" * 64
    assert apply_kwargs["group_handle"] == "contacts:group:v1:fixture"
    assert apply_kwargs["expected_group_sha256"] == "1" * 64
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:group"
    assert apply_kwargs["confirm_apply"] is True

    contacts_plan_change(
        "create_group",
        group_name="Friends",
        container_handle="contacts:container:v1:fixture",
        expected_container_sha256="2" * 64,
    )
    contacts_apply_change(
        "create_group",
        approval_token="contacts-apply:v1:create-group",
        group_name="Friends",
        container_handle="contacts:container:v1:fixture",
        expected_container_sha256="2" * 64,
        confirm_apply=True,
    )
    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "create_group"
    assert apply_operation == "create_group"
    assert plan_kwargs["container_handle"] == "contacts:container:v1:fixture"
    assert plan_kwargs["expected_container_sha256"] == "2" * 64
    assert apply_kwargs["group_name"] == "Friends"
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:create-group"


def test_mcp_contacts_batch_forwards_exact_items(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    items = [
        {
            "operation": "append_note",
            "handle": "contacts:contact:v1:fixture",
            "expected_current_sha256": "0" * 64,
            "note_text": "\n\nBatch context.",
        }
    ]
    captured: dict[str, tuple[str, dict]] = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["plan"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["apply"] = (operation, kwargs)
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.mcp_server.plan_contact_change", fake_plan)
    monkeypatch.setattr("local_apple_data.mcp_server.apply_contact_change", fake_apply)

    contacts_plan_change("batch", batch_items=items)
    contacts_apply_change(
        "batch",
        approval_token="contacts-apply:v1:batch",
        batch_items=items,
        confirm_apply=True,
    )

    plan_operation, plan_kwargs = captured["plan"]
    apply_operation, apply_kwargs = captured["apply"]
    assert plan_operation == "batch"
    assert apply_operation == "batch"
    assert plan_kwargs["batch_items"] == items
    assert apply_kwargs["batch_items"] == items
    assert apply_kwargs["approval_token"] == "contacts-apply:v1:batch"
    assert apply_kwargs["confirm_apply"] is True


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
                    "mail_search_body",
                    "mail_search_attachments",
                    "mail_search_advanced",
                    "mail_build_fts_index",
                    "mail_search_fts",
                    "mail_get_metadata",
                    "mail_search_mailboxes",
                    "mail_get_mailbox",
                    "mail_search_senders",
                    "mail_get_sender",
                    "mail_search_signatures",
                    "mail_get_signature",
                    "mail_create_template",
                    "mail_search_templates",
                    "mail_get_template",
                    "mail_delete_template",
                    "mail_get_content",
                    "mail_get_unsubscribe_metadata",
                    "mail_list_attachments",
                    "mail_export_attachment",
                    "mail_plan_change",
                    "mail_apply_change",
                    "mail_plan_search_triage",
                    "mail_plan_mailbox_change",
                    "mail_apply_mailbox_change",
                    "mail_plan_cleanup",
                    "mail_apply_cleanup",
                    "messages_search",
                    "messages_get_chat",
                    "messages_list_attachments",
                    "messages_list_participants",
                    "messages_get_participant",
                    "messages_export_attachment",
                    "messages_plan_change",
                    "messages_apply_change",
                    "hide_my_email_search",
                    "hide_my_email_get_alias",
                    "voice_memos_search",
                    "voice_memos_get_recording",
                    "voice_memos_export_audio",
                    "safari_search",
                    "safari_get_item",
                    "safari_search_folders",
                    "safari_get_folder",
                    "safari_list_folder_items",
                    "shortcuts_search",
                    "shortcuts_get_item",
                    "shortcuts_list_folder_items",
                    "shortcuts_plan_run",
                    "shortcuts_apply_run",
                    "books_search",
                    "books_get",
                    "books_list_annotations",
                    "podcasts_search",
                    "podcasts_get_show",
                    "podcasts_list_episodes",
                    "podcasts_get_episode",
                    "music_search",
                    "music_get_track",
                    "music_search_playlists",
                    "music_get_playlist",
                    "music_list_playlist_tracks",
                    "tv_search",
                    "tv_get_item",
                    "tv_search_playlists",
                    "tv_get_playlist",
                    "tv_list_playlist_items",
                    "freeform_list_boards",
                    "freeform_get_board",
                    "freeform_search_folders",
                    "freeform_get_folder",
                    "freeform_list_folder_boards",
                    "freeform_list_child_folders",
                    "notes_search",
                    "notes_search_folders",
                    "notes_get_folder",
                    "notes_list_folder_items",
                    "notes_list_folder_tree",
                    "notes_get_metadata",
                    "notes_get_content",
                    "notes_list_attachments",
                    "notes_export_attachment",
                    "notes_plan_change",
                    "notes_apply_change",
                    "icloud_drive_search",
                    "icloud_drive_get_root",
                    "icloud_drive_get_metadata",
                    "icloud_drive_list_folder",
                    "icloud_drive_list_tree",
                    "icloud_drive_get_content",
                    "icloud_drive_plan_change",
                    "icloud_drive_apply_change",
                    "filesystem_search",
                    "filesystem_get_root",
                    "filesystem_get_metadata",
                    "filesystem_list_folder",
                    "filesystem_list_tree",
                    "filesystem_get_content",
                    "filesystem_export_file",
                    "filesystem_plan_change",
                    "filesystem_apply_change",
                    "calendar_search",
                    "calendar_get_event",
                    "calendar_list_participants",
                    "calendar_get_participant",
                    "calendar_search_calendars",
                    "calendar_get_calendar",
                    "calendar_list_calendar_events",
                    "calendar_plan_change",
                    "calendar_apply_change",
                    "calendar_plan_calendar_change",
                    "calendar_apply_calendar_change",
                    "contacts_search",
                    "contacts_get",
                    "contacts_plan_change",
                    "contacts_apply_change",
                    "photos_search",
                    "photos_get_asset",
                    "photos_list_album_assets",
                    "photos_export_asset",
                    "photos_plan_change",
                    "photos_apply_change",
                    "reminders_search",
                    "reminders_due",
                    "reminders_eventkit_search",
                    "reminders_search_lists",
                    "reminders_list_lists",
                    "reminders_get_list",
                    "reminders_list_items",
                    "reminders_get_content",
                    "reminders_plan_change",
                    "reminders_apply_change",
                    "reminders_plan_list_change",
                    "reminders_apply_list_change",
                }.issubset(names)
                for tool in tools.tools:
                    if tool.name in names:
                        assert tool.annotations is not None
                        if tool.name in {
                            "reminders_apply_change",
                            "reminders_apply_list_change",
                            "icloud_drive_apply_change",
                            "filesystem_apply_change",
                            "calendar_apply_change",
                            "calendar_apply_calendar_change",
                            "contacts_apply_change",
                            "notes_apply_change",
                            "mail_apply_change",
                            "messages_apply_change",
                            "photos_apply_change",
                            "mail_build_fts_index",
                            "mail_create_template",
                            "mail_delete_template",
                            "mail_apply_mailbox_change",
                            "mail_apply_cleanup",
                            "shortcuts_apply_run",
                        }:
                            assert tool.annotations.readOnlyHint is False
                        else:
                            assert tool.annotations.readOnlyHint is True
                        if tool.name in {
                            "reminders_apply_change",
                            "reminders_apply_list_change",
                            "icloud_drive_apply_change",
                            "filesystem_apply_change",
                            "calendar_apply_change",
                            "calendar_apply_calendar_change",
                            "contacts_apply_change",
                            "notes_apply_change",
                            "mail_apply_change",
                            "photos_apply_change",
                            "mail_delete_template",
                            "mail_apply_mailbox_change",
                            "mail_apply_cleanup",
                            "shortcuts_apply_run",
                        }:
                            assert tool.annotations.destructiveHint is True
                            assert tool.annotations.idempotentHint is False
                        else:
                            assert tool.annotations.destructiveHint is False
                            assert tool.annotations.idempotentHint is True
                        assert tool.annotations.openWorldHint is False

    asyncio.run(run())


def _mcp_shortcuts_run_runner(command: list[str], _timeout: float):
    from local_apple_data.adapters.shortcuts import ShortcutCommandResult

    identifier = "11111111-1111-1111-1111-111111111111"
    if command == ["/usr/bin/shortcuts", "list", "--show-identifiers"]:
        return ShortcutCommandResult(0, f"MCP Shortcut ({identifier})\n")
    if command == ["/usr/bin/shortcuts", "list", "--folders", "--show-identifiers"]:
        return ShortcutCommandResult(0, "MCP Folder (33333333-3333-3333-3333-333333333333)\n")
    if command[:3] == ["/usr/bin/shortcuts", "run", identifier]:
        return ShortcutCommandResult(0, "mcp-run-output\n")
    return ShortcutCommandResult(1, "", "unexpected command")


def test_shortcuts_plan_run_and_apply_run_wrappers_gate_and_prove_invocation(monkeypatch) -> None:
    from local_apple_data.adapters import shortcuts as shortcuts_adapter

    def _search(query, **kwargs):
        return shortcuts_adapter.search_shortcuts_items(
            query, runner=_mcp_shortcuts_run_runner, **{k: v for k, v in kwargs.items() if k != "runner"}
        )

    monkeypatch.setattr("local_apple_data.mcp_server.plan_shortcuts_run", lambda *a, **k: shortcuts_adapter.plan_shortcuts_run(*a, runner=_mcp_shortcuts_run_runner, **k))
    monkeypatch.setattr("local_apple_data.mcp_server.apply_shortcuts_run", lambda *a, **k: shortcuts_adapter.apply_shortcuts_run(*a, runner=_mcp_shortcuts_run_runner, **k))

    handle = shortcuts_adapter.search_shortcuts_items("MCP Shortcut", runner=_mcp_shortcuts_run_runner)["results"][0]["handle"]

    plan = shortcuts_plan_run("run", handle=handle, input_text="mcp input")
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["effects_verifiable_by_read_back"] is False
    token = "shortcuts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    missing = shortcuts_apply_run("run", handle=handle, approval_token=token, confirm_apply=False)
    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_apply_confirmation"

    applied = shortcuts_apply_run("run", handle=handle, input_text="mcp input", approval_token=token, confirm_apply=True)
    assert applied["status"] == "ok"
    assert applied["mutation_applied"] is True
    assert applied["read_back"]["invocation_confirmed"] is True
    assert applied["read_back"]["side_effects_verified"] is False


def test_shortcuts_apply_run_wrapper_rejects_spoofed_handle() -> None:
    result = shortcuts_apply_run(
        "run",
        handle="notes:note:v2:forged",
        approval_token="shortcuts-apply:v1:deadbeef",
        confirm_apply=True,
    )
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
