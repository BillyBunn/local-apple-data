# Privacy Model

This project handles local personal-data surfaces. The default is metadata-first and read-only, with content retrieval exposed only through exact opaque handles and bounded output.

## Data Tiers

1. Health: tool availability, macOS version, and store presence/readability only.
2. Metadata: bounded subjects/titles/snippets and Mail content-availability hints only when the user asks for the workflow.
3. Content/detail/export: exact-handle retrieval for Mail, Messages chats, inferred Hide My Email aliases, Voice Memos, Notes, Calendar events, Contacts, Photos asset/resource metadata, Reminders, and supported iCloud Drive text files after the metadata flow returns a `mail:message:v2:`, `messages:chat:v1:`, `hide_my_email:alias:v1:`, `voice_memos:recording:v1:`, `notes:note:v2:`, `calendar:event:v1:`, `contacts:contact:v1:`, `photos:asset:v1:`, `reminders:reminder:eventkit:v1:`, or `icloud:file:v1:` handle and the user explicitly requests that selected item. Media export tools additionally require a caller-selected output directory and do not return media bytes inline.
4. Attachments: metadata only until a later approved phase.
5. Preview: non-mutating Reminders future-change planning for exact requested create/complete/update-due-date workflows.
6. Mutation: deferred until a separate design and approval phase.

## Never Persist

Do not persist any of the following in logs, docs, prompts, fixtures, tests, commits, or durable plan files:

- Message bodies
- Messages transcripts outside exact selected responses
- Full Hide My Email aliases outside exact selected responses
- Voice Memos transcript text outside exact selected responses
- Voice Memos audio bytes in chat, source recording paths, and raw recording identifiers
- Note bodies
- Calendar event notes and locations
- Contact email addresses, phone numbers, postal addresses, URLs, relations, and dates
- Contact notes and image data
- Photo asset bytes in chat, thumbnails, raw Photos identifiers, and asset/resource metadata outside exact selected responses
- Reminder titles or notes
- Reminder planning titles or notes outside transient preview responses
- iCloud Drive file contents or raw local paths
- Attachment content
- Full email addresses
- Raw Hide My Email identifiers
- Account identifiers
- Raw database rows
- Credentials, tokens, app passwords, cookies, OAuth artifacts, keychain data, or environment secrets

Opaque search-result handles are allowed. Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive handles are signed with a local secret so exact metadata fetches cannot be performed with guessed database row IDs, raw framework identifiers, raw alias identifiers, recording identifiers, or direct local paths. The same handles gate exact content/detail retrieval. The handle secret lives under the local plugin state directory and must not be printed or copied into durable docs.

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
- Mutating Mail, Notes, Reminders, Gmail, or iCloud state
- Adding direct network mail access
- Adding authoritative Hide My Email inventory or Hide My Email creation/deactivation/deletion
- Adding private iCloud web/API access, iCloud.com automation, browser sessions, or keychain credential access
- Adding new content classes beyond exact-handle Mail, Messages chat transcripts, inferred Hide My Email aliases, Voice Memos existing embedded transcripts/audio export, Notes, Calendar event detail, Contact detail, Photos asset/resource metadata/export, Reminder notes, and supported iCloud Drive text-file retrieval

## v1.11 Reminders Planning

The implemented v1.11 phase adds non-mutating Reminders planning only. It is not permission to apply, create, complete, update, or delete Reminders.

The v1.11 implementation:

- Exposes `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:false`.
- Validates requested create, complete, and update-due-date operations without calling EventKit or writing Reminders.
- Requires exact opaque `reminders:reminder:eventkit:v1:` handles for existing-reminder operation planning.
- Returns deterministic idempotency and approval fingerprints for a future apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, notes, handles, list names, and approval fingerprints.

## v1.1 Mail Content Retrieval

The implemented v1.1 phase is exact-handle Mail content retrieval only. It is not permission to retrieve content by default.

The v1.1 implementation:

- Require a `mail:message:v2:` handle returned by `mail_search`.
- Add a `content_status` hint to Mail search results using a metadata-only local file-presence check; it does not read message bodies.
- Reject raw IDs, old handles, mailbox refs, direct paths, and fabricated handles.
- Return bounded plain text with truncation metadata.
- Exclude attachments, raw MIME, full headers, remote resources, Notes bodies, Reminder notes, broad content search, background indexing, and durable content caches.
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
- Excludes locked/deleted notes, attachments, raw database rows, local paths, broad content search, background indexing, and durable content caches.
- Keeps automated tests synthetic-only and verifies the live path only by redacted status/count output when explicitly requested.

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

The implemented v1.6 phase adds Contacts.framework-backed contact name/organization search and exact-handle contact detail retrieval. It is not permission to run broad Contacts dumps, read contact notes/image data, or mutate Contacts data.

The v1.6 implementation:

- Requires a `contacts:contact:v1:` handle returned by `contacts search`.
- Searches local Contacts by name, nickname, organization, department, or job title only, with empty and broad queries rejected before Contacts.framework access.
- Uses a non-prompting Contacts helper. If Contacts are not authorized for the current process, it returns a safe `contacts_access_unavailable` warning.
- Returns display name, contact type, organization/job metadata, count/presence metadata, and opaque handle during search.
- Reads email addresses, phone numbers, postal addresses, URLs, birthdays, dates, social profiles, instant-message addresses, and contact relations only for exact selected contact handles.
- Does not fetch `CNContactNoteKey`; Apple requires the `com.apple.developer.contacts.notes` entitlement for notes on macOS 13 and later.
- Does not return image bytes; image access remains a separate content gate.
- Rejects raw Contacts identifiers, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
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
- Reads recent message text only for exact selected chat handles, with `max_messages` and `max_chars` caps.
- Does not return participant phone numbers, email addresses, chat GUIDs, raw message IDs, attachments, attributed bodies, tapbacks/reactions, or send-state metadata.
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
