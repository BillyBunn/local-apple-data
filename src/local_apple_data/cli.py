from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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
    plan_reminder_change,
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


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _health_command(_args: argparse.Namespace) -> int:
    payload = build_health()
    log_result("health", payload)
    _print_json(payload)
    return 0


def _doctor_command(_args: argparse.Namespace) -> int:
    payload = build_doctor()
    log_result("doctor", payload)
    _print_json(payload)
    return 0


def _mail_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_mail_metadata(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else search_mail_metadata(args.query, limit=args.limit)
    )
    log_result("mail.search", payload)
    _print_json(payload)
    return 0


def _mail_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_mail_metadata(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_mail_metadata(args.handle)
    )
    log_result("mail.get", payload)
    _print_json(payload)
    return 0


def _mail_content_command(args: argparse.Namespace) -> int:
    payload = (
        get_mail_content(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
            max_chars=args.max_chars,
        )
        if args.db or args.mail_root
        else get_mail_content(args.handle, max_chars=args.max_chars)
    )
    log_result("mail.content", payload)
    _print_json(payload)
    return 0


def _messages_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_message_chats(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else search_message_chats(args.query, limit=args.limit)
    )
    log_result("messages.search", payload)
    _print_json(payload)
    return 0


def _messages_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_message_chat(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            max_messages=args.max_messages,
            max_chars=args.max_chars,
        )
        if args.db
        else get_message_chat(
            args.handle,
            max_messages=args.max_messages,
            max_chars=args.max_chars,
        )
    )
    log_result("messages.get", payload)
    _print_json(payload)
    return 0


def _hide_my_email_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_hide_my_email_aliases(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else search_hide_my_email_aliases(args.query, limit=args.limit)
    )
    log_result("hide_my_email.search", payload)
    _print_json(payload)
    return 0


def _hide_my_email_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_hide_my_email_alias(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_hide_my_email_alias(args.handle)
    )
    log_result("hide_my_email.get", payload)
    _print_json(payload)
    return 0


def _voice_memos_search_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    if args.recordings_dir:
        kwargs["recordings_dir"] = Path(args.recordings_dir).expanduser()
    payload = search_voice_memos(args.query, **kwargs)
    log_result("voice_memos.search", payload)
    _print_json(payload)
    return 0


def _voice_memos_get_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"max_chars": args.max_chars}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    if args.recordings_dir:
        kwargs["recordings_dir"] = Path(args.recordings_dir).expanduser()
    payload = get_voice_memo_recording(args.handle, **kwargs)
    log_result("voice_memos.get", payload)
    _print_json(payload)
    return 0


def _voice_memos_export_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"output_dir": Path(args.output_dir).expanduser()}
    if args.filename:
        kwargs["filename"] = args.filename
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    if args.recordings_dir:
        kwargs["recordings_dir"] = Path(args.recordings_dir).expanduser()
    payload = export_voice_memo_audio(args.handle, **kwargs)
    log_result("voice_memos.export", payload)
    _print_json(payload)
    return 0


def _notes_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_notes_metadata(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else search_notes_metadata(args.query, limit=args.limit)
    )
    log_result("notes.search", payload)
    _print_json(payload)
    return 0


def _notes_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_notes_metadata(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_notes_metadata(args.handle)
    )
    log_result("notes.get", payload)
    _print_json(payload)
    return 0


def _notes_content_command(args: argparse.Namespace) -> int:
    payload = (
        get_notes_content(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            max_chars=args.max_chars,
            offset=args.offset,
        )
        if args.db
        else get_notes_content(args.handle, max_chars=args.max_chars, offset=args.offset)
    )
    log_result("notes.content", payload)
    _print_json(payload)
    return 0


def _icloud_drive_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_icloud_drive_metadata(
            args.query,
            root=Path(args.root).expanduser(),
            limit=args.limit,
        )
        if args.root
        else search_icloud_drive_metadata(args.query, limit=args.limit)
    )
    log_result("icloud_drive.search", payload)
    _print_json(payload)
    return 0


def _icloud_drive_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_icloud_drive_metadata(args.handle, root=Path(args.root).expanduser())
        if args.root
        else get_icloud_drive_metadata(args.handle)
    )
    log_result("icloud_drive.get", payload)
    _print_json(payload)
    return 0


def _icloud_drive_content_command(args: argparse.Namespace) -> int:
    payload = (
        get_icloud_drive_content(
            args.handle,
            root=Path(args.root).expanduser(),
            max_chars=args.max_chars,
        )
        if args.root
        else get_icloud_drive_content(args.handle, max_chars=args.max_chars)
    )
    log_result("icloud_drive.content", payload)
    _print_json(payload)
    return 0


def _calendar_search_command(args: argparse.Namespace) -> int:
    payload = search_calendar_events(
        args.query,
        limit=args.limit,
        days_back=args.days_back,
        days_forward=args.days_forward,
    )
    log_result("calendar.search", payload)
    _print_json(payload)
    return 0


def _calendar_get_command(args: argparse.Namespace) -> int:
    payload = get_calendar_event(
        args.handle,
        max_chars=args.max_chars,
        days_back=args.days_back,
        days_forward=args.days_forward,
    )
    log_result("calendar.get", payload)
    _print_json(payload)
    return 0


def _contacts_search_command(args: argparse.Namespace) -> int:
    payload = search_contacts(
        args.query,
        limit=args.limit,
        max_scan_contacts=args.max_scan_contacts,
    )
    log_result("contacts.search", payload)
    _print_json(payload)
    return 0


def _contacts_get_command(args: argparse.Namespace) -> int:
    payload = get_contact(
        args.handle,
        max_chars=args.max_chars,
        max_scan_contacts=args.max_scan_contacts,
    )
    log_result("contacts.get", payload)
    _print_json(payload)
    return 0


def _photos_search_command(args: argparse.Namespace) -> int:
    payload = search_photos(
        args.query,
        limit=args.limit,
        media_type=args.media_type,
        max_scan_assets=args.max_scan_assets,
    )
    log_result("photos.search", payload)
    _print_json(payload)
    return 0


def _photos_get_command(args: argparse.Namespace) -> int:
    payload = get_photo_asset(
        args.handle,
        max_scan_assets=args.max_scan_assets,
    )
    log_result("photos.get", payload)
    _print_json(payload)
    return 0


def _photos_export_command(args: argparse.Namespace) -> int:
    payload = export_photo_asset(
        args.handle,
        output_dir=Path(args.output_dir).expanduser(),
        filename=args.filename,
        max_scan_assets=args.max_scan_assets,
    )
    log_result("photos.export", payload)
    _print_json(payload)
    return 0


def _reminders_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_reminders_metadata(
            args.query,
            store_dir=Path(args.store_dir).expanduser() if args.store_dir else None,
            limit=args.limit,
        )
        if args.store_dir
        else search_reminders_metadata(args.query, limit=args.limit)
    )
    log_result("reminders.search", payload)
    _print_json(payload)
    return 0


def _reminders_due_command(args: argparse.Namespace) -> int:
    payload = (
        due_reminders_metadata(
            store_dir=Path(args.store_dir).expanduser() if args.store_dir else None,
            days=args.days,
            limit=args.limit,
        )
        if args.store_dir
        else due_reminders_metadata(days=args.days, limit=args.limit)
    )
    log_result("reminders.due", payload)
    _print_json(payload)
    return 0


def _reminders_eventkit_search_command(args: argparse.Namespace) -> int:
    payload = search_reminders_eventkit(
        args.query,
        limit=args.limit,
        include_completed=args.include_completed,
    )
    log_result("reminders.eventkit_search", payload)
    _print_json(payload)
    return 0


def _reminders_content_command(args: argparse.Namespace) -> int:
    payload = get_reminder_content(args.handle, max_chars=args.max_chars)
    log_result("reminders.content", payload)
    _print_json(payload)
    return 0


def _reminders_plan_command(args: argparse.Namespace) -> int:
    payload = plan_reminder_change(
        args.operation,
        title=args.title or "",
        list_name=args.list_name or "",
        due_date=args.due_date or "",
        notes=args.notes or "",
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_completed=args.expected_completed,
    )
    log_result("reminders.plan", payload)
    _print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-apple-data",
        description="Private local Apple data CLI for Codex.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser(
        "health",
        help="Report redacted local readiness without inspecting personal content.",
    )
    health.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output. This is currently the only output format.",
    )
    health.set_defaults(func=_health_command)

    doctor = subparsers.add_parser(
        "doctor",
        help="Alias for health until deeper diagnostics are implemented.",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output. This is currently the only output format.",
    )
    doctor.set_defaults(func=_doctor_command)

    mail = subparsers.add_parser("mail", help="Mail metadata commands.")
    mail_subparsers = mail.add_subparsers(dest="mail_command", required=True)

    mail_search = mail_subparsers.add_parser(
        "search",
        help="Search Mail metadata by subject with content availability hints.",
    )
    mail_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_search.add_argument("--query", required=True, help="Subject query text.")
    mail_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_search.set_defaults(func=_mail_search_command)

    mail_get = mail_subparsers.add_parser(
        "get",
        help="Get exact Mail metadata by handle.",
    )
    mail_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_get.add_argument("--handle", required=True, help="Mail handle from search output.")
    mail_get.add_argument(
        "--metadata-only",
        action="store_true",
        help="Accepted for clarity; content retrieval is not implemented.",
    )
    mail_get.add_argument("--db", help=argparse.SUPPRESS)
    mail_get.set_defaults(func=_mail_get_command)

    mail_content = mail_subparsers.add_parser(
        "content",
        help="Get exact local Mail plain-text content by opaque handle.",
    )
    mail_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_content.add_argument("--handle", required=True, help="Mail handle from search output.")
    mail_content.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum content characters to return, capped at 12000.",
    )
    mail_content.add_argument("--db", help=argparse.SUPPRESS)
    mail_content.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_content.set_defaults(func=_mail_content_command)

    messages = subparsers.add_parser("messages", help="Messages chat commands.")
    messages_subparsers = messages.add_subparsers(dest="messages_command", required=True)

    messages_search = messages_subparsers.add_parser(
        "search",
        help="Search Messages chat metadata by display name.",
    )
    messages_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_search.add_argument("--query", required=True, help="Chat display-name query text.")
    messages_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    messages_search.add_argument("--db", help=argparse.SUPPRESS)
    messages_search.set_defaults(func=_messages_search_command)

    messages_get = messages_subparsers.add_parser(
        "get",
        help="Get exact Messages chat transcript by handle.",
    )
    messages_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_get.add_argument(
        "--handle",
        required=True,
        help="Messages chat handle from search output.",
    )
    messages_get.add_argument(
        "--max-messages",
        type=int,
        default=25,
        help="Maximum text messages to return, capped at 100.",
    )
    messages_get.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum transcript characters to return, capped at 12000.",
    )
    messages_get.add_argument("--db", help=argparse.SUPPRESS)
    messages_get.set_defaults(func=_messages_get_command)

    hide_my_email = subparsers.add_parser(
        "hide-my-email",
        help="Inferred Hide My Email alias commands from local Mail metadata.",
    )
    hide_my_email_subparsers = hide_my_email.add_subparsers(
        dest="hide_my_email_command",
        required=True,
    )

    hide_my_email_search = hide_my_email_subparsers.add_parser(
        "search",
        help="Search inferred Hide My Email aliases by specific alias substring.",
    )
    hide_my_email_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    hide_my_email_search.add_argument(
        "--query",
        required=True,
        help="Specific alias substring; domains and generic terms are rejected.",
    )
    hide_my_email_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    hide_my_email_search.add_argument("--db", help=argparse.SUPPRESS)
    hide_my_email_search.set_defaults(func=_hide_my_email_search_command)

    hide_my_email_get = hide_my_email_subparsers.add_parser(
        "get",
        help="Get exact inferred Hide My Email alias detail by handle.",
    )
    hide_my_email_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    hide_my_email_get.add_argument(
        "--handle",
        required=True,
        help="Hide My Email alias handle from search output.",
    )
    hide_my_email_get.add_argument("--db", help=argparse.SUPPRESS)
    hide_my_email_get.set_defaults(func=_hide_my_email_get_command)

    voice_memos = subparsers.add_parser(
        "voice-memos",
        help="Voice Memos local metadata and exact transcript commands.",
    )
    voice_memos_subparsers = voice_memos.add_subparsers(
        dest="voice_memos_command",
        required=True,
    )

    voice_memos_search = voice_memos_subparsers.add_parser(
        "search",
        help="Search Voice Memos metadata by title or filename.",
    )
    voice_memos_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    voice_memos_search.add_argument(
        "--query",
        required=True,
        help="Voice Memo title or filename query text.",
    )
    voice_memos_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    voice_memos_search.add_argument("--db", help=argparse.SUPPRESS)
    voice_memos_search.add_argument("--recordings-dir", help=argparse.SUPPRESS)
    voice_memos_search.set_defaults(func=_voice_memos_search_command)

    voice_memos_get = voice_memos_subparsers.add_parser(
        "get",
        help="Get exact Voice Memo metadata and local transcript by handle.",
    )
    voice_memos_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    voice_memos_get.add_argument(
        "--handle",
        required=True,
        help="Voice Memos recording handle from search output.",
    )
    voice_memos_get.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum transcript characters to return, capped at 12000.",
    )
    voice_memos_get.add_argument("--db", help=argparse.SUPPRESS)
    voice_memos_get.add_argument("--recordings-dir", help=argparse.SUPPRESS)
    voice_memos_get.set_defaults(func=_voice_memos_get_command)

    voice_memos_export = voice_memos_subparsers.add_parser(
        "export",
        help="Export exact Voice Memo audio to an output directory by handle.",
    )
    voice_memos_export.add_argument("--json", action="store_true", help="Emit JSON output.")
    voice_memos_export.add_argument(
        "--handle",
        required=True,
        help="Voice Memos recording handle from search output.",
    )
    voice_memos_export.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected recording should be copied.",
    )
    voice_memos_export.add_argument(
        "--filename",
        help="Optional export filename. The .m4a suffix is enforced.",
    )
    voice_memos_export.add_argument("--db", help=argparse.SUPPRESS)
    voice_memos_export.add_argument("--recordings-dir", help=argparse.SUPPRESS)
    voice_memos_export.set_defaults(func=_voice_memos_export_command)

    notes = subparsers.add_parser("notes", help="Apple Notes metadata commands.")
    notes_subparsers = notes.add_subparsers(dest="notes_command", required=True)

    notes_search = notes_subparsers.add_parser(
        "search",
        help="Search Notes metadata by title/snippet only.",
    )
    notes_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_search.add_argument("--query", required=True, help="Title/snippet query text.")
    notes_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    notes_search.add_argument("--db", help=argparse.SUPPRESS)
    notes_search.set_defaults(func=_notes_search_command)

    notes_get = notes_subparsers.add_parser(
        "get",
        help="Get exact Notes metadata by handle.",
    )
    notes_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_get.add_argument("--handle", required=True, help="Notes handle from search output.")
    notes_get.add_argument(
        "--metadata-only",
        action="store_true",
        help="Accepted for clarity; use the content command for note body retrieval.",
    )
    notes_get.add_argument("--db", help=argparse.SUPPRESS)
    notes_get.set_defaults(func=_notes_get_command)

    notes_content = notes_subparsers.add_parser(
        "content",
        help="Get exact local Notes plain-text content by opaque handle.",
    )
    notes_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_content.add_argument("--handle", required=True, help="Notes handle from search output.")
    notes_content.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum content characters to return, capped at 12000.",
    )
    notes_content.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Zero-based content character offset for long imported notes.",
    )
    notes_content.add_argument("--db", help=argparse.SUPPRESS)
    notes_content.set_defaults(func=_notes_content_command)

    icloud_drive = subparsers.add_parser(
        "icloud-drive",
        help="iCloud Drive local metadata and exact content commands.",
    )
    icloud_drive_subparsers = icloud_drive.add_subparsers(
        dest="icloud_drive_command",
        required=True,
    )

    icloud_drive_search = icloud_drive_subparsers.add_parser(
        "search",
        help="Search local iCloud Drive metadata by filename.",
    )
    icloud_drive_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_search.add_argument("--query", required=True, help="Filename query text.")
    icloud_drive_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    icloud_drive_search.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_search.set_defaults(func=_icloud_drive_search_command)

    icloud_drive_get = icloud_drive_subparsers.add_parser(
        "get",
        help="Get exact iCloud Drive metadata by handle.",
    )
    icloud_drive_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_get.add_argument(
        "--handle",
        required=True,
        help="iCloud Drive handle from search output.",
    )
    icloud_drive_get.add_argument(
        "--metadata-only",
        action="store_true",
        help="Accepted for clarity; use the content command for file text retrieval.",
    )
    icloud_drive_get.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_get.set_defaults(func=_icloud_drive_get_command)

    icloud_drive_content = icloud_drive_subparsers.add_parser(
        "content",
        help="Get exact local iCloud Drive text content by opaque handle.",
    )
    icloud_drive_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_content.add_argument(
        "--handle",
        required=True,
        help="iCloud Drive handle from search output.",
    )
    icloud_drive_content.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum content characters to return, capped at 12000.",
    )
    icloud_drive_content.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_content.set_defaults(func=_icloud_drive_content_command)

    calendar = subparsers.add_parser("calendar", help="Apple Calendar commands.")
    calendar_subparsers = calendar.add_subparsers(dest="calendar_command", required=True)

    calendar_search = calendar_subparsers.add_parser(
        "search",
        help="Search Calendar event metadata by title.",
    )
    calendar_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_search.add_argument("--query", required=True, help="Event title query text.")
    calendar_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    calendar_search.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Past search window in days, capped at 3650.",
    )
    calendar_search.add_argument(
        "--days-forward",
        type=int,
        default=730,
        help="Future search window in days, capped at 3650.",
    )
    calendar_search.set_defaults(func=_calendar_search_command)

    calendar_get = calendar_subparsers.add_parser(
        "get",
        help="Get exact Calendar event details by handle.",
    )
    calendar_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_get.add_argument(
        "--handle",
        required=True,
        help="Calendar event handle from search output.",
    )
    calendar_get.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum notes characters to return, capped at 12000.",
    )
    calendar_get.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Past handle-resolution window in days, capped at 3650.",
    )
    calendar_get.add_argument(
        "--days-forward",
        type=int,
        default=730,
        help="Future handle-resolution window in days, capped at 3650.",
    )
    calendar_get.set_defaults(func=_calendar_get_command)

    contacts = subparsers.add_parser("contacts", help="Apple Contacts commands.")
    contacts_subparsers = contacts.add_subparsers(dest="contacts_command", required=True)

    contacts_search = contacts_subparsers.add_parser(
        "search",
        help="Search Contacts metadata by name or organization.",
    )
    contacts_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_search.add_argument(
        "--query",
        required=True,
        help="Name, nickname, organization, department, or job-title query text.",
    )
    contacts_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    contacts_search.add_argument(
        "--max-scan-contacts",
        type=int,
        default=10000,
        help="Maximum contacts to scan, capped at 10000.",
    )
    contacts_search.set_defaults(func=_contacts_search_command)

    contacts_get = contacts_subparsers.add_parser(
        "get",
        help="Get exact Contact details by handle.",
    )
    contacts_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_get.add_argument(
        "--handle",
        required=True,
        help="Contacts handle from search output.",
    )
    contacts_get.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum free-text field characters to return, capped at 12000.",
    )
    contacts_get.add_argument(
        "--max-scan-contacts",
        type=int,
        default=10000,
        help="Maximum contacts to scan while resolving the handle, capped at 10000.",
    )
    contacts_get.set_defaults(func=_contacts_get_command)

    photos = subparsers.add_parser("photos", help="Apple Photos metadata commands.")
    photos_subparsers = photos.add_subparsers(dest="photos_command", required=True)

    photos_search = photos_subparsers.add_parser(
        "search",
        help="Search Photos metadata by original filename.",
    )
    photos_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_search.add_argument("--query", required=True, help="Original filename query text.")
    photos_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    photos_search.add_argument(
        "--media-type",
        choices=["all", "image", "video", "audio"],
        default="all",
        help="Optional media type filter.",
    )
    photos_search.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum assets to scan, capped at 10000.",
    )
    photos_search.set_defaults(func=_photos_search_command)

    photos_get = photos_subparsers.add_parser(
        "get",
        help="Get exact Photos asset metadata by handle.",
    )
    photos_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_get.add_argument(
        "--handle",
        required=True,
        help="Photos asset handle from search output.",
    )
    photos_get.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum assets to scan while resolving the handle, capped at 10000.",
    )
    photos_get.set_defaults(func=_photos_get_command)

    photos_export = photos_subparsers.add_parser(
        "export",
        help="Export exact Photos asset bytes to an output directory by handle.",
    )
    photos_export.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_export.add_argument(
        "--handle",
        required=True,
        help="Photos asset handle from search output.",
    )
    photos_export.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected Photos resource should be written.",
    )
    photos_export.add_argument(
        "--filename",
        help="Optional export filename. The helper sanitizes the final filename.",
    )
    photos_export.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum assets to scan while resolving the handle, capped at 10000.",
    )
    photos_export.set_defaults(func=_photos_export_command)

    reminders = subparsers.add_parser("reminders", help="Apple Reminders metadata commands.")
    reminders_subparsers = reminders.add_subparsers(
        dest="reminders_command",
        required=True,
    )

    reminders_search = reminders_subparsers.add_parser(
        "search",
        help="Search Reminders metadata by title only.",
    )
    reminders_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_search.add_argument("--query", required=True, help="Title query text.")
    reminders_search.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum results, capped at 50.",
    )
    reminders_search.add_argument("--store-dir", help=argparse.SUPPRESS)
    reminders_search.set_defaults(func=_reminders_search_command)

    reminders_due = reminders_subparsers.add_parser(
        "due",
        help="List due Reminders metadata within a bounded window.",
    )
    reminders_due.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_due.add_argument(
        "--days",
        type=int,
        default=14,
        help="Future due window in days, capped at 31.",
    )
    reminders_due.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum results, capped at 50.",
    )
    reminders_due.add_argument("--store-dir", help=argparse.SUPPRESS)
    reminders_due.set_defaults(func=_reminders_due_command)

    reminders_eventkit_search = reminders_subparsers.add_parser(
        "eventkit-search",
        help="Search Reminders through EventKit by title.",
    )
    reminders_eventkit_search.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    reminders_eventkit_search.add_argument("--query", required=True, help="Title query text.")
    reminders_eventkit_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    reminders_eventkit_search.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed reminders in EventKit search results.",
    )
    reminders_eventkit_search.set_defaults(func=_reminders_eventkit_search_command)

    reminders_content = reminders_subparsers.add_parser(
        "content",
        help="Get exact Reminder notes by opaque EventKit handle.",
    )
    reminders_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_content.add_argument(
        "--handle",
        required=True,
        help="Reminder EventKit handle from eventkit-search output.",
    )
    reminders_content.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum notes characters to return, capped at 12000.",
    )
    reminders_content.set_defaults(func=_reminders_content_command)

    reminders_plan = reminders_subparsers.add_parser(
        "plan",
        help="Plan a future Reminder change without applying it.",
    )
    reminders_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_plan.add_argument(
        "--operation",
        required=True,
        choices=["create", "complete", "update-due-date", "update_due_date"],
        help="Future Reminder operation to plan. No mutation is applied.",
    )
    reminders_plan.add_argument(
        "--title",
        help="Reminder title for create planning.",
    )
    reminders_plan.add_argument(
        "--list-name",
        help="Target Reminders list name for create planning.",
    )
    reminders_plan.add_argument(
        "--due-date",
        help="YYYY-MM-DD or timezone-aware ISO 8601 due date for create/update planning.",
    )
    reminders_plan.add_argument(
        "--notes",
        help="Optional Reminder notes for create planning, capped at 12000 characters.",
    )
    reminders_plan.add_argument(
        "--handle",
        help="Reminder EventKit handle for complete or update-due-date planning.",
    )
    reminders_plan.add_argument(
        "--expected-title",
        help="Expected current title from a recent read-only result.",
    )
    reminders_plan.add_argument(
        "--expected-completed",
        choices=["true", "false"],
        help="Expected current completion state from a recent read-only result.",
    )
    reminders_plan.set_defaults(func=_reminders_plan_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
