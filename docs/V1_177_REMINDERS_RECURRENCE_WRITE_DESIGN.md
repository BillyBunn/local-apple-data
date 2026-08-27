# v1.177 Reminders Recurrence Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This gate approves exact Reminder recurrence create, replace, and clear on one exact local EventKit Reminder after plan-token and explicit-confirmation checks. `EKReminder` inherits `EKCalendarItem`, whose public `recurrenceRules` accept the same `EKRecurrenceRule` shapes as calendar events. This gate reuses the exact Calendar recurrence payload contract and the shared `_normalize_recurrence` builder rather than forking a second recurrence builder; the Swift helper reuses the same `applyRecurrence`, `recurrencePayload`, and `recurrenceMatches` machinery on the common `EKCalendarItem` type. It approves a create-with-recurrence operation that stamps a proposed recurrence at reminder creation and an update-recurrence operation that adds, replaces, or clears the recurrence on an existing reminder with exact expected recurrence-shape binding.

Reminder start-date set/clear is governed by `docs/V1_177_REMINDERS_START_DATE_WRITE_DESIGN.md`.

## Approved Operations

- `create_with_recurrence`
- `update_recurrence`

CLI aliases are `create-with-recurrence` and `update-recurrence`.

## Inputs

- Exact opaque `reminders:reminder:eventkit:v1:` handle for `update_recurrence`.
- Target `list_name` and `title` for `create_with_recurrence`.
- Recurrence fields identical to Calendar recurrence: `recurrence_frequency`, `recurrence_interval`, `recurrence_count`, `recurrence_end_date`, `recurrence_unbounded`, `recurrence_weekdays`, `recurrence_month_days`, `recurrence_month_weekdays`, `recurrence_year_months`, `recurrence_year_month_days`, `recurrence_year_month_weekdays`, `recurrence_year_days`, `recurrence_year_weeks`, and `recurrence_set_positions`.
- `clear_recurrence:true` to clear the recurrence on `update_recurrence`, mutually exclusive with recurrence fields.
- `expected_recurrence_present` and, when present, the exact `expected_recurrence` shape for `update_recurrence`.
- `expected_title` for `update_recurrence`.
- A due date anchor (required) when a recurrence is present. EventKit requires a due date for a recurring reminder — Reminders.app only enables repeat once a due date is set, and a start-date-only anchor is dropped by EventKit — so a recurring reminder must have a due date present on the reminder for `update_recurrence` or proposed for `create_with_recurrence`. The adapter enforces this with `missing_required_field` before recurrence-shape gates, matching the calendar anchor requirement. Start dates are never a recurrence anchor and recurrence operations never carry a `start_date`.
- Matching approval token.
- Explicit `confirm_apply`.

Recurrence fields are validated by the same bounds as Calendar recurrence: `recurrence_interval` from 1 through 4, exactly one recurrence bound using either `recurrence_count` from 2 through 52, a timezone `recurrence_end_date` within 3650 days of the reminder due date anchor, or explicit `recurrence_unbounded:true`, plus the shared weekly/monthly/yearly selector constraints. No custom recurrence shapes beyond the approved selector-backed EventKit rules are approved.

## Plan Contract

Planning is non-mutating. It validates the operation, exact handle shape for update, expected title, the anchor requirement, and the recurrence shape through the shared `_normalize_recurrence` builder. For update it also binds `expected_recurrence_present` and the exact `expected_recurrence` shape. `missing_required_field` anchor gates are ordered before recurrence shape gates. It returns preview metadata, `mutation_applied:false`, `apply_available:true`, and an approval token whose fingerprint binds the exact proposed and expected recurrence state.

## Apply Contract

Apply recomputes the plan and requires the matching approval token plus explicit confirmation.

Before mutation on `update_recurrence`, the adapter fetches the exact current Reminder recurrence shape through EventKit and refuses with `stale_recurrence_state` if the current recurrence shape no longer matches the approved `expected_recurrence`. The Swift EventKit helper must recheck title, completion state, and the exact expected recurrence shape before mutation.

For a recurrence create or replace, apply writes a single `EKRecurrenceRule` built by the shared rule builder. Read-back for create or replace is exact recurrence-shape proof. Success requires `read_back.recurrence_verified:true`.

For a recurrence clear, apply removes `recurrenceRules`. Read-back for clear returns recurrence absence proof. Success requires `read_back.recurrence_cleared_verified:true`.

No raw recurrence or date state beyond the existing recurrence-shape contract is returned in previews, read-back, warnings, logs, or runtime summaries.

## Runtime Synthetic Smoke

Runtime synthetic smoke covers direct CLI-style adapter flow and MCP wrapper flow:

- Create reminder with recurrence plan returns `status:"ok"`.
- Create reminder with recurrence apply returns `status:"ok"` and the exact recurrence shape.
- Update recurrence add/replace plan and apply return `status:"ok"` and `recurrence_verified:true`.
- Update recurrence clear plan and apply return `status:"ok"` and `recurrence_cleared_verified:true`.
- A recurrence without a due date anchor is rejected with `missing_required_field`.

## Non-Goals

This release allows only exact-handle Reminder recurrence create/update/clear plus start-date set and clear through the plan/apply/read-back gates in this document and `docs/V1_177_REMINDERS_START_DATE_WRITE_DESIGN.md`. Custom recurrence shapes beyond the approved selector-backed EventKit rules, implicit unbounded recurrence, alarm, attachment, image, sharing, rich-content, and bulk mutation remain blocked.
