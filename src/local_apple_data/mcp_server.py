from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .adapters.books import get_book, list_book_annotations, search_books
from .adapters.calendar import (
    apply_calendar_change,
    get_calendar_event,
    plan_calendar_change,
    search_calendar_events,
)
from .adapters.contacts import (
    apply_contact_change,
    get_contact,
    plan_contact_change,
    search_contacts,
)
from .adapters.icloud_drive import (
    apply_icloud_drive_change,
    get_icloud_drive_content,
    get_icloud_drive_metadata,
    plan_icloud_drive_change,
    search_icloud_drive_metadata,
)
from .adapters.hide_my_email import get_hide_my_email_alias, search_hide_my_email_aliases
from .adapters.mail import (
    apply_mail_change,
    export_mail_attachment,
    get_mail_content,
    get_mail_metadata,
    list_mail_attachments,
    plan_mail_change,
    search_mail_metadata,
)
from .adapters.messages import (
    apply_messages_change,
    export_message_attachment,
    get_message_chat,
    list_message_attachments,
    plan_messages_change,
    search_message_chats,
)
from .adapters.music import (
    get_music_playlist,
    get_music_track,
    search_music_playlists,
    search_music_tracks,
)
from .adapters.notes import (
    apply_notes_change,
    export_notes_attachment,
    get_notes_content,
    get_notes_metadata,
    list_notes_attachments,
    plan_notes_change,
    search_notes_metadata,
)
from .adapters.photos import (
    apply_photo_change,
    export_photo_asset,
    get_photo_asset,
    plan_photo_change,
    search_photos,
)
from .adapters.podcasts import (
    get_podcast_episode,
    get_podcast_show,
    list_podcast_episodes,
    search_podcasts,
)
from .adapters.reminders import (
    apply_reminder_change,
    due_reminders_metadata,
    get_reminder_content,
    plan_reminder_change,
    search_reminders_eventkit,
    search_reminders_metadata,
)
from .adapters.voice_memos import (
    export_voice_memo_audio,
    get_voice_memo_recording,
    search_voice_memos,
)
from .adapters.safari import get_safari_item, search_safari_items
from .adapters.shortcuts import get_shortcuts_item, search_shortcuts_items
from .adapters.tv import (
    get_tv_item,
    get_tv_playlist,
    search_tv_items,
    search_tv_playlists,
)
from .doctor import build_doctor
from .health import build_health
from .redacted_log import log_result


INSTRUCTIONS = (
    "Use these tools for local Apple data only. Stay metadata-first and "
    "bounded. Do not use Gmail connector paths. Do not request broad dumps. "
    "Mail, Messages, inferred Hide My Email aliases, Voice Memos, Safari bookmarks/Reading List, Shortcuts metadata, Apple Books metadata/annotations, Apple Podcasts show/episode metadata, Apple Music track/playlist metadata, Apple TV item/playlist metadata, Notes, iCloud Drive, Calendar, Contacts, Photos, and Reminder detail/export retrieval are exact-handle only. "
    "Mail, Messages, and Notes attachment export are exact-handle only and never return attachment bytes inline. "
    "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, Photos import apply, and Messages send-text apply, and each requires a matching plan approval token plus explicit confirmation."
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


def _record(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    log_result(f"mcp.{command}", payload)
    return payload


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def apple_data_health() -> dict[str, Any]:
    """Return redacted local readiness, schema checks, and access requirements."""

    return _record("apple_data_health", build_health())


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def apple_data_doctor() -> dict[str, Any]:
    """Return redacted non-mutating diagnostics and remediation guidance."""

    return _record("apple_data_doctor", build_doctor())


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Mail metadata by subject, including metadata-only content availability."""

    return _record("mail_search", search_mail_metadata(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact local Mail metadata by handle. Message bodies are not returned."""

    return _record("mail_get_metadata", get_mail_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_get_content(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local Mail plain-text content by opaque v2 handle, capped and read-only."""

    return _record("mail_get_content", get_mail_content(handle, max_chars=max_chars))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_list_attachments(handle: str, limit: int = 20) -> dict[str, Any]:
    """List exact local Mail attachment metadata by selected message handle, capped and read-only."""

    return _record("mail_list_attachments", list_mail_attachments(handle, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def mail_export_attachment(
    message_handle: str,
    attachment_handle: str,
    output_dir: str,
    filename: str = "",
) -> dict[str, Any]:
    """Export one exact local Mail attachment to a caller-selected directory without inline bytes."""

    return _record(
        "mail_export_attachment",
        export_mail_attachment(
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
) -> dict[str, Any]:
    """Plan a future Mail draft creation without applying it."""

    return _record(
        "mail_plan_change",
        plan_mail_change(
            operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def mail_apply_change(
    operation: str,
    approval_token: str,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str = "",
    body_text: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Mail draft creation and read back local Mail content when available."""

    return _record(
        "mail_apply_change",
        apply_mail_change(
            operation,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
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
    body_text: str,
) -> dict[str, Any]:
    """Plan a future exact-chat Messages send without applying it."""

    return _record(
        "messages_plan_change",
        plan_messages_change(operation, handle=handle, body_text=body_text),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def messages_apply_change(
    operation: str,
    handle: str,
    body_text: str,
    approval_token: str,
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved exact-chat Messages send and verify local read-back."""

    return _record(
        "messages_apply_change",
        apply_messages_change(
            operation,
            handle=handle,
            body_text=body_text,
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
def notes_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search local Apple Notes metadata by title/snippet, capped and read-only."""

    return _record("notes_search", search_notes_metadata(query, limit=limit))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact Apple Notes metadata by handle. Note bodies are not returned."""

    return _record("notes_get_metadata", get_notes_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def notes_get_content(handle: str, max_chars: int = 4000, offset: int = 0) -> dict[str, Any]:
    """Get exact local Notes plain-text content by opaque v2 handle, capped, paged, and read-only."""

    return _record(
        "notes_get_content",
        get_notes_content(handle, max_chars=max_chars, offset=offset),
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
    handle: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    """Preview an approved Notes create-note or append-text change without writing Notes data."""

    return _record(
        "notes_plan_change",
        plan_notes_change(
            operation,
            title=title,
            handle=handle,
            body_text=body_text,
            expected_current_sha256=expected_current_sha256,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def notes_apply_change(
    operation: str,
    title: str = "",
    body_text: str = "",
    approval_token: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Notes create-note or append-text change after approval token and explicit confirmation."""

    return _record(
        "notes_apply_change",
        apply_notes_change(
            operation,
            title=title,
            handle=handle,
            body_text=body_text,
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
def icloud_drive_get_metadata(handle: str) -> dict[str, Any]:
    """Get exact local iCloud Drive metadata by opaque handle. File content is not returned."""

    return _record("icloud_drive_get_metadata", get_icloud_drive_metadata(handle))


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_get_content(handle: str, max_chars: int = 4000) -> dict[str, Any]:
    """Get exact local iCloud Drive text content by opaque handle, capped and read-only."""

    return _record(
        "icloud_drive_get_content",
        get_icloud_drive_content(handle, max_chars=max_chars),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def icloud_drive_plan_change(
    operation: str,
    content_text: str,
    parent_handle: str = "",
    filename: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    """Plan a future iCloud Drive text-file create or append without mutating local files."""

    return _record(
        "icloud_drive_plan_change",
        plan_icloud_drive_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
            content_text=content_text,
            expected_current_sha256=expected_current_sha256,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def icloud_drive_apply_change(
    operation: str,
    content_text: str,
    approval_token: str,
    parent_handle: str = "",
    filename: str = "",
    handle: str = "",
    expected_current_sha256: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved iCloud Drive text-file create or append and read back metadata."""

    return _record(
        "icloud_drive_apply_change",
        apply_icloud_drive_change(
            operation,
            parent_handle=parent_handle,
            handle=handle,
            filename=filename,
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
def calendar_plan_change(
    operation: str,
    title: str,
    calendar_title: str,
    start_date: str,
    end_date: str,
    location: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Plan a future Calendar event creation without applying it."""

    return _record(
        "calendar_plan_change",
        plan_calendar_change(
            operation,
            title=title,
            calendar_title=calendar_title,
            start_date=start_date,
            end_date=end_date,
            location=location,
            notes=notes,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def calendar_apply_change(
    operation: str,
    title: str,
    calendar_title: str,
    start_date: str,
    end_date: str,
    approval_token: str,
    location: str = "",
    notes: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Calendar event creation and read back metadata."""

    return _record(
        "calendar_apply_change",
        apply_calendar_change(
            operation,
            title=title,
            calendar_title=calendar_title,
            start_date=start_date,
            end_date=end_date,
            location=location,
            notes=notes,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_search(query: str, limit: int = 20, max_scan_contacts: int = 10000) -> dict[str, Any]:
    """Search local Contacts metadata by name or organization, capped and read-only."""

    return _record(
        "contacts_search",
        search_contacts(
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

    return _record(
        "contacts_get",
        get_contact(
            handle,
            max_chars=max_chars,
            max_scan_contacts=max_scan_contacts,
        ),
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def contacts_plan_change(
    operation: str,
    contact_type: str = "person",
    given_name: str = "",
    family_name: str = "",
    organization_name: str = "",
    department_name: str = "",
    job_title: str = "",
    nickname: str = "",
    email_addresses: list[dict[str, str]] | None = None,
    phone_numbers: list[dict[str, str]] | None = None,
    url_addresses: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Plan a future Contacts contact creation without applying it."""

    return _record(
        "contacts_plan_change",
        plan_contact_change(
            operation,
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
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def contacts_apply_change(
    operation: str,
    approval_token: str,
    contact_type: str = "person",
    given_name: str = "",
    family_name: str = "",
    organization_name: str = "",
    department_name: str = "",
    job_title: str = "",
    nickname: str = "",
    email_addresses: list[dict[str, str]] | None = None,
    phone_numbers: list[dict[str, str]] | None = None,
    url_addresses: list[dict[str, str]] | None = None,
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Contacts contact creation and read back details."""

    return _record(
        "contacts_apply_change",
        apply_contact_change(
            operation,
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
    source_file: str,
    media_type: str = "auto",
) -> dict[str, Any]:
    """Plan a future Photos image/video import without applying it."""

    return _record(
        "photos_plan_change",
        plan_photo_change(
            operation,
            source_file=source_file,
            media_type=media_type,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def photos_apply_change(
    operation: str,
    source_file: str,
    media_type: str = "auto",
    approval_token: str = "",
    confirm_apply: bool = False,
) -> dict[str, Any]:
    """Apply an approved Photos image/video import and read back metadata."""

    return _record(
        "photos_apply_change",
        apply_photo_change(
            operation,
            source_file=source_file,
            media_type=media_type,
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
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_completed: str = "",
) -> dict[str, Any]:
    """Plan a future Reminder change without reading or mutating Reminders state."""

    return _record(
        "reminders_plan_change",
        plan_reminder_change(
            operation,
            title=title,
            list_name=list_name,
            due_date=due_date,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_completed=expected_completed,
        ),
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def reminders_apply_change(
    operation: str,
    approval_token: str,
    confirm_apply: bool = False,
    title: str = "",
    list_name: str = "",
    due_date: str = "",
    notes: str = "",
    handle: str = "",
    expected_title: str = "",
    expected_completed: str = "",
) -> dict[str, Any]:
    """Apply an approved Reminder create/complete/due-date change and read back the result."""

    return _record(
        "reminders_apply_change",
        apply_reminder_change(
            operation,
            title=title,
            list_name=list_name,
            due_date=due_date,
            notes=notes,
            handle=handle,
            expected_title=expected_title,
            expected_completed=expected_completed,
            approval_token=approval_token,
            confirm_apply=confirm_apply,
        ),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
