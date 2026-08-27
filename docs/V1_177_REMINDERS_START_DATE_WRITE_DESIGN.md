# v1.177 Reminders Start Date Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder start-date set and clear on one exact local EventKit Reminder after plan-token and explicit-confirmation checks. `EKReminder` inherits `EKCalendarItem`, whose public `startDateComponents` accepts a date-only or timed start date; this gate mirrors the existing reminder due-date handling for that field. It approves a create-with-start-date operation that stamps a proposed start date at reminder creation and an update-start-date operation that sets or clears the start date on an existing reminder with exact expected current start-date binding.

Reminder recurrence create/update/clear is governed by `docs/V1_177_REMINDERS_RECURRENCE_WRITE_DESIGN.md`.

No notes, alarm, priority, URL, list, recurrence, attachment, image, sharing, rich-content, or bulk mutation is approved through this gate beyond the exact start-date set/clear surface described here.

## Approved Operations

- `create_with_start_date`
- `update_start_date`

CLI aliases are `create-with-start-date` and `update-start-date`.

## Inputs

- Exact opaque `reminders:reminder:eventkit:v1:` handle for `update_start_date`.
- Target `list_name` and `title` for `create_with_start_date`.
- `start_date` as a date-only `YYYY-MM-DD` value or a timezone-explicit ISO 8601 timestamp. An empty `start_date` on `update_start_date` clears the start date.
- `expected_start_date` for `update_start_date`, the exact current start-date state (empty means the reminder currently has no start date).
- `expected_title` for `update_start_date`.
- Matching approval token.
- Explicit `confirm_apply`.

The adapter normalizes a timed `start_date` to UTC second precision and preserves a date-only value as `YYYY-MM-DD`, mirroring due-date normalization. The start date must be on or before the due date when both are present; otherwise plan fails closed with `invalid_start_date`.

## Plan Contract

Planning is non-mutating. It validates the operation, exact handle shape for update, expected title, expected current start-date state for update, and the proposed start date, including the start-not-after-due check when a due date is present. It returns preview metadata, `mutation_applied:false`, `apply_available:true`, and an approval token whose fingerprint binds the exact proposed and expected state.

## Apply Contract

Apply recomputes the plan and requires the matching approval token plus explicit confirmation.

Before mutation on `update_start_date`, the adapter fetches the exact current Reminder through EventKit and refuses with `expected_state_mismatch` if the current start-date state no longer matches the approved `expected_start_date`. The Swift EventKit helper must recheck title, completion state, and the exact expected start-date state before mutation.

For a start-date set, apply writes `startDateComponents` and proves the result. Read-back for set is exact start-date proof. Success requires `read_back.start_date_verified:true`.

For a start-date clear, apply removes `startDateComponents`. Read-back for clear returns start-date absence proof. Success requires `read_back.start_date_absent_verified:true`.

## Runtime Synthetic Smoke

Runtime synthetic smoke covers direct CLI-style adapter flow and MCP wrapper flow:

- Create reminder with start date plan returns `status:"ok"`.
- Create reminder with start date apply returns `status:"ok"` and the exact proposed start date.
- Update start date set plan and apply return `status:"ok"` and `start_date_verified:true`.
- Update start date clear plan and apply return `status:"ok"` and `start_date_absent_verified:true`.

## Non-Goals

This release allows only exact-handle Reminder start-date set and clear plus recurrence create/update/clear through the plan/apply/read-back gates in this document and `docs/V1_177_REMINDERS_RECURRENCE_WRITE_DESIGN.md`. Alarm, attachment, image, sharing, rich-content, and bulk mutation remain blocked.
