from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Literal

sys.dont_write_bytecode = True

from .operator_env import OperatorEnvError, load_operator_env

OPERATOR_LOCAL_ENV_PATH = Path(__file__).resolve().parents[2] / ".env.local"

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .adapters.books import get_book, list_book_annotations, search_books
from .adapters.calendar import (
    apply_calendar_calendar_change,
    apply_calendar_change,
    get_calendar_calendar,
    get_calendar_event,
    get_calendar_participant,
    list_calendar_events_for_calendar,
    list_calendar_participants,
    plan_calendar_calendar_change,
    plan_calendar_change,
    search_calendar_calendars,
    search_calendar_events,
)
from .adapters.contacts import (
    apply_contact_change,
    count_contacts,
    export_contacts_archive,
    get_contact,
    get_contact_container,
    get_contact_group,
    list_contact_container_members,
    list_contact_group_members,
    plan_contact_change,
    search_contact_containers,
    search_contact_groups,
    search_contacts,
)
from .adapters.freeform import (
    get_freeform_board,
    get_freeform_folder,
    list_freeform_child_folders,
    list_freeform_folder_boards,
    list_freeform_boards,
    search_freeform_folders,
)
from .adapters.icloud_drive import (
    apply_icloud_drive_change,
    export_icloud_drive_file,
    get_icloud_drive_content,
    get_icloud_drive_metadata,
    get_icloud_drive_root_metadata,
    list_icloud_drive_folder,
    list_icloud_drive_folder_tree,
    plan_icloud_drive_change,
    search_icloud_drive_metadata,
)
from .adapters.filesystem import (
    apply_filesystem_change,
    export_filesystem_file,
    get_filesystem_content,
    get_filesystem_metadata,
    get_filesystem_root_metadata,
    list_filesystem_folder,
    list_filesystem_folder_tree,
    plan_filesystem_change,
    search_filesystem_metadata,
)
from .adapters.hide_my_email import get_hide_my_email_alias, search_hide_my_email_aliases
from .adapters.mail import (
    apply_mail_change,
    apply_mail_cleanup,
    apply_mail_mailbox_change,
    build_mail_fts_index,
    create_mail_template,
    delete_mail_template,
    export_mail_attachment,
    get_mail_content,
    get_mail_fts_status,
    get_mail_mailbox,
    get_mail_metadata,
    get_mail_sender,
    get_mail_signature,
    get_mail_template,
    get_mail_unsubscribe_metadata,
    list_mail_attachments,
    list_mail_mailbox_messages,
    plan_mail_change,
    plan_mail_cleanup,
    plan_mail_mailbox_change,
    plan_mail_search_triage,
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
from .adapters.messages import (
    apply_messages_change,
    export_message_attachment,
    get_message_chat,
    get_message_participant,
    list_message_attachments,
    list_message_participants,
    plan_messages_change,
    search_message_chats,
)
from .adapters.music import (
    get_music_playlist,
    get_music_track,
    list_music_playlist_tracks,
    search_music_playlists,
    search_music_tracks,
)
from .adapters.notes import (
    apply_notes_change,
    export_notes_attachment,
    export_notes_folder_content,
    get_notes_content,
    get_notes_folder,
    get_notes_metadata,
    list_notes_attachments,
    list_notes_folder_items,
    list_notes_folder_tree,
    plan_notes_change,
    search_notes_folders,
    search_notes_metadata,
)
from .adapters.photos import (
    apply_photo_change,
    export_photo_asset,
    get_photo_album,
    get_photo_asset,
    list_photo_album_assets,
    plan_photo_change,
    search_photo_albums,
    search_photos,
)
from .adapters.podcasts import (
    get_podcast_episode,
    get_podcast_show,
    list_podcast_episodes,
    search_podcasts,
)
from .adapters.reminders import (
    apply_reminder_list_change,
    apply_reminder_change,
    due_reminders_metadata,
    get_reminder_content,
    get_reminder_list,
    list_reminder_items,
    list_reminder_lists,
    plan_reminder_list_change,
    plan_reminder_change,
    search_reminder_lists,
    search_reminders_eventkit,
    search_reminders_metadata,
)
from .adapters.voice_memos import (
    export_voice_memo_audio,
    get_voice_memo_recording,
    search_voice_memos,
)
from .adapters.safari import (
    get_safari_folder,
    get_safari_item,
    list_safari_folder_items,
    search_safari_folders,
    search_safari_items,
)
from .adapters.shortcuts import (
    apply_shortcuts_run,
    get_shortcuts_item,
    list_shortcuts_folder_items,
    plan_shortcuts_run,
    search_shortcuts_items,
)
from .adapters.tv import (
    get_tv_item,
    get_tv_playlist,
    list_tv_playlist_items,
    search_tv_items,
    search_tv_playlists,
)
from .doctor import build_doctor
from .health import build_health
from .redacted_log import log_result


ICloudDriveOperation = Literal[
    "create_text",
    "create-text",
    "create_folder",
    "create-folder",
    "create_folder_path",
    "create-folder-path",
    "rename_folder",
    "rename-folder",
    "trash_folder",
    "trash-folder",
    "delete_folder",
    "delete-folder",
    "move_folder",
    "move-folder",
    "copy_folder",
    "copy-folder",
    "import_file",
    "import-file",
    "replace_file",
    "replace-file",
    "trash_file",
    "trash-file",
    "delete_file",
    "delete-file",
    "append_text",
    "append-text",
    "replace_text",
    "replace-text",
    "trash_text",
    "trash-text",
    "delete_text",
    "delete-text",
    "rename_text",
    "rename-text",
    "copy_text",
    "copy-text",
    "move_text",
    "move-text",
    "rename_file",
    "rename-file",
    "copy_file",
    "copy-file",
    "move_file",
    "move-file",
]

FilesystemOperation = Literal[
    "create_text",
    "create-text",
    "create_folder",
    "create-folder",
    "create_folder_path",
    "create-folder-path",
    "rename_folder",
    "rename-folder",
    "trash_folder",
    "trash-folder",
    "delete_folder",
    "delete-folder",
    "move_folder",
    "move-folder",
    "copy_folder",
    "copy-folder",
    "import_file",
    "import-file",
    "replace_file",
    "replace-file",
    "trash_file",
    "trash-file",
    "delete_file",
    "delete-file",
    "append_text",
    "append-text",
    "replace_text",
    "replace-text",
    "trash_text",
    "trash-text",
    "delete_text",
    "delete-text",
    "rename_text",
    "rename-text",
    "copy_text",
    "copy-text",
    "move_text",
    "move-text",
    "rename_file",
    "rename-file",
    "copy_file",
    "copy-file",
    "move_file",
    "move-file",
]

# Budget for the part of INSTRUCTIONS that must actually reach a model. Clients may
# truncate this string: Claude Code 2.1.165 cuts it at 2048 characters, appending an
# ellipsis marker and logging the cut, but giving the model no way to recover what was
# dropped (observed 2026-07-30). This constant is deliberately below that so the repo owns
# a budget with margin rather than transcribing another product's private constant; if a
# client ever truncates lower, lower this and shorten the body.
CLIENT_INSTRUCTION_BUDGET_CHARS = 1900

# Order matters here, and not for style. Everything past a client's cut is invisible at
# runtime, so the mutation gating rule leads: it is the most important sentence here, and
# it previously sat last, inside the discarded tail, where no Claude Code model ever read
# it. The apply-surface enumeration at the end is required verbatim in this file by
# scripts/audit_mutation_gates.py and is redundant with tools/list, so it is the right
# thing to leave beyond the cut. tests/test_mcp_server.py enforces the ordering and the
# budget so this cannot silently regress.
INSTRUCTIONS = (
    "The *_plan_change and *_apply_change pair is the mutation path: apply requires the "
    "matching plan approval token plus explicit confirmation, and re-derives the plan "
    "from your own arguments, so argument drift between the two calls is refused. Other "
    "write tools carry their own confirm flag instead. "
    "Use these tools for local Apple data only. Stay metadata-first and "
    "bounded. Do not use Gmail connector paths. Do not request broad dumps. "
    "Mail subject search stays metadata-only. Mail body, advanced, attachment discovery, and opt-in FTS searches require date bounds, return capped redacted snippets or attachment metadata only, and still require exact handles for full content/export. Mail FTS build is an explicit local private cache write; Mail FTS search opens the existing index read-only and skips stale content rows. Across every surface, detail and export retrieval is exact-handle only: pass a handle exactly as a search returned it, and never construct, edit, or guess one. tools/list names the per-surface tools. Safari folder listing returns direct child metadata only and no full URLs. Shortcuts selected-folder listing is exact-handle only and returns names, kinds, opaque handles, and no raw identifiers or shortcut bodies. Mail sender selection is approved for draft/send/reply/reply-all/forward through an exact mail:sender:v1 handle and masked sender metadata. Messages participant list returns no phone/email previews. "
    "Mail/Messages/Notes attachment exports require exact handles and return no inline bytes. "
    "Outbound Mail may use bounded caller-selected local attachments; output returns no paths or bytes. "
    "Contacts note gates are designed and synthetic-testable, but live calls fail closed with `contacts_note_unavailable` because the restricted entitlement is absent. "
    "The only apply-capable mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact URL update/clear/exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear/exact same-source list-move/delete apply and exact list create/rename/empty-delete/same-source migrate-delete apply, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply, Calendar create-event/update/delete apply including exact relative alarm offsets, exact absolute display alarms, exact audio alarms, exact email alarms, exact structured geofence alarms, explicit timed-event time zones, exact availability create/update with expected-state binding, exact allow-listed event URL create/update and exact event URL clearing with hash-only read-back proof, exact target-calendar create/move, date-only all-day inference, simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly recurrence create and add-to-non-recurring-event update with weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year and selector-backed set-position filtering, selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected-occurrence recurring-event delete, future-event recurring span delete, whole-series recurring-event delete, first-visible and mid-series recurrence clearing, mid-series recurrence replacement, future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, and structured event location create/update/clear, apply from approved explicit default-calendar create plans only through the resolved exact calendar handle, and Calendar synthetic `LAD-TEST-*` calendar create/rename/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Mail synthetic `LAD-TEST-*` mailbox create/rename apply, source-gated synthetic mailbox delete and synthetic cleanup apply only when public Mail.app deletion plus exact target-state binding, mailbox-scoped absence proof, and Mail-idle guards succeed, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete apply with full Photos Library authorization, and Messages send-text/send-file apply, home-directory Filesystem create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply rooted at the operator home directory reusing the exact iCloud Drive within-root plan/apply/read-back gates with a credential/secret path denylist, and Shortcuts run apply of one exact identifier-bound shortcut through the plan/apply approval-token/confirm gate, resolved by an exact `shortcuts:item:v1:` handle with the resolved identifier bound into the approval fingerprint, invoked by argv (never a shell string) under a hard execution timeout, proving invocation of the named shortcut only because a shortcut's arbitrary side effects are not verifiable by read-back."
)

mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

DESTRUCTIVE_WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)


def _record(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    log_result(f"mcp.{command}", payload)
    return payload


def _safe_mcp_error(command: str, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": command,
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "error",
        },
        "warnings": [
            {
                "code": "mcp_tool_error",
                "message": f"MCP tool failed safely: {exc.__class__.__name__}",
            }
        ],
    }


def _record_tool(
    command: str,
    producer: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        payload = producer()
    except Exception as exc:
        payload = _safe_mcp_error(command, exc)
    return _record(command, payload)


def _record_readiness(
    command: str,
    producer: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return _record_tool(command, producer)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def apple_data_health() -> dict[str, Any]:
    """Return redacted local readiness, schema checks, and access requirements."""

    return _record_readiness("apple_data_health", build_health)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def apple_data_doctor() -> dict[str, Any]:
    """Return redacted non-mutating diagnostics and remediation guidance."""

    return _record_readiness("apple_data_doctor", build_doctor)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search(query: str, limit: int = 20, mailbox_handle: str = "") -> dict[str, Any]:
    """Search local Mail metadata by subject, including metadata-only content availability."""

    return _record_tool(
        "mail_search",
        lambda: search_mail_metadata(query, limit=limit, mailbox_handle=mailbox_handle),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_body(
    query: str,
    after: str = "",
    before: str = "",
    cursor: str = "",
    limit: int = 20,
    max_snippet_chars: int = 240,
    max_seconds: float = 20,
) -> dict[str, Any]:
    """Search local Mail body text within a required date range; returns capped redacted snippets only."""

    return _record_tool(
        "mail_search_body",
        lambda: search_mail_body(
            query,
            after=after or None,
            before=before or None,
            cursor=cursor,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
            max_seconds=max_seconds,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_attachments(
    query: str,
    after: str = "",
    before: str = "",
    cursor: str = "",
    limit: int = 20,
    include_content: bool = False,
    include_ocr: bool = False,
    max_snippet_chars: int = 240,
    max_seconds: float = 20,
) -> dict[str, Any]:
    """Search local Mail attachment filename/MIME metadata, and optionally text/PDF/OCR snippets, within a required date range."""

    return _record_tool(
        "mail_search_attachments",
        lambda: search_mail_attachments(
            query,
            after=after or None,
            before=before or None,
            cursor=cursor,
            limit=limit,
            include_content=include_content,
            include_ocr=include_ocr,
            max_snippet_chars=max_snippet_chars,
            max_seconds=max_seconds,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_advanced(
    query: str,
    scopes: list[str] | None = None,
    after: str = "",
    before: str = "",
    mailbox: str = "",
    has_attachments: bool | None = None,
    cursor: str = "",
    limit: int = 20,
    max_snippet_chars: int = 240,
    max_seconds: float = 20,
) -> dict[str, Any]:
    """Search Mail subject/from/to/cc/bcc/body/attachment metadata within a required date range."""

    return _record_tool(
        "mail_search_advanced",
        lambda: search_mail_advanced(
            query,
            scopes=scopes,
            after=after or None,
            before=before or None,
            mailbox=mailbox,
            has_attachments=has_attachments,
            cursor=cursor,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
            max_seconds=max_seconds,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def mail_build_fts_index(
    after: str = "",
    before: str = "",
    cursor: str = "",
    limit: int = 1000,
    include_attachments: bool = False,
    include_ocr: bool = False,
    confirm_index: bool = False,
    reset: bool = False,
    max_seconds: float = 20,
) -> dict[str, Any]:
    """Build an opt-in local Mail FTS index for a required date range; writes only to the local private index path."""

    return _record_tool(
        "mail_build_fts_index",
        lambda: build_mail_fts_index(
            after=after or None,
            before=before or None,
            cursor=cursor,
            limit=limit,
            include_attachments=include_attachments,
            include_ocr=include_ocr,
            confirm_index=confirm_index,
            reset=reset,
            max_seconds=max_seconds,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_fts_status() -> dict[str, Any]:
    """Report the opt-in local Mail FTS index state: missing, building, partial, ready, or stale, with coverage counts and the resume checkpoint."""

    return _record_tool("mail_fts_status", lambda: get_mail_fts_status())


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_fts(
    query: str,
    scopes: list[str] | None = None,
    after: str = "",
    before: str = "",
    cursor: str = "",
    limit: int = 20,
    max_snippet_chars: int = 240,
) -> dict[str, Any]:
    """Search the opt-in local Mail FTS index within a required date range; returns capped redacted snippets only."""

    return _record_tool(
        "mail_search_fts",
        lambda: search_mail_fts(
            query,
            scopes=scopes,
            after=after or None,
            before=before or None,
            cursor=cursor,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact local Mail metadata by handle, including masked headers and attachment names when local files are available."""

    return _record_tool("mail_get_metadata", lambda: get_mail_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_mailboxes(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Mail mailbox metadata by name for exact move targets."""

    return _record_tool(
        "mail_search_mailboxes",
        lambda: search_mail_mailboxes(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_mailbox(handle: str) -> dict[str, Any]:
    """Get exact local Mail mailbox metadata by opaque mailbox handle."""

    return _record_tool("mail_get_mailbox", lambda: get_mail_mailbox(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_list_mailbox_messages(
    handle: str,
    after: str = "",
    before: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """List date-bounded local Mail message metadata for one exact mailbox handle."""

    return _record_tool(
        "mail_list_mailbox_messages",
        lambda: list_mail_mailbox_messages(
            handle,
            after=after or None,
            before=before or None,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_senders(query: str, limit: int = 20) -> dict[str, Any]:
    """Search configured local Mail sender metadata with masked email previews."""

    return _record_tool(
        "mail_search_senders",
        lambda: search_mail_senders(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_sender(handle: str) -> dict[str, Any]:
    """Get exact configured local Mail sender metadata by opaque sender handle."""

    return _record_tool("mail_get_sender", lambda: get_mail_sender(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_signatures(query: str, limit: int = 20) -> dict[str, Any]:
    """Search configured local Mail signature names without returning signature bodies."""

    return _record_tool(
        "mail_search_signatures",
        lambda: search_mail_signatures(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_signature(handle: str) -> dict[str, Any]:
    """Get exact configured local Mail signature metadata by opaque signature handle."""

    return _record_tool("mail_get_signature", lambda: get_mail_signature(handle))


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def mail_create_template(name: str, body_text: str, subject: str = "") -> dict[str, Any]:
    """Create a plugin-managed Mail template from explicit user-provided plain text."""

    return _record_tool(
        "mail_create_template",
        lambda: create_mail_template(name, body_text, subject=subject),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search_templates(query: str = "", limit: int = 20) -> dict[str, Any]:
    """Search plugin-managed Mail template metadata without returning template bodies."""

    return _record_tool(
        "mail_search_templates",
        lambda: search_mail_templates(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_template(handle: str, include_body: bool = False) -> dict[str, Any]:
    """Get exact plugin-managed Mail template metadata; body is returned only when requested."""

    return _record_tool(
        "mail_get_template",
        lambda: get_mail_template(handle, include_body=include_body),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def mail_delete_template(handle: str, confirm_delete: bool = False) -> dict[str, Any]:
    """Delete one exact plugin-managed Mail template by opaque handle."""

    return _record_tool(
        "mail_delete_template",
        lambda: delete_mail_template(handle, confirm_delete=confirm_delete),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_content(handle: str, max_chars: int = 4000, offset: int = 0) -> dict[str, Any]:
    """Get exact local Mail plain-text content by opaque v2 handle, capped, paged, and read-only."""

    return _record_tool(
        "mail_get_content",
        lambda: get_mail_content(handle, max_chars=max_chars, offset=offset),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_unsubscribe_metadata(
    handle: str,
    include_body_links: bool = False,
) -> dict[str, Any]:
    """Get exact list-header detail, optionally conservative manual links from the selected MIME body."""

    return _record_tool(
        "mail_get_unsubscribe_metadata",
        lambda: get_mail_unsubscribe_metadata(
            handle,
            include_body_links=include_body_links,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_list_attachments(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact local Mail attachment metadata by selected message handle, capped and read-only."""

    return _record_tool(
        "mail_list_attachments",
        lambda: list_mail_attachments(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_export_attachment(
    message_handle: str,
    attachment_handle: str,
    output_dir: str,
    filename: str = "",
) -> dict[str, Any]:
    """Export one exact local Mail attachment to a caller-selected directory without inline bytes."""

    return _record_tool(
        "mail_export_attachment",
        lambda: export_mail_attachment(
            message_handle,
            attachment_handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_plan_change(
    operation: str,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    message_handles: list[str] | None = None,
    target_mailbox_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
) -> dict[str, Any]:
    """Plan a future Mail create-draft/send/reply/reply-all/forward with optional sender/signature/template, optional local attachments, source-forward parts, or exact/bulk triage."""

    return _record_tool(
        "mail_plan_change",
        lambda: plan_mail_change(
            operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            message_handles=message_handles,
            target_mailbox_handle=target_mailbox_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            include_source_attachments=include_source_attachments,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def mail_apply_change(
    operation: str,
    approval_token: str,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    message_handle: str = "",
    message_handles: list[str] | None = None,
    target_mailbox_handle: str = "",
    sender_handle: str = "",
    signature_handle: str = "",
    template_handle: str = "",
    attachment_paths: list[str] | None = None,
    include_source_attachments: bool = False,
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Mail change; optional sender/signature and attachments are accepted for draft/send/reply/reply-all/forward."""

    return _record_tool(
        "mail_apply_change",
        lambda: apply_mail_change(
            operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            message_handle=message_handle,
            message_handles=message_handles,
            target_mailbox_handle=target_mailbox_handle,
            sender_handle=sender_handle,
            signature_handle=signature_handle,
            template_handle=template_handle,
            attachment_paths=attachment_paths,
            include_source_attachments=include_source_attachments,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_plan_search_triage(
    operation: str,
    query: str,
    search_source: str = "fts",
    scopes: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
    cursor: str = "",
    limit: int = 20,
    target_mailbox_handle: str = "",
) -> dict[str, Any]:
    """Convert capped durable FTS query results into an exact-handle bulk triage plan."""

    return _record_tool(
        "mail_plan_search_triage",
        lambda: plan_mail_search_triage(
            operation,
            query,
            search_source=search_source,
            scopes=scopes,
            after=after,
            before=before,
            cursor=cursor,
            limit=limit,
            target_mailbox_handle=target_mailbox_handle,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_plan_mailbox_change(
    operation: str,
    sender_handle: str = "",
    mailbox_handle: str = "",
    mailbox_name: str = "",
    new_mailbox_name: str = "",
) -> dict[str, Any]:
    """Plan a synthetic LAD-TEST-* Mail mailbox create/rename/delete operation."""

    return _record_tool(
        "mail_plan_mailbox_change",
        lambda: plan_mail_mailbox_change(
            operation,
            sender_handle=sender_handle,
            mailbox_handle=mailbox_handle,
            mailbox_name=mailbox_name,
            new_mailbox_name=new_mailbox_name,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def mail_apply_mailbox_change(
    operation: str,
    approval_token: str,
    sender_handle: str = "",
    mailbox_handle: str = "",
    mailbox_name: str = "",
    new_mailbox_name: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved synthetic LAD-TEST-* Mail mailbox create/rename/delete operation."""

    return _record_tool(
        "mail_apply_mailbox_change",
        lambda: apply_mail_mailbox_change(
            operation,
            sender_handle=sender_handle,
            mailbox_handle=mailbox_handle,
            mailbox_name=mailbox_name,
            new_mailbox_name=new_mailbox_name,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_plan_cleanup(
    operation: str,
    message_handle: str = "",
    sender_handle: str = "",
) -> dict[str, Any]:
    """Plan synthetic-only Mail permanent delete or empty Trash/Junk cleanup."""

    return _record_tool(
        "mail_plan_cleanup",
        lambda: plan_mail_cleanup(
            operation,
            message_handle=message_handle,
            sender_handle=sender_handle,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def mail_apply_cleanup(
    operation: str,
    approval_token: str,
    message_handle: str = "",
    sender_handle: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply approved synthetic-only Mail permanent delete or empty Trash/Junk cleanup."""

    return _record_tool(
        "mail_apply_cleanup",
        lambda: apply_mail_cleanup(
            operation,
            message_handle=message_handle,
            sender_handle=sender_handle,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Messages chat metadata by display name, capped and read-only."""

    return _record("messages_search", search_message_chats(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_get_chat(
    handle: str,
    max_messages: int = 25,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Get exact local Messages chat transcript by opaque handle, capped and read-only."""

    return _record(
        "messages_get_chat",
        get_message_chat(handle, max_messages=max_messages, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_list_attachments(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact local Messages attachment metadata by selected chat handle, capped and read-only."""

    return _record("messages_list_attachments", list_message_attachments(handle, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_list_participants(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact local Messages participant metadata by selected chat handle, capped and read-only."""

    return _record("messages_list_participants", list_message_participants(handle, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_get_participant(chat_handle: str, participant_handle: str) -> dict[str, Any]:
    """Get exact local Messages participant detail by chat and participant opaque handles."""

    return _record(
        "messages_get_participant",
        get_message_participant(chat_handle, participant_handle),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_export_attachment(
    chat_handle: str,
    attachment_handle: str,
    output_dir: str,
    filename: str = "",
) -> dict[str, Any]:
    """Export one exact local Messages attachment to a caller-selected directory without inline bytes."""

    return _record(
        "messages_export_attachment",
        export_message_attachment(
            chat_handle,
            attachment_handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def messages_plan_change(
    operation: str,
    handle: str,
    body_text: str = "",
    file_path: str = "",
) -> dict[str, Any]:
    """Plan a future exact-chat Messages text or file send without applying it."""

    return _record(
        "messages_plan_change",
        plan_messages_change(operation, handle=handle, body_text=body_text, file_path=file_path),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def messages_apply_change(
    operation: str,
    handle: str,
    approval_token: str,
    body_text: str = "",
    confirm_apply: bool = False,
    file_path: str = "",
) -> dict[str, Any]:
    """Apply an approved exact-chat Messages text or file send and verify local read-back."""

    return _record(
        "messages_apply_change",
        apply_messages_change(
            operation,
            handle=handle,
            body_text=body_text,
            file_path=file_path,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def hide_my_email_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search inferred Hide My Email aliases from local Mail metadata, capped and read-only."""

    return _record(
        "hide_my_email_search",
        search_hide_my_email_aliases(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def hide_my_email_get_alias(handle: str) -> dict[str, Any]:
    """Get exact inferred Hide My Email alias detail by opaque handle, capped and read-only."""

    return _record("hide_my_email_get_alias", get_hide_my_email_alias(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def voice_memos_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Voice Memos metadata by title or filename, capped and read-only."""

    return _record("voice_memos_search", search_voice_memos(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def voice_memos_get_recording(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local Voice Memo metadata/transcript by opaque handle, capped and read-only."""

    return _record(
        "voice_memos_get_recording",
        get_voice_memo_recording(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def voice_memos_export_audio(
    handle: str,
    output_dir: str,
    filename: str = "",
) -> dict[str, Any]:
    """Export exact local Voice Memo audio by opaque handle to a caller-selected directory."""

    return _record(
        "voice_memos_export_audio",
        export_voice_memo_audio(
            handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def safari_search(
    query: str,
    limit: int = 20,
    kind: str = "all",
    max_scan_items: int = 20000,
) -> dict[str, Any]:
    """Search local Safari bookmarks and Reading List metadata, capped and read-only."""

    return _record(
        "safari_search",
        search_safari_items(
            query,
            limit=limit,
            kind=kind,
            max_scan_items=max_scan_items,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def safari_get_item(handle: str, max_scan_items: int = 20000) -> dict[str, Any]:
    """Get exact Safari bookmark or Reading List detail by opaque handle, capped and read-only."""

    return _record(
        "safari_get_item",
        get_safari_item(handle, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def safari_search_folders(
    query: str,
    limit: int = 20,
    max_scan_items: int = 20000,
) -> dict[str, Any]:
    """Search local Safari bookmark folder metadata, capped and read-only."""

    return _record(
        "safari_search_folders",
        search_safari_folders(query, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def safari_get_folder(handle: str, max_scan_items: int = 20000) -> dict[str, Any]:
    """Get exact Safari bookmark folder metadata by opaque handle, capped and read-only."""

    return _record(
        "safari_get_folder",
        get_safari_folder(handle, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def safari_list_folder_items(
    handle: str,
    limit: int = 20,
    max_scan_items: int = 20000,
) -> dict[str, Any]:
    """List direct Safari bookmark metadata for one exact folder handle."""

    return _record(
        "safari_list_folder_items",
        list_safari_folder_items(handle, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def shortcuts_search(
    query: str,
    limit: int = 20,
    kind: str = "all",
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """Search Apple Shortcuts shortcut/folder metadata, capped and read-only."""

    return _record(
        "shortcuts_search",
        search_shortcuts_items(
            query,
            limit=limit,
            kind=kind,
            max_scan_items=max_scan_items,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def shortcuts_get_item(handle: str, max_scan_items: int = 5000) -> dict[str, Any]:
    """Get exact Apple Shortcuts metadata by opaque handle, capped and read-only."""

    return _record(
        "shortcuts_get_item",
        get_shortcuts_item(handle, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def shortcuts_list_folder_items(
    handle: str,
    limit: int = 20,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """List exact selected Shortcuts folder shortcut metadata by opaque folder handle."""

    return _record(
        "shortcuts_list_folder_items",
        list_shortcuts_folder_items(
            handle,
            limit=limit,
            max_scan_items=max_scan_items,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def shortcuts_plan_run(
    operation: str,
    handle: str,
    input_text: str = "",
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """Plan an exact identifier-bound Shortcuts run without executing it; effects are arbitrary and unverifiable."""

    return _record(
        "shortcuts_plan_run",
        plan_shortcuts_run(
            operation,
            handle=handle,
            input_text=input_text,
            max_scan_items=max_scan_items,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def shortcuts_apply_run(
    operation: str,
    handle: str,
    approval_token: str,
    input_text: str = "",
    confirm_apply: bool = False,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """Apply an approved exact identifier-bound Shortcuts run; proves invocation only, not the shortcut's arbitrary effects."""

    return _record(
        "shortcuts_apply_run",
        apply_shortcuts_run(
            operation,
            handle=handle,
            input_text=input_text,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
            max_scan_items=max_scan_items,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def books_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Books metadata by title, author, or genre."""

    return _record("books_search", search_books(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def books_get(handle: str) -> dict[str, Any]:
    """Get exact local Apple Books metadata by opaque handle."""

    return _record("books_get", get_book(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def books_list_annotations(
    handle: str,
    limit: int = 20,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """List bounded annotations for one exact selected Apple Books book handle."""

    return _record(
        "books_list_annotations",
        list_book_annotations(handle, limit=limit, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def podcasts_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Podcasts show metadata by title, author, category, or provider."""

    return _record("podcasts_search", search_podcasts(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def podcasts_get_show(handle: str) -> dict[str, Any]:
    """Get exact local Apple Podcasts show metadata by opaque handle."""

    return _record("podcasts_get_show", get_podcast_show(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def podcasts_list_episodes(handle: str, limit: int = 20) -> dict[str, Any]:
    """List bounded episode metadata for one exact selected Apple Podcasts show handle."""

    return _record(
        "podcasts_list_episodes",
        list_podcast_episodes(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def podcasts_get_episode(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact Apple Podcasts episode metadata and bounded description by opaque handle."""

    return _record(
        "podcasts_get_episode",
        get_podcast_episode(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def music_search(query: str, limit: int = 20, max_scan_items: int = 5000) -> dict[str, Any]:
    """Search local Apple Music track metadata by title, artist, album, or genre."""

    return _record(
        "music_search",
        search_music_tracks(query, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def music_get_track(handle: str, max_scan_items: int = 5000) -> dict[str, Any]:
    """Get exact local Apple Music track metadata by opaque handle."""

    return _record("music_get_track", get_music_track(handle, max_scan_items=max_scan_items))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def music_search_playlists(
    query: str,
    limit: int = 20,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """Search local Apple Music playlist metadata by name."""

    return _record(
        "music_search_playlists",
        search_music_playlists(query, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def music_get_playlist(handle: str, max_scan_items: int = 5000) -> dict[str, Any]:
    """Get exact local Apple Music playlist metadata by opaque handle."""

    return _record(
        "music_get_playlist",
        get_music_playlist(handle, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def music_list_playlist_tracks(
    handle: str,
    limit: int = 20,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """List exact selected Apple Music playlist track metadata by playlist handle."""

    return _record(
        "music_list_playlist_tracks",
        list_music_playlist_tracks(handle, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def tv_search(query: str, limit: int = 20, max_scan_items: int = 5000) -> dict[str, Any]:
    """Search local Apple TV item metadata by title, show, artist, genre, or kind."""

    return _record(
        "tv_search",
        search_tv_items(query, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def tv_get_item(handle: str, max_scan_items: int = 5000) -> dict[str, Any]:
    """Get exact local Apple TV item metadata by opaque handle."""

    return _record("tv_get_item", get_tv_item(handle, max_scan_items=max_scan_items))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def tv_search_playlists(
    query: str,
    limit: int = 20,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """Search local Apple TV playlist metadata by name."""

    return _record(
        "tv_search_playlists",
        search_tv_playlists(query, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def tv_get_playlist(handle: str, max_scan_items: int = 5000) -> dict[str, Any]:
    """Get exact local Apple TV playlist metadata by opaque handle."""

    return _record("tv_get_playlist", get_tv_playlist(handle, max_scan_items=max_scan_items))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def tv_list_playlist_items(
    handle: str,
    limit: int = 20,
    max_scan_items: int = 5000,
) -> dict[str, Any]:
    """List exact selected Apple TV playlist item metadata by playlist handle."""

    return _record(
        "tv_list_playlist_items",
        list_tv_playlist_items(handle, limit=limit, max_scan_items=max_scan_items),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_list_boards(limit: int = 20) -> dict[str, Any]:
    """List recent local Apple Freeform board metadata, capped and read-only."""

    return _record("freeform_list_boards", list_freeform_boards(limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_get_board(handle: str) -> dict[str, Any]:
    """Get exact local Apple Freeform board metadata by opaque handle."""

    return _record("freeform_get_board", get_freeform_board(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_search_folders(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Freeform folder metadata by folder title."""

    return _record(
        "freeform_search_folders",
        search_freeform_folders(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_get_folder(handle: str) -> dict[str, Any]:
    """Get exact local Apple Freeform folder metadata by opaque handle."""

    return _record("freeform_get_folder", get_freeform_folder(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_list_folder_boards(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact selected Apple Freeform folder board metadata by folder handle."""

    return _record(
        "freeform_list_folder_boards",
        list_freeform_folder_boards(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def freeform_list_child_folders(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact selected Apple Freeform child folder metadata by folder handle."""

    return _record(
        "freeform_list_child_folders",
        list_freeform_child_folders(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Notes metadata by title/snippet, capped and read-only."""

    return _record("notes_search", search_notes_metadata(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_search_folders(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Notes folder metadata by folder title, capped and read-only."""

    return _record("notes_search_folders", search_notes_folders(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_get_folder(handle: str) -> dict[str, Any]:
    """Get exact Apple Notes folder metadata by opaque handle."""

    return _record("notes_get_folder", get_notes_folder(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_list_folder_items(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact selected Apple Notes folder direct note and child-folder metadata by opaque handle."""

    return _record(
        "notes_list_folder_items",
        list_notes_folder_items(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_list_folder_tree(handle: str, depth: int = 2, limit: int = 50) -> dict[str, Any]:
    """List bounded Apple Notes child-folder metadata tree by opaque folder handle."""

    return _record(
        "notes_list_folder_tree",
        list_notes_folder_tree(handle, depth=depth, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact Apple Notes metadata by handle. Note bodies are not returned."""

    return _record("notes_get_metadata", get_notes_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_get_content(
    handle: str,
    max_chars: int = 4000,
    offset: int = 0,
    content_format: str = "text",
) -> dict[str, Any]:
    """Get exact local Notes content by opaque v2 handle, capped, paged, and read-only; content_format='html' also returns the bounded rich-text body plus its extracted visible text."""

    return _record(
        "notes_get_content",
        get_notes_content(
            handle,
            max_chars=max_chars,
            offset=offset,
            content_format=content_format,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_export_folder_content(
    folder_handle: str,
    modified_after: str,
    cursor: int = 0,
    limit: int = 10,
    max_chars_per_note: int = 4000,
    confirm_bulk: bool = False,
) -> dict[str, Any]:
    """Export bounded, paged note text for one exact normal Notes folder, date-bounded (modified_after ISO-8601 required) and confirm_bulk-gated: the v1.182 operator-approved bulk-content read for the operator's private downstream store. Returns per-note bounded text plus full-text content_sha256 and next_cursor; password-protected/deleted notes excluded, smart folders fail closed, read-only, nothing persisted by this server."""

    return _record(
        "notes_export_folder_content",
        export_notes_folder_content(
            folder_handle,
            modified_after,
            cursor=cursor,
            limit=limit,
            max_chars_per_note=max_chars_per_note,
            confirm_bulk=confirm_bulk,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_list_attachments(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact local Notes attachment metadata by selected note handle."""

    return _record(
        "notes_list_attachments",
        list_notes_attachments(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_export_attachment(
    handle: str,
    output_dir: str,
    filename: str = "",
) -> dict[str, Any]:
    """Export exact local Notes attachment bytes by attachment handle to a caller-selected directory."""

    return _record(
        "notes_export_attachment",
        export_notes_attachment(
            handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_plan_change(
    operation: str,
    title: str = "",
    body_text: str = "",
    body_html: str = "",
    handle: str = "",
    folder_handle: str = "",
    target_folder_handle: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    """Preview an approved Notes create-note, rich-text body create, create-folder, rename-folder, delete-folder, move-folder, append-text, replace-text, rich-text body replace, move-to-folder, or note delete change without writing Notes data."""

    return _record(
        "notes_plan_change",
        plan_notes_change(
            operation,
            title=title,
            handle=handle,
            folder_handle=folder_handle,
            target_folder_handle=target_folder_handle,
            body_text=body_text,
            body_html=body_html,
            expected_current_sha256=expected_current_sha256,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def notes_apply_change(
    operation: str,
    title: str = "",
    body_text: str = "",
    body_html: str = "",
    approval_token: str = "",
    handle: str = "",
    folder_handle: str = "",
    target_folder_handle: str = "",
    expected_current_sha256: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Notes create-note, rich-text body create, create-folder, rename-folder, delete-folder, move-folder, append-text, replace-text, rich-text body replace, move-to-folder, or note delete change after approval token and explicit confirmation."""

    return _record(
        "notes_apply_change",
        apply_notes_change(
            operation,
            title=title,
            handle=handle,
            folder_handle=folder_handle,
            target_folder_handle=target_folder_handle,
            body_text=body_text,
            body_html=body_html,
            expected_current_sha256=expected_current_sha256,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local iCloud Drive metadata by filename, capped and read-only."""

    return _record(
        "icloud_drive_search",
        search_icloud_drive_metadata(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_get_root() -> dict[str, Any]:
    """Get the local iCloud Drive root metadata and opaque directory handle, read-only."""

    return _record("icloud_drive_get_root", get_icloud_drive_root_metadata())


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact local iCloud Drive metadata by opaque handle. File content is not returned."""

    return _record("icloud_drive_get_metadata", get_icloud_drive_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_list_folder(handle: str, limit: int = 20) -> dict[str, Any]:
    """List direct children of one exact local iCloud Drive folder by opaque handle, capped and read-only."""

    return _record(
        "icloud_drive_list_folder",
        list_icloud_drive_folder(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_list_tree(handle: str, depth: int = 2, limit: int = 50) -> dict[str, Any]:
    """List a bounded recursive metadata tree for one exact local iCloud Drive folder by opaque handle, capped and read-only."""

    return _record(
        "icloud_drive_list_tree",
        list_icloud_drive_folder_tree(handle, depth=depth, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_get_content(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local iCloud Drive text content by opaque handle, capped and read-only."""

    return _record(
        "icloud_drive_get_content",
        get_icloud_drive_content(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_export_file(
    handle: str,
    output_dir: str,
    filename: str = "",
    max_bytes: int = 250 * 1024 * 1024,
) -> dict[str, Any]:
    """Export one exact local iCloud Drive regular file by opaque handle to a caller-selected directory outside iCloud Drive. File bytes are not returned inline."""

    return _record(
        "icloud_drive_export_file",
        export_icloud_drive_file(
            handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
            max_bytes=max_bytes,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_plan_change(
    operation: ICloudDriveOperation,
    content_text: str = "",
    parent_handle: str = "",
    filename: str = "",
    folder_components: list[str] | None = None,
    source_file: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    """Plan a future iCloud Drive folder, text-file, or regular-file change without mutating local files."""

    return _record(
        "icloud_drive_plan_change",
        plan_icloud_drive_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
            folder_components=folder_components,
            source_file=source_file,
            content_text=content_text,
            expected_current_sha256=expected_current_sha256,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def icloud_drive_apply_change(
    operation: ICloudDriveOperation,
    approval_token: str,
    content_text: str = "",
    parent_handle: str = "",
    filename: str = "",
    folder_components: list[str] | None = None,
    source_file: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved iCloud Drive folder, text-file, or regular-file change and read back proof."""

    return _record(
        "icloud_drive_apply_change",
        apply_icloud_drive_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
            folder_components=folder_components,
            source_file=source_file,
            content_text=content_text,
            expected_current_sha256=expected_current_sha256,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local home-directory filesystem metadata by filename, capped and read-only. Hidden files and credential/secret paths never surface content."""

    return _record(
        "filesystem_search",
        search_filesystem_metadata(query, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_get_root() -> dict[str, Any]:
    """Get the local home-directory filesystem root metadata and opaque directory handle, read-only."""

    return _record("filesystem_get_root", get_filesystem_root_metadata())


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact local home-directory filesystem metadata by opaque handle. File content is not returned. Metadata is available even for credential/secret paths."""

    return _record("filesystem_get_metadata", get_filesystem_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_list_folder(handle: str, limit: int = 20) -> dict[str, Any]:
    """List direct children of one exact local home-directory folder by opaque handle, capped and read-only."""

    return _record(
        "filesystem_list_folder",
        list_filesystem_folder(handle, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_list_tree(handle: str, depth: int = 2, limit: int = 50) -> dict[str, Any]:
    """List a bounded recursive metadata tree for one exact local home-directory folder by opaque handle, capped and read-only."""

    return _record(
        "filesystem_list_tree",
        list_filesystem_folder_tree(handle, depth=depth, limit=limit),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_get_content(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local home-directory text content by opaque handle, capped and read-only. Content of credential/secret paths is refused with credential_path_blocked."""

    return _record(
        "filesystem_get_content",
        get_filesystem_content(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_export_file(
    handle: str,
    output_dir: str,
    filename: str = "",
    max_bytes: int = 250 * 1024 * 1024,
) -> dict[str, Any]:
    """Export one exact local home-directory regular file by opaque handle to a caller-selected directory outside the home root. File bytes are not returned inline. Credential/secret paths are refused."""

    return _record(
        "filesystem_export_file",
        export_filesystem_file(
            handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
            max_bytes=max_bytes,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def filesystem_plan_change(
    operation: FilesystemOperation,
    content_text: str = "",
    parent_handle: str = "",
    filename: str = "",
    folder_components: list[str] | None = None,
    source_file: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    """Plan a future home-directory folder, text-file, or regular-file change without mutating local files. Mutation of credential/secret paths is refused."""

    return _record(
        "filesystem_plan_change",
        plan_filesystem_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
            folder_components=folder_components,
            source_file=source_file,
            content_text=content_text,
            expected_current_sha256=expected_current_sha256,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def filesystem_apply_change(
    operation: FilesystemOperation,
    approval_token: str,
    content_text: str = "",
    parent_handle: str = "",
    filename: str = "",
    folder_components: list[str] | None = None,
    source_file: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved home-directory folder, text-file, or regular-file change and read back proof. Stays within the home root; credential/secret paths and symlink/package escapes are refused."""

    return _record(
        "filesystem_apply_change",
        apply_filesystem_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
            folder_components=folder_components,
            source_file=source_file,
            content_text=content_text,
            expected_current_sha256=expected_current_sha256,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_search(
    query: str,
    limit: int = 20,
    days_back: int = 365,
    days_forward: int = 730,
) -> dict[str, Any]:
    """Search local Calendar event metadata by title, capped and read-only."""

    return _record(
        "calendar_search",
        search_calendar_events(
            query,
            limit=limit,
            days_back=days_back,
            days_forward=days_forward,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_get_event(
    handle: str,
    max_chars: int = 4000,
    days_back: int = 365,
    days_forward: int = 730,
) -> dict[str, Any]:
    """Get exact local Calendar event details by opaque handle, capped and read-only."""

    return _record(
        "calendar_get_event",
        get_calendar_event(
            handle,
            max_chars=max_chars,
            days_back=days_back,
            days_forward=days_forward,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_list_participants(
    handle: str,
    limit: int = 20,
    days_back: int = 365,
    days_forward: int = 730,
) -> dict[str, Any]:
    """List exact local Calendar event participant metadata by opaque event handle."""

    return _record(
        "calendar_list_participants",
        list_calendar_participants(
            handle,
            limit=limit,
            days_back=days_back,
            days_forward=days_forward,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_get_participant(
    event_handle: str,
    participant_handle: str,
    days_back: int = 365,
    days_forward: int = 730,
) -> dict[str, Any]:
    """Get exact local Calendar participant detail by opaque event and participant handles."""

    return _record(
        "calendar_get_participant",
        get_calendar_participant(
            event_handle,
            participant_handle,
            days_back=days_back,
            days_forward=days_forward,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_search_calendars(
    query: str = "",
    limit: int = 20,
    include_default: bool = False,
) -> dict[str, Any]:
    """Search local Calendar target metadata by title, capped and read-only."""

    return _record(
        "calendar_search_calendars",
        search_calendar_calendars(
            query,
            limit=limit,
            include_default=include_default,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_get_calendar(handle: str) -> dict[str, Any]:
    """Get exact local Calendar target metadata by opaque handle, read-only."""

    return _record(
        "calendar_get_calendar",
        get_calendar_calendar(handle),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_list_calendar_events(
    handle: str,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> dict[str, Any]:
    """List selected local Calendar target event metadata in an explicit date window."""

    return _record(
        "calendar_list_calendar_events",
        list_calendar_events_for_calendar(
            handle,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_plan_change(
    operation: str,
    title: str = "",
    start_date: str = "",
    end_date: str = "",
    time_zone: str = "",
    all_day: bool = False,
    availability: str = "",
    alarm_offsets_minutes: list[int] | None = None,
    alarm_absolute_dates: list[str] | None = None,
    alarm_sound_name: str = "",
    alarm_email_address: str = "",
    alarm_proximity: str = "",
    alarm_structured_location: dict[str, Any] | None = None,
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str] | None = None,
    recurrence_month_days: list[int] | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | None = None,
    recurrence_year_months: list[int] | None = None,
    recurrence_year_month_days: list[int] | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | None = None,
    recurrence_year_days: list[int] | None = None,
    recurrence_year_weeks: list[int] | None = None,
    recurrence_set_positions: list[int] | None = None,
    recurrence_delete_scope: str = "",
    recurrence_update_scope: str = "",
    clear_recurrence: bool = False,
    event_url: str = "",
    clear_event_url: bool = False,
    calendar_title: str = "",
    calendar_handle: str = "",
    use_default_calendar: bool = False,
    target_calendar_handle: str = "",
    location: str = "",
    structured_location: dict[str, Any] | None = None,
    clear_structured_location: bool = False,
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_calendar_title: str = "",
    expected_start_date: str = "",
    expected_end_date: str = "",
    expected_time_zone: str = "",
    expected_all_day: bool = False,
    expected_availability: str = "",
    expected_alarm_offsets_minutes: list[int] | None = None,
    expected_alarm_absolute_dates: list[str] | None = None,
    expected_alarm_sound_name: str = "",
    expected_alarm_email_address_sha256: str = "",
    expected_alarm_proximity: str = "",
    expected_alarm_structured_location: dict[str, Any] | None = None,
    expected_event_url_present: bool = False,
    expected_event_url_sha256: str = "",
    expected_location: str = "",
    expected_structured_location: dict[str, Any] | None = None,
    expected_notes: str = "",
) -> dict[str, Any]:
    """Plan a future Calendar event create/update/delete without applying it."""

    return _record(
        "calendar_plan_change",
        plan_calendar_change(
            operation,
            title=title,
            calendar_title=calendar_title,
            calendar_handle=calendar_handle,
            use_default_calendar=use_default_calendar,
            target_calendar_handle=target_calendar_handle,
            start_date=start_date,
            end_date=end_date,
            time_zone=time_zone,
            all_day=all_day,
            availability=availability,
            alarm_offsets_minutes=alarm_offsets_minutes,
            alarm_absolute_dates=alarm_absolute_dates,
            alarm_sound_name=alarm_sound_name,
            alarm_email_address=alarm_email_address,
            alarm_proximity=alarm_proximity,
            alarm_structured_location=alarm_structured_location,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_count=recurrence_count,
            recurrence_end_date=recurrence_end_date,
            recurrence_unbounded=recurrence_unbounded,
            recurrence_weekdays=recurrence_weekdays,
            recurrence_month_days=recurrence_month_days,
            recurrence_month_weekdays=recurrence_month_weekdays,
            recurrence_year_months=recurrence_year_months,
            recurrence_year_month_days=recurrence_year_month_days,
            recurrence_year_month_weekdays=recurrence_year_month_weekdays,
            recurrence_year_days=recurrence_year_days,
            recurrence_year_weeks=recurrence_year_weeks,
            recurrence_set_positions=recurrence_set_positions,
            recurrence_delete_scope=recurrence_delete_scope,
            recurrence_update_scope=recurrence_update_scope,
            clear_recurrence=clear_recurrence,
            event_url=event_url,
            clear_event_url=clear_event_url,
            location=location,
            structured_location=structured_location,
            clear_structured_location=clear_structured_location,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_calendar_title=expected_calendar_title,
            expected_start_date=expected_start_date,
            expected_end_date=expected_end_date,
            expected_time_zone=expected_time_zone,
            expected_all_day=expected_all_day,
            expected_availability=expected_availability,
            expected_alarm_offsets_minutes=expected_alarm_offsets_minutes,
            expected_alarm_absolute_dates=expected_alarm_absolute_dates,
            expected_alarm_sound_name=expected_alarm_sound_name,
            expected_alarm_email_address_sha256=expected_alarm_email_address_sha256,
            expected_alarm_proximity=expected_alarm_proximity,
            expected_alarm_structured_location=expected_alarm_structured_location,
            expected_event_url_present=expected_event_url_present,
            expected_event_url_sha256=expected_event_url_sha256,
            expected_location=expected_location,
            expected_structured_location=expected_structured_location,
            expected_notes=expected_notes,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def calendar_apply_change(
    operation: str,
    approval_token: str,
    title: str = "",
    start_date: str = "",
    end_date: str = "",
    time_zone: str = "",
    all_day: bool = False,
    availability: str = "",
    alarm_offsets_minutes: list[int] | None = None,
    alarm_absolute_dates: list[str] | None = None,
    alarm_sound_name: str = "",
    alarm_email_address: str = "",
    alarm_proximity: str = "",
    alarm_structured_location: dict[str, Any] | None = None,
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str] | None = None,
    recurrence_month_days: list[int] | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | None = None,
    recurrence_year_months: list[int] | None = None,
    recurrence_year_month_days: list[int] | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | None = None,
    recurrence_year_days: list[int] | None = None,
    recurrence_year_weeks: list[int] | None = None,
    recurrence_set_positions: list[int] | None = None,
    recurrence_delete_scope: str = "",
    recurrence_update_scope: str = "",
    clear_recurrence: bool = False,
    event_url: str = "",
    clear_event_url: bool = False,
    calendar_title: str = "",
    calendar_handle: str = "",
    target_calendar_handle: str = "",
    location: str = "",
    structured_location: dict[str, Any] | None = None,
    clear_structured_location: bool = False,
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_calendar_title: str = "",
    expected_start_date: str = "",
    expected_end_date: str = "",
    expected_time_zone: str = "",
    expected_all_day: bool = False,
    expected_availability: str = "",
    expected_alarm_offsets_minutes: list[int] | None = None,
    expected_alarm_absolute_dates: list[str] | None = None,
    expected_alarm_sound_name: str = "",
    expected_alarm_email_address_sha256: str = "",
    expected_alarm_proximity: str = "",
    expected_alarm_structured_location: dict[str, Any] | None = None,
    expected_event_url_present: bool = False,
    expected_event_url_sha256: str = "",
    expected_location: str = "",
    expected_structured_location: dict[str, Any] | None = None,
    expected_notes: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Calendar event create/update/delete and read back metadata."""

    return _record(
        "calendar_apply_change",
        apply_calendar_change(
            operation,
            title=title,
            calendar_title=calendar_title,
            calendar_handle=calendar_handle,
            target_calendar_handle=target_calendar_handle,
            start_date=start_date,
            end_date=end_date,
            time_zone=time_zone,
            all_day=all_day,
            availability=availability,
            alarm_offsets_minutes=alarm_offsets_minutes,
            alarm_absolute_dates=alarm_absolute_dates,
            alarm_sound_name=alarm_sound_name,
            alarm_email_address=alarm_email_address,
            alarm_proximity=alarm_proximity,
            alarm_structured_location=alarm_structured_location,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_count=recurrence_count,
            recurrence_end_date=recurrence_end_date,
            recurrence_unbounded=recurrence_unbounded,
            recurrence_weekdays=recurrence_weekdays,
            recurrence_month_days=recurrence_month_days,
            recurrence_month_weekdays=recurrence_month_weekdays,
            recurrence_year_months=recurrence_year_months,
            recurrence_year_month_days=recurrence_year_month_days,
            recurrence_year_month_weekdays=recurrence_year_month_weekdays,
            recurrence_year_days=recurrence_year_days,
            recurrence_year_weeks=recurrence_year_weeks,
            recurrence_set_positions=recurrence_set_positions,
            recurrence_delete_scope=recurrence_delete_scope,
            recurrence_update_scope=recurrence_update_scope,
            clear_recurrence=clear_recurrence,
            event_url=event_url,
            clear_event_url=clear_event_url,
            location=location,
            structured_location=structured_location,
            clear_structured_location=clear_structured_location,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_calendar_title=expected_calendar_title,
            expected_start_date=expected_start_date,
            expected_end_date=expected_end_date,
            expected_time_zone=expected_time_zone,
            expected_all_day=expected_all_day,
            expected_availability=expected_availability,
            expected_alarm_offsets_minutes=expected_alarm_offsets_minutes,
            expected_alarm_absolute_dates=expected_alarm_absolute_dates,
            expected_alarm_sound_name=expected_alarm_sound_name,
            expected_alarm_email_address_sha256=expected_alarm_email_address_sha256,
            expected_alarm_proximity=expected_alarm_proximity,
            expected_alarm_structured_location=expected_alarm_structured_location,
            expected_event_url_present=expected_event_url_present,
            expected_event_url_sha256=expected_event_url_sha256,
            expected_location=expected_location,
            expected_structured_location=expected_structured_location,
            expected_notes=expected_notes,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def calendar_plan_calendar_change(
    operation: str,
    source_calendar_handle: str = "",
    calendar_handle: str = "",
    calendar_title: str = "",
    new_calendar_title: str = "",
) -> dict[str, Any]:
    """Plan a synthetic LAD-TEST-* Calendar calendar create/rename/delete operation."""

    return _record(
        "calendar_plan_calendar_change",
        plan_calendar_calendar_change(
            operation,
            source_calendar_handle=source_calendar_handle,
            calendar_handle=calendar_handle,
            calendar_title=calendar_title,
            new_calendar_title=new_calendar_title,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def calendar_apply_calendar_change(
    operation: str,
    approval_token: str,
    source_calendar_handle: str = "",
    calendar_handle: str = "",
    calendar_title: str = "",
    new_calendar_title: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved synthetic LAD-TEST-* Calendar calendar operation."""

    return _record(
        "calendar_apply_calendar_change",
        apply_calendar_calendar_change(
            operation,
            source_calendar_handle=source_calendar_handle,
            calendar_handle=calendar_handle,
            calendar_title=calendar_title,
            new_calendar_title=new_calendar_title,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_search(query: str, limit: int = 20, max_scan_contacts: int = 10000) -> dict[str, Any]:
    """Search local Contacts metadata by name or organization, capped and read-only."""

    return _record_tool(
        "contacts_search",
        lambda: search_contacts(
            query,
            limit=limit,
            max_scan_contacts=max_scan_contacts,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_get(
    handle: str,
    max_chars: int = 4000,
    max_scan_contacts: int = 10000,
) -> dict[str, Any]:
    """Get exact local Contact details by opaque handle, capped and read-only."""

    return _record_tool(
        "contacts_get",
        lambda: get_contact(
            handle,
            max_chars=max_chars,
            max_scan_contacts=max_scan_contacts,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_search_groups(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Contacts groups by name, capped and read-only."""

    return _record_tool(
        "contacts_search_groups",
        lambda: search_contact_groups(
            query,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_get_group(handle: str) -> dict[str, Any]:
    """Get exact local Contacts group metadata by opaque group handle, read-only."""

    return _record_tool(
        "contacts_get_group",
        lambda: get_contact_group(handle),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_list_group_members(handle: str, limit: int = 20) -> dict[str, Any]:
    """List capped Contact metadata for one exact Contacts group handle, read-only."""

    return _record_tool(
        "contacts_list_group_members",
        lambda: list_contact_group_members(
            handle,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_search_containers(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Contacts containers by name or type, capped and read-only."""

    return _record_tool(
        "contacts_search_containers",
        lambda: search_contact_containers(
            query,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_get_container(handle: str) -> dict[str, Any]:
    """Get exact local Contacts container metadata by opaque container handle, read-only."""

    return _record_tool(
        "contacts_get_container",
        lambda: get_contact_container(handle),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_list_container_members(handle: str, limit: int = 20) -> dict[str, Any]:
    """List capped Contact metadata for one exact Contacts container handle, read-only."""

    return _record_tool(
        "contacts_list_container_members",
        lambda: list_contact_container_members(
            handle,
            limit=limit,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_count(max_contacts: int = 50000) -> dict[str, Any]:
    """Count local Contacts records without returning contact details."""

    return _record_tool(
        "contacts_count",
        lambda: count_contacts(max_contacts=max_contacts),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_export_archive(
    output_dir: str,
    filename_prefix: str = "contacts",
    max_contacts: int = 50000,
) -> dict[str, Any]:
    """Export a verified local Contacts JSON and vCard archive to a caller-selected directory."""

    return _record_tool(
        "contacts_export_archive",
        lambda: export_contacts_archive(
            output_dir=Path(output_dir),
            filename_prefix=filename_prefix,
            max_contacts=max_contacts,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_plan_change(
    operation: str,
    handle: str = "",
    expected_current_sha256: str = "",
    group_handle: str = "",
    expected_group_sha256: str = "",
    container_handle: str = "",
    expected_container_sha256: str = "",
    group_name: str | None = None,
    contact_type: str = "person",
    given_name: str | None = None,
    family_name: str | None = None,
    organization_name: str | None = None,
    department_name: str | None = None,
    job_title: str | None = None,
    nickname: str | None = None,
    email_addresses: list[dict[str, str]] | None = None,
    phone_numbers: list[dict[str, str]] | None = None,
    url_addresses: list[dict[str, str]] | None = None,
    note_text: str | None = None,
    postal_addresses: list[dict[str, Any]] | None = None,
    birthday: dict[str, Any] | None = None,
    dates: list[dict[str, Any]] | None = None,
    social_profiles: list[dict[str, str]] | None = None,
    instant_message_addresses: list[dict[str, str]] | None = None,
    contact_relations: list[dict[str, str]] | None = None,
    image_path: str | None = None,
    clear_image: bool = False,
    batch_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan Contacts changes; note operations currently fail closed as unavailable."""

    return _record_tool(
        "contacts_plan_change",
        lambda: plan_contact_change(
            operation,
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            group_handle=group_handle,
            expected_group_sha256=expected_group_sha256,
            container_handle=container_handle,
            expected_container_sha256=expected_container_sha256,
            group_name=group_name,
            contact_type=contact_type,
            given_name=given_name,
            family_name=family_name,
            organization_name=organization_name,
            department_name=department_name,
            job_title=job_title,
            nickname=nickname,
            email_addresses=email_addresses,
            phone_numbers=phone_numbers,
            url_addresses=url_addresses,
            note_text=note_text,
            postal_addresses=postal_addresses,
            birthday=birthday,
            dates=dates,
            social_profiles=social_profiles,
            instant_message_addresses=instant_message_addresses,
            contact_relations=contact_relations,
            image_path=image_path,
            clear_image=clear_image,
            batch_items=batch_items,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def contacts_apply_change(
    operation: str,
    approval_token: str,
    handle: str = "",
    expected_current_sha256: str = "",
    group_handle: str = "",
    expected_group_sha256: str = "",
    container_handle: str = "",
    expected_container_sha256: str = "",
    group_name: str | None = None,
    contact_type: str = "person",
    given_name: str | None = None,
    family_name: str | None = None,
    organization_name: str | None = None,
    department_name: str | None = None,
    job_title: str | None = None,
    nickname: str | None = None,
    email_addresses: list[dict[str, str]] | None = None,
    phone_numbers: list[dict[str, str]] | None = None,
    url_addresses: list[dict[str, str]] | None = None,
    note_text: str | None = None,
    postal_addresses: list[dict[str, Any]] | None = None,
    birthday: dict[str, Any] | None = None,
    dates: list[dict[str, Any]] | None = None,
    social_profiles: list[dict[str, str]] | None = None,
    instant_message_addresses: list[dict[str, str]] | None = None,
    contact_relations: list[dict[str, str]] | None = None,
    image_path: str | None = None,
    clear_image: bool = False,
    batch_items: list[dict[str, Any]] | None = None,
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply approved Contacts changes; note operations currently fail closed before mutation."""

    return _record_tool(
        "contacts_apply_change",
        lambda: apply_contact_change(
            operation,
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            group_handle=group_handle,
            expected_group_sha256=expected_group_sha256,
            container_handle=container_handle,
            expected_container_sha256=expected_container_sha256,
            group_name=group_name,
            contact_type=contact_type,
            given_name=given_name,
            family_name=family_name,
            organization_name=organization_name,
            department_name=department_name,
            job_title=job_title,
            nickname=nickname,
            email_addresses=email_addresses,
            phone_numbers=phone_numbers,
            url_addresses=url_addresses,
            note_text=note_text,
            postal_addresses=postal_addresses,
            birthday=birthday,
            dates=dates,
            social_profiles=social_profiles,
            instant_message_addresses=instant_message_addresses,
            contact_relations=contact_relations,
            image_path=image_path,
            clear_image=clear_image,
            batch_items=batch_items,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_search(
    query: str,
    limit: int = 20,
    media_type: str = "all",
    max_scan_assets: int = 5000,
) -> dict[str, Any]:
    """Search local Photos metadata by original filename, capped and read-only."""

    return _record(
        "photos_search",
        search_photos(
            query,
            limit=limit,
            media_type=media_type,
            max_scan_assets=max_scan_assets,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_get_asset(handle: str, max_scan_assets: int = 5000) -> dict[str, Any]:
    """Get exact local Photos asset metadata by opaque handle, capped and read-only."""

    return _record(
        "photos_get_asset",
        get_photo_asset(handle, max_scan_assets=max_scan_assets),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_search_albums(query: str, limit: int = 20, max_scan_albums: int = 5000) -> dict[str, Any]:
    """Search local Photos regular album metadata by title, capped and read-only."""

    return _record(
        "photos_search_albums",
        search_photo_albums(
            query,
            limit=limit,
            max_scan_albums=max_scan_albums,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_get_album(handle: str, max_scan_albums: int = 5000) -> dict[str, Any]:
    """Get exact local Photos regular album metadata by opaque handle, capped and read-only."""

    return _record(
        "photos_get_album",
        get_photo_album(handle, max_scan_albums=max_scan_albums),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_list_album_assets(
    handle: str,
    limit: int = 20,
    max_scan_albums: int = 5000,
    max_scan_assets: int = 5000,
) -> dict[str, Any]:
    """List exact local Photos regular-album asset metadata by opaque album handle."""

    return _record(
        "photos_list_album_assets",
        list_photo_album_assets(
            handle,
            limit=limit,
            max_scan_albums=max_scan_albums,
            max_scan_assets=max_scan_assets,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_export_asset(
    handle: str,
    output_dir: str,
    filename: str = "",
    max_scan_assets: int = 5000,
) -> dict[str, Any]:
    """Export exact local Photos asset bytes by opaque handle to a caller-selected directory."""

    return _record(
        "photos_export_asset",
        export_photo_asset(
            handle,
            output_dir=Path(output_dir).expanduser(),
            filename=filename or None,
            max_scan_assets=max_scan_assets,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def photos_plan_change(
    operation: str,
    source_file: str = "",
    media_type: str = "auto",
    handle: str = "",
    album_handle: str = "",
    album_title: str = "",
    new_album_title: str = "",
    favorite: bool | None = None,
    hidden: bool | None = None,
    expected_favorite: bool | None = None,
    expected_hidden: bool | None = None,
    expected_in_album: bool | None = None,
    max_scan_assets: int = 5000,
    max_scan_albums: int = 5000,
) -> dict[str, Any]:
    """Plan a future Photos import, exact asset update/delete, album membership, or regular album change."""

    return _record(
        "photos_plan_change",
        plan_photo_change(
            operation,
            source_file=source_file,
            media_type=media_type,
            handle=handle,
            album_handle=album_handle,
            album_title=album_title,
            new_album_title=new_album_title,
            favorite=favorite,
            hidden=hidden,
            expected_favorite=expected_favorite,
            expected_hidden=expected_hidden,
            expected_in_album=expected_in_album,
            max_scan_assets=max_scan_assets,
            max_scan_albums=max_scan_albums,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def photos_apply_change(
    operation: str,
    source_file: str = "",
    media_type: str = "auto",
    handle: str = "",
    album_handle: str = "",
    album_title: str = "",
    new_album_title: str = "",
    favorite: bool | None = None,
    hidden: bool | None = None,
    expected_favorite: bool | None = None,
    expected_hidden: bool | None = None,
    expected_in_album: bool | None = None,
    max_scan_assets: int = 5000,
    max_scan_albums: int = 5000,
    approval_token: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Photos import, exact asset update/delete, album membership, or regular album change."""

    return _record(
        "photos_apply_change",
        apply_photo_change(
            operation,
            source_file=source_file,
            media_type=media_type,
            handle=handle,
            album_handle=album_handle,
            album_title=album_title,
            new_album_title=new_album_title,
            favorite=favorite,
            hidden=hidden,
            expected_favorite=expected_favorite,
            expected_hidden=expected_hidden,
            expected_in_album=expected_in_album,
            max_scan_assets=max_scan_assets,
            max_scan_albums=max_scan_albums,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_search(query: str, limit: int = 50) -> dict[str, Any]:
    """Search local Apple Reminders metadata by title only, capped and read-only."""

    return _record("reminders_search", search_reminders_metadata(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_due(days: int = 14, limit: int = 50) -> dict[str, Any]:
    """List local Apple Reminders metadata due in a bounded window."""

    return _record("reminders_due", due_reminders_metadata(days=days, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_eventkit_search(
    query: str,
    limit: int = 20,
    include_completed: bool = False,
) -> dict[str, Any]:
    """Search local Reminders through EventKit by title, capped and read-only."""

    return _record(
        "reminders_eventkit_search",
        search_reminders_eventkit(
            query,
            limit=limit,
            include_completed=include_completed,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_search_lists(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Reminders list metadata by title, capped and read-only. Title search cannot prove a list is absent; call reminders_list_lists to enumerate every list."""

    return _record("reminders_search_lists", search_reminder_lists(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_list_lists(limit: int = 20) -> dict[str, Any]:
    """Enumerate ALL local Reminders lists as capped metadata, read-only. Check is_shared before writing to a list: true means other people see it."""

    return _record("reminders_list_lists", list_reminder_lists(limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_get_list(handle: str) -> dict[str, Any]:
    """Get exact local Reminders list metadata by opaque EventKit list handle."""

    return _record("reminders_get_list", get_reminder_list(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_list_items(
    handle: str,
    limit: int = 20,
    include_completed: bool = False,
) -> dict[str, Any]:
    """List exact local Reminder metadata in one selected list, capped and read-only."""

    return _record(
        "reminders_list_items",
        list_reminder_items(
            handle,
            limit=limit,
            include_completed=include_completed,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_get_content(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local Reminder notes by opaque EventKit handle, capped and read-only."""

    return _record(
        "reminders_get_content",
        get_reminder_content(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_plan_change(
    operation: str,
    title: str = "",
    list_name: str = "",
    due_date: str = "",
    start_date: str = "",
    expected_start_date: str = "",
    notes: str | None = None,
    handle: str = "",
    expected_title: str = "",
    expected_completed: str = "",
    expected_list_name: str = "",
    expected_list_handle: str = "",
    target_list_handle: str = "",
    expected_priority: int | str | None = None,
    expected_notes_sha256: str = "",
    priority: int | str | None = None,
    url: str = "",
    expected_url_present: str = "",
    expected_url_sha256: str = "",
    alarm_absolute_dates: list[str] | None = None,
    alarm_offsets_minutes: list[int] | None = None,
    expected_alarms_count: int | str | None = None,
    expected_alarms_sha256: str = "",
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    clear_recurrence: bool = False,
    expected_recurrence_present: str = "",
    expected_recurrence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan a future Reminder change, including exact URL/display-alarm set/clear, start-date set/clear, and recurrence create/update/clear, without mutating Reminders state. move_to_list cannot move reminders out of a shared list (is_shared=true in list metadata); plan create-on-target plus guarded delete instead."""

    return _record(
        "reminders_plan_change",
        plan_reminder_change(
            operation,
            title=title,
            list_name=list_name,
            due_date=due_date,
            start_date=start_date,
            expected_start_date=expected_start_date,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_completed=expected_completed,
            expected_list_name=expected_list_name,
            expected_list_handle=expected_list_handle,
            target_list_handle=target_list_handle,
            expected_priority=expected_priority,
            expected_notes_sha256=expected_notes_sha256,
            priority=priority,
            url=url,
            expected_url_present=expected_url_present,
            expected_url_sha256=expected_url_sha256,
            alarm_absolute_dates=alarm_absolute_dates,
            alarm_offsets_minutes=alarm_offsets_minutes,
            expected_alarms_count=expected_alarms_count,
            expected_alarms_sha256=expected_alarms_sha256,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_count=recurrence_count,
            recurrence_end_date=recurrence_end_date,
            recurrence_unbounded=recurrence_unbounded,
            recurrence_weekdays=recurrence_weekdays,
            recurrence_month_days=recurrence_month_days,
            recurrence_month_weekdays=recurrence_month_weekdays,
            recurrence_year_months=recurrence_year_months,
            recurrence_year_month_days=recurrence_year_month_days,
            recurrence_year_month_weekdays=recurrence_year_month_weekdays,
            recurrence_year_days=recurrence_year_days,
            recurrence_year_weeks=recurrence_year_weeks,
            recurrence_set_positions=recurrence_set_positions,
            clear_recurrence=clear_recurrence,
            expected_recurrence_present=expected_recurrence_present,
            expected_recurrence=expected_recurrence,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def reminders_apply_change(
    operation: str,
    approval_token: str,
    confirm_apply: bool = False,
    title: str = "",
    list_name: str = "",
    due_date: str = "",
    start_date: str = "",
    expected_start_date: str = "",
    notes: str | None = None,
    handle: str = "",
    expected_title: str = "",
    expected_completed: str = "",
    expected_list_name: str = "",
    expected_list_handle: str = "",
    target_list_handle: str = "",
    expected_priority: int | str | None = None,
    expected_notes_sha256: str = "",
    priority: int | str | None = None,
    url: str = "",
    expected_url_present: str = "",
    expected_url_sha256: str = "",
    alarm_absolute_dates: list[str] | None = None,
    alarm_offsets_minutes: list[int] | None = None,
    expected_alarms_count: int | str | None = None,
    expected_alarms_sha256: str = "",
    recurrence_frequency: str = "",
    recurrence_interval: int | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: str = "",
    recurrence_unbounded: bool = False,
    recurrence_weekdays: list[str | int] | str | None = None,
    recurrence_month_days: list[int] | str | None = None,
    recurrence_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_months: list[int] | str | None = None,
    recurrence_year_month_days: list[int] | str | None = None,
    recurrence_year_month_weekdays: list[dict[str, Any]] | str | None = None,
    recurrence_year_days: list[int] | str | None = None,
    recurrence_year_weeks: list[int] | str | None = None,
    recurrence_set_positions: list[int] | str | None = None,
    clear_recurrence: bool = False,
    expected_recurrence_present: str = "",
    expected_recurrence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply an approved Reminder create/complete/uncomplete/due-date/start-date set/clear/recurrence create/update/clear/title/notes/priority/URL/display-alarm/exact same-source list-move/delete change and read back the result. move_to_list out of a shared list fails with shared_list_move_unsupported; fall back to create-on-target plus guarded delete."""

    return _record(
        "reminders_apply_change",
        apply_reminder_change(
            operation,
            title=title,
            list_name=list_name,
            due_date=due_date,
            start_date=start_date,
            expected_start_date=expected_start_date,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_completed=expected_completed,
            expected_list_name=expected_list_name,
            expected_list_handle=expected_list_handle,
            target_list_handle=target_list_handle,
            expected_priority=expected_priority,
            expected_notes_sha256=expected_notes_sha256,
            priority=priority,
            url=url,
            expected_url_present=expected_url_present,
            expected_url_sha256=expected_url_sha256,
            alarm_absolute_dates=alarm_absolute_dates,
            alarm_offsets_minutes=alarm_offsets_minutes,
            expected_alarms_count=expected_alarms_count,
            expected_alarms_sha256=expected_alarms_sha256,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_count=recurrence_count,
            recurrence_end_date=recurrence_end_date,
            recurrence_unbounded=recurrence_unbounded,
            recurrence_weekdays=recurrence_weekdays,
            recurrence_month_days=recurrence_month_days,
            recurrence_month_weekdays=recurrence_month_weekdays,
            recurrence_year_months=recurrence_year_months,
            recurrence_year_month_days=recurrence_year_month_days,
            recurrence_year_month_weekdays=recurrence_year_month_weekdays,
            recurrence_year_days=recurrence_year_days,
            recurrence_year_weeks=recurrence_year_weeks,
            recurrence_set_positions=recurrence_set_positions,
            clear_recurrence=clear_recurrence,
            expected_recurrence_present=expected_recurrence_present,
            expected_recurrence=expected_recurrence,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_plan_list_change(
    operation: str,
    source_list_handle: str = "",
    list_handle: str = "",
    target_list_handle: str = "",
    list_title: str = "",
    new_list_title: str = "",
) -> dict[str, Any]:
    """Plan an exact Reminders list create/rename/delete/migrate-delete operation."""

    return _record(
        "reminders_plan_list_change",
        plan_reminder_list_change(
            operation,
            source_list_handle=source_list_handle,
            list_handle=list_handle,
            target_list_handle=target_list_handle,
            list_title=list_title,
            new_list_title=new_list_title,
        ),
    )


@mcp.tool(annotations=DESTRUCTIVE_WRITE_ANNOTATIONS)
def reminders_apply_list_change(
    operation: str,
    approval_token: str,
    confirm_apply: bool = False,
    source_list_handle: str = "",
    list_handle: str = "",
    target_list_handle: str = "",
    list_title: str = "",
    new_list_title: str = "",
) -> dict[str, Any]:
    """Apply an approved exact Reminders list operation."""

    return _record(
        "reminders_apply_list_change",
        apply_reminder_list_change(
            operation,
            source_list_handle=source_list_handle,
            list_handle=list_handle,
            target_list_handle=target_list_handle,
            list_title=list_title,
            new_list_title=new_list_title,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


def main() -> None:
    try:
        load_operator_env(local_env_path=OPERATOR_LOCAL_ENV_PATH)
    except OperatorEnvError as exc:
        print(f"local-apple-data operator environment failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    mcp.run()


if __name__ == "__main__":
    main()
