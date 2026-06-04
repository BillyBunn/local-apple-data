# Changelog

All notable public-release changes are tracked here.

## 0.1.0+codex.20260604120000 - 2026-06-04

### Added

- Approved Calendar create-event apply through `local-apple-data calendar apply` and MCP `calendar_apply_change`.
- Non-mutating Calendar create-event planning through `local-apple-data calendar plan` and MCP `calendar_plan_change`.
- Approval-token, explicit-confirmation, explicit-calendar-title, timed-event, idempotency, and read-back verification checks for Calendar create-event apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, and `calendar_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Calendar update, delete, recurrence, attendees, invitations, alarms, all-day events, default-calendar guessing, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604110000 - 2026-06-04

### Added

- Approved iCloud Drive create-text apply through `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`.
- Non-mutating iCloud Drive create-text planning through `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Approval-token, explicit-confirmation, exact-parent-handle, exclusive-create, idempotency, and read-back verification checks for iCloud Drive create-text apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` and `icloud_drive_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- iCloud Drive append, overwrite, rename, move, copy, delete, binary/document writes, broad folder writes, and raw path writes remain blocked by mutation gates.

## 0.1.0+codex.20260604100000 - 2026-06-04

### Added

- Approved Reminders apply through `local-apple-data reminders apply` and MCP `reminders_apply_change`.
- Apply support for Reminder create, complete, and due-date update through the Swift EventKit helper.
- Approval-token, explicit-confirmation, expected-state, idempotency, and read-back verification checks for Reminders apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` is the only non-read-only MCP tool and is annotated non-destructive, idempotent, and closed-world.
- All non-Reminders mutation surfaces remain blocked by mutation gates.

## 0.1.0+codex.20260604090000 - 2026-06-04

### Added

- Preview-only Reminders planning through `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Deterministic `reminders-plan:v1:` idempotency keys plus approval fingerprints for future apply-token binding.
- Synthetic adapter, CLI, MCP, runtime, redacted-log, surface-contract, and packaging coverage for Reminders planning.

### Security

- Reminders planning returns `mutation_applied:false` and `apply_available:false`, does not call EventKit, and does not mutate Reminders.
- Apply-capable Reminders tools remain absent.

## 0.1.0+codex.20260604080000 - 2026-06-04

### Added

- Public Reminders write design gate for future create/complete/due-date operations through EventKit, with preview/apply/read_back contract language and explicit approval requirements.
- Write-design gate auditor that fails when required write design docs drift or preview/apply/read_back-style CLI/MCP tools appear before approval.
- Release-readiness, CI, staged-public-tree, cross-agent sync, and path-redacted release receipt coverage for the write-design gate.

### Security

- The current release remains read-only. The new Reminders write document is design-only and exposes no mutating CLI or MCP tools.

## 0.1.0+codex.20260604074000 - 2026-06-04

### Added

- Read-only local Apple data CLI and stdio MCP server.
- Codex plugin manifest, bundled skill, and MCP runner script.
- Metadata-first search plus exact opaque-handle detail/content flows for Mail, Messages, inferred Hide My Email aliases, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive.
- Exact Mail plain-text content, Notes plain-text content, Reminder notes, Calendar details, Contact details, Photos asset/resource metadata, Messages bounded transcripts, Voice Memos existing embedded transcripts, iCloud Drive text-file content, and inferred Hide My Email selected alias detail.
- Synthetic unit, CLI, MCP, runtime, packaging, and redaction tests.
- macOS GitHub Actions workflow with tests, compile, Swift helper typechecks, runtime smoke, and redaction scan.
- Public capability matrix, mutation gates, publishing checklist, install guide, sample outputs, macOS support notes, security policy, and MIT license.
- Notes content pagination for long imported notes through `offset`, `content_total_chars`, and `next_offset`.
- Public release scan for local-path/operator-term leakage in publishable files.
- Release-readiness audit for required files, version/changelog consistency, public scan status, sanitized git-checkout prep, and git remote presence.
- Public release tree builder for staging the sanitized publishable file set outside the working repo.
- Public git-checkout preparer for creating a sanitized local GitHub-ready checkout without pushing, including optional initial local commit creation.
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw configuration, including compact server-object output for CLI registration commands.
- Optional Cursor MCP config verification in the cross-agent sync verifier, with explicit `--require-cursor` and `--cursor-config` controls.
- Exact-handle Photos asset export and Voice Memos `.m4a` export to caller-selected output directories without returning media bytes inline.
- Broad-surface health and doctor readiness covering Messages, Voice Memos, iCloud Drive, normalized per-surface summaries, and non-prompting access requirements in addition to Mail, Notes, and Reminders schema checks.
- Mutation-gate auditor that fails release readiness if write-like CLI/MCP surfaces appear before a mutation gate is intentionally approved.
- CI and staged-public-tree verification run the mutation-gate audit.
- Surface-contract auditor that fails release readiness if supported Apple data surfaces drift across MCP tools, CLI commands, health summaries, access requirements, and `docs/CAPABILITY_MATRIX.md`.
- CI and staged-public-tree verification run the surface-contract audit.
- Public contributor guide plus GitHub PR and issue templates that require synthetic fixtures, redaction checks, surface-contract checks, and explicit mutation-gate review for write-like changes.
- Path-redacted release receipt generator for reviewer handoff before a GitHub push or tag, with committed public checkout proof and CI coverage in source and staged public trees.
- Public ecosystem review comparing current Apple Notes, Messages, Voice Memos, iCloud Drive, and official Apple framework references against this plugin's broad-surface exact-handle architecture.

### Security

- The current release is read-only and local-only.
- Search is metadata-first; content/detail retrieval requires exact opaque handles returned by metadata tools.
- Runtime avoids Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, network mail services, telemetry, background indexing, and durable personal-content caches.

### Deferred

- Mutating tools.
- Attachments, broad content search, broad Messages text search, generated Voice Memos transcription, Contact notes/images, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API paths, and arbitrary binary/document extraction.
