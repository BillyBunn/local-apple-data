# V1.123 Calendar Set-Position Recurrence Write Design

Status: Apply-capable implementation.

This gate adds explicit Calendar set-position recurrence selection to the
existing bounded recurrence create and add-to-non-recurring-event update flow.
It stays local-only, EventKit-only, exact-target gated, and finite bounded.

Uses public EventKit `setPositions` on `EKRecurrenceRule`. Apple SDK headers
state that set positions are valid only with another recurrence selector and
that values may be 1 through 366 or -1 through -366.

This is the Calendar BYSETPOS recurrence gate.

## Approved Shape

- `recurrence_set_positions`: adapter/MCP list of integers or comma-separated
  adapter value.
- `--recurrence-set-positions`: CLI comma-separated integers from -366 through
  -1 or 1 through 366.
- Requires another recurrence selector such as `recurrence_weekdays`,
  `recurrence_month_days`, `recurrence_month_weekdays`,
  `recurrence_year_months`, `recurrence_year_month_days`,
  `recurrence_year_month_weekdays`, `recurrence_year_days`, or
  `recurrence_year_weeks`.
- Supported only inside existing daily/weekly/monthly/yearly finite recurrence
  create and add-to-non-recurring-event update validation.
- Values are canonicalized to sorted unique integers.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite
  end bound: `recurrence_count` from 2 through 52 or timezone
  `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered values. Adds
`set_positions:[...]` inside `preview.proposed.recurrence` only when explicit
set-position selection is requested. Binds set positions into the approval
fingerprint and idempotency key. Missing selector, zero, out-of-range values,
booleans, string-list values, and otherwise invalid recurrence shapes return
`invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded
`EKRecurrenceRule` with `setPositions` plus the approved selector. Create writes
the recurrence on the new event. Update first proves the exact event is
non-recurring and then adds the recurrence.

Read-back must prove the same bounded set-position list and the same selector.
A mismatch returns the existing recurrence read-back warning path instead of
claiming clean success. The deterministic verifier proof is fixture-backed;
live EventKit proof from the current Codex process remains host/TCC dependent.

## Verification

Fixture-backed runtime verifier proves direct create/apply read-back and MCP
plan plus invalid-token apply proof for set-position recurrence. Direct runtime
proof checks `calendar_set_positions_recurrence_plan_status`,
`calendar_set_positions_recurrence_plan_weekdays`,
`calendar_set_positions_recurrence_plan_set_positions`,
`calendar_set_positions_recurrence_apply_status`,
`calendar_set_positions_recurrence_apply_read_back_weekdays`, and
`calendar_set_positions_recurrence_apply_read_back_set_positions`. MCP runtime
proof checks `mcp_calendar_set_positions_recurrence_plan_status`,
`mcp_calendar_set_positions_recurrence_plan_weekdays`,
`mcp_calendar_set_positions_recurrence_plan_set_positions`,
`mcp_calendar_set_positions_recurrence_apply_status`, and
`mcp_calendar_set_positions_recurrence_apply_warning`.

Source tests cover adapter planning, selector-required refusal, invalid-shape
refusal, EventKit helper binding/read-back strings, Swift CFBoolean-before-
integer parsing guards, CLI parsing/apply binding, MCP plan/apply binding,
runtime verifier receipts, and write-design audit coverage.

Named regressions include
`test_plan_calendar_change_create_set_positions_recurrence_binds_preview`,
`test_plan_calendar_change_set_positions_requires_recurrence_selector`,
`test_apply_calendar_change_creates_set_positions_recurrence_and_reads_back`,
`test_apply_calendar_change_updates_set_positions_recurrence_and_reads_back`,
and
`test_mcp_calendar_set_positions_recurrence_plan_and_apply_bind_without_eventkit`.

## Audit Anchors

- `recurrence_set_positions`: adapter/MCP list of integers or comma-separated adapter value.
- `--recurrence-set-positions`: CLI comma-separated integers from -366 through -1 or 1 through 366.
- Supported only inside existing daily/weekly/monthly/yearly finite recurrence create and add-to-non-recurring-event update validation.
- Adds `set_positions:[...]` inside `preview.proposed.recurrence`.
- Binds set positions into the approval fingerprint and idempotency key.
- Missing selector, zero, out-of-range values, booleans, string-list values are rejected before mutation.
- Apply writes one bounded `EKRecurrenceRule` with `setPositions` plus the approved selector.
- Fixture-backed runtime verifier proves direct create/apply read-back and MCP plan plus invalid-token apply proof for set-position recurrence.

## Still Out Of Scope

- Mid-series recurrence clearing/replacement.
- Existing-recurring-event recurrence replacement beyond first-visible clear
  and selected/future-span/whole-series occurrence delete.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Non-allow-listed URLs.
- Calendar creation/deletion.
- Account management.
