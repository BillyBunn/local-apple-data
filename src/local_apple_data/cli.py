from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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


def _mail_attachments_command(args: argparse.Namespace) -> int:
    payload = (
        list_mail_attachments(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
            limit=args.limit,
        )
        if args.db or args.mail_root
        else list_mail_attachments(args.handle, limit=args.limit)
    )
    log_result("mail.attachments", payload)
    _print_json(payload)
    return 0


def _mail_export_attachment_command(args: argparse.Namespace) -> int:
    payload = export_mail_attachment(
        args.message_handle,
        args.handle,
        output_dir=Path(args.output_dir).expanduser(),
        filename=args.filename,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.export_attachment", payload)
    _print_json(payload)
    return 0


def _mail_plan_command(args: argparse.Namespace) -> int:
    payload = plan_mail_change(
        args.operation,
        to=args.to or [],
        cc=args.cc or [],
        bcc=args.bcc or [],
        subject=args.subject,
        body_text=args.body_text or "",
    )
    log_result("mail.plan", payload)
    _print_json(payload)
    return 0


def _mail_apply_command(args: argparse.Namespace) -> int:
    payload = apply_mail_change(
        args.operation,
        to=args.to or [],
        cc=args.cc or [],
        bcc=args.bcc or [],
        subject=args.subject,
        body_text=args.body_text or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.apply", payload)
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


def _messages_attachments_command(args: argparse.Namespace) -> int:
    payload = (
        list_message_attachments(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            messages_root=Path(args.messages_root).expanduser()
            if args.messages_root
            else None,
            limit=args.limit,
        )
        if args.db or args.messages_root
        else list_message_attachments(args.handle, limit=args.limit)
    )
    log_result("messages.attachments", payload)
    _print_json(payload)
    return 0


def _messages_export_attachment_command(args: argparse.Namespace) -> int:
    payload = export_message_attachment(
        args.chat_handle,
        args.handle,
        output_dir=Path(args.output_dir).expanduser(),
        filename=args.filename,
        db_path=Path(args.db).expanduser() if args.db else None,
        messages_root=Path(args.messages_root).expanduser() if args.messages_root else None,
    )
    log_result("messages.export_attachment", payload)
    _print_json(payload)
    return 0


def _messages_plan_command(args: argparse.Namespace) -> int:
    payload = plan_messages_change(
        args.operation,
        handle=args.handle,
        body_text=args.body_text or "",
        db_path=Path(args.db).expanduser() if args.db else None,
    )
    log_result("messages.plan", payload)
    _print_json(payload)
    return 0


def _messages_apply_command(args: argparse.Namespace) -> int:
    payload = apply_messages_change(
        args.operation,
        handle=args.handle,
        body_text=args.body_text or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        db_path=Path(args.db).expanduser() if args.db else None,
    )
    log_result("messages.apply", payload)
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


def _safari_search_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {
        "limit": args.limit,
        "kind": args.kind,
        "max_scan_items": args.max_scan_items,
    }
    if args.bookmarks_path:
        kwargs["bookmarks_path"] = Path(args.bookmarks_path).expanduser()
    payload = search_safari_items(args.query, **kwargs)
    log_result("safari.search", payload)
    _print_json(payload)
    return 0


def _safari_get_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"max_scan_items": args.max_scan_items}
    if args.bookmarks_path:
        kwargs["bookmarks_path"] = Path(args.bookmarks_path).expanduser()
    payload = get_safari_item(args.handle, **kwargs)
    log_result("safari.get", payload)
    _print_json(payload)
    return 0


def _shortcuts_search_command(args: argparse.Namespace) -> int:
    payload = search_shortcuts_items(
        args.query,
        limit=args.limit,
        kind=args.kind,
        max_scan_items=args.max_scan_items,
    )
    log_result("shortcuts.search", payload)
    _print_json(payload)
    return 0


def _shortcuts_get_command(args: argparse.Namespace) -> int:
    payload = get_shortcuts_item(args.handle, max_scan_items=args.max_scan_items)
    log_result("shortcuts.get", payload)
    _print_json(payload)
    return 0


def _books_search_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit}
    if args.library_db:
        kwargs["library_db_path"] = Path(args.library_db).expanduser()
    if args.annotations_db:
        kwargs["annotations_db_path"] = Path(args.annotations_db).expanduser()
    payload = search_books(args.query, **kwargs)
    log_result("books.search", payload)
    _print_json(payload)
    return 0


def _books_get_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {}
    if args.library_db:
        kwargs["library_db_path"] = Path(args.library_db).expanduser()
    if args.annotations_db:
        kwargs["annotations_db_path"] = Path(args.annotations_db).expanduser()
    payload = get_book(args.handle, **kwargs)
    log_result("books.get", payload)
    _print_json(payload)
    return 0


def _books_annotations_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit, "max_chars": args.max_chars}
    if args.library_db:
        kwargs["library_db_path"] = Path(args.library_db).expanduser()
    if args.annotations_db:
        kwargs["annotations_db_path"] = Path(args.annotations_db).expanduser()
    payload = list_book_annotations(args.handle, **kwargs)
    log_result("books.annotations", payload)
    _print_json(payload)
    return 0


def _podcasts_search_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = search_podcasts(args.query, **kwargs)
    log_result("podcasts.search", payload)
    _print_json(payload)
    return 0


def _podcasts_get_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = get_podcast_show(args.handle, **kwargs)
    log_result("podcasts.get", payload)
    _print_json(payload)
    return 0


def _podcasts_episodes_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = list_podcast_episodes(args.handle, **kwargs)
    log_result("podcasts.episodes", payload)
    _print_json(payload)
    return 0


def _podcasts_episode_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"max_chars": args.max_chars}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = get_podcast_episode(args.handle, **kwargs)
    log_result("podcasts.episode", payload)
    _print_json(payload)
    return 0


def _music_search_command(args: argparse.Namespace) -> int:
    payload = search_music_tracks(
        args.query,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("music.search", payload)
    _print_json(payload)
    return 0


def _music_get_command(args: argparse.Namespace) -> int:
    payload = get_music_track(args.handle, max_scan_items=args.max_scan_items)
    log_result("music.get", payload)
    _print_json(payload)
    return 0


def _music_playlists_command(args: argparse.Namespace) -> int:
    payload = search_music_playlists(
        args.query,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("music.playlists", payload)
    _print_json(payload)
    return 0


def _music_playlist_command(args: argparse.Namespace) -> int:
    payload = get_music_playlist(args.handle, max_scan_items=args.max_scan_items)
    log_result("music.playlist", payload)
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


def _notes_attachments_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    if args.notes_container:
        kwargs["notes_container"] = Path(args.notes_container).expanduser()
    payload = list_notes_attachments(args.handle, **kwargs)
    log_result("notes.attachments", payload)
    _print_json(payload)
    return 0


def _notes_export_attachment_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"output_dir": Path(args.output_dir).expanduser()}
    if args.filename:
        kwargs["filename"] = args.filename
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    if args.notes_container:
        kwargs["notes_container"] = Path(args.notes_container).expanduser()
    payload = export_notes_attachment(args.handle, **kwargs)
    log_result("notes.export_attachment", payload)
    _print_json(payload)
    return 0


def _notes_plan_command(args: argparse.Namespace) -> int:
    payload = plan_notes_change(
        args.operation,
        title=args.title or "",
        handle=args.handle or "",
        body_text=args.body_text or "",
        expected_current_sha256=args.expected_current_sha256 or "",
    )
    log_result("notes.plan", payload)
    _print_json(payload)
    return 0


def _notes_apply_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = apply_notes_change(
        args.operation,
        title=args.title or "",
        handle=args.handle or "",
        body_text=args.body_text or "",
        expected_current_sha256=args.expected_current_sha256 or "",
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
        **kwargs,
    )
    log_result("notes.apply", payload)
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


def _icloud_drive_plan_command(args: argparse.Namespace) -> int:
    payload = plan_icloud_drive_change(
        args.operation,
        parent_handle=args.parent_handle or "",
        handle=args.handle or "",
        filename=args.filename or "",
        content_text=args.content_text or "",
        expected_current_sha256=args.expected_current_sha256 or "",
    )
    log_result("icloud_drive.plan", payload)
    _print_json(payload)
    return 0


def _icloud_drive_apply_command(args: argparse.Namespace) -> int:
    payload = (
        apply_icloud_drive_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=args.filename or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            approval_token=args.approval_token or "",
            confirm_apply=args.confirm_apply,
            root=Path(args.root).expanduser(),
        )
        if args.root
        else apply_icloud_drive_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=args.filename or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            approval_token=args.approval_token or "",
            confirm_apply=args.confirm_apply,
        )
    )
    log_result("icloud_drive.apply", payload)
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


def _calendar_plan_command(args: argparse.Namespace) -> int:
    payload = plan_calendar_change(
        args.operation,
        title=args.title or "",
        calendar_title=args.calendar_title or "",
        start_date=args.start_date or "",
        end_date=args.end_date or "",
        location=args.location or "",
        notes=args.notes or "",
    )
    log_result("calendar.plan", payload)
    _print_json(payload)
    return 0


def _calendar_apply_command(args: argparse.Namespace) -> int:
    payload = apply_calendar_change(
        args.operation,
        title=args.title or "",
        calendar_title=args.calendar_title or "",
        start_date=args.start_date or "",
        end_date=args.end_date or "",
        location=args.location or "",
        notes=args.notes or "",
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("calendar.apply", payload)
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


def _contact_labeled_values(values: list[str] | None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw in values or []:
        label, separator, value = raw.partition("=")
        if separator:
            entries.append({"label": label, "value": value})
        else:
            entries.append({"label": "other", "value": raw})
    return entries


def _contacts_plan_command(args: argparse.Namespace) -> int:
    payload = plan_contact_change(
        args.operation,
        contact_type=args.contact_type,
        given_name=args.given_name or "",
        family_name=args.family_name or "",
        organization_name=args.organization_name or "",
        department_name=args.department_name or "",
        job_title=args.job_title or "",
        nickname=args.nickname or "",
        email_addresses=_contact_labeled_values(args.email),
        phone_numbers=_contact_labeled_values(args.phone),
        url_addresses=_contact_labeled_values(args.url),
    )
    log_result("contacts.plan", payload)
    _print_json(payload)
    return 0


def _contacts_apply_command(args: argparse.Namespace) -> int:
    payload = apply_contact_change(
        args.operation,
        contact_type=args.contact_type,
        given_name=args.given_name or "",
        family_name=args.family_name or "",
        organization_name=args.organization_name or "",
        department_name=args.department_name or "",
        job_title=args.job_title or "",
        nickname=args.nickname or "",
        email_addresses=_contact_labeled_values(args.email),
        phone_numbers=_contact_labeled_values(args.phone),
        url_addresses=_contact_labeled_values(args.url),
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("contacts.apply", payload)
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


def _photos_plan_command(args: argparse.Namespace) -> int:
    payload = plan_photo_change(
        args.operation,
        source_file=args.source_file,
        media_type=args.media_type,
    )
    log_result("photos.plan", payload)
    _print_json(payload)
    return 0


def _photos_apply_command(args: argparse.Namespace) -> int:
    payload = apply_photo_change(
        args.operation,
        source_file=args.source_file,
        media_type=args.media_type,
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("photos.apply", payload)
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


def _reminders_apply_command(args: argparse.Namespace) -> int:
    payload = apply_reminder_change(
        args.operation,
        title=args.title or "",
        list_name=args.list_name or "",
        due_date=args.due_date or "",
        notes=args.notes or "",
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_completed=args.expected_completed,
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("reminders.apply", payload)
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

    mail_attachments = mail_subparsers.add_parser(
        "attachments",
        help="List exact local Mail attachment metadata by message handle.",
    )
    mail_attachments.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_attachments.add_argument("--handle", required=True, help="Mail message handle from search output.")
    mail_attachments.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum attachment results, capped at 50.",
    )
    mail_attachments.add_argument("--db", help=argparse.SUPPRESS)
    mail_attachments.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_attachments.set_defaults(func=_mail_attachments_command)

    mail_export_attachment = mail_subparsers.add_parser(
        "export-attachment",
        help="Export one exact local Mail attachment by message and attachment handles.",
    )
    mail_export_attachment.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_export_attachment.add_argument(
        "--message-handle",
        required=True,
        help="Mail message handle from search output.",
    )
    mail_export_attachment.add_argument(
        "--handle",
        required=True,
        help="Mail attachment handle from attachments output.",
    )
    mail_export_attachment.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected attachment should be written.",
    )
    mail_export_attachment.add_argument(
        "--filename",
        default=None,
        help="Optional export filename; sanitized before writing.",
    )
    mail_export_attachment.add_argument("--db", help=argparse.SUPPRESS)
    mail_export_attachment.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_export_attachment.set_defaults(func=_mail_export_attachment_command)

    mail_plan = mail_subparsers.add_parser(
        "plan",
        help="Preview an approved Mail draft creation without writing.",
    )
    mail_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_plan.add_argument(
        "--operation",
        required=True,
        choices=["create-draft", "create_draft"],
        help="Mail operation to preview.",
    )
    mail_plan.add_argument(
        "--to",
        action="append",
        default=[],
        help="To recipient email address. Repeat for multiple recipients.",
    )
    mail_plan.add_argument(
        "--cc",
        action="append",
        default=[],
        help="Cc recipient email address. Repeat for multiple recipients.",
    )
    mail_plan.add_argument(
        "--bcc",
        action="append",
        default=[],
        help="Bcc recipient email address. Repeat for multiple recipients.",
    )
    mail_plan.add_argument("--subject", required=True, help="Draft subject.")
    mail_plan.add_argument(
        "--body-text",
        default="",
        help="Plain-text draft body, capped at 12000 characters.",
    )
    mail_plan.set_defaults(func=_mail_plan_command)

    mail_apply = mail_subparsers.add_parser(
        "apply",
        help="Apply an approved Mail draft creation after plan approval.",
    )
    mail_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_apply.add_argument(
        "--operation",
        required=True,
        choices=["create-draft", "create_draft"],
        help="Mail operation to apply.",
    )
    mail_apply.add_argument(
        "--to",
        action="append",
        default=[],
        help="To recipient email address. Repeat for multiple recipients.",
    )
    mail_apply.add_argument(
        "--cc",
        action="append",
        default=[],
        help="Cc recipient email address. Repeat for multiple recipients.",
    )
    mail_apply.add_argument(
        "--bcc",
        action="append",
        default=[],
        help="Bcc recipient email address. Repeat for multiple recipients.",
    )
    mail_apply.add_argument("--subject", required=True, help="Draft subject.")
    mail_apply.add_argument(
        "--body-text",
        default="",
        help="Plain-text draft body, capped at 12000 characters.",
    )
    mail_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token returned by mail plan.",
    )
    mail_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation before writing Mail data.",
    )
    mail_apply.add_argument("--db", help=argparse.SUPPRESS)
    mail_apply.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_apply.set_defaults(func=_mail_apply_command)

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

    messages_attachments = messages_subparsers.add_parser(
        "attachments",
        help="List exact local Messages attachment metadata by chat handle.",
    )
    messages_attachments.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_attachments.add_argument(
        "--handle",
        required=True,
        help="Messages chat handle from search output.",
    )
    messages_attachments.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum attachment results, capped at 50.",
    )
    messages_attachments.add_argument("--db", help=argparse.SUPPRESS)
    messages_attachments.add_argument("--messages-root", help=argparse.SUPPRESS)
    messages_attachments.set_defaults(func=_messages_attachments_command)

    messages_export_attachment = messages_subparsers.add_parser(
        "export-attachment",
        help="Export one exact local Messages attachment by chat and attachment handles.",
    )
    messages_export_attachment.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_export_attachment.add_argument(
        "--chat-handle",
        required=True,
        help="Messages chat handle from search output.",
    )
    messages_export_attachment.add_argument(
        "--handle",
        required=True,
        help="Messages attachment handle from attachments output.",
    )
    messages_export_attachment.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected attachment should be written.",
    )
    messages_export_attachment.add_argument(
        "--filename",
        default=None,
        help="Optional export filename; sanitized before writing.",
    )
    messages_export_attachment.add_argument("--db", help=argparse.SUPPRESS)
    messages_export_attachment.add_argument("--messages-root", help=argparse.SUPPRESS)
    messages_export_attachment.set_defaults(func=_messages_export_attachment_command)

    messages_plan = messages_subparsers.add_parser(
        "plan",
        help="Plan a future exact-chat Messages send without applying it.",
    )
    messages_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_plan.add_argument(
        "--operation",
        required=True,
        choices=["send-text"],
        help="Messages change to plan.",
    )
    messages_plan.add_argument(
        "--handle",
        required=True,
        help="Opaque messages:chat:v1 handle returned by messages search.",
    )
    messages_plan.add_argument("--body-text", required=True, help="Plaintext message body.")
    messages_plan.add_argument("--db", help=argparse.SUPPRESS)
    messages_plan.set_defaults(func=_messages_plan_command)

    messages_apply = messages_subparsers.add_parser(
        "apply",
        help="Apply an approved exact-chat Messages send.",
    )
    messages_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_apply.add_argument(
        "--operation",
        required=True,
        choices=["send-text"],
        help="Messages change to apply.",
    )
    messages_apply.add_argument(
        "--handle",
        required=True,
        help="Opaque messages:chat:v1 handle returned by messages search.",
    )
    messages_apply.add_argument("--body-text", required=True, help="Plaintext message body.")
    messages_apply.add_argument(
        "--approval-token",
        required=True,
        help="Exact messages-apply:v1 approval token from the matching plan.",
    )
    messages_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation for Messages send apply.",
    )
    messages_apply.add_argument("--db", help=argparse.SUPPRESS)
    messages_apply.set_defaults(func=_messages_apply_command)

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

    safari = subparsers.add_parser(
        "safari",
        help="Safari bookmarks and Reading List metadata commands.",
    )
    safari_subparsers = safari.add_subparsers(dest="safari_command", required=True)

    safari_search = safari_subparsers.add_parser(
        "search",
        help="Search Safari bookmarks and Reading List metadata by title or URL.",
    )
    safari_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    safari_search.add_argument("--query", required=True, help="Bookmark title or URL query text.")
    safari_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    safari_search.add_argument(
        "--kind",
        choices=["all", "bookmark", "reading-list"],
        default="all",
        help="Optional item kind filter.",
    )
    safari_search.add_argument(
        "--max-scan-items",
        type=int,
        default=20000,
        help="Maximum bookmark items to scan.",
    )
    safari_search.add_argument("--bookmarks-path", help=argparse.SUPPRESS)
    safari_search.set_defaults(func=_safari_search_command)

    safari_get = safari_subparsers.add_parser(
        "get",
        help="Get exact Safari bookmark or Reading List detail by handle.",
    )
    safari_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    safari_get.add_argument(
        "--handle",
        required=True,
        help="Safari item handle from search output.",
    )
    safari_get.add_argument(
        "--max-scan-items",
        type=int,
        default=20000,
        help="Maximum bookmark items to scan while resolving the handle.",
    )
    safari_get.add_argument("--bookmarks-path", help=argparse.SUPPRESS)
    safari_get.set_defaults(func=_safari_get_command)

    shortcuts = subparsers.add_parser(
        "shortcuts",
        help="Apple Shortcuts metadata commands.",
    )
    shortcuts_subparsers = shortcuts.add_subparsers(
        dest="shortcuts_command",
        required=True,
    )

    shortcuts_search = shortcuts_subparsers.add_parser(
        "search",
        help="Search Shortcuts shortcut and folder metadata by name.",
    )
    shortcuts_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    shortcuts_search.add_argument("--query", required=True, help="Shortcut or folder name query text.")
    shortcuts_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    shortcuts_search.add_argument(
        "--kind",
        choices=["all", "shortcut", "folder"],
        default="all",
        help="Optional Shortcuts item kind filter.",
    )
    shortcuts_search.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Shortcuts items to scan.",
    )
    shortcuts_search.set_defaults(func=_shortcuts_search_command)

    shortcuts_get = shortcuts_subparsers.add_parser(
        "get",
        help="Get exact Shortcuts metadata by handle.",
    )
    shortcuts_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    shortcuts_get.add_argument(
        "--handle",
        required=True,
        help="Shortcuts item handle from search output.",
    )
    shortcuts_get.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Shortcuts items to scan while resolving the handle.",
    )
    shortcuts_get.set_defaults(func=_shortcuts_get_command)

    books = subparsers.add_parser(
        "books",
        help="Apple Books metadata and annotation commands.",
    )
    books_subparsers = books.add_subparsers(dest="books_command", required=True)

    books_search = books_subparsers.add_parser(
        "search",
        help="Search Apple Books library metadata by title, author, or genre.",
    )
    books_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    books_search.add_argument("--query", required=True, help="Book title, author, or genre query text.")
    books_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    books_search.add_argument("--library-db", help=argparse.SUPPRESS)
    books_search.add_argument("--annotations-db", help=argparse.SUPPRESS)
    books_search.set_defaults(func=_books_search_command)

    books_get = books_subparsers.add_parser(
        "get",
        help="Get exact Apple Books metadata by handle.",
    )
    books_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    books_get.add_argument("--handle", required=True, help="Book handle from search output.")
    books_get.add_argument("--library-db", help=argparse.SUPPRESS)
    books_get.add_argument("--annotations-db", help=argparse.SUPPRESS)
    books_get.set_defaults(func=_books_get_command)

    books_annotations = books_subparsers.add_parser(
        "annotations",
        help="List bounded annotations for one exact selected Apple Books book handle.",
    )
    books_annotations.add_argument("--json", action="store_true", help="Emit JSON output.")
    books_annotations.add_argument("--handle", required=True, help="Book handle from search output.")
    books_annotations.add_argument("--limit", type=int, default=20, help="Maximum annotations, capped at 50.")
    books_annotations.add_argument("--max-chars", type=int, default=4000, help="Maximum annotation text characters, capped at 12000.")
    books_annotations.add_argument("--library-db", help=argparse.SUPPRESS)
    books_annotations.add_argument("--annotations-db", help=argparse.SUPPRESS)
    books_annotations.set_defaults(func=_books_annotations_command)

    podcasts = subparsers.add_parser(
        "podcasts",
        help="Apple Podcasts metadata and selected episode commands.",
    )
    podcasts_subparsers = podcasts.add_subparsers(dest="podcasts_command", required=True)

    podcasts_search = podcasts_subparsers.add_parser(
        "search",
        help="Search Apple Podcasts show metadata by title, author, category, or provider.",
    )
    podcasts_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    podcasts_search.add_argument(
        "--query",
        required=True,
        help="Show title, author, category, or provider query text.",
    )
    podcasts_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    podcasts_search.add_argument("--db", help=argparse.SUPPRESS)
    podcasts_search.set_defaults(func=_podcasts_search_command)

    podcasts_get = podcasts_subparsers.add_parser(
        "get",
        help="Get exact Apple Podcasts show metadata by handle.",
    )
    podcasts_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    podcasts_get.add_argument("--handle", required=True, help="Show handle from search output.")
    podcasts_get.add_argument("--db", help=argparse.SUPPRESS)
    podcasts_get.set_defaults(func=_podcasts_get_command)

    podcasts_episodes = podcasts_subparsers.add_parser(
        "episodes",
        help="List bounded episode metadata for one exact selected Apple Podcasts show handle.",
    )
    podcasts_episodes.add_argument("--json", action="store_true", help="Emit JSON output.")
    podcasts_episodes.add_argument("--handle", required=True, help="Show handle from search output.")
    podcasts_episodes.add_argument("--limit", type=int, default=20, help="Maximum episodes, capped at 50.")
    podcasts_episodes.add_argument("--db", help=argparse.SUPPRESS)
    podcasts_episodes.set_defaults(func=_podcasts_episodes_command)

    podcasts_episode = podcasts_subparsers.add_parser(
        "episode",
        help="Get exact Apple Podcasts episode metadata and bounded description by handle.",
    )
    podcasts_episode.add_argument("--json", action="store_true", help="Emit JSON output.")
    podcasts_episode.add_argument("--handle", required=True, help="Episode handle from episodes output.")
    podcasts_episode.add_argument("--max-chars", type=int, default=4000, help="Maximum description characters, capped at 12000.")
    podcasts_episode.add_argument("--db", help=argparse.SUPPRESS)
    podcasts_episode.set_defaults(func=_podcasts_episode_command)

    music = subparsers.add_parser(
        "music",
        help="Apple Music track and playlist metadata commands.",
    )
    music_subparsers = music.add_subparsers(dest="music_command", required=True)

    music_search = music_subparsers.add_parser(
        "search",
        help="Search Apple Music track metadata by title, artist, album, or genre.",
    )
    music_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    music_search.add_argument(
        "--query",
        required=True,
        help="Track title, artist, album, or genre query text.",
    )
    music_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    music_search.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Music.app items to scan, capped by the adapter.",
    )
    music_search.set_defaults(func=_music_search_command)

    music_get = music_subparsers.add_parser(
        "get",
        help="Get exact Apple Music track metadata by handle.",
    )
    music_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    music_get.add_argument("--handle", required=True, help="Track handle from search output.")
    music_get.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Music.app items to scan, capped by the adapter.",
    )
    music_get.set_defaults(func=_music_get_command)

    music_playlists = music_subparsers.add_parser(
        "playlists",
        help="Search Apple Music playlist metadata by playlist name.",
    )
    music_playlists.add_argument("--json", action="store_true", help="Emit JSON output.")
    music_playlists.add_argument("--query", required=True, help="Playlist name query text.")
    music_playlists.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    music_playlists.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Music.app playlists to scan, capped by the adapter.",
    )
    music_playlists.set_defaults(func=_music_playlists_command)

    music_playlist = music_subparsers.add_parser(
        "playlist",
        help="Get exact Apple Music playlist metadata by handle.",
    )
    music_playlist.add_argument("--json", action="store_true", help="Emit JSON output.")
    music_playlist.add_argument("--handle", required=True, help="Playlist handle from search output.")
    music_playlist.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Music.app playlists to scan, capped by the adapter.",
    )
    music_playlist.set_defaults(func=_music_playlist_command)

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

    notes_attachments = notes_subparsers.add_parser(
        "attachments",
        help="List exact local Notes attachment metadata by note handle.",
    )
    notes_attachments.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_attachments.add_argument("--handle", required=True, help="Notes handle from search output.")
    notes_attachments.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum attachments to return, capped at 50.",
    )
    notes_attachments.add_argument("--db", help=argparse.SUPPRESS)
    notes_attachments.add_argument("--notes-container", help=argparse.SUPPRESS)
    notes_attachments.set_defaults(func=_notes_attachments_command)

    notes_export_attachment = notes_subparsers.add_parser(
        "export-attachment",
        help="Export exact local Notes attachment bytes to an output directory by handle.",
    )
    notes_export_attachment.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_export_attachment.add_argument(
        "--handle",
        required=True,
        help="Notes attachment handle from attachment list output.",
    )
    notes_export_attachment.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected Notes attachment should be copied.",
    )
    notes_export_attachment.add_argument(
        "--filename",
        help="Optional export filename. The adapter sanitizes the final filename.",
    )
    notes_export_attachment.add_argument("--db", help=argparse.SUPPRESS)
    notes_export_attachment.add_argument("--notes-container", help=argparse.SUPPRESS)
    notes_export_attachment.set_defaults(func=_notes_export_attachment_command)

    notes_plan = notes_subparsers.add_parser(
        "plan",
        help="Preview an approved Notes create or append operation without writing.",
    )
    notes_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_plan.add_argument(
        "--operation",
        required=True,
        choices=["create", "append-text", "append_text"],
        help="Notes operation to preview.",
    )
    notes_plan.add_argument("--title", default="", help="New note title for create.")
    notes_plan.add_argument(
        "--handle",
        default="",
        help="Opaque Notes handle from search output for append-text.",
    )
    notes_plan.add_argument(
        "--body-text",
        default="",
        help="Plain-text body for the new note or append, capped at 12000 characters.",
    )
    notes_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 required for append-text.",
    )
    notes_plan.set_defaults(func=_notes_plan_command)

    notes_apply = notes_subparsers.add_parser(
        "apply",
        help="Apply an approved Notes create or append operation after plan approval.",
    )
    notes_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_apply.add_argument(
        "--operation",
        required=True,
        choices=["create", "append-text", "append_text"],
        help="Notes operation to apply.",
    )
    notes_apply.add_argument("--title", default="", help="New note title for create.")
    notes_apply.add_argument(
        "--handle",
        default="",
        help="Opaque Notes handle from search output for append-text.",
    )
    notes_apply.add_argument(
        "--body-text",
        default="",
        help="Plain-text body for the new note or append, capped at 12000 characters.",
    )
    notes_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 required for append-text.",
    )
    notes_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token returned by notes plan.",
    )
    notes_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation before writing Notes data.",
    )
    notes_apply.add_argument("--db", help=argparse.SUPPRESS)
    notes_apply.set_defaults(func=_notes_apply_command)

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

    icloud_drive_plan = icloud_drive_subparsers.add_parser(
        "plan",
        help="Plan a future iCloud Drive text-file change without applying it.",
    )
    icloud_drive_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_plan.add_argument(
        "--operation",
        required=True,
        choices=["create-text", "create_text", "append-text", "append_text"],
        help="Future iCloud Drive operation to plan. No mutation is applied.",
    )
    icloud_drive_plan.add_argument(
        "--parent-handle",
        default="",
        help="Opaque iCloud Drive directory handle from search output for create-text.",
    )
    icloud_drive_plan.add_argument(
        "--handle",
        default="",
        help="Opaque iCloud Drive file handle from search output for append-text.",
    )
    icloud_drive_plan.add_argument(
        "--filename",
        default="",
        help="New text filename to create inside the selected directory.",
    )
    icloud_drive_plan.add_argument(
        "--content-text",
        required=True,
        help="Text content for the new file or append, capped at 12000 characters.",
    )
    icloud_drive_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 required for append-text.",
    )
    icloud_drive_plan.set_defaults(func=_icloud_drive_plan_command)

    icloud_drive_apply = icloud_drive_subparsers.add_parser(
        "apply",
        help="Apply an approved iCloud Drive text-file change and read back metadata.",
    )
    icloud_drive_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_apply.add_argument(
        "--operation",
        required=True,
        choices=["create-text", "create_text", "append-text", "append_text"],
        help="Approved iCloud Drive operation to apply.",
    )
    icloud_drive_apply.add_argument(
        "--parent-handle",
        default="",
        help="Opaque iCloud Drive directory handle from search output for create-text.",
    )
    icloud_drive_apply.add_argument(
        "--handle",
        default="",
        help="Opaque iCloud Drive file handle from search output for append-text.",
    )
    icloud_drive_apply.add_argument(
        "--filename",
        default="",
        help="New text filename to create inside the selected directory.",
    )
    icloud_drive_apply.add_argument(
        "--content-text",
        required=True,
        help="Text content for the new file or append, capped at 12000 characters.",
    )
    icloud_drive_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 required for append-text.",
    )
    icloud_drive_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token bound to the matching plan fingerprint.",
    )
    icloud_drive_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    icloud_drive_apply.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_apply.set_defaults(func=_icloud_drive_apply_command)

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

    calendar_plan = calendar_subparsers.add_parser(
        "plan",
        help="Plan a future Calendar event create without applying it.",
    )
    calendar_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_plan.add_argument(
        "--operation",
        required=True,
        choices=["create"],
        help="Future Calendar operation to plan. No mutation is applied.",
    )
    calendar_plan.add_argument("--title", required=True, help="New event title.")
    calendar_plan.add_argument(
        "--calendar-title",
        required=True,
        help="Exact target calendar title.",
    )
    calendar_plan.add_argument(
        "--start-date",
        required=True,
        help="Event start as ISO 8601 timestamp with timezone.",
    )
    calendar_plan.add_argument(
        "--end-date",
        required=True,
        help="Event end as ISO 8601 timestamp with timezone.",
    )
    calendar_plan.add_argument("--location", default="", help="Optional event location.")
    calendar_plan.add_argument("--notes", default="", help="Optional event notes.")
    calendar_plan.set_defaults(func=_calendar_plan_command)

    calendar_apply = calendar_subparsers.add_parser(
        "apply",
        help="Apply an approved Calendar event create.",
    )
    calendar_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_apply.add_argument(
        "--operation",
        required=True,
        choices=["create"],
        help="Approved Calendar operation to apply.",
    )
    calendar_apply.add_argument("--title", required=True, help="New event title.")
    calendar_apply.add_argument(
        "--calendar-title",
        required=True,
        help="Exact target calendar title.",
    )
    calendar_apply.add_argument(
        "--start-date",
        required=True,
        help="Event start as ISO 8601 timestamp with timezone.",
    )
    calendar_apply.add_argument(
        "--end-date",
        required=True,
        help="Event end as ISO 8601 timestamp with timezone.",
    )
    calendar_apply.add_argument("--location", default="", help="Optional event location.")
    calendar_apply.add_argument("--notes", default="", help="Optional event notes.")
    calendar_apply.add_argument(
        "--approval-token",
        required=True,
        help="calendar-apply:v1 token from the matching plan response.",
    )
    calendar_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    calendar_apply.set_defaults(func=_calendar_apply_command)

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

    contacts_plan = contacts_subparsers.add_parser(
        "plan",
        help="Plan a future Contacts contact create without applying it.",
    )
    contacts_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_plan.add_argument(
        "--operation",
        required=True,
        choices=["create"],
        help="Future Contacts operation to plan. No mutation is applied.",
    )
    contacts_plan.add_argument(
        "--contact-type",
        choices=["person", "organization"],
        default="person",
        help="Contact type to create.",
    )
    contacts_plan.add_argument("--given-name", default="", help="Given name for a person contact.")
    contacts_plan.add_argument("--family-name", default="", help="Family name for a person contact.")
    contacts_plan.add_argument("--organization-name", default="", help="Organization name.")
    contacts_plan.add_argument("--department-name", default="", help="Department name.")
    contacts_plan.add_argument("--job-title", default="", help="Job title.")
    contacts_plan.add_argument("--nickname", default="", help="Nickname.")
    contacts_plan.add_argument(
        "--email",
        action="append",
        default=[],
        help="Optional labeled email as label=value. Repeatable, capped at 5.",
    )
    contacts_plan.add_argument(
        "--phone",
        action="append",
        default=[],
        help="Optional labeled phone number as label=value. Repeatable, capped at 5.",
    )
    contacts_plan.add_argument(
        "--url",
        action="append",
        default=[],
        help="Optional labeled URL as label=value. Repeatable, capped at 5.",
    )
    contacts_plan.set_defaults(func=_contacts_plan_command)

    contacts_apply = contacts_subparsers.add_parser(
        "apply",
        help="Apply an approved Contacts contact create.",
    )
    contacts_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_apply.add_argument(
        "--operation",
        required=True,
        choices=["create"],
        help="Approved Contacts operation to apply.",
    )
    contacts_apply.add_argument(
        "--contact-type",
        choices=["person", "organization"],
        default="person",
        help="Contact type to create.",
    )
    contacts_apply.add_argument("--given-name", default="", help="Given name for a person contact.")
    contacts_apply.add_argument("--family-name", default="", help="Family name for a person contact.")
    contacts_apply.add_argument("--organization-name", default="", help="Organization name.")
    contacts_apply.add_argument("--department-name", default="", help="Department name.")
    contacts_apply.add_argument("--job-title", default="", help="Job title.")
    contacts_apply.add_argument("--nickname", default="", help="Nickname.")
    contacts_apply.add_argument(
        "--email",
        action="append",
        default=[],
        help="Optional labeled email as label=value. Repeatable, capped at 5.",
    )
    contacts_apply.add_argument(
        "--phone",
        action="append",
        default=[],
        help="Optional labeled phone number as label=value. Repeatable, capped at 5.",
    )
    contacts_apply.add_argument(
        "--url",
        action="append",
        default=[],
        help="Optional labeled URL as label=value. Repeatable, capped at 5.",
    )
    contacts_apply.add_argument(
        "--approval-token",
        required=True,
        help="contacts-apply:v1 token from the matching plan response.",
    )
    contacts_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    contacts_apply.set_defaults(func=_contacts_apply_command)

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

    photos_plan = photos_subparsers.add_parser(
        "plan",
        help="Preview an approved Photos import without applying it.",
    )
    photos_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_plan.add_argument(
        "--operation",
        required=True,
        choices=["import"],
        help="Approved Photos plan operation.",
    )
    photos_plan.add_argument(
        "--source-file",
        required=True,
        help="Local image or video file to import. The output does not echo the path.",
    )
    photos_plan.add_argument(
        "--media-type",
        choices=["auto", "image", "video"],
        default="auto",
        help="Optional media type assertion for the source file.",
    )
    photos_plan.set_defaults(func=_photos_plan_command)

    photos_apply = photos_subparsers.add_parser(
        "apply",
        help="Apply an approved Photos import after plan-token confirmation.",
    )
    photos_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_apply.add_argument(
        "--operation",
        required=True,
        choices=["import"],
        help="Approved Photos apply operation.",
    )
    photos_apply.add_argument(
        "--source-file",
        required=True,
        help="Local image or video file to import. The output does not echo the path.",
    )
    photos_apply.add_argument(
        "--media-type",
        choices=["auto", "image", "video"],
        default="auto",
        help="Optional media type assertion for the source file.",
    )
    photos_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token copied from the matching Photos plan output.",
    )
    photos_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    photos_apply.set_defaults(func=_photos_apply_command)

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

    reminders_apply = reminders_subparsers.add_parser(
        "apply",
        help="Apply an approved Reminder change and read back the result.",
    )
    reminders_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_apply.add_argument(
        "--operation",
        required=True,
        choices=["create", "complete", "update-due-date", "update_due_date"],
        help="Approved Reminder operation to apply.",
    )
    reminders_apply.add_argument(
        "--title",
        help="Reminder title for create apply.",
    )
    reminders_apply.add_argument(
        "--list-name",
        help="Target Reminders list name for create apply.",
    )
    reminders_apply.add_argument(
        "--due-date",
        help="YYYY-MM-DD or timezone-aware ISO 8601 due date for create/update apply.",
    )
    reminders_apply.add_argument(
        "--notes",
        help="Optional Reminder notes for create apply, capped at 12000 characters.",
    )
    reminders_apply.add_argument(
        "--handle",
        help="Reminder EventKit handle for complete or update-due-date apply.",
    )
    reminders_apply.add_argument(
        "--expected-title",
        help="Expected current title from a recent read-only result.",
    )
    reminders_apply.add_argument(
        "--expected-completed",
        choices=["true", "false"],
        help="Expected current completion state from a recent read-only result.",
    )
    reminders_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token bound to the matching plan fingerprint.",
    )
    reminders_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    reminders_apply.set_defaults(func=_reminders_apply_command)

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
