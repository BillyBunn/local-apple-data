# Threat Model

This plugin is for local, metadata-first access to locally synced Apple data, with exact-handle content/detail retrieval for selected Mail messages, Messages chats, inferred Hide My Email aliases, Voice Memos, Notes, Calendar events, Contacts, Photos asset/resource metadata, Reminders, and supported iCloud Drive text files. The only approved mutation surfaces are Reminders create/complete/due-date apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, Mail create-draft apply, and Photos import apply through plan/apply/read-back gates.

## Assets

- Local Mail, Notes, and Reminders databases.
- Local Messages `chat.db`.
- Local Mail address metadata that may contain Hide My Email or Sign in with Apple private relay aliases.
- Local Voice Memos `CloudRecordings.db` and local `.m4a` recording files.
- Local Calendar EventKit data.
- Local Contacts.framework data.
- Local Photos PhotoKit asset metadata.
- Local iCloud Drive file/folder metadata and supported text-file content.
- Search-result metadata: subjects, Messages chat display names, masked inferred Hide My Email alias previews, Voice Memo titles, note titles/snippets, Calendar event titles, contact names/organizations, Photos filenames/asset metadata, iCloud Drive filenames, reminder titles, dates, flags, and opaque handles.
- Exact Mail content returned transiently for one selected `mail:message:v2:` handle.
- Exact Messages transcript returned transiently for one selected `messages:chat:v1:` handle.
- Exact inferred Hide My Email alias returned transiently for one selected `hide_my_email:alias:v1:` handle.
- Exact Voice Memos transcript returned transiently for one selected `voice_memos:recording:v1:` handle when already embedded locally.
- Exact Notes content returned transiently for one selected `notes:note:v2:` handle.
- Exact Calendar event location/notes returned transiently for one selected `calendar:event:v1:` handle.
- Exact Contact details returned transiently for one selected `contacts:contact:v1:` handle.
- Exact Photos asset/resource metadata returned transiently for one selected `photos:asset:v1:` handle.
- Exact Reminder notes returned transiently for one selected `reminders:reminder:eventkit:v1:` handle.
- Non-mutating Reminder plan previews returned transiently for requested future create/complete/update-due-date workflows.
- Exact iCloud Drive text content returned transiently for one selected `icloud:file:v1:` handle.
- Non-mutating iCloud Drive create-text plan previews returned transiently for requested future file creates.
- Non-mutating Calendar create-event plan previews returned transiently for requested future timed-event creates.
- Non-mutating Contacts create-contact plan previews returned transiently for requested future contact creates.
- Non-mutating Notes create-note plan previews returned transiently for requested future note creates.
- Non-mutating Mail create-draft plan previews returned transiently for requested future draft creates.
- Local handle secret under `~/.local/state/local-apple-data/handle-secret.key`.
- Redacted event log under `~/.local/state/local-apple-data/events.jsonl`.

## Non-Goals

- No attachments, broad content search, durable content caches, raw database rows, raw framework identifiers, raw local file paths, unsupported/binary iCloud Drive content extraction, Contact notes/image data, inline Photos image/video bytes, inline Voice Memos audio bytes, generated transcription, broad Messages text search, broad Voice Memos transcript search, broad Reminder note retrieval, authoritative Hide My Email inventory, or Hide My Email creation/deactivation/deletion.
- No Gmail connector, Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or network mail access.
- No mutation of Mail, Notes, Hide My Email, Gmail, iCloud, TCC, launchd, Codex config, or OpenClaw state outside the approved Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail draft, and Photos import apply gates.
- Reminders mutation is limited to create, complete, and due-date update through the approved plan/apply/read-back gate. No Reminders delete, bulk, list/account, attachment, URL, rich-content, or uncomplete mutation is approved.
- iCloud Drive mutation is limited to creating one supported text-like file through the approved plan/apply/read-back gate. No append, overwrite, rename, move, copy, delete, binary/document write, broad folder write, hidden-file write, symlink/package traversal, or raw path write is approved.
- Calendar mutation is limited to creating one timed event in an explicit target calendar title through the approved plan/apply/read-back gate. No update, delete, move, recurrence, attendees, invitations, URLs, alarms, attachments, travel time, availability change, all-day event, default-calendar guessing, or bulk Calendar mutation is approved.
- Contacts mutation is limited to creating one contact through the approved plan/apply/read-back gate. No update, delete, merge, move, group membership, postal address, birthday, relationship, social profile, instant message, note, image, or bulk Contacts mutation is approved.
- Notes mutation is limited to creating one plaintext note through the approved plan/apply/read-back gate. No append, update, delete, move, folder/account targeting, rich-text editing, checklist state, attachment, locked/shared-note, Recently Deleted, or bulk Notes mutation is approved.
- Mail mutation is limited to saving one plaintext draft through the approved plan/apply/read-back gate. No send, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, sender-account selection, attachment, HTML/rich-text draft, template, or bulk Mail mutation is approved.
- Photos mutation is limited to importing one caller-selected image or video file through the approved plan/apply/read-back gate. No edit, delete, album targeting, hidden/favorite/metadata mutation, thumbnail generation, inline asset byte return, network iCloud fetch, URL import, or bulk Photos mutation is approved.
- No background indexing or durable personal-metadata cache.

## Main Risks And Mitigations

- Broad data dumps: empty, wildcard-only, and one-character searches are rejected before opening local stores.
- Handle guessing and correlation: Mail and Notes exact fetches require fully opaque v2 HMAC handles from search output; Messages, inferred Hide My Email aliases, Voice Memos, Calendar, Contacts, Photos, Reminders, and iCloud Drive exact fetches require opaque handles. Legacy raw row IDs, raw framework identifiers, raw alias identifiers, raw recording identifiers, older encoded-ID handles, and direct paths are rejected.
- Content overreach: Mail search exposes only a metadata-only `content_status` availability hint. Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive content/detail retrieval require exact opaque handles, clamp output to a hard maximum where text is returned, skip attachments and unsupported file types, and return only parsed/plain text, exact selected alias detail, or bounded chat/voice/event/contact/photo/reminder details.
- Hide My Email overclaiming: v1.10 returns `authoritative_inventory:false` and provenance for local Mail address inference. It does not use iCloud account inventory, browser sessions, keychain credentials, or private iCloud web APIs.
- Notes automation hangs or permission prompts: Notes content retrieval uses a hard local automation timeout and returns safe warning codes instead of blocking indefinitely or leaking raw exceptions.
- Calendar, Contacts, Photos, and Reminders permission prompts: framework access uses non-prompting helpers; unavailable permissions return safe warning codes instead of requesting TCC access automatically.
- Contact notes and images: Contacts exact detail does not fetch `CNContactNoteKey` or image bytes; those require separate entitlement/content gates.
- Photos bytes, export paths, and import source paths: Photos exact detail does not return thumbnails, originals, edited assets, videos, or raw file paths. Photos exact export writes one selected local PhotoKit resource to a caller-selected output directory and returns destination metadata only. Photos import accepts a caller-selected source path as input but does not echo or log the raw source path; source filename and hash appear only in transient preview/apply responses.
- Messages participant leakage: Messages search and exact transcript retrieval do not return phone numbers, email addresses, chat GUIDs, raw row IDs, or attachment paths.
- Voice Memos audio/path leakage: Voice Memos exact retrieval parses only an existing local transcript atom unless export is explicitly requested. Voice Memos exact export copies one selected `.m4a` to a caller-selected output directory and does not return inline audio bytes, raw source recording paths, or recording identifiers.
- iCloud Drive traversal overreach: searches are filename-only, capped, skip hidden files and symlinks, and do not return raw local paths.
- Unauthorized iCloud Drive apply: `icloud-drive apply` and `icloud_drive_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, resolve only exact opaque parent folder handles, keep targets under the configured root, use exclusive create, and return read-back metadata.
- Unauthorized Calendar apply: `calendar apply` and `calendar_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, resolve only an explicit target calendar title through EventKit, refuse ambiguous calendars, create only one timed event, and return read-back metadata.
- Unauthorized Contacts apply: `contacts apply` and `contacts_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, create only one bounded contact through Contacts.framework, and return read-back detail.
- Unauthorized Notes apply: `notes apply` and `notes_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, create only one bounded plaintext note through Notes.app automation, and return exact-content read-back.
- Unauthorized Mail apply: `mail apply` and `mail_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, create only one bounded plaintext draft through save-only Mail.app automation, avoid the `send` command, and return local Drafts read-back when available.
- Local path leakage: store and SQLite warnings use safe generic messages; health store paths are `~/...` labels; tool paths are redacted.
- Log leakage: event logs include command/status/source/result count/warning codes/privacy flags only, not queries, results, warning messages, or content.
- Schema and readiness drift: health and doctor use store-readability checks, schema-only checks for Mail, Messages, Voice Memos, Notes, and Reminders, iCloud Drive root checks, non-prompting framework access requirements, and safe warning codes; doctor gives non-mutating remediation guidance.
- Planning confused with mutation: Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail, and Photos planning use `plan` naming, read-only MCP annotations, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and no write calls. Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail, and Photos apply use separate non-read-only MCP annotations.
- Unauthorized Reminder apply: `reminders apply` and `reminders_apply_change` recompute the plan, require the matching approval token, require explicit confirmation, check expected state, apply through EventKit only after those checks, and return read-back metadata.
- Mail version drift: Mail store discovery chooses the highest existing local Envelope Index path without exposing the raw path in normal output.
- Runtime cache drift: local install verification can compare project source, personal/plugin source, and installed cache key files.
- Runtime dependency drift: MCP startup uses `scripts/run_mcp_server.sh` to prefer the plugin-local `.venv`, then an optional `LOCAL_APPLE_DATA_PROJECT_VENV`, before attempting fallback dependency resolution.

## Review Gates

Before installing a new version:

1. Run `uv run pytest`.
2. Run `uv run python -m compileall src tests`.
3. Run the plugin and skill validators.
4. Run `uv run python scripts/audit_mutation_gates.py`.
5. Run `uv run python scripts/verify_runtime.py`.
6. If testing a local Codex plugin install, sync to the configured personal plugin source.
7. Reinstall through the configured local marketplace.
8. Run `uv run python scripts/verify_runtime.py` and `uv run python scripts/audit_mutation_gates.py` from the installed cache.

Any attachment retrieval, mutation beyond the approved Reminders create/complete/due-date apply surface, iCloud Drive create-text apply surface, Calendar create-event apply surface, Contacts create-contact apply surface, Notes create-note apply surface, Mail create-draft apply surface, and Photos import apply surface, background indexing, arbitrary document extraction, Contact update/delete/note/image retrieval, Notes append/update/delete/move/rich-text mutation, Mail send/reply/forward/archive/move/delete/mark/flag/mailbox-account mutation, Photos edit/delete/album/metadata mutation, generated transcription, broad Messages text search, broad Voice Memos transcript search, broad Reminder content search, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API access, browser/keychain credential access, or connector fallback requires a separate explicit design and approval gate.

The implemented v1.1 gate is `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`. It added exact-handle Mail content retrieval only.
The implemented v1.2/v1.3/v1.4/v1.5/v1.6/v1.7/v1.8/v1.9/v1.10 gate is `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`. It adds exact-handle Notes content retrieval, exact-handle supported iCloud Drive text-file retrieval, exact-handle Calendar event detail retrieval, exact-handle Reminder note retrieval, exact-handle Contact detail retrieval, exact-handle Photos asset/resource metadata and export, exact-handle Messages chat transcript retrieval, exact-handle Voice Memos existing transcript and audio export, and exact-handle inferred Hide My Email alias detail while keeping attachments, broad content search, background indexing, connector fallback, private iCloud web/API access, and mutation out of scope.
The implemented v1.11 gate is `docs/V1_11_REMINDERS_WRITE_DESIGN.md`. It adds non-mutating Reminders planning and the approved Reminders apply surface while keeping every other Reminders mutation surface out of scope.
The implemented v1.12 gate is `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`. It adds non-mutating iCloud Drive create-text planning and the approved iCloud Drive create-text apply surface while keeping every other iCloud Drive mutation surface out of scope.
The implemented v1.13 gate is `docs/V1_13_CALENDAR_WRITE_DESIGN.md`. It adds non-mutating Calendar create-event planning and the approved Calendar create-event apply surface while keeping every other Calendar mutation surface out of scope.
The implemented v1.14 gate is `docs/V1_14_CONTACTS_WRITE_DESIGN.md`. It adds non-mutating Contacts create-contact planning and the approved Contacts create-contact apply surface while keeping every other Contacts mutation surface out of scope.
The implemented v1.15 gate is `docs/V1_15_NOTES_WRITE_DESIGN.md`. It adds non-mutating Notes create-note planning and the approved Notes create-note apply surface while keeping every other Notes mutation surface out of scope.
The implemented v1.16 gate is `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`. It adds non-mutating Mail create-draft planning and the approved Mail create-draft apply surface while keeping every other Mail mutation surface out of scope.
The implemented v1.17 gate is `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`. It adds non-mutating Photos import planning and the approved Photos import apply surface while keeping every other Photos mutation surface out of scope.
