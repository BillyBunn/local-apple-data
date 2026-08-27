# V1.106 Calendar Yearly Month Recurrence Write Design

Status: Apply-capable implementation.

This gate adds explicit yearly month recurrence selection to the existing bounded Calendar recurrence create and add-to-non-recurring-event update flow. It stays local-only, EventKit-only, exact-target gated, and finite-bound only.

Uses public EventKit `monthsOfTheYear`.

## Approved Shape

- `recurrence_year_months`: adapter/MCP list of integers or comma-separated adapter value.
- `--recurrence-year-months`: CLI comma-separated integers 1 through 12.
- Supported only with `recurrence_frequency:"yearly"`.
- Values are canonicalized to sorted unique integers.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered values. Adds `year_months:[...]` inside `preview.proposed.recurrence` only when explicit yearly months are requested. Binds year-months into the approval fingerprint and idempotency key. Non-yearly input, zero, out-of-range values, booleans, and string-list values return `invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded yearly `EKRecurrenceRule` with `monthsOfTheYear`. Create writes the recurrence on the new event. Update first proves the exact event is non-recurring and then adds the recurrence.

Read-back must prove the same bounded yearly month set. A mismatch returns the existing recurrence read-back warning path instead of claiming clean success. The deterministic verifier proof is fixture-backed; live EventKit proof from the current Codex process is host/TCC dependent.

## Verification

Fixture-backed runtime verifier proves direct create/update plan/apply read-back and MCP create/update plan plus invalid-token apply proof. Direct runtime proof checks `calendar_year_month_recurrence_plan_year_months`, `calendar_year_month_recurrence_apply_read_back_year_months`, `calendar_year_month_update_recurrence_plan_year_months`, and `calendar_year_month_update_recurrence_apply_read_back_year_months`. MCP runtime proof checks `mcp_calendar_year_month_recurrence_plan_year_months` and `mcp_calendar_year_month_update_recurrence_plan_year_months`, and rejects mismatched apply with `invalid_approval_token`.

Source tests cover adapter planning, invalid-shape refusal, EventKit helper binding/read-back strings, Swift CFBoolean-before-integer parsing guards, CLI parsing/apply binding, MCP plan/apply binding, public-surface audit expectations, and write-design audit coverage.

Live proof from this Codex process is currently blocked by Calendar TCC/access. `local-apple-data calendar calendars --json --include-default --limit 5` returns `calendar_access_unavailable`, and `local-apple-data calendar plan --json --operation create --use-default-calendar ... --recurrence-year-months 1,7,12` returns the same warning before mutation. No live event was created.

## Still Out Of Scope

- Mid-series recurrence clearing/replacement.
- Existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete.
- custom yearly recurrence rules beyond yearly BYMONTH/BYMONTH+nth-BYDAY/BYYEARDAY/BYWEEK.
- Combining yearly selectors, yearly day-of-month, nth-weekday, and set-position recurrence.
- Unbounded recurrence.
- attendee/invitation mutation.
- Travel time.
- Email/procedure alarms.
