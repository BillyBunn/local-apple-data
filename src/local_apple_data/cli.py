from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .operator_env import OperatorEnvError, load_operator_env

OPERATOR_LOCAL_ENV_PATH = Path(__file__).resolve().parents[2] / ".env.local"

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
    request_calendar_full_access,
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
    request_contacts_access,
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
    get_mail_unsubscribe_metadata,
    get_mail_sender,
    get_mail_signature,
    get_mail_template,
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
    request_photos_full_access,
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
    request_reminders_full_access,
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


def _exception_class_name(exc: BaseException) -> str:
    return exc.__class__.__name__ or "Exception"


def _mail_search_command(args: argparse.Namespace) -> int:
    payload = (
        search_mail_metadata(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            mailbox_handle=args.mailbox_handle or "",
            limit=args.limit,
        )
        if args.db
        else search_mail_metadata(
            args.query,
            mailbox_handle=args.mailbox_handle or "",
            limit=args.limit,
        )
    )
    log_result("mail.search", payload)
    _print_json(payload)
    return 0


def _mail_body_search_command(args: argparse.Namespace) -> int:
    payload = search_mail_body(
        args.query,
        after=args.after or None,
        before=args.before or None,
        cursor=args.cursor or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        limit=args.limit,
        max_snippet_chars=args.max_snippet_chars,
        max_seconds=args.max_seconds,
    )
    log_result("mail.body_search", payload)
    _print_json(payload)
    return 0


def _mail_attachment_search_command(args: argparse.Namespace) -> int:
    payload = search_mail_attachments(
        args.query,
        after=args.after or None,
        before=args.before or None,
        cursor=args.cursor or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        limit=args.limit,
        include_content=args.include_content,
        include_ocr=args.include_ocr,
        max_snippet_chars=args.max_snippet_chars,
        max_seconds=args.max_seconds,
    )
    log_result("mail.attachment_search", payload)
    _print_json(payload)
    return 0


def _mail_advanced_search_command(args: argparse.Namespace) -> int:
    payload = search_mail_advanced(
        args.query,
        scopes=args.scope or None,
        after=args.after or None,
        before=args.before or None,
        mailbox=args.mailbox or "",
        has_attachments=args.has_attachments,
        cursor=args.cursor or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        limit=args.limit,
        max_snippet_chars=args.max_snippet_chars,
        max_seconds=args.max_seconds,
    )
    log_result("mail.advanced_search", payload)
    _print_json(payload)
    return 0


def _mail_fts_build_command(args: argparse.Namespace) -> int:
    payload = build_mail_fts_index(
        after=args.after or None,
        before=args.before or None,
        cursor=args.cursor or "",
        include_attachments=args.include_attachments,
        include_ocr=args.include_ocr,
        confirm_index=args.confirm_index,
        reset=args.reset,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        index_path=Path(args.index).expanduser() if args.index else None,
        limit=args.limit,
        max_seconds=args.max_seconds,
    )
    log_result("mail.fts_build", payload)
    _print_json(payload)
    return 0


def _mail_fts_search_command(args: argparse.Namespace) -> int:
    payload = search_mail_fts(
        args.query,
        scopes=args.scope or None,
        after=args.after or None,
        before=args.before or None,
        cursor=args.cursor or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        index_path=Path(args.index).expanduser() if args.index else None,
        limit=args.limit,
        max_snippet_chars=args.max_snippet_chars,
    )
    log_result("mail.fts_search", payload)
    _print_json(payload)
    return 0


def _mail_fts_status_command(args: argparse.Namespace) -> int:
    payload = get_mail_fts_status(
        db_path=Path(args.db).expanduser() if args.db else None,
        index_path=Path(args.index).expanduser() if args.index else None,
    )
    log_result("mail.fts_status", payload)
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


def _mail_mailboxes_command(args: argparse.Namespace) -> int:
    payload = (
        search_mail_mailboxes(
            args.query,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else search_mail_mailboxes(args.query, limit=args.limit)
    )
    log_result("mail.mailboxes", payload)
    _print_json(payload)
    return 0


def _mail_mailbox_command(args: argparse.Namespace) -> int:
    payload = (
        get_mail_mailbox(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_mail_mailbox(args.handle)
    )
    log_result("mail.mailbox", payload)
    _print_json(payload)
    return 0


def _mail_mailbox_messages_command(args: argparse.Namespace) -> int:
    payload = list_mail_mailbox_messages(
        args.handle,
        after=args.after or None,
        before=args.before or None,
        db_path=Path(args.db).expanduser() if args.db else None,
        limit=args.limit,
    )
    log_result("mail.mailbox_messages", payload)
    _print_json(payload)
    return 0


def _mail_senders_command(args: argparse.Namespace) -> int:
    payload = search_mail_senders(args.query, limit=args.limit)
    log_result("mail.senders", payload)
    _print_json(payload)
    return 0


def _mail_sender_command(args: argparse.Namespace) -> int:
    payload = get_mail_sender(args.handle)
    log_result("mail.sender", payload)
    _print_json(payload)
    return 0


def _mail_signatures_command(args: argparse.Namespace) -> int:
    payload = search_mail_signatures(args.query, limit=args.limit)
    log_result("mail.signatures", payload)
    _print_json(payload)
    return 0


def _mail_signature_command(args: argparse.Namespace) -> int:
    payload = get_mail_signature(args.handle)
    log_result("mail.signature", payload)
    _print_json(payload)
    return 0


def _mail_template_create_command(args: argparse.Namespace) -> int:
    payload = create_mail_template(
        args.name,
        args.body_text,
        subject=args.subject or "",
    )
    log_result("mail.template_create", payload)
    _print_json(payload)
    return 0


def _mail_templates_command(args: argparse.Namespace) -> int:
    payload = search_mail_templates(args.query or "", limit=args.limit)
    log_result("mail.templates", payload)
    _print_json(payload)
    return 0


def _mail_template_command(args: argparse.Namespace) -> int:
    payload = get_mail_template(args.handle, include_body=args.include_body)
    log_result("mail.template", payload)
    _print_json(payload)
    return 0


def _mail_template_delete_command(args: argparse.Namespace) -> int:
    payload = delete_mail_template(args.handle, confirm_delete=args.confirm_delete)
    log_result("mail.template_delete", payload)
    _print_json(payload)
    return 0


def _mail_content_command(args: argparse.Namespace) -> int:
    payload = (
        get_mail_content(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
            max_chars=args.max_chars,
            offset=args.offset,
        )
        if args.db or args.mail_root
        else get_mail_content(args.handle, max_chars=args.max_chars, offset=args.offset)
    )
    log_result("mail.content", payload)
    _print_json(payload)
    return 0


def _mail_unsubscribe_metadata_command(args: argparse.Namespace) -> int:
    payload = (
        get_mail_unsubscribe_metadata(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
            include_body_links=args.include_body_links,
        )
        if args.db or args.mail_root
        else get_mail_unsubscribe_metadata(
            args.handle,
            include_body_links=args.include_body_links,
        )
    )
    log_result("mail.unsubscribe_metadata", payload)
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
    message_handles = args.message_handle or []
    payload = plan_mail_change(
        args.operation,
        to=args.to or [],
        cc=args.cc or [],
        bcc=args.bcc or [],
        subject=args.subject or "",
        body_text=args.body_text or "",
        message_handle=message_handles[0] if message_handles else "",
        message_handles=message_handles[1:],
        target_mailbox_handle=args.target_mailbox_handle or "",
        sender_handle=args.sender_handle or "",
        signature_handle=args.signature_handle or "",
        template_handle=args.template_handle or "",
        attachment_paths=args.attachment_path or [],
        include_source_attachments=args.include_source_attachments,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.plan", payload)
    _print_json(payload)
    return 0


def _mail_apply_command(args: argparse.Namespace) -> int:
    message_handles = args.message_handle or []
    payload = apply_mail_change(
        args.operation,
        to=args.to or [],
        cc=args.cc or [],
        bcc=args.bcc or [],
        subject=args.subject or "",
        body_text=args.body_text or "",
        message_handle=message_handles[0] if message_handles else "",
        message_handles=message_handles[1:],
        target_mailbox_handle=args.target_mailbox_handle or "",
        sender_handle=args.sender_handle or "",
        signature_handle=args.signature_handle or "",
        template_handle=args.template_handle or "",
        attachment_paths=args.attachment_path or [],
        include_source_attachments=args.include_source_attachments,
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.apply", payload)
    _print_json(payload)
    return 0


def _mail_plan_search_triage_command(args: argparse.Namespace) -> int:
    payload = plan_mail_search_triage(
        args.operation,
        args.query,
        search_source=args.search_source,
        scopes=args.scope or None,
        after=args.after,
        before=args.before,
        cursor=args.cursor or "",
        limit=args.limit,
        target_mailbox_handle=args.target_mailbox_handle or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
        index_path=Path(args.index).expanduser() if args.index else None,
    )
    log_result("mail.plan_search_triage", payload)
    _print_json(payload)
    return 0


def _mail_plan_mailbox_command(args: argparse.Namespace) -> int:
    payload = plan_mail_mailbox_change(
        args.operation,
        sender_handle=args.sender_handle or "",
        mailbox_handle=args.mailbox_handle or "",
        mailbox_name=args.mailbox_name or "",
        new_mailbox_name=args.new_mailbox_name or "",
        db_path=Path(args.db).expanduser() if args.db else None,
    )
    log_result("mail.plan_mailbox", payload)
    _print_json(payload)
    return 0


def _mail_apply_mailbox_command(args: argparse.Namespace) -> int:
    payload = apply_mail_mailbox_change(
        args.operation,
        sender_handle=args.sender_handle or "",
        mailbox_handle=args.mailbox_handle or "",
        mailbox_name=args.mailbox_name or "",
        new_mailbox_name=args.new_mailbox_name or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        db_path=Path(args.db).expanduser() if args.db else None,
    )
    log_result("mail.apply_mailbox", payload)
    _print_json(payload)
    return 0


def _mail_plan_cleanup_command(args: argparse.Namespace) -> int:
    payload = plan_mail_cleanup(
        args.operation,
        message_handle=args.message_handle or "",
        sender_handle=args.sender_handle or "",
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.plan_cleanup", payload)
    _print_json(payload)
    return 0


def _mail_apply_cleanup_command(args: argparse.Namespace) -> int:
    payload = apply_mail_cleanup(
        args.operation,
        message_handle=args.message_handle or "",
        sender_handle=args.sender_handle or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        db_path=Path(args.db).expanduser() if args.db else None,
        mail_root=Path(args.mail_root).expanduser() if args.mail_root else None,
    )
    log_result("mail.apply_cleanup", payload)
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


def _messages_participants_command(args: argparse.Namespace) -> int:
    payload = (
        list_message_participants(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            limit=args.limit,
        )
        if args.db
        else list_message_participants(args.handle, limit=args.limit)
    )
    log_result("messages.participants", payload)
    _print_json(payload)
    return 0


def _messages_participant_command(args: argparse.Namespace) -> int:
    payload = (
        get_message_participant(
            args.chat_handle,
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
        )
        if args.db
        else get_message_participant(args.chat_handle, args.handle)
    )
    log_result("messages.participant", payload)
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
        file_path=args.file_path or "",
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
        file_path=args.file_path or "",
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


def _safari_folders_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit, "max_scan_items": args.max_scan_items}
    if args.bookmarks_path:
        kwargs["bookmarks_path"] = Path(args.bookmarks_path).expanduser()
    payload = search_safari_folders(args.query, **kwargs)
    log_result("safari.folders", payload)
    _print_json(payload)
    return 0


def _safari_folder_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"max_scan_items": args.max_scan_items}
    if args.bookmarks_path:
        kwargs["bookmarks_path"] = Path(args.bookmarks_path).expanduser()
    payload = get_safari_folder(args.handle, **kwargs)
    log_result("safari.folder", payload)
    _print_json(payload)
    return 0


def _safari_folder_items_command(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {"limit": args.limit, "max_scan_items": args.max_scan_items}
    if args.bookmarks_path:
        kwargs["bookmarks_path"] = Path(args.bookmarks_path).expanduser()
    payload = list_safari_folder_items(args.handle, **kwargs)
    log_result("safari.folder_items", payload)
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


def _shortcuts_folder_items_command(args: argparse.Namespace) -> int:
    payload = list_shortcuts_folder_items(
        args.handle,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("shortcuts.folder_items", payload)
    _print_json(payload)
    return 0


def _shortcuts_plan_command(args: argparse.Namespace) -> int:
    payload = plan_shortcuts_run(
        args.operation,
        handle=args.handle,
        input_text=args.input_text or "",
        max_scan_items=args.max_scan_items,
    )
    log_result("shortcuts.plan", payload)
    _print_json(payload)
    return 0


def _shortcuts_apply_command(args: argparse.Namespace) -> int:
    payload = apply_shortcuts_run(
        args.operation,
        handle=args.handle,
        input_text=args.input_text or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
        max_scan_items=args.max_scan_items,
    )
    log_result("shortcuts.apply", payload)
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


def _music_playlist_tracks_command(args: argparse.Namespace) -> int:
    payload = list_music_playlist_tracks(
        args.handle,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("music.playlist_tracks", payload)
    _print_json(payload)
    return 0


def _tv_search_command(args: argparse.Namespace) -> int:
    payload = search_tv_items(
        args.query,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("tv.search", payload)
    _print_json(payload)
    return 0


def _tv_get_command(args: argparse.Namespace) -> int:
    payload = get_tv_item(args.handle, max_scan_items=args.max_scan_items)
    log_result("tv.get", payload)
    _print_json(payload)
    return 0


def _tv_playlists_command(args: argparse.Namespace) -> int:
    payload = search_tv_playlists(
        args.query,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("tv.playlists", payload)
    _print_json(payload)
    return 0


def _tv_playlist_command(args: argparse.Namespace) -> int:
    payload = get_tv_playlist(args.handle, max_scan_items=args.max_scan_items)
    log_result("tv.playlist", payload)
    _print_json(payload)
    return 0


def _tv_playlist_items_command(args: argparse.Namespace) -> int:
    payload = list_tv_playlist_items(
        args.handle,
        limit=args.limit,
        max_scan_items=args.max_scan_items,
    )
    log_result("tv.playlist_items", payload)
    _print_json(payload)
    return 0


def _freeform_boards_command(args: argparse.Namespace) -> int:
    payload = (
        list_freeform_boards(
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else list_freeform_boards(limit=args.limit)
    )
    log_result("freeform.boards", payload)
    _print_json(payload)
    return 0


def _freeform_get_command(args: argparse.Namespace) -> int:
    payload = (
        get_freeform_board(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_freeform_board(args.handle)
    )
    log_result("freeform.get", payload)
    _print_json(payload)
    return 0


def _freeform_folders_command(args: argparse.Namespace) -> int:
    payload = (
        search_freeform_folders(
            args.query,
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else search_freeform_folders(args.query, limit=args.limit)
    )
    log_result("freeform.folders", payload)
    _print_json(payload)
    return 0


def _freeform_folder_command(args: argparse.Namespace) -> int:
    payload = (
        get_freeform_folder(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_freeform_folder(args.handle)
    )
    log_result("freeform.folder", payload)
    _print_json(payload)
    return 0


def _freeform_folder_boards_command(args: argparse.Namespace) -> int:
    payload = (
        list_freeform_folder_boards(
            args.handle,
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else list_freeform_folder_boards(args.handle, limit=args.limit)
    )
    log_result("freeform.folder_boards", payload)
    _print_json(payload)
    return 0


def _freeform_child_folders_command(args: argparse.Namespace) -> int:
    payload = (
        list_freeform_child_folders(
            args.handle,
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else list_freeform_child_folders(args.handle, limit=args.limit)
    )
    log_result("freeform.child_folders", payload)
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


def _notes_folders_command(args: argparse.Namespace) -> int:
    payload = (
        search_notes_folders(
            args.query,
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else search_notes_folders(args.query, limit=args.limit)
    )
    log_result("notes.folders", payload)
    _print_json(payload)
    return 0


def _notes_folder_command(args: argparse.Namespace) -> int:
    payload = (
        get_notes_folder(args.handle, db_path=Path(args.db).expanduser())
        if args.db
        else get_notes_folder(args.handle)
    )
    log_result("notes.folder", payload)
    _print_json(payload)
    return 0


def _notes_folder_items_command(args: argparse.Namespace) -> int:
    payload = (
        list_notes_folder_items(
            args.handle,
            db_path=Path(args.db).expanduser(),
            limit=args.limit,
        )
        if args.db
        else list_notes_folder_items(args.handle, limit=args.limit)
    )
    log_result("notes.folder_items", payload)
    _print_json(payload)
    return 0


def _notes_folder_tree_command(args: argparse.Namespace) -> int:
    payload = (
        list_notes_folder_tree(
            args.handle,
            db_path=Path(args.db).expanduser(),
            depth=args.depth,
            limit=args.limit,
        )
        if args.db
        else list_notes_folder_tree(args.handle, depth=args.depth, limit=args.limit)
    )
    log_result("notes.folder_tree", payload)
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
    content_format = getattr(args, "content_format", "text") or "text"
    payload = (
        get_notes_content(
            args.handle,
            db_path=Path(args.db).expanduser() if args.db else None,
            max_chars=args.max_chars,
            offset=args.offset,
            content_format=content_format,
        )
        if args.db
        else get_notes_content(
            args.handle,
            max_chars=args.max_chars,
            offset=args.offset,
            content_format=content_format,
        )
    )
    log_result("notes.content", payload)
    _print_json(payload)
    return 0


def _notes_export_content_command(args: argparse.Namespace) -> int:
    kwargs = {
        "cursor": args.cursor,
        "limit": args.limit,
        "max_chars_per_note": args.max_chars_per_note,
        "confirm_bulk": args.confirm_bulk,
    }
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = export_notes_folder_content(args.folder_handle, args.modified_after, **kwargs)
    log_result("notes.export-content", payload)
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
    kwargs: dict[str, Any] = {}
    if args.db:
        kwargs["db_path"] = Path(args.db).expanduser()
    payload = plan_notes_change(
        args.operation,
        title=args.title or "",
        handle=args.handle or "",
        folder_handle=args.folder_handle or "",
        target_folder_handle=args.target_folder_handle or "",
        body_text=args.body_text or "",
        body_html=getattr(args, "body_html", "") or "",
        expected_current_sha256=args.expected_current_sha256 or "",
        **kwargs,
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
        folder_handle=args.folder_handle or "",
        target_folder_handle=args.target_folder_handle or "",
        body_text=args.body_text or "",
        body_html=getattr(args, "body_html", "") or "",
        expected_current_sha256=args.expected_current_sha256 or "",
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
        **kwargs,
    )
    log_result("notes.apply", payload)
    _print_json(payload)
    return 0


def _icloud_drive_root_override_error(mode: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
        },
        "mode": mode,
        "result_count": 0,
        "warnings": [
            {
                "code": "unsupported_test_root",
                "message": "iCloud Drive root overrides are limited to synthetic tests.",
            }
        ],
    }
    if mode == "apply":
        payload.update(
            {
                "mutation_applied": False,
                "apply_available": True,
                "preview": None,
                "read_back": None,
            }
        )
    return payload


def _icloud_drive_root_override_allowed(args: argparse.Namespace) -> bool:
    return not getattr(args, "root", "") or os.environ.get("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT") == "1"


def _icloud_drive_search_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("search")
        log_result("icloud_drive.search", payload)
        _print_json(payload)
        return 0
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


def _icloud_drive_root_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("root")
        log_result("icloud_drive.root", payload)
        _print_json(payload)
        return 0
    payload = (
        get_icloud_drive_root_metadata(root=Path(args.root).expanduser())
        if args.root
        else get_icloud_drive_root_metadata()
    )
    log_result("icloud_drive.root", payload)
    _print_json(payload)
    return 0


def _icloud_drive_get_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("get")
        log_result("icloud_drive.get", payload)
        _print_json(payload)
        return 0
    payload = (
        get_icloud_drive_metadata(args.handle, root=Path(args.root).expanduser())
        if args.root
        else get_icloud_drive_metadata(args.handle)
    )
    log_result("icloud_drive.get", payload)
    _print_json(payload)
    return 0


def _icloud_drive_list_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("list")
        log_result("icloud_drive.list", payload)
        _print_json(payload)
        return 0
    payload = (
        list_icloud_drive_folder(
            args.handle,
            root=Path(args.root).expanduser(),
            limit=args.limit,
        )
        if args.root
        else list_icloud_drive_folder(args.handle, limit=args.limit)
    )
    log_result("icloud_drive.list", payload)
    _print_json(payload)
    return 0


def _icloud_drive_tree_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("tree")
        log_result("icloud_drive.tree", payload)
        _print_json(payload)
        return 0
    payload = (
        list_icloud_drive_folder_tree(
            args.handle,
            root=Path(args.root).expanduser(),
            depth=args.depth,
            limit=args.limit,
        )
        if args.root
        else list_icloud_drive_folder_tree(args.handle, depth=args.depth, limit=args.limit)
    )
    log_result("icloud_drive.tree", payload)
    _print_json(payload)
    return 0


def _icloud_drive_content_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("content")
        log_result("icloud_drive.content", payload)
        _print_json(payload)
        return 0
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


def _icloud_drive_export_command(args: argparse.Namespace) -> int:
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("export")
        log_result("icloud_drive.export", payload)
        _print_json(payload)
        return 0
    kwargs: dict[str, Any] = {
        "output_dir": Path(args.output_dir).expanduser(),
        "filename": args.filename or None,
        "max_bytes": args.max_bytes,
    }
    if args.root:
        kwargs["root"] = Path(args.root).expanduser()
    payload = export_icloud_drive_file(args.handle, **kwargs)
    log_result("icloud_drive.export", payload)
    _print_json(payload)
    return 0


def _icloud_drive_plan_command(args: argparse.Namespace) -> int:
    filename, error_payload = _icloud_drive_filename_arg(args)
    if error_payload is not None:
        log_result("icloud_drive.plan", error_payload)
        _print_json(error_payload)
        return 0
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("plan")
        log_result("icloud_drive.plan", payload)
        _print_json(payload)
        return 0
    payload = (
        plan_icloud_drive_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            root=Path(args.root).expanduser(),
        )
        if args.root
        else plan_icloud_drive_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
        )
    )
    log_result("icloud_drive.plan", payload)
    _print_json(payload)
    return 0


def _icloud_drive_apply_command(args: argparse.Namespace) -> int:
    filename, error_payload = _icloud_drive_filename_arg(args)
    if error_payload is not None:
        log_result("icloud_drive.apply", error_payload)
        _print_json(error_payload)
        return 0
    if not _icloud_drive_root_override_allowed(args):
        payload = _icloud_drive_root_override_error("apply")
        log_result("icloud_drive.apply", payload)
        _print_json(payload)
        return 0
    payload = (
        apply_icloud_drive_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
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
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            approval_token=args.approval_token or "",
            confirm_apply=args.confirm_apply,
        )
    )
    log_result("icloud_drive.apply", payload)
    _print_json(payload)
    return 0


def _icloud_drive_filename_arg(args: argparse.Namespace) -> tuple[str, dict[str, Any] | None]:
    filename = args.filename or ""
    folder_name = getattr(args, "folder_name", "") or ""
    operation = str(args.operation).replace("-", "_")
    if not folder_name:
        return filename, None
    if operation not in {"create_folder", "rename_folder", "move_folder", "copy_folder"}:
        return "", {
            "source": "icloud_drive",
            "status": "error",
            "warning": "unexpected_folder_name",
            "message": "--folder-name is only supported for create-folder, rename-folder, move-folder, or copy-folder operations.",
        }
    if filename and filename != folder_name:
        return "", {
            "source": "icloud_drive",
            "status": "error",
            "warning": "conflicting_folder_name",
            "message": "Use either --folder-name or --filename for create-folder, rename-folder, move-folder, or copy-folder, not both.",
        }
    return folder_name, None


def _filesystem_root_override_error(mode: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "source": "filesystem",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
        },
        "mode": mode,
        "result_count": 0,
        "warnings": [
            {
                "code": "unsupported_test_root",
                "message": "Filesystem root overrides are limited to synthetic tests.",
            }
        ],
    }
    if mode == "apply":
        payload.update(
            {
                "mutation_applied": False,
                "apply_available": True,
                "preview": None,
                "read_back": None,
            }
        )
    return payload


def _filesystem_root_override_allowed(args: argparse.Namespace) -> bool:
    return not getattr(args, "root", "") or os.environ.get("LOCAL_APPLE_DATA_ALLOW_TEST_ROOT") == "1"


def _filesystem_search_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("search")
        log_result("filesystem.search", payload)
        _print_json(payload)
        return 0
    payload = (
        search_filesystem_metadata(
            args.query,
            root=Path(args.root).expanduser(),
            limit=args.limit,
        )
        if args.root
        else search_filesystem_metadata(args.query, limit=args.limit)
    )
    log_result("filesystem.search", payload)
    _print_json(payload)
    return 0


def _filesystem_root_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("root")
        log_result("filesystem.root", payload)
        _print_json(payload)
        return 0
    payload = (
        get_filesystem_root_metadata(root=Path(args.root).expanduser())
        if args.root
        else get_filesystem_root_metadata()
    )
    log_result("filesystem.root", payload)
    _print_json(payload)
    return 0


def _filesystem_get_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("get")
        log_result("filesystem.get", payload)
        _print_json(payload)
        return 0
    payload = (
        get_filesystem_metadata(args.handle, root=Path(args.root).expanduser())
        if args.root
        else get_filesystem_metadata(args.handle)
    )
    log_result("filesystem.get", payload)
    _print_json(payload)
    return 0


def _filesystem_list_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("list")
        log_result("filesystem.list", payload)
        _print_json(payload)
        return 0
    payload = (
        list_filesystem_folder(
            args.handle,
            root=Path(args.root).expanduser(),
            limit=args.limit,
        )
        if args.root
        else list_filesystem_folder(args.handle, limit=args.limit)
    )
    log_result("filesystem.list", payload)
    _print_json(payload)
    return 0


def _filesystem_tree_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("tree")
        log_result("filesystem.tree", payload)
        _print_json(payload)
        return 0
    payload = (
        list_filesystem_folder_tree(
            args.handle,
            root=Path(args.root).expanduser(),
            depth=args.depth,
            limit=args.limit,
        )
        if args.root
        else list_filesystem_folder_tree(args.handle, depth=args.depth, limit=args.limit)
    )
    log_result("filesystem.tree", payload)
    _print_json(payload)
    return 0


def _filesystem_content_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("content")
        log_result("filesystem.content", payload)
        _print_json(payload)
        return 0
    payload = (
        get_filesystem_content(
            args.handle,
            root=Path(args.root).expanduser(),
            max_chars=args.max_chars,
        )
        if args.root
        else get_filesystem_content(args.handle, max_chars=args.max_chars)
    )
    log_result("filesystem.content", payload)
    _print_json(payload)
    return 0


def _filesystem_export_command(args: argparse.Namespace) -> int:
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("export")
        log_result("filesystem.export", payload)
        _print_json(payload)
        return 0
    kwargs: dict[str, Any] = {
        "output_dir": Path(args.output_dir).expanduser(),
        "filename": args.filename or None,
        "max_bytes": args.max_bytes,
    }
    if args.root:
        kwargs["root"] = Path(args.root).expanduser()
    payload = export_filesystem_file(args.handle, **kwargs)
    log_result("filesystem.export", payload)
    _print_json(payload)
    return 0


def _filesystem_plan_command(args: argparse.Namespace) -> int:
    filename, error_payload = _filesystem_filename_arg(args)
    if error_payload is not None:
        log_result("filesystem.plan", error_payload)
        _print_json(error_payload)
        return 0
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("plan")
        log_result("filesystem.plan", payload)
        _print_json(payload)
        return 0
    payload = (
        plan_filesystem_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            root=Path(args.root).expanduser(),
        )
        if args.root
        else plan_filesystem_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
        )
    )
    log_result("filesystem.plan", payload)
    _print_json(payload)
    return 0


def _filesystem_apply_command(args: argparse.Namespace) -> int:
    filename, error_payload = _filesystem_filename_arg(args)
    if error_payload is not None:
        log_result("filesystem.apply", error_payload)
        _print_json(error_payload)
        return 0
    if not _filesystem_root_override_allowed(args):
        payload = _filesystem_root_override_error("apply")
        log_result("filesystem.apply", payload)
        _print_json(payload)
        return 0
    payload = (
        apply_filesystem_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            approval_token=args.approval_token or "",
            confirm_apply=args.confirm_apply,
            root=Path(args.root).expanduser(),
        )
        if args.root
        else apply_filesystem_change(
            args.operation,
            parent_handle=args.parent_handle or "",
            handle=args.handle or "",
            filename=filename,
            folder_components=args.folder_components,
            source_file=args.source_file or "",
            content_text=args.content_text or "",
            expected_current_sha256=args.expected_current_sha256 or "",
            approval_token=args.approval_token or "",
            confirm_apply=args.confirm_apply,
        )
    )
    log_result("filesystem.apply", payload)
    _print_json(payload)
    return 0


def _filesystem_filename_arg(args: argparse.Namespace) -> tuple[str, dict[str, Any] | None]:
    filename = args.filename or ""
    folder_name = getattr(args, "folder_name", "") or ""
    operation = str(args.operation).replace("-", "_")
    if not folder_name:
        return filename, None
    if operation not in {"create_folder", "rename_folder", "move_folder", "copy_folder"}:
        return "", {
            "source": "filesystem",
            "status": "error",
            "warning": "unexpected_folder_name",
            "message": "--folder-name is only supported for create-folder, rename-folder, move-folder, or copy-folder operations.",
        }
    if filename and filename != folder_name:
        return "", {
            "source": "filesystem",
            "status": "error",
            "warning": "conflicting_folder_name",
            "message": "Use either --folder-name or --filename for create-folder, rename-folder, move-folder, or copy-folder, not both.",
        }
    return folder_name, None


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


def _calendar_participants_command(args: argparse.Namespace) -> int:
    payload = list_calendar_participants(
        args.handle,
        limit=args.limit,
        days_back=args.days_back,
        days_forward=args.days_forward,
    )
    log_result("calendar.participants", payload)
    _print_json(payload)
    return 0


def _calendar_participant_command(args: argparse.Namespace) -> int:
    payload = get_calendar_participant(
        args.event_handle,
        args.participant_handle,
        days_back=args.days_back,
        days_forward=args.days_forward,
    )
    log_result("calendar.participant", payload)
    _print_json(payload)
    return 0


def _calendar_calendars_command(args: argparse.Namespace) -> int:
    payload = search_calendar_calendars(
        args.query or "",
        limit=args.limit,
        include_default=args.include_default,
    )
    log_result("calendar.calendars", payload)
    _print_json(payload)
    return 0


def _calendar_calendar_command(args: argparse.Namespace) -> int:
    payload = get_calendar_calendar(args.handle)
    log_result("calendar.calendar", payload)
    _print_json(payload)
    return 0


def _calendar_events_command(args: argparse.Namespace) -> int:
    payload = list_calendar_events_for_calendar(
        args.handle,
        start_date=args.start,
        end_date=args.end,
        limit=args.limit,
    )
    log_result("calendar.events", payload)
    _print_json(payload)
    return 0


def _calendar_request_access_command(args: argparse.Namespace) -> int:
    payload = request_calendar_full_access()
    log_result("calendar.request_access", payload)
    _print_json(payload)
    return 0


def _calendar_alarm_offsets_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    offsets: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError("Alarm offsets must be comma-separated integers.")
        try:
            offsets.append(int(token, 10))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Alarm offsets must be comma-separated integers."
            ) from exc
    return offsets


def _calendar_alarm_absolute_dates_arg(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    dates: list[str] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Absolute alarm dates must be comma-separated ISO 8601 timestamps."
            )
        dates.append(token)
    return dates


def _calendar_recurrence_weekdays_arg(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    weekdays: list[str] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence weekdays must be comma-separated weekday names or integers 1 through 7."
            )
        weekdays.append(token)
    return weekdays


def _calendar_recurrence_month_days_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    month_days: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence month days must be comma-separated integers from -31 through -1 or 1 through 31."
            )
        try:
            month_days.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence month days must be comma-separated integers from -31 through -1 or 1 through 31."
            ) from exc
    return month_days


def _calendar_recurrence_month_weekdays_arg(value: str) -> list[dict[str, Any]]:
    stripped = value.strip()
    if not stripped:
        return []
    month_weekdays: list[dict[str, Any]] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence month weekdays must be comma-separated weekday:week_number values."
            )
        pieces = token.split(":", 1)
        if len(pieces) != 2 or not pieces[0].strip() or not pieces[1].strip():
            raise argparse.ArgumentTypeError(
                "Recurrence month weekdays must be comma-separated weekday:week_number values."
            )
        try:
            week_number = int(pieces[1].strip())
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence month weekdays week numbers must be integers from -5 through -1 or 1 through 5."
            ) from exc
        month_weekdays.append({"weekday": pieces[0].strip(), "week_number": week_number})
    return month_weekdays


def _calendar_recurrence_year_month_weekdays_arg(value: str) -> list[dict[str, Any]]:
    stripped = value.strip()
    if not stripped:
        return []
    year_month_weekdays: list[dict[str, Any]] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence year month weekdays must be comma-separated weekday:week_number values."
            )
        pieces = token.split(":", 1)
        if len(pieces) != 2 or not pieces[0].strip() or not pieces[1].strip():
            raise argparse.ArgumentTypeError(
                "Recurrence year month weekdays must be comma-separated weekday:week_number values."
            )
        try:
            week_number = int(pieces[1].strip())
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence year month weekdays week numbers must be integers from -5 through -1 or 1 through 5."
            ) from exc
        year_month_weekdays.append(
            {"weekday": pieces[0].strip(), "week_number": week_number}
        )
    return year_month_weekdays


def _calendar_recurrence_year_months_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    year_months: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence year months must be comma-separated integers from 1 through 12."
            )
        try:
            year_months.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence year months must be comma-separated integers from 1 through 12."
            ) from exc
    return year_months


def _calendar_recurrence_year_month_days_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    year_month_days: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence year month days must be comma-separated integers from -31 through -1 or 1 through 31."
            )
        try:
            year_month_days.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence year month days must be comma-separated integers from -31 through -1 or 1 through 31."
            ) from exc
    return year_month_days


def _calendar_recurrence_year_days_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    year_days: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence year days must be comma-separated integers from -366 through -1 or 1 through 366."
            )
        try:
            year_days.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence year days must be comma-separated integers from -366 through -1 or 1 through 366."
            ) from exc
    return year_days


def _calendar_recurrence_year_weeks_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    year_weeks: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence year weeks must be comma-separated integers from -53 through -1 or 1 through 53."
            )
        try:
            year_weeks.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence year weeks must be comma-separated integers from -53 through -1 or 1 through 53."
            ) from exc
    return year_weeks


def _calendar_recurrence_set_positions_arg(value: str) -> list[int]:
    stripped = value.strip()
    if not stripped:
        return []
    set_positions: list[int] = []
    for part in stripped.split(","):
        token = part.strip()
        if not token:
            raise argparse.ArgumentTypeError(
                "Recurrence set positions must be comma-separated integers from -366 through -1 or 1 through 366."
            )
        try:
            set_positions.append(int(token))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "Recurrence set positions must be comma-separated integers from -366 through -1 or 1 through 366."
            ) from exc
    return set_positions


def _add_reminders_start_date_recurrence_arguments(
    parser: argparse.ArgumentParser,
    *,
    verb: str,
) -> None:
    parser.add_argument(
        "--start-date",
        default="",
        help=f"YYYY-MM-DD or timezone-aware ISO 8601 start date for create-with-start-date, create-with-recurrence, or update-start-date {verb}. Empty on update-start-date clears the start date.",
    )
    parser.add_argument(
        "--expected-start-date",
        default="",
        help=f"Expected current start date from a recent read-only result for update-start-date {verb}. Empty means the reminder currently has no start date.",
    )
    parser.add_argument(
        "--recurrence-frequency",
        help=f"Recurrence frequency daily, weekly, monthly, or yearly for create-with-recurrence or update-recurrence {verb}.",
    )
    parser.add_argument(
        "--recurrence-interval",
        type=int,
        help=f"Recurrence interval from 1 through 4 for create-with-recurrence or update-recurrence {verb}.",
    )
    parser.add_argument(
        "--recurrence-count",
        type=int,
        help=f"Occurrence count, 2 through 52, for create-with-recurrence or update-recurrence {verb}. Mutually exclusive with --recurrence-end-date and --recurrence-unbounded.",
    )
    parser.add_argument(
        "--recurrence-end-date",
        help=f"Finite recurrence end timestamp with timezone for create-with-recurrence or update-recurrence {verb}. Mutually exclusive with --recurrence-count and --recurrence-unbounded.",
    )
    parser.add_argument(
        "--recurrence-unbounded",
        action="store_true",
        help="Request an unbounded recurrence. Mutually exclusive with --recurrence-count and --recurrence-end-date.",
    )
    parser.add_argument(
        "--recurrence-weekdays",
        type=_calendar_recurrence_weekdays_arg,
        help="Optional comma-separated weekdays, e.g. monday,thursday, for weekly, monthly nth-weekday, or yearly week recurrence.",
    )
    parser.add_argument(
        "--recurrence-month-days",
        type=_calendar_recurrence_month_days_arg,
        help="Optional comma-separated day-of-month values for monthly recurrence, e.g. 1,15,-1.",
    )
    parser.add_argument(
        "--recurrence-month-weekdays",
        type=_calendar_recurrence_month_weekdays_arg,
        help="Optional comma-separated weekday:week_number values for monthly recurrence, e.g. monday:2,friday:-1.",
    )
    parser.add_argument(
        "--recurrence-year-months",
        type=_calendar_recurrence_year_months_arg,
        help="Optional comma-separated month values for yearly recurrence, e.g. 1,6,12.",
    )
    parser.add_argument(
        "--recurrence-year-month-days",
        type=_calendar_recurrence_year_month_days_arg,
        help="Optional comma-separated day-of-month values for yearly month recurrence, e.g. 1,15,-1. Requires --recurrence-year-months.",
    )
    parser.add_argument(
        "--recurrence-year-month-weekdays",
        type=_calendar_recurrence_year_month_weekdays_arg,
        help="Optional comma-separated weekday:week_number values for yearly month recurrence, e.g. monday:2,friday:-1. Requires --recurrence-year-months.",
    )
    parser.add_argument(
        "--recurrence-year-days",
        type=_calendar_recurrence_year_days_arg,
        help="Optional comma-separated day-of-year values for yearly recurrence, e.g. 1,100,-1.",
    )
    parser.add_argument(
        "--recurrence-year-weeks",
        type=_calendar_recurrence_year_weeks_arg,
        help="Optional comma-separated week-of-year values for yearly recurrence, e.g. 1,26,-1. Requires --recurrence-weekdays.",
    )
    parser.add_argument(
        "--recurrence-set-positions",
        type=_calendar_recurrence_set_positions_arg,
        help="Optional comma-separated set-position filters, e.g. 1,-1, applied to a recurrence selector.",
    )
    parser.add_argument(
        "--clear-recurrence",
        action="store_true",
        help="Clear the reminder recurrence during update-recurrence. Mutually exclusive with recurrence fields.",
    )
    parser.add_argument(
        "--expected-recurrence-present",
        choices=["true", "false"],
        help=f"Expected current recurrence presence from a recent read-only result for update-recurrence {verb}.",
    )
    parser.add_argument(
        "--expected-recurrence",
        help=f"Expected current recurrence-shape JSON from a recent read-only result for update-recurrence {verb} when expected-recurrence-present is true.",
    )


def _calendar_structured_location_arg(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            "Structured location must be a JSON object."
        ) from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("Structured location must be a JSON object.")
    return parsed


def _calendar_plan_command(args: argparse.Namespace) -> int:
    payload = plan_calendar_change(
        args.operation,
        title=args.title or "",
        calendar_title=args.calendar_title or "",
        calendar_handle=args.calendar_handle or "",
        use_default_calendar=args.use_default_calendar,
        target_calendar_handle=args.target_calendar_handle or "",
        start_date=args.start_date or "",
        end_date=args.end_date or "",
        time_zone=args.time_zone or "",
        all_day=args.all_day,
        availability=args.availability or "",
        alarm_offsets_minutes=args.alarm_offsets_minutes,
        alarm_absolute_dates=args.alarm_absolute_dates,
        alarm_sound_name=args.alarm_sound_name or "",
        alarm_email_address=args.alarm_email_address or "",
        alarm_proximity=args.alarm_proximity or "",
        alarm_structured_location=args.alarm_structured_location,
        recurrence_frequency=args.recurrence_frequency or "",
        recurrence_interval=args.recurrence_interval,
        recurrence_count=args.recurrence_count,
        recurrence_end_date=args.recurrence_end_date or "",
        recurrence_unbounded=args.recurrence_unbounded,
        recurrence_weekdays=args.recurrence_weekdays,
        recurrence_month_days=args.recurrence_month_days,
        recurrence_month_weekdays=args.recurrence_month_weekdays,
        recurrence_year_months=args.recurrence_year_months,
        recurrence_year_month_days=args.recurrence_year_month_days,
        recurrence_year_month_weekdays=args.recurrence_year_month_weekdays,
        recurrence_year_days=args.recurrence_year_days,
        recurrence_year_weeks=args.recurrence_year_weeks,
        recurrence_set_positions=args.recurrence_set_positions,
        recurrence_delete_scope=args.recurrence_delete_scope or "",
        recurrence_update_scope=args.recurrence_update_scope or "",
        clear_recurrence=args.clear_recurrence,
        event_url=args.event_url or "",
        clear_event_url=args.clear_event_url,
        location=args.location or "",
        structured_location=args.structured_location,
        clear_structured_location=args.clear_structured_location,
        notes=args.notes or "",
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_calendar_title=args.expected_calendar_title or "",
        expected_start_date=args.expected_start_date or "",
        expected_end_date=args.expected_end_date or "",
        expected_time_zone=args.expected_time_zone or "",
        expected_all_day=args.expected_all_day,
        expected_availability=args.expected_availability or "",
        expected_alarm_offsets_minutes=args.expected_alarm_offsets_minutes,
        expected_alarm_absolute_dates=args.expected_alarm_absolute_dates,
        expected_alarm_sound_name=args.expected_alarm_sound_name or "",
        expected_alarm_email_address_sha256=args.expected_alarm_email_address_sha256 or "",
        expected_alarm_proximity=args.expected_alarm_proximity or "",
        expected_alarm_structured_location=args.expected_alarm_structured_location,
        expected_event_url_present=args.expected_event_url_present,
        expected_event_url_sha256=args.expected_event_url_sha256 or "",
        expected_location=args.expected_location or "",
        expected_structured_location=args.expected_structured_location,
        expected_notes=args.expected_notes or "",
    )
    log_result("calendar.plan", payload)
    _print_json(payload)
    return 0


def _calendar_apply_command(args: argparse.Namespace) -> int:
    payload = apply_calendar_change(
        args.operation,
        title=args.title or "",
        calendar_title=args.calendar_title or "",
        calendar_handle=args.calendar_handle or "",
        target_calendar_handle=args.target_calendar_handle or "",
        start_date=args.start_date or "",
        end_date=args.end_date or "",
        time_zone=args.time_zone or "",
        all_day=args.all_day,
        availability=args.availability or "",
        alarm_offsets_minutes=args.alarm_offsets_minutes,
        alarm_absolute_dates=args.alarm_absolute_dates,
        alarm_sound_name=args.alarm_sound_name or "",
        alarm_email_address=args.alarm_email_address or "",
        alarm_proximity=args.alarm_proximity or "",
        alarm_structured_location=args.alarm_structured_location,
        recurrence_frequency=args.recurrence_frequency or "",
        recurrence_interval=args.recurrence_interval,
        recurrence_count=args.recurrence_count,
        recurrence_end_date=args.recurrence_end_date or "",
        recurrence_unbounded=args.recurrence_unbounded,
        recurrence_weekdays=args.recurrence_weekdays,
        recurrence_month_days=args.recurrence_month_days,
        recurrence_month_weekdays=args.recurrence_month_weekdays,
        recurrence_year_months=args.recurrence_year_months,
        recurrence_year_month_days=args.recurrence_year_month_days,
        recurrence_year_month_weekdays=args.recurrence_year_month_weekdays,
        recurrence_year_days=args.recurrence_year_days,
        recurrence_year_weeks=args.recurrence_year_weeks,
        recurrence_set_positions=args.recurrence_set_positions,
        recurrence_delete_scope=args.recurrence_delete_scope or "",
        recurrence_update_scope=args.recurrence_update_scope or "",
        clear_recurrence=args.clear_recurrence,
        event_url=args.event_url or "",
        clear_event_url=args.clear_event_url,
        location=args.location or "",
        structured_location=args.structured_location,
        clear_structured_location=args.clear_structured_location,
        notes=args.notes or "",
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_calendar_title=args.expected_calendar_title or "",
        expected_start_date=args.expected_start_date or "",
        expected_end_date=args.expected_end_date or "",
        expected_time_zone=args.expected_time_zone or "",
        expected_all_day=args.expected_all_day,
        expected_availability=args.expected_availability or "",
        expected_alarm_offsets_minutes=args.expected_alarm_offsets_minutes,
        expected_alarm_absolute_dates=args.expected_alarm_absolute_dates,
        expected_alarm_sound_name=args.expected_alarm_sound_name or "",
        expected_alarm_email_address_sha256=args.expected_alarm_email_address_sha256 or "",
        expected_alarm_proximity=args.expected_alarm_proximity or "",
        expected_alarm_structured_location=args.expected_alarm_structured_location,
        expected_event_url_present=args.expected_event_url_present,
        expected_event_url_sha256=args.expected_event_url_sha256 or "",
        expected_location=args.expected_location or "",
        expected_structured_location=args.expected_structured_location,
        expected_notes=args.expected_notes or "",
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("calendar.apply", payload)
    _print_json(payload)
    return 0


def _calendar_plan_calendar_command(args: argparse.Namespace) -> int:
    payload = plan_calendar_calendar_change(
        args.operation,
        source_calendar_handle=args.source_calendar_handle or "",
        calendar_handle=args.calendar_handle or "",
        calendar_title=args.calendar_title or "",
        new_calendar_title=args.new_calendar_title or "",
    )
    log_result("calendar.plan_calendar", payload)
    _print_json(payload)
    return 0


def _calendar_apply_calendar_command(args: argparse.Namespace) -> int:
    payload = apply_calendar_calendar_change(
        args.operation,
        source_calendar_handle=args.source_calendar_handle or "",
        calendar_handle=args.calendar_handle or "",
        calendar_title=args.calendar_title or "",
        new_calendar_title=args.new_calendar_title or "",
        approval_token=args.approval_token,
        confirm_apply=args.confirm_apply,
    )
    log_result("calendar.apply_calendar", payload)
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


def _contacts_request_access_command(args: argparse.Namespace) -> int:
    payload = request_contacts_access()
    log_result("contacts.request_access", payload)
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


def _contacts_groups_command(args: argparse.Namespace) -> int:
    payload = search_contact_groups(
        args.query,
        limit=args.limit,
    )
    log_result("contacts.groups", payload)
    _print_json(payload)
    return 0


def _contacts_group_command(args: argparse.Namespace) -> int:
    payload = get_contact_group(args.handle)
    log_result("contacts.group", payload)
    _print_json(payload)
    return 0


def _contacts_group_members_command(args: argparse.Namespace) -> int:
    payload = list_contact_group_members(
        args.handle,
        limit=args.limit,
    )
    log_result("contacts.group_members", payload)
    _print_json(payload)
    return 0


def _contacts_containers_command(args: argparse.Namespace) -> int:
    payload = search_contact_containers(
        args.query,
        limit=args.limit,
    )
    log_result("contacts.containers", payload)
    _print_json(payload)
    return 0


def _contacts_container_command(args: argparse.Namespace) -> int:
    payload = get_contact_container(args.handle)
    log_result("contacts.container", payload)
    _print_json(payload)
    return 0


def _contacts_container_members_command(args: argparse.Namespace) -> int:
    payload = list_contact_container_members(
        args.handle,
        limit=args.limit,
    )
    log_result("contacts.container_members", payload)
    _print_json(payload)
    return 0


def _contacts_count_command(args: argparse.Namespace) -> int:
    payload = count_contacts(max_contacts=args.max_contacts)
    log_result("contacts.count", payload)
    _print_json(payload)
    return 0


def _contacts_export_command(args: argparse.Namespace) -> int:
    payload = export_contacts_archive(
        output_dir=Path(args.output_dir),
        filename_prefix=args.filename_prefix,
        max_contacts=args.max_contacts,
    )
    log_result("contacts.export", payload)
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


def _contact_method_arg(
    args: argparse.Namespace,
    values_name: str,
    clear_name: str,
) -> list[dict[str, str]] | None:
    values = getattr(args, values_name)
    clear_requested = bool(getattr(args, clear_name))
    operation = str(args.operation).strip().replace("-", "_")
    if clear_requested:
        return []
    if values is None:
        return [] if operation == "create" else None
    return _contact_labeled_values(values)


def _contact_scalar_arg(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name)
    if value is not None:
        return value
    operation = str(args.operation).strip().replace("-", "_")
    return "" if operation == "create" else None


def _json_argument(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("expected valid JSON") from exc


def _contacts_plan_command(args: argparse.Namespace) -> int:
    payload = plan_contact_change(
        args.operation,
        handle=args.handle or "",
        expected_current_sha256=args.expected_current_sha256 or "",
        group_handle=args.group_handle or "",
        expected_group_sha256=args.expected_group_sha256 or "",
        container_handle=args.container_handle or "",
        expected_container_sha256=args.expected_container_sha256 or "",
        group_name=args.group_name,
        contact_type=args.contact_type,
        given_name=_contact_scalar_arg(args, "given_name"),
        family_name=_contact_scalar_arg(args, "family_name"),
        organization_name=_contact_scalar_arg(args, "organization_name"),
        department_name=_contact_scalar_arg(args, "department_name"),
        job_title=_contact_scalar_arg(args, "job_title"),
        nickname=_contact_scalar_arg(args, "nickname"),
        email_addresses=_contact_method_arg(args, "email", "clear_emails"),
        phone_numbers=_contact_method_arg(args, "phone", "clear_phones"),
        url_addresses=_contact_method_arg(args, "url", "clear_urls"),
        note_text=args.note_text,
        postal_addresses=args.postal_addresses_json,
        birthday=args.birthday_json,
        dates=args.dates_json,
        social_profiles=args.social_profiles_json,
        instant_message_addresses=args.instant_message_addresses_json,
        contact_relations=args.contact_relations_json,
        image_path=args.image_path,
        clear_image=args.clear_image,
        batch_items=args.batch_items_json,
    )
    log_result("contacts.plan", payload)
    _print_json(payload)
    return 0


def _contacts_apply_command(args: argparse.Namespace) -> int:
    payload = apply_contact_change(
        args.operation,
        handle=args.handle or "",
        expected_current_sha256=args.expected_current_sha256 or "",
        group_handle=args.group_handle or "",
        expected_group_sha256=args.expected_group_sha256 or "",
        container_handle=args.container_handle or "",
        expected_container_sha256=args.expected_container_sha256 or "",
        group_name=args.group_name,
        contact_type=args.contact_type,
        given_name=_contact_scalar_arg(args, "given_name"),
        family_name=_contact_scalar_arg(args, "family_name"),
        organization_name=_contact_scalar_arg(args, "organization_name"),
        department_name=_contact_scalar_arg(args, "department_name"),
        job_title=_contact_scalar_arg(args, "job_title"),
        nickname=_contact_scalar_arg(args, "nickname"),
        email_addresses=_contact_method_arg(args, "email", "clear_emails"),
        phone_numbers=_contact_method_arg(args, "phone", "clear_phones"),
        url_addresses=_contact_method_arg(args, "url", "clear_urls"),
        note_text=args.note_text,
        postal_addresses=args.postal_addresses_json,
        birthday=args.birthday_json,
        dates=args.dates_json,
        social_profiles=args.social_profiles_json,
        instant_message_addresses=args.instant_message_addresses_json,
        contact_relations=args.contact_relations_json,
        image_path=args.image_path,
        clear_image=args.clear_image,
        batch_items=args.batch_items_json,
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


def _photos_request_access_command(args: argparse.Namespace) -> int:
    payload = request_photos_full_access()
    log_result("photos.request_access", payload)
    _print_json(payload)
    return 0


def _photos_albums_command(args: argparse.Namespace) -> int:
    payload = search_photo_albums(
        args.query,
        limit=args.limit,
        max_scan_albums=args.max_scan_albums,
    )
    log_result("photos.albums", payload)
    _print_json(payload)
    return 0


def _photos_album_command(args: argparse.Namespace) -> int:
    payload = get_photo_album(
        args.handle,
        max_scan_albums=args.max_scan_albums,
    )
    log_result("photos.album", payload)
    _print_json(payload)
    return 0


def _photos_album_assets_command(args: argparse.Namespace) -> int:
    payload = list_photo_album_assets(
        args.handle,
        limit=args.limit,
        max_scan_albums=args.max_scan_albums,
        max_scan_assets=args.max_scan_assets,
    )
    log_result("photos.album_assets", payload)
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
        handle=args.handle or "",
        album_handle=args.album_handle or "",
        album_title=args.album_title or "",
        new_album_title=args.new_album_title or "",
        favorite=_optional_bool_arg(args.favorite),
        hidden=_optional_bool_arg(args.hidden),
        expected_favorite=_optional_bool_arg(args.expected_favorite),
        expected_hidden=_optional_bool_arg(args.expected_hidden),
        expected_in_album=_optional_bool_arg(args.expected_in_album),
        max_scan_assets=args.max_scan_assets,
        max_scan_albums=args.max_scan_albums,
    )
    log_result("photos.plan", payload)
    _print_json(payload)
    return 0


def _photos_apply_command(args: argparse.Namespace) -> int:
    payload = apply_photo_change(
        args.operation,
        source_file=args.source_file,
        media_type=args.media_type,
        handle=args.handle or "",
        album_handle=args.album_handle or "",
        album_title=args.album_title or "",
        new_album_title=args.new_album_title or "",
        favorite=_optional_bool_arg(args.favorite),
        hidden=_optional_bool_arg(args.hidden),
        expected_favorite=_optional_bool_arg(args.expected_favorite),
        expected_hidden=_optional_bool_arg(args.expected_hidden),
        expected_in_album=_optional_bool_arg(args.expected_in_album),
        max_scan_assets=args.max_scan_assets,
        max_scan_albums=args.max_scan_albums,
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("photos.apply", payload)
    _print_json(payload)
    return 0


def _optional_bool_arg(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise SystemExit(f"Expected boolean value, got {value!r}.")


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


def _reminders_request_access_command(args: argparse.Namespace) -> int:
    payload = request_reminders_full_access()
    log_result("reminders.request_access", payload)
    _print_json(payload)
    return 0


def _reminders_lists_command(args: argparse.Namespace) -> int:
    payload = (
        search_reminder_lists(args.query, limit=args.limit)
        if args.query
        else list_reminder_lists(limit=args.limit)
    )
    log_result("reminders.lists", payload)
    _print_json(payload)
    return 0


def _reminders_list_command(args: argparse.Namespace) -> int:
    payload = get_reminder_list(args.handle)
    log_result("reminders.list", payload)
    _print_json(payload)
    return 0


def _reminders_list_items_command(args: argparse.Namespace) -> int:
    payload = list_reminder_items(
        args.handle,
        limit=args.limit,
        include_completed=args.include_completed,
    )
    log_result("reminders.list_items", payload)
    _print_json(payload)
    return 0


def _reminders_content_command(args: argparse.Namespace) -> int:
    payload = get_reminder_content(args.handle, max_chars=args.max_chars)
    log_result("reminders.content", payload)
    _print_json(payload)
    return 0


def _reminders_recurrence_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    expected_recurrence: dict[str, Any] | None = None
    raw_expected = getattr(args, "expected_recurrence", None)
    if raw_expected:
        expected_recurrence = json.loads(raw_expected)
    return {
        "recurrence_frequency": getattr(args, "recurrence_frequency", None) or "",
        "recurrence_interval": getattr(args, "recurrence_interval", None),
        "recurrence_count": getattr(args, "recurrence_count", None),
        "recurrence_end_date": getattr(args, "recurrence_end_date", None) or "",
        "recurrence_unbounded": bool(getattr(args, "recurrence_unbounded", False)),
        "recurrence_weekdays": getattr(args, "recurrence_weekdays", None),
        "recurrence_month_days": getattr(args, "recurrence_month_days", None),
        "recurrence_month_weekdays": getattr(args, "recurrence_month_weekdays", None),
        "recurrence_year_months": getattr(args, "recurrence_year_months", None),
        "recurrence_year_month_days": getattr(args, "recurrence_year_month_days", None),
        "recurrence_year_month_weekdays": getattr(args, "recurrence_year_month_weekdays", None),
        "recurrence_year_days": getattr(args, "recurrence_year_days", None),
        "recurrence_year_weeks": getattr(args, "recurrence_year_weeks", None),
        "recurrence_set_positions": getattr(args, "recurrence_set_positions", None),
        "clear_recurrence": bool(getattr(args, "clear_recurrence", False)),
        "expected_recurrence_present": getattr(args, "expected_recurrence_present", None),
        "expected_recurrence": expected_recurrence,
    }


def _reminders_plan_command(args: argparse.Namespace) -> int:
    payload = plan_reminder_change(
        str(args.operation).replace("-", "_"),
        title=args.title or "",
        list_name=args.list_name or "",
        due_date=args.due_date or "",
        start_date=args.start_date or "",
        expected_start_date=args.expected_start_date or "",
        notes=args.notes,
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_completed=args.expected_completed,
        expected_list_name=args.expected_list_name or "",
        expected_list_handle=args.expected_list_handle or "",
        target_list_handle=args.target_list_handle or "",
        expected_priority=args.expected_priority,
        expected_notes_sha256=args.expected_notes_sha256 or "",
        priority=args.priority,
        url=args.url or "",
        expected_url_present=args.expected_url_present,
        expected_url_sha256=args.expected_url_sha256 or "",
        alarm_absolute_dates=args.alarm_absolute_dates,
        alarm_offsets_minutes=args.alarm_offsets_minutes,
        expected_alarms_count=args.expected_alarms_count,
        expected_alarms_sha256=args.expected_alarms_sha256 or "",
        **_reminders_recurrence_kwargs(args),
    )
    log_result("reminders.plan", payload)
    _print_json(payload)
    return 0


def _reminders_apply_command(args: argparse.Namespace) -> int:
    payload = apply_reminder_change(
        str(args.operation).replace("-", "_"),
        title=args.title or "",
        list_name=args.list_name or "",
        due_date=args.due_date or "",
        start_date=args.start_date or "",
        expected_start_date=args.expected_start_date or "",
        notes=args.notes,
        handle=args.handle or "",
        expected_title=args.expected_title or "",
        expected_completed=args.expected_completed,
        expected_list_name=args.expected_list_name or "",
        expected_list_handle=args.expected_list_handle or "",
        target_list_handle=args.target_list_handle or "",
        expected_priority=args.expected_priority,
        expected_notes_sha256=args.expected_notes_sha256 or "",
        priority=args.priority,
        url=args.url or "",
        expected_url_present=args.expected_url_present,
        expected_url_sha256=args.expected_url_sha256 or "",
        alarm_absolute_dates=args.alarm_absolute_dates,
        alarm_offsets_minutes=args.alarm_offsets_minutes,
        expected_alarms_count=args.expected_alarms_count,
        expected_alarms_sha256=args.expected_alarms_sha256 or "",
        **_reminders_recurrence_kwargs(args),
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("reminders.apply", payload)
    _print_json(payload)
    return 0


def _reminders_plan_list_command(args: argparse.Namespace) -> int:
    payload = plan_reminder_list_change(
        str(args.operation).replace("-", "_"),
        source_list_handle=args.source_list_handle or "",
        list_handle=args.list_handle or "",
        target_list_handle=args.target_list_handle or "",
        list_title=args.list_title or "",
        new_list_title=args.new_list_title or "",
    )
    log_result("reminders.plan_list", payload)
    _print_json(payload)
    return 0


def _reminders_apply_list_command(args: argparse.Namespace) -> int:
    payload = apply_reminder_list_change(
        str(args.operation).replace("-", "_"),
        source_list_handle=args.source_list_handle or "",
        list_handle=args.list_handle or "",
        target_list_handle=args.target_list_handle or "",
        list_title=args.list_title or "",
        new_list_title=args.new_list_title or "",
        approval_token=args.approval_token or "",
        confirm_apply=args.confirm_apply,
    )
    log_result("reminders.apply_list", payload)
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
    mail_search.add_argument(
        "--mailbox-handle",
        default="",
        help="Optional exact mail:mailbox:v1 handle filter from mail mailboxes output.",
    )
    mail_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_search.set_defaults(func=_mail_search_command)

    mail_body_search = mail_subparsers.add_parser(
        "body-search",
        help="Search bounded local Mail body snippets within a required date range.",
    )
    mail_body_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_body_search.add_argument("--query", required=True, help="Body query text.")
    mail_body_search.add_argument("--after", help="ISO date/time or Mail timestamp lower bound.")
    mail_body_search.add_argument("--before", help="ISO date/time or Mail timestamp upper bound.")
    mail_body_search.add_argument("--cursor", default="", help="Pagination cursor from prior output.")
    mail_body_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_body_search.add_argument(
        "--max-snippet-chars",
        type=int,
        default=240,
        help="Maximum snippet characters per result, capped at 500.",
    )
    mail_body_search.add_argument(
        "--max-seconds",
        type=float,
        default=20,
        help="Scan time budget in seconds (1-120); stops cleanly with next_cursor.",
    )
    mail_body_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_body_search.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_body_search.set_defaults(func=_mail_body_search_command)

    mail_attachment_search = mail_subparsers.add_parser(
        "attachment-search",
        help="Search local Mail attachment filename/MIME metadata within a required date range.",
    )
    mail_attachment_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_attachment_search.add_argument("--query", required=True, help="Attachment filename or MIME query text.")
    mail_attachment_search.add_argument("--after", help="ISO date/time or Mail timestamp lower bound.")
    mail_attachment_search.add_argument("--before", help="ISO date/time or Mail timestamp upper bound.")
    mail_attachment_search.add_argument("--cursor", default="", help="Pagination cursor from prior output.")
    mail_attachment_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_attachment_search.add_argument(
        "--include-content",
        action="store_true",
        help="Also search bounded text/PDF attachment content snippets.",
    )
    mail_attachment_search.add_argument(
        "--include-ocr",
        action="store_true",
        help="Allow OCR fallback for PDF attachments when --include-content is set.",
    )
    mail_attachment_search.add_argument(
        "--max-snippet-chars",
        type=int,
        default=240,
        help="Maximum attachment content snippet characters per result, capped at 500.",
    )
    mail_attachment_search.add_argument(
        "--max-seconds",
        type=float,
        default=20,
        help="Scan time budget in seconds (1-120); stops cleanly with next_cursor.",
    )
    mail_attachment_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_attachment_search.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_attachment_search.set_defaults(func=_mail_attachment_search_command)

    mail_advanced_search = mail_subparsers.add_parser(
        "advanced-search",
        help="Search Mail subject/header/body/attachment metadata within a required date range.",
    )
    mail_advanced_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_advanced_search.add_argument("--query", required=True, help="Query text.")
    mail_advanced_search.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Search scope: subject, from, to, cc, bcc, body, or attachment_filename. Repeat or comma-separate.",
    )
    mail_advanced_search.add_argument("--after", help="ISO date/time or Mail timestamp lower bound.")
    mail_advanced_search.add_argument("--before", help="ISO date/time or Mail timestamp upper bound.")
    mail_advanced_search.add_argument("--mailbox", default="", help="Optional mailbox-name metadata filter.")
    attachment_filter = mail_advanced_search.add_mutually_exclusive_group()
    attachment_filter.add_argument(
        "--has-attachments",
        dest="has_attachments",
        action="store_true",
        default=None,
        help="Return only messages with attachments.",
    )
    attachment_filter.add_argument(
        "--no-attachments",
        dest="has_attachments",
        action="store_false",
        help="Return only messages without attachments.",
    )
    mail_advanced_search.add_argument("--cursor", default="", help="Pagination cursor from prior output.")
    mail_advanced_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_advanced_search.add_argument(
        "--max-snippet-chars",
        type=int,
        default=240,
        help="Maximum body snippet characters per result, capped at 500.",
    )
    mail_advanced_search.add_argument(
        "--max-seconds",
        type=float,
        default=20,
        help="Scan time budget in seconds (1-120); stops cleanly with next_cursor.",
    )
    mail_advanced_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_advanced_search.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_advanced_search.set_defaults(func=_mail_advanced_search_command)

    mail_fts_build = mail_subparsers.add_parser(
        "fts-build",
        help="Build an opt-in local Mail FTS index for a required date range.",
    )
    mail_fts_build.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_fts_build.add_argument("--after", help="ISO date/time or Mail timestamp lower bound.")
    mail_fts_build.add_argument("--before", help="ISO date/time or Mail timestamp upper bound.")
    mail_fts_build.add_argument("--cursor", default="", help="Pagination cursor from prior build output.")
    mail_fts_build.add_argument("--limit", type=int, default=1000, help="Maximum messages to index, capped at 1000.")
    mail_fts_build.add_argument(
        "--include-attachments",
        action="store_true",
        help="Also index attachment filename/MIME metadata and bounded text/PDF content.",
    )
    mail_fts_build.add_argument(
        "--include-ocr",
        action="store_true",
        help="Allow OCR fallback for PDF attachment indexing when --include-attachments is set.",
    )
    mail_fts_build.add_argument(
        "--confirm-index",
        action="store_true",
        help="Required confirmation because this writes a local durable content index.",
    )
    mail_fts_build.add_argument("--reset", action="store_true", help="Clear the existing index before building.")
    mail_fts_build.add_argument(
        "--max-seconds",
        type=float,
        default=20,
        help="Scan time budget in seconds (1-120); stops cleanly with next_cursor.",
    )
    mail_fts_build.add_argument("--index", help=argparse.SUPPRESS)
    mail_fts_build.add_argument("--db", help=argparse.SUPPRESS)
    mail_fts_build.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_fts_build.set_defaults(func=_mail_fts_build_command)

    mail_fts_search = mail_subparsers.add_parser(
        "fts-search",
        help="Search the opt-in local Mail FTS index within a required date range.",
    )
    mail_fts_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_fts_search.add_argument("--query", required=True, help="Query text.")
    mail_fts_search.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Search scope: subject, from, to, cc, bcc, body, attachment_filename, or attachment_content. Repeat or comma-separate.",
    )
    mail_fts_search.add_argument("--after", help="ISO date/time or Mail timestamp lower bound.")
    mail_fts_search.add_argument("--before", help="ISO date/time or Mail timestamp upper bound.")
    mail_fts_search.add_argument("--cursor", default="", help="Pagination cursor from prior output.")
    mail_fts_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_fts_search.add_argument(
        "--max-snippet-chars",
        type=int,
        default=240,
        help="Maximum snippet characters per result, capped at 500.",
    )
    mail_fts_search.add_argument("--index", help=argparse.SUPPRESS)
    mail_fts_search.add_argument("--db", help=argparse.SUPPRESS)
    mail_fts_search.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_fts_search.set_defaults(func=_mail_fts_search_command)

    mail_fts_status = mail_subparsers.add_parser(
        "fts-status",
        help="Report the opt-in local Mail FTS index state, coverage counts, and resume checkpoint.",
    )
    mail_fts_status.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_fts_status.add_argument("--index", help=argparse.SUPPRESS)
    mail_fts_status.add_argument("--db", help=argparse.SUPPRESS)
    mail_fts_status.set_defaults(func=_mail_fts_status_command)

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

    mail_mailboxes = mail_subparsers.add_parser(
        "mailboxes",
        help="Search Mail mailbox metadata by mailbox name.",
    )
    mail_mailboxes.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_mailboxes.add_argument("--query", required=True, help="Mailbox name query text.")
    mail_mailboxes.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_mailboxes.add_argument("--db", help=argparse.SUPPRESS)
    mail_mailboxes.set_defaults(func=_mail_mailboxes_command)

    mail_mailbox = mail_subparsers.add_parser(
        "mailbox",
        help="Get exact Mail mailbox metadata by handle.",
    )
    mail_mailbox.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_mailbox.add_argument("--handle", required=True, help="Mailbox handle from mailboxes output.")
    mail_mailbox.add_argument("--db", help=argparse.SUPPRESS)
    mail_mailbox.set_defaults(func=_mail_mailbox_command)

    mail_mailbox_messages = mail_subparsers.add_parser(
        "mailbox-messages",
        help="List date-bounded Mail message metadata for one exact mailbox handle.",
    )
    mail_mailbox_messages.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_mailbox_messages.add_argument("--handle", required=True, help="Mailbox handle from mailboxes output.")
    mail_mailbox_messages.add_argument("--after", default="", help="Required ISO date/time or Mail timestamp lower bound unless --before is set.")
    mail_mailbox_messages.add_argument("--before", default="", help="Required ISO date/time or Mail timestamp upper bound unless --after is set.")
    mail_mailbox_messages.add_argument("--limit", type=int, default=20, help="Maximum message results, capped at 50.")
    mail_mailbox_messages.add_argument("--db", help=argparse.SUPPRESS)
    mail_mailbox_messages.set_defaults(func=_mail_mailbox_messages_command)

    mail_senders = mail_subparsers.add_parser(
        "senders",
        help="Search configured Mail sender metadata by account label or masked email.",
    )
    mail_senders.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_senders.add_argument("--query", required=True, help="Sender account label or email query text.")
    mail_senders.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_senders.set_defaults(func=_mail_senders_command)

    mail_sender = mail_subparsers.add_parser(
        "sender",
        help="Get exact configured Mail sender metadata by handle.",
    )
    mail_sender.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_sender.add_argument("--handle", required=True, help="Sender handle from senders output.")
    mail_sender.set_defaults(func=_mail_sender_command)

    mail_signatures = mail_subparsers.add_parser(
        "signatures",
        help="Search configured Mail signature names without returning signature bodies.",
    )
    mail_signatures.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_signatures.add_argument("--query", required=True, help="Signature name query text.")
    mail_signatures.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_signatures.set_defaults(func=_mail_signatures_command)

    mail_signature = mail_subparsers.add_parser(
        "signature",
        help="Get exact configured Mail signature metadata by handle without returning the body.",
    )
    mail_signature.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_signature.add_argument("--handle", required=True, help="Signature handle from signatures output.")
    mail_signature.set_defaults(func=_mail_signature_command)

    mail_template_create = mail_subparsers.add_parser(
        "template-create",
        help="Create a plugin-managed Mail template from explicit user-provided text.",
    )
    mail_template_create.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_template_create.add_argument("--name", required=True, help="Unique template name.")
    mail_template_create.add_argument("--subject", default="", help="Optional template subject for draft/send.")
    mail_template_create.add_argument(
        "--body-text",
        required=True,
        help="Plain-text template body, capped at 12000 characters.",
    )
    mail_template_create.set_defaults(func=_mail_template_create_command)

    mail_templates = mail_subparsers.add_parser(
        "templates",
        help="Search plugin-managed Mail template metadata without returning template bodies.",
    )
    mail_templates.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_templates.add_argument("--query", default="", help="Optional template name/subject query.")
    mail_templates.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    mail_templates.set_defaults(func=_mail_templates_command)

    mail_template = mail_subparsers.add_parser(
        "template",
        help="Get exact plugin-managed Mail template metadata by handle.",
    )
    mail_template.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_template.add_argument("--handle", required=True, help="Template handle from templates output.")
    mail_template.add_argument(
        "--include-body",
        action="store_true",
        help="Return the exact stored template body for the selected template.",
    )
    mail_template.set_defaults(func=_mail_template_command)

    mail_template_delete = mail_subparsers.add_parser(
        "template-delete",
        help="Delete one exact plugin-managed Mail template by handle.",
    )
    mail_template_delete.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_template_delete.add_argument("--handle", required=True, help="Template handle from templates output.")
    mail_template_delete.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Required confirmation for template deletion.",
    )
    mail_template_delete.set_defaults(func=_mail_template_delete_command)

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
    mail_content.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Character offset for paged content retrieval.",
    )
    mail_content.add_argument("--db", help=argparse.SUPPRESS)
    mail_content.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_content.set_defaults(func=_mail_content_command)

    mail_unsubscribe_metadata = mail_subparsers.add_parser(
        "unsubscribe-metadata",
        help="Get allowlisted unsubscribe header metadata for one exact Mail message.",
    )
    mail_unsubscribe_metadata.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_unsubscribe_metadata.add_argument(
        "--handle",
        required=True,
        help="Mail message handle from search output.",
    )
    mail_unsubscribe_metadata.add_argument(
        "--include-body-links",
        action="store_true",
        help="Inspect the selected MIME body for conservative manual unsubscribe links.",
    )
    mail_unsubscribe_metadata.add_argument("--db", help=argparse.SUPPRESS)
    mail_unsubscribe_metadata.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_unsubscribe_metadata.set_defaults(func=_mail_unsubscribe_metadata_command)

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
        help="Preview an approved Mail change without writing.",
    )
    mail_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-draft",
            "create_draft",
            "send-message",
            "send_message",
            "reply-message",
            "reply_message",
            "reply-all-message",
            "reply_all_message",
            "forward-message",
            "forward_message",
            "mark-read",
            "mark_read",
            "mark-unread",
            "mark_unread",
            "flag-message",
            "flag_message",
            "unflag-message",
            "unflag_message",
            "archive-message",
            "archive_message",
            "trash-message",
            "trash_message",
            "move-message",
            "move_message",
        ],
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
    mail_plan.add_argument("--subject", help="Draft or outbound message subject. Reply/reply-all/forward derive this from the exact source message.")
    mail_plan.add_argument(
        "--body-text",
        default="",
        help="Plain-text draft, outbound, reply, reply-all, or forward body, capped at 12000 characters.",
    )
    mail_plan.add_argument(
        "--message-handle",
        action="append",
        default=[],
        help="Mail message handle for exact-message reply/reply-all/forward/status/archive/trash/move planning; repeat for capped bulk triage.",
    )
    mail_plan.add_argument(
        "--target-mailbox-handle",
        default="",
        help="Mail mailbox handle from mailboxes output for move-message planning.",
    )
    mail_plan.add_argument(
        "--sender-handle",
        default="",
        help="Mail sender handle from senders output for draft/send/reply/reply-all/forward planning.",
    )
    mail_plan.add_argument(
        "--signature-handle",
        default="",
        help="Mail signature handle from signatures output for draft/send/reply/reply-all/forward planning.",
    )
    mail_plan.add_argument(
        "--template-handle",
        default="",
        help="Mail template handle from templates output for draft/send/reply/reply-all/forward planning.",
    )
    mail_plan.add_argument(
        "--attachment-path",
        action="append",
        default=[],
        help="Local file path to attach to draft/send/reply/reply-all/forward plans. Repeat for multiple files.",
    )
    mail_plan.add_argument(
        "--include-source-attachments",
        action="store_true",
        help="For forward-message only, preserve source message attachments and non-body parts through Mail.app forwarding.",
    )
    mail_plan.add_argument("--db", help=argparse.SUPPRESS)
    mail_plan.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_plan.set_defaults(func=_mail_plan_command)

    mail_plan_search_triage = mail_subparsers.add_parser(
        "plan-search-triage",
        help="Convert capped FTS query results into an exact-handle bulk triage plan.",
    )
    mail_plan_search_triage.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_plan_search_triage.add_argument(
        "--operation",
        required=True,
        choices=[
            "mark-read",
            "mark_read",
            "mark-unread",
            "mark_unread",
            "flag-message",
            "flag_message",
            "unflag-message",
            "unflag_message",
            "archive-message",
            "archive_message",
            "trash-message",
            "trash_message",
            "move-message",
            "move_message",
        ],
        help="Bulk triage operation to preview.",
    )
    mail_plan_search_triage.add_argument("--query", required=True, help="FTS query text.")
    mail_plan_search_triage.add_argument(
        "--search-source",
        default="fts",
        choices=["fts"],
        help="Search source for result selection.",
    )
    mail_plan_search_triage.add_argument(
        "--scope",
        action="append",
        default=[],
        help="FTS scope to search. Repeat for multiple scopes.",
    )
    mail_plan_search_triage.add_argument("--after", default=None, help="Required lower date bound for FTS search.")
    mail_plan_search_triage.add_argument("--before", default=None, help="Optional upper date bound for FTS search.")
    mail_plan_search_triage.add_argument("--cursor", default="", help="FTS result cursor.")
    mail_plan_search_triage.add_argument("--limit", type=int, default=20, help="Maximum messages, capped at 20.")
    mail_plan_search_triage.add_argument(
        "--target-mailbox-handle",
        default="",
        help="Mail mailbox handle from mailboxes output for move-message planning.",
    )
    mail_plan_search_triage.add_argument("--db", help=argparse.SUPPRESS)
    mail_plan_search_triage.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_plan_search_triage.add_argument("--index", help=argparse.SUPPRESS)
    mail_plan_search_triage.set_defaults(func=_mail_plan_search_triage_command)

    mailbox_operation_choices = [
        "create-mailbox",
        "create_mailbox",
        "rename-mailbox",
        "rename_mailbox",
        "delete-mailbox",
        "delete_mailbox",
    ]
    mail_plan_mailbox = mail_subparsers.add_parser(
        "plan-mailbox",
        help="Preview a synthetic LAD-TEST-* Mail mailbox create/rename/delete operation.",
    )
    mail_plan_mailbox.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_plan_mailbox.add_argument("--operation", required=True, choices=mailbox_operation_choices)
    mail_plan_mailbox.add_argument("--sender-handle", default="", help="Sender handle selecting the target account for create-mailbox.")
    mail_plan_mailbox.add_argument("--mailbox-handle", default="", help="Mailbox handle from mailboxes output for rename/delete.")
    mail_plan_mailbox.add_argument("--mailbox-name", default="", help="Synthetic LAD-TEST-* mailbox name for create.")
    mail_plan_mailbox.add_argument("--new-mailbox-name", default="", help="Synthetic LAD-TEST-* target name for rename.")
    mail_plan_mailbox.add_argument("--db", help=argparse.SUPPRESS)
    mail_plan_mailbox.set_defaults(func=_mail_plan_mailbox_command)

    mail_apply_mailbox = mail_subparsers.add_parser(
        "apply-mailbox",
        help="Apply an approved synthetic LAD-TEST-* Mail mailbox operation.",
    )
    mail_apply_mailbox.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_apply_mailbox.add_argument("--operation", required=True, choices=mailbox_operation_choices)
    mail_apply_mailbox.add_argument("--sender-handle", default="", help="Sender handle selecting the target account for create-mailbox.")
    mail_apply_mailbox.add_argument("--mailbox-handle", default="", help="Mailbox handle from mailboxes output for rename/delete.")
    mail_apply_mailbox.add_argument("--mailbox-name", default="", help="Synthetic LAD-TEST-* mailbox name for create.")
    mail_apply_mailbox.add_argument("--new-mailbox-name", default="", help="Synthetic LAD-TEST-* target name for rename.")
    mail_apply_mailbox.add_argument("--approval-token", required=True, help="Approval token returned by plan-mailbox.")
    mail_apply_mailbox.add_argument("--confirm-apply", action="store_true", help="Required confirmation.")
    mail_apply_mailbox.add_argument("--db", help=argparse.SUPPRESS)
    mail_apply_mailbox.set_defaults(func=_mail_apply_mailbox_command)

    cleanup_operation_choices = [
        "permanent-delete-message",
        "permanent_delete_message",
        "empty-trash",
        "empty_trash",
        "empty-junk",
        "empty_junk",
    ]
    mail_plan_cleanup = mail_subparsers.add_parser(
        "plan-cleanup",
        help="Preview synthetic-only Mail permanent delete or empty Trash/Junk cleanup.",
    )
    mail_plan_cleanup.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_plan_cleanup.add_argument("--operation", required=True, choices=cleanup_operation_choices)
    mail_plan_cleanup.add_argument("--message-handle", default="", help="Exact synthetic Trash/Junk message handle for permanent-delete-message.")
    mail_plan_cleanup.add_argument("--sender-handle", default="", help="Sender handle selecting the target account for empty-trash/empty-junk.")
    mail_plan_cleanup.add_argument("--db", help=argparse.SUPPRESS)
    mail_plan_cleanup.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_plan_cleanup.set_defaults(func=_mail_plan_cleanup_command)

    mail_apply_cleanup = mail_subparsers.add_parser(
        "apply-cleanup",
        help="Apply approved synthetic-only Mail permanent delete or empty Trash/Junk cleanup.",
    )
    mail_apply_cleanup.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_apply_cleanup.add_argument("--operation", required=True, choices=cleanup_operation_choices)
    mail_apply_cleanup.add_argument("--message-handle", default="", help="Exact synthetic Trash/Junk message handle for permanent-delete-message.")
    mail_apply_cleanup.add_argument("--sender-handle", default="", help="Sender handle selecting the target account for empty-trash/empty-junk.")
    mail_apply_cleanup.add_argument("--approval-token", required=True, help="Approval token returned by plan-cleanup.")
    mail_apply_cleanup.add_argument("--confirm-apply", action="store_true", help="Required confirmation.")
    mail_apply_cleanup.add_argument("--db", help=argparse.SUPPRESS)
    mail_apply_cleanup.add_argument("--mail-root", help=argparse.SUPPRESS)
    mail_apply_cleanup.set_defaults(func=_mail_apply_cleanup_command)

    mail_apply = mail_subparsers.add_parser(
        "apply",
        help="Apply an approved Mail change after plan approval.",
    )
    mail_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    mail_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-draft",
            "create_draft",
            "send-message",
            "send_message",
            "reply-message",
            "reply_message",
            "reply-all-message",
            "reply_all_message",
            "forward-message",
            "forward_message",
            "mark-read",
            "mark_read",
            "mark-unread",
            "mark_unread",
            "flag-message",
            "flag_message",
            "unflag-message",
            "unflag_message",
            "archive-message",
            "archive_message",
            "trash-message",
            "trash_message",
            "move-message",
            "move_message",
        ],
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
    mail_apply.add_argument("--subject", help="Draft or outbound message subject. Reply/reply-all/forward derive this from the exact source message.")
    mail_apply.add_argument(
        "--body-text",
        default="",
        help="Plain-text draft, outbound, reply, reply-all, or forward body, capped at 12000 characters.",
    )
    mail_apply.add_argument(
        "--message-handle",
        action="append",
        default=[],
        help="Mail message handle for exact-message reply/reply-all/forward/status/archive/trash/move apply; repeat for capped bulk triage.",
    )
    mail_apply.add_argument(
        "--target-mailbox-handle",
        default="",
        help="Mail mailbox handle from mailboxes output for move-message apply.",
    )
    mail_apply.add_argument(
        "--sender-handle",
        default="",
        help="Mail sender handle from senders output for draft/send/reply/reply-all/forward apply.",
    )
    mail_apply.add_argument(
        "--signature-handle",
        default="",
        help="Mail signature handle from signatures output for draft/send/reply/reply-all/forward apply.",
    )
    mail_apply.add_argument(
        "--template-handle",
        default="",
        help="Mail template handle from templates output for draft/send/reply/reply-all/forward apply.",
    )
    mail_apply.add_argument(
        "--attachment-path",
        action="append",
        default=[],
        help="Local file path to attach to draft/send/reply/reply-all/forward apply. Repeat for multiple files.",
    )
    mail_apply.add_argument(
        "--include-source-attachments",
        action="store_true",
        help="For forward-message only, preserve source message attachments and non-body parts through Mail.app forwarding.",
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

    messages_participants = messages_subparsers.add_parser(
        "participants",
        help="List exact local Messages participant metadata by chat handle.",
    )
    messages_participants.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_participants.add_argument(
        "--handle",
        required=True,
        help="Messages chat handle from search output.",
    )
    messages_participants.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum participant results, capped at 50.",
    )
    messages_participants.add_argument("--db", help=argparse.SUPPRESS)
    messages_participants.set_defaults(func=_messages_participants_command)

    messages_participant = messages_subparsers.add_parser(
        "participant",
        help="Get exact local Messages participant detail by chat and participant handles.",
    )
    messages_participant.add_argument("--json", action="store_true", help="Emit JSON output.")
    messages_participant.add_argument(
        "--chat-handle",
        required=True,
        help="Messages chat handle from search output.",
    )
    messages_participant.add_argument(
        "--handle",
        required=True,
        help="Messages participant handle from participants output.",
    )
    messages_participant.add_argument("--db", help=argparse.SUPPRESS)
    messages_participant.set_defaults(func=_messages_participant_command)

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
        choices=["send-text", "send_text", "send-file", "send_file"],
        help="Messages change to plan.",
    )
    messages_plan.add_argument(
        "--handle",
        required=True,
        help="Opaque messages:chat:v1 handle returned by messages search.",
    )
    messages_plan.add_argument("--body-text", default="", help="Plaintext message body for send-text.")
    messages_plan.add_argument("--file-path", default="", help="Local file path for send-file.")
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
        choices=["send-text", "send_text", "send-file", "send_file"],
        help="Messages change to apply.",
    )
    messages_apply.add_argument(
        "--handle",
        required=True,
        help="Opaque messages:chat:v1 handle returned by messages search.",
    )
    messages_apply.add_argument("--body-text", default="", help="Plaintext message body for send-text.")
    messages_apply.add_argument("--file-path", default="", help="Local file path for send-file.")
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

    safari_folders = safari_subparsers.add_parser(
        "folders",
        help="Search Safari bookmark folder metadata by title.",
    )
    safari_folders.add_argument("--json", action="store_true", help="Emit JSON output.")
    safari_folders.add_argument("--query", required=True, help="Folder title query text.")
    safari_folders.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    safari_folders.add_argument(
        "--max-scan-items",
        type=int,
        default=20000,
        help="Maximum bookmark entries to scan.",
    )
    safari_folders.add_argument("--bookmarks-path", help=argparse.SUPPRESS)
    safari_folders.set_defaults(func=_safari_folders_command)

    safari_folder = safari_subparsers.add_parser(
        "folder",
        help="Get exact Safari folder metadata by handle.",
    )
    safari_folder.add_argument("--json", action="store_true", help="Emit JSON output.")
    safari_folder.add_argument(
        "--handle",
        required=True,
        help="Safari folder handle from folder search output.",
    )
    safari_folder.add_argument(
        "--max-scan-items",
        type=int,
        default=20000,
        help="Maximum bookmark entries to scan while resolving the handle.",
    )
    safari_folder.add_argument("--bookmarks-path", help=argparse.SUPPRESS)
    safari_folder.set_defaults(func=_safari_folder_command)

    safari_folder_items = safari_subparsers.add_parser(
        "folder-items",
        help="List direct Safari bookmark metadata for one exact folder handle.",
    )
    safari_folder_items.add_argument("--json", action="store_true", help="Emit JSON output.")
    safari_folder_items.add_argument(
        "--handle",
        required=True,
        help="Safari folder handle from folder search output.",
    )
    safari_folder_items.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum direct items and child folders, capped at 50.",
    )
    safari_folder_items.add_argument(
        "--max-scan-items",
        type=int,
        default=20000,
        help="Maximum bookmark entries to scan while resolving the handle.",
    )
    safari_folder_items.add_argument("--bookmarks-path", help=argparse.SUPPRESS)
    safari_folder_items.set_defaults(func=_safari_folder_items_command)

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

    shortcuts_folder_items = shortcuts_subparsers.add_parser(
        "folder-items",
        help="List exact selected Shortcuts folder shortcut metadata by folder handle.",
    )
    shortcuts_folder_items.add_argument("--json", action="store_true", help="Emit JSON output.")
    shortcuts_folder_items.add_argument(
        "--handle",
        required=True,
        help="Shortcuts folder handle from search output.",
    )
    shortcuts_folder_items.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum contained shortcuts, capped at 50.",
    )
    shortcuts_folder_items.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Shortcuts items to scan while resolving the handle.",
    )
    shortcuts_folder_items.set_defaults(func=_shortcuts_folder_items_command)

    shortcuts_plan = shortcuts_subparsers.add_parser(
        "plan",
        help="Plan an exact identifier-bound Shortcuts run without executing it.",
    )
    shortcuts_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    shortcuts_plan.add_argument(
        "--operation",
        required=True,
        choices=["run"],
        help="Shortcuts run operation to plan.",
    )
    shortcuts_plan.add_argument(
        "--handle",
        required=True,
        help="Exact shortcuts:item:v1 shortcut handle from search output.",
    )
    shortcuts_plan.add_argument(
        "--input-text",
        default="",
        help="Optional bounded plaintext input passed to the shortcut by temp-file path (argv only).",
    )
    shortcuts_plan.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Shortcuts items to scan while resolving the handle.",
    )
    shortcuts_plan.set_defaults(func=_shortcuts_plan_command)

    shortcuts_apply = shortcuts_subparsers.add_parser(
        "apply",
        help="Apply an approved Shortcuts run; proves invocation only, not the shortcut's arbitrary effects.",
    )
    shortcuts_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    shortcuts_apply.add_argument(
        "--operation",
        required=True,
        choices=["run"],
        help="Shortcuts run operation to apply.",
    )
    shortcuts_apply.add_argument(
        "--handle",
        required=True,
        help="Exact shortcuts:item:v1 shortcut handle from search output.",
    )
    shortcuts_apply.add_argument(
        "--input-text",
        default="",
        help="Optional bounded plaintext input passed to the shortcut by temp-file path (argv only).",
    )
    shortcuts_apply.add_argument(
        "--approval-token",
        required=True,
        help="Exact shortcuts-apply:v1 approval token from the matching plan.",
    )
    shortcuts_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation for the arbitrary-execution Shortcuts run apply.",
    )
    shortcuts_apply.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Shortcuts items to scan while resolving the handle.",
    )
    shortcuts_apply.set_defaults(func=_shortcuts_apply_command)

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

    music_playlist_tracks = music_subparsers.add_parser(
        "playlist-tracks",
        help="List exact selected Apple Music playlist track metadata by playlist handle.",
    )
    music_playlist_tracks.add_argument("--json", action="store_true", help="Emit JSON output.")
    music_playlist_tracks.add_argument(
        "--handle",
        required=True,
        help="Playlist handle from playlists output.",
    )
    music_playlist_tracks.add_argument("--limit", type=int, default=20, help="Maximum tracks, capped at 50.")
    music_playlist_tracks.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum Music.app playlists and tracks to scan, capped by the adapter.",
    )
    music_playlist_tracks.set_defaults(func=_music_playlist_tracks_command)

    tv = subparsers.add_parser(
        "tv",
        help="Apple TV item and playlist metadata commands.",
    )
    tv_subparsers = tv.add_subparsers(dest="tv_command", required=True)

    tv_search = tv_subparsers.add_parser(
        "search",
        help="Search Apple TV item metadata by title, show, artist, genre, or kind.",
    )
    tv_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    tv_search.add_argument(
        "--query",
        required=True,
        help="Item title, show, artist, genre, or kind query text.",
    )
    tv_search.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    tv_search.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum TV.app items to scan, capped by the adapter.",
    )
    tv_search.set_defaults(func=_tv_search_command)

    tv_get = tv_subparsers.add_parser(
        "get",
        help="Get exact Apple TV item metadata by handle.",
    )
    tv_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    tv_get.add_argument("--handle", required=True, help="Item handle from search output.")
    tv_get.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum TV.app items to scan, capped by the adapter.",
    )
    tv_get.set_defaults(func=_tv_get_command)

    tv_playlists = tv_subparsers.add_parser(
        "playlists",
        help="Search Apple TV playlist metadata by playlist name.",
    )
    tv_playlists.add_argument("--json", action="store_true", help="Emit JSON output.")
    tv_playlists.add_argument("--query", required=True, help="Playlist name query text.")
    tv_playlists.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    tv_playlists.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum TV.app playlists to scan, capped by the adapter.",
    )
    tv_playlists.set_defaults(func=_tv_playlists_command)

    tv_playlist = tv_subparsers.add_parser(
        "playlist",
        help="Get exact Apple TV playlist metadata by handle.",
    )
    tv_playlist.add_argument("--json", action="store_true", help="Emit JSON output.")
    tv_playlist.add_argument("--handle", required=True, help="Playlist handle from search output.")
    tv_playlist.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum TV.app playlists to scan, capped by the adapter.",
    )
    tv_playlist.set_defaults(func=_tv_playlist_command)

    tv_playlist_items = tv_subparsers.add_parser(
        "playlist-items",
        help="List exact selected Apple TV playlist item metadata by opaque playlist handle.",
    )
    tv_playlist_items.add_argument("--json", action="store_true", help="Emit JSON output.")
    tv_playlist_items.add_argument("--handle", required=True, help="Playlist handle from search output.")
    tv_playlist_items.add_argument("--limit", type=int, default=20, help="Maximum items, capped at 50.")
    tv_playlist_items.add_argument(
        "--max-scan-items",
        type=int,
        default=5000,
        help="Maximum TV.app playlists and items to scan, capped by the adapter.",
    )
    tv_playlist_items.set_defaults(func=_tv_playlist_items_command)

    freeform = subparsers.add_parser(
        "freeform",
        help="Apple Freeform board and folder metadata commands.",
    )
    freeform_subparsers = freeform.add_subparsers(
        dest="freeform_command",
        required=True,
    )

    freeform_boards = freeform_subparsers.add_parser(
        "boards",
        help="List recent Apple Freeform board metadata without board content.",
    )
    freeform_boards.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_boards.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    freeform_boards.add_argument("--db", help=argparse.SUPPRESS)
    freeform_boards.set_defaults(func=_freeform_boards_command)

    freeform_get = freeform_subparsers.add_parser(
        "get",
        help="Get exact Apple Freeform board metadata by handle.",
    )
    freeform_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_get.add_argument("--handle", required=True, help="Board handle from boards output.")
    freeform_get.add_argument("--db", help=argparse.SUPPRESS)
    freeform_get.set_defaults(func=_freeform_get_command)

    freeform_folders = freeform_subparsers.add_parser(
        "folders",
        help="Search Apple Freeform folder metadata by folder title.",
    )
    freeform_folders.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_folders.add_argument("--query", required=True, help="Folder title query text.")
    freeform_folders.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    freeform_folders.add_argument("--db", help=argparse.SUPPRESS)
    freeform_folders.set_defaults(func=_freeform_folders_command)

    freeform_folder = freeform_subparsers.add_parser(
        "folder",
        help="Get exact Apple Freeform folder metadata by handle.",
    )
    freeform_folder.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_folder.add_argument("--handle", required=True, help="Folder handle from folders output.")
    freeform_folder.add_argument("--db", help=argparse.SUPPRESS)
    freeform_folder.set_defaults(func=_freeform_folder_command)

    freeform_folder_boards = freeform_subparsers.add_parser(
        "folder-boards",
        help="List exact selected Freeform folder board metadata by folder handle.",
    )
    freeform_folder_boards.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_folder_boards.add_argument(
        "--handle",
        required=True,
        help="Folder handle from folders output.",
    )
    freeform_folder_boards.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    freeform_folder_boards.add_argument("--db", help=argparse.SUPPRESS)
    freeform_folder_boards.set_defaults(func=_freeform_folder_boards_command)

    freeform_child_folders = freeform_subparsers.add_parser(
        "child-folders",
        help="List exact selected Freeform child folder metadata by folder handle.",
    )
    freeform_child_folders.add_argument("--json", action="store_true", help="Emit JSON output.")
    freeform_child_folders.add_argument(
        "--handle",
        required=True,
        help="Folder handle from folders output.",
    )
    freeform_child_folders.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    freeform_child_folders.add_argument("--db", help=argparse.SUPPRESS)
    freeform_child_folders.set_defaults(func=_freeform_child_folders_command)

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

    notes_folders = notes_subparsers.add_parser(
        "folders",
        help="Search Notes folder metadata by folder title.",
    )
    notes_folders.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_folders.add_argument("--query", required=True, help="Folder title query text.")
    notes_folders.add_argument("--limit", type=int, default=20, help="Maximum results, capped at 50.")
    notes_folders.add_argument("--db", help=argparse.SUPPRESS)
    notes_folders.set_defaults(func=_notes_folders_command)

    notes_folder = notes_subparsers.add_parser(
        "folder",
        help="Get exact Notes folder metadata by handle.",
    )
    notes_folder.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_folder.add_argument("--handle", required=True, help="Notes folder handle from folders output.")
    notes_folder.add_argument("--db", help=argparse.SUPPRESS)
    notes_folder.set_defaults(func=_notes_folder_command)

    notes_folder_items = notes_subparsers.add_parser(
        "folder-items",
        help="List exact selected Notes folder direct note and child-folder metadata.",
    )
    notes_folder_items.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_folder_items.add_argument("--handle", required=True, help="Notes folder handle from folders output.")
    notes_folder_items.add_argument("--limit", type=int, default=20, help="Maximum direct items, capped at 50.")
    notes_folder_items.add_argument("--db", help=argparse.SUPPRESS)
    notes_folder_items.set_defaults(func=_notes_folder_items_command)

    notes_folder_tree = notes_subparsers.add_parser(
        "folder-tree",
        help="List a bounded recursive Notes child-folder metadata tree by handle.",
    )
    notes_folder_tree.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_folder_tree.add_argument("--handle", required=True, help="Notes folder handle from folders output.")
    notes_folder_tree.add_argument("--depth", type=int, default=2, help="Maximum recursive folder depth, capped at 3.")
    notes_folder_tree.add_argument("--limit", type=int, default=50, help="Maximum descendant folders, capped at 50.")
    notes_folder_tree.add_argument("--db", help=argparse.SUPPRESS)
    notes_folder_tree.set_defaults(func=_notes_folder_tree_command)

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
        help="Get exact local Notes content by opaque handle; --content-format html also returns the bounded rich-text body plus extracted text.",
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
    notes_content.add_argument(
        "--content-format",
        choices=["text", "html"],
        default="text",
        help="Return plain text (default) or the bounded rich-text HTML body plus extracted visible text.",
    )
    notes_content.add_argument("--db", help=argparse.SUPPRESS)
    notes_content.set_defaults(func=_notes_content_command)

    notes_export_content = notes_subparsers.add_parser(
        "export-content",
        help="Export bounded, paged note text for one exact normal folder, date-bounded and confirm-gated (v1.182 operator-approved bulk-content read).",
    )
    notes_export_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_export_content.add_argument(
        "--folder-handle", required=True, help="Notes folder handle from folder metadata output."
    )
    notes_export_content.add_argument(
        "--modified-after",
        required=True,
        help="Required ISO-8601 date bound; only notes modified after this instant are exported.",
    )
    notes_export_content.add_argument(
        "--cursor", type=int, default=0, help="Zero-based page cursor from a prior next_cursor."
    )
    notes_export_content.add_argument(
        "--limit", type=int, default=10, help="Notes per page, capped at 20."
    )
    notes_export_content.add_argument(
        "--max-chars-per-note",
        type=int,
        default=4000,
        help="Maximum content characters per note, capped at 12000.",
    )
    notes_export_content.add_argument(
        "--confirm-bulk",
        action="store_true",
        help="Required acknowledgement that this returns multiple note bodies in one response.",
    )
    notes_export_content.add_argument("--db", help=argparse.SUPPRESS)
    notes_export_content.set_defaults(func=_notes_export_content_command)

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
        help="Preview an approved Notes create, create-html, create-folder, rename-folder, delete-folder, move-folder, append, replace, replace-html, move, or delete operation without writing.",
    )
    notes_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "create",
            "create-html",
            "create_html",
            "create-folder",
            "create_folder",
            "rename-folder",
            "rename_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "replace-html",
            "replace_html",
            "move-to-folder",
            "move_to_folder",
            "delete",
        ],
        help="Notes operation to preview.",
    )
    notes_plan.add_argument("--title", default="", help="New note title for create, folder title for create-folder, or new folder title for rename-folder.")
    notes_plan.add_argument(
        "--handle",
        default="",
        help="Opaque Notes handle from search output for append-text, replace-text, move-to-folder, or note delete.",
    )
    notes_plan.add_argument(
        "--folder-handle",
        default="",
        help="Opaque Notes folder handle from folders output for create, create-folder parent, rename-folder, delete-folder, move-folder source, or move-to-folder target.",
    )
    notes_plan.add_argument(
        "--target-folder-handle",
        default="",
        help="Opaque Notes destination folder handle from folders output for move-folder.",
    )
    notes_plan.add_argument(
        "--body-text",
        default="",
        help="Plain-text body for the new note, append, or replacement, capped at 12000 characters.",
    )
    notes_plan.add_argument(
        "--body-html",
        default="",
        help="Sanitized rich-text HTML body for create-html or replace-html, capped at 24000 characters.",
    )
    notes_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content or folder-title SHA-256 required for append-text, replace-text, replace-html (extracted visible-text SHA-256), rename-folder, delete-folder, move-folder, move-to-folder, or delete.",
    )
    notes_plan.add_argument("--db", help=argparse.SUPPRESS)
    notes_plan.set_defaults(func=_notes_plan_command)

    notes_apply = notes_subparsers.add_parser(
        "apply",
        help="Apply an approved Notes create, create-html, create-folder, rename-folder, delete-folder, move-folder, append, replace, replace-html, move, or delete operation after plan approval.",
    )
    notes_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    notes_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "create",
            "create-html",
            "create_html",
            "create-folder",
            "create_folder",
            "rename-folder",
            "rename_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "replace-html",
            "replace_html",
            "move-to-folder",
            "move_to_folder",
            "delete",
        ],
        help="Notes operation to apply.",
    )
    notes_apply.add_argument("--title", default="", help="New note title for create, folder title for create-folder, or new folder title for rename-folder.")
    notes_apply.add_argument(
        "--handle",
        default="",
        help="Opaque Notes handle from search output for append-text, replace-text, move-to-folder, or note delete.",
    )
    notes_apply.add_argument(
        "--folder-handle",
        default="",
        help="Opaque Notes folder handle from folders output for create, create-folder parent, rename-folder, delete-folder, move-folder source, or move-to-folder target.",
    )
    notes_apply.add_argument(
        "--target-folder-handle",
        default="",
        help="Opaque Notes destination folder handle from folders output for move-folder.",
    )
    notes_apply.add_argument(
        "--body-text",
        default="",
        help="Plain-text body for the new note, append, or replacement, capped at 12000 characters.",
    )
    notes_apply.add_argument(
        "--body-html",
        default="",
        help="Sanitized rich-text HTML body for create-html or replace-html, capped at 24000 characters.",
    )
    notes_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content or folder-title SHA-256 required for append-text, replace-text, replace-html (extracted visible-text SHA-256), rename-folder, delete-folder, move-folder, move-to-folder, or delete.",
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

    icloud_drive_root = icloud_drive_subparsers.add_parser(
        "root",
        help="Get local iCloud Drive root metadata and opaque folder handle.",
    )
    icloud_drive_root.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_root.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_root.set_defaults(func=_icloud_drive_root_command)

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

    icloud_drive_list = icloud_drive_subparsers.add_parser(
        "list",
        help="List direct children of one exact iCloud Drive folder by handle.",
    )
    icloud_drive_list.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_list.add_argument(
        "--handle",
        required=True,
        help="iCloud Drive directory handle from search output.",
    )
    icloud_drive_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum direct children, capped at 50.",
    )
    icloud_drive_list.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_list.set_defaults(func=_icloud_drive_list_command)

    icloud_drive_tree = icloud_drive_subparsers.add_parser(
        "tree",
        help="List a bounded recursive metadata tree for one exact iCloud Drive folder by handle.",
    )
    icloud_drive_tree.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_tree.add_argument(
        "--handle",
        required=True,
        help="iCloud Drive directory handle from search output.",
    )
    icloud_drive_tree.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum recursive folder depth, capped at 3.",
    )
    icloud_drive_tree.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum descendants, capped at 100.",
    )
    icloud_drive_tree.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_tree.set_defaults(func=_icloud_drive_tree_command)

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

    icloud_drive_export = icloud_drive_subparsers.add_parser(
        "export",
        help="Export one exact local iCloud Drive file by opaque handle.",
    )
    icloud_drive_export.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_export.add_argument(
        "--handle",
        required=True,
        help="iCloud Drive file handle from search output.",
    )
    icloud_drive_export.add_argument(
        "--output-dir",
        required=True,
        help="Directory outside iCloud Drive where the selected file will be copied.",
    )
    icloud_drive_export.add_argument(
        "--filename",
        default="",
        help="Optional export filename. The adapter sanitizes the final filename.",
    )
    icloud_drive_export.add_argument(
        "--max-bytes",
        type=int,
        default=250 * 1024 * 1024,
        help="Maximum file bytes to export, capped at 250 MiB.",
    )
    icloud_drive_export.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_export.set_defaults(func=_icloud_drive_export_command)

    icloud_drive_plan = icloud_drive_subparsers.add_parser(
        "plan",
        help="Plan a future iCloud Drive folder, text-file, or regular-file change without applying it.",
    )
    icloud_drive_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-text",
            "create_text",
            "create-folder",
            "create_folder",
            "create-folder-path",
            "create_folder_path",
            "rename-folder",
            "rename_folder",
            "trash-folder",
            "trash_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "copy-folder",
            "copy_folder",
            "import-file",
            "import_file",
            "replace-file",
            "replace_file",
            "trash-file",
            "delete-file",
            "delete_file",
            "trash_file",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "trash-text",
            "trash_text",
            "delete-text",
            "delete_text",
            "rename-text",
            "rename_text",
            "copy-text",
            "copy_text",
            "move-text",
            "move_text",
            "rename-file",
            "rename_file",
            "copy-file",
            "copy_file",
            "move-file",
            "move_file",
        ],
        help="Future iCloud Drive operation to plan. No mutation is applied.",
    )
    icloud_drive_plan.add_argument(
        "--parent-handle",
        default="",
        help="Opaque iCloud Drive directory handle from search output for create-text, create-folder, create-folder-path, import-file target, copy-text/copy-file target, move-folder/copy-folder target, or move-text/move-file target.",
    )
    icloud_drive_plan.add_argument(
        "--handle",
        default="",
        help="Opaque iCloud Drive file or directory handle from search output for append-text, replace-text, trash-text, delete-text, trash-folder, delete-folder, rename-text, rename-folder, move-folder, copy-folder, copy-text, move-text, replace-file, rename-file, copy-file, move-file, trash-file, or delete-file.",
    )
    icloud_drive_plan.add_argument(
        "--filename",
        default="",
        help="New text/regular filename or folder name for create, rename, copy, folder rename, or optional move rename.",
    )
    icloud_drive_plan.add_argument(
        "--folder-name",
        default="",
        help="Folder name alias for create-folder, rename-folder, move-folder, or copy-folder. Cannot conflict with --filename.",
    )
    icloud_drive_plan.add_argument(
        "--folder-component",
        action="append",
        dest="folder_components",
        default=None,
        help="Repeat for each bounded create-folder-path component under the exact parent handle.",
    )
    icloud_drive_plan.add_argument(
        "--content-text",
        default="",
        help="Text content for the new file, append, or replacement, capped at 12000 characters. Rejected for trash/delete/rename-folder/rename/copy/move operations.",
    )
    icloud_drive_plan.add_argument(
        "--source-file",
        default="",
        help="Caller-selected local regular file for import-file or replace-file. The output does not echo the path.",
    )
    icloud_drive_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 for exact text-file operations, directory metadata SHA-256 for exact existing-folder operations, or regular-file metadata SHA-256 for rename-file/copy-file/move-file/replace-file/trash-file/delete-file.",
    )
    icloud_drive_plan.add_argument("--root", help=argparse.SUPPRESS)
    icloud_drive_plan.set_defaults(func=_icloud_drive_plan_command)

    icloud_drive_apply = icloud_drive_subparsers.add_parser(
        "apply",
        help="Apply an approved iCloud Drive folder, text-file, or regular-file change and read back proof.",
    )
    icloud_drive_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    icloud_drive_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-text",
            "create_text",
            "create-folder",
            "create_folder",
            "create-folder-path",
            "create_folder_path",
            "rename-folder",
            "rename_folder",
            "trash-folder",
            "trash_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "copy-folder",
            "copy_folder",
            "import-file",
            "import_file",
            "replace-file",
            "replace_file",
            "trash-file",
            "delete-file",
            "delete_file",
            "trash_file",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "trash-text",
            "trash_text",
            "delete-text",
            "delete_text",
            "rename-text",
            "rename_text",
            "copy-text",
            "copy_text",
            "move-text",
            "move_text",
            "rename-file",
            "rename_file",
            "copy-file",
            "copy_file",
            "move-file",
            "move_file",
        ],
        help="Approved iCloud Drive operation to apply.",
    )
    icloud_drive_apply.add_argument(
        "--parent-handle",
        default="",
        help="Opaque iCloud Drive directory handle from search output for create-text, create-folder, create-folder-path, import-file target, copy-text/copy-file target, move-folder/copy-folder target, or move-text/move-file target.",
    )
    icloud_drive_apply.add_argument(
        "--handle",
        default="",
        help="Opaque iCloud Drive file or directory handle from search output for append-text, replace-text, trash-text, delete-text, trash-folder, delete-folder, rename-text, rename-folder, move-folder, copy-folder, copy-text, move-text, replace-file, rename-file, copy-file, move-file, trash-file, or delete-file.",
    )
    icloud_drive_apply.add_argument(
        "--filename",
        default="",
        help="New text/regular filename or folder name for create, rename, copy, folder rename, or optional move rename.",
    )
    icloud_drive_apply.add_argument(
        "--folder-name",
        default="",
        help="Folder name alias for create-folder, rename-folder, move-folder, or copy-folder. Cannot conflict with --filename.",
    )
    icloud_drive_apply.add_argument(
        "--folder-component",
        action="append",
        dest="folder_components",
        default=None,
        help="Repeat for each bounded create-folder-path component under the exact parent handle.",
    )
    icloud_drive_apply.add_argument(
        "--content-text",
        default="",
        help="Text content for the new file, append, or replacement, capped at 12000 characters. Rejected for trash/delete/rename-folder/rename/copy/move operations.",
    )
    icloud_drive_apply.add_argument(
        "--source-file",
        default="",
        help="Caller-selected local regular file for import-file or replace-file. The output does not echo the path.",
    )
    icloud_drive_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 for exact text-file operations, directory metadata SHA-256 for exact existing-folder operations, or regular-file metadata SHA-256 for rename-file/copy-file/move-file/replace-file/trash-file/delete-file.",
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

    filesystem = subparsers.add_parser(
        "filesystem",
        help="Home-directory filesystem local metadata and exact content commands.",
    )
    filesystem_subparsers = filesystem.add_subparsers(
        dest="filesystem_command",
        required=True,
    )

    filesystem_search = filesystem_subparsers.add_parser(
        "search",
        help="Search local home-directory filesystem metadata by filename.",
    )
    filesystem_search.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_search.add_argument("--query", required=True, help="Filename query text.")
    filesystem_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    filesystem_search.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_search.set_defaults(func=_filesystem_search_command)

    filesystem_root = filesystem_subparsers.add_parser(
        "root",
        help="Get local home-directory filesystem root metadata and opaque folder handle.",
    )
    filesystem_root.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_root.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_root.set_defaults(func=_filesystem_root_command)

    filesystem_get = filesystem_subparsers.add_parser(
        "get",
        help="Get exact home-directory filesystem metadata by handle.",
    )
    filesystem_get.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_get.add_argument(
        "--handle",
        required=True,
        help="Filesystem handle from search output.",
    )
    filesystem_get.add_argument(
        "--metadata-only",
        action="store_true",
        help="Accepted for clarity; use the content command for file text retrieval.",
    )
    filesystem_get.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_get.set_defaults(func=_filesystem_get_command)

    filesystem_list = filesystem_subparsers.add_parser(
        "list",
        help="List direct children of one exact home-directory folder by handle.",
    )
    filesystem_list.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_list.add_argument(
        "--handle",
        required=True,
        help="Filesystem directory handle from search output.",
    )
    filesystem_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum direct children, capped at 50.",
    )
    filesystem_list.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_list.set_defaults(func=_filesystem_list_command)

    filesystem_tree = filesystem_subparsers.add_parser(
        "tree",
        help="List a bounded recursive metadata tree for one exact home-directory folder by handle.",
    )
    filesystem_tree.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_tree.add_argument(
        "--handle",
        required=True,
        help="Filesystem directory handle from search output.",
    )
    filesystem_tree.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum recursive folder depth, capped at 3.",
    )
    filesystem_tree.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum descendants, capped at 100.",
    )
    filesystem_tree.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_tree.set_defaults(func=_filesystem_tree_command)

    filesystem_content = filesystem_subparsers.add_parser(
        "content",
        help="Get exact local home-directory text content by opaque handle.",
    )
    filesystem_content.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_content.add_argument(
        "--handle",
        required=True,
        help="Filesystem handle from search output.",
    )
    filesystem_content.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum content characters to return, capped at 12000.",
    )
    filesystem_content.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_content.set_defaults(func=_filesystem_content_command)

    filesystem_export = filesystem_subparsers.add_parser(
        "export",
        help="Export one exact local home-directory file by opaque handle.",
    )
    filesystem_export.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_export.add_argument(
        "--handle",
        required=True,
        help="Filesystem file handle from search output.",
    )
    filesystem_export.add_argument(
        "--output-dir",
        required=True,
        help="Directory outside the home root where the selected file will be copied.",
    )
    filesystem_export.add_argument(
        "--filename",
        default="",
        help="Optional export filename. The adapter sanitizes the final filename.",
    )
    filesystem_export.add_argument(
        "--max-bytes",
        type=int,
        default=250 * 1024 * 1024,
        help="Maximum file bytes to export, capped at 250 MiB.",
    )
    filesystem_export.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_export.set_defaults(func=_filesystem_export_command)

    filesystem_plan = filesystem_subparsers.add_parser(
        "plan",
        help="Plan a future home-directory folder, text-file, or regular-file change without applying it.",
    )
    filesystem_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-text",
            "create_text",
            "create-folder",
            "create_folder",
            "create-folder-path",
            "create_folder_path",
            "rename-folder",
            "rename_folder",
            "trash-folder",
            "trash_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "copy-folder",
            "copy_folder",
            "import-file",
            "import_file",
            "replace-file",
            "replace_file",
            "trash-file",
            "delete-file",
            "delete_file",
            "trash_file",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "trash-text",
            "trash_text",
            "delete-text",
            "delete_text",
            "rename-text",
            "rename_text",
            "copy-text",
            "copy_text",
            "move-text",
            "move_text",
            "rename-file",
            "rename_file",
            "copy-file",
            "copy_file",
            "move-file",
            "move_file",
        ],
        help="Future home-directory filesystem operation to plan. No mutation is applied.",
    )
    filesystem_plan.add_argument(
        "--parent-handle",
        default="",
        help="Opaque filesystem directory handle from search output for create-text, create-folder, create-folder-path, import-file target, copy-text/copy-file target, move-folder/copy-folder target, or move-text/move-file target.",
    )
    filesystem_plan.add_argument(
        "--handle",
        default="",
        help="Opaque filesystem file or directory handle from search output for append-text, replace-text, trash-text, delete-text, trash-folder, delete-folder, rename-text, rename-folder, move-folder, copy-folder, copy-text, move-text, replace-file, rename-file, copy-file, move-file, trash-file, or delete-file.",
    )
    filesystem_plan.add_argument(
        "--filename",
        default="",
        help="New text/regular filename or folder name for create, rename, copy, folder rename, or optional move rename.",
    )
    filesystem_plan.add_argument(
        "--folder-name",
        default="",
        help="Folder name alias for create-folder, rename-folder, move-folder, or copy-folder. Cannot conflict with --filename.",
    )
    filesystem_plan.add_argument(
        "--folder-component",
        action="append",
        dest="folder_components",
        default=None,
        help="Repeat for each bounded create-folder-path component under the exact parent handle.",
    )
    filesystem_plan.add_argument(
        "--content-text",
        default="",
        help="Text content for the new file, append, or replacement, capped at 12000 characters. Rejected for trash/delete/rename-folder/rename/copy/move operations.",
    )
    filesystem_plan.add_argument(
        "--source-file",
        default="",
        help="Caller-selected local regular file for import-file or replace-file. The output does not echo the path.",
    )
    filesystem_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 for exact text-file operations, directory metadata SHA-256 for exact existing-folder operations, or regular-file metadata SHA-256 for rename-file/copy-file/move-file/replace-file/trash-file/delete-file.",
    )
    filesystem_plan.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_plan.set_defaults(func=_filesystem_plan_command)

    filesystem_apply = filesystem_subparsers.add_parser(
        "apply",
        help="Apply an approved home-directory folder, text-file, or regular-file change and read back proof.",
    )
    filesystem_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    filesystem_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-text",
            "create_text",
            "create-folder",
            "create_folder",
            "create-folder-path",
            "create_folder_path",
            "rename-folder",
            "rename_folder",
            "trash-folder",
            "trash_folder",
            "delete-folder",
            "delete_folder",
            "move-folder",
            "move_folder",
            "copy-folder",
            "copy_folder",
            "import-file",
            "import_file",
            "replace-file",
            "replace_file",
            "trash-file",
            "delete-file",
            "delete_file",
            "trash_file",
            "append-text",
            "append_text",
            "replace-text",
            "replace_text",
            "trash-text",
            "trash_text",
            "delete-text",
            "delete_text",
            "rename-text",
            "rename_text",
            "copy-text",
            "copy_text",
            "move-text",
            "move_text",
            "rename-file",
            "rename_file",
            "copy-file",
            "copy_file",
            "move-file",
            "move_file",
        ],
        help="Approved home-directory filesystem operation to apply.",
    )
    filesystem_apply.add_argument(
        "--parent-handle",
        default="",
        help="Opaque filesystem directory handle from search output for create-text, create-folder, create-folder-path, import-file target, copy-text/copy-file target, move-folder/copy-folder target, or move-text/move-file target.",
    )
    filesystem_apply.add_argument(
        "--handle",
        default="",
        help="Opaque filesystem file or directory handle from search output for append-text, replace-text, trash-text, delete-text, trash-folder, delete-folder, rename-text, rename-folder, move-folder, copy-folder, copy-text, move-text, replace-file, rename-file, copy-file, move-file, trash-file, or delete-file.",
    )
    filesystem_apply.add_argument(
        "--filename",
        default="",
        help="New text/regular filename or folder name for create, rename, copy, folder rename, or optional move rename.",
    )
    filesystem_apply.add_argument(
        "--folder-name",
        default="",
        help="Folder name alias for create-folder, rename-folder, move-folder, or copy-folder. Cannot conflict with --filename.",
    )
    filesystem_apply.add_argument(
        "--folder-component",
        action="append",
        dest="folder_components",
        default=None,
        help="Repeat for each bounded create-folder-path component under the exact parent handle.",
    )
    filesystem_apply.add_argument(
        "--content-text",
        default="",
        help="Text content for the new file, append, or replacement, capped at 12000 characters. Rejected for trash/delete/rename-folder/rename/copy/move operations.",
    )
    filesystem_apply.add_argument(
        "--source-file",
        default="",
        help="Caller-selected local regular file for import-file or replace-file. The output does not echo the path.",
    )
    filesystem_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current normalized content SHA-256 for exact text-file operations, directory metadata SHA-256 for exact existing-folder operations, or regular-file metadata SHA-256 for rename-file/copy-file/move-file/replace-file/trash-file/delete-file.",
    )
    filesystem_apply.add_argument(
        "--approval-token",
        required=True,
        help="Approval token bound to the matching plan fingerprint.",
    )
    filesystem_apply.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    filesystem_apply.add_argument("--root", help=argparse.SUPPRESS)
    filesystem_apply.set_defaults(func=_filesystem_apply_command)

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

    calendar_participants = calendar_subparsers.add_parser(
        "participants",
        help="List exact Calendar event participant metadata by event handle.",
    )
    calendar_participants.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_participants.add_argument(
        "--handle",
        required=True,
        help="Calendar event handle from search output.",
    )
    calendar_participants.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum participants, capped at 50.",
    )
    calendar_participants.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Past handle-resolution window in days, capped at 3650.",
    )
    calendar_participants.add_argument(
        "--days-forward",
        type=int,
        default=730,
        help="Future handle-resolution window in days, capped at 3650.",
    )
    calendar_participants.set_defaults(func=_calendar_participants_command)

    calendar_participant = calendar_subparsers.add_parser(
        "participant",
        help="Get exact Calendar participant detail by event and participant handles.",
    )
    calendar_participant.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_participant.add_argument(
        "--event-handle",
        required=True,
        help="Calendar event handle from search output.",
    )
    calendar_participant.add_argument(
        "--participant-handle",
        required=True,
        help="Calendar participant handle from participants output.",
    )
    calendar_participant.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Past handle-resolution window in days, capped at 3650.",
    )
    calendar_participant.add_argument(
        "--days-forward",
        type=int,
        default=730,
        help="Future handle-resolution window in days, capped at 3650.",
    )
    calendar_participant.set_defaults(func=_calendar_participant_command)

    calendar_calendars = calendar_subparsers.add_parser(
        "calendars",
        help="Search Calendar target calendars by title or include the default target.",
    )
    calendar_calendars.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_calendars.add_argument(
        "--query",
        default="",
        help="Calendar title query text. Required unless --include-default is set.",
    )
    calendar_calendars.add_argument(
        "--include-default",
        action="store_true",
        help="Include the current default event calendar metadata.",
    )
    calendar_calendars.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    calendar_calendars.set_defaults(func=_calendar_calendars_command)

    calendar_calendar = calendar_subparsers.add_parser(
        "calendar",
        help="Get exact Calendar target metadata by handle.",
    )
    calendar_calendar.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_calendar.add_argument(
        "--handle",
        required=True,
        help="Calendar target handle from calendars output.",
    )
    calendar_calendar.set_defaults(func=_calendar_calendar_command)

    calendar_events = calendar_subparsers.add_parser(
        "events",
        help="List selected Calendar target event metadata in an explicit date window.",
    )
    calendar_events.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_events.add_argument(
        "--handle",
        required=True,
        help="Calendar target handle from calendars output.",
    )
    calendar_events.add_argument(
        "--start",
        required=True,
        help="Window start as YYYY-MM-DD or ISO 8601 timestamp with timezone.",
    )
    calendar_events.add_argument(
        "--end",
        required=True,
        help="Window end as YYYY-MM-DD or ISO 8601 timestamp with timezone.",
    )
    calendar_events.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum events, capped at 50.",
    )
    calendar_events.set_defaults(func=_calendar_events_command)

    calendar_request_access = calendar_subparsers.add_parser(
        "request-access",
        help="Prompt once for full Calendar access through the EventKit helper.",
    )
    calendar_request_access.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_request_access.set_defaults(func=_calendar_request_access_command)

    calendar_plan = calendar_subparsers.add_parser(
        "plan",
        help="Plan a future Calendar event create/update/delete without applying it.",
    )
    calendar_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_plan.add_argument(
        "--operation",
        required=True,
        choices=["create", "update", "delete"],
        help="Future Calendar operation to plan. No mutation is applied.",
    )
    calendar_plan.add_argument(
        "--title",
        default="",
        help="New or updated event title. Required for create/update.",
    )
    calendar_plan.add_argument(
        "--calendar-title",
        default="",
        help="Exact target calendar title. Required for create unless --calendar-handle is set.",
    )
    calendar_plan.add_argument(
        "--calendar-handle",
        default="",
        help="Exact target calendar handle from calendars output. Create only.",
    )
    calendar_plan.add_argument(
        "--use-default-calendar",
        action="store_true",
        help="Resolve the current default event calendar during planning and bind its exact handle. Create only.",
    )
    calendar_plan.add_argument(
        "--target-calendar-handle",
        default="",
        help="Exact target calendar handle from calendars output for update/move.",
    )
    calendar_plan.add_argument(
        "--start-date",
        default="",
        help="Event start as YYYY-MM-DD date or ISO 8601 timestamp with timezone.",
    )
    calendar_plan.add_argument(
        "--end-date",
        default="",
        help="Event end as YYYY-MM-DD date or ISO 8601 timestamp with timezone.",
    )
    calendar_plan.add_argument(
        "--time-zone",
        default="",
        help="Optional IANA time zone for a timed event, e.g. America/Los_Angeles.",
    )
    calendar_plan.add_argument(
        "--all-day",
        action="store_true",
        help="Plan an all-day Calendar event. Date-only start/end values also infer all-day.",
    )
    calendar_plan.add_argument(
        "--availability",
        choices=["busy", "free", "tentative", "unavailable"],
        default="",
        help="Optional event availability to set: busy, free, tentative, or unavailable.",
    )
    calendar_plan.add_argument(
        "--alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        default=None,
        help="Comma-separated integer alarm offsets in minutes, e.g. -10,0.",
    )
    calendar_plan.add_argument(
        "--alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        default=None,
        help="Comma-separated absolute alarm ISO 8601 timestamps with timezones.",
    )
    calendar_plan.add_argument(
        "--alarm-sound-name",
        default="",
        help="Optional bare system sound name for audio alarms, e.g. Glass. Requires alarm offsets or absolute dates.",
    )
    calendar_plan.add_argument(
        "--alarm-email-address",
        default="",
        help="Optional email address for email alarms. Requires alarm offsets or absolute dates; output returns only SHA-256 proof.",
    )
    calendar_plan.add_argument(
        "--alarm-proximity",
        choices=["enter", "leave"],
        default="",
        help="Optional geofence alarm trigger: enter or leave. Requires --alarm-structured-location.",
    )
    calendar_plan.add_argument(
        "--alarm-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Optional geofence alarm structured location JSON. Requires --alarm-proximity.",
    )
    calendar_plan.add_argument(
        "--recurrence-frequency",
        choices=["daily", "weekly", "monthly", "yearly"],
        default="",
        help="Optional simple recurrence frequency for create or add-to-non-recurring-event update.",
    )
    calendar_plan.add_argument(
        "--recurrence-interval",
        type=int,
        default=None,
        help="Optional recurrence interval, 1 to 4, for create or add-to-non-recurring-event update.",
    )
    calendar_plan.add_argument(
        "--recurrence-count",
        type=int,
        default=None,
        help="Occurrence count, 2 to 52, for create or add-to-non-recurring-event update. Required unless --recurrence-end-date or --recurrence-unbounded is supplied.",
    )
    calendar_plan.add_argument(
        "--recurrence-end-date",
        default="",
        help="Finite recurrence end timestamp with timezone for create or add-to-non-recurring-event update. Mutually exclusive with --recurrence-count and --recurrence-unbounded.",
    )
    calendar_plan.add_argument(
        "--recurrence-unbounded",
        action="store_true",
        help="Explicitly request an unbounded recurrence. Mutually exclusive with --recurrence-count and --recurrence-end-date.",
    )
    calendar_plan.add_argument(
        "--recurrence-weekdays",
        type=_calendar_recurrence_weekdays_arg,
        default=None,
        help="Optional comma-separated weekdays for weekly, monthly, or yearly week-of-year recurrence, e.g. monday,wednesday,friday.",
    )
    calendar_plan.add_argument(
        "--recurrence-month-days",
        type=_calendar_recurrence_month_days_arg,
        default=None,
        help="Optional comma-separated month days for monthly recurrence, e.g. 1,15,-1.",
    )
    calendar_plan.add_argument(
        "--recurrence-month-weekdays",
        type=_calendar_recurrence_month_weekdays_arg,
        default=None,
        help="Optional comma-separated weekday:week_number values for monthly recurrence, e.g. tuesday:3,friday:-1.",
    )
    calendar_plan.add_argument(
        "--recurrence-year-months",
        type=_calendar_recurrence_year_months_arg,
        default=None,
        help="Optional comma-separated months for yearly recurrence, e.g. 1,7,12.",
    )
    calendar_plan.add_argument(
        "--recurrence-year-month-days",
        type=_calendar_recurrence_year_month_days_arg,
        default=None,
        help="Optional comma-separated day-of-month values for yearly month recurrence, e.g. 1,15,-1. Requires --recurrence-year-months.",
    )
    calendar_plan.add_argument(
        "--recurrence-year-month-weekdays",
        type=_calendar_recurrence_year_month_weekdays_arg,
        default=None,
        help="Optional comma-separated weekday:week_number values for yearly month recurrence, e.g. monday:2,friday:-1. Requires --recurrence-year-months.",
    )
    calendar_plan.add_argument(
        "--recurrence-year-days",
        type=_calendar_recurrence_year_days_arg,
        default=None,
        help="Optional comma-separated day-of-year values for yearly recurrence, e.g. 1,100,-1.",
    )
    calendar_plan.add_argument(
        "--recurrence-year-weeks",
        type=_calendar_recurrence_year_weeks_arg,
        default=None,
        help="Optional comma-separated week-of-year values for yearly recurrence, e.g. 1,26,-1. Requires --recurrence-weekdays.",
    )
    calendar_plan.add_argument(
        "--recurrence-set-positions",
        type=_calendar_recurrence_set_positions_arg,
        default=None,
        help="Optional comma-separated BYSETPOS values, -366 through -1 or 1 through 366. Requires another recurrence selector.",
    )
    calendar_plan.add_argument(
        "--recurrence-delete-scope",
        choices=["this-event", "future-events", "all-events"],
        default="",
        help="Delete a selected recurring event occurrence scope. Delete only.",
    )
    calendar_plan.add_argument(
        "--recurrence-update-scope",
        choices=["this-event", "future-events"],
        default="",
        help="Recurring update scope. Use this-event for selected occurrence edits; use future-events with --clear-recurrence or approved replacement recurrence fields.",
    )
    calendar_plan.add_argument(
        "--clear-recurrence",
        action="store_true",
        help="Clear a simple bounded recurrence from a first selected occurrence during update.",
    )
    calendar_plan.add_argument("--location", default="", help="Optional event location.")
    calendar_plan.add_argument(
        "--structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help='Optional JSON structured location, e.g. {"title":"Room","latitude":37.0,"longitude":-122.0,"radius_meters":25}.',
    )
    calendar_plan.add_argument(
        "--clear-structured-location",
        action="store_true",
        help="Clear an existing structured location during update after exact expected structured-location binding.",
    )
    calendar_plan.add_argument("--notes", default="", help="Optional event notes.")
    calendar_plan.add_argument(
        "--event-url",
        default="",
        help="Optional allow-listed event URL/meeting link to set for create or update.",
    )
    calendar_plan.add_argument(
        "--clear-event-url",
        action="store_true",
        help="Clear an existing event URL during update after exact expected URL hash binding.",
    )
    calendar_plan.add_argument(
        "--handle",
        default="",
        help="Exact event handle. Required for update/delete.",
    )
    calendar_plan.add_argument(
        "--expected-title",
        default="",
        help="Expected current event title. Required for update/delete.",
    )
    calendar_plan.add_argument(
        "--expected-calendar-title",
        default="",
        help="Expected current calendar title. Required for update/delete.",
    )
    calendar_plan.add_argument(
        "--expected-start-date",
        default="",
        help="Expected current start date or timestamp. Required for update/delete.",
    )
    calendar_plan.add_argument(
        "--expected-end-date",
        default="",
        help="Expected current end date or timestamp. Required for update/delete.",
    )
    calendar_plan.add_argument(
        "--expected-time-zone",
        default="",
        help="Expected current IANA time zone for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-all-day",
        action="store_true",
        help="Expected current all-day flag for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-availability",
        choices=["busy", "free", "tentative", "unavailable", "not_supported", "not-supported"],
        default="",
        help="Expected current availability for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        default=None,
        help="Expected comma-separated current alarm offsets in minutes for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        default=None,
        help="Expected comma-separated current absolute alarm timestamps for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-sound-name",
        default="",
        help="Expected current bare system sound name for audio-alarm drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-email-address-sha256",
        default="",
        help="Expected current email alarm address SHA-256 for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-proximity",
        choices=["enter", "leave"],
        default="",
        help="Expected current geofence alarm trigger for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-alarm-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Expected current geofence alarm structured location JSON for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-event-url-present",
        action="store_true",
        help="Expected current event URL presence for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-event-url-sha256",
        default="",
        help="Expected current event URL SHA-256 from exact event detail when URL is present.",
    )
    calendar_plan.add_argument(
        "--expected-location",
        default="",
        help="Expected current event location for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Expected current structured location JSON for update/delete drift checks.",
    )
    calendar_plan.add_argument(
        "--expected-notes",
        default="",
        help="Expected current event notes for update/delete drift checks.",
    )
    calendar_plan.set_defaults(func=_calendar_plan_command)

    calendar_apply = calendar_subparsers.add_parser(
        "apply",
        help="Apply an approved Calendar event create/update/delete.",
    )
    calendar_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_apply.add_argument(
        "--operation",
        required=True,
        choices=["create", "update", "delete"],
        help="Approved Calendar operation to apply.",
    )
    calendar_apply.add_argument(
        "--title",
        default="",
        help="New or updated event title. Required for create/update.",
    )
    calendar_apply.add_argument(
        "--calendar-title",
        default="",
        help="Exact target calendar title. Required for create unless --calendar-handle is set.",
    )
    calendar_apply.add_argument(
        "--calendar-handle",
        default="",
        help="Exact target calendar handle from calendars output. Create only.",
    )
    calendar_apply.add_argument(
        "--target-calendar-handle",
        default="",
        help="Exact target calendar handle from calendars output for update/move.",
    )
    calendar_apply.add_argument(
        "--start-date",
        default="",
        help="Event start as YYYY-MM-DD date or ISO 8601 timestamp with timezone.",
    )
    calendar_apply.add_argument(
        "--end-date",
        default="",
        help="Event end as YYYY-MM-DD date or ISO 8601 timestamp with timezone.",
    )
    calendar_apply.add_argument(
        "--time-zone",
        default="",
        help="Optional IANA time zone for a timed event. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--all-day",
        action="store_true",
        help="Apply an all-day Calendar event change. Date-only start/end values also infer all-day.",
    )
    calendar_apply.add_argument(
        "--availability",
        choices=["busy", "free", "tentative", "unavailable"],
        default="",
        help="Optional event availability to set. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        default=None,
        help="Comma-separated integer alarm offsets in minutes. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        default=None,
        help="Comma-separated absolute alarm ISO 8601 timestamps. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--alarm-sound-name",
        default="",
        help="Optional bare system sound name for audio alarms. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--alarm-email-address",
        default="",
        help="Optional email address for email alarms. Must match the approved plan; output returns only SHA-256 proof.",
    )
    calendar_apply.add_argument(
        "--alarm-proximity",
        choices=["enter", "leave"],
        default="",
        help="Optional geofence alarm trigger. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--alarm-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Optional geofence alarm structured location JSON. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-frequency",
        choices=["daily", "weekly", "monthly", "yearly"],
        default="",
        help="Optional simple recurrence frequency for create or add-to-non-recurring-event update. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-interval",
        type=int,
        default=None,
        help="Optional recurrence interval, 1 to 4, for create or add-to-non-recurring-event update. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-count",
        type=int,
        default=None,
        help="Occurrence count, 2 to 52, for create or add-to-non-recurring-event update. Required unless --recurrence-end-date or --recurrence-unbounded is supplied. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-end-date",
        default="",
        help="Finite recurrence end timestamp with timezone for create or add-to-non-recurring-event update. Mutually exclusive with --recurrence-count and --recurrence-unbounded. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-unbounded",
        action="store_true",
        help="Explicitly apply an approved unbounded recurrence. Mutually exclusive with --recurrence-count and --recurrence-end-date. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-weekdays",
        type=_calendar_recurrence_weekdays_arg,
        default=None,
        help="Optional comma-separated weekdays for weekly, monthly, or yearly week-of-year recurrence. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-month-days",
        type=_calendar_recurrence_month_days_arg,
        default=None,
        help="Optional comma-separated month days for monthly recurrence. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-month-weekdays",
        type=_calendar_recurrence_month_weekdays_arg,
        default=None,
        help="Optional comma-separated weekday:week_number values for monthly recurrence. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-year-months",
        type=_calendar_recurrence_year_months_arg,
        default=None,
        help="Optional comma-separated months for yearly recurrence. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-year-month-days",
        type=_calendar_recurrence_year_month_days_arg,
        default=None,
        help="Optional comma-separated day-of-month values for yearly month recurrence. Requires --recurrence-year-months and must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-year-month-weekdays",
        type=_calendar_recurrence_year_month_weekdays_arg,
        default=None,
        help="Optional comma-separated weekday:week_number values for yearly month recurrence. Requires --recurrence-year-months and must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-year-days",
        type=_calendar_recurrence_year_days_arg,
        default=None,
        help="Optional comma-separated day-of-year values for yearly recurrence. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-year-weeks",
        type=_calendar_recurrence_year_weeks_arg,
        default=None,
        help="Optional comma-separated week-of-year values for yearly recurrence. Requires --recurrence-weekdays and must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-set-positions",
        type=_calendar_recurrence_set_positions_arg,
        default=None,
        help="Optional comma-separated BYSETPOS values. Requires another recurrence selector and must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-delete-scope",
        choices=["this-event", "future-events", "all-events"],
        default="",
        help="Delete a selected recurring event occurrence scope. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--recurrence-update-scope",
        choices=["this-event", "future-events"],
        default="",
        help="Recurring update scope. Use this-event for selected occurrence edits; use future-events with --clear-recurrence or approved replacement recurrence fields. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--clear-recurrence",
        action="store_true",
        help="Clear a simple bounded recurrence from a first selected occurrence during update. Must match the approved plan.",
    )
    calendar_apply.add_argument("--location", default="", help="Optional event location.")
    calendar_apply.add_argument(
        "--structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Optional structured location JSON. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--clear-structured-location",
        action="store_true",
        help="Clear an existing structured location during update. Must match the approved plan.",
    )
    calendar_apply.add_argument("--notes", default="", help="Optional event notes.")
    calendar_apply.add_argument(
        "--event-url",
        default="",
        help="Optional allow-listed event URL/meeting link. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--clear-event-url",
        action="store_true",
        help="Clear an existing event URL during update. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--handle",
        default="",
        help="Exact event handle. Required for update/delete.",
    )
    calendar_apply.add_argument(
        "--expected-title",
        default="",
        help="Expected current event title. Required for update/delete.",
    )
    calendar_apply.add_argument(
        "--expected-calendar-title",
        default="",
        help="Expected current calendar title. Required for update/delete.",
    )
    calendar_apply.add_argument(
        "--expected-start-date",
        default="",
        help="Expected current start timestamp. Required for update/delete.",
    )
    calendar_apply.add_argument(
        "--expected-end-date",
        default="",
        help="Expected current end timestamp. Required for update/delete.",
    )
    calendar_apply.add_argument(
        "--expected-time-zone",
        default="",
        help="Expected current IANA time zone for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-all-day",
        action="store_true",
        help="Expected current all-day flag for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-availability",
        choices=["busy", "free", "tentative", "unavailable", "not_supported", "not-supported"],
        default="",
        help="Expected current availability for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        default=None,
        help="Expected comma-separated current alarm offsets in minutes for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        default=None,
        help="Expected comma-separated current absolute alarm timestamps for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-sound-name",
        default="",
        help="Expected current bare system sound name for audio-alarm drift checks. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-email-address-sha256",
        default="",
        help="Expected current email alarm address SHA-256 for update/delete drift checks. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-proximity",
        choices=["enter", "leave"],
        default="",
        help="Expected current geofence alarm trigger for update/delete drift checks. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--expected-alarm-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Expected current geofence alarm structured location JSON for update/delete drift checks. Must match the approved plan.",
    )
    calendar_apply.add_argument(
        "--expected-event-url-present",
        action="store_true",
        help="Expected current event URL presence for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-event-url-sha256",
        default="",
        help="Expected current event URL SHA-256 from exact event detail when URL is present.",
    )
    calendar_apply.add_argument(
        "--expected-location",
        default="",
        help="Expected current event location for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-structured-location",
        type=_calendar_structured_location_arg,
        default=None,
        help="Expected current structured location JSON for update/delete drift checks.",
    )
    calendar_apply.add_argument(
        "--expected-notes",
        default="",
        help="Expected current event notes for update/delete drift checks.",
    )
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

    calendar_plan_calendar = calendar_subparsers.add_parser(
        "plan-calendar",
        help="Plan a synthetic LAD-TEST-* Calendar calendar create/rename/delete operation.",
    )
    calendar_plan_calendar.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_plan_calendar.add_argument(
        "--operation",
        required=True,
        choices=(
            "create-calendar",
            "create_calendar",
            "rename-calendar",
            "rename_calendar",
            "delete-calendar",
            "delete_calendar",
        ),
        help="Future Calendar calendar-management operation to plan. No mutation is applied.",
    )
    calendar_plan_calendar.add_argument(
        "--source-calendar-handle",
        default="",
        help="Existing calendar:calendar:v1 handle selecting the source/account for create-calendar.",
    )
    calendar_plan_calendar.add_argument(
        "--calendar-handle",
        default="",
        help="Synthetic calendar:calendar:v1 handle for rename-calendar or delete-calendar.",
    )
    calendar_plan_calendar.add_argument(
        "--calendar-title",
        default="",
        help="Synthetic LAD-TEST-* calendar title for create-calendar.",
    )
    calendar_plan_calendar.add_argument(
        "--new-calendar-title",
        default="",
        help="Synthetic LAD-TEST-* target title for rename-calendar.",
    )
    calendar_plan_calendar.set_defaults(func=_calendar_plan_calendar_command)

    calendar_apply_calendar = calendar_subparsers.add_parser(
        "apply-calendar",
        help="Apply an approved synthetic LAD-TEST-* Calendar calendar operation.",
    )
    calendar_apply_calendar.add_argument("--json", action="store_true", help="Emit JSON output.")
    calendar_apply_calendar.add_argument(
        "--operation",
        required=True,
        choices=(
            "create-calendar",
            "create_calendar",
            "rename-calendar",
            "rename_calendar",
            "delete-calendar",
            "delete_calendar",
        ),
        help="Approved Calendar calendar-management operation to apply.",
    )
    calendar_apply_calendar.add_argument(
        "--source-calendar-handle",
        default="",
        help="Same source calendar handle used for the approved create-calendar plan.",
    )
    calendar_apply_calendar.add_argument(
        "--calendar-handle",
        default="",
        help="Same synthetic calendar handle used for the approved rename plan.",
    )
    calendar_apply_calendar.add_argument(
        "--calendar-title",
        default="",
        help="Same synthetic calendar title used for the approved create-calendar plan.",
    )
    calendar_apply_calendar.add_argument(
        "--new-calendar-title",
        default="",
        help="Same synthetic target title used for the approved rename-calendar plan.",
    )
    calendar_apply_calendar.add_argument(
        "--approval-token",
        required=True,
        help="calendar-apply:v1 token from the matching plan-calendar response.",
    )
    calendar_apply_calendar.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    calendar_apply_calendar.set_defaults(func=_calendar_apply_calendar_command)

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

    contacts_request_access = contacts_subparsers.add_parser(
        "request-access",
        help="Prompt once for Contacts access through Contacts.framework.",
    )
    contacts_request_access.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    contacts_request_access.set_defaults(func=_contacts_request_access_command)

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

    contacts_groups = contacts_subparsers.add_parser(
        "groups",
        help="Search local Contacts groups by name.",
    )
    contacts_groups.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_groups.add_argument("--query", required=True, help="Group name query text.")
    contacts_groups.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    contacts_groups.set_defaults(func=_contacts_groups_command)

    contacts_group = contacts_subparsers.add_parser(
        "group",
        help="Get exact Contacts group metadata by handle.",
    )
    contacts_group.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_group.add_argument(
        "--handle",
        required=True,
        help="Contacts group handle from groups output.",
    )
    contacts_group.set_defaults(func=_contacts_group_command)

    contacts_group_members = contacts_subparsers.add_parser(
        "group-members",
        help="List capped Contact metadata for one exact Contacts group handle.",
    )
    contacts_group_members.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_group_members.add_argument(
        "--handle",
        required=True,
        help="Contacts group handle from groups output.",
    )
    contacts_group_members.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    contacts_group_members.set_defaults(func=_contacts_group_members_command)

    contacts_containers = contacts_subparsers.add_parser(
        "containers",
        help="Search local Contacts containers by name or type.",
    )
    contacts_containers.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_containers.add_argument("--query", required=True, help="Container name or type query text.")
    contacts_containers.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    contacts_containers.set_defaults(func=_contacts_containers_command)

    contacts_container = contacts_subparsers.add_parser(
        "container",
        help="Get exact Contacts container metadata by handle.",
    )
    contacts_container.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_container.add_argument(
        "--handle",
        required=True,
        help="Contacts container handle from containers output.",
    )
    contacts_container.set_defaults(func=_contacts_container_command)

    contacts_container_members = contacts_subparsers.add_parser(
        "container-members",
        help="List capped Contact metadata for one exact Contacts container handle.",
    )
    contacts_container_members.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_container_members.add_argument(
        "--handle",
        required=True,
        help="Contacts container handle from containers output.",
    )
    contacts_container_members.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    contacts_container_members.set_defaults(func=_contacts_container_members_command)

    contacts_count = contacts_subparsers.add_parser(
        "count",
        help="Count local Contacts records without returning contact details.",
    )
    contacts_count.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_count.add_argument(
        "--max-contacts",
        type=int,
        default=50000,
        help="Maximum contacts to count before reporting truncation, capped at 100000.",
    )
    contacts_count.set_defaults(func=_contacts_count_command)

    contacts_export = contacts_subparsers.add_parser(
        "export",
        help="Export a verified local Contacts archive as JSON plus vCard files.",
    )
    contacts_export.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_export.add_argument(
        "--output-dir",
        required=True,
        help="Directory where JSON, vCard, and manifest files will be written.",
    )
    contacts_export.add_argument(
        "--filename-prefix",
        default="contacts",
        help="Safe archive filename prefix.",
    )
    contacts_export.add_argument(
        "--max-contacts",
        type=int,
        default=50000,
        help="Maximum contacts to export before reporting truncation, capped at 100000.",
    )
    contacts_export.set_defaults(func=_contacts_export_command)

    contacts_plan = contacts_subparsers.add_parser(
        "plan",
        help="Plan a future Contacts create, exact update, exact note append, or exact delete without applying it.",
    )
    contacts_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "create",
            "update",
            "append-note",
            "append_note",
            "set-note",
            "set_note",
            "replace-note",
            "replace_note",
            "overwrite-note",
            "overwrite_note",
            "clear-note",
            "clear_note",
            "delete-note",
            "delete_note",
            "merge-note",
            "merge_note",
            "add-group-member",
            "add_group_member",
            "remove-group-member",
            "remove_group_member",
            "create-group",
            "create_group",
            "rename-group",
            "rename_group",
            "delete-group",
            "delete_group",
            "batch",
            "delete",
        ],
        help="Future Contacts operation to plan. No mutation is applied.",
    )
    contacts_plan.add_argument(
        "--handle",
        default="",
        help="Opaque Contacts handle from search output for update/delete.",
    )
    contacts_plan.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current update-safe SHA-256 from contacts get, required for update/delete.",
    )
    contacts_plan.add_argument(
        "--group-handle",
        default="",
        help="Opaque Contacts group handle from contacts groups output for group membership updates.",
    )
    contacts_plan.add_argument(
        "--expected-group-sha256",
        default="",
        help="Current group-safe SHA-256 from contacts group, required for group membership updates.",
    )
    contacts_plan.add_argument(
        "--container-handle",
        default="",
        help="Opaque Contacts container handle from contacts containers output for exact container targeting.",
    )
    contacts_plan.add_argument(
        "--expected-container-sha256",
        default="",
        help="Current container-safe SHA-256 from contacts container, required with --container-handle.",
    )
    contacts_plan.add_argument(
        "--group-name",
        default=None,
        help="Contacts group name for create-group or rename-group.",
    )
    contacts_plan.add_argument(
        "--contact-type",
        choices=["person", "organization"],
        default="person",
        help="Contact type to create.",
    )
    contacts_plan.add_argument("--given-name", default=None, help="Given name for create, or replacement given name for update.")
    contacts_plan.add_argument("--family-name", default=None, help="Family name for create, or replacement family name for update.")
    contacts_plan.add_argument("--organization-name", default=None, help="Organization name for create, or replacement organization for update.")
    contacts_plan.add_argument("--department-name", default=None, help="Department name for create, or replacement department for update.")
    contacts_plan.add_argument("--job-title", default=None, help="Job title for create, or replacement job title for update.")
    contacts_plan.add_argument("--nickname", default=None, help="Nickname for create, or replacement nickname for update.")
    contacts_plan_email_group = contacts_plan.add_mutually_exclusive_group()
    contacts_plan_email_group.add_argument(
        "--email",
        action="append",
        default=None,
        help="Optional labeled email as label=value. Repeatable, capped at 5. For update, replaces the email array.",
    )
    contacts_plan_email_group.add_argument(
        "--clear-emails",
        action="store_true",
        help="For update, replace the selected contact's email array with an empty array.",
    )
    contacts_plan_phone_group = contacts_plan.add_mutually_exclusive_group()
    contacts_plan_phone_group.add_argument(
        "--phone",
        action="append",
        default=None,
        help="Optional labeled phone number as label=value. Repeatable, capped at 5. For update, replaces the phone array.",
    )
    contacts_plan_phone_group.add_argument(
        "--clear-phones",
        action="store_true",
        help="For update, replace the selected contact's phone array with an empty array.",
    )
    contacts_plan_url_group = contacts_plan.add_mutually_exclusive_group()
    contacts_plan_url_group.add_argument(
        "--url",
        action="append",
        default=None,
        help="Optional labeled URL as label=value. Repeatable, capped at 5. For update, replaces the URL array.",
    )
    contacts_plan_url_group.add_argument(
        "--clear-urls",
        action="store_true",
        help="For update, replace the selected contact's URL array with an empty array.",
    )
    contacts_plan.add_argument(
        "--note-text",
        default=None,
        help="Exact note text for append/set/replace/merge note operations.",
    )
    contacts_plan.add_argument(
        "--postal-addresses-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled postal address objects for update. Empty array clears.",
    )
    contacts_plan.add_argument(
        "--birthday-json",
        type=_json_argument,
        default=None,
        help="JSON birthday object with month/day and optional year for update. Empty object clears.",
    )
    contacts_plan.add_argument(
        "--dates-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled date objects for update. Empty array clears.",
    )
    contacts_plan.add_argument(
        "--social-profiles-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled social profile objects for update. Empty array clears.",
    )
    contacts_plan.add_argument(
        "--instant-message-addresses-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled instant-message address objects for update. Empty array clears.",
    )
    contacts_plan.add_argument(
        "--contact-relations-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled contact relation objects for update. Empty array clears.",
    )
    contacts_plan_image_group = contacts_plan.add_mutually_exclusive_group()
    contacts_plan_image_group.add_argument(
        "--image-path",
        default=None,
        help="Local image file to set as the selected contact image; output includes only hash/size metadata.",
    )
    contacts_plan_image_group.add_argument(
        "--clear-image",
        action="store_true",
        help="For update, remove the selected contact image.",
    )
    contacts_plan.add_argument(
        "--batch-items-json",
        type=_json_argument,
        default=None,
        help="JSON array of exact existing-contact operation objects for batch planning.",
    )
    contacts_plan.set_defaults(func=_contacts_plan_command)

    contacts_apply = contacts_subparsers.add_parser(
        "apply",
        help="Apply an approved Contacts create, exact update, exact note append, or exact delete.",
    )
    contacts_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    contacts_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "create",
            "update",
            "append-note",
            "append_note",
            "set-note",
            "set_note",
            "replace-note",
            "replace_note",
            "overwrite-note",
            "overwrite_note",
            "clear-note",
            "clear_note",
            "delete-note",
            "delete_note",
            "merge-note",
            "merge_note",
            "add-group-member",
            "add_group_member",
            "remove-group-member",
            "remove_group_member",
            "create-group",
            "create_group",
            "rename-group",
            "rename_group",
            "delete-group",
            "delete_group",
            "batch",
            "delete",
        ],
        help="Approved Contacts operation to apply.",
    )
    contacts_apply.add_argument(
        "--handle",
        default="",
        help="Opaque Contacts handle from search output for update/delete.",
    )
    contacts_apply.add_argument(
        "--expected-current-sha256",
        default="",
        help="Current update-safe SHA-256 from contacts get, required for update/delete.",
    )
    contacts_apply.add_argument(
        "--group-handle",
        default="",
        help="Opaque Contacts group handle from contacts groups output for group membership updates.",
    )
    contacts_apply.add_argument(
        "--expected-group-sha256",
        default="",
        help="Current group-safe SHA-256 from contacts group, required for group membership updates.",
    )
    contacts_apply.add_argument(
        "--container-handle",
        default="",
        help="Same opaque Contacts container handle used for the approved plan.",
    )
    contacts_apply.add_argument(
        "--expected-container-sha256",
        default="",
        help="Same container-safe SHA-256 used for the approved plan.",
    )
    contacts_apply.add_argument(
        "--group-name",
        default=None,
        help="Same Contacts group name used for the approved group plan.",
    )
    contacts_apply.add_argument(
        "--contact-type",
        choices=["person", "organization"],
        default="person",
        help="Contact type to create.",
    )
    contacts_apply.add_argument("--given-name", default=None, help="Given name for create, or replacement given name for update.")
    contacts_apply.add_argument("--family-name", default=None, help="Family name for create, or replacement family name for update.")
    contacts_apply.add_argument("--organization-name", default=None, help="Organization name for create, or replacement organization for update.")
    contacts_apply.add_argument("--department-name", default=None, help="Department name for create, or replacement department for update.")
    contacts_apply.add_argument("--job-title", default=None, help="Job title for create, or replacement job title for update.")
    contacts_apply.add_argument("--nickname", default=None, help="Nickname for create, or replacement nickname for update.")
    contacts_apply_email_group = contacts_apply.add_mutually_exclusive_group()
    contacts_apply_email_group.add_argument(
        "--email",
        action="append",
        default=None,
        help="Optional labeled email as label=value. Repeatable, capped at 5. For update, replaces the email array.",
    )
    contacts_apply_email_group.add_argument(
        "--clear-emails",
        action="store_true",
        help="For update, replace the selected contact's email array with an empty array.",
    )
    contacts_apply_phone_group = contacts_apply.add_mutually_exclusive_group()
    contacts_apply_phone_group.add_argument(
        "--phone",
        action="append",
        default=None,
        help="Optional labeled phone number as label=value. Repeatable, capped at 5. For update, replaces the phone array.",
    )
    contacts_apply_phone_group.add_argument(
        "--clear-phones",
        action="store_true",
        help="For update, replace the selected contact's phone array with an empty array.",
    )
    contacts_apply_url_group = contacts_apply.add_mutually_exclusive_group()
    contacts_apply_url_group.add_argument(
        "--url",
        action="append",
        default=None,
        help="Optional labeled URL as label=value. Repeatable, capped at 5. For update, replaces the URL array.",
    )
    contacts_apply_url_group.add_argument(
        "--clear-urls",
        action="store_true",
        help="For update, replace the selected contact's URL array with an empty array.",
    )
    contacts_apply.add_argument(
        "--note-text",
        default=None,
        help="Exact note text for append/set/replace/merge note operations.",
    )
    contacts_apply.add_argument(
        "--postal-addresses-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled postal address objects for update. Empty array clears.",
    )
    contacts_apply.add_argument(
        "--birthday-json",
        type=_json_argument,
        default=None,
        help="JSON birthday object with month/day and optional year for update. Empty object clears.",
    )
    contacts_apply.add_argument(
        "--dates-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled date objects for update. Empty array clears.",
    )
    contacts_apply.add_argument(
        "--social-profiles-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled social profile objects for update. Empty array clears.",
    )
    contacts_apply.add_argument(
        "--instant-message-addresses-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled instant-message address objects for update. Empty array clears.",
    )
    contacts_apply.add_argument(
        "--contact-relations-json",
        type=_json_argument,
        default=None,
        help="JSON array of labeled contact relation objects for update. Empty array clears.",
    )
    contacts_apply_image_group = contacts_apply.add_mutually_exclusive_group()
    contacts_apply_image_group.add_argument(
        "--image-path",
        default=None,
        help="Same local image file used for the approved plan.",
    )
    contacts_apply_image_group.add_argument(
        "--clear-image",
        action="store_true",
        help="For update, remove the selected contact image.",
    )
    contacts_apply.add_argument(
        "--batch-items-json",
        type=_json_argument,
        default=None,
        help="Same JSON array of exact operation objects used for the approved batch plan.",
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

    photos_request_access = photos_subparsers.add_parser(
        "request-access",
        help="Prompt once for Photos access through the PhotoKit helper.",
    )
    photos_request_access.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_request_access.set_defaults(func=_photos_request_access_command)

    photos_albums = photos_subparsers.add_parser(
        "albums",
        help="Search Photos regular album metadata by title.",
    )
    photos_albums.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_albums.add_argument("--query", required=True, help="Album title query text.")
    photos_albums.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    photos_albums.add_argument(
        "--max-scan-albums",
        type=int,
        default=5000,
        help="Maximum albums to scan, capped at 10000.",
    )
    photos_albums.set_defaults(func=_photos_albums_command)

    photos_album = photos_subparsers.add_parser(
        "album",
        help="Get exact Photos album metadata by handle.",
    )
    photos_album.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_album.add_argument(
        "--handle",
        required=True,
        help="Photos album handle from albums output.",
    )
    photos_album.add_argument(
        "--max-scan-albums",
        type=int,
        default=5000,
        help="Maximum albums to scan while resolving the handle, capped at 10000.",
    )
    photos_album.set_defaults(func=_photos_album_command)

    photos_album_assets = photos_subparsers.add_parser(
        "album-assets",
        help="List exact Photos regular-album asset metadata by album handle.",
    )
    photos_album_assets.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_album_assets.add_argument(
        "--handle",
        required=True,
        help="Photos album handle from albums output.",
    )
    photos_album_assets.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum asset results, capped at 50.",
    )
    photos_album_assets.add_argument(
        "--max-scan-albums",
        type=int,
        default=5000,
        help="Maximum albums to scan while resolving the handle, capped at 10000.",
    )
    photos_album_assets.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum selected-album assets to scan, capped at 10000.",
    )
    photos_album_assets.set_defaults(func=_photos_album_assets_command)

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
        help="Preview an approved Photos import, exact asset flag update/delete, exact regular-album membership, or regular album change without applying it.",
    )
    photos_plan.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_plan.add_argument(
        "--operation",
        required=True,
        choices=[
            "import",
            "update-flags",
            "update_flags",
            "delete",
            "add-to-album",
            "add_to_album",
            "remove-from-album",
            "remove_from_album",
            "create-album",
            "create_album",
            "rename-album",
            "rename_album",
            "delete-album",
            "delete_album",
        ],
        help="Approved Photos plan operation.",
    )
    photos_plan.add_argument(
        "--source-file",
        default="",
        help="Local image or video file to import. The output does not echo the path.",
    )
    photos_plan.add_argument("--handle", default="", help="Exact Photos asset handle for update-flags or delete.")
    photos_plan.add_argument(
        "--media-type",
        choices=["auto", "image", "video"],
        default="auto",
        help="Optional media type assertion for the source file.",
    )
    photos_plan.add_argument("--favorite", default=None, help="Target favorite flag for update-flags.")
    photos_plan.add_argument("--hidden", default=None, help="Target hidden flag for update-flags.")
    photos_plan.add_argument("--album-handle", default="", help="Exact Photos album handle for album membership.")
    photos_plan.add_argument("--album-title", default="", help="Regular album title for create-album.")
    photos_plan.add_argument(
        "--new-album-title",
        default="",
        help="Regular album target title for rename-album.",
    )
    photos_plan.add_argument(
        "--expected-in-album",
        default=None,
        help="Expected current album membership for add-to-album or remove-from-album.",
    )
    photos_plan.add_argument(
        "--expected-favorite",
        default=None,
        help="Expected current favorite flag for update-flags.",
    )
    photos_plan.add_argument(
        "--expected-hidden",
        default=None,
        help="Expected current hidden flag for update-flags.",
    )
    photos_plan.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum assets to scan while resolving the handle, capped at 10000.",
    )
    photos_plan.add_argument(
        "--max-scan-albums",
        type=int,
        default=5000,
        help="Maximum albums to scan while resolving the album handle, capped at 10000.",
    )
    photos_plan.set_defaults(func=_photos_plan_command)

    photos_apply = photos_subparsers.add_parser(
        "apply",
        help="Apply an approved Photos import, exact asset flag update/delete, exact regular-album membership, or regular album change after plan-token confirmation.",
    )
    photos_apply.add_argument("--json", action="store_true", help="Emit JSON output.")
    photos_apply.add_argument(
        "--operation",
        required=True,
        choices=[
            "import",
            "update-flags",
            "update_flags",
            "delete",
            "add-to-album",
            "add_to_album",
            "remove-from-album",
            "remove_from_album",
            "create-album",
            "create_album",
            "rename-album",
            "rename_album",
            "delete-album",
            "delete_album",
        ],
        help="Approved Photos apply operation.",
    )
    photos_apply.add_argument(
        "--source-file",
        default="",
        help="Local image or video file to import. The output does not echo the path.",
    )
    photos_apply.add_argument("--handle", default="", help="Exact Photos asset handle for update-flags or delete.")
    photos_apply.add_argument(
        "--media-type",
        choices=["auto", "image", "video"],
        default="auto",
        help="Optional media type assertion for the source file.",
    )
    photos_apply.add_argument("--favorite", default=None, help="Target favorite flag for update-flags.")
    photos_apply.add_argument("--hidden", default=None, help="Target hidden flag for update-flags.")
    photos_apply.add_argument("--album-handle", default="", help="Exact Photos album handle for album membership.")
    photos_apply.add_argument("--album-title", default="", help="Regular album title for create-album.")
    photos_apply.add_argument(
        "--new-album-title",
        default="",
        help="Regular album target title for rename-album.",
    )
    photos_apply.add_argument(
        "--expected-in-album",
        default=None,
        help="Expected current album membership for add-to-album or remove-from-album.",
    )
    photos_apply.add_argument(
        "--expected-favorite",
        default=None,
        help="Expected current favorite flag for update-flags.",
    )
    photos_apply.add_argument(
        "--expected-hidden",
        default=None,
        help="Expected current hidden flag for update-flags.",
    )
    photos_apply.add_argument(
        "--max-scan-assets",
        type=int,
        default=5000,
        help="Maximum assets to scan while resolving the handle, capped at 10000.",
    )
    photos_apply.add_argument(
        "--max-scan-albums",
        type=int,
        default=5000,
        help="Maximum albums to scan while resolving the album handle, capped at 10000.",
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

    reminders_request_access = reminders_subparsers.add_parser(
        "request-access",
        help="Prompt once for full Reminders access through the EventKit helper.",
    )
    reminders_request_access.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_request_access.set_defaults(func=_reminders_request_access_command)

    reminders_lists = reminders_subparsers.add_parser(
        "lists",
        help="Search Reminders list metadata through EventKit, or enumerate all lists when --query is omitted.",
    )
    reminders_lists.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_lists.add_argument(
        "--query",
        default="",
        help="List title query text; omit to enumerate all lists.",
    )
    reminders_lists.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results, capped at 50.",
    )
    reminders_lists.set_defaults(func=_reminders_lists_command)

    reminders_list = reminders_subparsers.add_parser(
        "list",
        help="Get exact Reminders list metadata by opaque EventKit list handle.",
    )
    reminders_list.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_list.add_argument(
        "--handle",
        required=True,
        help="Reminder list EventKit handle from lists output.",
    )
    reminders_list.set_defaults(func=_reminders_list_command)

    reminders_list_items = reminders_subparsers.add_parser(
        "list-items",
        help="List exact Reminders metadata in one selected list.",
    )
    reminders_list_items.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_list_items.add_argument(
        "--handle",
        required=True,
        help="Reminder list EventKit handle from lists output.",
    )
    reminders_list_items.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum items, capped at 50.",
    )
    reminders_list_items.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed reminders in selected-list output.",
    )
    reminders_list_items.set_defaults(func=_reminders_list_items_command)

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
        choices=[
            "create",
            "create-with-start-date",
            "create_with_start_date",
            "create-with-recurrence",
            "create_with_recurrence",
            "complete",
            "uncomplete",
            "update-due-date",
            "update_due_date",
            "update-start-date",
            "update_start_date",
            "update-recurrence",
            "update_recurrence",
            "update-title",
            "update_title",
            "update-notes",
            "update_notes",
            "update-priority",
            "update_priority",
            "update-url",
            "update_url",
            "clear-url",
            "clear_url",
            "set-absolute-display-alarm",
            "set_absolute_display_alarm",
            "set-relative-display-alarm",
            "set_relative_display_alarm",
            "set-mixed-display-alarm",
            "set_mixed_display_alarm",
            "clear-display-alarm",
            "clear_display_alarm",
            "move-to-list",
            "move_to_list",
            "delete",
        ],
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
    _add_reminders_start_date_recurrence_arguments(reminders_plan, verb="planning")
    reminders_plan.add_argument(
        "--notes",
        help="Optional Reminder notes for create planning, or replacement notes for update-notes, capped at 12000 characters.",
    )
    reminders_plan.add_argument(
        "--handle",
        help="Reminder EventKit handle for complete, uncomplete, update-due-date, update-title, update-notes, update-priority, update-url, clear-url, set-absolute-display-alarm, set-relative-display-alarm, set-mixed-display-alarm, clear-display-alarm, move-to-list, or delete planning.",
    )
    reminders_plan.add_argument(
        "--url",
        help="Allowed replacement URL for update-url. Raw URL is used only for planning/apply and is not returned.",
    )
    reminders_plan.add_argument(
        "--target-list-handle",
        help="Opaque Reminders list handle from lists output for move-to-list planning.",
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
    reminders_plan.add_argument(
        "--expected-list-name",
        help="Expected current list title from a recent read-only result for move-to-list.",
    )
    reminders_plan.add_argument(
        "--expected-list-handle",
        help="Opaque current Reminders list handle from recent reminder metadata for move-to-list.",
    )
    reminders_plan.add_argument(
        "--expected-priority",
        type=int,
        help="Expected current priority from a recent read-only result for update-priority or delete.",
    )
    reminders_plan.add_argument(
        "--expected-notes-sha256",
        help="Expected current notes SHA-256 from exact Reminder content for update-notes or delete.",
    )
    reminders_plan.add_argument(
        "--expected-url-present",
        choices=["true", "false"],
        help="Expected current Reminder URL presence for update-url or clear-url.",
    )
    reminders_plan.add_argument(
        "--expected-url-sha256",
        help="Expected current URL SHA-256 from exact Reminder metadata when expected-url-present is true.",
    )
    reminders_plan.add_argument(
        "--alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        help="Comma-separated absolute Reminder alarm ISO 8601 timestamps with timezones for set-absolute-display-alarm or set-mixed-display-alarm.",
    )
    reminders_plan.add_argument(
        "--alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        help="Comma-separated integer minute offsets for set-relative-display-alarm or set-mixed-display-alarm.",
    )
    reminders_plan.add_argument(
        "--expected-alarms-count",
        type=int,
        help="Expected current Reminder alarm count for set-absolute-display-alarm, set-relative-display-alarm, set-mixed-display-alarm, or clear-display-alarm.",
    )
    reminders_plan.add_argument(
        "--expected-alarms-sha256",
        help="Expected current Reminder alarm-state SHA-256 from exact Reminder content when alarms are present.",
    )
    reminders_plan.add_argument(
        "--priority",
        type=int,
        help="Replacement Reminder priority for update-priority, from 0 to 9.",
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
        choices=[
            "create",
            "create-with-start-date",
            "create_with_start_date",
            "create-with-recurrence",
            "create_with_recurrence",
            "complete",
            "uncomplete",
            "update-due-date",
            "update_due_date",
            "update-start-date",
            "update_start_date",
            "update-recurrence",
            "update_recurrence",
            "update-title",
            "update_title",
            "update-notes",
            "update_notes",
            "update-priority",
            "update_priority",
            "update-url",
            "update_url",
            "clear-url",
            "clear_url",
            "set-absolute-display-alarm",
            "set_absolute_display_alarm",
            "set-relative-display-alarm",
            "set_relative_display_alarm",
            "set-mixed-display-alarm",
            "set_mixed_display_alarm",
            "clear-display-alarm",
            "clear_display_alarm",
            "move-to-list",
            "move_to_list",
            "delete",
        ],
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
    _add_reminders_start_date_recurrence_arguments(reminders_apply, verb="apply")
    reminders_apply.add_argument(
        "--notes",
        help="Optional Reminder notes for create apply, or replacement notes for update-notes, capped at 12000 characters.",
    )
    reminders_apply.add_argument(
        "--handle",
        help="Reminder EventKit handle for complete, uncomplete, update-due-date, update-title, update-notes, update-priority, update-url, clear-url, set-absolute-display-alarm, set-relative-display-alarm, set-mixed-display-alarm, clear-display-alarm, move-to-list, or delete apply.",
    )
    reminders_apply.add_argument(
        "--url",
        help="Allowed replacement URL for update-url. Must match the approved plan.",
    )
    reminders_apply.add_argument(
        "--target-list-handle",
        help="Opaque Reminders list handle from lists output for move-to-list apply.",
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
        "--expected-list-name",
        help="Expected current list title from a recent read-only result for move-to-list.",
    )
    reminders_apply.add_argument(
        "--expected-list-handle",
        help="Opaque current Reminders list handle from recent reminder metadata for move-to-list.",
    )
    reminders_apply.add_argument(
        "--expected-priority",
        type=int,
        help="Expected current priority from a recent read-only result for update-priority or delete.",
    )
    reminders_apply.add_argument(
        "--expected-notes-sha256",
        help="Expected current notes SHA-256 from exact Reminder content for update-notes or delete.",
    )
    reminders_apply.add_argument(
        "--expected-url-present",
        choices=["true", "false"],
        help="Expected current Reminder URL presence for update-url or clear-url.",
    )
    reminders_apply.add_argument(
        "--expected-url-sha256",
        help="Expected current URL SHA-256 from exact Reminder metadata when expected-url-present is true.",
    )
    reminders_apply.add_argument(
        "--alarm-absolute-dates",
        type=_calendar_alarm_absolute_dates_arg,
        help="Comma-separated absolute Reminder alarm ISO 8601 timestamps with timezones for set-absolute-display-alarm or set-mixed-display-alarm.",
    )
    reminders_apply.add_argument(
        "--alarm-offsets-minutes",
        type=_calendar_alarm_offsets_arg,
        help="Comma-separated integer minute offsets for set-relative-display-alarm or set-mixed-display-alarm.",
    )
    reminders_apply.add_argument(
        "--expected-alarms-count",
        type=int,
        help="Expected current Reminder alarm count for set-absolute-display-alarm, set-relative-display-alarm, set-mixed-display-alarm, or clear-display-alarm.",
    )
    reminders_apply.add_argument(
        "--expected-alarms-sha256",
        help="Expected current Reminder alarm-state SHA-256 from exact Reminder content when alarms are present.",
    )
    reminders_apply.add_argument(
        "--priority",
        type=int,
        help="Replacement Reminder priority for update-priority, from 0 to 9.",
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

    reminders_plan_list = reminders_subparsers.add_parser(
        "plan-list",
        help="Plan an exact Reminders list create/rename/delete/migrate-delete operation.",
    )
    reminders_plan_list.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_plan_list.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-list",
            "create_list",
            "rename-list",
            "rename_list",
            "delete-list",
            "delete_list",
            "delete-list-with-migration",
            "delete_list_with_migration",
        ],
        help="Future Reminders list operation to plan. No mutation is applied.",
    )
    reminders_plan_list.add_argument(
        "--source-list-handle",
        default="",
        help="Existing Reminders list handle whose source will receive create-list.",
    )
    reminders_plan_list.add_argument(
        "--list-handle",
        default="",
        help="Exact Reminders list handle for rename-list or delete-list.",
    )
    reminders_plan_list.add_argument(
        "--target-list-handle",
        default="",
        help="Exact same-source target list handle for delete-list-with-migration.",
    )
    reminders_plan_list.add_argument(
        "--list-title",
        default="",
        help="List title for create-list.",
    )
    reminders_plan_list.add_argument(
        "--new-list-title",
        default="",
        help="Target title for rename-list.",
    )
    reminders_plan_list.set_defaults(func=_reminders_plan_list_command)

    reminders_apply_list = reminders_subparsers.add_parser(
        "apply-list",
        help="Apply an approved exact Reminders list operation.",
    )
    reminders_apply_list.add_argument("--json", action="store_true", help="Emit JSON output.")
    reminders_apply_list.add_argument(
        "--operation",
        required=True,
        choices=[
            "create-list",
            "create_list",
            "rename-list",
            "rename_list",
            "delete-list",
            "delete_list",
            "delete-list-with-migration",
            "delete_list_with_migration",
        ],
        help="Approved Reminders list operation to apply.",
    )
    reminders_apply_list.add_argument(
        "--source-list-handle",
        default="",
        help="Same source Reminders list handle used for create-list planning.",
    )
    reminders_apply_list.add_argument(
        "--list-handle",
        default="",
        help="Same exact Reminders list handle used for rename-list or delete-list planning.",
    )
    reminders_apply_list.add_argument(
        "--target-list-handle",
        default="",
        help="Same exact target list handle used for delete-list-with-migration planning.",
    )
    reminders_apply_list.add_argument(
        "--list-title",
        default="",
        help="Same list title used for create-list planning.",
    )
    reminders_apply_list.add_argument(
        "--new-list-title",
        default="",
        help="Same target title used for rename-list planning.",
    )
    reminders_apply_list.add_argument(
        "--approval-token",
        required=True,
        help="Approval token bound to the matching Reminders list plan fingerprint.",
    )
    reminders_apply_list.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Required explicit confirmation flag for the approved apply operation.",
    )
    reminders_apply_list.set_defaults(func=_reminders_apply_list_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        load_operator_env(local_env_path=OPERATOR_LOCAL_ENV_PATH)
    except OperatorEnvError as exc:
        print(f"local-apple-data operator environment failed: {exc}", file=sys.stderr)
        return 1
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(
            f"local-apple-data command failed: {_exception_class_name(exc)}",
            file=sys.stderr,
        )
        return 1
