# Mutation Gates

The current plugin is local-only and read-mostly. Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, `icloud_drive_apply_change`, `calendar apply`, `calendar_apply_change`, `contacts apply`, `contacts_apply_change`, `notes apply`, `notes_apply_change`, `mail apply`, `mail_apply_change`, `photos apply`, `photos_apply_change`, `messages apply`, and `messages_apply_change`.

Those tools are limited to Reminders create, complete, and due-date update through the plan/apply/read-back contract in `docs/V1_11_REMINDERS_WRITE_DESIGN.md`, iCloud Drive create-text through the plan/apply/read-back contract in `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`, iCloud Drive append-text through the plan/apply/read-back contract in `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`, Calendar create-event through the plan/apply/read-back contract in `docs/V1_13_CALENDAR_WRITE_DESIGN.md`, Contacts create-contact through the plan/apply/read-back contract in `docs/V1_14_CONTACTS_WRITE_DESIGN.md`, Notes create-note through the plan/apply/read-back contract in `docs/V1_15_NOTES_WRITE_DESIGN.md`, Notes append-text through the plan/apply/read-back contract in `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`, Mail create-draft through the plan/apply/read-back contract in `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`, Photos import through the plan/apply/read-back contract in `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`, and Messages send-text through the plan/apply/read-back contract in `docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md`. All other write tools remain intentionally absent until each mutation class has a separate design, explicit user approval, synthetic tests, and independent read-back verification.

For sequencing and later candidates, see `docs/WRITE_TOOL_ROADMAP.md`.

## Global Requirements

Every mutating tool must satisfy all of these before exposure through CLI or MCP:

- Separate design doc for the specific surface and operation.
- Explicit user approval for the exact mutation class.
- Dry-run or preview mode that returns the planned change without applying it.
- Independent read-back after mutation.
- Idempotency story for retries and partial failures.
- Narrow input schema with no broad batch mutation by default.
- Stable warning/error codes with no raw paths, identifiers, stack traces, or personal content in logs.
- MCP annotations marking the tool as non-read-only and destructive when applicable.
- Tests using synthetic fixtures or mocked Apple framework helpers only.
- Redaction scan and runtime smoke passing before install.

The current `reminders plan` / `icloud-drive plan` / `calendar plan` / `contacts plan` / `notes plan` / `mail plan` / `photos plan` / `messages plan` CLI commands and `reminders_plan_change` / `icloud_drive_plan_change` / `calendar_plan_change` / `contacts_plan_change` / `notes_plan_change` / `mail_plan_change` / `photos_plan_change` / `messages_plan_change` MCP tools are not mutating tools. They return `mutation_applied:false`, `apply_available:true`, and approval metadata only.

The current `reminders apply` CLI command and `reminders_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, operation-specific expected state, EventKit apply, and read-back verification. MCP annotations mark `reminders_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `icloud-drive apply` CLI command and `icloud_drive_apply_change` MCP tool are mutating tools. For create-text they require a matching approval token from the plan fingerprint, explicit confirmation, exact opaque parent folder handle, exclusive create, and read-back verification. For append-text they require a matching approval token, explicit confirmation, exact opaque file handle, expected current content SHA-256, drift refusal, bounded UTF-8 append, and read-back hash verification. MCP annotations mark `icloud_drive_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `calendar apply` CLI command and `calendar_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, explicit target calendar title, EventKit apply, and read-back verification. MCP annotations mark `calendar_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `contacts apply` CLI command and `contacts_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, Contacts.framework apply, and read-back verification. MCP annotations mark `contacts_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `notes apply` CLI command and `notes_apply_change` MCP tool are mutating tools. For create-note they require a matching approval token from the plan fingerprint, explicit confirmation, Notes.app automation, and exact-content read-back verification. For append-text they require a matching approval token, explicit confirmation, exact opaque note handle, expected current content SHA-256, drift refusal, bounded plaintext append, shared/locked-note refusal, and exact-content read-back hash verification. MCP annotations mark `notes_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `mail apply` CLI command and `mail_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, save-only Mail.app automation, and local Drafts read-back verification when the local Mail store exposes the saved draft. MCP annotations mark `mail_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `photos apply` CLI command and `photos_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, source-file hash binding, PhotoKit import, and created-asset read-back verification. MCP annotations mark `photos_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

The current `messages apply` CLI command and `messages_apply_change` MCP tool are mutating tools. They require a matching approval token from the plan fingerprint, explicit confirmation, exact existing chat handle, stale chat-state refusal, Messages.app automation, ghost-row detection, and local `chat.db` read-back verification without returning the sent body text in apply output. MCP annotations mark `messages_apply_change` as non-read-only, non-destructive, idempotent, and closed-world.

## First Candidate Write Surfaces

| Surface | Candidate operations | Preferred API | Extra approval checks |
| --- | --- | --- | --- |
| Reminders | Create reminder, complete reminder, update due date | EventKit helper | Approved. Confirm target list, title, due date, completion state, approval token, and explicit confirmation before apply |
| Calendar | Create timed event | EventKit helper | Approved. Confirm exact calendar title, title, start/end timestamps, approval token, and explicit confirmation before apply; no attendees, recurrence, alarms, all-day events, update, or delete |
| Notes | Create note; append text to an exact note | Notes.app automation | Approved. Confirm title/body for create, or exact note handle plus expected current SHA-256 for append, approval token, and explicit confirmation before apply; no arbitrary update, delete, move, rich text, attachment mutation, broad attachment export, folder/account targeting, locked/shared-note mutation, or bulk operations |
| Mail | Create draft only | Mail.app automation | Approved. Confirm recipients, subject, body length/preview, approval token, explicit confirmation, and save-only behavior; no send, attachment mutation, broad attachment export, reply, forward, mailbox/account management, or sender-account selection |
| Contacts | Create contact | Contacts.framework helper | Approved. Confirm contact type, name or organization, labeled fields, approval token, and explicit confirmation before apply; no update, delete, notes, image data, postal addresses, birthdays, group membership, or bulk operations |
| Photos | Import one image or video asset | PhotoKit change requests | Approved. Confirm caller-selected source file, inferred media type, file size/hash, approval token, and explicit confirmation before apply; no edits, delete, album targeting, hidden/favorite/metadata mutation, network fetch, or bulk operations |
| Messages | Send plaintext to one exact existing chat | Messages.app automation plus local `chat.db` read-back | Approved. Confirm exact chat handle, body length/preview, approval token, explicit confirmation, stale chat-state refusal, and ghost-row detection before success; no direct-recipient send, new chat, SMS fallback selection, file send, reactions, edit, delete, or account selection |
| Safari | None | Local `Bookmarks.plist` is read-only in the current release | Bookmark/Reading List mutation, history/tabs access, cookies, passwords, page content, and browser state require separate design and approval |
| Shortcuts | None | Apple `shortcuts` CLI is used only for name metadata in the current release | Run/open/view/sign/export, body/action-graph reads, dynamic run tools, import/export, and mutation require separate design and approval |
| Books | None | Local Books SQLite stores are read-only in the current release | Book/chapter/PDF/EPUB text extraction, broad library or annotation dumps/searches, iCloud fetch, Books.app automation, and mutation require separate design and approval |
| Podcasts | None | Local Podcasts SQLite store is read-only in the current release | Transcript/audio/feed/enclosure URL extraction, broad library or episode-description dumps/searches, iCloud media fetch, Podcasts.app automation, and mutation require separate design and approval |
| Hide My Email | None | No approved local public API | Authoritative inventory or mutation requires a new source review and explicit approval |
| iCloud Drive | Create text file; append text to an exact text file | Local filesystem | Approved. Confirm exact parent folder or file by opaque handle, filename or expected current SHA-256, content hash, approval token, and explicit confirmation before apply; no overwrite/rename/move/copy/delete |

## Default Refusals

Outside the approved Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail draft, Photos import, and Messages send-text apply gates, the plugin must refuse:

- Sending mail.
- Messages direct-recipient sends, new chat creation, SMS fallback selection, file sends, rich text, effects, inline replies, reactions/tapbacks, edit, unsend, delete, mark read, group management, participant lookup, contact lookup, broad text search, and account selection.
- Mail reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, sender-account selection, attachment mutation, broad attachment export, HTML/rich-text draft mutation, templates, or bulk mail mutation.
- Deleting, archiving, moving, or marking Messages beyond the approved send-text apply gate; broad Messages attachment export; Messages attachment mutation; inline Messages attachment bytes; source Messages media paths.
- Creating, deleting, deactivating, or managing Hide My Email aliases.
- Deleting Calendar events, Contacts, Photos, Notes, Reminders, Voice Memos, or iCloud Drive files.
- Photos edit, album targeting, album create/update/delete, hidden/favorite mutation, metadata mutation, thumbnails, inline asset bytes, network iCloud fetch, importing from URLs, and bulk Photos operations.
- Safari bookmark creation/update/delete/move, history access, open tabs/iCloud tabs, private browsing data, cookies, passwords, browser caches, page content, or Safari UI automation.
- Shortcuts run/open/view/sign/export, shortcut body/action graph reads, dynamic run tools, folder-scoped handles, Shortcuts SQLite scraping, import, create, update, delete, duplicate, or mutation.
- Books book/chapter/PDF/EPUB text extraction, broad library dumps, broad annotation search/dumps, raw Books IDs/paths, iCloud content fetch, Books.app automation, or mutation.
- Podcasts transcript/audio/feed/enclosure URL extraction, broad library dumps, broad episode-description search/dumps, raw Podcasts IDs/paths, iCloud media fetch, Podcasts.app automation, or mutation.
- Notes arbitrary update, delete, move, folder/account targeting, rich-text editing, checklist state, attachment mutation, broad attachment export, locked/shared-note mutation, Recently Deleted management, or bulk operations.
- Calendar update, delete, move, recurrence, attendees, invitations, URLs, alarms, attachments, travel time, availability changes, all-day events, default-calendar guessing, or bulk operations.
- Contacts update, delete, merge, move, group membership, postal addresses, birthdays, dates, relationships, social profiles, instant messaging addresses, notes, image data, custom labels beyond bounded local labels, or bulk operations.
- Reminders bulk mutation, list/account management, attachment mutation, URL/rich-content mutation, delete, or uncomplete.
- iCloud Drive overwrite, rename, move, copy, delete, binary/document writes, raw path writes, hidden-file writes, symlink/package traversal, or broad folder writes.
- Bulk mutation.
- Mutation through iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, OAuth, IMAP, or connector fallbacks.

## Verification Shape

A mutation tranche is not done until:

- The read-only tools still pass all existing tests.
- New preview/apply/read-back tests pass.
- `uv run python scripts/audit_mutation_gates.py` is updated for the approved tool names and passes.
- `uv run python scripts/audit_write_design_gates.py` is updated from design-only to approved-with-tests for the exact operation and passes.
- Runtime smoke proves the tool list annotations and refusal behavior.
- The skill, privacy model, threat model, testing doc, capability matrix, README, and plugin manifest all describe the new mutation state consistently.
- Installed cache and cross-agent sync verification pass.
