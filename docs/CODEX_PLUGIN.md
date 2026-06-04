# Codex Plugin Packaging

This repo is a local Codex plugin root.

For the public support matrix, see `docs/CAPABILITY_MATRIX.md`. For installation, see `docs/INSTALL.md`. For future write/mutation gates, see `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, `docs/V1_11_REMINDERS_WRITE_DESIGN.md`, `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`, and `docs/V1_13_CALENDAR_WRITE_DESIGN.md`. For release readiness, see `docs/PUBLISHING.md`.

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

iCloud Drive create-text planning is non-mutating. `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. They do not resolve the parent handle or write iCloud Drive files.

iCloud Drive create-text apply is one approved mutation surface. `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` require the matching `icloud-drive-apply:v1:<approval_fingerprint>` token, explicit confirmation, an exact opaque parent folder handle, exclusive create, and read-back verification.

Calendar create-event planning is non-mutating. `local-apple-data calendar plan` and MCP `calendar_plan_change` return `mutation_applied:false`, `apply_available:true`, idempotency metadata, and an approval fingerprint for the approved apply gate. They do not call EventKit or write Calendar data.

Calendar create-event apply is one approved mutation surface. `local-apple-data calendar apply` and MCP `calendar_apply_change` require the matching `calendar-apply:v1:<approval_fingerprint>` token, explicit confirmation, an explicit target calendar title, EventKit apply, and read-back verification.

## Current Boundaries

- This package is local-only and metadata-first. The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create-text apply, and Calendar create-event apply.
- It provides Mail content retrieval only for one exact `mail:message:v2:` handle selected from metadata output.
- It provides Messages chat transcript retrieval only for one exact `messages:chat:v1:` handle selected from chat display-name metadata output.
- It provides inferred Hide My Email alias detail only for one exact `hide_my_email:alias:v1:` handle selected from masked local Mail address metadata output.
- It provides Voice Memos transcript retrieval and `.m4a` export only for one exact `voice_memos:recording:v1:` handle selected from title/filename metadata output.
- It provides Notes content retrieval only for one exact `notes:note:v2:` handle selected from metadata output, with bounded pagination for long imported notes.
- It provides Calendar event detail retrieval only for one exact `calendar:event:v1:` handle selected from metadata output.
- It provides Calendar create-event planning as a non-mutating preview and Calendar create-event apply only after matching approval-token, explicit target calendar title, timed-event inputs, and explicit-confirmation checks.
- It provides Contact detail retrieval only for one exact `contacts:contact:v1:` handle selected from Contacts metadata output.
- It provides Photos asset/resource metadata retrieval and asset export only for one exact `photos:asset:v1:` handle selected from Photos metadata output.
- It provides Reminder note retrieval only for one exact `reminders:reminder:eventkit:v1:` handle selected from EventKit metadata output.
- It provides Reminders future-change planning as a non-mutating preview and Reminders create/complete/due-date apply only after matching approval-token and explicit-confirmation checks.
- It provides iCloud Drive text-file content retrieval only for one exact `icloud:file:v1:` handle selected from filename metadata output.
- It provides iCloud Drive create-text planning as a non-mutating preview and iCloud Drive create-text apply only after matching approval-token, exact opaque parent folder handle, exclusive-create, and explicit-confirmation checks.
- It does not provide attachment retrieval, broad content search, arbitrary document/binary extraction, Contact note/image retrieval, generated Voice Memos transcription, broad Messages text search, broad Voice Memos transcript search, broad Reminder content search, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, or durable content caches.
- It does not mutate Mail, Notes, Hide My Email, Gmail, iCloud, TCC, launchd, Codex config, or OpenClaw runtime state outside the approved apply gates. Reminders mutation is limited to the approved create/complete/due-date apply surface. iCloud Drive mutation is limited to approved create-text apply under an exact opaque parent folder handle. Calendar mutation is limited to approved timed-event create under an explicit target calendar title.
- It does not use the Gmail connector, Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or any network mail service.

The v1.1 Mail content gate is documented in `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`. The v1.2/v1.3/v1.4/v1.5/v1.6/v1.7/v1.8/v1.9/v1.10 Messages, inferred Hide My Email, Voice Memos, Notes, iCloud Drive, Calendar, Contacts, Photos, Reminders, and broader Apple data expansion gate is documented in `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`. The v1.11 Reminders apply gate is documented in `docs/V1_11_REMINDERS_WRITE_DESIGN.md`. The v1.12 iCloud Drive create-text apply gate is documented in `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`. The v1.13 Calendar create-event apply gate is documented in `docs/V1_13_CALENDAR_WRITE_DESIGN.md`. Any future attachment, indexing, connector fallback, broad content search, Contact note/image retrieval, generated transcription, Messages send/mutation, authoritative Hide My Email inventory, private iCloud web/API path, or additional mutation feature requires a separate design and approval gate.
