from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .adapters.calendar import get_calendar_event, search_calendar_events
from .adapters.contacts import get_contact, search_contacts
from .adapters.icloud_drive import (
    get_icloud_drive_content,
    get_icloud_drive_metadata,
    search_icloud_drive_metadata,
)
from .adapters.hide_my_email import get_hide_my_email_alias, search_hide_my_email_aliases
from .adapters.mail import get_mail_content, get_mail_metadata, search_mail_metadata
from .adapters.messages import get_message_chat, search_message_chats
from .adapters.notes import get_notes_content, get_notes_metadata, search_notes_metadata
from .adapters.photos import export_photo_asset, get_photo_asset, search_photos
from .adapters.reminders import (
    due_reminders_metadata,
    get_reminder_content,
    search_reminders_eventkit,
    search_reminders_metadata,
)
from .adapters.voice_memos import (
    export_voice_memo_audio,
    get_voice_memo_recording,
    search_voice_memos,
)
from .doctor import build_doctor
from .health import build_health
from .redacted_log import log_result


INSTRUCTIONS = (
    "Use these tools for local Apple data only. Stay metadata-first and "
    "read-only. Do not use Gmail connector paths. Do not request broad dumps. "
    "Mail, Messages, inferred Hide My Email aliases, Voice Memos, Notes, iCloud Drive, Calendar, Contacts, Photos, and Reminder detail/export retrieval are exact-handle only. "
    "Mutation is not available in this server."
)

mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
