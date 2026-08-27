#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import public_release_scan


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MUTATION_VERBS = {
    "add",
    "append",
    "apply",
    "archive",
    "complete",
    "copy",
    "create",
    "delete",
    "draft",
    "edit",
    "flag",
    "import",
    "mark",
    "move",
    "rename",
    "remove",
    "replace",
    "save",
    "send",
    "trash",
    "uncomplete",
    "update",
    "write",
}
APPROVED_WRITE_MCP_TOOLS = {
    "calendar_apply_calendar_change",
    "calendar_apply_change",
    "contacts_apply_change",
    "filesystem_apply_change",
    "icloud_drive_apply_change",
    "mail_apply_change",
    "mail_apply_cleanup",
    "mail_apply_mailbox_change",
    "messages_apply_change",
    "notes_apply_change",
    "photos_apply_change",
    "reminders_apply_list_change",
    "reminders_apply_change",
    "shortcuts_apply_run",
}
APPROVED_LOCAL_CACHE_WRITE_MCP_TOOLS = {
    "mail_build_fts_index",
    "mail_create_template",
    "mail_delete_template",
}
ALLOWED_READ_ONLY_MUTATION_LIKE_MCP_TOOLS = {
    "contacts_export_archive",
}
REQUIRED_DESTRUCTIVE_MCP_TOOLS = {
    "calendar_apply_calendar_change",
    "calendar_apply_change",
    "contacts_apply_change",
    "filesystem_apply_change",
    "icloud_drive_apply_change",
    "mail_apply_change",
    "mail_apply_cleanup",
    "mail_apply_mailbox_change",
    "mail_delete_template",
    "notes_apply_change",
    "photos_apply_change",
    "reminders_apply_list_change",
    "reminders_apply_change",
    "shortcuts_apply_run",
}
APPROVED_WRITE_CLI_HANDLERS = {
    "calendar_apply_calendar",
    "calendar_apply",
    "contacts_apply",
    "filesystem_apply",
    "icloud_drive_apply",
    "mail_apply",
    "mail_apply_cleanup",
    "mail_apply_mailbox",
    "messages_apply",
    "notes_apply",
    "photos_apply",
    "reminders_apply_list",
    "reminders_apply",
    "shortcuts_apply",
}
APPROVED_LOCAL_CACHE_WRITE_CLI_HANDLERS = {
    "mail_template_create",
    "mail_template_delete",
}
MANIFEST_WRITE_CAPABILITIES = {
    "Create",
    "Delete",
    "Edit",
    "Manage",
    "Mutate",
    "Send",
    "Update",
    "Write",
}
EXPECTED_MANIFEST_CAPABILITIES = {
    "Local",
    "MCP",
    "Read",
    "Search",
    "Write",
}
AGENTS_DOC = "A" + "GENTS.md"
CONTACTS_NOTE_FAIL_CLOSED_CONTRACT = (
    "Contacts note gates are designed and synthetic-testable, but live calls fail "
    "closed with `contacts_note_unavailable` because the restricted entitlement "
    "is absent."
)
CANONICAL_APPLY_SURFACE_SUMMARY = (
    "Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact URL update/clear/exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear/exact same-source list-move/delete apply and exact list create/rename/empty-delete/same-source migrate-delete apply, "
    "iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply, "
    "Calendar create-event/update/delete apply including exact relative alarm offsets, exact absolute display alarms, exact audio alarms, exact email alarms, exact structured geofence alarms, explicit timed-event time zones, exact availability create/update with expected-state binding, exact allow-listed event URL create/update and exact event URL clearing with hash-only read-back proof, exact target-calendar create/move, date-only all-day inference, simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly recurrence create and add-to-non-recurring-event update with weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year and selector-backed set-position filtering, selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected-occurrence recurring-event delete, future-event recurring span delete, whole-series recurring-event delete, first-visible and mid-series recurrence clearing, mid-series recurrence replacement, future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, and structured event location create/update/clear, apply from approved explicit default-calendar create plans only through the resolved exact calendar handle, and Calendar synthetic `LAD-TEST-*` calendar create/rename/delete apply, "
    "Contacts create-contact/exact scalar/method/rich-field/image update/exact group membership/exact group create/rename/delete/exact batch/delete apply, "
    "Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete apply, "
    "Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, "
    "Mail synthetic `LAD-TEST-*` mailbox create/rename apply, source-gated synthetic mailbox delete and synthetic cleanup apply only when public Mail.app deletion plus exact target-state binding, mailbox-scoped absence proof, and Mail-idle guards succeed, "
    "Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete apply with full Photos Library authorization, and Messages send-text/send-file apply, "
    "home-directory Filesystem create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply rooted at the operator home directory reusing the exact iCloud Drive within-root plan/apply/read-back gates with a credential/secret path denylist, "
    "and Shortcuts run apply of one exact identifier-bound shortcut through the plan/apply approval-token/confirm gate, resolved by an exact `shortcuts:item:v1:` handle with the resolved identifier bound into the approval fingerprint, invoked by argv (never a shell string) under a hard execution timeout, proving invocation of the named shortcut only because a shortcut's arbitrary side effects are not verifiable by read-back"
)
REQUIRED_MUTATION_GATE_TEXT = {
    AGENTS_DOC: "Approved mutation is limited to " + CANONICAL_APPLY_SURFACE_SUMMARY,
    "README.md": "Its plan/apply surfaces cover approved exact operations in Reminders, iCloud Drive, Calendar, Contacts excluding note mutation, Notes",
    "docs/MUTATION_GATES.md": "Approved write tools: `reminders apply`, `reminders_apply_change`, `reminders apply-list`, `reminders_apply_list_change`, `icloud-drive apply`, `icloud_drive_apply_change`, `calendar apply`, `calendar_apply_change`, `calendar apply-calendar`, `calendar_apply_calendar_change`, `contacts apply`, `contacts_apply_change`, `notes apply`, `notes_apply_change`, `mail apply`, `mail_apply_change`, `mail apply-mailbox`, `mail_apply_mailbox_change`, `mail apply-cleanup`, `mail_apply_cleanup`, `photos apply`, `photos_apply_change`, `messages apply`, `messages_apply_change`, `filesystem apply`, `filesystem_apply_change`, `shortcuts apply`, and `shortcuts_apply_run`",
    "docs/WRITE_TOOL_ROADMAP.md": CANONICAL_APPLY_SURFACE_SUMMARY + " are the only approved write surfaces",
    "src/local_apple_data/mcp_server.py": "The only apply-capable mutation surfaces are " + CANONICAL_APPLY_SURFACE_SUMMARY,
}
REQUIRED_MUTATION_DETAIL_TEXT = {
    AGENTS_DOC: (
        "The designed Contacts note gates are synthetic-testable but currently fail closed before mutation with `contacts_note_unavailable`.",
    ),
    "README.md": (
        "Contacts note plan/apply contracts are designed and synthetic-testable, but they are not a usable live mutation surface",
        "every note operation fails closed with `contacts_note_unavailable` before mutation",
    ),
    "src/local_apple_data/mcp_server.py": (CONTACTS_NOTE_FAIL_CLOSED_CONTRACT,),
    "docs/MUTATION_GATES.md": (
        "The public MCP inventory contains 14 apply-capable tools.",
        "Contacts note contracts are designed and synthetic-testable",
        "live note operations fail closed with `contacts_note_unavailable` before mutation",
        "Photos exact regular-album membership add/remove through the plan/apply/read-back contract in `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`",
        "For add_to_album/remove_from_album they require a matching approval token, explicit confirmation, one exact `photos:asset:v1:` handle, one exact `photos:album:v1:` handle, exact `expected_in_album` binding, regular-album add/remove support, PhotoKit `PHAssetCollectionChangeRequest`, `addAssets` or `removeAssets`, membership read-back proof, `raw_asset_identifier_returned:false`, and `raw_album_identifier_returned:false`.",
        "Photos exact regular-album create/rename/delete with full Photos Library authorization through the plan/apply/read-back contract in `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`",
        "For create_album/rename_album/delete_album they require a matching approval token, explicit confirmation, full Photos Library authorization, bounded non-empty title for create/rename, exact `photos:album:v1:` handle for rename/delete, expected album-state binding, duplicate-title refusal, empty-album proof for delete, public PhotoKit `PHAssetCollectionChangeRequest`, title read-back for create/rename, absence proof for delete, and `raw_album_identifier_returned:false`.",
        "iCloud Drive exact folder Trash through the plan/apply/read-back metadata and absence-proof contracts in `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` and `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`",
        "For trash-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, expected directory metadata SHA-256, metadata drift refusal, recoverable Trash move, original absence proof, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `non_empty_allowed:true`, and metadata-only read-back.",
        "iCloud Drive exact folder move, including non-empty directories, through the plan/apply/read-back metadata-proof contract in `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` and `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`",
        "For move-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, exact opaque target parent handle, expected directory metadata SHA-256, metadata drift refusal, descendant-parent refusal, no-overwrite target proof, source/target presence proof, `non_empty_allowed:true`, and metadata-only read-back.",
        "iCloud Drive exact selected-folder copy through the plan/apply/read-back metadata-proof contracts in `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md` and `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`",
        "For copy-folder they require a matching approval token, explicit confirmation, exact opaque directory handle, exact opaque target parent handle, expected directory metadata SHA-256, private bounded source-tree binding, metadata/tree drift refusal, hidden/symlink/package/tree-size refusal, descendant-parent refusal, no-overwrite target proof, source preservation proof, target presence proof, `non_empty_allowed:true`, no child listing, and metadata-only read-back.",
        "iCloud Drive exact selected-folder permanent delete through the plan/apply/read-back metadata, hidden-staging, and absence-proof contract in `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`",
        "For delete-folder they require a matching approval token, explicit confirmation, one exact directory handle, expected directory metadata SHA-256, private bounded source-tree binding, metadata/tree drift refusal, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `non_empty_allowed:true`, no child listing, and metadata-only read-back.",
        "iCloud Drive exact text-file permanent delete through the plan/apply/read-back content-hash, exact file identity, random-only hidden-staging, and absence-proof contract in `docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md`",
        "For delete-text they require a matching approval token, explicit confirmation, one exact supported text-file handle, expected current SHA-256, approval fingerprint binding to exact file identity, stale identity/token replay refusal, current-content drift refusal, no-follow/package/symlink traversal refusal, random-only hidden staging identity proof, permanent unlink, original absence proof, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, and no raw path return.",
        "iCloud Drive exact regular-file rename/copy/move through the plan/apply/read-back metadata-proof contract in `docs/V1_127_ICLOUD_DRIVE_REGULAR_FILE_RENAME_COPY_MOVE_WRITE_DESIGN.md`",
        "For rename-file/copy-file/move-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected file metadata SHA-256, metadata drift refusal, no-overwrite target proof, source/target presence proof, metadata-only read-back, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.",
        "iCloud Drive exact local regular-file import through the plan/apply/read-back metadata-proof contract in `docs/V1_129_ICLOUD_DRIVE_IMPORT_FILE_WRITE_DESIGN.md`",
        "For import-file they require a matching approval token, explicit confirmation, one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, one exact target parent handle, private source identity/content binding, no-overwrite target proof, source preservation proof, metadata-only target read-back, `source_path_returned:false`, `source_hash_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no source path/hash return, no content hash return, and no raw path return.",
        "iCloud Drive exact regular-file replace through the plan/apply/read-back metadata-proof contract in `docs/V1_130_ICLOUD_DRIVE_REPLACE_FILE_WRITE_DESIGN.md`",
        "For replace-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, one caller-selected local non-text non-package regular file outside the configured iCloud Drive root, private source identity/content binding, source/target extension match, target metadata drift refusal, source preservation proof, byte replacement proof, metadata-only target read-back, `source_path_returned:false`, `source_hash_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no source path/hash return, no content hash return, and no raw path return.",
        "iCloud Drive exact regular-file Trash through the plan/apply/read-back metadata-proof contract in `docs/V1_131_ICLOUD_DRIVE_TRASH_FILE_WRITE_DESIGN.md`",
        "For trash-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, recoverable Trash move, original absence proof, metadata-only read-back, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.",
        "Home-directory Filesystem CRUD through the plan/apply/read-back contract in `docs/V1_178_FILESYSTEM_HOME_SCOPE_WRITE_DESIGN.md`",
        "For home-directory Filesystem operations they reuse the exact iCloud Drive plan/apply/read-back gates re-rooted at the operator home directory (`~`), require a matching approval token, explicit confirmation, and an exact `fs:file:v1:` handle or parent handle, keep every resolved target within the home root after realpath/symlink resolution, refuse `..` or symlink escapes outside the home root, refuse other users' home directories and system paths, refuse content-read and mutation of a credential/secret denylist (`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.config/gcloud`, `~/.netrc`, `~/.docker/config.json`, `~/.kube`, `~/Library/Keychains`, `~/Library/Application Support/com.apple.TCC`, and any `.env` or `.env.*`) with `credential_path_blocked` while still allowing metadata-only listing, remain operator-overridable via `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1`, use `~/.Trash` for reversible trash, and keep permanent delete behind the same hidden-staging identity-proof and absence-proof gate as iCloud delete.",
        "iCloud Drive exact regular-file permanent delete through the plan/apply/read-back metadata-proof contract in `docs/V1_132_ICLOUD_DRIVE_DELETE_FILE_WRITE_DESIGN.md`",
        "For delete-file they require a matching approval token, explicit confirmation, one exact non-text non-package regular-file handle, expected target metadata SHA-256, target metadata drift refusal, no-follow/package/symlink traversal refusal, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, `staging_path_returned:false`, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, no content hash return, and no raw path return.",
        "Reminders exact URL update/clear through the plan/apply/read-back contract in `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`",
        "For Reminder URL update/clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, exact expected URL presence, exact expected URL SHA-256 when a URL is present, allow-listed URL scheme, ASCII-only URL input, EventKit apply, hash-only URL read-back proof for update, absence proof for clear, and no raw URL return.",
        "Reminders exact absolute display-alarm set/clear through the plan/apply/read-back contract in `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`",
        "For Reminder absolute display-alarm set/clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, expected completed state, exact expected alarm count, exact expected alarm-state SHA-256 when alarms are present, bounded timezone-explicit absolute alarm dates, EventKit apply, exact date read-back proof for set, absence proof for clear, and no raw alarm state return.",
        "Reminders exact relative display-alarm set and broadened pure display-alarm clear through the plan/apply/read-back contract in `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`",
        "For Reminder relative display-alarm set and pure display-alarm clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, expected completed state, exact expected alarm count, exact expected alarm-state SHA-256 when alarms are present, bounded integer minute offsets for set, EventKit apply, exact offset read-back proof for set, absence proof for pure display-alarm clear, and no raw alarm state return.",
        "Reminders exact mixed absolute-plus-relative display-alarm set/clear through the plan/apply/read-back contract in `docs/V1_176_REMINDERS_MIXED_DISPLAY_ALARM_WRITE_DESIGN.md`",
        "For Reminder mixed display-alarm set and mixed display-alarm clear they require a matching approval token, explicit confirmation, exact opaque reminder handle, expected title, expected completed state, exact expected alarm count, exact expected alarm-state SHA-256 when alarms are present, bounded integer minute offsets plus bounded timezone-explicit absolute alarm dates for set, EventKit apply, exact mixed offset/date read-back proof for set, absence proof for clear, and no raw alarm state return.",
        "Calendar future-series recurring-event event URL set/clear through the plan/apply/read-back contract in `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`",
        "For future-series recurring-event event URL set/clear they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, exact allow-listed `event_url` or update-only `clear_event_url:true`, required URL expected-state binding for clear, no scalar/timed/all-day/calendar/availability/structured-location/alarm/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus hash-only URL read-back or absence proof, no raw URL return, and previous-occurrence preservation proof.",
        "Calendar future-series recurring-event structured-location set/clear through the plan/apply/read-back contract in `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`",
        "For future-series recurring-event structured-location set/clear they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, bounded `structured_location` or update-only `clear_structured_location:true`, exact expected structured-location binding for clear, no scalar/timed/all-day/calendar/availability/event-URL/alarm/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof.",
        "Calendar future-series recurring-event display-alarm set/clear through the plan/apply/read-back contract in `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`",
        "For future-series recurring-event display-alarm set/clear they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, bounded relative `alarm_offsets_minutes` or absolute `alarm_absolute_dates` or update-only display-alarm clear, exact expected display-alarm state binding, no scalar/timed/all-day/calendar/availability/event-URL/structured-location/action-alarm/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof.",
        "Calendar future-series recurring-event action-alarm set/clear through the plan/apply/read-back contract in `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`",
        "For future-series recurring-event action-alarm set/clear they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, exact audio `alarm_sound_name`, raw-input-only email `alarm_email_address`, or structured geofence `alarm_proximity` plus `alarm_structured_location` with explicit proposed trigger state or update-only action-alarm clear, exact expected display/audio/email/geofence alarm state binding, hash-only `alarm_email_address_sha256` output with no raw email return, no scalar/timed/all-day/calendar/availability/event-URL/structured-location/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof.",
        "Calendar future-series recurring-event all-day set/clear/date-only reschedule through the plan/apply/read-back contract in `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`",
        "For future-series recurring-event all-day set/clear/date-only reschedule they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, exact expected all-day/time-zone state binding, date-only proposed `start_date`/`end_date` for all-day set or same-state all-day date-only reschedule, explicit proposed `time_zone` for all-day-to-timed clear, no scalar/calendar/availability/event-URL/structured-location/alarm/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof.",
        "Calendar future-series recurring-event target-calendar move through the plan/apply/read-back contract in `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`",
        "For future-series recurring-event target-calendar move they require update-only `recurrence_update_scope:future_events` without recurrence fields, exact expected recurrence shape binding, selected occurrence start/end identity binding, previous occurrence identity binding, future occurrence identity binding, exact `calendar:calendar:v1:` target handle with resolved writable target-calendar binding, no scalar/timed/all-day/availability/event-URL/structured-location/alarm/recurrence co-mutation, matching approval token, explicit confirmation, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof.",
        "recurrence outside simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly create, add-to-non-recurring-event update, weekly weekday selection, monthly weekday selection, monthly day-of-month selection, monthly nth-weekday selection, yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year and selector-backed set-position filtering, selected-occurrence title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected-occurrence delete, future-event recurring span delete, whole-series recurring-event delete, first-visible or mid-series recurrence clearing, mid-series recurrence replacement, or future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update",
        "custom recurrence shapes beyond approved selector-backed EventKit rules",
    )
}
REQUIRED_OPERATION_SETS = {
    "src/local_apple_data/adapters/calendar.py": {
        "PLAN_OPERATIONS": {"create", "update", "delete"},
        "CALENDAR_MANAGEMENT_OPERATIONS": {
            "create_calendar",
            "delete_calendar",
            "rename_calendar",
        },
    },
    "src/local_apple_data/adapters/contacts.py": {
        "PLAN_OPERATIONS": {
            "batch",
            "create",
            "update",
            "append_note",
            "set_note",
            "replace_note",
            "overwrite_note",
            "clear_note",
            "delete_note",
            "merge_note",
            "add_group_member",
            "remove_group_member",
            "create_group",
            "rename_group",
            "delete_group",
            "delete",
        },
    },
    "src/local_apple_data/adapters/icloud_drive.py": {
        "PLAN_OPERATIONS": {
            "create_text",
            "append_text",
            "replace_text",
            "create_folder",
            "create_folder_path",
            "rename_folder",
            "trash_folder",
            "delete_folder",
            "move_folder",
            "copy_folder",
            "trash_text",
            "delete_text",
            "rename_text",
            "copy_text",
            "move_text",
            "rename_file",
            "copy_file",
            "move_file",
            "import_file",
            "replace_file",
            "trash_file",
            "delete_file",
        },
    },
    "src/local_apple_data/adapters/filesystem.py": {
        "PLAN_OPERATIONS": {
            "create_text",
            "append_text",
            "replace_text",
            "create_folder",
            "create_folder_path",
            "rename_folder",
            "trash_folder",
            "delete_folder",
            "move_folder",
            "copy_folder",
            "trash_text",
            "delete_text",
            "rename_text",
            "copy_text",
            "move_text",
            "rename_file",
            "copy_file",
            "move_file",
            "import_file",
            "replace_file",
            "trash_file",
            "delete_file",
        },
    },
    "src/local_apple_data/adapters/mail.py": {
        "PLAN_OPERATIONS": {
            "create_draft",
            "send_message",
            "reply_message",
            "reply_all_message",
            "forward_message",
            "mark_read",
            "mark_unread",
            "flag_message",
            "unflag_message",
            "archive_message",
            "trash_message",
            "move_message",
        },
    },
    "src/local_apple_data/adapters/messages.py": {
        "PLAN_OPERATIONS": {"send_text", "send_file"},
    },
    "src/local_apple_data/adapters/notes.py": {
        "PLAN_OPERATIONS": {
            "create",
            "create_html",
            "create_folder",
            "rename_folder",
            "delete_folder",
            "move_folder",
            "append_text",
            "replace_text",
            "replace_html",
            "move_to_folder",
            "delete",
        },
    },
    "src/local_apple_data/adapters/photos.py": {
        "PLAN_OPERATIONS": {
            "import",
            "update_flags",
            "delete",
            "add_to_album",
            "remove_from_album",
            "create_album",
            "rename_album",
            "delete_album",
        },
    },
    "src/local_apple_data/adapters/reminders.py": {
        "PLAN_OPERATIONS": {
            "create",
            "create_with_start_date",
            "create_with_recurrence",
            "complete",
            "uncomplete",
            "update_due_date",
            "update_start_date",
            "update_recurrence",
            "update_title",
            "update_notes",
            "update_priority",
            "update_url",
            "clear_url",
            "set_absolute_display_alarm",
            "set_relative_display_alarm",
            "set_mixed_display_alarm",
            "clear_display_alarm",
            "move_to_list",
            "delete",
        },
        "LIST_MANAGEMENT_OPERATIONS": {
            "create_list",
            "rename_list",
            "delete_list",
            "delete_list_with_migration",
        },
    },
    "src/local_apple_data/adapters/shortcuts.py": {
        "PLAN_OPERATIONS": {"run"},
    },
}


def _operation_aliases(values: set[str]) -> set[str]:
    return set(values) | {value.replace("_", "-") for value in values}


REQUIRED_CLI_OPERATION_CHOICES = {
    "calendar_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/calendar.py"]["PLAN_OPERATIONS"]),
    "calendar_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/calendar.py"]["PLAN_OPERATIONS"]),
    "calendar_plan_calendar": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/calendar.py"]["CALENDAR_MANAGEMENT_OPERATIONS"]),
    "calendar_apply_calendar": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/calendar.py"]["CALENDAR_MANAGEMENT_OPERATIONS"]),
    "contacts_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/contacts.py"]["PLAN_OPERATIONS"]),
    "contacts_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/contacts.py"]["PLAN_OPERATIONS"]),
    "icloud_drive_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/icloud_drive.py"]["PLAN_OPERATIONS"]),
    "icloud_drive_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/icloud_drive.py"]["PLAN_OPERATIONS"]),
    "filesystem_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/filesystem.py"]["PLAN_OPERATIONS"]),
    "filesystem_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/filesystem.py"]["PLAN_OPERATIONS"]),
    "mail_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/mail.py"]["PLAN_OPERATIONS"]),
    "mail_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/mail.py"]["PLAN_OPERATIONS"]),
    "messages_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/messages.py"]["PLAN_OPERATIONS"]),
    "messages_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/messages.py"]["PLAN_OPERATIONS"]),
    "notes_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/notes.py"]["PLAN_OPERATIONS"]),
    "notes_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/notes.py"]["PLAN_OPERATIONS"]),
    "photos_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/photos.py"]["PLAN_OPERATIONS"]),
    "photos_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/photos.py"]["PLAN_OPERATIONS"]),
    "reminders_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/reminders.py"]["PLAN_OPERATIONS"]),
    "reminders_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/reminders.py"]["PLAN_OPERATIONS"]),
    "reminders_plan_list": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/reminders.py"]["LIST_MANAGEMENT_OPERATIONS"]),
    "reminders_apply_list": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/reminders.py"]["LIST_MANAGEMENT_OPERATIONS"]),
    "shortcuts_plan": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/shortcuts.py"]["PLAN_OPERATIONS"]),
    "shortcuts_apply": _operation_aliases(REQUIRED_OPERATION_SETS["src/local_apple_data/adapters/shortcuts.py"]["PLAN_OPERATIONS"]),
}
REQUIRED_MCP_OPERATION_LITERALS = {
    "ICloudDriveOperation": REQUIRED_CLI_OPERATION_CHOICES["icloud_drive_plan"],
    "FilesystemOperation": REQUIRED_CLI_OPERATION_CHOICES["filesystem_plan"],
}
REQUIRED_PLUGIN_DESCRIPTION_TEXT = (
    "approved Reminders, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create-text/append-text/replace-text/"
    "trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file, Calendar create/update/delete with date-only all-day inference, exact availability create/update, exact allow-listed event URL create/update and exact event URL clearing, and simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly recurrence create plus add-to-non-recurring-event update plus weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year and selector-backed set-position filtering plus selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update plus selected-occurrence recurring-event delete plus future-event recurring span delete plus whole-series recurring-event delete, first-visible and mid-series recurrence clearing, mid-series recurrence replacement, future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, and "
    "structured event location create/update/clear, exact audio alarms, exact email alarms, exact structured geofence alarms, "
    "Contacts create-contact/exact scalar/method/rich-field/image update/exact group membership/exact group create/rename/delete/exact batch/delete, Notes default/exact-folder note "
    "create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, "
    "move-to-folder, and exact-note delete, Mail "
    "draft/send/reply/reply-all/forward plus exact/capped-bulk read/flag/archive/move/trash triage, "
    "synthetic LAD-TEST-* mailbox create/rename/delete and source-gated cleanup planning with crash-safe cleanup guards, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete with full Photos Library authorization, "
    "and Messages send-text/send-file apply, and home-directory Filesystem CRUD reusing the exact iCloud Drive gates re-rooted at the operator home directory (`~`) with a within-home boundary and a credential/secret path denylist. Mail draft/send/reply/reply-all/forward support optional exact sender selection and bounded local file attachments"
)
REQUIRED_PLUGIN_LONG_DESCRIPTION_TEXT = (
    CONTACTS_NOTE_FAIL_CLOSED_CONTRACT,
    "Reminders list management is limited to exact create/rename/empty-delete/same-source migrate-delete with exact source/target reminders:list:eventkit:v1 handles, bounded title validation, duplicate-title refusal, writable-state binding, empty-list proof for rename/delete, bounded same-source migration count proof for migrate-delete, EventKit source/title/migration/target-count/absence read-back, and no raw EventKit identifiers.",
    "Photos regular album management requires full Photos Library authorization, bounded non-empty titles, exact photos:album:v1 handles for rename/delete, duplicate-title refusal, empty-album proof for delete, PhotoKit title read-back or absence proof, and returns no raw PhotoKit identifiers.",
    "Mail attachment search can opt into text/PDF snippets with include_content and OCR fallback with include_ocr; it returns no attachment bytes, temporary paths, or cache paths. Mail FTS build/search is opt-in, date-bounded, and confirmation-gated for build because it writes a private local content cache; FTS output returns capped redacted snippets, exact handles, counts, and an opaque index ref, never full bodies, attachment bytes, raw cached text, or cache paths.",
    "Mail sender search returns masked configured sender metadata and opaque `mail:sender:v1:` handles only; optional sender_handle is accepted for create-draft/send/reply/reply-all/forward and synthetic account-scoped mailbox/cleanup planning, where apply sets the outgoing message sender for outbound mail and requires read-back confirmation without returning full sender emails.",
    "Mail create-draft/send-message/reply-message/reply-all-message/forward-message may attach bounded caller-selected local files through the approved draft/send/reply/reply-all/forward attachment gate; planning binds selected file identity and content SHA-256 into the approval token, apply uses token-validated private attachment identity metadata, copies validated bytes to a private temporary file before Mail automation, confirms Mail-derived attachment count before reporting success, and tool output returns no local attachment paths or file bytes.",
    "Mail capped exact bulk triage accepts unique exact selected message handles only for mark-read/mark-unread/flag/unflag/archive/move/trash, caps batches at 20 handles, preflights every selected message before mutation, and query-result triage is plan-only over capped FTS/search results before exact selected handles are passed to the existing bulk apply gate.",
    "Mail synthetic mailbox apply is limited to top-level `LAD-TEST-*` mailbox create/rename/delete with empty-mailbox checks, source-gated public Mail.app deletion for delete, and read-back/absence proof; delete remains live-blocked on this host by Mail.app AppleEvent `-10000`. Mail synthetic cleanup is limited to exact Trash/Junk messages whose subject starts with `LAD-TEST-` or empty Trash/Junk only when every planned current target is synthetic, and success requires exact target-state binding, mailbox-scoped absence proof, and Mail-idle guards; live cleanup is fail-closed unless public Mail.app deletion, Mail-idle guards, exact target-state binding, and mailbox-scoped absence proof all succeed.",
    "iCloud Drive text-file rename/copy/move is limited to one exact supported text file with no-overwrite targets, expected current SHA-256 binding, source/target presence proof, and target hash read-back without content text; rename/move use no-overwrite target reservation plus no-follow swap with post-swap proof, and copy rechecks source after target proof.",
    "iCloud Drive regular-file rename/copy/move is limited to one exact non-text non-package regular-file handle with expected metadata SHA-256 binding, no-overwrite target proof, source/target presence proof, metadata-only read-back, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash.",
    "iCloud Drive import-file is limited to one caller-selected local non-text non-package regular file outside iCloud Drive plus one exact target parent handle with private source identity/content binding, no-overwrite target proof, source-preservation proof, byte-preservation proof, metadata-only target read-back, no source path/hash return, `source_path_returned:false`, `source_hash_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash.",
    "iCloud Drive replace-file is limited to one exact non-text non-package regular-file handle plus one caller-selected local non-text non-package regular file outside iCloud Drive with expected target metadata binding, private source identity/content binding, source/target extension match, target metadata drift refusal, source-preservation proof, byte-replacement proof, metadata-only target read-back, no source path/hash return, `source_path_returned:false`, `source_hash_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash.",
    "iCloud Drive trash-file is limited to one exact non-text non-package regular-file handle with expected target metadata binding, target metadata drift refusal, recoverable Trash move, original absence proof, metadata-only read-back, no raw Trash path return, `trash_path_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash.",
    "iCloud Drive delete-file is limited to one exact non-text non-package regular-file handle with expected target metadata binding, target metadata drift refusal, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, no raw staging or Trash path return, `staging_path_returned:false`, `trash_path_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash.",
    "iCloud Drive exact folder rename, including non-empty directories, is limited to one exact directory handle with metadata SHA-256 binding, no-overwrite target proof, `non_empty_allowed:true`, and metadata-only read-back.",
    "iCloud Drive exact folder trash, including non-empty directories, is limited to one exact directory handle with metadata SHA-256 binding, recoverable Trash move, `non_empty_allowed:true`, child preservation, and metadata-only absence proof.",
    "iCloud Drive exact selected-folder delete is limited to one exact directory handle with metadata SHA-256 binding, private bounded source-tree binding, hidden/symlink/package/tree-size refusal, hidden staging identity proof, bounded permanent staged-tree removal, metadata-only original absence proof, no child listing, no content/hash/path return, `non_empty_allowed:true`, and `permanently_deleted:true` only after successful removal.",
    "iCloud Drive exact text-file delete is limited to one exact supported text-file handle with expected current SHA-256 and exact file identity binding, stale token replay refusal for recreated same-path/same-content files, no-follow/package/symlink refusal, random-only hidden staging identity proof, permanent unlink, original absence proof, no content/hash/path return, and `permanently_deleted:true` only after successful removal.",
    "iCloud Drive exact folder move, including non-empty directories, is limited to one exact directory handle with metadata SHA-256 binding, one exact target parent handle, descendant-parent refusal, no-overwrite target proof, `non_empty_allowed:true`, and metadata-only read-back.",
    "iCloud Drive exact selected-folder copy is limited to one exact directory handle with metadata SHA-256 binding, one exact target parent handle, optional bounded target folder name, private bounded source-tree binding, hidden/symlink/package/tree-size refusal, descendant-parent refusal, no-overwrite target proof, source/target presence proof, `non_empty_allowed:true`, no child listing, and metadata-only read-back.",
    "Home-directory Filesystem CRUD reuses the exact iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create-text/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file plan/apply/read-back gates re-rooted at the operator home directory (`~`) through a distinct `fs:file:v1:` handle namespace, keeps every resolved target within the home root after realpath/symlink resolution, refuses `..`/symlink escapes and other users' home directories and system paths, refuses content-read and mutation of a credential/secret denylist (`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.config/gcloud`, `~/.netrc`, `~/.docker/config.json`, `~/.kube`, `~/Library/Keychains`, `~/Library/Application Support/com.apple.TCC`, and any `.env` or `.env.*`) with `credential_path_blocked` while still allowing metadata-only listing, is operator-overridable via `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1`, uses `~/.Trash` for reversible trash, and keeps permanent delete behind the same hidden-staging identity-proof and absence-proof gate as iCloud delete.",
    "The only apply-capable mutation surfaces are " + CANONICAL_APPLY_SURFACE_SUMMARY + ", each with a matching plan approval token and explicit confirmation.",
    "The plugin avoids Gmail connector, Gmail API, IMAP, OAuth, private iCloud web APIs, browser sessions, keychain credentials, and network mail paths.",
)
FORBIDDEN_PLUGIN_OVERCLAIM_PATTERNS = {
    r"\bfull\s+CRUD\b",
    r"\ball[- ]encompassing\b",
    r"\bcompletely\s+bug[- ]free\b",
    r"\bpermanent[- ]delete\s+(apply|support|mutation|write)\b",
    r"\bempty[- ]trash\s+(apply|support|mutation|write)\b",
    r"\bnew[- ]chat\b",
    r"\bdirect[- ]recipient\b",
    r"\bsms[- ]fallback\b",
    r"\buses\s+browser\s+sessions\b",
    r"\bbrowser\s+sessions\s+fallback\b",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    path: Path
    line: int
    name: str
    message: str

    def to_json(self, root: Path) -> dict[str, Any]:
        try:
            relative = self.path.relative_to(root)
        except ValueError:
            relative = self.path
        return {
            "kind": self.kind,
            "path": relative.as_posix(),
            "line": self.line,
            "name": self.name,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExposedName:
    name: str
    path: Path
    line: int
    read_only_annotations: bool = True
    write_annotations: bool = False
    destructive_annotations: bool = False


def audit_mutation_gates(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    findings: list[Finding] = []
    mcp_tools = _mcp_tools(root / "src/local_apple_data/mcp_server.py", findings)
    cli_handlers = _cli_handlers(root / "src/local_apple_data/cli.py", findings)

    for tool in mcp_tools:
        approved_write = tool.name in APPROVED_WRITE_MCP_TOOLS
        approved_local_cache_write = tool.name in APPROVED_LOCAL_CACHE_WRITE_MCP_TOOLS
        terms = _mutation_terms(tool.name)
        if (
            terms
            and not approved_write
            and not approved_local_cache_write
            and tool.name not in ALLOWED_READ_ONLY_MUTATION_LIKE_MCP_TOOLS
        ):
            findings.append(
                Finding(
                    "mutation_like_mcp_tool",
                    tool.path,
                    tool.line,
                    tool.name,
                    f"Exposed MCP tool name contains mutation verb(s): {', '.join(terms)}",
                )
            )
        if (approved_write or approved_local_cache_write) and not tool.write_annotations:
            findings.append(
                Finding(
                    "approved_write_mcp_tool_annotation",
                    tool.path,
                    tool.line,
                    tool.name,
                    "Approved MCP write tool must use WRITE_ANNOTATIONS or DESTRUCTIVE_WRITE_ANNOTATIONS.",
                )
            )
        if tool.name in REQUIRED_DESTRUCTIVE_MCP_TOOLS and not tool.destructive_annotations:
            findings.append(
                Finding(
                    "approved_destructive_mcp_tool_annotation",
                    tool.path,
                    tool.line,
                    tool.name,
                    "Approved destructive MCP write tool must use DESTRUCTIVE_WRITE_ANNOTATIONS.",
                )
            )
        if not approved_write and not approved_local_cache_write and not tool.read_only_annotations:
            findings.append(
                Finding(
                    "mcp_tool_not_read_only",
                    tool.path,
                    tool.line,
                    tool.name,
                    "MCP tool is not annotated with READ_ONLY_ANNOTATIONS.",
                )
            )

    for handler in cli_handlers:
        exposed_name = handler.name.removesuffix("_command").removeprefix("_")
        approved_write = exposed_name in APPROVED_WRITE_CLI_HANDLERS
        approved_local_cache_write = exposed_name in APPROVED_LOCAL_CACHE_WRITE_CLI_HANDLERS
        terms = _mutation_terms(exposed_name)
        if terms and not approved_write and not approved_local_cache_write:
            findings.append(
                Finding(
                    "mutation_like_cli_handler",
                    handler.path,
                    handler.line,
                    handler.name,
                    f"Exposed CLI command handler contains mutation verb(s): {', '.join(terms)}",
                )
            )

    findings.extend(_mutation_contract_findings(root))
    findings.extend(_operation_contract_findings(root))
    findings.extend(_plugin_manifest_findings(root))

    return {
        "cli_handlers_checked": len(cli_handlers),
        "findings": [finding.to_json(root) for finding in findings],
        "mcp_tools_checked": len(mcp_tools),
        "mutation_verbs": sorted(MUTATION_VERBS),
        "approved_write_tools": sorted(APPROVED_WRITE_MCP_TOOLS),
        "approved_local_cache_write_tools": sorted(APPROVED_LOCAL_CACHE_WRITE_MCP_TOOLS),
        "read_only": not APPROVED_WRITE_MCP_TOOLS and not findings,
        "status": "ok" if not findings else "error",
    }


def _mcp_tools(path: Path, findings: list[Finding]) -> list[ExposedName]:
    tree = _parse_python(path, findings)
    if tree is None:
        return []
    tools: list[ExposedName] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorator = _mcp_tool_decorator(node.decorator_list)
        if decorator is None:
            continue
        tools.append(
            ExposedName(
                name=node.name,
                path=path,
                line=node.lineno,
                read_only_annotations=_uses_read_only_annotations(decorator),
                write_annotations=_uses_write_annotations(decorator),
                destructive_annotations=_uses_destructive_annotations(decorator),
            )
        )
    return tools


def _cli_handlers(path: Path, findings: list[Finding]) -> list[ExposedName]:
    tree = _parse_python(path, findings)
    if tree is None:
        return []
    handlers: list[ExposedName] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_") and node.name.endswith("_command"):
            handlers.append(ExposedName(name=node.name, path=path, line=node.lineno))
    return handlers


def _parse_python(path: Path, findings: list[Finding]) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except OSError as exc:
        findings.append(
            Finding(
                "source_unreadable",
                path,
                0,
                path.name,
                f"Could not read source file: {type(exc).__name__}",
            )
        )
    except SyntaxError as exc:
        findings.append(
            Finding(
                "source_syntax_error",
                path,
                exc.lineno or 0,
                path.name,
                "Could not parse source file.",
            )
        )
    return None


def _mcp_tool_decorator(decorators: Iterable[ast.expr]) -> ast.Call | None:
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "tool"
            and isinstance(func.value, ast.Name)
            and func.value.id == "mcp"
        ):
            return decorator
    return None


def _uses_read_only_annotations(decorator: ast.Call) -> bool:
    return _annotation_name(decorator) == "READ_ONLY_ANNOTATIONS"


def _uses_write_annotations(decorator: ast.Call) -> bool:
    return _annotation_name(decorator) in {
        "WRITE_ANNOTATIONS",
        "DESTRUCTIVE_WRITE_ANNOTATIONS",
    }


def _uses_destructive_annotations(decorator: ast.Call) -> bool:
    return _annotation_name(decorator) == "DESTRUCTIVE_WRITE_ANNOTATIONS"


def _annotation_name(decorator: ast.Call) -> str | None:
    for keyword in decorator.keywords:
        if keyword.arg != "annotations":
            continue
        if isinstance(keyword.value, ast.Name):
            return keyword.value.id
        return None
    return None


def _mutation_terms(name: str) -> list[str]:
    tokens = {token for token in re.split(r"[^A-Za-z0-9]+", name.casefold()) if token}
    return sorted(tokens & MUTATION_VERBS)


def _mutation_contract_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    # A generated public tree omits every operator-only doc by design, so requiring
    # contract text inside one there would fail on the generator's own output.
    public_tree = public_release_scan.is_sanitized_public_tree(root)
    for relative, required_text in REQUIRED_MUTATION_GATE_TEXT.items():
        if public_tree and relative in public_release_scan.LOCAL_OPERATOR_DOCS:
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                Finding(
                    "read_only_contract_missing",
                    path,
                    0,
                    relative,
                    f"Required mutation-gate contract file is unreadable: {type(exc).__name__}",
                )
            )
            continue
        if required_text not in text:
            findings.append(
                Finding(
                    "read_only_contract_missing",
                    path,
                    0,
                    relative,
                    f"Missing required mutation-gate contract text: {required_text}",
                )
            )
    for relative, required_texts in REQUIRED_MUTATION_DETAIL_TEXT.items():
        if public_tree and relative in public_release_scan.LOCAL_OPERATOR_DOCS:
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                Finding(
                    "read_only_contract_missing",
                    path,
                    0,
                    relative,
                    f"Required mutation-gate detail file is unreadable: {type(exc).__name__}",
                )
            )
            continue
        for required_text in required_texts:
            if required_text not in text:
                findings.append(
                    Finding(
                        "read_only_contract_missing",
                        path,
                        0,
                        relative,
                        f"Missing required mutation-gate detail text: {required_text}",
                    )
                )
    return findings


def _operation_contract_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative, constants in REQUIRED_OPERATION_SETS.items():
        path = root / relative
        tree = _parse_python(path, findings)
        if tree is None:
            continue
        for constant_name, expected_values in constants.items():
            actual_values = _module_string_set(tree, constant_name)
            if actual_values != expected_values:
                findings.append(
                    Finding(
                        "operation_contract_mismatch",
                        path,
                        0,
                        constant_name,
                        "Expected operation set "
                        f"{sorted(expected_values)}, found {sorted(actual_values or set())}.",
                    )
                )
    findings.extend(_cli_operation_choice_findings(root))
    findings.extend(_mcp_operation_literal_findings(root))
    return findings


def _module_string_set(tree: ast.Module, name: str) -> set[str] | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, (ast.Set, ast.List, ast.Tuple)):
            return None
        values: set[str] = set()
        for element in node.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            values.add(element.value)
        return values
    return None


def _cli_operation_choice_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    path = root / "src/local_apple_data/cli.py"
    tree = _parse_python(path, findings)
    if tree is None:
        return findings
    actual_by_parser = _cli_operation_choices(tree)
    for parser_name, expected_values in REQUIRED_CLI_OPERATION_CHOICES.items():
        actual = actual_by_parser.get(parser_name)
        actual_values = actual[0] if actual is not None else None
        line = actual[1] if actual is not None else 0
        if actual_values != expected_values:
            findings.append(
                Finding(
                    "operation_contract_mismatch",
                    path,
                    line,
                    f"cli.{parser_name}.choices",
                    "Expected CLI operation choices "
                    f"{sorted(expected_values)}, found {sorted(actual_values or set())}.",
                )
            )
    return findings


def _cli_operation_choices(tree: ast.Module) -> dict[str, tuple[set[str] | None, int]]:
    choices: dict[str, tuple[set[str] | None, int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if not node.args or not _is_string_constant(node.args[0], "--operation"):
            continue
        parser_name = func.value.id
        choices[parser_name] = (_call_keyword_string_sequence(node, "choices"), node.lineno)
    return choices


def _mcp_operation_literal_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    path = root / "src/local_apple_data/mcp_server.py"
    tree = _parse_python(path, findings)
    if tree is None:
        return findings
    for literal_name, expected_values in REQUIRED_MCP_OPERATION_LITERALS.items():
        actual = _module_literal_string_set(tree, literal_name)
        actual_values = actual[0] if actual is not None else None
        line = actual[1] if actual is not None else 0
        if actual_values != expected_values:
            findings.append(
                Finding(
                    "operation_contract_mismatch",
                    path,
                    line,
                    f"mcp.{literal_name}",
                    "Expected MCP operation Literal "
                    f"{sorted(expected_values)}, found {sorted(actual_values or set())}.",
                )
            )
    return findings


def _module_literal_string_set(tree: ast.Module, name: str) -> tuple[set[str] | None, int] | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id == "Literal"
        ):
            return (None, node.lineno)
        if isinstance(value.slice, ast.Tuple):
            values = _string_sequence(value.slice)
        else:
            values = _string_sequence(ast.Tuple(elts=[value.slice], ctx=ast.Load()))
        return (values, node.lineno)
    return None


def _call_keyword_string_sequence(call: ast.Call, name: str) -> set[str] | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return _string_sequence(keyword.value)
    return None


def _string_sequence(node: ast.AST) -> set[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: set[str] = set()
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        values.add(element.value)
    return values


def _is_string_constant(node: ast.AST, expected: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == expected


def _plugin_manifest_findings(root: Path) -> list[Finding]:
    path = root / ".codex-plugin/plugin.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding(
                "plugin_manifest_unreadable",
                path,
                0,
                "plugin.json",
                f"Could not read plugin manifest: {type(exc).__name__}",
            )
        ]

    findings: list[Finding] = []
    capabilities = set(manifest.get("interface", {}).get("capabilities", []))
    if capabilities != EXPECTED_MANIFEST_CAPABILITIES:
        findings.append(
            Finding(
                "plugin_manifest_capability_contract",
                path,
                0,
                "interface.capabilities",
                "Manifest capabilities must exactly match "
                f"{sorted(EXPECTED_MANIFEST_CAPABILITIES)}, found {sorted(capabilities)}.",
            )
        )
    write_capabilities = sorted(capabilities & MANIFEST_WRITE_CAPABILITIES)
    if write_capabilities and not APPROVED_WRITE_MCP_TOOLS:
        findings.append(
            Finding(
                "plugin_manifest_write_capability",
                path,
                0,
                "interface.capabilities",
                f"Manifest exposes write capability without mutation gate audit support: {', '.join(write_capabilities)}",
            )
        )

    description = str(manifest.get("description", ""))
    long_description = str(manifest.get("interface", {}).get("longDescription", ""))
    if REQUIRED_PLUGIN_DESCRIPTION_TEXT not in description:
        findings.append(
            Finding(
                "plugin_manifest_text_contract",
                path,
                0,
                "description",
                "Manifest description is missing the canonical approved-write summary.",
            )
        )
    if CONTACTS_NOTE_FAIL_CLOSED_CONTRACT not in description:
        findings.append(
            Finding(
                "plugin_manifest_text_contract",
                path,
                0,
                "description",
                "Manifest description is missing the exact Contacts-note fail-closed contract.",
            )
        )
    for required_text in REQUIRED_PLUGIN_LONG_DESCRIPTION_TEXT:
        if required_text not in long_description:
            findings.append(
                Finding(
                    "plugin_manifest_text_contract",
                    path,
                    0,
                    "interface.longDescription",
                    "Manifest longDescription is missing required safety wording.",
                )
            )
    manifest_text = f"{description}\n{long_description}"
    for pattern in sorted(FORBIDDEN_PLUGIN_OVERCLAIM_PATTERNS):
        if re.search(pattern, manifest_text, flags=re.IGNORECASE):
            findings.append(
                Finding(
                    "plugin_manifest_text_contract",
                    path,
                    0,
                    "description",
                    f"Manifest contains forbidden overclaim pattern: {pattern}",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit that public CLI/MCP surfaces remain read-only until mutation gates are approved."
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    payload = audit_mutation_gates(Path(args.project_root))
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "mutation gate audit: "
            f"status={payload['status']} "
            f"mcp_tools={payload['mcp_tools_checked']} "
            f"cli_handlers={payload['cli_handlers_checked']}"
        )
        for finding in payload["findings"]:
            print(
                f"- {finding['kind']}: {finding['path']}:{finding['line']}: "
                f"{finding['name']}: {finding['message']}"
            )
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
