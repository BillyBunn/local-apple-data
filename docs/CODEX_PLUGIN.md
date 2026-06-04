# Codex Plugin Packaging

This repo is a local Codex plugin root.

For the public support matrix, see `docs/CAPABILITY_MATRIX.md`. For installation, see `docs/INSTALL.md`. For future write/mutation gates, see `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, `docs/V1_11_REMINDERS_WRITE_DESIGN.md`, `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`, `docs/V1_13_CALENDAR_WRITE_DESIGN.md`, `docs/V1_14_CONTACTS_WRITE_DESIGN.md`, `docs/V1_15_NOTES_WRITE_DESIGN.md`, `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`, `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`, `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`, and `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`. For release readiness, see `docs/PUBLISHING.md`.

Plugin components:

- `.codex-plugin/plugin.json`: local plugin manifest.
- `.mcp.json`: stdio MCP server entry that launches `scripts/run_mcp_server.sh`.
- `scripts/run_mcp_server.sh`: runtime launcher that uses the plugin `.venv` when present, falls back to the project `.venv`, then falls back to `uv run --no-project --with mcp`.
- `skills/local-apple-data/SKILL.md`: model-facing workflow rules for using the local data tools safely.
- `skills/local-apple-data/agents/openai.yaml`: Codex UI/dependency metadata for the skill.

## Validation

Run these from the repo root:

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
swiftc -typecheck scripts/eventkit_helper.swift
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
uv run local-apple-data health --json
```

Also run the plugin and skill validator scripts when those local validator helpers are installed in the current Codex skills cache.

`uv run local-apple-data health --json` is safe because it reports redacted readiness and schema-only checks. Search tools can print local metadata and should only be run for a specific user-requested workflow.

Search, exact metadata, and exact Mail/Messages/inferred Hide My Email/Voice Memos/Notes/Calendar/Contacts/Photos/Reminders/iCloud Drive content tools use opaque handles. Mail search results include a metadata-only `content_status` hint; prefer `available` handles for exact Mail content retrieval, and treat `unavailable` or `unknown` as a reason to skip or report before calling `mail_get_content`. Messages transcript retrieval must use a `messages:chat:v1:` handle returned by `messages_search`. Hide My Email exact alias detail must use a `hide_my_email:alias:v1:` handle returned by `hide_my_email_search`; search output is masked local Mail evidence with `authoritative_inventory:false`, not an iCloud inventory. Voice Memos transcript retrieval and audio export must use a `voice_memos:recording:v1:` handle returned by `voice_memos_search`; export requires a caller-selected output directory and does not return audio bytes inline. Notes content retrieval must use a `notes:note:v2:` handle returned by `notes_search`; long imported notes can be paged with `offset` and `next_offset`. Calendar event detail retrieval must use a `calendar:event:v1:` handle returned by `calendar_search`. Contact detail retrieval must use a `contacts:contact:v1:` handle returned by `contacts_search`. Photos asset detail and asset export must use a `photos:asset:v1:` handle returned by `photos_search`; export requires a caller-selected output directory and does not return image/video bytes inline. Reminder note retrieval must use a `reminders:reminder:eventkit:v1:` handle returned by `reminders_eventkit_search`. iCloud Drive text-file content retrieval must use an `icloud:file:v1:` handle returned by `icloud_drive_search`. Do not fabricate handles or retry older raw row-ID/direct-path/framework-id/raw-alias handles if a get call returns `invalid_handle`; run a narrow search and use the returned handle.

Reminders planning is non-mutating. `local-apple-data reminders plan` and MCP `reminders_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. They do not call EventKit, read Reminders, or modify Reminders.

Reminders apply is one approved mutation surface. `local-apple-data reminders apply` and MCP `reminders_apply_change` require the matching `reminders-apply:v1:<approval_fingerprint>` token, explicit confirmation, operation-specific expected state, EventKit apply, and read-back verification.

iCloud Drive create-text and append-text planning are non-mutating. `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. Create-text planning does not resolve the parent handle or write iCloud Drive files. Append-text planning validates the exact file handle shape, expected current SHA-256, and bounded append text without resolving the file or writing iCloud Drive files.

iCloud Drive create-text and append-text apply are one approved mutation surface exposed through `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`. Create-text apply requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token, explicit confirmation, an exact opaque parent folder handle, exclusive create, and read-back verification. Append-text apply requires the matching token, explicit confirmation, an exact opaque file handle, expected current content SHA-256 from exact content retrieval, drift refusal, bounded UTF-8 append, and read-back hash verification.

Calendar create-event planning is non-mutating. `local-apple-data calendar plan` and MCP `calendar_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. They do not call EventKit or write Calendar data.

Calendar create-event apply is one approved mutation surface. `local-apple-data calendar apply` and MCP `calendar_apply_change` require the matching `calendar-apply:v1:<approval_fingerprint>` token, explicit confirmation, an explicit target calendar title, EventKit apply, and read-back verification.

Contacts create-contact apply is one approved mutation surface. `local-apple-data contacts apply` and MCP `contacts_apply_change` require the matching `contacts-apply:v1:<approval_fingerprint>` token, explicit confirmation, Contacts.framework apply, and read-back verification. Contact update, delete, merge, move, group membership, notes, image data, postal addresses, birthdays, relationships, social profiles, instant messages, and bulk operations remain blocked.

Notes create-note and append-text planning are non-mutating. `local-apple-data notes plan` and MCP `notes_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. Create-note planning does not call Notes.app, read Notes data, or write Notes data. Append-text planning validates the exact note handle shape, expected current SHA-256, and bounded append text without resolving the note or writing Notes data.

Notes create-note and append-text apply are one approved mutation surface exposed through `local-apple-data notes apply` and MCP `notes_apply_change`. Create-note apply requires the matching `notes-apply:v1:<approval_fingerprint>` token, explicit confirmation, Notes.app automation, and exact-content read-back verification. Append-text apply requires the matching token, explicit confirmation, an exact opaque note handle, expected current content SHA-256 from exact content retrieval, drift refusal, bounded plaintext append, shared/locked-note refusal, and exact-content read-back hash verification. Notes arbitrary update, delete, move, folder/account targeting, rich text, attachments, locked/shared-note mutation, and bulk operations remain blocked.

Mail create-draft planning is non-mutating. `local-apple-data mail plan` and MCP `mail_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. They do not call Mail.app, read Mail data, or write Mail data.

Mail create-draft apply is one approved mutation surface. `local-apple-data mail apply` and MCP `mail_apply_change` require the matching `mail-apply:v1:<approval_fingerprint>` token, explicit confirmation, save-only Mail.app automation, and local Drafts read-back verification when available. Mail send, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, sender-account selection, attachments, HTML/rich-text drafts, and bulk operations remain blocked.

Photos import planning is non-mutating. `local-apple-data photos plan` and MCP `photos_plan_change` return `mutation_applied:false`, `apply_available:true`, source-file hash/idempotency metadata, and an approval fingerprint for the approved apply gate. They do not call PhotoKit or write Photos data.

Photos import apply is one approved mutation surface. `local-apple-data photos apply` and MCP `photos_apply_change` require the matching `photos-apply:v1:<approval_fingerprint>` token, explicit confirmation, source-file hash binding, PhotoKit import, and created-asset read-back verification. Photos edit, delete, album targeting, hidden/favorite/metadata mutation, thumbnails, inline asset bytes, network iCloud fetch, and bulk operations remain blocked.

## Current Boundaries

- This package is local-only and metadata-first. The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply.
- It provides Mail content retrieval only for one exact `mail:message:v2:` handle selected from metadata output.
- It provides Mail create-draft planning as a non-mutating preview and Mail create-draft apply only after matching approval-token, bounded recipient/subject/body input, save-only Mail.app automation, and explicit-confirmation checks.
- It provides Messages chat transcript retrieval only for one exact `messages:chat:v1:` handle selected from chat display-name metadata output.
- It provides inferred Hide My Email alias detail only for one exact `hide_my_email:alias:v1:` handle selected from masked local Mail address metadata output.
- It provides Voice Memos transcript retrieval and `.m4a` export only for one exact `voice_memos:recording:v1:` handle selected from title/filename metadata output.
- It provides Notes content retrieval only for one exact `notes:note:v2:` handle selected from metadata output, with bounded pagination for long imported notes.
- It provides Notes create-note and append-text planning as non-mutating previews and Notes create/append-text apply only after matching approval-token, bounded content, operation-specific exact-handle/hash checks, Notes.app automation, and explicit-confirmation checks.
- It provides Calendar event detail retrieval only for one exact `calendar:event:v1:` handle selected from metadata output.
- It provides Calendar create-event planning as a non-mutating preview and Calendar create-event apply only after matching approval-token, explicit target calendar title, timed-event inputs, and explicit-confirmation checks.
- It provides Contact detail retrieval only for one exact `contacts:contact:v1:` handle selected from Contacts metadata output.
- It provides Contacts create-contact planning as a non-mutating preview and Contacts create-contact apply only after matching approval-token, bounded contact fields, and explicit-confirmation checks.
- It provides Photos asset/resource metadata retrieval and asset export only for one exact `photos:asset:v1:` handle selected from Photos metadata output.
- It provides Photos import planning as a non-mutating preview and Photos image/video import apply only after matching approval-token, source-file hash binding, and explicit-confirmation checks.
- It provides Reminder note retrieval only for one exact `reminders:reminder:eventkit:v1:` handle selected from EventKit metadata output.
- It provides Reminders future-change planning as a non-mutating preview and Reminders create/complete/due-date apply only after matching approval-token and explicit-confirmation checks.
- It provides iCloud Drive text-file content retrieval only for one exact `icloud:file:v1:` handle selected from filename metadata output.
- It provides iCloud Drive create/append-text planning as non-mutating preview and iCloud Drive create/append-text apply only after matching approval-token, exact opaque target handle, operation-specific create/append safety checks, and explicit-confirmation checks.
- It does not provide attachment retrieval, broad content search, arbitrary document/binary extraction, Contact note/image retrieval, generated Voice Memos transcription, broad Messages text search, broad Voice Memos transcript search, broad Reminder content search, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, or durable content caches.
- It does not mutate Mail beyond the approved create-draft apply gate, and it does not mutate Notes, Hide My Email, Gmail, iCloud, TCC, launchd, Codex config, or OpenClaw runtime state outside the approved apply gates. Reminders mutation is limited to the approved create/complete/due-date apply surface. iCloud Drive mutation is limited to approved create-text under an exact opaque parent folder handle and approved append-text under an exact opaque file handle plus expected current SHA-256. Calendar mutation is limited to approved timed-event create under an explicit target calendar title. Contacts mutation is limited to approved create-contact apply. Notes mutation is limited to approved create-note apply and append-text apply under an exact opaque note handle plus expected current SHA-256. Mail mutation is limited to approved save-only create-draft apply. Photos mutation is limited to approved image/video import apply.
- It does not use the Gmail connector, Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or any network mail service.

The v1.1 Mail content gate is documented in `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`. The v1.2/v1.3/v1.4/v1.5/v1.6/v1.7/v1.8/v1.9/v1.10 Messages, inferred Hide My Email, Voice Memos, Notes, iCloud Drive, Calendar, Contacts, Photos, Reminders, and broader Apple data expansion gate is documented in `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`. The v1.11 Reminders apply gate is documented in `docs/V1_11_REMINDERS_WRITE_DESIGN.md`. The v1.12 iCloud Drive create-text apply gate is documented in `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`. The v1.13 Calendar create-event apply gate is documented in `docs/V1_13_CALENDAR_WRITE_DESIGN.md`. The v1.14 Contacts create-contact apply gate is documented in `docs/V1_14_CONTACTS_WRITE_DESIGN.md`. The v1.15 Notes create-note apply gate is documented in `docs/V1_15_NOTES_WRITE_DESIGN.md`. The v1.16 Mail create-draft apply gate is documented in `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`. The v1.17 Photos import apply gate is documented in `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`. The v1.18 iCloud Drive append-text apply gate is documented in `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`. The v1.19 Notes append-text apply gate is documented in `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`. Any future attachment, indexing, connector fallback, broad content search, Contact update/delete/notes/image retrieval, Notes arbitrary update/delete/move/rich-text mutation, generated transcription, Messages send/mutation, Mail send/reply/forward/archive/move/delete/mark/flag/mailbox-account mutation, Photos edit/delete/album/metadata mutation, authoritative Hide My Email inventory, private iCloud web/API path, or additional mutation feature requires a separate design and approval gate.
