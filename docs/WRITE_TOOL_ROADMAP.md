# Write Tool Roadmap

The current release is read-mostly. Reminders apply, iCloud Drive create-text apply, Calendar create-event apply, and Contacts create-contact apply are the only approved write surfaces; every other write surface remains gated by this roadmap and `docs/MUTATION_GATES.md`.

Use this file with `docs/MUTATION_GATES.md`. The first concrete Reminders write design gate is `docs/V1_11_REMINDERS_WRITE_DESIGN.md`; the first iCloud Drive write design gate is `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`; the first Calendar write design gate is `docs/V1_13_CALENDAR_WRITE_DESIGN.md`; the first Contacts write design gate is `docs/V1_14_CONTACTS_WRITE_DESIGN.md`.

Current progress: `reminders plan` / `reminders_plan_change`, `icloud-drive plan` / `icloud_drive_plan_change`, `calendar plan` / `calendar_plan_change`, and `contacts plan` / `contacts_plan_change` implement non-mutating previews. `reminders apply` / `reminders_apply_change` implement approved Reminder create, complete, and due-date update with approval-token checks and read-back verification. `icloud-drive apply` / `icloud_drive_apply_change` implement approved iCloud Drive create-text with approval-token checks, exclusive create, and read-back verification. `calendar apply` / `calendar_apply_change` implement approved Calendar create-event with approval-token checks, explicit calendar title, EventKit apply, and read-back verification. `contacts apply` / `contacts_apply_change` implement approved Contacts create-contact with approval-token checks, Contacts.framework apply, and read-back verification.

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
| 7 | Notes | Create note | Notes.app automation | Notes metadata search and exact content |
| 8 | Mail | Create draft only | Mail.app automation | Mail metadata search for draft |

No first-tranche tool should delete, send, archive, move, overwrite, bulk edit, or manage account state.

## Deferred Write Tranches

These need separate design documents:

- Contact update/delete/merge/move/group membership, notes, image data, postal addresses, birthdays, relationships, social profiles, instant messages, and bulk operations through Contacts.framework.
- Calendar update/delete/move/recurrence/attendees/alarms/all-day/default-calendar guessing.
- Reminder delete, uncomplete, list/account management, attachments, URLs, and rich-content mutation.
- Note append/update with rich-text conversion.
- iCloud Drive append/overwrite/rename/move/copy/delete and binary/document writes.
- Mail send.
- Messages send/edit/delete.
- Photos asset edits/import/delete.
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
- Mail sending from the plugin before draft-only behavior is proven.
- Photos mutation/import/delete before a separate PhotoKit write design.
- Voice Memos generated transcription or mutation before a separate media-content design.
