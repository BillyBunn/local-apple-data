# Write Tool Roadmap

The current release is read-mostly. Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply are the only approved write surfaces; every other write surface remains gated by this roadmap and `docs/MUTATION_GATES.md`.

Use this file with `docs/MUTATION_GATES.md`. The first concrete Reminders write design gate is `docs/V1_11_REMINDERS_WRITE_DESIGN.md`; the first iCloud Drive create-text write design gate is `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`; the first Calendar write design gate is `docs/V1_13_CALENDAR_WRITE_DESIGN.md`; the first Contacts write design gate is `docs/V1_14_CONTACTS_WRITE_DESIGN.md`; the first Notes write design gate is `docs/V1_15_NOTES_WRITE_DESIGN.md`; the first Mail draft write design gate is `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`; the first Photos import write design gate is `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`; the first iCloud Drive append-text write design gate is `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`; the first Notes append-text write design gate is `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`; the first Notes attachment export design gate is `docs/V1_20_NOTES_ATTACHMENT_EXPORT.md`; the first Mail attachment export design gate is `docs/V1_21_MAIL_ATTACHMENT_EXPORT.md`; the first Messages attachment export design gate is `docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md`; the Messages attributed-body fallback design gate is `docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md`.

Current progress: `reminders plan` / `reminders_plan_change`, `icloud-drive plan` / `icloud_drive_plan_change`, `calendar plan` / `calendar_plan_change`, `contacts plan` / `contacts_plan_change`, `notes plan` / `notes_plan_change`, `mail plan` / `mail_plan_change`, and `photos plan` / `photos_plan_change` implement non-mutating previews. `reminders apply` / `reminders_apply_change` implement approved Reminder create, complete, and due-date update with approval-token checks and read-back verification. `icloud-drive apply` / `icloud_drive_apply_change` implement approved iCloud Drive create-text with approval-token checks, exclusive create, and read-back verification, plus approved append-text with exact file handles, expected-current-SHA-256 drift refusal, and read-back hash verification. `calendar apply` / `calendar_apply_change` implement approved Calendar create-event with approval-token checks, explicit calendar title, EventKit apply, and read-back verification. `contacts apply` / `contacts_apply_change` implement approved Contacts create-contact with approval-token checks, Contacts.framework apply, and read-back verification. `notes apply` / `notes_apply_change` implement approved Notes create-note with approval-token checks, Notes.app automation, and exact-content read-back verification, plus approved append-text with exact note handles, expected-current-SHA-256 drift refusal, shared/locked-note refusal, and exact-content read-back hash verification. `notes attachments` / `notes_list_attachments` and `notes export-attachment` / `notes_export_attachment` implement exact-handle Notes attachment metadata/export without inline bytes or mutation. `mail attachments` / `mail_list_attachments` and `mail export-attachment` / `mail_export_attachment` implement exact-message-plus-attachment-handle Mail MIME attachment metadata/export without inline bytes, source message paths, externalized fetch, broad export, or mutation. `mail apply` / `mail_apply_change` implement approved Mail create-draft with approval-token checks, save-only Mail.app automation, and local Drafts read-back verification when available. `photos apply` / `photos_apply_change` implement approved Photos import with approval-token checks, source-file hash binding, PhotoKit apply, and created-asset read-back verification.

## Principle

Write support must be boring, narrow, and independently verifiable. A write tool should never be the first way an agent discovers state. The agent must search or fetch current state first, present a preview, apply only after explicit approval, and then read back through an independent path.

## Tool Shape

Every mutation class should expose three layers:

- `preview`: validate inputs and return the planned change without touching Apple data. Reminders planning is implemented as `reminders plan` / `reminders_plan_change`.
- `apply`: perform the exact approved change. Reminders apply is implemented as `reminders apply` / `reminders_apply_change`.
- `read_back`: verify the resulting state through the normal read-only adapter.

The MCP tool annotations must mark write tools as not read-only. Destructive tools must be annotated as destructive and should stay absent until non-destructive writes are proven.

## First Write Tranche

Start with low-risk local writes through public Apple APIs or user-visible app automation:

| Priority | Surface | Operation | Preferred implementation | Read-back |
| --- | --- | --- | --- | --- |
| 1 | Reminders | Create reminder | Swift EventKit helper | Implemented; EventKit read-back |
| 2 | Reminders | Complete reminder | Swift EventKit helper | Implemented; EventKit read-back |
| 3 | Reminders | Update due date | Swift EventKit helper | Implemented; EventKit read-back |
| 4 | iCloud Drive | Create text file | Implemented; local filesystem with parent handle | Implemented; iCloud Drive metadata, content hash, and text content |
| 5 | Calendar | Create timed event | Implemented; Swift EventKit helper | Implemented; EventKit read-back |
| 6 | Contacts | Create contact | Implemented; Swift Contacts.framework helper | Implemented; Contacts.framework read-back |
| 7 | Notes | Create note | Implemented; Notes.app automation | Implemented; Notes metadata search and exact content |
| 8 | Mail | Create draft only | Implemented; save-only Mail.app automation | Implemented; Mail metadata search and exact content when local Drafts indexing is available |
| 9 | Photos | Import image or video asset | Implemented; Swift PhotoKit helper | Implemented; PhotoKit created-asset read-back |
| 10 | iCloud Drive | Append text to one exact text file | Implemented; local filesystem with exact file handle and expected current hash | Implemented; iCloud Drive metadata, new content hash, and text content |
| 11 | Notes | Append text to one exact note | Implemented; Notes.app automation with exact handle and expected current hash | Implemented; Notes exact content and new content hash |
| 12 | Notes | Attachment metadata/export for one exact note | Implemented read/export only; no mutation | Implemented; selected note handle plus selected attachment handle |
| 13 | Mail | Attachment metadata/export for one exact message | Implemented read/export only; no mutation | Implemented; selected message handle plus selected attachment handle |

No first-tranche tool should delete, send, archive, move, overwrite, bulk edit, or manage account state.

## Deferred Write Tranches

These need separate design documents:

- Contact update/delete/merge/move/group membership, notes, image data, postal addresses, birthdays, relationships, social profiles, instant messages, and bulk operations through Contacts.framework.
- Calendar update/delete/move/recurrence/attendees/alarms/all-day/default-calendar guessing.
- Reminder delete, uncomplete, list/account management, attachments, URLs, and rich-content mutation.
- Notes arbitrary update with rich-text conversion, delete, move, folder/account targeting, attachment mutation, broad attachment export, checklist state, locked/shared-note mutation, and bulk operations.
- iCloud Drive overwrite/rename/move/copy/delete and binary/document writes.
- Mail send, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, sender-account selection, attachment mutation, broad attachment export, HTML/rich-text draft mutation, templates, or bulk operations.
- Messages send/edit/delete.
- Photos asset edits/delete, album targeting, hidden/favorite/metadata mutation, thumbnails, inline asset bytes, network iCloud fetch, and bulk operations.
- Voice Memos creation, generated transcription, or deletion.
- Authoritative Hide My Email inventory or mutation.

## Required Tests

Each mutation tranche must add:

- Synthetic preview tests.
- Synthetic apply/read-back tests with mocked Apple helpers.
- Invalid-handle and stale-handle tests.
- Permission-denied tests.
- Partial-failure tests.
- Runtime verifier coverage for tool annotations and refusal behavior.
- Mutation-gate auditor coverage for approved tool names.
- Write-design gate auditor coverage for the operation's design-only or approved-with-tests state.
- Redaction scan coverage for logs and docs.

## Required Runtime Safeguards

- Default to preview.
- Require exact target handles for edits to existing objects.
- Require explicit target container selection for creates.
- Return structured warning/error codes.
- Log only command name, status, warning codes, counts, and duration.
- Do not log proposed content, handles, raw paths, account identifiers, framework identifiers, recipients, attendees, or aliases.
- Refuse broad batch mutation unless a later approved design adds bounded batch semantics.

## Still Blocked

The following remain blocked until a separate source review proves a durable, local, privacy-respecting path:

- Hide My Email alias creation, deactivation, deletion, or authoritative inventory.
- Any iCloud.com, browser-session, cookie, keychain, private iCloud web/API, IMAP, OAuth, or connector fallback mutation path.
- Sending Messages from the plugin.
- Mail sending or management from the plugin before a separate source review and explicit design gate.
- Photos edit/delete/album/metadata mutation before a separate PhotoKit write design.
- Voice Memos generated transcription or mutation before a separate media-content design.
