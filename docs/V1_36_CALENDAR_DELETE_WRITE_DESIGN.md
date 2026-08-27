# v1.36 Calendar Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document approves exactly one destructive Calendar operation: delete one exact timed or all-day event selected by an opaque `calendar:event:v1:` handle returned by the Calendar metadata flow. No bulk delete, calendar deletion, move, recurrence mutation, attendee/invitation mutation, URL mutation, date-only/time-zone inference, or default-calendar guessing is approved. Explicit all-day delete support is governed by this gate as extended by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`; exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.

## Scope

Allowed:

- `local-apple-data calendar plan --operation delete`
- `calendar plan --operation delete`
- `calendar_plan_change(operation="delete")`
- `local-apple-data calendar apply --operation delete`
- `calendar_apply_change(operation="delete")`

Required delete inputs:

- Exact opaque `calendar:event:v1:` handle.
- `expected_title` from a recent read-only result.
- `expected_calendar_title` from a recent read-only result.
- `expected_start_date` from a recent read-only result.
- `expected_end_date` from a recent read-only result.
- `expected_all_day` from a recent read-only result.
- `expected_location` from exact event detail when a location is present.
- `expected_notes` from exact event detail when notes are present.
- Matching `calendar-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Out of scope:

- Raw EventKit identifiers.
- Raw SQLite row IDs or fabricated handles.
- Delete by title, query, calendar, date range, attendee, location, or broad filter.
- Bulk delete.
- Delete combined with update, move, recurrence, attendee, invitation, URL, availability, travel-time, default-calendar guessing, or date-only/time-zone inference.
- Calendar/account deletion or management.
- Any UI automation, browser/iCloud path, keychain path, external connector, or network service.

## Safety Contract

Plan is non-mutating. It validates the exact handle and required expected fields, returns `mutation_applied:false`, produces an idempotency key, and creates an approval fingerprint over the exact target, expected current state, and proposed delete.

Apply recomputes the plan, requires the matching approval token, requires explicit confirmation, resolves the opaque handle through the bounded EventKit scan, and refuses absent targets before apply with `mutation_applied:false`.

The Swift EventKit helper must recheck title, calendar title, start/end time, all-day state, location, notes, and exact alarm offsets before deleting. It must refuse recurring or attendee-bearing events. It must call EventKit removal only for the resolved event identifier with `span: .thisEvent`, and it must not expose the raw EventKit identifier in public output. Exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.

Read-back for delete is absence proof. A successful delete result must include:

- `mutation_applied:true`
- `operation:"delete"`
- `read_back.deleted:true`
- `read_back.verified_absent:true`

If EventKit removal returns success but absence cannot be proven, the operation must return `apply_unknown` with `mutation_applied:true` and `read_back_unavailable`.

## MCP Annotation

Because MCP tool annotations are static per tool, adding `delete` to `calendar_apply_change` makes `calendar_apply_change` destructive at the tool descriptor level. The tool must use non-read-only, destructive, non-idempotent, closed-world MCP annotations.

Non-delete Calendar apply operations remain approval-token gated and exact-targeted, but the public descriptor must reflect the most dangerous operation the tool can perform.

## Idempotency

Delete is not idempotent before apply without a durable operation ledger. If the target is absent before apply, the tool must return not found / target absent and `mutation_applied:false`; it must not pretend that a previous delete succeeded.

After EventKit removal, the only accepted success proof is absence of the same resolved EventKit identifier. There is no durable personal-content operation ledger in this release.

## Synthetic Tests Required

Required tests:

- Plan success for delete with exact handle and expected title, calendar, start/end time, location, and notes.
- Plan refusal for raw identifiers or missing expected fields.
- Apply refusal before helper call when confirmation or approval token is missing.
- Apply success using mocked EventKit helper responses and read-back absence proof.
- Apply unknown when delete succeeds but absence proof is missing.
- Redaction checks proving raw EventKit identifiers and event notes do not appear in public output.
- MCP annotation tests proving `calendar_apply_change` is destructive and non-idempotent.
- Runtime synthetic smoke proving the delete adapter path without touching live Calendar.

## Current Release Gate

This release allows only exact-handle Calendar delete through the plan/apply/read-back absence-proof gate above. Calendar explicit all-day delete support is governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`; exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`. Calendar move, recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, default-calendar guessing, date-only/time-zone inference, calendar/account management, bulk operations, and any delete path outside `calendar apply --operation delete` / `calendar_apply_change(operation="delete")` remain blocked.
