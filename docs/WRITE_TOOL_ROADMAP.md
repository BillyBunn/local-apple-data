# Write Tool Roadmap

The current release is read-only. This roadmap defines the sequence and engineering contract for future mutation support. It does not approve or expose any write tools by itself.

Use this file with `docs/MUTATION_GATES.md`.

## Principle

Write support must be boring, narrow, and independently verifiable. A write tool should never be the first way an agent discovers state. The agent must search or fetch current state first, present a preview, apply only after explicit approval, and then read back through an independent path.

## Tool Shape

Every mutation class should expose three layers:

- `preview`: validate inputs and return the planned change without touching Apple data.
- `apply`: perform the exact approved change.
- `read_back`: verify the resulting state through the normal read-only adapter.

The MCP tool annotations must mark write tools as not read-only. Destructive tools must be annotated as destructive and should stay absent until non-destructive writes are proven.

## First Write Tranche

Start with low-risk local writes through public Apple APIs or user-visible app automation:

| Priority | Surface | Operation | Preferred implementation | Read-back |
| --- | --- | --- | --- | --- |
| 1 | Reminders | Create reminder | Swift EventKit helper | EventKit search by generated handle/title |
| 2 | Reminders | Complete reminder | Swift EventKit helper | EventKit exact reminder fetch |
| 3 | Calendar | Create event | Swift EventKit helper | EventKit search by event title/time |
| 4 | Notes | Create note | Notes.app automation | Notes metadata search and exact content |
| 5 | iCloud Drive | Create text file | Local filesystem with parent handle | iCloud Drive metadata and text content |
| 6 | Mail | Create draft only | Mail.app automation | Mail metadata search for draft |

No first-tranche tool should delete, send, archive, move, overwrite, bulk edit, or manage account state.

## Deferred Write Tranches

These need separate design documents:

- Contact create/update through Contacts.framework.
- Calendar update/delete.
- Reminder update/delete.
- Note append/update with rich-text conversion.
- iCloud Drive append/overwrite/delete.
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
