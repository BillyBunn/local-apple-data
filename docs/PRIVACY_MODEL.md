# Privacy Model

This project handles local personal-data surfaces. The default is metadata-first and read-only for discovery/content retrieval, with content retrieval exposed only through exact opaque handles and bounded output. The only approved mutation surfaces are Reminders create/complete/due-date apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, Photos import apply, and Messages send-text apply through plan/apply/read-back gates.

## Data Tiers

1. Health: tool availability, macOS version, and store presence/readability only.
2. Metadata: bounded subjects/titles/snippets and Mail content-availability hints only when the user asks for the workflow.
3. Content/detail/export: exact-handle retrieval for Mail, Messages chats, inferred Hide My Email aliases, Voice Memos, Safari bookmarks/Reading List URLs, Shortcuts metadata, Notes, Calendar events, Contacts, Photos asset/resource metadata, Reminders, and supported iCloud Drive text files after the metadata flow returns a `mail:message:v2:`, `messages:chat:v1:`, `hide_my_email:alias:v1:`, `voice_memos:recording:v1:`, `safari:item:v1:`, `shortcuts:item:v1:`, `notes:note:v2:`, `calendar:event:v1:`, `contacts:contact:v1:`, `photos:asset:v1:`, `reminders:reminder:eventkit:v1:`, or `icloud:file:v1:` handle and the user explicitly requests that selected item. Media export tools additionally require a caller-selected output directory and do not return media bytes inline.
4. Attachments: exact selected Mail, Messages, and Notes attachment metadata/export only, using the selected parent item handle plus selected attachment handle where required. Broad attachment export, inline bytes, source paths, remote fetches, and attachment mutation remain blocked.
5. Preview: non-mutating Reminders future-change planning for exact requested create/complete/update-due-date workflows, non-mutating iCloud Drive create-text planning for exact requested parent folder handles, non-mutating iCloud Drive append-text planning for exact requested file handles plus expected current content hash, non-mutating Calendar create-event planning for explicit target calendar titles, non-mutating Contacts create-contact planning for bounded contact fields, non-mutating Notes create-note planning for bounded title/body input, non-mutating Notes append-text planning for exact requested note handles plus expected current content hash, non-mutating Mail create-draft planning for bounded recipient/subject/body input, non-mutating Photos import planning for caller-selected image/video source files, and non-mutating Messages send-text planning for exact existing chat handles plus bounded body preview.
6. Mutation: approved only for Reminders create/complete/due-date apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, Photos import apply, and Messages send-text apply; all other mutation requires a separate design and approval phase.

## Never Persist

Do not persist any of the following in logs, docs, prompts, fixtures, tests, commits, or durable plan files:

- Message bodies
- Mail draft planned recipients, subjects, body previews, handles, or approval fingerprints outside transient preview/apply responses
- Messages transcripts outside exact selected responses
- Messages send body text, body previews, body hashes, chat handles, chat GUIDs, participant identifiers, approval tokens, or approval fingerprints outside transient preview/apply responses
- Messages attachment metadata outside selected-chat responses and exported Messages attachments outside the caller-selected export path
- Full Hide My Email aliases outside exact selected responses
- Voice Memos transcript text outside exact selected responses
- Voice Memos audio bytes in chat, source recording paths, and raw recording identifiers
- Full Safari URLs outside exact selected responses
- Raw Shortcuts identifiers or shortcut bodies/action graphs
- Note bodies
- Note planned titles, body previews, handles, or approval fingerprints outside transient preview/apply responses
- Calendar event notes and locations
- Calendar planned titles, calendar names, locations, notes, handles, or approval fingerprints outside transient preview/apply responses
- Contact email addresses, phone numbers, postal addresses, URLs, relations, and dates
- Contact planned names, organization names, email addresses, phone numbers, URLs, handles, or approval fingerprints outside transient preview/apply responses
- Contact notes and image data
- Photo asset bytes in chat, thumbnails, raw Photos identifiers, and asset/resource metadata outside exact selected responses
- Photos import source paths, source filenames, source-file hashes, handles, or approval fingerprints outside transient preview/apply responses
- Reminder titles or notes
- Reminder planning titles or notes outside transient preview responses
- iCloud Drive file contents or raw local paths
- Safari history, open tabs, private browsing data, passwords, cookies, sessions, autofill, keychain data, or browser caches
- Shortcuts run/open/view/sign/export, shortcut body/action graph reads, dynamic run tools, or Shortcuts mutation
- iCloud Drive planned filenames, content, handles, content hashes, or approval fingerprints outside transient preview/apply responses
- Attachment content
- Attachment source media paths
- Full email addresses
- Raw Hide My Email identifiers
- Account identifiers
- Raw database rows
- Credentials, tokens, app passwords, cookies, OAuth artifacts, keychain data, or environment secrets

Opaque search-result handles are allowed. Mail, Messages, inferred Hide My Email, Voice Memos, Safari, Shortcuts, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive handles are signed with a local secret so exact metadata fetches cannot be performed with guessed database row IDs, raw framework identifiers, raw alias identifiers, recording identifiers, Shortcuts identifiers, or direct local paths. The same handles gate exact content/detail retrieval. The handle secret lives under the local plugin state directory and must not be printed or copied into durable docs.

## Allowed In Phase 0

- macOS version
- Tool availability
- Redacted tool path labels only, not full executable paths
- Redacted path labels for expected local stores
- Store presence and readability booleans
- Synthetic test data

## Redacted Audit Logs

The CLI writes redacted command events to `~/.local/state/local-apple-data/events.jsonl`.

Allowed log fields:

- Timestamp
- Command name
- Source
- Status
- Schema version
- Result count
- Warning codes
- Privacy flags

Forbidden log fields:

- Query text
- Result titles, subjects, snippets, note text, reminder text, or message content
- Warning messages that might include paths or private content
- Raw rows or stack traces from local stores
- Full local executable paths
- Handles, subjects, bodies, raw MIME, full headers, local Mail file paths, or raw exception strings

Warning payloads returned to the user should use stable warning codes and safe generic messages only. Do not include local store paths, store filenames, raw exception strings, query text, or result metadata in warning messages.

## Approval Required

Ask the local operator before:

- Changing TCC or Full Disk Access
- Editing Codex config
- Editing launchd jobs
- Editing OpenClaw runtime state
- Mutating Mail, Messages, Notes, Reminders, Gmail, or iCloud state outside the approved Reminders, iCloud Drive create/append-text, Calendar, Contacts, Notes, Mail draft, Photos import, and Messages send-text apply gates
- Adding direct network mail access
- Adding authoritative Hide My Email inventory or Hide My Email creation/deactivation/deletion
- Adding private iCloud web/API access, iCloud.com automation, browser sessions, or keychain credential access
- Adding new content classes beyond exact-handle Mail content/attachment export, Messages chat transcripts/attachment export, inferred Hide My Email aliases, Voice Memos existing embedded transcripts/audio export, Safari bookmark/Reading List URL detail, Shortcuts metadata, Notes content/attachment export, Calendar event detail, Contact detail, Photos asset/resource metadata/export, Reminder notes, and supported iCloud Drive text-file retrieval

## v1.11 Reminders Planning And Apply

The implemented v1.11 phase adds non-mutating Reminders planning and the first approved apply-capable mutation surface for Reminders create, complete, and due-date update. It is not permission to delete Reminders, run bulk changes, manage lists/accounts, mutate attachments/URLs/rich content, or mutate any other Apple data surface.

The v1.11 planning implementation:

- Exposes `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create, complete, and update-due-date operations without calling EventKit or writing Reminders.
- Requires exact opaque `reminders:reminder:eventkit:v1:` handles for existing-reminder operation planning.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, notes, handles, list names, and approval fingerprints.

The v1.11 apply implementation:

- Exposes `local-apple-data reminders apply` and MCP `reminders_apply_change`.
- Requires the matching `reminders-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque Reminder handles internally before existing-reminder updates.
- Calls EventKit only after approval checks pass.
- Returns read-back metadata and never logs titles, notes, handles, raw EventKit identifiers, list names, or approval tokens.

## v1.12 iCloud Drive Planning And Apply

The implemented v1.12 phase adds non-mutating iCloud Drive create-text planning and the approved apply-capable mutation surface for creating one supported text-like file under an exact opaque parent folder handle. Append-text is governed separately by v1.18. v1.12 is not permission to overwrite, rename, move, copy, delete, generate binary/documents, use raw paths, or run broad folder writes.

The v1.12 planning implementation:

- Exposes `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create-text operations without resolving the parent handle or writing iCloud Drive files.
- Requires exact opaque `icloud:file:v1:` parent folder handles.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned filenames, content, handles, content hashes, and approval fingerprints.

The v1.12 apply implementation:

- Exposes `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque parent folder handles internally before writing.
- Uses exclusive create so existing files are never overwritten.
- Returns read-back metadata and never logs filenames, content, handles, raw paths, content hashes, approval fingerprints, or approval tokens.

## v1.18 iCloud Drive Append Planning And Apply

The implemented v1.18 phase adds non-mutating iCloud Drive append-text planning and the approved apply-capable mutation surface for appending bounded UTF-8 text to one supported text-like file selected by exact opaque handle. It is not permission to overwrite, rename, move, copy, delete, generate binary/documents, use raw paths, or run broad folder writes.

The v1.18 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: append_text`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates the exact opaque `icloud:file:v1:` handle shape, expected current SHA-256, and bounded append text without resolving the handle or writing iCloud Drive files.
- Requires the caller to obtain `expected_current_sha256` from exact-handle iCloud Drive content retrieval.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned content, handles, content hashes, and approval fingerprints.

The v1.18 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: append_text`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves the exact opaque file handle internally.
- Reads the current normalized text content, refuses to append if the current SHA-256 differs from the approved plan, then appends bounded UTF-8 text.
- Returns read-back metadata plus the new content SHA-256 and never logs filenames, content, handles, raw paths, content hashes, approval fingerprints, or approval tokens.

## v1.13 Calendar Planning And Apply

The implemented v1.13 phase adds non-mutating Calendar create-event planning and the approved apply-capable mutation surface for creating one timed event in an explicit target calendar title. It is not permission to update, delete, move, create recurrence, add attendees/invitations, add alarms, create all-day events, guess a default calendar, or run bulk Calendar mutations.

The v1.13 planning implementation:

- Exposes `local-apple-data calendar plan` and MCP `calendar_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling EventKit or writing Calendar data.
- Requires explicit target calendar title, title, start timestamp, and end timestamp.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, calendar names, locations, notes, and approval fingerprints.

The v1.13 apply implementation:

- Exposes `local-apple-data calendar apply` and MCP `calendar_apply_change`.
- Requires the matching `calendar-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Calls EventKit only after approval checks pass.
- Resolves the target calendar by exact title and refuses missing or ambiguous calendars.
- Returns read-back metadata and never logs event titles, calendar names, locations, notes, raw EventKit identifiers, approval fingerprints, or approval tokens.

## v1.1 Mail Content Retrieval

The implemented v1.1 phase is exact-handle Mail content retrieval only. It is not permission to retrieve content by default.

The v1.1 implementation:

- Require a `mail:message:v2:` handle returned by `mail_search`.
- Add a `content_status` hint to Mail search results using a metadata-only local file-presence check; it does not read message bodies.
- Reject raw IDs, old handles, mailbox refs, direct paths, and fabricated handles.
- Return bounded plain text with truncation metadata.
- Exclude broad attachment export, inline attachment bytes, raw MIME, full headers, remote resources, Notes bodies, Reminder notes, broad content search, background indexing, and durable content caches. Exact selected Mail attachment export is governed separately by v1.21.
- Keep automated tests synthetic-only.
- Keep redacted event logs free of handles, subjects, bodies, warning messages, raw paths, and raw exceptions.

## v1.2 Notes Content Retrieval

The implemented v1.2 phase adds exact-handle Apple Notes content retrieval. It is not permission to retrieve Notes content by default or to run broad Notes exports.

The v1.2 implementation:

- Requires a `notes:note:v2:` handle returned by `notes_search`.
- Resolves the handle internally and derives the Notes app Core Data ID without returning or logging it.
- Reads one selected note through local Notes automation with a hard timeout.
- Returns bounded plain text with truncation metadata.
- Rejects raw IDs, old handles, fabricated handles, and direct paths.
- Excludes locked/deleted notes, source attachment paths, inline attachment bytes, raw database rows, local paths, broad content search, background indexing, and durable content caches.
- Keeps automated tests synthetic-only and verifies the live path only by redacted status/count output when explicitly requested.

## v1.20 Notes Attachment Export

The implemented v1.20 phase adds exact-handle Apple Notes attachment metadata and local export. It is not permission to run broad Notes exports or return attachment bytes inline.

The v1.20 implementation:

- Requires a `notes:note:v2:` handle returned by `notes_search` before listing attachments.
- Returns bounded metadata and opaque `notes:attachment:v1:` handles for attachments on that selected note.
- Exports one selected attachment only to a caller-selected output directory.
- Prefers locally available Notes media files and falls back to local database BLOB data when present.
- Does not return source media paths, remote attachment URLs, or attachment bytes inline.
- Does not fetch remote iCloud-only attachments.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, and export paths.

## v1.21 Mail Attachment Export

The implemented v1.21 phase adds exact-handle Apple Mail attachment metadata and local MIME attachment export. It is not permission to run broad Mail attachment exports, expose raw MIME/full headers, fetch externalized attachments, or mutate Mail attachments.

The v1.21 implementation:

- Requires a `mail:message:v2:` handle returned by `mail_search` before listing attachments.
- Returns bounded metadata and opaque `mail:attachment:v1:` handles for attachments on that selected message.
- Requires both the selected message handle and selected attachment handle before export, so export does not scan the whole Mail store to resolve a detached token.
- Exports one selected MIME attachment only to a caller-selected output directory.
- Does not return source `.emlx` paths, raw MIME, full headers, or attachment bytes inline.
- Reports externalized or partial-message attachments as unavailable when bytes are not in the local `.emlx`; it does not fetch remote or missing attachment data.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, source paths, and export paths.

## v1.22 Messages Attachment Export

The implemented v1.22 phase adds exact-handle Apple Messages attachment metadata and local export. It is not permission to run broad Messages attachment exports, reveal participant identifiers or source paths, fetch unavailable iCloud media, or mutate Messages.

The v1.22 implementation:

- Requires a `messages:chat:v1:` handle returned by `messages_search` before listing attachments.
- Returns bounded metadata and opaque `messages:attachment:v1:` handles for attachments linked to that selected chat.
- Requires both the selected chat handle and selected attachment handle before export, so export does not scan the whole Messages store to resolve a detached token.
- Exports one selected local attachment only to a caller-selected output directory.
- Does not return participant identifiers, chat GUIDs, attachment GUIDs, source media paths, or attachment bytes inline.
- Reports unavailable local media as unavailable and does not fetch remote or missing iCloud attachment data.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, source paths, and export paths.

## v1.3 iCloud Drive Content Retrieval

The implemented v1.3 phase adds exact-handle local iCloud Drive item metadata and supported text-file content retrieval. It is not permission to run broad file dumps or retrieve arbitrary binary/document contents by default.

The v1.3 implementation:

- Requires a `icloud:file:v1:` handle returned by `icloud-drive search`.
- Searches local iCloud Drive by filename only, with empty and broad queries rejected before scanning.
- Returns filenames, file/folder kind, extension, size, modified timestamp, depth, and opaque handle without raw local paths.
- Reads content only for supported text-like file suffixes and exact selected file handles.
- Returns bounded plain text with truncation metadata.
- Rejects direct paths, fabricated handles, hidden files, symlinks, unsupported binary/document types, broad content search, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.4 Calendar Event Retrieval

The implemented v1.4 phase adds EventKit-backed Calendar event title search and exact-handle event detail retrieval. It is not permission to run broad calendar dumps or mutate Calendar data.

The v1.4 implementation:

- Requires a `calendar:event:v1:` handle returned by `calendar search`.
- Searches local Calendar events by title only, with empty and broad queries rejected before EventKit access.
- Uses a non-prompting EventKit helper. If Calendar is not authorized for the current process, it returns a safe `calendar_access_unavailable` warning.
- Returns event title, calendar title, start/end dates, all-day flag, availability, and presence/count metadata during search.
- Reads event location and notes only for exact selected event handles.
- Returns bounded notes text with truncation metadata.
- Rejects raw EventKit identifiers, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.5 Reminders EventKit Retrieval

The implemented v1.5 phase adds EventKit-backed Reminders title search and exact-handle Reminder note retrieval. It is not permission to run broad Reminder dumps or mutate Reminders data.

The v1.5 implementation:

- Requires a `reminders:reminder:eventkit:v1:` handle returned by `reminders eventkit-search`.
- Searches local Reminders by title only, with empty and broad queries rejected before EventKit access.
- Uses the same non-prompting EventKit helper approach. If Reminders are not authorized for the current process, it returns a safe `reminders_access_unavailable` warning.
- Returns reminder title, list name, due/start dates, completion state, priority, and presence/count metadata during search.
- Reads reminder notes only for exact selected EventKit reminder handles.
- Returns bounded notes text with truncation metadata.
- Rejects raw EventKit identifiers, legacy SQLite reminder handles, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.6 Contacts Retrieval

The implemented v1.6 phase adds Contacts.framework-backed contact name/organization search and exact-handle contact detail retrieval. Contacts create-contact apply is separately approved by v1.14. v1.6 alone is not permission to run broad Contacts dumps, read contact notes/image data, update/delete Contacts, or mutate Contacts data outside the v1.14 create-contact gate.

The v1.6 implementation:

- Requires a `contacts:contact:v1:` handle returned by `contacts search`.
- Searches local Contacts by name, nickname, organization, department, or job title only, with empty and broad queries rejected before Contacts.framework access.
- Uses a non-prompting Contacts helper. If Contacts are not authorized for the current process, it returns a safe `contacts_access_unavailable` warning.
- Returns display name, contact type, organization/job metadata, count/presence metadata, and opaque handle during search.
- Reads email addresses, phone numbers, postal addresses, URLs, birthdays, dates, social profiles, instant-message addresses, and contact relations only for exact selected contact handles.
- Does not fetch `CNContactNoteKey`; Apple requires the `com.apple.developer.contacts.notes` entitlement for notes on macOS 13 and later.
- Does not return image bytes; image access remains a separate content gate.
- Rejects raw Contacts identifiers, fabricated handles, broad content search, update/delete/notes/image mutation, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.14 Contacts Create Apply

The implemented v1.14 phase adds non-mutating Contacts create-contact planning and the approved apply-capable mutation surface for creating one contact through Contacts.framework. It is not permission to update, delete, merge, move, add group membership, read or write notes, attach image data, mutate postal addresses, birthdays, relationships, social profiles, instant messages, or run bulk Contacts operations.

The v1.14 planning implementation:

- Exposes `local-apple-data contacts plan` and MCP `contacts_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling Contacts.framework or writing Contacts.
- Requires a person contact to include `given_name` or `family_name`.
- Requires an organization contact to include `organization_name`.
- Caps email, phone, and URL lists at five entries each.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned names, organizations, email addresses, phone numbers, URLs, handles, and approval fingerprints.

The v1.14 apply implementation:

- Exposes `local-apple-data contacts apply` and MCP `contacts_apply_change`.
- Requires the matching `contacts-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through Contacts.framework only after those checks.
- Returns bounded read-back contact detail through the existing Contacts detail shape.
- Keeps automated tests synthetic-only.

## v1.15 Notes Create Apply

The implemented v1.15 phase adds non-mutating Notes create-note planning and the approved apply-capable mutation surface for creating one plaintext note through Notes.app automation. The implemented v1.19 phase adds non-mutating Notes append-text planning and approved append-text apply for exact note handles plus expected current SHA-256. These gates are not permission to arbitrary update, delete, move, target folders/accounts, mutate rich text, create attachments, mutate locked/shared notes, manage Recently Deleted, or run bulk Notes operations.

The v1.15 planning implementation:

- Exposes `local-apple-data notes plan` and MCP `notes_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling Notes.app, reading Notes data, or writing Notes.
- Requires a bounded non-empty title and caps body text at 12000 normalized characters.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, body previews, handles, and approval fingerprints.

The v1.15 apply implementation:

- Exposes `local-apple-data notes apply` and MCP `notes_apply_change`.
- Requires the matching `notes-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through Notes.app automation only after those checks.
- Returns read-back content through the existing exact-handle Notes content shape.
- Keeps automated tests synthetic-only.

## v1.16 Mail Draft Create Apply

The implemented v1.16 phase adds non-mutating Mail create-draft planning and the approved apply-capable mutation surface for saving one plaintext draft through Mail.app automation. It is not permission to send, reply, forward, archive, move, delete, mark read/unread, flag, manage mailboxes/accounts, select sender accounts, attach files, create HTML/rich-text drafts, or run bulk Mail operations.

The v1.16 planning implementation:

- Exposes `local-apple-data mail plan` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create-draft operations without calling Mail.app, reading Mail data, or writing Mail.
- Requires at least one bounded To recipient and a bounded non-empty subject.
- Caps body text at 12000 normalized characters.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned recipients, subjects, body previews, handles, and approval fingerprints.

The v1.16 apply implementation:

- Exposes `local-apple-data mail apply` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through save-only Mail.app automation after those checks and does not call `send`.
- Returns read-back through the existing exact-handle Mail content shape when the local Drafts store indexes the saved draft.
- Returns `partial` if Mail.app accepts the draft save but read-back is not available yet.
- Keeps automated tests synthetic-only.

## v1.17 Photos Import Apply

The implemented v1.17 phase adds non-mutating Photos import planning and the approved apply-capable mutation surface for importing one caller-selected local image or video file through PhotoKit. It is not permission to edit, delete, target albums, mutate hidden/favorite/metadata state, return thumbnails, return inline asset bytes, fetch missing iCloud media over the network, or run bulk Photos operations.

The v1.17 planning implementation:

- Exposes `local-apple-data photos plan` and MCP `photos_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested import operations without calling PhotoKit or writing Photos.
- Requires a caller-selected regular local image or video source file.
- Refuses symlinks, directories, empty files, unsupported media types, media-type mismatches, and oversized files.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Returns source filename, media type, file size, and source-file hash in the transient preview response.
- Does not echo the raw source path.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of source paths, source filenames, source hashes, PhotoKit identifiers, handles, and approval fingerprints.

The v1.17 apply implementation:

- Exposes `local-apple-data photos apply` and MCP `photos_apply_change`.
- Requires the matching `photos-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying so changed source bytes invalidate stale approval tokens.
- Applies through a Swift PhotoKit helper and `PHPhotoLibrary.performChanges`.
- Returns read-back metadata for the created asset through the existing opaque-handle Photos detail shape.
- Keeps automated tests synthetic-only.

## v1.24 Messages Send-Text Apply

The implemented v1.24 phase adds non-mutating Messages send-text planning and the approved apply-capable mutation surface for sending one bounded plaintext message to one exact existing chat through Messages.app automation. It is not permission to send to direct recipients, create chats, choose SMS fallback or outgoing accounts, send files, react/tapback, edit, unsend, delete, mark read, manage groups, expose participants, or run bulk Messages operations.

The v1.24 planning implementation:

- Exposes `local-apple-data messages plan` and MCP `messages_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested send-text operations without calling Messages.app or writing Messages data.
- Requires exact opaque `messages:chat:v1:` handles for target-chat planning.
- Returns bounded body preview text, body length, deterministic idempotency keys, and approval fingerprints for the apply gate.
- Binds approval to current chat state, including message count and last-message row.
- Keeps redacted event logs free of body text, body previews, body hashes, chat GUIDs, handles, participant identifiers, and approval fingerprints.
- Keeps automated tests synthetic-only.

The v1.24 apply implementation:

- Exposes `local-apple-data messages apply` and MCP `messages_apply_change`.
- Requires the matching `messages-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying so changed body text or changed chat state invalidates stale approval tokens.
- Applies through Messages.app AppleScript only after approval checks pass.
- Returns success only after local `chat.db` read-back confirms a newer outgoing row joined to the selected chat with matching body hash.
- Detects empty unjoined outgoing ghost rows and returns a non-success status.
- Does not echo the sent body text in apply read-back.
- Keeps automated tests synthetic-only.

## v1.7 Photos Asset Detail Retrieval

The implemented v1.7 phase adds PhotoKit-backed Photos original-filename search, exact-handle asset resource metadata retrieval, and exact-handle asset export to a caller-selected output directory. It is not permission to run broad Photos dumps, return image/video bytes inline, fetch missing iCloud media over the network, or mutate Photos data.

The v1.7 implementation:

- Requires a `photos:asset:v1:` handle returned by `photos search`.
- Searches local Photos by original filename only, with empty and broad queries rejected before PhotoKit access.
- Uses a non-prompting PhotoKit helper. If Photos are not authorized for the current process, it returns a safe `photos_access_unavailable` warning.
- Returns media type, dimensions, dates, favorite/hidden flags, source type, primary filename, resource count, and opaque handle during search.
- Reads asset resource filenames, resource types, and uniform type identifiers only for exact selected asset handles.
- Does not return image/video bytes inline, thumbnails, raw Photos identifiers, or source paths. Export returns only caller-selected destination metadata.
- Rejects raw Photos identifiers, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.8 Messages Chat Transcript Retrieval

The implemented v1.8 phase adds read-only Messages chat display-name search and exact-handle bounded chat transcript retrieval. It is not permission to run broad Messages text search, expose participant phone/email identifiers, or mutate/send Messages.

The v1.8 implementation:

- Requires a `messages:chat:v1:` handle returned by `messages search`.
- Searches local Messages chats by chat display name only, with empty and broad queries rejected before opening `chat.db`.
- Opens `~/Library/Messages/chat.db` read-only and query-only.
- Returns chat display name, service name, participant count, message count, last message date, and opaque handle during search.
- Reads recent message text only for exact selected chat handles, with `max_messages` and `max_chars` caps. When modern Messages rows leave `message.text` empty, it may decode bounded plaintext from the local `message.attributedBody` typedstream value.
- Does not return participant phone numbers, email addresses, chat GUIDs, raw message IDs, attachments, raw attributed-body blobs, attributed-string attributes, tapbacks/reactions, or send-state metadata.
- Rejects raw row IDs, raw chat GUIDs, fabricated handles, broad message-text search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.9 Voice Memos Transcript Retrieval

The implemented v1.9 phase adds read-only Voice Memos title/filename search, exact-handle existing embedded transcript retrieval, and exact-handle `.m4a` export to a caller-selected output directory. It is not permission to run broad transcript search, return audio bytes inline, generate transcripts, or mutate Voice Memos data.

The v1.9 implementation:

- Requires a `voice_memos:recording:v1:` handle returned by `voice-memos search`.
- Searches local Voice Memos by title or filename only, with empty and broad queries rejected before opening `CloudRecordings.db`.
- Opens the local Voice Memos `CloudRecordings.db` read-only and query-only.
- Returns title, recorded date, duration, local audio availability, and opaque handle during search.
- Reads existing Apple-generated transcript JSON only for exact selected recording handles when a local `.m4a` contains the `tsrp` atom.
- Returns bounded transcript text with truncation metadata and never returns audio bytes inline, raw source file paths, or recording identifiers.
- Rejects raw recording IDs, fabricated handles, broad transcript search, generated transcription, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.25 Safari Bookmarks And Reading List

The implemented v1.25 phase adds read-only Safari bookmark and Reading List search plus exact-handle URL detail. It is not permission to read Safari history, open tabs, private browsing data, passwords, cookies, sessions, page content, browser caches, or to mutate bookmarks.

The v1.25 implementation:

- Requires a `safari:item:v1:` handle returned by `safari search` before returning a full URL.
- Searches local Safari `Bookmarks.plist` by title or URL, with empty and broad queries rejected before reading the store.
- Returns title, kind, URL domain, URL scheme, query-presence, path depth, dates when present, and opaque handle during search.
- Does not return full URLs during search.
- Reads and returns the full URL only for exact selected handles.
- Rejects raw identifiers, fabricated handles, Safari history, open tabs, private browsing data, passwords, cookies, browser caches, page content, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.26 Shortcuts Metadata

The implemented v1.26 phase adds read-only Apple Shortcuts shortcut/folder name metadata search plus exact-handle metadata detail. It is not permission to run, open, view, sign, export, inspect, or mutate shortcuts.

The v1.26 implementation:

- Requires a `shortcuts:item:v1:` handle returned by `shortcuts search` before exact metadata detail.
- Searches local Shortcuts through Apple's `shortcuts list --show-identifiers` and `shortcuts list --folders --show-identifiers` commands, with empty and broad queries rejected before invoking the CLI.
- Returns title, kind, identifier-presence, and opaque handle during search.
- Does not return raw Shortcuts identifiers, shortcut bodies, action graphs, source paths, icons, colors, URL schemes, or generated dynamic run tools.
- Refuses folder-scoped searches so handles always resolve from the same global metadata flow.
- Rejects fabricated handles, shortcut run/open/view/sign/export/body/action-graph/mutation, Shortcuts SQLite scraping, private iCloud APIs, browser/keychain access, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.10 Hide My Email Inferred Alias Retrieval

The implemented v1.10 phase adds read-only inferred Hide My Email alias search from local Mail address metadata and exact-handle alias detail retrieval. It is not an authoritative iCloud Hide My Email inventory, and it is not permission to create, deactivate, delete, or manage aliases.

The v1.10 implementation:

- Requires a `hide_my_email:alias:v1:` handle returned by `hide-my-email search` before returning a full alias.
- Searches local Mail `addresses`, `messages`, and `recipients` metadata only, with empty, domain-only, and generic queries rejected before opening the Mail store.
- Returns masked alias previews, domain, inference kind, confidence, message-count metadata, provenance, and `authoritative_inventory:false` during search.
- Reads and returns the full alias only for exact selected handles.
- Distinguishes high-confidence Sign in with Apple private relay aliases from medium-confidence iCloud Hide My Email-like aliases inferred from local Mail evidence.
- Rejects raw identifiers, fabricated handles, broad domain searches, iCloud.com/browser automation, private iCloud web APIs, keychain credentials, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.
