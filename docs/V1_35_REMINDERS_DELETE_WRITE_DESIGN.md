# v1.35 Reminders Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This document approves exactly one destructive Reminders operation: delete one exact Reminder selected by an opaque `reminders:reminder:eventkit:v1:` handle returned by EventKit search. No bulk delete, list delete, account mutation, list move, attachment mutation, URL mutation, rich-content mutation, or permanent cross-surface cleanup is approved.

## Scope

Allowed:

- `local-apple-data reminders plan --operation delete`
- `reminders_plan_change(operation="delete")`
- `local-apple-data reminders apply --operation delete`
- `reminders_apply_change(operation="delete")`

Required delete inputs:

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- `expected_title` from a recent read-only result.
- `expected_completed` from a recent read-only result.
- `expected_priority` from a recent read-only result.
- `expected_notes_sha256` from exact `local-apple-data reminders content` / `reminders_get_content`.
- Matching `reminders-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Out of scope:

- Raw EventKit identifiers.
- Raw SQLite row IDs or legacy `reminders:reminder:v1:` handles.
- Delete by title, query, list, account, due date, or broad filter.
- Bulk delete.
- Delete combined with update, move, completion, or notes edits.
- List/account deletion or management.
- Reminder attachment, URL, image, or rich-content mutation.
- Any UI automation, browser/iCloud path, keychain path, external connector, or network service.

## Safety Contract

Plan is non-mutating. It validates the exact handle and required expected fields, returns `mutation_applied:false`, produces an idempotency key, and creates an approval fingerprint over the exact target and proposed delete.

Apply recomputes the plan, requires the matching approval token, requires explicit confirmation, resolves the opaque handle through EventKit search, and refuses absent targets before apply with `mutation_applied:false`.

Apply must verify current notes state before delete by reading the selected reminder through EventKit and comparing the normalized notes SHA-256 to `expected_notes_sha256`. If the current notes hash differs, apply must refuse with `current_notes_changed` before calling the delete helper.

The Swift EventKit helper must recheck title, completion state, and priority before deleting. It must call EventKit removal only for the resolved reminder identifier. It must not expose the raw EventKit identifier in public output.

Read-back for delete is absence proof. A successful delete result must include:

- `mutation_applied:true`
- `operation:"delete"`
- `read_back.deleted:true`
- `read_back.verified_absent:true`

If EventKit removal returns success but absence cannot be proven, the operation must return `apply_unknown` with `mutation_applied:true` and `read_back_unavailable`.

## MCP Annotation

Because MCP tool annotations are static per tool, adding `delete` to `reminders_apply_change` makes `reminders_apply_change` destructive at the tool descriptor level. The tool must use non-read-only, destructive, non-idempotent, closed-world MCP annotations.

Non-delete Reminder apply operations remain approval-token gated and exact-targeted, but the public descriptor must reflect the most dangerous operation the tool can perform.

## Idempotency

Delete is not idempotent before apply without a durable operation ledger. If the target is absent before apply, the tool must return not found / target absent and `mutation_applied:false`; it must not pretend that a previous delete succeeded.

After EventKit removal, the only accepted success proof is absence of the same resolved EventKit identifier. There is no durable personal-content operation ledger in this release.

## Synthetic Tests Required

Required tests:

- Plan success for delete with exact handle, expected title, expected completed, expected priority, and expected notes SHA-256.
- Plan refusal for raw identifiers or missing expected fields.
- Apply refusal before helper call when confirmation or approval token is missing.
- Apply refusal before helper call when current notes SHA-256 differs.
- Apply success using mocked EventKit helper responses and read-back absence proof.
- Apply unknown when delete succeeds but absence proof is missing.
- Redaction checks proving raw EventKit identifiers and notes do not appear in public output.
- MCP annotation tests proving `reminders_apply_change` is destructive and non-idempotent.
- Runtime synthetic smoke proving the delete adapter path without touching live Reminders.

## Current Release Gate

This release allows only exact-handle Reminder delete through the plan/apply/read-back absence-proof gate above. Reminder bulk delete, list/account delete or management, list moves, attachments, images, rich-content mutation, and any delete path outside `reminders apply --operation delete` / `reminders_apply_change(operation="delete")` remain blocked. The blanket URL blocker in this historical design is superseded only for exact URL update/clear by `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`; all other Reminder URL mutation remains blocked.
